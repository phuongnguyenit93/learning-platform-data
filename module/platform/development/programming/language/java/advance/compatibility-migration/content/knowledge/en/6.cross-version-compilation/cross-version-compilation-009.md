# Dependency library with bytecode higher than the declared support level

An application may compile successfully targeting Java 17 yet still fail to run on Java 17 because a dependency library contains class files compiled for Java 21. This situation often arises when upgrading a dependency version, when a library updates its build JDK while forgetting to preserve the minimum runtime level, or when a transitive dependency changes without the application proactively upgrading.

**Dependency library with bytecode higher than the declared support level** is the case where an artifact is declared to support a certain runtime, yet one or more classes that the runtime needs to load have a class-file version exceeding the runtime's capability. The declared support level may appear in documentation, release notes, package metadata, or the product contract. When the actual bytecode does not meet that level, the consumer may fail to start or only error when entering a specific functional flow.

This is an issue of the entire dependency graph, not only the libraries that the application declares directly. A primary library may be compiled for Java 17 yet pull in a dependency that only runs on Java 21. Without inspecting the resolved artifacts, verifying that the application's source code uses --release 17 does not prove that the product supports Java 17.

## 1. Correctly understanding a library's minimum Java level

When a vendor writes “requires Java 17” or “supports Java 17+”, that information usually means a Java 17 or higher runtime falls within the library's support scope. To fulfill this commitment, the classes that need to be loaded on Java 17 must use a class-file format that Java 17 understands, and APIs, modules, dependencies, as well as runtime behavior must also be compatible.

There are at least three separate conditions to consider:

1. **Class-file compatibility:** Can the JVM read the .class format?
2. **API compatibility:** Does the code call Java SE APIs or library APIs that the target runtime actually provides?
3. **Runtime behavior compatibility:** Does the dependency work properly with the semantics, module system, TLS, reflection, GC, and other runtime characteristics of the target JDK?

The class-file version is a necessary condition for the JVM to load a class, but it is not sufficient to prove that the library can run. A class with major version 61 can still call a method that only exists since Java 21 if it was compiled in a way that did not constrain the API appropriately; when running on Java 17, the error may be NoSuchMethodError instead of UnsupportedClassVersionError.

### 1.1. Class-file major version

Each class file has a header containing a magic number, minor version, and major version. The major version indicates the class-file format. Some common milestones:

| Java release | Class-file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |

For modern Java releases, you can convert a major version to a release by subtracting 44 from the major version. For example, major 61 corresponds to Java 17; major 65 corresponds to Java 21. When analyzing an actual class, use javap -verbose or read the class file header to verify instead of guessing from the JAR name.

If the JVM has to load a class with a major version higher than what it supports, it may throw UnsupportedClassVersionError. For example, Java 17 supports class-file major 61; if a class to be loaded has major 65, the Java 17 JVM does not understand that class format.

### 1.2. Compiler version does not equal target version

A library built with JDK 21 can still support Java 17 if the author compiles properly with --release 17 and the dependencies are also compatible. Conversely, a library built with JDK 17 does not automatically support Java 17 if it pulls in a dependency that only runs on Java 21.

Therefore, the minimum runtime level cannot be concluded solely from:

- The version name of the artifact.
- The JDK used in the vendor's CI.
- The maven.compiler.source or target values seen in a POM.
- The sourceCompatibility or targetCompatibility values of a Gradle project.
- The consumer's application compiling successfully.

It is necessary to inspect the bytecode in the resolved artifact, the APIs used, and transitive dependencies on the exact target runtime.

## 2. Why can a dependency break the runtime floor?

### 2.1. Direct library is built with a higher release

The application declares:

~~~text
orders-api
  └── com.vendor:payment-client:5.0
~~~

The vendor declares that payment-client:5.0 supports Java 17, yet the PaymentClient class in the JAR has major version 65. An application running on Java 17 will not be able to load this class when the code path using it is executed.

A common cause is that the library's pipeline uses a newer JDK, but the build does not set the corresponding --release or target. The artifact is still published with a valid version, and the POM still resolves normally, yet the bytecode does not match the runtime commitment.

### 2.2. Transitive dependency raises the minimum Java level

Example:

~~~text
orders-api
  └── payment-client:5.0       (base bytecode Java 17)
        └── transport-core:4.2 (base bytecode Java 21)
~~~

The application does not declare transport-core directly. The build tool automatically resolves it through payment-client's dependencies. If the Java 17 runtime has to load a class from transport-core, the application may fail even though orders-api's source and payment-client's bytecode are both at major 61.

A dependency graph should be viewed as a set of artifacts with dependency relationships, not a list of direct dependencies. You must inspect the runtime classpath, dependencies selected after conflict resolution, and the variants resolved by the build tool.

### 2.3. New version changes bytecode without changing the artifact name

A vendor may keep the same group, artifact, and library name while releasing a new version with a higher Java baseline. If the release notes do not clearly state the minimum Java level, consumers may upgrade the version through their normal dependency update process and only discover the failure in older runtime environments.

Do not assume that versions within the same major or minor series of a library preserve the runtime floor. Check the support matrix and the artifact of the exact resolved version.

### 2.4. Multiple classes in the same JAR have different bytecode levels

An ordinary JAR may contain class files produced from multiple modules or different build steps. The main class might have major 61, while a helper class, nested class, secondary package, or generated class has major 65. Inspecting only a single representative class can miss the issue.

Classes are loaded lazily along code paths. Therefore, an application may start up and pass health checks successfully, only to fail when a specific feature loads a class whose bytecode is higher than the runtime.

### 2.5. Multi-release JAR

A multi-release JAR is a mechanism that allows a library to provide different implementations for different JDKs. The JAR has the manifest attribute Multi-Release: true and may contain:

~~~text
library.jar
├── META-INF/MANIFEST.MF
├── com/example/Parser.class
└── META-INF/versions/
    ├── 17/com/example/Parser.class
    └── 21/com/example/Parser.class
~~~

The class in the root directory is the base implementation. The JVM selects the implementation in META-INF/versions/N matching the running release, according to multi-release JAR rules. On a Java 17 runtime, the class in versions/21 is not selected; the base class or the highest versioned entry not exceeding 17 will be used.

Therefore, a scanner reporting a major 65 class in META-INF/versions/21 is not sufficient to conclude that the JAR does not support Java 17. You must verify that the manifest has Multi-Release: true and compute the exact view that the target runtime will select. Conversely, if the base class has major 65, the JAR will not run on Java 17 even if it contains a versions/17 directory inside.

## 3. Symptoms when the runtime floor is violated

| Timing | Symptom | Possible cause |
|---|---|---|
| Compile | bad class file ... wrong version 65.0, should be 61.0 | Older compiler cannot read newer dependency class files |
| Startup | UnsupportedClassVersionError | JVM loads a class with an unsupported major/minor version |
| Startup or when using a feature | NoSuchMethodError / NoSuchFieldError | Class file is readable, but runtime API lacks the member referenced by bytecode |
| Startup or during initialization | NoClassDefFoundError | Missing transitive class, earlier initialization failure, or class loader cannot find the class |
| Only on one functional branch | Error appears when the class is loaded for the first time | Class loading happens lazily; the code path was not exercised during smoke tests |
| Only on a specific runtime | One environment works, another fails | Different runtime, dependency resolution, or multi-release view |

An UnsupportedClassVersionError typically identifies the specific class file and the version the JVM expected. Record the class name and JAR source from the stack trace or class loading log to locate the exact offending artifact.

Not every “Java version” error is caused by the major version. NoSuchMethodError often indicates that compile-time and runtime are using different API versions; ClassNotFoundException may involve the classpath/module path; InaccessibleObjectException relates to reflective access and the module system. Categorize the error before changing dependencies or the runtime.

## 4. Inspecting the actual dependency graph

Before scanning bytecode, determine the exact artifacts and versions that the build resolved. Versions declared in build files may be version ranges, constraints, platforms/BOMs, or versions replaced by conflict resolution.

### 4.1. With Gradle

List runtime dependencies:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Find out why a dependency was selected:

~~~bash
./gradlew dependencyInsight \
  --dependency transport-core \
  --configuration runtimeClasspath
~~~

For compile configuration, also check compileClasspath. A dependency may appear at compile time but not at runtime, or vice versa, due to scope, variant, exclusions, and project configuration.

