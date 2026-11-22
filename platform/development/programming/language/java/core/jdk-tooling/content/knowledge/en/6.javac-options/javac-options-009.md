# Compiler Plugins in javac

A compiler plugin is an extension loaded into the javac compilation process. A plugin can observe the phases in which the compiler processes source code, inspect the Abstract Syntax Tree (AST), collect information about classes or methods, and perform custom checks. This mechanism is useful when you want to add source code checking rules, record compilation progress, or integrate an analysis tool into the build.

In the JDK, the main API for a javac plugin is **com.sun.source.util.Plugin** in the **jdk.compiler** module. A compiler plugin here refers to a plugin that runs inside javac; this concept is different from the Maven Compiler Plugin or Gradle plugins, which configure and orchestrate the build.

## 1. How It Works

A javac plugin typically consists of three parts:

1. A class implementing the **Plugin** interface.
2. A service provider declaration so that Java ServiceLoader can discover the class.
3. A javac command specifying the plugin via the **-Xplugin** option.

When javac starts compilation, it discovers plugins via ServiceLoader, initializes the requested plugin, and calls the **init** method. The plugin receives a **JavacTask** representing the compilation run. Most plugins register a **TaskListener** on the task and then perform their work when the compiler emits events.

General flow:

~~~text
javac command
    |
    +-- locate Plugin implementation via ServiceLoader
    |
    +-- match the name from -Xplugin against Plugin.getName()
    |
    +-- call Plugin.init(JavacTask, args)
    |
    +-- plugin registers TaskListener
    |
    +-- javac emits PARSE, ENTER, ANALYZE, GENERATE, ... events
    |
    +-- TaskListener observes events and processes AST or compilation info
    |
    +-- javac continues compiling and generates class files
~~~

The plugin name is the friendly name returned by the **getName()** method. Each invoked plugin receives a string array **args** containing the arguments written after the plugin name on the command line.

## 2. Key APIs

The APIs reside in the **jdk.compiler** module, primarily in the **com.sun.source.util** and **com.sun.source.tree** packages.

| API | Role |
|---|---|
| Plugin | Entry point of the plugin; provides getName(), init(), and autoStart() |
| JavacTask | Represents a javac compilation run; allows registering listeners and accessing certain compiler APIs |
| TaskListener | Receives notifications when a compilation phase starts or finishes |
| TaskEvent | Describes the event, event kind, and related compilation unit or type |
| Tree | Base type for nodes in the syntax tree |
| ClassTree, MethodTree, VariableTree | Represent class, method, and variable declarations |
| TreePathScanner | Traverses the AST depth-first and maintains the path from the root to the current node |
| Trees | Bridge between the AST, language elements, and type information; supports reporting diagnostics attached to source trees |

### Plugin

The **Plugin** interface has two core methods:

~~~java
String getName();

void init(JavacTask task, String... args);
~~~

- **getName()** returns the name used to invoke the plugin with -Xplugin.
- **init()** is called when the plugin is initialized for a compilation task. This is where you register listeners or prepare required state.
- **autoStart()** is a default method added in JDK 14. A plugin can return true to be started automatically when discovered via ServiceLoader, even if not explicitly specified with -Xplugin. Only enable this behavior when you genuinely want the plugin to run automatically in every compilation where it is discovered.

The Plugin API has been available since JDK 8. The hands-on example below uses JDK 17 or later.

### TaskListener and TaskEvent

**TaskListener** has two callbacks:

- **started(TaskEvent event)** is called when an event starts.
- **finished(TaskEvent event)** is called when an event finishes.

Common event kinds include:

| Event kind | Meaning |
|---|---|
| COMPILATION | The entire compilation run |
| PARSE | Reading source code and building the syntax tree |
| ENTER | Entering declarations into the symbol table |
| ANNOTATION_PROCESSING | The annotation processing phase |
| ANNOTATION_PROCESSING_ROUND | A single round of annotation processing |
| ANALYZE | Semantic analysis and type checking |
| GENERATE | Generating class files |

Which events occur depends on the program structure and how the compiler runs. Do not rely on a fixed sequence of events across all projects or all JDK versions.

During a finished **PARSE** event, the plugin can obtain the compilation unit from **event.getCompilationUnit()** and traverse the syntax tree. For other events, compilation unit or type data may not be available; check the event kind properly before accessing them.

## 3. Distinguishing javac Plugins from Annotation Processors

Both mechanisms extend the compilation process, but they serve different purposes.

