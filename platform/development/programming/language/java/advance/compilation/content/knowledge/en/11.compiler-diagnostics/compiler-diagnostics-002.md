# Distinguishing Syntax, Name, Type, Access, and Dependency Errors When Compiling Java

## 1. Learning Objectives

When running javac, the word error alone is not enough to know where to fix. Many errors have similar-looking messages but belong to different causes: a statement written with invalid syntax, a syntactically valid name whose declaration the compiler cannot find, an expression using the wrong type, a member that exists but is not allowed to be accessed, or a class/library not present in the dependency set used for compilation.

This lesson focuses on five diagnostic groups:

1. **Syntax/parsing errors**: the token sequence does not form a valid Java construct.
2. **Name/symbol resolution errors**: the compiler cannot resolve the name of a class, variable, method, or package in the current context.
3. **Type checking errors**: the name is resolved, but the type, parameter, return value, or assignment is incompatible.
4. **Accessibility errors**: the declaration exists, but cannot be used from the call site according to access modifiers or module boundaries.
5. **Dependency/configuration errors**: the source code requires a class/JAR/module, but the compiler or runtime cannot find a matching version.

The goal is not to memorize a fixed wording table of javac, because diagnostics can change across JDK versions, but to **trace backward from the error to the checking layer and the condition that needs to be restored**. At the end of the lesson, there is a runnable Java 17+ project, intentional error experiments, a diagnostic workflow, and self-check exercises.

## 2. Why Are Error Groups Related Yet Different?

Imagine the compilation process at a high level:

~~~text
.java file
   |
   v
Read characters, tokenize, parse syntax
   |             Syntax error: missing ;, }, misplaced token
   v
Resolve names and declarations
   |             Name error: cannot find symbol
   v
Check types and accessibility
   |             Type error: incompatible types
   |             Access error: private access / package not visible
   v
Flow analysis, check other constraints
   |             Example: missing return, uninitialized variable
   v
Generate .class bytecode
   |
   v
JVM loads and runs .class
                 Runtime error: NoClassDefFoundError, NoSuchMethodError...
~~~

The diagram is a **learning model**. In actual javac, name resolution, type attribution, accessibility, and semantic checks may interleave; do not view them as five completely independent subroutines running sequentially. Nor should you equate **the first message javac prints** with the single root cause: one dependency error can trigger a cascade of cannot find symbol and incompatible types errors afterward.

Orientation table:

| Group | Question to Check | Common Diagnostics |
| --- | --- | --- |
| Syntax | Are braces/parentheses, semicolons, and token positions valid? | ';' expected; reached end of file while parsing |
| Name | Is the name declared in the right scope/import/package? | cannot find symbol |
| Type | Are conversions/assignments/calls between types valid? | incompatible types; method cannot be applied to given types |
| Access | Does the caller have permission to use that type/member? | has private access; is not public; package ... is not visible |
| Dependency | Is the class/JAR/module on the right compile/runtime path? | package ... does not exist; module not found; NoClassDefFoundError |
| Other checks | Are control paths/exceptions/definite assignment valid? | missing return; unreachable statement; unreported exception |

**Classification is for finding the cause, not for forcing every error line into one single box.** For example, cannot find symbol can happen because of a misspelled name, but also because of a missing JAR. When a dependency is missing, the compiler symptom can sometimes appear as a name resolution error.

## 3. Preparing a Java 17 Project for Comparison

Create the **diagnostics-lab** directory with two source files:

~~~text
diagnostics-lab/
└── src/
    └── demo/
        ├── api/
        │   └── Printer.java
        └── app/
            └── Main.java
~~~

The out directory will be created before compilation. The two classes are placed in two different packages to demonstrate import and access issues.

### File src/demo/api/Printer.java

~~~java
package demo.api;

public final class Printer {
    private Printer() {
    }

    public static String label(int count) {
        return "Count=" + count;
    }

    private static String internalLabel(int count) {
        return "Secret=" + count;
    }
}
~~~

Printer has a public method label(int) returning String. internalLabel(int) exists but is private, used only internally within the Printer class. The private constructor does not affect calling the public static method.

### File src/demo/app/Main.java

~~~java
package demo.app;

