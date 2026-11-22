# Constant Values May Already Be Inlined Into Calling Code

## 1. Why Does Calling Code Still See the Old Value After Modifying a `final` Field?

In Java, when a field qualifies as a **compile-time constant variable**, the compiler can replace reads of the field with the constant value itself directly in the bytecode of the calling class. This phenomenon is commonly called **constant inlining** or **constant folding at the use site**.

An important consequence: if a library changes the value of a constant such as `public static final int LIMIT = 10` to `20` and only recompiles the library, previously compiled application bytecode **may continue using 10**. Changing the `.class` file containing the field does not automatically update values already embedded in the `.class` files of calling programs.

~~~java
public class Limits {
    public static final int MAX_ITEMS = 100;
    public static final String VERSION = "v1";
}
~~~

With calling code:

~~~java
System.out.println(Limits.MAX_ITEMS);
System.out.println(Limits.VERSION);
~~~

The two expressions above can be replaced by the compiler with the literals `100` and `"v1"`. In the caller's bytecode, there may **no longer be any instruction reading the `Limits.MAX_ITEMS`/`Limits.VERSION` fields**. Therefore, we must distinguish:

- **Runtime value of the field:** the value currently present in the class loaded by the JVM.
- **Value embedded in calling code:** the literal placed into the caller's bytecode when the caller was compiled.
- **Value observed via Reflection:** `Field.get(...)` reads the field of the runtime class after applying access-permission rules, not the literal embedded in the caller.

This is especially important for `final` fields in library APIs, shared modules, configuration stored as constants, and multi-module build projects.

## 2. Which Fields Are Actually Compile-Time Constants?

According to Java language rules, a **constant variable** is a `final` variable of **primitive** or `String` type initialized with a **constant expression**. In practice, the most common fields are `static final` of type `int`, `long`, `boolean`, `char`, `String`, etc., assigned directly with a literal or constant expression.

| Declaration | Is it a constant variable? | Why |
| --- | --- | --- |
| `public static final int PORT = 8080;` | Yes | Primitive, `final`, and literal expression |
| `public static final int TOTAL = 40 + 2;` | Yes | `40 + 2` is a constant expression |
| `public static final String LABEL = "core" + "-api";` | Yes | Concatenates constant strings at compile time |
| `public static final boolean ENABLED = true;` | Yes | Primitive, constant expression |
| `public static final Integer COUNT = 42;` | No | `Integer` is a reference type other than `String`, even though the value represents an integer |
| `public static final int PORT = Integer.parseInt("8080");` | No | An ordinary method call is not a constant expression |
| `public static final String LABEL = new String("core");` | No | Creating an object with `new` is not a constant expression |
| `public static final long CREATED_AT = System.currentTimeMillis();` | No | Value is computed at runtime |
| `public final int id = 7;` | Yes, per the constant variable definition | An instance field can also be a constant variable if `final`, primitive/`String`, and initialized with a constant expression |
| `public final int id;` assigned in constructor | No | Not initialized with a constant expression directly at declaration |

**Not every `final` field gets inlined.** `final` expresses a language-level restriction on reassigning the field, whereas whether it is treated as a compile-time constant also depends on its **type** and **initializer expression**. `static final` constants have the greatest impact on public APIs because many other classes reference the same field.

To avoid confusion, `static final Integer VALUE = 42` is **not** a compile-time constant under this rule. When using that field normally, the compiler must fetch the runtime reference; autoboxing the number 42 at the initializer does not turn an `Integer` field into a constant variable.

## 3. Java 17+ Example: Modifying the Constant-Holding Class Without Recompiling the Caller

This exercise uses **two files in the same directory**. Run through two compilation rounds to observe the difference between the library's bytecode and the consumer's bytecode.

### Step A — Initial Version

Create the file `Constants.java`:

~~~java
public class Constants {
    static {
        System.out.println("Constants initialized");
    }

    public static final int LIMIT = 10;
    public static final String LABEL = "v1";
    public static final int RUNTIME = Integer.parseInt("10");
}
~~~