| Criterion | javac plugin | Annotation processor |
|---|---|---|
| Primary API | Plugin, JavacTask, TaskListener | Processor, ProcessingEnvironment |
| Trigger point | Events in the javac pipeline | Annotation processing rounds |
| Primary data | TaskEvent and AST via the Tree API | Annotations and Element/TypeMirror |
| Common purpose | Observing the compiler, AST analysis, custom checking rules | Processing annotations, generating sources/resources |
| Invocation | -Xplugin:name args | -processor or auto-discovery |
| Compatibility | javac-specific | Standard Java annotation processing |

For example, a processor handles **@GenerateBuilder** to generate additional Java code. A javac plugin can traverse the AST to warn when code violates internal rules, such as a class whose name does not follow a convention or a method with a disallowed structure.

If the requirement is only to generate code based on annotations, an annotation processor is usually more suitable. If you need to observe compilation phases or traverse the AST along javac's event stream, the plugin API is the right choice.

## 4. How javac Discovers Plugins

Plugins are discovered using **ServiceLoader**. According to the javac documentation, this mechanism uses the same search path as annotation processors, namely **ANNOTATION_PROCESSOR_PATH** or the **-processorpath** option.

For a plugin packaged as a JAR on the classpath, the JAR must contain a service descriptor file at the exact path:

~~~text
META-INF/services/com.sun.source.util.Plugin
~~~

The file content is the fully qualified name of the class implementing Plugin, one provider per line. For example:

~~~text
demo.TracePlugin
~~~

Sample project structure:

~~~text
compiler-plugin-demo/
  plugin-src/
    demo/
      TracePlugin.java
    META-INF/
      services/
        com.sun.source.util.Plugin
  plugin-classes/
  trace-plugin.jar
  src/
    Hello.java
  out/
~~~

Notes:

- The service descriptor file must be packaged inside the JAR, not merely placed alongside the JAR.
- The class name in the descriptor must match the exact package and class name.
- The plugin JAR must be on the processor path that javac uses to search for services.
- If using multiple plugins or annotation processors, join the JARs with the operating system's path separator.
- When using Java modules, you can declare the service provider in the module descriptor using the provides/with syntax. The example below uses a JAR on the classpath to make the ServiceLoader mechanism easy to observe.

## 5. Complete Example: A Plugin That Logs Classes in Source Code

We will create a plugin named **Trace**. The plugin registers a TaskListener, waits for the PARSE event to finish, then traverses the AST and prints the name of each class found.

### File TracePlugin.java

Create the file **plugin-src/demo/TracePlugin.java**:

~~~java
package demo;

import com.sun.source.tree.ClassTree;
import com.sun.source.util.JavacTask;
import com.sun.source.util.Plugin;
import com.sun.source.util.TaskEvent;
import com.sun.source.util.TaskListener;
import com.sun.source.util.TreePathScanner;

public final class TracePlugin implements Plugin {

    @Override
    public String getName() {
        return "Trace";
    }

    @Override
    public void init(JavacTask task, String... args) {
        String label = args.length == 0 ? "Trace" : args[0];
        System.out.println("[" + label + "] plugin initialized");

        task.addTaskListener(new TaskListener() {
            @Override
            public void finished(TaskEvent event) {
                if (event.getKind() != TaskEvent.Kind.PARSE
                        || event.getCompilationUnit() == null) {
                    return;
                }

                new TreePathScanner<Void, Void>() {
                    @Override
                    public Void visitClass(ClassTree node, Void unused) {
                        System.out.println(
                                "[" + label + "] class: " + node.getSimpleName()
                        );
                        return super.visitClass(node, unused);
                    }
                }.scan(event.getCompilationUnit(), null);
            }
        });
    }
}
~~~

Explanation:

- The **TracePlugin** class implements Plugin.
- **getName()** returns Trace so javac will recognize this name in the -Xplugin option.
- **init()** receives the task and optional arguments. This example uses the first argument as a log label.
- **addTaskListener()** registers a listener for the current compilation run.
- The **finished()** callback only handles completed PARSE events.
- **TreePathScanner** traverses the syntax tree; **visitClass()** is called when a class declaration is encountered, including nested classes.
- **super.visitClass()** continues traversing child nodes so inner classes are not skipped.

### Service Descriptor File

Create the file **plugin-src/META-INF/services/com.sun.source.util.Plugin** with the content:

~~~text
demo.TracePlugin
~~~

