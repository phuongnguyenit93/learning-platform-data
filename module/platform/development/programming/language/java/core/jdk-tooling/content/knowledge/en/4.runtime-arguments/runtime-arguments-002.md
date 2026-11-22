# Argument Separators When Launching Java

When running a Java program from the command line, arguments pass through multiple processing layers: the terminal or shell splits the command line into tokens, the Java launcher recognizes JVM options and identifies the program to run, and then the tokens following the launch point are passed to the `main` method. Understanding this boundary properly helps avoid confusing JVM arguments with application arguments, especially when arguments contain hyphens, spaces, or special characters.

This lesson uses Java 21 syntax as an example. The fundamental rules are similar across modern Java versions.

## 1. Three Layers to Distinguish

A command line for running Java can be understood in three layers:

1. **Shell / terminal:** handles spaces, quotes, escape characters, and builds the argument list passed to the process.
2. **Java launcher:** reads JVM startup options, classpath/module path, and determines the class, JAR, module, or source file to run.
3. **Java application:** receives application arguments in `String[] args` and decides their meaning on its own.

Example:

~~~bash
java -Xmx512m -Dapp.env=dev -cp out ArgsDemo --mode fast --file "report final.csv"
~~~

In this command:

- `-Xmx512m` is a JVM heap memory option.
- `-Dapp.env=dev` sets a system property named `app.env`.
- `-cp out` configures the classpath for the Java launcher.
- `ArgsDemo` is the main class to run.
- `--mode`, `fast`, `--file`, and `report final.csv` are application arguments passed to `main`.

**The main class name is a critical boundary** in class-launch syntax: launcher options come before the class name; tokens after the class name are passed to the application. When using a JAR, module, or source-file mode, the position of the JAR, module, or source file serves as the corresponding boundary.

## 2. Launch Syntax and Argument Boundaries

Common command forms:

~~~text
java [options] mainclass [args ...]
java [options] -jar jarfile [args ...]
java [options] -m module[/mainclass] [args ...]
java [options] source-file [args ...]
~~~

| Launch method | Boundary where application arguments start |
|---|---|
| `java [options] com.example.Main [args]` | Immediately after the main class name |
| `java [options] -jar app.jar [args]` | Immediately after the JAR file name |
| `java [options] -m app/com.example.Main [args]` | Immediately after the module/main class name |
| `java [options] Main.java [args]` | Immediately after the source file name |

Example with a main class:

~~~bash
java -Dapp.env=dev -cp out com.example.Main --mode fast
~~~

The application receives two elements: `--mode` and `fast`. The system property `app.env` has the value `dev`.

Example with a JAR:

~~~bash
java -Xmx512m -jar app.jar --mode fast
~~~

The application inside the JAR receives `--mode` and `fast`. The heap option `-Xmx512m` is processed before the application starts.

Example with a module:

~~~bash
java --module-path mods -m com.example.app/com.example.Main --mode fast
~~~

`--module-path` and `-m` belong to the launcher. `--mode` and `fast` belong to the application.

## 3. The Java Launcher Has No General `--` End-of-Options Marker

Some command-line programs use `--` as a marker to end the program's own options section. This is a common convention in many CLI parsers, but you should not assume that the Java launcher uses `--` according to that convention.

For the Java launcher, the syntax is described as `java [options] mainclass [args ...]` (and the `-jar`, `-m`, and source-file forms). The transition point from launcher options to application arguments is the launch target: the class name, JAR file, module, or source file. There is no need to insert a special `--` marker before application arguments.

Valid example:

~~~bash
java -cp out ArgsDemo -- --mode fast
~~~

In this case, `--` is **after** the class name `ArgsDemo`, so it is the first argument of the application. If the application itself defines `--` as the marker to stop reading options, the application's parser can apply that rule.

Do not write `java -- -Xmx512m ArgsDemo` expecting `--` to terminate JVM options. `--` is not a general separator defined by the Java launcher for this purpose; place JVM options before the launch target and application arguments after the launch target.

## 4. Spaces, Quotes, and Multi-Word Arguments

Shells typically use whitespace to split tokens. If a value contains spaces, enclose that value in quotes so the shell passes it as a single argument.

~~~bash
java -cp out ArgsDemo --file "report final.csv"
~~~

The application receives:

- `args[0]` is `--file`
- `args[1]` is `report final.csv`

Quotes used for grouping tokens are usually stripped by the shell before invoking Java. Therefore, the application receives the string `report final.csv`, not the two surrounding quotation marks.

Examples of several cases:

| Command line after the launch target | Application arguments |
|---|---|
| `Main alpha beta` | `"alpha"`, `"beta"` |
| `Main "alpha beta"` | `"alpha beta"` |
| `Main ""` | One empty string |
| `Main --file "report final.csv"` | `"--file"`, `"report final.csv"` |
| `Main --config=dev` | One string `--config=dev` |

In Bash or POSIX shells, single quotes and double quotes have different escaping rules. In Windows PowerShell, quote handling and argument passing rules also differ. When you need to pass a path containing spaces, use double quotes around the entire value and test it with a small program before putting it into a complex script.

## 5. Practical Java Example to Inspect Arguments

Create the file `ArgsDemo.java`:

~~~java
public class ArgsDemo {
    public static void main(String[] args) {
        System.out.println("app.env=" + System.getProperty("app.env"));
        System.out.println("args.length=" + args.length);

        for (int i = 0; i < args.length; i++) {
            System.out.println("args[" + i + "]=<" + args[i] + ">");
        }
    }
}
~~~

Compile:

~~~bash
javac -d out ArgsDemo.java
~~~

Run on macOS/Linux, Windows Command Prompt, or PowerShell:

~~~bash
java -Xmx512m -Dapp.env=dev -cp out ArgsDemo --mode fast --file "report final.csv"
~~~

Output:

~~~text
app.env=dev
args.length=4
args[0]=<--mode>
args[1]=<fast>
args[2]=<--file>
args[3]=<report final.csv>
~~~

The output shows that `-Dapp.env=dev` is converted by the launcher into a system property and does not appear in `args`. The tokens after `ArgsDemo` are preserved in order and passed into the `String[]` array.

Try passing `--` to the application:

~~~bash
java -cp out ArgsDemo -- --mode fast
~~~

Output:

~~~text
app.env=null
args.length=3
args[0]=<-->
args[1]=<--mode>
args[2]=<fast>
~~~

The application receives `--` as an ordinary string. Only when application code or an argument-parsing library explicitly assigns meaning to that string does it become an end-of-options marker at the application layer.

## 6. Distinguishing JVM Options and Application Options

The same string can be handled differently depending on its position on the command line.

| String | Before launch target | After launch target |
|---|---|---|
| `-Xmx512m` | JVM heap option | Application argument |
| `-Dapp.env=dev` | Sets a system property | Application argument |
| `--class-path out` | Launcher classpath option | Application argument |
| `--mode=fast` | Not a standard general Java launcher option; may be treated as an invalid option | Application argument |
| `--` | Not a general end-of-options marker of the Java launcher | Application argument |

Example:

~~~bash
# JVM receives -Xmx and -D; the application receives --mode
java -Xmx512m -Dapp.env=prod -cp out ArgsDemo --mode=fast

# Here -Xmx512m is input data for the application
java -cp out ArgsDemo -Xmx512m
~~~

The Java launcher has its own options such as `-Xmx`, `-D`, `-cp`, `--class-path`, `--module-path`, `-jar`, and `-m`. Application option names such as `--mode`, `--file`, and `--help` are usually defined by the application itself. Do not place application options before the main class name expecting the launcher to forward them automatically.

A launcher option that takes a value may use a space or an equals sign depending on the option's syntax. Example:

~~~bash
java --class-path out ArgsDemo
java --class-path=out ArgsDemo
~~~

Both forms set the classpath to `out`. The word `out` in these two commands is the value of the launcher option, not a `main` argument.

## 7. How Do Applications Define Their Own Separators?

Java only passes arguments as a string array; Java does not enforce a universal format for application-level business options. A program can define its own syntax styles:

| Application convention | Example token | How a parser typically interprets it |
|---|---|---|
| Boolean flag | `--verbose` | A flag with no separate value |
| Separated name and value | `--mode fast` | Two consecutive arguments |
| Name and value with equals sign | `--mode=fast` | One argument; the parser splits at `=` |
| Short pair | `-p 8080` | Two arguments |
| End-of-options marker | `-- file.txt` | Meaningful only if the application parser supports this convention |

For example, with `--mode=fast`, Java passes the whole token `--mode=fast`. Splitting it into the name `--mode` and the value `fast` is the responsibility of the parser inside the application.

With `--mode fast`, Java passes two separate elements. The parser must read the next element as the value of `--mode` and check whether that element exists.

If you write your own parser, you should clearly define:

- Whether option names are case-sensitive.
- Whether values can contain `=`.
- Whether an option can appear multiple times.
- Whether boolean flags accept the `--flag=true` form.
- Whether `--` stops option parsing.
- How missing values, duplicate options, or unsupported options report errors.

For large applications, use a well-tested command-line parsing library instead of manually handling every case with string splitting.

