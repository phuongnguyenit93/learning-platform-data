# Scope of the javax to jakarta Namespace Change

When modernizing a Java EE application or moving to a framework supporting Jakarta EE, one of the most misunderstood changes is renaming packages from **javax** to **jakarta**. Many developers hear that "Jakarta replaces javax" and perform a global string replace across the source code. That approach can break APIs that still belong to Java SE, while missing dependencies, configuration files, service descriptors, and third-party binary libraries already compiled against the old namespace.

The most crucial boundary is: **the change from javax.* to jakarta.* applies to APIs belonging to Jakarta EE specifications whose namespaces moved starting in Jakarta EE 9; it does not apply to all Java javax.* packages.** An application running Java 21 still uses javax.sql.DataSource, javax.net.ssl.SSLContext, or javax.xml.parsers.DocumentBuilderFactory normally.

This lesson belongs to **Java Advance Compatibility Migration**, chapter **Java EE and Jakarta**. The content focuses on the exact scope of the namespace change, before/after examples for representative APIs, server and framework involvement, inventorying locations outside Java imports, synchronized upgrade strategies, and identifying compatibility errors during conversion.

## 1. Understanding the Relationship Between Java SE, Java EE, and Jakarta EE

The Java Platform comprises distinct technology families:

- **Java SE (Standard Edition):** the language, JVM, and foundational libraries such as collections, concurrency, JDBC, XML processing, networking, and cryptography.
- **Java EE (Enterprise Edition):** a set of enterprise application specifications such as Servlet, JPA, JAX-RS, CDI, JMS, Bean Validation, and other APIs.
- **Jakarta EE:** the name and ecosystem continuing the evolution of those enterprise technologies after transferring Java EE to the Eclipse Foundation.

These three names do not correspond to three Java language versions. Upgrading from Java 8 to Java 17 or Java 21 is one effort; migrating from Java EE/Jakarta EE 8 to Jakarta EE 9+ is another effort. They often happen at the same time because newer frameworks or application servers raise both the minimum JDK level and enterprise APIs.

### 1.1. Milestones to Remember

| Platform | Primary Enterprise API Namespace | Migration Significance |
|---|---|---|
| Java EE 8 | javax.* | Traditional Java EE ecosystem |
| Jakarta EE 8 | Still javax.* | Rebranded/transferred specification governance without changing all package names yet |
| Jakarta EE 9 | jakarta.* for migrated EE APIs | Major namespace transition step |
| Jakarta EE 9.1 | jakarta.* | Continues Jakarta EE platform with baseline changes |
| Jakarta EE 10, 11, and applicable newer releases | jakarta.* | Evolution of Jakarta APIs post-transition |

Common confusion: **Jakarta EE 8 does not mean sources already use jakarta.servlet or jakarta.persistence.** Many artifacts published under Jakarta EE 8 branding or Maven groupIds still contain classes named javax.*. To determine compatibility, inspect the actual **package and API level**, not merely the groupId name.

### 1.2. The Accurate Model

~~~text
Java SE
  java.*
  many javax.* belonging to Java SE
  (DO NOT rename wholesale)

Java EE / Jakarta EE 8
  javax.servlet.*
  javax.persistence.*
  javax.ws.rs.*
  javax.validation.*
             |
             | Jakarta EE 9 namespace migration
             v
Jakarta EE 9+
  jakarta.servlet.*
  jakarta.persistence.*
  jakarta.ws.rs.*
  jakarta.validation.*
~~~

Changing package names is not aliasing. To the JVM, javax.servlet.Filter and jakarta.servlet.Filter are **two types with different fully qualified names**; they may look structurally similar, yet they are not the same interface.

## 2. What Scope Actually Needs Changing?

The accurate approach is checking the **specification owning the API**:

1. Does that package belong to Java SE or to a Java EE/Jakarta EE specification?
2. Which class namespace does the artifact used by the project actually contain?
3. Which namespace does the target framework/container require?
4. Do other dependencies still expose javax EE types in public signatures?
5. Do configuration files or metadata outside Java sources reference old type names?

For an application moving from Java EE 8/Jakarta EE 8 to Jakarta EE 9+, most enterprise APIs need import updates according to their corresponding specifications. Java SE APIs, however, stay unchanged.

### 2.1. Common Mapping Table

| API / Area | Old Namespace | Jakarta EE 9+ Namespace |
|---|---|---|
| Servlet and filters | javax.servlet.* | jakarta.servlet.* |
| Servlet HTTP | javax.servlet.http.* | jakarta.servlet.http.* |
| JSP / Jakarta Server Pages | javax.servlet.jsp.* | jakarta.servlet.jsp.* |
| Expression Language | javax.el.* | jakarta.el.* |
| Persistence / JPA | javax.persistence.* | jakarta.persistence.* |
| Bean Validation | javax.validation.* | jakarta.validation.* |
| REST / JAX-RS | javax.ws.rs.* | jakarta.ws.rs.* |
| Contexts and Dependency Injection | javax.enterprise.* | jakarta.enterprise.* |
| Dependency Injection API | javax.inject.* | jakarta.inject.* |
| EE Common Annotations | javax.annotation.* | jakarta.annotation.* |
| Enterprise Beans / EJB | javax.ejb.* | jakarta.ejb.* |
| Jakarta Transactions | javax.transaction.* | jakarta.transaction.* |
| Messaging / JMS | javax.jms.* | jakarta.jms.* |
| WebSocket | javax.websocket.* | jakarta.websocket.* |
| Faces / JSF | javax.faces.* | jakarta.faces.* |
| Security Enterprise | javax.security.enterprise.* | jakarta.security.enterprise.* |
| Interceptors | javax.interceptor.* | jakarta.interceptor.* |
| Batch | javax.batch.* | jakarta.batch.* |
| JSON Processing | javax.json.* | jakarta.json.* |
| JSON Binding | javax.json.bind.* | jakarta.json.bind.* |
| Mail | javax.mail.* | jakarta.mail.* |
| Activation | javax.activation.* | jakarta.activation.* |
| XML Binding / JAXB | javax.xml.bind.* | jakarta.xml.bind.* |
| XML Web Services / JAX-WS | javax.xml.ws.* | jakarta.xml.ws.* |
| SOAP API | javax.xml.soap.* | jakarta.xml.soap.* |
| Connectors | javax.resource.* | jakarta.resource.* |

