# Reading Metadata with ASM and the Limits of Avoiding Class Loading in Spring Boot

## 1. Core Question: Why Can a Class Be Checked Without Loading It?

In Spring Boot, **auto-configuration** must decide whether a configuration fits the classpath. For example: only auto-configure JDBC when the required JDBC types are present; only create Jackson mechanisms when the appropriate Jackson types are present. Common conditions are `@ConditionalOnClass` and `@ConditionalOnMissingClass`.

However, there is a very practical problem: **how do you read information about a class containing references to an optional library without forcing the JVM to load that class itself too early?** If the framework had to load every configuration class just to discover annotations, references to absent dependencies could cause `NoClassDefFoundError`, `ClassNotFoundException`, or linkage errors before the condition can answer “not eligible”.

Spring Framework uses **ASM**, a Java bytecode reading library, to read `.class` file metadata without necessarily defining/loading that class into a `Class<?>` object in the JVM. As a result, classpath scanners and configuration analyzers can discover class names, annotations, superclasses, interfaces, and method metadata before having to work with real Java types.

However: **“reading metadata without loading the class” does not mean “Spring's entire startup will not load classes”, “optional code will never be linked”, or “missing any dependency is safe”**. Those limits are the most important part of this lesson.

~~~text
       Classpath: JAR / BOOT-INF/classes / classes directory
                              |
                              v
                      Resource / .class bytes
                              |
                ASM parses bytecode structure
                              |
          ClassMetadata / AnnotationMetadata / MethodMetadata
                              |
                  recognizes class + annotation
                              |
                    @ConditionalOnClass ?
                              |
                   +----------+----------+
                   |                     |
             class present         class missing
                   |                     |
             continue eval           skip config
                   |
              may reach step
            load/work with class
                   |
        JVM loading -> linking -> initialization
                   |
                  create bean
~~~

**Goal after this lesson:** you understand how Spring reads metadata using ASM, distinguish metadata scanning from class loading/linking/initialization, know how to write safe classpath conditions, pinpoint when avoiding class loading is not enough to protect code, and can run a Java 17/Spring Boot experiment yourself to verify it.

## 2. What Is ASM and How Does Spring Use It?

**ASM** is a Java bytecode manipulation library. A program can open a `.class` file as binary data and inspect constant pool entries, annotation tables, type signatures, and method structures without calling `Class.forName(...)` to load the class being read.

In Spring, several APIs are designed for this task:

| Component | Primary role | Notes |
| --- | --- | --- |
| `Resource` | Represents classpath, file, URL resources... | Can access the bytes of a `.class` file |
| `MetadataReader` | Gateway for reading a class's metadata | Provides `ClassMetadata` and `AnnotationMetadata` |
| `MetadataReaderFactory` | Creates `MetadataReader` by class name or `Resource` | Convenient API entry point |
| `SimpleMetadataReaderFactory` | Simple metadata-reading implementation | Reads the resource each time per factory behavior |
| `CachingMetadataReaderFactory` | Caches metadata reader results | Suitable when scanning many classes on a classpath |
| `ClassMetadata` | Class name, superclass, interfaces, flags... | Requires no instance of the class being read |
| `AnnotationMetadata` | Annotations on the class and related metadata | Can look up annotations by name |
| `MethodMetadata` | Method metadata (such as `@Bean` methods) | Does not require invoking the method |
| `org.springframework.asm.*` | ASM repackaged into Spring's namespace | Mostly infrastructure; no need to call directly for most apps |

You can view it simply:

~~~text
Resource (.class bytes)
    -> MetadataReaderFactory
       -> MetadataReader
          -> ClassMetadata
          -> AnnotationMetadata
             -> MethodMetadata if needed
~~~

Most applications **do not need to use low-level ASM themselves**. Reading `MetadataReader`/`AnnotationMetadata` is more appropriate when building class discovery tools, writing infrastructure libraries, or investigating scanners.

### Class Names Are Strings, Not Yet `Class<?>` Objects

When calling:

~~~java
MetadataReader reader =
    new SimpleMetadataReaderFactory()
        .getMetadataReader("example.optional.ExampleClient");
~~~

the factory attempts to locate the corresponding class resource, such as `example/optional/ExampleClient.class`, and read its metadata. If the resource does not exist, reading may throw an `IOException`; this is not the same situation as a `ClassNotFoundException` from `Class.forName`.

*This snippet illustrates the API; to run it requires importing `org.springframework.core.type.classreading.MetadataReader`, `SimpleMetadataReaderFactory`, handling `IOException`, and having the corresponding class/resource.*

Do not infer from `getMetadataReader` accepting a class name that all dependencies mentioned by that class are ready. It has only read bytecode data at the requested level.

## 3. Three JVM Concepts You Must Distinguish

You cannot understand ASM's limits if you lump all three together as “loading a class”.

### 3.1. Loading — Loading/Defining a Class

