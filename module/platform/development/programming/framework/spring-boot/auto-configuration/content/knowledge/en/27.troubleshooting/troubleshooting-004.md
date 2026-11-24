# NoSuchMethodError Due to Incompatible Library Versions

## 1. Understand the Error Before Changing Dependencies

`java.lang.NoSuchMethodError` is a runtime linkage error. The JVM is executing bytecode that invokes a method by a specific name and descriptor, yet the actually loaded class lacks a matching method.

The message typically looks like:

~~~text
Exception in thread "main" java.lang.NoSuchMethodError:
  'java.lang.String com.example.api.TextFormatter.format(java.lang.String, java.util.Locale)'
~~~

Read the message in three parts:

- `com.example.api.TextFormatter` is the class where the JVM is looking up the method.
- `format` is the method name.
- The parameter types and return type specify the bytecode signature requested by the caller.

A classic error happens when an application or a dependent library is compiled against a newer API version where the method exists, yet at runtime the JVM loads an older version of the class where that method did not exist yet or was changed.

For example:

- At compile time: `text-api:2.0` has `format(String, Locale)`.
- At runtime: the classpath contains only `text-api:1.0`, which only has `format(String)`.
- The caller still contains the call to `format(String, Locale)`.
- The JVM cannot find a method with the required descriptor and throws `NoSuchMethodError`.

This is a binary compatibility error. Source code may have compiled cleanly because the compiler saw the new API, while runtime loaded a different class definition.

### 1.1. Why Did the Compiler Not Catch It?

During compilation, the compiler checks classes and methods on the compile classpath. It records method calls into bytecode. At runtime, the JVM must link those calls to classes loaded from the actual runtime classpath or classloader.

If the two sets of classes differ, the compiler may accept calls that runtime cannot link.

Model:

~~~text
Compile time
  Application source
       |
       v
  API library 2.0
  has format(String, Locale)
       |
       v
  Application bytecode
  invokes format(String, Locale)

Runtime
  Application bytecode
       |
       v
  ClassLoader loads API library 1.0
  has format(String) only
       |
       v
  NoSuchMethodError
~~~

The divergence can come from transitive dependencies, version conflicts, stale JARs remaining in a deployment directory, an application server providing its own libraries, shaded JARs, or a classloader loading classes from an unexpected source.

### 1.2. What Is a Method Descriptor?

At the Java source level, a method is typically identified by its name and parameter type list. At the JVM bytecode level, a symbolic method reference contains:

- The name of the class/interface owning the method.
- The method name.
- The method descriptor.

The descriptor includes parameter types **and the return type**. For example:

~~~text
format(String, Locale): String
(Ljava/lang/String;Ljava/util/Locale;)Ljava/lang/String;
~~~

Therefore, changing parameter types, return type, or the owning class/interface can prevent old bytecode from linking to the new API. Adding a new overload also fails to help an older caller if runtime loads a version that lacks that overload.

Common situations causing this error:

| API change | Possible consequence |
|---|---|
| Removing or renaming a method | Older caller still invokes a method that no longer exists |
| Changing parameter types | Old descriptor no longer matches |
| Changing return type | Bytecode descriptor changes |
| Moving a method to another class/interface | Caller references the old owner |
| Adding an overload while runtime uses an older version | Caller invokes an overload missing from the runtime version |
| Loading the wrong version of a class with the same FQCN | Runtime API differs from compile-time API |

Not every method change produces `NoSuchMethodError` specifically. Changing between static and instance, or altering class/interface relationships, can lead to `IncompatibleClassChangeError`; an abstract method lacking a compatible implementation can lead to `AbstractMethodError`.

## 2. Distinguishing Easily Confused Errors

Similar error names have different causes and fixes:

| Error | Meaning | First investigation step |
|---|---|---|
| `NoSuchMethodError` | Bytecode calls a method missing from the loaded class | Compare method descriptors between compile-time and runtime classes |
| `NoSuchMethodException` | Code uses reflection to look up a method and cannot find it | Check `getMethod`/`getDeclaredMethod`, name, and parameter types |
| `NoClassDefFoundError` | JVM needs a class but cannot load/define it | Check missing JAR, class initialization failure, or classloader |
| `ClassNotFoundException` | An explicit class-loading call cannot find the class | Check classpath and the classloader calling `Class.forName` |
| `AbstractMethodError` | Runtime invokes an abstract method, but the loaded implementation lacks a compatible implementation | Check interface and implementation versions |
| `NoSuchFieldError` | Bytecode references a field that no longer exists | Compare fields in caller and runtime class |
| `IncompatibleClassChangeError` | Class structure changed incompatibly with how caller uses it | Check class/interface, static/instance, and hierarchy |

Do not fix `NoSuchMethodError` by catching and ignoring the exception. This is a `LinkageError`, usually indicating that the running bytecode and libraries do not share the same API contract. Swallowing it can leave the application running with missing behavior or corrupt data.

## 3. Common Causes

### 3.1. Transitive Dependency Pulling an Older Version

An application declares libraries A and B. A requires API C in a newer version; B requires an older API C. The build tool resolves the conflict and selects one version of C. If the chosen version is not binary-compatible with the caller, the error surfaces at runtime.

Example graph:

~~~text
application
  |-- report-client 4.0
  |      |-- text-api 2.0
  |
  |-- legacy-exporter 1.5
         |-- text-api 1.0

Resolved runtime:
  text-api 1.0
~~~

The dependency tree must be inspected to see what requests each version and why the build tool chose the final one.

### 3.2. Compile Classpath Differs from Runtime Classpath

Some build configurations separate dependencies by scope:

- Maven: `compile`, `provided`, `runtime`, `test`.
- Gradle: `compileClasspath`, `runtimeClasspath`, `testCompileClasspath`, `testRuntimeClasspath`, `compileOnly`, `runtimeOnly`.

An application may compile against one version yet package or deploy with another. For example, a `provided` dependency is supplied by an application server; the server-provided version may be older than the API the application compiled against.

### 3.3. Duplicate Class JARs or a Library Packaged Twice

An application can contain two different JARs declaring the same class:

~~~text
lib/
  text-api-1.0.jar
  text-api-2.0.jar
~~~

Classpath order or classloader rules decide which class gets loaded. Looking only at dependency names in a POM/Gradle file is not enough to know which JAR a class actually comes from.

This situation also occurs when:

- A JAR is manually copied into `lib/` alongside dependencies managed by Maven/Gradle.
- A fat JAR/shaded JAR contains an old copied class.
- A WAR has libraries in `WEB-INF/lib` while the server provides libraries with the same classes.
- A Docker image was not rebuilt after updating dependencies.
- A plugin module or application server uses a separate classloader.

### 3.4. Version Overridden Outside the BOM

Spring Boot tests each release with a curated set of library versions. If an application individually overrides Spring Framework, Jackson, Hibernate, logging, or a foundational library without checking compatibility, modules may become out of sync.

For instance, upgrading `spring-core` while leaving `spring-context` on an older version can create an inconsistent Spring Framework set. Similarly, overriding a foundational library used by multiple starters can cause callers and implementations to diverge on APIs.

### 3.5. Runtime Is Not the Newly Built Artifact

Some cases do not stem from the current dependency graph:

- CI built a new JAR, but the server is still running an old JAR.
- Two copies of the application with the same name exist in two deployment directories.
- Container uses a stale image tag or un-invalidated cache layer.
- Application server holds shared libraries in a global directory.
- Hot reload/devtools or a plugin classloader retains old classes in another classloader.

Always verify the exact file being executed and the exact class being loaded before changing versions wholesale.


## 4. Reproducing the Error with Two JAR Versions

The short example below demonstrates how the exact same application bytecode runs with the new API yet fails with the old API. Use Java 17 or newer and PowerShell commands; if running on Linux/macOS, replace the `;` classpath separator with `:`.

### 4.1. Directory Structure

~~~text
nosuchmethod-demo/
├── src-v1/
│   └── demo/api/GreetingService.java
├── src-v2/
│   └── demo/api/GreetingService.java
└── src-app/
    └── demo/app/Main.java
