
# Distinguishing Java SE, Java EE, and Jakarta EE in migration planning

A long-lived Java project can encounter seemingly contradictory errors when upgrading the JDK: `java.sql.Connection` still exists, `javax.servlet.http.HttpServlet` cannot be found with only the JDK, `javax.xml.bind.JAXBContext` used to work on Java 8 yet disappears on Java 11, and newer framework versions demand `jakarta.persistence.Entity` instead of `javax.persistence.Entity`. If someone attributes all of this to “Java renamed its libraries” or “the JDK dropped Java EE”, engineers performing migration can easily add the wrong dependencies, mix two API generations, or deploy to an incompatible application server.

The key point is that **Java SE, Java EE, and Jakarta EE are distinct platforms/specifications**, with different histories and boundaries for providing APIs, implementations, and runtimes. Upgrading the **JDK** does not automatically upgrade **Jakarta EE**, and renaming the `javax.*` namespace to `jakarta.*` does not apply to all of Java SE.

This lesson belongs to *Java Advance Compatibility Migration*, topic *Java EE and Jakarta*. It presents how to classify APIs, identify parts supplied by the JDK versus application servers, understand the transition from Java EE to Jakarta EE, evaluate source–binary–runtime compatibility, and build a verifiable upgrade plan.

## 1. Which layers do the three names describe?

### 1.1. Java SE — the standard Java platform

**Java Platform, Standard Edition (Java SE)** defines the core APIs and standard Java execution environment. Common examples:

- The Java language, the `javac` compiler, and compilation via the JDK.
- `java.lang`, `java.util`, `java.io`, `java.nio`.
- Collections, concurrency, networking, and `java.time`.
- JDBC APIs under `java.sql`, `javax.sql`.
- Java Cryptography Architecture, `javax.crypto`, and standard security APIs.
- XML parsing/processing APIs such as `javax.xml.parsers`, `javax.xml.transform`, `org.w3c.dom` in the corresponding Java SE modules.
- APIs related to `javax.annotation.processing` used for annotation processing.

Java SE is typically consumed alongside a JDK or runtime image containing the required modules. However, a **custom runtime image** built with `jlink` may carry only selected modules, so you cannot assume every image includes every module found in a full JDK.

An API whose name starts with `javax.` **is not automatically a Java EE API**. For example, `javax.crypto.Cipher` is a Java SE API; changing its import to `jakarta.crypto.Cipher` is wrong.

### 1.2. Java EE — the enterprise platform generation prior to Jakarta

**Java Platform, Enterprise Edition (Java EE)** is the platform/specification family for enterprise applications. Many Java EE APIs use `javax.*` packages, for example:

- `javax.servlet.*`: HTTP servlets.
- `javax.persistence.*`: Java Persistence API (JPA).
- `javax.validation.*`: Bean Validation.
- `javax.ws.rs.*`: JAX-RS for REST.
- `javax.enterprise.inject.*`: CDI.
- `javax.ejb.*`: Enterprise JavaBeans.
- `javax.jms.*`: Java Message Service.
- `javax.transaction.*`: Java Transaction API.
- `javax.mail.*`: Mail API in the corresponding generations.
- `javax.xml.bind.*` and `javax.xml.ws.*`: JAXB/JAX-WS in the Java EE ecosystem.

Enterprise APIs may be supplied by an **application server** or declared by the application through external libraries. They are not equivalent to “every Java EE API is a mandatory component of the JDK”.

### 1.3. Jakarta EE — the continuation of the enterprise platform

**Jakarta EE** is the successor generation after Java EE development transitioned to the Eclipse Foundation. Enterprise specifications continue evolving under it, with one pivotal namespace transition:

- **Java EE 8**: primarily uses `javax.*` APIs.
- **Jakarta EE 8**: retains `javax.*` packages across specifications even though the platform name changed.
- **Jakarta EE 9 onward**: many enterprise packages were renamed to `jakarta.*`.

Example:

~~~java
// Java EE / Jakarta EE 8 generation
import javax.persistence.Entity;
import javax.servlet.http.HttpServlet;

// Jakarta EE 9+ generation
import jakarta.persistence.Entity;
import jakarta.servlet.http.HttpServlet;
~~~

The change alters the **fully qualified Java type name**, not merely a display label. `javax.persistence.Entity` and `jakarta.persistence.Entity` are two distinct annotation types, and compiled bytecode references two distinct names.

## 2. Brief comparison of scope and responsibility

| Attribute | Java SE | Java EE | Jakarta EE |
|---|---|---|---|
| Purpose | Core APIs, language, standard Java runtime | Prior-generation enterprise/web APIs | Actively evolved enterprise/web APIs |
| Example APIs | `java.util`, `java.time`, `java.sql` | `javax.servlet`, `javax.persistence` | `jakarta.servlet`, `jakarta.persistence` |
| Typically provided by | JDK/runtime modules | Application server or dependencies | Jakarta-compatible server or dependencies |
| Mandatory part of JDK? | Platform component, depending on modules/image | No; a few auxiliary APIs were bundled historically in the JDK | No |
| Namespace | `java.*` and certain SE `javax.*` | Many `javax.*` | Many `jakarta.*` starting in EE 9 |
| Deployment examples | JDK vendor/runtime image | Java EE application server | Jakarta EE application server, compatible providers/embedded runtimes |
| Migration risks | JDK/API removals, modules, classfiles, behavior | API/server versions, external dependencies | Namespace migration, implementations, and container generations |