The JVM locates the binary representation of a type and creates the `Class<?>` object representing that type. A class loader may participate in reading bytes and defining the class. When using `Class.forName(String, boolean, ClassLoader)` with `initialize=false`, you are **requesting loading** of the type by the JVM, without requesting its immediate initialization.

### 3.2. Linking — Linking a Class

Under the JVM model, linking consists of verification, preparation, and resolution. Some resolution steps may be deferred; exact timing depends on VM behavior and execution paths. During this process the JVM may need to resolve additional types/dependencies.

### 3.3. Initialization — Initializing a Class

Initialization executes static initializers and assignments of non-compile-time-constant static fields according to JVM rules. For instance:

~~~java
public final class NoisyType {
    static {
        System.out.println("static-init=NoisyType");
    }
}
~~~

When the class is **initialized**, that line is printed. Merely reading the `NoisyType.class` file as a resource with ASM does not run `NoisyType`'s static initializer.

**Important note:** `Class.forName(name, false, loader)` is still **class loading**, even though it has not run the initializer yet. Therefore these two statements are not equivalent:

- “MetadataReader does not need to load the target class”: means reading bytecode without creating a `Class<?>` for that class.
- “Class.forName with initialize=false does not initialize the class”: the JVM still loads and may link the class; it only avoids immediately running initialization.

### Comparison Table

| Operation | Needs `Class<?>` of target class? | Runs target class's static initializer? |
| --- | --- | --- |
| `MetadataReaderFactory.getMetadataReader("a.B")` | No | No |
| `ClassLoader.getResource("a/B.class")` | No | No |
| `Class.forName("a.B", false, loader)` | Yes: requests loading | No, per the `initialize=false` parameter |
| `Class.forName("a.B")` | Yes | Yes, on success with this overload |
| `new B()` | Yes | Yes, before first instantiation if not yet initialized |
| `B.class` | Creates/returns `Class<?>`, does not force immediate init | Not necessarily |
| Reflection invoking method/reading non-constant static field | May require linking/initialization | Depends on operation and JVM rules |

Do not rely on `getResource` as proof that the class file is valid or that all dependent types are present: it only reports whether a resource can be found at that path.

## 4. What Does Class Metadata Contain, and What Does It Lack?

`ClassMetadata` lets you read data such as:

- `getClassName()`: the class name recorded in bytecode.
- `getSuperClassName()`: the superclass name, which may return `null` where absent.
- `getInterfaceNames()`: interface names as strings.
- `isInterface()`, `isAbstract()`, `isFinal()`: corresponding modifier flags.
- `isIndependent()`: whether the class is independent of an enclosing class per metadata.

`AnnotationMetadata` lets you inspect a class's annotations:

~~~java
boolean annotated = reader.getAnnotationMetadata()
    .hasAnnotation("example.annotations.FeatureFlagged");
~~~

It returns a `boolean` based on metadata, **without requiring an instance of the annotated class**. Note that `hasAnnotation` checks directly present annotations per the corresponding API; if you need meta-annotations or merged attributes, choose the appropriate API instead of assuming every lookup method behaves the same.

### Metadata Is Not Full Reflection

| What you want to know | How does ASM/metadata help? | Limitation |
| --- | --- | --- |
| Does the class have annotation X? | Can check via metadata | May require meta-annotation or explicit alias analysis |
| Which interfaces does the class implement? | Can read the declared interface name list | Does not automatically validate the entire runtime hierarchy |
| Is class `a.B` on the classpath? | Can look up resource `a/B.class` | Does not guarantee that class loads/links successfully |
| What does the static initializer do? | Reading bytecode can inspect instructions | Does not execute or verify runtime behavior |
| Does the constructor open a DB connection? | Bytecode can undergo advanced analysis | Should not use ASM to “simulate” every business flow |
| Which beans will appear after conditions? | Metadata is one input | Other conditions, registration, dependencies, lifecycle still apply |
| Does the class have full optional dependencies? | Cannot conclude from `.class` file presence alone | Requires checking runtime linking/execution paths |
| Which JAR did the JVM pick the class from? | Resources can offer clues | Class loader order, nesting, module path can be complex |

Do not confuse “bytecode can be read” with “Java objects are guaranteed to work normally”.

## 5. Why Is `@ConditionalOnClass` Usually Safe with Optional Dependencies?

In Spring Boot 3.3, `@ConditionalOnClass` allows writing:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.optional.OptionalClient")
public class OptionalClientAutoConfiguration {
}
~~~

The condition checks for the presence of `com.vendor.optional.OptionalClient` on the classpath; if missing, the auto-configuration can be skipped before Spring deeply processes its internals.

Spring Boot also supports class-literal syntax:

~~~java
@AutoConfiguration
@ConditionalOnClass(com.vendor.optional.OptionalClient.class)
public class OptionalClientAutoConfiguration {
}
~~~

