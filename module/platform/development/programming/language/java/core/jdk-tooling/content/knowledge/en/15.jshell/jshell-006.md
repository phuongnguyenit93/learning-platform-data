# Imports in JShell

**JShell** is the Java Shell, a REPL (Read–Eval–Print Loop) environment included with the JDK. You can enter expressions, statements, variables, methods, classes, and import declarations directly and see the results immediately. In JShell, an **import declaration is a snippet**: once accepted, the imported type name or static member can be used in subsequent snippets within the same session.

Example:

~~~text
jshell> import java.time.LocalDate;

jshell> LocalDate today = LocalDate.of(2026, 11, 10);
today ==> 2026-11-10

jshell> today.plusDays(7)
$... ==> 2026-11-17
~~~

After importing, you can use the short name LocalDate instead of writing the full java.time.LocalDate in every expression. Temporary result variable names such as $5 vary by session.

Imports in JShell follow Java's import rules. The key difference is that JShell also has a startup script with commonly used imports, and imports are persisted within the interactive state of the session.

## 1. What Is an Import Declaration Used For?

A Java type has a fully qualified name consisting of its package and type name. For example:

~~~java
java.time.LocalDate
java.util.ArrayList
java.nio.file.Path
~~~

Without an import, you may have to write the full type name:

~~~java
java.time.LocalDate today =
        java.time.LocalDate.now();
~~~

When you import a type, you can use its simple name:

~~~java
import java.time.LocalDate;

LocalDate today = LocalDate.now();
~~~

An import helps the compiler resolve simple names in source code. It does not:

- Create objects.
- Initialize classes.
- Run static initializers.
- Add JARs or directories to the classpath.
- Load a library that is not yet in the compilation environment.
- Grant access to a package that a module does not export.

An import only lets you write shorter names and identifies which type or static member is being referenced. The type must still be available on the classpath/module path and must be accessible according to Java rules.

In JShell, an import entered at the prompt remains in effect for subsequent snippets in the same session. You do not have to repeat the import on every line.

## 2. Default Imports When Starting JShell

When running JShell with the default configuration, the tool loads a startup script named **DEFAULT**. This script adds commonly used imports so you can experiment quickly.

In JDK 17, common default imports include:

~~~java
import java.io.*;
import java.math.*;
import java.net.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.function.*;
import java.util.prefs.*;
import java.util.regex.*;
import java.util.stream.*;
~~~

Therefore, in a default session you can usually use names like these right away:

~~~java
List.of("Java", "JShell");
Map.of("name", "Ada");
Path.of("notes.txt");
Pattern.compile("[A-Z]+");
Predicate.isEqual("ready");
~~~

There is no need to re-enter java.util.* or java.nio.file.* if the current startup script has already loaded them.

### java.lang Is a Special Case

Java automatically imports public types in the **java.lang** package according to the language specification. This does not depend specifically on JShell.

For example, you can directly use:

~~~java
String message = "Hello";
System.out.println(message);
Math.max(10, 20);
Integer.parseInt("42");
~~~

java.lang does not need to be imported explicitly. You can write import java.lang.* but it is usually unnecessary.

It is important to distinguish between the two mechanisms:

- **java.lang:** automatically imported by Java according to the language rules.
- **Packages in DEFAULT:** loaded by JShell via the startup script. They can change if you use a different startup script or disable startup.

### Viewing Loaded Imports

In JShell, enter:

~~~text
jshell> /imports
~~~

This command displays the active imports, including imports from the startup script and scripts loaded at startup.

You can view the startup snippets with:

~~~text
jshell> /list -start
~~~

In the output, startup snippets usually have IDs starting with the letter s, such as s1, s2. The exact list depends on the JDK and the startup script.

Do not assume every commonly used package is already present. When a type name is not recognized, check /imports first and then import it explicitly if needed.

## 3. Importing a Specific Type (Single-Type Import)

Syntax:

~~~java
import package.name.TypeName;
~~~

Example:

~~~java
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
~~~

Then you can use the simple names:

~~~java
LocalDate date = LocalDate.of(2026, 11, 10);
LocalTime time = LocalTime.of(9, 30);

DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("dd/MM/uuuu");

formatter.format(date);
~~~

Single-type import is suitable when:

- You only need one or a few types from a package.
- You want to clearly show the dependencies of the code.
- The package has many types that could easily collide in name.
- You want readers to know the exact type being used.

You can import a nested type if that type is accessible:

~~~java
import java.util.Map.Entry;
~~~

Then use Entry as a simple type name within the session scope.

Importing one type does not import the entire package containing that type. For example, import java.time.LocalDate does not automatically import LocalTime or DateTimeFormatter.

## 4. Importing by Package (Type-Import-On-Demand)

Syntax:

~~~java
import package.name.*;
~~~

Example:

~~~java
import java.time.*;
import java.nio.file.*;
~~~

Then you can use the public types directly in that package:

~~~java
LocalDate today = LocalDate.now();
LocalTime now = LocalTime.now();
Path file = Path.of("notes.txt");
~~~

The * symbol is called an on-demand import. It does not mean loading all classes or the entire library into memory; the compiler only uses this declaration to resolve type names when needed.

### Wildcard Imports Do Not Include Subpackages

~~~java
import java.util.*;
~~~

This import does not automatically import types in:

- java.util.concurrent
- java.util.function
- java.util.regex
- java.util.stream

Each subpackage is a separate package. If the startup script has not loaded them, you need to import them separately:

~~~java
import java.util.concurrent.*;
import java.util.function.*;
import java.util.stream.*;
~~~

There is no recursive wildcard syntax to import all subpackages of a package.

### When to Use Wildcards?

Wildcards can be convenient in JShell when quickly experimenting with many types in the same package. For code saved to files or examples that need to show dependencies clearly, single-type imports are usually easier to read and create fewer ambiguous names.

Wildcards do not increase the number of classes initialized. They only expand the set of type names that can be referenced by their simple names.

## 5. Static Imports

A static import allows referencing a static field, static method, or static nested type without writing the class name in front of it.

Syntax to import a single static member:

~~~java
import static package.TypeName.memberName;
~~~

Syntax to import matching static members in a type:

~~~java
import static package.TypeName.*;
~~~

Example importing the constant PI and the sqrt method:

~~~java
import static java.lang.Math.PI;
import static java.lang.Math.sqrt;

PI;
sqrt(81);
~~~

The results are the value of PI and 9.0, respectively.

You can import all static members:

~~~java
import static java.lang.Math.*;
~~~

Then call:

~~~java
max(12, 30);
abs(-5);
pow(2, 5);
~~~

Static imports apply only to static members. They do not import instance methods or instance fields.

### Static Imports with Collections

Example:

~~~java
import static java.util.Collections.emptyList;
import static java.util.Collections.singletonList;

emptyList();
singletonList("ready");
~~~

You can call emptyList() and singletonList() directly without writing Collections.emptyList().

### Static Imports Do Not Create Objects

~~~java
import static java.lang.Math.PI;
~~~

This line does not create a Math object, nor does it invoke a method. It only allows using the name PI without the Math qualifier.

If a static method returns an object, the object is only created when you actually call that method:

~~~java
import static java.util.List.of;

of("A", "B", "C");
~~~

In this example, List.of is executed when the snippet calls of(...).

### Differences Between Static Imports and Regular Imports

| Declaration | Imported Element | Usage |
|---|---|---|
| import java.time.LocalDate; | Type LocalDate | LocalDate.now() |
| import java.time.*; | Types in java.time | LocalDate.now() |
| import static java.lang.Math.PI; | Static field PI | PI |
| import static java.lang.Math.sqrt; | Static method sqrt | sqrt(81) |
| import static java.lang.Math.*; | Accessible static members | max(1, 2) |

Regular imports do not make static members directly callable. To omit the class name from a static member, a static import is required.

