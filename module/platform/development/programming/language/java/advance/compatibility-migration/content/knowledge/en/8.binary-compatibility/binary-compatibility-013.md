# Testing Old Consumers Against a New Library Without Recompiling

In Java migration, a library can be upgraded, compile successfully, and pass all unit tests yet still break applications that use the old version. The reason is that those applications were already compiled into bytecode with references to classes, methods, and fields from the previous library version. When replacing only the JAR in the runtime environment, the JVM must link the old bytecode with the new definitions. Errors such as NoSuchMethodError, NoSuchFieldError, or IncompatibleClassChangeError may appear only when the program actually executes the relevant operation.

**Testing old consumers against a new library without recompiling** (old-consumer binary compatibility test) is the approach of keeping the consumer artifact that was compiled with the old version of the library, and then running that exact artifact with the new version of the library on the classpath or module path. The goal is to verify that an already-released consumer can still link and execute when the dependency is replaced, within the binary compatibility scope the library claims to support.

The core point is **locking the consumer's bytecode**. If you recompile the consumer against the new library, you have changed the subject under test: the compiler may emit different symbolic references, catch certain errors before runtime, or accidentally mask errors that consumers deployed in production will encounter.

## 1. Distinguishing Binary Compatibility from Recompilation and Behavioral Compatibility

An API change can affect different types of compatibility in different ways:

| Inspection Angle | Question | How to Test |
|---|---|---|
| Source compatibility | Can the old consumer source be recompiled against the new library? | Compile the old source against the new library |
| Binary compatibility | Can the old consumer's classes/JAR run with the new library without recompiling? | Keep the consumer artifact unchanged; swap the library JAR at runtime |
| Behavioral compatibility | Do results, exceptions, state, and side effects continue to satisfy the contract? | Run behavioral scenarios on the new library and compare against the contract |
| Runtime/class-file compatibility | Can the target JVM read the artifacts' bytecode? | Check the class-file major version and run on the target JDK |

A library can preserve binary signatures and allow old consumers to run, yet change rounding rules or result ordering. In that case binary compatibility is preserved, while behavioral compatibility may be broken. Conversely, consumer source may recompile against new code after a developer fixes API calls, yet old consumer artifacts still fail when only the library is replaced.

For example, an old method:

~~~java
public String findName(long id);
~~~

is changed to:

~~~java
public CharSequence findName(long id);
~~~

The two methods look identical in name and parameters at source level, and String is a subtype of CharSequence. However, the JVM method descriptor also includes the **return type**: calls from an old consumer may require the descriptor (J)Ljava/lang/String;, whereas the new class only provides (J)Ljava/lang/CharSequence;. If no method with the old descriptor remains, the runtime may throw NoSuchMethodError.

What matters in a migration is defining the exact support commitment: which group of consumers, which consumer versions, which JDKs, and which artifact replacements are permitted without rebuilding.

## 2. Why Can Java Fail at Runtime?

When javac compiles a consumer, the class file contains symbolic references to types, methods, and fields, typically via the constant pool. The JVM is not required to link every reference immediately when the process starts; some references are resolved when a class is loaded, verified, or when a code path is executed.

An invocation can be encoded with information including:

- **Class binary name:** for example com.example.api.PriceService.
- **Method name:** for example calculate.
- **Method descriptor:** the parameter type list together with the return type in JVM form.
- **Invocation kind:** for example invokevirtual, invokestatic, invokeinterface, or invokespecial.
- **Access and inheritance rules:** whether the method is accessible and exists in an appropriate hierarchy.

Fields are also referenced by owner, name, descriptor, and static/instance rules. Changing an instance field to static can cause old bytecode to use getfield while the new field can only be accessed via getstatic. This is a structural change at the JVM level, even though the field name still exists.

The compiler checks APIs based on the build-time classpath. The JVM links based on the actual classes that the class loader finds at runtime. When those two sets of classes differ, a linkage error can appear even though the old consumer build previously succeeded.

### 2.1. Common Linkage Errors