**These two snippets only illustrate the idea; they cannot compile without `OptionalClient` at compile time.** The `name` syntax uses a string, so it can compile without the optional class. The `value = SomeType.class` syntax requires the class on the compile classpath.

A subtle point in Boot's documentation: when `@ConditionalOnClass` is placed **directly on a configuration class**, the `value` attribute can be read from annotation metadata via ASM before Spring needs to load the configuration class. Therefore referencing the class in the `value` attribute does not automatically trigger loading the optional type at the condition step.

However, this has boundaries:

- Protection depends on **annotation placement**, Spring's processing steps, and the configuration class not being loaded early elsewhere.
- When `@ConditionalOnClass` sits inside a custom **meta-annotation**, Boot documentation requires using `name` to avoid situations where class references are not handled as safely as when the annotation is attached directly.
- `@Bean` methods whose return type, parameters, superclass, or interfaces reference optional classes can force the JVM to resolve those types **before the method condition takes effect**. In such cases, extract a separate configuration and attach the condition to the enclosing class.
- Exceptions from bean creation or loading libraries at later stages are not “shielded by ASM”.

### `value` or `name`?

| Syntax | Advantage | Limitation |
| --- | --- | --- |
| `@ConditionalOnClass(OptionalType.class)` | Compile-time type safety, IDE refactoring | Requires type on compile classpath; safety depends on processing site |
| `@ConditionalOnClass(name="vendor.OptionalType")` | No import/class literal needed at compile time | Prone to typos; package renames do not auto-update |
| `@ConditionalOnMissingClass("vendor.OptionalType")` | Enabled only when that class is absent | Must understand why a fallback configuration is wanted |
| `@ConditionalOnClass({A.class, B.class})` | AND: requires every listed class | Must ensure class literals can compile |
| `@ConditionalOnClass(name={"a.A","b.B"})` | AND by multiple type names | Types checked by name, not full runtime API |

In real libraries, choose conditions that express the exact **dependencies a bean genuinely needs**. Do not use the presence of an arbitrary class as proof that an entire library has all its components.

## 6. Special Case: Meta-Annotations and Class Literals

Suppose you define a composite annotation:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@ConditionalOnClass(OptionalClient.class)
public @interface ConditionalOnOptionalClient {
}
~~~

*The snippet above only illustrates the risk; imports and the `OptionalClient` type are required to compile.*

Boot documentation notes that when `@ConditionalOnClass` is used as a **meta-annotation**, referencing classes via `value` does not have the same processing safety guarantees as the direct case. Write it using `name`:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@ConditionalOnClass(name = "com.vendor.optional.OptionalClient")
public @interface ConditionalOnOptionalClient {
}
~~~

*This is an annotation snippet requiring imports for `ElementType`, `RetentionPolicy`, `ConditionalOnClass` if added to a project; it is not a standalone file.*

**Why be explicit?** Metadata may be analyzed through different paths. Do not assume every annotation at every nesting level is processed purely via ASM with the same non-loading guarantee.

## 7. Dangerous Case: `@Bean` Returning a Type from an Optional Library

This is a common design mistake:

~~~java
@Configuration(proxyBeanMethods = false)
public class BadConfiguration {

    @Bean
    @ConditionalOnClass(name = "com.vendor.optional.OptionalClient")
    public com.vendor.optional.OptionalClient optionalClient() {
        return new com.vendor.optional.OptionalClient();
    }
}
~~~

**Anti-pattern**: it only compiles when the optional library is present at compile time; if the library is omitted at runtime, method processing can fail before Spring applies the method condition.

The problem is that the **method's return type** contains the optional class name. The JVM, reflection, or configuration parsing may need to resolve the method signature before the method condition prevents registration. ASM helps read metadata in many stages, but does not guarantee every method-processing path avoids class loading.

### Safer Pattern: Separate Configuration with Class-Level Condition

~~~java
@Configuration(proxyBeanMethods = false)
public class RootConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.optional.OptionalClient")
    static class OptionalClientConfiguration {

        @Bean
        com.vendor.optional.OptionalClient optionalClient() {
            return new com.vendor.optional.OptionalClient();
        }
    }
}
~~~

*This is a template requiring the optional library at compile time; outer/inner classes and full imports are needed for a complete compilable file.*

Here `OptionalClientConfiguration` is isolated in a **separate configuration class**, so the class-level condition can be evaluated by Spring via metadata **before having to deeply process methods with optional signatures**. Using nested static configurations is a standard Spring Boot pattern for isolating optional library APIs.

**Crucial:** this isolation is not a “cure-all for every classpath error”. If a superclass/annotation/custom code loads the optional type too early, if the configuration class is referenced directly via reflection, or if another library already triggered loading, errors can still occur. Keep optional dependencies strictly inside properly guarded configurations.

### Do Not Treat an `@Bean` Method Condition as an Absolute Shield

A mistake is reasoning “because the method has `@ConditionalOnClass`, the JVM will never read that method's signature”. Method signatures may be inspected by the JVM/Spring analysis at another point, depending on configuration type and execution path. Boot documentation advises extracting a separate `@Configuration` class whenever optional dependencies need isolation.

