# Distinguishing reads, exports, and opens in the Java Module System and Instrumentation

When a Java agent modifies the bytecode of a class in a **named module**, errors often lie not in the instrumentation instruction itself, but in the **access relationships between modules**. A new bytecode snippet calling a helper may encounter an **IllegalAccessError** even though the helper is **public**; a library using reflection may encounter an **InaccessibleObjectException** even though it used **setAccessible(true)**. To understand and fix this properly, you must distinguish three relationships of the Java Platform Module System (JPMS):

- **reads**: does module A have a **read** relationship to module B?
- **exports**: does module B **export package p** so that code in A can access types and members with appropriate access levels?
- **opens**: does module B **open package p** for A to perform **deep reflection** on non-public members as well?

These are **three different things**, each with its own direction and target. With Instrumentation, an agent typically uses **Instrumentation.redefineModule(...)** to add those relationships **at runtime**. This API can only **expand**, and cannot be used to revoke a read edge or an export/open permission already granted. It also does not automatically update **module-info.java** or make code that could not compile suddenly compilable if you only add permissions after the JVM starts.

This lesson uses Java 17+, includes an access-permission decision table, module-info.java configuration patterns and JVM options, along with **a compilable and runnable example with two named modules + a Java agent**. The example also demonstrates the case of **opening a package without declaring exports**: at runtime, **Module.isExported(package, targetModule)** can still return **true** because an opened package is considered exported to that module *at runtime*; that **is not equivalent to exports at compile time**.

## 1. The Three-Relationship Model

Let us name:

- **C**: the code-consuming module, for example **demo.client**.
- **T**: the module defining the type to be accessed, for example **demo.target**.
- **p**: a package belonging to T, for example **demo.hidden**.

~~~text
Module C = demo.client
    │
    ├── reads ───────────────────────────► Module T = demo.target
    │                                          │
    │                                          ├── package p = demo.hidden
    │                                          │
    │◄── T exports p to C ────────────────────┤ for public API access
    │                                          │
    │◄── T opens p to C ──────────────────────┘ for deep reflection
    │
    └── C may simultaneously need both a read edge and export/open.
~~~

**Direction is very important.** A needing to call a public method in B means **A reads B**, while package exposure permission must be set on **B exports package to A**. If you want to read a private field via reflection, then **B opens package to A**. You cannot fix everything by calling addReads on B or addOpens on a module that does not own package p.

### 1.1. Three Quick Check Questions

Suppose a method in **demo.client** needs to call a **public static** method in **demo.hidden.Vault** defined by **demo.target**:

1. **Does demo.client read demo.target yet?** If not, a class outside the module is not a valid dependency for ordinary type linking.
2. **Does demo.target export demo.hidden to demo.client yet?** If not, public classes there remain encapsulated at the module boundary; fixing reads alone is not enough.
3. **Is it necessary to bypass Java access checks to retrieve a private member via reflection?** If so, **opens** is required, not just exports.

In short: **reads determines module dependencies; exports determines public API; opens determines deep reflection**. You need Java member/class-level access rights, class loader visibility of the definition, and module/package policy; JPMS does not make **public/private/protected/package-private** rules disappear.

## 2. Comparing reads, exports, and opens

| Concept | Who grants it? | module-info.java syntax | Permission granted | What it does NOT automatically grant |
| --- | --- | --- | --- | --- |
| **reads** | Calling module C | **requires demo.target;** | C reads T; allows a valid dependency relationship | Does not automatically export non-public packages to C |
| **exports** | Package-owning module T | **exports demo.api;** or **exports demo.api to demo.client;** | Public types and appropriate public/protected members are accessible at compile time and runtime when the consumer module reads T | Does not open private members for deep reflection |
| **opens** | Package-owning module T | **opens demo.hidden;** or **opens demo.hidden to demo.client;** | Deep reflection at runtime, including non-public types/members when reflection APIs allow; also provides public access at runtime | Does not export the package to consumer source code at compile time |
| **open module** | Module T | **open module demo.target { ... }** | Opens all packages of T for deep reflection at runtime | Does not automatically export all packages to the compiler; does not allow adding separate opens directives |
| **--add-reads** | Launcher/JVM | **--add-reads demo.client=demo.target** | Adds a read edge at launcher scope | Does not modify export/open |
| **--add-exports** | Launcher/JVM | **--add-exports demo.target/demo.hidden=demo.client** | Relaxes public access to a package, usable at compile/runtime when placed in the right phase | Does not grant private reflection |
| **--add-opens** | Launcher/JVM | **--add-opens demo.target/demo.hidden=demo.client** | Opens a package for reflection at runtime | Does not replace module-info.java and is not equivalent to compile-time exports |
| **redefineModule** | Agent with Instrumentation | **extraReads / extraExports / extraOpens** | Adds relationships at runtime | Does not remove/revoke existing relationships, does not rewrite the source descriptor |

**Note on qualified/unqualified:** **exports p** or **opens p** without **to** applies to all eligible modules; **exports p to A** or **opens p to A** restricts it to module A (and the specified modules). When building an agent, **only open to the necessary modules** instead of granting blanket access to every module.

## 3. Reads: Visibility of Module Dependencies

A named module declares a dependency on another module using **requires**:

~~~java
// module-info.java file of module demo.client.
// Just a JPMS syntax example, not a regular class.
module demo.client {
    requires demo.target;
}
~~~

In the module descriptor, **requires demo.target** creates a read relationship from **demo.client → demo.target**. At runtime, we can query:

~~~java
// Illustrative snippet, assuming both Module objects are already available.
boolean readable = clientModule.canRead(targetModule);
~~~

**canRead** refers to the **relationship between two modules**; it does not check a specific package or member access rights. For a named module, by default it reads itself and **java.base**; other modules must be established via the module descriptor, module graph rules, or appropriate runtime modifications. **requires transitive** can cause another module to read additional dependent modules via transitive readability; you should not infer read edges solely from direct requires when debugging.

A valid read edge is **not enough** to access a public class in a non-exported package:

~~~text
client.canRead(target)       == true
target.isExported(p, client) == false
→ No ordinary public access to public classes in p.
~~~

### 3.1. Adding a Read Edge with an Agent

