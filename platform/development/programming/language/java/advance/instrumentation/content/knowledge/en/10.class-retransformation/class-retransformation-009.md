# Retransformation: Constraints with `NestHost`, `NestMembers`, `Record`, and `PermittedSubclasses`

> **Context:** Java Advance → Instrumentation → **Retransformation**. Once a JVM has defined a class, `Instrumentation.retransformClasses(...)` can install a new version of **method bodies**, but cannot arbitrarily alter the identity, structure, or class relationships already recognized by the JVM. The four class-file attributes `NestHost`, `NestMembers`, `Record`, and `PermittedSubclasses` belong to the group that **must not be changed** during retransformation and redefinition according to the Java 17/21 JVM TI specification. The example below runs with Java 17+ source code and has been empirically verified on OpenJDK 24.

## 1. Why Does a Retransformation Have Limits?

A class can be instrumented when it is **first defined** (load-time transformation) or after a `Class<?>` already exists using `retransformClasses(...)`:

~~~text
Original class file
   │
   ├── Load-time: ClassFileTransformer.transform(..., classBeingRedefined=null)
   │   └── JVM defines the class and establishes type/nest/record/sealed relationships
   │
   └── Class already exists in the JVM
       └── Instrumentation.retransformClasses(existingClass)
           ├── transformers with canRetransform=true are invoked again
           ├── JVM validates the class file after the entire transformer chain
           ├── valid     -> installs the new definition
           └── violation -> rejects, does not install the modified version
~~~

Retransformation is not a tool to “recompile any Java source and hot-swap it.” According to the JVM TI specification:

- **Method bodies** and certain constant pool/attribute contents may be modified, **except** for changes that are prohibited or make the class file invalid.
- **Fields/methods** must not be added, removed, or renamed; **method signatures**, **modifiers**, and **inheritance** must not be changed.
- **Four class-level attributes must not be changed:** `NestHost`, `NestMembers`, `Record`, `PermittedSubclasses`.
- These restrictions apply to both `RetransformClasses` and `RedefineClasses` on the specified JDKs; do not assume using `redefineClasses` instead of `retransformClasses` is a valid way to bypass them.
- If a retransformation request targets multiple classes and the JVM returns an error, **no class in that set receives a new definition**. Evaluation/validation occurs after the transformer chain has processed the bytes.

A Java agent must request the `Can-Retransform-Classes: true` capability in its manifest and verify `Instrumentation.isRetransformClassesSupported()`. Furthermore, `isModifiableClass(type)` only indicates that a class **can be considered for transformation**, not that every bytecode patch submitted is valid.

### Distinguishing the Three Operations

| Operation | Input | Can It Modify the Four Attributes? |
|---|---|---|
| **Load-time transform** | Bytes when the class has **not yet** been defined by the JVM | Can produce a valid class file with appropriate attributes before initial definition; must still comply with JVMS, access control, class-format, and verification |
| **Retransform** | Loaded `Class<?>`, JVM re-runs the transformation pipeline | **Must not change** `NestHost`, `NestMembers`, `Record`, `PermittedSubclasses` |
| **Redefine** | `ClassDefinition(type, replacementBytes)` of a loaded class | **Also must not change** the four attributes per JVM TI |

It is possible to **preserve the four attributes** and modify valid code: do not assume “record/sealed/nest classes cannot be retransformed.” A class containing those attributes **can still be retransformed** if the JVM supports it, the class is modifiable, and the result does not violate constraints. The presence of the attribute is not an error; **an invalid modification of the attribute** is what causes the problem.

## 2. `NestHost` and `NestMembers`: Private Access Relationships

Since Java 11 (class-file version **55**), the JVM has supported the **nest** concept (JEP 181). Classes belonging to the same nest can access each other's `private` members under JVM access control rules, even when they are in separate class files.

Two attributes hold **the two sides of the same relationship**:

| Attribute | Located in Which Class? | Data and Meaning |
|---|---|---|
| `NestHost` | **Member** class/interface that is not the host | A `u2 host_class_index` referencing the `CONSTANT_Class_info` constant-pool entry of the nest host |
| `NestMembers` | Class/interface **acting as host** | A `number_of_classes` count and `u2 classes[]` array, listing the classes permitted by the host to declare themselves as members |

