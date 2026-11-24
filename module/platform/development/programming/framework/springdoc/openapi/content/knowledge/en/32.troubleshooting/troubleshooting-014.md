# NoSuchMethodError, ClassNotFoundException, and Version Conflicts

Errors such as `NoSuchMethodError`, `ClassNotFoundException`, and `NoClassDefFoundError` commonly arise when a Spring Boot application is compiled against one set of libraries yet loads a different set of classes at runtime. Causes include transitive dependencies picking the wrong version, a library missing from the runtime classpath, two JARs containing the same class, application packaging differing from IDE run settings, or Spring/springdoc components not belonging to the same compatibility matrix.

Do not fix these errors by adding random dependencies or forcing every library to the latest version. Determine which class or method the JVM is looking for, which JAR is actually loaded, which dependency pulls that JAR into runtime, and which version fits the running Spring Boot version.

This lesson helps distinguish class-loading and binary-linkage errors, trace dependency graphs with Maven/Gradle, align Spring Boot with springdoc-openapi and Swagger libraries, and verify the exact deployed artifact.

## 1. Distinguishing Three Common Errors

The error names sound similar, yet when they occur and how to investigate them differ.

| Error | Kind | Core meaning | Common sign |
| --- | --- | --- | --- |
| `ClassNotFoundException` | Checked exception | Code asked a `ClassLoader` to load a class by name and no definition was found | `Class.forName` or provider/plugin config error caused by missing class |
| `NoClassDefFoundError` | `LinkageError` | JVM needed a class definition during linking or execution, yet the class is absent at runtime | App compiled fine, yet startup or invoking a code path misses a class |
| `NoSuchMethodError` | `LinkageError` | Bytecode invokes a method, yet the class loaded at runtime lacks a method with the matching descriptor | Compiles fine, runtime reports a specific method does not exist |

Both `LinkageError` types usually point to a mismatch between the API bytecode compiled against and the class definition the JVM actually loads. `ClassNotFoundException` typically indicates a failed dynamic class-load by name; it does not by itself prove the dependency graph has two versions.

## 2. `ClassNotFoundException`: Class Loaded by Name Could Not Be Found

`ClassNotFoundException` is thrown when code invokes class loading by name, such as:

- `Class.forName("com.example.SomeType")`.
- `ClassLoader.loadClass("com.example.SomeType")`.
- `ClassLoader.findSystemClass("com.example.SomeType")` when called from an appropriate subclass.

For example:

~~~java
public class DriverLoader {

    public Object load(String driverClassName)
            throws ReflectiveOperationException {
        Class<?> driverClass = Class.forName(driverClassName);
        return driverClass.getDeclaredConstructor().newInstance();
    }
}
~~~

If the class name is misspelled, the JAR containing the class is undeclared, the dependency sits in test scope, or the classloader cannot see the JAR, that call can throw `ClassNotFoundException`.

With Spring Boot and springdoc, this error can occur when:

- Configuring a plugin, serializer, or converter by class name in properties.
- An integration library tries to load an optional class while the corresponding dependency is absent at runtime.
- A dependency is declared with `test` or `provided` scope and is not packaged as expected.
- The application runs inside an application server whose classloader differs from the IDE.
- A module or plugin creates its own `ClassLoader` and cannot see application dependencies.

Extract the exact class name from the exception, find which JAR must supply that class, then verify whether that JAR is inside the runtime artifact and visible to the classloader.

## 3. `NoClassDefFoundError`: JVM Needs a Class Yet Cannot Link It

`NoClassDefFoundError` is a `LinkageError`. The JVM or `ClassLoader` needs a class definition during method invocation, object instantiation, or bytecode linking, yet cannot find the required definition. A classic case is a class present at compile time but absent at runtime.

For example:

~~~java
public class ApiFacade {

    public ApiResult execute(ApiClient client) {
        return client.call();
    }
}
~~~

