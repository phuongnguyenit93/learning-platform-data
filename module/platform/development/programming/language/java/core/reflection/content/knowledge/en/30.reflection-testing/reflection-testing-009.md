# Testing Metadata With and Without `-parameters` in Java Reflection

## 1. Why Must Both Build Variants Be Tested?

When compiling Java, parameter names in source code such as `firstName` and `repeat` are **not required** to exist in the class file in a form readable by Java Reflection. The `javac -parameters` option instructs the compiler to store parameter names and modifiers for **methods and constructors** in the `MethodParameters` bytecode attribute. If this option is omitted, the program still invokes methods normally and reflection still knows the **parameter count, order, and types**; what is typically missing are the **original parameter names**.

This affects frameworks that use reflection to map query/path/body parameters, bind constructor arguments, read parameter names in validation, dependency injection, CLI command mapping, or API doc generation. A test run only on builds with `-parameters` can hide build-configuration bugs in other environments.

**Lesson goal:** produce two artifacts from the **same source** (one with `-parameters`, one without), inspect them with `Executable.getParameters()`, verify both `getName()` and `isNamePresent()`, compare class files using `javap -v`, and design tests that catch hidden dependencies on parameter names.

## 2. Which Metadata Is Preserved and Which Changes?

Consider the Java method:

~~~java
// Excerpt from class Sample; not a standalone program.
public String greet(String firstName, int repeat) {
    return firstName.repeat(repeat);
}
~~~

On a JDK supporting Java 8+ parameter metadata:

| Reflection query | With `-parameters` | Without `-parameters` (standard javac class) |
| --- | --- | --- |
| `method.getParameterCount()` | `2` | `2` |
| `method.getParameterTypes()` | `String.class`, `int.class` | Identical |
| `method.getParameters()[0].getName()` | `"firstName"` | Synthetic placeholder name, typically `"arg0"` |
| `method.getParameters()[1].getName()` | `"repeat"` | Synthetic placeholder name, typically `"arg1"` |
| `Parameter.isNamePresent()` | `true` | `false` |
| `method.invoke(target, "Hi", 2)` | Executes by argument types and order | Works identically |
| Annotations/type info with separate metadata sources | Not controlled by `-parameters` | Not controlled by `-parameters` |

Crucial point: **`getName()` can always return a `String`**, even when source names were not recorded in bytecode. Therefore:

- `getName() != null` **does not prove** real parameter names exist.
- `getName().equals("arg0")` **is not** a valid check for missing metadata: `arg0` could also be a name chosen by a developer in source code.
- The proper check is `parameter.isNamePresent()` before relying on `parameter.getName()` for data binding.

`Executable` is the common superclass of `Method` and `Constructor`; both support `getParameters()`. The `-parameters` option does not apply only to methods.

## 3. Java 17+ Experiment: Compiling Two Variants from One Source

### 3.1. Directory Structure

Create a new test directory with two source files and three output directories:

~~~text
parameter-lab/
├── src/
│   ├── demo/
│   │   └── Sample.java
│   └── probe/
│       └── ParameterMetadataProbe.java
├── without/
├── with/
└── probe/
~~~

The two directories `without` and `with` hold **two different builds of the same class `demo.Sample`**. Directory `probe` holds the metadata-reading program. Do not place both `.class` versions onto the same classpath simultaneously: doing so lets classpath order decide which build is loaded and makes test results unreliable.

**File `src/demo/Sample.java`:**

~~~java
package demo;

public final class Sample {
    private final String label;

    public Sample(String label) {
        this.label = label;
    }

    public String greet(String firstName, int repeat) {
        return firstName.repeat(repeat) + label;
    }
}
~~~

Here we have a **constructor** with one parameter `label` and an **instance method** `greet` with two parameters `firstName` and `repeat`. The class uses `String.repeat(int)` available since Java 11; compiling targeting Java 17 is valid.

**File `src/probe/ParameterMetadataProbe.java`:**

~~~java
package probe;

import java.lang.reflect.Constructor;
import java.lang.reflect.Executable;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

public final class ParameterMetadataProbe {
    static void inspect(String tag, Executable executable) {
        Parameter[] parameters = executable.getParameters();
        for (int i = 0; i < parameters.length; i++) {
            Parameter p = parameters[i];
            System.out.printf("%s[%d]: name=%s, present=%s, type=%s%n",
                    tag, i, p.getName(), p.isNamePresent(),
                    p.getType().getSimpleName());
        }
    }

    public static void main(String[] args) throws Exception {
        Class<?> sample = Class.forName("demo.Sample");

        Constructor<?> ctor =
                sample.getDeclaredConstructor(String.class);

        Method greet = sample.getDeclaredMethod(
                "greet", String.class, int.class);

        inspect("constructor", ctor);
        inspect("greet", greet);
    }
}
~~~