A host belongs to the nest of which it is the host, so it does not need to record a `NestHost` pointing to itself. According to the JVMS, **`NestHost` and `NestMembers` must not both appear in the same class file**. An ordinary Java nested class can have `NestHost` pointing to the outer class; the outer class has `NestMembers` containing the nested classes.

Java 17 example:

~~~java
package lab.model;

public final class Outer {
    private static int secret() {
        return 41;
    }

    public static final class Inner {
        public static int answer() {
            return secret() + 1; // Private access enabled by nestmates.
        }
    }
}
~~~

When compiled, `Outer.class` typically has `NestMembers: lab/model/Outer$Inner` and `Outer$Inner.class` has `NestHost: class lab/model/Outer`. Verify with `javap -v -p`.

**Why can't they be changed once a class is loaded?** The JVM may already have used nest information for access checking, resolution, and linking classes. If hot-swapping arbitrarily changed the host or member list, a class already accepted by the JVM could suddenly be granted or stripped of `private` access. The specification does not allow “changing the nest ancestry” via retransform/redefine.

Examples of **prohibited** changes:

- Changing `Outer$Inner.NestHost` from `Outer` to another host.
- Adding/removing `Outer$Inner` from `Outer.NestMembers`.
- Removing `NestHost`/`NestMembers` entirely from a loaded class, even without changing method bytecode.
- Altering the contents of the member list, even if the visible class names in Java source do not change.

**Distinguishing `InnerClasses`:** the `InnerClasses` attribute carries metadata about nested-class structure in source/bytecode; it **does not replace** `NestHost`/`NestMembers` for determining nestmate private access. ASM tools or bytecode visitors must not use the `InnerClasses` list to heuristically “reconstruct” nest metadata during retransformation.

### Caution with Multiple Class Loaders

Nest membership is also tied to **run-time package** and class identity. Two classes with the same name defined by two different defining class loaders are not automatically nestmates. Editing a `NestHost` name string cannot turn two incompatible class loaders into a valid nest; and for a loaded class, the JVM forbids changing the attribute during retransformation even if the new name looks “valid.”

## 3. `Record`: Record Shape and Record Components

The `Record` class-file attribute appeared in class-file version **60** (Java 16). It records metadata about **record components**, including each component's name, descriptor, and associated attributes. For example:

~~~java
package lab.model;
public record Point(int x, int y) { }
~~~

In `Point.class`, `javap -v` may display:

~~~text
Record:
  int x;
    descriptor: I

  int y;
    descriptor: I
~~~

A record class also has compiler-generated fields/methods/constructors: `private final` fields, `x()`/`y()` accessors, canonical constructor, `equals`, `hashCode`, `toString`. However, **the `Record` attribute is not just a list of fields**: it is record component metadata used by reflection `Class.isRecord()` and `Class.getRecordComponents()` along with language/runtime rules.

Retransform/redefine must not be used to:

- Change record components `(x, y)` to `(x, y, z)`.
- Rename component `x` to `left`, or change a component's descriptor.
- Remove the `Record` attribute to turn a loaded class into an ordinary class.
- Add `Record` to a class that did not have one to “turn it into a record.”
- Let a code visitor accidentally drop or rewrite `Record` metadata in an incompatible form.

Many of the cases above also violate the rule against **adding/removing fields, methods, or changing signatures**. However, even a patch that **only alters the `Record` attribute** without touching the method list is prohibited. Checking the field/method schema is necessary but **not sufficient**.

**What remains useful:** you can instrument **the bodies of existing accessors, constructors, or business methods** when the transformation is valid, keeping the count/names/descriptors/modifiers and `Record` metadata intact. For example, adding a timing probe to `Point.x()` without changing its signature, provided the new bytecode is valid and does not break application semantics.

## 4. `PermittedSubclasses`: Inheritance Boundaries of Sealed Types

The `PermittedSubclasses` attribute appeared in class-file version **61** (Java 17). It resides on a sealed class/interface and lists the classes/interfaces **permitted to directly extend or implement** that type.

Example:

~~~java
package lab.model;
public sealed interface Shape permits Circle, Square { }

final class Circle implements Shape { }
final class Square implements Shape { }
~~~

In `Shape.class`, `javap -v` may display:

~~~text
PermittedSubclasses:
  lab/model/Circle
  lab/model/Square
~~~

