# Updating imports, annotations, XML descriptors, and class names in configuration

When migrating an application from **Java EE** to **Jakarta EE**, one change can look deceptively simple: replacing `javax.servlet.http.HttpServlet` with `jakarta.servlet.http.HttpServlet`, or changing `javax.persistence.Entity` to `jakarta.persistence.Entity`. However, a real-world project rarely consists only of directly visible Java code. Framework class names can live in `web.xml`, `persistence.xml`, Spring metadata, `META-INF/services`, environment variables, YAML configurations, databases, or template-generated code. If you only change `import` statements and stop there, the application server or framework may fail to start, fail to discover providers, miss annotations, or ignore deployment configuration.

This lesson belongs to the **Java EE and Jakarta** chapter of the **Java Advance Compatibility Migration** module. Its goal is establishing a controlled migration workflow across **four interrelated layers of information**:

1. **Source imports and fully qualified type names** in Java/Kotlin/Groovy and generated code.
2. **Annotations and contracts**: annotation classes sharing the same simple name yet belonging to two separate package hierarchies.
3. **XML descriptors**: namespaces, schema locations, versions, and class-name contents.
4. **Runtime configuration and service metadata**: strings used to load classes, providers, filters, listeners, persistence, and dependency injection.

Important rule: never replace every string starting with `javax.` with `jakarta.`. Many `javax.*` packages belong to **Java SE**, remain unchanged, and fall outside Jakarta EE namespace migration.

## 1. Distinguishing JDK upgrades from Jakarta EE upgrades

### 1.1. Java SE, Java EE, and Jakarta EE are not on the same version line

**Java SE** provides the Java language, JVM, and foundational APIs. **Java EE** was the enterprise technology platform built on specifications such as Servlet, JPA, CDI, Bean Validation, and JAX-RS. Those enterprise specifications continued evolving under the **Jakarta EE** name.

These two migrations are often related yet must be analyzed separately:

- **JDK upgrade**: e.g., Java 8 → Java 11 or Java 17, impacting runtime behavior, module system, removed APIs, compiler, and libraries.
- **Enterprise API namespace change**: e.g., Servlet/JPA from `javax.*` to `jakarta.*`, impacting source code, binary interfaces, descriptors, and runtime containers.

An application can run on a newer JDK with some libraries still using `javax.*` if the chosen stack supports it. Conversely, switching all sources to `jakarta.*` does not make an application run if the application server or framework still expects `javax.*` APIs.

### 1.2. Jakarta EE 8 differs from Jakarta EE 9

This is the most common source of confusion:

| Platform generation | Primary enterprise namespace | Migration consequence |
| --- | --- | --- |
| Java EE 8 | `javax.*` | Enterprise APIs carry the legacy namespace. |
| Jakarta EE 8 | Still `javax.*` | The brand changed without a wholesale move of packages to `jakarta.*`. |
| Jakarta EE 9 / 9.1 | Many enterprise APIs moved to `jakarta.*` | Major namespace transition milestone for Servlet, Persistence, CDI, Validation, etc. |
| Jakarta EE 10 and later | `jakarta.*` with spec-specific API additions/changes | Beyond namespace changes, check behavioral, API, and Java baseline differences. |

**Do not treat the word "Jakarta" in a dependency name as proof that its packages changed.** For example, an artifact with groupId `jakarta.*` may still ship `javax.*` classes in an older version. Always verify **actual JAR contents, artifact versions, and the APIs provided by the framework/container**.

### 1.3. Binary compatibility breaks when packages change

At the JVM level, the package name is part of the type name and method descriptor:

~~~text
Before:
  javax.servlet.http.HttpServletRequest

After:
  jakarta.servlet.http.HttpServletRequest
~~~

These are **two distinct types**, not aliases. For example, the method:

~~~java
void handle(javax.servlet.http.HttpServletRequest request);
~~~

has a different descriptor from:

~~~java
void handle(jakarta.servlet.http.HttpServletRequest request);
~~~

Therefore, a library compiled against `javax.servlet.*` does not become compatible with a servlet container providing `jakarta.servlet.*` simply because the simple class name remains `HttpServletRequest`. You may need a newer library release, recompilation, or a deliberately designed adapter.

## 2. Mapping conversions before editing source

Do not run "Replace All" across the whole repository right away. First classify every namespace present.

### 2.1. Common enterprise API mappings

| API / specification | Old name | Common new name | Notes |
| --- | --- | --- | --- |
| Servlet | `javax.servlet.*` | `jakarta.servlet.*` | Includes servlets, filters, listeners, and HTTP APIs. |
| JavaServer Pages / Jakarta Server Pages | `javax.servlet.jsp.*` | `jakarta.servlet.jsp.*` | Check JSP engine and compatible JSTL/taglibs. |
| JPA / Jakarta Persistence | `javax.persistence.*` | `jakarta.persistence.*` | Update entity annotations, interfaces, XML, and provider. |
| Bean Validation | `javax.validation.*` | `jakarta.validation.*` | E.g., `@Valid`, `@NotNull`, `Validator`. |
| CDI | `javax.enterprise.*` | `jakarta.enterprise.*` | Contexts, scopes, events, interceptor bindings. |
| Injection | `javax.inject.*` | `jakarta.inject.*` | E.g., `@Inject`, `@Named`, `Provider`. |
| Common annotations | `javax.annotation.*` | `jakarta.annotation.*` | E.g., `@PostConstruct`, `@PreDestroy`; does not apply to all Java SE annotation packages. |
| JAX-RS / REST | `javax.ws.rs.*` | `jakarta.ws.rs.*` | `@Path`, `@GET`, `Response`, filters/providers. |
| JAX-WS | `javax.xml.ws.*` | `jakarta.xml.ws.*` | Watch source generation and SOAP tooling. |
| JAXB / XML Binding | `javax.xml.bind.*` | `jakarta.xml.bind.*` | Annotations, runtime, XJC/generated classes. |
| JSON-B | `javax.json.bind.*` | `jakarta.json.bind.*` | Requires a compatible JSON-B implementation. |
| JSON-P | `javax.json.*` | `jakarta.json.*` | Do not confuse with third-party JSON libraries. |
| Jakarta Messaging (JMS) | `javax.jms.*` | `jakarta.jms.*` | Client, broker adapter, and JMS provider. |
| Mail | `javax.mail.*` | `jakarta.mail.*` | Check Jakarta Activation as well. |
| Activation | `javax.activation.*` | `jakarta.activation.*` | Verify runtime/provider. |
| Jakarta Transactions | `javax.transaction.*` | `jakarta.transaction.*` | Watch the `javax.transaction.xa.*` exception, which is Java SE API. |
| Expression Language | `javax.el.*` | `jakarta.el.*` | Affects JSP/JSF/validation integration. |
| Faces (JSF) | `javax.faces.*` | `jakarta.faces.*` | Includes annotations, taglibs, faces-config. |
| EJB / Enterprise Beans | `javax.ejb.*` | `jakarta.ejb.*` | Check container and deployment descriptors. |
| WebSocket | `javax.websocket.*` | `jakarta.websocket.*` | Client/server endpoints and annotations. |
| Security enterprise | `javax.security.enterprise.*` | `jakarta.security.enterprise.*` | Distinct from Java SE security packages. |
| Servlet authentication | `javax.security.auth.message.*` | `jakarta.security.auth.message.*` | Verify runtime/container support. |

