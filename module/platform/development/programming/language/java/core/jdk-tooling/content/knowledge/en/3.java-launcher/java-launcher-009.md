# VM options in the Java launcher

## 1. What is a VM option?

When running a Java program, the **java** command starts the Java Virtual Machine (JVM), loads the main class, and invokes the **main** method. A VM option is a command-line option used to configure or observe the JVM for a single run. Options can adjust the heap memory area, Garbage Collector, thread stack, system properties, assertions, logging, and diagnostic tools.

VM options are processed when the JVM starts. They typically affect the entire Java process, so it is important to place them in the right position on the command line and understand the scope of each flag.

A Java command can consist of three groups of components:

1. **VM options**: configure the JVM, for example **-Xmx1g**, **-Xms256m**, **-Dapp.env=dev**, **-ea**.
2. **Launcher options**: instruct the Java launcher on how to find and select the program, for example **-cp**, **--class-path**, **-jar**, **-m**.
3. **Application arguments**: arguments passed into the program's **main(String[] args)** method.

These three groups serve different purposes. **-cp** selects the classpath, whereas **-Xmx** limits the heap; one option chooses how to launch the application, and the other configures JVM memory.

## 2. Syntax and placement of VM options

General syntax when running a class:

~~~bash
java [VM options] [launcher options] <main-class> [application arguments...]
~~~

When running a JAR file:

~~~bash
java [VM options] -jar <application.jar> [application arguments...]
~~~

When running a module:

~~~bash
java [VM options] -m <module>/<main-class> [application arguments...]
~~~

Example:

~~~bash
java -Xms256m -Xmx1g -Dapp.env=dev -ea -cp app/classes com.example.Main input.txt
~~~

In this example:

- **-Xms256m** sets the initial heap size to 256 MiB.
- **-Xmx1g** sets the maximum heap limit to 1 GiB.
- **-Dapp.env=dev** creates a system property named **app.env** with the value **dev**.
- **-ea** enables assertion checking in application classes.
- **-cp app/classes** is a launcher option specifying where to find classes.
- **com.example.Main** is the main class.
- **input.txt** is an application argument, which appears in **args**.

In JAR mode, VM options must appear before **-jar** and the JAR filename:

~~~bash
java -Xmx512m -Dapp.env=prod -jar app.jar --port 8080
~~~

Here **--port 8080** is passed to the application. If you write **-Dapp.env=prod** after **app.jar**, that token also becomes an application argument; it is no longer processed by the JVM as a system property.

Similarly, in class-execution mode, every token after the class name is passed to **main**. Therefore, always place VM options before the class name, JAR filename, or module to be run.

When using **-jar**, the JAR is selected as the class source and application entry point according to the **Main-Class** attribute in the manifest. An external classpath configured with **-cp** does not replace the classpath in **-jar** mode. If you need to specify the classpath yourself, you typically run the main class using **-cp** instead of **-jar**.

## 3. Common option groups

### Standard options

Several options are broadly supported by the Java launcher:

| Option | Meaning |
|---|---|
| **-Dname=value** | Set a system property |
| **-ea** or **-enableassertions** | Enable assertions |
| **-da** or **-disableassertions** | Disable assertions |
| **-esa** | Enable system assertions |
| **-dsa** | Disable system assertions |
| **-verbose:gc** | Display GC information in legacy verbose format |
| **-agentlib:...** | Load a native agent by library name |
| **-agentpath:...** | Load a native agent by path |
| **-javaagent:...** | Load a Java instrumentation agent |

### Extended -X options

Options starting with **-X** are commonly called extended or non-standard options. They are supported by specific JVMs and may vary by vendor or version. Familiar examples include **-Xms**, **-Xmx**, **-Xss**, **-Xlog**, and **-Xint**.

### Advanced -XX options

Options starting with **-XX** typically control advanced HotSpot flags. Common syntax:

~~~text
-XX:+FlagName
-XX:-FlagName
-XX:FlagName=value
~~~

- **-XX:+FlagName** enables a boolean flag.
- **-XX:-FlagName** disables a boolean flag.
- **-XX:FlagName=value** assigns a value to a flag.

Example:

~~~bash
java -XX:+UseG1GC -Xmx1g -jar app.jar
~~~