## 8. Complete Experiment: Reading Metadata Without Initializing the Class

This section provides a **Spring Boot 3.3.13 + Java 17 + Maven 3.9+** console project. The goal is not to build a REST API, but to directly observe four events:

1. `MetadataReader` reads metadata of an uninitialized class.
2. `Class.forName(name, false, loader)` loads the type without initializing it.
3. `Class.forName(name)` initializes it and triggers the static initializer.
4. `@ConditionalOnClass(name="...")` can skip an auto-configuration if the optional type name does not exist at all.

### 8.1. Project Structure

~~~text
asm-metadata-demo/
├── pom.xml
└── src/main/
    ├── java/demo/
    │   ├── app/
    │   │   └── DemoApplication.java
    │   ├── target/
    │   │   ├── Marker.java
    │   │   └── NoisyType.java
    │   └── autoconfigure/
    │       └── MissingClientAutoConfiguration.java
    └── resources/META-INF/spring/
        └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

`DemoApplication` resides in package `demo.app`. The experiment class and auto-configuration class are placed outside the default scan package so **we do not accidentally load them via the app's component scan**. Auto-configuration is listed in imports, while `NoisyType` is only read for metadata and then explicitly loaded.

### 8.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>asm-metadata-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter` already provides Spring Core and metadata reading tools. We do not need to declare an ASM dependency directly; Spring uses the ASM repackaged inside Spring Core for these operations.

### 8.3. `src/main/java/demo/target/Marker.java`

~~~java
package demo.target;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface Marker {
}
~~~

This is a standalone marker annotation. Keeping runtime retention clearly shows the annotation is recorded in the class file and visible to reflection if needed; ASM can also read the metadata directly from bytecode.

### 8.4. `src/main/java/demo/target/NoisyType.java`

~~~java
package demo.target;

@Marker
public final class NoisyType {
    static {
        System.setProperty("demo.target.initialized", "true");
        System.out.println("static-init=NoisyType");
    }

    private NoisyType() {
    }
}
~~~

The static initializer marks the initialization state with a system property and prints a line. That is a **side effect placed in the target class to illustrate initialization timing**, not behavior you should put in Spring conditions.

Because the class is not component-scanned from `demo.app` and not declared as a bean, initialization in the example is triggered only by the deliberate `Class.forName(...)` call in `main`.

### 8.5. `src/main/java/demo/autoconfigure/MissingClientAutoConfiguration.java`

~~~java
package demo.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(name = "demo.missing.OptionalClient")
public class MissingClientAutoConfiguration {

    @Bean
    public String guardedText() {
        return "should-not-exist";
    }
}
~~~

`demo.missing.OptionalClient` is intentionally **not created** in the project and no dependency is added. Hence `@ConditionalOnClass(name=...)` does not match, and `guardedText` contributes no bean.

The condition is attached **directly to the auto-configuration class**, not the method. This is a safe and simple choice for guarding a configuration when a required class is absent.

### 8.6. Candidate Registration File

Create the exact file:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Sole content:

~~~text
demo.autoconfigure.MissingClientAutoConfiguration
~~~

Spring Boot 3.x will evaluate this class when `@EnableAutoConfiguration` takes effect via `@SpringBootApplication`, and then the classpath condition prevents the configuration from matching.

### 8.7. `src/main/java/demo/app/DemoApplication.java`

~~~java
package demo.app;

import org.springframework.boot.Banner;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Import;
import org.springframework.core.type.classreading.MetadataReader;
import org.springframework.core.type.classreading.SimpleMetadataReaderFactory;

@SpringBootApplication(scanBasePackages = "demo.app")
public class DemoApplication {

    public static void main(String[] args) throws Exception {
        try (ConfigurableApplicationContext context =
                 new SpringApplicationBuilder(DemoApplication.class)
                     .web(WebApplicationType.NONE)
                     .bannerMode(Banner.Mode.OFF)
                     .run(args)) {

            String className = "demo.target.NoisyType";

            MetadataReader reader =
                new SimpleMetadataReaderFactory()
                    .getMetadataReader(className);

            System.out.println("metadataName=" +
                reader.getClassMetadata().getClassName());
            System.out.println("marker=" +
                reader.getAnnotationMetadata()
                    .hasAnnotation("demo.target.Marker"));
            System.out.println("initializedAfterMetadata=" +
                Boolean.getBoolean("demo.target.initialized"));

            ClassLoader loader = DemoApplication.class.getClassLoader();
            Class.forName(className, false, loader);

            System.out.println("initializedAfterLoad=" +
                Boolean.getBoolean("demo.target.initialized"));

            Class.forName(className);

            System.out.println("initializedAfterInitialize=" +
                Boolean.getBoolean("demo.target.initialized"));

            System.out.println("guardedBean=" +
                context.containsBean("guardedText"));

            ConditionEvaluationReport.ConditionAndOutcomes outcome =
                ConditionEvaluationReport.get(context.getBeanFactory())
                    .getConditionAndOutcomesBySource()
                    .get("demo.autoconfigure.MissingClientAutoConfiguration");

            System.out.println("missingClientConditionMatched=" +
                (outcome != null && outcome.isFullMatch()));
        }
    }
}
~~~

