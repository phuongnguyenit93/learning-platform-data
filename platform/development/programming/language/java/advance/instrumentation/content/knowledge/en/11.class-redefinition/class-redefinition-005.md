# Unsupported Structural Changes Under the Current JVM Contract

> **Key Takeaway:** For a **class already defined by the JVM**, `Instrumentation.redefineClasses(...)` can update **method bodies**, the constant pool, and permitted class-file attributes; however, it is **not a mechanism for arbitrarily changing a class's structure**. Under the standard Java Instrumentation/JVM TI contract, redefinition cannot be used to add, remove, or rename fields/methods; change a method descriptor; change the class hierarchy; change modifiers; or alter structural attributes specified as immutable such as `NestHost`, `NestMembers`, `Record`, and `PermittedSubclasses`. If a request violates these rules, the JVM rejects it and **does not install the new definition**.

This lesson belongs to the **Redefinition** topic in Java Advance – instrumentation. The goal is not merely to memorize "HotSwap only edits method bodies," but to understand why a small-looking source code change can alter the class-file schema, how to recognize each type of rejection, and how to design agents/update paths that do not violate the JVM contract.

## 1. Distinguishing Behavioral Changes from Structural Changes

Once a class is defined, it is not just a sequence of bytecodes for a method. It has an **identity and structure** that the JVM, verifier, runtime, reflection, and other classes may already depend on:

- Class identity is tied to **binary name + defining class loader**, along with the appropriate module/package relationship.
- Inheritance relationships: the direct superclass and the list of directly implemented interfaces.
- **Field** list: name, JVM type descriptor, modifiers, and related layout/metadata.
- **Method/constructor** list: name, descriptor, modifiers; a class may also contain compiler-generated methods.
- Class attributes with structural significance: nestmate, record, sealed subclasses, and other attributes governed by JVM TI rules.
- The **Code** attribute of methods, the constant pool, and metadata not prohibited from changing.

Consider two cases:

~~~java
// Version A — abridged example, not a standalone runnable file.
public class Invoice {
    private int amount;

    public int total() {
        return amount;
    }
}
~~~

~~~java
// Version B — same field/method descriptors, only Code changed.
public class Invoice {
    private int amount;

    public int total() {
        return Math.max(0, amount);
    }
}
~~~

Version B **can be a valid redefinition candidate** if the JVM supports it, the class is modifiable, and the new bytecode is compatible. Simply keeping method names is not enough: the same schema and other checks are still required.

By contrast:

~~~java
// Version C — adding a field to an already-loaded class: different schema.
public class Invoice {
    private int amount;
    private int discount; // added field

    public int total() {
        return amount - discount;
    }
}
~~~

Version C is **not** a method-body-only change. It requires the already-loaded class to have a new field, affecting structure and layout. When using standard `redefineClasses` to replace A with C on a current JVM, the request is rejected due to the schema change.

**Do not confuse the two points in time:** When a class is **defined for the first time**, a `ClassFileTransformer` can produce a classfile with additional fields/methods as long as that classfile is valid and satisfies runtime conditions. However, once a class is **already defined**, `redefineClasses` or `retransformClasses` must adhere to the limits on modifying an existing definition. The ability to transform at **first load** does not grant permission to change the schema during **live redefinition**.

## 2. Table of Unsupported Structural Changes

Compare **two classfiles** of the same class, not just two `.java` files:

| Category | Example Change | Reason Restricted During Redefinition |
| --- | --- | --- |
| **Add field** | `private long count;` appears after the class has loaded | Changes the field list and object/class schema |
| **Remove field** | New version no longer has `private int amount;` | Removes a field already defined by the JVM |
| **Rename field** | `amount` → `quantity` | At the classfile level, removes the old field and adds a newly named field |
| **Change field type** | `int amount` → `long amount` | JVM descriptor changes from `I` to `J`; changes schema |
| **Change field modifiers** | `private` → `public`, `static` ↔ instance, different `final` | Modifiers no longer match the original field structure |
| **Add method/constructor** | Adding `calculateTax()` or a constructor overload | JVM method list changes |
| **Remove method/constructor** | Removing `total()` or an `<init>` | The JVM has an existing method identity that must be preserved |
| **Rename method** | `total()` → `sum()` | Old method is removed, new method is added |
| **Change signature/descriptor** | `total()I` → `total(J)I` or `total()J` | JVM method descriptor changes (including parameters and return type) |
| **Change method modifiers** | Instance → `static`, public → private, adding/removing `synchronized`/`native` | Changing method modifiers is not supported |
| **Change class modifiers** | Running class becomes `final` or changes accessibility | Class modifiers differ from the currently defined version |
| **Change superclass** | `extends BaseA` → `extends BaseB` | Changes inheritance and method/field resolution relationships |
| **Change direct interfaces** | Adding/removing `implements Marker` | Changes the JVM class hierarchy contract |
| **Change nestmate attributes** | `NestHost` or `NestMembers` differs from before | Changes the already-defined nestmate relationship |
| **Change `Record` attribute** | Changing record components of an already-loaded class | The structural `Record` attribute must remain consistent |
| **Change `PermittedSubclasses`** | Adding/removing a permitted subclass for a sealed class | The sealed hierarchy contract changes |

