# Accessing static fields can trigger class initialization in Java Reflection

## 1. The problem: getting a Field and reading a Field happen at two different times

In Java Reflection, there is an important distinction between **finding a field's metadata** and **actually reading or writing that field's value**. For a `static` field, reading or writing through `java.lang.reflect.Field` can cause the JVM to **initialize the class declaring the field** before returning the value or performing the assignment.

```java
Class<?> type = Sample.class;                       // Does not yet require initializing Sample
Field field = type.getDeclaredField("value");       // Only retrieves metadata
Object value = field.get(null);                     // If Sample is not yet initialized: triggers init
```

The code snippet above is **illustrative**, requiring a `Sample` class with a `value` field and `import java.lang.reflect.Field;`; access permissions must also be valid. For a `static` field, the receiver argument of `Field.get(Object)` can be `null` because the value belongs to the class, not to a specific object.

Point to distinguish: class initialization occurs **before the first value access that requires initialization**, not necessarily immediately when the JVM loads the class, when Java creates the `Class<?>` object, or when Reflection creates the `Field` object.

### Objectives

After this lesson, you can:

- Explain why `getDeclaredField()` only looks up metadata whereas `Field.get(null)` or `Field.set(null, value)` can run static initializers.
- Distinguish **loading, linking, and initialization**, and reading a `static final` compile-time constant vs. reading it via Reflection.
- Predict output order when a class has a `static` block and `static` field assignments.
- Identify **the field's declaring class** with `Field.getDeclaringClass()` under inheritance.
- Avoid unintentionally triggering side effects, initialization errors, or risks when frameworks scan metadata.

## 2. Three phases: loading, linking, and initialization

A class typically goes through the following basic steps in the JVM lifecycle:

| Phase | Meaning | Does it necessarily run user-written `static` code? |
| --- | --- | --- |
| **Loading** | The JVM finds/reads the class representation and creates the corresponding runtime `Class` object | No |
| **Linking** | Verification, preparation, and resolution (resolution may happen lazily); preparation allocates and sets default values for `static` fields | Does not run the static initializer body as in initialization |
| **Initialization** | The JVM executes the class initialization method `<clinit>` synthesized by the compiler from static field initializers and static initializer blocks | **Yes**, if the class has corresponding initialization code |

Example:

```java
class Config {
    static int port = parsePort();  // This statement runs when initializing Config

    static {
        System.out.println("Config initialized");
    }

    private static int parsePort() {
        return 8080;
    }
}
```

When initialization of `Config` occurs, the assignment `port = parsePort()` and the static block are executed in **the textual order they appear in the class**. In this example `parsePort()` runs before the `Config initialized` message.

**Do not treat "the class has been loaded" as "the class has been initialized".** A framework may load a class to inspect its name, annotations, or members without requiring initialization logic to run; however, when the framework accesses a `static` field value, that boundary changes.

The JVM manages initialization per runtime class definition (tied to a specific class loader). Successful initialization occurs only once for that class definition; that does not mean every use of the class name in source code causes re-initialization.

## 3. Which Reflection operations can trigger initialization?

Consider:

```java
class Settings {
    static int timeout = computeTimeout();

    private static int computeTimeout() {
        System.out.println("Calculating timeout");
        return 10;
    }
}
```

| Operation | Requires initializing `Settings` if not yet initialized? | Why |
| --- | --- | --- |
| `Settings.class` | No | Class literal obtains the `Class` object, not accessing a `static` value |
| `Settings.class.getDeclaredField("timeout")` | No | Looks up field metadata |
| `Settings.class.getDeclaredFields()` | No | Lists metadata of directly declared fields |
| `field.getName()`, `field.getType()`, `field.getModifiers()` | Not a field value read operation | Inspects member characteristics; some dependent types may be loaded/resolved |
| `field.get(null)` | **Yes** | Reads a `static` field value via Reflection |
| `field.getInt(null)` | **Yes** | Specialized primitive `int` read |
| `field.set(null, value)` | **Yes** if the write is permitted | Writes a `static` field value |
| `field.setInt(null, value)` | **Yes** if the write is permitted | Writes `static int` via specialized API |
| `Settings.timeout` | **Yes** because `timeout` is not a compile-time constant | Uses a non-constant `static` field in ordinary code |
| `Class.forName("...", false, loader)` | Does not require initialization | Obtains/loads the class with flag `initialize=false` |
| `Class.forName("...")` | **Yes**, for an uninitialized class | Single-parameter variant actively requests initializing the named class |