This table is a directional map; **actual scope must follow your chosen specification versions and dependencies**. No single transform validly applies to all `javax` packages.

### 2.2. `javax.*` packages that must not be renamed mechanically

Several packages remain Java SE APIs, such as:

~~~java
import javax.crypto.Cipher;
import javax.net.ssl.SSLContext;
import javax.sql.DataSource;
import javax.naming.InitialContext;
import javax.management.MBeanServer;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.transform.Transformer;
import javax.xml.namespace.QName;
import javax.annotation.processing.Generated;
~~~

Those packages **do not become `jakarta.crypto`, `jakarta.sql`, or `jakarta.xml.parsers`**. Blind renaming produces non-existent imports and breaks compilation.

In particular:

- `javax.sql.DataSource` remains a Java SE interface even when used via JPA or Jakarta Transactions.
- `javax.naming.InitialContext` is still commonly used for JNDI lookups.
- `javax.transaction.xa.XAResource` belongs to Java SE; do not assume it changes alongside `javax.transaction.UserTransaction`.
- `javax.xml.*` contains both Java SE XML APIs and split-out enterprise APIs; check each subpackage individually.
- `javax.annotation.processing.Generated` from the compiler differs from enterprise lifecycle annotations like `jakarta.annotation.PostConstruct`.

**Principle:** before renaming, verify the groupId/artifact, owning class, module, and Java baseline for that API.

## 3. Inventorying old namespace usage

### 3.1. Do not search only `import` statements

A repository may contain `javax.servlet` references in:

- Java/Kotlin/Groovy source files.
- Java annotations in application and test code.
- Generated sources produced by OpenAPI, JAXB, JPA metamodels, or frameworks.
- `web.xml`, `persistence.xml`, `beans.xml`, `orm.xml`, `faces-config.xml`, `validation.xml`.
- `application.properties`, `application.yml`, Spring XML.
- `META-INF/services/*`.
- Manifests or framework resource metadata.
- Build files, plugin configs, and code-generation templates.
- `Class.forName(...)` string literals.
- Databases, parameter stores, environment variables, or external config servers.
- Serialized payloads or persisted type-name metadata spanning releases.

Therefore, the audit criterion is **every location storing contract type names or XML namespaces**, not merely the count of edited `.java` files.

### 3.2. Suggested repository search commands

Search legacy enterprise namespaces:

~~~bash
rg -n 'javax\.(servlet|persistence|validation|enterprise|inject|annotation|ws\.rs|xml\.bind|xml\.ws|jms|mail|activation|faces|ejb|websocket)' .
~~~

Search legacy XML schemas and namespaces:

~~~bash
rg -n 'java\.sun\.com/xml/ns/javaee|xmlns\.jcp\.org/xml/ns/javaee|xmlns\.jcp\.org/xml/ns/persistence|web-app_[0-9]|persistence_[0-9]|beans_[0-9]' .
~~~

Search dynamic loading and provider mechanisms:

~~~bash
rg -n 'Class\.forName|loadClass|ServiceLoader|PersistenceProvider|provider\.class|listener-class|filter-class|servlet-class' .
~~~

Locate metadata files and directories:

~~~bash
rg --files | rg '(web\.xml|persistence\.xml|orm\.xml|beans\.xml|faces-config\.xml|validation\.xml|META-INF/services|spring\.factories|application\.(yml|yaml|properties))'
~~~

These commands are **starting points**; they cannot find everything inside binary JARs, external config stores, or container-provided libraries.

### 3.3. Pre-edit inventory table

| Component | Location | Current API/namespace | Intended target | Owner | Risk |
| --- | --- | --- | --- | --- | --- |
| Servlet | `src/main/java` | `javax.servlet` | `jakarta.servlet` | Web team | Container compatibility. |
| JPA | Entities + `persistence.xml` | `javax.persistence` | `jakarta.persistence` | Data team | Provider, ORM schema. |
| CDI | Source + `beans.xml` | `javax.enterprise` | `jakarta.enterprise` | Backend | Discovery/interceptors. |
| REST | Source + config | `javax.ws.rs` | `jakarta.ws.rs` | API team | Servlet/JAX-RS runtime. |
| SPI | `META-INF/services` | Old interface/provider names | Accurate names per new API | Platform | Provider not found. |
| External config | Config server/DB | Active FQCNs | Actual runtime class names | Operations | Version-skewed deployments. |

For every change, record dependency and runtime target evidence. Avoid writing a mapping purely from package names without knowing which team owns each component.

## 4. Selectively updating Java imports

### 4.1. Servlet: before and after example

**Before – Java EE / Jakarta EE 8:**

~~~java
package com.example.web;

import java.io.IOException;
import javax.servlet.ServletException;
import javax.servlet.annotation.WebServlet;
import javax.servlet.http.HttpServlet;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

@WebServlet("/health")
public class HealthServlet extends HttpServlet {
    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response)
            throws ServletException, IOException {
        response.getWriter().write("OK");
    }
}
~~~

**After – Jakarta Servlet namespace:**

~~~java
package com.example.web;

import java.io.IOException;
import jakarta.servlet.ServletException;
import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

@WebServlet("/health")
public class HealthServlet extends HttpServlet {
    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response)
            throws ServletException, IOException {
        response.getWriter().write("OK");
    }
}
~~~