In the current JDK, both JVM TI **RedefineClasses** and **RetransformClasses** explicitly state these prohibited categories. The list may change in a **future JVM version**, so "current" must always be tied to the target API/VM. Do not assume every product advertising "enhanced hotswap" shares the same standard Java Instrumentation contract.

### Reading descriptors instead of looking only at source names

From a Java source perspective, the following two declarations look like only a parameter changed:

~~~java
public int total() { return 0; }
public int total(long customerId) { return 0; }
~~~

However, the classfile has two different method descriptors:

~~~text
total()I       // no parameters, returns int
total(J)I      // takes long, returns int
~~~

When **replacing** the old method with the new method, the JVM observes one method removed and a different method added. Also remember that the **return type is part of the JVM method descriptor**, even though Java language signatures do not distinguish overloads by return type alone. Therefore, changing `int total()` to `long total()` is still a descriptor change and is invalid for redefining an already-loaded class.

### Source looks unchanged in form, yet the compiler may emit a different schema

The compiler can generate methods/fields that the author did not directly declare:

- A lambda expression may be compiled into a synthetic helper method named like `lambda$...`; changing the expression structure can add/remove/move methods in the classfile.
- A generic override can generate a **bridge method** to preserve polymorphism under erasure.
- A change to inner classes, records, enums, synthetic access, or desugaring can alter the method/field list or class attributes.
- Kotlin, Scala, Lombok, or code generation tools can also emit members that are not obvious from a short diff.

Therefore, code review of a live class patch should **compare the actual classfiles** using `javap -p -s` or a bytecode analysis library; never conclude that "only one Java line was edited" means "only the Code attribute was edited."

## 3. What *Can* Usually Change

The JVM TI contract allows changing **method bodies**, the **constant pool**, and **certain non-prohibited attributes**, provided that the final bytes after the transformer chain form a valid classfile and do not alter protected schema elements.

| Change | Can Be a Valid Redefinition? | Important Conditions |
| --- | --- | --- |
| Changing the algorithm in an **existing method body** | Usually **yes** | Keep name/descriptor/modifiers, accepted by the verifier, dependencies can link |
| Changing a string constant used by a method | Usually **yes** | Valid constant pool/classfile, does not break schema |
| Changing exception handling in Code | Usually **yes** | Valid bytecode, stack-map frames, and exception handlers |
| Adding a call to a **helper method in another class** inside an existing body | Potentially **yes** | Helper is loadable, visibility/module access is valid, no new method added to the target class |
| Changing metadata not prohibited by JVM TI | **Depends** on the attribute and JVM | Do not assume every annotation/attribute is automatically allowed |
| Adding a field to the target class | **No** under this contract | Requires another mechanism or deploying a new version when the class is defined |
| Adding a method to the target class | **No** | Cannot "hide" this using `ClassDefinition` |
| Changing `extends`/`implements` | **No** | Hierarchy relationships must be preserved |
| Changing `Record`/`PermittedSubclasses`/nestmate attributes | **No** | These class attributes are prohibited from changing |

**Structurally valid example** (illustrative code):

~~~java
// Before: this method already exists in the running class.
public int calculate(int a, int b) {
    return a + b;
}

// After: still calculate(II)I, but with a different method body.
public int calculate(int a, int b) {
    return Math.addExact(a, b);
}
~~~

Changing the implementation as above **does not automatically guarantee** the request will succeed: if the bytes have the wrong version, the method body lacks valid stack-map frames, the module cannot read the new helper, or another transformer modifies the structure, the JVM will still reject it or throw a linkage error.

**Limitation on transforming `<clinit>`:** If you change the body of the class initializer, redefinition **does not re-run the class initializer**. Keeping the name/descriptor of `<clinit>` does not mean you get an opportunity to re-initialize static state on a running JVM.

## 4. Checking Preconditions Before Calling `redefineClasses`

Primary Java API:

~~~java
boolean supported = inst.isRedefineClassesSupported();
boolean modifiable = inst.isModifiableClass(Target.class);

if (!supported || !modifiable) {
    throw new IllegalStateException("Cannot redefine this class here");
}

