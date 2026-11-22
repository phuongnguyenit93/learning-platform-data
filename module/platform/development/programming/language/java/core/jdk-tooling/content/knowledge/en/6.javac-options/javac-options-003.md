# Debug Information in Java Class Files

When compiling Java source code, `javac` can embed additional debugging metadata into class files. This metadata helps debuggers map bytecode back to source lines, display local variable names, and determine execution positions when setting breakpoints.

The key option is `-g`. You can select specific types of information with `-g:source,lines,vars` or disable it completely with `-g:none`. Understanding these options helps you investigate why breakpoints do not align with source lines, why a debugger does not show variable names, or why one build is harder to debug than another.

## 1. What is debug metadata?

A Java class file contains bytecode and metadata for the JVM to load, link, and execute the class. Some metadata only serves development tools and debuggers, and is not required for normal runtime logic.

Common types of debug information:

| Information | Purpose |
|---|---|
| Source file | Records the source file name associated with the class, typically via the `SourceFile` attribute |
| Line numbers | Maps bytecode offsets to source line numbers, via `LineNumberTable` |
| Local variables | Records names, types, slots, and scopes of local variables, via `LocalVariableTable` |
| Generic local variable signatures | Adds generic type information for local variables when present, via `LocalVariableTypeTable` |

Debug metadata is not a copy of the Java source code. `SourceFile` usually records only the file name, and `LineNumberTable` stores line mappings; the actual source code still needs to be accessed separately by the debugger or IDE if you want to view its contents.

The JVM can run a class file even if most debug metadata is missing. The bytecode and execution rules are still there; debug information simply makes it easier for humans and tools to inspect the program.

## 2. The javac -g option

`javac` supports the following main forms:

| Command | Information generated |
|---|---|
| `javac -g ...` | All debug information supported by the compiler, including source, line, and local variables |
| `javac -g:source,lines,vars ...` | Explicitly specifies all three groups of information |
| `javac -g:source,lines ...` | Source file name and line mappings, without requiring a local-variable table |
| `javac -g:lines ...` | Line number information |
| `javac -g:vars ...` | Local variable information |
| `javac -g:none ...` | Generates no debug information |

If `-g` is not specified, `javac` generates line number and source file name information by default, but not local variable information. Therefore, when you need to inspect variable names and values in a debugger, compile with `-g` or at least `-g:vars`.

Group names are comma-separated: `source`, `lines`, and `vars`. You can check the help output of your current compiler with:

~~~sh
javac -help
~~~

`-g` is a compiler option passed to the `javac` command. It is not a `java` runtime option; do not pass `-g` when running the application.

## 3. Example of a class with variables to debug

Create `src/com/example/DebugInfoDemo.java`:

~~~java
package com.example;

public class DebugInfoDemo {
    public static void main(String[] args) {
        String message = "Debug metadata";
        int first = 20;
        int second = 22;
        int total = add(first, second);

        System.out.println(message + ": " + total);
    }

    private static int add(int left, int right) {
        int result = left + right;
        return result;
    }
}
~~~

The example has local variables `message`, `first`, `second`, `total`, as well as parameters and the `result` variable in the `add` method. These are useful values to inspect when setting breakpoints and stepping through code.

Create the output directory and compile with full debug metadata:

~~~sh
mkdir -p out
javac -g -d out src/com/example/DebugInfoDemo.java
~~~

On PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -g -d out src/com/example/DebugInfoDemo.java
~~~

Run the application:

~~~sh
java -cp out com.example.DebugInfoDemo
~~~

Stdout output:

~~~text
Debug metadata: 42
~~~

If compilation succeeds, the class file is created at `out/com/example/DebugInfoDemo.class`. The `out` directory is the classpath root; do not use `out/com/example` as the classpath when running the fully qualified name `com.example.DebugInfoDemo`.

## 4. Inspecting metadata with javap

`javap` is the JDK disassembler tool, which can display class file structure and debug attributes.

Use the `-l` option to view line number and local variable information:

~~~sh
javap -classpath out -l -p com.example.DebugInfoDemo
~~~

Options:

- `-classpath out` specifies the location of the class file to read.
- `-l` prints line number and local variable tables.
- `-p` shows non-public members as well.

