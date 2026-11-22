# Reading Scan Results with jdeprscan

**jdeprscan** is a tool in the JDK used to find compiled classes that reference Java APIs marked as deprecated. When running a scan, the tool identifies which deprecated methods, constructors, or fields from a specific Java SE release API are being used by the application's classes.

The output typically looks like this:

~~~text
class LegacyApiUse uses deprecated method java/util/Date::getYear()I
class LegacyApiUse uses deprecated method java/lang/Thread::stop()V (forRemoval=true)
~~~

Each line indicates the **application class**, the **referenced deprecated API**, and, if applicable, the **forRemoval=true** status. This provides the input needed to determine the scope of impact, prioritize upgrades, and find API replacements.

Basic scan command:

~~~bash
jdeprscan --release 17 build/classes
~~~

The command above checks classes in build/classes against the deprecated API list of Java 17. The --release option is crucial: the same API might be marked as deprecated for removal in a newer release while not carrying that status in an older release.

## 1. What Questions Do jdeprscan Results Answer?

jdeprscan analyzes bytecode to find references to deprecated APIs. The results help answer:

- Which classes in the application are using deprecated APIs?
- Which class or package does the called API belong to?
- Is it a method, constructor, or field?
- Is the API marked for removal in the selected release?
- Which API can replace it?
- Which parts should be prioritized for fixing before upgrading the JDK?

The tool reads compiled class files, class directories, or JARs. It does not analyze Java source code like a typical source linter, and it does not run the application.

Example:

~~~java
import java.util.Date;

public final class LegacyApiUse {
    public static int year(Date date) {
        return date.getYear();
    }
}
~~~

The Date.getYear() method is deprecated. After compiling, jdeprscan can detect that the LegacyApiUse class references that method.

A finding in the output does not by itself mean the application fails at runtime. Deprecated APIs can still work in the current release. The result warns that the API has been marked as discouraged for continued use and may be removed in the future if marked for removal.

## 2. Structure of a Result Line

Example:

~~~text
class LegacyApiUse uses deprecated method java/util/Date::getYear()I
~~~

It can be broken down into parts:

| Part | Meaning |
|---|---|
| class | This line represents a class using a deprecated API |
| LegacyApiUse | The application-side class containing the reference |
| uses deprecated method | Finding type: uses a deprecated method |
| java/util/Date | The class owning the deprecated API |
| getYear | The name of the method being used |
| ()I | JVM method descriptor: no parameters, returns int |

### Caller class

The name immediately following the word class is the class containing the reference to the deprecated API. In the example, LegacyApiUse is the caller.

If the output has multiple callers:

~~~text
class com.example.report.ReportService uses deprecated method java/util/Date::getYear()I
class com.example.importer.LegacyReader uses deprecated method java/util/Date::getYear()I
~~~

then both ReportService and LegacyReader need to be reviewed. You should not fix one caller and conclude that the entire application is clean.

### Owner of the deprecated API

The class name after uses deprecated method is where the member is declared. In the example, java/util/Date is the owner.

Class names are written in JVM internal form, using forward slashes between packages instead of dots:

~~~text
java/util/Date
java/lang/Thread
java/io/File
~~~

When searching in Javadoc or source code, convert them to standard fully qualified names:

~~~text
java.util.Date
java.lang.Thread
java.io.File
~~~

### Member name

After the double colon is the member name. For example:

~~~text
java/util/Date::getYear()I
java/lang/Thread::stop()V
~~~

getYear and stop are the referenced methods. The output can also indicate a constructor or field depending on the type of deprecated API.

## 3. Reading JVM Method Descriptors

The part in parentheses after the method name is the JVM descriptor. It describes the parameter types and return type in bytecode format.

Examples:

~~~text
getYear()I
stop()V
substring(I)Ljava/lang/String;
valueOf(I)Ljava/lang/String;
~~~

Some basic symbols:

| Symbol | Java Type |
|---|---|
| V | void |
| Z | boolean |
| B | byte |
| C | char |
| S | short |
| I | int |
| J | long |
| F | float |
| D | double |
| Lpackage/Type; | Reference type |
| [T | Array of type T |

How to read them:

- getYear()I: takes no parameters, returns int.
- stop()V: takes no parameters, returns void.
- substring(I)Ljava/lang/String;: takes one int, returns String.
- valueOf(I)Ljava/lang/String;: takes one int, returns String.

With multiple parameters, the descriptors are concatenated consecutively inside the parentheses:

~~~text
replace(CC)Ljava/lang/String;
~~~

This example takes two char parameters and returns String.

Descriptors are useful when a class has multiple overloads with the same name. A method name alone may not be enough to identify the overload; the descriptor indicates the exact signature referenced by the bytecode.

## 4. Meaning of forRemoval=true

Some deprecated APIs are explicitly marked as being considered for removal from the Java platform. In the annotation, this status is represented by the forRemoval=true attribute.

Example output:

~~~text
class LegacyApiUse uses deprecated method java/lang/Thread::stop()V (forRemoval=true)
~~~

This line means:

- LegacyApiUse is referencing Thread.stop().
- The method is deprecated in the selected release.
- The API is marked as deprecated for removal in that release.
- This usage should be prioritized for remediation because the API may be removed in a future release.

forRemoval=true does not specify the exact Java version in which the API will be deleted. It is a signal of intent to remove, not a committed removal schedule.

If a result line does not have the forRemoval=true marker, it only means the API is not marked for removal in the release dataset being used. The API may still be deprecated and still need to be replaced according to plan.

### Why care about the release?

An API's deprecation status can change over time. An API may:

1. Not be deprecated yet in an older release.
2. Become deprecated in a subsequent release.
3. Later be marked for removal.
4. Potentially be removed in a future release.

Therefore, when reading scan results, always record the release used for the analysis.

## 5. How --release Changes Result Interpretation

The --release option specifies the Java SE release that provides the deprecated API set to check against.

~~~bash
jdeprscan --release 17 build/classes
~~~

The command above uses the deprecated API set of Java 17.

~~~bash
jdeprscan --release 24 build/classes
~~~

The command above uses the deprecated API set of Java 24.

This option **does not recompile classes**, does not modify bytecode, and does not automatically verify whether class files are compatible with that release. It selects the deprecated API dataset that jdeprscan uses for comparison.

### Example verified on JDK 24.0.2

A class compiled with --release 17 uses Date.getYear() and Thread.stop(). When scanned against Java 17, the output is:

~~~text
class LegacyApiUse uses deprecated method java/util/Date::getYear()I
class LegacyApiUse uses deprecated method java/lang/Thread::stop()V
~~~

When scanning the same class against Java 24:

~~~text
class LegacyApiUse uses deprecated method java/util/Date::getYear()I
class LegacyApiUse uses deprecated method java/lang/Thread::stop()V (forRemoval=true)
~~~

We can see that Thread.stop() is marked forRemoval=true in the Java 24 API set, but does not have that marker in the Java 17 API set.

This is why you should not read a scan result while ignoring the release. A report without the forRemoval=true marker does not prove the API will not be removed; it only reflects the metadata of the selected release.

### Which release should you choose?

- Choose the release the application currently supports to find deprecated APIs against the current baseline.
- Choose the JDK release you plan to upgrade to in order to see warnings for the future target.
- If preparing for a multi-step upgrade, scan against each target release in sequence.
- Record the release and tool version alongside the report so results are reproducible.

JDK 24.0.2 lists --release values from 8 to 24. The list of supported releases varies by jdeprscan version; check --help of the JDK you are using rather than assuming every JDK supports the same range.

## 6. --for-removal: Viewing Only APIs at Risk of Removal

The option:

~~~bash
jdeprscan --for-removal build/classes
~~~

retains only APIs marked as deprecated for removal in the API set the tool is using.

Combined with a specific release:

~~~bash
jdeprscan --release 24 --for-removal build/classes
~~~

In the LegacyApiUse example, the output only contains Thread.stop():

~~~text
class LegacyApiUse uses deprecated method java/lang/Thread::stop()V (forRemoval=true)
~~~

Date.getYear() is still deprecated, but it is not marked for removal in that API set, so it is filtered out of the output.

This is a useful way to prioritize tasks:

- Run a normal scan to get all deprecated APIs.
- Run an additional --for-removal scan to create a high-priority list.
- Do not ignore regular deprecated APIs; they still need to be evaluated and replaced.
- Track for-removal APIs separately in the JDK upgrade plan.

According to JDK 24 help, --for-removal cannot be combined with --release 6, 7, or 8. Check the corresponding restrictions in the tool version you are using.

## 7. --list: Looking Up the Deprecated API List

You can use jdeprscan to view the deprecated API set of a release without scanning any classes.

~~~bash
jdeprscan --list
~~~

This command lists the deprecated APIs of the default release (the running JDK).

List only for-removal APIs:

~~~bash
jdeprscan --list --for-removal
~~~

Look up against Java 17:

~~~bash
jdeprscan --list --release 17
~~~

Note: --list only lists the APIs and does not perform a scan. Do not pass directories, JARs, or classes as scan arguments in this same mode.

The output of --list typically provides API signatures and annotation metadata. Examples observed on JDK 24:

~~~text
@Deprecated(since="1.2", forRemoval=true) void java.lang.Thread.stop()
@Deprecated(since="9", forRemoval=true) void java.lang.Object.finalize()
@Deprecated int java.util.Date.getYear()
~~~

When using --list --release 17, Thread.stop() and Object.finalize() appear as deprecated but without forRemoval=true in that release's metadata. Date.getYear() is also deprecated.

This list helps look up API status and deprecation time (since) when deciding on a replacement direction. It does not by itself tell you which classes in your application are calling the API; you need to scan artifacts to find callers.

## 8. Reading Headers and Grouping Results

When scanning a directory, jdeprscan may print a header:

~~~text
Directory C:\work\app\classes:
class LegacyApiUse uses deprecated method java/util/Date::getYear()I
~~~

The header indicates the target being scanned. The following lines are findings within that target.

When scanning a JAR, the header may indicate the archive being processed. When passing multiple inputs, read each header to know which directory or JAR a finding belongs to.

If multiple classes use the same API, the output may contain multiple lines. When aggregating reports:

- Group by deprecated API to see which APIs are used in many places.
- Group by caller class to identify which modules or packages need fixing.
- Preserve the release used during the scan.
- Preserve the forRemoval=true marker in the aggregated data.
- Do not merge overloads with different descriptors into a single finding if exact tracing is needed.

One API can appear in multiple callers. One caller can also use multiple deprecated APIs. This is a many-to-many relationship.

## 9. Scanning Directories, Class Files, and JARs

General syntax:

~~~bash
jdeprscan [options] {dir|jar|class} ...
~~~

Input types:

- A directory is the root of a package hierarchy containing class files.
- A JAR is an archive to be analyzed.
- A class file is a specific .class file.
- A class name is the fully qualified name of a class; nested classes use $ as a separator.

Example of scanning a directory:

~~~bash
jdeprscan --release 17 build/classes
~~~

Scanning a single class file:

~~~bash
jdeprscan --release 17 build/classes/com/example/LegacyApiUse.class
~~~

Scanning a JAR:

~~~bash
jdeprscan --release 17 build/libs/application.jar
~~~

Scanning a nested class by class name:

~~~bash
jdeprscan --release 17 'com.example.Outer$Nested'
~~~

When using a class name instead of a file path, the class name must be fully qualified. The $ sign in nested class names must be preserved; in a shell, it can be enclosed in quotes to avoid special processing.

### Scanning multiple artifacts

Multiple inputs can be passed:

~~~bash
jdeprscan --release 17 \
    build/libs/application.jar \
    build/libs/legacy-adapter.jar \
    build/classes
~~~

This helps audit multiple parts of a product in one pass. However, pay attention to scope: jdeprscan scans the passed inputs. Having a JAR on the classpath for dependency resolution does not mean that JAR automatically becomes a scan target.

## 10. Classpath for Dependency Resolution

The --class-path option specifies where to find dependent classes when jdeprscan needs to resolve references.

Example:

~~~bash
jdeprscan \
    --release 17 \
    --class-path "lib/common.jar;lib/vendor.jar" \
    build/classes
~~~

On Windows, the classpath separator is a semicolon. On Linux/macOS, use a colon:

~~~bash
jdeprscan \
    --release 17 \
    --class-path "lib/common.jar:lib/vendor.jar" \
    build/classes
~~~

The classpath helps the tool find classes that the inputs reference. It is not a list of artifacts to be scanned.

If you want to scan both application.jar and vendor.jar, pass both as inputs:

~~~bash
jdeprscan --release 17 \
    --class-path lib/common.jar \
    application.jar \
    vendor.jar
~~~

If a dependency class is not found, the scan results may be incomplete or the tool may report a resolution error. Add the correct JAR and run again.

In JDK 24 help, jdeprscan has the --class-path option but does not list --module-path. Do not infer module path syntax from other tools like jdeps or javac. Check --help for the exact JDK when working with modular artifacts and ensure all dependencies needed for resolution are available via mechanisms supported by that jdeprscan version.

## 11. --verbose and Other Display Options

The --verbose or -v option enables additional information during processing:

~~~bash
jdeprscan --verbose --release 17 build/classes
~~~

Verbose is useful when you need to diagnose how the tool processes inputs. However, do not assume it will add source line numbers for every finding. The main output of jdeprscan identifies the caller class and deprecated API, but usually does not give the exact source line.

Version options:

~~~bash
jdeprscan --version
jdeprscan --full-version
~~~

--version prints the short version; --full-version prints the full version string of the tool.

Before writing CI scripts, check the help:

~~~bash
jdeprscan --help
~~~

Specifically check the release range and available options on the build agent's JDK.

## 12. From Finding to Source Location to Fix

jdeprscan typically reports the caller class and API, not the Java file and line number. To find the call site in source code:

1. Read the caller class in the output.
2. Locate the corresponding source file by package and class name.
3. Search for the reported method or field.
4. If there are multiple overloads, match against the descriptor.
5. If source is unavailable, use javap to inspect bytecode and identify the method containing the reference.
6. Also check auto-generated code or internal dependencies.

Example output:

~~~text
class com.example.legacy.DateAdapter uses deprecated method java/util/Date::getYear()I
~~~

You can search in source:

~~~bash
rg "getYear" src
~~~

The rg command is an external source search tool outside the JDK; if unavailable, use your IDE search or grep.

If source is unavailable or the method name is not enough to identify the overload, inspect the bytecode:

~~~bash
javap -classpath build/classes -c -p com.example.legacy.DateAdapter
~~~

javap -c displays bytecode; -p also displays non-public members. Find the instruction calling the corresponding method, then trace back to the source method if debug information is present.

Do not claim source line numbers solely from jdeprscan output if the tool does not provide that location.

## 13. Handling Findings: From Old API to Replacement API

A finding is the starting point of the remediation process, not an automatic instruction. You need to read the API documentation and understand the code semantics before replacing it.

### Date.getYear()

Finding:

~~~text
java/util/Date::getYear()I
~~~

Date.getYear() returns the year minus 1900 and depends on the default time zone. When replacing it with java.time, choose an explicit time zone to preserve the correct business meaning.

Example converting to the year in the system default zone:

~~~java
import java.time.ZoneId;
import java.util.Date;

int year = date.toInstant()
        .atZone(ZoneId.systemDefault())
        .getYear();
~~~

If business logic requires a fixed time zone, replace ZoneId.systemDefault() with a specific ZoneId. Do not mechanically replace it with LocalDate.now() because that is the current date, not the date held in the Date object.

### Thread.stop()

Finding:

~~~text
java/lang/Thread::stop()V (forRemoval=true)
~~~

Thread.stop() can stop a thread abruptly, leaving objects in an inconsistent state. The usual replacement is a cooperative stopping mechanism: using interruption, a status flag, or a cancellation token.

Example:

~~~java
public final class Worker implements Runnable {
    @Override
    public void run() {
        while (!Thread.currentThread().isInterrupted()) {
            doOneUnitOfWork();
        }
    }

    private void doOneUnitOfWork() {
        // Perform one bounded unit of work.
    }
}
~~~

Management code requesting shutdown:

~~~java
Thread worker = new Thread(new Worker());
worker.start();

// Request cooperative shutdown.
worker.interrupt();
~~~

If the worker is waiting in a blocking operation that can throw InterruptedException, handle interruption properly and preserve the interrupt status when needed. Do not use interrupt as a forced immediate stop command; the worker needs a chance to clean up resources.

### Object.finalize()

If a finding points to finalize(), move resource cleanup logic to an explicit mechanism such as AutoCloseable and try-with-resources. Do not rely on when the garbage collector runs to close files, sockets, or handles.

Example:

~~~java
try (var input = java.nio.file.Files.newInputStream(path)) {
    // Read data.
}
~~~

Closing resources deterministically by lexical scope makes code easier to test and independent of finalization.

## 14. Prioritizing and Classifying Scan Results

A useful report should classify results across multiple dimensions.

### By deprecation status

- Regular deprecated: needs evaluation and a replacement plan.
- Deprecated for removal: higher priority because the API is marked as potentially being removed.
- API only deprecated in newer releases: may not affect the current baseline, but impacts upgrade targets.

### By caller location

- Code owned by the development team: can be fixed directly.
- Internal dependencies: update the relevant module or library.
- Third-party dependencies: look for a newer version or contact the vendor.
- Auto-generated code: update the generator or template, not just the output files.

### By impact level

Evaluate further:

- Is the API on the main execution path?
- Is it called frequently?
- Is it part of a library's public API?
- Does it affect binary compatibility?
- Is there an equivalent replacement?
- Does it require changing behavior or timezone/concurrency semantics?

Do not just count warning lines. One forRemoval finding on the main execution path can be more critical than many deprecated findings in a rarely used internal tool.

## 15. Distinguishing Deprecated APIs from Removed APIs

jdeprscan finds deprecated APIs according to the selected release's API set. It is not a general tool to prove that all references are compatible with another JDK.

Cases to distinguish:

- **Deprecated:** The API still exists, but its use is discouraged.
- **Deprecated for removal:** The API still exists in the analyzed release, but is marked as potentially being removed.
- **Removed:** The API no longer exists in the newer release; classes may encounter compile or linkage errors if they still reference it.
- **Missing dependency:** A class cannot be found when the tool resolves dependencies; this is not synonymous with a deprecated API.

If the application needs a JDK upgrade, combine jdeprscan with compiling using the appropriate --release, testing on the target runtime, and checking dependencies. Do not use a single deprecation scan as complete proof of binary compatibility.

## 16. Complete Hands-on Example for Java 17+

The following example creates a class with two deprecated references to illustrate how to read the results.

Structure:

~~~text
jdeprscan-demo/
├── src/
│   └── LegacyApiUse.java
└── build/
    └── classes/
~~~

### LegacyApiUse.java

~~~java
import java.util.Date;

public final class LegacyApiUse {

    private LegacyApiUse() {
    }

    public static int legacyYear(Date date) {
        return date.getYear();
    }

    public static void legacyStop(Thread thread) {
        thread.stop();
    }

    public static void main(String[] args) {
        System.out.println("jdeprscan demo ready.");
    }
}
~~~

### Compiling

~~~bash
mkdir -p build/classes

javac --release 17 \
    -Xlint:deprecation \
    -d build/classes \
    src/LegacyApiUse.java
~~~

The compiler may print deprecation warnings for getYear() and stop(). These are warnings from javac; they differ from jdeprscan output.

### Running the program

~~~bash
java -cp build/classes LegacyApiUse
~~~

Output:

~~~text
jdeprscan demo ready.
~~~

Main does not call the two deprecated methods, so the example can run without executing the thread-stopping operation.

### Scanning against Java 17

~~~bash
jdeprscan --release 17 build/classes
~~~

Output verified on JDK 24.0.2:

~~~text
Directory ...\build\classes:
class LegacyApiUse uses deprecated method java/util/Date::getYear()I
class LegacyApiUse uses deprecated method java/lang/Thread::stop()V
~~~

The ... represents the actual directory path. The result shows that LegacyApiUse contains two deprecated references. In the Java 17 API set, Thread.stop() does not carry the forRemoval=true marker yet.

### Scanning against Java 24

~~~bash
jdeprscan --release 24 build/classes
~~~

Output:

~~~text
Directory ...\build\classes:
class LegacyApiUse uses deprecated method java/util/Date::getYear()I
class LegacyApiUse uses deprecated method java/lang/Thread::stop()V (forRemoval=true)
~~~

### Viewing only for-removal APIs

~~~bash
jdeprscan --release 24 --for-removal build/classes
~~~

Output:

~~~text
Directory ...\build\classes:
class LegacyApiUse uses deprecated method java/lang/Thread::stop()V (forRemoval=true)
~~~

Date.getYear() no longer appears because that API is not marked for removal in the Java 24 set. This illustrates using --for-removal to filter a priority list.

### Packaging and scanning a JAR

~~~bash
jar --create \
    --file build/legacy-api-use.jar \
    -C build/classes .

jdeprscan --release 24 build/legacy-api-use.jar
~~~

The deprecated API results are similar to scanning the class directory. The header will indicate the analyzed archive instead of the directory.

## 17. Integrating jdeprscan into CI

jdeprscan can serve as an audit step in a JDK upgrade pipeline:

1. Compile all modules/artifacts.
2. Scan class directories or JARs of team-owned code.
3. Run against the current release.
4. Run against the target release.
5. Run --for-removal to generate a priority list.
6. Classify findings by caller and API.
7. Save the report along with the JDK version and commands used.
8. Fix code or update dependencies.
9. Re-scan and compare results.

Example:

~~~bash
jdeprscan --release 17 build/classes
jdeprscan --release 24 build/classes
jdeprscan --release 24 --for-removal build/classes
~~~

In CI, you need to decide on your own policy:

- Report findings only, or fail the build?
- Block new forRemoval findings?
- Allow a baseline of old findings during migration?
- Scan third-party dependencies or only internal code?
- Who is responsible for addressing findings in each module?

Do not assume that every finding causes jdeprscan to return a non-zero exit code. The tool may print findings and still exit normally; a pipeline that wants to fail based on policy needs to parse the output or use a separate check step.

Additional note: findings in a dependency JAR need to be scanned by passing that JAR as an input. Simply adding it to --class-path for resolution does not mean all code inside the JAR has been audited.

## 18. Limitations of jdeprscan

jdeprscan performs static bytecode analysis. It may miss or be unable to conclude about:

- APIs called via reflection with class/member names obtained from strings.
- Classes loaded dynamically from plugins or external configurations.
- Dependencies loaded after application startup.
- Behavior of native code.
- APIs used in source code that have not been compiled into the scanned artifacts.
- Artifacts not passed as input.
- Any binary compatibility issues or semantic changes.

A scan with no findings does not mean the application is guaranteed to be compatible with every Java release. It only states that the tool found no deprecated references within the scope of the provided inputs and selected API release.

For a more reliable audit, scan all application-owned artifacts, provide the necessary dependency classpath, check plugins/configurations, and run tests on the target runtime.

## 19. Checklist for Reading and Handling a Report

For each finding line, confirm:

- [ ] The release used for the scan has been recorded.
- [ ] The caller class has been identified.
- [ ] The owner class and deprecated member have been identified.
- [ ] The descriptor has been decoded if overloads exist.
- [ ] The forRemoval=true marker has been preserved if present.
- [ ] The API has been looked up in the Javadoc of the exact release.
- [ ] Source or bytecode has been traced to the usage site.
- [ ] Classified as internal code, auto-generated code, or third-party dependency.
- [ ] Semantics of the replacement API have been evaluated.
- [ ] Tests have been run after fixing.
- [ ] Re-scanned against the target release.
- [ ] Report and tool version saved for future comparison.

## 20. Command Workflow to Remember

~~~bash
# Version and options
jdeprscan --version
jdeprscan --help

# List deprecated APIs
jdeprscan --list
jdeprscan --list --for-removal
jdeprscan --list --release 17

# Scan compiled classes
jdeprscan --release 17 build/classes

# Scan a JAR
jdeprscan --release 24 build/libs/application.jar

# Scan only APIs for removal
jdeprscan --release 24 --for-removal build/classes

# Resolve dependent classes
jdeprscan --class-path "lib/common.jar" build/classes

# Additional processing messages
jdeprscan --verbose --release 24 build/classes
~~~

When reading output, start with the release, identify the caller class, decode the owner/member/descriptor, and check for the forRemoval=true marker. Then trace the source, evaluate replacement APIs, and re-scan. This approach turns a list of deprecations into a concrete upgrade plan, rather than just a set of hard-to-handle warnings.

## References

- [The jdeprscan Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdeprscan.html)
- [Deprecated API — Java Platform, Standard Edition 24](https://docs.oracle.com/en/java/javase/24/docs/api/deprecated-list.html)
- [The javap Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javap.html)
- [JEP 277: Enhanced Deprecation](https://openjdk.org/jeps/277)