This is a list from class-file metadata, **not a list of all indirect subtypes**. In the experiment, `Shape.class.getPermittedSubclasses().length == 2`. If a new subtype extends a `non-sealed` permitted subtype, it does not automatically become a direct entry in `Shape`'s `PermittedSubclasses`.

Do not retransform/redefine `Shape` to:

- Add `Triangle` to `PermittedSubclasses` of a loaded `Shape`.
- Remove `Square` from the list.
- Rename an entry, swap it to another class, or delete the attribute.
- Add the attribute to an ordinary class to turn it into a sealed type after it has been defined.

**Reason:** The JVM enforces `permits` constraints when subclasses are defined; expanding or narrowing inheritance rights mid-JVM-lifecycle creates inconsistency with the already established class hierarchy. Beyond the attribute itself, changing the `final` modifier or hierarchy is also subject to separate retransformation restrictions.

**Do not over-extrapolate:** you can still retransform **method bodies** of a sealed interface, its permitted implementations, or existing subclasses, as long as prohibited relationships are not altered. Having sealed classes in a program does not require the JVM to block *all* instrumentation.

## 5. Summary of Attributes and Constraint Levels

| Class-File Attribute | First Class-File Version | What Does It Reflect? | Example of Prohibited Change During Retransform |
|---|---:|---|---|
| `NestHost` | 55.0 / Java 11 | A class declares its nest host | Changing host from `Outer` to `Other` |
| `NestMembers` | 55.0 / Java 11 | List of members approved by the host | Adding/removing `Outer$Inner` |
| `Record` | 60.0 / Java 16 | Record components metadata | Changing `Point(x, y)` to `Point(x, y, z)` or removing the attribute |
| `PermittedSubclasses` | 61.0 / Java 17 | Direct subclasses permitted by a sealed type | Adding/removing/changing `Circle`, `Square` |

All four are **class-level attributes** in JVMS §4.7; the rule prohibiting changes is stated directly in **JVM TI — Retransform Classes** and repeated in **Redefine Classes**. Specific runtime/JDK limits may evolve in the future, but **do not design a Java 17+ agent assuming the VM will allow changing them**.

### Other Changes That Are Also Constrained

A class can still be rejected even if all four attributes are preserved:

- Adding a `trace()` method to a loaded class; adding a field to store probe state.
- Changing a method descriptor, return type, or parameters.
- Changing `extends`/`implements` or class/method modifiers.
- Returning corrupted bytes, wrong class name, wrong class-file version, verification errors, or an invalid StackMapTable.

Therefore, in retransformation, prefer **injecting code into existing methods**, and keep agent state in a separate class with a clear lifecycle (helper/registry) instead of trying to add fields to target classes. Helper classes, if needed, must be loaded properly without causing recursive class loading/deadlocks.

## 6. Runnable Java 17+ Example: Valid No-Op and Rejected Change

The experiment uses a startup agent with two transformers run in two **separate** passes:

1. **Positive:** a transformer returns `null` and logs a marker when retransforming four classes that carry the attributes above. All passes succeed on HotSpot, showing that classes containing this metadata can still be retransformed.
2. **Negative:** a transformer targets only `Shape.class`, replaces **one entry in `PermittedSubclasses`** in the bytecode after the class has loaded, and asks the JVM to install that version. The JVM rejects it due to constraint violation. The negative code intentionally performs a disallowed action for learning purposes; **do not use this parser/patcher in a production agent**.

File layout:

~~~text
retransform-attributes-lab/
├── manifest.mf
├── src/
│   └── lab/
│       ├── agent/
│       │   └── ConstraintAgent.java
│       ├── app/
│       │   └── ConstraintDemo.java
│       └── model/
│           ├── Outer.java
│           ├── Point.java
│           └── Shape.java
└── out/
    ├── agent/                     # generated during compilation
    ├── app/
    └── constraint-agent.jar
~~~

Use **JDK 17+**, running all commands from the `retransform-attributes-lab` directory. No ASM, Byte Buddy, or Maven is required.

### 6.1 Three Model Files

`src/lab/model/Outer.java`:

~~~java
package lab.model;

public final class Outer {
    private static int secret() { return 41; }

    public static final class Inner {
        public static int answer() { return secret() + 1; }
    }
}
~~~

`src/lab/model/Point.java`:

~~~java
package lab.model;