If `ApiFacade` was compiled while `ApiClient` existed yet the deployed JAR omits `ApiClient`, the JVM can throw `NoClassDefFoundError` when resolving that class.

Another form to watch for is:

~~~text
java.lang.NoClassDefFoundError: Could not initialize class com.example.SomeConfiguration
~~~

This case can originate from an error during a static initializer or first-time class initialization. Find the first exception—often `ExceptionInInitializerError` or an underlying cause—rather than editing dependencies solely based on the subsequent `NoClassDefFoundError` message.

## 4. `NoSuchMethodError`: Class Is Present Yet Lacks the Method Bytecode Expects

`NoSuchMethodError` occurs when code compiled against a method present at compile time, yet runtime loads a class lacking that matching method.

Illustrative example:

~~~java
// API library version 2 has a new method.
public class DocumentFactory {
    public Document create(String name, boolean includeExamples) {
        return new Document(name, includeExamples);
    }
}
~~~

Another module compiled against API version 2 calls:

~~~java
Document document =
    factory.create("Orders", true);
~~~

If runtime loads `DocumentFactory` from API version 1 having only `create(String)`, the bytecode still requests the `create(String, boolean)` descriptor and the JVM throws `NoSuchMethodError`.

The example above illustrates binary linkage. In a real project, read the full method name, parameter types, and return type in the error message. Then identify which JAR supplies the class containing that method.

Not every source change causes `NoSuchMethodError`. The JVM links by method name and descriptor. Changing overloads, parameter types, return types, or `static`/instance modifiers can trigger different binary compatibility errors such as `NoSuchMethodError`, `IncompatibleClassChangeError`, or `AbstractMethodError`.

## 5. Related Linkage Errors to Recognize

When troubleshooting `NoSuchMethodError`, watch for sibling errors:

| Error | Sign | Investigation direction |
| --- | --- | --- |
| `NoSuchFieldError` | Field referenced by bytecode is absent from runtime class | Compare JAR versions and field descriptors |
| `AbstractMethodError` | Runtime class lacks an implementation for an abstract method called by caller | Check interface, implementation, and dependency versions |
| `IncompatibleClassChangeError` | Incompatible change between class/interface or `static`/instance | Inspect binary API between compile and runtime |
| `IllegalAccessError` | Code accesses a class/member no longer permitted | Check visibility, modules, and library versions |
| `NoClassDefFoundError` | Required class definition missing or failed initialization | Check runtime classpath and initial initialization error |

Do not lump these errors together as "missing dependency." In some cases the class is present while its binary layout changed.

## 6. Direct Dependencies vs Transitive Dependencies

A direct dependency is a library declared in the application's build file. A transitive dependency is pulled in by another dependency.

For example:

~~~text
application
├── springdoc-openapi-starter-webmvc-ui
│   ├── springdoc-openapi-starter-webmvc-api
│   ├── swagger-core
│   └── swagger-ui
└── legacy-reporting-library
    └── swagger-annotations
~~~

If `legacy-reporting-library` requests a different Swagger annotation version than springdoc uses, the build tool must mediate the conflict. The final dependency graph may pick only one version; if the chosen version is incompatible with the other library's bytecode, runtime failures can happen.

Therefore, reading only direct dependencies in `pom.xml` or `build.gradle` is insufficient. Inspect the resolved graph for the exact configuration running the application.

## 7. Understanding Compile Classpath vs Runtime Classpath

Compile classpath and runtime classpath can differ:

- `compileClasspath` holds libraries needed to compile source code.
- `runtimeClasspath` holds libraries needed when running the application.
- `testCompileClasspath` and `testRuntimeClasspath` serve tests and may hold libraries absent from production.
- `buildscript`/plugin classpath is the environment running build plugins, not the application runtime classpath.

A dependency added only to `testImplementation` or Maven `test` scope may let tests pass while remaining absent from the production executable.

When an error occurs only after packaging, inspect the runtime classpath and JAR/container image contents. Do not look only at the compile classpath.

