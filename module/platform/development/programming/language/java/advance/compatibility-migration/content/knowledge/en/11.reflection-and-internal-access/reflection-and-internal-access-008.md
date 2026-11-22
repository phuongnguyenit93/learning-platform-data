# Reflection in ORMs, Serializers, Proxies, and Testing Libraries

In a **Java Advance Compatibility Migration** project, reflection is often the cause of errors that only appear at runtime. The application source code still compiles, but when an ORM instantiates an entity, a serializer reads a private field, a framework creates a proxy, or a testing library initializes a mock, the program may encounter access errors, class loading errors, or bytecode instrumentation errors.

This content belongs to the **Reflection and Internal APIs** chapter. The goal is not only to know how to call **Class.getDeclaredField()** or **Method.invoke()**, but also to understand why libraries work on one JDK yet fail on another, how to distinguish errors caused by the Java Platform Module System (JPMS) from errors caused by frameworks/dependencies, and how to verify compatibility after migration.

The examples use standard Java APIs and illustrative configurations. The actual module names of Hibernate, Jackson, Mockito, Byte Buddy, or the application must be confirmed from the running artifacts and module graph; do not mechanically copy example module names into production.

## 1. Why Is Reflection a Risk Area When Upgrading Java?

Reflection allows a program to inspect and manipulate class structures at runtime: type names, constructors, fields, methods, annotations, and sometimes non-public members. Frameworks use this capability to handle classes they do not specifically know at compile time.

For example:

- **ORM:** reads annotations, instantiates entities, assigns primary keys, or hydrates data from query results.
- **Serializer:** identifies properties and constructors, converts objects to JSON/XML, and reconstructs objects.
- **Proxy/AOP:** discovers methods, generates intermediate classes, delegates calls, or injects transaction/logging logic.
- **Testing libraries:** locate annotated methods, run tests, create mocks, inject dependencies, or alter method behavior.

These mechanisms often depend on details that a regular API does not require: visibility, no-arg constructors, packages, class loaders, parameter names, annotation retention, final/sealed modifiers, and whether packages are open for deep reflection.

A seemingly small change such as moving a library from the classpath to the module path, updating the JDK, or changing the mock maker implementation can alter runtime rules.

### 1.1. Do Not Equate Four Compatibility Concepts

| Aspect | Question to answer | Error example |
|---|---|---|
| Source compatibility | Does existing source still compile? | Imported old API was removed |
| Binary compatibility | Can compiled bytecode still link? | NoSuchMethodError, IllegalAccessError |
| Reflective compatibility | Can frameworks still find and access the right members at runtime? | InaccessibleObjectException, NoSuchMethodException |
| Behavioral compatibility | Are business results still correct? | JSON renames fields, proxy fails to apply advice |

A green build does not prove the other three aspects. Reflection often occurs late: on the first query, when receiving a special payload, when loading a plugin, or when a separate test suite is run.

### 1.2. Distinguishing Public APIs from Implementation Details

If a library only calls public methods through exported types, it depends less on private structure than looking up private fields by string name. Deep reflection is often an implicit dependency on implementation.

For example, **Customer.id** might not appear in the public Java API, yet a mapper still relies on the exact name and type of this field. Renaming the field may not cause a compile error in consumers, but it changes mapping, data, or serialization behavior.

## 2. Reflection API Foundations

The Java Reflection API resides primarily in **java.lang.Class**, **java.lang.reflect**, and related APIs.

### 2.1. Inspecting Fields, Methods, and Constructors

~~~java
package example;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public final class InspectPerson {
    public static void main(String[] args) {
        Class<Person> type = Person.class;

        for (Field field : type.getDeclaredFields()) {
            System.out.println("field: " + field.getName());
        }

        for (Method method : type.getDeclaredMethods()) {
            System.out.println("method: " + method.getName());
        }

        for (Constructor<?> constructor : type.getDeclaredConstructors()) {
            System.out.println("constructor: " + constructor);
        }
    }

    static class Person {
        private String name;

        private Person(String name) {
            this.name = name;
        }

        public String getName() {
            return name;
        }
    }
}
~~~

**getDeclaredFields()** returns the fields declared directly in the class, including private ones, but does not automatically return inherited fields. **getFields()** focuses on accessible public fields of the class, including inherited public members.

Similarly, **getDeclaredMethods()** and **getMethods()** differ in member scope. During migration, this difference matters: a framework switching its scanning strategy from public accessors to declared fields may encounter new access constraints.

### 2.2. Accessing Private Members

~~~java
package example;

import java.lang.reflect.Field;

public final class ReflectionDemo {
    public static void main(String[] args) throws Exception {
        Account account = new Account("A-001");

        Field field = Account.class.getDeclaredField("id");
        field.setAccessible(true);

        String id = (String) field.get(account);
        System.out.println(id);
    }

    static final class Account {
        private final String id;

        Account(String id) {
            this.id = id;
        }
    }
}
~~~

In the example above, the code and target class belong to the same simple application; the JVM may allow suppressing Java language access checks. However, **setAccessible(true)** is not a pass to bypass all JPMS boundaries. If the target class belongs to another named module and the package is not opened accordingly, the operation may be blocked.

Do not rely on being able to arbitrarily write to every private final field. Even when a field can be observed via reflection, modifying final fields is restricted by field kind and runtime rules; mutating immutable state also risks breaking invariants.

### 2.3. setAccessible and trySetAccessible

Two commonly encountered APIs:

- **setAccessible(true):** requests bypassing Java language access checks if the platform permits; may throw **InaccessibleObjectException** when blocked by module encapsulation.
- **trySetAccessible():** attempts to enable access, returning **false** if it cannot be granted instead of throwing InaccessibleObjectException in that case.

