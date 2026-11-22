# Module Dependency Cycles and Resolution Errors

In the Java Platform Module System (JPMS), each named module declares dependencies using the `requires` directive in `module-info.java`. The set of modules and `requires` relationships forms a dependency graph. For Java to resolve the module graph, the modules must be found and the dependency relationships must be valid.

An important error is a **module dependency cycle**: module A needs B, B needs C, and C needs A in return. This cycle prevents dependency boundaries from having a clear ordering, so JPMS cannot resolve the module graph as a valid structure.

It is necessary to distinguish a module-level dependency cycle from two classes calling each other or two packages referencing each other's types. Java allows multiple types to have mutual reference relationships; what is prohibited in JPMS design is a cycle in dependency relationships between named modules.

## 1. The module graph formed by requires

Each `requires` directive creates a directed dependency edge from the declaring module to the required module.

Example:

~~~java
module com.example.checkout {
    requires com.example.catalog;
    requires com.example.payment;
}
~~~

This can be read in direction:

- `com.example.checkout` needs to read `com.example.catalog`.
- `com.example.checkout` needs to read `com.example.payment`.

If `com.example.payment` also declares `requires com.example.catalog`, the dependency relationship remains valid:

~~~java
module com.example.payment {
    requires com.example.catalog;
}
~~~

The graph now looks like this:

~~~text
com.example.checkout ──requires──> com.example.catalog
          │
          └────────────requires──> com.example.payment
                                         │
                                         └──requires──> com.example.catalog
~~~

This is a directed acyclic graph. A module can depend on multiple modules, and multiple modules can depend on a shared module together.

A problem arises when a chain of dependencies loops back to the starting module:

~~~text
com.example.order
       │
       ▼
com.example.payment
       │
       ▼
com.example.customer
       │
       └──────────────> com.example.order
~~~

A cycle can involve two modules or many modules. As long as a path exists from a module back to itself through `requires` edges, the module graph has a dependency cycle.

## 2. Example of a two-module dependency cycle

Suppose a system has two modules:

~~~text
module-order/
└── module-info.java

module-payment/
└── module-info.java
~~~

Descriptor of the order module:

~~~java
module com.example.order {
    requires com.example.payment;
}
~~~

Descriptor of the payment module:

~~~java
module com.example.payment {
    requires com.example.order;
}
~~~

Actual relationship:

~~~text
com.example.order ──requires──> com.example.payment
com.example.payment ──requires──> com.example.order
~~~

When the compiler or Java tooling resolves both modules, it detects that each module needs the other module to complete the dependency graph. This is a cycle in the module graph, and resolution will fail.

Depending on the JDK version, tool, and detection phase, the error message may be phrased differently, such as containing phrases like `cyclic dependence`, `cycle detected`, or pointing out the involved module chain. Do not rely on a single error string; read the module names and trace the `requires` directives to find the path back to the initial module.

## 3. Multi-module dependency cycles

In large projects, cycles are often hard to spot because dependency edges reside across many different descriptors.

Example:

~~~java
// module com.example.order
module com.example.order {
    requires com.example.payment;
}
~~~

~~~java
// module com.example.payment
module com.example.payment {
    requires com.example.customer;
}
~~~

~~~java
// module com.example.customer
module com.example.customer {
    requires com.example.order;
}
~~~

Graph:

~~~text
order ──requires──> payment
  ▲                    │
  │                    ▼
customer <─────────────┘
       requires
~~~

We can trace the chain:

1. `com.example.order` needs `com.example.payment`.
2. `com.example.payment` needs `com.example.customer`.
3. `com.example.customer` in turn needs `com.example.order`.

Cycles do not necessarily appear in two adjacent files or within the same directory. Therefore, when handling resolution errors, check the entire relevant dependency path rather than only fixing the first descriptor mentioned in the message.

## 4. Why is a dependency cycle a problem?

Module descriptors are designed to describe resolvable dependency boundaries. A cycle causes those boundaries to lose unidirectionality: each module is both a dependency of another module and requires that module to establish readability.

Several consequences:

- **Cannot resolve the module graph:** JPMS does not allow cycles in `requires` relationships of named modules.
- **Blurred responsibility boundaries:** two modules may be sharing too many implementation details or co-owning part of an abstraction.
- **Hard to control APIs:** changes in one module easily trigger descriptor and build changes in the other module.
- **Hard to reuse independently:** a module cannot be distributed or developed independently if it always drags along a dependency cycle.
- **Hard to test and maintain:** the development team struggles to determine which module should own shared APIs, data, or business rules.

A dependency cycle is usually a sign that module partitioning and the dependency direction of abstractions need to be revisited.

## 5. Distinguishing module cycles from other types of circular references

Not every bidirectional relationship in code is a JPMS dependency cycle error.

### 5.1. Two classes referencing each other

Example of two classes in the same module:

~~~java
package com.example.order;

public class Order {
    private Customer customer;
}
~~~

~~~java
package com.example.order;

public class Customer {
    private Order latestOrder;
}
~~~

Two classes can reference each other's types. This is a type-level relationship within the same module and does not create two `requires` edges between modules.

### 5.2. Two packages referencing each other

Two packages in the same module can contain classes that use each other's types. A package is not an independent module unit in JPMS, so this relationship by itself does not create a module cycle.

Even so, bidirectional references at the package level can make code difficult to organize. You can consider extracting interfaces, grouping related types, or adjusting responsibilities if mutual dependencies make the design hard to understand.

### 5.3. Two named modules requiring each other

This is what constitutes a dependency cycle at the JPMS level:

~~~java
// module A
module com.example.a {
    requires com.example.b;
}
~~~

~~~java
// module B
module com.example.b {
    requires com.example.a;
}
~~~

This cycle is invalid when resolving the module graph.

### 5.4. Dependency cycles between Gradle/Maven projects

Gradle projects or Maven modules also have their own dependency graphs. If project A needs project B and project B needs project A, the build tool may encounter task cycles or dependency configuration errors.

This is the build layer, independent of JPMS:

- Gradle/Maven manages artifacts, project dependencies, and task ordering.
- JPMS manages readability between named modules and package access permissions.

A project may encounter both types of dependency cycles, and fixing one layer does not automatically fix the other layer. Check both `build.gradle`/`pom.xml` and `module-info.java` if errors appear in a modular project using multiple build projects.

## 6. Common causes of module cycles

### 6.1. Splitting modules by class groups instead of responsibilities

For example, the order module holds business rules yet needs concrete classes from payment; payment also needs to call order classes directly. The two modules become tightly coupled to each other.

The solution is to identify a shared abstraction or communication contract, then have both sides depend in a single clear direction.

### 6.2. Placing a shared API inside a module that already depends in the reverse direction

For example, `com.example.order` contains the `PaymentGateway` interface, while the payment module needs order's API and order also needs the payment implementation. When both the API and implementation live together or inside the order module, module splitting can create a cycle.

The interface can be extracted into an independent API module:

~~~text
com.example.payment.api
       ▲             ▲
       │             │
       │             │
com.example.order   com.example.payment.impl
~~~

The order module and the implementation both depend on the API; the API does not depend back on the other two modules.

### 6.3. Using implementation classes directly instead of interfaces

If module A needs to instantiate or call internal classes of B, and B needs internal classes of A, the two sides easily form bidirectional `requires` relationships.

Consider having the module owning the contract expose an interface, while the other module depends on that contract. Implementation instantiation can be done at the composition root or via a service loader.

### 6.4. Adding requires based on compiler errors without reviewing the graph

When encountering an error about an unreadable module or package, adding a `requires` directive may make one error disappear while creating a new edge in the graph. If that edge completes a path back to the initial module, a cycle error will appear.

Before adding `requires`, ask:

- Which API does the current module need?
- Which module does that API belong to?
- Are we depending on an implementation instead of an abstraction?
- Can this dependency be moved to a shared API module?

### 6.5. Mistaking requires transitive or requires static for a way to break cycles

`requires transitive` changes how a dependency is propagated to consuming modules; it is still a dependency edge in the module graph. It does not remove a cycle.