import demo.api.Printer;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        String message = Printer.label(3);
        System.out.println(message);
    }
}
~~~

Main imports the correct class name Printer, passes an int to label(int), receives a String, and prints it out. Both files use valid Java 17 syntax.

### Compile and Run Commands

Position your terminal in the **diagnostics-lab** directory, which contains src. Check:

~~~sh
javac -version
java -version
~~~

Use JDK 17 or newer. Create out according to the shell you are using:

~~~bash
# Bash (Linux/macOS)
mkdir -p out
~~~

~~~powershell
# Windows PowerShell
New-Item -ItemType Directory -Path out -Force | Out-Null
~~~

Compile both files:

~~~sh
javac -encoding UTF-8 --release 17 -d out src/demo/api/Printer.java src/demo/app/Main.java
~~~

Run:

~~~sh
java -cp out demo.app.Main
~~~

**Exact stdout of the original code:**

~~~text
Count=3
~~~

The bytecode output contains:

~~~text
out/
└── demo/
    ├── api/
    │   └── Printer.class
    └── app/
        └── Main.class
~~~

In the experiments below, **only edit the specified line and recompile**. Each experiment starts from the original version of the two files above; revert changes before trying the next error. The broken snippets are code **intentionally written not to compile**, not standalone runnable examples.

## 4. Group 1 — Syntax Errors: The Compiler Does Not Understand the Statement Structure

Characteristic: the compiler cannot yet build a valid syntax tree from the token sequence in a portion of the source. Common omissions include missing semicolons, missing braces/parentheses, misplaced characters, unclosed quotes, invalid escape sequences, or syntactically invalid keyword usage.

### Example 1: missing semicolon

In Main.java, modify:

~~~java
String message = Printer.label(3)
System.out.println(message);
~~~

The variable declaration line is missing a ;. javac usually reports a message like **';' expected** at the position where it expects a terminator. Fix to:

~~~java
String message = Printer.label(3);
System.out.println(message);
~~~

**Why is this a syntax error?** Without even checking whether Printer exists, whether the method is public, or whether the String type is correct: the way the statement is structured violates Java grammar.

### Example 2: missing closing curly brace

If you delete a closing } at the end of the class, javac may report something like **reached end of file while parsing**. The error location sometimes lies **at the end of the file**, not right where you accidentally missed the brace. When seeing this error, match pairs of { }, ( ), [ ], and inspect the class/method/if/try blocks just edited.

### Example 3: misplaced token

~~~java
int value = ;
~~~

The expression after the = sign is left blank. The diagnostic may state illegal start of expression. Do not fix by casting the variable to String or adding an import: you must supply a valid expression, for example int value = 3;.

### How to Diagnose Syntax Errors

- Start from **the first line with a parsing diagnostic**, but also check the preceding line: the error may appear on the token after the actual missing location.
- Verify pairs of braces/parentheses, semicolons, quotation marks, declaration structures, and keywords.
- Fix one structural error first, then recompile. A single missing } can cause the compiler to report many cascading errors.
- When code is newly copied from a webpage, check for curly quotation marks or Unicode characters replacing regular " or '.

The compiler **does not fix syntax for you** even though an IDE may suggest fixes; diagnostics help locate what needs fixing in the source.

## 5. Group 2 — Name Errors: cannot find symbol

A name error occurs when the compiler understands an expression or call grammatically, but cannot find a matching declaration in the visible scope, imports, or type set.

### Example 1: wrong method name

In Main.java, write:

~~~java
String message = Printer.lable(3);
~~~

Printer has a method named label, not lable. javac usually reports something like:

~~~text
cannot find symbol
  symbol:   method lable(int)
  location: class demo.api.Printer
~~~

The snippet above illustrates the main part of the diagnostic, without guaranteeing the exact position/alignment/lines of every javac build.

**How to fix:** change lable to label. The Printer class has already been identified, so the first step is checking the method name and signature of Printer rather than rushing to adjust the classpath.

### Example 2: variable out of scope

~~~java
if (true) {
    int count = 3;
}
System.out.println(count); // ERROR: count is out of scope
~~~

The count variable is declared inside the if block. Outside that block, the name is no longer in scope; the compiler may report cannot find symbol for variable count. Fix by declaring the variable in an appropriate scope and ensuring definite assignment before reading.

