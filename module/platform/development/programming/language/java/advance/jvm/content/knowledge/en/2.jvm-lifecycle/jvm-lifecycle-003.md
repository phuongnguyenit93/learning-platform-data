# Distinguishing JVM Options, System Properties, and Application Arguments

## 1. Objectives and Context

When launching a Java program, multiple pieces of information can appear on the same command line: memory limits, classpath selection, configuration values, input file paths, operating modes, and program-specific flags. They look similar because they are all character strings in the terminal, but they **differ in who handles them, when they are processed, their scope of impact, and the access API**.

After this lesson, you need to:

- Distinguish **Java/JVM launch options** (launcher/VM options), **Java system properties**, and **application arguments**.
- Place parameters in the correct position in the **java** command, and understand the exact role of **-D**.
- Read a system property using **System.getProperty(...)** and read arguments through **String[] args**.
- Understand which configurations must be applied when creating the JVM and which configurations can be changed while the program is running.
- Diagnose situations where parameters are mistakenly passed into **args**, values are not applied, or behavior depends on the shell, build tool, and environment.

This lesson focuses on the startup process of a Java process. An application, framework, or launch script may define additional configuration rules of its own, but those rules must be identified separately.

## 2. One Command Line, Three Types of Information

The common syntax when invoking a class with a **main** method is:

~~~text
java [java/VM options] <MainClassName> [application arguments...]

Example:
java -Xmx256m -Ddemo.mode=dev -cp out Main --input=data.csv
     |       |              |       |    |
     |       |              |       |    +-- application argument
     |       |              |       +------- main class name
     |       |              +--------------- classpath for Java launcher
     |       +------------------------------ option to set a system property
     +-------------------------------------- VM configuration option
~~~

The separator is the **main class name** (or launch target such as **-jar app.jar**). Tokens after the launch target are passed into the program as application arguments. The Java launcher processes its options before calling **main(String[] args)**. The shell also has a phase that processes quotes, whitespace, and escaping before the **java** process receives the tokens.

| Type | Example | Who handles it directly? | How to access/observe |
| --- | --- | --- | --- |
| **JVM/Java launcher option** | **-Xmx256m**, **-ea**, **-cp out**, **-XX:+UseG1GC** | Java launcher and/or VM at startup | VM behavior, management/observability tools; not in **args** if placed correctly |
| **System property** | **-Ddemo.mode=dev** creates property **demo.mode** with value **dev** | The **-D** option is processed by the launcher, then the JVM provides the property to the program | **System.getProperty("demo.mode")** |
| **Application argument** | **--input=data.csv**, **--dry-run**, **report.csv** | **main(...)** or the framework/parser used by the application | **String[] args** |

**Important relationship:** **-D** is both a **command-line option syntax of the java command** and a way to **initialize a system property**. A “system property” is configuration data residing inside the Java process; it is not a type of VM-tuning option like **-Xmx**. You should not force the three groups into completely disjoint sets at the syntax level.

Similarly, **-cp** is a **Java launcher** option that determines where to find classes, not a parameter that adjusts the heap. In everyday communication, options placed before main are sometimes collectively referred to as “JVM arguments”; when analyzing errors, you need to distinguish **VM options** from **launcher options**.

## 3. JVM Options: Configuring the Launch Process

These options are consumed when the Java launcher/JVM prepares the process, and are normally not passed to **main(String[] args)**.

### 3.1. Representative Examples

| Option | Practical Meaning | Notes |
| --- | --- | --- |
| **-Xms128m** | Requests the initial heap size | Common HotSpot option; actual physical memory allocation depends on the VM/OS |
| **-Xmx512m** | Sets the maximum heap size limit for the Java heap | Does not mean a limit on total process RAM; there is also metaspace, stacks, native memory, etc. |
| **-ea** or **-enableassertions** | Enables assertions according to the default/specified scope of the option | Only affects **assert** statements; does not replace input data validation |
| **-XX:+UseG1GC** | Selects G1 GC on HotSpot supporting this option | Belongs to implementation-specific VM options; need to check the JDK/VM in use |
| **-cp out** or **-classpath out** | Specifies the classpath when running the main class | Handled by the launcher; syntax and meaning differ from application arguments |
| **-Dapp.region=apac** | Sets the system property **app.region** | A launcher option to provide property data to Java |