Note: the import `org.springframework.context.annotation.Import` is unnecessary in the file above; Java does not fail on unused imports, though you may remove it for cleanliness. Target class names are passed as **strings** to avoid accidentally referencing class literals in the verification code.

How to read the output:

- `getMetadataReader(className)` reads `NoisyType.class` as a classpath resource.
- `getClassMetadata().getClassName()` retrieves the type name from bytecode.
- `getAnnotationMetadata().hasAnnotation(...)` detects `@Marker` in bytecode.
- `Boolean.getBoolean(...)` returns true when the system property has the string value “true”; this measures static initializer status.
- `Class.forName(className,false,loader)` requests class loading without initialization.
- `Class.forName(className)` requests initialization, causing the static initializer line to print.
- `guardedBean` checks whether the bean is in the context; because the optional class is absent, it must be `false`.
- `ConditionEvaluationReport` shows the condition status recorded by Boot; `isFullMatch()` for this configuration cannot be true when the required class is absent.

The program uses only the APIs needed to see the boundary between **metadata read** and **JVM initialization**; do not call `getBean(...)` just to check the classpath.

### 8.8. Compiling and Running

From the directory containing `pom.xml`:

~~~bash
java -version
mvn -version
mvn -q clean package
java -jar target/asm-metadata-demo-1.0.0.jar
~~~

Lines printed by program code and the static initializer, in order:

~~~text
metadataName=demo.target.NoisyType
marker=true
initializedAfterMetadata=false
initializedAfterLoad=false
static-init=NoisyType
initializedAfterInitialize=true
guardedBean=false
missingClientConditionMatched=false
~~~

Spring Boot may print additional logging messages; the block above only describes the verification lines produced by the example, without claiming the entire stdout/stderr contains only eight lines.

**Explanation of the three key lines:**

1. `initializedAfterMetadata=false`: reading the class file with Spring's MetadataReader **does not run the static initializer**.
2. `initializedAfterLoad=false`: `Class.forName(...,false,...)` requested loading the type without initializing it.
3. `static-init=NoisyType` appears between the two measurements because `Class.forName(className)` performs first-time initialization.

The line `missingClientConditionMatched=false` illustrates that Boot does not need to create the `guardedText` bean when the classpath condition is not satisfied.

**Assumed preconditions for reproducible results:** launch a fresh JVM, do not preset the system property `demo.target.initialized=true`, and add no other code that explicitly initializes `NoisyType` before the measurement. Both conditions are ensured in the sample project as presented.

## 9. Extended Experiment: When the Class File Exists, but a Dependency Is Missing

Suppose `com.vendor.client.FancyClient` exists in a JAR and its bytecode references `com.vendor.transport.TransportProtocol` — a class from a dependency **absent at runtime**.

An ASM-based class file reader can still read much of `FancyClient`'s metadata from the resource, because it primarily parses bytecode structure. Yet an actual runtime operation may fail:

~~~text
FancyClient.class -> read with ASM: may succeed
                 -> Class.forName(...): may fail during load/link
                 -> new FancyClient(...): may fail when resolving dependencies
                 -> call a method: may fail when resolving related types/methods
~~~

**Do not conclude “`Class.forName(false)` definitely fails” or “definitely succeeds”** for every missing-dependency case. JVM resolution/linking timing and reference kinds (superclass, interface, descriptor, annotation, instruction...) differ. Some failures surface during loading; others only surface when calling a specific method.

Exceptions/errors that may occur in different contexts:

| Symptom | Error example | How to interpret |
| --- | --- | --- |
| Cannot find the class being loaded itself | `ClassNotFoundException` | Reflective lookup or loader cannot find the type name |
| Class being loaded references a missing type | `NoClassDefFoundError` | JVM cannot find the definition when resolution is needed |
| Binary API mismatch across versions | `NoSuchMethodError` / `IncompatibleClassChangeError` | Binary incompatibility during linking/execution (note: `NoSuchFieldError` also fits here) |
| Incompatible hierarchy/interface | `IncompatibleClassChangeError` | Binary linkage violates expectations |
| Initializer throws an exception | `ExceptionInInitializerError` | Initialization was triggered and failed |
| Method body tries to use missing dependency | May be `NoClassDefFoundError` or other linkage error | Depends on where the JVM resolves the dependency |

**Core point:** metadata reading is a technique for avoiding loading **the class under inspection during a given phase**. It does not validate the transitive dependency graph, guarantee binary compatibility, replace the JVM verifier/linker, or guarantee a bean can be created successfully.