## 8. Aligning Spring Boot and springdoc-openapi First

springdoc aligns its major versions with Spring Boot major versions. The project's current compatibility matrix lists:

| Spring Boot | springdoc-openapi line |
| --- | --- |
| 4.1.x | 3.1.x to 3.2.x |
| 4.0.x | 3.0.x |
| 3.5.x | 2.8.x to 2.10.x |
| 3.4.x | 2.7.x to 2.8.x |
| 3.3.x | 2.6.x |
| 3.2.x | 2.3.x to 2.5.x |
| 3.1.x | 2.2.x |
| 3.0.x | 2.0.x to 2.1.x |
| 2.x and 1.x | 1.8.0 is the last open-source line |

This matrix reflects lines built and tested by springdoc, not a guarantee that every patch version within a major line is interchangeable without testing. When upgrading Spring Boot, pick springdoc for the matching Boot line and check release notes for the specific version.

For example, a Spring Boot 3.x application should not use springdoc 3.x merely because the version number is higher. The springdoc 3.x line targets Spring Boot 4; springdoc 2.x targets Spring Boot 3.

## 9. Do Not Manually Upgrade Spring Framework Underneath Spring Boot

Spring Boot provides dependency management tested as a cohesive set of versions. The `spring-boot-dependencies` BOM manages Spring Framework and many integration libraries so components work together.

If an application runs Spring Boot 3.5.x yet forces `spring-core` or `spring-web` to a version from another Boot line, the classpath can contain inconsistent APIs. A library compiled against a newer Spring Framework method while runtime loads an older module can trigger `NoSuchMethodError`.

Principles:

- Pick the Spring Boot version as the anchor for the Spring ecosystem.
- Use the BOM from that exact Spring Boot release to manage BOM-owned dependencies.
- Override versions only with clear justification and verified compatibility.
- Do not declare individual versions for Spring Framework modules unnecessarily.
- When upgrading a third-party library outside the BOM, check its compatibility with Spring Boot and springdoc.

## 10. Maven: Using the Spring Boot Parent or Importing the BOM

With Maven, the simplest approach is inheriting the Spring Boot parent:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.1.2</version>
    <relativePath/>
</parent>
~~~

Then declare starters without versions when managed by the parent:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webmvc</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jackson</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
        <version>3.2.0</version>
    </dependency>
</dependencies>
~~~

This example uses Spring Boot 4.1.2 and springdoc 3.2.0 per the current matrix. For Boot 3, replace springdoc with the matching 2.x line; do not copy this version into a Boot 3 project.

If the project cannot inherit the parent, import the BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>4.1.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Importing the BOM still provides Spring Boot version management without auto-configuring every plugin as the starter parent does. Configure compiler, Surefire, and Spring Boot Maven Plugin individually if the project manages its own build.

## 11. Gradle: Using Spring Boot Dependency Management or Platform

Gradle can use the Spring Boot plugin alongside the dependency management plugin, or native BOM support.

Kotlin DSL example with `platform`:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "4.1.2"
}

dependencies {
    implementation(platform(
        "org.springframework.boot:spring-boot-dependencies:4.1.2"
    ))

    implementation("org.springframework.boot:spring-boot-starter-webmvc")
    implementation("org.springframework.boot:spring-boot-starter-jackson")
    implementation("org.springdoc:springdoc-openapi-starter-webmvc-ui:3.2.0")
}
~~~

The Spring Boot BOM manages dependencies in Boot's catalog. springdoc is an external dependency outside the BOM in this example, so its version is declared per the compatibility matrix.

If using the `io.spring.dependency-management` plugin, the Spring Boot plugin can import the corresponding BOM automatically. There is no need to declare both `platform` and import the same BOM via the plugin once the project has chosen one clear version management mechanism.

## 12. Avoid Arbitrarily Forcing `swagger-core` and `swagger-annotations` Versions