`requires static` allows a compile-time dependency to be optional at runtime in some situations. It is also not a tool to legitimize a cyclic `requires` graph. If two modules need each other at compile time, changing one edge to `static` does not resolve a cyclic dependency design.

## 7. How to break dependency cycles

The goal is to make the module graph a directed acyclic graph while maintaining clear business responsibilities.

### 7.1. Extract a shared API or contract module

This is a common approach when two modules both need certain interfaces, DTOs, or contract types.

Before splitting:

~~~text
order <──────────────> payment
     bidirectional requires
~~~

After splitting:

~~~text
        payment-api
          ▲     ▲
          │     │
          │     │
        order  payment-impl
~~~

Example:

~~~java
// module com.example.payment.api
module com.example.payment.api {
    exports com.example.payment.api;
}
~~~

~~~java
// module com.example.order
module com.example.order {
    requires com.example.payment.api;
}
~~~

~~~java
// module com.example.payment.impl
module com.example.payment.impl {
    requires com.example.payment.api;
}
~~~

The API module only contains the contract to be shared. It must not depend back on order or the payment implementation; otherwise, the cycle may simply shift to another location.

### 7.2. Use dependency inversion

A business module should depend on an interface describing what it needs. The implementation resides in another module and implements that interface.

For example, the order module defines a payment port:

~~~java
package com.example.order.spi;

public interface PaymentPort {
    void charge(String orderId);
}
~~~

Order's descriptor:

~~~java
module com.example.order {
    exports com.example.order.spi;
}
~~~

The payment implementation module depends on order's API:

~~~java
module com.example.payment.impl {
    requires com.example.order;

    provides com.example.order.spi.PaymentPort
        with com.example.payment.impl.CardPaymentAdapter;
}
~~~

The order module does not need `requires com.example.payment.impl`. It only knows the `PaymentPort` interface; the implementation is discovered via service loader or injected from the composition root.

The order module can declare using the service:

~~~java
module com.example.order {
    exports com.example.order.spi;
    uses com.example.order.spi.PaymentPort;
}
~~~

In this case, the dependency relationship is unidirectional from payment implementation to order's API. If a more independent service contract separation is needed, the interface can be placed into a separate API module so both consumer and provider depend on that module.

### 7.3. Use module composition or an application module

An application-layer module can connect business modules:

~~~text
             application
              /       \
             ▼         ▼
           order     payment
             \         /
              ▼       ▼
              shared-api
~~~

The application module is responsible for wiring implementations and configuring the system. Business modules do not need to know each other's implementations directly.

This approach fits when a business flow needs to coordinate multiple capabilities. The composition layer can depend on both sides without creating reverse dependencies between them.

### 7.4. Merge modules when boundaries have no independent meaning

If two code groups always change together, share many internal details, and have no stable API between them, splitting them into two named modules may bring no benefit.

You can merge them into one module, then continue organizing using packages and Java-level encapsulation. There is no need to create a module for every package or every group of classes.

## 8. Process for diagnosing resolution errors

When encountering a module resolution error, handle it in the following order.

### Step 1: Identify the phase of the error

Note whether the error occurs when:

- Compiling with `javac`.
- Running the application with `java`.
- Packaging a modular JAR.
- Running a Gradle/Maven task.
- Starting the application in an IDE or framework.

The detection phase helps narrow down which configuration is being used. A build may compile successfully yet fail at runtime due to using a different module path.

### Step 2: Read the module names in the error message

Find the module names mentioned. If the error indicates a chain of modules, write down each module and the dependency path between them.

Do not only fix the first module appearing in the log; identify which edge closes the cycle.

### Step 3: Inspect the module descriptors

Find all relevant `requires` directives in the `module-info.java` files. Redraw the relationships as a directed diagram.

Example:

~~~text
A -> B
B -> C
C -> A
~~~

The chain above shows the cycle A-B-C-A. Check `requires transitive` and `requires static` as well, because they still represent dependency relationships in the descriptor.

### Step 4: Check module names and the module path

Some resolution errors are not cycles but are caused by a module not being found or a name mismatch.

You can use:

~~~bash
jar --describe-module --file path/to/library.jar
~~~

