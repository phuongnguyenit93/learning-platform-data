# Observing Phases with TaskListener Without Modifying Compiler Internals

## 1. Goal and Core Idea

When learning how Java is compiled, we often want to know when javac **parses**, **enters declarations into the symbol table (enter)**, **checks/attributes types (analyze)**, and **generates bytecode (generate)**. Some people solve this by importing classes like com.sun.tools.javac.comp.Attr, com.sun.tools.javac.main.JavaCompiler, or modifying JCTree trees; that approach depends directly on javac's internal implementation and easily breaks upon JDK upgrades.

The Java JDK provides a better observation option: **TaskListener** in package com.sun.source.util, accompanied by **JavacTask** and **TaskEvent**. These are **public JDK APIs**, located in module **jdk.compiler** and exported to applications. You can register a listener on a javac compilation task to receive callbacks whenever an event starts or finishes, **without modifying the AST, without accessing Context, or compiler internal passes**.

This lesson guides you to:

- Clearly distinguish standard Java SE, public javac APIs, and internal implementation classes.
- Understand JavacTask, TaskListener, TaskEvent.Kind, and started/finished.
- Create a JavaCompiler.CompilationTask yourself, check whether it is a JavacTask, and register a listener before running.
- Observe PARSE, ENTER, ANALYZE, and GENERATE events for a Java 17 program.
- Read CompilationUnitTree/TypeElement from events in the right context, understanding that callbacks can repeat and data can be null.
- Troubleshoot when no events appear, when the compiler hits errors, when using annotation processors, or in multi-file projects.
- Know what TaskListener can observe and that it must **not** be used to alter compiler implementations.

The goal is **evidence-based observation**, not trying to "intervene so javac runs in the order we want".

## 2. Which API Layer Does TaskListener Belong To?

To avoid confusing stability levels, distinguish three groups:

| Group | Examples | Module | Commitment Level |
| --- | --- | --- | --- |
| Java SE compiler API | javax.tools.JavaCompiler, ToolProvider, JavaFileObject, DiagnosticCollector | java.compiler | Standard Java SE interface for requesting compilation and receiving diagnostics |
| Public JDK compiler API | com.sun.source.util.JavacTask, TaskListener, TaskEvent, Trees, and com.sun.source.tree.* | jdk.compiler | Public API exported by the JDK for observing/integrating tools with javac |
| Internal javac implementation | com.sun.tools.javac.comp.Attr, com.sun.tools.javac.util.Context, com.sun.tools.javac.tree.JCTree | jdk.compiler | Implementation details; many packages are not exported to ordinary applications |

**TaskListener is not in Java SE's javax.tools**, yet it is also **not an internal class requiring --add-exports** like many parts of com.sun.tools.javac.*.

What to check is **API documentation, module-exported packages, and usage contracts**, not merely the com.sun prefix. A public JDK package can still couple code to javac rather than every JavaCompiler implementation.

Diagram:

~~~text
Compiler-learning tool application
          |
          +-- javax.tools.JavaCompiler (Java SE API)
          |           |
          |           v
          |    CompilationTask
          |           |
          |      instanceof JavacTask?
          |           |
          |           v
          +-- com.sun.source.util.JavacTask
                         |
                         v
                  addTaskListener(...)
                         |
                         v
                  TaskListener
                  started(event)
                  finished(event)
                         |
                         v
                  Observe Kinds:
                  PARSE / ENTER / ANALYZE / GENERATE
~~~

Thanks to this approach, your code is written against public interfaces. You do not need to call the constructor of com.sun.tools.javac.api.JavacTool directly or manipulate JCTree.

## 3. Three Core Interfaces/Classes

### JavacTask

com.sun.source.util.JavacTask is a specialized CompilationTask for javac, providing capabilities such as:

- addTaskListener(TaskListener): registers a listener to observe events.
- removeTaskListener(TaskListener): removes a registered listener.
- parse(): requests parsing sources in task context when using phase-by-phase APIs.
- analyze(): requests analysis/checking when using public phase control.
- generate(): requests generating output from the task per the corresponding API.
- getElements() and getTypes(): obtains related language model utilities to inspect declarations/types.

