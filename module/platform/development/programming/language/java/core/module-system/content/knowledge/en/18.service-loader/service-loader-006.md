# Failing providers and ServiceConfigurationError

## 1. Objectives

In Java's Service Provider Interface (SPI), an application knows about a service type, while other libraries or modules supply implementation classes (providers). **ServiceLoader** discovers and instantiates providers at runtime. This mechanism allows an application to be extended with plugins without depending directly on individual implementation classes.

This lesson explains what happens when a provider is misdeclared, cannot be loaded, or cannot be instantiated; how **ServiceConfigurationError** arises; and how to trace the cause in applications using the classpath or the Java Platform Module System (JPMS).

After this lesson, you will be able to:
- Distinguish between the case where no provider is found and the case where a provider fails.
- Identify when ServiceLoader actually locates and instantiates providers.
- Find errors in SPI configuration files, module-info.java, classpath, module path, and class loaders.
- Catch and handle ServiceConfigurationError at the right application boundary.

## 2. How does ServiceLoader locate providers?

A service is usually an interface or an abstract class. A provider is a concrete class implementing or extending that service. For example, an application declares a Codec service; other libraries may supply GzipCodec, ZipCodec, or another codec.

~~~java
package com.example.spi;

public interface Codec {
    String name();
    byte[] encode(byte[] input);
}
~~~

The application asks ServiceLoader to find providers:

~~~java
ServiceLoader<Codec> codecs = ServiceLoader.load(Codec.class);

for (Codec codec : codecs) {
    System.out.println(codec.name());
}
~~~

The **ServiceLoader.load(...)** call creates a ServiceLoader. It typically does not read all configuration or instantiate all providers right at this line. Discovery, class loading, and object creation happen lazily as the application iterates the iterator or processes the stream.

Therefore, an error can occur in the loop, at **hasNext()** or **next()**, even though the line calling **load()** succeeded normally. With streams, an error can occur at whichever operation causes a provider to be located or loaded; calling **Provider.get()** instantiates the provider.

Two situations must be distinguished:

- **No providers:** this is a valid outcome. The iterator has no elements; **findFirst()** returns **Optional.empty()**. No ServiceConfigurationError is thrown merely because no provider was found.
- **A provider declaration exists but cannot be processed:** this is a configuration, loading, or instantiation error. ServiceLoader can throw ServiceConfigurationError.

## 3. What is ServiceConfigurationError?

**java.util.ServiceConfigurationError** is a subclass of **java.lang.Error**. The JDK throws this error when there is a problem locating, loading, or instantiating a service provider.

Because it extends **Error**, code that only catches **Exception** will not catch ServiceConfigurationError. When an application needs to handle SPI errors at a clear boundary, catch this exact error type:

~~~java
try {
    for (Codec codec : ServiceLoader.load(Codec.class)) {
        System.out.println(codec.name());
    }
} catch (ServiceConfigurationError error) {
    error.printStackTrace();
    throw new IllegalStateException(
        "Unable to load a Codec provider", error
    );
}
~~~

Do not catch every **Error** or **Throwable** just to ignore failures. A broken provider can leave the application missing critical functionality or produce unreliable results. Decide explicitly whether the application should stop, fall back to a default implementation, or disable an optional plugin.

ServiceConfigurationError has a constructor taking a message and a constructor taking both a message and a cause. When the error has an underlying cause, preserve the exception chain by logging the full stack trace or inspecting **getCause()**. The message often helps identify the service/provider name, while the cause can pinpoint a specific failure such as a constructor throwing an exception or a missing dependency.

## 4. Common causes on the classpath

For applications using the classpath, providers are registered via a provider-configuration file in the **META-INF/services** directory.

The file name is the fully qualified name of the service. Each line contains a fully qualified provider class name (binary name), for example:

~~~text
META-INF/services/com.example.spi.Codec
~~~

Contents:

~~~text
com.example.impl.GzipCodec
com.example.impl.ZipCodec
~~~

A provider can reside in the same JAR as the configuration file or in another JAR, as long as the class loader used to locate providers can see that class.

Common mistakes:

1. **Wrong configuration file name or location.** The file name must match the fully qualified name of the service, and the file must live under META-INF/services at the JAR's resource root.
2. **Wrong provider class name.** The configuration line must be the fully qualified class name, case-sensitive; do not write a .java file name or directory path.
3. **Malformed configuration file.** The file must use UTF-8. Each provider sits on one line; leading and trailing spaces/tabs, blank lines, and comments starting with # are ignored. Duplicate declarations are ignored.
4. **Unable to load provider class.** The JAR containing the provider is missing from the runtime classpath, the class name is wrong, or a dependency required by the provider is missing.
5. **Provider does not implement the service.** The declared class must actually be assignable to the service type ServiceLoader is using.
6. **No valid provider constructor.** A provider on the classpath must be a public class, not an inner class, and have a public no-argument constructor so ServiceLoader can instantiate it.

Example of a valid implementation:

~~~java
package com.example.impl;

import com.example.spi.Codec;

public final class GzipCodec implements Codec {
    public GzipCodec() {
        // Initialize necessary provider state.
    }

    @Override
    public String name() {
        return "gzip";
    }

    @Override
    public byte[] encode(byte[] input) {
        // Illustration: implement the compression algorithm here.
        return input;
    }
}
~~~

If the configuration file lists **com.example.impl.GzipCodec** but the class actually resides in another package, ServiceLoader cannot load the provider. If the class is found but does not implement the Codec interface properly, ServiceLoader also reports an error.

A subtle error is when an application packages two copies of the service API in different class loaders. Two classes with the same fully qualified name are still two distinct types if defined by two different class loaders. The provider may implement the Codec copy it sees, while the application expects another Codec copy; the type check then fails. Ensure the service API is shared consistently between the application and plugins.

## 5. Common causes on the module path

With JPMS, modules declare service relationships using two directives: **uses** on the application consuming the service and **provides ... with ...** on the module supplying the provider.

Example application module:

~~~java
module com.example.app {
    requires com.example.spi;
    uses com.example.spi.Codec;
}
~~~

Example provider module:

~~~java
module com.example.codec.gzip {
    requires com.example.spi;
    provides com.example.spi.Codec
        with com.example.codec.gzip.GzipCodec;
}
~~~

In this example:
- The application module needs to read the module publishing the service API and declare **uses** for the service it loads via ServiceLoader.
- The provider module needs to read the module containing the service API and declare the provider in **provides**.
- The provider module must be included in the appropriate deployment configuration/module path so the runtime can find it.

If the application is in a named module but lacks the **uses** directive, calling ServiceLoader can throw ServiceConfigurationError right when creating the loader. This is a case where the error can appear earlier than errors from a provider's constructor.

### Provider constructor and provider method

A provider in a named module has two ways to be instantiated by ServiceLoader.

**Option 1: the provider class implements the service and has a public no-argument constructor.**

~~~java
package com.example.codec.gzip;

import com.example.spi.Codec;

public final class GzipCodec implements Codec {
    public GzipCodec() {}

    @Override
    public String name() {
        return "gzip";
    }

    @Override
    public byte[] encode(byte[] input) {
        return input;
    }
}
~~~

Module declaration:

~~~java
provides com.example.spi.Codec
    with com.example.codec.gzip.GzipCodec;
~~~

**Option 2: the provider class has a public static provider() method.**

~~~java
package com.example.codec.gzip;

import com.example.spi.Codec;

public final class GzipCodecProvider {
    public static Codec provider() {
        return new GzipCodec();
    }
}
~~~

Module declaration:

~~~java
provides com.example.spi.Codec
    with com.example.codec.gzip.GzipCodecProvider;
~~~

With a provider method, the provider class does not need to implement Codec itself; the **provider()** method must be public, static, parameterless, and return a type assignable to Codec. ServiceLoader calls that method to obtain an instance. If the method returns null or throws an exception, ServiceConfigurationError can be raised.

Common module errors include: the provider class cannot be loaded; the provider class neither implements the service nor has a valid provider method; the provider method returns an incompatible type; there are multiple public static no-arg methods named provider; or the constructor/provider method throws an exception.

Note: a provider packaged as an automatic module on the module path must have a provider constructor; registration via a provider method is not supported for automatic modules.

