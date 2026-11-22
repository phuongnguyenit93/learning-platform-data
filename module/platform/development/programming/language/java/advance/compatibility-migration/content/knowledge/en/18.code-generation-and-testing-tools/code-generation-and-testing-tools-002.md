
# Lombok, MapStruct, and javac compatibility

When upgrading Java, source code using **Lombok** and **MapStruct** may suddenly fail to compile, even when business classes have barely changed. The root cause usually sits in the **code generation and compiler layer**: a different javac version, altered annotation processing mechanics, stricter module access, unregistered processors, or the two tools failing to see each other's outputs within the same compilation pass.

This content belongs to *Java Advance Compatibility Migration*, section *Code generation and testing tools*. The lesson explains the technical differences between Lombok and MapStruct, how they interact with javac, how to configure Maven/Gradle, typical error patterns, and methods to verify both generated sources and the final artifact across multiple JDK versions.

The objective is not to pin a Lombok version forever or scatter `--add-opens` flags indiscriminately, but to **bring annotation processing under managed build governance**: verified versions, proper dependency scopes, visible outputs, and reproducible tests.

## 1. Why does annotation-driven code easily trigger migration issues?

A project uses annotations to avoid boilerplate code:

~~~java
import lombok.Getter;
import lombok.RequiredArgsConstructor;

@Getter
@RequiredArgsConstructor
public class Product {
    private final String code;
    private final long price;
}
~~~

In the source file, there are only fields and annotations. Yet consumers can invoke:

~~~java
Product product = new Product("BOOK-1", 100L);
System.out.println(product.getCode());
~~~

The constructor and getter are generated with Lombok's help during compilation. If Lombok fails to run, both calls above can report errors even though `Product` source code is still present.

Another project uses MapStruct:

~~~java
import org.mapstruct.Mapper;

@Mapper
public interface ProductMapper {
    ProductDto toDto(Product product);
}
~~~

The source declares only an interface. MapStruct must generate a concrete implementation, typically named something like `ProductMapperImpl`, so the runtime can instantiate or inject that mapper.

Therefore, regarding code generation, distinguish:

| Layer | Lombok | MapStruct |
|---|---|---|
| Developer-written source | Fields, annotations, and Java types | Mapper interfaces/abstract classes and annotations |
| Compiler mechanism | Deep integration with javac AST and compiler phases | Standard annotation processor using `javax.annotation.processing` |
| Primary output | Members injected into compiled classes | Generated Java mapper source, then compiled to classes |
| Processor needed at compile time? | Yes, when source uses Lombok annotations | Yes, when mapper implementations must be generated |
| Processor needed at runtime? | Usually no for generated members | No for compiled mappers |
| Risk when changing JDK | Relies on internal javac structures | Changes in annotation processing, model, source language, and toolchain |
| When working together | Lombok creates accessors/builders read by other processors | MapStruct must properly recognize accessors/builders from Lombok |

Do not assume the two tools merely “process annotations the same way”. They operate differently, leading to different failure causes and resolutions.

## 2. How does javac compile and run annotation processing?

`javac` is Java's compiler. It processes source code across phases such as parsing, symbol resolution, type checking, annotation processing, and class-file emission. Standard annotation processing is defined by **JSR 269** and APIs in packages:

~~~java
javax.annotation.processing
javax.lang.model
javax.tools
~~~

Note: package `javax.annotation.processing` remains a Java SE API. It **does not change to `jakarta.annotation.processing`** simply because an application migrates from `javax.persistence` to `jakarta.persistence`.

A standard annotation processor receives elements from the compiler, inspects annotations, and can emit additional source/resource files via `Filer`. MapStruct follows this model to generate Java source for mappers.

### 2.1. Processing-rounds model

~~~mermaid
flowchart TD
    A["Java source + annotations"] --> B["javac: parse and symbol model"]
    B --> C["Annotation processors"]
    C --> D{"New source generated?"}
    D -->|Yes| E["Generate Java source into generated-sources"]
    E --> C
    D -->|No| F["Type checking and bytecode generation"]
    F --> G["Class files in artifact"]
~~~

Processors can execute across multiple **processing rounds**. New source created in one round becomes visible in the next round. However, the compiler only tracks elements created properly through the processing API; not all internal AST modification techniques share the same contract.

### 2.2. Lombok differs from ordinary annotation processors

Lombok registers to participate in compilation while also integrating deeply with the compiler to add members, constructors, getters, setters, builders, and other constructs not written directly in source.

This lets the compiler see generated members as if they belonged to the Java class. However, it also makes compatibility with the **javac version** far more critical than for processors relying solely on standard APIs.

A newer JDK may modify compiler internals, AST structures, internal classes, or module access rules. Older Lombok releases may fail with exceptions like:

~~~text
java.lang.NoSuchFieldError
java.lang.IllegalAccessError
java.lang.ExceptionInInitializerError
~~~

These exceptions are examples; actual errors depend on Lombok version, JDK, and build setup. Never conclude the root cause based solely on an exception name.

### 2.3. MapStruct uses the compiler model to generate code

MapStruct inspects the mapper interface/abstract class, source types, target types, getters/setters, constructors, builders, and mapping annotations. It emits Java code that directly calls the appropriate accessors/converters.

Example:

~~~java
import org.mapstruct.Mapper;

@Mapper
public interface ProductMapper {
    ProductDto toDto(Product source);
}
~~~

With matching types, generated output might look like:

~~~java
// Illustrative generated code, not verbatim across every version
public class ProductMapperImpl implements ProductMapper {
    @Override
    public ProductDto toDto(Product source) {
        if (source == null) {
            return null;
        }

        ProductDto result = new ProductDto();
        result.setCode(source.getCode());
        result.setPrice(source.getPrice());
        return result;
    }
}
~~~

If the compiler has not seen getters generated by Lombok, MapStruct may conclude `Product` lacks properties `code` or `price`. The error then manifests as a **missing property**, even though the deeper cause is the interaction between the two tools.

## 3. Distinguishing API, processor, and runtime dependencies

Both libraries typically ship distinct artifacts serving different roles:

| Role | Typical artifact | Purpose |
|---|---|---|
| MapStruct annotations and API | `org.mapstruct:mapstruct` | Contains `@Mapper`, `@Mapping`, and related APIs |
| MapStruct processor | `org.mapstruct:mapstruct-processor` | Runs during compilation to generate mapper sources |
| Lombok | `org.projectlombok:lombok` | Annotations and javac integration machinery |
| Integration bridge | `org.projectlombok:lombok-mapstruct-binding` | Helps the two processors coordinate in applicable setups |
| Compiled mapper implementation | Generated classes inside your app/library artifact | Executes at runtime to perform mappings |

These coordinates specify only **artifact names**, not prescribed versions. Each project must choose a version combination compatible with its actual JDK, compiler, framework, and build plugins.