This line tells ServiceLoader which class is the Plugin implementation.

### Test Source Code

Create the file **src/Hello.java**:

~~~java
public class Hello {
    static class Greeter {
        void greet() {
            System.out.println("Hello from javac plugin");
        }
    }

    public static void main(String[] args) {
        new Greeter().greet();
    }
}
~~~

### Compiling the Plugin and Packaging the JAR

Use JDK 17 or later. The commands below are written for PowerShell:

~~~powershell
New-Item -ItemType Directory -Force plugin-classes | Out-Null

javac -encoding UTF-8 -d plugin-classes plugin-src/demo/TracePlugin.java

New-Item -ItemType Directory -Force plugin-classes/META-INF/services | Out-Null

Copy-Item plugin-src/META-INF/services/com.sun.source.util.Plugin plugin-classes/META-INF/services/

jar --create --file trace-plugin.jar -C plugin-classes .
~~~

After this step, the JAR should contain at least:

~~~text
demo/TracePlugin.class
META-INF/services/com.sun.source.util.Plugin
~~~

You can inspect the JAR contents with:

~~~bash
jar --list --file trace-plugin.jar
~~~

### Invoking the Plugin When Compiling an Application

Create the output directory and invoke javac:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null

javac -encoding UTF-8 -processorpath trace-plugin.jar '-Xplugin:Trace Build' -d out src/Hello.java
~~~

Explanation of the parts:

- **-processorpath trace-plugin.jar** provides the JAR for the ServiceLoader mechanism to locate the plugin.
- **-Xplugin:Trace Build** requests running the plugin named Trace and passes the argument Build. Because the name and argument contain a space, the entire value is enclosed in quotes.
- **-d out** writes the application's class files to the out directory.
- **src/Hello.java** is the source file being compiled and observed by the plugin.

While javac runs, the plugin prints representative log output:

~~~text
[Build] plugin initialized
[Build] class: Hello
[Build] class: Greeter
~~~

The order of classes follows the AST traversal order. If the source contains additional classes or nested classes, the plugin will print their corresponding names.

Run the application:

~~~bash
java -cp out Hello
~~~

Stdout:

~~~text
Hello from javac plugin
~~~

The plugin only observes the source during compilation. It does not need to be included on the classpath when running the application; the application's class files can run independently after compilation succeeds.

## 6. Passing Arguments to a Plugin

The option has the form:

~~~bash
javac -Xplugin:name args Source.java
~~~

When the plugin is invoked, the strings following the plugin name are passed into the **args** array of the init method.

Example:

~~~bash
javac -processorpath trace-plugin.jar -Xplugin:"Trace Build verbose" -d out src/Hello.java
~~~

In the sample plugin:

- args[0] is Build.
- args[1] is verbose.

You can define your own argument conventions, such as log level, report file name, or check mode. You should validate the number and values of arguments right in init; if misconfigured, emit a clear message and stop the plugin appropriately.

Do not parse strings arbitrarily when there are multiple options. Define a clear syntax, such as key=value or a documented set of flags.

## 7. Traversing the AST and Enforcing Custom Rules

The example above only prints class names. In real-world tools, a plugin typically inspects other nodes to check rules.

Some node types:

- **ClassTree**: class, interface, enum, or record declaration.
- **MethodTree**: method or constructor declaration.
- **VariableTree**: field, parameter, or local variable.
- **MethodInvocationTree**: method invocation.
- **IfTree**, **ForLoopTree**, **TryTree**: control flow structures.

For example, to print method names, you can add to TreePathScanner:

~~~java
@Override
public Void visitMethod(MethodTree node, Void unused) {
    System.out.println("Method: " + node.getName());
    return super.visitMethod(node, unused);
}
~~~

Required import:

~~~java
import com.sun.source.tree.MethodTree;
~~~

Some methods have special names like **<init>**, which represents a constructor. Therefore, when displaying or checking method names, handle constructors according to the purpose of your rule.

### Distinguishing Syntax and Semantics

The AST after PARSE represents the syntactic structure of the source code. It does not necessarily contain resolved type and symbol information.

If a rule needs to know which overload a method call invokes, the type of an expression, or the declaration an identifier refers to, consider events after ANALYZE and use the **Trees**, **Elements**, or **Types** APIs as appropriate.

Example of obtaining Trees from the task:

~~~java
import com.sun.source.util.Trees;

Trees trees = Trees.instance(task);
~~~