| Error | Common Likelihood When Replacing a Library | Evidence to Inspect |
|---|---|---|
| NoSuchMethodError | Old method or constructor was removed; descriptor, return type, or overload changed | Call descriptor in consumer and existing methods in new library |
| NoSuchFieldError | Old field was removed/renamed or field descriptor changed | Field reference in constant pool and field declaration in new JAR |
| IncompatibleClassChangeError | Incompatible change to class/interface, static/instance, or member access form | Calling instruction and class structure of both versions |
| IllegalAccessError | Member or class is no longer accessible under runtime rules | Access flags, package, module, and class loader |
| AbstractMethodError | Call to a method needing an implementation yet runtime finds no concrete implementation | Class/interface hierarchy and actual loaded versions |
| NoClassDefFoundError | Required class is no longer found, or prior class initialization failed | Class loading log, root cause, and runtime dependency graph |
| UnsupportedClassVersionError | New library has a class-file version higher than the target JVM supports | Class major/minor version via javap and runtime JDK |

The errors above generally inherit from LinkageError, yet they should not be treated as the same cause. For example, upgrading the JDK may resolve UnsupportedClassVersionError but does not solve an old method having been removed. Changing the classpath may resolve NoClassDefFoundError without fixing an actual binary API break.

### 2.2. No Exception Does Not Guarantee Compatibility

Some changes do not trigger linkage errors yet still break the consumer contract. In particular, compile-time constants can be embedded directly by javac into consumer bytecode:

~~~java
public static final int MAX_RETRIES = 3;
~~~

If library v2 changes it to 5, the old consumer may continue using the value 3 that was inlined at compile time. The JVM does not need to read the field at runtime at that site, so it may not throw NoSuchFieldError. The binary test result might still appear to "run," yet behavior can violate expectations if the library requires the new value to take effect.

Therefore, tests must both detect linkage failures and verify meaningful public behaviors. An application can start up successfully while unexecuted code paths still conceal failures.

## 3. Designing a Standard Test

We need three clearly identified artifacts:

| Artifact | How Is It Built? | When Is It Used? |
|---|---|---|
| library-v1.jar | Build of the old library already used by the consumer | Compile the old consumer and run baseline |
| consumer-v1.jar | Built **once** from consumer source, with compile-time classpath containing library-v1.jar | Used untouched in both baseline and migration tests |
| library-v2.jar | Build of the new library version under evaluation | Replaces library-v1.jar at runtime without rebuilding the consumer |

Test flow:

~~~text
     old consumer source        library v1 source
               |                       |
               | compile with v1       | build
               v                       v
       consumer-v1.jar <---------- library-v1.jar
               |
               | keep checksum unchanged
               |
      +--------+---------------------+
      |                              |
      v                              v
 Run A (baseline)              Run B (migration)
 consumer-v1.jar               consumer-v1.jar
 library-v1.jar                library-v2.jar
      |                              |
      v                              v
 Save reference                 Observe linkage,
 results                        behavior, and errors
~~~

In Run B, library-v1.jar must be removed from the application's runtime classpath. Merely appending library-v2.jar to the end of a classpath that also contains v1 easily causes the JVM to keep loading classes from v1 and yield a false positive.

For the test to be valid, keep other factors constant as much as possible: JDK, system configuration, test data, and dependencies outside the migration. When a JDK upgrade is also required at the same time, separate tests should be run to determine whether a failure comes from the library or the runtime.

## 4. Complete Example: Old Consumer Failing with a New Library

The example uses a JDK with the javac, java, and jar tools. Directory structure:

~~~text
binary-compat-lab/
├── lib-v1/src/demo/api/MessageFormatter.java
├── lib-v2/src/demo/api/MessageFormatter.java
├── consumer/src/demo/client/Main.java
└── out/
~~~

### 4.1. Writing Library v1

File lib-v1/src/demo/api/MessageFormatter.java:

~~~java
package demo.api;

public class MessageFormatter {
    public String format(String name) {
        return "Hello, " + name;
    }
}
~~~

The public method has the name format, one String parameter, and return type String. This is the API the consumer will reference at compile time.

### 4.2. Writing the Consumer and Compiling Exactly Once

File consumer/src/demo/client/Main.java:

~~~java
package demo.client;

import demo.api.MessageFormatter;

public class Main {
    public static void main(String[] args) {
        MessageFormatter formatter = new MessageFormatter();
        System.out.println(formatter.format("An"));
    }
}
~~~

From the binary-compat-lab directory, run on Linux/macOS:

~~~bash
mkdir -p out/classes-v1 out/classes-consumer out/classes-v2

javac -d out/classes-v1 lib-v1/src/demo/api/MessageFormatter.java
jar --create --file out/library-v1.jar -C out/classes-v1 .

