# Redefine, retransform, and differences from loading a class with a new loader

## 1. Three ways to change Java code while the JVM is running

When an application needs to modify method behavior, attach a profiler, update a plugin, or run two versions side by side, there are three techniques that are easily lumped together as hot reload yet have completely different meanings:

1. **Redefine** uses **Instrumentation.redefineClasses(ClassDefinition...)** to supply replacement class-file bytes for an **existing Class**.
2. **Retransform** uses **Instrumentation.retransformClasses(Class<?>...)** so that the JVM re-runs the matching **ClassFileTransformer** chain on an **existing Class**, without passing replacement bytes directly into this call.
3. **Loading with a new ClassLoader** uses loadClass/findClass/defineClass in the usual way to create a **different runtime Class**, even if the binary name remains the same as the old version.

**If you only modify a method body and want existing instances to use the new code on the next invocation, look at redefine/retransform. If you must change the class schema, run two versions concurrently, or replace a module/plugin comprehensively, consider a new ClassLoader.**

Terms to remember:

- **Loading**: the JVM finds and defines the class.
- **Linking**: verification/preparation/resolution according to the specification.
- **Initialization**: executes static initializers upon active use according to Java rules.
- **Class identity**: for an ordinary class, based on the **binary name together with its defining ClassLoader**.
- **Instrumentation**: the agent API that operates on bytecode/classes that the JVM has loaded or is about to load.

Do not confuse **ClassLoader.defineClass** with **Instrumentation.redefineClasses** just because their names sound similar: one creates a runtime definition from a loader, while the other updates an existing definition subject to specific limitations.

## 2. Comparison table

| Criterion | redefineClasses | retransformClasses | New loader |
| --- | --- | --- | --- |
| Input | ClassDefinition(Class c, byte[] bytes) | Class<?> targets | Class name and byte source |
| Is a Java agent required? | Yes, Instrumentation | Yes, Instrumentation | No |
| Are replacement class-file bytes passed directly? | Yes | No, handled by the transformer pipeline | Possible, via defineClass |
| Does the target Class object change to another object? | No | No | Yes, a new Class defined by the new loader |
| Do existing instances use the new method body? | Yes, on a new invocation | Yes, on a new invocation | No, old instances still belong to the old Class |
| Are static field values reset? | No | No | The new Class has its own static state |
| Re-run the old class's static initializer? | No | No | The new Class initializes separately upon active use |
| Add new fields or methods? | No, under Java 17 JVMTI limits | No, under Java 17 JVMTI limits | Possible in the new class |
| Can two versions with the same binary name run? | No, not as two runtime types | No, not as two runtime types | Yes, if the loaders differ |
| Example use cases | Hot-fixing a method body | Coverage/APM instrumentation | Plugin reload, isolation, API evolution |
| Risks | Capability, schema, active frames | Transformer ordering, replay | Type identity, delegation, leaks |

**Key takeaway:** Redefine and retransform are not ways to replace a Class object. A new loader does not modify the old Class object. The three approaches solve different problems.

## 3. Can an already loaded class be redefined using defineClass?

**No.** Once a loader has defined a class with a binary name such as **lesson.hot.Feature**, that loader cannot call defineClass again with the same name as a way to overwrite the old version. The JVM may throw a **LinkageError** due to a duplicate definition. loadClass may continue returning the same Class already recorded by the JVM.

To change the behavior of the exact running Class, use the instrumentation mechanism if supported; to obtain a completely new class with the same name, create another loader:

~~~text
Initially:
  Feature Class object
       |
       +-- binary name = lesson.hot.Feature
       +-- defining loader = L1
       +-- method body V1

Redefine / retransform:
  Feature Class object (still the same object)
       |
       +-- defining loader = L1 (unchanged)
       +-- method body V2 installed validly

Different loader:
  Feature class A = (lesson.hot.Feature, L1)
  Feature class B = (lesson.hot.Feature, L2)

  A != B even though the names are completely identical