`ParameterMetadataProbe` looks up **one exact constructor and one method**, then prints the name, parameter-name metadata status, and parameter type. Both Java files above are compilable programs/classes with no dependencies outside the JDK.

### 3.2. Compiling With and Without `-parameters`

From `parameter-lab/`, first create `without`, `with`, and `probe` if they do not yet exist. On Linux/macOS (bash):

~~~bash
mkdir -p without with probe

# Build A: has local variable debug info (-g) but WITHOUT -parameters.
javac --release 17 -g -d without src/demo/Sample.java

# Build B: has -parameters but WITHOUT debug info (-g:none).
javac --release 17 -parameters -g:none -d with src/demo/Sample.java

# Probe is compiled independently, without needing to import demo.Sample.
javac --release 17 -d probe src/probe/ParameterMetadataProbe.java

echo '=== WITHOUT -parameters (with -g) ==='
java -cp probe:without probe.ParameterMetadataProbe

echo '=== WITH -parameters (without -g) ==='
java -cp probe:with probe.ParameterMetadataProbe
~~~

**On Windows PowerShell:** create the directories using `New-Item -ItemType Directory -Force without,with,probe` (or create them in Explorer); Java's classpath separator on Windows is a **semicolon**, so the two run commands are:

~~~powershell
java -cp 'probe;without' probe.ParameterMetadataProbe
java -cp 'probe;with' probe.ParameterMetadataProbe
~~~

The `javac --release 17 ...` commands are identical on Windows and Unix. Do not overwrite `Sample.java` into the same output directory and test, as it is very easy to run the wrong variant. Each `java` command launches a fresh JVM, avoiding `demo.Sample` already loaded by a class loader from the previous variant.

### 3.3. Exact Output

When running the two `java` commands above:

~~~text
=== WITHOUT -parameters (with -g) ===
constructor[0]: name=arg0, present=false, type=String
greet[0]: name=arg0, present=false, type=String
greet[1]: name=arg1, present=false, type=int
=== WITH -parameters (without -g) ===
constructor[0]: name=label, present=true, type=String
greet[0]: name=firstName, present=true, type=String
greet[1]: name=repeat, present=true, type=int
~~~

The output uses `echo` lines to separate the two runs. Running only `java` prints the three constructor/method lines per run without separator headers.

**Explanation:** `getDeclaredConstructor(String.class)` and `getDeclaredMethod("greet", String.class, int.class)` find the members in both builds. The difference appears when `getParameters()` returns `Parameter` and `getName()`/`isNamePresent()` inspect name metadata. Both builds preserve parameter order and types `String, int`. That is the exact boundary: **name metadata differs from signature and invocation metadata**.

## 4. How Does `-parameters` Differ from `-g`?

The two flags serve different purposes:

| `javac` flag | What the class file mainly receives | What standard Reflection observes |
| --- | --- | --- |
| `-parameters` | **`MethodParameters`** attribute for method/constructor parameter info | `Parameter.getName()`, `isNamePresent()`, and certain metadata modifiers |
| `-g` | Debug info including line numbers, source file, local variables | **Does not automatically populate** real names for `Parameter.getName()` |
| `-g:none` | Does not emit standard debug information | **Does not strip `MethodParameters`** if built with `-parameters` |
| Omitting `-parameters` | Standard `javac` does not store source parameter names via `MethodParameters` | Placeholder names `arg0`, `arg1`, ... and `isNamePresent() == false` in the example |

`LocalVariableTable` debug info, when present, lives inside the `Code` attribute and serves debuggers/bytecode tools. It is **not** the same attribute as `MethodParameters`; core reflection **does not use `LocalVariableTable` as a public fallback** to recover parameter names for `Parameter.getName()`. An external library may explicitly parse debug bytecode to recover information in some cases, but that behavior must not be equated with core Java Reflection.

**Experiment intentionally controlling two variables:**

- **Without** build: `-g` has debug info, **no `-parameters`** → `isNamePresent() = false`.
- **With** build: `-parameters -g:none` **has no debug info**, yet has `MethodParameters` → `isNamePresent() = true`.

Thus, test results cannot be mistakenly explained as parameter names coming from debug flags.

### 4.1. Inspecting Bytecode Directly with `javap`

Run:

~~~bash
javap -v -p -classpath without demo.Sample
javap -v -p -classpath with demo.Sample
~~~

In the output of the **with** build, look for an attribute shaped like:

~~~text
MethodParameters:
  Name                           Flags
  firstName
  repeat
~~~

This is an **illustrative excerpt from the `greet` method section** (`javap` column alignment may vary by JDK), not the entire program output. The constructor also has a `MethodParameters` attribute containing `label`.

The **without** build may have `LocalVariableTable` because it was compiled with `-g`, yet **has no `MethodParameters` block for those methods**. The **with** build has `MethodParameters` despite being compiled with `-g:none`. You can use `javap -l` to inspect line/local-variable debug info separately.