javac -cp out/library-v1.jar \
  -d out/classes-consumer \
  consumer/src/demo/client/Main.java
jar --create --file out/consumer-v1.jar -C out/classes-consumer .
~~~

The -cp argument in the consumer compilation step points to **library-v1.jar**. This is the condition of the test: the consumer bytecode must be generated based on the old API.

Run the baseline:

~~~bash
java -cp "out/consumer-v1.jar:out/library-v1.jar" demo.client.Main
~~~

Expected output:

~~~text
Hello, An
~~~

On Windows, use a semicolon to separate entries in the classpath:

~~~powershell
java -cp "out/consumer-v1.jar;out/library-v1.jar" demo.client.Main
~~~

After this step, do not re-run javac on the consumer source until the binary compatibility test is finished.

### 4.3. Making an Incompatible API Change in Library v2

Suppose library v2 changes the method parameter from String to Object and removes the old method. File lib-v2/src/demo/api/MessageFormatter.java:

~~~java
package demo.api;

public class MessageFormatter {
    public String format(Object name) {
        return "Hello, " + name;
    }
}
~~~

The two methods taking Object and String have an overload relationship at source level, but their JVM descriptors differ. A previously compiled consumer does not automatically redirect its call to the Object overload.

Compile and package only library v2:

~~~bash
javac -d out/classes-v2 lib-v2/src/demo/api/MessageFormatter.java
jar --create --file out/library-v2.jar -C out/classes-v2 .
~~~

Run the old consumer with the new library:

~~~bash
java -cp "out/consumer-v1.jar:out/library-v2.jar" demo.client.Main
~~~

On Windows:

~~~powershell
java -cp "out/consumer-v1.jar;out/library-v2.jar" demo.client.Main
~~~

The JVM may emit an error similar to:

~~~text
Exception in thread "main" java.lang.NoSuchMethodError:
  'java.lang.String demo.api.MessageFormatter.format(java.lang.String)'
    at demo.client.Main.main(Main.java:...)
~~~

The cause is not that Object cannot accept String; the issue is that Main's bytecode still requests the method with descriptor (Ljava/lang/String;)Ljava/lang/String;, whereas library v2 only has (Ljava/lang/Object;)Ljava/lang/String;.

### 4.4. Fixing v2 to Preserve the Binary Contract

One compatible approach is to keep the old method and add the new overload:

~~~java
package demo.api;

public class MessageFormatter {
    public String format(String name) {
        return format((Object) name);
    }

    public String format(Object name) {
        return "Hello, " + name;
    }
}
~~~

After rebuilding **only library-v2.jar**, the old consumer-v1.jar can link to the format(String) method and run normally again. Adding an overload can create other source compatibility issues when consumers are recompiled, yet the binary test under consideration only requires that old consumers be able to run with the new API.

Instead of editing consumer source, we fixed the library to continue providing the bytecode-level contract that consumers actually use.

## 5. Using javap to Prove the Exact Method Descriptor

Linkage errors can be confusing when the current source code looks "nearly identical" to the old API. javap lets you inspect the compiled class files themselves.

Inspect the consumer's bytecode and constant pool:

~~~bash
javap -verbose -classpath out/consumer-v1.jar demo.client.Main
~~~

Find the Methodref to demo/api/MessageFormatter.format and its descriptor. In the example above, the expected descriptor is:

~~~text
(Ljava/lang/String;)Ljava/lang/String;
~~~

Compare the class signatures across the two libraries:

~~~bash
javap -s -classpath out/library-v1.jar demo.api.MessageFormatter
javap -s -classpath out/library-v2.jar demo.api.MessageFormatter
~~~

Version v1 provides:

~~~text
public java.lang.String format(java.lang.String);
  descriptor: (Ljava/lang/String;)Ljava/lang/String;
~~~

Whereas the incompatible v2 version only has:

~~~text
public java.lang.String format(java.lang.Object);
  descriptor: (Ljava/lang/Object;)Ljava/lang/String;
~~~

You can inspect the consumer's instructions:

~~~bash
javap -c -classpath out/consumer-v1.jar demo.client.Main
~~~

When the consumer uses invokevirtual pointing to the old method descriptor, the new library having a same-named method with different parameters does not satisfy that symbolic reference.

In static/instance-change cases, also check instructions such as invokestatic and invokevirtual. In field cases, check getfield, getstatic, putfield, or putstatic. For methods declared via an interface, check invokeinterface and the new hierarchy.