Here `java.io.IOException` **stays unchanged**; the application package `com.example.web` does not need to change either. What must change are the imports and binary types provided by the Servlet API. After updating, deploy onto a matching Jakarta Servlet container.

### 4.2. REST/JAX-RS

Before:

~~~java
import javax.ws.rs.GET;
import javax.ws.rs.Path;
import javax.ws.rs.core.Response;
~~~

After:

~~~java
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.core.Response;
~~~

Example:

~~~java
@Path("/status")
public class StatusResource {
    @GET
    public Response status() {
        return Response.ok("ready").build();
    }
}
~~~

Source code may look identical aside from imports, yet the JAX-RS runtime implementation, servlet integration, and provider metadata must belong to the **same Jakarta generation**. A `javax.ws.rs.ext.MessageBodyReader` cannot automatically register as a `jakarta.ws.rs.ext.MessageBodyReader`.

### 4.3. JPA and Bean Validation

Before:

~~~java
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.validation.constraints.NotNull;
~~~

After:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.validation.constraints.NotNull;
~~~

Example:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.validation.constraints.NotNull;

@Entity
public class Customer {
    @Id
    private Long id;

    @NotNull
    private String name;
}
~~~

When converting, align entity annotations with the JPA provider and Bean Validation provider versions. Having `jakarta.persistence-api` alone without an appropriate implementation will not let the application build an `EntityManagerFactory`.

### 4.4. Generated sources and regenerating code

A project may generate code on every build, such as:

- JAXB from XSD/WSDL.
- JAX-WS SOAP clients.
- JPA static metamodels.
- OpenAPI servers/clients.
- Annotation processing and framework codegen.
- Source templates from internal scaffolding.

If generated files still carry `javax.xml.bind.annotation.XmlElement`, do not hand-edit them only for the next build to overwrite them. Update the **generator/plugin version, templates, and runtime APIs**, then regenerate source in the Jakarta namespace.

With some generators, the generated code namespace depends not only on the JDK, but also on plugin versions and supported generator flags. Record generated API outputs as part of migration evidence.

## 5. Annotations: changing types does not mean keeping the entire contract intact

### 5.1. Annotations sharing a simple name yet differing in runtime type

Example:

~~~java
@javax.persistence.Entity
~~~

and:

~~~java
@jakarta.persistence.Entity
~~~

are **two different annotation types**. Frameworks scanning annotations by class type may recognize only the type matching their implementation.

If an entity retains the old annotation while a newer JPA provider scans only Jakarta Persistence annotations, that entity may go unrecognized. The consequence is not necessarily a compile error; it can surface at startup as a mapping error or when accessing repositories.

### 5.2. CDI and injection

Before:

~~~java
import javax.enterprise.context.ApplicationScoped;
import javax.inject.Inject;
~~~

After:

~~~java
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
~~~

Example:

~~~java
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;

@ApplicationScoped
public class OrderService {
    @Inject
    OrderRepository repository;
}
~~~

Source alone is not enough: the CDI container, extensions, interceptors, and bean discovery configs must also be compatible. An older CDI extension implementing `javax.enterprise.inject.spi.Extension` does not automatically work on a runtime expecting `jakarta.enterprise.inject.spi.Extension`.

### 5.3. Lifecycle annotations

Common annotations:

~~~java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;

public class StartupBean {
    @PostConstruct
    void initialize() {
        // Initialize resources.
    }

    @PreDestroy
    void shutdown() {
        // Release resources.
    }
}
~~~

After changing imports, verify the container actually manages the object's lifecycle. Placing `@PostConstruct` on an instance created directly with `new` does not make the framework invoke that method.

### 5.4. `@Resource`, `@PersistenceContext`, and JNDI names

Example:

~~~java
import jakarta.annotation.Resource;
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.EntityManager;

public class OrderRepository {
    @PersistenceContext(unitName = "ordersPU")
    private EntityManager em;

    @Resource(lookup = "java:comp/env/jdbc/Orders")
    private javax.sql.DataSource dataSource;
}
~~~

Here `@Resource` and `@PersistenceContext` belong to Jakarta enterprise APIs, while `DataSource` remains Java SE's `javax.sql.DataSource`. The JNDI name `java:comp/env/jdbc/Orders` is a **configuration resource name**, not a Java package, so it must never be changed to `jakarta:...` via find-and-replace.

### 5.5. Annotations in tests and framework integrations

Audit:

- Test fixtures using legacy `@RunWith`, extensions, or annotation providers.
- Custom validation annotations implementing the old `ConstraintValidator`.
- Interceptor annotations provided by legacy CDI.
- JAXB annotations on DTOs serialized by frameworks.
- Auto-configuration or annotation processing relying on framework metadata.

Sometimes annotations share identical names and similar attributes while their owning modules and consuming service providers changed. Passing compilation does not prove injection, validation, or lifecycle hooks run properly.

## 6. XML descriptors: namespaces, XSDs, versions, and contents must all change

XML descriptors generally contain **three distinct layers**:

1. **XML element/attribute names** per schema.
2. **Namespace URI, schema location, and version**.
3. **Values containing class names, provider names, resource names, or config identifiers**.

Replacing only `javax.` in XML is not enough. XML namespaces are not Java packages, and XSD versions must match your target Jakarta specification.

### 6.1. `web.xml` before migration example