byte[] bytes = /* valid classfile for the same target class */;
inst.redefineClasses(new ClassDefinition(Target.class, bytes));
~~~

This is an **illustrative code snippet**, not a standalone Java file because `Instrumentation inst`, `Target`, and `bytes` are not defined here. A complete example follows in the next section.

### Manifest configuration and JVM capability

A startup agent using `-javaagent` must declare:

~~~text
Manifest-Version: 1.0
Premain-Class: RedefineAgent
Can-Redefine-Classes: true
~~~

`Can-Redefine-Classes: true` is a capability request. `isRedefineClassesSupported()` also depends on the JVM; it does **not** become true solely from the manifest. Setting it to `true` does not enable **structural changes** — it only permits calling redefine within the limits supported by the JVM.

**Two independent checks:**

- `isRedefineClassesSupported()`: whether the VM configuration supports class redefinition.
- `isModifiableClass(clazz)`: whether the specific class is permitted to have its definition modified.

Both can return `true` and **the new classfile can still be rejected due to structural changes**. This is the most important point when debugging an `UnsupportedOperationException` after preflight checks have passed.

### Distinguishing from `retransformClasses`

`redefineClasses` accepts a `ClassDefinition(targetClass, byte[])` supplied by the caller; `retransformClasses` takes the underlying bytes and re-runs the transformer chain according to the `canRetransform` capability rules. How the bytes are obtained differs, but **the restrictions against adding/removing methods/fields or changing the hierarchy in an already-loaded class still apply**.

Do not switch `redefineClasses` to `retransformClasses` just because you see a "method added" error: if the resulting bytecode still adds a method/field, switching APIs does not make the structural delta permissible.

## 5. Java 17+ Experiment: Method Body Accepted, Adding a Field Rejected

The following example is **a complete program** with a redefine-capable startup agent. It verifies three things:

1. Replacing the body of `Target.status()` from `"ORIGINAL"` to `"UPDATED"` **succeeds**, while the same `Target` instance still retains its field `amount=7`.
2. Attempting to **add a field** to the already-loaded `Target` class is rejected with `UnsupportedOperationException` on the tested OpenJDK/HotSpot.
3. When redefining **two classes in a single batch**, if one definition is structurally invalid, the JVM **does not apply a partial update**; the `Companion` class retains its old behavior even though its replacement bytes are valid.

Use **JDK 17+**, with no external bytecode libraries required. We compile different `.class` files from sources with the same class name, then pass their bytes to `ClassDefinition`; this is not instrumenting at initial load time.

### 5.1. Original file `Target.java`

~~~java
public class Target {
    private int amount = 7;
    public String status() { return "ORIGINAL"; }
    public int amount() { return amount; }
}
~~~

The class name, default constructor, field, and both methods form the original schema. The version at the classpath root will be loaded by the JVM before redefine is called.

### 5.2. Original file `Companion.java`

~~~java
public class Companion {
    public String status() { return "COMPANION_ORIGINAL"; }
}
~~~

This is the second class used to verify **atomic all-or-none** behavior when a redefine call contains multiple `ClassDefinition`s.

### 5.3. Replacement changing only the method body — `variants/body/Target.java`

~~~java
public class Target {
    private int amount = 7;
    public String status() { return "UPDATED"; }
    public int amount() { return amount; }
}
~~~

The schema matches the original; only the string returned by the method changes. This is a change that standard redefinition can accept.

### 5.4. Replacement intentionally adding a field — `variants/addField/Target.java`

~~~java
public class Target {
    private int amount = 7;
    private int extra = 99;
    public String status() { return "STRUCTURAL"; }
    public int amount() { return amount; }
}
~~~

This file **compiles normally in Java**, but its bytes are not valid **for redefining the existing `Target` class** because `extra` was added. Keep this distinction clear: **a successful `javac` build does not prove `redefineClasses` can install the new definition**.

### 5.5. Valid replacement for the other class — `variants/companionBody/Companion.java`

~~~java
public class Companion {
    public String status() { return "COMPANION_UPDATED"; }
}
~~~

This version only changes the body, but it will be submitted in the **same batch** as the `Target` version that adds a field, to demonstrate that the entire batch is rejected.

### 5.6. Agent `RedefineAgent.java`

~~~java
import java.lang.instrument.ClassDefinition;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;

public final class RedefineAgent {
    private static Instrumentation instrumentation;

    public static void premain(String args, Instrumentation inst) {
        instrumentation = inst;
        System.out.println("capability=" + inst.isRedefineClassesSupported());
    }

    public static boolean modifiable(Class<?> target) {
        return instrumentation.isModifiableClass(target);
    }