**-XX** flags are not a universal compatibility contract across all JVMs. A flag may not exist or may have a different meaning on another vendor or version. Check the documentation for the exact JDK version you are running before using them in a deployment environment.

## 4. JVM memory configuration

### Initial heap and maximum heap

The heap is the memory area the JVM uses to allocate most Java objects. Two fundamental options:

- **-Xms<size>**: initial heap size.
- **-Xmx<size>**: maximum heap size.

Example:

~~~bash
java -Xms256m -Xmx2g -jar app.jar
~~~

The JVM starts with an initial heap of 256 MiB and is allowed to expand up to a maximum of 2 GiB. The actual heap size and how the JVM uses memory regions also depend on the version, platform, and runtime conditions.

Common suffixes:

| Suffix | Unit |
|---|---|
| **k** or **K** | KiB, multiples of 1024 bytes |
| **m** or **M** | MiB, multiples of 1024 KiB |
| **g** or **G** | GiB, multiples of 1024 MiB |

For example, **-Xmx512m** sets the maximum heap to 512 MiB; **-Xmx2g** sets the maximum to 2 GiB. If no suffix is given, the numeric value is interpreted in bytes. Ensure that **-Xms** is not greater than **-Xmx**.

### Heap is not the entire process memory

**-Xmx** limits the heap, not the total RAM that the Java process can use. The process also needs memory for:

- Metaspace storing class metadata.
- Code cache containing machine code generated by the JIT compiler.
- Stacks of individual Java threads.
- Direct buffers, native libraries, and internal JVM structures.
- Memory reserved for agents and other native components.

Therefore, the process can be terminated by the operating system or container even when the heap has not reached **-Xmx**. When setting heap limits for a container, leave headroom for native memory, thread stacks, JVM overhead, and other processes.

### Thread stack

**-Xss<size>** sets the stack size for each Java thread:

~~~bash
java -Xss1m -jar app.jar
~~~

The stack holds method call frames, local variables, and thread execution state. A stack that is too small can lead to **StackOverflowError** when call depth is high; a stack that is too large increases native memory demand when the application creates many threads. Only change this value when you understand the application's characteristics and have measured data.

### Metaspace and direct memory

Some advanced limits can be useful during diagnostics:

~~~bash
java -XX:MaxMetaspaceSize=256m -XX:MaxDirectMemorySize=512m -jar app.jar
~~~

**MaxMetaspaceSize** sets a limit on Metaspace; **MaxDirectMemorySize** sets a limit on direct buffer memory managed by the JVM. These are HotSpot flags and should not be set arbitrarily. Setting limits too low can cause the application to fail when loading many classes or allocating many direct buffers.

## 5. Choosing a Garbage Collector

The Garbage Collector reclaims heap memory that the program no longer references. The JVM provides multiple garbage collectors with different characteristics regarding throughput, latency, and resource consumption.

Example on HotSpot:

~~~bash
java -XX:+UseG1GC -jar app.jar
~~~

The **-XX:+UseG1GC** flag requests the G1 Garbage Collector. Another option on supported HotSpot builds is:

~~~bash
java -XX:+UseSerialGC -jar app.jar
~~~

There is no single optimal garbage collector for every application. The choice depends on heap size, CPU core count, latency targets, throughput, and object allocation patterns. The JVM can select a default collector based on the platform and configuration; do not change the default just because you saw a flag in an example.

When making a decision, measure pause times, throughput, and CPU usage on a representative workload. Record the JDK version and all active flags so test runs can be compared fairly.

## 6. System properties with -D

The **-Dname=value** option sets a system property when the JVM starts:

~~~bash
java -Dapp.env=dev -Dapp.region=ap-southeast-1 -jar app.jar
~~~

The application reads the value using the **System.getProperty** API:

~~~java
String environment = System.getProperty("app.env");
String region = System.getProperty("app.region", "unknown");
~~~

A system property is a string name-value pair inside the JVM. It is different from an operating system environment variable:

- **System.getProperty("app.env")** reads a system property set via **-D** or through the Java API.
- **System.getenv("APP_ENV")** reads an environment variable provided by the operating system.