Options starting with **-X** or **-XX** should not be assumed stable across all versions and all JVM vendors. Flags may be unsupported, renamed, or change meaning between runtimes. When a flag is invalid, the program may terminate **before main is called**.

### 3.2. Application Timing and Scope

Configurations such as heap limits or GC selection must be set when starting the corresponding JVM. Calling:

~~~java
// Illustrative code, not a standalone Java program.
System.setProperty("Xmx", "1g");
~~~

**does not** increase the maximum heap to 1 GB, because **Xmx** in the example is just the name of a custom system property; the JVM does not interpret that property as the **-Xmx** option. Similarly, the string **"-Xmx1g"** appearing in **args** does not automatically change the VM.

A running VM may support certain dynamic management mechanisms (depending on the implementation/flags), but that does not make all startup options configurable via the Java API.

## 4. System Properties: A Name–Value Table in the Java Process

**System properties** are a set of string key/value pairs provided by the **java.lang.System** class. There are properties set by the runtime, such as **java.version**, **os.name**, **user.dir**; and there are also properties set by the launcher caller, for example **demo.profile**, **app.port**.

Common operations:

~~~java
// Illustrative lines placed inside a Java method.
String profile = System.getProperty("demo.profile");
String fallback = System.getProperty("demo.profile", "local");
System.setProperty("demo.profile", "test");
System.clearProperty("demo.profile");
~~~

- **System.getProperty(key)** returns the current value; when the key does not exist, the result is **null**.
- **System.getProperty(key, defaultValue)** returns the default value if the key is absent.
- **System.setProperty(key, value)** changes the value within the same JVM process, returning the old value or **null** if it did not exist before; other parts of the process can observe the change.
- **System.clearProperty(key)** removes the property and returns the old value if any.
- Java also allows accessing the set of properties via **System.getProperties()**; you should not print the entire set to logs when it may contain sensitive data.

**-Ddemo.profile=dev** is the common way to initialize a property before **main** runs:

~~~bash
java -Ddemo.profile=dev Main
~~~

The name **demo.profile** is chosen by the application; the JVM does not know what “dev” means if no component reads that property. **-D** by itself does not create a configuration system with hierarchy, data types, validation, or a reload mechanism.

### 4.1. Properties Are Not Equivalent to VM Options

Compare:

~~~text
-Xmx512m                   Processed by the JVM to set the heap limit
-Ddemo.maxItems=512        Creates a property named demo.maxItems, string value "512"
--max-items=512            Application argument if placed after main/JAR
~~~

These three lines are not interchangeable. The application must read, convert the type, and validate **demo.maxItems** itself, while **--max-items=512** only has meaning if the application itself or a framework understands it.

A system property can be changed at runtime, but there is **no guarantee** that all libraries will automatically re-read the new value. A library may have captured the value at initialization; the JVM/OS also has configurations determined before **main** starts. Avoid relying on changing a property at runtime to alter already-initialized system behavior.

### 4.2. System Properties Differ from Environment Variables

These are two different data stores:

| Aspect | System property | Environment variable |
| --- | --- | --- |
| Read API | **System.getProperty("demo.profile")** | **System.getenv("DEMO_PROFILE")** |
| Common source | Java launcher **-D**, runtime, Java code | Process environment passed by OS, shell, container, or process launcher |
| Scope | Inside the JVM; can be modified by Java code via the System API | Environment that the process receives at startup; Java has no standard API to modify the process environment in a way equivalent to **setProperty** |
| Naming convention | For example **demo.profile** | For example **DEMO_PROFILE** |
| Automatic mapping between the two? | **No** | **No** |

For example, setting the environment variable **DEMO_PROFILE=dev** does not cause **System.getProperty("demo.profile")** to automatically return **dev**. If a mapping rule is desired, the application or framework must program that behavior.