For a class compiled with `-g`, the output for methods will contain `LineNumberTable` and `LocalVariableTable`. The exact line numbers depend on source layout and the compiler; what matters is confirming that the corresponding tables appear.

To view full class file details and attributes:

~~~sh
javap -classpath out -v com.example.DebugInfoDemo
~~~

In the verbose output, look for `SourceFile`, `LineNumberTable`, `LocalVariableTable`, or `LocalVariableTypeTable` depending on the class contents.

If a class is compiled without local variable information, `javap -l` may still show the line table without `LocalVariableTable`. This is a sign that you should check your compiler options or build configuration.

## 5. Comparing debug levels

You can compile the same source into different directories to see the differences:

~~~sh
mkdir -p out-default out-full out-lines out-none

# Default: source and line information
javac -d out-default src/com/example/DebugInfoDemo.java

# All debug information
javac -g -d out-full src/com/example/DebugInfoDemo.java

# Only source and line information
javac -g:source,lines -d out-lines src/com/example/DebugInfoDemo.java

# No debug information
javac -g:none -d out-none src/com/example/DebugInfoDemo.java
~~~

On Windows PowerShell, you can create the directories in one command:

~~~powershell
New-Item -ItemType Directory -Force out-default,out-full,out-lines,out-none | Out-Null
javac -d out-default src/com/example/DebugInfoDemo.java
javac -g -d out-full src/com/example/DebugInfoDemo.java
javac -g:source,lines -d out-lines src/com/example/DebugInfoDemo.java
javac -g:none -d out-none src/com/example/DebugInfoDemo.java
~~~

Inspect each build:

~~~sh
javap -classpath out-default -l -p com.example.DebugInfoDemo
javap -classpath out-full -l -p com.example.DebugInfoDemo
javap -classpath out-lines -l -p com.example.DebugInfoDemo
javap -classpath out-none -l -p com.example.DebugInfoDemo
~~~

You can compare them as follows:

| Build | Source/line info | Local variable info |
|---|---|---|
| Default | Yes | No |
| `-g` | Yes | Yes |
| `-g:source,lines` | Yes | No |
| `-g:none` | No | No |

These options affect metadata in the class file. They do not change the logical result of the example at runtime; all four builds will print `Debug metadata: 42`.

## 6. Using debug information in debuggers and IDEs

When a debugger pauses at a breakpoint, it needs to map the bytecode position to a source line. `LineNumberTable` supports this. When you want to see local variable names in the Variables window or list locals with a command, `LocalVariableTable` provides the variable's name, type, slot, and scope.

With the example compiled using `-g`, you can run the command-line debugger:

~~~sh
jdb -classpath out com.example.DebugInfoDemo
~~~

At the `jdb` prompt, you can use basic commands:

~~~text
stop in com.example.DebugInfoDemo.main
run
locals
step
where
cont
exit
~~~

`stop in` sets a breakpoint at the method; `run` starts the program; `locals` prints local variables in the current frame; `step` executes the next line; `where` displays the call stack; `cont` resumes execution.

In IntelliJ IDEA, Eclipse, or another IDE:

1. Run the **Debug** configuration instead of running the application normally.
2. Set a breakpoint on an executable line in the source.
3. Verify that the IDE is using the exact class files built from the current source.
4. Use Step Over, Step Into, Variables, and Watches to observe state.
5. If variables have no names or breakpoints jump to the wrong lines, check the debug metadata and whether the source matches the class files.

If stale class files remain after the source has changed, the debugger may display mismatched lines or variables. Rebuild the right module and verify the output directory and classpath actually used by the application. If multiple versions of the same class exist on the classpath, the JVM may load a different one from what the IDE has open.

## 7. Distinguishing debug metadata from -parameters

The `-parameters` option also stores method parameter names in the class file, but it serves a different purpose from `-g`.

- `-g` and `-g:vars` provide local variable information for debuggers.
- `-parameters` stores formal parameter names so reflection can query them via the `java.lang.reflect.Parameter` API.

For example, a framework using reflection might call `Parameter.getName()`. If the class was not compiled with `-parameters`, the parameter name may just be a synthetic name such as `arg0`, and `isNamePresent()` returns `false`.

You can combine both options:

~~~sh
javac -g -parameters -d out src/com/example/DebugInfoDemo.java
~~~

`-parameters` does not replace `-g`; conversely, `-g` does not guarantee that parameter names will be available through reflection.

