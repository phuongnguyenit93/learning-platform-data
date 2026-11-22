# ServiceLoader.Provider type

## Objectives

After this lesson, you will be able to:

- Explain what `ServiceLoader.Provider<S>` represents in the ServiceLoader mechanism.
- Distinguish between `type()` and `get()`.
- Use `ServiceLoader.stream()` to filter or sort providers based on metadata before creating instances.
- Understand how `Provider.type()` behaves when a module uses a provider factory method.

## 1. Where does ServiceLoader.Provider live?

Since Java 9, `java.util.ServiceLoader` provides the nested interface `ServiceLoader.Provider<S>`. `S` is the service type the application is looking for. This interface extends `Supplier<S>` and represents a service provider discovered by `ServiceLoader`.

When calling `ServiceLoader.stream()`, each element of the stream has type `ServiceLoader.Provider<S>`, rather than directly being a service object:

~~~java
ServiceLoader<CodecFactory> loader =
        ServiceLoader.load(CodecFactory.class);

Stream<ServiceLoader.Provider<CodecFactory>> providers =
        loader.stream();
~~~

The key point is that the application can inspect information about the provider type before requesting object creation. This is useful when needing to choose an implementation based on annotations, class name, package, or other metadata.

Comparing the two ways to iterate:

| Traversal method | Element received | When is the service instance obtained? |
|---|---|---|
| `loader.iterator()` | `S` | When fetching the next element from the iterator |
| `loader.stream()` | `ServiceLoader.Provider<S>` | When calling `Provider.get()` |

`stream()` supports lazy processing. Locating and processing providers occurs as the stream is consumed. A pipeline can filter out unsuitable providers based on `type()` without calling `get()` for those providers.

## 2. API structure

The core API has the form:

~~~java
public static interface ServiceLoader.Provider<S>
        extends Supplier<S> {

    Class<? extends S> type();

    S get();
}
~~~

The two methods serve two distinct purposes:

| Method | Return type | Meaning |
|---|---|---|
| `type()` | `Class<? extends S>` | Returns the provider type |
| `get()` | `S` | Returns an instance of the service provider |

Because `Provider` extends `Supplier<S>`, you can also use the method reference `ServiceLoader.Provider::get` in the Stream API.

### 2.1. `type()` — inspect the type without obtaining an instance

~~~java
ServiceLoader.Provider<CodecFactory> provider = /* obtained from loader.stream() */;

Class<? extends CodecFactory> providerType = provider.type();

System.out.println(providerType.getName());
~~~

`type()` provides the `Class` object so the application can read metadata, for example:

~~~java
boolean supportsPng =
        provider.type().isAnnotationPresent(SupportsPng.class);

String implementationName = provider.type().getName();
~~~

Calling `type()` does not request creating a service provider instance. However, the returned type is not guaranteed to be accessible from the current code or to have a public no-argument constructor. Therefore, do not use `type()` as a way to instantiate objects yourself via reflection.

### 2.2. `get()` — obtain the service instance

~~~java
CodecFactory factory = provider.get();
String format = factory.format();
~~~

`get()` returns an instance of service type `S`. For standard providers, `ServiceLoader` creates the provider using its public no-argument constructor. For providers declaring a factory method in a module, `ServiceLoader` invokes that method to obtain the instance.

If the provider cannot be instantiated, the factory method returns `null`, or the factory method throws an error/exception, `get()` may throw `ServiceConfigurationError`.

Do not invoke a constructor from `provider.type()` as a substitute for `get()`. Doing so bypasses ServiceLoader's instantiation rules and can fail for providers that use a factory method.

## 3. Example: filtering providers before instantiation

Suppose the application has a `CodecFactory` service:

~~~java
package com.example.codec;

public interface CodecFactory {
    String format();
}
~~~

The application uses an annotation to mark providers that support PNG:

~~~java
package com.example.codec;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface SupportsPng {
}
~~~

An implementation marked with the annotation:

~~~java
package com.example.codec.png;

import com.example.codec.CodecFactory;
import com.example.codec.SupportsPng;

@SupportsPng
public final class PngCodecFactory implements CodecFactory {

    public PngCodecFactory() {
    }

    @Override
    public String format() {
        return "PNG";
    }
}
~~~

The module containing the provider declares the service with the `provides` directive:

~~~java
module codec.png {
    requires codec.api;

    provides com.example.codec.CodecFactory
            with com.example.codec.png.PngCodecFactory;
}
~~~

The application module declares the service it uses with the `uses` directive:

~~~java
module codec.app {
    requires codec.api;

    uses com.example.codec.CodecFactory;
}
~~~

The application can check the annotation first, and then instantiate only matching providers:

~~~java
import com.example.codec.CodecFactory;
import com.example.codec.SupportsPng;

import java.util.List;
import java.util.ServiceLoader;

public class CodecRegistry {

    public static List<CodecFactory> loadPngFactories() {
        ServiceLoader<CodecFactory> loader =
                ServiceLoader.load(CodecFactory.class);

        return loader.stream()
                .filter(provider ->
                        provider.type()
                                .isAnnotationPresent(SupportsPng.class))
                .map(ServiceLoader.Provider::get)
                .toList();
    }
}
~~~

The pipeline above works in the following order:

1. `ServiceLoader.load(...)` creates a loader for the `CodecFactory` service.
2. `stream()` supplies `Provider<CodecFactory>` objects.
3. `filter(...)` calls `type()` to check the annotation on the provider type.
4. Providers without the annotation are dropped from the pipeline without calling `get()` on them.
5. `map(ServiceLoader.Provider::get)` creates instances for the remaining providers.
6. `toList()` consumes the stream and collects the instances into a list.

If you want to process by class name, you can sort before the instantiation step:

~~~java
List<CodecFactory> factories = loader.stream()
        .sorted((left, right) ->
                left.type().getName().compareTo(right.type().getName()))
        .map(ServiceLoader.Provider::get)
        .toList();
~~~

This sorting makes the processing order deterministic by class name, rather than relying on the order in which providers were discovered.

## 4. Provider factory methods and the result of `type()`

In a named module, a provider can be created via a public static method named `provider`, taking no arguments and returning a type compatible with the service. When using this approach, the class declaring the `provider()` method is not required to implement the service.

Example:

~~~java
package com.example.codec.png;

import com.example.codec.CodecFactory;

public final class PngCodecFactory implements CodecFactory {

    @Override
    public String format() {
        return "PNG";
    }
}
~~~

Factory class:

~~~java
package com.example.codec.png;

public final class ExtendedCodecsFactory {

    public static PngCodecFactory provider() {
        return new PngCodecFactory();
    }
}
~~~

The module declares the factory class as the provider:

~~~java
module codec.png {
    requires codec.api;

    provides com.example.codec.CodecFactory
            with com.example.codec.png.ExtendedCodecsFactory;
}
~~~

In this case:

- `ExtendedCodecsFactory` is the class containing the factory method.
- `PngCodecFactory` is the declared return type of the `provider()` method.
- `Provider.type()` returns `PngCodecFactory.class`, which is the return type of the factory method.
- `Provider.get()` invokes the factory method to obtain the service instance.

Therefore, `type()` does not necessarily return the class listed after `with` in the `provides` directive. When a module uses a provider factory, the API specifies that `type()` returns the return type of the `provider()` method.

This detail matters when using annotations or metadata to select providers: place the metadata on the type that `type()` actually returns.

## 5. Key points when using it

- Use `type()` when you need to inspect metadata or decide whether to select a provider.
- Use `get()` when you actually need an instance to call the service's methods.
- `Provider<S>` is a wrapper describing a provider; it is not itself an instance of `S`.
- Do not assume the type from `type()` is directly accessible or has a public no-argument constructor.
- Do not instantiate it manually via reflection; let `ServiceLoader.Provider.get()` follow the proper provider creation rules.
- Handle `ServiceConfigurationError` at an appropriate place if a provider might be misconfigured or fail to instantiate.
- For provider factories in named modules, remember that `type()` returns the return type of the `provider()` method.

## 6. Summary

`ServiceLoader.Provider<S>` adds an intermediate step between finding a provider and creating a service instance. `type()` allows inspecting the provider type for filtering, sorting, or checking annotations. `get()` is the operation that obtains the `S` instance. Combining both methods with `ServiceLoader.stream()` lets an application select providers based on metadata before instantiating only the ones needed.

API documentation: [ServiceLoader.Provider — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.Provider.html)