~~~

Instances belonging to A do not automatically turn into instances of B. You need to manage traffic/migration when switching a plugin to B.

## 4. Instrumentation, agent, and capability

### 4.1 A Java agent provides Instrumentation

An application normally cannot call a constructor itself to create an **Instrumentation**. The JVM passes this object into the entry point of a Java agent:

~~~java
import java.lang.instrument.Instrumentation;

public class Agent {
    public static void premain(
            String args, Instrumentation instrumentation) {
        // Called by the JVM when the application starts with -javaagent
    }

    public static void agentmain(
            String args, Instrumentation instrumentation) {
        // May be called when the agent is attached later,
        // if the JVM and runtime policy allow
    }
}
~~~

These are illustrative signatures, not yet a standalone runnable program.

The simple and reproducible way in this lesson is to run **-javaagent:agent.jar**. The JVM reads **Premain-Class** in the JAR manifest, calls premain before the application main, and only then does the application execute its work.

Dynamic attach/agentmain is a conditional capability that may be restricted by JDK policy or the deployment environment. Do not assume you can always attach to a production JVM.

### 4.2 Manifest capabilities

~~~text
Premain-Class: Agent
Can-Redefine-Classes: true
Can-Retransform-Classes: true
~~~

This is the content of the **agent.mf** file, not Java source. Capabilities must be appropriately requested via the manifest and actually supported by the JVM.

Checking in agent code:

~~~java
boolean redefine = inst.isRedefineClassesSupported();
boolean retransform = inst.isRetransformClassesSupported();
boolean targetModifiable = inst.isModifiableClass(Target.class);
~~~

This is a snippet placed inside a method that has appropriate inst and Target variables.

- **isRedefineClassesSupported** and **isRetransformClassesSupported** are two independent capabilities.
- **isModifiableClass** checks whether a specific class is modifiable; a true result does not replace checking the corresponding capability.
- Primitive classes and array classes cannot be redefined/retransformed.
- Some VM-defined classes may also not be modifiable.
- Requesting a capability in the manifest does not force the JVM to grant a capability that the VM does not support.

## 5. Valid class-file data and modification limits

With standard Java 17/JVMTI, redefine/retransform primarily allow **modifying method bodies, the constant pool, and permitted attributes** of an existing class. The following changes are generally prohibited:

| Change | Java 17 redefine/retransform |
| --- | --- |
| Modifying instructions in an existing method | Possible, if the bytes are valid |
| Replacing the constant pool/permitted attributes | Possible |
| Adding or removing a field | No |
| Adding or removing a method | No |
| Changing a method's name or descriptor | No |
| Changing the field schema | No |
| Changing modifiers restricted by the specification | No |
| Changing the direct superclass or implemented interfaces | No |
| Changing NestHost/NestMembers | No |
| Changing Record/PermittedSubclasses attributes | No |
| Bytes declaring a binary name different from the target Class | No |
| Class-file version newer than the VM supports | No |

Do not assume that because a new class **compiled successfully**, it can definitely redefine the old class. The two versions may differ in schema, prohibited annotations/attributes, method modifiers, or hierarchy.

**A new loader differs here:** A loader L2 can define a new type with added/removed fields/methods or a different API, as long as it is a valid class according to the JVM and satisfies the corresponding loading/module/package constraints. However, you must accept a **new Class identity**.

Specialized VMs/tools may provide non-standard enhanced hot-swap; do not treat that as a general guarantee of Java 17.

## 6. Java 17+ example environment

The three complete examples below use a unified source tree. The two Feature versions have the same binary name but different behavior. TraceTarget is used to test the transformer. The demos have been compiled/run on OpenJDK 21 and use only Java 17+ APIs.

