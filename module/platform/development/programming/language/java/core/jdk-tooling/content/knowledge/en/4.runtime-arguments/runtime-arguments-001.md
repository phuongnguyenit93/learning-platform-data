# Application Arguments in Java

When launching a Java program, input data can be passed directly on the command line. These values are called **application arguments**. The Java launcher passes them to the program's entry point method, typically **main(String[] args)**.

It is important to distinguish application arguments from JVM options and Java launcher options. All three can appear in the same command, but they are processed at different stages. Understanding this boundary helps configure applications correctly from the terminal, IDE, build tools, scripts, and containers.

## 1. What are application arguments?

Application arguments are values passed by the caller to a program to change its input data or behavior for that run. For example:

~~~bash
java -cp out com.example.ReportApp --format csv --output report.csv
~~~

In the command above:

- **java** is the launcher that starts the Java application.
- **-cp out** is a launcher option specifying the classpath.
- **com.example.ReportApp** is the name of the class containing the main method to run.
- **--format csv --output report.csv** are the application arguments passed to main.

The application itself decides the meaning of the arguments. Java does not automatically know that --format is a format option or --output is a file name. The program must read, parse, validate, and apply them.

Application arguments are commonly used to:

- Select a running mode such as dev, test, or production.
- Specify input and output files.
- Choose a port, host, locale, or data format.
- Enable or disable a program behavior.
- Pass a task name, subcommand, or value to process.

## 2. The main method and the args array

The traditional entry point of a Java program is:

~~~java
public static void main(String[] args) {
    // handle arguments here
}
~~~

When the launcher invokes this method, the application arguments are placed in a String array named args.

Key characteristics to remember:

- Each element of args is a String.
- The order of elements is preserved exactly as the launcher received the arguments.
- args[0] is the first application argument, args[1] is the second, and so on.
- args.length indicates the number of arguments.
- If no arguments are passed, the launcher provides an empty array of length 0; the program does not need to assume args is null.
- The class name, JAR name, JVM options, and classpath options are not included in args.

Java also allows declaring main with varargs syntax:

~~~java
public static void main(String... args) {
    System.out.println(args.length);
}
~~~

In the context of a method declaration, String... is the varargs form of String[]. To the Java launcher, this is still the String array parameter of the main method.

### Printing received arguments

A simple example:

~~~java
public class ArgsPrinter {
    public static void main(String[] args) {
        System.out.println("count=" + args.length);

        for (int i = 0; i < args.length; i++) {
            System.out.printf("args[%d]=%s%n", i, args[i]);
        }
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 ArgsPrinter.java
java ArgsPrinter alpha beta
~~~

Output:

~~~text
count=2
args[0]=alpha
args[1]=beta
~~~

This example shows that the launcher passes the two values alpha and beta as two separate elements. If there are no arguments after the class name, the program prints count=0.

## 3. Distinguishing JVM options, launcher options, and application arguments

A Java launch command can contain three groups of information:

| Group | Example | Handled by | Typical position |
|---|---|---|---|
| JVM options | -Xmx512m, -Dapp.env=prod | JVM | Before the class name/JAR/module |
| Launcher options | -cp out, --module-path mods, -jar app.jar | Java launcher | Before the entry point, following launcher syntax |
| Application arguments | --port 8080, input.csv | Application's main method | After the class name, JAR, or module entry point |

Example:

~~~bash
java -Xmx512m -Dapp.env=production -cp out com.example.Server --port 8080
~~~

You can read the command part by part:

1. -Xmx512m configures the JVM maximum heap size.
2. -Dapp.env=production sets a system property named app.env.
3. -cp out tells the launcher to look for classes in the out directory.
4. com.example.Server is the class to be launched.
5. --port 8080 is passed to main as two strings.

In the Java launcher, options must be placed in the correct position according to the command syntax. Once the launcher has identified the main class, the remaining arguments that follow are passed to the application. Therefore, placing --port before the class name usually does not pass it as an application argument; the launcher may interpret it as one of its own options and report an error.

### Running from a JAR

If a JAR has a manifest specifying Main-Class, you can run:

~~~bash
java -jar app.jar --port 8080 --mode batch
~~~

The values following the JAR name are passed to the main method of the main class. JVM options such as -Xmx or -Dapp.env should be placed before -jar:

~~~bash
java -Xmx512m -Dapp.env=production -jar app.jar --port 8080
~~~

When using -jar, the launcher obtains the application classpath from the JAR/manifest configuration; -cp should not be treated as the usual way to add to the classpath for this launch form.

### Running a module

For an application using the Java Platform Module System, you can run a module:

~~~bash
java --module-path mods -m com.example.app/com.example.Main --port 8080
~~~

The --module-path and -m parts are launcher options. --port 8080 following the module entry point are application arguments.

## 4. Whitespace, quotes, and how the shell passes arguments

Java receives the arguments after the operating system shell has parsed the command line. Quotes generally group multiple words into a single argument; the quotes themselves are not included in the String in args.

Example:

~~~bash
java ArgsPrinter one "two words" three
~~~

The application receives three elements:

~~~text
args[0]=one
args[1]=two words
args[2]=three
~~~

Some cases to keep in mind:

- "two words" creates one argument containing a space.
- "" creates an empty string argument.
- No arguments after the class name creates an empty args array.
- Escape characters, single quotes, and double quotes are handled by the shell according to the rules of each environment.

Quoting syntax differs between Bash/Zsh, PowerShell, and Windows Command Prompt. When writing scripts for multiple operating systems, test how the shell actually produces the arguments rather than assuming all shells handle quotes the same way.

An application can print each element and its length to diagnose quoting issues. Do not split a command string by whitespace and treat the result as equivalent to the args array, because doing so loses the boundaries of arguments containing spaces or escape characters.

## 5. Parsing and validating arguments

Java provides the String array; the application is responsible for defining the syntax. A program can accept arguments positionally or by name.

### Positional arguments

Example:

~~~bash
java CopyFile source.txt backup.txt
~~~

The application's convention might be:

- args[0]: source file.
- args[1]: destination file.
- Require args.length to be 2.

This approach is simple for commands with few arguments, but as the number of options grows, users must remember the exact order.

### Named arguments

Example:

~~~bash
java Server --host localhost --port 8080
~~~

The application can accept name/value pairs regardless of order, provided the parser is written to support it. The named form is easier to read when there are many configuration options, but you must handle missing values, repeated options, or invalid names.

### Safe parsing workflow

A basic parser should perform the following steps:

1. Define valid syntax and default values.
2. Read each argument in order.
3. Distinguish between option, value, and positional argument.
4. Check that a value exists when an option requires one.
5. Convert types, such as String to int or Path.
6. Validate value ranges and relationships between options.
7. Report clear errors and show usage instructions when input is invalid.
8. Execute the task only after the entire configuration is valid.

Do not access args[0] before checking args.length. If no arguments are present, accessing index 0 throws an ArrayIndexOutOfBoundsException.

Do not cast or parse data directly from String without handling errors. For example, Integer.parseInt can throw NumberFormatException; the application should catch the error and report which argument is invalid. For paths, you can use Path.of and then check file existence, read permission, or write permission as needed.

## 6. Complete example: parsing host, port, and tag

The following example uses Java 17 and accepts three named options:

- --host HOST: host name, defaults to localhost.
- --port PORT: port from 1 to 65535, defaults to 8080.
- --tag TAG: run tag, defaults to local.
- -Dapp.env=VALUE: JVM system property, defaults to local.

Create the file src/AppArgsDemo.java:

~~~java
public final class AppArgsDemo {
    private AppArgsDemo() {
    }

    public static void main(String[] args) {
        try {
            Options options = Options.parse(args);
            String environment = System.getProperty("app.env", "local");

            System.out.printf("environment=%s%n", environment);
            System.out.printf("host=%s%n", options.host());
            System.out.printf("port=%d%n", options.port());
            System.out.printf("tag=%s%n", options.tag());
        } catch (IllegalArgumentException ex) {
            System.err.println("Error: " + ex.getMessage());
            System.err.println(
                "Usage: java -Dapp.env=production -cp out AppArgsDemo "
                + "[--host HOST] [--port PORT] [--tag TAG]"
            );
            System.exit(2);
        }
    }

    private record Options(String host, int port, String tag) {
        static Options parse(String[] args) {
            String host = "localhost";
            int port = 8080;
            String tag = "local";

            for (int i = 0; i < args.length; i++) {
                switch (args[i]) {
                    case "--host" -> {
                        host = requireValue(args, i);
                        i++;
                    }
                    case "--port" -> {
                        String value = requireValue(args, i);
                        i++;

                        try {
                            port = Integer.parseInt(value);
                        } catch (NumberFormatException ex) {
                            throw new IllegalArgumentException(
                                "--port must be an integer: " + value
                            );
                        }

                        if (port < 1 || port > 65535) {
                            throw new IllegalArgumentException(
                                "--port must be between 1 and 65535"
                            );
                        }
                    }
                    case "--tag" -> {
                        tag = requireValue(args, i);
                        i++;
                    }
                    default -> throw new IllegalArgumentException(
                        "Unknown argument: " + args[i]
                    );
                }
            }

            return new Options(host, port, tag);
        }
    }

    private static String requireValue(String[] args, int optionIndex) {
        int valueIndex = optionIndex + 1;

        if (valueIndex >= args.length || args[valueIndex].startsWith("--")) {
            throw new IllegalArgumentException(
                "Missing value for " + args[optionIndex]
            );
        }

        return args[valueIndex];
    }
}
~~~

From the project directory, create the output directory, compile, and run:

~~~bash
mkdir out
javac --release 17 -d out src/AppArgsDemo.java
java -Dapp.env=production -cp out AppArgsDemo --host api.internal --port 9090 --tag "nightly build"
~~~

Output:

~~~text
environment=production
host=api.internal
port=9090
tag=nightly build
~~~

Points to observe:

- The system property app.env is read with System.getProperty; it does not appear in args.
- --host, --port, and --tag are application data and appear in args.
- The string "nightly build" is passed by the shell as a single argument containing a space.
- The Options record holds the parsed configuration with explicit types.
- The parser validates missing values, integers, and port bounds before the program uses the configuration.

Try passing an invalid port value:

~~~bash
java -cp out AppArgsDemo --port abc
~~~

The program prints an error message to stderr, shows usage instructions, and exits with exit code 2. This is a convention of the example application; Java does not mandate exit code 2 for all argument errors.

This parser intentionally supports only the listed options and does not support positional arguments, combined options, equals signs such as --port=9090, or repeated options. For complex CLIs, use a dedicated library instead of building a large custom parser.

## 7. Application arguments, system properties, and environment variables

All three mechanisms can pass configuration to an application, but they differ in source and how they are accessed.

| Mechanism | How it is passed | How it is read in Java | Example |
|---|---|---|---|
| Application argument | After the class/JAR/module entry point | args | --port 8080 |
| System property | JVM -D option before the entry point | System.getProperty | -Dapp.env=prod |
| Environment variable | Process environment | System.getenv | APP_ENV=prod |

### Application arguments

Suitable for input data specific to a single run: file names, tasks, modes, query parameters, or CLI options. They are typically visible in the program invocation command.

### System properties

A system property is a name/value pair attached to the JVM. It can be set from the command line using -Dname=value:

~~~bash
java -Dapp.region=ap-southeast-1 -cp out AppArgsDemo
~~~

Reading it in Java:

~~~java
String region = System.getProperty("app.region", "local");
~~~

System properties can also be set or modified within the process using System.setProperty. Do not use system properties as a secret store.

### Environment variables

Environment variables are configured in the process environment before the program runs. Example on a POSIX-style shell:

~~~bash
APP_ENV=production java -cp out AppArgsDemo
~~~

Reading it in Java:

~~~java
String environment = System.getenv("APP_ENV");
~~~

On Windows, the way environment variables are set in the terminal differs from Bash. The Java application still reads them via System.getenv.

### Which mechanism should you choose?

- Use application arguments for commands and data that the caller wants to specify explicitly on each run.
- Use system properties for JVM configuration or application configuration that needs to be passed via the -D convention.
- Use environment variables for deployment configuration provided by the environment, container, or runtime platform.
- Use configuration files or a secret manager when configuration has a large structure, requires lifecycle management, or contains sensitive information.

If the same value is provided from multiple sources, the application must define a clear precedence order—for example, CLI overrides environment variables and default values. Java does not automatically enforce a uniform configuration precedence across all applications.

## 8. Configuration in IDEs, Maven, and Gradle

When running from an IDE, there are usually two separate fields:

- **Program arguments:** arguments passed to main, i.e., args.
- **VM options / VM arguments:** JVM options such as -Xmx or -Dapp.env=production.

Do not enter --port 8080 into VM options if it is an argument the program expects to read from args. Conversely, -Dapp.env=production must go in VM options when configuring the application to run directly.

In Maven or Gradle, the build tool may spawn a separate Java process to run the application or tests. Therefore, you must identify whether arguments are being passed to:

- The JVM running the build tool itself.
- The compiler or a plugin.
- The child JVM running tests.
- The Java application launched by the run task.

A -D flag passed to the Maven/Gradle process does not necessarily become an application argument for the application. Use the task/plugin configuration to pass program arguments to the right place. The exact property name depends on the plugin and build tool version.

## 9. Passing arguments to an application in Docker

With a Dockerfile using exec form:

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
CMD ["--port", "8080"]
~~~

CMD provides the default arguments appended to ENTRYPOINT. When running:

~~~bash
docker run --rm my-java-app
~~~

The application receives --port and 8080.

You can override the default arguments:

~~~bash
docker run --rm my-java-app --port 9090
~~~

In this case, the application receives --port 9090. This declaration keeps the JVM as the main process and passes application arguments via the command line.

If you use shell form or an entrypoint script, the script must forward arguments properly. In a shell script, the construct exec java ... "$@" replaces the script process with the JVM and preserves the boundaries of each argument. Do not concatenate all arguments into a single string and split them again by whitespace.

## 10. Security and common pitfalls

### Do not pass secrets via the command line

Command-line arguments can appear in process listings, logs, shell history, monitoring systems, or diagnostic output. Avoid passing passwords, access tokens, private keys, or secrets directly via args or system properties. Use a secret manager, protected mounted files, or an appropriate credential-provisioning mechanism.

### Do not assume data types

All application arguments are Strings. If you need an integer, boolean, enum, date/time, or path, parse and validate it explicitly. Handle NumberFormatException and format errors in a way that tells the user which argument is invalid.

### Do not assume option order

If the parser supports named options, clearly define whether reordering is allowed. Do not access args[0] and args[1] by position if the actual syntax allows users to pass options flexibly.

### Distinguish missing arguments from empty strings

args.length == 0 means no arguments were passed. An element with an empty string value can be passed using empty quotes according to shell syntax. These two cases are not the same.

### Handling repeated options

For example, --port 8080 --port 9090 can either be rejected or follow a "last value wins" rule. This is a parser design decision; document it clearly in the usage documentation.

### Error reporting and exit codes

When input is invalid, print a concise message to stderr, provide the usage syntax, and return a non-zero exit code. Avoid printing only a long stack trace for common input errors. Exit codes help shell scripts and CI systems detect command failure.

## 11. Application arguments design checklist

- Clearly identify which arguments are JVM options, launcher options, and application arguments.
- Document the CLI syntax and example invocations.
- Specify required arguments, defaults, data types, and value ranges.
- Choose positional or named arguments based on the number of options.
- Check args.length before accessing indices.
- Parse and validate all input before starting the task.
- Handle whitespace and quoting properly for the target shell.
- Separate program arguments from VM options in IDEs and build tools.
- Define precedence order among CLI, system properties, environment variables, and configuration files.
- Do not pass secrets via the command line or logs.
- Print usage on error and return a non-zero exit code.
- Test cases with no arguments, missing values, invalid values, strings with spaces, and unknown options.

## 12. Key terminology

| Term | Meaning |
|---|---|
| Application argument | A value passed to the program at launch |
| args | The String array containing application arguments in main |
| JVM option | An option configuring the virtual machine, e.g., -Xmx |
| Launcher option | An option for the Java launcher, e.g., -cp or -jar |
| System property | A JVM name/value pair, typically set with -D |
| Environment variable | An environment variable inherited by the process |
| Positional argument | An argument interpreted based on its position |
| Named option | An option with a name, such as --port |
| Parser | A component that parses argument strings into a meaningful configuration |
| Validation | Checking that input is valid before using it |
| Exit code | The status code a process returns to the operating system |

Key takeaway: **all application arguments in main are Strings**. The Java launcher simply forwards them to the entry point; the application itself defines the syntax, performs type conversion, validates values, and decides how to use them. Clearly distinguishing args from JVM options and launcher options helps keep launch commands consistent across terminals, IDEs, build tools, and containers.