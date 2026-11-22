# Debug Information in Java Class Files

## 1. What is debug information?

Debug information is optional metadata written by the compiler into `.class` bytecode files so that debuggers and analysis tools can map bytecode back to source code. With this information, developers can set line breakpoints, inspect local variable names, track variable scopes, and read stack traces with clear source locations.

Java code can still run when a class file contains no debug information. The JVM does not need local variable names or source line numbers to execute bytecode. This information primarily supports development, testing, and troubleshooting.

Common categories of debug information include:

- The source file name used to compile the class.
- Mappings between bytecode instruction positions and source line numbers.
- Names, types, and live scopes of local variables.
- Generic signatures of local variables when generic types are erased at runtime.

In Java, debug information is controlled mainly through `javac` compiler options: `-g`, `-g:none`, and `-g:<options>`. These are compile-time options; adding JVM options at runtime cannot recover information that was not written into the class file.

## 2. Where is debug information stored in a class file?

A Java class file consists of a header, constant pool, class declaration, fields, methods, and attributes. Debug information is stored in optional attributes at the class level or inside the `Code` attribute of each method.

| Attribute | Location | Information Stored |
|---|---|---|
| `SourceFile` | Class level | Name of the source file used to compile the class. |
| `LineNumberTable` | Inside a method's `Code` attribute | Mapping between bytecode offsets and source line numbers. |
| `LocalVariableTable` | Inside a method's `Code` attribute | Local variable name, JVM type descriptor, slot, and the bytecode range where the variable is valid. |
| `LocalVariableTypeTable` | Inside a method's `Code` attribute | Generic signature of a local variable when the full type cannot be represented by a standard JVM descriptor. |

These attributes are optional. The compiler may emit a subset of them or omit them depending on configuration.

### `SourceFile`

`SourceFile` stores the source file name, such as `DebugInfoDemo.java`. It does not embed the full source code in the class file and typically does not store the full path to the project directory.

A debugger needs the corresponding source code on the machine where debugging is performed to display source lines. If only the class file is available without matching source, the debugger may know the file name and line number but cannot display the actual source code.

### `LineNumberTable`

`LineNumberTable` associates bytecode offsets with line numbers in the source file. A single Java line can compile into multiple bytecode instructions; the compiler records mapping entries so a debugger can pause at the position corresponding to a source line.

This information also enables the JVM to display line numbers in stack traces. If a class file lacks line mappings, stack traces may omit specific line numbers or show `Unknown Source` depending on what information remains.

### `LocalVariableTable`

`LocalVariableTable` stores local variable information, typically including:

- `Start`: bytecode offset where the variable's scope begins.
- `Length`: length of the bytecode range in which the variable remains valid.
- `Slot`: index storing the variable in the frame's local-variable array.
- `Name`: variable name in the source code.
- `Signature`: type descriptor in JVM format, such as `I` for `int`, or `Ljava/lang/String;` for `String`.

A variable may exist only within part of a method. Therefore, a debugger only displays the variable when the current execution point falls within the recorded range. A variable that is out of scope or not yet initialized may not appear as expected.

### `LocalVariableTypeTable`

Java generics use type erasure. For example, `List<String>` typically has the JVM descriptor `Ljava/util/List;`, which is identical to `List<Integer>` after type arguments are erased.

`LocalVariableTypeTable` can store a generic signature such as `Ljava/util/List<Ljava/lang/String;>;` so debuggers and bytecode tools know the variable's original generic type. This attribute supplements `LocalVariableTable`; it does not change the runtime type of the object.

## 3. `javac` debug options

`javac` supports three main ways to configure debug output:

| Option | Result |
|---|---|
| `-g` not specified | By default, the compiler generates source file name and line number information (`source`, `lines`); it does not include local variable names. |
| `-g` | Emits all debug information categories supported by the compiler: `source`, `lines`, and `vars`. |
| `-g:none` | Emits none of the debug information categories controlled by `-g`. |
| `-g:source` | Emits only the source file name. |
| `-g:lines` | Emits only line number mappings. |
| `-g:vars` | Emits only local variable information. |
| `-g:source,lines` | Emits the source file name and line number mappings. |
| `-g:source,lines,vars` | Emits all three categories. |

