# Enabling lint in javac

Lint is the warning analysis mechanism of the Java compiler. When lint is enabled, javac performs additional checks for code patterns that may cause bugs, be hard to maintain, or hide problems, even when the source code is still valid in syntax and types. Warnings can point out the use of raw generic types, calls to deprecated APIs, redundant casts, switch statements with potential fall-through, or classpath configuration issues.

Lint helps teams detect risks right at the compilation step. It is especially useful in code reviews, multi-member projects, and CI pipelines, where a small warning ignored for a long time can turn into a hard-to-trace bug.

## 1. How is a lint warning different from a compile error?

The Java compiler checks multiple rules at different levels:

- **Compile error:** source code violates a mandatory language rule or cannot resolve a type/member. Javac cannot complete a normal compilation.
- **Lint warning:** the code can still compile, but javac notices a suspicious construct or one with a risk of causing bugs. Warnings help developers review and decide whether a fix is needed.
- **Runtime error:** an issue that only appears when the program runs, such as invalid data, missing configuration, or a logic bug. Lint cannot detect every runtime error.

For example, using raw types with collections is still valid in Java because the language maintains compatibility with older Java code. However, this usage loses generic type checking and can lead to a ClassCastException. Lint can warn developers so they switch to concrete generic types.

By default, many lint warnings do not cause javac to fail. If you want to treat warnings as build errors, you can combine the -Werror option.

## 2. Enabling lint with -Xlint

The primary option is:

~~~bash
javac -Xlint SourceFile.java
~~~

To enable lint categories:

~~~bash
javac -Xlint:all SourceFile.java
~~~

- **-Xlint** enables the recommended lint warnings.
- **-Xlint:all** enables all lint categories supported by the current javac version.
- **-Xlint:<category>** enables a specific warning category.
- **-Xlint:-<category>** disables a specific warning category.
- **-Xlint:none** disables lint categories.

For example, enabling only warnings about unsafe generics:

~~~bash
javac -Xlint:unchecked SourceFile.java
~~~

Enabling both raw types and unchecked operations:

~~~bash
javac -Xlint:rawtypes,unchecked SourceFile.java
~~~

Enabling most warnings while excluding the serial category:

~~~bash
javac -Xlint:all,-serial SourceFile.java
~~~

Category names and warning scopes may vary between JDK versions. To view the list supported by the javac installed on your machine:

~~~bash
javac --help-lint
~~~

Do not assume every developer machine and CI environment has the same list of warnings if they use different JDK versions.

## 3. Common lint categories

The categories below are often useful when working with Java code:

| Category | What does it warn about? |
|---|---|
| deprecation | Using an API marked as deprecated. |
| removal | Using an API marked for removal. |
| unchecked | Generic conversions, calls, or operations that are not fully type-checked at compile time. |
| rawtypes | Using a generic type without providing type arguments, for example List instead of List<String>. |
| serial | Issues related to serialization, such as a Serializable class missing serialVersionUID. |
| cast | Casts that may be redundant or unnecessary. |
| fallthrough | A switch branch that may fall through to the next case without an appropriate break/yield. |
| finally | Certain suspicious finally constructs that may lose the expected control flow. |
| static | Accessing a static member through an object expression instead of a class name. |
| try | Certain issues related to try-with-resources or resources declared but not used as expected. |
| varargs | Potentially unsafe varargs usage, especially with generic varargs. |
| path | Issues with path elements for finding classes or source code. |
| processing | Warnings related to annotation processing. |

These are common categories to start with. The exact list and detailed descriptions depend on the JDK; use javac --help-lint to view information for the current version.

## 4. Example: raw type and unchecked warning

Generics help the compiler check collection element types. When type arguments are omitted, the code uses a raw type and loses part of the type checking.

Create the file RawTypeWarning.java:

~~~java
import java.util.ArrayList;
import java.util.List;

public class RawTypeWarning {
    public static void main(String[] args) {
        List names = new ArrayList();
        names.add("Linh");

        String first = (String) names.get(0);
        System.out.println(first);
    }
}
~~~

Compile with lint:

~~~bash
javac -Xlint:rawtypes,unchecked RawTypeWarning.java
~~~

Javac may warn at the List and ArrayList declarations due to missing type arguments, and also warn on the add call on the raw type because the operation is not fully generic-type-checked. The exact warning formatting, line positions, and detailed messages depend on the JDK version.

The program can still run and print:

~~~text
Linh
~~~

However, data types are not fully checked. If a non-String object is accidentally added to the collection and then cast to String, the program may fail at runtime.

### How to fix using generics

Use type arguments to declare the element type:

~~~java
import java.util.ArrayList;
import java.util.List;

public class GenericListDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("Linh");

        String first = names.get(0);
        System.out.println(first);
    }
}
~~~

Compile with all lint warnings enabled and treat warnings as errors:

~~~bash
javac -Xlint:all -Werror GenericListDemo.java
java GenericListDemo
~~~

Output:

~~~text
Linh
~~~