public record Point(int x, int y) { }
~~~

`src/lab/model/Shape.java`:

~~~java
package lab.model;

public sealed interface Shape permits Circle, Square { }

final class Circle implements Shape { }
final class Square implements Shape { }
~~~

The Java compiler itself generates the corresponding attributes. Do not attempt to manually assemble `NestHost`/`Record`/`PermittedSubclasses` during compilation. Package-private access for `Circle` and `Square` is sufficient because they are in the same package as `Shape`.

### 6.2 Agent: `src/lab/agent/ConstraintAgent.java`

~~~java
package lab.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.security.ProtectionDomain;

public final class ConstraintAgent {
    private static Instrumentation inst;

    private ConstraintAgent() {}

    public static void premain(String options, Instrumentation instrumentation) {
        inst = instrumentation;
        System.out.println("[AGENT] retransformSupported="
                + inst.isRetransformClassesSupported());
    }

    public static void observe(Class<?>... types) throws Exception {
        if (!inst.isRetransformClassesSupported()) {
            System.out.println("[PROBE] unsupported");
            return;
        }

        ClassFileTransformer observer = new ClassFileTransformer() {
            @Override
            public byte[] transform(Module module, ClassLoader loader, String name,
                    Class<?> old, ProtectionDomain pd, byte[] bytes) {
                if (old != null && name != null && name.startsWith("lab/model/")) {
                    System.out.println("[PROBE] " + name);
                }
                return null;
            }
        };

        inst.addTransformer(observer, true);
        try {
            for (Class<?> type : types) {
                if (inst.isModifiableClass(type)) {
                    inst.retransformClasses(type);
                } else {
                    System.out.println("[PROBE] unmodifiable=" + type.getName());
                }
            }
        } finally {
            inst.removeTransformer(observer);
        }
    }

    public static void attemptPermittedChange(Class<?> sealed) throws Exception {
        if (!inst.isRetransformClassesSupported() || !inst.isModifiableClass(sealed)) {
            System.out.println("[NEGATIVE] unsupported");
            return;
        }

        ClassFileTransformer mutator = new ClassFileTransformer() {
            @Override
            public byte[] transform(Module module, ClassLoader loader, String name,
                    Class<?> old, ProtectionDomain pd, byte[] bytes) {
                if (old != null && "lab/model/Shape".equals(name)) {
                    return patchPermitted(bytes);
                }
                return null;
            }
        };

        inst.addTransformer(mutator, true);
        try {
            inst.retransformClasses(sealed);
            System.out.println("[NEGATIVE] unexpectedlyAccepted");
        } catch (UnsupportedOperationException expected) {
            System.out.println("[NEGATIVE] rejected="
                    + expected.getClass().getSimpleName());
        } finally {
            inst.removeTransformer(mutator);
        }
    }

    // Reads just enough structure to locate the PermittedSubclasses class attribute.
    // ONLY for the small class files in this exercise; not a general-purpose parser library.
    private static byte[] patchPermitted(byte[] input) {
        byte[] copy = input.clone();
        ByteBuffer b = ByteBuffer.wrap(copy).order(ByteOrder.BIG_ENDIAN);
        if (b.getInt() != 0xCAFEBABE) {
            throw new IllegalArgumentException("not class");
        }
        skip(b, 4); // minor_version, major_version
        int size = u2(b);
        String[] names = new String[size];

        for (int i = 1; i < size; i++) {
            int tag = Byte.toUnsignedInt(b.get());
            switch (tag) {
                case 1 -> {
                    byte[] data = new byte[u2(b)];
                    b.get(data);
                    names[i] = new String(data, StandardCharsets.UTF_8);
                }
                case 3, 4 -> skip(b, 4);
                case 5, 6 -> { skip(b, 8); i++; }
                case 7, 8, 16, 19, 20 -> skip(b, 2);
                case 9, 10, 11, 12, 17, 18 -> skip(b, 4);
                case 15 -> skip(b, 3);
                default -> throw new IllegalArgumentException("tag=" + tag);
            }
        }

        skip(b, 4);              // access_flags + this_class
        int superIndex = u2(b); // java/lang/Object for Shape
        skip(b, 2 * u2(b));     // interfaces
        skipMembers(b);         // fields
        skipMembers(b);         // methods

        int attributes = u2(b);
        for (int i = 0; i < attributes; i++) {
            String name = names[u2(b)];
            int length = b.getInt();
            int start = b.position();

            if ("PermittedSubclasses".equals(name)) {
                if (u2(b) < 1) {
                    throw new IllegalArgumentException("empty permitted");
                }
                // First u2 in the list: replace with the CP index of Object.
                // Does not change length or method/field count.
                b.putShort(b.position(), (short) superIndex);
                return copy;
            }
            b.position(start + length);
        }
        throw new IllegalArgumentException("missing PermittedSubclasses");
    }