### Example 3: class name not found

If you delete the line:

~~~java
import demo.api.Printer;
~~~

while still using the short name Printer in package demo.app, the compiler does not automatically look inside package demo.api. Fix by restoring the import or using the fully qualified name demo.api.Printer.

**Note:** a cannot find symbol error does not always mean "misspelled". It can also happen because the class is in a dependency not yet added to the compile classpath, the package is wrong, the source has not been compiled, or the code was written for a different API/version.

### Procedure for Name Errors

1. Read the **symbol** section: is a variable, class, or method missing? Are there specific parameters/types?
2. Read the **location** section: in which class is the compiler looking for the method, or in which scope is it looking for the name?
3. Check spelling and uppercase/lowercase, imports, packages, block scope, and actual declarations.
4. If the class is not yet visible to the compiler, move on to checking **dependencies and classpath**; do not create a dummy variable or method just to make the error disappear.

## 6. Group 3 — Type Errors: The Name May Be Correct, Yet Usage Is Invalid

Java checks types statically. A method may exist and be accessible, yet the call is still invalid if the parameter list, generic types, return value, or assignment is invalid.

### Example 1: passing String instead of int

Main.java calls:

~~~java
String message = Printer.label("3");
~~~

The method is declared as label(int), while "3" is a String. The compiler will report an error about **String cannot be converted to int**, or that the method cannot be applied to the passed argument types, depending on how diagnostics are displayed.

**Proper fix:** pass an actual int:

~~~java
String message = Printer.label(3);
~~~

If the data starts as user-entered text, it must be converted with validation:

~~~java
int count = Integer.parseInt("3");
String message = Printer.label(count);
~~~

The conversion snippet can throw NumberFormatException if the string is not a valid integer. Passing type checking **does not guarantee valid runtime input**.

### Example 2: unassignable return type

~~~java
int result = Printer.label(3); // ERROR: method returns String
~~~

The compiler may report incompatible types: String cannot be converted to int. The error is not in the import, because the method was found. Change the receiving variable to String, or modify the API design if an integer is genuinely needed.

### Example 3: generic invariance

~~~java
java.util.List<String> texts = java.util.List.of("a", "b");
java.util.List<Object> values = texts; // COMPILE ERROR
~~~

Although String is a subtype of Object, List<String> is **not** a subtype of List<Object>. If such an assignment were allowed, one could add an Integer into a list expected to contain only Strings. Depending on the goal, you can use List<? extends Object> for reading with corresponding bounds, or create a new list:

~~~java
java.util.List<Object> values =
        new java.util.ArrayList<>(texts);
~~~

This snippet is valid with appropriate generic inference, creating a separate list to add other Objects if needed.

### Example 4: overloaded methods and ambiguity

If multiple overloads match equally well with no single best choice, the compiler may report **reference to ... is ambiguous**. You should not treat this as cannot find symbol: the method was found with **too many equivalent candidates**. Fix by choosing exact parameter types, a less ambiguous overload, or an intentional cast if truly needed.

### How to Diagnose Type Errors

- Read **required** and **found** (or inferred type/actual argument list) in the detailed output.
- Compare each parameter type with each argument in exact order.
- Check method return types, generic type arguments, boxing/unboxing, and primitive conversions.
- Do not fix blindly with a cast. A cast may pass compilation but cause ClassCastException at runtime.
- If a dependency API has changed its signature, check the **dependency version** before modifying logic.

## 7. Group 4 — Access Errors: The Member Exists, Yet Cannot Be Used

Access errors differ from name errors: the compiler can find the declaration, but **the calling context lacks permission to use it**.

### Example 1: calling a private method from another class

In Printer.java, internalLabel(int) is private. If Main.java calls:

~~~java
String message = Printer.internalLabel(3);
~~~

javac reports something like:

~~~text
internalLabel(int) has private access in demo.api.Printer
~~~

The difference from the lable case is: **the method actually exists**, yet private prevents Main from accessing it.

Well-designed fix: call the public API Printer.label(3). Only change internalLabel to public if you truly want to include it in the API contract, because changing an access modifier affects class design and future clients.

### Common Access Levels