~~~text
project/
├── agent.mf
├── versions/
│   ├── v1/lesson/hot/Feature.java
│   └── v2/lesson/hot/Feature.java
├── retrans-src/lesson/hot/TraceTarget.java
└── host-src/
    ├── Agent.java
    ├── RedefineDemo.java
    ├── RetransformDemo.java
    └── NewLoaderDemo.java
~~~

Output folders when compiling: **v1**, **v2**, **retrans**, **host**. Run all commands from the **project** directory. If you use Windows PowerShell, the separator between multiple classpath entries is **;** instead of **:** on Linux/macOS.

### 6.1 Feature version 1

**versions/v1/lesson/hot/Feature.java**:

~~~java
package lesson.hot;

public class Feature {
    public static int state = 7;

    static {
        System.out.println("Feature V1 initialized");
    }

    public String label() {
        return "v1";
    }
}
~~~

### 6.2 Feature version 2

**versions/v2/lesson/hot/Feature.java**:

~~~java
package lesson.hot;

public class Feature {
    public static int state = 999;

    static {
        System.out.println("Feature V2 initialized");
    }

    public String label() {
        return "v2";
    }
}
~~~

The two versions **keep the exact same schema**: the same public field state and method label. Only the method bodies and the static initializer code change.

Compile into two separate directories:

~~~bash
javac -d v1 versions/v1/lesson/hot/Feature.java
javac -d v2 versions/v2/lesson/hot/Feature.java
~~~

Do not place these two Feature.java files in the same compilation unit or the same output folder, because one version will be overwritten or the compiler will report a duplicate class.

### 6.3 Shared agent

**host-src/Agent.java**:

~~~java
import java.lang.instrument.Instrumentation;

public class Agent {
    static volatile Instrumentation instrumentation;

    public static void premain(
            String args, Instrumentation inst) {
        instrumentation = inst;
    }
}
~~~

**agent.mf** (text manifest file, must have a trailing newline):

~~~text
Premain-Class: Agent
Can-Redefine-Classes: true
Can-Retransform-Classes: true
~~~

After compiling Agent.class into host, package it:

~~~bash
jar --create --file agent.jar --manifest agent.mf -C host Agent.class
~~~

In the two instrumentation demos, **-javaagent:agent.jar** ensures that premain has set Instrumentation by the time main runs.

## 7. Runnable example 1 — redefineClasses

**host-src/RedefineDemo.java**:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.lang.instrument.ClassDefinition;
import java.lang.instrument.Instrumentation;
import lesson.hot.Feature;

public class RedefineDemo {
    public static void main(String[] args) throws Exception {
        Instrumentation inst = Agent.instrumentation;

        System.out.println("redefine supported = "
                + inst.isRedefineClassesSupported());

        Feature object = new Feature();
        Class<?> type = object.getClass();

        System.out.println("before = " + object.label());
        System.out.println("state before = " + Feature.state);

        byte[] replacement = Files.readAllBytes(
                Path.of(args[0]));

        inst.redefineClasses(
                new ClassDefinition(Feature.class, replacement));

        System.out.println("same Class = "
                + (type == object.getClass()));
        System.out.println("same object = " + object.label());
        System.out.println("new object = "
                + new Feature().label());
        System.out.println("state after = " + Feature.state);
    }
}
~~~

Compile once v1/v2 and Agent.java are in place:

~~~bash
javac -cp v1 -d host host-src/Agent.java host-src/RedefineDemo.java
jar --create --file agent.jar --manifest agent.mf -C host Agent.class
java -javaagent:agent.jar -cp host:v1 RedefineDemo v2/lesson/hot/Feature.class
~~~

Windows PowerShell:

~~~powershell
javac -cp v1 -d host host-src/Agent.java host-src/RedefineDemo.java
jar --create --file agent.jar --manifest agent.mf -C host Agent.class
java -javaagent:agent.jar -cp "host;v1" RedefineDemo v2/lesson/hot/Feature.class
~~~

**Actual stdout on OpenJDK 21:**