Gradle Module Metadata can publish variants with the org.gradle.jvm.version attribute. This attribute helps Gradle select the variant matching the JVM target when metadata and consumer are configured compatibly. However, not every library publishes this metadata; a Maven POM or repository mirror may only provide other information. Do not treat successful dependency graph resolution as proof that bytecode has been thoroughly verified.

### 4.2. With Maven

List the dependency tree:

~~~bash
mvn dependency:tree -Dscope=runtime
~~~

Also view compile dependencies if needed:

~~~bash
mvn dependency:tree -Dscope=compile
~~~

To view the effective POM after applying parent, profiles, and properties:

~~~bash
mvn help:effective-pom
~~~

The POM can help identify the dependency's version, scope, exclusions, and build configuration. However, compiler settings in a library's POM are not always propagated as a runtime guarantee that every consumer can check. Cross-reference the vendor's support matrix with the actual bytecode.

### 4.3. Inspecting the exact resolved artifact

Once you have the dependency graph, obtain the JAR path from the cache or the resolved dependency directory. Verify the group/artifact/version coordinates, checksum if available, and source repository. Avoid analyzing a JAR with the same name downloaded from an old cache or another manual directory.

With Gradle, you can use a dependency report, build scan, or a task/configuration that prints the configuration's artifact files. With Maven, you can use the dependency plugin to build the classpath or inspect files in the local repository. Record the specific artifact before drawing conclusions.

## 5. Checking class-file versions in dependency JARs

### 5.1. Checking a known class with javap

If the fully qualified class name is known:

~~~bash
javap -verbose -classpath transport-core-4.2.jar com.vendor.transport.TransportClient
~~~

Look for:

~~~text
minor version: 0
major version: 65
~~~

Major 65 corresponds to the Java 21 class-file format. If the supported runtime floor is Java 17 and this is a class selected to load by the Java 17 runtime, the dependency exceeds that support level.

javap can read classes in a JAR via the classpath. Be sure to specify the exact artifact and class name. For classes not present in the JAR or classes with duplicate names, the result might come from another source on the classpath; keep the classpath minimal to avoid confusion.

### 5.2. Listing classes in a JAR

View the list of entries:

~~~bash
jar --list --file transport-core-4.2.jar
~~~

This command helps locate packages and classes to analyze. However, a JAR may contain hundreds or thousands of classes; manually checking every class is impractical. You can use a script that reads class file headers to collect major version statistics for all .class entries.

Python example using the standard zipfile library:

~~~python
from pathlib import Path
from zipfile import ZipFile
import sys

MAGIC = b"\xca\xfe\xba\xbe"

for jar_name in sys.argv[1:]:
    path = Path(jar_name)
    print(f"JAR: {path}")

    with ZipFile(path) as archive:
        for entry in archive.namelist():
            if not entry.endswith(".class"):
                continue

            header = archive.read(entry)[:8]
            if len(header) < 8 or header[:4] != MAGIC:
                continue

            minor = int.from_bytes(header[4:6], "big")
            major = int.from_bytes(header[6:8], "big")
            java_release = major - 44
            preview = minor == 65535

            print(
                f"  {entry}: major={major}, minor={minor}, "
                f"approx_java={java_release}, preview={preview}"
            )
~~~

Save the script as inspect_class_versions.py, then pass one or more JARs:

~~~bash
python inspect_class_versions.py transport-core-4.2.jar payment-client-5.0.jar
~~~

The script reads the header of every class entry, including nested classes and classes inside the version directories of a multi-release JAR. It does not need to extract the entire JAR to disk. The major minus 44 formula applies to modern class-file versions listed in the example; treat this as a quick conversion, while retaining the original major/minor values for exact reference.

The script above only reports the version of each entry and does not automatically determine which class the runtime will select in a multi-release JAR. You need to read the manifest and handle META-INF/versions/N according to the target release before flagging an entry as a violation.

### 5.3. Interpreting scanner results

Suppose the runtime floor is Java 17:

| Entry in JAR | Major version | Preliminary interpretation |
|---|---:|---|
| com/vendor/Client.class | 61 | Format compatible with Java 17 |
| com/vendor/Helper.class | 65 | Incompatible if this class is loaded by Java 17 |
| META-INF/versions/21/com/vendor/Client.class | 65 | May be valid if the JAR is multi-release and Java 17 does not select this entry |
| META-INF/versions/17/com/vendor/Client.class | 61 | Java 17 view can use this entry if the manifest and JAR structure are valid |

For a multi-release JAR, you need to:

1. Read META-INF/MANIFEST.MF and confirm Multi-Release: true.
2. Group entries by logical class name, stripping the META-INF/versions/N/ prefix to identify alternative versions.
3. For a Java N runtime, select the versioned entry with the largest N not exceeding runtime N; if none exists, use the entry in the root directory.
4. Check the class-file version of the selected entry. Entries with versions higher than the runtime will not be selected by that runtime.

If the manifest does not enable multi-release, do not interpret entries under META-INF/versions/ as alternative implementations selected by the JVM. Cross-check against multi-release JAR rules and the specific tool/runtime.

### 5.4. Preview class files

Class files using preview features can carry minor version: 65535. They require the runtime of the corresponding Java release and typically require --enable-preview. A Java 21 preview class does not become a portable class merely because its major version does not exceed the runtime level; preview requirements must be satisfied separately.

If the inventory detects minor version 65535, record the release that created the class, how the compiler enabled preview, and the runtime configuration. Do not simply compare major versions and conclude compatibility.

## 6. Reading metadata and bytecode to verify APIs

The class-file version answers whether the JVM can read the format. To understand which APIs a class references, you can use additional modes of javap.

~~~bash
javap -p -s -classpath transport-core-4.2.jar com.vendor.transport.TransportClient
javap -c -classpath transport-core-4.2.jar com.vendor.transport.TransportClient
javap -verbose -classpath transport-core-4.2.jar com.vendor.transport.TransportClient
~~~

- -p displays private members as well.
- -s displays JVM descriptors of fields and methods.
- -c displays bytecode instructions.
- -verbose displays the constant pool, version, and detailed attributes.

When investigating NoSuchMethodError, compare the descriptor referenced by the compiled consumer with the method in the actual runtime class. When investigating new Java SE APIs, jdeps can assist in analyzing package/module dependencies and JDK internals:

~~~bash
jdeps --multi-release 17 --jdk-internals transport-core-4.2.jar
~~~

jdeps is useful for dependency analysis and JDK internal APIs, but it does not replace a class-file major version scanner. A JAR may have an appropriate major version yet still reference APIs that do not exist on the target runtime; conversely, a JAR with high-version entries in its multi-release section for newer JDKs does not necessarily break older runtimes.

## 7. Finding loaded classes and the offending artifact

When an application has multiple versions of the same library, analyzing the wrong JAR can lead to incorrect conclusions. On HotSpot/OpenJDK JDK 9 and later, enable class loading logs in the test environment:

~~~bash
java -Xlog:class+load=info -cp app.jar com.example.Main
~~~

For older JDKs:

~~~bash
java -verbose:class -cp app.jar com.example.Main
~~~

Logs help identify which JAR or directory a class was loaded from. Then run javap and the scanner on that exact artifact. If the error only occurs in one feature, execute that flow to trigger loading of the relevant classes; successful startup does not prove the entire dependency graph is compatible.

When the runtime involves custom class loaders, plugin loaders, an application server, or module layers, the class source may not be as simple as the launch command's classpath. Combine class loading logs with loader configuration and deployment details.

## 8. Strategies for handling dependencies exceeding the runtime floor

After identifying the offending artifact and class, choose a resolution according to the product's support contract.

### 8.1. Using a dependency version that still supports the target runtime

Find an older release with a matching support matrix and verify the bytecode of the artifact and its transitive dependencies. Pin the specific version, check security/bug fixes, and record an expiration window if this is an interim workaround.

Do not downgrade blindly. Older versions may contain vulnerabilities or bugs that have since been fixed; weigh the risks and select a vendor-supported release.

### 8.2. Selecting the appropriate variant

Some libraries publish multiple variants or multi-release JARs. Select the appropriate variant for the target runtime, verifying metadata and actual entries. With Gradle, check variant attributes such as org.gradle.jvm.version if the publisher provides Gradle Module Metadata. With Maven, verify the actual artifact/version classifier or profile published by the vendor.