~~~

### 4.2. API Version 1.0

File `src-v1/demo/api/GreetingService.java`:

~~~java
package demo.api;

public final class GreetingService {

    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

### 4.3. API Version 2.0

File `src-v2/demo/api/GreetingService.java`:

~~~java
package demo.api;

public final class GreetingService {

    public String greet(String name) {
        return "Hello, " + name;
    }

    public String greet(String name, String locale) {
        if ("vi".equals(locale)) {
            return "Xin chao, " + name;
        }
        return greet(name);
    }
}
~~~

Version 2.0 adds the overload `greet(String, String)`. This is the method the caller will invoke.

### 4.4. Application Calling the New API

File `src-app/demo/app/Main.java`:

~~~java
package demo.app;

import demo.api.GreetingService;

public class Main {
    public static void main(String[] args) {
        System.out.println(new GreetingService().greet("Lan", "vi"));
    }
}
~~~

### 4.5. Building Both JARs and Compiling the Application

From the demo root directory, run in PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/v1, build/v2, build/app | Out-Null

javac -d build/v1 src-v1/demo/api/GreetingService.java
jar --create --file build/greeting-v1.jar -C build/v1 .

javac -d build/v2 src-v2/demo/api/GreetingService.java
jar --create --file build/greeting-v2.jar -C build/v2 .

javac -cp build/greeting-v2.jar -d build/app src-app/demo/app/Main.java
~~~

Key point: the application is compiled against `greeting-v2.jar`. Thus, `Main`'s bytecode contains the call to `greet(String, String)`.

### 4.6. Running Against API 1.0 by Mistake

Place JAR 1.0 on the runtime classpath:

~~~powershell
java -cp "build/app;build/greeting-v1.jar" demo.app.Main
~~~

The error on JDK 17 looks like:

~~~text
Exception in thread "main" java.lang.NoSuchMethodError: 'java.lang.String demo.api.GreetingService.greet(java.lang.String, java.lang.String)'
        at demo.app.Main.main(Main.java:7)
~~~

The caller requests the two-String-parameter method. The runtime 1.0 class only has the one-parameter method, so the JVM cannot link the call.

### 4.7. Running Against API 2.0

Use the exact JAR the application compiled against:

~~~powershell
java -cp "build/app;build/greeting-v2.jar" demo.app.Main
~~~

Expected stdout:

~~~text
Xin chao, Lan
~~~

The example shows the error is not in the method-call syntax in source code. The issue is that the compiled class and the runtime-loaded class are not the same API version.


## 5. Diagnostic Workflow from Stack Trace to Actual JAR

Do not start by upgrading every dependency to the latest version. First identify the class and method the JVM failed to link, then locate the runtime class source.

### Step 1: Read the Entire Stack Trace

Record:

- The class name in the error message.
- The method name and parameter type list.
- The first frame belonging to application code or a third-party library.
- Which method calls into the failing API.
- Whether the error happens at startup, during a request, in a scheduled job, or only in tests.

If the first frame lies in a third-party library, that does not mean application code is uninvolved. The direct caller may be that library; the application simply placed an incompatible version combination on the classpath.

### Step 2: Determine Where the Runtime Class Comes From

You can print the classloader and code source of the class:

~~~java
package demo.app;

import java.security.CodeSource;

public final class ClassOrigin {

    private ClassOrigin() {
    }