This example compiles cleanly on JDK 17+ without manual casting. If the source code has warnings belonging to enabled lint categories, -Werror will cause the compilation to fail.

## 5. Combining -Xlint with -Werror

The -Werror option tells javac to terminate with an error when warnings are detected. When used together with lint, a team can establish a rule: all new lint warnings must be resolved before a build can succeed.

~~~bash
javac -Xlint:all -Werror -d out src/main/java/com/example/Main.java
~~~

Meaning:

- -Xlint:all enables warning categories.
- -Werror turns warnings into a condition that fails the build.
- -d out selects the output directory for bytecode.

If out does not exist yet, create the directory before running javac:

~~~bash
mkdir -p out
~~~

In PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
~~~

Then run the corresponding javac command. For multi-file projects, source path, classpath, or module path still need to be configured separately; -Xlint does not locate dependencies in place of those options.

### When should you use -Werror?

- In shared libraries, where APIs and warnings affect multiple projects.
- In CI, to prevent new warnings from slipping into the main branch.
- In new projects, where the team can keep the source code clean from the start.
- When upgrading the JDK, after reviewing new warnings caused by compiler changes.

Do not enable -Werror abruptly on a legacy codebase that already has many unresolved warnings. Doing so can cause a configuration change to fail the entire build even though there are no new functional bugs. Instead, enable lint, collect warnings, resolve them by category, and only switch to -Werror once the baseline is clean or the team has a clear control plan.

## 6. Selecting and excluding individual categories

Not every project wants to enable all categories right away. You can enable a specific category to investigate:

~~~bash
javac -Xlint:deprecation -d out src/main/java/com/example/Main.java
~~~

This command focuses on the usage of deprecated APIs.

If you have enabled all categories but need to temporarily exclude a category that has been evaluated:

~~~bash
javac -Xlint:all,-serial -d out src/main/java/com/example/Main.java
~~~

You can disable unchecked separately:

~~~bash
javac -Xlint:all,-unchecked -d out src/main/java/com/example/Main.java
~~~

Exclusions should only be used when there is a clear reason, such as a legacy compatibility section waiting to be fixed. Document the reason and scope so the team can revisit it. Disabling warnings broadly removes useful signals in future builds.

## 7. Using @SuppressWarnings with the right scope

Sometimes a warning is intentional or cannot be eliminated immediately, such as when integrating with a legacy API that does not use generics. Java provides the SuppressWarnings annotation to ignore certain warning categories in a specific scope.

Example:

~~~java
import java.util.ArrayList;
import java.util.List;

public class LegacyAdapter {
    @SuppressWarnings({"rawtypes", "unchecked"})
    static List legacyValues() {
        List values = new ArrayList();
        values.add("Linh");
        return values;
    }

    public static void main(String[] args) {
        System.out.println(legacyValues().get(0));
    }
}
~~~

The annotation on the method tells the compiler to ignore rawtypes and unchecked warnings within the scope of that method. It does not make the code safer and is not a substitute for understanding why the warning occurs.

Usage principles:

1. Prefer fixing the root cause, such as adding generic types instead of suppressing.
2. If suppression is unavoidable, place the annotation at the smallest possible scope.
3. Only list the categories that actually need to be suppressed; do not suppress all warnings.
4. Write a comment explaining why the operation cannot be avoided and what safety conditions are guaranteed.
5. Re-check when upgrading APIs or changing code structure.

Example with an intentional unchecked conversion:

~~~java
@SuppressWarnings("unchecked")
static <T> T castLegacyValue(Object value) {
    return (T) value;
}
~~~

This is only an illustration of annotation placement. The cast can still throw ClassCastException if the actual type is incompatible. The caller must ensure the data type contract; the annotation only disables the compiler warning at the marked scope.

Do not place @SuppressWarnings("unchecked") at the entire package or project level just to get the build to pass. Doing so hides new warnings and makes root causes harder to find.

## 8. Other warnings and how to handle them

### Deprecated API

When an API is marked deprecated, the compiler can warn that the source code is using an old API. That API may still work, but developers should look for the documented replacement.

~~~bash
javac -Xlint:deprecation OldClient.java
~~~

If the API is also marked for removal, you can additionally enable:

~~~bash
javac -Xlint:removal OldClient.java
~~~

Do not suppress the warning just for a clean build output. Check the API's Javadoc, the replacement version, and the scheduled removal timeline.

### Serializable and serialVersionUID

A class implementing Serializable should generally declare serialVersionUID explicitly to control serialization compatibility across class versions.

~~~java
import java.io.Serializable;

public class UserRecord implements Serializable {
    private static final long serialVersionUID = 1L;

    private final String name;

    public UserRecord(String name) {
        this.name = name;
    }
}
~~~

Use the serial lint category to check serialization warnings:

~~~bash
javac -Xlint:serial UserRecord.java
~~~

The serialVersionUID value must be managed according to the application's data compatibility strategy; do not copy an arbitrary value without considering class structure changes.

### Switch fall-through

A traditional switch can fall through to the next case if there is no break or appropriate terminating statement. If this is intentional, make the intent clear with a comment or an appropriate switch structure.