A project can **simultaneously use Java SE and Jakarta EE**. They are not mutually exclusive alternatives. A Jakarta EE application still runs on top of the Java SE platform.

~~~mermaid
flowchart TD
    A["Java application"] --> B["Java SE / JDK runtime"]
    A --> C["Enterprise API: Java EE or Jakarta EE"]
    C --> D["Implementation / provider / container"]
    D --> B
    A --> E["Third-party libraries"]
    E --> B
~~~

## 3. Distinguishing APIs from implementations and runtime containers

A **specification/API** defines the types and promised behavior. An **implementation/provider** executes that behavior. An **application server or embedded container** can bundle APIs, providers, and the application lifecycle.

Examples:

| Contract | Example API type | Implementation/runtime |
|---|---|---|
| Servlet | `jakarta.servlet.http.HttpServlet` | Tomcat, Jetty, or compatible servlet container |
| Persistence | `jakarta.persistence.EntityManager` | Hibernate ORM, EclipseLink |
| Validation | `jakarta.validation.Validator` | Hibernate Validator or compatible provider |
| REST (JAX-RS) | `jakarta.ws.rs.GET` | Jersey, RESTEasy, or another implementation |
| CDI | `jakarta.enterprise.inject.spi.CDI` | Weld, OpenWebBeans, corresponding server |
| XML Binding | `jakarta.xml.bind.JAXBContext` | JAXB runtime/provider |
| Mail | `jakarta.mail.Session` | Compatible mail provider/runtime |
| Transactions | `jakarta.transaction.UserTransaction` | Transaction manager/container |
| Messaging | `jakarta.jms.Message` | JMS provider/broker integration |

Having a `*-api.jar` containing classes/interfaces/annotations for compilation **does not mean** the application already has an engine to handle requests, validate, persist, or serialize at runtime.

Conversely, inside a matching-generation application server, the container may already supply both APIs and implementations. Packaging extra JARs of a different version inside a WAR can create class-loader conflicts. Therefore, every migration must answer:

1. Is this API from Java SE, Java EE, Jakarta EE, or a third-party library?
2. Who supplies the **API classes** for compilation?
3. Who supplies the **implementation** at runtime?
4. Who bootstraps/selects the provider?
5. Who owns the version: the application, framework BOM, container, or server?
6. Is the deployment model a WAR on an external server or an executable JAR with an embedded runtime?

## 4. Why does JAXB/JAX-WS work on Java 8 yet fail on Java 11?

A major source of confusion is that certain Java EE/CORBA modules **were previously bundled inside some JDKs** like JDK 8, and later separated from the JDK.

JEP 320 removed the Java EE and CORBA modules from **JDK 11**. Among the modules present in JDK 9/10 that were removed are:

- `java.xml.bind` (JAXB).
- `java.xml.ws` (JAX-WS).
- `java.activation` (JavaBeans Activation Framework).
- `java.xml.ws.annotation`.
- `java.corba`.
- `java.transaction`.
- Related tool modules `jdk.xml.bind` and `jdk.xml.ws`.

This is **not** a claim that the entire Java EE platform used to live inside the JDK; Servlet, JPA, CDI, and many other enterprise APIs were never automatically provided as part of the Java SE JDK.

### 4.1. Symptoms with legacy JAXB

A Java 8 system might contain:

~~~java
import javax.xml.bind.JAXBContext;

JAXBContext context =
        JAXBContext.newInstance(Customer.class);
~~~

When moving to JDK 11+ without adding dependencies, compilation may report:

~~~text
package javax.xml.bind does not exist
~~~

or the existing application running on the new runtime may hit:

~~~text
java.lang.NoClassDefFoundError: javax/xml/bind/JAXBContext
~~~

The fix requires determining **which API generation to retain** and **the matching implementation**:

- If keeping `javax.xml.bind.*` sources, select an API/runtime set still supporting that namespace per migration goals.
- If migrating sources to `jakarta.xml.bind.*`, use the compatible Jakarta-generation API and runtime.
- Do not just add any random JAR with “jaxb” in its name.
- Inspect related frameworks, generated classes, annotations, and schema tooling.

### 4.2. Two tasks that must not be conflated

**Task A — The JDK no longer bundles legacy APIs:** add the proper external dependencies to replace capabilities previously provided by the JDK.

**Task B — Migrating from `javax.*` to `jakarta.*`:** update sources, dependencies, implementations, frameworks, and deployment generations when planned.

In some cases, only Task A is needed to keep running during a migration phase; in other cases, product strategy requires both A and B. Upgrading the JDK to Java 17/21 **does not automatically force** all sources to move to `jakarta.*`.

## 5. Transition history and namespaces: easily confused milestones

| Era | Key point to remember |
|---|---|
| Java EE before handover | Enterprise APIs predominantly resided under `javax.*` |
| Java EE 8 | A major Java EE generation prior to Jakarta |
| Jakarta EE 8 | Jakarta platform branding; base API namespace remained `javax.*` |
| Jakarta EE 9 | Major transition moving many enterprise packages to `jakarta.*` |
| Jakarta EE 9.1 and later | Continued Jakarta platform releases raising baselines/specs per release |
| JDK 11 | Previously bundled Java EE/CORBA modules removed per JEP 320 |

Do not assume “if it says Jakarta EE, packages must be `jakarta.*`”: Jakarta EE 8 is a clear counterexample.

