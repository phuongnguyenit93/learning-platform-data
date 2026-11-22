# Externally Provided JAXB, JAX-WS, Activation, and Code Generation Tools

When migrating a Java application from an older JDK to a modern JDK, the development team may encounter errors even though business code barely changed: `package javax.xml.bind does not exist`, `package javax.xml.ws does not exist`, `NoClassDefFoundError: javax/activation/DataHandler`, or the `xjc` and `wsimport` commands can no longer be found in the JDK's `bin` directory. This is not necessarily a bug in JAXB, SOAP, or WSDL; the underlying cause is that several APIs and tools previously shipped with the JDK have been removed from the Java SE distribution.

Starting in **JDK 11**, under **JEP 320**, the Java EE/CORBA modules previously bundled with the JDK—including JAXB, JAX-WS, and JavaBeans Activation Framework (JAF)—are no longer packaged with the JDK. Related tools such as `xjc`, `schemagen`, `wsimport`, and `wsgen` are also no longer provided as built-in JDK programs. To continue using these technologies on JDK 11, 17, 21, or later, the project must proactively manage **APIs, implementations/runtimes, providers, build plugins, and code generation tools** as external dependencies.

Alongside the distribution change, the Java EE ecosystem transitioned to Jakarta EE. Earlier API generations still use `javax.*` packages, while newer Jakarta EE generations use `jakarta.*`. These two naming systems are not binary-equivalent. Choosing the right external library but the wrong namespace generation can still prevent the application from compiling or cause runtime errors.

This lesson provides an understanding of the history of these changes, distinguishes the roles of each component, explains how to select appropriate dependencies, configure code generation from XSD/WSDL, troubleshoot compatibility errors, and establish a verifiable migration process.

## 1. Why Did These Technologies Disappear from the JDK?

### 1.1. From JDK 8 to JDK 11

On many JDK 8 distributions, developers could import JAXB and JAX-WS without declaring external libraries. Several code generation tools were also located in `JAVA_HOME/bin`.

Example:

```java
import javax.xml.bind.JAXBContext;
import javax.xml.bind.Marshaller;
import javax.xml.ws.Service;
import javax.activation.DataHandler;
```

And commands that may be familiar:

```bash
xjc -d generated src/main/xsd/customer.xsd
wsimport -keep -s generated src/main/wsdl/CustomerService.wsdl
```

Starting in JDK 9, the related modules were marked deprecated for removal. By **JDK 11**, JEP 320 removed them from the JDK. Consequently, the exact same repository may build on JDK 8 yet fail during compilation or code generation when moving to JDK 17/21.

### 1.2. Directly Related Removed Modules

| Component previously bundled with the JDK | Related module before removal | Primary purpose |
|---|---|---|
| JAXB API | `java.xml.bind` | Java object ↔ XML mapping |
| JAX-WS API | `java.xml.ws` | SOAP web services and clients |
| JavaBeans Activation Framework | `java.activation` | MIME types, DataHandler, DataSource |
| Common Annotations subset | `java.xml.ws.annotation` | Certain annotations used by these stacks |
| JAXB tools | `jdk.xml.bind` | `xjc`, `schemagen` |
| JAX-WS tools | `jdk.xml.ws` | `wsimport`, `wsgen` |

JEP 320 also covers other modules such as CORBA; this lesson focuses on JAXB, JAX-WS, Activation, and generators.

**Point to distinguish:** not every package named `javax.xml.*` was removed. Java XML Processing APIs such as `javax.xml.parsers`, `javax.xml.transform`, `javax.xml.namespace`, `javax.xml.stream`, DOM, and SAX still belong to Java SE XML APIs, mainly in the `java.xml` module. Do not mechanically replace all `javax.xml.*` with `jakarta.xml.*`.

### 1.3. On JDK 17 or 21, the Issue Already Existed Before

If an application is currently running on JDK 17 and plans to upgrade to JDK 21, JAXB/JAX-WS no longer being bundled is a condition that has existed since JDK 11, not a change specific to JDK 21.

However, the issue may only surface during an upgrade because CI or a generator task previously still ran on JDK 8, the application runtime used a different image, the IDE had hidden dependencies, or an older plugin pulled `javax.*` classes onto the classpath. The migration must lock down the actual JDK version at every step: build, generate, compile, test, package, and production runtime.

## 2. Distinguishing APIs, Runtime Implementations, and Code Generation Tools

These components serve different roles; they cannot substitute for one another.

| Group | Role | Example |
|---|---|---|
| API | Contains interfaces, annotations, and contracts that compiled source depends on | `JAXBContext`, `Marshaller`, `Service`, `DataHandler` |
| Implementation/runtime | Executes the APIs at runtime | JAXB Runtime, Metro JAX-WS RI, Apache CXF |
| Provider/service discovery | Allows the API to locate the corresponding implementation | Provider declared via SPI/ServiceLoader or an implementation-specific mechanism |
| Generator | Generates source or metadata from a schema/service contract | JAXB XJC, JAX-WS wsimport, CXF wsdl2java |
| Build plugin | Integrates the generator into Maven/Gradle and the task graph | XJC plugin, CXF Codegen Plugin, Metro tools integration |
| Runtime integration | Connects with HTTP transport, servlets, SOAP attachments, security, and service registry | Endpoint runtime, SOAP binding, MTOM, transport |

A compilation error `package ... does not exist` usually indicates a missing API on the compile classpath. Conversely, a "provider not found" error after successful compilation usually indicates that a suitable implementation/runtime is missing or cannot be discovered.

Having `xjc` generate Java code does not mean the program has a JAXB runtime to marshal/unmarshal. Having `wsimport` generate SOAP stubs does not mean the application has a JAX-WS provider, HTTP transport, and dependencies needed to send requests.

## 3. Two Namespace Generations: `javax.*` and `jakarta.*`

### 3.1. Why Is the Library Name Not Enough to Infer the Package?

When Java EE technologies transitioned to Jakarta EE, an initial phase kept `javax.*` packages while changing artifact names or maintaining organizations. Subsequent Jakarta EE generations then changed the public namespace to `jakarta.*`.