| Modifier | Rule at the Java Language Level |
| --- | --- |
| public | Accessible from elsewhere if other conditions like module readability/exports are also satisfied |
| protected | Accessible within the same package and from subclasses in other packages according to specific protected rules |
| No modifier written | Package-private: only code in the matching same package may use it |
| private | Private access scope according to Java's private/nestmates rules; not open to any other class |

**Do not confuse a package with a folder:** two classes having the same package name in Java is not simply "being in the same directory". Package declarations, modules, and runtime environments all matter.

### Example 2: unexported package of a named module

In JPMS, a public class inside an unexported package of a target module can still be **inaccessible** from another named module. Illustrative descriptor snippet:

~~~java
// module-info.java of the library module
module demo.library {
    exports demo.api;
}
~~~

If another module requires demo.library and then imports a public class in demo.internal (unexported), the compiler may report package ... is not visible or does not export package. This is a **module boundary error**, not because the class lacks public.

The descriptor above is only illustrative; to run standalone, you need to organize the sources of the two modules, a consumer module, and the corresponding classes.

**How to fix:** prefer a public API located in an exported package, or intentionally change the descriptor's exports. A requires declaration creates a readability relationship, yet **does not automatically export every package** of the dependency. When errors involve deep reflection, opens may be needed rather than exports; the goals of the two declarations differ.

## 8. Group 5 — Dependency Errors: Valid Code, Missing Matching Class/JAR/Module

A **dependency** is a class, library, or module that source code needs to compile and/or the program needs at runtime. A missing dependency can manifest as a package-does-not-exist or cannot find symbol error, yet the real cause is **an incomplete compiler/runtime input set**.

### Case A: compiling only Main while the compiler cannot see Printer

From the diagnostics-lab root, if you run:

~~~sh
javac -encoding UTF-8 --release 17 -d out src/demo/app/Main.java
~~~

in a setup where Printer is not on the compiler classpath/sourcepath, javac cannot find demo.api.Printer. Diagnostics may include **package demo.api does not exist** and **cannot find symbol Printer**.

This is an error of missing **dependent source or class in the search path**. It may look like a name error; you must check whether Printer.java exists and has the right package.

The simplest way is to list both files as in section 3:

~~~sh
javac -encoding UTF-8 --release 17 -d out src/demo/api/Printer.java src/demo/app/Main.java
~~~

Or if Printer.class is already compiled in out, compile Main separately with the classpath:

~~~sh
javac -encoding UTF-8 --release 17 -d out src/demo/api/Printer.java
javac -encoding UTF-8 --release 17 -cp out -d out src/demo/app/Main.java
~~~

The two options have different roles:

- **-cp out** (for javac) helps the compiler find already-compiled classes belonging to dependencies.
- **-d out** selects where to write new .class files. It does not automatically add out to the compiler classpath.

### Case B: compilation succeeds, runtime is missing Printer