    public static void redefineBody() throws Exception {
        byte[] bytes = Files.readAllBytes(Path.of("variants/body/Target.class"));
        instrumentation.redefineClasses(new ClassDefinition(Target.class, bytes));
        System.out.println("body=SUCCESS");
    }

    public static void tryAddingField() throws Exception {
        byte[] bytes = Files.readAllBytes(Path.of("variants/addField/Target.class"));
        try {
            instrumentation.redefineClasses(new ClassDefinition(Target.class, bytes));
            System.out.println("addField=UNEXPECTED_SUCCESS");
        } catch (UnsupportedOperationException expected) {
            System.out.println("addField=UnsupportedOperationException");
        }
    }

    public static void tryBatch() throws Exception {
        byte[] invalid = Files.readAllBytes(Path.of("variants/addField/Target.class"));
        byte[] valid = Files.readAllBytes(Path.of("variants/companionBody/Companion.class"));
        try {
            instrumentation.redefineClasses(
                new ClassDefinition(Target.class, invalid),
                new ClassDefinition(Companion.class, valid));
            System.out.println("batch=UNEXPECTED_SUCCESS");
        } catch (UnsupportedOperationException expected) {
            System.out.println("batch=UnsupportedOperationException");
        }
    }
}
~~~

**How to read the agent:**

- `Instrumentation` is supplied by the JVM via `premain`.
- `ClassDefinition(Target.class, bytes)` pairs **an already-loaded class object** with the proposed class-file bytes to install.
- `redefineBody()` performs a valid method-body change.
- `tryAddingField()` catches **only** the `UnsupportedOperationException` expected by this test. In a real application, you must distinguish other exceptions (missing file, corrupt classfile, unsupported VM, non-modifiable target) and have a concrete handling policy.
- `tryBatch()` submits two definitions together. If any definition is invalid, the JVM installs neither class.
- After a failed redefinition, log output printed by the agent or the fact that a transformer received a callback **does not mean** the new classfile was installed.

The agent class does not need `Target.class` or `Companion.class` inside the agent JAR; they reside on the application classpath. `Can-Redefine-Classes: true` belongs to the agent JAR's manifest, not to `Target.class`.

### 5.7. Application `Demo.java`

~~~java
public final class Demo {
    public static void main(String[] args) throws Exception {
        Target target = new Target();
        Companion companion = new Companion();
        if (!RedefineAgent.modifiable(Target.class)) {
            throw new IllegalStateException("Target is not modifiable");
        }
        System.out.println("modifiable=true");
        System.out.println("before=" + target.status() + "/" + target.amount());

        RedefineAgent.redefineBody();
        System.out.println("after-body=" + target.status() + "/" + target.amount());

        RedefineAgent.tryAddingField();
        System.out.println("after-reject=" + target.status() + "/" + target.amount());

        System.out.println("companion-before=" + companion.status());
        RedefineAgent.tryBatch();
        System.out.println("companion-after=" + companion.status());
    }
}
~~~

In the demo, `Target` and `Companion` are instantiated **before** the redefine requests. The object names and references do not change; it is the **method body used by the JVM on new invocations** that can change.

### 5.8. Manifest `agent.mf`

~~~text
Manifest-Version: 1.0
Premain-Class: RedefineAgent
Can-Redefine-Classes: true
~~~

Save the manifest with a trailing newline. The lesson uses a `-javaagent` startup agent, so `Premain-Class` is required. `Can-Retransform-Classes` is not needed, because every call in the example uses **`redefineClasses`**, not `retransformClasses`.

### 5.9. Directory structure and commands to run

Create the directory layout as follows:

~~~text
demo/
  Target.java
  Companion.java
  RedefineAgent.java
  Demo.java
  agent.mf
  variants/
    body/
      Target.java
    addField/
      Target.java
    companionBody/
      Companion.java
~~~

From the **`demo` directory**, run with JDK 17+:

~~~bash
javac --release 17 Target.java Companion.java RedefineAgent.java Demo.java

javac --release 17 -d variants/body variants/body/Target.java

javac --release 17 -d variants/addField variants/addField/Target.java

javac --release 17 -d variants/companionBody variants/companionBody/Companion.java

jar --create --file redefine-agent.jar --manifest agent.mf RedefineAgent.class

java -javaagent:redefine-agent.jar Demo
~~~

The `-d` flag compiles each variant into its **own separate directory**. The Java app only sees the original `Target.class` and `Companion.class` in the working directory; the agent explicitly reads the replacement files from `variants/...`. Do not copy a variant `Target.class` into the root before the app starts, or the exercise will no longer simulate **redefinition of an already-running class**.

**Stdout on OpenJDK 24 with sources compiled using `javac --release 17`:**