Web descriptor from the legacy Java EE generation:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<web-app xmlns="http://xmlns.jcp.org/xml/ns/javaee"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://xmlns.jcp.org/xml/ns/javaee
           http://xmlns.jcp.org/xml/ns/javaee/web-app_4_0.xsd"
         version="4.0">

    <filter>
        <filter-name>traceFilter</filter-name>
        <filter-class>com.example.web.TraceFilter</filter-class>
    </filter>

    <filter-mapping>
        <filter-name>traceFilter</filter-name>
        <url-pattern>/*</url-pattern>
    </filter-mapping>
</web-app>
~~~

The `filter-class` value names an **application class**. If the application's package does not change, it can remain unchanged after migration, although that class itself must implement `jakarta.servlet.Filter`.

### 6.2. `web.xml` for Jakarta Servlet 6.0 example

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<web-app xmlns="https://jakarta.ee/xml/ns/jakartaee"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           https://jakarta.ee/xml/ns/jakartaee
           https://jakarta.ee/xml/ns/jakartaee/web-app_6_0.xsd"
         version="6.0">

    <filter>
        <filter-name>traceFilter</filter-name>
        <filter-class>com.example.web.TraceFilter</filter-class>
    </filter>

    <filter-mapping>
        <filter-name>traceFilter</filter-name>
        <url-pattern>/*</url-pattern>
    </filter-mapping>
</web-app>
~~~

This example fits **Jakarta Servlet 6.0**. If the target runtime is Jakarta Servlet 5.0, use the matching descriptor version/schema rather than copying `version="6.0"` simply because namespaces changed.

Points to remember:

- Update the namespace URI to the Jakarta namespace for the corresponding specification.
- Update `xsi:schemaLocation` to the exact XSD URL.
- Update `version` to match the Servlet version supported by your container.
- Check whether elements/attributes changed across spec versions.
- Keep `com.example.web.TraceFilter` if the application class keeps its FQCN.
- Check `servlet-class`, `listener-class`, `filter-class`, error pages, and other class entries.

### 6.3. Annotations and `web.xml` must stay consistent

If a filter is declared in XML, the actual class must implement `jakarta.servlet.Filter` when deployed to a Jakarta Servlet container. If only `web.xml` changed while the class still implements `javax.servlet.Filter`, the runtime may reject it as an invalid filter type.

Conversely, if the container enables annotation scanning, confirm `@jakarta.servlet.annotation.WebFilter` and actual discovery configs are processed. Applications may use annotations, descriptors, or both; inspect precedence and effect under the target container/spec.

## 7. `persistence.xml` and `orm.xml`: JPA is more than entity imports

### 7.1. Legacy Persistence descriptor

Java Persistence 2.2 example:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
  xmlns="http://xmlns.jcp.org/xml/ns/persistence"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="
    http://xmlns.jcp.org/xml/ns/persistence
    http://xmlns.jcp.org/xml/ns/persistence/persistence_2_2.xsd"
  version="2.2">

    <persistence-unit name="ordersPU">
        <provider>org.example.jpa.LegacyProvider</provider>
        <class>com.example.model.Customer</class>
    </persistence-unit>
</persistence>
~~~

The name `org.example.jpa.LegacyProvider` illustrates a provider class supplied by a specific runtime. When upgrading to Jakarta, determine this class from the **actual provider implementation and version**, never a guessed name.

### 7.2. Jakarta Persistence 3.0 descriptor

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

    <persistence-unit name="ordersPU">
        <class>com.example.model.Customer</class>
        <properties>
            <property name="jakarta.persistence.schema-generation.database.action"
                      value="none"/>
        </properties>
    </persistence-unit>
</persistence>
~~~

For newer Persistence versions, pick the matching XSD and version. The example omits `<provider>` to avoid tying readers to an assumed implementation; the container/runtime must supply a Jakarta Persistence-compatible provider.

Items to review:

- Does the `ordersPU` unit name stay intact per contract?
- Does `<class>` contain an app FQCN whose package changed?
- Does `<mapping-file>` point to the updated `orm.xml`?
- Did standard property prefixes change from `javax.persistence.*` to `jakarta.persistence.*`?
- Do vendor-specific properties keep their names/behavior in the new provider version?
- Must the JDBC datasource JNDI name and `javax.sql.DataSource` stay unchanged?
- Which Jakarta Persistence version does the provider target?

Never enable `schema-generation.database.action=drop-and-create` during production migration. Namespace changes and database schema changes must be controlled independently.

### 7.3. `orm.xml` and mapping metadata

Beyond annotations, Hibernate/EclipseLink or JPA providers can use XML mappings. A class without annotations can still be mapped as an entity in `orm.xml`.

Therefore, audit for:

- XML namespace and XSD version of mapping files.
- Entity/embeddable/converter/listener FQCNs inside XML.
- Provider-matching property names or types.
- Packages targeted by the mapping file.
- Whether converters or callback classes still reference legacy Java namespaces.

A migration that updates `@Entity` while overlooking `orm.xml` can partially start and fail on another entity during persistence unit initialization.

### 7.4. JPA properties in application configuration

Standard JDBC keys in persistence config can shift as follows:

~~~properties
# Jakarta Persistence generation
jakarta.persistence.jdbc.url=jdbc:postgresql://localhost:5432/orders
jakarta.persistence.jdbc.user=app_user
jakarta.persistence.jdbc.password=example-placeholder
~~~

In practice, never commit real credentials in example files or version control; use a secret manager or environment variables.

Crucially, not every key containing `javax.persistence` or `hibernate` follows the same rename rule. Standard specification keys and provider/framework-specific configuration keys must be checked individually.

## 8. `beans.xml`, CDI, Validation, and Faces descriptors

### 8.1. CDI: `beans.xml`

In Jakarta CDI, `beans.xml` can carry the new namespace and version alongside bean discovery and interceptor configs.

CDI 4.0 illustrative example:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="https://jakarta.ee/xml/ns/jakartaee"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
         https://jakarta.ee/xml/ns/jakartaee
         https://jakarta.ee/xml/ns/jakartaee/beans_4_0.xsd"
       bean-discovery-mode="annotated"
       version="4.0">
</beans>
~~~

More than the schema changes: **bean discovery rules can differ across CDI versions**. With `bean-discovery-mode="annotated"`, beans lacking qualifying bean-defining annotations may no longer be discovered. Migration must verify actual dependency injection at runtime.

### 8.2. Bean Validation: `validation.xml`

Frameworks may read `META-INF/validation.xml` to configure message interpolators, validator factories, constraint mappings, and providers. When upgrading to Jakarta Validation, verify:

- Namespace and schema for the target Validation version.
- Class names for `ConstraintValidatorFactory`, `MessageInterpolator`, and provider.
- External XML constraint mapping files beyond annotations.
- Whether custom constraints still implement `javax.validation.ConstraintValidator` or moved to `jakarta.validation.ConstraintValidator`.
- Whether the runtime provider version supports the new namespace.

Do not change only `@NotNull`; unmigrated custom validators and XML mappings can break validation bootstrap.

### 8.3. Jakarta Faces: `faces-config.xml` and tag libraries

When an application uses JSF/Jakarta Faces, migration scope can cover:

- Imports `javax.faces.*` → `jakarta.faces.*`.
- `faces-config.xml` namespace/XSD/version.
- Managed beans, converters, validators, and phase listeners in XML.
- Expression Language and `javax.el.*` → `jakarta.el.*` dependencies for the matching generation.
- Facelets taglib URIs or framework tag libraries.
- Component libraries (e.g., UI widgets) compatible with the target Jakarta Faces version.

An XHTML file might not mention `javax.` yet still use legacy taglib URIs or UI-library namespaces. Replace those URIs strictly per **library documentation and target specifications**, rather than blindly rewriting every `java.sun.com` or `xmlns.jcp.org` across arbitrary HTML/XML documents.

## 9. Class names in XML and application configuration

### 9.1. Distinguishing app class names from framework API names

Suppose `web.xml` contains:

~~~xml
<servlet-class>com.example.web.CustomerServlet</servlet-class>
~~~

If you only changed `CustomerServlet`'s imports from `javax.servlet` to `jakarta.servlet` while keeping the `com.example.web` package, **this value does not change**.

Conversely, if the descriptor specifies a library implementation class whose package changed:

~~~xml
<listener-class>com.vendor.legacy.LegacyListener</listener-class>
~~~

determine the **actual replacement class** shipped by the Jakarta library release. There is no universal rule turning every `com.vendor.legacy` name into one containing `jakarta`.

### 9.2. Spring or other framework configuration

Configurations may hold FQCNs:

~~~yaml
application:
  converter-class: com.example.legacy.LegacyConverter
  security-filter-class: com.vendor.security.LegacyFilter
~~~

If Java sources or dependencies renamed classes, update these values accordingly. However, many framework properties such as `spring.jpa.*`, `server.servlet.*`, or application-defined keys **must not have their prefixes renamed merely because of Jakarta EE**.

Always check the framework version contract:

- Is the property name still valid?
- Is the value a class name, bean name, resource path, or business identifier?
- Which package does the new class belong to?
- Does the framework provide dedicated binding/configuration mechanisms or adapters?
- Under which profile is this configuration read?

### 9.3. Reflection via `Class.forName` or `loadClass`

Example:

~~~java
String name = config.getProperty("handler.class");
Class<?> handlerType = Class.forName(name);
~~~

If `handler.class` resides in a file outside the JAR or in a database, source-refactoring tools cannot update it automatically. Runtime execution can throw `ClassNotFoundException`.

When investigating, record:

1. Actual config value in the failing environment.
2. Whether that class name exists inside the new version's JARs.
3. Which class loader/module layer is loading it.
4. Expected constructors and interfaces required by the framework.
5. Whether any `javax.*` dependency remains inside the new class's signatures.

Sometimes the name is right yet the class implements the legacy interface, turning `ClassNotFoundException` into `ClassCastException`.

### 9.4. Namespace changes in long-lived stored data

Class names may be persisted inside JSON polymorphic type metadata, caches, or serialized payloads. Example:

~~~json
{
  "type": "javax.example.LegacyHandler",
  "payload": {}
}
~~~

This merely illustrates a string-stored type name rather than a standard Jakarta API mapping. If legacy payloads rely on FQCNs to look up decoders, updating code can render historical data unreadable.

Solutions include **allowlisted aliases**, stable DTO schemas, or backed-up data migrations. Never enable arbitrary class loading from untrusted input just to stay backward-compatible with old names.

## 10. `META-INF/services` and provider metadata

### 10.1. How Java ServiceLoader finds providers

Libraries can register providers using files at:

~~~text
META-INF/services/<fully-qualified-service-interface>
~~~

whose content lists implementation classes, for example:

~~~text
com.example.provider.DefaultProvider
~~~

When the **service interface** shifts from `javax.*` to `jakarta.*`, **the metadata filename may also have to change**. If the provider class changes packages, **the file contents** must change accordingly too.

### 10.2. Persistence provider example

A Jakarta Persistence environment may require a service descriptor named for the Jakarta interface:

~~~text
META-INF/services/jakarta.persistence.spi.PersistenceProvider
~~~

Its content points to the provider class shipped by the actual library version. Never guess or invent provider names; rely strictly on metadata distributed by the official provider release.

Similarly, CDI extensions implement `jakarta.enterprise.inject.spi.Extension`, not `javax.enterprise.inject.spi.Extension`. If the service file keeps the old filename, the runtime may fail to discover the extension.

### 10.3. Impact of shading and fat JARs

When merging multiple JARs or relocating dependencies, `META-INF/services` files can suffer from:

- Dropped files when resource paths collide.
- Keeping legacy interface filenames while new classes target `jakarta.*`.
- Keeping old provider class names.
- Pointing to classes stripped from the artifact.
- Merging providers from two incompatible namespaces accidentally.

Do not treat `Class.forName(provider)` succeeding as proof that `ServiceLoader` registered the provider properly. Execute actual ServiceLoader or framework provider discovery flows.

### 10.4. JPMS `uses`/`provides`

When running with explicit named modules, descriptors may contain:

~~~java
module com.example.provider {
    requires jakarta.persistence;
    provides jakarta.persistence.spi.PersistenceProvider
        with com.example.provider.CustomPersistenceProvider;
}
~~~

This example is valid only if the provider class actually implements that SPI with matching module dependencies. For third-party implementations, never author replacement descriptors without knowing the vendor's module design.

When migrating namespaces, check `module-info.java`/`module-info.class`, module names, package `exports`/`opens`, and whether provider modules are resolved. `META-INF/services` is not the sole discovery path on the module path.

## 11. Dependencies and application server must share the same namespace generation

### 11.1. You cannot update imports while keeping an old container

A servlet compiled as:

~~~java
public final class HealthServlet
        extends jakarta.servlet.http.HttpServlet {
}
~~~

requires a runtime/container providing the matching Jakarta Servlet API. A container supporting only `javax.servlet.*` will not accept this class.

Conversely, a legacy `javax.servlet.*` application will not deploy unmodified onto a `jakarta.servlet.*`-only container unless a vendor-supported, verified compatibility transformation layer is used.

### 11.2. Check the framework/container matrix before migrating

Directional version pairings:

| Stack | Primary namespace | What to verify |
| --- | --- | --- |
| Legacy servlet containers (e.g., Servlet 4 line) | `javax.servlet.*` | Generally incompatible with WARs compiled against `jakarta.servlet.*`. |
| Jakarta Servlet 5+ containers | `jakarta.servlet.*` | Verify exact Servlet level, JSP, WebSocket, and JDK requirements. |
| Spring Framework 5.x / Spring Boot 2.x | Primarily integrates `javax.*` enterprise namespaces | Requires a framework upgrade plan before moving the full stack to Jakarta. |
| Spring Framework 6.x / Spring Boot 3.x | Jakarta namespaces for related enterprise APIs | Check minimum JDK, starter dependencies, and integration libraries. |
| Pre-Jakarta Hibernate ORM | JPA `javax.persistence.*` in many releases | Do not mix Jakarta entity annotations with a javax-only provider. |
| Jakarta-era Hibernate ORM (e.g., 6.x) | Jakarta Persistence | Check API behavior, dialects, queries, and mapping changes beyond namespaces. |

Rows above illustrate compatibility relationships only. Verify the **exact releases your product selects**, since JDK requirements and supported features vary per release.

### 11.3. Servlet APIs normally should not be double-packaged in a WAR

When deploying a WAR to an application server, the Servlet API is typically supplied by the container. In Maven, API dependencies commonly use `provided`:

~~~xml
<dependency>
  <groupId>jakarta.servlet</groupId>
  <artifactId>jakarta.servlet-api</artifactId>
  <version>6.0.0</version>
  <scope>provided</scope>
</dependency>
~~~

The version shown suits Jakarta Servlet 6.0; do not copy it unchanged for containers supporting only Servlet 5.0. For executable applications, packaging and starter configs differ.

Never drop both `javax.servlet-api` and `jakarta.servlet-api` into `WEB-INF/lib` expecting the container to bridge both type systems automatically.

### 11.4. An API JAR is not an implementation

Importing `jakarta.persistence.EntityManager` does not provide a JPA implementation; having `jakarta.validation.Validator` does not supply a Bean Validation implementation.

A project must verify:

- Spec-accurate API artifacts at the right version.
- Runtime provider or container supplying the implementation.
- Extensions and SPIs matching the same namespace.
- Correct scopes for compile, test, and deployment.
- No stale legacy API versions pulled via transitive dependencies.

On full Jakarta EE servers, the server supplies many APIs/implementations; in standalone apps, declare runtime providers matching your stack.

## 12. Subtle failures when old and new APIs coexist

### 12.1. Two annotations with the same simple name

A project can accidentally compile both:

~~~java
import javax.persistence.Entity;
~~~

and:

~~~java
import jakarta.persistence.Entity;
~~~

if both API JARs sit on the classpath. Yet passing compilation does not mean the runtime handles both. A newer provider may scan only Jakarta annotations, silently leaving legacy-annotated entities unmanaged.

This situation is often riskier than compile failures because the application may boot in some profiles yet fail in others.

### 12.2. Servlet filters/listeners sharing no common interface

A legacy filter:

~~~java
public class LegacyFilter implements javax.servlet.Filter {
    // ...
}
~~~

is not a subtype of `jakarta.servlet.Filter`. Attempting to load it via `web.xml` or annotations on a Jakarta container can cause incompatibility errors, class-cast failures, or startup errors.

Changing the XML schema alone cannot fix it if the class has not been recompiled against the new API.

### 12.3. Integration libraries lagging behind

A REST client, security filter, JSP tag library, metrics integration, or custom JPA provider might still depend on `javax.*`. Even after editing application sources, legacy dependencies may remain incompatible.

Classify dependencies into:

- Official Jakarta releases available.
- Supported replacement alternatives available.
- Vendor-recommended bytecode/resource transformation tooling.
- Components that must sit behind a process boundary or stay on the legacy stack temporarily.

Avoid building a custom "bridge" JAR bundling both API generations without a well-tested adapter design.

## 13. XML namespaces are not strings to replace in bulk

### 13.1. Four string categories easily confused

One XML file can simultaneously contain:

~~~xml
xmlns="https://jakarta.ee/xml/ns/jakartaee"
xsi:schemaLocation="https://jakarta.ee/xml/ns/jakartaee ..."
<listener-class>com.example.web.SessionListener</listener-class>
<res-ref-name>jdbc/Orders</res-ref-name>
~~~

Respective meanings:

1. **Namespace URI** identifying the XML vocabulary/schema.
2. **Schema location** pointing to the versioned XSD.
3. **Class name** loaded by the framework/container via reflection.
4. **Resource identifier** such as a JNDI name; not a Java package.

Using one blind string replacement to turn everything into `jakarta.*` can severely corrupt descriptors.

### 13.2. Schema versions must match the target runtime

An application deployed to Servlet 5.0 must not use a version 6.0 web descriptor merely to look "latest". Conversely, leaving old namespace URIs may push newer Jakarta containers into legacy compatibility modes or outright rejection.

The right approach:

- Choose target stack and spec versions.
- Retrieve the matching XML schemas.
- Update namespaces, schema locations, and versions per spec.
- Verify class names and supported XML elements.
- Deploy and verify the parser loads the descriptors cleanly.

### 13.3. XML validation does not replace runtime tests

An XSD-valid descriptor still does not guarantee:

- The `filter-class` actually exists.
- The class implements `jakarta.servlet.Filter`.
- The persistence provider is compatible.
- CDI beans are actually discovered.
- JNDI resources exist on the server.
- Listeners or extensions initialize cleanly.

XML validation catches structural errors; runtime tests verify wiring and type compatibility.

## 14. Automated code modification: use selectively

### 14.1. Where automation excels

Source refactoring tools such as OpenRewrite or IDE migration features can assist with:

- Updating enterprise API imports per verified mapping rules.
- Rewriting fully qualified type references in source code.
- Adjusting common annotation and API usages.
- Updating dependency coordinates/versions per recipes.
- Transforming supported configuration and XML formats.

Some ecosystems offer bytecode/resource transformers to shift namespaces when source is unavailable. However, coverage and risk vary by tool version, artifact, and target.

Automation works best when mappings are structured cleanly and every diff is reviewable.

### 14.2. Why never run global "replace `javax.` → `jakarta.`"?

A blanket replacement breaks:

~~~java
javax.sql.DataSource
javax.crypto.Cipher
javax.naming.InitialContext
javax.xml.parsers.DocumentBuilderFactory
~~~

so it must never be used as a default approach. Replace only verified enterprise package lists while accounting for exceptions. Even prefix mappings must check target specifications.

### 14.3. Organizing changes into small commits

Split work into scoped commits or pull requests:

1. Lock baseline and dependency versions.
2. Upgrade framework/container and integration libraries.
3. Update source imports and annotations.
4. Regenerate generated-code sources/templates.
5. Update XML namespaces/XSDs/versions.
6. Update configuration class names and SPI metadata.
7. Update tests, test engines, fixtures, and packaging.
8. Verify runtime behavior and drop legacy dependencies.
9. Finalize migration docs, deployment configs, and rollback steps.

Separating change groups makes it easy to trace whether an error stems from sources, XML, SPI, or the runtime stack.

## 15. Migration testing: what must be confirmed?

### 15.1. Compile both main and test sources

Confirm that:

- No enterprise `javax.*` imports remain in modules required to move fully to Jakarta.
- Valid Java SE `javax.*` imports were not broken.
- Test frameworks, mocks, and extensions use the matching Jakarta APIs.
- Generated sources do not reintroduce the old namespace.
- No wrong-version classpath dependency gets pulled transitively.

Absence of `javax.*` in source code does not guarantee a clean artifact, because third-party JARs may still hold old bytecode or metadata.

### 15.2. Boot on the exact target application server

Deploy to the target server/runtime and verify:

- Servlets, filters, and listeners register cleanly.
- REST endpoints respond properly.
- CDI injection resolves properly.
- JPA persistence units initialize and map entities cleanly.
- Bean Validation triggers as expected.
- Security integration works.
- JSP/Faces/tag libraries render cleanly if used.
- SOAP/JAXB/JMS/Mail modules operate if within scope.

A smoke test hitting only a health endpoint can miss providers triggered only by rarely used flows.

### 15.3. Inspect XML descriptors and metadata

Practical checks should include:

- XML parsing/validation against target spec schemas.
- Runtime loading of every descriptor (`web.xml`, `persistence.xml`, `beans.xml`, etc.).
- Class lists referenced in `servlet-class`, `filter-class`, `listener-class`, and `provider`.
- `META-INF/services` metadata and other resources in final JAR/WARs.
- ServiceLoader or provider discovery tests.
- Dependency trees and `WEB-INF/lib` contents.
- Environment/profile/remote store configurations.

### 15.4. Preserve behavioral baselines

For critical flows, compare before and after:

| Flow | Expected evidence |
| --- | --- |
| HTTP servlets/filters | Status codes, headers, encoding, sessions, and filter ordering. |
| REST APIs | JSON requests/responses, validation, exception mappings. |
| JPA | Entity mappings, transactions, lazy loading, queries, and schema. |
| CDI | Injection, scopes, and lifecycle callbacks. |
| Bean Validation | Constraint violations and messages. |
| Authentication | Login, roles, filter chains, and sessions. |
| Messaging | Producers/consumers, deserialization, and ack behavior. |
| JSP/Faces | Taglibs, component bindings, and rendered output. |

Compare flows against **business contracts**, not startup success alone.

## 16. Controlled migration roadmap

### Phase 1: Choose targets and lock the support matrix

Specify:

- Target JDK and source/bytecode baseline.
- Target Jakarta EE platform/specification versions.
- Application server / servlet container version.
- Frameworks (Spring, Hibernate, Faces, REST implementations...) and integration libraries.
- Packaging layout: WAR, EAR, executable JAR, modular runtime.
- Permitted change scope and rollback plan.

Do not shift namespaces before confirming which APIs the target runtime supports.

### Phase 2: Inventory sources and dependencies

Categorize every `javax.*` reference as enterprise or Java SE. Trace owning artifacts, transitive dependencies, generated sources, descriptors, SPIs, and external configs.

Flag components lacking Jakarta-compatible releases so replacements or isolation strategies can be chosen.

### Phase 3: Upgrade dependencies and build tools

Pick a **synchronized version stack**; avoid pairing new APIs with old providers. Update build plugins, annotation processors, code generators, and test tools to match the target JDK.

For third-party libraries, prefer official Jakarta releases. Use bytecode transformers only as scoped bridges after testing tool boundaries.

### Phase 4: Update source imports and annotations

Apply selective enterprise mappings. Review diffs to ensure `javax.sql`, `javax.crypto`, `javax.naming`, and other Java SE packages stay intact. Update custom constraints, interceptors, injection, and SOAP/JAXB/REST adapters to match the target stack.

### Phase 5: Update XML descriptors

Update namespace URIs, schema locations, and versions appropriately. Inspect every class name, JNDI name, provider name, and property inside `web.xml`, `persistence.xml`, `beans.xml`, `orm.xml`, `validation.xml`, and `faces-config.xml`. Leave unrelated business identifiers untouched.

### Phase 6: Update metadata and runtime configurations

Update `META-INF/services`, config files, package scans, class names in environment variables, and external configs. Synchronize config rollouts with binary deployments so new code never reads incompatible legacy configs.

### Phase 7: Test in a production-like environment

Compile, run unit/integration tests, deploy to the target container, and inspect final artifacts. Verify providers, reflection, entity mappings, REST endpoints, and legacy clients.

### Phase 8: Incremental rollout and rollback

In multi-service systems, consider separating migrations along HTTP/message/database boundaries instead of mixing `javax.servlet` and `jakarta.servlet` within one app.

Keep old artifacts/configs deployable, verify data migrations independently, and roll out with canaries when suitable.

## 17. Reading migration errors by root cause

| Symptom | Possible causes | Investigation path |
| --- | --- | --- |
| `package javax.servlet does not exist` | Compile API switched while source still imports old package. | Update imports for target Servlet or align stack. |
| `package jakarta.servlet does not exist` | Missing Jakarta Servlet API on compile classpath or wrong version. | Check dependencies and scopes. |
| `ClassNotFoundException: javax...` | Legacy FQCN remains in XML/config/provider or old JAR missing. | Search class names in descriptors and runtime artifacts. |
| `ClassCastException` on Servlet/Provider | Incompatible `javax`/`jakarta` interface generations. | Compare class/interface signatures and dependency tree. |
| Filter/listener fails to load | Class does not implement Jakarta interface or descriptor invalid. | Inspect source, `web.xml`, and container spec. |
| JPA entities unrecognized | Old annotation, old provider, or wrong `persistence.xml`/mapping. | Check annotation packages, API/provider, and metadata. |
| `PersistenceException` on bootstrap | Invalid persistence unit, provider, class, or properties. | Read root cause, XML schema, and JPA runtime. |
| CDI beans not injected | CDI API/container/discovery or `beans.xml` out of sync. | Inspect bean-defining annotations and logs. |
| `ValidationException` | API/provider mismatch or legacy constraint metadata. | Check `jakarta.validation` and provider. |
| XML descriptor rejected | Namespace/XSD/version unsupported by runtime. | Cross-check target spec and validate XML. |
| `ServiceConfigurationError` | Provider metadata missing/misnamed or wrong interface implemented. | Inspect `META-INF/services` and runtime provider. |
| Tests pass yet deploy fails | Unit tests do not run on target application server. | Add integration/deployment tests. |
| `NoSuchMethodError` | Library compiled against a different API than runtime. | Compare `javap` and dependency classpath. |
| `NoClassDefFoundError` | Missing runtime dependency, old class removed. | Check WAR/EAR artifacts and server libraries. |
| Fails only in production profile | Unmigrated FQCN/descriptor/remote properties in prod config. | Compare environments and active runtime configs. |

Do not try to solve every error by placing both `javax.*` and `jakarta.*` API suites on the runtime. That may mask compile errors without creating safe type adapters.

## 18. Mini-lab: migrating a simple WAR

### 18.1. Current state

The application contains:

~~~text
src/main/java/com/example/web/OrderServlet.java
src/main/java/com/example/web/RequestAuditFilter.java
src/main/java/com/example/model/Order.java
src/main/resources/META-INF/persistence.xml
src/main/webapp/WEB-INF/web.xml
pom.xml
~~~

- Servlet and filter import `javax.servlet.*`.
- Entity imports `javax.persistence.*`.
- `web.xml` uses the legacy Java EE namespace.
- `persistence.xml` uses the JPA 2.x namespace.
- The new application server requires matching Jakarta Servlet and Jakarta Persistence support.

### 18.2. Tasks

1. Select target Servlet/Persistence spec versions and server JDK.
2. Update Servlet/JPA imports accurately; retain `java.io.*` and `javax.sql.DataSource` if used.
3. Update `@WebServlet`, `@Entity`, and `@PersistenceContext` annotations to the Jakarta namespace.
4. Migrate `web.xml` to the target namespace/XSD/version.
5. Migrate `persistence.xml` to the target namespace/XSD/version and verify the provider.
6. Audit `servlet-class` and `filter-class`; keep application FQCNs unchanged if packages did not move.
7. Confirm no `javax.persistence.spi.PersistenceProvider` provider metadata remains in Jakarta runtime components.
8. Deploy the WAR to the target container, call endpoints, and exercise JPA transactions.
9. Verify classpath, dependency scopes, and runtime logs.

### 18.3. Outcomes that are insufficient for completion

- **`mvn package` succeeds alone:** does not prove the container parses XML and loads providers properly.
- **Changing only `import` statements:** leaves descriptors, annotation scanners, and providers unverified.
- **Editing only `web.xml`:** leaves unverified whether Servlet classes implement `jakarta.servlet.Servlet`.
- **Replacing `javax.` with `jakarta.` across every file:** risks breaking Java SE APIs such as `javax.sql.DataSource`.
- **Clean startup alone:** does not verify JPA, injection, and rarely invoked code paths.

### 18.4. Mini-lab completion criteria

Required outputs:

- Map of updated source imports and annotations.
- XML descriptors aligned with target spec versions.
- Consistent dependency tree.
- Real WAR packaged with proper API/provider scopes.
- Runtime logs confirming servlet/filter/JPA bootstrap.
- Passing tests calling endpoints and exercising persistence.
- List of any external configs still carrying legacy class names, with assigned owners.

## 19. Practical checklist for Java EE → Jakarta

- [ ] Separated JDK upgrade scope from enterprise namespace change.
- [ ] Identified target Jakarta EE/Servlet/Persistence/CDI/Validation versions and runtime support.
- [ ] Remembered that Jakarta EE 8 still uses the `javax.*` namespace.
- [ ] Created selective enterprise API mappings rather than renaming all `javax.*`.
- [ ] Preserved Java SE APIs including `javax.sql`, `javax.naming`, `javax.crypto`, and `javax.xml.parsers`.
- [ ] Updated imports, FQCNs, and annotations across main and test sources.
- [ ] Updated code generators/templates so they do not regenerate legacy `javax.*`.
- [ ] Updated XML namespaces, schema locations, and versions per target specifications.
- [ ] Checked class names in `web.xml`, `persistence.xml`, `orm.xml`, `beans.xml`, `validation.xml`, and `faces-config.xml`.
- [ ] Distinguished class names from JNDI names and business identifiers.
- [ ] Audited standard `javax.persistence.*` property keys and provider-specific configs.
- [ ] Audited Spring/framework metadata, YAML/properties, environment variables, and external configs.
- [ ] Checked `META-INF/services` filenames and provider classes against actual Jakarta interfaces.
- [ ] Aligned application server, API JARs, providers, and frameworks to a compatible generation.
- [ ] Tested actual test runtimes and containers rather than relying solely on compilation.
- [ ] Verified class loading, annotation discovery, injection, persistence, REST/servlets, and service providers.
- [ ] Evaluated impact on serialized data, caches, and persistent FQCN records.
- [ ] Prepared rollback steps and documentation covering mappings and remaining incompatible dependencies.

## 20. Conclusion

Migrating from Java EE to Jakarta EE is **an application-wide type-contract and metadata migration**, not merely swapping `import javax.*` for `import jakarta.*`. Similarly named annotations represent distinct runtime types; XML descriptors require matching namespaces, XSDs, and versions; class names in configs, SPI metadata, and external stores must also resolve to real implementations in the target Jakarta stack.

The reliable approach is to **lock runtime versions first, build selective namespace mappings, update sources and XML layer by layer, synchronize providers and configuration, and validate the deployed artifact end-to-end**. Doing so avoids both extremes: leaving legacy namespaces behind so the runtime misses components, or over-replacing broadly and breaking Java SE APIs and valid business identifiers.