Conversely, if Jakarta EE 9+ dependencies require `jakarta.servlet.*` while source code still imports `javax.servlet.*`, putting both JARs on the classpath does not make them the same class.

### 5.1. Do not change every javax to jakarta

Several `javax.*` APIs remain part of Java SE and must stay unchanged:

~~~java
import javax.crypto.Cipher;
import javax.net.ssl.SSLContext;
import javax.sql.DataSource;
import javax.annotation.processing.Processor;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.management.MBeanServer;
~~~

For the APIs above, doing a global find-and-replace `javax.` → `jakarta.` will break source code.

Conversion rules must rely on the **list of enterprise specifications/packages actually renamed**, not blindly on package prefixes.

## 6. Servlet example: compiler, server, and namespace

### 6.1. Source on the legacy generation

~~~java
import javax.servlet.http.HttpServlet;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

import java.io.IOException;

public class LegacyHealthServlet extends HttpServlet {
    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response) throws IOException {
        response.getWriter().write("OK");
    }
}
~~~

This code depends on the `javax.servlet.*` Servlet API and requires a servlet container matching that generation. A Java SE JDK alone does not provide a servlet engine.

### 6.2. Source after migrating to the Jakarta generation

~~~java
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import java.io.IOException;

public class HealthServlet extends HttpServlet {
    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response) throws IOException {
        response.getWriter().write("OK");
    }
}
~~~

In the Jakarta code, `jakarta.servlet.http.HttpServlet` has a different bytecode class name from `javax.servlet.http.HttpServlet`. You need the corresponding generation of Servlet API and container.

Changing source imports is not enough if:

- Other filters/listeners still use `javax.servlet.*`.
- MVC, security, or file-upload extension frameworks were built for the legacy namespace.
- Annotations, `web.xml` descriptors, or component scanning retain old metadata.
- The running container belongs to a generation not yet supporting the new API.
- The WAR contains duplicate Servlet APIs mismatched with the server.

### 6.3. Why binary compatibility breaks

Compiled class bytecode can contain symbolic references to:

~~~text
javax/servlet/http/HttpServlet
~~~

The new Jakarta version has class:

~~~text
jakarta/servlet/http/HttpServlet
~~~

These are two distinct **binary names**. The JVM does not automatically create aliases between them. Adding a Jakarta JAR does not make a class compiled against javax automatically rewrite its references.

Some bytecode/resource transformation tools can assist migration within their documented scope, yet you must verify outputs and tool limitations. Never assume a single package-rename pass covers every annotation, reflection string, config file, and dependency.

## 7. Persistence example: annotations also need matching provider generation

Entity using Java EE/Jakarta EE 8:

~~~java
import javax.persistence.Entity;
import javax.persistence.Id;

@Entity
public class LegacyOrder {
    @Id
    private Long id;
}
~~~

Entity using Jakarta EE 9+:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public class Order {
    @Id
    private Long id;
}
~~~

With a provider that does not recognize the `jakarta.persistence.Entity` annotation, the entity may go unrecognized. Conversely, a newer Jakarta provider may not process an old entity carrying `javax.persistence.Entity` the same way.

Symptoms may appear as:

- Failing to locate a persistence unit/provider.
- Entities not being managed.
- Mapping or bootstrap errors.
- Missing classes/methods due to API/provider version mismatch.
- Missing `DataSource` or JDBC driver even when JPA APIs are present.

How to proceed:

1. Identify the JPA API generation.
2. Select a compatible provider version.
3. Verify framework integration.
4. Update imports and annotations on entities, converters/listeners.
5. Inspect `persistence.xml` and service registrations if used.
6. Verify DB migrations and schema.
7. Run integration tests against a real database.

### 7.1. Jakarta Persistence is not JDBC

JDBC interfaces such as `java.sql.Connection` and `javax.sql.DataSource` belong to Java SE. When upgrading JPA from javax to Jakarta, **do not rename `javax.sql.DataSource` to `jakarta.sql.DataSource`**.

A valid stack combines `jakarta.persistence.EntityManager` with `javax.sql.DataSource` and `java.sql.Connection`. This clearly illustrates why standard boundaries must be understood by **API role**, not by package prefix.

## 8. Jakarta Validation, CDI, and JAX-RS

### 8.1. Jakarta Validation

A Jakarta DTO might use:

~~~java
import jakarta.validation.constraints.NotBlank;

public record CreateCustomer(
        @NotBlank String name) {
}
~~~

Annotations only describe constraints. You need a compatible validation implementation provider and validation trigger points in the application/framework.

Without a runtime provider, `@NotBlank` may still compile, yet bootstrapping `jakarta.validation.Validation` will not work as expected.

When migrating from `javax.validation.*` to `jakarta.validation.*`:

- Update imports for annotations and types.
- Align provider versions.
- Check frameworks/starters.
- Test constraints actually failing on invalid data.
- Inspect generated sources, custom validators, and exception mappers.

### 8.2. CDI

CDI is more than `@Inject`. The container also manages bean discovery, scopes, interceptors, events, and lifecycles.

A standalone application containing CDI annotations without bootstrapping a CDI container does not gain dependency injection from the JDK alone. If an application server provides CDI, packaging and dependency scopes can differ from a standalone application.

During migration, review:

- Namespace of injection/CDI annotations.
- Bean archive discovery.
- `beans.xml` when present.
- Interceptor/decorator/extension code.
- API/provider/container versions.
- Module opens and reflective access if running with JPMS.