## 10. When Might ASM Still Need to Read Other Classes?

`MetadataReader` reading class A does not mean Spring infrastructure will never read metadata for class B:

- To analyze meta-annotations, Spring may need metadata of other annotations.
- To identify candidates via superclasses/interfaces or imported configurations, Spring may read additional metadata for related types.
- To process `@Configuration`, Spring may need to inspect `@Bean` methods, composed annotations, and import relationships.
- A custom `Condition` might call `ClassUtils.isPresent(...)` or another API itself, bringing type loading/checking into evaluation.
- Another framework might use reflection at a later stage to read generic signatures, annotation attributes, or type hierarchies.

ASM is only a bytecode parsing tool; **Spring's overall algorithm** decides when additional resources must be read or real types loaded.

If a library must work when an optional dependency is missing, you must deliberately design both **class structure and annotation processing scope**, rather than relying solely on ASM.

## 11. Characteristics of `@ConditionalOnClass` Compared to Other Checks

In Spring Boot, classpath conditions can be expressed in multiple ways:

### `@ConditionalOnClass`

~~~java
@ConditionalOnClass(name = {
    "com.vendor.alpha.AlphaClient",
    "com.vendor.beta.BetaCodec"
})
~~~

Both types must be present under the condition's semantics for the configuration to match. Presence does not prove network connectivity, licenses, or runtime APIs are configured.

### `@ConditionalOnMissingClass`

~~~java
@ConditionalOnMissingClass("com.vendor.optional.FastClient")
~~~

Used for fallbacks that activate when a type is absent; for example, substituting an implementation when a fast library is not on the classpath. Do not overuse it: a missing class is sometimes a deployment error rather than a valid feature branch.

### `ClassUtils.isPresent`

~~~java
boolean available =
    org.springframework.util.ClassUtils.isPresent(
        "com.vendor.optional.FastClient",
        getClass().getClassLoader()
    );
~~~

This is a fragment to place in code with an appropriate context. `ClassUtils.isPresent` is a Spring utility for checking whether a class can be present, but it goes through class loading and catches certain errors per its API — **operating at a different layer** than simply reading a `.class` file with ASM.

If you only need to gate an auto-configuration, prefer `@ConditionalOnClass`/`@ConditionalOnMissingClass`. Do not write a custom condition calling `Class.forName` if the built-in annotations already express the requirement.

### `ClassLoader.getResource`

~~~java
boolean resourceFound = getClass().getClassLoader()
    .getResource("com/vendor/optional/FastClient.class") != null;
~~~

Having the resource file does not mean the JVM can load or link the class successfully. Tooling may use resource presence as one signal, but it should not be treated as a **complete** classpath verification check.

## 12. Optimizing Candidate Discovery: Metadata and Auto-Configuration Files

Spring Boot 3.x receives auto-configuration candidates from the resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

The resource lists candidate classes by FQCN, not bean instances. Boot also applies exclusions/filters/conditions to decide which configurations are actually processed.

A library can generate optimization metadata via an annotation processor:

~~~text
META-INF/spring-autoconfigure-metadata.properties
~~~

This metadata assists filtering/optimizing auto-configurations for certain conditions, especially checks that can run early. It **does not replace** the imports file; and having a metadata file also **does not prove beans were created**.

### Why Does This Matter for Performance?

If an application uses hundreds of starters/dependencies, loading every candidate class just to ask whether the classpath matches would be costly and risk loading optional types too early. Reading bytecode metadata and filtering candidates early reduces unnecessary work, especially with large classpaths.

However, do not promise specific startup time numbers because gains depend on version, classpath, candidate count, caching, conditions, and project structure.

### ASM Does Not Replace Runtime Conditions

Successfully reading an imports file is only the discovery step. An `@AutoConfiguration` class reported as condition-matched can still fail during bean creation due to missing required properties, binary incompatibility, or constructor errors. Diagnosis combines:

1. Are the imports/candidate resources actually packaged?
2. Do `@ConditionalOnClass`/other conditions match?
3. Are bean definitions and bean instances created validly?
4. Are there linkage/initialization errors at runtime?

## 13. Reading Metadata from Regular JARs and Boot Executable JARs

`MetadataReaderFactory` accepts a class name and uses an appropriate resource/class loader to locate bytecode. In projects run from Maven or `target/classes`, the resource is typically a `.class` file on the filesystem. In regular JARs, it can be located via a classpath URL inside the archive.

A Spring Boot executable JAR has a common layout:

~~~text
app.jar
├── BOOT-INF/classes/
│   └── demo/app/DemoApplication.class
├── BOOT-INF/lib/
│   └── dependency.jar
└── org/springframework/boot/loader/...
~~~

When launched via Spring Boot's loader, the classpath sees `BOOT-INF/classes` and nested dependency JARs. Metadata tools reading through resource/class loaders operate on the classpath provided by that loader; you do not need to manually unpack every JAR just to use `MetadataReader` inside the running program.