### 5.1. Saving a Checksum to Ensure the Consumer Was Not Rebuilt

Before and after the test, you can compute the SHA-256 of the consumer artifact:

Linux/macOS:

~~~bash
sha256sum out/consumer-v1.jar
~~~

PowerShell:

~~~powershell
Get-FileHash out/consumer-v1.jar -Algorithm SHA256
~~~

The two values must match in a test that preserves the consumer artifact. Save the checksum together with the build id, version, and artifact creation timestamp. If the consumer file changes, the test must be reset with a frozen copy.

## 6. API Changes That Need to Be Tested with Old Consumers

Not every source change breaks binary compatibility. Focus on modifications that can affect symbolic references or JVM linking rules.

| Change in the New Library | Risk to Old Consumer Bytecode | How to Construct a Test Scenario |
|---|---|---|
| Remove or rename a public method | No method matching the old descriptor remains | Call the method from the old consumer JAR |
| Change parameter types, parameter order, or return type | Different method descriptor | Use javap to compare Methodref |
| Remove a constructor or change constructor parameters | Failure when bytecode invokes invokespecial to construct objects | Construct an object using the old constructor |
| Change a static method to instance, or vice versa | Invocation kind is no longer valid | Call the old method from the consumer |
| Remove/rename a field or change field type | Corresponding field reference no longer exists | Read/write the field from old bytecode |
| Change an instance field to static, or vice versa | Field access kind is no longer valid | Read/write the field in the consumer |
| Reduce visibility of a class/member | JVM denies access | Call the old API from the consumer's package/module |
| Change a class to an interface or vice versa | Changes the kind of type the bytecode references | Instantiate/cast/call methods via the old type |
| Change superclass or interface hierarchy | Changes method resolution and assignability | Call inherited methods or cast |
| Change an interface affecting old implementations | AbstractMethodError may appear on new usage paths | Use old implementation with the new library/API |

You should not assert that all changes in the table always produce errors in every case; the outcome depends on the exact class structure, inheritance relationships, and kind of compiled symbolic reference. For example, a method moved to a new superclass may sometimes still resolve successfully, whereas another same-named change breaks the descriptor.

### 6.1. Generics, Erasure, and Bridge Methods

For Java generics, the JVM works primarily with erased descriptors; certain synthetic methods (bridge methods) are generated by the compiler to preserve dispatch semantics after type erasure. If a generic hierarchy or covariant return type is changed without keeping the necessary bridge method, an old consumer may invoke a descriptor that no longer exists.

Do not look only at the library source. Use javap -p -s -verbose to see all bridge/synthetic methods that javac generated. When ABI must be maintained, you sometimes must keep a forwarding method or alter the design so the compiler continues generating the appropriate bridge.

### 6.2. Public Constants and Enums

As noted, constant expressions can be inlined into consumers. Changing the value of a public static final primitive or String constant may not produce a LinkageError, yet old consumers continue using the previous value. Enums can affect switch behavior, serialization, and constant names; removing an enum constant used by old consumers can break related code paths.

For changes like these, add behavioral tests and data tests rather than only checking whether class loading succeeds.

### 6.3. Reflection, ServiceLoader, and Configuration

A consumer may load classes using Class.forName, ServiceLoader, dependency injection, or names declared in configuration files. Failures may not appear in the method-reference list of consumer bytecode. Therefore, you must exercise plugin initialization, service discovery, serializers, mappers, and active frameworks.

Binary compatibility of a Java API does not guarantee that data, serialization, or reflection contracts remain compatible. If a library has such boundaries, additional dedicated tests are needed.

## 7. Do Not Let the Build Tool Automatically Recompile the Consumer

In real projects, this mistake easily happens with multi-module builds: running a project test task can trigger the consumer's compileJava and silently compile the consumer against the new API. The result then is a source compatibility test or an integration test of the new version, no longer an old-consumer test.

### 7.1. General Principles

- Use an already-released consumer JAR/class files, or build the consumer from the v1 baseline and store it separately as an immutable fixture.
- Do not declare the consumer as a project dependency that gets rebuilt in the same run.
- The runtime classpath must contain library v2 and the corresponding runtime dependencies; exclude library v1 and duplicate copies of library classes.
- Do not place consumer source in a source set that will be compiled when running the test task.
- Record the exact classpath, module path, and target JDK of the execution process.
- Keep old consumer fixtures across multiple new library versions if the library claims support for multiple consumer generations.