In an agent context, you need to call **redefineModule** on the **consumer**, because the consumer is the side that must read the target:

~~~java
// Illustrative snippet, with valid inst, client, target.
inst.redefineModule(
    client,
    Set.of(target), // extraReads
    Map.of(),        // extraExports
    Map.of(),        // extraOpens
    Set.of(),        // extraUses
    Map.of()         // extraProvides
);
~~~

All six parameters are meaningful; the **extraReads** set only adds module reads and does not change exports/opens on the target's packages.

### 3.2. What Is Special About the Unnamed Module?

Code on the classpath belongs to the **unnamed module** of its defining class loader. According to **Module.canRead**, an unnamed module **reads all modules**. Therefore, using a program running entirely on the classpath to demonstrate the difference when adding **reads** often leads to wrong conclusions: the reads condition is already true.

That is why the hands-on example uses **two named modules**. When an agent helper in an unnamed module needs to be referenced from bytecode in a named module, the direction to consider is **the named target module reads the unnamed helper module**, not the other way around. An agent on the classpath reads named modules by default, but code injected **into a named module class** is subject to the access rules of the **target class's module**.

### 3.3. Class.forName Does Not Prove API Accessibility

In the demo, code in **demo.client** can still find the **Class<?>** object of **demo.hidden.Vault** using **Class.forName** because the modules have been resolved and the class loader finds the definition. Finding a class by name **does not mean** the client module has permission to link and invoke public methods via JVM instructions or MethodHandles.

Do not rely solely on **Class.forName succeeding** to conclude that **reads + exports** are sufficient. You must check **canRead**, **isExported**, and test an actual access operation.

## 4. Exports: Ability to Use a Package's Public API

A package-owning module can export it unconditionally:

~~~java
// module-info.java of demo.target, example exporting to all modules.
module demo.target {
    exports demo.api;
}
~~~

Or export conditionally to a named module:

~~~java
// module-info.java of demo.target, example of qualified exports.
module demo.target {
    exports demo.internal.api to demo.client;
}
~~~

When the consumer **reads** the target module, the Java compiler and JVM allow access to **public** types and members in the exported package, while still applying standard Java access controls. You cannot call a **private method** of another class solely through exports.

~~~java
// Runtime query on a Module object.
boolean toClient = targetModule.isExported(
        "demo.api", clientModule);
boolean toEveryone = targetModule.isExported("demo.api");
~~~

The two checks have different meanings:

- **isExported(p, client)**: whether the package is exported **at least to client**, taking into account packages opened at runtime.
- **isExported(p)**: exported unconditionally to all modules **at runtime**.

**Neither isExported method checks the client's read edge.** A module can export a package to client even if client does not read that module yet. Therefore, to explain actual access, you must look at **both reads and exports**, not just a single boolean.

### 4.1. Public Class in a Private-by-Module Package

A class can be declared **public**, but if its package is not exported to client, client still has no permission to access it from outside the named module under ordinary Java access:

~~~java
package demo.hidden;

public final class Vault {
    public static String publicInfo() {
        return "PUBLIC_OK";
    }
}
~~~

**public** in a Java file is only one layer of access control; JPMS adds the module boundary. Do not change a public class to package-private or arbitrarily resort to reflection when the real error is that the package has not been exported to the consumer.

### 4.2. Adding Qualified Exports with Instrumentation

~~~java
// Illustrative snippet.
inst.redefineModule(
    target,                       // module owning demo.hidden
    Set.of(),                     // do not add reads on target
    Map.of("demo.hidden", Set.of(client)),
    Map.of(),
    Set.of(),
    Map.of()
);
~~~

The Map has **keys as dot-separated package names** (**demo.hidden**), not internal JVM names like **demo/hidden**. The **value** is a set of **recipient Module objects**, not module name strings. A map entry with an empty set is invalid according to the Javadoc.

If target is not currently exporting the package to client, granting **reads on client** and **exports on target** are two **independent changes in opposite directions**. Do not call **redefineModule(target, Set.of(client), ...)** and expect client to read target.

## 5. Opens: Deep Access via Reflection

**opens** opens a package for **deep reflection**, meaning it allows requesting suppression of ordinary Java access checks via **AccessibleObject.setAccessible(true)** / **trySetAccessible()** or via **MethodHandles.privateLookupIn** if other preconditions are met.

~~~java
// module-info.java of demo.target: only client is allowed to deep reflect.
module demo.target {
    opens demo.hidden to demo.client;
}
~~~

Code in **demo.client** can do:

~~~java
// Illustrative snippet; valid Class<?> vault = ... is available.
java.lang.reflect.Method secret =
        vault.getDeclaredMethod("secret");

boolean canDeepReflect = secret.trySetAccessible();
if (canDeepReflect) {
    Object value = secret.invoke(null);
}
~~~

If the package is not open to the module executing the reflection code, **trySetAccessible()** returns **false**; with **setAccessible(true)** you typically get **InaccessibleObjectException**. Exports alone is **not enough** for private methods/fields belonging to another module.

**opens is not synonymous with export at compile time.** The **opens p** directive is used by JPMS for runtime; if the client's source wants to directly **import demo.hidden.Vault** and compile normally, the compiler still needs the package to be **exports** (and the client needs reads). Use **exports** for intentionally public APIs; use **opens** for reflection frameworks that need private access.

### 5.1. Important Nuance: opens Is Considered Exported at Runtime

According to Java SE 17 **Module.isExported(p, other)**, a package that is **open** to module other is considered **exported at runtime** to other. Consequently:

~~~text
target.isOpen("demo.hidden", client)      == true
target.isExported("demo.hidden", client)  == true
~~~

can both be true simultaneously, **even when module-info.java has no exports demo.hidden** and the agent only added **opens** permission. Having **isExported=true** here **does not mean the compiler was granted compile-time exports**.

This is a debugging trap:

- **Module.isExported** observes **runtime accessibility**, taking opened packages into account.
- **module-info.java** and compilation options determine **compile-time visibility**.
- **Module.getDescriptor()** reflects the original module declaration; it does not turn into a rewritten module-info file when an agent dynamically adds reads/exports/opens.

If you need to know *whether exports was declared via a directive or only via opens*, also inspect **ModuleDescriptor.exports()/opens()**, runtime **isOpen(...)**, and the launcher/agent configuration. Do not rely solely on a single **isExported(...)** value to infer the source of the permission.