Suppose Main.class was compiled when Printer was present, yet at runtime Printer.class is missing from the runtime classpath (or Printer's JAR was omitted from the package). The JVM may throw **NoClassDefFoundError** when needing to load Printer. This is a runtime error, not a javac syntax error.

Similarly, **ClassNotFoundException** usually appears when an API loading a class by name (such as Class.forName) cannot find the class. The two types are related, yet they are different APIs/failure points; you should not use them as a single label.

### Case C: class exists, but API version differs

A client compiled against the label(int) method, yet at runtime loads a Printer.class version that no longer has a binary-compatible method. When bytecode tries to call the old descriptor, the JVM may report **NoSuchMethodError**. Check dependency versions and runtime artifacts, and rebuild the appropriate modules; do not edit spelling in the source when the error arises from mismatched .class/JAR files.

### Case D: incompatible JDK and bytecode

If a newer JDK generates bytecode with a class-file version higher than the running JVM supports, runtime reports **UnsupportedClassVersionError**. The --release 17 flag in the example restricts the source's bytecode/platform APIs to Java 17. It **does not automatically make an external JAR compiled with a newer Java version compatible with Java 17**.

Check java -version, javac -version, toolchain configuration, and dependency class versions.

### Case E: module path and classpath mixed up

With explicit named modules, the compiler/runtime must resolve dependencies on the appropriate module path and the descriptor must declare requires; public packages must have appropriate exports. Placing a JAR on the classpath or module path **does not always have the same effect**.

When javac says module not found or package is not visible, check module-info.java, module names, module path, requires, and exports. When using only the regular classpath, check compile/runtime -cp and .class/JAR structure.

## 9. Distinguishing Compile-Time Errors from Runtime Errors

| Phase | Example | Characteristics |
| --- | --- | --- |
| Before/during javac | ';' expected | Parser does not understand source |
| During javac | cannot find symbol | Compiler cannot resolve name |
| During javac | incompatible types | Argument/value type is invalid |
| During javac | has private access | No permission to access method |
| During javac | package ... does not exist | May be missing source/import/classpath |
| When JVM starts | Could not find or load main class | Wrong main class name or runtime classpath/module configuration |
| When JVM loads/links class | NoClassDefFoundError | Missing dependency class that had been needed during compile/link |
| When JVM links call | NoSuchMethodError | Runtime method descriptor differs from caller's assumption |
| When JVM checks .class version | UnsupportedClassVersionError | Bytecode is newer than what runtime can handle |
| While code runs | NumberFormatException, NullPointerException | Actual data or condition is invalid |

**Important:** javac may report errors while the out directory still holds .class files from a previous compilation. If you immediately run java, you may be running **the old build**, leading to the false conclusion that broken code still runs. When testing, make sure javac succeeds from the current source and java uses the right output.

Not every runtime error is a "dependency error"; for example, NullPointerException can be caused by logic or data. Conversely, a dependency-related error can appear **right at compile-time** if javac cannot see an imported class.

## 10. How to Read a javac Diagnostic Properly

Illustrative example when calling a wrong method:

~~~text
src/demo/app/Main.java:...
error: cannot find symbol
    String message = Printer.lable(3);
                            ^
  symbol:   method lable(int)
  location: class demo.api.Printer
~~~

Do not rely on line numbers or the ^ marker position in this illustrative example, because actual output may vary across javac versions. Extract the key information:

- **File/line**: the source being processed by javac and the location to inspect.
- **Error message**: the type of issue detected by the compiler.
- **Symbol/required/found/location**: specific names or types to compare.
- **First meaningful errors**: the source of the error causing cascading diagnostics.

Every diagnostic line should be read, yet **it is not necessary to fix every line simultaneously**. If the parser is missing a } brace or a dependency JAR, fixing that exact cause can make many subsequent errors disappear.

### Enabling Detailed Diagnostics

When supported by the compiler, add the option:

~~~sh
javac -Xdiags:verbose -encoding UTF-8 --release 17 -d out src/demo/api/Printer.java src/demo/app/Main.java
~~~

The -Xdiags:verbose option helps view more detailed diagnostics in some situations such as overloads and generic types. This is an **observation** tool, not an automatic error-fixing mode.

To view potential warnings:

~~~sh
javac -Xlint:all -encoding UTF-8 --release 17 -d out src/demo/api/Printer.java src/demo/app/Main.java
~~~

-Xlint:all enables lint warning groups supported by javac. Warnings are not synonymous with compile errors: javac can still generate .class files when there are only warnings. The **-Werror** option can turn the "has warnings" condition into a build failure; only use it when project policy requires it.

### Exit Codes and Build Tools

Normally javac returns a non-zero exit code when compilation fails. In CI, Maven, Gradle, or IDEs, look for **the actual javac command or original diagnostic** beneath the "build failed" message. The wrapper error itself does not tell you whether you encountered a syntax, type, or dependency issue; the original message helps locate it.

When needing to inspect the compiler command that a build tool actually uses, inspect the tool's compiler arguments/verbose logging at an appropriate level. Pay special attention to JDK toolchain, source roots, classpath/module path, and annotation processors.

## 11. Diagnostic Decision Tree

~~~text
javac fails
    |
    +-- Does not understand token/structure? (';' expected, parsing ...)
    |      -> Check syntax and braces/brackets/parentheses.
    |
    +-- Name cannot be resolved? (cannot find symbol)
    |      -> Check scope, imports, API names.
    |      -> If a dependency class is missing: check compile classpath/module path.
    |
    +-- Name exists but types do not match? (incompatible types)
    |      -> Compare required/found, signature, generics, overloads.
    |
    +-- Name exists but is not usable? (private access/not exported)
    |      -> Check modifiers, package, requires/exports.
    |
    +-- Module/JAR cannot be found?
    |      -> Check version, source roots, dependency artifact/path.
    |
    v