### 8.3. JAX-RS

A REST resource:

~~~java
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;

@Path("/health")
public class HealthResource {
    @GET
    @Produces(MediaType.TEXT_PLAIN)
    public String health() {
        return "OK";
    }
}
~~~

The `jakarta.ws.rs.*` API defines annotations and contracts. A runtime JAX-RS provider/framework must bootstrap routing and HTTP integration.

If an application uses Spring MVC annotations instead of JAX-RS, do not add a JAX-RS implementation simply because both handle REST. Identify the framework actually in use.

## 9. Java EE/Jakarta EE does not equal Spring

Many projects use Spring Framework or Spring Boot without running a full Java EE/Jakarta EE application server.

Possibilities include:

- Spring MVC running on an embedded servlet container.
- A Spring Boot executable JAR bundling the necessary container and providers.
- A Spring application packaged as a WAR for deployment to an external container.
- Spring Data JPA integrating with a persistence provider.
- Spring using selected Jakarta EE APIs across layers without needing a full Jakarta EE platform implementation.

Therefore, the three phrases “running Java”, “using Jakarta Servlet API”, and “being a full Jakarta EE application” do not mean the same thing.

### 9.1. Framework major versions often dictate the namespace

One framework generation may build upon `javax.*` enterprise APIs; a newer generation may move to `jakarta.*`. During migration, consult the **compatibility matrix** covering framework, JDK, container, and API generation.

You cannot simply upgrade the JDK, keep an old framework, and manually rewrite all entity/servlet imports without checking what the framework supports.

### 9.2. Do not drop application server dependencies into every executable JAR

A standalone application needs only the embedded server and providers chosen by its framework. Packing multiple containers or full Jakarta platform implementations into one artifact does not improve compatibility—it risks classpath conflicts, service discovery ambiguity, and larger maintenance surface.

## 10. Java EE servers, Jakarta EE servers, and embedded containers

### 10.1. External application server

A WAR deployed to an external server can rely on the server supplying APIs and implementations according to the profiles/specifications supported by that server.

Maven example for a container-provided Servlet API:

~~~xml
<dependency>
    <groupId>jakarta.servlet</groupId>
    <artifactId>jakarta.servlet-api</artifactId>
    <version>VERSION_MATCHING_SERVER</version>
    <scope>provided</scope>
</dependency>
~~~

`VERSION_MATCHING_SERVER` is an illustrative placeholder that must be replaced with the actual compatible version.

**`provided` does not mean the API is unnecessary at runtime.** It means the build expects an external server/container to supply the matching dependency.

### 10.2. Embedded server

An application launched via `java -jar application.jar` needs an embedded HTTP/servlet engine if its design uses the servlet web stack.

In that case, marking Servlet API `provided` without an embedded container at runtime is insufficient. A framework starter may pull the container in transitively; inspect `runtimeClasspath` and the released artifact.

### 10.3. Full platform vs. profiles

Java EE/Jakarta EE platforms define different specification sets/profiles depending on version. A server supporting one profile does not necessarily supply every API of the full platform.

Before removing a dependency from a WAR on the assumption that “the server surely provides it”, check **which exact server version, which profile, and which services are actually supplied**.

### 10.4. Class-loader isolation and duplicate APIs

An API JAR packaged inside `WEB-INF/lib` can conflict with the version already supplied by the container. On the JVM, class identity depends not only on binary name, but also on the defining class loader.

Two classes sharing the same name yet defined by two independent class loaders cannot be cast to one another, leading to `ClassCastException` or linkage errors. Investigation must verify where classes are loaded from, not merely inspect the dependency tree.

## 11. Maven: scoping along platform boundaries

A WAR application:

~~~xml
<dependencies>
    <dependency>
        <groupId>jakarta.servlet</groupId>
        <artifactId>jakarta.servlet-api</artifactId>
        <version>SERVLET_API_VERSION</version>
        <scope>provided</scope>
    </dependency>

    <dependency>
        <groupId>jakarta.persistence</groupId>
        <artifactId>jakarta.persistence-api</artifactId>
        <version>PERSISTENCE_API_VERSION</version>
    </dependency>
</dependencies>
~~~

This is **sample syntax**, not a complete production POM: the JPA API may be server-provided on a Jakarta EE server, or bundled by the application alongside its provider. Scopes depend on deployment topology.

| Maven scope | Role during migration |
|---|---|
| `compile` | API present at compile time and normally at runtime |
| `provided` | API needed at compile time, supplied at runtime by server/container |
| `runtime` | Provider/driver needed at runtime, unnecessary to import at compile time |
| `test` | Dependencies/implementations solely for testing |
| BOM `import` in `dependencyManagement` | Manages versions without automatically adding runtime implementations |

A Jakarta EE or framework BOM coordinates versions, yet **a BOM does not install providers by itself**. Declare the concrete dependencies actually used.

### 11.1. Do not work around errors with an uncontrolled “mega JAR”

Adding all Java EE APIs, Jakarta EE APIs, and assorted providers together just to silence errors can trigger:

- Duplicate classes/namespaces.
- Mismatched API and implementation generations.
- `ServiceLoader` picking an unintended provider.
- Skewed transitive dependencies.
- Container and logging collisions.
- Broken JDK runtime baselines.

Instead, inventory every API in use and identify who supplies its implementation.