**Trees** provides mapping between the syntax tree and language elements. This API is useful when querying symbols or emitting messages attached to source locations. Do not assume semantic information is already available in the PARSE callback.

### Emitting Source-Attached Diagnostics

You can use Trees to report a warning on the exact node:

~~~java
trees.printMessage(
        javax.tools.Diagnostic.Kind.WARNING,
        "Internal rule: this declaration needs review",
        tree,
        compilationUnit
);
~~~

This call requires the corresponding **trees**, **tree**, and **compilationUnit** variables. Emitting diagnostics this way makes warnings appear with their source location in compiler output, rather than just printing a contextless log line.

A plugin should avoid emitting excessive duplicate warnings. Clearly define the ERROR/WARNING/NOTE severity level and the exact node to attach the diagnostic to.

## 8. autoStart and Plugin Loading Behavior

Since JDK 14, Plugin has a default method **autoStart()**. When it returns true, javac initializes the plugin with an empty argument array if the plugin is found via ServiceLoader and has not already been initialized by an explicit option.

This creates two usage modes:

- **Explicit invocation**: the user specifies -Xplugin:name. This is the most controllable and predictable approach for most plugins.
- **Auto-start**: the plugin overrides autoStart() to return true. The plugin can run whenever the JAR appears on the processor search path, even if the user does not specify -Xplugin.

Do not enable autoStart if the plugin has major side effects, writes files, alters compilation results, or significantly increases build time. Automatic behavior must be documented and controlled in the build environment.

## 9. Integrating with Build Tools

A javac plugin is activated when the build tool invokes javac with the appropriate processor path and plugin option. It is important to distinguish a javac plugin from a build tool plugin.

### Maven

The Maven Compiler Plugin is the component that configures compilation in Maven. It is not the javac Plugin API. When using javac as the compiler backend, you can pass compiler options to activate the plugin.

An illustrative configuration with maven-compiler-plugin:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <compilerArgs>
            <arg>-Xplugin:Trace</arg>
        </compilerArgs>
        <annotationProcessorPaths>
            <path>
                <groupId>example</groupId>
                <artifactId>trace-plugin</artifactId>
                <version>1.0.0</version>
            </path>
        </annotationProcessorPaths>
    </configuration>
</plugin>
~~~

In a real configuration, declare the plugin artifact with your internal Maven coordinates and verify that your Maven Compiler Plugin version supports passing the processor path as expected. If you need to pass arguments containing spaces, use the appropriate argument configuration and inspect the actual compiler command line generated by Maven.

### Gradle

With Gradle Java, you can configure compiler arguments and the annotation processor path on JavaCompile tasks:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-Xplugin:Trace']
    options.annotationProcessorPath = configurations.tracePlugin
}
~~~

The configuration above assumes the project has declared a **tracePlugin** configuration containing the plugin JAR. You need to create the configuration and add the appropriate dependency, for example:

~~~groovy
configurations {
    tracePlugin
}

dependencies {
    tracePlugin 'example:trace-plugin:1.0.0'
}
~~~

The configuration name and dependency sharing should fit your project structure. If using the plugin across multiple modules, place the configuration in a convention plugin or shared build logic to avoid inconsistent behavior across modules.

Build tools may use a different compiler or a daemon with its own classloader. Verify that the backend is actually javac and check build logs if the plugin is not loaded.

## 10. Limitations and Development Considerations

- **javac-specific**: The Plugin API is an extension point of javac. Do not assume the plugin will work with the Eclipse Compiler for Java or other compilers.
- **Do not rely on internal implementations**: prefer com.sun.source.util and com.sun.source.tree. Packages under com.sun.tools.javac.* are internal and may change between versions.
- **JDK compatibility**: compile and run the plugin with an appropriate JDK. Check new APIs before using them if you must support multiple major versions.
- **Build impact**: traversing the entire AST, reading files, or calling external services can slow down compilation. Avoid heavy work inside callbacks.
- **Security and reproducibility**: plugins execute code inside the compiler process with the permissions of the build process. Only load trusted JARs, control dependencies, and avoid unnecessary dynamic code loading.
- **Parallelism**: build tools may compile multiple modules or source tasks concurrently. Do not use shared mutable static state unless it is designed to be thread-safe.
- **Diagnostics**: clearly define when to only warn and when to fail compilation. Do not turn unstable rules into mandatory build errors.
- **Do not overwrite source files**: analysis plugins should avoid modifying source files directly. If you need to generate sources, an annotation processor or a separate code generation step is usually more appropriate.