**Note:** `javap` prints the constant pool and many attributes; do not just search for the string `firstName` across the whole output and conclude parameter names are available to reflection. Check the **exact `MethodParameters` attribute** of the respective method/constructor.

## 5. Writing Automated Tests to Catch Missing Metadata in Builds

Instead of only reading stdout, add assertions in dedicated tests targeting the **actual artifact used in deployment**. JUnit is omitted here to avoid adding dependencies; below is a standalone Java 17 class with `main` asserting via `AssertionError`:

**File `src/probe/ParameterMetadataAssertions.java`:**

~~~java
package probe;

import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.util.Arrays;

public final class ParameterMetadataAssertions {
    public static void main(String[] args) throws Exception {
        Class<?> type = Class.forName("demo.Sample");
        Method method =
                type.getDeclaredMethod("greet", String.class, int.class);

        Parameter[] params = method.getParameters();

        if (params.length != 2) {
            throw new AssertionError("Unexpected parameter count");
        }

        String[] sourceNames = {"firstName", "repeat"};

        for (int i = 0; i < params.length; i++) {
            if (!params[i].isNamePresent()) {
                throw new AssertionError(
                        "Missing -parameters at index " + i);
            }
            if (!sourceNames[i].equals(params[i].getName())) {
                throw new AssertionError(
                        "Unexpected parameter name at index " + i);
            }
        }

        System.out.println("parameter metadata present: "
                + Arrays.toString(sourceNames));
    }
}
~~~

Compile this test class into `probe` (in the same project directory):

~~~bash
javac --release 17 -d probe src/probe/ParameterMetadataAssertions.java
java -cp probe:with probe.ParameterMetadataAssertions
~~~

The last command is expected to print:

~~~text
parameter metadata present: [firstName, repeat]
~~~

If you replace `with` with `without`, the program must **fail** with `AssertionError` containing `Missing -parameters at index 0`. Do not include full stack traces in golden output because line numbers change when editing code.

In real projects, test the **JAR or compiled classes produced by the CI/deploy pipeline**, not just a manually compiled build. The test can run in CI to catch lost compiler flags when updating Maven/Gradle/IDE settings.

### 5.1. Why Check Both the Name and `isNamePresent()`?

A test checking only `getName()` against `"firstName"` catches the bug in this example, but does not distinguish cases where `arg0` is an actual source name. A test checking only `isNamePresent()` does not guarantee expected names survived refactoring. Therefore:

1. If "source names exist" is required, assert `isNamePresent()`.
2. If a binding contract mandates specific names, also assert `getName()` has the defined value.
3. If only signatures/identifying annotations are actually needed, **do not** introduce an unnecessary dependency on source parameter names.

### 5.2. Practical Test Matrix

| Test case | What to verify | Significance |
| --- | --- | --- |
| Build without `-parameters` | `isNamePresent() == false` in standard javac classes | Understand clear degrade/fail behavior |
| Build with `-parameters` | `true` and names match source | Pipeline preserves metadata accurately |
| `-g` without `-parameters` | Core reflection still cannot read source names | Do not confuse debug info with `MethodParameters` |
| `-parameters -g:none` | Names remain readable | Independent of debug info |
| Constructor | `Constructor.getParameters()` matches method behavior | Framework constructor injection/binding works |
| Method overloads | Look up using both name + `Class<?>[]` list | Avoid inspecting the wrong overload |
| Final packaged artifact | Inspect classes inside actual JAR/container | No drift between IDE, tests, and production |
| Tool-generated classes | Check `isImplicit()`, `isSynthetic()`, names | Do not assume source parameter names for implicit/synthetic parameters |

## 6. Project Configuration and Sources of Divergence

### 6.1. Maven

For Maven projects using `maven-compiler-plugin`, you can configure the compiler parameters property:

~~~xml
<!-- Snippet inside pom.xml, not a standalone pom.xml. -->
<properties>
    <maven.compiler.parameters>true</maven.compiler.parameters>
</properties>
~~~

Or configure the plugin explicitly:

~~~xml
<!-- Configuration snippet inside <plugins>, not a standalone pom.xml. -->
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-compiler-plugin</artifactId>
  <configuration>
    <parameters>true</parameters>
  </configuration>
</plugin>
~~~

Plugin/JDK versions and build profiles must be aligned across the project. After changing flags, run a **clean compilation** and test the real artifact, because stale `.class` files can remain in the output directory.

### 6.2. Gradle

With the Gradle Java plugin, configure `JavaCompile` tasks in **Groovy DSL**:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
~~~

This is a configuration snippet in `build.gradle`, not a runnable Java file. In multi-module builds, check every module that produces classes needing reflection, including modules holding DTOs or constructors used by frameworks. For Kotlin/Scala builds or code generators, `javac` flags are not enough to infer metadata of classes emitted by other compilers; inspecting the **final class file** is the only proof.