## 12. Gradle: `compileOnly`, `implementation`, `runtimeOnly`, and `api`

With Gradle, declarations depend on your deployment model:

~~~groovy
plugins {
    id 'java'
}

dependencies {
    // Example API supplied by an external servlet container:
    compileOnly("jakarta.servlet:jakarta.servlet-api:SERVLET_VERSION")

    // API used directly by application code:
    implementation("jakarta.persistence:jakarta.persistence-api:JPA_VERSION")

    // Provider executing persistence in a standalone deployment:
    runtimeOnly("org.example:orm-provider:PROVIDER_VERSION")
}
~~~

`org.example` coordinates and `*_VERSION` are placeholders. Do not copy them verbatim into real builds. With Gradle's Java Library plugin, use `api(...)` if a dependency type is exposed in your library's **public contract** and consumers need it on their compile classpath.

Key distinctions:

- `compileOnly` does not automatically include the API at runtime.
- `runtimeOnly` does not make classes available for source compilation.
- `implementation` is available on the module's compile/runtime paths without exporting it on the consumer's public compile API.
- `api` exposes the dependency to consumers using the public contract.
- Test source sets have separate classpaths from production and must not be treated as proof of production packaging.

Inspect:

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
~~~

These commands are examples for learners to run on appropriate projects, not commands executed while authoring this material.

## 13. Migration is more than updating imports

Replacing `javax.servlet` with `jakarta.servlet` may make one file compile, yet many other constraints remain.

### 13.1. Source code

Search across:

- Application sources and test sources.
- Filters/listeners/interceptors.
- Controller/resource classes.
- Entities, converters, validators, event listeners.
- Custom annotation processors.
- Generated sources.
- Utility libraries whose public types contain legacy enterprise APIs.

### 13.2. Binary dependencies

A JAR already compiled against `javax.persistence.EntityManager` still references that exact binary name even after application source changes. You may need to upgrade or replace the dependency, or apply supported transformations.

### 13.3. XML descriptors and resources

Enterprise applications may rely on:

- `web.xml`.
- `persistence.xml`.
- `beans.xml`.
- Server/vendor deployment descriptors.
- Tag library descriptors.
- Service loader files in `META-INF/services`.
- Config files holding Java class names as strings.
- Reflection configs for native-image.

Some descriptors use distinct schema namespaces/versions. Changing Java imports does not automatically update XML schemas or server configuration.

### 13.4. Annotations and reflection

An annotation processor, scanner, or framework may search for `javax.*` annotations by exact class name. After changing annotations to `jakarta.*`, an old scanner might silently skip classes without reporting any compile error.

You must test **real functionality**: request routing, persistence, validation, injection, and serialization.

### 13.5. Service Provider Interface

Some APIs use `ServiceLoader` or provider discovery via files inside `META-INF/services`. When an interface changes from `javax...` to `jakarta...`, the service descriptor filename may also need updating to the new API name.

Having the provider JAR present with the wrong service file name leads to “provider not found”. Shading or fat JAR assembly can also drop or overwrite service files.

## 14. Source compatibility, binary compatibility, and runtime compatibility

| Compatibility layer | Question | Failure examples |
|---|---|---|
| Source | Does source recompile against the new API? | `package javax.servlet does not exist` |
| Binary | Does pre-compiled bytecode resolve types/methods as before? | `NoClassDefFoundError`, `NoSuchMethodError` |
| Runtime provider | Does an implementation exist executing the API in use? | Validation/JSON/JAXB provider not found |
| Container | Does the server/embedded runtime support the target generation? | Servlet class mismatch |
| Deployment metadata | Are descriptors, resources, and service registries accurate? | Routes/beans/entities unregistered |
| Behavior | Do operations preserve semantics? | Mapping, transactions, or validation changed |
| Data protocol | Are JSON/XML/database contracts preserved? | Serializer output changed or consumer parsing fails |
| JDK compatibility | Do APIs/providers run on the target JDK? | `UnsupportedClassVersionError` |

A system can achieve **source compatibility** and still fail at runtime. Conversely, an application retaining the `javax.*` namespace can still run on a newer JDK if it uses a legacy enterprise stack supporting that runtime with all dependencies explicitly declared.

### 14.1. Why different type names mean major breaking changes

Example public method:

~~~java
// Legacy contract
void handle(javax.servlet.http.HttpServletRequest request);

// New contract
void handle(jakarta.servlet.http.HttpServletRequest request);
~~~

The class-file method descriptors differ because the parameter has a different binary name. For pre-compiled consumers, the new method **is not** the same descriptor as the old method; calling it against the updated library can throw `NoSuchMethodError`.

Evaluate binary consumers independently if your library publishes public APIs consumed across multiple services.

## 15. Diagnosing failures accurately so you fix the right layer

