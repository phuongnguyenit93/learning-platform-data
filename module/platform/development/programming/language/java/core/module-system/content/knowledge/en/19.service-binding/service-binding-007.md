# Distinguishing service binding from reflection scanning

## 1. Two mechanisms solving two different problems

In the Java Module System, **service binding** and **reflection scanning** can both help an application locate implementations at runtime, but they operate according to different rules.

**Service binding** is based on explicitly declared service contracts. The consuming module declares **uses**, the supplying module declares **provides ... with ...**, and **ServiceLoader** finds matching providers. When creating a runtime image, **jlink --bind-services** can include the required provider modules and their dependencies in the image.

**Reflection scanning** is how an application or framework searches for classes by package, annotation, class name, or metadata. A framework may read resources inside JARs/modules, load classes, and then use reflection to inspect annotations, constructors, fields, or methods. This is a discovery mechanism implemented by the framework; JPMS does not automatically know that every class with a certain annotation is a provider that needs to be included in a runtime image.

Therefore, the two mechanisms do not replace each other:

- Service binding is suitable when the application has a service interface and wants providers to follow a declared contract.
- Reflection scanning is suitable when a framework needs to discover many kinds of classes by convention, annotation, or custom configuration.
- An application can use both: `ServiceLoader` to discover plugins, and reflection to inspect metadata or instantiate components after they are found.

## 2. ServiceLoader and service binding in JPMS

A service is a Java contract, typically represented by an interface or abstract class. The consuming module knows the contract without needing to depend directly on each implementation.

For example, the API module exposes an interface:

~~~java
package com.example.spi;

public interface PaymentProvider {
    String name();
    void pay(int amount);
}
~~~

The module containing the interface exports the package so other modules can use it:

~~~java
module com.example.payment.api {
    exports com.example.spi;
}
~~~

The application module consuming the service declares **uses**:

~~~java
module com.example.payment.app {
    requires com.example.payment.api;

    uses com.example.spi.PaymentProvider;
}
~~~

The provider module declares its implementation with **provides ... with ...**:

~~~java
module com.example.payment.card {
    requires com.example.payment.api;

    provides com.example.spi.PaymentProvider
        with com.example.payment.card.CardPaymentProvider;
}
~~~

The provider class implements the interface:

~~~java
package com.example.payment.card;

import com.example.spi.PaymentProvider;

public class CardPaymentProvider implements PaymentProvider {
    @Override
    public String name() {
        return "card";
    }

    @Override
    public void pay(int amount) {
        System.out.println("Pay by card: " + amount);
    }
}
~~~

The consuming module can locate providers using `ServiceLoader`:

~~~java
package com.example.payment.app;

import com.example.spi.PaymentProvider;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        ServiceLoader<PaymentProvider> providers =
            ServiceLoader.load(PaymentProvider.class);

        for (PaymentProvider provider : providers) {
            System.out.println(provider.name());
        }
    }
}
~~~

In named modules, the module calling **ServiceLoader.load** must declare **uses** for the service. The provider module must declare **provides** for the exact service type. The provider module must also be found and resolved in the module layer being used.

`ServiceLoader` does not walk every package looking for classes with annotations. It reads service metadata declared according to Java conventions. As a result, the relationship between service and provider can be determined without scanning the entire classpath.

### Providers on the classpath

Non-modular applications can still use `ServiceLoader`. Providers on the classpath are declared in the file:

~~~text
META-INF/services/com.example.spi.PaymentProvider
~~~

The file contents list the fully qualified names of provider classes, one provider per line:

~~~text
com.example.payment.card.CardPaymentProvider
com.example.payment.wallet.WalletPaymentProvider
~~~

This is also structured service metadata, not general reflection scanning. For named modules, provider declarations should be placed in **module-info.java** using **provides**.

## 3. Service binding when creating a runtime image

**jlink** creates a runtime image from resolvable modules on the module path. The **--bind-services** option instructs `jlink` to link matching service provider modules along with their dependencies.

Example module structure:

~~~text
mods/
  com.example.payment.api/
  com.example.payment.app/
  com.example.payment.card/
  com.example.payment.wallet/
~~~

Suppose the application module declares **uses com.example.spi.PaymentProvider**, while both the card and wallet modules declare **provides** for that service. You can build the image with:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.payment.app \
  --bind-services \
  --output payment-runtime
~~~

Here:

- **--module-path** provides the JDK modules and application modules.
- **--add-modules** selects the application's root module.
- **--bind-services** finds providers for services used in the module graph and links the provider modules along with required dependencies.
- **--output** specifies the runtime image directory.

Service binding can cause the image to include additional provider modules that the application did not list directly in **--add-modules**. This is a key benefit of describing services with **uses** and **provides**: tools can infer providers from module metadata.

You can inspect the modules in the image:

~~~bash
payment-runtime/bin/java --list-modules
~~~

And run the application using the runtime image:

~~~bash
payment-runtime/bin/java -m com.example.payment.app/com.example.payment.app.Main
~~~

If you create a custom launcher using the **--launcher** option, you can run the application via the launcher file in the image's **bin** directory.

**--bind-services** only processes service providers that can be identified through module metadata and are present on the module path at link time. It does not scan arbitrary annotations, does not find every class sharing an interface, does not download JARs over the network, and does not automatically put arbitrary classpath libraries into the image.

If providers are selected by class name read from configuration, reflection, or a custom plugin registry, `jlink` may not know that module is needed. In that case, you must declare the appropriate root modules via **--add-modules** or redesign discovery using service metadata.

## 4. How does reflection scanning work?

Reflection scanning typically starts from a package or convention, for example:

- Finding every class annotated with **@Plugin** in package **com.example.plugins**.
- Finding classes that implement a specific interface.
- Reading class metadata to register components.
- Finding classes configured by name in YAML or properties files.
- Scanning directories and JARs to build a framework registry.

A framework can locate package resources through a classloader, read entry listings inside JARs, use module APIs, or read bytecode with a class-analysis library. After discovering a class, the framework can load it with **Class.forName**, inspect annotations via reflection, and invoke constructors or methods.

Illustrative example of how a framework checks an annotation once it has a class:

~~~java
Class<?> type = Class.forName(
    "com.example.plugins.CardPlugin"
);

if (type.isAnnotationPresent(Plugin.class)) {
    System.out.println("Plugin found: " + type.getName());
}
~~~

The snippet above only illustrates checking a class whose name is already known. A real scanning library must also discover class names or resources before it can call **Class.forName**.

Reflection scanning is often flexible when a framework supports many kinds of extensions. However, results depend on the scanning scope, how the framework enumerates resources, the classloader, the module layer, and the access permissions allowed by JPMS.

## 5. How JPMS affects reflection scanning

On the traditional classpath, many frameworks assumed they could enumerate packages and access classes fairly freely. When moving to named modules, this assumption may no longer hold.

Three steps must be separated:

1. **Finding the class:** the framework must see the resource or module containing the class.
2. **Loading the class:** the classloader or module layer must be able to load that class.
3. **Accessing via reflection:** the framework must be permitted to access the member it wants to inspect or invoke.

A class may be found, yet the framework is still not allowed to access a private field or constructor. That is a module encapsulation issue, not always a class-lookup error.

### exports and opens

**exports** exposes a package so other modules can access its public types:

~~~java
module com.example.plugins {
    exports com.example.plugins.api;
}
~~~

**opens** allows deep reflection into a package, including non-public members according to JPMS rules:

~~~java
module com.example.plugins {
    opens com.example.plugins.model
        to com.example.framework;
}
~~~

If a framework needs deep reflection into many packages, **open module** can be used, but that opens every package of the module to deep reflection and reduces encapsulation. Prefer opening only the specific packages to the specific framework module that needs access.

**exports** does not replace **opens** for deep reflection. Conversely, **opens** does not make a package a normal public Java API for other modules to import types from that package.

If a framework uses reflection scanning to read public annotations or metadata, package-opening requirements may differ from when the framework accesses private fields/methods. Check the framework's documentation to know exactly which packages must be **exports** or **opens**.

### Module layers and classloaders

An application can create a new module layer to load plugins dynamically. In that case, the framework needs to look for modules in the right layer. The **ServiceLoader.load(layer, Service.class)** API allows locating service providers in a specific module layer.

A reflection scanner also needs to know which modules and classloaders it must scan. Scanning the system classloader's classpath does not mean scanning every named module in every module layer.

If a framework only supports classpath scanning, turning libraries into named modules may prevent the scanner from seeing packages as before. Check the framework's JPMS support and how it discovers modules before migrating.

## 6. Comparing service binding and reflection scanning

| Criterion | Service binding / ServiceLoader | Reflection scan |
|---|---|---|
| Discovery basis | **uses**, **provides**, service metadata | Packages, classes, annotations, class names, or conventions |
| Contract | Service interface or abstract class | Can be an interface, annotation, or custom rule |
| Provider declaration | **provides S with P** in module descriptor; or `META-INF/services` file on classpath | Typically based on classes present in the scan scope and framework metadata |
| Search scope | Providers declared and visible in the corresponding module layer/classpath | Depends on scanner, classloader, module layer, and configuration |
| jlink support | **--bind-services** can link provider modules | `jlink` cannot automatically infer modules solely from annotations or reflection |
| Access permissions | Follows `exports` and `ServiceLoader` provider rules | May require `exports` or `opens` depending on how reflection is used |
| Explicitness | High; providers and consumers declare contracts | More flexible, but depends on framework conventions |
| Best suited for | SPIs, contract-based plugins, standard providers | Framework scanning, component registries, runtime annotation processing |

The most important difference is that **service binding has metadata that JPMS understands**, whereas reflection scanning is logic implemented by the framework itself. Because of this, `jlink` can link provider modules according to the service graph, but cannot infer every class that a scanner might find when the application runs.