For migration, rely on **the packages actually contained in the JAR** and the framework's compatibility matrix, not merely on whether the artifact name contains the word "jakarta".

| Technology family | Common legacy API branch | Common newer API branch |
|---|---|---|
| JAXB | `javax.xml.bind.*` | `jakarta.xml.bind.*` |
| JAX-WS | `javax.xml.ws.*` | `jakarta.xml.ws.*` |
| Activation | `javax.activation.*` | `jakarta.activation.*` |
| Web Services Metadata annotations | `javax.jws.*` | `jakarta.jws.*` |
| Common Annotations | `javax.annotation.*` | `jakarta.annotation.*` |

Under the common version split, JAXB/JAX-WS 2.x generations use `javax.*`, whereas 3.x and later generations use `jakarta.*`. Activation 1.x uses `javax.activation.*`, and 2.x uses `jakarta.activation.*`. Always verify the specific release because Maven coordinates and Jakarta EE labels do not always directly indicate the package namespace.

### 3.2. The Two Namespaces Are Not Interchangeable at the Bytecode Level

Example:

```java
// Type from the old generation:
javax.xml.bind.JAXBContext oldContext;

// Type from the new generation:
jakarta.xml.bind.JAXBContext newContext;
```

These are two different binary names. The JVM does not automatically convert `javax/xml/bind/JAXBContext` into `jakarta/xml/bind/JAXBContext`.

The same rule applies to annotations:

```java
@javax.xml.bind.annotation.XmlRootElement
public class CustomerLegacy {
}
```

A `jakarta`-generation JAXB runtime should not be assumed to interpret the `javax.xml.bind.annotation.XmlRootElement` annotation as `jakarta.xml.bind.annotation.XmlRootElement`. Using a new runtime with model code generated by an old generator can cause class-not-found errors or unexpected mappings.

### 3.3. Choose a Strategy Before Choosing Dependencies

There are two reasonable migration directions that differ in scope:

**Option A — Keep `javax.*`, only decouple dependencies from the JDK.** Appropriate when the current application or framework is still on a Java EE/Jakarta EE generation compatible with the old namespace. Focus on adding external JAXB/JAX-WS/Activation APIs and runtimes, keeping source imports and generators aligned with `javax.*`.

**Option B — Migrate the entire stack to `jakarta.*`.** Appropriate when upgrading frameworks to a generation that requires Jakarta, such as modern framework versions that have switched namespaces. You need to update imports, annotations, generated source, providers, binding customizations, framework integration, and plugins according to a unified matrix.

Do not randomly mix `javax` and `jakarta` components in the same marshalling chain or SOAP call. If both must be supported at an integration boundary, use adapters or separate modules with clear tests covering data types and contracts.

## 4. Inventory Before Modifying Code or Build

### 4.1. Find Imports and APIs Currently in Use

Indicators in source code:

```java
import javax.xml.bind.JAXBContext;
import javax.xml.bind.annotation.XmlElement;
import javax.xml.ws.Service;
import javax.jws.WebService;
import javax.activation.DataHandler;
```

Or their `jakarta.*` equivalents.

Locations to inspect beyond the main source:

- Generated source in `target/generated-sources` or `build/generated`.
- DTOs and JAXB annotations generated from XSD.
- SOAP client stubs, SEIs, and service classes generated from WSDL.
- Code using MTOM/SOAP attachments, `DataHandler`, and MIME.
- WSDL/XSD/binding XML, catalogs, and endpoint configurations.
- Dependency injection, component scanning, and web service endpoint publication.
- Build plugins, CI scripts, and custom commands invoking `xjc`/`wsimport`.
- Consumers or internal libraries precompiled with `javax.*` binary names.

### 4.2. Inspect the Actual Dependency Graph

With Maven:

```bash
./mvnw -version
./mvnw dependency:tree
./mvnw help:effective-pom
./mvnw dependency:resolve-plugins
```

With Gradle:

```bash
./gradlew --version
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencies --configuration testRuntimeClasspath
./gradlew :app:buildEnvironment
```

Replace `:app` with the actual project path. With Gradle, `buildEnvironment` does not fully cover plugins from the Plugin DSL; inspect `plugins {}`, `pluginManagement`, convention plugins, version catalogs, and included builds.

The goal is to identify which API/runtime/generator versions are **actually resolved**, not just the directly declared versions. BOMs or dependency management can alter transitive versions. An Activation or JAXB API JAR of the wrong generation can be pulled in by a SOAP client, framework, or mail library.

### 4.3. Environment Inventory

Record specifically:

| Component | Details to lock down |
|---|---|
| JDK running Maven/Gradle | Vendor, major/update version, `JAVA_HOME`, wrapper |
| Compiler/toolchain | Release target, language level, API target |
| Generator JVM | JDK running `xjc`/`wsimport` or the codegen plugin |
| Runtime JVM | Production JDK/container image |
| Framework stack | Servlet/JAX-WS implementation, Jakarta/Javax generation |
| Contract | WSDL version, XSD, imported schemas, XML namespace |
| Artifact | JAR/WAR/EAR, module path/classpath, shaded/uber-JAR |
| Integration | SOAP endpoints, TLS/WS-Security, MTOM, timeouts, and authentication |

In particular, a generator running on JDK 8 may produce `javax.*` source while the application compiler runs on JDK 21 and the framework expects `jakarta.*`. Without separately pinning the generator JVM and generator version, failures are easily misdiagnosed as JDK bugs.

## 5. JAXB Outside the JDK

### 5.1. What Is JAXB Used For?

JAXB (XML Binding) maps Java objects to XML and vice versa. Commonly used APIs:

- `JAXBContext` creates a binding context.
- `Marshaller` converts objects to XML.
- `Unmarshaller` converts XML to objects.
- `@XmlRootElement`, `@XmlElement`, `@XmlAttribute`, `@XmlType` describe XML mappings.
- `@XmlAccessorType`, `@XmlSchema`, and adapters customize the binding structure.

A simple model in the Jakarta generation:

```java
package com.example.model;

import jakarta.xml.bind.annotation.XmlElement;
import jakarta.xml.bind.annotation.XmlRootElement;

@XmlRootElement(name = "customer")
public class Customer {
    private String name;

    public Customer() {
    }

    @XmlElement
    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
```

And the marshalling step:

```java
import jakarta.xml.bind.JAXBContext;
import jakarta.xml.bind.Marshaller;

JAXBContext context = JAXBContext.newInstance(Customer.class);
Marshaller marshaller = context.createMarshaller();
marshaller.setProperty(Marshaller.JAXB_FORMATTED_OUTPUT, Boolean.TRUE);
marshaller.marshal(customer, System.out);
```

For the `javax` branch, imports become `javax.xml.bind.*` and the corresponding annotations. The API concept is largely similar, but namespaces from the two generations must not be mixed in the same deployment.

### 5.2. API Dependency and JAXB Runtime

For the modern Jakarta branch, Maven can declare the API and runtime:

```xml
<dependencies>
    <dependency>
        <groupId>jakarta.xml.bind</groupId>
        <artifactId>jakarta.xml.bind-api</artifactId>
        <version>${jaxb.api.version}</version>
    </dependency>
    <dependency>
        <groupId>org.glassfish.jaxb</groupId>
        <artifactId>jaxb-runtime</artifactId>
        <version>${jaxb.runtime.version}</version>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

The `jaxb.api.version` and `jaxb.runtime.version` properties are placeholders that must be replaced with verified versions **from the same Jakarta generation**. In Gradle, the equivalent configuration can be `implementation` for the API and `runtimeOnly` for the runtime; if code directly requires implementation APIs, an appropriate scope must be chosen.

For the `javax` branch, choose a 2.x-generation JAXB API and implementation containing `javax.xml.bind.*` packages, commonly with coordinates such as `javax.xml.bind:jaxb-api` and `org.glassfish.jaxb:jaxb-runtime` of the compatible generation. Some artifacts named `jakarta.xml.bind-api` at version 2.3.x still use the `javax` namespace; therefore, verify the JAR contents and release notes rather than relying solely on the groupId.

The API JAR alone is not enough to run JAXB operations. At runtime, the implementation and its dependencies are needed so that `JAXBContext.newInstance(...)` can locate a suitable provider.

### 5.3. Typical JAXB Errors

| Symptom | Common cause | Resolution |
|---|---|---|
| `package javax.xml.bind does not exist` | Newer JDK no longer provides the old JAXB API on the compile classpath | Add the external `javax` API or migrate source to `jakarta` and add the right API |
| `package jakarta.xml.bind does not exist` | Missing Jakarta JAXB API on the compile classpath | Add the API with the matching generation and scope |
| `JAXBException` reporting implementation/provider not found | API is present without a compatible runtime/provider | Add the JAXB runtime, check provider discovery and classpath |
| `NoClassDefFoundError` related to `javax.activation` or `jakarta.activation` | Missing or mismatched Activation dependency | Align Activation API/implementation |
| Runtime does not recognize XML annotations | Generated model uses a different namespace from the JAXB runtime, or model is invalid | Align generator, annotations, and runtime |
| `ClassCastException` between two JAXB types | Two namespace systems or different class loaders | Isolate boundaries; do not cast directly between `javax` and `jakarta` |

Do not handle JAXB errors by adding both 2.x and 4.x APIs to the classpath. Coexistence of both systems does not automatically make frameworks recognize and convert models between them.

## 6. JAX-WS Outside the JDK

### 6.1. JAX-WS and SOAP Contracts

JAX-WS (XML Web Services) provides an API for building and invoking SOAP web services. Some typical concepts:

- `Service` creates or accesses a service based on a WSDL.
- Service Endpoint Interface (SEI) describes operations.
- `@WebService`, `@WebMethod`, and metadata annotations.
- `BindingProvider` for request context, endpoint address, and implementation-specific timeouts.
- `SOAPBinding`, handler chains, SOAP faults, and attachments.
- Generators create service classes, request/response models, and client proxies.

The API itself does not provide a complete HTTP/SOAP stack. An application typically uses an implementation such as **Metro JAX-WS RI** or **Apache CXF** depending on its framework and architecture.

### 6.2. Runtime API and Implementation Must Match

For the modern Jakarta branch, Maven can use:

```xml
<dependencies>
    <dependency>
        <groupId>jakarta.xml.ws</groupId>
        <artifactId>jakarta.xml.ws-api</artifactId>
        <version>${jaxws.api.version}</version>
    </dependency>
    <dependency>
        <groupId>com.sun.xml.ws</groupId>
        <artifactId>jaxws-rt</artifactId>
        <version>${metro.version}</version>
    </dependency>