A common mistake is adding only:

~~~groovy
implementation("org.mapstruct:mapstruct:VERSION")
~~~

and assuming MapStruct will automatically generate implementations. The API artifact containing annotations does not replace `mapstruct-processor`. Without enabling the processor, compiling the mapper interface may pass while runtime calls to `Mappers.getMapper(...)` or DI resolution fail.

Similarly, Lombok is not merely a runtime dependency. Lombok's processor must run at compile time to create the methods/constructors used by code.

### 3.1. Compile classpath vs. processor path

In modern builds, distinguish:

- **Compile classpath**: classes, annotations, and interfaces Java source is permitted to reference.
- **Annotation processor path**: processors discovered/loaded and executed by javac.
- **Runtime classpath**: classes and libraries the application needs when executing.
- **Test compile/processor path**: classpath/processors dedicated to test sources.

A processor may appear in the dependency graph without actually residing on the processor path. Conversely, a processor active during compilation does not need to be packaged inside the application.

### 3.2. An annotation processor is not a runtime implementation

MapStruct's processor only generates code during builds. Once `ProductMapperImpl.class` has been compiled, the runtime does not need to load `mapstruct-processor` to execute mappings.

Shipping compiler internals or processors inside a production fat JAR typically brings no benefit and can:

- Increase artifact size and dependency surface.
- Create conflicts with other runtime dependencies.
- Carry unnecessary compiler classes.
- Introduce risks when building custom runtimes with `jlink`.

Inspect packaged runtime artifacts to confirm dependencies are placed properly.

## 4. Configuring Gradle with Java, Lombok, and MapStruct

For Gradle using the `java` or `java-library` plugin, a typical configuration looks like:

~~~groovy
plugins {
    id 'java'
}

dependencies {
    // MapStruct API present when compiling code using @Mapper.
    implementation("org.mapstruct:mapstruct:MAPSTRUCT_VERSION")

    // Lombok annotations and transformer needed on compile + processor paths.
    compileOnly("org.projectlombok:lombok:LOMBOK_VERSION")
    annotationProcessor("org.projectlombok:lombok:LOMBOK_VERSION")

    // Processor used to generate MapperImpl.
    annotationProcessor(
        "org.mapstruct:mapstruct-processor:MAPSTRUCT_VERSION"
    )

    // Used when the Lombok/MapStruct setup needs the integration bridge.
    annotationProcessor(
        "org.projectlombok:lombok-mapstruct-binding:BINDING_VERSION"
    )

    // If test sources also directly use Lombok:
    testCompileOnly("org.projectlombok:lombok:LOMBOK_VERSION")
    testAnnotationProcessor("org.projectlombok:lombok:LOMBOK_VERSION")
}
~~~

`*_VERSION` are placeholders, not resolvable literals. Manage actual versions via version catalogs, platforms, or centralized project configuration.

### 4.1. When does the MapStruct API need `api` instead of `implementation`?

If the project is a **public library** whose public method/annotation contract directly exposes types from MapStruct or another API, Gradle `java-library` may need `api(...)` so consumers receive the compile dependency.

For applications using MapStruct as an internal implementation detail, `implementation(...)` is normally suitable. What decides this is the **contract exported to consumers**, not the label “code-generation library”.

### 4.2. Separating the processor path for tests

If Java tests declare their own code-generating annotations, they may need dedicated processor paths. Never assume `annotationProcessor` for main sources automatically populates `testAnnotationProcessor` across every setup.

If tests only call compiled classes from main sources, they do not necessarily need to re-run the MapStruct processor. Distinguish:

1. Main sources declaring mappers.
2. Test sources declaring additional mappers.
3. Test sources only invoking mapper classes already generated in main.

### 4.3. Using Java toolchains and `--release` properly

For example, to run the build/compiler on JDK 21 while emitting Java 17-compatible bytecode:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Three concerns must remain separate:

- **The JDK running the compiler and annotation processors**: e.g., JDK 21.
- **Source/API/bytecode target**: controlled via `--release 17`.
- **Minimum product runtime JDK**: requires testing the artifact on Java 17.

`--release` does not make an old Lombok “think it is running under javac 17”. Processors still execute inside compiler JDK 21 and must be compatible with JDK 21's javac.

This is one of the most frequent misconceptions when upgrading toolchains.

## 5. Configuring the Maven Compiler Plugin

With Maven, release and annotation processors can be configured via `maven-compiler-plugin`. Skeleton example:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>

<dependencies>
    <dependency>
        <groupId>org.mapstruct</groupId>
        <artifactId>mapstruct</artifactId>
        <version>MAPSTRUCT_VERSION</version>
    </dependency>

    <dependency>
        <groupId>org.projectlombok</groupId>
        <artifactId>lombok</artifactId>
        <version>LOMBOK_VERSION</version>
        <scope>provided</scope>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>COMPILER_PLUGIN_VERSION</version>
            <configuration>
                <release>17</release>
                <annotationProcessorPaths>
                    <path>
                        <groupId>org.projectlombok</groupId>
                        <artifactId>lombok</artifactId>
                        <version>LOMBOK_VERSION</version>
                    </path>
                    <path>
                        <groupId>org.mapstruct</groupId>
                        <artifactId>mapstruct-processor</artifactId>
                        <version>MAPSTRUCT_VERSION</version>
                    </path>
                    <path>
                        <groupId>org.projectlombok</groupId>
                        <artifactId>lombok-mapstruct-binding</artifactId>
                        <version>BINDING_VERSION</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

This is an **illustrative template** for Maven/JDK/plugin combinations supporting the setup shown. Never copy placeholder values into a real project.

Recent versions of the Maven Compiler Plugin also offer additional processor dependency declaration models. Choose a mechanism supported by your plugin and target JDK, then verify processors are actually discovered. Do not mix incompatible configuration patterns from different plugin generations just to “get it working”.

### 5.1. Lombok's `provided` scope does not guarantee annotation processing is enabled

Placing Lombok in `provided` allows compiled source to reference annotations, yet **does not ensure** the processor runs, especially when builds restrict processors to an isolated processor path.

`annotationProcessorPaths` explicitly declares which processors may load. If the build does not activate the processor, getters/builders remain absent even though Maven downloaded `lombok.jar`.

### 5.2. Do not ship processors on a server's runtime classpath

`mapstruct-processor` and compiler support artifacts normally belong only at build time, not in runtime distributions. In Maven, inspect packaged JARs/WARs and actual dependency scopes; never assume transitive dependencies vanish on their own without inspecting the artifact.

## 6. Changes in javac annotation processing behavior across JDKs

Alongside processor compatibility, `javac` itself has evolved how it **automatically discovers** processors.

