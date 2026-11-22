# What is the Java Platform Module System (JPMS)?

The Java Platform Module System (JPMS) is the module system introduced in Java 9. It allows splitting an application or library into named modules, explicitly declaring which module depends on which module and which packages are allowed to be exposed externally.

Before JPMS, Java primarily organized source code using packages and managed runtime dependencies through the classpath. Packages help group classes by namespace, but a package by itself does not specify which libraries an application needs or which packages form the public API. JPMS adds a module-level boundary to solve both of those problems.

## 1. Why does Java need a module system?

As an application grows, placing all JARs on the classpath creates several difficulties:

- **Hidden dependencies:** one library can use classes from another library without the build configuration clearly expressing that relationship.
- **Unclear API boundaries:** many internal packages can still be accessed by other applications if their classes and members are public.
- **Late configuration errors:** missing or conflicting libraries often only surface at application runtime.
- **Oversized JDK for actual needs:** small applications still typically run on a JRE containing many unused components.

JPMS provides mechanisms to:

1. Declare dependencies directly within the module.
2. Expose only selected packages.
3. Support checking and resolving the module graph at compile time or launch time.
4. Split the JDK into smaller modules and create leaner runtime images with tools such as jlink.

JPMS does not replace packages. Packages still organize classes by namespace; a module groups one or more packages and defines their dependency and access boundaries.

## 2. What is a module?

A **named module** is a named unit that contains packages and resources, along with a module descriptor that describes how the module works. The descriptor is typically written in a **module-info.java** file at the root directory of the source set.

A module typically has:

- A stable name, usually following reverse domain name conventions such as **com.example.orders**.
- One or more packages.
- A list of modules that it needs to read.
- A list of packages exported for other modules to use.
- Declarations opening packages for reflection or providing services, if needed.

After compilation, the descriptor becomes **module-info.class**. When packaged as a modular JAR, this file resides at the root of the JAR.

Example of a simple structure:

~~~text
project/
└── src/
    └── com.example.greetings/
        ├── module-info.java
        └── com/example/greetings/api/GreetingService.java
~~~

Descriptor content:

~~~java
module com.example.greetings {
    exports com.example.greetings.api;
}
~~~

The declaration above names the module **com.example.greetings** and exposes the **com.example.greetings.api** package. Other packages in the module remain hidden from external modules unless explicitly exported or opened.

## 3. The two most important declarations: requires and exports

JPMS separates two different questions:

- **requires:** which modules does the current module need to read?
- **exports:** which packages does the current module allow other modules to access?

Suppose there are two modules:

~~~text
src/
├── com.example.greetings/
│   ├── module-info.java
│   └── com/example/greetings/api/GreetingService.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
~~~

The library module exposes its API:

~~~java
module com.example.greetings {
    exports com.example.greetings.api;
}
~~~

The application module declares its dependency on the library:

~~~java
module com.example.app {
    requires com.example.greetings;
}
~~~

The API class in the library:

~~~java
package com.example.greetings.api;

