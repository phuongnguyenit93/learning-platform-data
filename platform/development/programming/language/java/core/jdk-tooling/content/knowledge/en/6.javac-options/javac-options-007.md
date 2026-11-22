# Parameter metadata in Java and the `javac -parameters` option

## 1. What is parameter metadata?

Parameter metadata is the formal parameter name information of methods and constructors stored in the `.class` bytecode file. This information allows programs to read parameter names at runtime through Java Reflection, rather than only knowing the type and position of each parameter.

For example, with the declaration:

~~~java
public void createUser(String email, int age) {
    // ...
}
~~~

When the class is compiled with parameter name metadata, a reflection program can read the two names `email` and `age`. If the class does not contain this metadata, reflection typically only returns synthetic names such as `arg0` and `arg1`.

In the JDK, the compiler option used to record parameter names in the class file is `-parameters`:

~~~bash
javac -parameters UserService.java
~~~

This is an option for the **`javac` compiler**, not a runtime JVM option. Place it in the compilation command or build tool configuration so that the output class file contains parameter name information.

Parameter metadata is useful when frameworks or libraries need to map parameter names to external data, for example:

- Web frameworks mapping request parameters to method parameters.
- Dependency injection frameworks using parameter names to assist with dependency resolution.
- Data mapping libraries using constructor parameter names to instantiate objects.
- CLI or RPC tools using parameter names to generate clearer help, bindings, or error messages.
- Logging and tracing tools displaying parameter names when analyzing calls.

The ability to leverage metadata depends on the framework, its version, and its configuration. Some frameworks still require explicit annotations or configuration.

## 2. How does `-parameters` work?

When compiling Java, `javac` converts source code into bytecode and writes the class structure into a `.class` file. If `-parameters` is enabled, the compiler writes an additional `MethodParameters` attribute in the class file for the corresponding methods and constructors.

This attribute stores the name and certain flags of each parameter. The JVM Reflection API can read that information when the class is loaded.

Process:

~~~text
Source code
    |
    | javac -parameters
    v
Class file (.class)
    |
    | contains MethodParameters
    v
Class loader loads class
    |
    | Reflection API
    v
Parameter.getName() -> source parameter name
~~~

If `-parameters` is not enabled, the compiler still produces bytecode that runs normally. Programs can still invoke methods, pass arguments in the correct order, and use reflection to retrieve parameter types. The difference is that source parameter names are generally not present in the metadata available to the Reflection API.

`-parameters` does not change:

- The method signature at the JVM level (method descriptor).
- The order or types of parameters.
- Overload rules or how methods are invoked.
- The values passed into methods.
- The runtime execution behavior of the program.

It adds metadata to the class file, which can slightly increase file size and makes parameter names observable information at runtime.

## 3. Reading parameter names with Java Reflection

Java Reflection provides the `java.lang.reflect.Parameter` class to represent a parameter of a method or constructor. You can retrieve the list of parameters from `Executable`, the common superclass of `Method` and `Constructor`.

Commonly used APIs:

| API | Meaning |
|---|---|
| `Executable.getParameters()` | Retrieves parameters in declaration order. |
| `Parameter.getName()` | Returns the parameter name; if no name is stored, typically returns a synthetic name such as `arg0`. |
| `Parameter.isNamePresent()` | Indicates whether the parameter name is stored in the class file for reflection to use. |
| `Parameter.getType()` | Retrieves the declared type of the parameter. |
| `Parameter.getModifiers()` | Retrieves the modifiers applied to the parameter, if any. |
| `Parameter.isImplicit()` | Checks whether the parameter was implicitly added by the compiler. |
| `Parameter.isSynthetic()` | Checks whether the parameter was marked synthetic by the compiler. |

Always check `isNamePresent()` before treating `getName()` as a meaningful name from the source code. A value of `arg0` does not prove that the author named the parameter `arg0`.

## 4. Runnable example: comparing with and without `-parameters`

Create the file `src/ParameterMetadataDemo.java`:

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

public class ParameterMetadataDemo {

    public void greet(String recipient, int repeat) {
        // Method used to demonstrate metadata.
    }

    public static void main(String[] args) throws Exception {
        Method method = ParameterMetadataDemo.class.getDeclaredMethod(
                "greet", String.class, int.class);

        System.out.println("method=" + method.getName());

        for (Parameter parameter : method.getParameters()) {
            System.out.printf(
                    "name=%s, present=%s, type=%s%n",
                    parameter.getName(),
                    parameter.isNamePresent(),
                    parameter.getType().getSimpleName());
        }
    }
}
~~~

Create two separate output directories to compare:

~~~bash
mkdir -p out-with out-without
~~~

### Compile with metadata

~~~bash
javac --release 17 -parameters -d out-with src/ParameterMetadataDemo.java
java -cp out-with ParameterMetadataDemo
~~~