In the main example, we only call **addTaskListener** and then call **task.call()** to run the entire task. Do not mix manual parse/analyze/generate calls with call() on the same task without a clear lifecycle control plan.

**Important:** JavaCompiler.CompilationTask is the standard interface. Not every compiler implementation guarantees its task is a JavacTask. Therefore we use **instanceof** and report unsupported if another provider is used.

### TaskListener

com.sun.source.util.TaskListener provides two callbacks:

~~~java
@Override
public void started(TaskEvent event) {
    // Compiler notifies that an activity started.
}

@Override
public void finished(TaskEvent event) {
    // Compiler notifies that an activity finished.
}
~~~

The listener is invoked during compiler activity; callbacks should be lightweight, fast, and perform no unnecessary side-effect work. Do not force the compiler into a different phase order by mutating internal state from callbacks.

### TaskEvent

TaskEvent holds data about the current event. Common methods:

- getKind(): the kind of compiler activity being reported.
- getCompilationUnit(): CompilationUnitTree if the event carries appropriate compilation unit information.
- getSourceFile(): JavaFileObject of the source when available.
- getTypeElement(): related TypeElement in certain events.

**Do not assume every field is non-null.** Some events are task-wide, some relate only to one source, and some relate to one type. Access source files, syntax trees, or types only when the value is actually provided; check for null first.

## 4. Important Events and Interpretation Limits

TaskEvent.Kind indicates the *kind of event*, not an immutable global timeline. Common values:

| Kind | Learning Meaning | What Not to Assume |
| --- | --- | --- |
| COMPILATION | Task-level compilation activity | Does not mean every callback kind occurs only once |
| PARSE | Javac parses a compilation unit | Does not prove all syntax errors have vanished after one event |
| ENTER | Enters declaration information into the symbol environment | Does not mean whole-program type checking is finished |
| ANALYZE | Analyzes/checks a type declaration or appropriate unit | Not an optimization result or performance metric |
| GENERATE | Generates output for the corresponding type/class | Does not guarantee only one event per source file |
| ANNOTATION_PROCESSING | Annotation processing activity | Does not guarantee processors actually create new sources |
| ANNOTATION_PROCESSING_ROUND | One annotation processing round | Does not mean one round contains only one annotation |

Do not hardcode a sequence "PARSE, then exactly one ENTER, then exactly one ANALYZE, then exactly one GENERATE" for every project. With multiple source files, nested classes, source-generating processors, and compile errors, callback counts and order can vary.

**Specifically:** GENERATE events can occur for multiple classes within the same source, while ANALYZE can relate to a type. It is better to count/record event kinds and associated source/type objects rather than treating exact event counts as an API contract.

### How Do started and finished Differ?

- started(event): the compiler notifies that an activity of the corresponding Kind started.
- finished(event): the compiler notifies that the activity finished per javac's reporting mechanism.

Receiving finished(PARSE) means a parse activity was reported as completed, **not that the entire compilation succeeded**. For example, a file may be parsed and entered and then fail due to a type error; in that case, do not expect GENERATE for the erroneous class.

Callbacks are meant for **instrumentation/observation**, not a rollback mechanism, transaction, or opportunity to replace the compiler implementation.

## 5. Complete Java 17 Project to Observe Phases

Create directory:

~~~text
task-listener-lab/
├── TaskListenerDemo.java
├── out/               # After compiling the tool
└── build/
    └── classes/       # Output created by the tool when running
~~~

The project needs only **one Java source file**. It compiles a small class named demo.Hello from an in-memory source string, listens to Kinds, and verifies the generated class file.

### File TaskListenerDemo.java