| Symptom | Possible cause | Check |
|---|---|---|
| `package javax.xml.bind does not exist` | New JDK no longer bundles JAXB API or compile dependency is missing | API generation, JDK/modules, Maven/Gradle |
| `package jakarta.persistence does not exist` | Jakarta Persistence API absent from compile classpath | Dependencies and namespace |
| `NoClassDefFoundError: javax/servlet/...` | Runtime lacks the legacy Servlet API generation | WAR/container, binary dependencies |
| `NoSuchMethodError` | API/provider or framework binary version mismatch | Descriptors and dependency graph |
| `AbstractMethodError` | Implementation lacks a method expected at runtime | API/provider versions |
| `ClassCastException` | Duplicate API classes or different class loaders | Class loading and server libraries |
| `ValidationException` at bootstrap | Missing/wrong validation provider or config | Provider discovery, generation |
| JAXB provider not found | API present without runtime implementation or metadata | JAXB runtime and service files |
| HTTP 404 despite servlet compiling | Container/registration/descriptor mismatch | Runtime logs, route mappings |
| Entity not managed | Wrong generation of annotations/provider/scanning | Persistence bootstrap and metadata |
| `ServiceConfigurationError` | Invalid SPI/provider resource | Service files/module declarations |
| `UnsupportedClassVersionError` | Artifact requires newer JDK than active runtime | Class major versions, JDK baseline |

None of the errors above proves a single root cause in isolation. Inspect full stack traces, nested causes, and **which JARs were actually loaded**.

### 15.1. Distinguishing missing API from missing implementation

Code example:

~~~java
import jakarta.validation.Validation;
import jakarta.validation.ValidatorFactory;

ValidatorFactory factory =
        Validation.buildDefaultValidatorFactory();
~~~

If the `Validation` class is absent: missing **API/runtime class**.

If the class exists yet bootstrap finds no provider: missing **implementation/discovery/configuration**.

If a provider is found yet fails linkage: possible **version mismatch**. Adding an API JAR from a different generation is not a reasoned fix.

## 16. Locating enterprise API usages prior to migration

Search suggestions:

~~~bash
rg -n "import javax\\.(servlet|persistence|validation|ws|enterprise|ejb|jms|transaction|mail|xml\\.bind)" src
rg -n "import jakarta\\." src
rg -n "javax\\.|jakarta\\." src/main/resources
rg -n "web\\.xml|persistence\\.xml|beans\\.xml" .
rg -n "META-INF/services|ServiceLoader" .
~~~

These commands only illustrate repository searches, not an exhaustive pattern set covering every API. Also inspect:

- Test fixtures.
- Generated Java sources.
- JSP/tag libraries.
- Build plugin configurations.
- Reflection strings and class names inside XML/YAML/properties.
- Packaged artifacts.
- Dependencies owned by other teams.

Never run a global replace-all on `javax.`, as it can break Java SE APIs.

### 16.1. Inspecting the dependency tree

Maven:

~~~bash
mvn dependency:tree
~~~

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jakarta.servlet \
  --configuration runtimeClasspath
~~~

Determine whether old Java EE / Jakarta EE APIs are pulled transitively, and whether the framework or server manages versions.

### 16.2. Inspecting classes inside artifacts

~~~bash
jar tf application.war
jar tf library.jar
javap -classpath library.jar -p -s com.example.PublicApi
~~~

`javap -s` reveals whether method descriptors still reference `javax/...` binary names or have moved to `jakarta/...`. For WARs, inspect `WEB-INF/lib` alongside container libraries to avoid duplicate APIs/runtimes.

### 16.3. Inspecting with jdeps

~~~bash
jdeps --recursive --class-path "lib/*" application.jar
~~~

`jdeps` analyzes static class/module dependencies. It cannot see every reflection string or dynamically loaded SPI provider, so pair it with runtime testing. For executable JARs containing nested libraries, extracting/adjusting the classpath may be required for accurate analysis.

## 17. Building a migration matrix before upgrading

Every project should build a table like this:

| Component | Current | Target | Runtime provider | Action |
|---|---|---|---|---|
| JDK | Old JDK | Target JDK | JDK distribution | Verify Java SE support and modules |
| Servlet | `javax.servlet` | `jakarta.servlet` or keep temporarily | External/embedded container | Upgrade container/framework in sync |
| Persistence | `javax.persistence` | `jakarta.persistence` or keep temporarily | ORM/server | Align API/provider and entity metadata |
| Validation | `javax.validation` | `jakarta.validation` | Provider/server | Test constraints and bootstrap |
| REST API | JAX-RS javax | Jakarta REST | JAX-RS provider | Test resource registration |
| JAXB/JAX-WS | JDK-bundled/legacy | Appropriate external dependency | Application/provider | Separate JDK removal from namespace |
| JDBC | `java.sql`/`javax.sql` | Keep Java SE API | JDK + JDBC driver | Do not change namespace |
| Cryptography | `javax.crypto` | Keep Java SE API | JDK/security provider | Do not change namespace |

For each row, also document version, JDK baseline, compatibility guide, owner, test coverage, and rollback plan.

### 17.1. Choosing the roadmap: keep javax temporarily or migrate to Jakarta?

Teams do not always have to switch namespaces on the exact day they upgrade the JDK.

**Path A — upgrade JDK first, keep the older enterprise generation:** fits when frameworks and providers already support the target JDK. Explicitly declare dependencies removed from the JDK and review security/support status for the stack.

**Path B — migrate the entire enterprise stack to Jakarta:** fits when target frameworks/containers require `jakarta.*`. Update source imports, binary dependencies, annotation/resource metadata, providers, and deployment.

**Path C — split by module/service:** applies when services deploy independently. Each service must maintain an internally consistent stack; communicate over HTTP/JSON/event schemas or compatible APIs rather than passing `javax.*` ↔ `jakarta.*` object types on a single classpath hoping the JVM converts them automatically.

Do not retain an unsupported legacy enterprise stack indefinitely merely to avoid change. Weigh security support, dependency lifecycles, and migration cost.

