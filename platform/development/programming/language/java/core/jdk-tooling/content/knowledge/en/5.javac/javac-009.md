# Target release in javac

When developing Java applications, you may use a newer JDK to compile while still needing to produce a program that runs on an older Java version. For example, a development team might use JDK 21 while the product must run on Java 17 or Java 8. In such cases, the **target release** specifies the minimum Java version that the compiled bytecode and platform APIs target.

With modern `javac`, the recommended option is `--release`. This option coordinates three requirements: the Java language rules, the class file format, and the Java SE/JDK API set of the target version. Lowering only the bytecode version is not enough to guarantee compatibility.

## 1. What is a target release?

A Java release can be viewed through three compilation-related aspects:

1. **Source level:** the syntax and language features that the compiler allows in the source code.
2. **Class-file target:** the bytecode format written into `.class` files so that the target version's JVM can read them.
3. **Platform API:** the Java SE/JDK classes, interfaces, and methods that the source code is permitted to use.

For example, if an application must run on Java 17, it needs to:

- Write source code within the scope of the Java 17 language.
- Generate class files compatible with Java 17.
- Use only platform APIs that already exist in Java 17.

If you only generate Java 17 bytecode but call a method that was added in Java 21, the program may still compile on JDK 21 yet fail at runtime on Java 17, typically with `NoSuchMethodError` or `NoClassDefFoundError`.

## 2. Using javac --release

The `--release N` option instructs the compiler to compile for the specified Java SE version `N`:

~~~bash
javac --release 17 -d out src/com/example/Main.java
~~~

The command above means:

- Use Java 17 language rules.
- Generate class files targeting Java 17.
- Compile against the public supported Java SE/JDK API set of Java 17.

It can be combined with standard compilation options:

~~~bash
javac --release 17 -encoding UTF-8 -Xlint:all -d out src/com/example/Main.java
~~~

Meaning:

| Option | Purpose |
|---|---|
| `--release 17` | Selects the Java 17 platform as the target version |
| `-encoding UTF-8` | Reads source code using UTF-8 |
| `-Xlint:all` | Enables additional warning groups |
| `-d out` | Places class files into the `out` directory |

You can check which releases the current compiler supports with:

~~~bash
javac --help
~~~

The supported list depends on the JDK version in use. A compiler only supports the current release and several older releases; an older JDK cannot compile for a future release it does not yet know about.

`--release` was added in JDK 9. If you are using a JDK 8 or earlier compiler, this option is not available.

## 3. Distinguishing --release, -source, and -target

These three options are related but have different scopes.

| Option | Controls | Does not automatically guarantee |
|---|---|---|
| `-source N` | Syntax rules/language features of Java N | Bytecode format and Java N API set |
| `-target N` | Class file format version | The API set used by the source code |
| `--release N` | Source level, class-file target, and platform APIs of release N | Compatibility of external libraries or runtime behavior |

Example with the two legacy options:

~~~bash
javac -source 17 -target 17 -d out src/com/example/Main.java
~~~

The compiler checks Java 17 syntax and generates Java 17 target class files. However, if the compiler is running on JDK 21, JDK 21 APIs may still be visible in the compilation environment unless you explicitly specify the appropriate platform classes.

When using `-source`/`-target` on their own:

- For Java 8 and earlier platforms, you need to provide the corresponding platform classes via the boot class path options.
- For Java 9 and later, you can use `--system` to specify the module system of a suitable JDK.

That is why modern workflows usually prefer `--release`: the compiler automatically selects the corresponding API set, avoiding the situation where older bytecode references newer APIs.

Do not combine `--release` with `-source` or `-target` in the same compilation. These are mutually exclusive ways of selecting the target version.

## 4. Example: newer APIs can break compatibility

Consider the file `TargetReleaseDemo.java`:

~~~java
import java.util.List;

public class TargetReleaseDemo {
    public static void main(String[] args) {
        List<String> names = List.of("Java", "JDK");
        System.out.println(String.join(", ", names));
    }
}
~~~

The `List.of` method was introduced in Java 9.

### 4.1. Compiling for Java 8

~~~bash
javac --release 8 -d out-8 TargetReleaseDemo.java
~~~

The compiler reports an error because `List.of` is not part of the Java 8 API. This is the desired outcome: the error is caught at compile time rather than waiting for the program to run on Java 8.

### 4.2. Compiling for Java 11

~~~bash
javac --release 11 -d out-11 TargetReleaseDemo.java
java -cp out-11 TargetReleaseDemo
~~~

Output:

~~~text
Java, JDK
~~~

Java 11 has the `List.of` API, so this source code is valid. The generated class file targets Java 11.

### 4.3. Why using only -source and -target may not be enough

With a JDK 21 compiler, try:

~~~bash
javac -source 8 -target 8 -d out-legacy TargetReleaseDemo.java
~~~

The source code may be accepted because `-source 8` only restricts syntax, while the compiler still sees the JDK 21 APIs. The compiler can generate a Java 8 target class file, yet that class file references `List.of`.

When run on Java 8, the JVM can load the class file but cannot find the `List.of` method in `java.util.List`. The error only surfaces during linking or execution. A warning about the bootstrap class path is also a sign that the older API environment was not provided.

Using `--release 8` blocks this API reference right at the compilation step.

## 5. Class file versions and how to inspect them

Each Java generation has a class-file major version. Some common milestones:

| Java release | Major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

You can inspect a class file using `javap`:

~~~bash
javap -verbose -classpath out-11 TargetReleaseDemo
~~~

In the output, look for the line:

~~~text
major version: 55
~~~

Major version 55 corresponds to Java 11. This is how you verify the class file format that the compiler actually generated.

If an older JVM tries to run a class file with a major version newer than it supports, it may throw `UnsupportedClassVersionError`. This error is different from `NoSuchMethodError`:

- `UnsupportedClassVersionError`: the JVM cannot read the class file version.
- `NoSuchMethodError`: the class file is loaded, but during linking/execution, the referenced method does not exist in the loaded class.

## 6. Which APIs does --release restrict?

When compiling with `--release`, `javac` uses the supported Java SE and JDK APIs of the selected release. As a result, source code cannot accidentally call a newer platform API simply because the installed JDK compiler is a newer version.

This is useful when:

- Maintaining applications that run across multiple Java versions.
- Building shared libraries for multiple projects.
- Upgrading the build JDK without yet upgrading the production runtime version.
- Catching usage of newer APIs early in pull requests or build pipelines.

However, `--release` does not restrict the APIs of external libraries. If the classpath contains a library that only supports Java 21, compiling the application with `--release 17` does not automatically make that library compatible with Java 17.

You still need to check:

- The bytecode version of dependencies.
- The minimum Java version declared by the library vendor.
- The APIs that the library calls at runtime.
- Reflection, service loading, JNI, and dynamically loaded components.
- Whether build tools, annotation processors, and plugins have their own JDK requirements.

In addition, `--release` only allows using APIs documented for that release; you cannot use options that break module encapsulation to access internal JDK APIs as if they were supported public APIs.

## 7. Choosing a release based on project requirements

Do not choose a release simply because it is the newest JDK on your machine. Start from the actual deployment environment.

| Situation | How to choose |
|---|---|
| New application, standardized on Java 21 runtime | Use `--release 21` |
| Project compiled with JDK 21, but server runs Java 17 | Use `--release 17` |
| Library must support Java 8 | Use `--release 8` and ensure dependencies also support Java 8 |
| Project requires Java 11 | Use `--release 11` and test on a Java 11 runtime |
| Want to use APIs newer than the supported release | Upgrade the minimum runtime or replace the API with a compatible alternative |

For example, if the production server uses Java 17 while the development machine has JDK 21 installed:

~~~bash
java --version
javac --version
javac --release 17 -d out src/com/example/Main.java
~~~

The first two commands may display Java 21. That does not conflict with the compiler generating bytecode and targeting APIs for Java 17.

## 8. Compatibility verification workflow

A single successful compilation is not enough to prove that an application will run reliably on the target release. You can follow this workflow:

1. **Identify the minimum runtime:** check the deployment environment or product requirements to know whether it is Java 8, 11, 17, 21, or another version.
2. **Choose a suitable compiler:** use a JDK that supports the target release; newer compilers can typically compile for several older releases.
3. **Compile with --release:** for example, `javac --release 17 -d out ...`.
4. **Inspect the bytecode:** use `javap -verbose` and verify the major version.
5. **Check dependencies:** confirm that external libraries support the minimum Java version.
6. **Run tests on the target runtime:** use the exact corresponding JDK/JRE or a container environment with that version.
7. **Check the pipeline:** ensure IDEs, Maven/Gradle, CI, and release scripts all use a consistent release configuration.

You should test on the lowest actual runtime version that the product commits to supporting. Running on a newer JDK can mask missing API errors because newer runtimes still retain many older APIs.

## 9. Common errors

| Symptom | Cause | How to fix |
|---|---|---|
| `invalid source release` or unsupported release | The JDK compiler is too old or the release is not in the supported list | Run `javac --version` and `javac --help`; install a suitable JDK |
| `option --release not allowed with target` | Using `--release` together with `-target` or `-source` | Choose a single mechanism; prefer `--release` |
| `cannot find symbol` when using a newer API | The API does not exist in the target release | Replace with a compatible API or raise the release |
| `UnsupportedClassVersionError` | The runtime is older than the class-file version | Compile with the appropriate release or upgrade the runtime |
| `NoSuchMethodError` | Dependency/runtime is missing a method referenced by the bytecode | Check actual APIs and dependency versions; run tests on the target runtime |
| Works on development machine but fails in production | Development machine uses a newer runtime or a different classpath | Test in an environment matching production |
| Local build and CI produce different results | JDK compiler or release configuration is inconsistent | Lock the toolchain and build configuration in CI |

## 10. Usage notes

- Use `--release` for modern projects that need to support older Java versions.
- Do not confuse the JDK version used to run the compiler with the product's target release.
- Do not use `-target` alone to conclude that an application is API-compatible with an older runtime.
- Do not specify `--release` together with `-source` or `-target`.
- Verify supported releases using `javac --help` instead of assuming every JDK supports every older release.
- Check dependencies and run tests on the minimum runtime.
- Read `javap -verbose` output when you need to verify the actual major version.
- For applications using preview features, you must follow the separate `--enable-preview` rules and matching runtime version; preview APIs are not a long-term compatibility contract.

## 11. Key takeaways

`--release` is a key option for controlling compatibility when using `javac`. It simultaneously selects the language rules, class-file version, and platform APIs of the target release. `-source` only selects the source level; `-target` only selects the class file format. Combining source/target without providing the matching platform classes can produce older bytecode that still depends on newer APIs.

Compiling with the right release, verifying the class file, checking dependencies, and running tests on the minimum runtime are essential steps for reliably controlling Java compatibility.

Reference: [The javac Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html), sections `--release`, `--source`, `--target`, and *Compiling for Earlier Releases of the Platform*.