This table assumes the operation actually reaches a valid access; if the field does not exist, the caller lacks permission, the argument type is wrong, or an earlier error occurs, do not infer that initialization **definitely** took place. The goal is to state the effect of **a successful operation on a static field**.

Do not confuse `Class.getDeclaredField` with `Field.get`: the two methods belong to different classes and have different meanings. `getDeclaredField` can even find a `private` member declared directly in the class; that **does not automatically grant permission** to call `get` or `set` later.

## 4. Java 17+ example: clearly seeing the initialization timing

Save the entire program to file **`StaticFieldInitDemo.java`**. Four cases are separated clearly: reading a normal constant, metadata lookup, reading a static field via Reflection, and writing a static field via Reflection.

```java
import java.lang.reflect.Field;

public class StaticFieldInitDemo {
    static class Target {
        static {
            System.out.println("Target: <clinit> block");
        }

        public static int number = loadNumber();
        public static final int COMPILE_CONSTANT = 42;

        private static int loadNumber() {
            System.out.println("Target: loadNumber()");
            return 7;
        }
    }

    static class Constants {
        static {
            System.out.println("Constants: <clinit> block");
        }

        public static final String TEXT = "hello";
    }

    static class Writable {
        static {
            System.out.println("Writable: <clinit> block");
        }

        public static int value = 1;
    }

    public static void main(String[] args) throws Exception {
        // Direct read of a compile-time constant can be inlined.
        System.out.println("direct constant: " + Target.COMPILE_CONSTANT);

        // Obtaining Class and Field metadata does not read the static value yet.
        Class<?> clazz = Target.class;
        Field number = clazz.getDeclaredField("number");
        System.out.println("metadata: " + number.getName());
        System.out.println("before first Field.getInt");

        // Field.getInt(null) triggers initializing Target.
        System.out.println("reflected number: " + number.getInt(null));
        System.out.println("reflected number again: " + number.getInt(null));

        // Reading a constant in regular Java does not initialize Constants.
        System.out.println("direct other constant: " + Constants.TEXT);

        // Reflection still actively reads the static field, so it initializes Constants.
        Field constant = Constants.class.getDeclaredField("TEXT");
        System.out.println("reflected constant: " + constant.get(null));

        // Obtaining Field does not initialize Writable, but writing via Field.setInt does.
        Field writable = Writable.class.getDeclaredField("value");
        System.out.println("before Field.setInt");
        writable.setInt(null, 25);
        System.out.println("updated value: " + writable.getInt(null));
    }
}
```

Compile and run with **JDK 17+**:

```bash
javac StaticFieldInitDemo.java
java StaticFieldInitDemo
```

**Exact output** when running the standalone program:

```text
direct constant: 42
metadata: number
before first Field.getInt
Target: <clinit> block
Target: loadNumber()
reflected number: 7
reflected number again: 7
direct other constant: hello
Constants: <clinit> block
reflected constant: hello
before Field.setInt
Writable: <clinit> block
updated value: 25
```

### 4.1. Why haven't the first two lines printed `Target: <clinit> block` yet?

`Target.COMPILE_CONSTANT` is a **constant variable**: a `final` field of primitive/`String` type initialized with a **constant expression**. The Java compiler can embed the constant directly in the caller's bytecode instead of emitting a runtime field-read instruction. Evaluating `Target.class` also does not itself require initialization. `clazz.getDeclaredField("number")` only produces metadata.

Thus, before the `Field.getInt(null)` call, the program has already printed information about the field while `Target` is still uninitialized.

### 4.2. Why does the static initializer output appear between two lines when reading the field?

The expression:

```java
System.out.println("reflected number: " + number.getInt(null));
```

must evaluate `number.getInt(null)` before printing the whole string. This first read requires initializing `Target`; the JVM runs the static block first, followed by `number`'s initializer calling `loadNumber()`. After initialization succeeds, `getInt(null)` returns `7` and only then does Java print `reflected number: 7`.

The second read sees that `Target` is already initialized, so it **does not re-run** the static block or `loadNumber()`.

### 4.3. Why does reading a constant via Reflection still initialize the class?

`Constants.TEXT` is a constant variable inlined by the compiler on direct reads, so the line `direct other constant: hello` does not initialize `Constants`. However:

```java
Field constant = Constants.class.getDeclaredField("TEXT");
System.out.println(constant.get(null));
```

calls `Field.get(null)` for real. The rule for reflective access to a `static` field requires initializing **the class declaring the field**, even when the field is a compile-time constant. Therefore, `Constants: <clinit> block` appears before `reflected constant: hello`.