</dependencies>
```

This is an illustration for the Metro stack; actual versions must be chosen according to the joint compatibility matrix with JAXB and Activation. The Metro runtime can pull in many transitive dependencies, so read the dependency graph and ensure versions are not mismatched by another BOM override.

If using Apache CXF, select the CXF modules for the JAX-WS frontend and appropriate transport—such as `org.apache.cxf:cxf-rt-frontend-jaxws` with the corresponding HTTP transport—at the exact CXF version supported by the project's runtime/framework. Do not arbitrarily mix Metro and CXF on the same classpath just because both provide a JAX-WS implementation.

For the `javax` branch, select the corresponding 2.x-generation JAX-WS API and implementation. Package names `javax.xml.ws.*` in legacy client code do not turn into `jakarta.xml.ws.*` simply by upgrading runtime coordinates.

### 6.3. Endpoints and SOAP Clients Must Be Verified Separately

Upgrading the API/JAX-WS provider can affect different integration layers:

| Area | What to verify |
|---|---|
| SOAP client | WSDL lookup, service name, port name, SOAP action, endpoint URL |
| Service endpoint | Annotations, publication, servlet/HTTP transport, lifecycle |
| Binding | SOAP 1.1/1.2, document/literal, headers, wrapper style |
| Fault | Checked exception mapping and SOAP Fault details |
| Security | TLS, WS-Security, signatures, certificates, authentication |
| Attachment | MTOM, XOP, MIME, `DataHandler` |
| Operability | Timeouts, retries, proxies, tracing, metrics, and logging |
| Generated stubs | Packages, namespaces, `Service` subclasses, request/response DTOs |

An application may build successfully yet send SOAP requests incompatible with a partner because WSDL bindings or SOAP envelopes changed. Therefore, contract tests on real XML/SOAP payloads are needed, not just unit tests of proxies.

### 6.4. JAX-WS Is Not JAX-RS

JAX-WS is primarily tied to SOAP/XML web services, whereas JAX-RS/Jakarta REST handles the REST model. A project can use both, but converting SOAP clients to REST is not a mandatory requirement of a JDK upgrade.

Switching to REST is a larger protocol and contract migration. If the goal is to preserve SOAP integrations while upgrading the JDK, using an external JAX-WS implementation is usually the path with fewer business logic changes.

## 7. Activation and MIME Attachments

### 7.1. What Does Activation Handle?

The JavaBeans Activation Framework—commonly called JAF or Activation—provides abstractions for MIME-typed content, `DataSource`, `DataHandler`, and content-handling mechanisms. It is used in mail libraries, SOAP attachments/MTOM, and data exchange systems involving file attachments.

In the Jakarta generation:

```java
import jakarta.activation.DataHandler;
import jakarta.activation.DataSource;
```

An attachment-processing flow may use `DataHandler` wrapping a `DataSource` and pass it to the SOAP/messaging framework. Ensure the API and implementation match the JAX-WS or mail stack in use.

### 7.2. Activation API Does Not Imply Implementation

In the modern Jakarta branch, the API and implementation are often distributed independently, such as the `jakarta.activation:jakarta.activation-api` API and the Angus Activation implementation like `org.eclipse.angus:angus-activation`.

Maven example:

```xml
<dependencies>
    <dependency>
        <groupId>jakarta.activation</groupId>
        <artifactId>jakarta.activation-api</artifactId>
        <version>${activation.api.version}</version>
    </dependency>
    <dependency>
        <groupId>org.eclipse.angus</groupId>
        <artifactId>angus-activation</artifactId>
        <version>${angus.activation.version}</version>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

The versions must share the same namespace and belong to a combination supported by the SOAP/mail framework. Libraries may supply a provider via transitive dependencies; add it directly only when the application needs it or the dependency graph shows it is missing, following the project's dependency management policy.

### 7.3. Signs of Activation Version Mismatch

- The compiler sees `jakarta.activation.DataHandler`, while the SOAP framework expects `javax.activation.DataHandler`.
- Runtime has the API but lacks content handlers or an implementation.
- Provider looks up the wrong factory/handler due to mismatched implementation versions.
- MTOM attachments are not encoded/decoded properly.
- The mail/SMTP library uses a different namespace from the SOAP stack.

Test actual attachments as well, including MIME types, filenames, charsets, stream lifecycle, file size, headers, transfer encoding, and large-file handling. Successfully starting a SOAP client does not prove attachments work properly.

## 8. Code Generation Tools No Longer Inside the JDK

### 8.1. XJC — XSD to Java

`xjc` reads XML Schema (XSD) and generates Java models with JAXB annotations. Task example:

```text
src/main/xsd/customer.xsd
            |
            v
   External XJC tool
            |
            v
target/generated-sources/xjc/com/example/xml/Customer.java
            |
            v
   Java compiler
            |
            v
  Application artifact
```

In JDK 8, `xjc` was typically provided with the JDK. Starting in JDK 11, you must install a standalone tool or use a Maven/Gradle plugin integrating JAXB XJC. With JAXB RI, a common tool artifact is `org.glassfish.jaxb:jaxb-xjc`, which must match the generation of the JAXB API/runtime.

Command-line invocation example once the external XJC toolset is properly installed:

```bash
xjc -d target/generated-sources/xjc \
    -p com.example.xml \
    src/main/xsd/customer.xsd
```

This command assumes the `xjc` executable is available from a separate distribution/tool and the output directory has been prepared as required by the tool. Do not expect `JAVA_HOME/bin/xjc` to exist on JDK 17/21.

### 8.2. schemagen — Java Model to XSD

`schemagen` generates XML Schemas from Java classes with JAXB annotations, useful in Java-first workflows. This tool must also be supplied outside modern JDKs, for example via a compatible JAXB RI schema generator/tool.

When using Java-first, keep input class versions and annotations stable. A change in annotations or packages can make the generated XSD differ from the published contract, even when compilation still succeeds.

### 8.3. wsimport — WSDL to JAX-WS Client/Stubs

`wsimport` reads WSDLs and related schemas to generate Java types and service endpoint proxies. Starting in JDK 11, use external JAX-WS tooling, such as Metro JAX-WS tools or an equivalent plugin.

Command-line example once the appropriate toolset is installed:

```bash
wsimport -keep \
    -s target/generated-sources/wsimport \
    -p com.example.soap.client \
    src/main/wsdl/CustomerService.wsdl
```

The output directory and options may vary by tool version. More importantly, **the generator version determines which annotation/import family is generated**. Source created by a `javax` generator does not automatically match a `jakarta` runtime.

### 8.4. wsgen — Endpoint Code to Related WSDL Artifacts

`wsgen` supports the Java-first JAX-WS workflow on stacks that provide this capability. On newer JDKs, it is no longer a built-in tool. If the project uses Java-first SOAP, select an appropriate JAX-WS implementation/tool and verify both the WSDL output and endpoint runtime.

Not every framework requires `wsgen`: some stacks use WSDL-first and other tools. Do not add the tool back merely because it previously existed in the JDK; first determine whether the actual pipeline invokes it.

### 8.5. Replacement Tools and Equivalent Roles