~~~text
capability=true
modifiable=true
before=ORIGINAL/7
body=SUCCESS
after-body=UPDATED/7
addField=UnsupportedOperationException
after-reject=UPDATED/7
companion-before=COMPANION_ORIGINAL
batch=UnsupportedOperationException
companion-after=COMPANION_ORIGINAL
~~~

Every line is meaningful:

- `capability=true`: the manifest and JVM permit redefinition. This is **not** permission to change the schema.
- `modifiable=true`: `Target` can in principle have its definition modified; it does **not** mean every replacement classfile is valid.
- `body=SUCCESS` and `after-body=UPDATED/7`: the method body change succeeded; the existing instance's `amount=7` state is preserved.
- `addField=UnsupportedOperationException`: adding `extra` is rejected by the JVM even though the Java source compiled successfully.
- `after-reject=UPDATED/7`: the class remains at its **most recently installed valid definition**; the `STRUCTURAL` version was not applied.
- `batch=UnsupportedOperationException`: the batch contains an invalid definition that adds a field.
- `companion-after=COMPANION_ORIGINAL`: even `Companion`, whose new bytes only edit a method body, is **not replaced** because the batch failed.

This is empirically verified behavior, not a simulation that hardcodes printed output for each branch. **Do not assume the exact same exception name for every error case across all JVMs**: a classfile with the wrong name can cause `NoClassDefFoundError`, malformed bytes can cause `ClassFormatError`, and an unmodifiable class can cause `UnmodifiableClassException`.

## 6. Other Failure Variants: Before–After Explanation at the Classfile Level

In an extended experiment on OpenJDK 24, starting from this initial class:

~~~java
public class DemoService {
    private int seed = 7;
    public String message() { return "ORIGINAL"; }
    public int value() { return seed; }
}
~~~

Separate replacement versions can be compiled, and each version's bytes passed to `redefineClasses(new ClassDefinition(DemoService.class, bytes))`. **The table below describes observed experimental results**, not a list of extra Java files you must create to run the Section 5 demo.

| New Version Tested | Classfile Delta | Result on OpenJDK 24 |
| --- | --- | --- |
| Only edit `message()` body to `"UPDATED"` | Different Code/constant pool | `SUCCESS` |
| Add `private int extra` | Added field | `UnsupportedOperationException` |
| Remove `seed` and change `value()` body to return a constant | Removed field | `UnsupportedOperationException` |
| Add `extraMethod()` | Added method | `UnsupportedOperationException` |
| Remove `value()` | Removed method | `UnsupportedOperationException` |
| Change `message()` to `message(int)` | Changed method descriptor | `UnsupportedOperationException` |
| Add `extends Parent` | Changed direct superclass | `UnsupportedOperationException` |
| Add `implements Marker` | Changed direct interface set | `UnsupportedOperationException` |
| Change field `seed` from `private` to `public` | Changed field modifier | `UnsupportedOperationException` |
| Change `message()` from instance to `static` | Changed method modifier | `UnsupportedOperationException` |
| Change class to `final class DemoService` | Changed class modifier | `UnsupportedOperationException` |

Special case: if a `ClassDefinition` targets `DemoService.class` but the actual bytecode declares **a class named `WrongName`**, the JVM throws `NoClassDefFoundError` in the experiment. This is a **class name mismatch** error, not an `UnsupportedOperationException` about a schema delta.

**Why test after a successful body change?** It illustrates that when a subsequent redefinition attempt fails, the JVM retains the definition in effect at that moment. "Remaining unchanged" does not necessarily mean reverting to the original startup version; it means keeping **the most recently installed valid version**.

## 7. Indirect Structural Changes That Are Easy to Miss

### 7.1. Constructors and compiler-generated methods

Changing a constructor from:

~~~java
public Order() {
    this.count = 0;
}
~~~

to:

~~~java
public Order(int start) {
    this.count = start;
}
~~~

changes the descriptor from `<init>()V` to `<init>(I)V`, which is **not just a Code edit**. Once the class is loaded, removing the old constructor and adding a new one is prohibited. You can modify **the body of an existing constructor** while keeping its descriptor unchanged, but redefinition **does not re-invoke the constructor** on already-created objects.

Similarly, changing generics or a method override can cause the compiler to add or remove a **bridge method**. In that case, the source diff may not mention a bridge, yet the classfile contains a different method set.

### 7.2. Lambdas and synthetic methods

A Java change like:

~~~java
// Illustrative snippet inside an existing method:
Runnable r = () -> System.out.println("audit");
~~~

can generate a synthetic method named `lambda$...` in the same class and bootstrap linkage via `invokedynamic`. Adding a new lambda is **not always** just a Code change to the original method. If the method/descriptor list or bootstrap/linkage is altered in a disallowed way, the JVM may reject the redefinition.