## 8. Debug metadata and remote debugging are two different things

Compiling with `-g` only adds information to the class file. It does not enable a debugger, open a network port, or make the JVM wait for an IDE to connect.

To allow a debugger to attach to a JVM over JDWP, you must configure the agent at runtime. For example, listening only on the local machine's loopback interface:

~~~sh
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -cp out com.example.DebugInfoDemo
~~~

Where:

- `transport=dt_socket` selects socket-based transport.
- `server=y` tells the JVM to wait for an incoming debugger connection.
- `suspend=n` allows the application to start running without waiting for a debugger.
- `address=127.0.0.1:5005` restricts the listener to loopback on port 5005.

When you need the debugger to attach before the application starts running, use `suspend=y`. Configure the IDE connection to match the host and port.

JDWP allows controlling the process and inspecting runtime data. Do not expose debug ports to public networks or untrusted environments; only enable them when needed and restrict access. Even with JDWP enabled, missing line or local-variable metadata will limit line-by-line debugging and variable inspection.

## 9. Impact, limitations, and release considerations

Debug metadata typically makes class files slightly larger. The increase depends on the number of methods, source lines, and variables. It does not alter program semantics, but it can expose source file names, line numbers, variable names, and some internal structural details.

Keep the following limitations in mind:

- `LocalVariableTable` only describes variables within their corresponding bytecode range. Variables out of scope do not appear in the current frame.
- Two variables in non-overlapping scopes can share the same local-variable slot. A slot is a storage location in the frame, not a fixed address for the entire runtime.
- Some values may not be observable when the JVM optimizes code at runtime; the debugger may report them as unavailable or show values that no longer exist as independent variables.
- Having debug metadata does not mean a debugger can reconstruct the full source code. The IDE still needs matching source files to display the code.
- Shrinkers, obfuscators, or packaging steps may strip or transform metadata; check the final released class files if diagnostic support is needed.
- `-g:none` is not a security mechanism to hide logic or data. Bytecode can still be analyzed with appropriate tools.

In development builds, it is usually best to keep line and local-variable information to support debugging. For production, deciding whether to keep or strip metadata should be based on diagnostic needs, artifact size, and information disclosure policies. Do not strip metadata mechanically if operations teams rely on it for troubleshooting.

## 10. Common issues and troubleshooting

| Symptom | Common cause | Resolution |
|---|---|---|
| Breakpoint does not stop on the right line | Missing line table, source/class file mismatch, or a different class is loaded | Rebuild with line info; verify source, output directory, and classpath |
| Debugger does not show local variable names | Class compiled with defaults or only source/line info | Recompile with `-g` or `-g:vars` |
| `javap -l` has no LocalVariableTable | Compiler did not emit debug variables or metadata was stripped | Check `javac` command, build tool, and packaged artifact |
| Reflection returns `arg0` as parameter name | Missing `MethodParameters` attribute | Compile with `-parameters` |
| IDE shows source that differs from bytecode | Current source does not match the running class file | Clean/rebuild the right module and check the classpath |
| `jdb` cannot connect | JVM did not enable JDWP or host/port is wrong | Launch with `-agentlib:jdwp=...` and verify connection settings |
| Variable shows as unavailable at runtime | Variable is out of scope or runtime optimized the value away | Pause in the right frame and check the build/debug level; do not assume every value always exists |

## 11. Debug compilation checklist

- [ ] Select the right JDK/compiler to build the classes.
- [ ] Use `-g` when you need source, line, and local-variable metadata.
- [ ] Use `-g:source,lines` if you only need line mappings.
- [ ] Use `-g:none` when intentionally stripping debug metadata.
- [ ] Use `-parameters` separately when parameter names are needed via reflection.
- [ ] Use `javap -l` or `javap -v` to verify the actual metadata.
- [ ] Rebuild the exact class files that the IDE or JVM will load.
- [ ] Provide matching source files to the debugger.
- [ ] Only enable JDWP when remote debugging is needed and restrict the bind address.
- [ ] Inspect the final artifact if your release pipeline runs shrinking/obfuscation.

`-g` enables `javac` to emit metadata so debuggers can link bytecode to source and inspect local variables. Combining the right debug level, `javap`, and your IDE debugger helps you track down bugs faster while keeping control over what goes into your released class files.