This table serves as a directional map across specifications that moved namespaces. Always verify against the **specific versions** of the API, framework, and server. Beyond package renaming, newer releases may introduce other changes in methods, behavior, dependencies, or configuration.

### 2.2. Do Not Replace All javax.*

Many javax.* packages remain Java SE APIs or independent APIs outside the namespace change above:

| API Keeping javax in Java SE | Role |
|---|---|
| javax.sql.DataSource | JDBC and data connection management |
| javax.net.ssl.SSLContext | TLS/JSSE |
| javax.crypto.Cipher | Cryptography |
| javax.naming.InitialContext | Java SE JNDI API |
| javax.xml.parsers.DocumentBuilderFactory | XML parser |
| javax.xml.stream.XMLInputFactory | StAX |
| javax.xml.transform.Transformer | XML transformation |
| javax.xml.validation.SchemaFactory | XML schema validation |
| javax.xml.xpath.XPath | XPath |
| javax.management.MBeanServer | Java Management Extensions |
| javax.swing.JFrame | Swing GUI |
| javax.annotation.processing.Generated | Annotation processing in Java SE |
| javax.transaction.xa.XAResource | XA/JTA integration interface residing in Java SE |

In particular, **javax.transaction.xa** remains a Java SE package; do not mechanically rename it to jakarta.transaction.xa. Likewise, never rename javax.xml.parsers to jakarta.xml.parsers: Jakarta XML Binding changed from javax.xml.bind to jakarta.xml.bind, yet many other XML processing parts remain inside Java SE's javax.xml.*.

### 2.3. Easily Confused Annotations

Two classes with similar simple names have different origins:

~~~java
import javax.annotation.processing.Generated;
~~~

This is the Java SE annotation processing API and should not be changed arbitrarily.

Meanwhile, with Jakarta Common Annotations:

~~~java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
~~~

these are lifecycle annotations used in Jakarta EE components or frameworks supporting them.

Some third-party annotations like Nullable and Nonnull come from independent libraries and are not automatically replaced by Jakarta Common Annotations. Always inspect the origin of each imported annotation.

## 3. Changing Packages Is Not Variable Renaming

Consider an old Servlet:

~~~java
import javax.servlet.ServletException;
import javax.servlet.annotation.WebServlet;
import javax.servlet.http.HttpServlet;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

import java.io.IOException;

@WebServlet("/hello")
public class HelloServlet extends HttpServlet {
    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response)
            throws ServletException, IOException {
        response.getWriter().write("Hello");
    }
}
~~~

In Jakarta Servlet:

~~~java
import jakarta.servlet.ServletException;
import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import java.io.IOException;

@WebServlet("/hello")
public class HelloServlet extends HttpServlet {
    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response)
            throws ServletException, IOException {
        response.getWriter().write("Hello");
    }
}
~~~

In this example the business logic is virtually unchanged. Yet the JVM treats the new superclass, annotations, and parameter types as distinct classes from the old namespace.

### 3.1. Java Source Is Easy to Edit, While Binaries Do Not Become Compatible Automatically

A method taking:

~~~java
void register(javax.servlet.Filter filter);
~~~

does not accept an object implementing only:

~~~java
jakarta.servlet.Filter
~~~

The two interfaces have different fully qualified names. If an older library was compiled to accept javax.servlet.Filter, you cannot make it compatible with jakarta.servlet.Filter simply by putting both JARs on the classpath.

In bytecode, references and method descriptors contain the respective binary names. Changing namespaces affects **binary linkage**, reflection, annotation scanning, and framework extension points.

### 3.2. Never Force Casts Between the Two Namespaces

Code like the following is not a migration strategy:

~~~java
// Cannot assume old and new Servlet Filters are equivalent:
jakarta.servlet.Filter jakartaFilter =
    (jakarta.servlet.Filter) legacyJavaxFilter;
~~~

If the object implements only javax.servlet.Filter, the cast is invalid. Upgrade the implementation, place an explicit adapter at a well-designed API boundary, or isolate deployments instead of forcing a cast.

## 4. Jakarta Persistence / JPA Example

Old Java EE entity:

~~~java
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.Table;

@Entity
@Table(name = "orders")
public class OrderEntity {
    @Id
    private Long id;

    private String status;
}
~~~

Using Jakarta Persistence 3.x:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "orders")
public class OrderEntity {
    @Id
    private Long id;

    private String status;
}
~~~

**Table and column names do not change automatically just because annotation packages changed.** The database schema can stay unchanged. However, the runtime persistence provider must recognize the jakarta.persistence.Entity annotation.

### 4.1. Common Error When Changing Only Dependencies

If an entity still uses javax.persistence.Entity while the target Hibernate/JPA provider only scans for jakarta.persistence annotations, the entity may fail to be recognized as a valid entity.

Symptoms may include:

- Not a managed type.
- Entity not scanned.
- Persistence unit failing to initialize.
- Mapping exceptions.
- Method signature mismatches on EntityManager/Criteria APIs.

Conversely, if code switches to jakarta.persistence while the provider supports only javax.persistence, compilation or runtime integration can also fail.

### 4.2. DAO Public APIs Must Change Too

A library exposing a method:

~~~java
javax.persistence.EntityManager getEntityManager();
~~~

exposes a javax type on its public boundary. If a new framework uses only jakarta.persistence.EntityManager, all consumers and plugins calling that contract need an upgrade strategy.

Do not scan only imports inside implementations; inspect generic types, parent interfaces, method signatures, annotations, and compiled metadata.

## 5. Bean Validation and Dependency Injection Examples

### 5.1. Bean Validation

Before:

~~~java
import javax.validation.Valid;
import javax.validation.constraints.NotBlank;

public final class CreateUserRequest {
    @NotBlank
    private String username;
}
~~~

After:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

public final class CreateUserRequest {
    @NotBlank
    private String username;
}
~~~