| Need | Common external tool/solution | Output to verify |
|---|---|---|
| XSD → JAXB Java classes | JAXB RI XJC or compatible XJC plugin | POJOs, annotations, `ObjectFactory`, `package-info.java` |
| Java JAXB classes → XSD | JAXB RI schema-generation tool | XML Schema matching the contract |
| WSDL → SOAP client/source | Metro JAX-WS tools, Apache CXF `wsdl2java` | SEI, service proxy, JAXB model |
| Java SOAP endpoint → WSDL | Appropriate JAX-WS tool or framework codegen | WSDL, binding, and namespaces |
| Build automation | Corresponding Maven/Gradle plugin | Generated source wired into the right source set |
| Runtime binding and SOAP | JAXB runtime + Metro/CXF + Activation | Marshalling, transport, SOAP request/response |

Avoid treating a "replacement tool" as strictly equivalent in output. Two generators can produce different class names, annotations, method signatures, date/time mappings, or package configurations from the same schema.

## 9. Contract-Based Code Generation: What Needs to Be Managed?

### 9.1. Inputs Are the Source of Truth

With WSDL-first or XSD-first, **WSDL/XSD and binding configuration** are the source of truth. Generated Java source is a product of the build step.

Store in the same repository or artifact registry the components required to regenerate:

- Main WSDL and imported WSDLs/XSDs.
- Binding customization files.
- XML catalogs used to map URIs to local copies.
- Tool and plugin versions.
- Package, binding, extension, and source target options.
- The JDK running the generator and compiler.
- Output directory/source set.
- Process for regenerating source in CI.

If a WSDL imports schemas from URLs that can change, the build is no longer reproducible. Control schema dependencies via local snapshots/catalogs and clearly define when updates happen.

### 9.2. Check Namespaces in Generated Source

After generating, inspect imports and annotations:

```java
// Code generated by the old tool:
import javax.xml.bind.annotation.XmlElement;
import javax.xml.ws.Service;
```

or:

```java
// Code generated by a Jakarta-compatible tool:
import jakarta.xml.bind.annotation.XmlElement;
import jakarta.xml.ws.Service;
```

Verify that the generator uses the same namespace family as the runtime API and framework. Do not run bulk string replacement `javax.` → `jakarta.` and assume every reference will be right; several `javax.xml.*` packages remain Java SE APIs and some generators have their own internal dependencies.

### 9.3. Binding Customizations May Need Migration

JAXB/JAX-WS binding files use schemas, XML namespaces, syntax, and options tied to the tool version. When moving across generations, you may need to update the binding file's namespaces and extensions.

A common failure is that a newer tool rejects an old binding file, or accepts it while ignoring customizations, causing the generated model to rename classes or change data types. Check generator logs and diff the output, not just the exit code.

### 9.4. Do Not Edit Generated Source Directly

If you need to rename fields, packages, enum mappings, or date/time types, prefer modifying the schema or binding customizations. Editing generated files directly causes changes to be lost upon regeneration.

If the project has a reason to commit generated source, clearly document how to regenerate it, how to inspect diffs, and how to prevent irreproducible manual edits.

## 10. Maven: Organizing APIs, Runtime, and Code Generation

### 10.1. Consistent Dependency Profile

A Maven template for a JAXB/JAX-WS application **using the Jakarta namespace** can declare the main components as follows:

```xml
<dependencies>
    <!-- Compile-time API -->
    <dependency>
        <groupId>jakarta.xml.bind</groupId>
        <artifactId>jakarta.xml.bind-api</artifactId>
        <version>${jaxb.api.version}</version>
    </dependency>
    <dependency>
        <groupId>jakarta.xml.ws</groupId>
        <artifactId>jakarta.xml.ws-api</artifactId>
        <version>${jaxws.api.version}</version>
    </dependency>
    <dependency>
        <groupId>jakarta.activation</groupId>
        <artifactId>jakarta.activation-api</artifactId>
        <version>${activation.api.version}</version>
    </dependency>

    <!-- Metro runtime stack example -->
    <dependency>
        <groupId>com.sun.xml.ws</groupId>
        <artifactId>jaxws-rt</artifactId>
        <version>${metro.version}</version>
    </dependency>
</dependencies>
```

The version variables are placeholders, **not a default set of versions guaranteed to be compatible**. Select them based on the BOM, release notes, and dependency tree of the stack. For example, the Metro runtime may supply transitive JAXB/Activation dependencies; avoid pinning conflicting versions before inspecting the graph.

If only JAXB is used, there is no need to add JAX-WS. If Apache CXF is used instead of Metro, select the appropriate set of CXF modules and remove unused runtime providers. If `javax` is still required, use the appropriate `javax`-branch API/runtime rather than copying the Jakarta template above as-is.

### 10.2. Integrating WSDL Code Generation with CXF Codegen Plugin

A common Maven configuration with Apache CXF:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.cxf</groupId>
            <artifactId>cxf-codegen-plugin</artifactId>
            <version>${cxf.version}</version>
            <executions>
                <execution>
                    <id>generate-soap-client</id>
                    <phase>generate-sources</phase>
                    <goals>
                        <goal>wsdl2java</goal>
                    </goals>
                    <configuration>
                        <wsdlOptions>
                            <wsdlOption>
                                <wsdl>${project.basedir}/src/main/wsdl/CustomerService.wsdl</wsdl>
                            </wsdlOption>
                        </wsdlOptions>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

Select the CXF plugin version and CXF runtime from the same branch according to the framework matrix. Older CXF generations may generate `javax` source, whereas modern Jakarta branches generate `jakarta` source. Inspect the generated source to verify what is actually produced.

Source is typically generated under a build directory configured by the plugin and wired into the compilation lifecycle. Check the output directory, target language/runtime, and actual source roots. Do not have two different plugins generate into the same directory and overwrite each other's files.

### 10.3. XJC in Maven

There are many standalone XJC plugins as well as plugins integrated with JAXB RI. When choosing one, verify:

- The plugin is maintained and runs on the build JDK in use.
- Compatibility between XJC tool coordinates and JAXB API/runtime versions.
- XML binding customizations, catalogs, and schema imports.
- Generated packages and output directory.
- Wiring of generated source into the Maven compile phase.
- Whether regeneration works from a clean checkout.

Some projects use community JAXB/XJC Maven plugins, while others use plugins from the Metro/CXF ecosystem. Do not keep an aging plugin simply because it used to run on JDK 8; that plugin may depend on JDK tools or JDK internals that no longer exist.