## 6. Scope and Lifetime of Imports

In traditional Java source files, import declarations sit at the top of a compilation unit and apply to the entire file. JShell does not require creating a separate source file for each snippet.

When you enter:

~~~java
import java.time.LocalDate;
~~~

JShell records the import in the session state. Subsequent snippets can use LocalDate:

~~~java
LocalDate start = LocalDate.of(2026, 11, 10);
LocalDate end = start.plusDays(5);
end;
~~~

You do not need to re-import LocalDate before every expression.

Imports are not automatically saved as a global configuration for every time JShell is opened. When a session is reset, user-entered snippets may be cleared; the startup script will be re-run according to the current configuration.

### Startup Imports vs. Directly Entered Imports

There are two common sources:

- **Startup imports:** loaded when JShell starts or re-runs the startup script.
- **Session imports:** entered directly at the prompt or loaded from a script using /open.

The /imports command shows the active set of imports, helping you see where a type name comes from at the import level.

## 7. JShell Commands Related to Imports

The following commands are useful when managing imports:

| Command | Effect |
|---|---|
| /imports | Displays currently active imports |
| /list -start | Displays snippets loaded from the startup script |
| /list -all | Displays snippets, including startup, failed, overwritten, or dropped ones |
| /open file | Loads snippets and commands from a script into the current session |
| /save file | Saves current snippets according to options |
| /save -start file | Saves the contents of the current startup script |
| /set start | Views or changes the startup script for the next reset |
| /reset | Clears snippet state and re-runs the startup script |
| /reload | Restarts the environment and replays valid history |
| /env | Views or changes the classpath/module path; changing the environment resets and replays the session |

Commands starting with / are JShell control commands, not Java import declarations. For example, import java.time.*; is a Java snippet, whereas /imports is a tool command.

### Viewing Active Imports

~~~text
jshell> /imports
~~~

The output displays the import lines. The list varies depending on the startup script, imports you have entered, and scripts loaded.

### Viewing Startup Imports

~~~text
jshell> /list -start
~~~

This command is useful when you need to distinguish default imports from manually entered imports. Startup snippets usually have their own IDs starting with s.

### Resetting the Session

~~~text
jshell> /reset
~~~

/reset removes snippets in the session, then runs the startup scripts. Imports entered manually after startup are no longer in the new state, unless they are in the startup script.

### Reloading the Session

~~~text
jshell> /reload
~~~

/reload restarts the environment and replays valid history. Therefore, imports in the history can be reloaded along with related snippets.

### Changing the Environment

~~~text
jshell> /env
~~~

Without options, /env displays the current environment configuration. When adding a classpath or module path with /env, JShell resets the execution state, runs startup scripts, and replays valid history according to the tool's rules.

## 8. Creating a Startup Script with Custom Imports

If you frequently use the same group of packages, you can create a startup script to automatically load imports every time you open JShell.

Example file **my-imports.jsh**:

~~~java
import java.time.*;
import java.time.format.*;
import java.nio.file.*;
import static java.time.temporal.ChronoUnit.DAYS;
import static java.lang.Math.*;
~~~

This is a script consisting of import declarations. Each snippet or JShell command should be on its own line for easy management.

### Loading a Script at Startup

~~~bash
jshell --startup my-imports.jsh
~~~

The --startup option uses the specified startup script instead of the default configuration. If you want to keep default imports and load your personal script as well, specify both:

~~~bash
jshell --startup DEFAULT --startup my-imports.jsh
~~~

Multiple startup scripts can be specified; they are executed in the order declared.

### Using /open in a Running Session

~~~text
jshell> /open my-imports.jsh
~~~

/open loads the snippets in the file into the current session. Imports are loaded from the script and can be used for subsequent snippets.

Key differences:

- --startup: loads the script when the session starts and when startup scripts are re-run.
- /open: loads the script immediately in the current session.
- /set start: changes the list of startup scripts used on the next reset.

### Saving a Startup Script