In older JDKs, projects sometimes “worked by accident” because javac picked up annotation processors from the classpath without an explicit processor path. On newer JDKs, the compiler may require enabling annotation processing or declaring processors more explicitly; for instance starting with JDK 23, automatic processor execution by default can no longer be relied upon without proper configuration.

Therefore, when migrating, **do not depend on processors discovered incidentally from the compile classpath**. Declare an explicit processor path/processor module path, or an explicit processor list and processing mode supported by your JDK/build tool.

### 6.1. Relevant javac options

| Option | Purpose |
|---|---|
| `-processorpath <path>` / `--processor-path <path>` | Specifies where to locate annotation processors |
| `-processor <names>` | Specifies concrete processor classes |
| `-proc:none` | Skips annotation processing |
| `-proc:only` | Runs only processing without compiling regular class code |
| `-proc:full` | Runs processing and compilation when the JDK supports this option |
| `-s <directory>` | Output directory for sources generated by annotation processing |
| `-XprintRounds` | Prints processing round details for diagnostics |
| `-XprintProcessorInfo` | Prints information about processors used by the compiler |

Not every option exists across all JDKs with identical syntax; for example, `-proc:full` was introduced in modern JDKs. Check `javac -help` or the documentation of your active compiler rather than assuming one command line works everywhere.

### 6.2. Testing directly with javac

Illustrative example with prepared classpath and processor path:

~~~bash
javac \
  --release 17 \
  -cp "lib/mapstruct-api.jar:lib/lombok.jar" \
  -processorpath "lib/lombok.jar:lib/mapstruct-processor.jar:lib/lombok-mapstruct-binding.jar" \
  -s build/generated-src \
  -d build/classes \
  src/main/java/com/example/*.java
~~~

This is a Unix-style shell example; on Windows, the classpath/processor-path separator is `;` instead of `:`. JAR filenames are illustrative, not guaranteed Maven artifact names.

In real projects, prefer letting Maven/Gradle manage classpaths and processor paths. Running javac directly helps isolate bugs, but does not substitute for full build and packaging.

### 6.3. Compilation success does not prove processors ran

If a mapper interface is unused at compile time, a build may pass even though no implementation was generated. Similarly, a class carrying Lombok annotations whose consumers never call generated getters might not expose a failure immediately.

Verify:

- Does generated source output contain the expected `*MapperImpl.java`?
- Do compiled classes include `*MapperImpl.class`?
- Can real consumers invoke Lombok-generated members?
- Are mappers discovered by the DI container?
- Are generated implementations packaged into the final artifact?

## 7. Lombok's special relationship with javac internals

Lombok does more than read annotations; it hooks deeply into compiler internals. Consequently, risks when upgrading the JDK often surface immediately when javac initializes processors or performs AST transformations.

### 7.1. Signs of incompatibility

Common symptoms:

~~~text
java.lang.NoSuchFieldError:
  Class com.sun.tools.javac.tree.JCTree$JCImport
  does not have member field ...

java.lang.IllegalAccessError:
  class ... cannot access class com.sun.tools.javac... 
  because module jdk.compiler does not export ...
~~~

Not every `NoSuchFieldError` is caused by Lombok. However, if the stack trace shows `lombok.javac` and `com.sun.tools.javac.*` classes, immediately compare **Lombok version vs. JDK compiler version**.

### 7.2. Why adding `--add-opens` is not a root fix

Some historical workarounds:

~~~text
--add-opens=jdk.compiler/com.sun.tools.javac.processing=ALL-UNNAMED
--add-exports=jdk.compiler/com.sun.tools.javac.tree=ALL-UNNAMED
~~~

These lines only exemplify opens/exports permissions—**they are not recommended settings to copy**. They may address specific module-access errors in narrow contexts, yet cannot fix changed javac methods, fields, AST nodes, or semantics.

Furthermore:

- `--add-opens` and `--add-exports` do not have the same effect.
- Flags passed to the JVM running the compiler can differ from flags passed to javac itself.
- Build daemons and forked compilers maintain separate JVM configurations.
- Opening broad compiler packages can mask an outdated Lombok version.

Prefer using a Lombok version officially documented to support your running JDK, and phase out workarounds once unnecessary.

### 7.3. The build JDK's javac determines the risk

A project using:

~~~text
Build JDK: 21
javac --release: 17
Runtime JDK baseline: 17
~~~

executes Lombok inside the JDK 21 compiler. Therefore, Lombok compatibility must be verified against **JDK 21**, not merely Java 17.

If the team upgrades the build runner to a newer JDK without changing `--release`, Lombok can still break because compiler internals changed.

### 7.4. Do not assume all compilers support Lombok identically

IDEs may use their own compilers or plugins manipulating the editor model. IntelliJ, Eclipse/JDT, javac, and build tools integrate differently.

A project may encounter:

- The IDE shows no errors while the Maven build fails.
- The Maven build passes while the IDE reports missing getters.
- The Eclipse compiler behaves differently from javac.
- Builds via the Gradle daemon run on a different JDK than the terminal shell.

Diagnosis must start by recording **which compiler actually ran**, which plugins are enabled, and the JDK versions of both the build and daemon.

## 8. How does MapStruct generate code?

MapStruct generates mapper implementations based on source/target types and mapping configuration.

Example of two DTOs:

~~~java
public class CustomerEntity {
    private Long id;
    private String fullName;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public String getFullName() { return fullName; }
    public void setFullName(String fullName) {
        this.fullName = fullName;
    }
}
~~~

~~~java
public class CustomerDto {
    private Long id;
    private String name;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public String getName() { return name; }
    public void setName(String name) {
        this.name = name;
    }
}
~~~

Mapper:

~~~java
import org.mapstruct.Mapper;
import org.mapstruct.Mapping;

@Mapper
public interface CustomerMapper {
    @Mapping(source = "fullName", target = "name")
    CustomerDto toDto(CustomerEntity source);
}
~~~

MapStruct attempts to generate an implementation calling `source.getFullName()` to populate `target.setName(...)`. If getters/setters change, the compiler can report errors immediately when generating or compiling the mapper.

### 8.1. Generated source is ordinary Java code

One strength of MapStruct is that its output does not rely on reflection for simple property mappings. You can inspect generated code and review:

- Which getters/setters or constructors are called.
- Which conversion methods are chosen.
- Null-handling logic.
- Collection/map/enum mappings.
- Builder usage.
- Dependency injection patterns.
- Ignored or defaulted mappings.

Generated code can change when MapStruct version, source models, or the compiler change. Do not treat generated local variable names or statement ordering as a public contract unless your project specifically requires and verifies it.

### 8.2. MapStruct API does not guarantee implementations are packaged

If the processor is missing or generated outputs are excluded during compilation/packaging, the `CustomerMapper` interface still exists while `CustomerMapperImpl` may be absent from the artifact.

With the factory pattern:

~~~java
import org.mapstruct.factory.Mappers;

CustomerMapper mapper =
        Mappers.getMapper(CustomerMapper.class);
~~~

the runtime requires an implementation instantiable/loadable per convention. With Spring or CDI component models, mapper implementations must be generated with suitable component/injection annotations and scanned by the container.

### 8.3. Component models can add extra dependencies

Example:

~~~java
@Mapper(componentModel = "spring")
public interface CustomerMapper {
    CustomerDto toDto(CustomerEntity source);
}
~~~

The generated implementation uses Spring annotations and is managed by the container. This makes build and runtime depend further on the Spring context and component-scanning configuration.

If using `componentModel = "default"`, mappers are normally obtained via MapStruct's factory. Do not copy patterns from both models and expect beans to appear in the DI container when the component model is misconfigured.

## 9. Why do Lombok + MapStruct often fail in the same compile?

Consider Lombok source:

~~~java
import lombok.Getter;
import lombok.Setter;

@Getter
@Setter
public class Account {
    private long id;
    private String displayName;
}
~~~

And mapper:

~~~java
import org.mapstruct.Mapper;

@Mapper
public interface AccountMapper {
    AccountDto toDto(Account source);
}
~~~

MapStruct needs to see `getId()` and `getDisplayName()` as properties on `Account`. Lombok adds those methods during compilation, yet **does not emit a standard separate Java file via normal generation**.

Consequently, if MapStruct inspects the type model before Lombok's AST updates become visible, MapStruct may see missing properties.

A typical error:

~~~text
Unknown property "displayName" in result type ...
No property named "displayName" exists in source parameter(s)
~~~

Errors can also genuinely stem from typos, getter visibility, builder settings, or accessor rules; gather evidence before blaming processor ordering.

### 9.1. Role of `lombok-mapstruct-binding`

In applicable Lombok and MapStruct versions, `lombok-mapstruct-binding` acts as an integration adapter helping MapStruct coordinate with Lombok-transformed types. For modern Lombok generations, this dependency is commonly needed when both libraries process the same sources.

Gradle example:

~~~groovy
annotationProcessor(
    "org.projectlombok:lombok-mapstruct-binding:BINDING_VERSION"
)
~~~

Maven configurations add the binding to `annotationProcessorPaths` alongside Lombok and the MapStruct processor.

Do not replace the binding by trying to “sort the order of annotationProcessor dependencies” and treating that as a stable contract. Javac does not guarantee internal reliance of one processor on non-standard side effects of another purely from JAR listing order.

### 9.2. Avoid confusing MapStruct mapping errors with Lombok errors

When MapStruct reports a nonexistent property:

1. Verify the property truly exists in source.
2. Check Lombok annotation scope.
3. Confirm Lombok's processor ran and is supported by javac.
4. Inspect getters/setters in compiled classes or via `delombok`.
5. Check the binding and MapStruct processor path.
6. Check whether the mapper compiles in the same module/source set or against a prebuilt dependency.
7. Check property naming under JavaBeans conventions or custom accessor naming strategies.
8. Check whether builders, fluent accessors, records, or constructor mappings changed.

Never add `@Mapping(ignore = true)` just to silence errors if that field represents mandatory business data.

## 10. `@Builder`, `@Value`, `@Accessors`, and constructor mapping

Lombok provides several annotations that reshape a class's API. MapStruct must select a matching way to construct target objects.

### 10.1. Setter mapping

For classes with a public no-args constructor and setters, MapStruct can normally instantiate and call setters.

~~~java
import lombok.Getter;
import lombok.Setter;

@Getter
@Setter
public class ItemDto {
    private String sku;
    private int quantity;
}
~~~

This form is straightforward under JavaBeans accessor conventions.

### 10.2. Immutable classes with builders

~~~java
import lombok.Builder;
import lombok.Value;

@Value
@Builder
public class ItemView {
    String sku;
    int quantity;
}
~~~

Lombok can generate a builder and getters; immutable classes lack conventional setters. MapStruct must recognize a matching builder or constructor.

Frequent failure modes:

- Builder factory not detected.
- Builder method names altered by Lombok customization.
- `@Accessors(fluent = true)` shifts property naming conventions.
- Generated constructors have incompatible visibility.
- Upgrading a processor changes builder detection rules.
- Mapping to a new field lacking a builder method.
- MapStruct configuration unintentionally disables builders.

Never judge the API solely from fields in source. Once compiled, constructors, getters, and builder methods constitute what consumers actually invoke.

### 10.3. `@Accessors` can affect naming

Example:

~~~java
import lombok.Getter;
import lombok.Setter;
import lombok.experimental.Accessors;

@Getter
@Setter
@Accessors(fluent = true)
public class Config {
    private String region;
}
~~~

Call sites become `config.region()` and `config.region("VN")` rather than `getRegion()`/`setRegion()`. This alters how MapStruct and other frameworks identify properties.

Verify MapStruct version, accessor naming strategy configuration, and Lombok integration support. Not every convention is automatically supported across all tool generations.

### 10.4. Records and newer source features

Java records expose accessors like `name()`, not `getName()` getters. Compatible MapStruct versions support record mapping, yet this must be verified against your actual JDK/source level and MapStruct release.

Example:

~~~java
public record ProductDto(String code, long price) {}
~~~

Lombok `@Getter` is unnecessary simply to expose record accessors. When converting a DTO from a Lombok class to a record, the binary API and constructor/accessor signatures can change; test legacy consumers, serializers, and mappers.

## 11. Lombok alters public APIs even when appearing only as annotations

Many constructs generated by Lombok are real binary APIs:

- Getters/setters.
- Constructors.
- `equals` and `hashCode`.
- `toString`.
- Builder classes and builder methods.
- Withers or helper methods.
- `@SneakyThrows` affecting how code exposes checked exceptions.
- `@SuperBuilder` shaping builder hierarchies across inheritance.

Example:

~~~java
import lombok.AllArgsConstructor;
import lombok.Getter;

@Getter
@AllArgsConstructor
public class ApiModel {
    private final String id;
}
~~~

Pre-compiled consumers may call constructor `ApiModel(String)` and method `getId()`. If annotation changes alter the constructor, drop a getter, or change visibility, older consumer bytecode can hit `NoSuchMethodError`.

This is a **binary compatibility risk** even though zero constructor lines were written by hand in source.

### 11.1. Changing Lombok versions can alter generated shapes

Upgrading Lombok can fix bugs, alter validation, or adjust edge-case code generation for certain features. Never assume generated code across two versions is byte-for-byte identical or keeps the exact same public member set.

For public libraries, compare actual compiled class files with:

~~~bash
javap -classpath build/classes/java/main -p -s com.example.ApiModel
~~~

What matters are **method names, descriptors, visibility, and behavior**, not whether the source annotations look unchanged.

### 11.2. `lombok.config` options are part of build inputs

A `lombok.config` file can customize Lombok code generation—such as accessors, generated annotations, constructor structure, or related policies.

A config change in a parent directory or another module can affect source output in ways not directly visible to the class author.

During migration:

- Identify all active `lombok.config` files.
- Verify how configuration inherits across directories.
- Record the Lombok version and key options.
- Confirm configs live in the intended projects/modules.
- Ensure clean builds pick up identical config in CI.

## 12. Generated sources, generated classes, and reproducibility

MapStruct normally emits Java source into build outputs. Common paths:

- Gradle: `build/generated/sources/annotationProcessor/java/main/`.
- Maven: `target/generated-sources/annotations/`.

Paths vary by plugin, custom source sets, Kotlin/kapt, or build configuration; inspect the actual output directory rather than hardcoding paths.

### 12.1. Should generated sources be committed?

There is no single right answer for every project.

**Not committing** reduces diff noise and manual edits, provided builds regenerate deterministically and CI always runs processors.

**Controlled committing** can be helpful in specialized build environments or when output is a separately governed artifact, provided strict rules prohibit manual edits and verify generated outputs match inputs.

Whichever option is chosen, ensure:

1. Generated sources are never hand-edited to mask processor failures.
2. Clean builds regenerate all implementations.
3. Final artifacts contain the required generated classes.
4. Stale output directories cannot produce “false green” builds.
5. CI never depends on an IDE having run generators on a developer machine.

### 12.2. Clean builds expose stale generated code

A leftover `MapperImpl.class` in the build directory can hide the fact that the processor did not run in the latest compile. Therefore, when changing JDKs or processor configurations, run a clean build in an isolated environment and verify outputs from scratch.

In study guides, you can use:

~~~bash
./gradlew clean compileJava
~~~

or:

~~~bash
mvn clean compile
~~~

These commands are **practice guidance for learners**, not steps executed during the authoring of this lesson.

### 12.3. Delombok helps inspect equivalent code

The `delombok` tool shows post-Lombok source in readable Java form in many cases. It is a valuable diagnostic aid for checking generated getters, constructors, builders, and annotations.

However, do not treat delombok output as the exact final bytecode; use `javap` when verifying binary APIs and class-file versions.

## 13. Common javac errors and how to diagnose them

| Error or symptom | Possible cause | Investigation path |
|---|---|---|
| `cannot find symbol: getX()` | Lombok processor did not run, method renamed, missing annotation | Processor path, Lombok version, delombok/javap |
| `cannot find symbol: builder()` | Builder not generated or customized name | Lombok annotations/config and compiled class |
| MapStruct reports unknown source property | Getter missing or MapStruct cannot see Lombok AST | Lombok/binding, accessor conventions, generated sources |
| Missing `*MapperImpl` | MapStruct processor did not run or compile failed | Processor path, javac rounds, output directory |
| `NoClassDefFoundError` for MapperImpl | Generated class absent from runtime artifact | Packaging, classpath, and DI discovery |
| `NoSuchMethodError` calling getter/constructor | Lombok-generated binary API changed | Compare `javap -s` between old and new builds |
| `NoSuchFieldError` inside `com.sun.tools.javac.*` | Lombok/compiler internals incompatible | JDK compiler version, Lombok support matrix |
| `IllegalAccessError` involving `jdk.compiler` | Internal compiler access restricted by modules | Upgrade Lombok, check remaining JVM workaround flags |
| `ClassNotFoundException` for processor | Processor dependency or registration missing | Annotation processor path |
| `FilerException: Attempt to recreate a file` | Overlapping rounds/processors or duplicate outputs/stale files | Processor configuration, clean build, duplicate generation |
| `UnsupportedClassVersionError` from processor | Processor JAR built for newer JDK | Build JDK and class-file version |
| `UnsupportedClassVersionError` running app | Generated/application bytecode newer than runtime | `--release` and dependency baseline |
| IDE build differs from CI | Different compiler/JDK/processor path | Toolchain, IDE plugins, and build logs |
| DI cannot find mapper bean | Component model, scan, or generation misconfigured | Generated annotations and runtime framework |

**Do not assume every compile failure is caused by Lombok.** For instance, a real MapStruct property typo requires fixing the mapping; adding bindings will not make an invalid mapping correct.

### 13.1. Reading stack traces layer by layer

A javac error can occur in:

1. Build tool daemon or compiler fork.
2. Annotation processor discovery.
3. Lombok transformer.
4. MapStruct processor.
5. Compilation of generated Java sources.
6. Classpath resolution.
7. Artifact packaging and runtime class loading.

Diagnosing a step requires data from that step. For example, a missing `MapperImpl` at runtime might happen because the processor never ran, or because a minimizer/shader stripped the class file.

### 13.2. Record the actual JDK instead of relying on `JAVA_HOME`

Useful checks:

~~~bash
java -version
javac -version
./gradlew --version
mvn -version
~~~

The Gradle daemon can run on a different JDK from `java` on your shell; Maven Toolchains can likewise pick a compiler distinct from Maven's JVM. When analyzing issues, record:

- JDK running the build tool.
- JDK running javac.
- JDK running tests.
- `--release` or source/target compatibility.
- Lombok/MapStruct/build plugin versions.

## 14. Diagnostic logging for annotation processing

When verifying which processors actually executed, use javac flags:

~~~text
-XprintRounds
-XprintProcessorInfo
~~~

Illustrative Gradle example:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += [
        '-XprintRounds',
        '-XprintProcessorInfo'
    ]
}
~~~

This is temporary diagnostic configuration. Do not leave verbose logging enabled on every production build, as it can bloat log output.

Items to check:

- Was the Lombok processor discovered?
- Did the MapStruct processor participate?
- Did a processing round generate `MapperImpl`?
- In which round did the error occur?
- Is the generated source directory correct?
- Was an unintended processor version loaded?

### 14.1. Reading the dependency graph for the processor path

With Gradle, inspect relevant configurations:

~~~bash
./gradlew dependencies --configuration annotationProcessor
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration testAnnotationProcessor
~~~

With Maven, inspect the effective POM and compiler plugin configuration, then reconcile the dependency tree with the processor path used by the plugin.

A Lombok JAR appearing on `compileClasspath` while **missing from `annotationProcessor`** is an immediate warning sign in Gradle.

### 14.2. Do not guess by JAR order when multiple processors exist

In Java annotation processing, processor discovery and interaction follow specific rules. An accidental change in classpath or build tools can make an error disappear for a single run without providing a durable fix.

Instead of reordering dependencies to “fix” it:

- Configure the processor path properly.
- Add the project-recommended binding when compatible.
- Align versions accurately.
- Verify with clean builds and output inspection.
- Isolate mapper/Lombok sources if architecture warrants it.

## 15. Splitting modules to reduce coupling between Lombok and MapStruct

In complex systems, one strategy is compiling Lombok models first and letting MapStruct in a separate module consume compiled classes.

Example:

~~~text
:domain-model
  - Lombok DTOs/entities
  - compileJava emits getters/constructors into class files

:mapper
  - depends on :domain-model
  - MapStruct interfaces
  - compileJava generates MapperImpl

:application
  - uses :domain-model and :mapper
~~~

Pros:

- MapStruct reads compiled class APIs, reducing sensitivity to AST transformation timing within one compilation pass.
- Model modules can be versioned independently.
- Easier to inspect binary APIs and public accessor shapes.

Cons:

- Adds module/build complexity.
- Requires clean dependency direction management.
- Risks cyclic dependencies if models depend on mappers.
- Does not remove the need to upgrade Lombok when a new javac version breaks compatibility.

Splitting modules is an architectural choice, not mandatory for every project.

## 16. Annotation processing with JPMS and `module-info.java`

In a modular project, the compiler may use the module path, processor path, or processor module path depending on configuration. Distinguish:

- Application `module-info.java` governs `requires`, `exports`, and `opens` for runtime code.
- Annotation processors load inside the compiler environment and do not necessarily belong in the runtime module graph.
- Because Lombok interacts with compiler internals, module access to `jdk.compiler` can matter.
- MapStruct emits code into the application's package/module, and generated code must compile under your source module rules.
- If generated mappers use DI annotations, the module needs matching dependencies and runtime configuration.

Never add `requires`/`opens` to the runtime module merely to fix a missing build-time annotation processor. Conversely, if DI/serializer runtime reflection accesses generated code inside a named module, you may need to `opens` application packages to the framework.

### 16.1. When should you inspect module opens?

For instance, a generated mapper calling only public getters/setters may not need deep reflection. However, DI/serialization frameworks reflecting on implementations, constructors, or fields may require module openness.

Separate:

1. **Compile-time** errors when processors fail to emit sources.
2. **Runtime linkage** errors when `MapperImpl` is absent.
3. **Runtime reflective access** errors when frameworks fail to instantiate or inject mappers.
4. **JDK compiler internals** errors from Lombok.

A single blanket module-opening flag will not fix all four categories.

## 17. Maven/Gradle incremental compilation and build caches

Annotation processing interacts closely with incremental builds:

- Processors can depend on a broader type graph than a single source file.
- Lombok alters the AST, complicating compiler input tracking.
- MapStruct generates sources from the type model, so changing a source/target property must trigger mapper regeneration.
- Build caches can hide failures while old outputs persist.
- When changing JDK or processor versions, cache keys must reflect the new inputs.

Some processors document incremental annotation processing support under specific constraints. Never assume every Lombok–MapStruct–Gradle combination is incremental-safe across all versions.

### 17.1. Practical test when upgrading toolchains

After configuring the new versions:

1. Run a clean compile from an empty workspace.
2. Change a model field used by a mapper.
3. Recompile and verify the generated mapper updates.
4. Change a mapping annotation and check the new output.
5. Delete generated output and recompile.
6. Verify the build cache does not restore implementations from stale inputs.
7. Run tests against packaged artifacts and the minimum runtime JDK.

If a build only succeeds when skipping clean or after an IDE pre-generated code, that workflow is unreliable for CI.

### 17.2. Deterministic generated output

A processor might embed timestamps, version comments, or metadata inside generated sources. Such details can alter checksums or generated-source diffs across builds despite identical mapper logic.

If reproducible artifacts are required:

- Enable options suppressing unstable metadata if the processor supports them.
- Pin JDK and processor versions.
- Compare semantic APIs/behavior rather than expecting every generated line to stay immutable across upgrades.
- Verify artifact checksums in release pipelines.
- Never hand-modify generated sources post-compilation.

## 18. Processor options and MapStruct configuration

MapStruct accepts configuration options passed to the annotation processor or via mapper/config annotations.

Example:

~~~java
import org.mapstruct.Mapper;
import org.mapstruct.ReportingPolicy;

@Mapper(unmappedTargetPolicy = ReportingPolicy.ERROR)
public interface OrderMapper {
    OrderDto toDto(OrderEntity source);
}
~~~

`ERROR` policy tells the compiler to fail when target properties go unmapped under MapStruct rules. This helps catch DTO changes after migration instead of silently dropping critical fields.

Some builds also set processor arguments:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += [
        '-Amapstruct.defaultComponentModel=spring'
    ]
}
~~~

This value exemplifies Spring projects; never enforce a default component model if your application does not use Spring.

### 18.1. Processor options are code-generation inputs

When source code stays identical yet processor options change, generated code can diverge:

- Component model: default, Spring, CDI, or others.
- Injection strategy: field, constructor, or setter per config.
- Null handling: check, ignore, or return default.
- Unmapped target policy: ignore, warn, or error.
- Builder detection and mapping strategies.
- Package/class naming conventions for implementations.

These options are **part of the build contract** and should be versioned and tested just like dependencies.

### 18.2. Upgrading MapStruct can expose missing mappings

Newer MapStruct versions may inspect properties differently or enforce stricter diagnostics than older versions. When compilation fails:

- Read exact property names/types on both sides.
- Check mapping inheritance.
- Check target constructors/builders.
- Check overloaded conversion methods.
- Check enum mappings and unmapped values.
- Check inherited annotations/configurations.
- Diff generated code before and after upgrading if a baseline exists.

Never lower `unmappedTargetPolicy` to IGNORE simply to make the build pass, as this can hide data loss.

## 19. Enums and types changed after migration

MapStruct can map enums and collections, yet data contracts require verification.

Example:

~~~java
public enum OldState {
    NEW, DONE, FAILED
}

public enum NewState {
    CREATED, COMPLETED, ERROR
}
~~~

You can write explicit mappings:

~~~java
import org.mapstruct.Mapper;
import org.mapstruct.ValueMapping;

@Mapper
public interface StateMapper {
    @ValueMapping(source = "NEW", target = "CREATED")
    @ValueMapping(source = "DONE", target = "COMPLETED")
    @ValueMapping(source = "FAILED", target = "ERROR")
    NewState toNewState(OldState state);
}
~~~

If producers add a new enum constant, mappers may need updates according to explicit rules. Never assume MapStruct selects a semantically correct business mapping merely from similar names.

When using Lombok `@Value` or `@Builder` on immutable DTOs, verify constructor/builder mapping and null handling. An incorrect mapping might compile cleanly without errors if fields are ignored or default policies permit it.

## 20. Source compatibility, binary compatibility, and runtime compatibility

Code generation impacts all three layers:

| Layer | Question | Example |
|---|---|---|
| Source compatibility | Can recompiled consumers still call the API? | Getter `getCode()` changed to `code()` |
| Binary compatibility | Can pre-compiled bytecode still find members/descriptors? | Lombok-generated constructor disappeared |
| Compile tool compatibility | Does the processor run on the target JDK's javac? | Old Lombok accesses changed javac internal fields |
| Generated-code compatibility | Does output compile under the declared `--release`? | Mapper generates code calling JDK-only newer APIs |
| Runtime compatibility | Does the artifact contain generated classes and dependencies? | `OrderMapperImpl` missing from JAR |
| Behavioral compatibility | Do mappings/`equals`/builders retain semantics? | MapStruct skips currency field after DTO refactor |
| Framework compatibility | Do DI, reflection, and module access work? | Generated mapper skipped by Spring component scan |

This is why you must inspect **input source, generated source, and compiled binaries**, not just a passing `compileJava` step.

### 20.1. Are generated implementations public APIs?

A `CustomerMapperImpl` class is typically a MapStruct-generated implementation detail. Consumers should depend on the `CustomerMapper` interface or dependency injection, rather than hardcoding implementation class names without controlled justification.

If a project genuinely exposes `*MapperImpl` or invokes constructors directly from other modules, generated implementations have become a de facto contract and must undergo binary compatibility evaluation when upgrading processors.

### 20.2. Lombok-generated members can be public APIs

Conversely, getters/constructors/builders generated by Lombok are often **the exact API called by consumers**. If a library publishes them, altering annotations can break contracts. Compare class files/public descriptors just like hand-written Java code.

## 21. Verifying with `javap` and `generated-sources`

After building, inspect outputs instead of guessing:

~~~bash
javap -classpath build/classes/java/main \
  -p -s com.example.Product

javap -classpath build/classes/java/main \
  -p -s com.example.ProductMapperImpl
~~~

Check:

- Do Lombok-generated getters and constructors exist?
- Are access modifiers and method descriptors correct?
- Do builder classes/methods match the contract?
- Does `MapperImpl` implement the interface and expose expected methods?
- Do compiler-generated methods have bridge/synthetic flags?
- Does the class-file major version fit the minimum JDK?

In Maven, class files typically sit under `target/classes`; in Gradle, paths depend on source sets and plugins.

### 21.1. Reading generated source to catch logic bugs

Example generated mapper:

~~~java
@Override
public CustomerDto toDto(CustomerEntity source) {
    if (source == null) {
        return null;
    }

    CustomerDto target = new CustomerDto();
    target.setId(source.getId());
    // If fullName -> name is omitted, data is lost.
    return target;
}
~~~

If tests only check that the returned object is non-null, unmapped data will slip through. Tests must assert critical fields, conversions, and null behavior.

### 21.2. Testing the actual release artifact

To ensure generated classes are not omitted during packaging:

~~~bash
jar tf build/libs/application.jar
~~~

Check for `*MapperImpl.class`, DTOs, and related classes. In Spring Boot executable JARs or nested JARs, class paths follow specific packaging structures; inspect the exact artifact.

Never assume “the class is in the build directory” means “the class is in the release JAR”.

## 22. How do IDE, CI, and local builds differ?

Lombok is especially sensitive to IDE integration because the IDE must understand generated code even when methods do not appear in source.

Common sources of divergence:

- The IDE toggles annotation processing separately.
- The IDE's Lombok plugin does not match the project's source/build version.
- The IDE uses a different JDK from Gradle/Maven.
- The Gradle toolchain differs from the Gradle daemon's JVM.
- Eclipse/JDT handles compilation differently from javac.
- CI runs clean builds while developer machines reuse stale outputs.
- Caches and generated-sources directories are managed differently.
- Maven/Gradle plugin versions differ due to wrappers or profiles.

A practical rule:

**CI builds using the project's declared Gradle Wrapper/Maven Wrapper and toolchain are the authoritative source of truth for the build.** IDEs should be configured to reflect that setup, not the reverse.

### 22.1. When the IDE shows red errors while CLI build passes

Check:

1. Does the IDE use the proper JDK language level?
2. Is annotation processing enabled?
3. Is the Lombok plugin compatible with the IDE/JDK?
4. Did the IDE import the project using the Gradle/Maven model properly?
5. Are generated source directories recognized?
6. Is the MapStruct processor present on the compiler processor path?
7. Do IDE caches/indexes need refreshing after config edits?

Never add processors into runtime artifacts merely to stop the editor from showing errors.

### 22.2. When CLI build fails while the IDE shows no errors

Never treat a green editor as proof. Inspect the actual compiler JDK used by the CLI and CI. Some IDEs emulate Lombok members inside the editor even when Gradle's javac cannot run that Lombok version.

## 23. Building safely when upgrading the JDK step by step

A practical roadmap:

### Phase A: Capture the baseline

Record:

- JDKs used for compilation and runtime.
- Maven/Gradle Wrapper and compiler plugin versions.
- Lombok, MapStruct, and binding versions.
- Compiler `--release`, source/target settings.
- Processor paths/processor options.
- Lombok configuration files.
- List of generated mapper files.
- Public API class-file signatures of published DTOs/models.
- Key unit/integration test results.

### Phase B: Upgrade code-gen tools before or alongside the build JDK

Verify Lombok, MapStruct, and compiler plugin support against the target JDK. One risk-reducing approach is upgrading necessary build tools in the baseline environment first before switching the compiler JDK, though exact sequencing depends on version compatibility and project constraints.

If parts cannot be upgraded independently, batch changes into small groups with clear evidence.

### Phase C: Enable processors explicitly

Ensure processors are declared on processor paths rather than only on compile classpaths. Verify the Lombok–MapStruct binding if both tools run in the same module.

### Phase D: Clean build on the target JDK

Confirm generated sources are created, implementations compile, bytecode matches the target, and no `jdk.compiler` errors appear. Never accept stale generated outputs as migration proof.

### Phase E: Verify generated behavior

Execute:

- DTO/constructor/getter/builder tests.
- Mapper integration tests covering critical fields.
- Null/collection/enum/immutable mapping tests.
- DI bootstrap tests.
- Legacy binary consumer checks if the library promises compatibility.
- Runtime smoke tests on the minimum supported JDK.

### Phase F: Release with evidence

Store artifact checksums, compiler/JDK metadata, dependency graphs, processor versions, test reports, and relevant generated-API diffs.

Never declare “Lombok and MapStruct support the new Java release” just because one sample module compiled. Verification scope must reflect actual sources, features, and runtime integration.

## 24. Suggested test matrix

| Axis | Example values | What to verify |
|---|---|---|
| Compiler JDK | Baseline and new JDK | Lombok javac internals |
| `--release` | Lowest supported JDK | Bytecode/API compatibility |
| Gradle/Maven plugin | Pinned versions | Processor discovery and options |
| Lombok | Approved version | Getter/constructor/builder shapes |
| MapStruct | Approved version | Mapper source generation |
| Binding | Compatible version | Lombok/MapStruct coordination |
| Source model | Mutable classes, immutable classes, records | Accessors/constructors/builders |
| Mapper model | Default, Spring, CDI if used | Wiring/DI behavior |
| Build mode | Clean and incremental | Generated source freshness |
| Environment | CLI CI and IDE | Toolchain consistency |
| Runtime | Minimum JDK, target JDK | Execution of generated classes |

There is no need to test all infinite combinations. Select an **officially supported version matrix** plus key migration paths, and enforce them in CI.

## 25. Combined migration example: Lombok DTO + MapStruct mapper

Suppose a system defines a DTO:

~~~java
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
public class InvoiceDto {
    private final String number;
    private final String currency;
    private final long amountMinorUnits;
}
~~~

Entity:

~~~java
public class InvoiceEntity {
    private String number;
    private String currencyCode;
    private long minorUnits;

    public String getNumber() { return number; }
    public String getCurrencyCode() { return currencyCode; }
    public long getMinorUnits() { return minorUnits; }
}
~~~

Mapper:

~~~java
import org.mapstruct.Mapper;
import org.mapstruct.Mapping;

@Mapper
public interface InvoiceMapper {
    @Mapping(source = "currencyCode", target = "currency")
    @Mapping(source = "minorUnits", target = "amountMinorUnits")
    InvoiceDto toDto(InvoiceEntity source);
}
~~~

On the older JDK, the mapper uses `InvoiceDto`'s builder cleanly. When switching to the newer compiler JDK, builds may fail because the older Lombok cannot run with javac. MapStruct then fails to detect the builder/getters and reports missing properties on the target.

**Structured investigation workflow:**

1. Record the exact compiler JDK running.
2. Confirm a Lombok version documented to support that JDK.
3. Verify `annotationProcessor` includes both Lombok and the MapStruct processor.
4. Add the appropriate binding version if required by the two tools' configuration.
5. Run a clean build to eliminate stale generated sources.
6. Read `InvoiceMapperImpl.java`: does it invoke `InvoiceDto.builder()`?
7. Test an entity with `currencyCode = "VND"` and `minorUnits = 250000L`.
8. Verify DTO output preserves all three fields accurately.
9. Inspect class files of `InvoiceDto` and `InvoiceMapperImpl`.
10. Execute the artifact on the minimum runtime JDK and check DI/mapper factories.

If mapper outputs remain wrong after building succeeds, **do not mark the migration as passed**. Distinguish compilation success from correctness of transformed data.

## 26. Practical failure cases and brief resolutions

### 26.1. "Lombok processor fails to load on the new JDK"

Inspect the stack trace, javac/JDK versions, and Lombok version. Prefer a Lombok version confirmed compatible; avoid keeping multiple opens/exports flags as a permanent solution.

### 26.2. "MapStruct does not generate implementations"

Check processor paths, processing modes, output directories, build plugin configuration, and clean compilation. MapStruct API may be present while the processor is missing.

### 26.3. "Unknown property despite `@Getter`"

Verify Lombok actually generates getters; then examine MapStruct/binding versions, property naming, fluent accessors, and builder behavior.

### 26.4. "Application starts, yet DI cannot find mappers"

Verify generated implementations use the right component model and framework annotations, are packaged in the artifact, and fall within package scanning scope.

### 26.5. "Compiles on Java 21, fails on Java 17"

Check `--release`, generated class-file major versions, dependency baselines, and processor-generated classes. A processor running on JDK 21 does not automatically guarantee Java 17 compatibility of emitted output.

### 26.6. "Every machine produces different results"

Standardize build tool wrappers, JDK toolchains, processor versions, processor options, and clean builds. Check IDE vs. CI, caches, and environment variables.

### 26.7. "Upgrading Lombok breaks older consumers"

Compare getter/constructor/builder symbols in class files; check Lombok configuration and annotation edits. If public binary APIs changed, consumers must migrate or compatible adapters/members must be retained.

### 26.8. "Generated mapper drops an important field"

Inspect `@Mapping`, `unmappedTargetPolicy`, DTO shapes, and generated code. Add business-data assertions rather than only checking the mapper instance is non-null.

## 27. Checklist for code review and CI

### Tools and versions

- [ ] Identified the JDK actually running javac, not just the Java runtime.
- [ ] Recorded Lombok, MapStruct, and binding versions.
- [ ] Confirmed build plugins/Wrappers support the target JDK.
- [ ] Configured `--release` matching the runtime baseline.
- [ ] Reviewed tool compatibility documentation when upgrading versions.
- [ ] Eliminated unowned workarounds opening `jdk.compiler`.

### Processor discovery

- [ ] Lombok is on both compile path and processor path per build tool conventions.
- [ ] MapStruct API is declared with the right scope.
- [ ] MapStruct processor is on the processor path.
- [ ] Binding added when required by the tool combination in use.
- [ ] Main and test source sets have suitable processor configurations.
- [ ] Eliminated reliance on accidental compiler processor auto-discovery.
- [ ] Generated source directories are tracked and inspected after clean builds.

### Generated API and behavior

- [ ] Lombok getters/setters/constructors/builders are generated as expected.
- [ ] Public method descriptors have not changed unexpectedly.
- [ ] `MapperImpl` is generated and compiled into classes.
- [ ] Mappings for critical fields are tested.
- [ ] Null, enum, collection, and immutable mappings are verified.
- [ ] Component models and DI setup are runtime-compatible.
- [ ] Generated classes exist inside the final artifact.

### Migration and reproducibility

- [ ] Clean build succeeds from an empty workspace on the target JDK.
- [ ] Incremental builds do not reuse stale incorrect outputs.
- [ ] CI, terminal, and IDEs use reconcilable toolchains/versions.
- [ ] Tested recompiled consumers and legacy binary consumers where applicable.
- [ ] Verified artifacts on the lowest declared JDK runtime.
- [ ] Archived compiler logs, generated-output evidence, and dependency graphs.
- [ ] Prepared a rollback plan in case code generation alters public APIs or mapping behavior.

## Conclusion

Both Lombok and MapStruct reduce boilerplate code, yet they sit at two distinct positions during compilation: **Lombok hooks deeply into javac to inject members**, whereas **MapStruct uses standard annotation processing to emit Java mapper implementations**. Consequently, upgrading the JDK can break Lombok's compatibility with compiler internals, while MapStruct can fail because processors are inactive or cannot see Lombok-created accessors/builders.

The sustainable strategy is **configuring processors explicitly, aligning versions with the compiler JDK, adding integration bindings when required, running clean builds, inspecting generated sources/class files, and testing real mappings**. Finally, verify generated classes reside inside the released artifact and execute on the runtime baseline. A “green” build is only a necessary precondition; migration succeeds only when APIs, generated outputs, and data behavior all satisfy the published contract.