## 11. Gradle: Separating Runtime Dependencies and Generator Tasks

### 11.1. Runtime Libraries

Groovy DSL example for Jakarta JAXB:

```groovy
dependencies {
    implementation "jakarta.xml.bind:jakarta.xml.bind-api:${jaxbApiVersion}"
    runtimeOnly "org.glassfish.jaxb:jaxb-runtime:${jaxbRuntimeVersion}"
}
```

For JAX-WS, add the appropriate API/runtime provider if the application actually uses SOAP. Version variables must be defined in the build and chosen according to the compatibility matrix.

### 11.2. Dedicated Configuration for XJC

Do not place the entire generator tool onto the application's runtime classpath just to run the code generation task. Create a dedicated configuration for the tool and a separate task:

```groovy
configurations {
    xjcTool
}

dependencies {
    xjcTool "org.glassfish.jaxb:jaxb-xjc:${jaxbToolVersion}"
}

def generatedXjcDir = layout.buildDirectory.dir("generated/sources/xjc/main")

tasks.register("generateJaxb", JavaExec) {
    classpath = configurations.xjcTool
    mainClass = "com.sun.tools.xjc.XJCFacade"

    inputs.file("src/main/xsd/customer.xsd")
    outputs.dir(generatedXjcDir)

    doFirst {
        generatedXjcDir.get().asFile.mkdirs()
    }

    args "-d", generatedXjcDir.get().asFile.absolutePath,
         "-p", "com.example.xml",
         file("src/main/xsd/customer.xsd").absolutePath
}

sourceSets {
    main {
        java.srcDir(generatedXjcDir)
    }
}

tasks.named("compileJava") {
    dependsOn(tasks.named("generateJaxb"))
}
```

This is a task organization pattern with JAXB RI XJC; **the entrypoint, classpath, and CLI syntax must be verified against the selected XJC version**, especially when changing major versions. Other generators, such as CXF wsdl2java or Metro tools, have their own main classes and options.

Principles worth preserving:

- Tool dependencies reside on `xjcTool`, not becoming runtime dependencies by default.
- The task has explicit inputs/outputs so the build is reproducible and supports caching/incremental behavior.
- Generated source resides in `build/`, without overwriting handwritten source.
- `compileJava` depends on the generator when the generator's output is compiled.
- A clean build must regenerate all required source.

### 11.3. Plugins and the JDK Running the Generator

Configuring a Java toolchain for the compiler does not necessarily change the JDK running every `JavaExec` task or plugin. You must identify the JDK used to run the generator, the compiler JDK, the source/bytecode target, and the production runtime JVM.

If the compiler is JDK 21 but the artifact must still run on Java 17, configure `--release 17` on `JavaCompile` tasks, while choosing a generator that produces Java 17-compatible source in the right namespace. The release configuration does not automatically make a new JAX-WS or JAXB runtime compatible with an old framework.

## 12. JPMS, Classpath, and Module Path

### 12.1. Removed Modules Cannot Be "Turned Back On"

On JDK 11+, adding:

```bash
java --add-modules java.xml.bind -jar app.jar
```

does not restore the JAXB module previously bundled in older JDKs. If the module is absent from the runtime/module path, the JVM reports that the module cannot be found. The `--add-opens` and `--add-exports` options also do not recreate removed classes or modules.

The proper solution is to supply the API and implementation as external dependencies, and configure the classpath/module path appropriately.

### 12.2. Module Descriptors and Automatic Modules

An application with `module-info.java` may need to declare JAXB/JAX-WS/Activation module dependencies using the module name actually provided by the artifact. The module name may be an explicit module name or an automatic module name depending on the version/library.

Do not infer the module name solely from the Maven artifactId. Inspect the JAR manifest, module descriptor, and analysis output:

```bash
jar --describe-module --file path/to/library.jar
jdeps --print-module-deps path/to/application.jar
```

Artifacts with split packages, automatic modules, or improper service provider wiring may run on the classpath yet fail on the module path. Choose an intentional packaging strategy and test on the target runtime configuration.

### 12.3. ServiceLoader and Provider Discovery

JAXB and JAX-WS implementations typically use provider/factory discovery mechanisms. During uber-JAR packaging, shading, or minimization, `META-INF/services` files and resource metadata can be lost or left unmerged.

If the API compiles successfully yet the runtime cannot find a provider, check:

- Whether the runtime JAR is packaged inside the artifact.
- Whether `META-INF/services` and provider metadata remain intact.
- Whether multiple conflicting providers exist on the classpath.
- Which class loader is loading the API and implementation.
- Whether the provider belongs to the same `javax`/`jakarta` generation.
- Whether the module path properly declares service usage/providers.

Do not apply workarounds by tweaking the classpath randomly until it runs. Determine the specific provider to be used and ensure the build produces a reproducible artifact.

## 13. XML Security: Do Not Overlook XXE and Schema Sources

Migration may change the parser implementation, generator, XML libraries, and schema handling. This is the time to clearly define policies for XML External Entities (XXE), DTDs, and external resource loading.

### 13.1. Protection at the XML Input Boundary

When unmarshalling data from untrusted sources, do not assume the JAXB runtime automatically blocks all external entities. Configure the XML parser at the ingestion point according to security policy, and pass only the configured parser source to JAXB.

Example with StAX when the environment and provider support these properties:

```java
XMLInputFactory inputFactory = XMLInputFactory.newFactory();
inputFactory.setProperty(XMLInputFactory.SUPPORT_DTD, Boolean.FALSE);
inputFactory.setProperty(
    XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES,
    Boolean.FALSE
);

try (InputStream in = Files.newInputStream(xmlPath)) {
    XMLStreamReader reader = inputFactory.createXMLStreamReader(in);
    try {
        Object value = unmarshaller.unmarshal(reader);
        // Process value.
    } finally {
        reader.close();
    }
}
```

This illustrates a parser policy, not a guarantee of safety across every provider. Verify that the implementation accepts and enforces the properties, also check entity expansion/resource limits, and test malicious XML according to organizational policy.

### 13.2. Network WSDL/XSD Imports