~~~text
redefine supported = true
Feature V1 initialized
before = v1
state before = 7
same Class = true
same object = v2
new object = v2
state after = 7
~~~

### 7.1 Detailed analysis

1. **Feature** is initialized for the first time from v1, printing **Feature V1 initialized**.
2. The JVM keeps the static field **state = 7**.
3. **ClassDefinition(Feature.class, replacement)** supplies the v2 bytes for the exact target Class.
4. **Instrumentation.redefineClasses** validly updates the method code. There is no new Class object.
5. **same Class = true** because the existing object still has the old runtime type in terms of identity.
6. **same object = v2** because a new method call on the existing instance uses the v2 method body.
7. A new instance also calls the v2 method body.
8. **state after = 7**, not 999. **Feature V2 initialized** also does not appear.

Redefinition **does not re-run the static initializer** and does not automatically reset static fields or recreate instances.

### 7.2 When the demo cannot run as-is

The redefine capability depends on the JVM, so the output “supported=true” applies to the test OpenJDK with an appropriate manifest, not every VM. If unsupported, calling redefineClasses may throw UnsupportedOperationException. If the replacement bytes change the field/method schema or have a different binary name, the JVM rejects them.

**If you only want to test on a JVM that has the capability**, this demo is sufficient. Production code should additionally check **isModifiableClass(Feature.class)** before intervening.

## 8. Runnable example 2 — retransformClasses

### 8.1 Difference in input

**retransformClasses(TraceTarget.class)** accepts only the target Class. The JVM uses the appropriate **ClassFileTransformer pipeline** to recompute the bytes for the existing definition, instead of the caller sending a class-file array to ClassDefinition.

**retrans-src/lesson/hot/TraceTarget.java**:

~~~java
package lesson.hot;

public class TraceTarget {
    public String label() {
        return "OLD-CODE";
    }
}
~~~

To avoid needing external library dependencies, the example only replaces a UTF-8 constant of the same length: **OLD-CODE → NEW-CODE**. This is a very narrow illustrative trick, not a production transformer.

### 8.2 RetransformDemo.java source

**host-src/RetransformDemo.java**:

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.nio.charset.StandardCharsets;
import java.security.ProtectionDomain;
import java.util.Arrays;
import lesson.hot.TraceTarget;

public class RetransformDemo {
    static byte[] replaceMarker(byte[] original) {
        byte[] search =
                "OLD-CODE".getBytes(StandardCharsets.US_ASCII);
        byte[] replace =
                "NEW-CODE".getBytes(StandardCharsets.US_ASCII);

        byte[] result = Arrays.copyOf(
                original, original.length);

        int matches = 0;

        for (int i = 0;
             i <= result.length - search.length; i++) {
            boolean match = true;

            for (int j = 0; j < search.length; j++) {
                if (result[i + j] != search[j]) {
                    match = false;
                    break;
                }
            }

            if (match) {
                matches++;
                System.arraycopy(
                        replace, 0, result, i, replace.length);
            }
        }

        if (matches != 1) {
            throw new IllegalStateException(
                    "Expected one marker, found " + matches);
        }

        return result;
    }

    public static void main(String[] args) throws Exception {
        Instrumentation inst = Agent.instrumentation;

        System.out.println("retransform supported = "
                + inst.isRetransformClassesSupported());

        TraceTarget existing = new TraceTarget();
        System.out.println("before = " + existing.label());

        ClassFileTransformer transformer =
                new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    ClassLoader loader,
                    String name,
                    Class<?> redef,
                    ProtectionDomain domain,
                    byte[] bytes) {

                if (!"lesson/hot/TraceTarget".equals(name)
                        || redef == null) {
                    return null;
                }

                return replaceMarker(bytes);
            }
        };

        inst.addTransformer(transformer, true);

        try {
            inst.retransformClasses(TraceTarget.class);
        } finally {
            inst.removeTransformer(transformer);
        }

        System.out.println("after = " + existing.label());
        System.out.println("same class = "
                + (existing.getClass() == TraceTarget.class));
    }
}
~~~