~~~java
import com.sun.source.util.JavacTask;
import com.sun.source.util.TaskEvent;
import com.sun.source.util.TaskListener;
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.EnumSet;
import java.util.List;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class TaskListenerDemo {
    private static final class Source extends SimpleJavaFileObject {
        private final String text;

        Source(String name, String text) {
            super(URI.create("string:///" + name.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.text = text;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return text;
        }
    }

    public static void main(String[] args) throws IOException {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            System.out.println("No system Java compiler");
            return;
        }

        Path output = Path.of("build", "classes");
        Files.createDirectories(output);

        String code = "package demo; public final class Hello {"
                + " public static int value() { return 42; } }";

        EnumSet<TaskEvent.Kind> finished =
                EnumSet.noneOf(TaskEvent.Kind.class);

        try (StandardJavaFileManager files =
                compiler.getStandardFileManager(
                        null, null, StandardCharsets.UTF_8)) {
            JavaCompiler.CompilationTask generic = compiler.getTask(
                    null, files, null,
                    List.of("--release", "17", "-proc:none",
                            "-d", output.toString()),
                    null, List.of(new Source("demo.Hello", code)));

            if (!(generic instanceof JavacTask task)) {
                System.out.println("JavacTask unavailable");
                return;
            }

            task.addTaskListener(new TaskListener() {
                @Override
                public void started(TaskEvent event) {
                }

                @Override
                public void finished(TaskEvent event) {
                    finished.add(event.getKind());
                }
            });

            boolean success = Boolean.TRUE.equals(task.call());
            System.out.println("Compilation success: " + success);
        }

        System.out.println("PARSE observed: "
                + finished.contains(TaskEvent.Kind.PARSE));
        System.out.println("ENTER observed: "
                + finished.contains(TaskEvent.Kind.ENTER));
        System.out.println("ANALYZE observed: "
                + finished.contains(TaskEvent.Kind.ANALYZE));
        System.out.println("GENERATE observed: "
                + finished.contains(TaskEvent.Kind.GENERATE));
        System.out.println("Class exists: "
                + Files.isRegularFile(
                        output.resolve("demo/Hello.class")));
    }
}
~~~

This is **self-contained, complete** source suitable for Java 17. The embedded source belongs to class Source extends SimpleJavaFileObject, supplying code via getCharContent. There is no need to create demo/Hello.java beforehand.

### 5.1. Compile the Observation Tool

Open a terminal at the **root of task-listener-lab** and check versions:

~~~sh
javac -version
java -version
~~~

Use JDK 17+ that includes javac, not a minimal runtime image lacking a compiler.

Create out:

~~~bash
# Bash (macOS/Linux)
mkdir -p out
~~~

~~~powershell
# PowerShell (Windows)
New-Item -ItemType Directory -Path out -Force | Out-Null
~~~

Compile:

~~~sh
javac --release 17 -encoding UTF-8 -d out TaskListenerDemo.java
~~~

Importing com.sun.source.util.JavacTask, TaskEvent, and TaskListener is valid on JDK 17 because **com.sun.source.util** is a public package in module jdk.compiler. This is not opening internal packages with --add-exports.

### 5.2. Run the Tool

~~~sh
java -cp out TaskListenerDemo
~~~

**Stdout of the example on a JDK with a system javac (tested with JDK 24 and --release 17):**

~~~text
Compilation success: true
PARSE observed: true
ENTER observed: true
ANALYZE observed: true
GENERATE observed: true
Class exists: true
~~~

This result shows:

1. ToolProvider.getSystemJavaCompiler returned a compiler provider.
2. getTask created a task taking source code from SimpleJavaFileObject.
3. The runtime task is a JavacTask, so listener registration succeeded.
4. The listener saw Kinds PARSE, ENTER, ANALYZE, and GENERATE in the finished callback.
5. The .class file was written under build/classes/demo/Hello.class.

**Result limitations:** the example displays booleans indicating *whether an event was received* rather than assuming callback ordering/counts. With another compiler provider that does not support JavacTask, the program prints "JavacTask unavailable" and does not perform compilation in that branch. With a runtime image lacking a system compiler, it prints "No system Java compiler".

### 5.3. What Did the Program Do Without Using Internals?

- JavaCompiler from **javax.tools** is responsible for creating the compilation task.
- JavacTask from **com.sun.source.util** provides listener registration.
- TaskEvent.Kind describes the reported event.
- StandardJavaFileManager manages compiler resources and is closed via try-with-resources.
- The compiler performs analysis and generates .class; the observer only records.
- The program does not import JCTree, Context, Attr, or other internal classes.

Even though it uses package com.sun.source.util, this is still usage of the **public JDK API** described in documentation.

## 6. Why Must the Listener Be Registered Before task.call()?

In the project, the execution order is:

~~~text
getTask(...) -> check instanceof JavacTask
            -> addTaskListener(listener)
            -> task.call()
            -> process results and recorded events
~~~

If you call task.call() first and register the listener afterward, callbacks for already-completed activities **are not replayed** to the new listener.

A typical CompilationTask is designed to execute **once**. Do not call task.call() multiple times to receive events again; if you want to compile another source, create another task with appropriate inputs/outputs.

### Is removeTaskListener Necessary?

In this short program, the task is not reused and the listener only lives as long as the task, so calling removeTaskListener is not mandatory. In reusable tools or dynamic listener registration/removal, removeTaskListener is the valid API to unregister. Do not register the same listener uncontrollably multiple times and miscount events.

### Why Is Output Saved After task.call?

The workflow diagram is as follows:

~~~text
Source(JavaFileObject)   -> javac
                             |
                             +-- parse -> listener
                             +-- enter -> listener
                             +-- analyze -> listener
                             +-- generate -> listener
                             |
                             v
                        Hello.class
~~~

The Files.isRegularFile call in the demo **checks evidence on the filesystem**, complementing the compiler returning success and the listener seeing GENERATE. An event does not replace verifying the real output.

## 7. Safely Observing Event Information

Besides getKind(), TaskEvent can also carry CompilationUnitTree, JavaFileObject, and TypeElement depending on the event.

Inside a TaskListener callback, you can log as follows:

~~~java
@Override
public void finished(TaskEvent event) {
    System.out.println("Kind: " + event.getKind());

    if (event.getSourceFile() != null) {
        System.out.println("Source: "
                + event.getSourceFile().getName());
    }

    if (event.getTypeElement() != null) {
        System.out.println("Type: "
                + event.getTypeElement().getQualifiedName());
    }

    if (event.getCompilationUnit() != null) {
        System.out.println("Package: "
                + event.getCompilationUnit().getPackageName());
    }
}
~~~

This is **a replacement snippet for the finished callback**, not a standalone class. Source names, event counts, and log order depend on activity types and the project. Therefore this lesson does **not** give "fixed stdout" for this snippet.

**Do not assume all getters simultaneously have values.** For task-wide compilation events, source or unit may be null. For events related to a specific type, TypeElement may be present. When writing an observer, handle absent data rather than unconditionally calling getQualifiedName or getPackageName.

### Using the Tree API Appropriately

TaskEvent.getCompilationUnit() returns CompilationUnitTree, a **public AST interface** in com.sun.source.tree. If you want to traverse syntax, you can use com.sun.source.util.TreeScanner or TreePathScanner. That is **observation**, without touching com.sun.tools.javac.tree.JCTree.

For example, for an event with a CompilationUnitTree, you can inspect:

~~~java
if (event.getCompilationUnit() != null) {
    int topLevelCount =
            event.getCompilationUnit().getTypeDecls().size();
}
~~~

This is a snippet, not a standalone program. It reads the list of declarations at the compilation unit level without modifying nodes. To analyze names/types of an AST at a position, you can use Trees/TreePath and the javax.lang.model model once that information is ready at the appropriate phase.

### Cases Where You Should Not Collect Too Early

During PARSE, syntax has been built, yet there is no guarantee that all names are resolved or all types are checked. Do not use data in PARSE events to claim type checking is finished. For tools wanting to see resolved TypeElements, ENTER or ANALYZE events may be more suitable depending on requirements; yet still check for null and each event's contract.

## 8. Adding Callback Count Statistics for Multi-File Projects

The main example uses EnumSet to answer "has an event of this kind been seen?". With multiple source files, you may need to know **how many times** an event is reported. In that case use EnumMap<TaskEvent.Kind,Integer>:

~~~java
java.util.EnumMap<TaskEvent.Kind, Integer> counts =
        new java.util.EnumMap<>(TaskEvent.Kind.class);

TaskListener listener = new TaskListener() {
    @Override
    public void started(TaskEvent event) {
    }

    @Override
    public void finished(TaskEvent event) {
        counts.merge(event.getKind(), 1, Integer::sum);
    }
};
~~~

This is an **illustrative snippet**, not a complete main method. If using it, add it into the appropriate scope and register the listener before calling task.call().

**Do not expect count(PARSE) to equal the number of .class outputs.** One source can contain multiple classes, nested types, and annotation processing can generate new sources. ANALYZE/GENERATE can be reported at per-type granularity, whereas PARSE relates to a compilation unit.

When comparing event counts across JDK versions, label those as **empirical measurements**, not a formal formula of the Java Language Specification.

### A Less Brittle Testing Approach

Instead of asserting "the exact event order is P, E, A, G and each kind occurs exactly once", test that with valid source and a supported javac:

- task.call() returns true;
- PARSE/ENTER/ANALYZE/GENERATE are present in the observed set in the specific example;
- the output class file actually exists;
- the task does not need to import internal packages.

When processing erroneous source, assert that compilation fails and ERROR diagnostics exist, **without** requiring GENERATE to occur.

## 9. Linking TaskListener with DiagnosticCollector

TaskListener reports activities, whereas javax.tools's DiagnosticCollector reports **issues detected by the compiler**. These two sources of information answer two different questions:

- TaskListener: which phase is/did the compiler announce?
- DiagnosticListener: what errors/warnings did the compiler report, in which file/line if available?

In a compiler task, you can configure DiagnosticCollector when calling getTask:

~~~java
javax.tools.DiagnosticCollector<JavaFileObject> diagnostics =
        new javax.tools.DiagnosticCollector<>();

JavaCompiler.CompilationTask generic = compiler.getTask(
        null, files, diagnostics,
        List.of("--release", "17", "-proc:none",
                "-d", output.toString()),
        null, sources);
~~~

This is a **code fragment replacing the getTask creation part of the example**, not a complete method. Variable sources must be a prepared Iterable<? extends JavaFileObject>.

After task.call() finishes, check:

~~~java
boolean hasErrors = diagnostics.getDiagnostics().stream()
        .anyMatch(d -> d.getKind()
                == javax.tools.Diagnostic.Kind.ERROR);
~~~

You can extract kind, source, line, column, and message when available. Do not define the entire build status solely by event counts: a compiler may have parsed a source yet hit name/type errors or missing dependencies and therefore produced no bytecode.

### A Syntax Error Scenario

Replace the demo's source with:

~~~java
String badCode = "package demo; public class Broken { "
        + "void test() { int x = ; } }";
~~~

If badCode is used as input to a new task, javac typically emits an ERROR diagnostic and task.call() returns false. The listener may still see parse-related events, yet **there is no reason to expect GENERATE** for the Broken class.

This clarifies the distinction between *observing reported phases* and *proving compilation succeeded*.

## 10. Annotation Processing and TaskListener

A compiler can run annotation processors, generate new source files, and create additional rounds. TaskListener has related Kinds:

- ANNOTATION_PROCESSING;
- ANNOTATION_PROCESSING_ROUND.

Events can help an observer recognize annotation processing activity, yet **do not mean the listener itself is an annotation processor**.

| Component | Role |
| --- | --- |
| TaskListener | Observes javac events starting/finishing an activity |
| AbstractProcessor | JSR 269 processor, processes annotations across rounds |
| RoundEnvironment | Provides elements and status of each processing round |
| ProcessingEnvironment | Supplies Filer, Messager, Elements, Types to processors |
| TaskEvent | Event data reported by compiler to TaskListener |

In the runnable example, we used **-proc:none** to disable annotation processing, keeping the four main Kinds easy to observe. If processors are enabled, they can add sources, add rounds, and change event counts. Configure processor path and processor selection explicitly when you want to study that; avoid guessing event counts based on a project without processors.

**Do not use TaskListener instead of Filer to generate new sources.** Filer manages generated files under the annotation processing API; TaskListener provides phase-observation callbacks, not a standard mechanism to modify source/AST directly or inject arbitrary code into the pipeline.

## 11. Observing via JavacTask Instead of Calling Internals Directly

The key point of this topic is **not modifying compiler internals**. Comparison:

| Task to Perform | Appropriate Public API | Unnecessary/Discouraged by Default |
| --- | --- | --- |
| Request source compilation | javax.tools.JavaCompiler.getTask | com.sun.tools.javac.api.JavacTool directly |
| Listen to phase events | JavacTask.addTaskListener | Patching com.sun.tools.javac.main.JavaCompiler |
| Read AST | com.sun.source.tree.* | Casting to JCTree |
| Traverse syntax | TreeScanner/TreePathScanner | Mutating fields of JCTree directly |
| Associate AST with type model | Trees and javax.lang.model | Accessing Attr or Context |
| Receive errors/warnings | javax.tools.DiagnosticListener | Parsing stderr messages by fixed strings |
| Generate source from annotations | AbstractProcessor + Filer | Overwriting source input inside TaskListener |

### Why Not Use com.sun.tools.javac.comp.Attr Directly?

Attr is a component of javac's implementation. Types such as Context, Attr, or JCTree can change fields/methods, constructors, and lifecycle across JDK releases. Module jdk.compiler does not publicly export most com.sun.tools.javac.* packages to ordinary applications. Code using those classes can encounter compile-time package-not-visible errors, IllegalAccessError, or binary compatibility failures when upgrading.

TaskListener and JavacTask reside in the API published by the JDK for building compiler tools. They do not necessarily make an application portable across **all** other Java compilers, yet they provide a much clearer usage boundary than coupling directly to javac internals.

### Is --add-exports Required?

**Not required for the section 5 example**, because com.sun.source.util is publicly exported from jdk.compiler on JDK 17. The --add-exports option is typically mentioned when code wants to access unexported internal packages; do not use it as a default solution for observing compilation events.

If writing a **named module** using TaskListener, you can declare:

~~~java
module demo.compiler.observer {
    requires java.compiler;
    requires jdk.compiler;
}
~~~

This is an **illustrative module-info.java snippet**. To actually compile/run a named module, place sources under module roots and use appropriate --module-path or --module-source-path commands. The two requires explicitly specify the modules containing javax.tools and com.sun.source.util. They do not open all com.sun.tools.javac.* packages.

## 12. Lifecycle, Resources, and Thread Safety

### One Task Corresponds to One Compile Operation

In the demo, the compiler creates the generic task, the observer registers callbacks, task.call() performs compilation, and then we read results. Do not keep JavacTask to invoke call a second time after it has already completed.

### Close the File Manager

StandardJavaFileManager uses try-with-resources to avoid leaking handles/resources. When the compiler works with many files/JARs or in a long-lived service, closing resources properly is very important.

### Keep Listeners Lightweight

TaskListener callbacks are invoked by the compiler during processing. If a callback performs slow disk writes, network calls, or inappropriate synchronization locks, you can slow down builds or cause risks while the compiler holds internal processing state.

Good practice for instrumentation: store minimal information such as event kind, source name/qualified type name (when available), monotonic timestamps if measuring duration, and diagnostics. Do not cache AST/Elements across multiple compilation invocations.

### Do Not Assume Every Callback Runs on a Specific Thread

In a specific toolchain you may observe a certain callback order and thread. Yet resilient integration code should avoid relying on concurrency behavior not guaranteed by the API. If a listener shares data with other threads, use appropriate synchronization. The demo only reads the finished set **after task.call() returns**, so no multi-threaded pipeline design is needed.

### Do Not Modify Source/AST from Callbacks

The TaskListener API provides no public contract allowing you to take a Tree and mutate implementation nodes inside a callback. Although some people use compiler-specific techniques to do that, it is **not** the safe, maintainable observation approach this lesson teaches.

## 13. Common Confusions When Reading Logs

| Symptom | Common Wrong Inference | Correct Understanding |
| --- | --- | --- |
| PARSE finished | All names/types have been resolved | PARSE relates mainly to syntactic structure |
| ENTER finished | Compilation is guaranteed to succeed | Subsequent semantic steps can still report errors |
| ANALYZE appears multiple times | The compiler repeated a phase erroneously | Can correspond to multiple types/units |
| GENERATE appears multiple times | Each source file should have only one .class | One source can declare multiple types/nested classes |
| No GENERATE | TaskListener is broken | Compilation may have failed before bytecode generation |
| Callback has null source | The compiler does not know the source | That event kind may be task-wide |
| Task is not instanceof JavacTask | JavaCompiler API is broken | That provider does not promise javac-specific API support |
| Annotation processing round present | Listener is an annotation processor | The two APIs have different responsibilities |
| TaskListener uses com.sun.* | It is an internal API | com.sun.source.* is public JDK compiler API |
| javac prints error yet PARSE was seen | Compile error is not real | Observing PARSE does not replace task.call and diagnostics |
| Running tool uses old .class | New source code compiled | Check output/build directory and compile result |

## 14. Diagnostic Workflow When Listener Does Not Work

1. **Check JDK:** javac -version, java -version; are you using JDK 17+, and does the runtime have a compiler provider?
2. **Check task:** is ToolProvider.getSystemJavaCompiler() null? Is CompilationTask instanceof JavacTask?
3. **Check order:** was the listener registered **before** task.call()?
4. **Check source input:** does JavaFileObject have a valid URI/Kind.SOURCE and valid source code? For sources on disk, can the file manager read the file?
5. **Check task options:** are --release, -proc, -d, and library paths set appropriately?
6. **Check diagnostics:** what did task.call() return, and are there ERRORs from parser/type checker/dependencies?
7. **Check Kind:** are you waiting for ANNOTATION_PROCESSING_ROUND even though -proc:none is enabled?
8. **Check metadata:** event.getCompilationUnit/getTypeElement/getSourceFile can be null; do not let a NullPointerException inside a callback mask the root error.
9. **Check output:** was .class created, and did you run in the right directory?
10. **Check portability:** if using another compiler implementation, clarify that JavacTask is a specific prerequisite of the observer feature.

### Add DiagnosticCollector When Needed

To distinguish bad source from a listener not running, pass javax.tools.DiagnosticCollector to getTask and print diagnostics by Kind/source/line when available. Do not just count events and decide build status yourself. Also do not rely on the full English sentence of an error message because javac can change phrasing across versions.

## 15. Extension: Tracking Activity Duration

A profiling application may want to measure time between started/finished for the same activity. This is **harder** than just counting events: a single Kind can appear for multiple compilation units/types, and activities can be nested.

Approach:

1. Choose an event key consisting of Kind, source, and type when available.
2. Track matching started/finished with the key and appropriate callback context.
3. Use a monotonic time source such as System.nanoTime if measuring duration within the same JVM.
4. Emit statistics only after the task completes; state event counts and pairing rules clearly.
5. Cross-check against profiler/benchmark measurements if performance conclusions are needed.

**Do not deduce that summing per-Kind durations equals wall-clock compile time.** Activities can overlap/nest, and listeners have overhead. An empirical measurement on a specific JDK is not a formal definition of parse/analyze time in Java.

The runnable lesson intentionally collects only **the presence of events** to avoid creating the impression that TaskListener is a profiler with completely stable timing precision/definitions.

## 16. Practice Exercises

### Exercise 1 — Read Demo Output

Run TaskListenerDemo.java. Explain why compilation success, PARSE, ENTER, ANALYZE, GENERATE, and Class exists are all true when source is valid. What is each line evidence of?

### Exercise 2 — Specify Which Callback Reports Events

Change the listener to count started and finished separately. Can you conclude solely from callback counts that every Kind always occurs exactly once? Why?

### Exercise 3 — Add a Second Source

Create another SimpleJavaFileObject for demo.Second and pass both sources to getTask. Compare PARSE/ANALYZE/GENERATE counts. Record the empirical observation without turning it into a fixed rule.

### Exercise 4 — Erroneous Source

Try compiling a source with int x = ; in a new task and use DiagnosticCollector. Predict that compilation success is false. Why might PARSE have been reported yet GENERATE not appear for the erroneous class?

### Exercise 5 — Add Source Name

In finished(), check event.getSourceFile()!=null and print the source name. Compare which events attach to a JavaFileObject and which events have no source.

### Exercise 6 — Add TypeElement

Check event.getTypeElement()!=null and print the qualified name. Why can you not always obtain a TypeElement for every Kind, especially right at parse?

### Exercise 7 — AST Without Internals

Get CompilationUnitTree from TaskEvent when available and print getTypeDecls().size(). Do not cast to JCTree. Explain why this approach is less implementation-dependent.

### Exercise 8 — Named Module

Sketch a module-info.java requiring java.compiler and jdk.compiler. Explain why requires jdk.compiler still does not permit importing com.sun.tools.javac.comp.Attr.

### Exercise 9 — Annotation Processing

Replace -proc:none by configuring a real annotation processor in a separate project. Observe ANNOTATION_PROCESSING_ROUND and generated sources. Why are TaskListener and Processor still two different extension types?

### Exercise 10 — Production Observer Design

Write a plan for logging events without slowing builds: bound log volume, check null, do not retain ASTs too long, attach type/source when available, distinguish diagnostics from events, and test on supported JDKs.

## 17. Pre-Completion Checklist

- Know that TaskListener is a public JDK API, not internal implementation com.sun.tools.javac.*.
- Distinguish standard Java SE javax.tools.JavaCompiler from javac-specific com.sun.source.util.JavacTask.
- Know to register TaskListener before task.call().
- Understand started/finished and TaskEvent.Kind, especially PARSE, ENTER, ANALYZE, GENERATE.
- Do not assume invariant event counts and ordering for all programs/JDKs.
- Check for null when reading CompilationUnitTree, JavaFileObject, and TypeElement from TaskEvent.
- Use DiagnosticCollector to understand compilation errors, rather than inferring build status from event counts.
- Ran Java 17 code and observed build/classes/demo/Hello.class.
- Understand -proc:none disables annotation processing in the demo; enabling processors can introduce additional rounds.
- Understand observing AST via com.sun.source.tree does not grant permission to modify JCTree.
- --add-exports is not needed for com.sun.source.util in normal examples.
- Know to close the file manager and not reuse a completed CompilationTask.
- Have a testing strategy when the compiler provider does not support JavacTask.

### Authoritative References for Deeper Study

- **JDK API com.sun.source.util.JavacTask**, **TaskListener**, and **TaskEvent**: public interfaces for tracking javac events.
- **JDK API com.sun.source.tree** and **com.sun.source.util.Trees/TreePathScanner**: AST and syntax-tree observation techniques.
- **Java SE javax.tools.JavaCompiler**, **JavaFileObject**, **DiagnosticListener**: requesting compilation and receiving errors/warnings through standard APIs.
- **Java Platform Module System (JPMS)**: boundaries of java.compiler, jdk.compiler, requires, and exports.
- The javac documentation of the JDK version in use for cross-referencing --release, -proc:none, and output classes.

**In short:** to know which phases javac goes through, create a JavacTask and register a TaskListener, combining TaskEvent and DiagnosticCollector to receive structured information. Observing with public APIs does not require touching Context, Attr, JCTree, or any internal compiler implementation class.