springdoc depends on OpenAPI/Swagger libraries such as `swagger-core`, `swagger-annotations`, and related modules. These versions must be compatible with the running springdoc line.

A common mistake is adding directly:

~~~xml
<dependency>
    <groupId>io.swagger.core.v3</groupId>
    <artifactId>swagger-annotations</artifactId>
    <version>2.x.y</version>
</dependency>
~~~

while the springdoc starter pulls in a different version. If the direct version wins dependency mediation, runtime may load an annotation/model API incompatible with springdoc's bytecode or the remaining Swagger modules.

Follow this sequence:

1. Check which `swagger-core` and `swagger-annotations` versions the springdoc starter requires.
2. Identify which direct dependency or other library overrides the version.
3. Remove the version override if no longer justified.
4. If another version is required, check compatibility across all `swagger-core` modules, not just a single artifact.
5. Re-run the dependency tree and test the OpenAPI endpoint.

Do not add `swagger-annotations` separately just because the IDE reports a missing import when the springdoc starter already supplies it transitively. If the project chooses to declare direct dependencies by convention, let dependency management select the right version.

## 13. Maven: Viewing the Resolved Dependency Tree

Basic command:

~~~bash
./mvnw dependency:tree
~~~

View runtime scope only:

~~~bash
./mvnw dependency:tree -Dscope=runtime
~~~

Filter libraries related to Spring, springdoc, and Swagger:

~~~bash
./mvnw dependency:tree -Dverbose -Dincludes=org.springframework:*,org.springdoc:*,io.swagger.core.v3:*
~~~

The Dependency Plugin supports exporting the graph to a file:

~~~bash
./mvnw dependency:tree -DoutputType=json -DoutputFile=target/dependency-tree.json
~~~

JSON output requires a Maven Dependency Plugin version that supports that format. If Maven reports `outputType=json` is unrecognized, check the plugin version; you can use default text output.

In the output, watch for:

- Which version is selected per artifact.
- Branches introducing an artifact into the graph.
- Omitted nodes or version conflicts.
- `compile`, `runtime`, `provided`, and `test` scopes.
- Artifacts appearing via multiple dependency paths.

When you need the effective configuration after applying parents and profiles, run:

~~~bash
./mvnw help:effective-pom
~~~

Effective POM reveals which `dependencyManagement`, properties, and profiles control the final versions.

## 14. Gradle: Viewing Dependencies and Version Selection Reasons

List the runtime graph:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Inspect Spring Framework specifically:

~~~bash
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
~~~

Inspect springdoc specifically:

~~~bash
./gradlew dependencyInsight --dependency springdoc-openapi --configuration runtimeClasspath
~~~

Inspect Swagger:

~~~bash
./gradlew dependencyInsight --dependency swagger-core --configuration runtimeClasspath
~~~

Dependency insight shows the chosen version, which dependencies requested other versions, and why Gradle picked the final version—such as conflict resolution, constraints, platform, or forced rules.

Do not inspect only `compileClasspath`. Errors occurring when running the executable require inspecting `runtimeClasspath`. If a build plugin fails, inspect `buildEnvironment` because the plugin classpath is separate from the application's runtime classpath.

## 15. Maven Enforcer and Dependency Convergence

Maven Enforcer provides the `dependencyConvergence` rule to catch artifacts requested at multiple versions across different branches of the dependency tree.

Example configuration:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>3.7.0</version>
    <executions>
        <execution>
            <id>enforce-dependency-convergence</id>
            <goals>
                <goal>enforce</goal>
            </goals>
            <configuration>
                <rules>
                    <dependencyConvergence/>
                </rules>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

This rule is useful for catching graphs demanding multiple versions of the same artifact. However, dependency convergence does not prove all dependencies are binary compatible. A graph with a single version can still select an incompatible version for a caller.

If valid exceptions exist, configure `includes`/`excludes` or scope explicitly and document the reason. Do not disable the whole rule merely because one dependency conflicts.