Stdout:

~~~text
method=greet
name=recipient, present=true, type=String
name=repeat, present=true, type=int
~~~

### Compile without metadata

~~~bash
javac --release 17 -d out-without src/ParameterMetadataDemo.java
java -cp out-without ParameterMetadataDemo
~~~

Stdout:

~~~text
method=greet
name=arg0, present=false, type=String
name=arg1, present=false, type=int
~~~

Both builds run the same logic and have the same method signature. The first build can read the source names because it was compiled with `-parameters`; the second build does not have parameter names in reflection metadata, so `isNamePresent()` returns `false`.

On Windows PowerShell, you can create the directories with:

~~~powershell
New-Item -ItemType Directory -Force out-with, out-without | Out-Null
javac --release 17 -parameters -d out-with src/ParameterMetadataDemo.java
java -cp out-with ParameterMetadataDemo
javac --release 17 -d out-without src/ParameterMetadataDemo.java
java -cp out-without ParameterMetadataDemo
~~~

If you re-run the compilation command into the same output directory after changing options, you should delete or recreate the output directory first. Otherwise, old class files may remain and make the verification results confusing.

## 5. Inspecting bytecode with `javap`

`javap` is the disassembler tool included with the JDK. The `-v` or `-verbose` option displays detailed attributes in the class file; `-p` displays private members as well.

Inspect the build with metadata:

~~~bash
javap -v -p -classpath out-with ParameterMetadataDemo
~~~

In the `greet` method declaration section, the output contains a `MethodParameters` entry with the parameter names `recipient` and `repeat`. The build without `-parameters` enabled typically does not have a `MethodParameters` entry containing those source names.

You can filter the output on Linux/macOS:

~~~bash
javap -v -p -classpath out-with ParameterMetadataDemo | grep -A4 MethodParameters
~~~

On PowerShell:

~~~powershell
javap -v -p -classpath out-with ParameterMetadataDemo | Select-String -Pattern "MethodParameters" -Context 0,4
~~~

This is a useful way to inspect actual artifacts in CI or released JARs, especially when the source project specifies `-parameters` but the build pipeline might not apply the option to all modules.

## 6. Distinguishing `-parameters` from debug information `-g`

A common misconception is assuming that simply enabling debug information with `-g` will let the Reflection API know parameter names. These two types of information serve different purposes.

| Option | Data written | Purpose |
|---|---|---|
| `-parameters` | Parameter names in the `MethodParameters` attribute. | Allows the Reflection API to read parameter names via `Parameter.getName()` and check via `isNamePresent()`. |
| `-g` | Debug information such as line numbers, local variables, and source file. | Supports debuggers and bytecode analysis tools. |
| `-g:vars` | Local variable information in `LocalVariableTable`. | Supports debuggers in viewing local variable names and their scopes. |
| `-g:none` | Does not write the debug information groups controlled by this option. | Reduces debug data in the artifact. |

`LocalVariableTable` and `MethodParameters` are different class file attributes. Having variable names in the debug table does not mean `Parameter.isNamePresent()` will return `true`.

If an application or framework needs parameter names via Java Reflection, enable `-parameters` explicitly. Both can be combined:

~~~bash
javac --release 17 -parameters -g -d out src/ParameterMetadataDemo.java
~~~

## 7. Applying to constructors and method overloads

`-parameters` is useful for both method and constructor parameters. To read constructor parameter names, use `Constructor.getParameters()` similarly to `Method`.

Example:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Parameter;

public class User {
    private final String email;
    private final int age;

    public User(String email, int age) {
        this.email = email;
        this.age = age;
    }

    public static void main(String[] args) throws Exception {
        Constructor<User> constructor =
                User.class.getConstructor(String.class, int.class);

        for (Parameter parameter : constructor.getParameters()) {
            System.out.println(
                    parameter.getName() + ": " + parameter.isNamePresent());
        }
    }
}
~~~

Compile:

~~~bash
javac --release 17 -parameters -d out User.java
java -cp out User
~~~

Stdout:

~~~text
email: true
age: true
~~~

With method overloads, select the exact method by name and parameter type list. Do not search by name alone because there may be multiple methods with the same name.

~~~java
Method method = UserService.class.getDeclaredMethod(
        "find", String.class, int.class);
Parameter[] parameters = method.getParameters();
~~~

Parameter names are stored in declaration order. `-parameters` does not change how Java distinguishes overloads; selecting a method via reflection still relies on the method name and parameter types.

## 8. Are parameter names part of the method signature?

Parameter names are not part of the method descriptor that the JVM uses to distinguish methods. For example, the following two declarations have the same method name and parameter type:

~~~java
public void update(String email) { }
public void update(String address) { }
~~~

These are not two valid overloads because parameter names do not make method signatures different. Parameter types and order are what determine overloads.