### 7.2. With Gradle

If the old consumer has already been published as a JAR, you can create a separate configuration for runtime testing. Conceptual example in Groovy DSL:

~~~groovy
configurations {
    binaryCompatRuntime
}

dependencies {
    binaryCompatRuntime("com.example:legacy-consumer:1.0.0")
    binaryCompatRuntime("com.example:library:2.0.0")
}

tasks.register("runOldConsumer", JavaExec) {
    classpath = configurations.binaryCompatRuntime
    mainClass = "com.example.client.Main"
}
~~~

When using this snippet, check transitive dependencies: legacy-consumer may pull in library v1; Gradle typically resolves same-group/artifact conflicts by picking one version, yet constraints, classifiers, shaded JARs, or different coordinates can cause two implementations to coexist at the same time. Inspect the exact configuration:

~~~bash
./gradlew dependencies --configuration binaryCompatRuntime
./gradlew dependencyInsight \
  --configuration binaryCompatRuntime \
  --dependency library
~~~

Only after that should you run the task with the verified classpath. Task names, dependency coordinates, and main classes in the example must be replaced with the real project's values. The consumer fixture must be a fixed binary artifact; if you declare project(":consumer") and Gradle rebuilds that project, the "without recompiling" condition may be violated.

For an unpublished library under development, you can use a dedicated task that constructs a classpath from the current build's JAR file and the locked consumer fixture file. Verify that library v2 has been built before running, without running consumer compilation.

### 7.3. With Maven

Create a module or harness project dedicated to running the old consumer binary, declaring dependencies on the old consumer version and the new library version. Maven will resolve the dependency graph according to dependency mediation rules; check the selected library version:

~~~bash
mvn dependency:tree
mvn dependency:build-classpath
~~~

If the consumer artifact transitively requests library v1, you can use dependencyManagement or appropriate exclusions to ensure runtime receives only version v2. After confirming the classpath, run the main class of the old consumer JAR using java or a suitable Maven execution mechanism.

If using a Maven reactor that builds consumer source simultaneously, move the fixture outside the reactor or ensure the run target does not trigger consumer compilation. A single mvn test run on the current source project does not by itself prove that consumer binaries from an old release run.

### 7.4. With Modular Applications

If the application uses the Java Platform Module System (JPMS), construct the proper module path, module name, and launch command. A new library may keep classes/methods yet alter the module descriptor, exports, or requires and cause the old consumer to fail during module resolution.

Example:

~~~bash
java --module-path "mods" \
  --module com.example.consumer/com.example.client.Main
~~~

The artifacts in mods must represent the old consumer and the new library version. Do not replace the module path with the classpath if actual deployment runs on the module path, because the two modes have different resolution and access rules.

## 8. What Should a Test Suite Run?

Merely calling main and checking exit code 0 is an initial smoke check. Because the JVM can resolve methods or load classes on demand, you must actively exercise the APIs the old consumer used.

### 8.1. Minimum Scenario Group

1. **Baseline:** consumer-v1.jar + library-v1.jar. Confirm that the fixture and test data inherently work.
2. **Migration:** consumer-v1.jar + library-v2.jar. Keep the exact consumer artifact and swap only the library/required runtime dependencies.
3. **Initialization:** load classes, instantiate objects, invoke old constructors and static factories.
4. **Methods:** call representative public APIs, including relevant overloaded, generic, and inherited methods.
5. **Fields/constants:** read/write public fields per contract and verify values that may be inlined.
6. **Interfaces:** instantiate and call old implementations through interfaces published by the new library.
7. **Errors:** test exception branches, data-not-found, invalid input, and timeouts where guaranteed.
8. **Frameworks:** trigger reflection, serializers, annotation scanning, ServiceLoader, or plugin lifecycles if the system uses them.
9. **Target runtime:** run on the lowest JDK still within the support scope, not just the CI JDK.

Depending on system characteristics, you may also need to test concurrency, transactions, IO, TLS, or native integration. Do not expand randomly, however: each case must tie to an API or contract the consumer actually depends on.

### 8.2. Using Reference Data and Results

In the baseline, record expected outputs or state per the contract: return values, exception types, database state, event counts, or important side effects. In the migration run, compare those results against the commitment. If semantics are intentionally changed, documentation must state whether old consumers are allowed to keep running under the new semantics or must migrate.