Do not confuse **-Dapp.env=dev** with creating an **APP_ENV** environment variable. Property names are case-sensitive. If a value contains spaces or special characters, enclose the token in quotes according to the rules of the shell you are using.

In PowerShell, it is good practice to enclose the entire **-D** token in single quotes so PowerShell passes the token verbatim to Java:

~~~powershell
java '-Dapp.env=dev' -jar app.jar
~~~

Do not pass passwords, tokens, or secrets in system properties on the command line. Command-line arguments may appear in process lists, logs, or diagnostic tools depending on the environment.

## 7. Enabling and disabling assertions

Java assertions allow you to verify assumptions during development and testing. Assertions are disabled by default during normal program execution.

Enable all assertions in application classes:

~~~bash
java -ea -jar app.jar
~~~

Disable assertions:

~~~bash
java -da -jar app.jar
~~~

You can enable them by package or class:

~~~bash
java -ea:com.example... -jar app.jar
java -ea:com.example.OrderService -jar app.jar
~~~

The package form with three dots applies to the package and its subpackages. The class-name form applies to the specified class. The **-esa** option enables assertions in system classes; **-dsa** disables them.

In Java code:

~~~java
int quantity = 3;
assert quantity > 0 : "quantity must be positive";
~~~

When assertions are enabled, a false condition throws **AssertionError**, optionally with a message. Do not use assertions to replace user input validation or mandatory checks in production, because assertions can be disabled. For mandatory business checks, use explicit conditions and error handling.

## 8. JVM logging and diagnostics

### Unified logging

Since Java 9, the JVM has a unified logging system. On modern JDKs, you can enable GC logging with:

~~~bash
java -Xlog:gc -jar app.jar
~~~

Write GC logs to a file with timestamps and tags:

~~~bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags -jar app.jar
~~~

**-Xlog** has syntax for selecting tags, log levels, output, and decorators. The **\*** after **gc** selects matching GC tags. You can view the syntax guide on the JDK you are using with **java -Xlog:help**. GC logs help analyze collection cycles, pause times, and heap behavior; overly verbose logging can generate large amounts of data and affect performance.

### Heap dump on out-of-memory

You can instruct the JVM to generate a heap dump when an **OutOfMemoryError** occurs:

~~~bash
java -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=./dumps -jar app.jar
~~~

The target path must be writable; create the **dumps** directory before running if it does not already exist. Heap dumps can contain sensitive data that the application held in memory. Protect the files, restrict access permissions, and delete them according to your retention policy once analysis is complete.

### Java agents and debugging tools

**-javaagent:path/to/agent.jar** loads a Java instrumentation agent. An agent can observe or transform bytecode as classes are loaded, for example for monitoring, profiling, or testing tools.

**-agentlib** and **-agentpath** load native agents. To open the JDWP debug protocol in a development environment, for example:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -jar app.jar
~~~

This option opens a debug port on the loopback address. **suspend=n** allows the application to continue running instead of waiting for a debugger to connect. Only enable the debug agent when necessary and when the environment and listening address are properly controlled.

## 9. Sample program to verify VM options

Create the file **VmOptionsDemo.java**:

~~~java
public class VmOptionsDemo {
    public static void main(String[] args) {
        String environment = System.getProperty("app.env", "not-set");
        long maxHeapMiB =
                Runtime.getRuntime().maxMemory() / (1024 * 1024);

        System.out.println("app.env=" + environment);
        System.out.println("maxHeapMiB=" + maxHeapMiB);
        System.out.println("assertions="
                + VmOptionsDemo.class.desiredAssertionStatus());
        System.out.println("argCount=" + args.length);

        for (int i = 0; i < args.length; i++) {
            System.out.println("arg[" + i + "]=" + args[i]);
        }
    }
}
~~~

Compile:

~~~bash
javac VmOptionsDemo.java
~~~

Run on Linux or macOS:

~~~bash
java -Xms64m -Xmx256m -Dapp.env=dev -ea -cp . VmOptionsDemo one two
~~~

Run in PowerShell:

~~~powershell
java -Xms64m -Xmx256m '-Dapp.env=dev' -ea -cp . VmOptionsDemo one two
~~~

Output:

~~~text
app.env=dev
maxHeapMiB=256
assertions=true
argCount=2
arg[0]=one
arg[1]=two
~~~