## 11. Troubleshooting Common Errors

### javac reports that the plugin cannot be found

Check:

1. Whether the plugin JAR is on the processor path.
2. Whether the service descriptor file has the exact name and path under META-INF/services.
3. Whether the descriptor content has the exact fully qualified class name.
4. Whether the implementation class is public and has a no-arg constructor so ServiceLoader can instantiate it.
5. Whether the plugin class properly implements the com.sun.source.util.Plugin interface.
6. Whether the name in -Xplugin matches getName() exactly.

### The plugin is found, but init does not run

- Confirm that -Xplugin:name was passed properly.
- Check quoting syntax if the plugin has arguments containing spaces.
- If relying on autoStart, check whether the JDK supports this API; autoStart was introduced in JDK 14.
- Check whether the build tool is actually passing the option to javac.
- Inspect the command line log or enable verbose mode in the build tool.

### Class not found or linkage errors

- Check that the JAR contains the compiled classes and required dependencies.
- Check the JDK version used to compile the plugin and the JDK running the compiler.
- Check the classpath/processorpath for missing dependencies or conflicting versions.
- For modular plugins, check the module descriptor, requires, and provides/uses declarations.
- Avoid referencing internal javac packages, as this can cause module access errors or API breakage.

### AST or type information is null

- Check the event kind before calling getCompilationUnit() or getTypeElement().
- Use the compilation unit in the appropriate event, typically PARSE.
- If resolved types or symbols are needed, process them in an appropriate phase such as ANALYZE.
- Check whether the source files are actually part of the compilation run or only found indirectly via the classpath.

### Build slows down after adding the plugin

- Measure build time before and after enabling the plugin.
- Restrict the event kinds being handled; do not traverse the AST repeatedly without need.
- Cache results within the scope of the compilation task.
- Avoid network access or synchronous multi-file reads inside listeners.
- Allow disabling the plugin via build configuration when comparing or isolating issues.

## 12. When Should You Use a javac Plugin?

Consider a javac plugin when you need to:

- Monitor compilation phases to debug builds or integrate tooling.
- Traverse the AST to enforce organization-specific conventions or source rules.
- Analyze source structure before or after a compiler phase.
- Produce custom diagnostics attached to source locations.
- Connect javac to a controlled compilation metrics or reporting system.

Do not choose a javac plugin merely to add dependencies, run a formatter, or generate simple sources. Those tasks are better handled by build plugins, formatters, static analyzers, or dedicated annotation processors.

## 13. Plugin Creation and Usage Checklist

- [ ] Choose the right goal: compiler monitoring, AST analysis, or annotation processing.
- [ ] Implement com.sun.source.util.Plugin and return a stable name in getName().
- [ ] Register TaskListener in init() and only handle the necessary events.
- [ ] Package the service descriptor at META-INF/services/com.sun.source.util.Plugin.
- [ ] Place the plugin JAR on the processor path.
- [ ] Invoke with -Xplugin using the exact name and arguments.
- [ ] Test the plugin on a small source file before integrating it across the project.
- [ ] Measure compilation time impact and verify JDK compatibility.
- [ ] Avoid internal com.sun.tools.javac.* APIs when public APIs suffice.
- [ ] Document how to enable/disable the plugin and how to handle findings reported by it.

## 14. Key Takeaways

- A javac plugin is a compiler extension point using the **Plugin** interface in the **jdk.compiler** module.
- **getName()** defines the plugin name; **init()** receives JavacTask and arguments.
- **ServiceLoader** discovers plugins via the same search path as annotation processors, typically configured with **-processorpath**.
- **-Xplugin:name args** activates the plugin on the javac command line.
- **TaskListener** observes PARSE, ENTER, ANALYZE, GENERATE, and other phase events.
- **TreePathScanner** and the Tree API enable AST traversal; use Trees when you need to link the AST to symbols or emit diagnostics.
- The Plugin API is specific to javac; annotation processors and Maven/Gradle plugins are separate mechanisms.
- Prefer public APIs, keep the plugin lightweight, clearly assess build impact, and control which JARs are loaded.

## Official References

- [javac Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html)
- [Plugin API — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.compiler/com/sun/source/util/Plugin.html)
- [TaskListener API — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/com/sun/source/util/TaskListener.html)
- [com.sun.source.util package — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.compiler/com/sun/source/util/package-summary.html)