`wsimport` and `xjc` may need to import schemas from external paths or URLs. Avoid letting CI download uncontrolled resources from the public network during each build. Use XML catalogs, pinned schema copies, or approved repositories, verify checksums, and restrict generator access permissions.

WSDL/XSD documents from partners should not automatically be treated as trusted input. Generators running during the build can read files, access URLs, and generate source code; review environment permissions and dependency sources.

## 14. Practical Migration Workflow

### Step 1: Capture the Baseline

Record the commit, JDK vendor/build, Maven/Gradle Wrapper, frameworks, dependency tree, WSDL/XSD, and current generated source. Keep build logs and test baselines to distinguish pre-existing failures.

### Step 2: Identify the Technologies Actually Used

Distinguish JAXB-only, SOAP client, SOAP server, Java-first or WSDL-first, and MTOM/attachments. Do not add a JAX-WS runtime to an application that only needs to marshal/unmarshal XML.

### Step 3: Choose the Target Namespace

Decide whether to keep `javax` to minimize changes or migrate to `jakarta` alongside the framework. Do not choose both directions within one module without clearly defining adapter boundaries.

### Step 4: Select Compatible API/Runtime/Provider Sets

Cross-check vendor documentation for JAXB RI, Metro or CXF, Activation providers, and frameworks. Identify versions supporting the chosen build/runtime JDK and Jakarta/Javax generation.

### Step 5: Decouple Code Generators from the JDK

Pin XJC/wsimport/wsgen/schemagen tool versions in Maven/Gradle or the tool distribution. Replace paths relying on `JAVA_HOME/bin` with tasks/goals using external dependencies. Lock down inputs/outputs and generated source roots.

### Step 6: Perform Clean Generation and Inspect Output

Rerun the generator from a clean checkout in a standard environment, then compare the generated source. Pay attention to packages, annotations, enums, date/time types, service/port names, operation signatures, and binding customizations.

### Step 7: Compile and Package

Compile all handwritten source and generated source on the target JDK. Check compile/runtime dependencies, shaded JARs, service provider metadata, JPMS, and required Activation libraries.

### Step 8: Verify XML/SOAP Contracts

Run JAXB round-trips, schema validation, SOAP requests/responses, fault mapping, headers, TLS, timeouts, and attachments. For partner-facing systems, use approved WSDLs/XSDs and payloads as contract tests.

### Step 9: Test on the Final Artifact

Run the exact JAR/WAR/container to be released, not just the IDE classpath. If the system uses an application server, check which APIs/providers the server provides and whether they conflict with libraries packaged by the application.

### Step 10: Release and Rollback

Release using a canary/rolling/blue-green strategy depending on the system. Retain the old artifact, WSDL/XSD versions, provider configuration, and runtime image; define rollback conditions and XML data compatibility between the two versions.

## 15. End-to-End Example: SOAP Application from JDK 8 to JDK 21

Suppose a legacy service uses JDK 8 and has:

- `javax.xml.bind` annotations on DTOs.
- A SOAP client using `javax.xml.ws.Service`.
- The `wsimport` generator invoked via a `$JAVA_HOME/bin/wsimport` script.
- SOAP responses with file attachments using `javax.activation.DataHandler`.
- CI building with JDK 8; the new target is JDK 21.

### 15.1. Initial Diagnosis

If you only switch the JDK to 21, the build may fail at two independent layers:

1. The script can no longer find `wsimport` in the JDK.
2. The compiler cannot find `javax.xml.bind`, `javax.xml.ws`, or `javax.activation` without external dependencies.

Even if adding API JARs makes compilation pass, the runtime may still lack a JAX-WS/JAXB provider or an Activation implementation.

### 15.2. Low-Change Approach: Keep javax

If the current framework and runtime still support the `javax` branch:

1. Keep the original imports and WSDL contract.
2. Select `javax`-generation JAXB API/runtime, JAX-WS API/implementation, and Activation dependencies compatible with JDK 21.
3. Use an external generator outside the JDK to produce `javax` source.
4. Align transitive dependencies and service providers.
5. Clean-generate, compile, and run SOAP contract tests and MTOM tests.
6. Release as planned and clearly document that this decouples dependencies from the JDK, and is not yet a migration to the Jakarta namespace.

The advantage is a small scope of source changes. The disadvantage is that older framework/implementation versions may have maintenance limitations or no longer meet support policies. Do not keep the `javax` branch indefinitely if the organization's ecosystem already requires Jakarta.

### 15.3. Stack-Upgrade Approach: Migrate to jakarta

If the goal includes a modern Jakarta framework:

1. Lock down the framework version and the Jakarta SOAP/JAXB/Activation stack.
2. Upgrade the generator to the matching generation to produce `jakarta.*` source.
3. Update imports and annotations in handwritten code.
4. Migrate binding customizations if required by the new tool.
5. Check public classes, method descriptors, and precompiled consumers: `javax` and `jakarta` are different binary names.
6. Check serialized data/metadata relying on class names if used by the application.
7. Run XML/SOAP contract tests, security/attachment tests, and integration tests on JDK 21.
8. Write a migration guide for consumers and a rollback plan.

Changing namespaces should be treated as an actual API migration step. Merely changing dependency versions without regenerating source or updating corresponding imports will not complete the job.

## 16. Common Errors and Investigation Approaches