The code looks similar, yet the annotation types are distinct. The validation provider or framework binding must support the target namespace. If the application keeps javax.validation annotations in a stack integrated only with Jakarta Validation, automatic validation may not execute as expected.

### 5.2. Dependency Injection

Before:

~~~java
import javax.inject.Inject;
import javax.enterprise.context.ApplicationScoped;

@ApplicationScoped
public class CatalogService {
    @Inject
    CatalogRepository repository;
}
~~~

After:

~~~java
import jakarta.inject.Inject;
import jakarta.enterprise.context.ApplicationScoped;

@ApplicationScoped
public class CatalogService {
    @Inject
    CatalogRepository repository;
}
~~~

Do not assume a CDI container built for jakarta.enterprise.* will handle legacy javax.enterprise.* annotations. Check the runtime's compatibility policy and version.

### 5.3. Lifecycle Annotations

Before:

~~~java
import javax.annotation.PostConstruct;
import javax.annotation.PreDestroy;
~~~

After:

~~~java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
~~~

If a framework detects annotations strictly by exact type, retaining old-namespace annotations can keep initialization/cleanup callbacks from firing. That easily causes bugs that appear only during runtime startup or shutdown.

## 6. JAX-RS / REST Example

An older resource:

~~~java
import javax.ws.rs.GET;
import javax.ws.rs.Path;
import javax.ws.rs.Produces;
import javax.ws.rs.core.MediaType;

@Path("/ping")
public class PingResource {
    @GET
    @Produces(MediaType.TEXT_PLAIN)
    public String ping() {
        return "pong";
    }
}
~~~

In Jakarta REST:

~~~java
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;

@Path("/ping")
public class PingResource {
    @GET
    @Produces(MediaType.TEXT_PLAIN)
    public String ping() {
        return "pong";
    }
}
~~~

The resource must also be deployed to a server or framework recognizing jakarta.ws.rs.* annotations. Changing imports alone does not guarantee routes get registered, JSON providers load, or exception mappers execute.

### 6.1. Client Libraries Must Also Align

If a legacy REST client library uses javax.ws.rs.client.Client while the application uses jakarta.ws.rs.client.Client, those are two different types. An API provider on the new namespace will not directly accept the old-namespace client type.

JAX-RS filters, exception mappers, and providers also require inspection because they implement interfaces from a specific namespace.

## 7. Non-Java-Source Locations Also Require Migration

An inventory checking only import lines often misses many integration points. Locations that can contain fully qualified class names or enterprise metadata:

- web.xml and web application descriptors.
- persistence.xml, orm.xml.
- CDI's beans.xml.
- faces-config.xml and JSF resources.
- validation.xml.
- JSP directives, tag files, tag libraries, and EL.
- META-INF/services for ServiceLoader.
- Class names in application.properties, YAML, XML, or database configuration.
- Reflection via Class.forName.
- Provider registrations and plugin manifests.
- Generated sources from annotation processors.
- Third-party dependency bytecode.
- Test scripts, mock/proxy configuration, and test utilities.
- Documentation, sample code, and shared SDKs for partners.
- Module descriptors and deployment configuration when using the module path.

### 7.1. web.xml

An older Java EE descriptor may declare a Java EE namespace:

~~~xml
<web-app xmlns="http://xmlns.jcp.org/xml/ns/javaee"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://xmlns.jcp.org/xml/ns/javaee
           http://xmlns.jcp.org/xml/ns/javaee/web-app_4_0.xsd"
         version="4.0">
</web-app>
~~~

A web.xml targeting Jakarta Servlet 6.0 may use the Jakarta namespace/schema:

~~~xml
<web-app xmlns="https://jakarta.ee/xml/ns/jakartaee"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           https://jakarta.ee/xml/ns/jakartaee
           https://jakarta.ee/xml/ns/jakartaee/web-app_6_0.xsd"
         version="6.0">
</web-app>
~~~

There is no universal "replace string javax with jakarta" rule for all XML namespaces. Schema URIs, root element names, versions, and descriptor contents must match the target specification and server. The example above illustrates Servlet 6.0; using Jakarta Servlet 5.0 requires the corresponding schema/version.

### 7.2. Persistence XML and CDI XML

Files like persistence.xml or beans.xml have their own versions/schemas. When upgrading to a specific Jakarta EE release, use the descriptor format supported by that persistence provider and CDI container.

Do not update annotation packages while leaving XML metadata untouched. Conversely, do not alter an ordinary Java SE XML config merely because a class attribute carries a javax prefix.

### 7.3. JSP, Taglibs, and EL

JSP and Expression Language also contain APIs that changed namespaces. Beyond Java imports, check:

- Page directive imports.
- Custom tag handler classes.
- Tag libraries and TLD files.
- Tag library URIs per the Jakarta Tags/JSTL version.
- EL resolvers, validators, converters, or custom expression functions.
- JSP/Tags/EL dependencies supplied by the container.

Legacy tag library URIs cannot be transformed with one universal rule across every version. Check the documentation for Jakarta Pages/Tags and the deployed server.

## 8. ServiceLoader, Providers, and String Class Names

A framework can discover providers automatically via META-INF/services.

Old resource example:

~~~text
META-INF/services/javax.servlet.ServletContainerInitializer
~~~

In a new Jakarta Servlet stack, the corresponding mechanism may need resource:

~~~text
META-INF/services/jakarta.servlet.ServletContainerInitializer
~~~

Do not just rename the file. The provider class must implement jakarta.servlet.ServletContainerInitializer and match its method descriptors.

### 8.1. Easy-to-Miss Places

~~~java
Class<?> type = Class.forName(
    "javax.servlet.http.HttpServletRequest");
~~~

This is a string literal, not an import. The compiler does not catch compatibility errors here when only imports elsewhere are edited.

Similarly, a configuration file may contain:

~~~properties
provider.interface=javax.ws.rs.ext.ExceptionMapper
~~~

Determine whether that string is a Java class name loaded by the framework; never blindly rewrite values that are plain text data or unrelated contract identifiers.

### 8.2. Third-Party Plugins Are a Compatibility Boundary