### 6.3. IDEs, Annotation Processors, Generators, and Bytecode Optimizers

- Compiling in an IDE can use different flags from CI, even for the same source code.
- Annotation processors/code generators produce their own classes; how those compilers/generators emit `MethodParameters` must be verified separately.
- Obfuscators/shrinkers/bytecode transformers can rename or strip name metadata; passing `-parameters` to `javac` is insufficient if a later pipeline stage transforms class files.
- Constructors of **inner classes, enums, records**, and **synthetic/bridge** methods can have compiler-generated parameters or special metadata rules. Do not mechanically apply conclusions about `arg0`/source names from a simple fixture to all members; check `Parameter.isImplicit()`, `isSynthetic()`, `getModifiers()`, and `isSynthetic()`/`isBridge()` on methods when relevant.

## 7. Limitations of Parameter Names at Runtime

### 7.1. `-parameters` Does Not Guarantee API Binding Always Works

Parameter names can change during source refactoring while the JVM signature stays identical. If an application relies on `firstName` to bind a request field, renaming it to `name` without updating the contract can break the API at runtime even though Java compiles cleanly.

Some frameworks support annotations specifying explicit names (e.g., framework annotations defining path/query field names). When a system needs stable API contracts, **reviewed explicit names** are usually more durable than inferring source names. Still, do not assume a framework always ignores `-parameters` when an annotation is present: read the contract of the framework version in use.

### 7.2. Methods with Annotations and Generics

- `Method.getParameterAnnotations()` and `Parameter.getAnnotations()` rely on annotation metadata, **not solely on `MethodParameters`**.
- `Executable.getGenericParameterTypes()` relies on generic `Signature` metadata (when present) and can be governed by type erasure and separate `Type` resolution.
- `getParameterTypes()` reads runtime parameter types from the method descriptor, so it still knows `String, int` even when source names are absent.
- Local variable names inside a method body are not added by `-parameters`: it is not a "keep all variable names" option for reflection.

### 7.3. Invalid Metadata Cases

`Executable.getParameters()` can throw `java.lang.reflect.MalformedParametersException` when the `MethodParameters` attribute in a class file is invalid. This differs from **missing** parameter names: for standard `javac` classes without `-parameters`, reflection synthesizes placeholder names and sets `isNamePresent() = false`, rather than treating the missing attribute as malformed bytecode.

In systems with plugins or classes generated by external tools, distinguish:

1. **No `MethodParameters`:** normally returns placeholder names; business logic requiring real names must reject or apply an explicit fallback.
2. **Valid `MethodParameters`:** verify names/order/kind per requirements.
3. **Corrupt `MethodParameters`:** treat as an artifact/build pipeline error; do not try to recover by guessing names from `arg0`.

## 8. Testing Checklist and Common Mistakes

**Checklist for tests or CI:**

1. Take **the exact same source**; build into two completely separate directories/JARs.
2. Create build A with `-g` but **without `-parameters`**, and build B with `-parameters -g:none`.
3. Do not place both versions of the **same fully-qualified class name** onto one classpath in the same JVM; use two runs or controlled isolated class loaders.
4. Inspect at least one method and one constructor with `getParameters()`.
5. Assert **`isNamePresent()` and `getName()`**; also verify `getParameterTypes()` and `getParameterCount()` to confirm signatures are intact.
6. Inspect with `javap -v -p`: compare `MethodParameters` directly against debug `LocalVariableTable`.
7. On CI, test the final artifact with the deployment flags/plugins and JDK version; after changing flags, run a clean build.
8. For framework binding, test both requests using contract names and cases missing metadata, rather than testing only a single sample method.
9. Avoid relying on fake `arg0` names as an API contract; for record/inner/synthetic constructors, verify their specific behavior.
10. When renaming parameters, regression-test data contracts and documentation, not only compilation.

**Self-check:**

- Why is `-g` not enough for `Parameter.isNamePresent()` to return true?
- Why does `Parameter.getName()` returning `arg0` not prove that name existed in source?
- Why should two `demo.Sample` classes with the same name but different compiler flags not share one classpath when running tests?
- What is the difference between `LocalVariableTable` and `MethodParameters`?
- Why can a name-binding framework break after renaming a parameter while the method signature remains unchanged?
- If `MalformedParametersException` appears, what should you investigate instead of merely adding `-parameters`?

### References

- Oracle JDK 21 — `javac` options, `-parameters`: https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html
- Oracle Java SE 21 — `Parameter`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Parameter.html
- Oracle Java SE 21 — `Executable`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Executable.html
- Oracle Java SE 21 — `MalformedParametersException`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/MalformedParametersException.html
- JVM Specification Java SE 21 — MethodParameters: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.7.24