public class GreetingService {
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

The class using the API:

~~~java
package com.example.app;

import com.example.greetings.api.GreetingService;

public class Main {
    public static void main(String[] args) {
        GreetingService service = new GreetingService();
        System.out.println(service.greet("Java"));
    }
}
~~~

**requires** enables the application module to read the library module. **exports** allows the application to access the public types in the API package. Having **public** on the class alone is not enough: the package containing the class must also be exported to the consuming module.

An unexported package can still contain public classes, but other modules cannot use them as ordinary API. This is what gives JPMS its strong encapsulation.

## 4. Common directives in module-info.java

| Directive | Meaning |
| --- | --- |
| **requires module.name;** | Declares a dependency and readability of the specified module. |
| **requires transitive module.name;** | The dependency module is propagated to modules that read the current module. |
| **requires static module.name;** | A dependency required at compile time that may be absent at runtime. |
| **exports package.name;** | Exposes the package to modules that read the current module. |
| **exports package.name to a, b;** | Exposes the package only to the named modules. |
| **opens package.name;** | Allows deep reflection on the package at runtime. |
| **opens package.name to a, b;** | Allows deep reflection on the package only for the named modules. |
| **uses service.Type;** | Declares that the module uses a service. |
| **provides service.Type with impl.Type;** | Declares that the module provides an implementation for a service. |

### requires transitive

Suppose the **com.example.facade** module uses types from **com.example.library** in its public API. If an application module only depends on the facade, it may need to read the library as well to compile and use that API.

~~~java
module com.example.facade {
    requires transitive com.example.library;
}
~~~

**transitive** propagates readability of the dependency to modules that read the facade. Only use it when the dependency is genuinely part of the API contract exposed by the facade.

### requires static

~~~java
module com.example.app {
    requires static com.example.annotations;
}
~~~

This directive is useful for annotations or optional integrations that are only needed at compile time. It does not by itself guarantee that the application can execute every code branch if the module is missing; code that actually needs classes from the dependency must still handle whether the dependency is present or not.

### Qualified exports

~~~java
module com.example.internal.api {
    exports com.example.internal.api to com.example.app;
}
~~~

The package is exposed only to the **com.example.app** module. This approach is appropriate when a package needs to be shared among certain internal modules but should not become a general API for all consumers.

## 5. How does exports differ from opens?

**exports** serves ordinary API access from Java code. It allows other modules to reference public types in the exported package, following Java's access rules.

**opens** serves runtime reflection, especially **deep reflection** — accessing non-public members when a framework needs to read or modify an object's internal state.

For example, a framework needs to read private fields to map data:

~~~java
module com.example.domain {
    opens com.example.domain.model to com.example.mapper;
}
~~~

The mapper module is allowed to perform deep reflection on the model package. The **opens** declaration does not turn the package into a public API for other source code to import at will.

All packages of a module can be opened for reflection using:

~~~java
open module com.example.domain {
    // Other requires and declarations if needed.
}
~~~

You should only open the scope that is needed. Opening an entire module reduces the encapsulation benefits that JPMS provides. For applications using frameworks, identify the exact packages the framework needs to access via reflection and open those packages.

## 6. JPMS and the Service Provider mechanism

JPMS supports the service model so that a module consumes a dependency through an interface instead of depending directly on an implementation.

The module declaring the service:

~~~java
module com.example.payment.api {
    exports com.example.payment;
}
~~~

The application module declaring service usage:

~~~java
module com.example.checkout {
    requires com.example.payment.api;
    uses com.example.payment.PaymentProcessor;
}
~~~

The implementation module declaring the provider:

~~~java
module com.example.payment.stripe {
    requires com.example.payment.api;
    provides com.example.payment.PaymentProcessor
        with com.example.payment.stripe.StripePaymentProcessor;
}
~~~

The application can discover implementations using **ServiceLoader**:

~~~java
ServiceLoader<PaymentProcessor> processors =
        ServiceLoader.load(PaymentProcessor.class);

for (PaymentProcessor processor : processors) {
    processor.process();
}
~~~

This approach decouples the service contract from the implementation and allows adding providers without forcing the consuming module to know concrete implementation classes.

## 7. Named module, automatic module, and unnamed module

Three kinds of modules can be encountered in a Java application:

| Kind | Origin | Characteristics |
| --- | --- | --- |
| Named module | Has **module-info.java** | Has a name and explicitly declares dependencies, exports, opens, and services. |
| Automatic module | A JAR without a descriptor placed on the module path | Name is usually taken from the **Automatic-Module-Name** manifest attribute or derived from the file name; automatically exports its packages and reads other named modules. |
| Unnamed module | Classes/JARs on the classpath | Has no module name; typically used to maintain compatibility with unmodularized applications. |

An automatic module is a useful bridge when migrating legacy libraries to the module path. However, because its packages are broadly exported and its dependency readability is very broad, it does not establish boundaries as clear as a named module with a carefully designed descriptor.

Classes on the classpath belong to the unnamed module of the corresponding class loader. The unnamed module can read observable named modules and exports its own packages. A named module cannot declare **requires** on an unnamed module, because an unnamed module has no name to reference.

## 8. How does the module path differ from the classpath?

The classpath is the traditional class-lookup mechanism. When running with the classpath, the JVM does not use module descriptors to build a dependency graph for JARs on the classpath.

The module path holds modules that JPMS can recognize and resolve. When launching a modular application, the JVM locates the root modules, resolves **requires** directives, and creates the appropriate module layer.

Example compiling the two modules using the structure above:

~~~bash
javac --module-source-path src -d out -m com.example.greetings,com.example.app
~~~

Running the main class in the application module:

~~~bash
java --module-path out -m com.example.app/com.example.app.Main
~~~

In the run command:

- **--module-path out** specifies where the compiled modules are located.
- **-m** or **--module** specifies the module and main class in the form **module.name/main.class**.

For an unmodularized application, it can still be run in the traditional way:

~~~bash
java -cp "lib/*:classes" com.example.app.Main
~~~

The classpath separator depends on the operating system: **:** on Unix-like systems and **;** on Windows. Projects can migrate step by step, but library and framework compatibility should be verified when moving dependencies from the classpath to the module path.

## 9. JPMS in the JDK itself

The JDK itself is also divided into modules. Some commonly encountered modules:

- **java.base:** foundational APIs such as java.lang, java.util, and java.io; every module implicitly depends on this module.
- **java.sql:** JDBC and database access APIs.
- **java.xml:** XML processing APIs.
- **java.logging:** standard logging API.
- **jdk.compiler:** tools and APIs related to the Java compiler.

Splitting the JDK into modules allows the runtime to include only the components the application requires. The **jlink** tool can assemble the necessary modules into a custom runtime image. This serves as the foundation for distributing applications with a leaner runtime environment compared to shipping the entire JDK.

## 10. JPMS does not mean every project must be modularized

JPMS is useful when you need to manage boundaries between parts of a system, develop libraries with clear APIs, control reflection, or create custom runtime images.

For a small application, adding **module-info.java** may increase configuration effort without delivering commensurate benefits. For applications using many legacy frameworks, moving to the module path may also require opening packages for reflection or dealing with dependencies that lack module descriptors.

Consider JPMS when:

- The project has multiple libraries or multiple development teams needing clear API boundaries.
- You want to prevent unintended use of internal packages.
- You are building a library that needs to publish a stable API.
- You want to analyze dependencies and create a minimal runtime image.
- You need to design plugins or service providers around explicit contracts.

If an existing application is already running stably on the classpath, adopting JPMS should be driven by a specific goal such as API control, dependency reduction, or runtime optimization.

## 11. Common misconceptions

**Packages and modules are the same thing:** False. A package is a namespace containing classes; a module is a larger unit that groups multiple packages and manages dependencies as well as access permissions.

**A public class is always usable from other modules:** False. The package containing the class must be exported to the consuming module.

**exports and opens are the same:** False. **exports** exposes API for ordinary Java access; **opens** allows deep reflection at runtime.

**requires automatically turns a dependency's packages into public API:** False. **requires** establishes a module readability relationship. Packages still need to be exported by the owning module.

**Having module-info.java makes it impossible to use legacy libraries:** False. JPMS supports automatic modules and the unnamed module for compatibility during transition, although these mechanisms have weaker boundaries than explicit named modules.

**JPMS is just a way to package JARs:** False. JAR is a packaging format; JPMS also defines how modules are resolved, readability, exports, reflection, and services.

## 12. How to remember it

JPMS can be understood through three questions:

1. **What does this module need?** Use **requires** to declare dependencies.
2. **What does this module expose?** Use **exports** to expose API packages.
3. **Where does a framework need internal access via reflection?** Use **opens** for the exact package and exact module.

When these three questions are answered clearly, the module descriptor becomes a concise description of the module's boundaries and contract. That is the core value of the Java Platform Module System.