## 18. Controlled migration workflow

~~~mermaid
flowchart TD
    A["Inventory JDK, APIs, providers, frameworks, servers"] --> B["Classify Java SE / Java EE / Jakarta EE"]
    B --> C["Choose target JDK and enterprise generation"]
    C --> D["Upgrade frameworks, providers, and containers together"]
    D --> E["Update sources/imports/annotations/descriptors"]
    E --> F["Build and inspect dependency graph / artifact"]
    F --> G["Run real integration tests"]
    G --> H{"Functionally correct and compatible?"}
    H -->|Yes| I["Controlled rollout and archive evidence"]
    H -->|No| J["Isolate classpath / provider / schema error"]
    J --> D
~~~

### Step 1. Lock down the baseline

Record:

- JDK vendor/version.
- Framework and application server versions.
- Enterprise APIs currently in use.
- Implementation providers.
- JAR/WAR/EAR packaging layout and class loaders.
- Dependency graph and artifact checksums.
- Current test results.
- API contracts and affected external clients/services.

### Step 2. Define the target

Select a supported combination of JDK runtime, enterprise API generation, and server/provider. Never use “the JDK installs on the machine” as proof that the server/framework supports that JDK.

### Step 3. Update dependencies and BOMs

Align frameworks, APIs, providers, build plugins, and containers per your project's compatibility matrix. Remove old APIs/providers only once replacements are confirmed. Avoid mixing two generations within one application unless an explicitly engineered isolation boundary exists.

### Step 4. Update sources and metadata

Update enterprise imports, annotations, XML descriptors, service descriptors, generated sources, and reflection strings. Keep Java SE `javax.*` unchanged.

### Step 5. Clean build

Run a clean build in CI using the target JDK/toolchain, verifying annotation processors and generated classes. Never let stale outputs mask migration bugs.

### Step 6. Test bootstrap and real functionality

Verify:

- HTTP requests flowing through servlets/filters.
- Bean dependency injection and lifecycles.
- JPA entity scanning, SQL, and transactions.
- Validation constraints failing at the expected boundaries.
- JAX-RS routes and serialization.
- JAXB/JAX-WS or Mail where used.
- Logging/security/TLS.
- Packaged application deployed onto the target server/container.

### Step 7. Test old and new consumers

If a public library changes namespaces in method signatures, pre-compiled consumers may be incompatible. A major release, adapter, or coordinated migration across consumers may be needed.

Wire protocols (JSON, XML, databases) also require testing: changing Java namespaces **does not automatically force** JSON schemas or XML document formats to change, though newer implementations may alter default behaviors.

### Step 8. Deploy and monitor

Define clear canary/rollback criteria: startup/DI errors, HTTP 5xx, persistence mapping issues, validation failures, payload schema errors, provider resolution failures, and latency. Collect telemetry per artifact/version rather than relying solely on “JDK upgraded”.

## 19. Environment-by-environment test matrix

| Scenario | API generation | Runtime | What to verify |
|---|---|---|---|
| Baseline | Legacy Java EE/Jakarta EE | Legacy server/JDK | Functionality and known issues |
| JDK upgrade only | Legacy API generation | New JDK, supported legacy runtime | Isolates JDK removal/behavior issues |
| Enterprise upgrade | New Jakarta generation | New framework/server | Source/metadata/provider compatibility |
| WAR production | API marked provided | External container | Class loaders, servlet boot, resources |
| Embedded JAR | Bundled API and server runtime | Target JDK | Packaging, endpoints, and dependencies |
| Legacy consumer | Compiled against old API | New library | Binary compatibility or consumer migration |
| Recompiled consumer | New API | New runtime | Source compatibility |
| Data integration | May differ from internal generation | HTTP/JSON/XML/DB | Wire contract preserved |

Execute tests against the **actual released JAR/WAR**, exact JDK, and target server/container image, not solely by compiling modules inside an IDE.

## 20. End-to-end migration scenario

Suppose an order-management system initially:

- Runs on JDK 8.
- Packages a WAR deployed to a Servlet container on the `javax.servlet` generation.
- Uses `javax.persistence` and an older ORM provider.
- Uses JAXB `javax.xml.bind` for XML integration.
- Uses `javax.sql.DataSource` to configure connection pools.
- Uses `javax.validation` validation annotations.
- Depends on external libraries already compiled against legacy enterprise APIs.

The team wants to run on a modern JDK and move to Jakarta-generation frameworks/controllers.

**Problems if upgraded out of sync:**

1. Dropping JDK 8 removes JAXB from the target JDK.
2. Updating only Servlet imports while still deploying to a legacy container.
3. Updating Entity annotations to `jakarta.persistence` while using an ORM provider that only understands javax.
4. Changing `javax.sql.DataSource` into a nonexistent Jakarta package.
5. Adding both Servlet APIs to avoid compile errors, creating classloader conflicts.
6. Failing to upgrade legacy integration libraries, leaving `javax.servlet.*` binary method signatures inside JARs.
7. Overlooking `web.xml` or provider metadata/resources.
8. Unit tests passing while runtime fails to register servlets or manage entities.

**An appropriate plan:**