The program demonstrates three distinct effects:

- **System.getProperty** reads the value set by **-Dapp.env=dev**.
- **Runtime.getRuntime().maxMemory()** reflects the maximum heap limit reported by the JVM to the application; in this example, it is 256 MiB.
- **desiredAssertionStatus()** indicates whether assertions are enabled or disabled for the class.

The tokens **one** and **two** appear after the class name, so they become elements of the **args** array. If you replace **-ea** with **-da**, the assertion line will be **assertions=false**. If you omit **-Dapp.env=dev**, the default value in the program will be **not-set**.

## 10. Looking up and inspecting active flags

Each JDK version has its own set of options. Use the following commands to view help output from the launcher itself:

~~~bash
java -help
java -X
java -XX:+PrintFlagsFinal -version
java -XshowSettings:vm -version
~~~

- **java -help** lists launcher options and standard options.
- **java -X** displays the extended options supported by the JVM.
- **-XX:+PrintFlagsFinal** prints HotSpot flags and their final values after initialization; the output is quite long.
- **-XshowSettings:vm** displays VM configuration settings and then prints the version.

For a running process, the JDK provides **jcmd** to inspect its information. First, list the Java processes:

~~~bash
jcmd -l
~~~

Then use the PID of the process you want to inspect:

~~~bash
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
~~~

**VM.command_line** shows the launch command line; **VM.flags** shows the active VM flags. These commands typically require the same user account and an available JVM attach mechanism. **jcmd** is a JDK tool; machines with only a minimal runtime installed may not have it.

## 11. Common errors and troubleshooting

### Unrecognized VM option

The JVM reports that it does not recognize an option. Possible causes:

- The flag is not supported by the JVM vendor in use.
- The flag was removed or changed in a newer version.
- A typo, syntax error, or missing value.
- Using a HotSpot flag on a JVM with a different set of flags.

Check **java -version**, **java -X**, and the documentation for the exact vendor and JDK version. Do not copy a set of flags verbatim from another machine without verifying them.

### Could not create the Java Virtual Machine

This message usually accompanies an invalid option, an unsuitable memory size, or conflicting configuration. Read the error lines immediately above it to find the offending flag. Try removing newly added options one by one in a test environment to isolate the cause.

### OutOfMemoryError despite setting -Xmx

**-Xmx** only limits the heap. **OutOfMemoryError** can also be related to Metaspace, direct buffers, or other resources. Additionally, the operating system or container may terminate the process because total memory usage exceeds the limit before the heap reaches **-Xmx**. Identify the error type and inspect logs, heap dumps, or native memory metrics before increasing the limit.

### VM option has no effect

Check the order of tokens on the command line. VM options must precede the class name, **-jar**, or **-m**. Also check run configurations in your IDE, startup scripts, service managers, and environment variables such as **JDK_JAVA_OPTIONS** or **JAVA_TOOL_OPTIONS**, as they can inject additional options into the process.

In an IDE, distinguish the **VM options** field from **Program arguments**. If you enter **-Xmx** into Program arguments, the application receives that string as an ordinary argument and the heap does not change.

### Configuring too many flags

Adding many **-XX** flags does not mean the JVM will run faster. Some flags may conflict, disable default optimizations, or only suit a specific workload. Start from the default configuration, measure with real data, change one group of flags at a time, and save results so you can revert to a known configuration.

## 12. Checklist when using VM options

- [ ] Identify the exact JVM and version using **java -version**.
- [ ] Distinguish between VM options, launcher options, and application arguments.
- [ ] Place VM options before the class name, **-jar**, or **-m**.
- [ ] Use **-Xms** and **-Xmx** intentionally; leave headroom for native memory and the runtime environment.
- [ ] Only change the GC or **-XX** flags when backed by documentation and measured data.
- [ ] Use **-D** for system properties and **System.getenv** for environment variables.
- [ ] Enable assertions with **-ea** during testing when needed; do not rely on assertions for mandatory checks.
- [ ] Use **-Xlog** and heap dumps to gather evidence during diagnostics.
- [ ] Inspect active flags with **jcmd** or **PrintFlagsFinal** when needed.
- [ ] Record the flags used along with the JDK version to reproduce results.