Create the file `Consumer.java`:

~~~java
public class Consumer {
    public static void main(String[] args) throws Exception {
        System.out.println("direct LIMIT = " + Constants.LIMIT);
        System.out.println("direct LABEL = " + Constants.LABEL);
        System.out.println("direct RUNTIME = " + Constants.RUNTIME);

        System.out.println("reflection LIMIT = "
                + Constants.class.getField("LIMIT").getInt(null));
        System.out.println("reflection LABEL = "
                + Constants.class.getField("LABEL").get(null));
    }
}
~~~

In a terminal in the directory containing both files:

~~~bash
javac --release 17 Constants.java Consumer.java
java Consumer
~~~

Output:

~~~text
direct LIMIT = 10
direct LABEL = v1
Constants initialized
direct RUNTIME = 10
reflection LIMIT = 10
reflection LABEL = v1
~~~

Explanation: `LIMIT` and `LABEL` are compile-time constants. The first two `direct` lines are produced from values that can be embedded directly into `Consumer`'s bytecode; they **do not cause `Constants` to be initialized**. When execution reaches the line using `Constants.RUNTIME`, the JVM must read the runtime field via static field access, so the `Constants` class is initialized and the static initializer prints `Constants initialized`. Reflection at the end reads the actual field values of the loaded class.

### Step B — Update the Library Without Recompiling `Consumer`

**Only replace the contents of `Constants.java`** with:

~~~java
public class Constants {
    static {
        System.out.println("Constants initialized");
    }

    public static final int LIMIT = 20;
    public static final String LABEL = "v2";
    public static final int RUNTIME = Integer.parseInt("20");
}
~~~

Then run only:

~~~bash
javac --release 17 Constants.java
java Consumer
~~~

Note: **do not** re-run `javac Consumer.java` in this step. The old `Consumer.class` remains intact.

Output verified on Java 21:

~~~text
direct LIMIT = 10
direct LABEL = v1
Constants initialized
direct RUNTIME = 20
reflection LIMIT = 20
reflection LABEL = v2
~~~

In the same run, the program simultaneously sees `10`, `"v1"` via previously compiled calling code, and `20`, `"v2"` in the current fields. This is not the JVM "misremembering" the field; the `Consumer.class` bytecode still contains the old literals.

- `Constants.LIMIT` and `Constants.LABEL` in the two `direct` statements were compiled into output strings containing the old literals.
- `Constants.RUNTIME` is **not** a constant variable because it is initialized with `Integer.parseInt(...)`; the caller performs a runtime field read and therefore sees `20` from the new `Constants.class`.
- `Constants.class.getField("LIMIT").getInt(null)` and `getField("LABEL").get(null)` read metadata/field values from the `Constants` class actually loaded at runtime. They see the new version.
- In this example, `Constants` is a public class and its fields are public; `getField` succeeds and `getInt(null)` is valid for a primitive `int` static field.

### Step C — Recompile the Caller

After updating `Constants.java`, continue with:

~~~bash
javac --release 17 Consumer.java
java Consumer
~~~

Now the two `direct` lines read the new constants because `Consumer.class` has been recompiled:

~~~text
direct LIMIT = 20
direct LABEL = v2
Constants initialized
direct RUNTIME = 20
reflection LIMIT = 20
reflection LABEL = v2
~~~

Practical rule: when **changing the value of a public compile-time constant** in a library, you must **also recompile the relevant consumers** to ensure their bytecode does not retain old literals.

## 4. Inspecting Bytecode to Understand the Cause

After Step B (before recompiling `Consumer`), run:

~~~bash
javap -c Consumer
~~~

In the bytecode of `main`, you will see the equivalent of:

- An `ldc` instruction loading the prebuilt string `"direct LIMIT = 10"`.
- An `ldc` instruction loading the prebuilt string `"direct LABEL = v1"`.
- For `RUNTIME`, a `getstatic Constants.RUNTIME:I` instruction reading the integer field of the `Constants` class at runtime.