    private static int u2(ByteBuffer b) {
        return Short.toUnsignedInt(b.getShort());
    }

    private static void skip(ByteBuffer b, int n) {
        b.position(b.position() + n);
    }

    private static void skipMembers(ByteBuffer b) {
        int count = u2(b);
        for (int i = 0; i < count; i++) {
            skip(b, 6); // access_flags, name_index, descriptor_index
            int attrs = u2(b);
            for (int j = 0; j < attrs; j++) {
                skip(b, 2);  // attribute_name_index
                int len = b.getInt();
                skip(b, len);
            }
        }
    }
}
~~~

**Agent learning points:**

- `premain` receives `Instrumentation` but does not register a transformer until the app calls `observe` or `attemptPermittedChange`. This reduces logging noise and gives the test control over timing.
- In `observe`, the transformer is registered with `canRetransform=true`, sees `classBeingRedefined != null`, and returns `null` to leave bytecode unmodified. Calls to `inst.retransformClasses(type)` are made one class at a time to avoid depending on callback ordering in a multi-class batch.
- In `attemptPermittedChange`, the mutator returns new bytes only for `lab/model/Shape` when processing an **already-loaded class**. `patchPermitted` walks the constant pool and member tables, locates the class-level `PermittedSubclasses` attribute, and replaces the first entry's `u2` with the `super_class` constant-pool index. For the sealed interface `Shape`, `super_class` points to `java/lang/Object`, which is not a class that `Shape` permits to directly implement it. This is a **deliberate modification** so the JVM detects a class attribute differing from the installed definition.
- `classfileBuffer` is not mutated in place: the method clones the array. The class definition is not installed if the JVM rejects it. `removeTransformer(mutator)` sits in `finally` to clean up registration after the experiment.
- This parser is **only sufficient to handle the ordinary class-file structure of the example**. Reading UTF-8 constants via `StandardCharsets.UTF_8` is convenient for matching ASCII attribute names; a production class-file reader must properly handle **modified UTF-8**, bounds checking, constant-pool tags, length/verification, and all new-version variants. Do not copy this patcher as a general bytecode library.

### 6.3 Application: `src/lab/app/ConstraintDemo.java`

~~~java
package lab.app;

import lab.agent.ConstraintAgent;
import lab.model.Outer;
import lab.model.Point;
import lab.model.Shape;

public final class ConstraintDemo {
    public static void main(String[] args) throws Exception {
        System.out.println("[APP] nestHost="
                + Outer.Inner.class.getNestHost().getSimpleName());
        System.out.println("[APP] nestMembers="
                + Outer.class.getNestMembers().length);
        System.out.println("[APP] record=" + Point.class.isRecord());
        System.out.println("[APP] permitted="
                + Shape.class.getPermittedSubclasses().length);

        ConstraintAgent.observe(
                Outer.Inner.class, Outer.class, Point.class, Shape.class);

        ConstraintAgent.attemptPermittedChange(Shape.class);
        System.out.println("[APP] permittedAfter="
                + Shape.class.getPermittedSubclasses().length);
    }
}
~~~

The two markers `permitted` and `permittedAfter` compare metadata before and after the **rejected** pass. In this exercise there are exactly two permitted direct implementations and two nest members including the host itself. The app does not call `answer()` because the goal is to test class structure and retransformation, not business behavior.

### 6.4 Manifest and Capability

`manifest.mf`, with a trailing newline and a blank line ending the header:

~~~text
Manifest-Version: 1.0
Premain-Class: lab.agent.ConstraintAgent
Can-Retransform-Classes: true

~~~