Compilation succeeds
    |
    +-- java cannot find main class?
    |      -> Check fully qualified name and runtime classpath/module path.
    |
    +-- Runtime missing class/method?
    |      -> Check class/JAR presence and binary compatibility.
    |
    v
Run tests to confirm behavior
~~~

This tree serves practical operations; not every diagnostic has completely independent boundaries. For example, access errors can occur during member resolution, and dependency errors can appear as cannot find symbol. Check for **the deepest cause consistent with the source code and configuration**.

## 12. Diagnosing by Root Cause, Not by Symptoms

### Scenario 1: method renamed, yet dependency has not been upgraded

Client code calls Printer.label(3). If the source of the Printer build being compiled only has the method format(int), javac may report cannot find symbol: method label(int). This is a name error **according to the API currently visible to the compiler**, yet the business/domain cause may be a version mismatch between client and library. Before recreating the method or editing code, check the API contract and expected dependency version.

### Scenario 2: missing import and missing JAR look quite similar

- If Printer is on the compile classpath yet import demo.api.Printer is missing and a fully qualified name is not used, fixing the import may be enough.
- If Printer is completely absent from the compile classpath/sourcepath, adding an import will not help the compiler find the class either.

Therefore, you must check both **the source declaration** and **the presence of the dependency**, instead of blindly trying imports.

### Scenario 3: private methods should not be "fixed" recklessly with public

A private access error does not prove the class is poorly designed. Most likely the caller is using an internal API. Look for a public method that serves the right task, or design a public façade with a clear contract. Automatically turning every member into public just to silence javac errors breaks encapsulation.

### Scenario 4: casting to make type errors disappear

If javac reports String cannot be converted to int, adding a cast forcing Object/String to Integer may allow code to compile in some configurations, yet easily causes ClassCastException at runtime. The right handling may be parsing text data into numbers with validation. Passing compilation only proves compliance with static type rules, not that runtime data is valid.

### Scenario 5: wrong package or wrong classpath root

A Java source declaring package demo.api yet run from the wrong classpath root can cause runtime class-loading errors. Distinguish:

~~~text
Class name: demo.app.Main
.class file: out/demo/app/Main.class
Classpath root: out
Command: java -cp out demo.app.Main
~~~

Do not set the classpath to out/demo/app and expect the JVM to automatically strip parts of the package name.

## 13. Additional Errors Easy to Misclassify

Besides the five main groups, Java has many other important language constraints:

| Diagnostic | Actual Cause |
| --- | --- |
| variable ... might not have been initialized | **Definite assignment**: a path to the read point has not assigned the variable |
| unreachable statement | **Reachability**: there is no valid control flow path to the statement |
| missing return statement | A method can finish normally without a return value |
| unreported exception ... must be caught or declared | Checked exception not yet caught or declared with throws |
| class X is public, should be declared in a file named X.java | Filename rule for public top-level classes |
| reference to method is ambiguous | Overload resolution cannot choose a unique candidate |
| variable X is already defined | Duplicate name declaration in a disallowed scope |
| bad class file / class file has wrong version | Input class file/dependency is incompatible or unreadable |

You should not call all of these syntax errors. Many snippets are **syntactically valid**, yet violate semantic/flow checks or file organization rules.

### Example of definite assignment

~~~java
int count;
if (args.length > 0) {
    count = 3;
}
System.out.println(count); // There is a path where count is not assigned
~~~

This is not an error caused by the int keyword or an invalid count name. The compiler analyzes control flow paths and notices that when args.length == 0, count has not been assigned. Fix by initializing, adding else, or changing the control flow to fit business logic.

## 14. Practice: Change Exactly One Cause Each Time

Start from the two valid files in section 3, keeping originals for easy reverting. For each experiment, predict in advance whether **compile will pass or fail**, the error group, then run javac and read the diagnostic.