Example:

~~~java
import java.lang.reflect.Field;

public final class SafeInspector {
    public static Object readIfAllowed(Object target, String fieldName)
            throws ReflectiveOperationException {
        Field field = target.getClass().getDeclaredField(fieldName);

        if (!field.trySetAccessible()) {
            throw new IllegalStateException(
                "Cannot access " + target.getClass().getName()
                    + "." + fieldName
            );
        }
        return field.get(target);
    }
}
~~~

**trySetAccessible()** does not make prohibited access valid. It only allows the program to handle denial in a more controlled way. For frameworks, prefer public APIs or official extension points before considering opening deep access.

## 3. JPMS: How Does exports Differ from opens?

Starting in Java 9, the Java Platform Module System (JPMS) provides module boundaries. When migrating from a traditional classpath system to named modules, access rules can change markedly.

### 3.1. exports: Providing Public APIs

Module A may declare:

~~~java
module com.example.domain {
    exports com.example.domain.api;
}
~~~

Another module that reads module A can use the public types and members of the exported package under normal Java rules. **exports** does not allow a framework to arbitrarily open private fields or private constructors via deep reflection.

### 3.2. opens: Allowing Deep Reflection

~~~java
module com.example.domain {
    exports com.example.domain.api;
    opens com.example.domain.model to com.example.mapper;
}
~~~

Here:

- **exports** allows access to public APIs in the api package.
- **opens ... to ...** allows the mapper module to perform deep reflection into the model package.
- The model package does not necessarily have to be exported to allow consumer source code to directly reference types inside it.
- Only the specified named module has deep reflection permission through this qualified opens declaration.

**opens** does not mean allowing any module to call APIs as if the package were exported; these are two distinct mechanisms.

### 3.3. Sample module-info for an Application

Example of an application using a mapper with a known module name:

~~~java
module com.example.orders {
    requires com.example.mapper;

    exports com.example.orders.api;
    opens com.example.orders.entity to com.example.mapper;
}
~~~

In practice, **com.example.mapper** here is a placeholder name, not the real module name of Jackson or Hibernate. Confirm the actual module name, for instance via the JAR's module description and the runtime module graph, before substituting it.

If multiple frameworks need reflective access, list the exact required modules or choose an appropriate module structure. Do not open all packages merely to avoid surveying dependencies.

### 3.4. open module

You can declare:

~~~java
open module com.example.legacy {
    requires java.sql;
}
~~~

An **open module** allows deep reflection into its packages under the module mechanism. This can aid in converting legacy code, but opens a broader scope than declaring **opens** per individual package.

For new applications or controlled migrations, prefer **qualified opens** or opening specific packages, then narrow permissions once the framework supports appropriate public APIs.

### 3.5. Classpath, Unnamed Modules, and Automatic Modules

- Code on the **classpath** generally belongs to an unnamed module; its packages are not encapsulated in the same way as application-defined named modules.
- A JAR placed on the **module path** can become a named automatic module if it lacks a module descriptor.
- Automatic modules have convenient exports/opens rules for transition; once an actual module-info.java is added, access permissions may become stricter.
- Code in a named module must consider **readability**, exports, and opens; merely adding to the module path is not enough to guarantee reflection succeeds.

Therefore, an application that runs on the classpath yet fails when moved to the module path may be relying on reflective access that was previously unrestricted.

## 4. Strong Encapsulation and Internal JDK APIs

Modern JDK releases tighten access to internal parts of the JDK. Starting in Java 17, strong encapsulation of most internal APIs is enforced more strictly under JEP 403; broadly relaxing access via the old **--illegal-access** option is no longer a viable strategy to restore prior behavior.

An older library may have previously done:

~~~java
Class<?> type = Class.forName("java.lang.String");
var field = type.getDeclaredField("value");
field.setAccessible(true);
~~~

Obtaining information about a field does not mean being permitted to read the private field. When access is blocked by JPMS, the typical error is:

~~~text
java.lang.reflect.InaccessibleObjectException:
Unable to make field ... accessible:
module java.base does not "opens java.lang" to ...
~~~

The error message specifies the closed **module/package** and the **calling module** requesting access. Read those exact parts instead of applying blanket flags system-wide.

### 4.1. What Is --add-opens?

The runtime option:

~~~bash
java --add-opens=java.base/java.lang=ALL-UNNAMED -jar app.jar
~~~

allows deep reflection from code in an unnamed module into the **java.lang** package of the **java.base** module. This is solely a technical example of opening scope, not a recommendation to add this flag by default.

General syntax:

~~~text
--add-opens=<module>/<package>=<target-module>
~~~

**ALL-UNNAMED** represents all unnamed modules. When the consumer is a named module, use the appropriate module name as the target.

### 4.2. --add-exports Does Not Replace --add-opens

| Option | Purpose | What it cannot do |
|---|---|---|
| **--add-exports** | Relaxes access to public types/members in an unexported package | Does not automatically open private fields/methods for deep reflection |
| **--add-opens** | Opens a package for deep reflection by a target module | Is not a long-term approach for depending on internal JDK APIs |
| **--add-reads** | Adds a module readability relationship | Does not automatically open private members |
| **opens** in module-info.java | Grants deep reflection permission from the package-owning module | Is not equivalent to exporting public APIs |

Overusing **--add-opens** can mask the fact that a dependency does not yet support the target JDK. The sustainable path is to upgrade the library or change the design to stop using internal JDK APIs.

### 4.3. Resolution Approach in Priority Order

