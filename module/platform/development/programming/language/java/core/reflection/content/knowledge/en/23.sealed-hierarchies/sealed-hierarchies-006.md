# Reading Metadata, Loading Classes, and Triggering Initialization

When Reflection returns a `Class<?>` object, that alone does not prove the class's `static` initializer has run. Conversely, an operation whose name sounds "read-only", such as reading a static field's value, can still trigger class initialization.

In a sealed hierarchy, `getPermittedSubclasses()` can also require obtaining the `Class` objects of the permitted types. Therefore, you must distinguish **observing metadata**, **loading or resolving types**, and **executing class initializers**.

This article uses Java 17 or later to observe these three things through a separate class loader, rather than guessing state from having seen a class name.

## 1. Concepts to Keep Separate

| Concept | What is happening | What not to infer |
| --- | --- | --- |
| Loading | Finding and creating a runtime representation of a class from a class definition | Not enough to conclude `static` code has run |
| Linking | Verifying, preparing, and resolving needed references | Do not equate with executing static initializer expressions |
| Class initialization | Executing static field initializers and `static` blocks per Java rules | Does not create a new object each time |
| Object instantiation | Creating an instance and running its constructor chain | Does not mean the class initializer runs again |

These are the phases distinguished in [the JLS on Java execution](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html). Reference resolution may be performed eagerly or lazily as permitted by the specification; do not infer the entire linking timeline from just a few lines of program logs.

The class initializer is commonly referred to by the special name `<clinit>` in bytecode. It differs from the instance-creating constructors obtained via `getConstructor()`.

## 2. Metadata Is Information; Using Members Is a Different Action

For an identified ordinary class:

| Operation | Primary meaning | Does it require running target class initialization? |
| --- | --- | --- |
| Taking a class literal such as `SomeType.class` | Obtaining the type descriptor object | Not solely because of the class literal |
| `Class.forName(name, false, loader)` | Finding and loading the type via the chosen loader | Does not request initialization of the named class |
| `Class.forName(name, true, loader)` | Finding the type and requesting initialization | Yes, if not yet initialized |
| `Class.forName(name)` with an ordinary class name | Overload that requests initialization | Yes |
| Looking up `Field`, `Method`, `Constructor` | Obtaining member metadata | Not yet reading a value, calling a method, or creating an instance |
| `Field.get(null)` on a static field | Reading the field value | May initialize the class declaring the field |
| `Method.invoke(null, ...)` on a static method | Executing the method | May initialize the class declaring the method |
| `Constructor.newInstance(...)` | Creating an object via constructor | Initializes the class first if not yet initialized before creating the object |

