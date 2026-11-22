# Inspecting Generated Code, Service Providers, and Resources Inside JARs

During **Java Advance Compatibility Migration**, migrating an application from **Java EE to Jakarta EE** cannot stop at changing **javax.\*** imports to **jakarta.\***. A JAR may compile successfully while still containing **generated classes referencing old APIs**, **META-INF/services files registering the wrong interface**, or **XML and metadata still carrying legacy class names and schemas**. These artifacts are typically not checked when the compiler processes Java sources, yet they directly affect how ORMs, servlet containers, validators, and frameworks initialize at runtime.

This lesson belongs to the **Java EE and Jakarta** chapter and explains how to audit three artifact layers:

- **Generated code:** sources, classes, and resources produced by annotation processors, XJC, WSDL/OpenAPI generators, or other tools.
- **Service providers:** Java **ServiceLoader**, **META-INF/services/** files, and provider registrations in **module-info.java**.
- **JAR/WAR resources:** **persistence.xml**, **orm.xml**, **beans.xml**, **validation.xml**, **web.xml**, Spring metadata, manifests, and specialized resources.

The goal is verifying the **final artifact distributed and loaded in the deployment environment**, not merely searching strings in the repository or seeing a BUILD SUCCESS message.

## 1. Nature of the Java EE to Jakarta change

Starting with the Jakarta EE 9 transition, many Java EE APIs changed namespaces:

| Technology | Legacy namespace | Jakarta namespace |
|---|---|---|
| Persistence/JPA | **javax.persistence** | **jakarta.persistence** |
| Servlet | **javax.servlet** | **jakarta.servlet** |
| Bean Validation | **javax.validation** | **jakarta.validation** |
| CDI | **javax.enterprise** | **jakarta.enterprise** |
| REST/JAX-RS | **javax.ws.rs** | **jakarta.ws.rs** |
| XML Binding/JAXB | **javax.xml.bind** | **jakarta.xml.bind** |
| Annotations | **javax.annotation** | **jakarta.annotation** |
| Dependency injection | **javax.inject** | **jakarta.inject** |
| Messaging/JMS | **javax.jms** | **jakarta.jms** |
| Transaction API | **javax.transaction** | **jakarta.transaction** |

The JVM treats **javax.persistence.Entity** and **jakarta.persistence.Entity** as two distinct types. A Jakarta framework reading the new annotations will not automatically treat javax annotations as equivalent. An old provider implementing a javax interface does not automatically become a Jakarta provider either.

### 1.1. Some javax packages belong to Java SE and must not be changed

**Do not** replace every **javax.** with **jakarta.**. The following packages still belong to Java SE:

- **javax.annotation.processing** and **javax.lang.model**: annotation processing and compiler model.
- **javax.tools**: Compiler API.
- **javax.xml.parsers** and **javax.xml.transform**: Java SE XML APIs.
- **javax.crypto**, **javax.net**, **javax.sql**, **javax.management**.

For instance, the service descriptor name for annotation processors must still be:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

Do not create **META-INF/services/jakarta.annotation.processing.Processor**, because that interface is not a Jakarta API.

### 1.2. Compatibility layers

| Layer | Question | Example failure |
|---|---|---|
| Source | Does source use target APIs? | `javax.persistence` imports remain |
| Binary | Do compiled classes link cleanly? | NoSuchMethodError |
| Generated code | Do processors emit classes in the target namespace? | Metamodel still uses javax |
| Metadata | Are descriptors and XML correct? | Provider not found |
| Packaging | Are resources actually inside the JAR/WAR? | Service files lost during shading |
| Runtime | Does the framework bootstrap? | ServiceConfigurationError |
| Behavioral | Does functionality stay accurate? | Mapper changes null handling |

A single compilation pass checks only part of this table. A successful build must not be treated as proof of runtime compatibility.

## 2. Why inspect inside the JAR?

A JAR can have the structure:

~~~text
application.jar
  com/example/domain/Order.class
  com/example/generated/OrderMapperImpl.class
  META-INF/services/...
  META-INF/persistence.xml
  META-INF/orm.xml
  META-INF/beans.xml
  META-INF/spring/...
  META-INF/MANIFEST.MF
  module-info.class
  META-INF/versions/...
~~~

Each entry plays a different role:

1. **Class files**: loaded by the JVM to verify type identity.
2. **Generated classes**: used by the JVM or frameworks for mapping/DI/queries.
3. **META-INF/services**: read by ServiceLoader for provider registration.
4. **XML**: configuration read by JPA, CDI, Servlet, or integration frameworks.
5. **Spring metadata**: Spring Boot locates auto-configurations and handlers.
6. **Manifest/module descriptor**: governs launch/module/service metadata.
7. **Multi-release entries**: runtime may choose class variants per JDK.

Valid Java sources do not automatically cause text resources in META-INF to be updated. A generated file sitting in a build directory is not guaranteed to be included in the published artifact either.

## 3. Inventorying all code-generation sources

Tools commonly encountered in Java migrations:

| Tool | Typical output | Easy mistake |
|---|---|---|
| MapStruct | **MapperImpl.java/.class** | Processor fails to run, wrong dependency |
| JPA/Hibernate metamodel | **Customer_.java/.class** | javax versus jakarta metamodel |
| QueryDSL APT | **QCustomer.java/.class** | Processor variant targeting different namespace |
| Lombok | Getters/builders in bytecode | Uses javac internals, JDK support |
| JAXB XJC | Model classes, ObjectFactory, package-info | JAXB annotations javax/jakarta |
| WSDL/wsimport | Service stubs, binding types | Legacy-generation JAX-WS APIs |
| OpenAPI Generator | DTO/client/server sources | Generated dependency imports |
| Dagger, Immutables, AutoValue | Implementations/sources/metadata | Processor path and output ownership |

Directories you may encounter:

~~~text
target/generated-sources/annotations/
target/generated-test-sources/test-annotations/
build/generated/sources/annotationProcessor/java/main/
build/generated/sources/annotationProcessor/java/test/
build/generated/sources/...
~~~

Paths are illustrative only; each plugin can be configured differently. Create an inventory per module: **generator → version → input schema/annotations → output directory → generated classes/resources → consumers**.

### 3.1. Why generated code easily masks bugs

- Outputs are uncommitted, so searching the source tree misses them.
- Local workspaces retain outputs from an earlier compile.
- The IDE runs processors while CI lacks configuration.
- Build caches restore stale generated files.
- Another module consumes the generated classes.
- Generated code lives inside a dependency JAR rather than the application module.
- Tools emit metadata/resources rather than separate Java source files.

Therefore, run a **clean build from scratch** and inspect generated outputs produced by the exact target generator version.

## 4. MapStruct example in migration

Source interface:

~~~java
package com.example.mapping;

import org.mapstruct.Mapper;

@Mapper
public interface OrderMapper {
    OrderDto toDto(OrderEntity entity);
}
~~~

The processor can generate code equivalent to:

~~~java
package com.example.mapping;

// Illustrative code, not fixed output for every release.
public final class OrderMapperImpl implements OrderMapper {
    @Override
    public OrderDto toDto(OrderEntity entity) {
        if (entity == null) {
            return null;
        }
        OrderDto result = new OrderDto();
        result.setId(entity.getId());
        return result;
    }
}
~~~

Questions to verify:

1. Is the processor triggered by javac?
2. Is the processor compatible with the target Java compiler?
3. Is the generated implementation freshly created in a clean build?
4. Does it reference DTOs/entities in the target namespace?
5. Are generated classes included in the final JAR?
6. Does the runtime framework resolve the right implementation?
7. Does mapping for nulls, enums, and collections still match the contract?

If **OrderMapperImpl** was previously committed or remains in **target/classes**, builds may appear to pass even when annotation processing never ran.

## 5. JPA static metamodel example

Entity using Jakarta Persistence:

~~~java
package com.example.domain;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public class Customer {
    @Id
    private Long id;

    private String name;
}
~~~

A Jakarta-supporting metamodel processor can emit:

~~~java
package com.example.domain;

import jakarta.persistence.metamodel.SingularAttribute;
import jakarta.persistence.metamodel.StaticMetamodel;

@StaticMetamodel(Customer.class)
public abstract class Customer_ {
    public static volatile SingularAttribute<Customer, Long> id;
    public static volatile SingularAttribute<Customer, String> name;
}
~~~

A **Customer_.java** file still importing **javax.persistence.metamodel.SingularAttribute** signals stale output or an incompatible processor.

| Symptom | Cause to examine |
|---|---|
| Missing Customer_ | Processor did not run or did not recognize annotations |
| Customer_ exists yet uses javax | Legacy processor/version or stale code |
| Customer_ compiles because both APIs are on classpath | Mismatch masked by dependencies |
| Compiles cleanly yet query fails | Mapping/provider uses different namespace or behavior |

Do not add **javax.persistence-api** to a Jakarta runtime solely so an old generated metamodel keeps compiling, unless a dedicated adapter is intentionally designed.

### 5.1. QueryDSL

QueryDSL may ship separate processor artifacts/variants for different JPA namespaces. When migrating **javax.persistence** to **jakarta.persistence**, confirm the exact annotation processor variant and updated **Q-types**. Do not infer from library names alone that one artifact supports every release.

## 6. JAXB/XJC and generated XML-binding classes

With XJC or related code generators, Java output can move from:

~~~java
import javax.xml.bind.annotation.XmlElement;
import javax.xml.bind.annotation.XmlRootElement;
~~~

to:

~~~java
import jakarta.xml.bind.annotation.XmlElement;
import jakarta.xml.bind.annotation.XmlRootElement;
~~~

After Java 11, legacy JAXB modules/tools once bundled with some JDKs are no longer built into the JDK; explicit dependencies and matching generators are required.

Artifacts that may appear:

~~~text
Order.java
ObjectFactory.java
package-info.java
jaxb.index
jaxb.properties
~~~

Cross-check:

- XJC/generator version.
- Jakarta XML Binding API/runtime version.
- Binding files and customization namespaces.
- Generated **ObjectFactory** and **package-info**.
- Runtime resource lookup.
- Whether legacy/new XML samples marshal and unmarshal properly.

**Important:** Changing the Java API from javax.xml.bind to jakarta.xml.bind does not automatically require changing **business XML data** namespaces defined by external partners. Wire XML Schema contracts are a separate concern.

### 6.1. An API is not a runtime implementation

Having the Jakarta XML Binding API on the compile classpath does not mean a JAXB runtime provider is packaged. Instantiate **JAXBContext** and perform at least one round-trip to confirm the provider works.

## 7. Annotation processors and JDK activation changes

A standard annotation processor implements:

~~~java
javax.annotation.processing.Processor
~~~

and is usually registered via:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

Even when a project moves completely to Jakarta APIs, this Java SE service type **does not change**.

Starting in **JDK 23**, javac no longer enables implicit annotation processing by default when explicit processing configuration is absent. JDK 21/22 already emitted notes when builds relied on implicit classpath discovery.

A migration can hit two separate bugs:

1. The processor never runs because the build omits an explicit processor path.
2. The processor runs yet only recognizes legacy javax annotations.

Fixing the first bug does not fix the second automatically.

### 7.1. Gradle

~~~groovy
plugins {
    id 'java'
}

dependencies {
    implementation 'org.mapstruct:mapstruct:VERSION'
    annotationProcessor 'org.mapstruct:mapstruct-processor:VERSION'
}
~~~

If test sources use annotation processing:

~~~groovy
dependencies {
    testAnnotationProcessor 'org.mapstruct:mapstruct-processor:VERSION'
}
~~~

**VERSION** must be replaced with a release confirmed to support the target JDK/framework. Placing a processor only in **implementation** is not a reliable explicit declaration.

### 7.2. Maven Compiler Plugin 3.x

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-compiler-plugin</artifactId>
  <version>3.14.1</version>
  <configuration>
    <release>17</release>
    <annotationProcessorPaths>
      <path>
        <groupId>org.mapstruct</groupId>
        <artifactId>mapstruct-processor</artifactId>
        <version>1.6.3</version>
      </path>
    </annotationProcessorPaths>
  </configuration>
</plugin>
~~~

The versions in the example illustrate syntax. Maven 4 and compiler plugin 4.x trend toward managing processors through dedicated dependency types such as **processor**, **classpath-processor**, or **modular-processor**. Configuration must match the build tool version.

### 7.3. Compiler JDK differs from target Java release

If javac runs on JDK 23 using **--release 17**, processors still execute inside the JDK 23 javac environment; only application output is constrained to the Java 17 target. For processors accessing **jdk.compiler** internals such as some Lombok integrations, a newer compiler JDK may require a newer processor release.

Do not treat **--release 17** as a way to emulate running the processor on JDK 17.

## 8. How does Java ServiceLoader work?

**ServiceLoader** discovers provider implementations for a service interface. On the classpath, the common mechanism uses files:

~~~text
META-INF/services/<service-interface-full-name>
~~~

Example:

~~~text
META-INF/services/com.example.spi.TextFormatter
~~~

Content:

~~~text
com.example.provider.DefaultTextFormatter
com.example.provider.PrettyTextFormatter
~~~

The file name must be the fully qualified name of the **service interface**, while the lines inside are provider class names.

### 8.1. Service API example

~~~java
package com.example.spi;

public interface TextFormatter {
    String format(String input);
}
~~~

Provider:

~~~java
package com.example.provider;

import com.example.spi.TextFormatter;

public final class DefaultTextFormatter implements TextFormatter {
    public DefaultTextFormatter() {
    }

    @Override
    public String format(String input) {
        return input == null ? "" : input.trim();
    }
}
~~~

Resource:

~~~text
src/main/resources/META-INF/services/com.example.spi.TextFormatter
~~~

Content:

~~~text
com.example.provider.DefaultTextFormatter
~~~

Consumer:

~~~java
package com.example.app;

import com.example.spi.TextFormatter;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        TextFormatter formatter = ServiceLoader
            .load(TextFormatter.class)
            .findFirst()
            .orElseThrow(() ->
                new IllegalStateException("No provider"));

        System.out.println(formatter.format("  Hello  "));
    }
}
~~~

With proper classpath and packaging, the output is **Hello**.

### 8.2. A provider class existing does not mean it can be loaded

A provider must also:

- Implement the exact service type.
- Have all transitive dependencies present.
- Be visible to the appropriate classloader.
- Have a valid instantiation path per ServiceLoader rules.
- Avoid relocation causing the descriptor to point to an old name.
- Not conflict with another copy of the API at runtime.

The presence of a **META-INF/services** file is only one step in verification.

## 9. Service descriptors when migrating javax to jakarta

The following two files are **two distinct resources**:

~~~text
META-INF/services/javax.persistence.spi.PersistenceProvider
META-INF/services/jakarta.persistence.spi.PersistenceProvider
~~~

A Jakarta Persistence runtime searching for **jakarta.persistence.spi.PersistenceProvider** will not automatically treat the javax descriptor as equivalent.

Examples:

| Provider type | Legacy service descriptor | Jakarta |
|---|---|---|
| JPA | **javax.persistence.spi.PersistenceProvider** | **jakarta.persistence.spi.PersistenceProvider** |
| Bean Validation | **javax.validation.spi.ValidationProvider** | **jakarta.validation.spi.ValidationProvider** |
| Servlet initializer | **javax.servlet.ServletContainerInitializer** | **jakarta.servlet.ServletContainerInitializer** |
| Compiler annotation processor | **javax.annotation.processing.Processor** | **Keep javax unchanged** |

The names in this table belong under **META-INF/services/** when using the corresponding file-based service discovery mechanism.

### 9.1. JPA provider

A Jakarta-compatible JPA provider JAR may contain:

~~~text
META-INF/services/jakarta.persistence.spi.PersistenceProvider
~~~

with an example provider class:

~~~text
org.hibernate.jpa.HibernatePersistenceProvider
~~~

This class name must exist in the right artifact version, and the class must actually implement the Jakarta Persistence SPI. Merely editing the service descriptor content is insufficient to turn a javax implementation into Jakarta.

### 9.2. Bean Validation

For Jakarta Validation, you need the **jakarta.validation.Validation** API, **jakarta.validation.spi.ValidationProvider** SPI, and a compatible runtime implementation. A project compiling **@NotNull** cleanly can still fail when building a validator factory if runtime provider discovery fails.

### 9.3. ServletContainerInitializer

Jakarta Servlet applications require implementations of **jakarta.servlet.ServletContainerInitializer**. An older extension JAR carrying only **javax.servlet.ServletContainerInitializer** will not be recognized by a Jakarta container as the same initializer.

A WAR may deploy without failing immediately, yet expected listeners/filters/initializers are never registered. This is a runtime metadata failure rather than a source compilation error.

## 10. JPMS and module-info.java

With the Java Platform Module System, explicit named modules can declare:

~~~java
module com.example.formatter.provider {
    requires com.example.formatter.api;

    provides com.example.spi.TextFormatter
        with com.example.provider.DefaultTextFormatter;
}
~~~

Consumer module:

~~~java
module com.example.formatter.app {
    requires com.example.formatter.api;

    uses com.example.spi.TextFormatter;
}
~~~

These are illustrative module names. The API module must export the service interface package, and provider/consumer modules must form a valid module graph.

| Packaging | Mechanism typically inspected |
|---|---|
| Plain JAR on classpath | META-INF/services |
| Explicit named module | uses/provides in module-info |
| Automatic module | Automatic module rules and service registration |
| WAR/EAR/container | Classloader/container resource discovery |
| Nested executable JAR | Launcher resource loading |

### 10.1. Classloaders can decide success or failure

In application servers or plugin architectures, the same fully qualified name loaded by two classloaders represents two distinct runtime types. A provider implementing one copy of an interface while a consumer uses another copy can trigger **ServiceConfigurationError** or **ClassCastException**.

One diagnostic snippet:

~~~java
ClassLoader loader =
    Thread.currentThread().getContextClassLoader();

ServiceLoader<TextFormatter> providers =
    ServiceLoader.load(TextFormatter.class, loader);
~~~

Switching loaders is only a diagnostic test; if an API dependency is loaded twice, fix ownership and classloader isolation.

### 10.2. Inspecting module metadata

~~~bash
jar --describe-module --file provider.jar
~~~

Inspect **module-info.class**, **Automatic-Module-Name** if present, and service directives. Do not guess module names from artifactId alone.

## 11. Shaded/fat JARs: risk of dropping service files

Two JARs can both contain:

~~~text
META-INF/services/com.example.spi.TextFormatter
~~~

JAR A lists **ProviderA**, and JAR B lists **ProviderB**. When assembling a fat JAR that keeps only one copy of the resource, the other provider disappears.

The expected outcome is a merged service file:

~~~text
com.example.provider.ProviderA
com.example.provider.ProviderB
~~~

### 11.1. Maven Shade

You can use **ServicesResourceTransformer**:

~~~xml
<transformers>
  <transformer
      implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
</transformers>
~~~

### 11.2. Gradle Shadow

Illustrative configuration:

~~~groovy
tasks.named('shadowJar') {
    mergeServiceFiles()
}
~~~

Actual configuration depends on the plugin version. After shading, inspect the final JAR to confirm service descriptors and provider classes are preserved.

### 11.3. Relocation changes class names

If shading renames:

~~~text
com.example.provider.ProviderA
~~~

to:

~~~text
hidden.com.example.provider.ProviderA
~~~

while the service file still points to the old name, the provider fails to load. Check transformer and relocation rules.

### 11.4. Other resources cannot be merged by appending lines

- **META-INF/persistence.xml**
- **META-INF/beans.xml**
- **META-INF/spring.handlers**
- **META-INF/spring.schemas**
- **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

A resource merge strategy suitable for ServiceLoader does not necessarily work for XML, properties, or Spring metadata. Never merge two XML documents by text concatenation.

## 12. META-INF/persistence.xml and Jakarta Persistence

A Jakarta JPA deployment can use:

~~~text
META-INF/persistence.xml
~~~

Jakarta Persistence 3.0 example:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        https://jakarta.ee/xml/ns/persistence
        https://jakarta.ee/xml/ns/persistence/persistence_3_0.xsd"
    version="3.0">

    <persistence-unit name="ordersPU"
                      transaction-type="RESOURCE_LOCAL">
        <class>com.example.domain.OrderEntity</class>
        <properties>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:h2:mem:orders"/>
        </properties>
    </persistence-unit>
</persistence>
~~~

This configuration is structural only. Databases, datasources, providers, and transaction management must be tailored for the real runtime.

### 12.1. Items to verify

- Do the XML namespace and schema version match the Jakarta release?
- Does the persistence unit name still match?
- Do entity classes exist?
- Does mapping-file **orm.xml** have the right path and namespace?
- Is any explicitly declared provider class still valid?
- Do property keys belong to the API/framework version?
- Is the file actually packaged in the JAR/WAR?
- Does persistence unit bootstrapping succeed at runtime?

### 12.2. Do not overlook XML mappings

**META-INF/orm.xml** can contain entity class names, field names, access modes, and relationship mappings. Converting Java annotations to Jakarta does not automatically alter XML inside another dependency JAR.

## 13. Other descriptors in JARs/WARs

### 13.1. CDI

Commonly found:

~~~text
META-INF/beans.xml
WEB-INF/beans.xml
~~~

Check the CDI version, XML schema, **bean-discovery-mode**, bean archive behavior, and class names. Bean discovery rules can change across framework/runtime versions; do not assume an empty file always behaves identically.

### 13.2. Servlet

A WAR typically contains:

~~~text
WEB-INF/web.xml
~~~

Jakarta Servlet 6.0 example:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<web-app
    xmlns="https://jakarta.ee/xml/ns/jakartaee"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        https://jakarta.ee/xml/ns/jakartaee
        https://jakarta.ee/xml/ns/jakartaee/web-app_6_0.xsd"
    version="6.0">
</web-app>
~~~

This schema does not apply to every Servlet container. Choose a descriptor version matching supported containers. Beyond XML namespaces, check servlet/filter/listener FQCNs and init-params.

### 13.3. WAR layout

~~~text
application.war
  WEB-INF/classes/com/example/...
  WEB-INF/classes/META-INF/persistence.xml
  WEB-INF/lib/provider.jar
  WEB-INF/lib/other.jar
  WEB-INF/web.xml
~~~

Service descriptors may reside in a dependency JAR under **WEB-INF/lib**. Checking only the root WAR is insufficient; inspect nested JARs and classloaders as well.

### 13.4. Other notable resources

- **META-INF/validation.xml** when using Bean Validation XML.
- **META-INF/web-fragment.xml** in web libraries.
- Taglib/TLD resources.
- **META-INF/spring.factories**, **spring.handlers**, **spring.schemas**.
- **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**.
- **META-INF/native-image/**.
- **META-INF/MANIFEST.MF**.
- **module-info.class**.
- **META-INF/versions/** in multi-release JARs.

## 14. Spring Boot auto-configuration resources

In many Spring Boot libraries, auto-configuration is declared in:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Its content lists auto-configuration class names:

~~~text
com.example.autoconfigure.OrdersAutoConfiguration
com.example.autoconfigure.OrdersMetricsAutoConfiguration
~~~

Spring Boot 2.7 introduced support for the imports mechanism, and Spring Boot 3 uses it for auto-configuration instead of registering via the corresponding key in **spring.factories**.

### 14.1. Do not delete spring.factories blindly

**spring.factories** can still be used for other extension points depending on the Spring version. Determine which resources the target framework reads.

Additionally, an auto-config class may exist while **@ConditionalOnClass** or similar conditions still reference **javax.servlet.\***, preventing the configuration from activating as intended on the Jakarta stack.

### 14.2. Resources lost during shading

If multiple dependencies contribute **AutoConfiguration.imports** and a fat JAR keeps only one copy, the remaining auto-configurations vanish. Verify the proper merge strategy for this format instead of assuming **mergeServiceFiles()** handles it.

## 15. Inspecting JARs with JDK tools

### 15.1. Listing entries

~~~bash
jar tf application.jar
~~~

Or:

~~~bash
jar --list --file application.jar
~~~

Look for paths:

~~~text
META-INF/services/
META-INF/persistence.xml
META-INF/orm.xml
META-INF/beans.xml
META-INF/spring/
META-INF/MANIFEST.MF
module-info.class
META-INF/versions/
com/example/generated/
~~~

### 15.2. Reading service descriptors

On systems with unzip:

~~~bash
unzip -p application.jar META-INF/services/com.example.spi.TextFormatter
~~~

Or extract into a **separate inspection directory**:

~~~bash
jar xf application.jar META-INF/services/com.example.spi.TextFormatter
~~~

Avoid extracting over the source workspace. An existing entry does not guarantee its content is right; read the service class names inside.

### 15.3. Inspecting class files

~~~bash
javap -classpath application.jar -p com.example.domain.Customer
~~~

To inspect additional metadata/constant pool entries:

~~~bash
javap -classpath application.jar -v com.example.domain.Customer
~~~

You can look for suspicious **javax.persistence** references. However, `javax` strings inside a JAR are not automatically errors because valid Java SE `javax` packages exist.

### 15.4. jdeps

~~~bash
jdeps --recursive --multi-release 21 application.jar
~~~

Check internal JDK APIs:

~~~bash
jdeps --jdk-internals application.jar
~~~

**jdeps** does not replace checking text resource files or class names written purely as XML or ServiceLoader strings. Clean output does not prove metadata migration succeeded.

### 15.5. JPMS metadata

~~~bash
jar --describe-module --file application.jar
~~~

For multi-release JARs, check which class/module variant is selected on the target runtime JDK.

### 15.6. Tying the artifact to a checksum

PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 -LiteralPath application.jar
~~~

Unix:

~~~bash
sha256sum application.jar
~~~

Collect evidence that the inspected file is the exact file published/deployed, rather than another artifact rebuilt inside a container image.

## 16. Automating entry checks with JarFile

~~~java
package com.example.verify;

import java.io.IOException;
import java.nio.file.Path;
import java.util.jar.JarFile;

public final class JarInspector {
    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException("JAR path required");
        }

        try (JarFile jar = new JarFile(Path.of(args[0]).toFile())) {
            requireEntry(
                jar,
                "META-INF/services/com.example.spi.TextFormatter"
            );
            requireEntry(
                jar,
                "com/example/provider/DefaultTextFormatter.class"
            );
        }
    }

    private static void requireEntry(JarFile jar, String path) {
        if (jar.getJarEntry(path) == null) {
            throw new IllegalStateException("Missing: " + path);
        }
    }
}
~~~

This is a **structural test**: checking entry presence. It neither reads descriptor contents nor attempts to instantiate the provider.

### 16.1. Verification levels

1. **Structural:** resource/class exists inside the archive.
2. **Metadata:** resource contains the right service/provider/namespace/version.
3. **Runtime:** framework/ServiceLoader instantiates the provider successfully.
4. **Behavioral:** business functionality produces expected results.

A test at level 1 does not substitute for levels 3 and 4. Set acceptance criteria commensurate with risk.

## 17. ServiceLoader smoke test

Example with JUnit 5:

~~~java
import com.example.spi.TextFormatter;
import java.util.ServiceLoader;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertTrue;

class ProviderDiscoveryTest {
    @Test
    void findsProvider() {
        boolean found = ServiceLoader.load(TextFormatter.class)
            .stream()
            .anyMatch(provider ->
                provider.type().getName().equals(
                    "com.example.provider.DefaultTextFormatter"
                )
            );

        assertTrue(found);
    }
}
~~~

**Note:** if tests run against the **build/classes + build/resources** classpath, they can miss JAR packaging defects. For an artifact-release gate, run tests using the **final JAR** and proper launch mechanism.

### 17.1. Verifying JPA

- Bootstrap the Jakarta Persistence unit.
- Confirm the selected provider and version.
- Initialize the entity manager factory.
- Execute a representative persistence operation.
- Close resources cleanly.

### 17.2. Verifying Bean Validation

~~~java
import jakarta.validation.Validation;

var factory = Validation.buildDefaultValidatorFactory();
try {
    var validator = factory.getValidator();
    // Validate a real object with constraints.
} finally {
    factory.close();
}
~~~

Compiling **@NotNull** does not prove a runtime validation provider is present. Run at least one real bootstrap and validation pass.

### 17.3. Verifying JAXB

Create a **jakarta.xml.bind.JAXBContext** and marshal/unmarshal sample data. If the API JAR is present without a runtime implementation, errors typically surface only when creating the context.

### 17.4. Verifying Servlet

For WARs, test deployment on a compatible Jakarta Servlet container. Standalone ServiceLoader tests do not fully replicate container lifecycle and classloader rules.

## 18. Common failures and investigation steps

| Failure / symptom | Possible cause | Verification step |
|---|---|---|
| **ServiceConfigurationError** | Wrong descriptor or provider | Inspect META-INF/services and cause |
| **ClassNotFoundException** | Resource references class name that no longer exists | Inspect JAR entries, classloader |
| **NoClassDefFoundError** | Provider lacks a dependency | Runtime graph, static initializer |
| **ClassCastException** | Provider does not match service type | javax/jakarta mismatch, classloader |
| **NoSuchMethodError** | Binary API/provider versions mismatch | Check javap and JAR versions |
| **AbstractMethodError** | SPI contract differs from implementation | Compare interface/method signatures |
| **IllegalAccessError** | Incorrect module access or binary access | Check JPMS, class metadata |
| **No Persistence provider** | Incompatible JPA service/bootstrap | persistence.xml, provider JAR |
| **Validation provider missing** | API and implementation use different namespaces | Validation SPI |
| **JAXBException** at bootstrap | Runtime JAXB implementation/metadata missing | JAXB artifacts |
| **cannot find symbol** for generated type | Processor failed to run or output stale | Clean compile, processor path |
| **FilerException** | Processor writes duplicate files | Processing rounds, output dirs |
| Spring auto-config ignored | Wrong metadata/class/condition | AutoConfiguration.imports |
| XML parse/schema error | Wrong resource namespace/version | XML inside final artifact |

Read the full stack trace, cause chain, provider name, and actually loaded artifact. Do not patch over every failure by adding another javax JAR.

## 19. Multi-release JARs and manifest

A multi-release JAR can contain:

~~~text
META-INF/MANIFEST.MF
META-INF/versions/9/module-info.class
META-INF/versions/17/com/example/SomeClass.class
com/example/SomeClass.class
~~~

When the manifest has **Multi-Release: true**, the runtime can pick a class variant based on the JDK version. Upon upgrading the JDK, the loaded variant may differ from the baseline and still reference an old Java EE namespace.

Inspect:

- Manifest.
- Base classes and relevant variants.
- Class-file versions.
- Module metadata.
- Per-variant dependencies.
- Service registrations per specification rules, without assuming service files themselves are versioned automatically.

Useful commands:

~~~bash
jar tf library.jar
jar --describe-module --file library.jar
jdeps --multi-release 17 library.jar
~~~

## 20. Packaging and real class loaders

### 20.1. Plain JAR

The runtime classpath sees classes/resources directly at the archive root. This differs from nested executable JARs.

### 20.2. Spring Boot executable JAR

Some Boot JARs contain nested libraries and a custom launcher. The proper run command may be:

~~~bash
java -jar application.jar
~~~

Testing with **java -cp application.jar com.example.Main** is not always equivalent because nested JARs and resource loaders behave differently. When verifying providers, use the real production launch mechanism.

### 20.3. WAR

A Jakarta Servlet container may supply runtime APIs while the application supplies implementation libraries. Check:

- Does the WAR accidentally package legacy servlet APIs?
- Which Jakarta Servlet version does the container support?
- Are WEB-INF/classes and WEB-INF/lib accurate?
- Are WEB-INF/web.xml and service descriptors accurate?
- Does ServletContainerInitializer execute?

### 20.4. EAR/container shared libraries

If the provider lives in a server-shared library while the API sits inside the WAR, classloader isolation or duplicate classes can occur. A JAR that looks right on disk is not guaranteed to be loaded by the right loader.

### 20.5. Container images

The tested artifact may differ from the file copied into an image. Cross-check checksums and entry listings at the exact deployment stage.

## 21. Dependency graph: simultaneous javax and jakarta

Example:

~~~text
application
  +-- jakarta.persistence-api
  +-- Hibernate compatible with Jakarta
  +-- legacy-validation-extension
        +-- javax.validation-api
  +-- jakarta.validation-api
~~~

Having both APIs present simultaneously is not automatically wrong in every scenario, yet requires confirming whether an intentional adapter exists. If an extension was compiled against **javax.validation.spi.ValidationProvider**, it will not serve **jakarta.validation.Validation** on its own.

Distinguish three path groups:

- **Compile classpath:** which APIs do sources require?
- **Processor path:** which code generators run?
- **Runtime classpath/module path:** which provider implementations and resources exist?

Inspection commands:

~~~bash
mvn dependency:tree
~~~

or:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration annotationProcessor
~~~

The dependency graph proves versions and paths, yet does not reliably reveal every service resource after shading.

## 22. Artifact verification matrix

| Case | Source/generated | Packaging | Runtime | What must be proven |
|---|---|---|---|---|
| Java EE baseline | javax | Legacy JAR/WAR | Legacy stack | Baseline behavior |
| New generated code | jakarta | Compile output | Target javac | Generated code accurate |
| Plain Jakarta JAR | jakarta | META-INF/services | Classpath | SPI discovery |
| Named module | jakarta | module-info | Module path | uses/provides |
| Shaded JAR | jakarta | Merged descriptors | Real launcher | No dropped providers |
| WAR | jakarta | WEB-INF/META-INF | Jakarta container | Deployment |
| Spring starter | jakarta | AutoConfiguration.imports | Boot target | Auto-config |
| Clean CI | jakarta | Reproducible artifact | Target JDK | No stale files used |
| Negative case | javax provider | Jakarta API consumer | Target runtime | Mismatch caught |

Tests should follow this sequence:

1. Clean compilation/code generation.
2. Inspect generated source namespaces.
3. Inspect artifact entries.
4. Read service/XML metadata.
5. Bootstrap providers at runtime.
6. Run integration behavior tests.
7. Verify artifact checksums and launch layout.

Do not force unsupported legacy/Jakarta combinations to pass. The aim is catching mismatches early.

## 23. Gate-based migration workflow

### Gate A — Inventory

- Lock down JDK/framework/Java EE/Jakarta versions.
- List processors, generators, and outputs.
- List SPI names and provider classes.
- List JAR/WAR resources.
- Identify classloader/packaging layouts.
- Store baseline artifacts and checksums.

### Gate B — Generated code

- Upgrade processors/generators to Jakarta-supporting releases.
- Configure annotation processing explicitly.
- Run clean builds.
- Verify outputs use the right namespace.
- Eliminate reliance on stale generated files.
- Confirm generated classes are packaged.

### Gate C — Services and resources

- Use Jakarta SPI descriptor names for migrated APIs.
- Preserve **javax.annotation.processing.Processor**.
- Verify provider classes and dependencies.
- Update XML schemas/versions/class names.
- Verify Spring metadata and shading rules.
- Verify module-info/manifest/multi-release entries.

### Gate D — Runtime

- Run the artifact inside the target JDK/container.
- Test ServiceLoader.
- Test JPA/Validation/JAXB bootstrap.
- Test Servlet/Spring integration.
- Test normal behavior and error paths.
- Finalize release evidence.

### Gate E — Cleanup

- Remove old dependencies/adapters once no consumers remain.
- Clear stale generator outputs per build lifecycle.
- Remove unneeded packaging workarounds.
- Update build templates and documentation.
- Record rollback pairings and approved exceptions.

## 24. Result recording template

~~~text
Migration ID:
Module / component:
Owner:
Baseline Java EE/JDK:
Target Jakarta EE/JDK:
Framework and container versions:
Packaging: jar / bootJar / war / ear / module

Code generators and versions:
Annotation APIs and processors:
Generated directories:
Generated classes/resources:
Namespace scan result:

Service interface old/new:
Provider implementation:
Service descriptor paths:
JPMS uses/provides:
Classloader expectations:

XML/resource inventory:
persistence.xml:
orm.xml:
beans.xml:
validation.xml:
web.xml:
Spring metadata:
Manifest/multi-release:
Shade/relocation/merge:

Artifact checksum:
Structural checks:
Provider bootstrap tests:
Business integration tests:
Legacy adapters:
Rollback plan:
Blockers:
Owner approval:
~~~

This template establishes traceability from code generators through packaged files down to runtime consumers.

## 25. Pre-release checklist

### Generated code

- [ ] Inventoried all processors and generators.
- [ ] Upgraded tools to versions supporting Jakarta namespaces.
- [ ] Configured annotation processing explicitly.
- [ ] Checked test and main source sets separately.
- [ ] Confirmed generated files come from a clean build.
- [ ] Verified no stale generated artifacts hide errors.
- [ ] Confirmed generated sources carry no unapproved legacy APIs.
- [ ] Verified generated classes/resources exist inside the final JAR/WAR.

### Service providers

- [ ] Service descriptor names match interfaces.
- [ ] Jakarta service names are properly updated.
- [ ] **javax.annotation.processing.Processor** is left unchanged.
- [ ] Providers implement the right Jakarta SPI.
- [ ] Provider dependencies exist at runtime.
- [ ] Classloader/JPMS configuration is accurate.
- [ ] Shaded JARs merge descriptors properly.
- [ ] Runtime ServiceLoader/provider bootstrapping succeeds.

### Resources

- [ ] persistence.xml and orm.xml match the runtime.
- [ ] beans.xml, validation.xml, and web.xml match the framework.
- [ ] Spring metadata and custom resources are preserved.
- [ ] All FQCNs in XML/properties are verified.
- [ ] Manifests and multi-release variants are inspected.
- [ ] Business XML namespaces outside contracts are untouched.
- [ ] Nested JARs and WAR layouts are inspected.
- [ ] Inspected artifact checksum matches deployed artifact.

### Operations

- [ ] Clean CI verifies generated outputs.
- [ ] Structural, metadata, and runtime tests exist.
- [ ] Compilation success alone is not treated as sufficient.
- [ ] Not all `javax` packages were blindly replace-all converted.
- [ ] No legacy API was added merely to hide mismatches.
- [ ] Release gates, owners, and rollback plans are in place.
- [ ] Supported adapters/legacy exceptions are documented.

## 26. References

- **Jakarta EE Specifications:** https://jakarta.ee/specifications/
- **Jakarta Persistence:** https://jakarta.ee/specifications/persistence/
- **Jakarta Servlet:** https://jakarta.ee/specifications/servlet/
- **Jakarta Bean Validation:** https://jakarta.ee/specifications/bean-validation/
- **Jakarta XML Binding:** https://jakarta.ee/specifications/xml-binding/
- **Java ServiceLoader:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html
- **Java JarFile:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/jar/JarFile.html
- **Java Annotation Processing:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/annotation/processing/package-summary.html
- **javac tool:** https://docs.oracle.com/en/java/javase/23/docs/specs/man/javac.html
- **Spring Boot Auto-Configuration:** https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- **Maven Shade Resource Transformers:** https://maven.apache.org/plugins/maven-shade-plugin/examples/resource-transformers.html
- **Gradle Shadow:** https://gradleup.com/shadow/configuration/merging/
- **JAR tool:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html

Every example must be cross-checked against actual Java/Jakarta/Servlet/Spring/Hibernate/build-tool versions. Configuration valid only on a newer release does not automatically apply to a project running on an older platform.

---

**Conclusion:** Migrating Java EE to Jakarta is not finished once Java imports are updated. You must verify **generated sources/classes**, **META-INF/services and provider implementations**, **XML/resources inside JARs/WARs**, and how they are loaded at runtime. A dependable process combines clean code generation, inspecting the final artifact, verifying service/interface names, testing provider bootstrapping, and running integration tests in the target container. **Compilation passing yet providers failing to be discovered** is a classic migration defect; auditing all three layers—generated code, services, and resources—prevents it before release.
