# Main Class in the Java Launcher

## Objectives

After this lesson, you will be able to identify the main class that the Java launcher will run, write a valid entry point, pass command-line arguments, run programs from a class directory, JAR, module, or source file, and understand the changes to instance main methods introduced in Java 25.

## 1. What Is a Main Class?

A **main class** is the class selected as the starting point (initial class) when launching a Java application. The Java launcher is typically the program named **java** in the JDK's bin directory. The launcher identifies the class or application to run, starts the JVM, loads the selected class, and instructs the JVM to invoke a valid main method.

A main class does not have to be named Main. The class name can be App, HelloWorld, Server, com.example.Application, or any other valid identifier. The name Main is simply a common convention used in examples.

It is important to distinguish between:

- **Main class:** the class selected to start a given run.
- **main method:** the entry point method inside the main class.
- **Java launcher:** the java tool that accepts the command and sets up the launch.
- **JVM:** the virtual machine that executes bytecode after the launcher starts the runtime.

A Java library can contain hundreds of classes without a single main method. Only programs that need to be run directly require an entry point. A project can also contain multiple classes with a main method to provide different applications or utilities; on each run, the launcher selects one specific starting point.

## 2. The Traditional Entry Point

From Java 8 through Java 24, the standard entry point form is:

~~~java
public class Main {
    public static void main(String[] args) {
        System.out.println("Hello, Java!");
    }
}
~~~

This method has four key parts:

| Part | Meaning |
|---|---|
| public | Allows the launcher to access the method under the traditional entry point rules |
| static | Invokes the method directly on the class without creating an object first |
| void | The method does not return a value |
| String[] args | An array containing the program arguments received from the command line |

The method name must be main in lowercase. Java is case-sensitive, so Main, MAIN, or start are not equivalent entry point names.

### Why is main static?

With the traditional entry point, the JVM needs to start running the program before the application can create ordinary objects on its own. A static method belongs to the class, so it can be called without instantiating that class.

Starting in Java 25, Java also supports instance main methods. When using this form, the launcher creates an instance of the main class before calling the method. A later section explains the differences in detail.

### Why is the parameter String[]?

The launcher converts the command-line arguments into a String array and passes that array into main. For example:

~~~java
public class Main {
    public static void main(String[] args) {
        System.out.println("Số đối số: " + args.length);

        for (int i = 0; i < args.length; i++) {
            System.out.println("args[" + i + "] = " + args[i]);
        }
    }
}
~~~

Run:

~~~text
java Main Alice "Java Core"
~~~

Output:

~~~text
Số đối số: 2
args[0] = Alice
args[1] = Java Core
~~~

The first argument is at index 0. Quotation marks tell the shell to treat Java Core as a single argument. The args array only contains arguments that appear after the main class name, JAR name, source file name, or module target.

### Is String... equivalent to String[]?

Yes. The following declaration is also valid:

~~~java
public static void main(String... args) {
    System.out.println(args.length);
}
~~~

In Java, String... is varargs syntax and has the same array type String[] at the method signature level. You cannot declare two main methods with String[] and String... in the same class because they have the same signature.

The main method can also declare a throws clause, for example public static void main(String[] args) throws Exception. The return type must still be void.

## 3. Complete Example: Compiling and Running a Main Class

Create a file named Main.java:

~~~java
package com.example;

public class Main {
    public static void main(String[] args) {
        System.out.println("Java launcher started the application.");
        System.out.println("Argument count: " + args.length);

        for (int i = 0; i < args.length; i++) {
            System.out.printf("args[%d] = %s%n", i, args[i]);
        }
    }
}
~~~

Suppose the initial directory structure is:

~~~text
project/
└── src/
    └── com/
        └── example/
            └── Main.java
~~~

Open a terminal in the project directory and compile:

~~~bash
javac -d out src/com/example/Main.java
~~~

The -d out option tells the compiler to place the .class files in the out directory and generate the matching package directory structure.

After compilation, the structure will look like this:

~~~text
project/
├── src/
│   └── com/
│       └── example/
│           └── Main.java
└── out/
    └── com/
        └── example/
            └── Main.class
~~~

Run the main class:

~~~bash
java -cp out com.example.Main Alice "Java Core"
~~~

Exact output:

~~~text
Java launcher started the application.
Argument count: 2
args[0] = Alice
args[1] = Java Core
~~~

Explanation:

- java invokes the Java launcher.
- -cp out puts the out directory on the classpath so the JVM can find the class and any dependent classes.
- com.example.Main is the fully qualified class name, consisting of the package and class name.
- Alice and Java Core are arguments passed to the main method.

### Class name, file name, and package

If a source file declares a public top-level class named Main, Java rules require the file name to be Main.java. With the package com.example, the file is typically located in the com/example directory under the source root.

When running a compiled class:

- Specify the fully qualified class name, for example com.example.Main.
- Do not include the .class extension.
- Do not pass the file path Main.class in place of the class name.
- The classpath must point to the root directory above the package directory.

For example, with out/com/example/Main.class, the classpath is out and the class name is com.example.Main. If you set the classpath to out/com/example, the JVM will look for the class at the wrong directory level when using the fully qualified name com.example.Main.

## 4. How Does the Java Launcher Select and Invoke main?

A typical launch follows this sequence:

1. The launcher reads the JVM options and identifies the target to run: a class, JAR, module, or source file.
2. The launcher configures the classpath/module path and required environment settings.
3. The JVM loads the specified initial class or interface.
4. The JVM links the class: verifying bytecode structure, preparing runtime data, and resolving references as needed.
5. The JVM initializes the class. Static field initializers and static initializers of the class are executed according to Java initialization rules.
6. The JVM identifies a valid main method according to the Java version and invokes it.
7. The program continues running, creating objects, calling methods, and using other classes according to the application logic.

Because the class is initialized before main is called, static initializers can run before the first statement inside main. If main is an instance method, the main class constructor also runs before the body of main.

Example:

~~~java
public class StartupOrder {
    static {
        System.out.println("1. Static initializer");
    }

    public StartupOrder() {
        System.out.println("2. Constructor");
    }

    public static void main(String[] args) {
        System.out.println("3. main method");
    }
}
~~~

Output:

~~~text
1. Static initializer
3. main method
~~~

In this example, main is static, so the launcher does not create a StartupOrder object, and the constructor does not run. If an instance main method is used on Java 25+, the constructor is called before main.

Note: the initialization order of superclasses and classes, as well as when dependent classes are loaded and linked, follows the Java Language Specification and the JVM Specification. You should not assume that all application classes are loaded before main begins.

## 5. Ways to Specify the Main Class When Running an Application

The Java launcher supports multiple execution modes. You should distinguish between the target specified on the command line and the main method located inside that target.

### Running a compiled class

~~~bash
java -cp out com.example.Main
~~~

You can use -classpath or --class-path instead of -cp:

~~~bash
java --class-path out com.example.Main
~~~

If the classpath contains multiple directories or JARs, the path separator depends on the operating system:

~~~text
Windows:       out;lib/*;config
Linux/macOS:   out:lib/*:config
~~~

Paths containing spaces should be enclosed in quotation marks according to the rules of the shell you are using.

### Running a source file directly

Since JDK 11, the Java launcher supports source-file mode, allowing you to run a program from a .java file without invoking javac separately:

~~~bash
java Hello.java
~~~

The launcher compiles the source file during startup and runs the appropriate class. This mode is useful for small examples, scripts, and simple command-line tools.

You can specify the language/API version with the --source option, for example:

~~~bash
java --source 17 Hello.java
~~~

For example, --source 17 requires a launcher from JDK 17 or later. When --source 17 is specified, the source code is checked against Java 17 language and API levels. A file using features introduced in Java 25 cannot run at source level 17.

Source-file mode does not fully replace a build system. The launcher does not automatically discover and compile every source file in a project like a full build command. For applications with multiple modules, multiple dependencies, or annotation processing, use javac, Gradle, or Maven.

### Running a main class in a JAR

A JAR can declare a default main class in its manifest using the Main-Class attribute.

For example, if the compiled classes are in out, create an executable JAR using JDK 9 or later:

~~~bash
jar --create --file app.jar --main-class com.example.Main -C out .
~~~

Run:

~~~bash
java -jar app.jar Alice
~~~

When using -jar, the launcher reads the main class from the Main-Class attribute in the manifest. In this mode, the specified JAR is the source of all user classes; other classpath settings on the command line are ignored. If the application needs external dependencies, package them using an appropriate strategy, declare Class-Path in the manifest where appropriate, or use another deployment mechanism.

Example manifest:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.Main
~~~

The class name in Main-Class must be the fully qualified package-and-class name without the .class extension.

### Running a main class in a module

For modular applications, you can specify the module path and main class:

~~~bash
java --module-path mods -m com.example.app/com.example.Main
~~~

Where:

- --module-path or -p specifies where the modules are located.
- -m or --module selects the module to run.
- com.example.app is the module name.
- com.example.Main is the main class inside the module.

If the module already declares a default main class in its module descriptor, you can run the module without specifying /com.example.Main. When you want to be explicit or need to select a different entry point, specify both the module name and the main class.

### java and javaw on Windows

java launches a Java application attached to the current console. javaw also launches a Java application, but without opening an associated console window. javaw is typically suited for desktop applications that do not need a console. When a launch fails, javaw may display an error dialog.

## 6. Changes from Java 25: Instance Main Methods

Before Java 25, the traditional entry point had to be public static void main(String[] args) or public static void main(String... args). Java 25 standardized **Compact Source Files and Instance Main Methods** via JEP 512. Starting from this release, the launch protocol accepts simpler forms of the main method.

In Java 25 and later, a candidate main method must:

- Be named main.
- Have a return type of void.
- Have either a single String[] (or String...) parameter or no parameters.
- Have public, protected, or package-private access.
- Be either a static or an instance method.

A private method is not a candidate main method under these rules. The traditional public static void main(String[] args) form remains valid and continues to be the most broadly compatible option.

### Four common forms in Java 25+

~~~java
public static void main(String[] args) {
    System.out.println("Static main with arguments");
}
~~~

~~~java
static void main() {
    System.out.println("Static main without arguments");
}
~~~

~~~java
void main(String[] args) {
    System.out.println("Instance main with arguments");
}
~~~

~~~java
void main() {
    System.out.println("Instance main without arguments");
}
~~~

The examples above assume compilation and execution on JDK 25 or later. On Java 8 through Java 24, only the static form with a single String[]/String... parameter is the standard entry point.

### Main method selection rules

If a class has multiple candidate main methods, the launcher prioritizes by parameter:

1. If there is a candidate main method with a single String[] parameter, the launcher selects that candidate.
2. If there is no single-parameter candidate, the launcher selects a candidate main method with no parameters.
3. If the selected method is static, the launcher invokes it directly.
4. If the selected method is an instance method, the launcher creates an instance of the main class using its no-arg constructor and then invokes the method on that object.

Example:

~~~java
public class MainChoice {
    public static void main(String[] args) {
        System.out.println("main(String[] args)");
    }

    void main() {
        System.out.println("main()");
    }
}
~~~

When run on JDK 25 or later, the output is:

~~~text
main(String[] args)
~~~

The method with the parameter takes precedence. Having an additional main() method in the class does not cause the launcher to invoke both methods.

### Instance main requires a no-arg constructor

The following example can be run on JDK 25 or later:

~~~java
public class InstanceMain {
    private final String applicationName;

    public InstanceMain() {
        applicationName = "Java Core";
    }

    void main(String[] args) {
        System.out.println("Application: " + applicationName);
        System.out.println("Arguments: " + args.length);
    }
}
~~~

Run:

~~~bash
javac InstanceMain.java
java InstanceMain one two
~~~

Output:

~~~text
Application: Java Core
Arguments: 2
~~~

The launcher creates an InstanceMain object using the no-arg constructor and then invokes the instance main method. If the class declares no constructors at all, the compiler generates a default no-arg constructor. If the class only defines constructors that require arguments, the launcher cannot instantiate it through this process; provide an appropriate no-arg constructor or use a static main method.

### When should you use static main?

The public static void main(String[] args) form has the advantage of compatibility with older JDKs, frameworks, IDEs, build tools, and long-standing documentation. It also makes the entry point immediately recognizable to readers.

Instance main is well suited for tutorials, small examples, or programs that need to access instance fields/methods without manually creating an initial object. For applications that need to run across multiple JDK generations, prefer the traditional signature unless the project already specifies JDK 25 as its minimum version.

## 7. Compact Source Files in Java 25+

Java 25 allows writing a small program without wrapping methods and fields in an explicit class declaration. Such a file is called a **compact source file**.

Example Hello.java file:

~~~java
String greeting = "Hello from Java 25";

void main() {
    IO.println(greeting);
}
~~~

Run directly:

~~~bash
java Hello.java
~~~

Output:

~~~text
Hello from Java 25
~~~

The compiler implicitly declares a top-level class for the members written directly in the file. This implicit class belongs to the unnamed package, is final, has a default no-arg constructor, and cannot be referenced by class name in source code. The instance main method can access the fields and methods of that implicit class.

Starting in Java 25, the IO class resides in the java.lang package and provides simple console methods such as IO.print, IO.println, and IO.readln. Because java.lang is imported implicitly, no import statement is needed for IO. Its static methods are still called through the class name IO, such as IO.println(...).

A compact source file is valid Java syntax, not a separate scripting language. As a program grows, you can move the fields and methods into an explicit class and organize packages, modules, and dependencies like a standard Java project.

Version note: instance main methods and compact source files appeared as preview features in JDK 21–24. They became standard features in Java 25 via JEP 512. When reading documentation or running older examples, check the JDK version and the preview status for that exact release.

## 8. Can a Main Class Be Inherited?

Yes. Under Java rules, a candidate main method can be declared directly or inherited from a superclass. Example:

~~~java
class BaseApplication {
    public static void main(String[] args) {
        System.out.println("Started from inherited main");
    }
}

public class ChildApplication extends BaseApplication {
}
~~~

You can run:

~~~bash
javac ChildApplication.java
java ChildApplication
~~~

Output:

~~~text
Started from inherited main
~~~

In this example, ChildApplication inherits the static main method from BaseApplication. As a result, the launcher still finds the entry point when ChildApplication is specified as the target class.

Although valid, you should not rely heavily on inherited main methods in typical applications because it can make the entry point harder for readers to locate. Declaring the entry point directly on the main class is usually clearer.

## 9. Distinguishing Launcher Options from Application Arguments

JVM options must appear before the main class name or execution target. Application arguments appear after that target.

Example:

~~~bash
java -Xms256m -Xmx1g -cp out com.example.Main --mode test
~~~

| Part | Meaning |
|---|---|
| java | Java launcher |
| -Xms256m | Initial JVM heap size |
| -Xmx1g | Maximum JVM heap size |
| -cp out | Application classpath |
| com.example.Main | Main class |
| --mode test | Two application arguments passed into args |

Inside the main method, args[0] is --mode and args[1] is test. The launcher does not interpret --mode; the application must parse and validate those arguments itself.

Do not confuse launcher options with application arguments. For example, placing -Xmx1g after the class name turns it into a program argument rather than a JVM heap configuration option.

## 10. Common Errors When Launching a Main Class

### Could not find or load main class

**Common causes:**

- The class name is misspelled or has incorrect casing.
- The package is missing from the fully qualified name.
- The classpath points to the wrong root directory.
- The .class file has not been compiled or is not on the classpath.
- Running a different JDK than the environment used to compile.

**How to fix:** check the directory structure, package name, class file location, and -cp value. For example, if the class file is out/com/example/Main.class, run com.example.Main with classpath out.

### Main method not found or no main method

**Common causes:**

- The method has the wrong name, return type, or parameter type.
- Using a private main method.
- Using an instance main method while running on a JDK earlier than Java 25.
- Using an instance main method when the main class cannot be instantiated with a no-arg constructor.
- Selecting the wrong class as the launch target.

**How to fix:** verify the method signature and JDK version. If broad compatibility is needed, use public static void main(String[] args).

### Main-Class attribute required

When running java -jar app.jar, this error can occur if the manifest lacks the Main-Class attribute or specifies an invalid class name.

**How to fix:** regenerate the manifest or use the --main-class option when creating the JAR. Verify the spelling, package, and that the class is packaged inside the JAR.

### NoClassDefFoundError or ClassNotFoundException

The main class was found, but a dependent class is missing from the runtime classpath/module path. This is a dependency resolution error, not necessarily a main method error.

**How to fix:** verify that dependencies are packaged, that the classpath includes the right JARs, and that the module declares any required dependencies.

### UnsupportedClassVersionError

The class file was compiled with a newer Java version than the current runtime. For example, compiling with JDK 25 and running with JDK 17 can trigger this error.

**How to fix:** upgrade the runtime to a matching version or compile with --release targeting the desired Java version. Check both java and javac on your shell's PATH.

### Mixing up source files and compiled classes

- java Main runs the compiled class Main.
- java Main.java runs in source-file mode.
- java -jar app.jar runs the main class declared in the manifest.
- java -m module.name/package.Main runs the module's main class.

Do not append .java when you want to run a compiled class, and do not omit .java when you want the launcher to run in source-file mode.

## 11. Pre-Delivery Application Checklist

- [ ] Identify the correct main class and its fully qualified package name.
- [ ] Use an entry point valid for the project's minimum JDK.
- [ ] Ensure every public class is in a file with a matching name.
- [ ] Verify that the classpath or module path contains the main class and its dependencies.
- [ ] If running a JAR, verify that the manifest has the correct Main-Class.
- [ ] Check the ordering of JVM options and application arguments.
- [ ] Test args with zero arguments, multiple arguments, and arguments containing spaces.
- [ ] Verify static initializers and constructors if the program has startup initialization logic.
- [ ] Verify the JDK version in the terminal, IDE, Gradle/Maven, CI, and containers.
- [ ] If using instance main or compact source files, confirm the runtime/compiler is Java 25 or later.
- [ ] Test on the actual deployment environment and verify dependencies.

## 12. Key Takeaways

The main class is the class the launcher selects to begin a run. The main method is the entry point method inside that class. For projects requiring broad compatibility, public static void main(String[] args) remains the most recognizable and widely supported choice. Since Java 25, the launch protocol also supports instance main methods and compact source files, making small programs more concise.

When running a program, always be able to answer three questions: which JDK is the launcher being invoked from, which class/JAR/module/source file is selected, and which main method will be invoked.

## 13. Official References

- [Java Language Specification, Java SE 26 — Chapter 12: Execution](https://docs.oracle.com/javase/specs/jls/se26/html/jls-12.html) — JVM startup process and main method selection/invocation rules.
- [Java - Your Application Launcher (dev.java)](https://dev.java/learn/jvm/tools/core/java/) — java command syntax, class/JAR/module/source-file modes, and passing arguments.
- [Java SE 25 Language Updates — Compact Source Files and Instance main Methods](https://docs.oracle.com/en/java/javase/25/language/java-se-language-updates.pdf) — JEP 512, compact source files, java.lang.IO, and instance main methods.
- [JEP 512: Compact Source Files and Instance Main Methods](https://openjdk.org/jeps/512) — goals and design of the feature standardized in JDK 25.

When an example depends on an instance main method or a compact source file, clearly note JDK 25+ so learners do not confuse it with the traditional entry point rules of older JDKs.