`javap` may also display constant pool indices and `invokedynamic` instructions used for string concatenation; exact bytecode offsets/indices may vary by JDK. What to verify is that **there is no `getstatic` to `Constants.LIMIT` or `Constants.LABEL` in the two direct expressions folded by the compiler**. Because the caller does not perform a static field read for those two constants, changing the field value in another class cannot update the literals in old bytecode.

This is an optimization and language semantics permitted by Java; it should not be attributed generally to a JIT cache. The JIT may perform other optimizations at runtime, but the example above reproduces the issue directly inside the **`Consumer.class` file after compilation**.

## 5. What Does Reflection See, and Should You Modify `final` via Reflection?

With `public static final int LIMIT = 20`:

~~~java
java.lang.reflect.Field field = Constants.class.getField("LIMIT");
System.out.println(field.getType());  // int
System.out.println(field.getInt(null)); // 20
System.out.println(field.get(null));    // Integer containing 20
~~~

This is an **illustrative snippet** reusing the Step B version of `Constants`, not a standalone program. `getInt(null)` reads the primitive `int` directly; `get(null)` returns `Object`, boxing into `Integer`. For static fields, the receiver can be `null`.

What Reflection **cannot** do is change literals already embedded in `Consumer.class` bytecode. `getInt(null)` reflects the existing field value; meanwhile, the old caller's `System.out.println("direct LIMIT = " + Constants.LIMIT)` statement has already been compiled into a string containing `10`.

**Do not try to modify `static final` with `Field.set` to "update everywhere".** In modern Java, `static final` belongs to the category of final fields not permitted to be written via Reflection, even when `setAccessible(true)` might be accepted for reading. Furthermore, even a mechanism capable of altering some value at runtime **cannot modify literals already baked into caller bytecode**. Opening access permission does not change how the compiler generates and uses compile-time constants.

If a value needs to be updated after release, design a formal runtime access point (a method, configuration, or service/registry with an explicit lifecycle) instead of using a public compile-time constant as a mutable configuration value.

## 6. Does Reading `static final` Always Trigger Class Initialization?

**No.** Under Java's class-initialization rules, using a `static final` **constant variable** can be compiled into a literal and is not an operation that triggers initialization of the class owning the field.

In the example:

~~~java
System.out.println("direct LIMIT = " + Constants.LIMIT);
System.out.println("direct LABEL = " + Constants.LABEL);
~~~

There is no `Constants initialized` line between these two statements. The `Constants` class is only initialized when the program reads `Constants.RUNTIME`, which is a `static final` field that is **not** a constant variable because it is computed via a method call at runtime.

Distinction:

| Usage | Typical result |
| --- | --- |
| Referencing compile-time constant `Constants.LIMIT` in compiled code | Bytecode uses a literal; no runtime field read is needed and the class is not initialized by that read |
| Referencing `Constants.RUNTIME` with a non-constant initializer | `getstatic` instruction; the JVM initializes the class before reading per JVM rules |
| Obtaining `Constants.class` | A class literal does not by itself trigger class initialization |
| Using Reflection to get a static field value via `Field.get` | Reading a static field can trigger class initialization if not yet initialized |
| Calling a static method or creating an instance | Normally triggers class initialization per Java rules |

Therefore, logging in a static initializer **is not a reliable measurement** of whether callers have read a compile-time constant. The compiler may completely eliminate runtime field access.

## 7. Impact on Binary Compatibility and Versioning

Changing a constant from `10` to `20` does not necessarily produce a linkage error (`LinkageError`). The application can still run with the new `Constants.class` file while keeping the old value embedded at compile time. This is a risk of **behavioral change upon version upgrades** that is very easy to overlook.

A typical scenario:

1. Library `api-v1.jar` publishes `public static final int MAX_RETRY = 3`.
2. Service A compiles against `api-v1.jar`; A's bytecode carries the literal `3` wherever the compile-time constant is used.
3. The library releases `api-v2.jar`, changing `MAX_RETRY = 5`.
4. If only the library JAR is swapped and Service A is restarted without **recompiling A**, A may still use `3` in its compiled logic.
5. Recompiling all consumers against the new `api-v2.jar` updates those literals to `5`.