- Inventory accurately which APIs belong to Java SE versus enterprise specifications.
- Keep `javax.sql.DataSource` because it belongs to Java SE.
- Decide explicitly whether JAXB stays on the javax generation temporarily or moves to Jakarta, then pick the matching runtime.
- Upgrade Servlet API, container, and framework to the same generation.
- Upgrade JPA API and ORM provider together, running persistence tests.
- Upgrade the validation provider and test real constraint enforcement.
- Inspect sources, dependency bytecode, and XML/service descriptors.
- Package WAR/JAR according to the chosen runtime model.
- Execute end-to-end tests with database/XML/HTTP on the new JDK.
- Roll out via canary while watching classloader/provider/data errors.

Crucially, you may need **one JDK upgrade plan** and **one enterprise platform upgrade plan**—linked yet distinct so risk remains controllable.

## 21. Common mistakes

### 21.1. “javax means Java EE, so everything must become jakarta”

False. `javax.crypto`, `javax.sql`, `javax.net.ssl`, `javax.annotation.processing`, and `javax.xml.parsers` are examples of Java SE APIs that stay under `javax.*`.

### 21.2. “Upgrading to JDK 21 means we are already using Jakarta EE”

False. The JDK is the Java SE runtime; enterprise APIs/providers sit in a separate layer. You must explicitly select enterprise dependencies or runtimes.

### 21.3. “Java EE was removed from JDK 11”

Too broad. JDK 11 removed **several previously bundled Java EE/CORBA modules**; not every Java EE specification ever resided inside the JDK.

### 21.4. “Jakarta EE 8 already moved completely to jakarta.*”

False. Moving many enterprise packages to `jakarta.*` was the defining transition of Jakarta EE 9.

### 21.5. “Adding both javax and jakarta APIs provides an adapter”

False. The two types have different binary names; the JVM creates no automatic bridge. Libraries, providers, and frameworks must align on one generation or use explicitly supported bridging adapters.

### 21.6. “Changing imports is enough”

False. Binary dependencies, annotation processors, runtime providers, descriptors, reflection strings, and containers may also need migration.

### 21.7. “Having the API means it can run”

False. Servlets need a container; JPA needs a provider; validation needs an engine; JAXB needs a runtime/provider under the chosen dependency model.

### 21.8. “Scope provided means the dependency is not needed at runtime”

False. It means a component **outside the application** will supply it. If the runtime fails to provide it, the application breaks.

### 21.9. “Spring Boot is definitely a Jakarta EE server”

Not so. Spring Boot can use Jakarta/Servlet APIs and embedded servers, yet that does not constitute implementing the full Jakarta EE platform.

### 21.10. “One local run proves migration compatibility”

Insufficient. Local runs may differ in JDK, broader classpath, IDE plugins, embedded providers, or test databases vs. production.

## 22. Classification and migration checklist

### Platform identification

- [ ] Separated Java SE APIs from enterprise APIs.
- [ ] Left Java SE `javax.*` packages unchanged rather than renaming to `jakarta.*`.
- [ ] Confirmed namespace differences across Java EE 8, Jakarta EE 8, and Jakarta EE 9+.
- [ ] Distinguished JDK upgrades from enterprise platform/framework upgrades.
- [ ] Identified relevant JEP 320 modules when crossing JDK 11+.

### Dependencies and implementations

- [ ] Designated runtime implementation/provider for every API.
- [ ] Verified whether the application, embedded server, or external container supplies implementations.
- [ ] Aligned versions per framework/server compatibility matrices.
- [ ] Audited Maven scopes/Gradle configurations.
- [ ] Audited `compileClasspath`, `runtimeClasspath`, and transitive dependencies.
- [ ] Eliminated duplicates or mismatched-generation providers where applicable.
- [ ] Verified JDK baselines for all runtime dependencies.

### Sources, binaries, and metadata

- [ ] Audited imports, annotations, and public API signatures.
- [ ] Searched for enterprise `javax.*` inside pre-compiled libraries, not just sources.
- [ ] Updated required XML descriptors and service/provider metadata.
- [ ] Verified annotation processing and generated sources.
- [ ] Distinguished missing APIs from missing implementations.
- [ ] Verified actual class loading/JARs inside server runtimes.
- [ ] Evaluated pre-compiled binary consumers when public APIs change namespaces.

### Operations and data

- [ ] Verified application bootstrap on target JDK/container.
- [ ] Tested servlet HTTP, CDI/DI, JPA/transactions, validation, and JAX-RS if used.
- [ ] Tested JAXB/JAX-WS, messaging, Mail, or service providers if used.
- [ ] Verified JSON/XML/data contracts across producer/consumer versions.
- [ ] Tested against the packaged artifact and target server image.
- [ ] Archived dependency graphs, runtime versions, and test evidence.
- [ ] Prepared rollout and rollback plans.

## Conclusion

**Java SE** is the core language, standard library, and runtime platform; **Java EE** is the enterprise specification generation preceding Jakarta; **Jakarta EE** continues those specifications, introducing the pivotal namespace transition from `javax.*` to `jakarta.*` in Jakarta EE 9. Not every `javax.*` belongs to Java EE, and upgrading the JDK does not automatically migrate an application to Jakarta EE.

When migrating, classify **which APIs come from the JDK, which come from enterprise specifications, who supplies implementations and containers, and which generation is supported**. Handle JDK-removed bundled modules at JDK 11 separately from enterprise namespace transitions. Then verify the entire stack—from sources, bytecode, dependency graphs, and descriptors through runtime behavior and data protocols. This approach prevents mixed `javax`/`jakarta` errors, missing providers, and class-loader conflicts while keeping Java upgrades verifiable and reversible.