Reports should be categorized as:

| Result | Interpretation |
|---|---|
| Binary pass and behavior pass | Old consumer links cleanly, tested scenarios continue to meet the contract |
| Linkage fail | API/bytecode/classpath/module fails to link; root cause investigation needed |
| Linkage pass, behavior fail | No linkage error, yet semantics or results changed |
| Runtime environment fail | JVM, config, native dependency, or external system mismatch; must distinguish from binary API break |
| Untested path | Code paths that might load that API have not been executed; insufficient evidence to claim compatibility |

The "untested path" point is very important. A passing test confirms only the executed paths and the environment used; it cannot by itself prove every class in the dependency graph will run safely.

## 9. Identifying the Exact Class Loaded by the JVM

During migration, a common mistake is thinking the test uses library v2 while the JVM actually loads classes from library v1, an old fat JAR, a build directory, or an application server class loader. In that case, a passing test does not reflect the intended JAR swap.

On HotSpot/OpenJDK JDK 9 and later, you can enable class loading logs in the test environment:

~~~bash
java -Xlog:class+load=info \
  -cp "out/consumer-v1.jar:out/library-v2.jar" \
  demo.client.Main
~~~

With JDK 8, a familiar syntax is:

~~~bash
java -verbose:class \
  -cp "out/consumer-v1.jar:out/library-v2.jar" \
  demo.client.Main
~~~

Check the source location of demo.api.MessageFormatter and suspect classes. The log typically shows the JAR/class file path that the JVM used. If a class is loaded by a custom loader or from a nested JAR, cross-reference further with the framework's packaging/loader mechanism.

Avoid looking only at same-named files in cache directories. Record the running artifact by group/artifact/version, file path, and checksum if available.

### 9.1. Checking the Library's Class-File Version

~~~bash
javap -verbose -classpath out/library-v2.jar demo.api.MessageFormatter
~~~

Look up major version and minor version. If library v2 contains classes requiring a JDK higher than the declared runtime, the old consumer may fail with UnsupportedClassVersionError before even reaching descriptor checks. For multi-release JARs, check the view appropriate for the target JDK; a Java 21 entry under META-INF/versions/21 does not by itself cause Java 17 to fail if the library is packaged properly as multi-release and has a suitable implementation.

## 10. Automating the Test in CI/CD

You can make the old-consumer test a dedicated compatibility lane alongside the new library's unit tests and integration tests.

~~~text
Old release / saved fixture
          |
          v
 consumer-v1.jar + checksum  ------+
                                    |
 Build new library                  |
          |                         |
          v                         v
   library-v2.jar ----------> Compatibility harness
                                     |
                      +--------------+-------------+
                      |              |             |
                      v              v             v
                    JDK 17         JDK 21       ...other JDKs
                      |              |             |
                      +--------------+-------------+
                                     |
                                     v
                        Linkage + behavior report
~~~

A suitable pipeline can:

1. Download or materialize the consumer binary fixture from the old release; verify the checksum.
2. Build library v2 using the declared toolchain.
3. Assemble the classpath/module path with the old consumer and new library; exclude the old library.
4. Record the JDK vendor/version and the resolved list of runtime dependencies.
5. Run the harness on the JDKs declared as supported and save stdout/stderr/exit status.
6. Categorize linkage errors, behavioral errors, environment errors, and unexecuted code paths.
7. Publish diagnostic reports/artifacts for reviewers, while masking secrets in logs.

If multiple old consumer versions need testing, create a clear matrix: consumer 1.x, 2.x, versions still within the support commitment, and target library 3.x. Avoid creating an unbounded matrix; use the support window policy to choose representative versions or releases that must be supported.

Example matrix:

| Consumer binary | Runtime library | JDK | Purpose |
|---|---|---|---|
| consumer 1.4 (compiled with lib 1.4) | lib 1.4 | Java 17 | Baseline |
| consumer 1.4 (unchanged) | lib 2.0 | Java 17 | Check binary compatibility |
| consumer 1.4 (unchanged) | lib 2.0 | Java 21 | Check on new JDK |
| consumer 2.0 (compiled with lib 2.0) | lib 2.0 | Java 21 | Control for new API, does not replace old-consumer test |

The last row checks that the new release works with new consumers, yet cannot be used as evidence that old consumers still run.