- `Premain-Class` tells the JVM to invoke the static `premain` method when using `-javaagent`.
- `Can-Retransform-Classes: true` requests the capability; the JVM still retains the right not to support it. Always check `isRetransformClassesSupported()` and `isModifiableClass()` instead of assuming.
- `Agent-Class` is not needed because dynamic Attach is not used, and `Can-Redefine-Classes` is not needed because the exercise only calls `retransformClasses`.

### 6.5 Compile and Run

**macOS/Linux (Bash):**

~~~bash
mkdir -p out/agent out/app
javac --release 17 -d out/agent src/lab/agent/ConstraintAgent.java
javac --release 17 -cp out/agent -d out/app src/lab/model/Outer.java src/lab/model/Point.java src/lab/model/Shape.java src/lab/app/ConstraintDemo.java
jar --create --file out/constraint-agent.jar --manifest manifest.mf -C out/agent .
java -javaagent:out/constraint-agent.jar -cp out/agent:out/app lab.app.ConstraintDemo
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force -Path out/agent, out/app | Out-Null
javac --release 17 -d out/agent src/lab/agent/ConstraintAgent.java
javac --release 17 -cp out/agent -d out/app src/lab/model/Outer.java src/lab/model/Point.java src/lab/model/Shape.java src/lab/app/ConstraintDemo.java
jar --create --file out/constraint-agent.jar --manifest manifest.mf -C out/agent .
java "-javaagent:out/constraint-agent.jar" -cp "out/agent;out/app" lab.app.ConstraintDemo
~~~

**Note:** the application needs to call the agent's public helpers, so `out/agent` is on the classpath. The agent JAR is loaded separately by the JVM via `-javaagent`; on a standard system loader, `ConstraintAgent` is shared. Use `:` as the classpath separator on Linux/macOS, and `;` on Windows. Commands must be run from the root directory so the `out/...` paths resolve correctly.

### 6.6 Experimental Stdout

Run on OpenJDK 24 (compiled with `javac --release 17`):

~~~text
[AGENT] retransformSupported=true
[APP] nestHost=Outer
[APP] nestMembers=2
[APP] record=true
[APP] permitted=2
[PROBE] lab/model/Outer$Inner
[PROBE] lab/model/Outer
[PROBE] lab/model/Point
[PROBE] lab/model/Shape
[NEGATIVE] rejected=UnsupportedOperationException
[APP] permittedAfter=2
~~~

**Result analysis:**

1. `retransformSupported=true` confirms the capability for the agent on the test JVM. On a JVM without support, the program prints the `unsupported` branch and skips the negative test.
2. `nestHost=Outer` and `nestMembers=2` reflect the nest relationship of the two compiler-generated classes. `record=true` and `permitted=2` confirm the metadata of the record and sealed type.
3. The four `[PROBE]` lines prove that each class can be retransformed when its structure is **unchanged**. `return null` means the transformer only observes and does not alter method bodies.
4. `[NEGATIVE] rejected=UnsupportedOperationException` proves the JVM rejected the `Shape` definition with a modified `PermittedSubclasses` attribute on the retransform path. The Java `Instrumentation.retransformClasses` Javadoc specifies `UnsupportedOperationException` when an unsupported change is attempted; at the JVM TI layer, a corresponding error is `JVMTI_ERROR_UNSUPPORTED_REDEFINITION_CLASS_ATTRIBUTE_CHANGED`.
5. `permittedAfter=2` shows that the rejected definition **was not installed** and the reflective metadata remained intact.

This output is from a specific JVM/version; exact `UnsupportedOperationException` messages, retransformation support, and additional logging may vary by vendor/JDK. Do not rely on a fixed error message string to detect all cases.

### 6.7 Inspecting the Actual Attributes with `javap -v`

After compilation, on Bash:

~~~bash
javap -v -p out/app/lab/model/Outer.class
javap -v -p 'out/app/lab/model/Outer$Inner.class'
javap -v -p out/app/lab/model/Point.class
javap -v -p out/app/lab/model/Shape.class
~~~

On PowerShell:

~~~powershell
javap -v -p 'out/app/lab/model/Outer.class'
javap -v -p 'out/app/lab/model/Outer$Inner.class'
javap -v -p 'out/app/lab/model/Point.class'
javap -v -p 'out/app/lab/model/Shape.class'
~~~