## 8. Using Argument Files for Long Command Lines

The Java launcher supports argument files: place options, the class name, and arguments in a text file, then pass the file name prefixed with `@`.

Create `run.args`:

~~~text
-Xmx512m
-Dapp.env=dev
-cp
out
ArgsDemo
--mode
fast
--file
"report final.csv"
~~~

Run:

~~~bash
java @run.args
~~~

The launcher expands the contents of the argument file into an argument list before parsing the command. Inside the file, whitespace or newlines separate tokens; double quotes can group values containing spaces. Argument file rules are defined by the Java launcher, not by shell escaping rules.

Argument files are useful when the classpath is long or a script has many JVM options. Relative paths inside the file are resolved relative to the current working directory. Do not confuse the launcher's `@run.args` argument file with a configuration file read by the application itself.

## 9. The `JDK_JAVA_OPTIONS` Environment Variable

`JDK_JAVA_OPTIONS` lets you prepend launcher options to the option list of the `java` command. Example in Bash:

~~~bash
export JDK_JAVA_OPTIONS="-Xmx512m -Dapp.env=dev"
java -cp out ArgsDemo --mode fast
~~~

In Windows PowerShell:

~~~powershell
$env:JDK_JAVA_OPTIONS = "-Xmx512m -Dapp.env=dev"
java -cp out ArgsDemo --mode fast
~~~

Values in this variable are processed as launcher options prepended before the command-line arguments. They are not automatically added to `String[] args`. The Java launcher also restricts certain kinds of options in this environment variable, such as options that select the main class/JAR or options that cause the launcher to exit immediately.

When a program runs with unexpected settings, check `JDK_JAVA_OPTIONS` along with launch scripts to see whether any JVM options are being injected.

## 10. Common Errors

| Symptom | Cause | Solution |
|---|---|---|
| The application receives a value with spaces as two elements | Forgot to put quotes around the value | Use `"report final.csv"` |
| `-Xmx` appears in `args` | Placed `-Xmx` after the class/JAR/module name | Move the JVM option before the launch target |
| `--mode` causes an option error when running Java | Placed an application-specific option before the main class name | Place it after the class/JAR/module/source file name |
| The application does not receive the expected system property | Used `-D` after the launch target or misspelled the property name | Put `-Dname=value` before the launch target; read with `System.getProperty` |
| Parser does not recognize `--mode=fast` | Parser only supports `--mode fast` or vice versa | Check the syntax defined by the application |
| Quotes appear in the received value | Escaped to pass literal quotes or script handles quoting differently than expected | Print each element of `args` to inspect the actual tokens |
| Behavior differs between terminal and IDE | IDE has separate fields for program arguments and VM options | Check both separate configuration fields in the Run Configuration |
| Options are injected even though they are not on the command line | `JDK_JAVA_OPTIONS` or a wrapper script adds arguments | Check environment variables and launch scripts |

## 11. Checklist When Arguments Are Wrong

When an application receives incorrect arguments, check in order:

1. **Print the entire `args`:** display the element count, index, and content of each element. Do not just print the whole array as a single string, because token boundaries will be hard to spot.
2. **Inspect the executed command:** identify exactly where the class name, JAR, module, or source file is; every token after the launch target belongs to the application.
3. **Check quotes:** verify whether the shell grouped values containing spaces into a single token.
4. **Check VM options:** verify whether `-X`, `-D`, `--class-path`, `--module-path`, and launcher options are placed before the launch target.
5. **Check the application parser:** determine whether the parser expects `--name value`, `--name=value`, or another custom convention.
6. **Check additional argument sources:** inspect the IDE Run Configuration, wrapper scripts, `JDK_JAVA_OPTIONS`, and `@...` argument files.

You can use the help commands to view the launcher syntax for your exact JDK:

~~~bash
java --help
java --help-extra
~~~

## 12. Key Takeaways

- Whitespace separates tokens; quotes keep a value containing spaces in a single token.
- The main class name, JAR, module, or source file defines the boundary between launcher options and application arguments.
- `-Xmx`, `-D`, `-cp`, and `--module-path` must be placed in the launcher options section.
- `--mode`, `--file`, and business options are usually placed after the launch target.
- The Java launcher does not define `--` as a general end-of-options marker; if `--` appears after the launch target, the application receives it as an argument.
- `String[] args` contains each token forwarded by the shell and launcher; interpreting those tokens is the application's responsibility.
- When launch commands get complex, use an argument file and print `args` to verify the actual data.

Reference: [The java Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html), especially the Synopsis, Description, Standard Options for Java, and Java Command-Line Argument Files sections.