    public static void print(Class<?> type) {
        System.out.println("class=" + type.getName());
        System.out.println("classLoader=" + type.getClassLoader());

        CodeSource source = type.getProtectionDomain().getCodeSource();
        System.out.println(
                "codeSource=" + (source == null ? "<unknown>" : source.getLocation())
        );
    }
}
~~~

Call the helper with the class named in the error:

~~~java
ClassOrigin.print(demo.api.GreetingService.class);
~~~

If code source returns null, the class may have been loaded from a source that does not provide a CodeSource or from a special classloader environment. Do not treat null as proof the class has no JAR; supplement with class-loading logs.

On Java 9 and newer:

~~~powershell
java -Xlog:class+load=info -cp "build/app;build/greeting-v1.jar" demo.app.Main 2>&1 | Select-String "demo.api.GreetingService"
~~~

On Java 8:

~~~powershell
java -verbose:class -cp "build/app;build/greeting-v1.jar" demo.app.Main
~~~

Class-loading logs reveal where the JVM loaded the class from. In a Spring Boot executable JAR, the path may point to a nested JAR inside the archive. In an application server, a parent classloader may supply the class ahead of libraries inside the application.

### Step 3: Compare the APIs of the Old and New JARs

Use `javap` to inspect methods and descriptors:

~~~powershell
javap -classpath build/greeting-v1.jar -p -s demo.api.GreetingService
javap -classpath build/greeting-v2.jar -p -s demo.api.GreetingService
~~~

For JAR 1.0, the relevant method section looks like:

~~~text
public java.lang.String greet(java.lang.String);
  descriptor: (Ljava/lang/String;)Ljava/lang/String;
~~~

For JAR 2.0, it also has:

~~~text
public java.lang.String greet(java.lang.String, java.lang.String);
  descriptor: (Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;
~~~

Next, inspect the caller's bytecode:

~~~powershell
javap -classpath "build/app;build/greeting-v2.jar" -c -s demo.app.Main
~~~

Find the invocation instruction:

~~~text
invokevirtual ... // Method demo/api/GreetingService.greet:(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;
~~~

If the caller requests the two-parameter descriptor while the runtime class only has the one-parameter descriptor, the exact mismatch is confirmed.

`javap` shows the contents of a class file; it does not by itself determine which class is loaded by an application server or container. Combine `javap` output with class-loading logs or code source to finish tracing.

### Step 4: Inspect the Dependency Graph of the Runtime Configuration

Do not look only at the declared dependencies file. Check the final resolved version in the exact configuration the application runs with.

With Maven:

~~~powershell
mvn dependency:tree -Dverbose -Dincludes=com.example:text-api
mvn help:effective-pom
~~~

Replace `com.example:text-api` with the real `groupId:artifactId`. `dependency:tree` shows dependency paths and requested/selected versions; `effective-pom` helps inspect the parent, BOM, and `dependencyManagement` applied.

If you need to view the runtime classpath Maven builds:

~~~powershell
mvn dependency:build-classpath -Dmdep.includeScope=runtime -Dmdep.outputFile=target/runtime-classpath.txt
~~~

Compare runtime scope against compile/test scope. A `provided` dependency may be supplied by the container at deployment, so check the container's version rather than only Maven's output.

With Gradle:

~~~powershell
.\gradlew dependencies --configuration compileClasspath
.\gradlew dependencies --configuration runtimeClasspath
.\gradlew dependencyInsight --dependency com.example:text-api --configuration runtimeClasspath
~~~

Substitute the actual dependency coordinates. `dependencyInsight` pinpoints who requested a version, which version won, and why. If the error occurs only in tests, also check `testRuntimeClasspath`; if it occurs only in production, gather info from the exact running artifact/image/container.

### Step 5: Inspect the Contents of the Deployed Artifact

For a standard JAR:

~~~powershell
jar tf target/application.jar
~~~

For an executable Spring Boot JAR, inspect libraries inside:

~~~text
BOOT-INF/lib/
~~~

For a WAR, inspect:

~~~text
WEB-INF/lib/
~~~

Find every JAR that might contain the failing class. If the application deploys to Tomcat, an application server, or a plugin platform, also inspect shared container libraries. A project's dependency tree cannot display libraries added by the server outside the artifact.

For Docker, verify the image digest/tag and startup command. Do not assume the running image contains the newly built JAR simply because the build pipeline succeeded.

## 6. Clues for Isolating the Root Cause

| Clue | High probability | What to check next |
|---|---|---|
| Compiles fine, fails immediately after deploy | Runtime uses a JAR different from compile classpath | Class-loading log, CodeSource, runtime dependencies |
| Fails on only one machine or container | Image/server has a stale library or different classloader | Compare image digests, mounted volumes, shared libs |
| Fails only in tests | `testRuntimeClasspath` differs from production runtime | Gradle/Maven test dependency tree |
| Fails only when enabling an integration | Transitive dependency of that integration conflicts | `dependencyInsight` or Maven tree filtered by artifact |
| Fails after overriding Spring Framework/Jackson/Hibernate | Modules are no longer on the same release line | BOM, effective POM, and resolved graph |
| Stack trace points into a plugin or server | Plugin/server loads its own classes | Environment's classloader and shared libraries |
| Multiple JARs contain the same FQCN | Classpath order or shading | `jar tf`, class-loading log, and archive contents |

An error occurring on only one endpoint can stem from lazy initialization: the class is not linked until that specific method is called. Therefore, an application starting up successfully does not prove all runtime APIs are compatible.


## 7. Fixing Dependency Conflicts in Maven

Maven uses dependency mediation to pick one version when the same artifact is requested multiple times. The default rule is **nearest definition**: the path closest to the project wins; if two paths have equal depth, the dependency declared first wins.

For example, a project has two branches pulling `com.example:text-api`:

~~~text
application
  |-- report-client:4.0
  |      |-- text-api:2.0
  |
  |-- legacy-exporter:1.5
         |-- text-api:1.0
~~~

If the path to `text-api:1.0` is closer to the project, Maven may select version 1.0 even though another library compiled against API 2.0.

### 7.1. Declaring the Compatible Version Directly

If you determine `text-api:2.0` is compatible with all callers, you can manage the version in the project:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>text-api</artifactId>
            <version>2.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

When the API is needed directly in code, declare the dependency in `dependencies` without repeating the version:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>text-api</artifactId>
    </dependency>
</dependencies>
~~~

`dependencyManagement` controls the version whether the dependency is declared directly or referenced transitively. Pin a version only after confirming it is compatible with every library calling it.

### 7.2. Excluding the Old Dependency from the Conflicting Branch

If `legacy-exporter` pulls in an incompatible dependency that is not actually needed at runtime, exclude it on that specific edge:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>legacy-exporter</artifactId>
    <version>1.5</version>
    <exclusions>
        <exclusion>
            <groupId>com.example</groupId>
            <artifactId>text-api</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

Then declare the compatible version explicitly. An exclusion removes only one dependency path; if a caller still requires that API, a replacement dependency must be provided. Never exclude a library merely to make the dependency tree look tidier.

### 7.3. Importing a BOM Instead of Pinning Versions Individually

When multiple libraries belong to the same ecosystem, prefer the vendor's BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.5.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

`3.5.0` is purely a syntax illustration. Choose the BOM matching the Spring Boot line your project actually uses. Do not copy this example version into another project without checking its release line.

After making changes, re-run:

~~~powershell
mvn dependency:tree -Dverbose
mvn clean verify
~~~

Verify the right version is selected across all modules and scopes. Also read omitted/conflicted dependency paths to understand why Maven chose the final version.

## 8. Fixing Dependency Conflicts in Gradle

Gradle resolves version conflicts by evaluating requested versions in the dependency graph. By default, Gradle typically selects the highest version among valid candidates; dependency constraints, platforms, rich versions, and resolution rules can alter the outcome.

### 8.1. Using a Platform/BOM

Gradle Groovy DSL example:

~~~groovy
dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.5.0')

    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'com.example:text-api'
}
~~~

A platform brings version constraints from the BOM into the configuration. In Gradle, `platform(...)` provides constraints that participate in conflict resolution; another dependency can still cause the selected version to change. `enforcedPlatform(...)` forces versions more aggressively and can affect downstream consumers, so use it only with clear justification.

### 8.2. Using a Dependency Constraint for a Single Library

If you only need to manage one specific module:

~~~groovy
dependencies {
    constraints {
        implementation('com.example:text-api:2.0') {
            because 'The runtime API must include the overload used by report-client'
        }
    }
}
~~~

A constraint lets Gradle pick a version intentionally within the relevant configuration. Still, verify that version 2.0 is truly compatible with all consumers and providers in the graph.

Avoid using `resolutionStrategy.force` as a default fix. Forcing a version can shift the failure to another library that expects the older API. If forced temporarily, document the reason, configuration scope, and protective tests.

### 8.3. Verifying the Selected Version

Run:

~~~powershell
.\gradlew dependencyInsight --dependency com.example:text-api --configuration runtimeClasspath
.\gradlew dependencyInsight --dependency com.example:text-api --configuration compileClasspath
.\gradlew dependencies --configuration runtimeClasspath
~~~

Compare compile and runtime. If only tests fail, also run `testRuntimeClasspath`. The `dependencyInsight` report explains which version was chosen, which dependency requested it, and the selection reason such as conflict resolution, constraint, rule, or forced version.

After fixing:

~~~powershell
.\gradlew clean test
.\gradlew bootJar
~~~

Do not stop at a green build. Run the exact packaged JAR and inspect dependencies inside the archive.

## 9. Synchronizing Dependencies in Spring Boot

Spring Boot publishes the `spring-boot-dependencies` BOM to manage a set of dependencies tested together. For Spring Boot applications:

- Use the Spring Boot parent POM or import the matching BOM in Maven.
- Use the Spring Boot Gradle plugin/dependency management plugin or native Gradle platform.
- Avoid assigning individual versions to Spring Framework, Spring Data, Spring Security, Jackson, or Hibernate modules when the BOM manages them.
- Verify Spring Cloud and out-of-BOM libraries using their own compatibility matrices.
- If overriding a version is unavoidable, document the reason and run integration tests against the actual dependency set.

Maven example using the Spring Boot parent:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
</parent>
~~~

The version above is illustrative. Pick the appropriate maintenance release and keep the Spring Boot Maven plugin on the same release line.

Gradle example with native BOM support:

~~~groovy
plugins {
    id 'org.springframework.boot' version '3.5.0'
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.5.0')
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

When using the `io.spring.dependency-management` plugin, the Spring Boot Gradle plugin can import the corresponding BOM automatically. Do not declare an extra duplicate platform if the build already manages dependencies this way.

A BOM cannot protect an application from manually packaged libraries, JARs supplied by an application server, or duplicate classes inside a shaded archive. Therefore, you must still inspect artifacts and classloaders when the dependency tree looks clean yet the error persists.

## 10. Checking Class Sources Outside the Dependency Graph

When Maven/Gradle already selects the right version yet `NoSuchMethodError` still occurs, inspect the real runtime:

1. **Executable Spring Boot JAR:** check `BOOT-INF/lib/` for packaged library versions.
2. **WAR:** check `WEB-INF/lib/` and Servlet container shared libraries.
3. **Application server:** inspect global/shared libraries and parent-first/child-first classloading rules.
4. **Docker/Kubernetes:** check image digest, tag, mounts, entrypoint, and the JAR file actually being executed.
5. **Shaded/uber JAR:** look for duplicate classes; if multiple versions truly must be packaged, use proper relocation and inspect bytecode after shading.
6. **Plugins or hot reload:** inspect custom classloaders and perform a full process restart to clear stale class state.

`jar tf` lists archive contents but does not resolve duplicate classes. Combine its output with class-loading logs to see which class is actually chosen.

Do not wipe the entire Maven/Gradle cache as a first step. Cache corruption can happen, but if dependency resolution selects the wrong version, re-downloading the same artifact will not change the outcome. First fix the graph and verify the artifact; clean the cache only when there is evidence of a corrupted file or bad cache metadata.


## 11. Choosing a Fix Based on Root Cause

Once you have identified the class and runtime version, pick one of the paths below.

### Case A: Runtime Uses an Older Version Than the Caller Needs

If the caller compiled against API 2.0 while runtime loads API 1.0:

- Upgrade the runtime dependency to a version containing the required method.
- Verify every other library is compatible with the newer version.
- Remove the old JAR from the classpath, deployment directory, image, or shared library folder.
- Rebuild the artifact and confirm the classloader loads the new JAR.

Do not merely add API 2.0 to the POM if API 1.0 is still packaged or the server still loads the old class first.

### Case B: An Older Library Is Incompatible with the New API

If upgrading a shared API breaks another library:

- Upgrade the calling library to a version supporting the new API.
- Or choose an API version compatible with all callers.
- If no overlapping version exists, replace the old library or isolate the integration into a separate module/classloader.
- Do not force a version without checking every consumer in the dependency graph.

### Case C: The Application Server Supplies the API

If the class comes from the server:

- Determine the exact API version provided by the server.
- Use that version for compiling and testing.
- Configure `provided` scope when the server owns the dependency.
- If the application must package its own library, follow the server's classloading and deployment guidelines; avoid two copies of the same FQCN.

Do not assume `WEB-INF/lib` always beats global libraries. Precedence depends on the application server and classloader configuration.

### Case D: The API Changed Incompatibly

If the vendor removed or changed a method descriptor, upgrade callers to a version supporting the new API or update callers to use the current API. If you maintain both API and callers, publish changes under a release plan with binary-compatibility checks.

### Case E: Deployed Artifact Does Not Match Built Artifact

If the dependency graph is right yet the server still loads an old JAR:

- Verify the running file and image via checksum/digest.
- Stop the old process and deploy the new artifact following the proper procedure.
- Delete manual copies or stale deployment directories after confirming the right target.
- Restart the process to create a fresh classloader.
- Log the resolved version and class CodeSource during smoke tests.

Never delete production files or directories based merely on similar names. Confirm the running artifact's exact path before modifying deployment files.

## 12. Example of Resolving a Real Incident

Suppose an application reports:

~~~text
java.lang.NoSuchMethodError:
  'com.example.json.JsonNode com.example.json.JsonMapper.readTree(java.io.InputStream)'
    at com.example.report.ReportParser.parse(ReportParser.java:48)
~~~

Workflow:

1. The stack trace shows the caller is `ReportParser.parse`, while the missing method belongs to `JsonMapper`.
2. Inspect `JsonMapper.class.getProtectionDomain().getCodeSource()` to identify the runtime JAR.
3. Run `javap -p -s` against the loaded JAR to see if `readTree(InputStream)` and its descriptor exist.
4. Run Maven `dependency:tree` or Gradle `dependencyInsight` for the artifact containing `JsonMapper`.
5. Compare the compile classpath, runtime classpath, and dependencies inside `BOOT-INF/lib`/`WEB-INF/lib`.
6. Identify which library requires the new API and which dependency branch pulls the old API.
7. Pick a compatible version, update the BOM/constraint/exclusion or upgrade the caller library.
8. Clean build, repackage, and inspect the actual JAR.
9. Run a smoke test using the exact deployment command or production container.
10. Record the resolved version and class source in logs to prevent recurrence.

Class and method names in the example are illustrative. In a real incident, substitute the exact owner, method descriptor, and artifact from the stack trace.

## 13. Preventing Binary Compatibility Errors

### 13.1. Centralized Version Management

- Use a BOM or dependency management for libraries in the same release train.
- Avoid repeating version numbers across multiple modules.
- Restrict version ranges and dynamic versions in release environments.
- Check the dependency graph in CI, not only on developer machines.
- If the project needs exact reproducible dependency graphs, consider Gradle dependency locking or an appropriate version-locking mechanism.

Locking versions makes builds reproducible; it does not by itself prove the locked versions are mutually compatible.

### 13.2. Checking Compile and Runtime Classpaths

In CI, verify key configurations:

- Compile classpath.
- Runtime classpath.
- Test compile/runtime classpaths.
- Integration test classpath.
- Container-provided dependencies if deploying a WAR or plugin.

Run tests against the packaged artifact, not only against IDE class directories. Some bugs appear only when the executable JAR, WAR, or image is built because packaging can include different dependencies than test classpaths.

### 13.3. Checking Compatibility When Releasing Libraries

If your team develops libraries:

- Avoid removing or changing public method descriptors in a minor release when promising binary compatibility.
- Use deprecation and migration paths before removing APIs.
- Check public APIs and binary compatibility with appropriate tools in CI.
- Test the library against all dependency versions it claims to support.
- Clearly publish minimum/maximum versions and a compatibility matrix.
- When changing major versions, upgrade callers alongside release notes and migration guides.

A library compiling cleanly against a new dependency does not prove it is compatible with an older runtime dependency that consumers might still use.

### 13.4. Testing the Artifact the Way Users Deploy It

For applications:

1. Build the executable JAR or WAR.
2. Inspect packaged dependencies.
3. Run the exact built artifact, not class directories from the IDE.
4. Smoke test flows calling the relevant libraries.
5. Inspect class-loading logs when duplicate classes or custom classloaders are involved.

For starters/libraries:

1. Publish or install the artifact into a test repository.
2. Create a sample consumer declaring only public dependencies.
3. Boot the consumer with the real runtime.
4. Verify transitive dependencies, packages, and auto-configurations load from the expected artifact.
5. Run tests against dependency versions listed in the compatibility matrix.

## 14. Anti-Patterns to Avoid

1. **Upgrading every dependency to latest immediately.** Can introduce more incompatibilities; identify the artifact and method first.
2. **Running only a clean build and assuming it is fixed.** Clean deletes stale build outputs but does not fix dependency resolution or server classloaders.
3. **Adding a direct dependency without checking the graph.** Can introduce new conflicts or mask an older dependency branch.
4. **Applying blanket forces/exclusions.** Can leave another library missing required methods or classes.
5. **Catching `LinkageError` and continuing.** The application can run in an inconsistent state and fail later.
6. **Inspecting only the POM/Gradle file.** You must verify the resolved version and loaded class.
7. **Assuming newer versions are always backward-compatible.** SemVer and release notes are guides, yet specific API contracts still need verification.
8. **Clearing caches as a default remedy.** If the graph still selects the same version, re-downloading JARs fixes nothing.
9. **Testing only locally.** CI, containers, application servers, and production can have different classpaths.
10. **Packaging two versions of the same class without controlled relocation.** The classloader will pick one definition; callers may link against the wrong one.

## 15. NoSuchMethodError Resolution Checklist

| Item | Question to answer |
|---|---|
| Stack trace | Which owning class, method, and descriptor are missing? |
| Caller | Which bytecode is invoking that method? |
| Runtime class | From which JAR/URL is the JVM loading the class? |
| API comparison | Do the compile-time and runtime JARs share the same method descriptor? |
| Dependency graph | Which artifacts request each version and which version won? |
| Scope | Do compile, runtime, test, and container share the same dependency? |
| Packaging | Does the JAR/WAR/image contain stale JARs or duplicate classes? |
| Classloader | Is a server/plugin/shared library loading a different class? |
| Resolution | Did the BOM, dependencyManagement, constraint, or exclusion fix the right edge? |
| Verification | Have you run the exact packaged artifact in a production-like environment? |

## 16. Key Takeaways

- `NoSuchMethodError` is a `LinkageError`: bytecode invokes a method, yet the class loaded by the JVM lacks the exact method descriptor.
- Common cause is a caller compiled against one API version while runtime loads another version.
- Read the stack trace, identify the owning class, print CodeSource/classloader, and use `javap` to compare descriptors.
- Maven picks versions by nearest definition; Gradle picks the highest version by default during conflict resolution. Use dependency tree/insight to see why.
- The Spring Boot BOM keeps dependencies on the same release train; per-module overrides require clear justification and testing.
- The dependency tree does not show libraries added by an application server, plugin, shaded JAR, or container.
- Fix the right version or caller, eliminate duplicate JARs, rebuild, and verify the actual runtime artifact.
- Never swallow `LinkageError`, never blindly force versions, and never declare success just because compilation passes.

### Official References

- Java SE API — `NoSuchMethodError`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/NoSuchMethodError.html
- Apache Maven — Introduction to the Dependency Mechanism: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Gradle — Viewing and Debugging Dependencies (`dependencies`, `dependencyInsight`): https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html
- Gradle — Graph Resolution and Version Conflict Resolution: https://docs.gradle.org/current/userguide/graph_resolution.html
- Spring Boot — Managing Dependencies and BOM Support: https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html