A plugin compiled against javax.* does not automatically become a jakarta.* plugin. When the framework upgrades extension interfaces, you need:

- A Jakarta-supporting release of the plugin.
- An explicit adapter or gateway, when genuinely feasible.
- Dual plugin releases during a transition window.
- Clear communication of API versions and Java baselines to plugin authors.

A plugin with source code may be simpler to migrate than a closed-source JAR. Either way, both must pass integration tests on the target namespace.

## 9. Dependencies and Artifact Names: Do Not Judge from groupId

The transition to Jakarta EE went through an artifact-renaming phase followed later by the Java namespace transition. Consequently, Maven coordinates starting with jakarta do not prove that classes inside use jakarta.*.

Distinguish clearly:

~~~text
Jakarta EE 8-era artifact:
  May belong to the Jakarta group or branding
  while classes still use javax.*

Jakarta EE 9+ API artifact:
  Enterprise APIs are moved to jakarta.*
~~~

Inspect the **API version**, **actual packages inside the JAR**, and **framework/server compatibility**.

### 9.1. Legacy Servlet Dependency Example

~~~xml
<dependency>
    <groupId>javax.servlet</groupId>
    <artifactId>javax.servlet-api</artifactId>
    <version>4.0.1</version>
    <scope>provided</scope>
</dependency>
~~~

When deploying on a Java EE 8 servlet container, the container may supply the Servlet API to the WAR. provided indicates the dependency is for compilation while runtime is typically supplied by the container.

### 9.2. Jakarta Servlet Dependency Example

~~~xml
<dependency>
    <groupId>jakarta.servlet</groupId>
    <artifactId>jakarta.servlet-api</artifactId>
    <version>6.0.0</version>
    <scope>provided</scope>
</dependency>
~~~

This example aligns conceptually with Jakarta Servlet 6.0. In practice, choose the exact API version matching your container and Java baseline. Do not copy the example's version number if the target server supports only Servlet 5.0 or runs a newer version.

### 9.3. Full Jakarta EE API in an Application Server

For a full Jakarta EE application, an aggregate API can be used for compilation:

~~~xml
<dependency>
    <groupId>jakarta.platform</groupId>
    <artifactId>jakarta.jakartaee-api</artifactId>
    <version>10.0.0</version>
    <scope>provided</scope>
</dependency>
~~~

The example uses Jakarta EE 10. If deployment targets Jakarta EE 9 or another release, pick the artifact matching the server level. Do not compile against a higher API release and deploy onto an older server without verification.

**provided is not suitable for every packaging style.** Executable JAR applications using embedded servers may need runtime dependencies managed by framework starters/BOMs instead of relying on an external container.

### 9.4. Gradle Equivalent

WAR example when the container provides the Servlet API:

~~~groovy
dependencies {
    compileOnly "jakarta.servlet:jakarta.servlet-api:6.0.0"
}
~~~

With the Gradle WAR plugin, provided-runtime configurations can be used depending on project structure. Crucially, do not bundle the wrong Servlet API version into the deployment package and do not rely on compileOnly to guarantee the container supplies the right version.

## 10. The Application Server Is a Decisive Factor

When using Servlet, JPA, CDI, Faces, or JMS, the application server/framework typically provides implementations. Each server generation supports specific specifications and namespaces.

Representative examples:

| Platform | Namespace Direction | Things to Confirm |
|---|---|---|
| Apache Tomcat 9 | javax.* Servlet API | Older-generation Java EE Servlet application |
| Apache Tomcat 10.0 | Jakarta Servlet 5.0, jakarta.* | WAR and dependencies must migrate namespaces |
| Apache Tomcat 10.1 | Jakarta Servlet 6.0, jakarta.* | Matching Java baseline and API level |
| Spring Framework 5.x / Spring Boot 2.x | Most enterprise integrations use javax.* | Older ecosystem libraries |
| Spring Framework 6.x / Spring Boot 3.x | Jakarta EE APIs use jakarta.* | Evaluate Java baseline and starter versions |
| Jakarta EE application servers | Per Jakarta EE version declared by server | Check platform profile, API versions, and implementations |

This table presents migration direction only and does not replace each patch/vendor compatibility matrix. In particular, a product may support Jakarta APIs at a specific level or require special configuration.

### 10.1. Tomcat 9 to Tomcat 10

A WAR using javax.servlet.* for Tomcat 9 cannot be assumed automatically compatible with Tomcat 10 simply because the WAR file uploads and deploys.

Needs upgrading:

- Servlet imports and annotations.
- Filters, listeners, and ServletContainerInitializer.
- web.xml and related descriptors.
- JSP/custom tag handlers if present.
- Libraries depending on javax.servlet.
- Frameworks used inside the WAR.
- Runtime/JDK as required by the target Tomcat.

Tomcat offers a Jakarta EE migration tool for certain scenarios, yet converted results still need testing. Never treat a bytecode transformation tool as a guarantee that all integrations or behaviors are fixed.

### 10.2. Spring Boot 2 to Spring Boot 3

This is a common example of namespace migration accompanying a platform upgrade: Spring Framework 6/Spring Boot 3 uses Jakarta APIs for EE integration points and requires the corresponding Java baseline (Spring Boot 3 requires Java 17 or newer).

Changes go beyond imports:

- Spring Security configuration and extension points may change APIs.
- The newer-generation Hibernate/JPA provider must use Jakarta Persistence.
- Validation annotations and runtime must align.
- Embedded servlet containers use the jakarta namespace.
- Third-party starters must be compatible with the new Boot generation.
- Test frameworks, mock servlet requests/responses, and filters use the matching namespace.

Consult the migration guide for the exact Spring Boot minor/major release rather than reducing the problem to search-and-replacing javax.*.

## 11. Can Mixed javax and jakarta Libraries Coexist?

In terms of class loading, one JVM can load both javax.foo.Bar and jakarta.foo.Bar because their names differ. However, **coexistence does not mean they can interoperate directly**.

Example:

~~~text
Library A:
  method filter(javax.servlet.ServletRequest)

Library B:
  object implements jakarta.servlet.ServletRequest
~~~