1. **Syntax:** delete the ; after Printer.label(3). Why does the compiler not need type checking yet to detect the error?
2. **Name:** change label to lable. Which class did the compiler find? Which method name does not exist?
3. **Type:** pass "3" instead of 3. Compare the actual type with the required type.
4. **Access:** change label to internalLabel. Why does the method really exist, yet Main is not allowed to call it?
5. **Dependency:** compile only Main from the project root when Printer is not configured in compile classpath/sourcepath. Why does adding an import not solve it?
6. **Runtime dependency:** suppose the runtime package is missing Printer.class even though compilation succeeded. Does the error occur in javac or the JVM?
7. **Version mismatch:** the client compiled with the old API, yet runtime receives a library build with a changed signature. What kind of error may appear?
8. **Stale output:** edit the code without recompiling, then run java. Why might stdout still reflect the previous build?

For syntax/name/type/access errors, after fixing back to the valid version, rerun:

~~~sh
javac -encoding UTF-8 --release 17 -d out src/demo/api/Printer.java src/demo/app/Main.java
java -cp out demo.app.Main
~~~

Expected output always returns to:

~~~text
Count=3
~~~

Do not test multiple error versions in the same source and try to attribute every diagnostic to one change: when the compiler encounters multiple errors, one error can mask or lead to another.

## 15. Error-Handling Checklist in Real Projects

Before editing code, ask yourself:

- **Did the error occur in javac or the JVM?** Were new .class files generated successfully, or are you running stale output?
- **What does the first diagnostic say?** Syntax parsing, unresolved name, wrong type, lack of permission, or artifact not found?
- **Which sources and dependencies is the compiler seeing?** Are the package, API version, JDK, and compile classpath/module path right?
- **Does the caller have permission to use that API?** Check public/private, package, requires, and exports.
- **Are the required/found types accurate?** Are generics, overloads, or conversions altering the call?
- **Does runtime use the same set of JAR/.class files as compile?** Is there a binary mismatch, missing class, or older JDK runtime?
- **Does the fix have a sound business contract?** Do not arbitrarily add casts, public, or fallbacks just to eliminate errors.
- **Have you recompiled and tested?** Confirm the javac command succeeds and the java command runs the new artifact.

### Quick-Reference Table

| Seeing Diagnostic | First Question | Usually Right Fix Direction |
| --- | --- | --- |
| ';' expected | Which punctuation or construct is missing? | Fix syntax |
| cannot find symbol | Which name, in which scope/class? | Fix name/import/scope or missing dependency |
| incompatible types | Where do required and actual differ? | Use right type/API/validated conversion |
| has private access | Why does the caller lack permission? | Use appropriate public API, preserve encapsulation |
| package ... does not exist | Wrong package or dependency not yet visible? | Check sources, compile classpath/module path |
| NoClassDefFoundError | Which class is runtime missing? | Check runtime artifact/classpath |
| NoSuchMethodError | Do client and library share the same binary contract? | Compare versions/rebuild consistently |
| UnsupportedClassVersionError | Does runtime support the class-file version? | Choose matching toolchain and --release |

## 16. Self-Assessment

You have mastered the lesson if you can explain:

1. Why a missing ; is a syntax error while misspelling lable is a name error.
2. Why passing String to label(int) is a type error even though the method exists and is public.
3. Why private access differs from cannot find symbol.
4. Why package does not exist can be a **dependency symptom** rather than a wrong package name.
5. Why compile success does not guarantee a complete runtime classpath.
6. Why -d out and -cp out serve two different purposes.
7. Why a first error can trigger many cascading diagnostics.
8. Why fixing compiler errors must go hand-in-hand with checking API contracts and runtime results.

### Further Reading

- **Java Language Specification (JLS)**: lexical structure, syntax, names, types, access control, and definite assignment.
- Official **javac** documentation for the exact JDK you are using: options -cp/--class-path, --module-path, --release, -Xdiags, and -Xlint.
- **Java Virtual Machine Specification** and Java launcher documentation: class loading/linking, class-file version, and linkage errors.
- **Java Platform Module System (JPMS)**: requires, exports, module resolution for programs using named modules.

Every time you encounter an error, distinguish **whether the code is syntactically valid, whether the name is found, whether the type is compatible, whether access permissions are valid, and whether the dependency is present in the right version**. Classifying like this helps fix **the cause** rather than merely deleting error messages.