## 16. Gradle Constraints and Avoiding Global Forced Versions

Gradle supports dependency constraints to control direct or transitive dependency versions:

~~~kotlin
dependencies {
    constraints {
        implementation("com.example:compatibility-module") {
            version {
                strictly("2.4.1")
            }
            because("Version verified against application runtime")
        }
    }
}
~~~

This is only an example of constraint syntax. In Spring Boot applications, prefer BOM/platform and use `strictly` only after verifying the exact version required.

Avoid `resolutionStrategy.force` across broad Spring or Swagger modules. Forcing can make the graph look uniform while pushing libraries onto versions they were never built or tested with. Fix the conflicting dependency or add a narrowly scoped constraint with clear justification.

## 17. Use Exclusions Only After Identifying the Offending Branch

If a legacy library pulls in an incompatible transitive dependency, you can exclude that dependency at that exact branch and declare a verified replacement version elsewhere.

Maven example:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>legacy-integration</artifactId>
    <version>5.1.0</version>
    <exclusions>
        <exclusion>
            <groupId>io.swagger.core.v3</groupId>
            <artifactId>swagger-annotations</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

Use this example only after proving `legacy-integration` pulls the conflicting version and a compatible version is managed in the appropriate place. An exclusion does not supply a replacement dependency by itself. Removing a module whose classes code still needs turns a version error into a missing-class error.

After adding an exclusion, re-run the dependency tree and runtime tests. Verify that another dependency actually supplies the classes the library requires.

## 18. Checking Which Class the JVM Actually Loads

The dependency graph shows which JARs are resolved, yet with multiple classloaders or differing packaging environments, confirm where the runtime class comes from.

You can print the `CodeSource` of a loaded class:

~~~java
import java.security.CodeSource;

public final class ClassOrigin {

    public static void print(Class<?> type) {
        CodeSource source = type.getProtectionDomain().getCodeSource();
        System.out.println(
            type.getName() + " -> "
                + (source == null ? "unknown" : source.getLocation())
        );
    }
}
~~~

Invoke it with representative classes such as `SpringApplication`, Spring MVC classes, or springdoc/swagger-core classes mentioned in the stack trace. `CodeSource` may be null in some classloaders or modules, making it useful evidence though not always populated.

With JDK 9 or newer, enable class-loading logs:

~~~bash
java -Xlog:class+load=info -jar app.jar
~~~

With JDK 8, a common option is:

~~~bash
java -verbose:class -jar app.jar
~~~

Search the logs for the relevant class to see which location the classloader loaded it from. Use logging selectively because output can be huge.

## 19. Inspecting Executable JAR Contents

Running inside an IDE may use a different classpath than an executable JAR. In Spring Boot executable JARs, dependencies are typically packaged under `BOOT-INF/lib`.

List contents:

~~~bash
jar tf target/application.jar
~~~

Filter relevant libraries on Windows:

~~~powershell
jar tf target/application.jar | Select-String 'BOOT-INF/lib/(spring|springdoc|swagger|jackson)'
~~~

On Linux/macOS:

~~~bash
jar tf target/application.jar | grep -E 'BOOT-INF/lib/(spring|springdoc|swagger|jackson)'
~~~

Verify:

- `spring-core`, `spring-web`, `spring-context` share the line managed by Spring Boot.
- Only one version of each critical module exists inside the executable.
- The springdoc starter and companion modules share the same version line.
- `swagger-core`, `swagger-models`, and `swagger-annotations` are not unintentionally overridden.
- Jackson modules match the Jackson core/databind loaded by the application.

If the JAR is right yet the container still fails, check whether the Docker image copied the right new artifact. An old image or layer cache can retain a different executable than the one just inspected.

## 20. Checking Compile-Time API with `javap`

When `NoSuchMethodError` names a class and method, `javap` can check whether that method exists in the JAR under inspection.

For example:

~~~bash
javap -classpath path/to/library.jar com.example.DocumentFactory
~~~

If the expected method is absent from output, that JAR does not supply the API bytecode calls. Compare:

1. JAR used on compile classpath.
2. JAR selected on `runtimeClasspath`.
3. JAR actually inside the executable or container.

You can run `javap -c -verbose` on the caller class to inspect bytecode and referenced method descriptors. Read the JVM descriptor rather than matching only method names, because overloads share a name yet differ in signature.

## 21. Checking `javax` vs `jakarta` When Upgrading Spring Boot

Spring Boot 3 migrated the Spring ecosystem to Jakarta EE APIs. Packages such as:

- `javax.servlet` moved to `jakarta.servlet`.
- `javax.validation` moved to `jakarta.validation`.
- `javax.persistence` moved to `jakarta.persistence`.

Classes with the same simple name yet different packages are completely different classes to the JVM. A library compiled against `javax` APIs is not automatically compatible with `jakarta` APIs just because their functionality is similar.

Common errors:

- `ClassNotFoundException` or `NoClassDefFoundError` for `javax.servlet.*` when runtime only has Jakarta Servlet.
- Incompatible method parameter or return types because descriptors contain `javax` instead of `jakarta`.
- Older frameworks failing to recognize Jakarta annotations.
- Old and new dependencies pulling both namespaces into one app, causing unpredictable behavior.

When upgrading from Boot 2 to Boot 3, upgrade integration libraries, validation providers, persistence providers, servlet containers, and `javax`-using modules together. Do not re-add `javax` APIs just to silence error messages once the application moved to Jakarta.

When upgrading further to Spring Boot 4, also check modularization and Jackson 3:

- Current MVC starter is `spring-boot-starter-webmvc`; `spring-boot-starter-web` is retained as deprecated for transition.
- Default JSON starter is `spring-boot-starter-jackson`.
- Jackson 3 uses group/package `tools.jackson`; Jackson 2 uses `com.fasterxml.jackson`. An exception is `jackson-annotations`, which continues using group `com.fasterxml.jackson.core` and package `com.fasterxml.jackson.annotation`.
- Libraries supporting only Jackson 2 may need a separate `ObjectMapper` or Spring Boot 4's Jackson 2 compatibility module. Do not force Jackson 2 and Jackson 3 to a single version because they are distinct API lines.

When seeing `NoClassDefFoundError` or `NoSuchMethodError` around `ObjectMapper`, `JsonMapper`, serializers, or customizers, identify which mapper the application uses and which dependency pulls each Jackson major into runtime. Consult the Boot 4 migration guide before adding compatibility modules.

## 22. Distinguishing Application Errors from Build Plugin Errors

A project has multiple classpaths:

| Classpath | Used for |
| --- | --- |
| Application compile classpath | Compiling application source code |
| Application runtime classpath | Running the application |
| Test runtime classpath | Running tests |
| Maven plugin classpath | Running Maven plugins |
| Gradle buildscript/plugin classpath | Running Gradle plugins |

If an error occurs while running an OpenAPI generation plugin, the fault may lie on the plugin classpath rather than application runtime. Conversely, a build plugin succeeding does not prove application runtime has no conflicts.

With Gradle, run:

~~~bash
./gradlew buildEnvironment
~~~

to inspect buildscript dependencies. With Maven, inspect plugins and plugin dependencies in the effective POM or `dependency:resolve-plugins` as needed.

Record the exact phase where the error happens: compile, test, package, plugin execution, startup, or endpoint request. The failing phase narrows which classpath needs investigation.

## 23. Distinguishing Classloader Errors from Version Errors

Not every `ClassNotFoundException` is solved by bumping a version.

Some environments have multiple classloaders:

- Spring Boot DevTools uses a restart classloader.
- Application servers use separate classloaders for server and each deployment.
- Plugin architectures isolate classloaders per plugin.
- OSGi or Java module layers enforce visibility boundaries.
- Thread context classloader can differ from the executing class's classloader.