Library A will not automatically accept B's object. Trying to load both APIs just so the compiler stops reporting missing classes can trigger:

- NoClassDefFoundError at runtime if one side's package is missing.
- ClassCastException when an object is cast erroneously.
- NoSuchMethodError or linkage errors when descriptors mismatch.
- Annotations ignored by the framework.
- Providers not discovered by ServiceLoader.
- Duplicate/conflicting dependency implementations.

### 11.1. When Does an Adapter Boundary Make Sense?

If a legacy library performs a pure-data function, you can build an adapter passing **neutral data** such as DTOs or byte[] across the outside boundary:

~~~text
Jakarta web layer
       |
       v
Domain DTO / service interface independent of Servlet
       |
       v
Legacy library using its own API
~~~

This differs from writing a one-to-one adapter for an entire HttpServletRequest, AsyncContext, security context, or transaction lifecycle. Such container types carry complex semantics that cannot always be bridged across namespaces with a mechanical wrapper.

If a subsystem cannot be upgraded yet, splitting it out into a separate service communicating over HTTP/messaging/events can keep the older runtime isolated in the short term. The conversion boundary is then an external protocol, rather than pretending two Servlet APIs are interchangeable.

## 12. JDK Upgrade and Jakarta Migration Are Two Distinct Problems

A common error: upgrading Java 8 to Java 17, hitting ClassNotFoundException for javax.xml.bind.JAXBContext, and concluding all javax.* must become jakarta.*.

In reality, two different changes occurred:

1. **JDK 11 removed several Java EE/CORBA modules previously bundled with the JDK**, such as JAXB and JAX-WS, under JEP 320. Applications may need standalone dependencies to stay on the old namespace or upgrade libraries appropriately.
2. **Jakarta EE 9 moved EE API namespaces to jakarta.***. This is a source/binary contract change for the enterprise ecosystem.

These two changes can coincide yet do not share the same cause.

### 12.1. JAXB Example

Legacy application:

~~~java
import javax.xml.bind.JAXBContext;
~~~

When running on JDK 8, that API was provided by the JDK at one time. On JDK 11+, do not assume that module still exists in the default runtime.

If the application retains an older stack compatible with javax.xml.bind, you can add a compatible JAXB API/runtime in the same namespace supported on the target JDK.

If migrating to Jakarta XML Binding 3.x+:

~~~java
import jakarta.xml.bind.JAXBContext;
~~~

then both the API dependency and JAXB implementation must align. Merely putting a jakarta.xml.bind JAR on the classpath does not rewrite javax.xml.bind bytecode inside an older library.

### 12.2. Java SE Still Retains Many javax.* Packages After Upgrading the JDK

Example:

~~~java
import javax.sql.DataSource;
import javax.net.ssl.SSLContext;
import javax.xml.parsers.DocumentBuilderFactory;
~~~

These imports are common Java SE APIs and must not be changed to jakarta.*. Modern JDKs keeping them does not contradict Servlet/JPA moving namespaces.

## 13. Inventory Roadmap Before Changing Namespaces

First, catalog namespaces in source code and dependencies. Never edit code immediately based only on search hits.

### 13.1. Finding Imports in Source

Example with ripgrep:

~~~bash
rg -n "import[[:space:]]+(static[[:space:]]+)?javax[.]" src
~~~

Then classify each group:

- Belongs to Jakarta EE and must change?
- Belongs to Java SE and must stay?
- Belongs to an independent library not on the list?
- Generated source or hand-written code?
- Exposed in public APIs for third parties?

Search common EE APIs:

~~~bash
rg -n "javax[.](servlet|persistence|validation|ws[.]rs|enterprise|inject|ejb|jms|websocket|faces|el|mail|activation|xml[.]bind|xml[.]ws)" src
~~~

This command does not cover every EE API; it is a starting point. For Kotlin, Scala, Groovy, JSP, or generated sources, broaden the search appropriately.

### 13.2. Finding String Class Names and Configurations

~~~bash
rg -n "javax[.]" src/main/resources src/test pom.xml
~~~

Search across configurations, descriptors, and service registrations. If using modules or multi-module layouts, adjust paths accordingly.

Do not automatically replace every search hit. For example, javax.net.ssl and javax.xml.parsers are Java SE; a documentation URL or text string might not be a Java type name at all.

### 13.3. Inspecting the Dependency Graph

Maven:

~~~bash
./mvnw dependency:tree
~~~

You can filter by relevant groups using Maven Dependency Plugin options in your project version.

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

To trace an artifact:

~~~bash
./gradlew dependencyInsight --dependency servlet-api --configuration runtimeClasspath
~~~

Inspect compile, runtime, test, annotation processor, and application-server-provided dependencies. A dependency absent from source imports can still hold callbacks or providers using javax.*.

### 13.4. Inspecting Actual Classes Inside a JAR

~~~bash
jar tf some-library.jar
~~~

For example, check whether output shows:

~~~text
javax/servlet/Filter.class
~~~

or:

~~~text
jakarta/servlet/Filter.class
~~~

Or other classes referencing javax names in bytecode even without defining their own javax classes. Tools like jdeps, javap, or bytecode/API scanners help inspect static dependencies and method descriptors. String-based reflection may require separate source/resource searches.

## 14. Do Not Forget Tests and Generated Sources

After migration, a project often compiles main sources cleanly yet fails tests because mocks, extensions, or fixtures still use the old namespace.

Example:

~~~java
// Old-style test:
import javax.servlet.http.HttpServletRequest;
~~~

In a new Jakarta Servlet stack, tests must use:

~~~java
import jakarta.servlet.http.HttpServletRequest;
~~~

This also affects test libraries such as mock servlet APIs, Spring test integrations, and container runner plugins. A Mockito mock of javax.servlet.http.HttpServletRequest cannot be passed to a method expecting jakarta.servlet.http.HttpServletRequest.

### 14.1. Annotation Processors

An annotation processor or code generator may emit javax.persistence or javax.annotation.Generated imports in generated sources.

Determine:

- Does the generator target Jakarta APIs or Java EE APIs?
- Does the processor version support the target compiler JDK?
- Which package does generated code reside in?
- Is @Generated imported from javax.annotation.processing or Jakarta Common Annotations?
- Do generated classes expose javax APIs in public signatures?

If generated sources fail, prefer upgrading the generator/template or its configuration. Never manually patch files inside target/generated-sources and treat that as migration complete.

### 14.2. Pre-Packaged Third-Party Libraries

A binary-only JAR may still be compiled against javax.*. If no Jakarta-compatible release exists yet, decide whether to:

- Wait for or request vendor support.
- Replace the library.
- Use an evaluated bytecode transformation tool.
- Design an adapter or isolate the subsystem at a data boundary.
- Defer upgrading that module while clearly documenting the risk.

There is no safe rule claiming that adding both javax and jakarta API JARs makes an older library compatible with the new server.

## 15. How Far Can Namespace Conversion Tools Help?

Tools such as **Eclipse Transformer** or **Apache Tomcat Migration Tool for Jakarta EE** can convert some source/binary/resource artifacts based on matching rules.

However, a migration tool is not a compatibility verifier. Situations that may need manual handling:

- Dynamically constructed reflection and class names.
- XML schemas or resources with special semantics.
- Framework versions not supporting the new namespace.
- Public API changes beyond package names.
- Jakarta EE API level differing from the server target.
- Private/proprietary integrations.
- Un-upgraded annotation processors.
- Java agents, bytecode weaving, or native integrations.
- Libraries offering separate javax and jakarta APIs simultaneously.
- Serialized forms, stored class names, or plugin identifiers.

A tool may make class files link after conversion without guaranteeing transaction, lifecycle, serialization, or security behavior matches the old system.

### 15.1. Using a Transformer Within a Controlled Scope

If a transformer must be used:

1. Record the input artifact and checksum.
2. Specify the exact list of packages/rules transformed.
3. Run on a copy of the artifact rather than overwriting original vendor binaries.
4. Inspect output classes/resources.
5. Run integration tests against the target container.
6. Track tool issues and versions.
7. Keep a rollback path to source artifacts and prior configuration.

Prefer official Jakarta releases of dependencies once available; transformation is usually suitable as a time-bounded transition strategy.

## 16. Why Green Compilation Does Not Prove Migration Success

Code with updated imports and a passing Maven build can still fail when the container starts.

Runtime paths to test:

- Servlet mappings and filter chains.
- REST resource registration.
- CDI bean discovery and injection.
- @PostConstruct/@PreDestroy callbacks.
- Entity scanning and persistence units.
- Bean Validation on requests/entities.
- JMS producers/consumers and transactional boundaries.
- WebSocket endpoint registration.
- JSP/EL/custom tags.
- Security identities and sessions.
- Async processing and transaction context.
- Provider discovery via service descriptors.
- Deployment descriptor loading and schema validation.

Many bugs surface only when callbacks fire or real data flows through the framework. Therefore, **runtime integration tests** are mandatory for critical enterprise paths.

### 16.1. Common Error Messages and Investigation Directions

| Symptom | Common Likelihood |
|---|---|
| ClassNotFoundException: javax.servlet.* | Old dependency requires javax API while runtime only has jakarta |
| NoClassDefFoundError: jakarta.persistence.* | New source/library needs Jakarta Persistence while runtime lacks it |
| Not a managed type | Provider failed to recognize the matching entity annotation/mapping |
| Unsatisfied dependency | CDI/DI annotations or bean discovery use a mismatched namespace |
| Servlet class is not a Servlet | Implementation belongs to a different interface namespace than the container |
| NoSuchMethodError | Dependency binary descriptors do not match |
| ServiceConfigurationError | Service registration or provider interface has wrong namespace |
| HTTP 404 after deploy | Resource/servlet mapping was not registered by framework |
| Validation does not execute | Provider or annotations do not match Jakarta Validation |
| JSP compile failure | JSP/EL/taglib APIs/dependencies are misaligned |

This table points toward isolation paths, not sole diagnoses. Inspect stack traces, effective dependencies, and server logs in the target environment.

## 17. Layered Migration Strategy

A large application should be structured into layers with explicit contracts:

~~~text
Public API / Web
  Servlet, JAX-RS, Validation
          |
          v
Application services
  Use-case / transaction boundaries
          |
          v
Domain model
  Pure Java, minimal EE dependence
          |
          v
Infrastructure
  Persistence, Messaging, Mail, Security
~~~

If the domain layer does not depend on javax.servlet, javax.persistence, or jakarta equivalents, migration work is much easier to isolate.

### 17.1. Step 1 — Lock Down the Target Platform

Record:

- Minimum JDK runtime.
- Target Java EE/Jakarta EE API level.
- Application server/embedded server.
- Spring/Quarkus/Hibernate or framework versions.
- Deployment model: WAR/EAR/executable JAR.
- Dependency and plugin compatibility matrix.

Never change imports before knowing which namespace the target server requires.

### 17.2. Step 2 — Inventory javax by Origin

Divide into three groups:

**Group A — Jakarta EE APIs to change:** Servlet, JPA, Validation, JAX-RS, CDI, JMS, etc.

**Group B — Java SE javax to preserve:** SQL, SSL, crypto, JNDI, XML parsers, annotation processing, XA.

**Group C — Unclear:** packages of independent libraries or annotations with different origins; consult dependency documentation.

Every entry needs an owner and evidence. Never equate Group B with legacy code requiring removal.

### 17.3. Step 3 — Upgrade Compatible Dependencies and Server

Prefer moving to framework and library versions declared by vendors to support the Jakarta target. With Maven/Gradle, use appropriate BOMs/dependency management to avoid pulling old versions transitively.

### 17.4. Step 4 — Update Source Code and Config

Rename the EE packages that genuinely must migrate, including:

- Imports, generic signatures, and annotations.
- Servlet/JPA/validation/CDI integration.
- Descriptors and provider registrations.
- JSP and resource files.
- Reflection strings and generated code.
- Test fixtures and plugin interfaces.

### 17.5. Step 5 — Handle Legacy Dependencies

For each un-migrated dependency:

- Is a Jakarta-compatible version available?
- Can it be replaced with another library?
- Can it be isolated into a separate service?
- Is a transformation tool practical and permitted?
- If not yet portable, must that module be deferred or kept on a legacy branch?

### 17.6. Step 6 — Test on the Target Runtime

Run builds, deployments, smoke tests, integration tests, and business flows. When replacing persistence providers, test transactions and SQL mappings; when replacing servlet stacks, test filters/security/sessions/async; when replacing Validation, verify constraints actually enforce.

### 17.7. Step 7 — Staged Rollout

Prefer canary or production-like staging. Monitor error rates, startup, 404s, validation failures, persistence errors, and dependency/classloader issues. Have a rollback plan compatible with data and infrastructure.

## 18. Separating the Java SE Upgrade from the Jakarta Namespace Upgrade When Possible

Both changes can be rolled out in stages to make isolation easier:

~~~text
Phase A:
  Existing javax EE stack application
  Upgrade build tool and JDK within framework-supported range

Phase B:
  Upgrade framework/container to Jakarta-compatible
  Migrate EE packages javax -> jakarta
  Keep domain/APIs outside web layer as stable as possible

Phase C:
  Modernize Java code, upgrade libraries, and remove workarounds
~~~

Separation is not always possible; for instance, the target framework may enforce a higher Java baseline. When deployment separation is impossible, at least separate changes in commits and testing: dependencies/frameworks, namespaces, descriptors, business refactors. That makes root-cause analysis much easier.

### 18.1. Avoid Unnecessary Wire Contract Changes

Changing javax.persistence.Entity to jakarta.persistence.Entity does not automatically require changing:

- REST endpoint paths.
- JSON field names.
- Database tables or columns.
- Message topics.
- External partner contracts.

If JSON/DB/event contracts must remain stable, keep those contracts separate. Avoid mixing namespace migration with schema renames or business refactoring unless needed.

## 19. Warning Regarding the Java Module System

While upgrading to a modern JDK, a project may use the Java Platform Module System (JPMS). Never assume namespace migration equals module-name migration.

A Java package named jakarta.persistence does not guarantee every implementation's module descriptor has whatever name you guessed. Inspect the artifact's module metadata.

You can inspect:

~~~bash
jar --describe-module --file some-api.jar
~~~

and verify which modules actually resolve.

### 19.1. Reflection Must Be Evaluated Separately

Frameworks using reflection on entities/DTOs may require appropriate exports/opens when running on the module path.

Changing javax.persistence to jakarta.persistence does not solve InaccessibleObjectException. If the persistence provider needs private field access, the module holding the entity may need to open packages per JPMS mechanisms and the appropriate framework version.

### 19.2. Classpath Risks Still Remain

Even without module-info.java, the classpath can contain both libraries using javax EE and Jakarta frameworks. Classloaders do not automatically make differently namespaced types compatible.

## 20. Sample Module-by-Module Inventory Checklist

Suppose a repository contains:

~~~text
platform/
  common-domain/
  order-api/
  order-service/
  order-web/
  batch-importer/
  partner-plugin/
~~~

You can track via a table:

| Module | Which javax EE Used? | Action |
|---|---|---|
| common-domain | None; only Java SE | Keep unchanged, avoid changing Java SE javax imports |
| order-api | javax.validation annotations | Determine whether public DTOs need upgrading to Jakarta Validation |
| order-service | javax.transaction, javax.inject | Migrate per target framework/platform |
| order-web | javax.servlet and javax.ws.rs | Migrate Servlet/REST APIs and descriptors |
| batch-importer | javax.xml.bind | Upgrade JAXB API/runtime if switching to Jakarta XML Binding |
| partner-plugin | javax.servlet.Filter extension | Requires a Jakarta-compatible release or adapter strategy |

This table is illustrative. What matters is **building a dependency and consumer list for each module**. Modules exposing javax.* public interfaces may need new releases for partners.

## 21. How Can CI Detect Mixed Namespaces?

After listing enterprise APIs requiring migration, create rules catching old-namespace usage in sources or dependencies.

Example grep scoped to Jakarta EE:

~~~bash
rg -n "javax[.](servlet|persistence|validation|ws[.]rs|enterprise|inject|ejb|jms|websocket|faces|el)" src/main
~~~

However, **never** use a rule banning all javax.* because it produces false positives on javax.sql, javax.crypto, javax.net.ssl, javax.xml.parsers, javax.annotation.processing, or javax.transaction.xa.

With forbidden-API plugins, bytecode scanning, or custom lint rules, configure allowlists/denylists per specification. Projects with isolated legacy integrations can receive time-bounded exceptions.

### 21.1. Checking Both Binaries and Resources

Beyond imports:

- Inspect JARs for class references to javax EE.
- Check META-INF/services.
- Check XML descriptors.
- Check generated code.
- Check shaded/relocated artifacts.
- Check dynamically loaded plugins and Java agents.
- Check which APIs the deployment container supplies.

A green build with a javax.servlet.Filter JAR still on a Jakarta Servlet host's runtime path must be investigated before release.

### 21.2. Running Compatibility Tests on the Exact Stack

Meaningful tests:

1. Servlets register and return proper HTTP status codes.
2. Filter chains and listeners execute.
3. JAX-RS resource mappings work.
4. CDI injection and lifecycle callbacks run.
5. Validation rejects invalid payloads.
6. JPA provider scans entities and executes transactions.
7. JMS producers/consumers send and receive properly.
8. JSP/EL/taglibs compile and render.
9. Security policies work.
10. Third-party plugins load into the right Jakarta extension points.
11. No old-namespace dependencies remain at critical boundaries.
12. Rollbacks do not corrupt business data.

## 22. Common Misconceptions

### "Every javax.* must become jakarta.*"

False. Many javax.* packages belong to Java SE and must remain, such as javax.sql, javax.net.ssl, javax.crypto, javax.xml.parsers, and javax.annotation.processing.

### "Jakarta EE 8 already renamed the packages"

False. Jakarta EE 8 still uses the javax namespace in enterprise APIs. The major transition to jakarta occurred in Jakarta EE 9.

### "Artifacts with a jakarta groupId mean importing jakarta"