The environment variables **JAVA_TOOL_OPTIONS** or **JDK_JAVA_OPTIONS** are a special case: they can affect the JVM/launcher according to runtime rules, but they are still **not** system properties and are not equivalent to application arguments. They have their own limitations and can cause flags to appear “unexpectedly” even though they were not typed directly on the command line.

## 5. Application Arguments: Data Passed to main

With a traditional Java class:

~~~java
public static void main(String[] args) {
    // args contains the tokens located after the main class name in the java command.
}
~~~

Element **args[0]** is the first argument of the program, **not** the main class name, not **java**, and does not contain JVM options that were processed by the launcher in the proper position.

Example:

~~~bash
java Main --mode=batch input.csv
~~~

If the program launches successfully, **args** has two elements: **"--mode=batch"** and **"input.csv"**. Java SE does not define the meaning of **--mode**, **--input**, **--dry-run**, or **--port** in **args**; that is syntax designed by the application or CLI library.

Arguments usually serve to select the run mode, input files, tasks, business ports, and one-off options for the run. You should not automatically infer that every argument with a hyphen is a JVM option.

### 5.1. The Shell Determines How Each Token Is Produced

Example:

~~~bash
java Main "first report.csv"
~~~

With common shells supporting this double-quote syntax, the application argument is **one string** containing a space: **first report.csv**. If you omit the quotes, the shell may split it into **two** arguments: **first** and **report.csv**. Detailed escaping and quoting rules differ among PowerShell, Command Prompt, Bash, and container environments; when portability is needed, check the target shell.

Some tools such as IDEs, Gradle, or container runtimes have two separate configuration fields for **VM options** and **program arguments**. Entering the right value in the wrong field can still cause Java to receive the wrong type of information.

## 6. Runnable Example: Observing All Three Types

Create the file **ConfigLayersDemo.java** (Java 17+):