If the JAR is inside the archive yet `ClassLoader` cannot see the class, investigate:

1. Which `ClassLoader` performs the load?
2. What is the current thread context classloader?
3. Is the class inside a module/classloader allowed to be accessed?
4. Is the dependency packaged under another classloader?
5. Do IDE/devtools construct a different classloader than the executable?

Do not alter `Thread.currentThread().setContextClassLoader()` application-wide without identifying which library needs the context loader. Global changes can affect `ServiceLoader`, logging, JDBC drivers, or other plugins.

## 24. Checking `HttpMessageConverter` When Swagger UI Fails to Render

An issue that is not necessarily `NoSuchMethodError` can mislead users into suspecting a springdoc version conflict: Swagger UI reports unable to render definition after an application overrides `HttpMessageConverter`.

The springdoc FAQ notes that when replacing Spring Boot's default `HttpMessageConverter` list, `ByteArrayHttpMessageConverter` and proper converter ordering must be preserved. If converters handling OpenAPI responses are altered, `/v3/api-docs` may return the wrong content or media type.

Test directly:

~~~bash
curl -i http://localhost:8080/v3/api-docs
~~~

Verify:

- Status code is 200.
- `Content-Type` matches JSON.
- Body is valid JSON, not an HTML error/login page.
- Response was not altered by a custom converter.

This is an HTTP serialization/negotiation error; do not rush to fix it by forcing `swagger-core` versions.

## 25. Parameters Missing Names After Upgrading Spring Boot

If the OpenAPI document stops generating expected parameter names after upgrading to Spring Boot 3.2, check Java parameter name discovery and compiler settings.

The springdoc FAQ notes you must compile with `-parameters` to preserve parameter names in bytecode when the application relies on parameter name discovery.

Maven example:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
~~~

Gradle example:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

This is a compile-time metadata issue, not necessarily a dependency conflict. Inspect class files and the OpenAPI document before changing library versions.

## 26. Ordered Diagnostic Procedure

When hitting `NoSuchMethodError`, `ClassNotFoundException`, or `NoClassDefFoundError`, follow this sequence:

1. Save the entire stack trace, including the initial cause and full class/method names.
2. Identify whether the error happens at compile, test, package, startup, or runtime request.
3. Identify the exact class or method the JVM cannot find.
4. Identify which artifact/JAR is supposed to supply that class or method.
5. Inspect `compileClasspath` and `runtimeClasspath`.
6. Trace the dependency path introducing the currently selected version into the graph.
7. Compare Spring Boot, springdoc, Spring Framework, Swagger, and Jackson versions.
8. Inspect the actual executable JAR/container.
9. Check class origin or classloaders if the dependency graph looks right yet the error persists.
10. Fix the dependency declaration, BOM, constraint, or exclusion at the exact conflicting source.
11. Delete stale build outputs and rebuild the artifact from current source.
12. Run the packaged artifact itself, not only inside the IDE.
13. Verify OpenAPI JSON, Swagger UI, and related business endpoints.

Do not change multiple versions at once. Change one cause, build a fresh artifact, and verify that the error disappeared without introducing another linkage error.

## 27. Example: Investigating a `NoSuchMethodError` in springdoc

Suppose the application throws:

~~~text
java.lang.NoSuchMethodError:
  'some.Type some.library.Api.method(java.lang.String)'
~~~

Do not guess that springdoc has a bug. Proceed as follows:

**Step 1 — Identify the class owning the method**

Read the stack trace to find both caller class and method-owning class. Record package, method name, and parameter types.

**Step 2 — Locate the artifact owning the class**

Inspect the dependency tree to see which artifact supplies that package. Check whether multiple versions exist or a legacy library pulls an old version.

**Step 3 — Verify runtime version**

Use `dependencyInsight` or runtime-scoped `dependency:tree` to check the chosen version. Inspect the packaged JAR to ensure the executable contains that exact version.