Compile/run:

~~~bash
javac -d retrans retrans-src/lesson/hot/TraceTarget.java
javac -cp retrans -d host host-src/Agent.java host-src/RetransformDemo.java
jar --create --file agent.jar --manifest agent.mf -C host Agent.class
java -javaagent:agent.jar -cp host:retrans RetransformDemo
~~~

Windows PowerShell:

~~~powershell
javac -d retrans retrans-src/lesson/hot/TraceTarget.java
javac -cp retrans -d host host-src/Agent.java host-src/RetransformDemo.java
jar --create --file agent.jar --manifest agent.mf -C host Agent.class
java -javaagent:agent.jar -cp "host;retrans" RetransformDemo
~~~

**Actual stdout on OpenJDK 21:**

~~~text
retransform supported = true
before = OLD-CODE
after = NEW-CODE
same class = true
~~~

### 8.3 Points to understand to avoid incorrect implementation

- **addTransformer(transformer, true)** requires a retransform-capable transformer.
- **ClassFileTransformer** in Java 17 has two default transform overloads and is **not a functional interface**. Therefore, the example uses an anonymous class, not a lambda.
- The transformer receives an **internal class name** such as **lesson/hot/TraceTarget**, not the Java name lesson.hot.TraceTarget.
- **redef != null** during retransformation; during initial class loading it is normally null.
- Return **null** when not modifying bytes.
- Do not mutate the input **classfileBuffer** directly; the example uses **Arrays.copyOf**.
- Both old/new markers are 8 ASCII bytes, so the length of a constant pool UTF-8 entry does not change. The code verifies there is exactly one marker in the target file.
- **removeTransformer** only removes the registration for subsequent transformations; it **does not automatically revert the already installed bytecode**.
- The existing instance remains the same object with the same class identity, while new invocations execute the new method code.

**Limitation:** modifying raw bytes via string search can corrupt other class files. Only apply this to a controlled compiled fixture. Real projects need ASM/Byte Buddy or an appropriate class-file API to make structured changes while keeping stack map frames and the constant pool valid.

## 9. Runnable example 3 — two new ClassLoaders

### 9.1 No Java agent needed

In this example we will **neither redefine nor retransform**. We define **two different Classes** from the exact two v1/v2 Feature.class files using two separate loaders.

**host-src/NewLoaderDemo.java**:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.io.IOException;

public class NewLoaderDemo {
    static final class VersionLoader extends ClassLoader {
        private final Path classFile;

        VersionLoader(Path classFile) {
            super(ClassLoader.getPlatformClassLoader());
            this.classFile = classFile;
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!name.equals("lesson.hot.Feature")) {
                throw new ClassNotFoundException(name);
            }

            try {
                byte[] bytes = Files.readAllBytes(classFile);
                return defineClass(name, bytes, 0, bytes.length);
            } catch (IOException ex) {
                throw new ClassNotFoundException(name, ex);
            }
        }
    }

    static String label(Class<?> type) throws Exception {
        Object object = type.getConstructor().newInstance();
        return (String) type.getMethod("label").invoke(object);
    }

    public static void main(String[] args) throws Exception {
        VersionLoader first = new VersionLoader(
                Path.of("v1/lesson/hot/Feature.class"));

        VersionLoader second = new VersionLoader(
                Path.of("v2/lesson/hot/Feature.class"));

        Class<?> a = first.loadClass("lesson.hot.Feature");
        Class<?> b = second.loadClass("lesson.hot.Feature");

        System.out.println("same name = "
                + a.getName().equals(b.getName()));
        System.out.println("same Class = " + (a == b));
        System.out.println("first loader = "
                + (a.getClassLoader() == first));
        System.out.println("second loader = "
                + (b.getClassLoader() == second));
        System.out.println("first value = " + label(a));
        System.out.println("second value = " + label(b));
    }
}
~~~