## 6. Why do errors only appear when iterating an iterator or stream?

ServiceLoader deliberately defers work so it does not have to load and instantiate every provider as soon as the application calls **load()**.

With an iterator, both **hasNext()** and **next()** can throw ServiceConfigurationError. An enhanced-for loop calls these methods under the hood as well, so the error often surfaces right at the loop line.

~~~java
ServiceLoader<Codec> loader = ServiceLoader.load(Codec.class);

// This line creates the loader; it does not mean all providers are instantiated yet.
Iterator<Codec> iterator = loader.iterator();

while (iterator.hasNext()) {
    Codec codec = iterator.next();
    System.out.println(codec.name());
}
~~~

With a stream, intermediate operations generally remain lazy. Errors are thrown when a processing operation causes ServiceLoader to locate or load providers. In the following example, **Provider.get()** creates the instance:

~~~java
ServiceLoader<Codec> loader = ServiceLoader.load(Codec.class);

loader.stream()
    .map(ServiceLoader.Provider::get)
    .forEach(codec -> System.out.println(codec.name()));
~~~

Streams allow inspecting the provider type via **Provider.type()** before creating an instance. This is useful when the application needs to filter providers by annotation or metadata. However, streams do not eliminate configuration errors: locating/loading a provider or calling **get()** can still throw ServiceConfigurationError.

Once an iterator has thrown an error, subsequent calls will make a best-effort attempt to locate the next provider; recovery is not guaranteed. Do not assume that skipping one error lets you safely continue with all remaining providers.

## 7. How to handle errors in an application

For an application that requires all providers to function, the safe approach is usually to log completely and halt initialization of the component depending on the SPI:

~~~java
public static List<Codec> loadCodecs() {
    List<Codec> result = new ArrayList<>();

    try {
        for (Codec codec : ServiceLoader.load(Codec.class)) {
            result.add(codec);
        }
    } catch (ServiceConfigurationError error) {
        // Preserve the stack trace and cause to locate the failing provider.
        error.printStackTrace();
        throw new IllegalStateException(
            "Codec SPI failed to initialize completely", error
        );
    }

    return result;
}
~~~

For applications with optional plugins, define a clear policy when a provider fails: disable that plugin, show the error status to the operator, or stop the application if the plugin is mandatory. Do not silently treat a failing provider as nonexistent, as that can leave the application running with missing features without anyone noticing.

If you need to diagnose instantiation failures, log the provider being processed, the message, stack trace, and cause. If using **ServiceLoader.stream()**, you can inspect **Provider.type()** before calling **Provider.get()**; keep in mind that both provider lookup and instance creation can raise errors.

## 8. Diagnostic workflow

When encountering ServiceConfigurationError, follow this sequence:

1. **Read the message and stack trace.** Identify which service is being loaded, which provider is mentioned, and whether the failure occurs during class lookup or instance creation.
2. **Check the cause.** If the cause is an exception thrown by the constructor/provider method, fix the initialization bug inside the provider first.
3. **Identify the deployment mode.** Is the application running providers from the classpath, an automatic module, or a named module? Each mode has different registration and instantiation rules.
4. **Inspect classpath configuration.** Open the JAR and confirm the exact file META-INF/services/<fully qualified service name> exists; verify each provider line and ensure the classes and their dependencies are present at runtime.
5. **Inspect module-info.java.** The application must have uses; the provider module must have provides ... with ...; modules must be able to read the service API.
6. **Check the constructor/provider method.** For a constructor, verify the provider class is public, not an inner class, implements the service properly, and has a public no-argument constructor. For a provider method, verify there is only one public static method named provider, with no parameters and a compatible return type.
7. **Check the class loader.** ServiceLoader.load(Service.class) uses the current thread's context class loader. In plugin applications, application servers, or test environments, confirm that loader can see both the service API and the provider.
8. **Try instantiating the provider independently.** Once the provider class is identified, run its constructor or provider method in a small test to separate initialization bugs from SPI discovery bugs.

Some symptoms and checks:

| Symptom | Possible cause | Resolution |
|---|---|---|
| Provider class not found | Wrong class name, missing JAR, or wrong runtime classpath/module path | Check fully qualified name, deployed artifacts, and dependencies |
| Provider is not a subtype of service | Wrong class declared or two copies of the service API defined by different class loaders | Check implements/extends and where the service API is loaded from |
| Missing provider constructor | No public no-argument constructor | Add an appropriate constructor or use a provider method in a named module |
| Module does not declare uses | Consumer module calls ServiceLoader but lacks the directive | Add uses for the right service |
| Provider method error | Wrong return type, returns null, or throws an exception | Fix the provider() method and its initialization logic |
| Error appears at iterator.hasNext()/next() | Provider discovery is lazy | Read the stack trace at the iteration point; inspect config files and provider classes |
| Works in IDE but fails when packaged | SPI resource or JAR was not included in the runtime artifact | Inspect the final JAR contents and runtime classpath/module path |

## 9. Class loaders and important notes

The call:

~~~java
ServiceLoader.load(Codec.class)
~~~

is equivalent to using the current thread's context class loader:

~~~java
ServiceLoader.load(
    Codec.class,
    Thread.currentThread().getContextClassLoader()
);
~~~

If the deployment environment has multiple class loaders, the default loader might not see the providers the application expects. You can pass a loader explicitly:

~~~java
ClassLoader providerLoader = Thread.currentThread().getContextClassLoader();
ServiceLoader<Codec> loader =
    ServiceLoader.load(Codec.class, providerLoader);
~~~

Choose a class loader that can actually see both the service API and the provider. Do not assume **Codec.class.getClassLoader()** is always right: providers might live in a child class loader, while the service API must be shared from a parent loader.

**ServiceLoader.loadInstalled(...)** uses the platform class loader. It is meant for providers installed in the runtime and will ignore providers only on the application classpath/module path; therefore, do not use it as a general replacement for **load(...)**.

ServiceLoader caches loaded providers. **reload()** clears the cache so subsequent iterations locate providers again; it does not fix broken configuration files, add missing JARs, or repair faulty constructors. A ServiceLoader instance is also not safe for concurrent use by multiple threads.

## 10. Pitfalls to avoid

- **Confusing no providers with a broken provider:** having no providers is a valid case; a misdeclared or uninstantiable provider produces an error.
- **Assuming load() has already finished instantiating providers:** providers are located and instantiated lazily; errors often surface while iterating an iterator or processing a stream.
- **Catching only Exception:** ServiceConfigurationError extends Error, so catch Exception will not catch it.
- **Catching all Errors to ignore them:** this can hide severe deployment bugs. Only catch ServiceConfigurationError where there is a clear recovery policy.
- **Checking only source code:** META-INF/services files, module-info.java, and runtime JAR contents all matter.
- **Using reload() to fix configuration bugs:** reload only clears the cache; it does not fix the root cause.
- **Forgetting about class loaders:** the same service name does not mean the same Class if two loaders define two separate copies.

## 11. Self-check

**1. ServiceLoader.load(Codec.class) succeeds, but the for-each loop throws ServiceConfigurationError. Why?**

Because provider discovery and instantiation are lazy. The error may only appear when the iterator calls hasNext() or next() during iteration.

**2. Is the absence of a META-INF/services file for a service necessarily an error?**

No. If no provider is found, the iterator can be empty and findFirst() returns Optional.empty(). An error occurs when configuration/providers exist but cannot be validly read, loaded, or instantiated.

**3. Why does catch (Exception e) fail to catch ServiceConfigurationError?**

Because ServiceConfigurationError extends java.lang.Error, not Exception. If you need to handle SPI errors, catch ServiceConfigurationError specifically.

**4. An application running in a named module calls ServiceLoader but lacks uses. Where must the fix be made?**

Add the uses directive for the service to module-info.java of the consuming module. Also ensure that module can read the module publishing the service API.

## 12. Key takeaways

ServiceConfigurationError signals that ServiceLoader could not complete locating, loading, or instantiating a provider. Identify the provider and the failing step first, then check the classpath or module path configuration, service type, constructor/provider method, and class loader. Having no providers is a valid outcome; a declared but broken provider is a problem that needs explicit handling.

## References

- [ServiceLoader — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html)
- [ServiceConfigurationError — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceConfigurationError.html)