This command shows the module name that the JAR declares or the inferred automatic module name. Compare it with the name in the `requires` directive.

Verify the module path passed to the compiler/runtime:

~~~bash
javac --module-path libs -d out --module com.example.app
~~~

~~~bash
java --module-path out:libs -m com.example.app/com.example.app.Main
~~~

On Windows, the separator for multiple paths is a semicolon instead of a colon. Specific syntax may also vary by shell and build tool.

### Step 5: Observe resolution at runtime

You can ask the JVM to display resolved modules:

~~~bash
java --show-module-resolution --module-path out:libs -m com.example.app/com.example.app.Main
~~~

This information helps confirm which modules were found, which modules were required, and from which locations the runtime module graph was built.

### Step 6: Check other errors after breaking the cycle

Once a cycle is broken, other independent errors may be uncovered:

- `Module ... not found`: missing module on the module path or mismatched module name.
- `Package ... is not visible`: the current module does not read the module containing that package or the package is not exported appropriately.
- `module ... does not read ...`: missing readability relationship.
- `Package ... is declared in module ...` or a split package message: multiple modules containing the same package causing a conflict in the module graph.
- `Module ... not in graph`: the target module has not been resolved or included in the appropriate configuration.
- `ClassNotFoundException` or `NoClassDefFoundError` errors: may relate to classpath/module path or runtime dependencies; inspect separately after the module graph is valid.

Do not handle all messages by blindly adding `requires` or opening packages en masse. Each error corresponds to a different type of relationship.

## 9. Supporting inspection tools

Some useful commands when investigating modules:

~~~bash
# Inspect the descriptor of a modular JAR or automatic module name
jar --describe-module --file path/to/library.jar

# Display module dependencies inferred from class/JAR
jdeps --module-path libs --check com.example.app

# Display module resolution at runtime
java --show-module-resolution --module-path out:libs -m com.example.app/com.example.app.Main
~~~

Meaning:

- `jar --describe-module` helps confirm the module name and directives packaged inside a JAR.
- `jdeps` assists in analyzing dependencies between classes/packages/modules; depending on the JDK version and options, it can point out dependencies that need review.
- `--show-module-resolution` indicates which modules the JVM resolved at launch.

With Gradle, also inspect the project's dependency graph:

~~~bash
./gradlew :app:dependencies
~~~

If a dependency cycle is suspected at the project or task level, also inspect project dependencies and the task graph. Do not confuse the output of Gradle's dependency report with the JPMS module graph; they are two different models.

## 10. Fixes to avoid

- **Adding bidirectional `requires` to make the compiler stop reporting errors:** can create a cycle or couple modules more tightly.
- **Switching to `requires transitive` to mask errors:** this modifier propagates readability, not removing a dependency edge.
- **Switching to `requires static` hoping to skip a cycle:** compile-time dependencies still must be resolved; this is not a way to fix the graph.
- **Putting all classes into one shared module without a clear API:** may avoid a cycle in the short term, but destroys responsibility boundaries.
- **Using `--add-reads` or `--add-exports` as a long-term architectural solution:** these options can assist testing or compatibility in special situations, but do not fix cyclic `requires` relationships.
- **Moving all JARs to the classpath:** can bypass some JPMS checks, but loses encapsulation and module graph transparency. You should only switch execution models when it is an intentional architectural decision.

## 11. Self-Check

When handling a module-related resolution error, ask yourself:

1. Which modules appear in the error message?
2. Which `requires` directives does each module declare?
3. Is there a dependency path returning to the starting module?
4. Is the cycle in the JPMS module graph, the Gradle/Maven project graph, or both?
5. Are two modules referencing each other's implementations instead of a stable contract?
6. Can a shared API be extracted, dependencies inverted via interfaces/SPI, or wiring moved up to an application module?
7. After modifying descriptors, do both compiler and runtime see a valid module path?

A module dependency cycle is a dependency structure problem. The sustainable way to handle it is to locate the exact cycle, identify the misplaced abstraction or responsibility, and redesign the dependency direction so each module can be resolved independently in an acyclic graph.