### 5.2. Both Exports and Opens Can Be Qualified

~~~java
// Just an example module descriptor for packages belonging to demo.target.
module demo.target {
    exports demo.api to demo.client;
    opens demo.internal to demo.framework;
}
~~~

**demo.client** is allowed to access the public API in **demo.api**; **demo.framework** is allowed to deep reflect **demo.internal**. If **demo.client** wants to retrieve a private field in **demo.internal**, exporting a different package does not help. If the framework is in an **unnamed module**, you cannot write **to ALL-UNNAMED** as a module name in module-info.java; the special token **ALL-UNNAMED** belongs to launcher option syntax such as **--add-opens**/**--add-exports**.

### 5.3. Open Module vs. Opening Individual Packages

~~~java
// Every package in the module has open permission at runtime.
open module demo.target {
    // requires/provides/exports can still appear if needed.
}
~~~

**open module** opens **every package** for deep reflection; inside an **open module declaration**, individual **opens** directives are not allowed per the JLS. This is broader permission than **opens p to framework** and is generally unsuitable for modules with strict encapsulation requirements.

## 6. Access Permission Decision Table by Operation

Assume **C** is a named consumer module, **T** is a named target module owning **p**, the class in p is **public**, and public/private methods are as named.

| C reads T | T exports p to C | T opens p to C | Ordinary public access | Private reflection |
| --- | --- | --- | --- | --- |
| No | No | No | No | No |
| Yes | No | No | No | No |
| Yes | Yes | No | Yes | No |
| Yes | No | Yes | Yes **at runtime** because open counts as runtime export | Yes |
| Yes | Yes | Yes | Yes | Yes |
| No | Yes | No | Missing read edge for ordinary access; reflection has separate rules | No |

**Important:** Reflection via **java.lang.reflect** by default **assumes readability** when checking access of a reflective object; therefore, you may observe reflection succeeding in some cases where **client.canRead(target)** is not true. Do not use this as an excuse to skip reads for **bytecode instructions/MethodHandles** that an agent injects into a named module. Each mechanism has its own access checks and should be tested using the exact operation the program performs.

### 6.1. First Three Diagnostic Lines When Debugging

~~~java
// Illustrative snippet.
System.out.println(client.canRead(target));
System.out.println(target.isExported("demo.hidden", client));
System.out.println(target.isOpen("demo.hidden", client));
~~~

Interpretation:

- **false, false, false**: missing all required permissions.
- **true, false, false**: has reads, missing public access and deep reflection.
- **true, true, false**: public access at runtime, cannot infer private reflection.
- **true, true, true**: package is open to client; private reflection can be enabled per API contract.

Remember that **isExported** returns true when the package is open; the signature **true, true, true** does not prove there is a separate exports directive.

## 7. Instrumentation.redefineModule: The API Connecting the Three Relationships

Java 17 provides:

~~~java
// API signature; reference snippet, not a standalone Java file.
void redefineModule(
    Module module,
    Set<Module> extraReads,
    Map<String, Set<Module>> extraExports,
    Map<String, Set<Module>> extraOpens,
    Set<Class<?>> extraUses,
    Map<Class<?>, List<Class<?>>> extraProvides
);
~~~

Explanation of arguments:

| Argument | Effect |
| --- | --- |
| **module** | The module receiving additional permissions/metadata |
| **extraReads** | Additional other modules that this module is allowed to read |
| **extraExports** | Packages **of this module** additionally exported to other modules |
| **extraOpens** | Packages **of this module** additionally opened to other modules |
| **extraUses** | Additional service types that the module is allowed to use via ServiceLoader |
| **extraProvides** | New service implementations that the module provides |

The last two arguments are **service bindings**, not reads/exports/opens, but valid **Set/Map** values must be passed, usually **Set.of()** and **Map.of()**, when only modifying the three access relationships.

### 7.1. Granting reads, then exports, then opens

~~~java
// Illustrative snippet inside an agent that already has inst, client, target.
inst.redefineModule(
    client, Set.of(target),
    Map.of(), Map.of(), Set.of(), Map.of()
);

inst.redefineModule(
    target, Set.of(),
    Map.of("demo.hidden", Set.of(client)),
    Map.of(), Set.of(), Map.of()
);

inst.redefineModule(
    target, Set.of(),
    Map.of(),
    Map.of("demo.hidden", Set.of(client)),
    Set.of(), Map.of()
);
~~~

In practice, you can combine **extraExports** and **extraOpens** into **a single redefineModule(target,...) call** since both share the same package owner. The read edge must be added to **client**, so it typically remains a separate call. These permissions are all **expand-only**; there is no redefineModule API to "close a package back" to its previous state.

### 7.2. Safety and Scope

- Call **inst.isModifiableModule(target)** before modifying; when not modifiable, **redefineModule** may throw **UnmodifiableModuleException**.
- The method is described by the Javadoc as **safe for concurrent use** so multiple agents can add relationships to the same module; this **does not mean** agents automatically agree on what permissions to grant or can roll back already opened permissions.
- **redefineModule** on an **unnamed module** is a **no-op**, and **isModifiableModule** on an unnamed module returns **true**; this can easily cause logs to say "API called" while nothing actually changed.
- Package keys in **extraExports/extraOpens** must belong to the module being modified; an invalid package or empty target set causes **IllegalArgumentException**.
- Null arguments or null elements in Sets/Maps cause **NullPointerException**.
- **redefineModule** does not allow narrowing existing reads/exports/opens or service uses/provides; if you need to revert relaxed module boundaries, you usually have to consider **starting a new JVM**.
- Do not treat redefineModule as a way to bypass all class loader errors: the helper must **actually be found by the appropriate loader**, the method name/descriptor must be correct, and the bytecode must be valid.

### 7.3. Module.addReads / addExports / addOpens Are Not an Unconditional Replacement

Java also has **Module.addReads**, **Module.addExports**, and **Module.addOpens**. However, these methods have **caller/module authority requirements**: for example, **Module.addReads** and **addExports** on a named module require the caller to belong to that same module; **addOpens** requires the package to already be open to the appropriate caller. An agent in an unnamed module **should not assume** it can call them directly on any named module.

**Instrumentation.redefineModule** exists to serve agents that need to add access relationships between modules during instrumentation. Do not use reflection to break module checks to call the add* methods in a way unsupported by the API.

## 8. Java 17+ Hands-On Practice: Observing 5 Access Permission States

This is a **buildable/runnable** example on JDK 17 or higher without external libraries. We create two named modules:

- **demo.target**: contains **demo.hidden.Vault**, whose package is neither exported nor opened in module-info.java.
- **demo.client**: contains **demo.client.Probe**, and the module does not require demo.target.
- **AccessAgent**: a startup Java agent (unnamed module on the classpath) that receives **Instrumentation** from the JVM and, depending on the mode, adds reads/exports/opens for the two modules in the **boot layer**.

**Probe** reads the graph state, attempts to invoke **publicInfo()** using **MethodHandles.lookup().findStatic(...)**, and tests **trySetAccessible** on the private method **secret()**. MethodHandles lookup enforces access checks according to the lookup class; this example is suitable for comparison with ordinary bytecode access. A regular reflection method has readability variations, so it cannot replace that test.

### 8.1. File Structure

~~~text
jpms-access-demo/
  src/
    demo.target/
      module-info.java
      demo/
        hidden/
          Vault.java
    demo.client/
      module-info.java
      demo/
        client/
          Probe.java
  agent/
    AccessAgent.java
    agent.mf
~~~

**Do not** place **Vault.java** and **Probe.java** in the same unnamed module, because doing so would lose the missing-read-edge case.

### 8.2. Package-Owning Module: demo.target

**File src/demo.target/module-info.java**

~~~java
module demo.target {
    // Do not export or open demo.hidden at compile time.
}
~~~

**File src/demo.target/demo/hidden/Vault.java**

~~~java
package demo.hidden;

public final class Vault {
    public static String publicInfo() {
        return "PUBLIC_OK";
    }

    private static String secret() {
        return "SECRET_OK";
    }
}
~~~

Note: the class is **public** and the method **publicInfo()** is also public, but package **demo.hidden** is not exported to the client module. The private method **secret()** is solely for the deep reflection test.

### 8.3. Named Consumer Module: demo.client

**File src/demo.client/module-info.java**

~~~java
module demo.client {
    // Intentionally does not require demo.target.
}
~~~

**File src/demo.client/demo/client/Probe.java**

~~~java
package demo.client;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;

public final class Probe {
    public static void main(String[] args) throws Throwable {
        Module client = Probe.class.getModule();
        Module target = ModuleLayer.boot()
                .findModule("demo.target").orElseThrow();

        // Class.forName succeeds in the demo configuration,
        // but does not mean public/private linking is allowed.
        Class<?> vault = Class.forName("demo.hidden.Vault");

        System.out.println("READS=" + client.canRead(target));
        System.out.println("EXPORTED=" +
                target.isExported("demo.hidden", client));
        System.out.println("OPEN=" +
                target.isOpen("demo.hidden", client));

        // Create a MethodHandle with Probe's permissions in the named module.
        try {
            MethodHandle mh = MethodHandles.lookup().findStatic(
                    vault,
                    "publicInfo",
                    MethodType.methodType(String.class));
            System.out.println("PUBLIC=" +
                    (String) mh.invokeExact());
        } catch (IllegalAccessException error) {
            System.out.println("PUBLIC=DENIED");
        }

        Method secret = vault.getDeclaredMethod("secret");
        boolean deep = secret.trySetAccessible();
        System.out.println("DEEP=" + deep);
        if (deep) {
            System.out.println("PRIVATE=" + secret.invoke(null));
        }
    }
}
~~~

**Why use MethodHandles here?** In the demo, **MethodHandles.lookup()** obtains the lookup context from the named module **demo.client**. When creating a handle to a public method of a class in another module, the lookup class's permissions reflect both the read edge and public access. Conversely, Core Reflection has an "assume readability" rule in access checks of reflected objects, so using **Method.invoke** alone to demonstrate reads can produce misleading results.

There is **no** need to import **demo.hidden.Vault** in the consumer source (and in the initial state that import would not compile). We use a string name to load the Class object from the module already resolved by the launcher, and then test the operations controlled by JPMS.

### 8.4. Java Agent Adding Module Edges

**File agent/AccessAgent.java**

~~~java
import java.lang.instrument.Instrumentation;
import java.util.Map;
import java.util.Set;

public final class AccessAgent {
    public static void premain(
            String mode, Instrumentation inst) {

        Module target = ModuleLayer.boot()
                .findModule("demo.target").orElseThrow();
        Module client = ModuleLayer.boot()
                .findModule("demo.client").orElseThrow();

        if (!inst.isModifiableModule(target)
                || !inst.isModifiableModule(client)) {
            throw new IllegalStateException(
                    "Modules not modifiable");
        }

        if (!Set.of(
                "none", "reads", "exports", "opens", "openOnly")
                .contains(mode)) {
            throw new IllegalArgumentException(
                    "Unknown mode: " + mode);
        }

        // Only expand the read-edge graph from client to target.
        if (!"none".equals(mode)) {
            inst.redefineModule(
                    client,
                    Set.of(target),
                    Map.of(), Map.of(), Set.of(), Map.of());
        }

        // Export the public API of target's package to client.
        if ("exports".equals(mode) || "opens".equals(mode)) {
            inst.redefineModule(
                    target,
                    Set.of(),
                    Map.of("demo.hidden", Set.of(client)),
                    Map.of(),
                    Set.of(),
                    Map.of());
        }

        // Open the package for private reflection.
        // openOnly only adds reads + opens, without adding separate exports.
        if ("opens".equals(mode) || "openOnly".equals(mode)) {
            inst.redefineModule(
                    target,
                    Set.of(),
                    Map.of(),
                    Map.of("demo.hidden", Set.of(client)),
                    Set.of(),
                    Map.of());
        }
    }
}
~~~

**Meaning of the five modes:**

| Mode | extraReads client→target | extraExports demo.hidden→client | extraOpens demo.hidden→client |
| --- | --- | --- | --- |
| **none** | No | No | No |
| **reads** | Yes | No | No |
| **exports** | Yes | Yes | No |
| **opens** | Yes | Yes | Yes |
| **openOnly** | Yes | No | Yes |

The name **openOnly** only means *extraExports is not called*, it **does not mean** the read edge is missing. This mode intentionally demonstrates that **isExported(package, client)** still becomes true at runtime when only **opens** is granted for the package.

### 8.5. Manifest File

**File agent/agent.mf** (keep a trailing newline):

~~~text
Manifest-Version: 1.0
Premain-Class: AccessAgent
~~~

There is no need to declare **Can-Retransform-Classes** or **Can-Redefine-Classes** for this demo. Those two capabilities relate to class retransform/redefine, and are **not** a default requirement for **Instrumentation.redefineModule**. The agent only adds edges to named modules at startup.

### 8.6. Building with javac --release 17 and jar

From the project root directory, using a POSIX shell:

~~~bash
mkdir -p out/mods/demo.target out/mods/demo.client out/agent

javac --release 17 -d out/mods/demo.target \
  src/demo.target/module-info.java \
  src/demo.target/demo/hidden/Vault.java

javac --release 17 -d out/mods/demo.client \
  src/demo.client/module-info.java \
  src/demo.client/demo/client/Probe.java

javac --release 17 -d out/agent agent/AccessAgent.java

jar cfm access-agent.jar agent/agent.mf \
  -C out/agent AccessAgent.class
~~~

The **\\** at the end of a line is line-continuation syntax in POSIX shells; on PowerShell or cmd.exe you can write **each javac/jar command on a single line**. Note that **out/mods** must contain the module directories **demo.target** and **demo.client**, each containing **module-info.class**. You can verify:

~~~bash
jar tf access-agent.jar
~~~

You should see **META-INF/MANIFEST.MF** and **AccessAgent.class**. The example uses a **startup agent**, without **agentmain** or dynamic attach.

### 8.7. Running Mode none: No Relationships Yet

~~~bash
java --module-path out/mods \
  --add-modules demo.target \
  -javaagent:access-agent.jar=none \
  -m demo.client/demo.client.Probe
~~~

Output:

~~~text
READS=false
EXPORTED=false
OPEN=false
PUBLIC=DENIED
DEEP=false
~~~

**--add-modules demo.target** ensures that module demo.target is resolved into the boot layer even though demo.client does not require it, allowing the agent and Probe to obtain the **Module object**. Mode none adds no edges. MethodHandles cannot be created for publicInfo due to missing permissions; private reflection is also not enabled.

### 8.8. Running Mode reads: Adding Only the Read Relationship

~~~bash
java --module-path out/mods \
  --add-modules demo.target \
  -javaagent:access-agent.jar=reads \
  -m demo.client/demo.client.Probe
~~~

Output:

~~~text
READS=true
EXPORTED=false
OPEN=false
PUBLIC=DENIED
DEEP=false
~~~

**READS=true** shows that client has a read edge to target. However, package **demo.hidden** is still neither exported nor opened, so the public method handle is still denied and private deep reflection still fails.

This is a common diagnostic error with agents: **extraReads** was added, yet the injected method still fails to link to the public helper because the module containing the helper has not exported the corresponding package.

### 8.9. Running Mode exports: Public Access Succeeds

~~~bash
java --module-path out/mods \
  --add-modules demo.target \
  -javaagent:access-agent.jar=exports \
  -m demo.client/demo.client.Probe
~~~

Output:

~~~text
READS=true
EXPORTED=true
OPEN=false
PUBLIC=PUBLIC_OK
DEEP=false
~~~

The **public method handle** can now be created and invoked. However, the private method **secret()** still lacks permission to suppress access checks, so **DEEP=false**. **exports** is not the same as **opens**.

### 8.10. Running Mode opens: Adding Deep Reflection

~~~bash
java --module-path out/mods \
  --add-modules demo.target \
  -javaagent:access-agent.jar=opens \
  -m demo.client/demo.client.Probe
~~~

Output:

~~~text
READS=true
EXPORTED=true
OPEN=true
PUBLIC=PUBLIC_OK
DEEP=true
PRIVATE=SECRET_OK
~~~

Here the agent added reads, exports, and opens. **trySetAccessible()** on the private method succeeds, and reflection invoke returns **SECRET_OK**.

### 8.11. Running Mode openOnly: opens Creates a Runtime Export

~~~bash
java --module-path out/mods \
  --add-modules demo.target \
  -javaagent:access-agent.jar=openOnly \
  -m demo.client/demo.client.Probe
~~~

Output:

~~~text
READS=true
EXPORTED=true
OPEN=true
PUBLIC=PUBLIC_OK
DEEP=true
PRIVATE=SECRET_OK
~~~

Look closely at **AccessAgent**: mode **openOnly** **does not call extraExports** for demo.hidden! So why is **EXPORTED=true**? Because **Module.isExported(package, target)** returns true for a package that is **open** to the target module **at runtime** according to the Javadoc. That does not make the source module descriptor contain an exports directive, nor does it allow javac to import that package at compile time.

**Run each mode in a new JVM.** Because redefineModule does not revoke permissions, if you test none→reads→exports→opens sequentially in **the same process**, the permissions from earlier steps remain. The commands above intentionally spawn **a new process per mode**, ensuring the output accurately measures that mode's state.

### 8.12. Actual Verification Results of the Example

This source set was compiled with **javac --release 17** and run with a compatible JDK on a test JVM. The **none, reads, exports, opens, and openOnly** outputs above are the results of five separate runs. In a different project environment, if the JVM disallows module modification, a module is not resolved, or the JAR manifest is invalid, the application may fail before the Probe step; in that case, investigate the root cause rather than arbitrarily changing the expected output.

## 9. Comparison with JVM Options --add-reads, --add-exports, --add-opens

You do not necessarily need an agent to test module edges. The Java launcher supports these options:

~~~bash
# Read edge at runtime.
--add-reads demo.client=demo.target

# Public access for a named consumer module.
--add-exports demo.target/demo.hidden=demo.client

# Deep reflection for a named consumer module.
--add-opens demo.target/demo.hidden=demo.client
~~~

The lines above **illustrate option syntax**, and are not standalone shell commands. On an actual command line, place them before **-m** and ensure the modules are resolved. They can be combined:

~~~bash
java --module-path out/mods \
  --add-modules demo.target \
  --add-reads demo.client=demo.target \
  --add-exports demo.target/demo.hidden=demo.client \
  --add-opens demo.target/demo.hidden=demo.client \
  -m demo.client/demo.client.Probe
~~~

When permissions are configured properly at runtime, the output is equivalent to mode **opens**. Differences:

- **--add-reads/exports/opens** are configured at the launcher; convenient for an application or test without writing an agent.
- **Instrumentation.redefineModule** adds edges **inside a running JVM** after the agent is loaded and has the appropriate Module objects.
- **module-info.java** declares static dependency/API contracts and is the preferred choice when you **own the source** and the permissions should exist at compile time.
- **--add-exports** can be used with both **javac** and **java** to handle compile-time/runtime public access as needed; passing the option only to **java** does not allow an **already-executed javac** to see a non-exported package.
- **--add-opens** is a runtime open permission, not a way to compile direct imports to a hidden package.

### 9.1. ALL-UNNAMED Is Not a Real Module Name

For libraries running on the classpath, you may see:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED ...
~~~

**ALL-UNNAMED** is a special launcher token for granting permissions to **all unnamed modules**, not a Module object or module name used in redefineModule's **Map<String, Set<Module>>**. When an agent uses the API, it must obtain the **Module object** of the specific consumer, such as **someAgentClass.getModule()** if it resides in an unnamed module.

Do not automatically add **--add-opens java.base/...=ALL-UNNAMED** to every application when only a different package and a specific named module are needed. This is a broad permission expansion with security and maintainability consequences.

### 9.2. Can You Add a Read Edge Without Adding Exports?

Yes, and as the **reads** demo proves, the read relationship is opened, but public access to the hidden package **remains blocked**. Similarly, adding only exports without adding reads can result in **target.isExported(p,client) == true** while the ordinary access path still lacks a read edge. Check the **exact module pair** and the **exact package**.

## 10. Applying to Bytecode Instrumentation: Can the Helper Be Called?

Suppose a target class is defined in module **com.acme.application**. A ClassFileTransformer injects:

~~~text
INVOKESTATIC com/acme/agent/TraceHooks.enter ()V
~~~

This is an **illustrative bytecode snippet**, not a Java source statement. The helper **TraceHooks** belongs to another module, e.g., **com.acme.telemetry**, or belongs to the unnamed module of the class loader holding the agent runtime.

For the new instruction to link, you must evaluate:

1. **Which module does the target class belong to?** Use **classBeingRedefined.getModule()** when available, or the **Module module** parameter of the **ClassFileTransformer.transform(Module,...)** overload. For newly loaded classes, classBeingRedefined is usually null, so **Module module** is more useful.
2. **Which module does TraceHooks belong to?** **TraceHooks.class.getModule()**; it may be an unnamed module.
3. **Does the target module read the helper module?** Having only the agent module read the target module is **not enough**, because the JVM resolves the instruction from the **module of the class containing the new instruction**.
4. **Does the helper module export the package containing TraceHooks to the target module?** For a helper in an unnamed module, all packages are considered exported/open at runtime, but the helper must still be resolved through an appropriate class loader.
5. **Does TraceHooks/enter have valid public access and the exact method descriptor?** Reads/exports do not automatically fix names, descriptors, or class loading.
6. **Is reflection used to access private fields/methods of the target?** If so, you must open the **target package** to the **module executing the reflection code**, which may differ from the helper/agent module.

### 10.1. Pattern for Granting reads to the Target Module

~~~java
// Pseudocode inside the agent; Module objects are already resolved.
Module targetModule = targetClass.getModule();
Module helperModule = TraceHooks.class.getModule();

inst.redefineModule(
    targetModule,
    Set.of(helperModule),
    Map.of(), Map.of(), Set.of(), Map.of()
);
~~~

If **helperModule** is an unnamed module, the agent can still instruct the named target to read it via extraReads. However, **adding only a read edge does not guarantee that the target's class loader can find TraceHooks**. In multi-classloader application servers, you need a strategy to place the helper on the bootstrap/system loader or an appropriate visible class loader, while avoiding loading the wrong helper version. **Do not** conclude everything is fine solely from **targetModule.canRead(helperModule)**.

### 10.2. Pattern for Opening a Target Package to the Agent for Private State Reflection

~~~java
// Pseudocode inside the agent; the target package belongs to targetModule.
Module reflector = TraceHooks.class.getModule();

inst.redefineModule(
    targetModule,
    Set.of(),
    Map.of(),
    Map.of("com.acme.internal", Set.of(reflector)),
    Set.of(),
    Map.of()
);
~~~

This is **opens on the target module**, because target owns the package containing the private field. If the code performing **setAccessible** resides in **a different module from TraceHooks**, you must open the package to **the exact module executing the reflection operation**. Opening to the agent entry class's module is not always sufficient.

### 10.3. Are exports or opens Needed for a Transformer That Only Reads classfileBuffer?

If a transformer **only receives byte[] class file bytes and analyzes them**, it generally does not need to open private fields via reflection. **ClassFileTransformer.transform** receives bytecode data directly and does not call **setAccessible** on the target class to transform instructions. Module edges may be needed when **new bytecode calls a helper**, when a framework uses reflection, or when the agent uses Java APIs to access types. Avoid relaxing all of reads, exports, and opens "just to be safe" if there is no real need.

### 10.4. Order of Opening Permissions and Installing Bytecode

A safe strategy:

1. Identify the exact **target module**, helper module, classloader, and package.
2. Preflight **isModifiableModule**, package ownership, and runtime helper visibility.
3. Grant **minimal read/export/open edges** via redefineModule before calling retransform/redefine, which could cause the new bytecode to link the helper.
4. Run instrumentation on the right class/method, produce valid bytes, and keep classfileBuffer unmutated.
5. Observe that the JVM accepted the class and **the new method actually runs**. Do not report success solely because redefineModule or ClassFileTransformer did not throw an exception.

Module permissions are **one-way expanded runtime permissions**; if the subsequent instrumentation step fails, the added module edges may **still remain**. There is no shared transaction with rollback between redefineModule and retransformClasses/redefineClasses.

## 11. Diagnosing Real-World Errors

| Symptom | Common Cause | What to Check |
| --- | --- | --- |
| **client.canRead(target) == false** | Missing requires / extraReads / --add-reads | Verify consumer→target direction |
| **canRead=true but public type inaccessible** | Target has not exported/opened the package to client | isExported(p,client), package name |
| **IllegalAccessError** when calling injected helper | Incorrect module access or Java member access; could also be wrong descriptor | Module of caller/owner, exports, method flags |
| **IllegalAccessException** from MethodHandles | Lookup class lacks reads or public access | findStatic access check, canRead and isExported |
| **InaccessibleObjectException** on setAccessible | Package not open to reflector module | isOpen(p, reflector), exact module executing reflection |
| **trySetAccessible() == false** | Insufficient deep reflection rights | Package opens vs exports, private member rules |
| **ClassNotFoundException / NoClassDefFoundError** | Module resolution/classloader visibility/helper not found | Boot layer, defining loader, --add-modules, packaging |
| **isExported=true but javac cannot import** | Package only opened at runtime or only dynamic export added | module-info, javac --add-exports, compile-time requires |
| **IllegalCallerException on Module.addReads** | Agent does not belong to the named module being modified | Use valid Instrumentation.redefineModule |
| **IllegalArgumentException in redefineModule** | Package does not belong to module, export/open to empty target set | Module.getPackages(), Map keys, target sets |
| **UnmodifiableModuleException** | Module does not allow redefineModule | isModifiableModule |
| **NullPointerException in redefineModule** | An argument or set/map element is null | Set.of/Map.of and validation |
| **Package opened but method link still fails** | May lack reads, classloader visibility, or method ABI | Compare caller, owner, and descriptor bytecode |

### 11.1. Log All Three Dimensions to Avoid Confusion

~~~text
SOURCE_MODULE=com.acme.application
HELPER_MODULE=com.acme.telemetry
SOURCE_READS_HELPER=true
HELPER_PACKAGE=com.acme.trace
HELPER_PACKAGE_EXPORTED_TO_SOURCE=true
TARGET_INTERNAL_PACKAGE=com.acme.internal
TARGET_INTERNAL_PACKAGE_OPEN_TO_REFLECTOR=false
~~~

This is a **custom diagnostic log pattern built by the agent**, not automatic output from Java 17. Always log the **defining class loader identity** and corresponding **Module object** in environments with multiple module layers/plugins.

### 11.2. A Method That Does Not Need Deep Reflection Still Gets InaccessibleObjectException?

If a framework calls **setAccessible(true)** on a non-public member even though the logical goal is merely to invoke a public API, the error may stem from **how the framework implements reflection**, not from the business requirement. If you control the framework, you can switch to the public API so opens is unnecessary. Before opening JDK internal packages or third-party libraries, evaluate whether that permission is truly needed.

### 11.3. Why Can Errors Still Occur After Adding Permissions?

JVM linkage caches failures along certain resolution paths. The **Module.addExports** Javadoc notes: after a symbolic reference resolution fails due to a linkage error, subsequent resolutions of the same symbolic reference may still throw the same error. Therefore, do not design an agent that intentionally lets a method run and throw **IllegalAccessError** before adding exports as a purely reactive fix. It is better to **establish edges before running new code**, and verify on a fresh JVM in tests.

## 12. Minimizing Permission Scope and Security Consequences

**opens** grants broader rights than **exports**: it enables code in the target module to **bypass Java access checks for private/package-private members** through permitted reflection APIs. Granting **opens** unconditionally to a package containing internal data can increase unintended access exposure. Therefore:

- Only grant **extraReads** to necessary helper modules.
- Only grant **extraExports** for public helper packages that instrumented code must link against.
- Only grant **extraOpens** for packages that genuinely need non-public reflection, and only to the **exact reflector module**.
- Avoid **ALL-UNNAMED** if a specific named module can be used; avoid **open module** if only one package needs to be opened.
- Check the module layer/classloader: a module with the same name in another layer may be a **different Module object**, so permissions cannot be inferred from the name string alone.
- Record opened module edges for auditing; **redefineModule has no narrowing operation**, so permission changes typically last for the lifetime of the JVM.
- Do not conflate JPMS permissions with an absolute security sandbox: the module system is an **encapsulation/dependency** mechanism, and exports/opens should not be treated as a security boundary preventing malicious code in the same process from executing.
- Check Java agent dependencies before adding to a classloader search path, because a helper class with a colliding name can lead to **LinkageError** or altered class identity.

## 13. Common Mistakes and How to Fix Them

1. **Confusing "reads module" with "exports package":** **requires demo.target** does not make package **demo.hidden** a public API. You need exports/opens on the target side.
2. **Confusing "exports public" with "opens private":** a public method working does not mean a private field can be setAccessible. You need opens.
3. **Assuming opens does not affect isExported:** at **runtime**, an opened package is treated as exported to the recipient module. However, the compiler still cannot by default import a package that is only opened.
4. **Granting extraReads in the wrong direction:** for a target class to call a helper, the **target module must read the helper module**. Do not add helper→target instead.
5. **Adding extraExports on the consumer instead of the owner:** the package key must belong to the module being redefined; target owns the package to be exported.
6. **Using slashes in the package key:** redefineModule requires **com.example.internal**, not the JVM internal name **com/example/internal**.
7. **Using module name strings instead of Set<Module>:** the API takes Module objects, so you must resolve the right boot/custom layer and class loader.
8. **Using the agent entry module instead of the reflection-executing module:** you must open the package to the module of the code executing setAccessible, which may be a helper or framework.
9. **Opening permissions at runtime and expecting a previously compiled javac error to disappear:** compilation and runtime are different phases; javac options and module-info must be right.
10. **Treating --add-opens as compile-time --add-exports:** incorrect. --add-opens serves runtime reflection.
11. **Treating Module.addReads as a privileged API for any agent:** named modules have caller constraints; use Instrumentation.redefineModule where appropriate.
12. **Assuming isModifiableModule returning true guarantees open will succeed:** package ownership, sets/maps, and parameters can still be invalid.
13. **Assuming you can "close" a package after testing:** redefineModule cannot reduce permissions; start a new JVM if you need a clean baseline.
14. **Blaming JPMS for every IllegalAccessError:** it could be Java access modifiers, class hierarchy, method descriptors, class loaders, verification, or cached linkage failures.
15. **Granting overly broad permissions instead of debugging:** opening java.base/java.lang to ALL-UNNAMED when only a public helper in a separate module is needed exceeds the minimum necessary.

## 14. Test Matrix for Java Agents with Module Boundaries

| Test Case | Configuration | Expected Result |
| --- | --- | --- |
| No permissions opened | named client does not require target, hidden package | reads/exports/open false |
| Only reads added | client→target | reads true, public/deep still insufficient |
| Exports added | reads + target exports p→client | public method handle works, private reflection blocked |
| Opens added | reads + target opens p→client | deep reflection works |
| Only opens (no separate export) | reads + extraOpens | runtime isExported true; does not imply compile-time exports |
| Deep reflection wrong module | p opens to framework A, reflection code in B | B does not automatically inherit A's permission |
| Wrong package key | extraOpens key does not belong to target | IllegalArgumentException |
| Wrong direction | extraReads placed on wrong owner module | consumer.canRead(target) unchanged |
| Unnamed helper | target named, helper unnamed | target needs read edge when new bytecode references helper |
| Custom class loader | same class name, different defining loader | exact Class/Module object required |
| Named module helper | public TraceHooks package not exported | injected bytecode may hit IllegalAccessError |
| Add rights after linkage failure | error already occurred before edges were added | do not rely on retrying same reference; test in new JVM |
| Cumulative permissions | multiple agents redefineModule same named module | permissions are additive, not automatically revoked |
| Invalid bytecode | right edges but wrong stack/frame/descriptor | JVM may still reject class file |
| Real runtime evaluation | test instrumented method after installation | verify helper and reflection actually execute |

## 15. Self-Check Questions

1. **Module A requires B; can A automatically call public classes in every package of B?** No. B's packages must be appropriately exported/opened to A according to access rules.
2. **Module B exports package p to A; can A retrieve a private field via setAccessible(true)?** Not through exports alone; p must be opened to the reflecting module or meet other privileged API conditions.
3. **Does a package with only opens p to A make isExported(p,A) return true?** Yes, at runtime per Module.isExported; this is not synonymous with compile-time exports.
4. **If A only needs to read byte[] classfileBuffer in ClassFileTransformer, is it mandatory to open the entire target package?** No. Opens relates to deep reflection, not receiving raw bytes.
5. **New bytecode in a class of module A calls a helper in B: who reads whom?** A must read B. B must export the helper package to A or grant appropriate runtime permissions.
6. **For an agent to read a private member of target via reflection, which module must open the package?** The module owning the member; opened to the module executing the reflection.
7. **Can --add-exports replace --add-opens for private fields?** No; exports primarily covers public APIs.
8. **Can redefineModule remove extraReads and close an already opened package?** No; the method only expands relationships.
9. **Why does the demo use two named modules instead of a classpath consumer?** Because an unnamed module reads all modules; it is difficult to demonstrate a missing read edge.
10. **Why does isExported=true not prove that client reads target?** Module.isExported does not check the read edge; canRead must be checked separately.
11. **Does Class.forName finding Vault prove access?** No. Type discovery and member usage permissions are two separate steps.
12. **Why does mode openOnly still produce PUBLIC=PUBLIC_OK even without calling extraExports?** A package opened to client is considered exported at runtime, with the read edge also granted in that mode.

## 16. Implementation Checklist for Instrumentation.redefineModule

- I have identified **the module containing the injected bytecode** and **the module containing the target helper/API**.
- I have identified the **correct reads direction**: the consumer code reads the provider module.
- I have identified the **package owned by the provider** and the **exports** permission needed for ordinary public access.
- I only request **opens** when there is deep reflection into non-public members.
- **isExported** is interpreted accurately: opens also makes it exported at runtime; the method does not check reads.
- I have checked **Module.isNamed**, **Module.canRead**, **isExported(package, other)**, **isOpen(package, other)**, and the defining loader/module layer.
- **extraExports/extraOpens** use **dot-separated** package names, map values are **non-empty Set<Module>**, and the package exists in the owner module.
- I have a real **Instrumentation** handle from the JVM and use **isModifiableModule** when needed.
- I do not assume **Module.addReads/addExports/addOpens** can be called arbitrarily from another agent module.
- Required permissions are opened **before** the instrumented bytecode is loaded/resolved/invoked.
- I do not expect **redefineModule** to alter source **module-info.java**, compile-time visibility, or perform automatic rollback.
- I do not mistake Class.forName or transform callbacks for proof that the helper linked and the method executed.
- I have tested **normal invocation**, **reflection**, **wrong loader/module**, and typical permission errors on the target JVM/JDK.
- I only grant minimal permissions and log all module edge expansions for auditing.

## 17. Official References

- [Java SE 17 — java.lang.instrument.Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): **redefineModule**, **isModifiableModule**, the **extraReads/extraExports/extraOpens** maps, expansion rules, and exceptions.
- [Java SE 17 — java.lang.Module](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): **canRead**, **isExported**, **isOpen**, named/unnamed modules, **addReads/addExports/addOpens**, and caller restrictions.
- [Java Language Specification SE 17 — §7.7.1 and §7.7.2](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html): **requires/exports/opens** syntax, qualified exports/opens, and compile-time/runtime accessibility.
- [Java SE 17 — AccessibleObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): **setAccessible**, **trySetAccessible**, deep reflection limits, and the reflection assume-readability rule.
- [Java SE 17 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): lookup class permissions, cross-module access checks, and public/private method handles.
- [Java SE 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): transform overload with **Module** when instrumenting class loading.
- [OpenJDK Dev.java — --add-exports and --add-opens](https://dev.java/learn/organizing/modules/add-exports-opens/): launcher options when controlled relaxation of encapsulation is needed.

**Practical summary:** **Consumer must read provider; provider must export the package for ordinary public access; provider must open the package for deep reflection.** In a Java agent, use **Instrumentation.redefineModule** with the **right Module objects, right direction, and right package names**, verify permissions using all three of **canRead/isExported/isOpen**, and then test actual access. Remember that **opens counts as exports at runtime but is not compile-time exports**, and permissions added via redefineModule **have no revoke operation within the same JVM**.