Not necessarily. Check the actual API version and class packages, especially for artifacts from the Jakarta EE 8 era.

### "Changing imports finishes the migration"

Incorrect. XML descriptors, service providers, reflection strings, generated sources, JSP, plugins, dependencies, and server compatibility remain.

### "Adding both javax.servlet-api and jakarta.servlet-api solves it"

Incorrect. That may let the compiler find both sets of classes, yet javax.servlet.Filter does not become jakarta.servlet.Filter.

### "Rename javax.sql.DataSource to jakarta.sql.DataSource"

False. javax.sql.DataSource belongs to Java SE and does not move with the Jakarta EE namespace migration.

### "JDK 11 losing javax.xml.bind means every javax.* must change"

False. JDK 11 removing some Java EE modules from the JDK is separate from the Jakarta EE 9 rename. Adding dependencies or upgrading the JAXB stack may be needed depending on architecture.

### "A transformer tool guarantees every old library runs on Jakarta"

Incorrect. Binary/resource rewriting only handles parts matching its rules. Lifecycles, API behavior, classloading, and framework compatibility still require integration tests.

### "The new namespace inherently requires changing REST URLs or database schemas"

Incorrect. Java packages and wire/schema business contracts are separate boundaries. Change them only for product reasons with a separate compatibility plan.

### "Successful compilation means the container will recognize beans/entities/filters"

Incorrect. The framework may scan annotations/interfaces from a different namespace. Errors may appear only at deployment time or on the first request.

## 23. Namespace Migration Record Template

~~~text
PROJECT / MODULE
  Service or artifact:
  Current JDK:
  Target JDK:
  Current Java EE/Jakarta EE level:
  Target Jakarta EE level:
  Current server/framework:
  Target server/framework:
  Deployment format:

API INVENTORY
  javax EE packages requiring change:
  Java SE javax packages to preserve:
  Ambiguous third-party javax packages:
  Public APIs exposing javax types:
  Generated source:
  Reflection/class-name strings:

DEPENDENCIES
  API dependencies:
  Implementations:
  Container-provided APIs:
  Starters/BOM:
  Third-party plugins:
  Legacy libraries without Jakarta release:

RESOURCES
  web.xml:
  persistence.xml / orm.xml:
  beans.xml / faces-config.xml:
  JSP / taglib / EL:
  META-INF/services:
  App config and provider manifests:

MIGRATION DECISION
  Direct source migration:
  Supported dependency upgrade:
  Binary transformer required?:
  Adapter or process boundary:
  Exception and expiry:
  Owner:

VALIDATION
  Dependency and bytecode scan:
  Build and package:
  Server startup:
  Servlet/REST smoke test:
  Persistence/transaction test:
  Validation and DI tests:
  Messaging and plugin tests:
  Negative/security tests:
  Canary and rollback:
~~~

The record must state exact **API levels and server versions**, not merely "migrated to Jakarta". Two applications both using jakarta.* yet on different Servlet/Persistence versions can still be incompatible.

## 24. End-to-End Implementation Workflow

### Step 1 — Select Target and Gather Evidence

Identify a Jakarta-compatible application server/framework, minimum JDK, API levels, and vendor-supported dependencies. If a critical library still depends on javax EE, identify it before editing sources.

### Step 2 — Classify javax.*

Mark as:

- **MIGRATE:** Jakarta EE APIs whose namespaces moved.
- **KEEP:** Java SE APIs or independent APIs outside the transition.
- **INVESTIGATE:** unclear origin or no Jakarta-compatible release yet.

Never run replace-all across the entire repository.

### Step 3 — Upgrade Dependencies and Container

Update API/implementation versions to target. Remove or upgrade transitive dependencies using old namespaces at enterprise boundaries. Distinguish server-provided APIs from runtime dependencies in executable JARs.

### Step 4 — Update Source and Resources

Selectively update import/class references; update annotations, XML descriptors, service metadata, JSP/taglibs, generated code, and test sources.

### Step 5 — Compile and Hunt Remaining javax EE Usage

Run a clean build with the target JDK and inspect errors and the dependency graph. Use bytecode/resource scanning to locate legacy class names missed by source grep.

### Step 6 — Runtime and Plugin Testing

Deploy to the exact target server. Test HTTP flows, filters, DI, JPA, Validation, JMS, Security, and third-party SPIs/plugins. Tests must run through the real container/framework.

### Step 7 — Canary and Observation

Monitor startup, bean/entity scanning exceptions, HTTP 404/500s, deserialization, database transactions, and plugin loading. Never shift full traffic before solid runtime evidence.

### Step 8 — Trim Temporary Compatibility Shims

Remove temporary transformers/adapters once official dependencies support Jakarta. Remove obsolete old-namespace JARs, except Java SE components that must stay.

## 25. Summary

The scope of the javax-to-jakarta namespace change is an **enterprise API contract change** with clear boundaries:

1. **Jakarta EE 8 still uses javax.*; Jakarta EE 9+ moves enterprise APIs to jakarta.*.**
2. **Do not change all javax.*** Many Java SE packages such as javax.sql, javax.net.ssl, javax.xml.parsers, and javax.transaction.xa stay unchanged.
3. **Changing packages changes type identity.** javax and jakarta interfaces/classes are not binary-compatible just because their simple names match.
4. **Dependencies and containers must align.** Jakarta sources must be paired with matching frameworks, API providers, and servers.
5. **Locations outside imports matter too.** XML descriptors, service providers, JSP, reflection strings, generated code, plugin artifacts, and test sources may all need migration.
6. **Never use replace-all as the primary strategy.** Classify each package by specification origin and support level.
7. **Test runtime thoroughly.** Passing compilation does not prove entities, filters, CDI beans, REST resources, or plugins register properly.
8. **Keep business contracts separate.** Never change REST URLs, JSON schemas, or databases solely due to a Java package rename.

A successful migration is not a repository containing zero instances of the word javax. Success is when all enterprise APIs use the exact namespace supported by the target platform, Java SE APIs remain untouched, dependencies and server belong to the same generation, and real execution paths operate stably on the new JDK.