**Step 4 — Compare binary API**

Run `javap` on the runtime JAR and compile JAR if available. Confirm whether the method descriptor exists at runtime.

**Step 5 — Fix the version-managing source**

If a Spring Boot BOM-managed module is overridden, remove the unnecessary override. If the springdoc major mismatches Boot, select the right major. If a legacy dependency pulls an old version, upgrade the library or apply a controlled exclusion.

**Step 6 — Verify**

Run the application from the new executable JAR/container, call `/v3/api-docs` and `/swagger-ui.html`, then run key endpoint tests.

## 28. Quick Diagnostic Table

| Message | Check first | Check next |
| --- | --- | --- |
| `ClassNotFoundException: com.example.X` | Class name and `Class.forName`/`loadClass` call site | Runtime scope, classloader, and JAR containing `X` |
| `NoClassDefFoundError: com/example/X` | Whether class `X` is inside the executable | Optional/provided dependencies, packaging, and earlier initialization errors |
| `NoClassDefFoundError: Could not initialize class` | First exception in static initializer | Configuration, static initialization, and root cause |
| `NoSuchMethodError: Y.foo(...)` | Runtime JAR of class `Y` | Compile/runtime versions and method descriptor |
| `NoSuchFieldError` | Runtime JAR and field descriptor | Caller/callee versions |
| `AbstractMethodError` | Interface and implementation | Dependency versions and binary compatibility |
| `ClassCastException` with same class name | Whether two classloaders loaded two copies of the class | Class origin, DevTools, and application server |
| Swagger UI unable to render definition | `/v3/api-docs` response | JSON body, content type, converters, security, and CORS |
| Parameter missing name in document | Whether compiler preserves parameter names | `-parameters` option and `@Parameter` annotation |

## 29. Version Conflict Prevention Checklist

- [ ] Spring Boot version is chosen explicitly and used as the anchor for dependency management.
- [ ] springdoc major matches Spring Boot major.
- [ ] Individual Spring Framework modules are not overridden without verified justification.
- [ ] `swagger-core` and `swagger-annotations` versions are not accidentally forced.
- [ ] Jackson modules are managed consistently.
- [ ] Production dependencies are not left only in `test` scope.
- [ ] Checked `runtimeClasspath`, not just `compileClasspath`.
- [ ] Inspected `dependency:tree` or `dependencyInsight` when upgrading versions.
- [ ] Maven Enforcer or Gradle constraints are used purposefully.
- [ ] Exclusions have clear justification and replacement dependencies are verified.
- [ ] No two JARs of different versions supply the same critical classes.
- [ ] Executable JAR/container contains the resolved dependencies.
- [ ] Tested the packaged artifact, not only running in an IDE.
- [ ] Checked classloaders and class origin when the dependency graph does not explain the error.
- [ ] Smoke-tested OpenAPI JSON, Swagger UI, and API runtime after upgrades.

## References

- [Java API – NoSuchMethodError](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/NoSuchMethodError.html)
- [Java API – ClassNotFoundException](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ClassNotFoundException.html)
- [Java API – NoClassDefFoundError](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/NoClassDefFoundError.html)
- [springdoc-openapi – Compatibility Matrix and FAQ](https://springdoc.org/faq.html)
- [springdoc-openapi v2 – Compatibility Matrix and FAQ](https://springdoc.org/v2/faq.html)
- [Spring Boot – Build Systems and Dependency Management](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
- [Spring Boot 4.0 – Migration Guide, modular starters and Jackson 3](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
- [Spring Boot – Gradle Dependency Management](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html)
- [Apache Maven Dependency Plugin – dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
- [Apache Maven Enforcer – Dependency Convergence](https://maven.apache.org/enforcer/enforcer-rules/dependencyConvergence.html)
- [Gradle – Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html)
- [Gradle – Dependency Constraints](https://docs.gradle.org/current/userguide/dependency_constraints.html)