Consequently, for public constants that form part of a contract between modules, **changing a value must be evaluated as a behavioral API change**. Clean builds/rebuilds and bytecode inspection help detect mixed states between old consumer code and a new library.

If a value needs to vary by configuration, deployment version, or environment, consider a runtime API:

~~~java
public final class RuntimeSettings {
    private RuntimeSettings() {}

    public static int maxRetry() {
        return Integer.getInteger("app.maxRetry", 3);
    }
}
~~~

The code above is an example runtime API; calling `RuntimeSettings.maxRetry()` reads the current system property (if it is not a valid number, `Integer.getInteger` returns the default value per its API contract). This is not a compile-time constant, so callers cannot pre-embed the result as a literal from a constant field. Real-world configuration design must account for validation, caching, and when values are allowed to change.

Another option when data is **intentionally immutable for the lifetime of an application release** is to keep using `static final`, while making clear that consumers must be recompiled when values change.

## 8. Common Misconceptions

| Misconception | Accurate understanding |
| --- | --- |
| "`final` means the compiler always inlines the value." | Only constant variables satisfying primitive/`String` type + constant initializer expression have this behavior; other final fields can still be read at runtime |
| "`static final Integer N = 1` is a constant just like `static final int N = 1`." | `Integer` is neither a primitive nor `String`, so `N` is not a constant variable |
| "Once the JAR containing the field is updated, all programs immediately see the new value." | Old consumers may retain embedded literals; consumers must be recompiled |
| "Using `final` guarantees every field access executes `getstatic`." | A compile-time constant may become a literal and have no `getstatic` left in the caller |
| "Reflection always returns the same value as code accessing the field directly." | `Field.get` reads the runtime field; old code may use an embedded literal |
| "Modifying the field via Reflection will update constants in consumers." | No: consumer code might no longer read the field. Writing static final via Reflection is also independently restricted |
| "`static final` always initializes the class when accessed." | Referencing a compile-time constant does not trigger class initialization if compiled into a literal; non-constant static fields are read at runtime |
| "`String` concatenation with `+` is always evaluated at runtime." | If all components are constant expressions, concatenation can be evaluated at compile time |

### How to diagnose a real-world bug

If a component reports an old configuration value after a library upgrade, inspect in order:

1. Is the field `final`, of primitive/`String` type, with a constant-expression initializer?
2. Is the running component old consumer bytecode compiled against the previous value?
3. Use `javap -c Consumer` to look for literals or `getstatic` at the exact usage site.
4. Read the field via Reflection at runtime (when permitted) to compare against the class's current value.
5. Recompile all relevant consumers and deploy matching versions; inspect JARs/classpath to avoid mixed versions.

## 9. Self-Check Questions

**1.** Can `public static final String NAME = "A" + "B";` be inlined into the caller? **Yes**: concatenating string literals is a constant expression, so the result `"AB"` can appear in the consumer's bytecode.

**2.** Is `public static final String NAME = System.getProperty("name");` the same? **No**: a method call is evaluated at runtime, not a constant expression.

**3.** Why does `Field.getInt(null)` see `20` while `Consumer` still prints `10`? Reflection reads the field of the new runtime class; the old `Consumer.class` uses the literal embedded before the library changed.

**4.** Can you update only the library file without recompiling callers and still receive the new constant value? **Cannot be guaranteed** for compile-time constants: callers might no longer access the field at runtime. The reliable solution is recompiling consumers.

**5.** Is an instance field `final int id = 7` never a constant variable just because it lacks `static`? **No**: the constant variable definition does not require `static`, though cross-class inlining issues are most prominent with `public static final`.

**Remember:** `final` and *compile-time constant* are related but distinct concepts. Once constant inlining has occurred, changing the field afterward cannot fix literals in consumer bytecode; therefore, publishing public constants and rebuilding callers must be considered together.