**Consequence:** A framework that merely "reads constant values" via Reflection can still execute `static` code alongside that constant. Do not rely on a field having `final` to infer that a reflective read is always harmless.

### 4.4. Why does writing also initialize the class?

`writable.setInt(null, 25)` first ensures `Writable` is initialized (initially `value=1`), then performs the permitted write. Afterward `getInt(null)` reads `25`. There is no second print from `Writable`'s static block because initialization does not happen again.

## 5. Compile-time constants and non-constant static final fields are two different cases

Not every `static final` field is considered a constant variable.

```java
class Flags {
    static {
        System.out.println("Flags initialized");
    }

    static final int FIXED = 100;                 // Constant expression
    static final String TITLE = "core" + "-api";  // Constant expression
    static final Integer BOXED = 100;             // Not primitive/String
    static final int COMPUTED = Integer.parseInt("100");
                                                  // Not a constant expression
    static int DYNAMIC = 100;                     // Not final
}
```

| Access in ordinary Java code | Normally requires initializing `Flags`? |
| --- | --- |
| `Flags.FIXED` | No; compile-time constant can be inlined |
| `Flags.TITLE` | No; constant expression of type `String` |
| `Flags.BOXED` | Yes; `Integer` is not a type for a constant variable |
| `Flags.COMPUTED` | Yes; `Integer.parseInt(...)` is not a constant expression |
| `Flags.DYNAMIC` | Yes; `static` field is not a constant variable |

Conversely, `Field.get(null)` for **any static field** in the table above requires initialization of the declaring class before reading, if the class has not yet been initialized and the operation is permitted.

Beyond initialization, constant inlining also affects binary compatibility: previously compiled classes can retain the old constant value until recompiled. This is why you should not change a `public static final` constant and observe output to draw simplistic conclusions about loading/initialization.

## 6. Which class is initialized under inheritance?

The initialization target is **the class declaring the accessed static field**, not automatically the class you used as the lookup starting point.

```java
class ParentConfig {
    static {
        System.out.println("ParentConfig initialized");
    }

    public static int port = 8080;
}

class ChildConfig extends ParentConfig {
    static {
        System.out.println("ChildConfig initialized");
    }
}
```

Example statements in a method with `throws Exception`:

```java
Field field = ChildConfig.class.getField("port");
System.out.println(field.getDeclaringClass().getSimpleName());
System.out.println(field.getInt(null));
```

If neither class has been initialized yet, this means:

- `getField("port")` can find the inherited `public` field; `getDeclaringClass()` indicates the field actually resides in `ParentConfig`.
- `field.getInt(null)` requires initializing `ParentConfig` (where the field is declared).
- Merely obtaining the field through `ChildConfig.class` does not mean `ChildConfig` needs to be initialized. Reading an inherited static field does not automatically force the subclass to run its static block.

With *field hiding*, always check `getDeclaringClass()`. If `ChildConfig` declares a different `port` field, you must pick the exact `Field` you intend to read; picking the wrong owner can trigger initializing a different class than expected.

When initializing a **class**, the JVM must also ensure required superclasses are initialized according to standard rules; certain interfaces with default methods may also participate in the process. Thus, reading a static field declared in a subclass can pull in related initialization along the hierarchy, but you must not reverse the reasoning to assume reading a superclass static field always initializes every subclass.

## 7. Loading/metadata is safer than initialization, yet its limits must be understood

If the task is solely **exploring class structure**, initialization can be deferred:

```java
String binaryName = "example.Settings";
ClassLoader loader = Thread.currentThread().getContextClassLoader();

Class<?> clazz = Class.forName(binaryName, false, loader);
Field field = clazz.getDeclaredField("timeout");

System.out.println(field.getName());
System.out.println(field.getDeclaringClass().getName());
```

This is an illustrative snippet, assuming class `example.Settings` is on the classpath/module path with appropriate lookup permissions; requires `import java.lang.reflect.Field`. `Class.forName(name, false, loader)` does not actively initialize the named class. Similarly, inspecting basic `Field` metadata does not read static values. Even so, loading, linking, resolution, or custom hooks/class loaders can still perform other work: "the target class is not yet initialized" **does not mean every related operation is guaranteed to have zero side effects**.

Some ways that actively request initialization:

```java
Class.forName("example.Settings");      // Normally requires initialization
// Or perform a valid static field read/write operation.
```

Adopt a clear policy: if a plugin scanner only lists fields, there is no need to read every `static` value. If the application genuinely needs runtime values, accept that this operation may initialize the class.