Compile/run after v1 and v2 are in place:

~~~bash
javac -d host host-src/NewLoaderDemo.java
java -cp host NewLoaderDemo
~~~

**Actual stdout on OpenJDK 21:**

~~~text
same name = true
same Class = false
first loader = true
second loader = true
Feature V1 initialized
first value = v1
Feature V2 initialized
second value = v2
~~~

### 9.2 Explanation

- Both Classes have the name **lesson.hot.Feature**.
- The defining loaders are two different VersionLoader objects, so **a != b**.
- Each Class has its own static state, initialized for the first time according to its lifecycle.
- Existing instances belonging to the V1 version still use V1; objects created from B use V2.
- There are no Instrumentation calls; this is normal class loading across two loaders.

**Why set the platform loader as parent?** The example does not put v1/v2 on the application classpath. The platform parent cannot see the plugin class provided by the test, so our custom findClass is called. If you use a parent that already has the same class name, the **parent-first** mechanism can return the parent's Class and fail to create the expected separate version.

The minimal example only supports one binary name; a production loader must control paths, packages, protection domains, modules, resources, and trust boundaries.

## 10. Old instances, static state, and active frames

### 10.1 Once redefine/retransform has succeeded

According to Instrumentation/JVMTI:

- An **existing Class object** still represents that class.
- **Existing objects** are not recreated. Instance fields keep their current values.
- **Static values** keep their state, even if the replacement file has different initialization code.
- The **static initializer does not automatically re-run** due to redefine/retransform.
- A **new method invocation** uses the new method body.
- **Active frames** currently executing the old method body may continue running the old bytecode until the frame completes.

~~~text
Thread A has already entered method V1
          |
JVM updates Class to V2
          |
          +-- frame A still uses V1 code
          |
Thread B starts a new method invocation
          |
          +-- uses V2 code
~~~

Therefore, after the agent reports a successful update, you cannot conclude that every request in every thread immediately switches to the new logic. If changing behavior related to state, transactions, or security, consider quiescence, in-flight requests, and rollback.

### 10.2 When using a new loader

Class V2 differs from Class V1, so V2 has its own static initialization upon active use. V1 objects are not automatically migrated by the JVM to V2. If data must be transferred, the application needs an explicit conversion/serialization/DTO or recreation mechanism, while preparing to release references to the old version.

Do not call a **new loader** “changing the method body of the current Class”. This is **switching the system to a new type identity**.

## 11. Exact retransformation pipeline

Retransform is not simply “re-calling every transformer”:

~~~text
Initial class file bytes
          |
          v
Transformer A: canRetransform = false
          |
          +-- reapply previous transform result
          |   DO NOT re-call A's transform method
          |
          v
Transformer B: canRetransform = true
          |
          +-- re-call B.transform(...)
          |
          v
Transformer C: canRetransform = true
          |
          +-- re-call C.transform(...)
          |
          v
Verify and install valid bytes for the same Class
~~~

According to the API, **initial class file bytes** may not match byte-for-byte the bytes originally passed into defineClass, because the JVM may differ in constant-pool layout or certain attributes. Do not write a transformer that relies on fixed offsets in an actual class file.

**Transformer ordering** is governed by ClassFileTransformer. In a multi-agent environment, transformations interact with each other: you must verify idempotence, class schema, performance, and ordering. RedefineClasses can also trigger registered transformers while processing replacement bytes, so an agent should not assume that redefine completely bypasses the chain.

**A transformer added after a Class is loaded does not automatically modify the already loaded Class.** Example 2 must explicitly call retransformClasses for the transformer to take effect retroactively.

## 12. What happens if the operation fails?