~~~java
public class SwitchDemo {
    public static void main(String[] args) {
        int day = 6;

        switch (day) {
            case 6:
            case 7:
                System.out.println("Weekend");
                break;
            default:
                System.out.println("Weekday");
        }
    }
}
~~~

The two labels case 6 and case 7 execute the same branch. This is valid case grouping, not an accidental fall-through bug. If a case has its own processing and then lets execution fall through to another case, inspect it carefully and use break, return, or an appropriate switch expression structure.

## 9. Adding lint to Maven

For Maven projects, you can configure the Maven Compiler Plugin to pass options to javac:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <showWarnings>true</showWarnings>
        <compilerArgs>
            <arg>-Xlint:all</arg>
            <arg>-Werror</arg>
        </compilerArgs>
    </configuration>
</plugin>
~~~

Place the configuration inside the build/plugins section of pom.xml. Plugin versions and release/toolchain configurations need to be managed separately according to project standards. When Maven runs, the compiler plugin passes compilerArgs to javac when using the corresponding compiler mechanism.

You can run the build:

~~~bash
mvn clean compile
~~~

If warnings are enabled and -Werror is applied, warnings can cause the compile goal to fail. Check the Maven log to distinguish between javac warnings, plugin warnings, and errors in other goals.

## 10. Adding lint to Gradle

With Gradle Groovy DSL, configure JavaCompile tasks in build.gradle:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-Xlint:all', '-Werror']
}
~~~

If the project has multiple source sets or modules, the configuration above applies to the corresponding Java compilation tasks. You can test the task with:

~~~bash
./gradlew compileJava
~~~

On Windows:

~~~powershell
.\gradlew.bat compileJava
~~~

Make sure Gradle runs with a JDK compatible with the project's Gradle version. Toolchains can select a separate compilation JDK; selecting a toolchain and enabling lint are two separate configurations.

## 11. Strategy for adopting lint in teams and CI

A practical process can be rolled out step by step:

1. **Check the JDK:** standardize the JDK version used across developer machines and CI, because categories and warning messages can change across compiler versions.
2. **Enable lint:** start with -Xlint:all or the categories important to the project.
3. **Collect warnings:** categorize warnings by severity, package, module, or owner.
4. **Fix root causes:** prioritize type safety, newer APIs, resource management, and clear control flow.
5. **Suppress with control:** only use suppression when there is a technical reason and a narrow scope.
6. **Enable -Werror:** once the baseline is clean enough, let new warnings fail CI.
7. **Maintain:** treat warnings as part of code reviews and re-check when upgrading the JDK.

A new warning appearing after a JDK upgrade is not necessarily caused by recently changed source code. A newer compiler may add categories or improve detection. Read the warning message, identify the relevant API/construct, and check the JDK release notes before deciding to fix or suppress.

Do not arbitrarily add -Werror to a module without checking dependent modules, annotation processors, or generated sources. Auto-generated source code can also produce warnings. Identify whether warnings come from team-written code, generated code, or external tools, and choose an appropriate handling approach.

## 12. Common errors and misconceptions

| Misconception or symptom | Explanation and how to handle it |
|---|---|
| Enabled -Xlint but no warnings appear. | The code may not trigger the enabled categories, or the compiler does not detect that issue. Use -Xlint:all and test with an example that has a warning. |
| -Xlint causes the build to fail. | Usually caused by combining -Werror or a build tool configuring warnings as errors. Check all compilerArgs. |
| Used -Xlint:unchecked but did not see raw type warnings. | rawtypes is a separate category. Use -Xlint:rawtypes,unchecked or -Xlint:all. |
| SuppressWarnings makes code safer. | The annotation only hides the warning; it does not add runtime checks or guarantee type safety. |
| Warnings disappear after a JDK upgrade. | The compiler may have changed categories or detection behavior. Verify the version and current lint list. |
| Legacy build fails immediately after adding -Werror. | The codebase may already have pre-existing warnings. Collect and clean up the baseline before enforcing strict rules. |
| IDE does not show the same warnings as CI. | The IDE may use its own compiler, JDK, or inspections. Verify the official build using javac/Maven/Gradle in CI. |

## 13. Checklist before enforcing lint

- Identify the JDK and compiler version being used.
- Use javac --help-lint to view supported categories.
- Enable -Xlint:all or select appropriate categories.
- Review warnings printed to standard error and locate the relevant files/lines.
- Fix warnings by improving source code before suppressing.
- If suppression is needed, use specific categories and a narrow scope.
- Run a clean build after fixing.
- Only enable -Werror once baseline warnings have been resolved or there is a clear acceptance process.
- Ensure IDE, Maven/Gradle, and CI use compatible configurations.
- Re-check warnings after every JDK or annotation processor upgrade.

Lint turns javac into a quality-check layer right during compilation. Enabling the right categories helps catch error-prone code early, while -Werror turns that standard into an enforceable build rule. Combined with explicit generic types, controlled suppression, and consistent configuration between IDEs and CI, teams can maintain safer and more maintainable Java code.