With default settings, `javac` typically writes `SourceFile` and `LineNumberTable` so stack traces include line numbers. If you need a debugger to inspect local variable names, enable `-g` or `-g:vars`.

Examples:

~~~bash
# All debug information
javac --release 17 -g -d out src/DebugInfoDemo.java

# Only source and line information
javac --release 17 -g:source,lines -d out src/DebugInfoDemo.java

# Only local variable information
javac --release 17 -g:vars -d out src/DebugInfoDemo.java

# No debug information
javac --release 17 -g:none -d out src/DebugInfoDemo.java
~~~

`-g` does not mean enabling a JVM debug mode at runtime. It instructs the compiler to include extra metadata in the compiled artifact upfront.

## 4. Runnable example: comparing classes with and without debug information

Create `src/DebugInfoDemo.java`:

~~~java
import java.util.List;

public class DebugInfoDemo {
    public static void main(String[] args) {
        List<String> names = List.of("Ada", "Linus");
        int count = names.size();
        System.out.println(names.get(0) + ":" + count);
    }
}
~~~

Create two separate output directories and compile:

~~~bash
mkdir -p out-debug out-no-debug

# Build with full debug information
javac --release 17 -g -d out-debug src/DebugInfoDemo.java

# Build without debug information
javac --release 17 -g:none -d out-no-debug src/DebugInfoDemo.java
~~~

Run the build with debug information:

~~~bash
java -cp out-debug DebugInfoDemo
~~~

Stdout:

~~~text
Ada:2
~~~

Run the build without debug information:

~~~bash
java -cp out-no-debug DebugInfoDemo
~~~

Stdout:

~~~text
Ada:2
~~~

Both builds execute the same logic and produce the same output. The difference lies in the class file metadata: the `-g` build includes line number and local variable tables, while the `-g:none` build omits those debug attributes.

On Windows PowerShell, you can create the output directories with:

~~~powershell
New-Item -ItemType Directory -Force out-debug, out-no-debug | Out-Null
javac --release 17 -g -d out-debug src/DebugInfoDemo.java
javac --release 17 -g:none -d out-no-debug src/DebugInfoDemo.java
java -cp out-debug DebugInfoDemo
java -cp out-no-debug DebugInfoDemo
~~~

Use separate output directories when comparing configurations. Recompiling into the same directory without cleaning old class files can leave stale artifacts that do not reflect the latest options.

## 5. Inspecting debug information with `javap`

`javap` is the JDK disassembler tool. The `-v` (`-verbose`) option displays class file attributes; `-l` displays line number and local variable tables; `-p` also shows private members.

Inspect the build with debug information:

~~~bash
javap -v -l -classpath out-debug DebugInfoDemo
~~~

In the output, look for these attributes:

~~~text
SourceFile: "DebugInfoDemo.java"

LineNumberTable:
  ...

LocalVariableTable:
  ...

LocalVariableTypeTable:
  ...
~~~

The `...` above represents the detailed entries printed by `javap`; the exact bytecode offsets, line numbers, slots, and ranges depend on the source code and compiler version.

Inspect the build without debug information:

~~~bash
javap -v -l -classpath out-no-debug DebugInfoDemo
~~~

This build does not contain `SourceFile`, `LineNumberTable`, `LocalVariableTable`, or `LocalVariableTypeTable` generated by `javac`'s debug options.

You can view only the line/local-variable tables with:

~~~bash
javap -l -classpath out-debug DebugInfoDemo
~~~

Or filter on Linux/macOS:

~~~bash
javap -v -l -classpath out-debug DebugInfoDemo | grep -E "SourceFile|LineNumberTable|LocalVariableTable|LocalVariableTypeTable"
~~~

On PowerShell:

~~~powershell
javap -v -l -classpath out-debug DebugInfoDemo | Select-String -Pattern "SourceFile|LineNumberTable|LocalVariableTable|LocalVariableTypeTable"
~~~

This is how you verify actual artifacts in the build directory or in a release JAR. Do not rely solely on Maven/Gradle configuration, because an individual module or compilation task might use different options.

## 6. How does a debugger use this information?

Debuggers rely on mappings between source code and bytecode to provide a smooth debugging experience:

- **Line breakpoints:** `LineNumberTable` lets the debugger determine the bytecode offset corresponding to a source line.
- **Step over / step into:** line information lets the debugger control execution steps by source position.
- **Variables view:** `LocalVariableTable` provides local variable names, types, and scopes.
- **Generic type display:** `LocalVariableTypeTable` helps display type arguments such as `String` in `List<String>`.
- **Stack traces:** `SourceFile` and `LineNumberTable` support displaying file names and line numbers when an exception occurs.

Some practical limitations:

- The debugger needs the exact source version matching the class file. Source modified after the build can cause displayed lines to mismatch the bytecode.
- Variables only appear within their recorded scopes; variables out of scope or not yet assigned may not be shown.
- The compiler may generate synthetic variables or internal implementation variables; not every entry in bytecode corresponds to a developer-declared variable.
- The JIT compiler can optimize code at runtime. Modern debuggers coordinate with the JVM to support debugging, but variable values at certain points may still be unavailable or differ from what the source code suggests.
- When remote debugging, matching source must be available on the debugger machine or configured via source lookup.

## 7. Distinguishing debug information from `-parameters`

`-g` and `-parameters` serve two different purposes and can be enabled independently.

| Aspect | `-g` | `-parameters` |
|---|---|---|
| Purpose | Debuggers and bytecode analysis tools. | Java Reflection reading method/constructor parameter names. |
| Main attributes | `SourceFile`, `LineNumberTable`, `LocalVariableTable`, `LocalVariableTypeTable`. | `MethodParameters`. |
| How it is read | Debugger or `javap`. | `Executable.getParameters()` and `Parameter.getName()`. |
| Impact when missing | Harder to set line breakpoints, inspect variables, and trace source. | Reflection usually lacks source parameter names; `Parameter.isNamePresent()` returns `false`. |
| Compiler option | `-g`, `-g:none`, `-g:...`. | `-parameters`. |

`LocalVariableTable` can contain parameter names as variable entries inside a method, but that does not replace `MethodParameters`. The Java Reflection API uses `MethodParameters` to determine formal parameter names.

They can be combined:

~~~bash
javac --release 17 -g -parameters -d out src/DebugInfoDemo.java
~~~

You can also disable debug information while keeping parameter names for reflection:

~~~bash
javac --release 17 -g:none -parameters -d out src/DebugInfoDemo.java
~~~

In the second case, `javap -v` can still show `MethodParameters`, while debug attributes such as `SourceFile`, `LineNumberTable`, and `LocalVariableTable` are omitted. If a framework needs parameter names at runtime, enable `-parameters` for the classes that the framework inspects.

## 8. Distinguishing debug attributes from other class file metadata

Not every attribute in a class file is debug information.

- `StackMapTable` contains stack map frames used for bytecode verification and type checking; it is not a line number table or local variable table.
- `MethodParameters` stores name and flag metadata for method/constructor parameters; it is controlled by `-parameters`.
- `RuntimeVisibleAnnotations` and `RuntimeInvisibleAnnotations` store annotations according to their retention policy; they serve reflection or annotation processors, not debug information.
- `Signature` stores generic signatures for classes, fields, or methods; it is not `LocalVariableTypeTable`.

Therefore, `javac -g:none` does not strip all metadata from a class file. It removes the debug information categories controlled by debug options; the class file still requires structures and attributes needed for linking, verification, and bytecode execution.

## 9. Integrating debug information with Maven

With the Maven Compiler Plugin, you can enable debug information using the `debug` configuration and select categories via `debuglevel`.

Example in `pom.xml`:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <release>17</release>
                <debug>true</debug>
                <debuglevel>source,lines,vars</debuglevel>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

`debug=true` enables debug information generation; `debuglevel` selects the `source`, `lines`, and `vars` categories. When strict artifact control is needed, check the plugin version and the actual compiler command in the build logs.

After building:

~~~bash
mvn clean compile
javap -v -l -classpath target/classes com.example.DebugInfoDemo
~~~

Replace `com.example.DebugInfoDemo` with the fully qualified class name in your project.

## 10. Integrating debug information with Gradle

In Gradle Groovy DSL (`build.gradle`):

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.debug = true
    options.debugOptions.debugLevel = "source,lines,vars"
}
~~~