**How to check:** compile both the original and new versions into separate directories, and use `javap -p -s -c` to inspect private/synthetic members and method descriptors. Do not guess from nicely formatted source code.

### 7.3. Records, sealed classes, and nestmates

Examples of intended structural changes:

~~~java
record InvoiceLine(long amount) {}
// Changed to record InvoiceLine(long amount, String currency) {}
~~~

This is an **illustrative snippet**, not two classes that can be declared side by side in the same file to run. Record components tie into fields, accessors, constructors, and the `Record` attribute. Redefining an already-loaded record in a way that alters its components violates multiple restrictions, including the `Record` attribute.

~~~java
sealed interface PaymentResult permits Success, Failure {}
// Wants to add Pending to the permits list after the interface has been defined.
~~~

Adding `Pending` to the `PermittedSubclasses` attribute of an already-loaded interface/class is not supported. A newly compiled `Pending` class on its own **does not** alter the permitted hierarchy already defined by the JVM.

Nestmate attributes `NestHost` and `NestMembers` also cannot be changed. If a bytecode rewriting tool arbitrarily adds/removes nest members to access private members, that is no longer a harmless body change.

**Key point:** These restrictions are based on **classfile attributes** and JVM TI, not just the Java language keywords `record`, `sealed`, or `private`. Depending on the JDK, compiler, and bytecode library, there may be other attributes to verify when producing the final classfile.

### 7.4. Enums and synthetic fields

Adding an enum constant after the enum class has been defined typically entails adding a static field, changing metadata, and changing initialization logic/internal value arrays. A new enum constant should not be treated as "just adding a string." Because redefinition neither allows adding fields nor re-runs initialization, this kind of enum hot-patching is unsuitable for the standard mechanism.

## 8. Why Doesn't the JVM Automatically Adjust Running Class Structures?

Imagine an application with:

~~~text
Objects a, b, c already created under Account version A's schema
     |
     +-- other bytecode already resolved to Account.balance:I
     +-- reflection/caches may hold member metadata
     +-- threads have stack frames currently executing the old method
     +-- JIT may have optimized based on layout and method assumptions
~~~

If redefinition could arbitrarily add `long creditLimit`, change `balance:I` to `balance:J`, or change the superclass, the JVM would have to restructure the state of live objects, handle already-linked references, inheritance resolution, and runtime frames/metadata. The standard Java Instrumentation contract **does not provide such a general-purpose object/schema migration facility**.

This is an explanation of the design rationale, **not** a claim that a JVM is technically incapable of ever supporting enhanced class redefinition. Some runtimes, custom VMs, or developer tools have proprietary capabilities beyond the standard API; portable production code must not assume they are present.

### What happens to objects and threads when a body redefinition succeeds?

- **Instances remain the same objects**; no constructor is re-run merely because of redefinition. Existing fields keep their current values.
- **Static fields keep their values**; the class initializer `<clinit>` does not automatically re-run.
- **Active stack frames** of the redefined method may continue executing the old bytecode version; **new invocations** of the method will use the new definition.
- Changing code logic **does not automatically undo** side effects, I/O, transactions, or business state that have already occurred.
- There is no guarantee that all threads immediately observe the same version at an application-chosen point if they are in different frames.

The Section 5 example shows `target.amount()` still returning `7` after the `status()` body changes. However, changing code for subsequent calls does not rewrite `Target.amount` data across all instances via a migration algorithm.

## 9. Distinguishing Structural Errors from Other `redefineClasses` Errors

Not every exception means "the structure changed."

| Exception / Symptom | Issue Category | How to Investigate |
| --- | --- | --- |
| `UnsupportedOperationException` | JVM lacks the capability **or** the classfile delta requests a disallowed change | Check `isRedefineClassesSupported()`, diff the schema, modifiers, and prohibited attributes |
| `UnmodifiableClassException` | Target class does not allow definition changes | Call `isModifiableClass(clazz)` first and verify the exact class/loader |
| `NoClassDefFoundError` | Binary name in the new classfile does not match the target class | Use `javap -verbose`, check that the `.class` file read is actually the right class |
| `ClassFormatError` | Bytes do not conform to the classfile format | Inspect the byte-generation tool, constant pool, stack-map frames, and file I/O |
| `UnsupportedClassVersionError` | New class-file version is not supported by the running JVM | Compile with `--release` matching the runtime JDK |
| `ClassCircularityError` | Class definition introduces an invalid inheritance cycle | Inspect superclass/interfaces after transformation |
| Other `LinkageError` | Linkage failure while applying/resolving the class | Check loader, class visibility, module access, and helper classes |
| `ClassNotFoundException` in API signature | Declared for historical compatibility; per Javadoc, not thrown by this operation itself | Check root cause and the actual API being called if the app has a custom wrapper |
| No exception, but method behaves the same | Bytes may actually be identical to the old ones, transformer returned `null`, or expected method wasn't instrumented | Check input classfile, transformer list, and post-operation behavior |