## 8. Initialization order and default values

During **preparation**, the JVM assigns initial default values to `static` fields: `0` for numeric integers, `false` for `boolean`, `null` for references. During **initialization**, compiler-generated code from static initializers runs in source order; this is when custom assignments execute.

Example:

```java
class Ordered {
    static int first = compute();
    static int later = 20;

    private static int compute() {
        return later + 1;
    }
}
```

When `Ordered` is initialized, the assignment `first = compute()` executes before `later = 20`. At the moment `compute()` reads `later`, the field has default value `0`, so `first` receives `1`. Afterward `later` becomes `20`. Both fields are `static`, yet initializer order still matters.

In this example a reflective read of `Ordered.first` after initialization will yield `1`. Do not use Reflection to infer that initializers run "simultaneously" or that a field always sees every other field already assigned its final value.

The JLS contains specific details about constant variables, superclass initialization, and interface initialization. For the common case in this lesson, the core point is that the JVM completes required initialization **before reflective access to the static field succeeds**.

## 9. What if static initialization fails?

Static initializers may load configuration, read files, open connections, call native libraries, or perform calculations that can fail. When Reflection is the first operation requesting initialization of a class, an error may surface right at `Field.get(null)` or `Field.set(null, value)`, even though the field itself is valid.

Example of a class whose initialization fails:

```java
class Broken {
    static int value = initialize();

    private static int initialize() {
        throw new IllegalStateException("missing configuration");
    }
}
```

If this is the first time code with permission calls:

```java
Field field = Broken.class.getDeclaredField("value");
field.getInt(null);
```

The metadata lookup on the first line can succeed; the second line requests initialization, causing the initialization error to propagate. When the initializer throws a `RuntimeException` as in the example, the first initialization attempt typically manifests as an `ExceptionInInitializerError` wrapping the cause. The JVM marks the class in an erroneous initialization state; subsequent active uses of the same class definition generally receive `NoClassDefFoundError` for a class that could not be initialized. You cannot "retry reading the Field" to make the class initialize from scratch. A different field of the same class cannot fix that either.

If you encounter this situation:

1. Inspect the stack trace and root **cause** of the initialization error, especially the part running inside `<clinit>`.
2. Distinguish **metadata lookup** errors (`NoSuchFieldException`), **access permission** errors (`IllegalAccessException`), and **initialization** errors (which may be `ExceptionInInitializerError` or a related `Error`).
3. Avoid wrapping every error as "field does not exist": that hides the real cause and misleads readers into thinking the Reflection API failed.
4. Keep static initialization lightweight, deterministic, and minimally dependent on environment resources. Move expensive/error-prone logic into a controlled initialization phase when appropriate.

The `Broken` snippet above illustrates an error; it is **not** run in the example program in section 4, to keep section 4's stdout deterministic and successful.

## 10. Access permissions, final, and class initialization are three separate concerns

A `Field` may describe a `public`, `private`, `static`, or `final` field, yet these attributes relate to separate rules:

- **Discoverability:** `getDeclaredField` finds directly declared fields regardless of `public`/`private`; `getField` finds `public` fields according to hierarchy rules.
- **Readability/writability:** `Field.get`/`Field.set` enforce caller access checks; `setAccessible`/`trySetAccessible` have their own rules, subject to module boundaries in modern Java.
- **Initialization timing:** When a `static` field read/write operation is permitted to proceed, the declaring class is initialized as needed.
- **`final` immutability:** Do not assume `Field.set` can modify `static final`. In modern Java, `static final` is a category of fields that cannot be made writable by Reflection in the ordinary way, even if trying to enable accessible overrides.

Example for a public `static int` field:

```java
Field f = MyType.class.getDeclaredField("counter");
int oldValue = f.getInt(null);
f.setInt(null, oldValue + 1);
```

This is an illustrative snippet inside a method with exception handling and an appropriate `MyType` class; the `getInt(null)` call will initialize the field's declaring class if needed. These two get-then-set operations **are not an atomic increment**, because other threads can intervene.

For `private static`, retrieving metadata can still succeed, yet calling `get`/`set` from an unauthorized caller will fail. Do not assert that the class has initialized simply because an access call **was rejected before reaching the read/write stage**; identify which step failed.

## 11. Concurrency issues: initializing once does not mean the field is thread-safe

The JVM coordinates class initialization across threads: while one thread is performing initialization of a class, other threads needing to use that class must follow JVM synchronization/waiting rules for initialization. Once initialization completes successfully, threads using the class do not automatically re-run the static initializer.

However, afterward:

```java
// Two separate operations, does not guarantee an atomic increment:
int count = field.getInt(null);
field.setInt(null, count + 1);
```

a read followed by a write via Reflection can still **race**. `static` does not automatically make a field `volatile`, does not make read-modify-write updates atomic, and does not replace application-level synchronization.

If multiple threads concurrently mutate static state, consider `synchronized`, `volatile` specifically for visibility, `AtomicInteger`, or an appropriate synchronization mechanism. Avoid using the initialization process as a guard lock for the entire lifetime of mutable static state.

Another hazard is **circular initialization**: class A's initializer uses B's static state while B conversely uses A's static state. When dependency paths form a cycle, results can be unexpected due to assignment order and default values. Hence `<clinit>` logic should be minimal.

## 12. API selection patterns by goal

| Goal | Approach | Side effect to watch for |
| --- | --- | --- |
| List fields for documentation | `type.getDeclaredFields()`, read name/type/modifiers | Does not require reading field values, usually avoids initializing target class |
| Identify the class owning a field | `field.getDeclaringClass()` | Helps reveal which class will be the initialization target |
| Get a `static int` value | `field.getInt(null)` | Can initialize declaring class |
| Get a reference-type `static` value | `field.get(null)` | Can initialize declaring class |
| Write a writable `static int` | `field.setInt(null, value)` | Can initialize before assigning; must ensure thread safety separately |
| Load only to inspect metadata | `Class.forName(name, false, loader)` | Actively avoids initializing the named class |
| Attempt to call into `static final` via Reflection to mutate it | **Do not design this way** | Write-restricted, neither guaranteed valid nor safe |

In plugin discovery tools, serializers, dependency-injection containers, or diagnostic scanners, "only viewing field names" and "reading static field values to log" are two very different decisions. Set an explicit threshold for permitting initialization, especially when classes have static blocks connecting to services, reading environment variables, or loading configuration.

## 13. Common mistakes and self-check questions

### Common mistakes

1. **Confusing `getDeclaredField` with `Field.get`:** similar names, yet one returns metadata while the other accesses values and can trigger initialization.
2. **Believing `static final` is always harmless:** direct constant reads can be inlined; reflective `get` can still initialize the class.
3. **Initializing the wrong owner under inheritance:** a field retrieved from `Child.class` may actually belong to `Parent`; check `getDeclaringClass()`.
4. **Using `Class.forName(name)` when only structure is needed:** the default variant requests initialization; use `Class.forName(name, false, loader)` when only inspecting metadata.
5. **Swallowing `ExceptionInInitializerError`:** concluding "Reflection failed to read" without examining the static initialization cause.
6. **Assuming initialization synchronizes all `static` updates:** it only coordinates the initialization process, not synchronization for subsequent operations.
7. **Trying to write `static final`:** permission to find a field does not imply permission to modify it; ordinary reflective writing is not supported for `static final`.

### Self-check

**Question 1.** If `Config.class.getDeclaredField("port")` returns a `Field`, does that prove `Config`'s static block has already run?

**Answer:** Not yet. Querying metadata is not a request to read/write a `static` value.

**Question 2.** Why might reading `public static final int VERSION = 3;` in regular Java code not initialize the class, whereas `field.getInt(null)` does?

**Answer:** `VERSION` is a compile-time constant so the compiler can inline its value; `Field.getInt(null)` is still a real reflective access to the `static` field and requires initializing the declaring class.

**Question 3.** When `Field.setInt(null, 25)` runs on an uninitialized class, does the static initializer run before or after the write?

**Answer:** Required initialization occurs **before** the field write succeeds; the static initializer may set an initial value, after which `setInt` overwrites it with `25`.

**Question 4.** If `public static int port` is declared in `Parent` and found via `Child.class.getField("port")`, which class is initialized by a reflective read of that field?

**Answer:** `Parent` is the declaring class. Do not assume `Child` is also initialized.

**Question 5.** If the first `Field.get(null)` causes `ExceptionInInitializerError`, should you immediately retry with another `Field` of the same class to re-initialize it?

**Answer:** No. After class initialization fails, the class remains in an erroneous state at runtime; you must fix the root cause and use an appropriate startup/lifecycle strategy.

**Remember:** Java Reflection can observe class structure without running initialization code, yet **reading/writing a `static` field with `Field.get`/`Field.set` is a runtime action that can trigger initialization of the field's declaring class**. Check `getDeclaringClass()`, distinguish compile-time constants from reflective access, and proactively manage side effects from static initializers when designing Reflection-based tools.