In Gradle Kotlin DSL (`build.gradle.kts`):

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.isDebug = true
    options.debugOptions.debugLevel = "source,lines,vars"
}
~~~

This configuration applies to matching `JavaCompile` tasks in the build. In multi-module or multi-source-set projects, verify that the task compiling the classes being debugged actually receives this configuration.

You can inspect the built class files using `javap -v -l`. Do not confuse enabling debugging on a test runtime task with generating debug information: the metadata must be written into the class file during compilation.

## 11. Choosing configurations for development and release

In development environments, keep line and variable information to support breakpoints, stepping, and variable inspection. `-g` is usually convenient because it emits all three categories.

In production environments, the choice depends on operational needs:

- If you need line numbers in stack traces, keep `source` and `lines`.
- If you need deep diagnostics with a debugger or variable inspection tools, also keep `vars`.
- If you need to reduce metadata in artifacts, consider `-g:none` after evaluating the impact on diagnostics.
- If a framework needs parameter names via reflection, enable `-parameters` independently of debug options.

Debug information does not store runtime variable values and does not replace logs, metrics, tracing, or core dumps. It helps tools understand locations and names in bytecode; observing process state still depends on the JVM, debugger, and runtime permissions.

Class files can expose variable names, file names, and internal code structure. Avoid putting secrets, tokens, or sensitive data in variable names, package names, or build paths. Omitting debug information is also not a source-code protection mechanism; bytecode can still be reverse-engineered.

## 12. Common issues and troubleshooting

| Symptom | Common Cause | Resolution |
|---|---|---|
| Line breakpoints do not work as expected | Missing `LineNumberTable` or debugger is using a different source version. | Compile with `-g:lines` or `-g`, and verify the source matches the build. |
| Stack trace shows `Unknown Source` | Class file lacks appropriate source/line information. | Keep `SourceFile` and `LineNumberTable` when building artifacts that need diagnostics. |
| Variables view has no local variable names | Class file lacks `LocalVariableTable`. | Compile with `-g:vars` or `-g`. |
| Generic type of a variable is not shown | Missing `LocalVariableTypeTable` or compiler did not emit the required generic signature. | Use `-g:vars`/`-g` and verify with `javap -v -l`. |
| Local build has debug info but CI does not | Different tasks or modules use different compiler configurations. | Check the actual `javac` command and configure all relevant compile tasks. |
| `javap` still shows metadata when using `-g:none` | The class file still contains non-debug attributes, such as `MethodParameters` or `StackMapTable`. | Distinguish debug attributes from metadata used for reflection and bytecode verification. |
| Debugger shows wrong lines or source | Current source file does not match the built artifact. | Check out the source matching the commit/build and verify classpath/module path. |
| `-g` is enabled but Reflection has no parameter names | Confusing `LocalVariableTable` with `MethodParameters`. | Enable `-parameters` if Reflection needs parameter names. |

A short verification workflow:

1. Identify the actual class file loaded by the application.
2. Run `javap -v -l` on that exact class file or JAR.
3. Check `SourceFile`, `LineNumberTable`, `LocalVariableTable`, and `LocalVariableTypeTable`.
4. Check the `javac` options or build tool configuration.
5. Verify that the source code used for debugging matches the artifact.
6. If reflection parameter names are needed, separately verify `MethodParameters` and `-parameters`.

## 13. Pre-release checklist

- Debug requirements have been determined for development, testing, and production environments.
- `-g` or `-g:source,lines,vars` is used if full debug information is required.
- `SourceFile` and `LineNumberTable` are kept if line-numbered stack traces are needed.
- `LocalVariableTable` and `LocalVariableTypeTable` are kept if debuggers need local variable names and generic types.
- `-g` is not confused with `-parameters`.
- Final class files/JARs have been verified with `javap -v -l`.
- Source code used for debugging matches the artifact version.
- Maven/Gradle configuration has been checked across all required modules and source sets.
- Stripping debug information is not relied upon as a secret-protection mechanism or a substitute for logging/monitoring.

Debug information bridges bytecode and source code for effective debugging. Choose `-g` or `-g:...` groups based on your needs, verify attributes with `javap`, and enable `-parameters` separately if a framework requires parameter names via Reflection.