**Note:** `UnsupportedOperationException` does not categorize the specific delta type in the Java API. Native JVM TI has more specific error codes such as `JVMTI_ERROR_UNSUPPORTED_REDEFINITION_SCHEMA_CHANGED`, `..._METHOD_ADDED`, `..._METHOD_DELETED`, `..._HIERARCHY_CHANGED`, `..._CLASS_MODIFIERS_CHANGED`, and `..._METHOD_MODIFIERS_CHANGED`. A Java agent should only infer the error category from the exception and a **classfile diff**, without guessing an exact internal JVM TI code without evidence.

### Inspecting the classfile before submitting it to the JVM

Useful inspection commands:

~~~bash
javap -p -s -classpath . Target
javap -p -s -classpath variants/body Target
javap -p -s -classpath variants/addField Target

javap -verbose -classpath . Target
javap -verbose -classpath variants/addField Target
~~~

- `-p` shows private members as well, avoiding missed fields/methods on the class.
- `-s` prints JVM descriptors, making changes like `()I` → `(J)I` visible.
- `-verbose` displays classfile version, access flags, constant pool, and attributes; use with selective diffing to understand the cause.
- **Member ordering in output is not the sole criterion**: a bytecode tool may reorder metadata while preserving the schema. Compare by *name, descriptor, modifiers, hierarchy, and prohibited attributes*.

For classes loaded by special loaders, **the file on disk does not necessarily match the running classfile**. Load-time transforms, shading, patches/modules, different versions, or prior redefinitions may have modified it. For production diagnostics, capture the exact bytes used/passed into callbacks via a reliable observability workflow, then verify on a real JVM.

## 10. Multiple Classes in One Request: Atomicity and Scope Limits

`Instrumentation.redefineClasses(ClassDefinition... definitions)` accepts **a set of classes** because two interdependent classes sometimes need to be updated simultaneously. Under the API/JVM TI contract, when the request fails and throws an exception, **no class in the set has its new definition installed**.

~~~text
Currently running:
  Target.status()    = UPDATED
  Companion.status() = COMPANION_ORIGINAL

Simultaneous redefine request:
  Target -> bytes with added "extra" field          (INVALID)
  Companion -> bytes changing only method body      (potentially valid)

Result:
  UnsupportedOperationException
  Target remains UPDATED
  Companion remains COMPANION_ORIGINAL
~~~

This is the **`batch`** case tested in the demo. However, "atomic with respect to installing definitions" **does not mean all agent side effects are rolled back**. If a `ClassFileTransformer` is invoked during processing and writes a file, emits telemetry, or mutates configuration before the JVM detects another class is invalid, those custom side effects are not automatically rolled back by the API.

Therefore, transformers should minimize side effects; pre-checking classfiles before submitting the request reduces the chance of a batch rejection, though **only the JVM makes the final decision** on whether the post-transformer bytes are installed.

In a safe hot-patching workflow:

1. Prepare **the exact bytes** and target `Class<?>` object for each class/loader.
2. Verify capability, modifiability, and structural diffs for **the entire set**.
3. Ensure the new bytecode can link against other running classes.
4. Submit small-scoped batches, avoiding mixing a schema change requiring deployment with a body-only hotfix.
5. Only report "installed" once `redefineClasses` returns successfully; verify behavior afterward.

## 11. If You Truly Need to Add Fields/Methods or Change Hierarchy, What Should You Do?

**Option 1 — Design the method body to call a new helper class.** If you only need to deploy additional logic, keep the target class's schema unchanged and replace the existing method body to call a `HelperClass` in an independent class that is validly loaded/defined. You must check class loaders, module readability, visibility, and dependencies. This approach does **not** make a new helper method a member of the target class.

~~~java
// Illustrative snippet of an existing method body after replacement:
public String status() {
    return AuditHelper.computeStatus(this);
}
~~~

The helper must exist and be linkable; this snippet is **not a standalone program**. If you need **a new per-instance field**, you can consider an external side table (such as a weak-key map) or redesigning state storage. In that case, you must handle garbage collection, identity, synchronization, and overhead; a side table should not be treated as equivalent to a Java field in every semantic respect.

**Option 2 — Add structure at first class definition.** With a startup `ClassFileTransformer`, an **unloaded** class can be transformed into a new classfile containing additional members, provided the bytes are valid. This is the difference between **load-time instrumentation** and **live redefinition**. You must ensure the agent runs early enough and that all target class loaders use compatible versions.