The rules for the `initialize` parameter and the single-argument overload are in the [`Class.forName` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#forName(java.lang.String,boolean,java.lang.ClassLoader)). The word "Reflection" does not dictate behavior; the specific operation does.

For example, `getField("VALUE")` asks which field exists; `field.get(null)` asks for that field's value. Two consecutive steps, yet with different consequences.

## 3. Experiment Separating the Loader and the Initializer

The example has a sealed class `Root` and three permitted subclasses. Lines starting with `INIT` are printed by static initialization code; `CTOR` lines are printed by object constructors.

The `TrackingLoader` loader records which `probe.*` classes it has successfully defined itself. It uses the platform class loader as its parent so the test classes are loaded via the custom loader instead of being picked up first by the application class loader.

Create five files with this structure:

```text
LifecycleDemo.java
probe/
  Root.java
  LeafA.java
  LeafB.java
  LeafC.java
```

### File `LifecycleDemo.java`

```java
import java.io.IOException;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.net.URL;
import java.net.URLClassLoader;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class LifecycleDemo {
    private static final class TrackingLoader extends URLClassLoader {
        private final Set<String> defined = new HashSet<>();

        TrackingLoader(URL location) {
            super(new URL[]{location}, ClassLoader.getPlatformClassLoader());
        }

        @Override
        protected Class<?> findClass(String name) throws ClassNotFoundException {
            Class<?> result = super.findClass(name);
            if (name.startsWith("probe.")) {
                defined.add(name);
            }
            return result;
        }

        List<String> definedNames() {
            return defined.stream().sorted().toList();
        }
    }

    private static Class<?> find(Class<?>[] types, String name) {
        return Arrays.stream(types)
                .filter(type -> type.getName().equals(name))
                .findFirst()
                .orElseThrow();
    }

    public static void main(String[] args)
            throws ReflectiveOperationException, IOException {
        URL location = LifecycleDemo.class.getProtectionDomain()
                .getCodeSource().getLocation();
        try (TrackingLoader loader = new TrackingLoader(location)) {
            System.out.println("1. Acquire Root Class without initialization");
            Class<?> root = Class.forName("probe.Root", false, loader);
            System.out.println("Root Class ready");

            System.out.println("2. Read metadata");
            System.out.println("Root sealed = " + root.isSealed());
            Class<?>[] permitted = root.getPermittedSubclasses();
            System.out.println("Permitted = " + Arrays.stream(permitted)
                    .map(Class::getName).sorted().toList());
            System.out.println("Defined after metadata = " + loader.definedNames());

            Field value = root.getField("VALUE");
            Class<?> leafB = find(permitted, "probe.LeafB");
            Class<?> leafC = find(permitted, "probe.LeafC");
            Method ping = leafB.getMethod("ping");
            Constructor<?> constructor = leafC.getConstructor();
            System.out.println("Member metadata ready");

            System.out.println("3. Read static field");
            System.out.println("VALUE = " + value.get(null));

            System.out.println("4. Initialize LeafA explicitly");
            Class.forName("probe.LeafA", true, loader);
            System.out.println("Repeat initialization request");
            Class.forName("probe.LeafA", true, loader);
            System.out.println("Repeat complete");

            System.out.println("5. Invoke static method");
            ping.invoke(null);

            System.out.println("6. Construct LeafC twice");
            constructor.newInstance();
            constructor.newInstance();
        }
    }
}
```

### File `probe/Root.java`

```java
package probe;

public sealed class Root permits LeafA, LeafB, LeafC {
    public static int VALUE = initialize();

    private static int initialize() {
        System.out.println("INIT Root");
        return 42;
    }

    public Root() {
        System.out.println("CTOR Root");
    }
}
```

### File `probe/LeafA.java`

```java
package probe;

public final class LeafA extends Root {
    static {
        System.out.println("INIT LeafA");
    }
}
```

### File `probe/LeafB.java`

```java
package probe;

public final class LeafB extends Root {
    static {
        System.out.println("INIT LeafB");
    }

    public static void ping() {
        System.out.println("CALL LeafB.ping");
    }
}
```

### File `probe/LeafC.java`

```java
package probe;

public final class LeafC extends Root {
    static {
        System.out.println("INIT LeafC");
    }

    public LeafC() {
        System.out.println("CTOR LeafC");
    }
}
```

### Compile and run

Create the `out` directory, then run the commands in the directory containing `LifecycleDemo.java`:

```bash
javac -encoding UTF-8 --release 17 -Xlint:all -Werror -d out LifecycleDemo.java probe/Root.java probe/LeafA.java probe/LeafB.java probe/LeafC.java
java -cp out LifecycleDemo
```

Output:

```text
1. Acquire Root Class without initialization
Root Class ready
2. Read metadata
Root sealed = true
Permitted = [probe.LeafA, probe.LeafB, probe.LeafC]
Defined after metadata = [probe.LeafA, probe.LeafB, probe.LeafC, probe.Root]
Member metadata ready
3. Read static field
INIT Root
VALUE = 42
4. Initialize LeafA explicitly
INIT LeafA
Repeat initialization request
Repeat complete
5. Invoke static method
INIT LeafB
CALL LeafB.ping
6. Construct LeafC twice
INIT LeafC
CTOR Root
CTOR LeafC
CTOR Root
CTOR LeafC
```

The class list is sorted before printing so it does not depend on `getPermittedSubclasses()`'s element order. The example observes the essential milestones without attempting to log every internal resolution step performed by the JVM.

## 4. Reading Each Milestone in the Output

### Milestone 1: having a `Class` without `INIT`

`Class.forName("probe.Root", false, loader)` returns the `Class` object for `Root`. The program prints `Root Class ready`, yet there is no `INIT Root`.

Thus, "already having a `Class` object" differs from "the class initializer has run". This is the foundation for tools that need to inspect structure before actively triggering class behavior.

`false` also does not mean the class name is guaranteed valid or that errors cannot happen. Finding, loading, and linking can still fail on their own, even without requesting the initializer to run.

### Milestone 2: reading sealed metadata can require additional classes

`getPermittedSubclasses()` returns the permitted types of `Root`. After this step, the loader has defined `Root`, `LeafA`, `LeafB`, and `LeafC`, yet none of their `INIT` lines appear in the output before milestone 3.

What is observed is that **the classes have been defined to serve metadata retrieval**, while their static initialization code has not yet executed.

The [`getPermittedSubclasses()` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getPermittedSubclasses()) describes attempting to obtain the `Class` of each entry using the current type's defining class loader. Therefore, do not view this call as merely copying a list of classes that were already loaded earlier.

Next, the program retrieves `Field`, `Method`, and `Constructor`. The line `Member metadata ready` still appears before any `INIT` line. No field value has been read, target method invoked, or test object constructed yet.

### Milestone 3: reading a static field value

Calling `value.get(null)` causes `Root` to initialize, so `INIT Root` appears before `VALUE = 42`.

`null` here is the unused receiver for a `static` field; it does not mean the field value is `null`.

The rule for initializing the field-declaring class when reading a static value via Reflection is stated in the [`Field.get` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Field.html#get(java.lang.Object)). The example uses an `int VALUE` field initialized via a method call so that observation is not confused with a compile-time constant.

### Milestone 4: explicit initialization request

`Class.forName("probe.LeafA", true, loader)` runs `LeafA`'s initialization. `Root` was already initialized successfully at milestone 3, so it does not run again.

Repeating the same request produces no extra `INIT LeafA` line. For that same class definition, successful initialization is not re-executed every time the program requests to use it.

### Milestone 5: invoking a static method

Looking up `Method ping` earlier did not run `ping`'s body. Upon `ping.invoke(null)`, the program initializes `LeafB`, and only then prints `CALL LeafB.ping` from the method body.

Those are two distinct actions that can happen in the same call: ensuring the class is initialized, then executing the method. The [`Method.invoke` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...)) specifies this behavior for static methods.

### Milestone 6: constructing two objects

The first `newInstance()` runs `INIT LeafC`, then runs the constructors of `Root` and `LeafC`. The second call runs only the two object constructors; there is no second `INIT LeafC`.

This is the difference between **initializing a class** and **constructing each instance**. The [`Constructor.newInstance` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Constructor.html#newInstance(java.lang.Object...)) specifies initializing the constructor's declaring class before creating the instance if necessary.

## 5. Superclasses, Interfaces, and Where Members Are Actually Declared

If a subclass needs to be initialized before its superclass has completed initialization, Java initializes the superclass first per the corresponding rules. In the experiment, `Root` was initialized early by reading `VALUE`, so later milestones did not need to repeat that part.

Do not mechanically generalize this into a conclusion that "initializing an interface always initializes every superinterface". Interface rules and interfaces with default methods have specific conditions in the specification.

For inherited static members, pay attention to the class **that actually declares** the member. Looking up a field through a subtype does not turn that field into one declared by the subtype. You can use `getDeclaringClass()` on `Field` or `Method` to preserve this information in reports.

These details help explain why an `INIT` log does not necessarily appear on the first type the code reader looks at visually.

## 6. Do Not Turn "Without Initialization" into "No Side Effects"

The `false` argument controls the initialization request for the named class. It does not turn a custom loader into purely read-only in-memory code.

A loader may search files, read resources, or execute its own logic. Metadata resolution may also require other types. Therefore, a tool should state clearly that it avoids **actively initializing the target class**, rather than claiming no discovery step can execute any code or operation.

Nor can initialization state be measured merely by whether a class appears in a loader's list or the loaded-classes list. The experiment includes a milestone where all four classes have been defined, yet none of the test classes has printed `INIT`.

Conversely, reading a static field's value or calling a method to "check whether a class has initialized" may itself be the action that triggers initialization, changing what you intended to observe.

## 7. Errors and When They Are Observed

Separate error categories:

| Step | Example issue |
| --- | --- |
| Finding and loading a class | Class not found via the chosen loader |
| Linking or resolution | Incompatible class definition or dependency |
| Class initialization | Static field initializer expression or `static` block fails |
| Later member invocation | Illegal access, invalid arguments, or target body throws an exception |

Failures during static initialization can surface as `ExceptionInInitializerError`. After a failed initialization, subsequent uses may report `NoClassDefFoundError` because the class is in an erroneous state; not every error with that name is merely a missing `.class` file.

Do not confuse a class initialization error with an exception thrown from a target method or constructor body. For Reflection calls, when the failure occurs affects how exceptions are thrown or wrapped; preserve the original cause during analysis.

Successful initialization is a state of a specific class definition. Two different loaders can define two classes with the same binary name while maintaining separate initialization states. In the experiment, the separate loader keeps the observation context clear.

`URLClassLoader`'s `close()` closes resources managed by the loader; it does not mean the JVM immediately unloads every defined class or resets their initializers.

## 8. How to Structure a Reflection Tool

A verifiable processing flow is:

1. Select the appropriate loader and obtain `Class` with the appropriate initialization policy.
2. Read the required metadata, such as sealed status, members, and signatures.
3. Verify tool conditions without using speculative member invocation as a structural check.
4. Only at the execution step read static values, invoke methods, or instantiate objects.
5. Report errors according to the exact step so missing metadata is not confused with initialization failure.

This separation is especially useful when building type catalogs, validating sealed hierarchies, or preparing data mappers. It helps explain which actions can cause application code to start executing.

## 9. Common Mistakes and Self-Check

| Wrong inference | Distinction to preserve |
| --- | --- |
| Having `Class<?>` means static initializer has run | Type representation vs. initialization state |
| Only reading metadata means no extra classes can be loaded | Metadata may require obtaining or resolving related types |
| `Class.forName(name)` behaves like the overload passed `false` | Initialization policy of each overload |
| Obtaining a `Method` means the method was called | Metadata vs. `invoke` |
| Looking up a `Field` is the same as reading its value | `getField` vs. `Field.get` |
| Every `newInstance()` re-runs the static initializer | Class initialization vs. per-instance constructor |
| `false` guarantees zero side effects from the loader | Target class initialization vs. class-loading logic |
| Reading a member via a subclass always initializes that subclass | Lookup type vs. member-declaring class |

Try modifying each milestone in the experiment:

1. Remove the step reading `VALUE`: before `INIT LeafA`, which initialization must occur?
2. Keep looking up `ping` but remove `ping.invoke(null)`: why does `INIT LeafB` not appear even though `Method` was obtained?
3. Construct only one `LeafC` object: how do the `INIT` and `CTOR` line counts change?
4. Change the first `Class.forName` from `false` to `true`: where does `INIT Root` move?
5. Why can `value.get(null)` not be used as a passive check for whether a class has initialized?

Track **obtained `Class` objects**, **loaded or resolved types**, and **triggered initialization code** separately. These three pieces of information are related, yet do not substitute for one another.