You can save the current startup configuration:

~~~text
jshell> /save -start my-startup.jsh
~~~

You can use /set start to configure scripts and /set start -retain to persist the startup configuration for future JShell launches.

Example:

~~~text
jshell> /set start DEFAULT my-imports.jsh
jshell> /set start -retain
~~~

The -retain option keeps the startup configuration for future sessions. Check again with /set start and /imports to confirm that the desired script is loaded.

## 9. Disabling Default Imports and Controlling the Environment

Sometimes you need a clean session to verify whether an import is actually necessary.

Start without a startup script:

~~~bash
jshell --no-startup
~~~

In this mode, imports provided by the DEFAULT startup script are not loaded. However, java.lang is still automatically imported according to Java rules.

You can enter imports explicitly:

~~~java
import java.util.List;
import java.time.LocalDate;

List<String> names = List.of("Ada", "Linus");
LocalDate date = LocalDate.of(2026, 11, 10);
~~~

You cannot use --no-startup and --startup at the same time. If you need a custom startup configuration, use --startup with the desired file.

This approach is useful when:

- Writing tutorials that need to show every import explicitly.
- Testing whether a snippet depends on implicit imports.
- Finding out which imports come from DEFAULT.
- Creating an experimentation environment close to regular Java source files.

## 10. Importing from External Libraries

Imports do not automatically find or download third-party libraries. Before importing a class, the library must be present in JShell's environment.

Suppose you have compiled a library into build/classes or have a JAR at lib/helper.jar.

### Setting the Classpath at Startup

Linux/macOS:

~~~bash
jshell --class-path "build/classes:lib/helper.jar"
~~~

Windows:

~~~powershell
jshell --class-path "build/classes;lib/helper.jar"
~~~

Then you can import public types in the library's package:

~~~java
import com.example.helper.TextFormatter;

TextFormatter.uppercase("hello");
~~~

Classes in the default package (unnamed package) cannot be accessed from JShell. Place library code in a named package.

### Adding a Classpath During a Session

You can use:

~~~text
jshell> /env --class-path build/classes
~~~

JShell will report the environment option change and restore the session by resetting and replaying valid history.

Note: /env can cause the session to restart. If an earlier snippet depended on external state or had side effects, replaying may produce different results. Save important work before changing the environment.

### Module Path

If the library is packaged as a named module, use the module path:

~~~bash
jshell --module-path mods --add-modules com.example.api
~~~

Then import public types from a package exported by the module:

~~~java
import com.example.api.GreetingService;
~~~

Requirements:

- The module is present on the module path.
- The module is resolved, for example via --add-modules.
- The package containing the type is exported to the using module.
- The type and member have appropriate access permissions.

The classpath and module path solve two different kinds of dependencies. Do not put a JAR on the classpath and expect an import to bypass the module boundary of a named module.

## 11. Handling Name Collisions and Ambiguous Imports

Some packages may contain types with the same name. For example, Date exists in both java.util and java.sql.

If you import both packages with wildcards:

~~~java
import java.util.*;
import java.sql.*;
~~~

then a simple reference:

~~~java
Date today;
~~~

can be ambiguous because both packages have a Date type.

The solution is to use the fully qualified name:

~~~java
java.util.Date utilDate = new java.util.Date();
java.sql.Date sqlDate = java.sql.Date.valueOf("2026-11-10");
~~~

Or import only one specific type and use the fully qualified name for the other.

### Two Single-Type Imports with the Same Name

If you enter two single-type imports with the same simple name pointing to two different types, Java reports an import conflict error:

~~~java
import java.util.Date;
import java.sql.Date;
~~~

In this case, keep one import and use the fully qualified name for the other type.

### Ambiguous Static Imports

Two classes can have static members with the same name. If you import multiple members with the same name and the compiler cannot determine the matching member, the call can be ambiguous.

General example:

~~~java
import static java.lang.Math.max;
~~~

If another static import also brings a max method with a competing signature into the same scope, call the method via the class name to disambiguate:

~~~java
Math.max(10, 20);
~~~

### How to Avoid Conflicts

- Use single-type imports for important types.
- Limit wildcards when packages have many easily colliding names.
- Use fully qualified names at the point of conflict.
- Use selective static imports instead of importing all static members.
- Check /imports when a session has multiple startup scripts or sequentially loaded scripts.

JShell applies Java's name resolution rules; the REPL does not automatically pick one type based on import order to hide ambiguity.

## 12. What Wildcards Do Not Do

There are several common misconceptions:

**Wildcards do not import subpackages**

java.util.* does not include java.util.stream.*.

**Wildcards do not import static members**

import java.lang.Math.* does not allow calling sqrt(9) directly. To do that, you must use import static java.lang.Math.sqrt or import static java.lang.Math.*.

**Imports do not add dependencies**

import com.example.Tool does not make the JAR containing Tool automatically appear on the classpath.

**Imports do not grant module access**

If a package is not exported or a module is not resolved, the import can still fail.

**Imports do not create objects**

import java.time.LocalDate does not call LocalDate.now() and does not create the current date.

**Imports are not aliases**

Java does not have type-renaming import syntax like some other languages. If two types share the same name, use fully qualified names or reorganize the code.

## 13. Practical Example: Importing Dates and Static Members

This example uses Java 17+ and runs directly in JShell.

Start:

~~~bash
jshell
~~~

Enter a single-type import:

~~~java
import java.time.LocalDate;
~~~

Enter a static import:

~~~java
import static java.time.temporal.ChronoUnit.DAYS;
~~~

Create two dates:

~~~java
LocalDate start = LocalDate.of(2026, 11, 10);
LocalDate due = start.plusDays(14);
~~~

Calculate the number of days:

~~~java
DAYS.between(start, due);
~~~

Result:

~~~text
14
~~~

JShell may display the result as a temporary variable, such as $5 ==> 14. The temporary variable ID varies by session; the number of days remains 14.

In this example:

- LocalDate is explicitly imported from java.time.
- DAYS is explicitly imported using a static import.
- between is a method of the ChronoUnit.DAYS value.
- The snippets share the previously declared imports.

You can inspect the import list:

~~~text
jshell> /imports
~~~

You will see the LocalDate import and the DAYS static import alongside the active startup imports.

## 14. Practical Example: Wildcard Imports and Streams

In default JShell, java.util.* and java.util.stream.* are usually already loaded by DEFAULT. You can verify with /imports.

Example:

~~~java
List<String> languages =
        List.of("Java", "Kotlin", "Scala", "JavaScript");

List<String> result = languages.stream()
        .filter(name -> name.startsWith("J"))
        .map(String::toUpperCase)
        .toList();

result;
~~~

Result:

~~~text
[JAVA, JAVASCRIPT]
~~~

To see explicit imports, you can run a session without startup:

~~~bash
jshell --no-startup
~~~

Then enter:

~~~java
import java.util.List;
import java.util.stream.Collectors;

List<String> result = List.of("Java", "Kotlin", "Scala")
        .stream()
        .filter(name -> name.length() > 4)
        .collect(Collectors.toList());

result;
~~~

Result:

~~~text
[Kotlin, Scala]
~~~

This is a good way to distinguish imports that come from the Java language, imports provided by the JShell startup script, and imports you declare yourself.

## 15. Practical Example: Static Imports and Numeric Operations

In a new or current session, enter:

~~~java
import static java.lang.Math.PI;
import static java.lang.Math.sqrt;
import static java.lang.Math.pow;
~~~

Execute:

~~~java
double radius = 3.0;
double area = PI * pow(radius, 2);
double diagonal = sqrt(3 * 3 + 4 * 4);
~~~

Inspect:

~~~java
area;
diagonal;
~~~

Approximate result:

~~~text
28.274333882308138
5.0
~~~

Static imports make formulas more concise. If the code has multiple classes providing methods with the same name, keep the qualifier to avoid ambiguity and help readers identify the method's source.