1. Identify the exact package/module that is blocked.
2. Identify the library and version performing reflective access.
3. Check for an updated version compatible with the target JDK.
4. Prefer standard Java APIs or public framework APIs.
5. If the package is owned by the application, consider a narrowly scoped **opens**.
6. If **--add-opens** must be used for transition, record the reason, target, owner, and removal deadline.
7. Test on the actual runtime and monitor on the next JDK upgrade.

Do not treat every **InaccessibleObjectException** as a reason to open **java.base** globally.

## 5. ORM: Reflection for Instantiating and Managing Entities

ORM (Object-Relational Mapping) maps data between tables and Java objects. Implementations such as Hibernate/JPA often use reflection, bytecode enhancement, and proxies to:

- Read entity and property annotations.
- Identify identifier fields, relationships, and mappings.
- Instantiate entities when reading data from the database.
- Set field values or invoke getters/setters depending on the access strategy.
- Track changes, lazy-load, and interact with proxies.
- Initialize collection wrappers or enhanced entities.

### 5.1. Example Entity Using Field Access

~~~java
package com.example.orders.entity;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class CustomerEntity {
    @Id
    private Long id;

    private String name;

    protected CustomerEntity() {
        // Constructor for ORM
    }

    public CustomerEntity(Long id, String name) {
        this.id = id;
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

In this mapping style, **@Id** is placed on the field, so the ORM can use field-based access. It may need to access private fields via reflection or an appropriate bytecode enhancement mechanism.

Some important constraints:

- Jakarta Persistence requires an entity to have a no-arg constructor with public or protected visibility.
- Providers may have restrictions on final classes or methods when using proxies/lazy loading.
- When modularizing the application, entity packages may need to be opened to the ORM provider's module.
- Private field mapping needs to be tested in the actual module path/runtime environment.

Do not conclude that every entity must make all fields public for the ORM to work. The issue is which access mechanism the mapping selects and what access permissions the runtime allows.

### 5.2. Field Access and Property Access

| Strategy | How mapping reads/writes values | Migration risks |
|---|---|---|
| Field access | Works with fields, potentially including private fields | JPMS opens, field names, access rules, enhancement |
| Property access | Works with getters/setters per mapping rules | Visibility, method signatures, bean conventions |
| Bytecode enhancement | Inserts or modifies bytecode for tracking/access | Class file version support, build plugins, and runtime agents |
| Proxy-based lazy loading | Generates proxies/delegates to load data on demand | Final classes/methods, constructors, class loaders, packages/modules |

When upgrading an ORM, do not convert all field access to property access as a quick fix without confirming mapping behavior. Changing the access strategy can affect property names, dirty checking, lazy loading, and serialization.

### 5.3. JPMS with Entities

Suppose the application module owns the entities:

~~~java
module com.example.orders {
    requires jakarta.persistence;

    exports com.example.orders.api;
    opens com.example.orders.entity to com.example.persistence.provider;
}
~~~

**com.example.persistence.provider** is only an illustrative name. In a real project, you must use the actual provider's module name. You also need to check whether the provider runs on the module path or classpath, whether it uses multiple supporting modules, and what configuration the official documentation specifies.

If the application is currently using the classpath, adding module-info.java during migration can introduce new errors even without changing entity source code.

### 5.4. Reflection and Proxies Are Two Different Constraints

An entity may be instantiated and have its fields populated via reflection yet still fail lazy loading because a proxy cannot create a subclass.

Example:

~~~java
@Entity
public final class InvoiceEntity {
    @Id
    private Long id;

    protected InvoiceEntity() {
    }
}
~~~

Some subclass-based proxy mechanisms cannot extend a final class. However, a class being final does not automatically prove that every ORM or every access path fails; the provider might use enhancement or another mechanism.

Therefore, test separately:

1. Persist an entity.
2. Load the entity from the database.
3. Access a lazy relationship.
4. Call a method requiring interception.
5. Verify the actual proxy/enhancement used by the provider.

### 5.5. Java EE to Jakarta EE

A major framework migration may simultaneously change packages from **javax.persistence** to **jakarta.persistence**. This is an API/dependency issue distinct from encapsulation, though they often appear at the same time.

If an application encounters an unrecognized entity error, do not simply add **--add-opens**. Check the correct Jakarta/Hibernate library set, annotation namespace, provider, and JDK version before investigating reflective access.

## 6. Serializers: Reflection for JSON, XML, and Interchange Data

Serializers/deserializers need to convert objects into data and reconstruct objects from data. Libraries such as Jackson may rely on:

- Public getters/setters.
- Field visibility.
- Annotations specifying property names.
- Constructors or factory methods.
- Record components.
- Generic type metadata.
- Polymorphic type information.
- Converters for special types.

### 6.1. DTOs with Public Accessors

~~~java
package com.example.api;

public final class UserDto {
    private final String id;
    private final String displayName;

    public UserDto(String id, String displayName) {
        this.id = id;
        this.displayName = displayName;
    }

    public String getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

Serialization can work through public accessors. However, deserialization requires an appropriate way to construct the object. A serializer may fail to infer constructor arguments properly if required metadata or configuration is missing.

### 6.2. Explicitly Declared Constructors

Jackson example with creator:

~~~java
package com.example.api;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;

public final class UserDto {
    private final String id;
    private final String displayName;

    @JsonCreator
    public UserDto(
            @JsonProperty("id") String id,
            @JsonProperty("displayName") String displayName) {
        this.id = id;
        this.displayName = displayName;
    }

    public String getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

Explicitly specifying the creator and property names makes the data contract easy to identify. It does not automatically solve all JPMS issues: the module containing the DTO must still export or open the package to match how the framework accesses constructors/methods.

### 6.3. Records and Reflection

Java records can be a good fit for immutable DTOs:

~~~java
package com.example.api;

public record UserView(String id, String displayName) {
}
~~~

Records provide components, accessors, and a canonical constructor by language definition. A serializer library supporting records can read this metadata without mutating private final fields.

However, check the specific version of the serializer library: not all older versions understand records or how to instantiate them properly. When upgrading the JDK and serializer together, errors may come from lacking record support rather than from JPMS.

### 6.4. Field Visibility and the Risks of Overly Broad Access

Some serializers have a mode that discovers all private fields. This is convenient for legacy models but creates extra dependencies on implementation details and reflective access permissions.

Example configuration logic that can broaden field discovery scope:

~~~java
ObjectMapper mapper = new ObjectMapper();
mapper.setVisibility(
    PropertyAccessor.FIELD,
    JsonAutoDetect.Visibility.ANY
);
~~~

This snippet only illustrates the configuration approach; a real project requires the appropriate imports and Jackson dependencies.

Possible consequences include:

- Internal fields are unintentionally included in JSON.
- Renaming a private field becomes a data change.
- Object graphs cause cycles or unintended lazy loading.
- Private fields belonging to a named module are blocked when the framework attempts access.
- Data security rules are easily bypassed if relying solely on serializer defaults.

Prefer DTOs with clear contracts for public APIs instead of directly serializing entities or all private fields.

### 6.5. Contracts Before and After Migration

Suppose an old DTO had a field **customerId**, but the new version renames it to **id**. If the serializer uses field names directly, the JSON output can change from:

~~~json
{"customerId":"C-001"}
~~~

to:

~~~json
{"id":"C-001"}
~~~

The Java code still compiles; binary compatibility of the class might not even be the main issue. However, existing API consumers reading **customerId** will fail.

Therefore, serializer tests must compare JSON/XML contracts and actual data, not merely verify that **ObjectMapper** runs without throwing an exception.

## 7. Dynamic Proxies, AOP, and Reflection

A proxy is an intermediary object that receives calls on behalf of a target object. Reflection is often used to inspect interfaces, methods, and dispatch calls. Some proxy mechanisms generate new classes at runtime.

### 7.1. JDK Dynamic Proxies for Interfaces

Example using standard Java:

~~~java
package com.example.proxy;

import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class ProxyDemo {
    public interface PaymentService {
        String pay(String invoiceId);
    }

    public static final class RealPaymentService implements PaymentService {
        @Override
        public String pay(String invoiceId) {
            return "paid:" + invoiceId;
        }
    }

    public static void main(String[] args) {
        PaymentService target = new RealPaymentService();

        InvocationHandler handler = (proxy, method, arguments) -> {
            System.out.println("calling " + method.getName());
            return method.invoke(target, arguments);
        };

        PaymentService proxy = (PaymentService) Proxy.newProxyInstance(
            PaymentService.class.getClassLoader(),
            new Class<?>[]{PaymentService.class},
            handler
        );

        System.out.println(proxy.pay("INV-001"));
    }
}
~~~

JDK dynamic proxies are primarily interface-based. They generate a class that can be used under the interface type and forward calls to an **InvocationHandler**. This is not a way to directly create a subclass of an arbitrary concrete class.

Notes on the example:

- **method.invoke()** can wrap exceptions thrown by the target in **InvocationTargetException**. A production handler must handle this appropriately.
- **Object** methods, default interface methods, and exception declarations have specific dispatch rules.
- Interfaces must satisfy the visibility/module/package requirements of the Proxy mechanism.
- A proxy may be created successfully, yet transaction, security, or exception mapping behavior still needs separate testing.

### 7.2. Subclass-Based Proxies

CGLIB, Byte Buddy, or AOP frameworks can create subclasses and override methods to inject behavior.

~~~text
Client
   |
   v
Proxy subclass
   |
   | intercept method
   v
Target logic
~~~

Common constraints:

- A **final** class cannot be subclassed.
- A **final** method cannot be overridden.
- A private method cannot be overridden.
- Constructors and class loaders can affect instantiation.
- JPMS access and package placement can affect class generation.
- A **sealed** class restricts direct subclasses, creating difficulties for generated subclasses not listed in permits.

During migration, do not conclude that merely switching from JDK proxies to class proxies will always resolve errors. The two mechanisms have different type contracts and constraints.

### 7.3. Spring AOP: Interface Proxies and Class Proxies

In Spring AOP, the framework can create interface-based or class-based proxies depending on configuration and conditions. With class-based proxies, final classes/methods can prevent advice from being applied as intended.

Example:

~~~java
public class BillingService {
    public final void charge() {
        // Business logic
    }
}
~~~

If AOP logic needs to override **charge()** in a proxy subclass, the final method prevents that mechanism. However, if the system uses interface proxies and invokes through the interface, the constraints may differ.

An easily confused scenario is **self-invocation**: a call from one method to another within the same object can bypass the outer proxy, causing advice not to run. This is an AOP behavioral risk; adding **--add-opens** will not solve it.

### 7.4. Proxies and Sealed Hierarchies

If a framework wants to create a direct subclass of a sealed class or a direct implementation of a sealed interface, the generated type must comply with the permitted set. For libraries needing dynamic extension, a sealed design may be unsuitable or require an explicit **non-sealed** branch.

Do not use reflective access flags to try to bypass **final/sealed** rules: these are inheritance and class verification rules, not merely private field read permissions.

## 8. Testing Libraries and Reflection

Testing frameworks may use reflection to discover and invoke test methods, process annotations, instantiate test objects, inject dependencies, or mock calls.

### 8.1. JUnit and Test Discovery

JUnit Jupiter typically discovers methods annotated with markers such as **@Test** and invokes them according to the appropriate lifecycle.

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class CalculatorTest {
    @Test
    void addsNumbers() {
        assertEquals(4, 2 + 2);
    }
}
~~~

Non-public test methods can still be handled by the framework depending on the framework and access mechanisms. When test classes move into a named module, module boundaries can prevent the test engine from reflectively accessing an unopened package.

Do not resolve this error by making every method public if the test framework's requirement is deep reflection into the package. Verify the module setup, the test engine module name, and how the build tool organizes test sources.

### 8.2. Mockito, Byte Buddy, and Instrumentation

Mockito and mocking libraries typically use several techniques:

- Creating mocks based on interfaces or subclasses.
- Generating bytecode for mock classes.
- Using Java instrumentation/agents for certain mock types or scenarios.
- Discovering methods/constructors via reflection.
- Altering dispatch to record invocations and configure behavior.

When upgrading the JDK, an older version of Mockito/Byte Buddy may not yet support the new class file version. Failures when creating mocks are not necessarily caused by business classes having private fields or modules missing opens.

Some mock makers can support mocking final classes via instrumentation, while other mock makers use subclasses and cannot extend final classes. Check the Mockito version, mock maker configuration, and JDK in use.

### 8.3. Agents and Runtime Policies

Instrumentation mechanisms may use a Java agent specified at startup or via dynamic attachment. JDK policies and warnings regarding agents can change across releases.

During migration:

- Read actual JVM warnings about agent attachment.
- Identify which library invokes the agent or attach API.
- Consult the corresponding Mockito/Byte Buddy/JDK documentation.
- Prefer the official agent configuration supported by the vendor.
- Do not suppress warnings or open permissions globally without understanding the reason.

Tests may fail in CI while passing in an IDE because JVM launch modes, attach permissions, or runner security policies differ.

### 8.4. JaCoCo and Class File Versions

A coverage tool that uses bytecode instrumentation such as JaCoCo must support the class file version generated by the new JDK. Errors involving unsupported class file versions or instrumentation failures may come from an outdated coverage tool version.

In this situation, adding **--add-opens** is no substitute for upgrading JaCoCo or the underlying bytecode processing library.

### 8.5. The Test Framework Is Not the Production Runtime Environment

The test suite may proactively open packages, use agents, and run mock makers that do not exist in production. Therefore:

- Passing tests do not guarantee production reflection will succeed.
- Running in production does not guarantee the test suite works on the new JDK.
- Both must be tested using the actual JVM arguments and dependency graph of each environment.
- If tests add temporary flags, clearly document whether those flags apply only to tests or also to production.

## 9. Distinguishing Common Reflection Errors

| Error / symptom | Possible cause | First step to check |
|---|---|---|
| **InaccessibleObjectException** | setAccessible was blocked by module encapsulation | Read module/package/caller in the message |
| **IllegalAccessException** | Reflective operation is not permitted under access rules | Visibility, exports/opens, caller |
| **NoSuchFieldException** | Field does not exist by that name or lookup method | Name, actual class, declared/inherited |
| **NoSuchMethodException** | Method/constructor not found for that signature | Parameter types, overloads, visibility |
| **InvocationTargetException** | Invoked method/constructor threw an exception | Inspect **getCause()** for the root error |
| **ExceptionInInitializerError** | Static initialization of the class failed | Cause and static initializer |
| **IncompatibleClassChangeError** | Binary relationships changed, such as final/sealed | Compare old/new class files and hierarchy |
| **NoClassDefFoundError** | Required class cannot be loaded or initialized | Runtime dependencies and cause |
| **ClassCastException** | Proxy/object is not of the type expected by the consumer | Interface/class proxy and class loaders |
| **UndeclaredThrowableException** | JDK proxy wrapped an undeclared checked exception | InvocationHandler and cause |
| **UnsupportedClassVersionError** | Bytecode is incompatible with the runtime | JDK compiler, class major version, JDK runtime |
| **VerifyError** | Bytecode or type relationships are invalid during verification | Bytecode instrumentation/version and dependencies |
| Mockito mock creation failure | Byte Buddy/mock maker/agent is incompatible | Mockito, Byte Buddy, agent, and JDK versions |
| Entity lazy-loading failure | Proxy/enhancement, session, hierarchy, or mapping | ORM logs, entity modifiers, access mode |
| JSON output changed | Serializer configuration or property discovery changed | Contract/golden JSON comparison |

One error can have multiple causes. For example, **NoSuchMethodException** can result from a renamed method, different parameters, or a framework looking for a nonexistent default constructor; it is not automatically a JPMS error.

### 9.1. Investigating the Cause Chain, Not Just the Top-Level Exception

~~~java
try {
    method.invoke(target);
} catch (java.lang.reflect.InvocationTargetException ex) {
    Throwable cause = ex.getCause();
    System.err.println("Underlying failure: " + cause);
    throw ex;
}
~~~

An exception thrown by the target method is wrapped by reflection. When reading a long framework stack trace, look for the deepest **Caused by**, while also examining the proxy/serializer creation context to trace the call path.

### 9.2. Class Loader Errors

Two classes with the same fully qualified name loaded by different class loaders can be treated by the JVM as different runtime types. Plugin architectures, application servers, or custom test class loaders can create this situation.

The typical symptom is **ClassCastException**, not directly related to **setAccessible**. When investigating, check the class loader of the target class, the class loader creating the proxy, and the JARs loaded at runtime.

## 10. Inspection Tools During Migration

### 10.1. Printing Java Version and Module Information

~~~bash
java -version
javac -version
java --list-modules
~~~

Inside a running application, you can check:

~~~java
Class<?> targetClass = SomeType.class;

System.out.println("module=" + targetClass.getModule().getName());
System.out.println("package=" + targetClass.getPackageName());
System.out.println("loader=" + targetClass.getClassLoader());
~~~

If the module name is **null**, the class usually belongs to an unnamed module. Do not infer that lacking a module name means the JVM applies no other access rules.

### 10.2. jdeps to Find Dependencies on JDK Internal APIs

~~~bash
jdeps --jdk-internals app.jar
~~~

This command helps detect certain static references to internal JDK APIs in bytecode. However, references constructed from class name strings and invoked via reflection may go undetected; a clean output does not prove the application is completely free of internal API usage.

### 10.3. javap to Inspect Bytecode and Modifiers

~~~bash
javap -classpath app.jar -p -v com.example.api.SomeType
~~~

You can inspect:

- Method descriptors.
- Constructors and access flags.
- Final/sealed-related metadata.
- Superclasses and interfaces.
- Annotations and class-file version.

Use it to verify the artifact actually being deployed, not just the source in the working tree.

### 10.4. Module Resolution Traces and JVM Command Line

You can run:

~~~bash
java --show-module-resolution --module-path mods --module com.example.app/com.example.Main
~~~

When investigating an already running process, tools like **jcmd** can provide JVM and command line information within permitted access bounds.

Items to record include JDK vendor/version, module path/classpath, JVM arguments, build artifact checksums, and the dependency graph. This information helps distinguish code bugs from environment issues.

## 11. Configuring Gradle When Frameworks Need Reflective Access

For modularized applications, prefer configuring **module-info.java** with **opens**. For test processes on the classpath that need access to packages in a named module, a specifically scoped **--add-opens** can be used.

Gradle Groovy DSL example for the test JVM:

~~~groovy
tasks.withType(Test).configureEach {
    jvmArgs '--add-opens=com.example.domain/com.example.domain=ALL-UNNAMED'
}
~~~

The example assumes the opened module is **com.example.domain** and the package is also named **com.example.domain**. Replace them with the actual module and package names.

If the test modules are named modules, the target can be the named module name instead of **ALL-UNNAMED**.

### 11.1. Test Flags Differ from Compiler Flags

- **javac options:** control compilation and module access needed at compile time.
- **Test JVM arguments:** apply to the process running JUnit/Mockito/ORM/serializer tests.
- **JavaExec JVM arguments:** apply to processes launched by JavaExec.
- **Production JVM arguments:** apply to the actual application process.

Setting **--add-opens** in a Test task does not automatically pass it to the application process. Setting a flag on the Gradle daemon also does not mean every forked process will receive that flag.

### 11.2. Diagnosing Which JVM a Task Runs On

~~~bash
./gradlew -version
./gradlew test --info
~~~

Cross-check logs and toolchain configuration to determine the JDK running Gradle, the compiler JDK, and the test worker JDK. On Windows, use **gradlew.bat** accordingly.

Do not run build tasks solely to “verify” migration guide documentation if the current workflow only asks for writing lessons; the commands above are examples for learners to practice in an appropriate project.

## 12. Configuring Maven Surefire and Failsafe

Maven can fork test JVMs via Surefire or Failsafe. If a temporary package opening is needed for tests, a runtime argument can be set:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <argLine>
            --add-opens=com.example.domain/com.example.domain=ALL-UNNAMED
        </argLine>
    </configuration>
</plugin>
~~~

Configure Failsafe correspondingly if integration tests also need access. If the project uses JaCoCo, a debugger, or a Java agent with its own **argLine**, merge them properly so other arguments are not overwritten.

If Surefire does not fork a JVM, flags for child processes will not modify the JVM that already started Maven. Configuration must match the actual test execution mode.

Do not add opens for the entire application just because one test fixture needs to access a private field. Review how the test is written or open access specifically for the test module first.

## 13. Sustainable Fix Strategy

When encountering a reflection error, prioritize the solution with the smallest scope and the least reliance on internal details.

### 13.1. Recommended Order

1. **Confirm the root error:** read the exception, cause chain, JDK, modules, and actual JARs.
2. **Identify the actor:** ORM, serializer, proxy, test framework, or application reflection?
3. **Check dependency compatibility:** does the library support the target JDK and framework?
4. **Upgrade appropriate dependencies:** prefer versions with official support that resolve the error.
5. **Use public APIs/clear contracts:** accessors, constructors, creators, DTOs, extension interfaces.
6. **Open packages deliberately:** when the package is owned by the application and the framework genuinely needs deep reflection.
7. **Use --add-opens under control:** only as a transitional measure with an owner and a removal plan.
8. **Write regression tests:** verify the exact ORM/JSON/proxy/mock path that previously failed.

### 13.2. Do Not Open Internal JDK Packages Just to “Make Errors Go Away”

A command with **--add-opens=java.base/java.lang=ALL-UNNAMED** might help an old dependency get past a specific encapsulation error. However, it does not guarantee that the dependency is compatible with new class files, security policies, module graphs, or runtime behavior of the new JDK.

Flags can also become scattered across local, CI, staging, and production environments. If one place is missed, the error will come back.

### 13.3. Do Not Serialize Entities Directly When Unnecessary

Using stable DTOs for public APIs helps separate:

- The consumer's data contract.
- The ORM's mapping and lazy-loading semantics.
- The entity's private fields/constructors.
- Internal module structure within the application.

DTOs do not solve every reflection error, but they reduce the number of places forcing the serializer to know ORM details.

### 13.4. Design Extensions Instead of Hacking Private Members

If a plugin or test needs internal state, consider an appropriate query API, hook, or test fixture instead of reflecting into private fields. A direct dependency on a private field name easily breaks during refactoring even without a JDK upgrade.

## 14. Combined Migration Scenario: Old JDK to New JDK

Suppose a Java system runs on an older JDK using an ORM, Jackson, Spring AOP, and Mockito. After upgrading the JDK, three groups of errors occur:

1. The ORM fails to instantiate an entity in a named module.
2. The serializer fails when reading a private field of a DTO.
3. The test suite fails to create a mock for a final class.

Do not assume all three errors share the same root cause or the same solution.

### Phase A: Lock Down the Baseline

Record:

- Current versions of the JDK, Gradle/Maven, frameworks, and dependencies.
- Released artifacts and checksums.
- module-info.java files, if any.
- JVM flags of the application, CI, and tests.
- JSON/XML contracts before migration.
- Representative integration tests for the ORM, serializer, and proxies.

### Phase B: Categorize and Isolate

| Issue | Possible cause | Evidence to gather |
|---|---|---|
| ORM entity fails | Entity package is not open, old provider, or unsuitable constructor | Full stack trace, entity mapping, module graph |
| JSON private field fails | Deep reflection is denied or property discovery changed | InaccessibleObjectException, serializer version, payload |
| Final class mock fails | Mock maker/Byte Buddy/agent is incompatible | Mockito version, JDK, mock configuration |
| Proxy advice does not run | Final method/class, interface/class proxy, or self-invocation | Runtime proxy type, call path, test advice |
| Class file error in coverage | JaCoCo/bytecode library does not yet support target | Major version, tool versions, stack trace |

### Phase C: Fix by Root Cause

- ORM: update to a compatible provider, verify mappings/constructors, and configure narrow module opens if needed.
- Serializer: upgrade the library, use explicit constructors/creators, adjust DTOs, and verify module access.
- Mocking: upgrade the mocking framework and bytecode tools per documentation, identify the agent mechanism; do not automatically add opens for all packages.
- Proxy: inspect modifiers and proxy strategy, and adjust the extension design if needed.
- Coverage: upgrade the tool to support the new class-file version.

### Phase D: Verification

Re-run the exact scenarios that previously failed and add clear acceptance criteria:

- ORM persist, load, and lazy relationships work on the new JDK.
- JSON serialization/deserialization works with old and new data; no unplanned contract changes.
- Proxies execute advice exactly once in the required business flows.
- Mockito creates mocks and verifies behavior on the target test runner.
- No remaining requirements to open internal JDK packages without an owner or rationale.
- CI, staging, and production use controlled dependency/runtime configurations.

## 15. Matrix-Based Compatibility Testing

A test suite running on only one JDK and one deployment mode may miss differences between environments.

| Test axis | States to consider |
|---|---|
| JDK | Baseline, target; versions declared as supported |
| Layout | Classpath, module path if the project supports both |
| ORM | Field access, property access, lazy loading, enhancement |
| Serializer | Serialize, deserialize, constructors, records, nullable/unknown properties |
| Proxy | Interface proxy, class proxy, final methods, self-invocation |
| Test | JUnit discovery, Mockito mock maker, coverage, integration tests |
| Deployment | Local, CI worker, container runtime, staging |
| Consumer | Current consumers and previously compiled older consumers if binary compatibility is needed |

You do not necessarily need to run every Cartesian product combination. Choose cases based on risk and support policy, especially where module boundaries or dependencies differ.

### 15.1. Golden Data Tests for Serializers

Save representative payloads to compare outputs:

~~~json
{
  "id": "C-001",
  "name": "Nguyen An",
  "active": true
}
~~~

Verify:

- Field names remain unchanged unless a versioning decision was made.
- Data types, nulls, and unknown fields are handled consistently.
- Polymorphic payloads if the application uses type metadata.
- Internal private fields are not accidentally exposed.
- Old payloads can be read on the new version according to the published contract.

### 15.2. Regression Tests for ORMs

An integration test should:

1. Create an entity through the business path.
2. Persist and flush.
3. Clear the persistence context.
4. Load the entity by id.
5. Access a relationship requiring lazy loading within an appropriate transaction.
6. Compare state and mapping behavior.

This test must run with a representative provider, database configuration, and module layout. Testing with mock repositories alone does not prove ORM reflection/lazy proxies work.

### 15.3. Regression Tests for AOP/Proxies

A test should call the method externally through the actual bean/proxy, then confirm the expected advice was applied. If you want to test self-invocation, create a separate test for internal calls to observe the difference.

Do not invoke the target object directly and conclude that the proxy works.

### 15.4. Regression Tests for Mocking

Tests need to verify:

- Mocks can be created on the target JDK.
- Final classes/methods, if used in tests, have the proper supporting mechanism.
- Tests do not rely on dynamic attach unexpectedly forbidden by the CI environment.
- Coverage agents and mocking agents do not conflict.
- No new runtime warnings are ignored without analysis.

## 16. Common Mistakes

### 16.1. Upgrading Only the JDK While Keeping All Bytecode Tools Unchanged

Mocking, coverage, proxies, and ORM enhancement can depend on libraries that read/write class files. Newer JDKs usually come with new class-file versions. If a tool does not support this version, errors can occur before business code runs.

How to handle: inspect the support matrix of each bytecode library and upgrade to a compatible version.

### 16.2. Adding --add-opens by Trial-and-Error Until It Runs

This approach easily produces hard-to-maintain configurations. Upon release, a missing flag in a container or batch process can cause the error to reappear.

How to handle: identify the package/module/caller from the stack trace, fix the dependency or design first, and use narrow flags only as a documented transitional step.

### 16.3. Making All Fields Public

Making fields public alters encapsulation and increases data exposure risk. It also does not automatically fix class-file instrumentation, proxy, or property mapping errors.

How to handle: use public accessors/creators with clear contracts, or selectively open packages when a framework officially requires deep reflection.

### 16.4. Testing on the Classpath While Deploying on the Module Path

Errors only appear in production because module boundaries differ from tests.

How to handle: run integration tests matching the actual deployment layout and JVM arguments.

### 16.5. Confusing Reflective Access Errors with Mapping Errors

A DTO deserializing incorrectly may be due to a missing constructor or annotation, not a closed module. An entity failing to lazy-load may be due to a closed session, not private field permissions.

How to handle: read the cause chain and pinpoint the specific failing operation.

### 16.6. Assuming Proxies Always Use Subclasses

JDK interface-based proxies work differently from class-based proxies. A final class may not cause the same consequence if the system uses only interface proxies. Conversely, a sealed interface can cause issues for generated implementations.

How to handle: identify the actual proxy type, class loader, and method contracts.

### 16.7. Running Only Unit Tests with Mocks

Mocking repositories or serializers can bypass the very reflection/proxy mechanisms that need testing.

How to handle: add integration tests with the real ORM, JSON mapper, and proxies on the target runtime.

## 17. Risk Register Template and Package-Opening Decisions

When a reflection error is discovered, record it to distinguish workarounds from sustainable solutions.

| Field | Content |
|---|---|
| Risk ID | For example, REF-001 |
| Component | ORM, serializer, proxy, or testing |
| JDK baseline/target | Versions being migrated |
| Library version | Actual dependency and artifact |
| Failing operation | Field access, constructor, method, proxy generation |
| Exception | Error name and root cause |
| Module/package | Blocked module/package |
| Caller module | Module requesting permission |
| Root cause | For example, old provider uses deep reflection into a closed package |
| Preferred fix | Upgrade library, public API, creator, qualified opens |
| Temporary workaround | Specific flag and scope if mandatory |
| Owner | Responsible team |
| Acceptance evidence | Test ID, log, artifact checksum |
| Removal date | When to remove the workaround |
| Residual risk | Remaining risk |

Example:

~~~text
Risk ID: REF-001
Component: Serialization
Root cause: Mapper needs deep reflection into the model package
Preferred fix: Explicit DTO/creator and a supported mapper version
Temporary workaround: Qualified opens only for the mapper module
Evidence: JSON contract test + runtime integration test
Owner: API team
Done when: No remaining dependency on JDK internal packages
~~~

A fix is only considered complete when there is evidence that it runs on the target runtime. “Added flag” is merely a configuration action, not compatibility evidence.

## 18. Pre-Completion Migration Checklist

### Survey

- [ ] List the ORM, serializer, proxy, mocking, and coverage libraries in use.
- [ ] Lock down baseline/target JDK, build tool, and dependency versions.
- [ ] Determine whether the application runs on the classpath or module path.
- [ ] Identify modules/packages containing entities, DTOs, and extension points.
- [ ] Find code using Class.forName, getDeclaredField, setAccessible, or MethodHandles private lookup.
- [ ] Confirm whether internal JDK APIs are used.
- [ ] Save JVM argument configurations for local, CI, and production.

### ORM and Serializer Compatibility

- [ ] The ORM provider supports the target JDK and framework.
- [ ] Entity mapping, constructors, and field/property access have been verified.
- [ ] Lazy-loading proxies or bytecode enhancement work properly.
- [ ] The serializer supports the DTOs, records, and constructors in use.
- [ ] JSON/XML contracts have no unplanned changes.
- [ ] No unintended private fields appear in public data.

### Proxies and Testing

- [ ] Identify actual interface-based vs. class-based proxies.
- [ ] Assess the impact of final/sealed modifiers and class loaders.
- [ ] Verify AOP interception and self-invocation.
- [ ] Mockito, Byte Buddy, and coverage tools support the target JDK.
- [ ] Test runners and agents are configured according to the real environment.
- [ ] Integration tests exist that do not rely entirely on mocks.

### JPMS and Operations

- [ ] Clearly distinguish exports, opens, and add-opens.
- [ ] Qualified opens only open necessary packages to the right modules.
- [ ] Every temporary --add-opens has an owner and a removal plan.
- [ ] Do not use --illegal-access as a default recovery mechanism.
- [ ] CI, staging, and production share consistent JDK and JVM arguments.
- [ ] Stack traces, test reports, dependency graphs, and artifact checksums have been saved.
- [ ] Residual risks have assigned owners and acceptance criteria.

## 19. Official Documentation to Cross-Check

During actual migration work, cross-check against the documentation of the exact JDK and frameworks:

- **Java Reflection API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/package-summary.html
- **AccessibleObject:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html
- **JPMS / JEP 261:** https://openjdk.org/jeps/261
- **Strong Encapsulation / JEP 403:** https://openjdk.org/jeps/403
- **Java Dynamic Proxy API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Proxy.html
- **Java Module System (JLS):** https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.7
- **Jakarta Persistence:** https://jakarta.ee/specifications/persistence/
- **Jackson:** https://github.com/FasterXML/jackson
- **Mockito:** https://site.mockito.org/
- **JUnit 5:** https://junit.org/junit5/

Documentation for frameworks, ORM providers, and mocking tools must be checked for the specific version. There is no universal **--add-opens** combination suitable for every project.

---

**Conclusion:** Reflection is a runtime contract that is often invisible to the compiler. When upgrading Java or moving from the classpath to the module path, identify which libraries need access to which members, distinguish **exports** from **opens**, verify JDK support for ORM/serializer/proxy/testing tools, and confirm with integration tests on the target runtime. Use access-opening only as a scoped, evidence-backed solution; prefer public APIs, stable DTOs, and supported dependencies to reduce long-term risk.