## 11. Combining Static Checks and Runtime Execution Checks

Binary API comparison tools such as japicmp, Revapi, or other ABI toolsets can compare libraries v1 and v2 to spot notable public changes. They help screen changes before running consumers, yet tests on real consumer artifacts are still needed because:

- The actual classpath/module path may differ from the graph assumed by the static tool.
- Reflection and frameworks can create runtime dependencies not visible in public method signatures.
- A change can be valid under binary compatibility rules yet violate behavior.
- Transitive dependencies, native libraries, and the JDK can cause runtime failures.
- On-demand class loading causes errors to appear only on a specific code path.

A sensible workflow is to use an ABI comparison tool to identify risks to watch for, use javap to confirm descriptors when in doubt, and use an old-consumer runtime harness to prove that old deployed artifacts can continue running in the target environment.

### 11.1. Finding the Cause When a Test Fails

When encountering LinkageError, save the full stack trace and follow this order:

1. Confirm the consumer JAR has the exact checksum of the pre-migration version.
2. Confirm the running JVM has the right version/vendor and module path/classpath.
3. Confirm the library class is loaded from the right library v2, not v1 or a duplicate copy in a fat JAR.
4. Use javap on the consumer to inspect the symbolic reference and instruction causing the error.
5. Use javap on library v2 to inspect available method/field descriptors, access flags, and hierarchy.
6. Compare against the old API to determine which change prevents the reference from resolving.
7. Choose to fix in the library, an adapter layer, dependency selection, or version compatibility declaration; re-run the relevant case.

Do not edit consumer source to make the old test pass, because that action destroys the ability to detect breaking changes for already-deployed applications.

## 12. Common Mistakes

- **Recompiling the consumer in the same build:** tests pass, yet the old bytecode needing verification has been lost.
- **Keeping both library v1 and v2 on the classpath:** the class loader may choose v1, leading to a wrong conclusion.
- **Testing only with the developer's or CI's JDK:** misses the lowest runtime the product still commits to support.
- **Only starting the application:** methods and classes may not yet have been loaded or resolved by the JVM.
- **Comparing only method names and parameters at source level:** JVM descriptors also involve return types, static/instance, access, and hierarchy.
- **Relying solely on the library compiling successfully:** does not verify whether old consumer binaries can link.
- **Relying solely on API comparison tools:** does not test classpath, modules, reflection, dependencies, or actual behavior.
- **Forgetting field constant inlining:** old consumers may keep using old compile-time values even though the library changed.
- **Using artifacts without provenance:** not knowing which library the consumer actually compiled against or which version runtime loaded.
- **Not recording versions of transitive dependencies:** an error originating from transitives gets misdiagnosed as a public library failure.
- **Mixing JDK and library changes and concluding a single cause:** makes it hard to distinguish a runtime issue from an ABI break.

## 13. Checklist Before Declaring Binary Compatibility

- [ ] Identified old consumer versions still within support scope.
- [ ] Saved consumer binary from a previous release, along with build id and checksum.
- [ ] Consumer was compiled against library v1 and not recompiled during the migration test.
- [ ] Baseline consumer-v1 + library-v1 runs successfully on the reference environment.
- [ ] Migration run uses only consumer-v1 + library-v2 and corresponding runtime dependencies.
- [ ] Verified that no library v1/duplicate classes are loaded by the JVM during the migration test.
- [ ] Ran tests on the lowest still-supported JDK.
- [ ] Exercised representative APIs, constructors, fields, interfaces, reflection, and relevant lazy-loaded code paths.
- [ ] Checked LinkageError and clearly distinguished environment errors, class-file versions, and API linkage.
- [ ] Compared public behavior that must be preserved beyond merely checking for no exceptions.
- [ ] Recorded classpath/module path, artifact versions, checksums, run commands, and results.
- [ ] Untested cases or breaking changes are clearly announced together with a consumer migration plan.

## 14. Conclusion

To verify binary compatibility in Java migration, you must run **the exact already-released consumer bytecode** against **the new library JAR** without recompiling the consumer. This test reflects what happens when a deployed application only swaps a dependency in its runtime environment. Combining an old baseline, a clean runtime classpath, method/field descriptor inspection via javap, real code paths, and a JDK matrix helps detect linkage errors before release. When old binary APIs cannot be kept, you must announce compatibility changes, provide adapters, or require consumers to rebuild/migrate along a concrete roadmap.