## 16. Putting Imports into a Script File

When you need to repeat an experiment, you can save imports and snippets into a .jsh file.

Example file **date-demo.jsh**:

~~~java
import java.time.LocalDate;
import static java.time.temporal.ChronoUnit.DAYS;

LocalDate start = LocalDate.of(2026, 11, 10);
LocalDate due = start.plusDays(14);
DAYS.between(start, due);
~~~

Load the file at startup:

~~~bash
jshell date-demo.jsh
~~~

Or from a running session:

~~~text
jshell> /open date-demo.jsh
~~~

Script files can contain Java snippets and JShell commands. Place each snippet or command on its own line for readability, editing, and reuse.

If you want to create a startup file containing only imports, place the imports at the top of the script and add any needed methods or helpers afterward. Avoid putting operations with side effects in a startup script if you do not want them to re-run after every reset.

## 17. Diagnosing Common Import Errors

### Cannot find symbol: class LocalDate

A common cause is a missing import or a startup script that does not load java.time.

How to fix:

~~~java
import java.time.LocalDate;
~~~

Or use the fully qualified name:

~~~java
java.time.LocalDate.now();
~~~

### Package does not exist

The package name may be wrong, or the library is not yet on the classpath/module path. Check the package name, JAR, path, and how JShell was started.

For external libraries:

~~~bash
jshell --class-path lib/helper.jar
~~~

### Reference to Date is ambiguous

Multiple types with the same name are imported. Use the fully qualified name:

~~~java
java.util.Date
java.sql.Date
~~~

Or import only one specific type.

### Static import cannot find member

Check whether the class has that public static member. Static imports cannot import instance methods or instance fields.

For example, Math.PI is a static field, whereas an instance method cannot be imported with import static.

### Import succeeds but the class is still inaccessible

Imports do not bypass visibility or module encapsulation. Check whether the class is public, whether the package is exported, and whether the module is resolved.

### Imports disappear right after a reset

/reset clears user-entered snippets and re-runs the startup script. Put frequently used imports in a startup script or re-enter them after a reset.

### Script loads but imports have no effect

Check the file path, syntax errors in the script, and the order of startup scripts. Use /imports and /list -start to see which snippets were actually loaded.

### Added a JAR but still cannot import

Check that the JAR contains classes in a named package, that the classes are accessible, and that the classpath points to the right file. If it is a named module, use the module path and resolve the module instead of only adding to the classpath.

## 18. Effective Workflow for Imports in JShell

1. Open JShell with the desired JDK.
2. Run /imports to see which imports startup already provides.
3. Only import additional packages or types that are not yet present.
4. Use single-type imports for important or easily colliding types.
5. Use wildcards when experimenting with many types from the same package.
6. Use static imports when expressions are short and the member source is clear.
7. When an ambiguous name error occurs, use the fully qualified name to specify the type.
8. If using external libraries, configure the classpath/module path before importing.
9. Put repeated imports into a .jsh script or startup script.
10. After /reset or /env, re-check imports because the session state may have been recreated.
11. Use /save or /save -start to save snippets and configurations for reuse.
12. When you need to verify independence, run jshell --no-startup and declare imports explicitly.

Imports make JShell a convenient experimentation environment: you can focus on APIs and logic instead of repeating long package names. When you understand startup imports, single-type imports, wildcard imports, static imports, and session management, you will avoid most missing-type or ambiguous-name errors when working with the Java REPL.

## References

- [Java Shell User’s Guide — Scripts (JDK 17)](https://docs.oracle.com/en/java/javase/17/jshell/scripts.html)
- [Java Shell User’s Guide — External Code (JDK 17)](https://docs.oracle.com/en/java/javase/17/jshell/external-code.html)
- [The jshell Command — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jshell.html)
- [Java Shell User’s Guide — Scripts (JDK 24)](https://docs.oracle.com/en/java/javase/24/jshell/scripts.html)