Where to look: `NestMembers` in Outer; `NestHost` in Outer$Inner; `Record` in Point; `PermittedSubclasses` in Shape. Attribute name strings may also appear in the constant pool, so look for **the class-level attribute section at the end of the output**, not just a string match in the constant pool. Single quotes around `Outer$Inner.class` are essential in Bash/PowerShell so `$` is not interpreted as a variable.

## 7. Diagnosing Failures During Retransform/Redefine

If an agent uses ASM, Byte Buddy, or an instrumentation framework and encounters `UnsupportedOperationException`, you must determine **what actually changed** after the entire transformer chain.

| Symptom | What to Check | How to Fix |
|---|---|---|
| Attempted to change nested class/host | `NestHost`, `NestMembers` differ from original | Preserve nest metadata and private-access topology |
| Record class rejected | `Record` attribute/record components missing or altered; field/method added | Preserve record component table; only modify valid method code |
| Sealed type rejected | `PermittedSubclasses` added/removed/modified | Keep the list of direct permitted subclasses intact |
| Method instrumentation still fails even though the four attributes are unchanged | Changed method descriptor, modifiers, fields, superclass/interfaces; invalid StackMapTable/bytecode | Check all JVMTI schema restrictions, verifier, and byte source |
| Codegen rewrites class file and drops unfamiliar attributes | Visitor/library fails to copy attributes during round-trip | Use a bytecode library version that understands the class-file version; test preserving class-level metadata |
| No callback received on `retransformClasses` | Transformer registered with `canRetransform=false` or capability unsupported | Manifest `Can-Retransform-Classes: true`, check `isRetransformClassesSupported`, `isModifiableClass` |
| Callback invoked but class does not change | Transformer returns `null` or errors on the resulting class file | Log transform decisions/exceptions and distinguish load vs retransform |
| Want to add a field to store tracing data | Retransformation does not allow changing field schema | Store probe state in agent/helper, avoid adding fields to target |

**Do not naively compare raw byte arrays.** The Javadoc allows the retransform input to differ from the original bytes in constant-pool ordering/contents and the presence of certain unimportant attributes; method ordering may also differ. When determining “Was NestHost changed?”, you must **parse the class file and compare semantic contents** (host class name, member names, component names/descriptors, and permitted names) rather than comparing raw offsets/CP indices.

**Watch out for masked errors:** `ClassFileTransformer.transform` can throw an exception and the JVM will still invoke subsequent transformers. Moreover, one transformer returning `null` does not prove other transformers did not alter the bytes. Rejections are typically detected at the **final class definition installation step**, i.e., after the entire transformer chain. Logs from a single callback are not enough to confirm the final result is valid.

### `isModifiableClass` Is Not Permission to Change Everything

Safe check order before invoking:

~~~java
if (!instrumentation.isRetransformClassesSupported()) {
    // Choose a fallback or report unsupported capability.
} else if (!instrumentation.isModifiableClass(target)) {
    // Do not call retransform on an unmodifiable class.
} else {
    // Must still ensure produced bytes do not change prohibited schema/attributes.
    instrumentation.retransformClasses(target);
}
~~~

This is an **illustrative snippet inside an agent**, not a standalone Java program. `isModifiableClass == true` does not mean you can change `PermittedSubclasses` or `NestHost`; it only rules out one category of failure.

## 8. Real-World Scenarios When Using Instrumentation Libraries

**Scenario A — “I only added logging to a record accessor.”** If a transformer injects code into the body of `Point.x()` while the bytecode visitor simultaneously drops the `Record` attribute, the JVM can reject the retransformation. This is not evidence that records cannot be instrumented; the failure comes from **failing to preserve metadata**.

**Scenario B — “Adding a nested helper to a loaded class.”** A framework generates an auxiliary class or alters the nest members list of an existing class after load time: this can touch `NestMembers` and be rejected. If a helper is needed, generate it in the appropriate classloader/package rather than rewriting the nest topology of an existing class. Opening module access via `redefineModule` (if needed and permitted) is also a **separate** concept from modifying nest metadata.

**Scenario C — “Allowing a new plugin subtype of a sealed interface.”** You cannot add an entry to `PermittedSubclasses` of a loaded sealed interface via retransformation. If the architecture requires runtime extensibility, design a different extension point (composition, service provider, or a `non-sealed` interface permitted from the start), or deploy a new class version in an appropriate runtime/classloader on restart.