| Error or symptom | Possible cause | Check steps |
|---|---|---|
| `package javax.xml.bind does not exist` | Old JAXB API is not bundled in JDK 11+ | Inspect compile classpath; add the proper external API or migrate namespace |
| `package jakarta.xml.ws does not exist` | Missing Jakarta JAX-WS API | Check dependency scope and API version |
| `xjc: command not found` | XJC is no longer in modern JDKs | Replace with an external XJC tool/plugin |
| `wsimport: command not found` | wsimport is no longer in the JDK | Integrate Metro tools or CXF codegen |
| JAXB provider not found | API is present but runtime/provider is missing | Check runtime dependencies and service metadata |
| `NoClassDefFoundError: javax/activation/DataHandler` | Missing old Activation or library generation mismatch | Identify the namespace required by the caller |
| Generated code imports `javax` while application uses `jakarta` | Generator and runtime are from different generations | Re-select the generator, regenerate, and inspect binding files |
| `ClassNotFoundException` in SOAP client | Missing JAX-WS implementation or generated classes | Check the final JAR, class loader, and generated roots |
| WSDL client compiles but cannot call service | Binding, endpoint, TLS, SOAP action, security, or transport | Run SOAP contract/integration tests |
| MTOM attachment fails | Incorrect Activation/provider/MIME or stream lifecycle | Test real attachments and dependency graph |
| Runs in IDE, fails in packaged JAR | Shading dropped service metadata or runtime JARs | Inspect final artifact and `META-INF/services` |
| Clean build produces different output | Tool not pinned, remote schema changed, or environment-dependent output | Pin tool/schemas, use catalogs, and diff generated source |
| JPMS reports module not found | Attempting to use a removed JDK module or module path lacks libraries | Supply external dependencies and inspect module descriptors |

One error can have multiple causes. The best process is to identify **the exact failing class and class loader**, resolved dependency versions, namespace, and failure stage (generate, compile, startup, or runtime request) before applying a fix.

## 17. Misconceptions to Avoid

### "Adding `--add-modules java.xml.bind` Is Enough"

False on JDK 11+ if that module no longer exists in the JDK. External API and implementation must be provided outside the JDK.

### "Jakarta JAXB API Is a Binary Drop-in Replacement for javax JAXB"

False when the namespace changes. `javax.xml.bind.JAXBContext` and `jakarta.xml.bind.JAXBContext` are two types with different names. Source, generated code, framework, and consumer compatibility must be addressed.

### "Having `jaxb-api` Guarantees Marshaling Will Run"

Not sufficient. The API requires a provider/runtime; XML operations also depend on model annotations, parsers, security, and binding configuration.

### "Having `jaxws-api` Means the SOAP Client Will Work"

Not sufficient. A SOAP client/server needs an implementation, transport, dependencies, and sometimes a generator. Test against a real service or an equivalent contract test.

### "If Generated Source Is Committed, No Generator Is Needed"

The current build might not invoke the generator, yet the project still relies on the ability to regenerate source when schemas change. Clearly document the source of truth and make an intentional decision about pinning/maintaining the generator.

### "All `javax.xml.*` Must Become `jakarta.xml.*`"

False. Several Java SE XML processing APIs remain under `javax.xml.*`. Only migrate APIs that have a corresponding namespace migration.

### "JDK 21 Was the Version That Removed JAXB/JAX-WS"

False. The removal milestone was JDK 11. If the system previously ran on JDK 17, check what was providing those components.

### "Updating Imports Is Enough to Migrate to Jakarta"

Not sufficient. Generated source, annotation metadata, runtime providers, Activation, SOAP transport, module path, tests, and consumers may still depend on the old namespace.

## 18. Completion Criteria and Handoff Record

A JAXB/JAX-WS/Activation migration can be considered ready for release when the team has the following evidence:

1. **Inventory:** locations using JAXB, JAX-WS, Activation, WSDL/XSD, and generators.
2. **Version matrix:** build/runtime JDK, framework, API, implementation, provider, generator, and plugins; clearly indicating `javax` or `jakarta`.
3. **Dependency graph:** resolved versions on compile/runtime/test/tool classpaths, with no unresolved conflicts.
4. **Codegen record:** tool versions, command/plugin configuration, schema/binding inputs, generated output, and reproducibility.
5. **Source change record:** imports, annotations, packages, configuration, module descriptors, service metadata, and adapters.
6. **JAXB tests:** marshal/unmarshal, XML schema validation, namespaces, null/nillable, date/time, encoding, and special data.
7. **SOAP tests:** WSDL compatibility, request/response/fault, headers, endpoints, auth, TLS, WS-Security, and MTOM attachments.
8. **Security evidence:** XML parser settings, XXE/DTD policy, schema import policy, and dependency vulnerability review.
9. **Artifact verification:** final JAR/WAR/container contains the right providers, metadata, and runtime.
10. **Release plan:** owner, rollout, monitoring, rollback, compatibility limitations, and operational documentation.

### Implementation Checklist

- [ ] Distinguished JAXB/JAX-WS/Activation from Java SE XML APIs still present in the JDK.
- [ ] Confirmed the JDK 11 milestone and removed assumptions that tools reside in `JAVA_HOME/bin`.
- [ ] Selected the `javax` or `jakarta` namespace based on framework and runtime.
- [ ] Verified API and implementation/provider belong to the same generation, not just having the API JAR.
- [ ] Verified the JAXB runtime is properly packaged and provider discovery works.
- [ ] Verified the JAX-WS implementation/transport works in the final artifact.
- [ ] Verified Activation API/implementation compatibility with the attachment/mail stack.
- [ ] Pinned versions of XJC, wsimport, wsgen, and schemagen in use outside the JDK.
- [ ] Regenerated source from controlled WSDLs/XSDs/bindings.
- [ ] Confirmed no wrong-namespace imports/annotations remain in generated source.
- [ ] Verified codegen plugins run on the build JDK without dependency conflicts.
- [ ] Verified module path, ServiceLoader, and `META-INF/services`.
- [ ] Configured XML parsers with appropriate XXE/DTD and external resource policies.
- [ ] Added/verified JAXB round-trip tests and SOAP contract tests.
- [ ] Tested MTOM/MIME attachments on representative payloads.
- [ ] Tested the final artifact on the exact production JDK/container.
- [ ] Prepared logs, artifact checksums, release notes, and a rollback plan.

When moving from an older JDK to a modern JDK, JAXB, JAX-WS, and Activation did not disappear from the Java ecosystem; they **are no longer components that an application can obtain from the JDK by default**. A successful migration requires choosing the right namespace generation, declaring both APIs and implementations, removing implicit JDK dependencies from generators, and then verifying XML/SOAP contracts on the final artifact. This approach keeps builds reproducible, reduces classpath errors, and keeps SOAP/XML integrations running reliably across JDK versions.
