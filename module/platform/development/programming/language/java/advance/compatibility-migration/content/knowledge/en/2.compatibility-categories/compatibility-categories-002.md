# Binary compatibility: running compiled components without recompiling

In the **Compatibility Categories** group of **Java Advance Compatibility Migration**, binary compatibility answers a very practical question: after a Java library is upgraded, can a program compiled against the old version continue running against the new version without being recompiled?

This is a key requirement when releasing shared libraries, plugins, SDKs, frameworks, or independently deployed components. An application may already be packaged as a JAR and running in another environment; the library provider still needs to upgrade the library without forcing every consuming application to recompile immediately.

## 1. Understanding binary compatibility accurately

A new library version is **backward binary-compatible** with an old version when programs already compiled against the old library can still be loaded, linked, and executed by the JVM when the old library is swapped for the new one, under matching appropriate runtime conditions.

Typical flow:

~~~text
Library version 1
        |
        v
Compile Client application
        |
        v
Client.class / client.jar
        |
        |  Replace library version 1 with version 2
        v
Library version 2 + old Client.class
        |
        v
JVM loads, links, and runs
~~~

The core point is that the Client's class file stays unchanged. The JVM must locate the classes, fields, and methods referenced by the old bytecode.

Distinguish several concepts:

| Compatibility type | Question to answer |
|---|---|
| Binary compatibility | Can already-compiled bytecode still link and run against the new version? |
| Source compatibility | Does old source code still compile against the new version? |
| Behavioral compatibility | Does the program continue producing the same results and effects as before? |
| Data compatibility | Can stored data, serialized objects, or old schemas still be read and written? |
| Protocol compatibility | Can components communicating via HTTP, messages, or wire protocols still understand one another? |

A change can be binary-compatible yet source-incompatible or behavior-incompatible. For example, adding an overload usually does not break old bytecode, yet can make a call in old source code ambiguous when recompiled. Likewise, changing the return value of a method whose binary signature stays identical can alter application behavior.

In this lesson, the compatibility direction primarily examined is **a new library running alongside a client compiled against an old library**. The reverse direction — a new client running against an old library — is a different requirement and is not automatically guaranteed.

## 2. Why can the JVM run old bytecode?

When compiling Java source, **javac** translates source code into bytecode inside **.class** files. Bytecode does not contain only executable instructions; it also holds a constant pool storing symbolic references to classes, methods, fields, and related data types.

For example, the client calls:

~~~java
printer.print("Hello");
~~~

In bytecode, this call is represented as a reference to the owning class, the method name, and the method descriptor. At runtime, the JVM uses that information to locate the matching member among loaded classes.

A method descriptor specifies parameter types and return type. Example:

~~~text
(Ljava/lang/String;I)Ljava/lang/String;
~~~

This descriptor means the method takes a **String** and an **int**, and returns a **String**.

Common descriptors:

| Java type | Descriptor notation |
|---|---|
| **int** | **I** |
| **long** | **J** |
| **boolean** | **Z** |
| **void** | **V** |
| **String** | **Ljava/lang/String;** |
| **int[]** | **[I** |
| **String[]** | **[Ljava/lang/String;** |

Because descriptors are part of binary references, two methods with the same name yet different parameters are distinct methods at the bytecode level. The return type also belongs to the JVM descriptor. Hence changing the return type alters the reference old clients search for.

Common bytecode instructions for member access include:

- **invokevirtual**: invokes an instance method using dynamic dispatch.
- **invokeinterface**: invokes a method through an interface.
- **invokestatic**: invokes a static method.
- **invokespecial**: used for special calls such as constructors, private methods, or **super** calls.
- **getfield** and **putfield**: reads and writes instance fields.
- **getstatic** and **putstatic**: reads and writes static fields.

When linking a reference, the JVM must locate a matching member and verify constraints such as member kind, access permissions, and inheritance hierarchy. If the new library no longer satisfies a reference recorded in old bytecode, errors may surface only at runtime.

### Generics and type erasure

Java generics are checked primarily at compile time. The JVM usually operates on erased types. For instance, **List<String>** and **List<Integer>** both have **List** as their runtime form.

~~~java
public String find(List<String> values) {
    return values.get(0);
}
~~~

Type arguments do not turn the runtime descriptor into a distinct **List<String>** type. Consequently, changing generic type arguments while preserving the erased type may stay binary-compatible, whereas recompiling source code may produce errors or warnings. If a change alters erasure, the descriptor can change and old clients may fail to link.

Generic signature metadata can still be read by reflection tools from class attributes, so binary compatibility does not guarantee every reflection behavior stays identical.

## 3. Changes that usually preserve binary compatibility

The safe rule is preserving all members referenced by old clients while adding new capabilities without breaking existing linkage paths.

| Change | Typical binary impact | What to watch |
|---|---|---|
| Adding a new class | Usually compatible | Must not alter existing classes used by clients. |
| Adding a new method | Usually compatible | Check interfaces, subclasses, and dynamic dispatch. |
| Adding an overload | Usually compatible with old bytecode | Recompiling source may become ambiguous when the new overload enters method resolution. |
| Adding a new field | Usually compatible | Verify field names and types do not collide with existing usage. |
| Changing a method body while keeping the signature | Usually binary-compatible | Can break behavioral compatibility if results, exceptions, or side effects change. |
| Adding a **default** method to an interface | Usually safer than adding an abstract method | Conflicts can arise if multiple interfaces supply conflicting default methods. |
| Adding annotations or metadata | Usually leaves descriptors unchanged | Reflection, frameworks, or annotation processors may observe the change. |

These points are practical guidelines, not blanket guarantees for every system. Inspect inheritance trees, client-implemented interfaces, how frameworks look up members, and reflection behavior as well.

### Adding overloads: old bytecode and new compiles can behave differently

Suppose version 1 has:

~~~java
public class MessageFormatter {
    public String format(String value) {
        return "[" + value + "]";
    }
}
~~~

Version 2 adds:

~~~java
public String format(Object value) {
    return String.valueOf(value);
}
~~~

Old bytecode already points to **format(String)** via its specific descriptor. When running against version 2, the JVM still resolves that exact method.

However, if old source code is recompiled, compiler overload resolution runs again. With complex argument types, **null**, generics, or inferred types, a new overload can alter which method is selected or render the call ambiguous.

Therefore, source compatibility and binary compatibility must be tested separately.

## 4. Changes that readily break binary compatibility

The following changes typically break references recorded in old bytecode:

| Change | Possible outcome when running old clients |
|---|---|
| Removing or renaming a class | **NoClassDefFoundError** |
| Removing or renaming a method | **NoSuchMethodError** |
| Changing parameter or return types in ways altering descriptors | **NoSuchMethodError** |
| Removing or renaming a field | **NoSuchFieldError** |
| Switching a field or method between **static** and instance | **IncompatibleClassChangeError** |
| Narrowing access visibility of a member used by old clients | **IllegalAccessError** |
| Changing a type from class to interface or vice versa | **IncompatibleClassChangeError** |
| Making incompatible inheritance or method-resolution changes | **AbstractMethodError**, **IncompatibleClassChangeError**, or other linkage errors |
| Removing a constructor called by old clients | **NoSuchMethodError** |

### Removing or changing method signatures

Version 1:

~~~java
public class PaymentService {
    public Receipt pay(long amount) {
        return new Receipt(amount);
    }
}
~~~

A client compiled against this version references **pay(long)** and return type **Receipt**.

If version 2 keeps only:

~~~java
public class PaymentService {
    public Receipt pay(String amount) {
        return new Receipt(Long.parseLong(amount));
    }
}
~~~

then the old method has vanished from the binary API. Having a method with the same name does not let the JVM relink, because descriptors differ. Old clients can throw **NoSuchMethodError**.

A safer migration keeps the old method and delegates to the new API:

~~~java
public class PaymentService {
    public Receipt pay(long amount) {
        return pay(String.valueOf(amount));
    }

    public Receipt pay(String amount) {
        return new Receipt(Long.parseLong(amount));
    }
}
~~~

The old method can be marked **@Deprecated** to signal migration guidance. Remove it only once a breaking release is planned and forcing client recompilation is acceptable.

### Changing access modifiers

If the old version exposed a **public** method and the new version makes it **private**, old bytecode still references that method. When the JVM checks access permissions, clients can fail with **IllegalAccessError**.

Changing **public** to **protected** or package-private must also be treated as potentially breaking for clients outside the narrower access boundary. Never assume an API stays compatible merely because one known client happens to share the same package or module.

### Changing between class and interface

Classes and interfaces serve distinct roles in bytecode and call resolution. A client compiled against a class cannot arbitrarily substitute an interface with the same name. Changing that declaration kind can trigger **IncompatibleClassChangeError**.

Similarly, changing inheritance relationships can alter inherited methods, overrides, or JVM call resolution. Verify such changes against real clients and implementing classes.

## 5. Evolving interfaces and abstract classes

Interfaces often serve as extension boundaries implemented independently by multiple teams or modules. Consequently, interface changes require more care than changes to classes owned by a single application.

### Adding an abstract method to an interface

Suppose version 1 has:

~~~java
public interface Storage {
    void save(String value);
}
~~~

Another module already compiled an implementation:

~~~java
public class FileStorage implements Storage {
    @Override
    public void save(String value) {
        // Write data to file
    }
}
~~~

Version 2 adds an abstract method:

~~~java
public interface Storage {
    void save(String value);
    String read(String key);
}
~~~

The old **FileStorage** class can still be loaded by the JVM, yet lacks an implementation of **read**. If the program invokes the new method on that object, the JVM can throw **AbstractMethodError**.

Recompiling **FileStorage** against the new interface will prompt the compiler to require an implementation unless the class is redesigned to satisfy the new contract.

### Using default methods when default behavior is needed

Since Java 8, interfaces can declare **default** methods:

~~~java
public interface Storage {
    void save(String value);

    default String read(String key) {
        throw new UnsupportedOperationException("read is not supported");
    }
}
~~~

An existing implementation does not immediately need a **read** method solely to satisfy the new binary contract; the JVM can invoke the default implementation.

However, **default** methods do not solve every case. If a class inherits multiple interfaces defining default methods with the same signature and no unique resolution rule applies, conflicts arise. The implementing class must override to clarify behavior. Adding a default method can also alter method selection in complex hierarchies.

### Adding an abstract method to an abstract class

An abstract class may be extended by classes compiled in other modules. If a new version adds an abstract method, older subclasses may lack an implementation. When a runtime path invokes that unimplemented method, **AbstractMethodError** can occur.

Therefore, when adding behavior to an extensively subclassed abstract class, consider a concrete method with default behavior, an optional hook, or a separate capability interface. Add an abstract method only when updating every subclass can be required and controlled.

## 6. Compile-time constants and behavioral changes

A **public static final** field of primitive type or **String** initialized with a compile-time constant expression can be inlined directly by the compiler into client bytecode.

For example, library version 1:

~~~java
public class RetryPolicy {
    public static final int MAX_RETRIES = 3;
}
~~~

Client:

~~~java
System.out.println(RetryPolicy.MAX_RETRIES);
~~~

After compilation, the client's bytecode may embed the value **3** directly rather than reading the field from the library at runtime. If library version 2 changes the value to **5**, older clients may keep using **3** until recompiled.

This is not necessarily a binary linkage failure: the client runs, yet uses stale data. If a value needs to evolve independently of client compilation lifecycles, expose a method or runtime config instead:

~~~java
public final class RetryPolicy {
    private RetryPolicy() {
    }

    public static int maxRetries() {
        return 5;
    }
}
~~~

Distinguish compile-time constants from **static final** fields initialized with objects or method calls. Not every **static final** field gets inlined into client bytecode.

Moreover, preserving signatures ensures binary linkage only. Changing method bodies lets old clients run while receiving different results, new exceptions, reordered side effects, or broken assumptions. Hence binary compatibility is necessary for safe upgrades, not proof of unchanged behavior.

## 7. Hands-on: running an already-compiled client against a new library

This example simulates replacing a library while keeping the client's class file unchanged.

### Step 1: Create library version 1

Create the **Greeting** class:

~~~java
package com.example.api;

public class Greeting {
    public String greet(String name) {
        return "Xin chao " + name;
    }
}
~~~

Compile and package:

~~~bash
javac -d out-v1 src-v1/com/example/api/Greeting.java
jar --create --file greeting-v1.jar -C out-v1 .
~~~

### Step 2: Compile the client once against version 1

Create **Client.java**:

~~~java
import com.example.api.Greeting;

public class Client {
    public static void main(String[] args) {
        Greeting greeting = new Greeting();
        System.out.println(greeting.greet("An"));
    }
}
~~~

Compile the client with library version 1:

~~~bash
javac -cp greeting-v1.jar -d client-out Client.java
~~~

From this point forward, **client-out/Client.class** is compiled bytecode. We keep this exact file untouched in subsequent steps.

### Step 3: Create library version 2 while keeping the old API

Version 2 adds new methods while keeping **greet(String)** intact:

~~~java
package com.example.api;

public class Greeting {
    public String greet(String name) {
        return "Xin chao " + name;
    }

    public String greet(String name, String language) {
        if ("en".equals(language)) {
            return "Hello " + name;
        }
        return greet(name);
    }

    public String version() {
        return "2";
    }
}
~~~

Compile and package the new library:

~~~bash
javac -d out-v2 src-v2/com/example/api/Greeting.java
jar --create --file greeting-v2.jar -C out-v2 .
~~~

### Step 4: Run the old client against the new library

Do not re-run **javac** on **Client.java**. Swap only the library JAR on the classpath:

~~~bash
# Windows
java -cp "greeting-v2.jar;client-out" Client

# Linux or macOS
java -cp "greeting-v2.jar:client-out" Client
~~~

Result:

~~~text
Xin chao An
~~~

The client compiled against version 1 still runs with version 2 because the method referenced by old bytecode still exists with a matching descriptor.

If version 2 deleted **greet(String)** and kept only **greet(String, String)**, the old client could throw **NoSuchMethodError**. Having a similarly named method or equivalent business logic does not make the JVM automatically redirect old calls to the new signature.

### Step 5: Inspect bytecode

Use **javap** to inspect descriptors and calls recorded in the compiled client:

~~~bash
javap -classpath greeting-v1.jar -s com.example.api.Greeting
javap -classpath client-out -c -verbose Client
~~~

The first command shows signatures and descriptors of library members. The second displays client bytecode, including method call references. After swapping JARs, you can re-run **javap** on library version 2 to verify old members are still provided.

This exercise demonstrates an essential rule: compiling cleanly against the new library is not enough. To verify binary compatibility, preserve bytecode built against the old library and actually execute it against the new library.

## 8. Testing binary compatibility in real projects

A verification process can follow these steps:

1. **Pin the baseline version:** preserve the exact released old library artifact used by clients. Do not substitute a rebuilt artifact with modified contents.
2. **Compare public APIs:** inspect classes, interfaces, constructors, methods, fields, descriptors, visibility, and inheritance across both versions.
3. **Run pre-compiled clients:** compile a test client suite against the old library, then execute that exact bytecode against the new library.
4. **Test extension points:** test interface implementations, abstract class subclasses, plugins, reflection, and service providers if supported by the library.
5. **Check runtime environment:** verify JDK versions, dependencies, module path/classpath, and class loaders match.
6. **Evaluate behavior:** check return values, exceptions, side effects, and output data. This is a distinct layer alongside binary linkage checks.

Tools such as **Revapi** or **japicmp** can compare APIs across two artifacts and catch many incompatible changes. They help automate checks, yet cannot replace executing pre-compiled clients against the new library, especially with plugins, reflection, custom class loaders, or runtime-dependent behavior.

### Do not confuse binary API with class-file version

A library may preserve every API yet be compiled with a newer JDK producing class files unrecognized by older JVMs. Applications can then encounter **UnsupportedClassVersionError**.

Even when clients need no recompilation at the API level, the running JVM must still support the new library's bytecode version. Check compilation target release, deployment JDK, JDK APIs used by the library, and bundled dependencies.

Classpath also affects results. If the runtime accidentally loads an old JAR, duplicate class copy, or incompatible dependency, behavior can diverge from tests. Confirm exact artifacts and class-loading order when investigating failures.

## 9. Migration strategy to keep old clients running

When an API must evolve, a phased strategy lowers risk for independently consumed modules.

### Phase 1: Expand the API

Add new APIs while keeping old APIs intact. When appropriate, forward the old method to the new one so business logic lives in one place.

~~~java
public class CustomerService {
    public Customer findById(long id) {
        return findById(String.valueOf(id));
    }

    public Customer findById(String id) {
        // Implement new lookup logic
        return loadCustomer(id);
    }

    private Customer loadCustomer(String id) {
        // Fetch data
        return new Customer(id);
    }
}
~~~

### Phase 2: Announce and migrate consumers

Mark the old API **@Deprecated**, documenting the replacement API, rationale, and planned removal timeline once policy is set.

~~~java
@Deprecated(since = "2.0", forRemoval = true)
public Customer findById(long id) {
    return findById(String.valueOf(id));
}
~~~

Consumers can migrate source code on their own schedules. Throughout this window, unrecompiled clients keep invoking the old method cleanly.

### Phase 3: Remove in a breaking release

Remove old APIs only after explicitly accepting the requirement for clients to upgrade. Document changes in release notes, migration guides, and versioning policy. For libraries with many consuming teams, factor in independent release timelines of those modules.

A small adapter or bridge method can be a low-cost way to preserve long-term compatibility. Deleting an old signature may save a few lines of source while imposing large upgrade costs across an entire ecosystem.

## 10. Interpreting common linkage errors

When old clients run against a new library, JVM errors generally pinpoint what changed:

| Error | Common meaning | Investigation focus |
|---|---|---|
| **NoClassDefFoundError** | The JVM requires a class yet cannot find or use it during linking/initialization | Check JARs, classpath, dependencies, and class initialization. |
| **NoSuchMethodError** | Method with the name and descriptor required by bytecode is missing | Compare names, parameters, return types, and actually loaded artifact. |
| **NoSuchFieldError** | Field required by bytecode is missing | Check field names, types, and actual library version. |
| **AbstractMethodError** | Call path requires an abstract method missing a concrete implementation on the runtime object | Inspect interfaces, abstract classes, and legacy implementations. |
| **IllegalAccessError** | Member exists yet the client lacks access permission under current runtime rules | Inspect access modifiers, module exports, and package/module boundaries. |
| **IncompatibleClassChangeError** | Member kind or class/interface structure contradicts bytecode assumptions | Check static/instance switches, class/interface changes, and inheritance changes. |
| **UnsupportedClassVersionError** | Current JVM does not support the compiled class-file version | Check application runtime JDK and bytecode target. |

**ClassNotFoundException** and **NoClassDefFoundError** are not identical. **ClassNotFoundException** typically occurs when explicit class-loading calls such as **Class.forName** or **ClassLoader.loadClass** cannot find the requested class. **NoClassDefFoundError** is a runtime linkage failure when the JVM requires a class definition it cannot supply. Always inspect both the root cause and the actual runtime artifacts.

## 11. Pre-release checklist for a new version

Before replacing a library used by multiple clients, check:

- [ ] Existing public classes and interfaces used by clients still exist.
- [ ] Existing constructors still exist with required descriptors.
- [ ] Existing methods and fields keep matching names, types, descriptors, and static/instance kinds.
- [ ] Access visibility of existing members has not narrowed.
- [ ] Inheritance and interface implementations do not introduce method-resolution errors.
- [ ] Interfaces gaining new behavior have a suitable strategy for existing implementations.
- [ ] Compile-time constants are reviewed for risk of clients retaining stale inlined values.
- [ ] Clients compiled against the old artifact still run against the new artifact.
- [ ] Key return values and side effects still satisfy behavioral contracts.
- [ ] Deployment JDK, class-file version, dependencies, classpath, and module path are supported.
- [ ] Release notes clearly document new APIs, deprecated APIs, and changes that may require recompilation.

Binary compatibility allows Java components to be released and upgraded independently. Achieving it requires maintaining the references old bytecode relies upon, offering migration paths for old APIs, and verifying against actual clients compiled from earlier versions.