**Option 3 — Deploy a new class/service version.** You can create a new binary name, a new structure, or a new class loader; the JVM identifies a class by name + defining loader, so a class with the same name from a new loader is **a different class** and does not automatically replace existing objects/references of the old class. Migrating state, dependency injection, serialization, and resource lifecycles is a separate architectural task.

**Option 4 — Restart/redeploy.** For genuine schema changes, the predictable, portable approach is to deploy a new artifact and start a new JVM/service, combined with rolling/canary deployments, data migration, and procedural rollback.

**Option 5 — Custom runtime with "enhanced HotSwap".** Some JVMs/tooling offer extensions beyond the standard contract, but you should not rely on them if the application must run portably across JDK versions/vendors. To use them, explicitly verify the runtime, flags, compatibility, new classfile support, migration mechanics, and rollback scenarios. This is **not** a feature enabled by standard Java Instrumentation's `Can-Redefine-Classes: true`.

## 12. Redefinition Patch Review Checklist and Practice Questions

Before signing off on a redefinition in a running JVM:

- [ ] Have you identified the exact `Class<?>`, defining loader, and module, not just the source file name?
- [ ] Does the agent manifest have `Can-Redefine-Classes: true`, and does the JVM return `isRedefineClassesSupported()==true`?
- [ ] Does the specific class return `isModifiableClass(clazz)==true`?
- [ ] Does the new classfile have **the same binary name** and a compatible classfile version?
- [ ] No fields/methods/constructors added, removed, or renamed; no changes to field descriptors, method descriptors, or modifiers?
- [ ] No changes to superclass, direct interfaces, `NestHost`/`NestMembers`, `Record`, or `PermittedSubclasses`?
- [ ] Have you compared the **post-compile** member set including synthetic/bridge methods, not just the `.java` diff?
- [ ] Could other transformers modify the final bytes, and is validity checked after the chain?
- [ ] Have you tested a successful method-body-only update, a rejected schema update, and batch all-or-none behavior?
- [ ] Have you distinguished **changing code** from **migrating state** and accounted for active stack frames?
- [ ] Is there a rollback plan using valid bytes or redeployment if an issue occurs, not merely removing the transformer?
- [ ] Do you confirm the request actually installed the definition before reporting "hotfix succeeded"?

### Self-Check

**1.** `isRedefineClassesSupported() == true` and `isModifiableClass(Invoice.class) == true`. An agent adds `private long amount;` and calls redefine. Are the preconditions satisfied?

**Answer:** No. Those two checks verify capability and class eligibility; they **do not lift schema restrictions**. Adding a field is still unsupported.

**2.** A hotfix changes the body of method `parse(String)` but the new method takes a `CharSequence` parameter. Is this body-only?

**Answer:** No. `String` and `CharSequence` produce **different descriptors**, so this is replacing a method, not just changing Code.

**3.** A developer adds a lambda inside a method without changing the public API. Is redefinition guaranteed to succeed?

**Answer:** No. You must compare the actual classfiles, especially synthetic/bridge methods and compiler-generated attribute changes.

**4.** A batch updates valid class A and invalid class B. Could class A have had its new version installed?

**Answer:** Under the `redefineClasses` contract, **no**: if the operation fails, no class in the set gets the new definition installed. However, external side effects from callbacks/agents are not automatically rolled back.

**5.** A method body change succeeds. Do existing instances, static fields, and stack frames automatically reset?

**Answer:** No. Instance and static state remain intact; constructors/class initializers are not automatically re-run; active frames may continue executing the old body until they finish.

**6.** The JVM throws `NoClassDefFoundError` when redefining with `WrongName.class`. Is this the same "added field" error?

**Answer:** No. Here the binary name in the classfile does not match the target `Class<?>`. You must verify the class bytes and class name before analyzing schema deltas.

**One-sentence summary:** `redefineClasses` **replaces the implementation of an existing class within its fixed schema**; it is not an API for arbitrarily upgrading the object model, member list, or hierarchy of a running JVM.

### Official Documentation

- [Java SE 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): capabilities, `isModifiableClass`, `redefineClasses`, exceptions, handling of stack frames, static state, and batch semantics.
- [Java SE 17 — `ClassDefinition`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html): packaging the target `Class<?>` and class-file bytes for redefinition.
- [Java SE 17 — `java.lang.instrument` manifest](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): the `Can-Redefine-Classes` attribute.
- [JVM TI 25.0 — `RedefineClasses` and `RetransformClasses`](https://docs.oracle.com/en/java/javase/25/docs/specs/jvmti.html): schema restrictions, modifiers, inheritance, nestmate/record/sealed attributes, and atomicity.