Therefore, enabling `-parameters` does not change bytecode method linking rules. However, the recorded names can affect frameworks or libraries that use reflection to map data by name. Thus, if a framework depends on parameter names, renaming them in source code can change binding behavior even though the method descriptor remains the same.

For public APIs, consider parameter names as part of the framework user experience. If names must remain stable across internal refactorings, you can use explicit annotations or configuration supported by the framework instead of relying solely on source names.

## 9. Integrating `-parameters` with Maven

With the Maven Compiler Plugin, you can enable parameter metadata by configuring `<parameters>true</parameters>`. Example plugin section in `pom.xml`:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <release>17</release>
                <parameters>true</parameters>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

`<parameters>true</parameters>` instructs the compiler to write parameter names into the class file. `<release>17</release>` sets the target Java 17 API and bytecode.

In real projects, you should declare the project-approved Maven Compiler Plugin version and manage it centrally in `pluginManagement` if there are multiple modules. For multi-module Maven builds, verify that the configuration applies to each module producing class files that the framework needs to read.

After building, you can inspect the artifact:

~~~bash
mvn clean compile
javap -v -p -classpath target/classes com.example.ParameterMetadataDemo
~~~

Replace the class name in the `javap` command with the actual package and class of your project.

## 10. Integrating `-parameters` with Gradle

In Gradle Groovy DSL (`build.gradle`), add the compiler option to all `JavaCompile` tasks:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

In Gradle Kotlin DSL (`build.gradle.kts`):

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

If the project has multiple source sets or modules, configure it at the appropriate build level so that all relevant compilation tasks receive the option. You can inspect the compiler command in the build logs or run `javap -v` on the output class files.

Do not add the option to a test runtime task expecting it to change already compiled classes. Metadata must be generated during the compile phase of the classes that need introspection.

## 11. When should you enable it and when should you check?

You should enable `-parameters` when:

- A framework needs to infer method or constructor parameter names.
- A reflection library uses parameter names to map data.
- An application wants to generate error messages, documentation, or help tools from API signatures.
- A dependency explicitly requires parameter metadata.

You may not need to enable it if the application does not use parameter names at runtime. For libraries distributed to third parties, check the requirements of the target framework and decide on a consistent build policy.

When debugging a name-based binding issue, check in order:

1. Was the actual class file compiled with `-parameters`?
2. Is the right class file or JAR being loaded at runtime?
3. Does `Parameter.isNamePresent()` return `true`?
4. Is the framework using the right method/constructor and the right library version?
5. Does the framework require additional annotations or configuration?
6. Is there any obfuscation, shading, bytecode enhancement, or packaging step that strips or alters metadata?

An external dependency does not automatically get parameter names just because your application is built with `-parameters`. The option must be applied when compiling the exact class containing the method or constructor that the framework wants to introspect.

## 12. Common issues

| Symptom | Cause | Solution |
|---|---|---|
| `getName()` returns `arg0`, `arg1` | The class file lacks parameter names for reflection. | Recompile that class with `javac -parameters`. |
| `isNamePresent()` returns `false` | `MethodParameters` is not present in the loaded class file. | Check compiler options and run `javap -v` on the exact artifact. |
| `-g` is enabled but reflection still returns `arg0` | Debug local-variable metadata does not replace `MethodParameters`. | Enable `-parameters` separately. |
| Local build has names but CI does not | A build task or module on CI is not receiving the option. | Check the actual `javac` command and Maven/Gradle configuration for all relevant compile tasks. |
| Source has new names but runtime shows old names | The JVM is loading an old class file/JAR or a duplicate dependency. | Clean build, check the classpath/module path and the location from which the class is loaded. |
| Some parameters have special status | The compiler or language may generate implicit/synthetic parameters. | Check `isImplicit()`, `isSynthetic()`, and the corresponding constructor/method signature. |
| Framework still fails to bind even though `isNamePresent()` is `true` | The framework has its own binding rules or annotations. | Check the framework documentation and the configuration/annotations of the endpoint or constructor. |

## 13. Release checklist

- Confirmed whether frameworks or libraries need parameter names at runtime.
- `javac` receives `-parameters` when compiling classes that need introspection.
- Maven/Gradle configuration applies to the right modules and source sets.
- Verified `Parameter.isNamePresent()` on the built artifact.
- Used `javap -v` to confirm `MethodParameters` in the class file.
- Did not confuse `-parameters` with `-g` or `LocalVariableTable`.
- Inspected the final JAR after shading, obfuscation, or bytecode transformation steps.
- If parameter names are part of the binding contract, tests exist to detect unintended renames.

`-parameters` is a small compiler option with significant impact for reflection-based systems. Enable it at the class file generation step, verify it with `Parameter.isNamePresent()` and `javap -v`, and test the actual framework binding behavior.