## 7. When should each mechanism be used?

Use **ServiceLoader** when:

- The application defines a clear SPI and multiple modules can provide implementations.
- You want the consumer to depend on an interface rather than concrete implementations.
- You need JPMS to recognize providers and support linking them when building a runtime image.
- You want to be able to add or swap providers with other modules without editing the consumer.

Use **reflection scanning** when:

- A framework needs to find components by annotations or package conventions.
- Class metadata must be read to register controllers, entities, serializers, or extensions.
- The framework has a scanning mechanism designed and tested for JPMS.
- The set of classes to discover changes based on configuration or a plugin registry.

If you only need to find implementations of an SPI, `ServiceLoader` is usually easier to describe and integrate with the module graph. If you need to discover many kinds of components by annotation, a scanner may fit better. A framework can also use `ServiceLoader` to locate extension roots and then use reflection to read configuration or metadata for each extension.

## 8. Combining ServiceLoader and reflection properly

The two mechanisms can be combined in the following flow:

1. The consumer declares **uses** for the service interface.
2. The provider module declares **provides** with the implementation.
3. `ServiceLoader` discovers the registered providers.
4. The framework receives provider instances and reads public annotations or metadata if needed.
5. If the framework must access non-public members, the provider module opens the specific package to the framework module using **opens ... to**.

Consumer example:

~~~java
module com.example.host {
    requires com.example.plugin.api;
    uses com.example.plugin.api.Plugin;
}
~~~

Provider:

~~~java
module com.example.plugin.card {
    requires com.example.plugin.api;

    provides com.example.plugin.api.Plugin
        with com.example.plugin.card.CardPlugin;
}
~~~

The service API can define annotations for the framework to use on implementations:

~~~java
package com.example.plugin.api;

public interface Plugin {
    String id();
}
~~~

When deep access into the implementation package is needed, the provider can declare:

~~~java
module com.example.plugin.card {
    requires com.example.plugin.api;

    provides com.example.plugin.api.Plugin
        with com.example.plugin.card.CardPlugin;

    opens com.example.plugin.card
        to com.example.framework;
}
~~~

Only open a package when the framework genuinely needs deep reflection. If the framework only calls public methods on the interface or implementation, opening the implementation package may not be necessary.

## 9. Common issues when creating an image with service providers

**Provider does not appear in ServiceLoader**

Check whether the consumer declares **uses**, whether the provider module declares **provides**, whether the service type belongs to the same module/package, and whether the provider is present in the module layer being searched. If using the classpath, check the **META-INF/services** file and provider class name.

**Provider works on a full JDK but is missing in the runtime image**

Check whether the `jlink` command uses **--bind-services** and whether the service provider is on the module path at link time. If the provider module is selected via configuration or reflection rather than service metadata, add that module to **--add-modules**.

**Framework cannot scan packages after modularization**

Check whether the scanner supports named modules, module layers, and the module path. Determine whether the scanner enumerates resources via a classloader or module APIs. A scanner that only walks the classpath may miss named modules.

**IllegalAccessException or InaccessibleObjectException**

Check whether the module containing the class exports or opens the appropriate package to the framework module. Use **exports** for public access and **opens** for deep reflection. If only one package is needed, open it selectively rather than opening the entire module.

**Class is found but fails to load in the image**

The module containing the class might not have been included in the image, or a dependency of the class might not be resolved. Reflection does not automatically guarantee a module is added to the runtime image. Identify the module owning the class and add it to the module graph when needed.

## 10. Selection and implementation checklist

- Determine whether the requirement is to locate providers for an SPI or scan components by annotation.
- If using `ServiceLoader` in a named module, declare **uses** in the consumer.
- Declare **provides ... with ...** in the provider module.
- Ensure the service interface resides in an exported package.
- If using **jlink --bind-services**, place provider modules on the module path and inspect the service graph.
- If providers are loaded via configuration/reflection, add the required modules to **--add-modules**.
- If using deep reflection, open the exact package to the exact framework module.
- Verify that the framework supports the module path and module layers.
- Run **java --list-modules** on the image to verify packaged modules.
- Test the actual discovery, instantiation, and provider usage paths on the runtime image itself.

## 11. Key Takeaways

**Service binding** relies on service metadata that JPMS understands. Consumers declare **uses**, providers declare **provides**, and `jlink` can use **--bind-services** to link provider modules into a runtime image.

**Reflection scanning** is performed by an application or framework itself to find classes by package, annotation, or convention. JPMS can restrict module visibility and member access; frameworks need to support the module path/module layers and may need **exports** or **opens**.

Choose the mechanism based on the application's discovery contract. `ServiceLoader` is the natural choice for SPIs with explicitly declared providers; reflection scanning suits frameworks that need to discover components by metadata. When building a runtime image, always verify provider modules and discovery paths using the actual image that will be deployed.