| Scenario | Error or symptom | How to handle |
| --- | --- | --- |
| Capability not supported | UnsupportedOperationException | Check manifest and is*Supported |
| Class not modifiable | UnmodifiableClassException | Check isModifiableClass |
| Adding a field/method or changing hierarchy | UnsupportedOperationException/related VM error | Compare schema, choose a new loader if needed |
| Malformed bytes | ClassFormatError | Check generator, input bytes |
| Binary name in bytes does not match target | NoClassDefFoundError | Check the internal name of the class file |
| Bytecode verifier rejects | VerifyError/LinkageError | Inspect bytecode and dependencies |
| Classfile version too new | UnsupportedClassVersionError | Use --release and a suitable JDK |
| Transformer not registered as capable | Not re-called during retransform | addTransformer(..., true), capabilities |
| JAR changes on disk but Class stays old version | Does not auto-reload | Use instrumentation or a new loader |
| Child loader returns Class from parent | No separate version | Understand parent delegation and defining loader |

Operations on **a set of Classes** have documented semantics: if redefinition/retransformation throws an exception while being applied, **none of the classes in that set get the new version installed**. Do not extrapolate that into a rollback of all side effects in the application or in external transformers.

An individual transformer failure does not necessarily halt the entire pipeline: the Javadoc states that the JVM may continue with other transformers. Do not use an exception inside a transformer as a guaranteed rollback mechanism; instead, validate bytes and log according to an appropriate contract.

## 13. Hot-reload capabilities and application state limitations

### 13.1 Redefine for patching methods

Suitable for a logic fix with an unchanged schema. The advantage is that existing objects use the new code on new invocations without needing to replace references across the entire system.

However, if the new logic expects new static fields or new invariants, the JVM does not automatically convert state. You must design migration/feature flags/compatibility separately.

### 13.2 Retransform for monitoring

Profilers and coverage agents often want to insert instructions into existing methods without manually rewriting entire classes. Retransform allows re-running the pipeline when instrumentation needs to be enabled/disabled or when changing strategy (within API/VM limits).

There is no guarantee that every class is instrumentable; check capabilities and modifiability.

### 13.3 New loader for plugin evolution

A plugin manager typically loads the V2 implementation in a new loader/layer, routes requests to the V2 service, and then stops V1. V2 can have a different schema, but requires:

- Shared interfaces/DTOs/APIs with the same Class identity at the host/plugin boundary.
- A parent delegation policy that does not cause the child to accidentally load the old version from the parent.
- In-flight requests currently using V1 have a path to finish.
- Plugin V1 has its listeners/services/caches unregistered.
- Threads/executors/ThreadLocal/TCCL do not retain the V1 loader indefinitely.
- The JVM can only unload old classes when the defining loader has no remaining strong references, with no guarantee immediately after stop.

Do not use ClassLoader as a security sandbox for untrusted code; class-loading isolation is not equivalent to process isolation.

## 14. Common misconceptions

**“Redefine creates a new Class object.”** False: it is still the existing target Class.

**“Retransform is like calling defineClass a second time.”** False: retransform operates on an already loaded Class through the transformer pipeline.

**“The new version's static block always runs on redefine.”** False: <clinit> is not proactively re-run.

**“Replace the source/JAR and the class updates automatically.”** False: the JVM does not automatically overwrite a live Class when file bytes change on disk.

**“Redefine can arbitrarily add methods/fields.”** False under standard Java 17/JVMTI limits.

**“All running threads immediately use the new bytecode.”** False: active stack frames may continue executing the old bytecode.

**“A new Class with the same name can always be cast to the old Class.”** False if the defining loaders differ.

**“A transformer with canRetransform=false is re-called on every retransform.”** False: its previous result is replayed according to the rules.

**“removeTransformer reverts installed changes.”** False: it removes future registration.

**“ClassFileTransformer uses a Java 17 lambda like Runnable.”** False: it is not a functional interface; Example 2 uses an anonymous class.