Do not assume all repositories or consumers use the same metadata. Inspect the resolved file and the bytecode inside it.

### 8.3. Requesting upstream to release an artifact matching the baseline

If a library declares Java 17 support but its base classes are built as major 65, provide concrete evidence to upstream: artifact coordinates, checksum, class entry, major/minor version, target runtime, and error message. The vendor can re-release the artifact with --release 17 or adjust the support matrix.

Only rebuild from source when you have permission and full control over the build/dependencies. Compiling the library's source with --release 17 does not automatically fix transitive dependencies that still contain Java 21 bytecode.

### 8.4. Raising the application's runtime floor

If the new dependency genuinely requires Java 21 and the product can upgrade its runtime, update the application's support statement, toolchain, container image, CI/CD, deployment, testing, and operations guides. Verify that all related processes also meet the new baseline, including batch jobs, workers, and administrative tools.

This is a change to the product's support scope; evaluate consumers still running Java 17 before rollout.

### 8.5. Isolating the dependency into a separate process

If the main application must continue running on Java 17 while one component only supports Java 21, you can isolate it into an independent process/service running Java 21 and communicate via an API or message contract. This establishes a clear runtime boundary, though it increases operational, communication, observability, and distributed error-handling overhead.

### 8.6. Do not use shading or bytecode downgrading as a default solution

Shading/relocation renames packages or classes to avoid conflicts; it does not lower the class-file version or backport new APIs. Bytecode downgrading tools can alter the header, but they cannot synthesize equivalent older Java APIs, nor do they guarantee correct semantics, verifier, or module behavior. Only consider these techniques when there is a verified engineering procedure for the exact library and runtime.

## 9. Testing dependencies on the lowest declared runtime

To prove an application supports Java 17, you need to test on an actual Java 17 runtime or an equivalent supported runtime. A successful build on JDK 21 is not enough.

A testing strategy may include:

1. Resolving a clean dependency graph from configured repositories; recording artifact coordinates and checksums.
2. Scanning class-file versions of runtime JARs, distinguishing base entries from multi-release entries.
3. Compiling application source with --release 17 or equivalent build configuration.
4. Running tests on JDK 17 using a pinned executable/container image.
5. Exercising functional flows that may load optional or lazy-loaded dependencies.
6. Inspecting class loading logs when needed to identify the actual artifact.
7. Running integration/contract tests involving external systems, TLS, reflection, and relevant module access.
8. Repeating across representative deployment environments and preserving evidence.

A bytecode scanner is a useful static filter, but it does not replace runtime execution testing. A dependency may have a compatible class version yet still call APIs unavailable on Java 17; conversely, a high class version residing in a multi-release branch meant for Java 21 may be completely valid for a Java 17 runtime.

## 10. Checklist for investigating dependencies with overly new bytecode

- [ ] Identified the declared runtime floor for the application and each critical library.
- [ ] Obtained the dependency graph and the actual resolved artifact versions.
- [ ] Checked transitive dependencies on the runtime classpath.
- [ ] Scanned the class-file major/minor versions of the relevant JARs.
- [ ] Distinguished base classes from entries in multi-release JARs and verified the manifest.
- [ ] Identified the specific offending class and its source artifact.
- [ ] Distinguished UnsupportedClassVersionError from API linkage, classpath, and module errors.
- [ ] Checked preview class files if present.
- [ ] Evaluated Java SE APIs and other dependencies beyond the class-file version.
- [ ] Selected the appropriate solution: older version, correct variant, upstream fix, raising the runtime floor, or isolating into a separate process.
- [ ] Ran the application and functional flows on the lowest supported runtime.
- [ ] Saved the artifact/version/checksum, verification commands, and test results.

## 11. Conclusion

A library truly meets its declared minimum Java level only when the classes selected by the target runtime have compatible bytecode and APIs, and the entire dependency graph operates properly on that runtime. Inspect resolved artifacts, scan class-file versions, understand multi-release JARs properly, identify which classes are actually loaded, and run functional flows on the lowest supported runtime. When overly new bytecode is detected, address it at the dependency source or explicitly adjust the runtime floor; do not rely on your application compiling successfully to conclude that a library is compatible.