**Scenario D — “The class runs fine on initial load, but fails on subsequent retransform.”** On initial load, a transformer might establish a valid class file with one structure; on retransform, the pipeline inadvertently produces different output for nest/record/permits. In this case, compare **the definition already accepted by the JVM** against the retransform output, not just source files on disk.

## 9. Self-Check Questions

1. **If a class has `NestMembers`, is it completely barred from retransformation?** No. Valid method-body changes are allowed, as long as `NestMembers` is not altered.
2. **Are `NestHost` and `NestMembers` the same as `InnerClasses`?** No; the first two govern nestmate access relationships, while `InnerClasses` describes nested-class metadata.
3. **Can a timing probe be inserted into a record accessor?** Yes, if the bytecode is valid and field/method schema, `Record` metadata, and other constraints are preserved.
4. **What about adding a record component via retransformation?** Not allowed; it violates the `Record` attribute and usually the field/method schema as well.
5. **Can the list of permitted direct subclasses be changed after a sealed class is loaded?** No, not under current JVM TI retransformation/redefinition rules.
6. **If retransformation only calls `transform` and returns `null` for a sealed class, can it succeed?** Yes; the example runs successfully on HotSpot/OpenJDK.
7. **Does `isModifiableClass(type) == true` allow modifying the four attributes?** No. Capability and class modifiability do not lift class-attribute restrictions.
8. **If one class in a batch retransformation fails, have the remaining classes received their new bytes?** Per JVMTI, if a batch returns an error, no class in the batch receives a new definition.
9. **Can `PermittedSubclasses` be modified using `redefineClasses` instead of retransformation?** No, JVM TI rules for redefinition also prohibit changing it.
10. **Why might a patch that appears to change only a method body still be rejected?** A rewriting tool may inadvertently drop metadata, or another transformer in the chain may modify the class file.
11. **Why shouldn't raw numeric CP indices be used to compare two class-file versions?** Because constant-pool layout can change between passes; resolved attribute contents must be compared instead.
12. **Does the failing `PermittedSubclasses` entry-replacement test prove Java does not support sealed types in agents?** No. It only proves that **changing sealed metadata already installed by the JVM** is invalid.

## 10. Safe Transformer Design Checklist

- [ ] Verify JVM/capabilities properly: `Can-Retransform-Classes`, `isRetransformClassesSupported()`, and `isModifiableClass()`.
- [ ] Transform code only inside existing methods, preserving schema, modifiers, and inheritance.
- [ ] Preserve the semantic `NestHost`/`NestMembers`, `Record`, and `PermittedSubclasses` of already-defined classes.
- [ ] Do not drop class-file attributes when parsing/rewriting with ASM, Byte Buddy, or other codegen tools.
- [ ] Test with **nested classes**, **records**, and **sealed classes**, not just simple POJO classes.
- [ ] In `ClassFileTransformer`, filter accurately on internal class name and `classBeingRedefined`; avoid recursive loading or heavy I/O in the callback.
- [ ] Do not equate `isModifiableClass` with “allowed to add fields/methods/nest members.”
- [ ] On failure, record the API exception, class identity/loader, capabilities, and the outcome of the entire transformer chain.
- [ ] Acknowledge that methods currently executing on the stack may continue using the old bytecode version, while new invocations use the newly installed method version.
- [ ] Do not expect retransformation to re-run static initializers, recreate instances, or change existing field values.

## References

- [JVM TI 21 — Retransform Classes](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html#RetransformClasses): specification directly stating that `NestHost`, `NestMembers`, `Record`, or `PermittedSubclasses` must not be changed, along with redefinition errors.
- [JVM TI 21 — Redefine Classes](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html#RedefineClasses): corresponding restrictions for redefinition.
- [Java SE 21 — Instrumentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): capabilities, `retransformClasses`, `UnmodifiableClassException`, `UnsupportedOperationException`.
- [JVMS 21 — §4.7.28 NestHost, §4.7.29 NestMembers](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.7.28): format and obligations of the two nest attributes.
- [JVMS 21 — §4.7.30 Record](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.7.30): format of record components metadata.
- [JVMS 21 — §4.7.31 PermittedSubclasses](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.7.31): list of direct permitted subclasses of a sealed class/interface.
- [JVMS 21 — §5.4.4 Access Control](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.4.4): nestmate access and checking nest host/host membership.