**“When isModifiableClass is true, the capability is definitely granted.”** False: you must check the capability separately.

**“A new ClassLoader always ensures the old loader gets unloaded.”** False: if old threads/callbacks retain strong references, the old loader stays alive.

## 15. Technical decision flow

~~~text
Want to modify Java runtime code behavior?
          |
          v
Has the target Class already been defined by the JVM?
          |
          +-- No: normally use ClassLoader/findClass/defineClass
          |
          +-- Yes
                |
                v
          Only valid method body / instrumentation changes?
                |
          +-----+-----+
          |           |
         Yes          No
          |           |
          v           v
    Have agent and   Need new schema,
    capability?      new API, dual versions?
          |           |
       +--+--+        v
       |     |       New loader + lifecycle
      Yes    No
       |     |
       v     v
   Redefine/ need another tool,
   Retransform restart, or a new loader
~~~

**Use redefine** if you have replacement class-file bytes and want to replace the definition of an existing Class.

**Use retransform** if you want to reapply the transformer chain on an already loaded Class.

**Use a new loader** if you need a separate new runtime class version, especially when a different schema or coexistence is required.

## 16. Self-check

**Question 1.** Feature v1 has initialized state=7. When redefining from bytes that have state=999, does state automatically change to 999?

**Answer:** No. Static values are preserved; <clinit> does not automatically re-run.

**Question 2.** Does an existing object calling a method after redefine use the new body?

**Answer:** Yes, on a new invocation, with exceptions for active frames already executing the old code.

**Question 3.** Does the caller of retransformClasses pass ClassDefinition or Class<?>?

**Answer:** Class<?> targets; the JVM applies the transformer pipeline.

**Question 4.** Is a non-capable transformer re-called during retransform?

**Answer:** No; the previous transform result is replayed per the API.

**Question 5.** Two loaders define a class with the same binary name; are the Class objects equal?

**Answer:** No; the defining loader is part of class identity.

**Question 6.** To add a new field to a live Feature on standard Java 17, should you redefine it?

**Answer:** No; that is an unsupported schema change—consider a new loader and migration.

**Question 7.** Why are Can-Retransform-Classes and addTransformer(..., true) needed?

**Answer:** Both the capability and the transformer registration must allow retransformation; otherwise, retransform cannot re-call the transformer as expected.

**Question 8.** An agent registers a new transformer after TraceTarget has already been loaded. Does the Class change automatically right away?

**Answer:** No; the example must explicitly call retransformClasses.

**Question 9.** Is ClassLoader.loadClass guaranteed to see a .class file that was replaced on disk?

**Answer:** No. The loader may return an already loaded Class; parent delegation may also return a Class from another source.

**Question 10.** Does using a new loader to deploy plugin V2 automatically remove the V1 instance from the host registry?

**Answer:** No. You must unregister and clean up references/callbacks/threads so that V1 can be collectible.

## 17. Takeaways

~~~text
Redefine:
  Existing Class C
      + replacement bytes via ClassDefinition
      -> method body changes validly
      -> same C, same objects, static state preserved

Retransform:
  Existing Class C
      + transformer chain reapplied
      -> method body changes validly
      -> same C, same objects, static state preserved

New ClassLoader:
  Binary name + new loader
      -> a different Class C2, C2 != C
      -> separate static initialization/state
      -> suitable for new schema/dual versions
~~~

**In one sentence:** Redefine **replaces the definition of the same Class** from new bytes; retransform **reapplies bytecode transformers** on the same Class; a new ClassLoader **creates a new type identity** and requires managing migration, boundaries, and lifecycle.

### Official references

- Java SE 17 Instrumentation API: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- Java SE 17 ClassDefinition API: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html
- Java SE 17 ClassFileTransformer API: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
- Java SE 17 java.lang.instrument agent package: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
- Java SE 17 JVM Tool Interface specification: https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html
- Java SE 17 ClassLoader API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 JLS §12: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html