If you inspect **from outside the application** using `jar tf app.jar`, it only lists entries of the outer JAR without automatically opening nested JARs. To directly inspect `.class` files or imports of dependencies nested in `BOOT-INF/lib`, open the nested JAR individually or use a tool that understands nested JARs.

### Notes on Class/Resource Names

- FQCN in annotations and metadata: `com.acme.Foo`.
- Classpath resource: `com/acme/Foo.class`.
- Entry in a JAR: `com/acme/Foo.class` in a regular JAR.
- Nested class by binary name: `com.acme.Outer$Inner` and entry `com/acme/Outer$Inner.class`.

Confusing dots and slashes is a simple yet very common mistake when writing custom discovery tools.

## 14. Common Mistakes When Trying to Avoid Class Loading

| Situation | Mistake | Right approach |
| --- | --- | --- |
| Only need to read names/annotations | Calling `Class.forName(...)` then reflection | Use `MetadataReader`/`AnnotationMetadata` |
| Only want to avoid static initializer | Thinking `Class.forName(name,false,loader)` means “no loading” | It still loads; only avoids initialization |
| Writing auto-config depending on optional lib | Putting condition on a method returning optional type | Move condition onto a separate configuration class |
| Writing a `@ConditionalOnClass` meta-annotation | Using class literal and assuming ASM always shields it | Use `name` per Boot's guidance |
| Seeing `.class` on classpath | Concluding the whole runtime API works | Check dependency graph, linkage, and startup |
| Managed to read bytecode of class A | Thinking all Spring condition checks load nothing else | Distinguish Spring's processing phases |
| `AutoConfiguration.imports` exists | Concluding the bean definitely exists | Check conditions and post-startup context |
| Cannot find resource in outer JAR | Concluding nested dependency does not exist | Inspect `BOOT-INF/lib` inside the executable JAR |
| Creating custom condition that reads network | Treating presence checks like service availability | Use classpath conditions for presence; health/retry for external state |
| Relying on reflection of optional class | Thinking metadata scanning prevents linkage errors | Isolate classes; avoid optional signatures where processed early |
| Caching metadata for too long | Assuming classpath/resources never change in any environment | Scope caches to lifecycle and class loader environment |
| Using inaccurate class names | Missing candidates/annotations | Verify FQCN, package, version, and actual classpath |

## 15. Diagnostic Workflow for `NoClassDefFoundError`

Do not assume “ASM is broken”. Follow these steps:

1. **Read the root stack trace.** See whether the exception occurs during metadata scanning, configuration parsing, method reflection, bean creation, or business invocation.
2. **Verify library versions.** Compare compile/runtime dependencies and conflicting versions.
3. **Check condition placement.** Is `@ConditionalOnClass` directly on the auto-configuration class, on an `@Bean` method, or inside a meta-annotation?
4. **Inspect class/method signatures.** Are there return types/parameters/superclasses/interfaces requiring optional type resolution before conditions evaluate?
5. **Check imports.** Is the auto-configuration class in `AutoConfiguration.imports`? Is it accidentally scanned as a component?
6. **Check the runtime classpath.** Is the target class file in the right JAR/version? Are required direct or transitive dependencies present?
7. **Separate class loading from bean creation.** Did the error happen before `BeanDefinition` or inside a factory method/constructor?
8. **Isolate optional configuration.** Use a static nested class or standalone configuration class with class-level `@ConditionalOnClass`.
9. **Enable Boot's `--debug`.** The Condition Evaluation Report can show a class-level condition did not match; however, do not expect the report to replace a linkage error stack trace.
10. **Write a missing-dependency test.** Test a classpath truly lacking the optional library, because running with all dependencies in an IDE does not prove the configuration is safe.

**Key distinguishing signal:** `ClassNotFoundException` when you actively look up a class name differs from `NoClassDefFoundError` when the JVM must resolve a binary reference from another class. Both can stem from missing dependencies, yet the investigation path and code fix differ.

## 16. Practical Testing of Classpaths With/Without Optional Dependencies

To test a real auto-configuration library, include at least two test groups:

### Group A — Complete Classpath

- Real optional dependency present.
- Classpath condition matches.
- Default bean is registered when other bean/property conditions match.
- Bean works without linkage or initialization errors.

### Group B — Missing Classpath

- Omit the optional dependency from the runtime/test classpath.
- Auto-configuration is skipped **without causing loading/linking errors from optional class signatures**.
- Independent beans still start normally.
- Report records the classpath condition did not match (if the config was evaluated by Boot and the report is logged).
- No `NoClassDefFoundError` from the configuration class.

`ApplicationContextRunner` in `spring-boot-test` helps create contexts for different sets of user configurations/properties; `FilteredClassLoader` can be used to simulate absent classes in a test context. These are Spring Boot-specific testing utilities.

Example **test fragment** requiring `spring-boot-test`, AssertJ, and the configuration class:

~~~java
new ApplicationContextRunner()
    .withClassLoader(new FilteredClassLoader("com.vendor.optional"))
    .withConfiguration(
        AutoConfigurations.of(OptionalClientAutoConfiguration.class))
    .run(context -> {
        assertThat(context).doesNotHaveBean(OptionalClient.class);
    });
~~~

**This is only a test illustration**, not a complete program: the `OptionalClient` type in the assertion must exist at compile time, and the auto-config class/test helpers must exist in the project. In a true missing-dependency test, assert by bean name or type/string name when you do not want to link directly to the optional class. The example clarifies the idea of using `FilteredClassLoader`, not proof that a JAR lacking the API is safe on every path.

### Testing the Right Scope

Merely hiding classes with a test class loader does not necessarily reproduce every module path, app server class loader, or executable nested JAR scenario. For critical starters, combine missing-class tests using `FilteredClassLoader` with running a minimal app whose runtime dependency is genuinely removed.

## 17. Advanced Note: Annotation Metadata Does Not Exempt Class Loading in Every API

Some metadata APIs return class names as `String` or metadata structures; some reflection or annotation-synthesizing APIs resolve `Class<?>` values. Never assume every method with “metadata” in its name never loads additional classes.

For example:

- Reading `ClassMetadata.getClassName()` only requires the name from bytecode.
- Reading annotation names from `AnnotationMetadata` usually does not require instantiating the target class.
- Accessing annotation attributes where class values are converted to `Class<?>` may trigger class resolution depending on the API/path; Spring offers options to process class values as strings where appropriate.
- Reflection like `getDeclaredMethods()` may need to resolve parameter/return types and fail if dependencies are missing.
- Type descriptors or generic signatures may contain absent type names; seeing a name in bytecode does not check runtime compatibility.

**Pick the API for the question you need answered.** If you only need to know whether annotation X is present, do not switch to reflection just for a boolean result. If you need to invoke real methods, you cannot permanently avoid JVM loading/linking/initialization.

## 18. Practice Questions and Extended Experiments

1. **Concept:** What does it mean that ASM reads a `.class` file as data? How does it differ from `Class.forName(name,false,loader)`?
2. **Three phases:** Describe loading, linking, and initialization. Why doesn't reading metadata print the static initializer's output?
3. **Run the example:** After `MetadataReader`, what is `Boolean.getBoolean("demo.target.initialized")`? Why?
4. **Reorder:** Move `Class.forName(className)` before the ASM step. How will the initialization measurement lines change?
5. **Simulate missing dependency:** Place `@ConditionalOnClass(name="demo.missing.OptionalClient")` on the config. Why does Boot skip the bean without needing the optional class defined in the project?
6. **Dangerous method:** Why is `@ConditionalOnClass` on a standalone `@Bean` method with an optional return type not safe enough?
7. **Isolate configuration:** Move optional code to a static nested `@Configuration` with a class-level condition. How does that change processing order?
8. **Meta-annotations:** Why does Boot documentation require `name` instead of a class literal when composing `@ConditionalOnClass`?
9. **Inside a JAR:** If the app is an executable Boot JAR, where do you look to inspect a dependency's `.class` files yourself?
10. **Transitive dependencies:** If `FancyClient.class` is present yet an interface it implements is missing, can metadata still be read? Which JVM operation might detect the missing interface?
11. **Deployment errors:** How do `ClassNotFoundException`, `NoClassDefFoundError`, and `ExceptionInInitializerError` differ?
12. **Evidence:** Does the existence of `AutoConfiguration.imports` prove a bean was created? What additional data is needed?
13. **Testing technique:** What is `FilteredClassLoader` suited to test, and why is testing on a real runtime classpath still necessary?
14. **Optimization:** When scanning thousands of classes, how can caching metadata help? When might a cache become a burden?
15. **Limits:** Name at least five situations where ASM does not automatically protect against class loading or runtime dependency errors.

**Lesson mastery** is achieved when you can read class metadata via Spring APIs, accurately explain why static initializers do not run, use `@ConditionalOnClass` to guard optional configurations, isolate configurations at the class level when method signatures contain optional types, and distinguish metadata, classpath, linkage, and bean creation errors.

## 19. Official Documentation

- [Spring Framework — `MetadataReader` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/type/classreading/MetadataReader.html)
- [Spring Framework — `MetadataReaderFactory` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/type/classreading/MetadataReaderFactory.html)
- [Spring Framework — `SimpleMetadataReaderFactory` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/type/classreading/SimpleMetadataReaderFactory.html)
- [Spring Framework — `ClassMetadata` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/type/ClassMetadata.html)
- [Spring Framework — `AnnotationMetadata` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/type/AnnotationMetadata.html)
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 — Condition annotations](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.condition-annotations)
- [Spring Boot 3.3 — `@ConditionalOnClass` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html)
- [Java SE 17 — JVM specification, Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html)