~~~java
public class ConfigLayersDemo {
    public static void main(String[] args) {
        String profile = System.getProperty("demo.profile", "(unset)");
        String retries = System.getProperty("demo.retries", "(unset)");

        System.out.println("profile=" + profile);
        System.out.println("retries=" + retries);
        System.out.println("argCount=" + args.length);

        for (int i = 0; i < args.length; i++) {
            System.out.println("arg[" + i + "]=" + args[i]);
        }
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac -encoding UTF-8 ConfigLayersDemo.java
java -Xmx256m -Ddemo.profile=dev -Ddemo.retries=3 ConfigLayersDemo --mode=batch report.csv
~~~

**Exact stdout of the program:**

~~~text
profile=dev
retries=3
argCount=2
arg[0]=--mode=batch
arg[1]=report.csv
~~~

Why?

1. **-Xmx256m** is processed by the JVM before calling **main**. It does not appear in **args** and this program does not print the heap limit.
2. **-Ddemo.profile=dev** and **-Ddemo.retries=3** are used to set system properties. The two **System.getProperty(...)** calls read the corresponding strings.
3. **ConfigLayersDemo** is the launch target; the Java launcher loads this class and calls **main**.
4. The two tokens following the launch target are **--mode=batch** and **report.csv**, which are preserved in **args**. The program only prints them; it does not yet have logic to handle batch mode or read files.

### 6.1. Same -D String, Different Position

Run:

~~~bash
java ConfigLayersDemo -Ddemo.profile=dev
~~~

**Exact stdout:**

~~~text
profile=(unset)
retries=(unset)
argCount=1
arg[0]=-Ddemo.profile=dev
~~~

Here, **-Ddemo.profile=dev** stands **after** the main class name, so it is program data. Java does not set the **demo.profile** property in this case. The correct solution is to move **-D** before **ConfigLayersDemo**, rather than changing the property-reading code. Both outputs in this section assume no other environment configuration presets the two demo properties and no code outside the example modifies them.

### 6.2. Wrong Position of -Xmx

~~~bash
java ConfigLayersDemo -Xmx256m
~~~

In this command, **-Xmx256m** is passed into **args[0]**; the heap is not configured by that token. Conversely:

~~~bash
java -Xmx256m ConfigLayersDemo
~~~

is what requests the JVM to set the corresponding maximum heap limit. Do not verify the exact heap size by taking a hardcoded number from the output: the VM may round/adjust the value, and total process memory includes many regions outside the Java heap.

## 7. With a JAR File, Where Is the Separator?

An application packaged as a JAR can be launched with the syntax:

~~~text
java [launcher/JVM options] -jar application.jar [application arguments...]
~~~

**-jar** together with the path **application.jar** selects the runnable artifact, usually relying on **Main-Class** in the manifest to find the main class. This is illustrative syntax; to actually run, the real JAR must have a valid main class and the required dependencies.

Example with correct placement:

~~~bash
java -Xmx512m -Ddemo.profile=prod -jar application.jar --mode=batch input.csv
~~~

- The JVM receives the heap request **-Xmx512m**.
- The system property **demo.profile** is initialized with **prod**.
- The application receives **--mode=batch** and **input.csv** through the main arguments mechanism.

Compare with the command:

~~~bash
java -jar application.jar -Xmx512m -Ddemo.profile=prod
~~~

The two tokens after **application.jar** are application arguments. They **do not automatically** configure the heap or properties. If a framework intentionally parses strings of the form **-D...** as its own convention, that is application logic, not the default behavior of the Java launcher.

**Note:** When launching with **-jar**, the classpath option **-cp** is not used in the same way as when running a main class directly; class lookup in a JAR relies on the launcher's own mechanism and metadata/dependencies. Do not treat **-jar** simply as a replacement for the class name in all cases.

## 8. The Application Defines How to Interpret args and Precedence

**String[] args** only contains strings. Java does not automatically convert **--port=8081** to an integer, does not automatically verify that the port is within a valid range, and does not automatically decide whether **args** or **-Ddemo.port** takes precedence. The application must state the rules.

The next standalone example uses a specific strategy: default **8080**, if the system property **demo.port** is present then use it, and if the argument **--port=...** is present then the argument takes precedence. The parameter **--dry-run** enables dry-run mode.

Create **ApplicationArgsDemo.java**:

~~~java
public class ApplicationArgsDemo {
    public static void main(String[] args) {
        int port = Integer.parseInt(System.getProperty("demo.port", "8080"));
        boolean dryRun = false;

        for (String arg : args) {
            if (arg.startsWith("--port=")) {
                port = Integer.parseInt(arg.substring("--port=".length()));
            } else if (arg.equals("--dry-run")) {
                dryRun = true;
            } else {
                throw new IllegalArgumentException("Unknown argument: " + arg);
            }
        }

        if (port < 1 || port > 65535) {
            throw new IllegalArgumentException("Invalid port: " + port);
        }

        System.out.println("port=" + port);
        System.out.println("dryRun=" + dryRun);
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 ApplicationArgsDemo.java
java -Ddemo.port=9000 ApplicationArgsDemo --port=8081 --dry-run
~~~

**Exact stdout:**

~~~text
port=8081
dryRun=true
~~~

The configuration **9000** from the system property was read first, but the application argument **--port=8081** overrode it according to the **for** loop logic implemented by the application author. This is the **rule of the example**, not a mandatory precedence rule in Java SE.

Try omitting the port argument:

~~~bash
java -Ddemo.port=9000 ApplicationArgsDemo --dry-run
~~~

**Exact stdout:**

~~~text
port=9000
dryRun=true
~~~

If neither **-Ddemo.port** nor **--port=...** is passed, the program uses **8080**. In this learning example, a non-numeric port value will throw **NumberFormatException**; an unknown argument or a port outside 1–65535 will throw **IllegalArgumentException**. Real-world applications typically catch errors, display usage instructions, and exit with an appropriate exit code.

A framework may use different parameter names or precedence orders; for example, Spring Boot has its own command-line properties mechanism. You must not apply one framework's configuration precedence order to all Java programs.

## 9. Position, Lifecycle, and Scope of Impact

Overview timeline:

~~~text
User / script / IDE / container
          |
          v
Shell or launch tool builds tokens
          |
          v
Java launcher parses options and identifies main class/JAR
          |
          +--> VM options: configure JVM at startup
          |
          +--> -D: initialize system properties
          |
          v
JVM initializes, loads/links/initializes classes on demand
          |
          v
Calls public static void main(String[] args)
          |
          +--> System.getProperty(...) reads properties table
          |
          +--> args contains tokens received by the program
          |
          v
Application parses args, initializes components, and runs business logic
~~~

Understand that this is an overview diagram, not a list of every JVM phase in strict absolute order: the launcher and JVM perform many internal tasks, and classes can be loaded before or after main depending on demand.

| Question | JVM/launcher option | System property | Application argument |
| --- | --- | --- | --- |
| Where is it provided at runtime? | Before the main/JAR target | Usually via **-D** before the main/JAR target | After the main/JAR target |
| First processing time | Before the program enters main | When the VM initializes properties; the application can read it later | When main/framework receives and parses it |
| Who owns the meaning? | Specific Java launcher/JVM | The JVM owns the property table; the application/library defines the meaning of custom keys | The application/framework owns the syntax and behavior |
| Automatically included in **args**? | No, if placed in the right position | No, for **-D** processed before the main target | Yes |
| Can it be modified at runtime? | Most startup options cannot be modified via a system property | Has **setProperty/clearProperty** APIs, but components using it do not necessarily reload | Logical data created by the application after parsing can be changed; the original **args** array is not automatically “updated” by Java |

### 9.1. System Properties Are Shared Within One JVM

Components within the same process typically access the same system properties table. If library A calls **System.setProperty("demo.profile", "test")**, code B calling **System.getProperty(...)** later may see the new value. Arbitrarily using properties to store dynamic business state can create hidden dependencies and race conditions between libraries/tests.

In multi-threaded applications, reading/writing properties must be evaluated for consistency and how libraries consume configuration; even if operations on the properties table itself are safely synchronized, **multi-field application configuration** does not automatically become an atomic transaction.

### 9.2. JVM Options Usually Belong to a Specific Process

One machine can run multiple Java processes, each with its own options, properties, and args. Passing **-Xmx512m** to process A does not automatically change the heap of B. Setting **-Dapp.mode=dev** in the launch command of one program also does not make it a system property of other Java processes.

For example, the **java** command running an application invoked by Gradle may belong to a different process than the **Gradle daemon**. Setting **-Ddemo.profile=dev** on the Gradle invocation command does not by default guarantee that a **JavaExec** task or a forked application will inherit that property; you need to configure it in the exact place where the tool creates the child process.

## 10. How to Observe and Diagnose

### 10.1. Observing Runtime and System Properties

In Java code:

~~~java
// Illustrative code placed inside a method:
System.out.println(System.getProperty("java.version"));
System.out.println(System.getProperty("demo.profile", "(unset)"));
~~~

**java.version** reflects the executing runtime. **demo.profile** reflects the system property value at the time of the call. There is no fixed output for **java.version** across all machines.

From the command line, the **java -version** tool reports the version/runtime, but it is not a substitute for testing the application run. With a supporting HotSpot/JDK, you can use diagnostic commands:

~~~bash
java -XshowSettings:properties -version
java -XX:+PrintFlagsFinal -version
~~~

The output is long, depends on the JDK and implementation, and often includes messages on **stderr**. Do not treat the entire output of those two commands as stable across versions. The **jcmd** tool, when accessible and supported by the runtime, also has commands like **VM.command_line** or **VM.system_properties** to inspect a running JVM; the list of available commands depends on the JVM.

In a program, **ManagementFactory.getRuntimeMXBean().getInputArguments()** can provide the JVM launch arguments recorded by the runtime, but it is **not** an API to reconstruct the original shell command line or the application's **String[] args**. Do not use it in place of a CLI parser.

### 10.2. Symptoms and Troubleshooting

| Symptom | First check | How to fix |
| --- | --- | --- |
| Property returns **null** or default | Is **-Dkey=value** placed before the main class name or **-jar app.jar**? Is the key name cased correctly? | Place **-D** in the right position, use the exact name, and check the configuration source |
| **args** unexpectedly contains **-Xmx512m** or **-D...** | Was the option placed after main/JAR? | Move it before the launch target |
| JVM fails to start due to unsupported flag | Does the JDK version and vendor accept that **-X/-XX** flag? | Consult the documentation of the VM in use; remove/replace the incompatible flag |
| Property was set, but heap did not change | Was **-D...** confused with **-Xmx...**? | Place the corresponding VM option before main/JAR |
| Application reports **Unknown argument** | Does the parameter belong to the application's custom syntax? | Read the application's CLI help/contract; fix the name and position |
| Property is correct, but the library still uses the old value | Did the library cache the configuration at initialization? | Provide the value early, or use an official reload mechanism if available |
| Runs correctly in IDE, but fails in terminal | Were VM options, program arguments, and environment variables entered into the corresponding fields? | Compare the actual run configuration and working directory |
| Arguments with spaces get split | How did the shell handle quoting? | Quote appropriately for the target shell; verify the actual **args** received |
| Changed value in Gradle, but forked app does not receive it | Are you configuring Gradle's JVM or the application's JVM? | Pass VM options/properties/args on the right task and process |

### 10.3. Be Careful with Sensitive Data

Do not put passwords, tokens, or secret keys on the command line or in system properties and log them indiscriminately. Command-line arguments and some system properties can be exposed by management tools, process info, error reports, or diagnostics depending on the environment. Use an appropriate secret management mechanism and control logging.

## 11. Self-Practice Exercises

Use the **ConfigLayersDemo** class in section 6 and predict the results beforehand. The questions below assume no environment variables or other tools inject the demo properties.

**Exercise 1.**

~~~bash
java -Ddemo.profile=test ConfigLayersDemo alpha beta
~~~

Question: What are **profile**, **retries**, **argCount**, and the elements of **args**?

**Answer:**

~~~text
profile=test
retries=(unset)
argCount=2
arg[0]=alpha
arg[1]=beta
~~~

**Exercise 2.**

~~~bash
java ConfigLayersDemo --profile=test
~~~

Question: Is there a system property **demo.profile=test**?

**Answer:** Not automatically. **--profile=test** is **args[0]**; the example only prints this string. For the application to understand it, you must write a CLI parser or use a corresponding framework.

**Exercise 3.**

~~~bash
java -Xmx256m ConfigLayersDemo --dry-run
~~~

Question: Is there any way to read **-Xmx256m** via **args[0]**?

**Answer:** Not in this command; **args[0]** is **--dry-run**. **-Xmx256m** was already consumed by the JVM before main. To inspect the heap limit, you can use a runtime-contract API such as **Runtime.getRuntime().maxMemory()**, but do not assume the number must match the value written on the command line down to the exact byte.

**Exercise 4.** Compare:

~~~bash
java -Ddemo.profile=dev ConfigLayersDemo
java ConfigLayersDemo -Ddemo.profile=dev
~~~

**Answer:** The first command creates a system property and passes no application arguments; the second command does not create that property from **-D** and instead passes the raw token into **args[0]**. Position determines the role.

**Exercise 5.** In **ApplicationArgsDemo**, why does **--port=8081** win over **-Ddemo.port=9000**?

**Answer:** The code reads the system property as the initial value, then loops through **args** and reassigns the **port** variable. Changing the processing order in code can create a different rule; the JVM does not enforce application precedence order.

## 12. Implementation Checklist

1. Identify **who** needs the parameter: the VM/launcher, the property system, or application logic.
2. Choose the **right syntax and position**: options before main/JAR; app args after main/JAR.
3. Verify that the JDK version/JVM supports the **-X/-XX** flags, and avoid applying unsupported flags.
4. For properties you create, name them clearly, convert/validate data types, and document defaults and mutability scope.
5. For CLI args, define the parser, error messages, help, and precedence rules with other configuration sources.
6. Verify that the shell/IDE/build tool/container passes the **right tokens** to the **right Java process**.
7. Test actual operation on the target JVM; avoid logging sensitive information.

**Remember:** **-Xmx** changes VM configuration; **-Dkey=value** is a startup option used to set a **system property**, read via **System.getProperty(key)**; and tokens after the main class name or **-jar app.jar** go into **String[] args** and only have meaning when the application interprets them. These three layers are related on the same command line, but they are not interchangeable.
