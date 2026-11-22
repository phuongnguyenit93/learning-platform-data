# Java SE `javax` Packages Outside the Scope of Bulk Renaming

When upgrading an application from Java EE to Jakarta EE, a simple yet **wrong** rule is often proposed: “replace all `javax.` with `jakarta.`”. In reality, many enterprise APIs switched namespaces, while `javax` packages belonging to **Java SE** retain their names across modern JDKs. Within the same Jakarta EE application, it is completely normal for source code to import both `jakarta.persistence.Entity` and `javax.sql.DataSource`.

The crux of **Java Advance Compatibility Migration** is not stripping out every occurrence of `javax`, but identifying **which platform owns the API, which module or artifact supplies it, and whether it falls within the namespace migration scope**. If `javax.net.ssl.SSLContext` is mistakenly changed to `jakarta.net.ssl.SSLContext`, or `javax.xml.parsers.DocumentBuilderFactory` to `jakarta.xml.parsers.DocumentBuilderFactory`, code will fail to locate the corresponding Java SE API. Conversely, keeping legacy `javax.servlet` when the server has moved to a newer Jakarta Servlet generation can prevent the runtime from recognizing filters, servlets, or extensions.

This lesson clarifies the boundary between Java SE and Jakarta EE, package families sharing similar prefixes yet belonging to different systems, common bugs caused by bulk search-and-replace, and a verified migration workflow.

## 1. Why Does `javax` Appear in Both Java SE and Java EE?

Historically, several standard APIs entered the Java platform under the `javax` namespace. These include Java SE technologies such as JDBC DataSource, JSSE/TLS, Swing, XML parsing, JNDI, and Java Management Extensions. Meanwhile, enterprise specifications such as Servlet, JPA, JAX-RS, JMS, and many others also used the `javax` namespace in Java EE.

When Java EE transitioned to Jakarta EE, the namespace shift applied to enterprise APIs within Jakarta's scope, **not to Java SE as a whole**. Jakarta EE 8 still used the `javax` namespace for inherited APIs; the main move to `jakarta` took place in Jakarta EE 9.

Therefore, the right question is not:

> “Does the import start with javax?”

Rather, it is:

> “Does this class belong to a Java SE specification or an enterprise API within Jakarta EE's namespace migration scope?”

### 1.1. Three Layers to Distinguish

| Layer | Function | Examples |
|---|---|---|
| Java SE / JDK | Platform APIs, JVM, standard modules | `javax.sql`, `javax.net.ssl`, `javax.xml.parsers` |
| Jakarta EE specifications | Enterprise contracts | `jakarta.servlet`, `jakarta.persistence`, `jakarta.ws.rs` |
| Implementation/framework/container | Runtime execution of enterprise contracts | Servlet container, JPA provider, Jakarta REST implementation |

Changing an enterprise namespace neither automatically updates its implementation nor alters Java SE classes.

## 2. Identification Table for Java SE `javax` Packages

The packages below are key examples that **must not be automatically changed to jakarta**. The JPMS module shows one source supplying the API on modern JDKs; cross-check the exact target JDK if the project uses special configurations.

| Java SE API Group | Representative Package / Class | JPMS Module | Decision |
|---|---|---|---|
| JDBC DataSource | `javax.sql.DataSource`, `javax.sql.XADataSource` | `java.sql` | Keep unchanged |
| JDBC RowSet | `javax.sql.rowset.CachedRowSet` | `java.sql.rowset` | Keep unchanged |
| XA resource interface | `javax.transaction.xa.XAResource`, `Xid` | `java.transaction.xa` | Keep unchanged |
| TLS / JSSE | `javax.net.ssl.SSLContext`, `SSLSocket` | `java.base` | Keep unchanged |
| Cryptography | `javax.crypto.Cipher`, `SecretKey` | `java.base` | Keep unchanged |
| Java authentication | `javax.security.auth.Subject` | `java.base` | Keep unchanged |
| JNDI | `javax.naming.InitialContext` | `java.naming` | Keep unchanged |
| JMX | `javax.management.MBeanServer` | `java.management` | Keep unchanged |
| XML parser | `javax.xml.parsers.DocumentBuilderFactory` | `java.xml` | Keep unchanged |
| XML transformation | `javax.xml.transform.TransformerFactory` | `java.xml` | Keep unchanged |
| XML validation / XPath | `javax.xml.validation.SchemaFactory`, `javax.xml.xpath.XPathFactory` | `java.xml` | Keep unchanged |
| Streaming XML | `javax.xml.stream.XMLInputFactory` | `java.xml` | Keep unchanged |
| XML namespace | `javax.xml.namespace.QName` | `java.xml` | Keep unchanged |
| XML digital signature | `javax.xml.crypto.dsig.XMLSignature` | `java.xml.crypto` | Keep unchanged |
| Swing/GUI | `javax.swing.JFrame`, `JPanel` | `java.desktop` | Keep unchanged |
| Desktop facilities | `javax.imageio.ImageIO`, `javax.print` | `java.desktop` | Keep unchanged |
| Java Sound | `javax.sound.sampled`, `javax.sound.midi` | `java.desktop` | Keep unchanged |
| Script API | `javax.script.ScriptEngineManager` | `java.scripting` | Keep unchanged |
| Compiler APIs | `javax.tools.JavaCompiler` | `java.compiler` | Keep unchanged |
| Annotation processing | `javax.annotation.processing.Processor` | `java.compiler` | Keep unchanged |
| Language model | `javax.lang.model.element.TypeElement` | `java.compiler` | Keep unchanged |

This table does not list every `javax` package inside Java SE. When encountering an unfamiliar class, check its API specification, module descriptor, or the artifact containing it. **Never conclude based solely on prefix.**

## 3. Enterprise Namespaces That Typically Must Change

When upgrading to Jakarta EE generations using the new namespace, common mappings include:

| Legacy Enterprise API | New Jakarta API | Function |
|---|---|---|
| `javax.servlet` | `jakarta.servlet` | Servlet/filter/listener |
| `javax.persistence` | `jakarta.persistence` | Persistence/JPA |
| `javax.ws.rs` | `jakarta.ws.rs` | REST/JAX-RS |
| `javax.validation` | `jakarta.validation` | Bean Validation |
| `javax.inject` | `jakarta.inject` | Dependency injection |
| `javax.enterprise` | `jakarta.enterprise` | CDI |
| `javax.ejb` | `jakarta.ejb` | Enterprise Beans |
| `javax.jms` | `jakarta.jms` | Messaging |
| `javax.websocket` | `jakarta.websocket` | WebSocket |
| `javax.mail` | `jakarta.mail` | Mail |
| `javax.json` | `jakarta.json` | JSON Processing |
| `javax.json.bind` | `jakarta.json.bind` | JSON Binding |
| `javax.xml.bind` | `jakarta.xml.bind` | JAXB/XML Binding |
| `javax.xml.ws` | `jakarta.xml.ws` | JAX-WS |
| `javax.activation` | `jakarta.activation` | Activation |
| `javax.annotation.Resource` | `jakarta.annotation.Resource` | Common Annotations |
| `javax.transaction.UserTransaction` | `jakarta.transaction.UserTransaction` | Enterprise Transactions |

This is a **classification map**, not a guarantee that rewriting imports suffices. API artifacts, implementations, extensions, and frameworks/containers must all upgrade together to supported versions. For example, a Servlet filter already compiled against `javax.servlet.Filter` does not automatically implement `jakarta.servlet.Filter`. The two interfaces have different fully qualified names and are distinct types in the JVM.

## 4. Classic Case: Jakarta Persistence Still Uses `javax.sql.DataSource`

After migration, entities may use:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public class ProductEntity {
    @Id
    private Long id;

    private String name;

    protected ProductEntity() {}
}
~~~

Meanwhile, the JDBC layer still uses Java SE types:

~~~java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class ProductDao {
    private final DataSource dataSource;

    public ProductDao(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public String findName(long id) throws SQLException {
        try (Connection connection = dataSource.getConnection();
             PreparedStatement query =
                     connection.prepareStatement(
                         "SELECT name FROM product WHERE id = ?")) {
            query.setLong(1, id);

            try (ResultSet result = query.executeQuery()) {
                return result.next()
                        ? result.getString("name")
                        : null;
            }
        }
    }
}
~~~

These files are illustrative. `jakarta.persistence` requires a matching Jakarta Persistence API/implementation; `javax.sql.DataSource` belongs to Java SE and **must not** be changed to `jakarta.sql.DataSource`.

### 4.1. JDBC Drivers Are Not JPA APIs

Switching ORM/JPA namespaces does not change JDBC contracts. `java.sql.Connection`, `java.sql.PreparedStatement`, `javax.sql.DataSource`, and `javax.sql.XADataSource` keep their Java SE names. A Jakarta-generation connection pool or ORM provider continues using them.

When database errors arise during migration, distinguish JPA mapping, driver, schema, transaction, or dependency causes instead of blaming `javax.sql` imports by default.

## 5. An Easy-to-Miss Exception: `javax.transaction.xa`

The name `javax.transaction.xa` leads many developers to mistakenly assume it must become `jakarta.transaction.xa`. In reality, the **XA resource interface** group is supplied by Java SE and retains its namespace.

~~~java
import javax.transaction.xa.XAResource;
import javax.transaction.xa.XAException;
import javax.transaction.xa.Xid;
~~~

Within a Jakarta Transactions application, other enterprise APIs may use:

~~~java
import jakarta.transaction.Transactional;
import jakarta.transaction.UserTransaction;
~~~

Both groups can **validly coexist**. Do not apply a blanket rule `javax.transaction.* → jakarta.transaction.*` without excluding `javax.transaction.xa`.

An `XADataSource`/transaction manager interacts with `XAResource` as defined by the Java SE interface. Replacing it with another similarly named type of different JVM identity causes calls or casts to fail.

### 5.1. JPMS Module

In a modularized project, the module containing the XA API is `java.transaction.xa`. When used directly from a named module, declare the corresponding dependence in `module-info.java`. Do not invent a new module named “jakarta.transaction.xa” by analogy from enterprise namespace shifts.

## 6. `javax.xml` Is Not a Single Monolith

`javax.xml` is prone to confusion because it contains both core Java SE XML APIs and enterprise technologies once bundled with older JDKs.

### 6.1. Java SE XML APIs Keep Their Names

~~~java
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.transform.TransformerFactory;
import javax.xml.validation.SchemaFactory;
import javax.xml.xpath.XPathFactory;
import javax.xml.stream.XMLInputFactory;
import javax.xml.namespace.QName;
~~~

DOM parser example:

~~~java
import javax.xml.parsers.DocumentBuilderFactory;

DocumentBuilderFactory factory =
        DocumentBuilderFactory.newInstance();

factory.setNamespaceAware(true);
~~~

Parser/transformer/validation/StAX APIs still belong to Java SE, primarily in module `java.xml`. Moving JAXB to Jakarta does not create `jakarta.xml.parsers.DocumentBuilderFactory`.

For XML from untrusted sources, parsers also need proper security hardening to restrict external entities and external resource access. That is an XML security concern, not a reason to rename packages.

### 6.2. JAXB and JAX-WS Have a Different History

Legacy JAXB API:

~~~java
import javax.xml.bind.JAXBContext;
~~~

New-namespace Jakarta XML Binding API:

~~~java
import jakarta.xml.bind.JAXBContext;
~~~

Likewise, `javax.xml.ws` belongs to earlier JAX-WS generations, while `jakarta.xml.ws` belongs to the newer Jakarta XML Web Services generation.

**JEP 320** removed the Java EE and CORBA modules once bundled in the JDK starting in **JDK 11**. Thus, when moving from JDK 8 to JDK 11/17/21, an application relying on JDK-bundled JAXB/JAX-WS requires external dependencies. Yet not every `javax.xml` package vanished.

Two paths may exist depending on your roadmap:

- Retain an external JAXB version still using the `javax.xml.bind` namespace if frameworks and application contracts need the older generation.
- Migrate to `jakarta.xml.bind` along with compatible API/implementation and frameworks, then verify XML contracts.

Pick one path per the support matrix; never mix APIs/implementations merely because simple class names look alike.

### 6.3. XML on the Wire Is Not a Java Package

Changing Java classes from `javax.xml.bind` to `jakarta.xml.bind` does not mean business XML namespace URIs, element names, or XSDs must change in lockstep. XML documents are wire data with their own contracts; test old/new fixtures before altering schemas.

## 7. `javax.annotation.processing` Differs from `javax.annotation`

This is a frequent trap when migrating Common Annotations.

Annotation processors use **Java SE compiler APIs**:

~~~java
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.Processor;
import javax.annotation.processing.RoundEnvironment;
import javax.lang.model.element.TypeElement;
import javax.tools.JavaCompiler;
~~~

These packages belong to module `java.compiler` and do not change to `jakarta.annotation.processing`.

Meanwhile, a Jakarta EE application may need:

~~~java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.Resource;
~~~

An important example: `javax.annotation.processing.Generated` (Java SE) must not be confused with `javax.annotation.Generated` from legacy Common Annotations APIs. The two names are similar yet differ in origin and lifecycle.

### 7.1. Generated Code Can Rightly Mix Both Namespaces

A JPA metamodel processor can use `javax.annotation.processing` to execute inside `javac` while generating source importing `jakarta.persistence.metamodel`. These represent two distinct contracts:

- API used to **implement the annotation processor**: Java SE.
- API inside **generated JPA source**: Jakarta Persistence.

If generated source still contains legacy `javax.persistence`, upgrade the generator/plugin or fix generator configuration—**do not alter the Java SE compiler API**.

## 8. JNDI, JSSE, JMX, JAAS, and Crypto Remain Java SE

Examples of valid imports inside a Jakarta EE application:

~~~java
import javax.naming.InitialContext;
import javax.sql.DataSource;
import javax.net.ssl.SSLContext;
import javax.crypto.Cipher;
import javax.security.auth.Subject;
import javax.management.MBeanServer;
~~~

Breakdown:

- `javax.naming`: JNDI, module `java.naming`.
- `javax.net.ssl`: SSL/TLS, module `java.base`.
- `javax.crypto`: cryptography, module `java.base`.
- `javax.security.auth`: Java SE authentication APIs.
- `javax.management`: JMX, module `java.management`.
- `javax.sql`: JDBC DataSource, module `java.sql`.

JNDI DataSource lookup example:

~~~java
import javax.naming.InitialContext;
import javax.naming.NamingException;
import javax.sql.DataSource;

public final class DataSourceResolver {
    public DataSource resolve() throws NamingException {
        InitialContext context = new InitialContext();
        try {
            return (DataSource) context.lookup(
                    "java:comp/env/jdbc/MainDataSource");
        } finally {
            context.close();
        }
    }
}
~~~

The JNDI name is illustrative; actual lookup paths and config depend on your server/framework. Do not rename `javax.naming` to `jakarta.naming`.

If TLS fails after a JDK upgrade, check certificates, truststores, protocols, and hostnames; `javax.net.ssl` did not change because of Jakarta EE migration.

## 9. Java Desktop and Other `javax` Packages

For desktop applications, `javax.swing` stays in Java SE:

~~~java
import javax.swing.JFrame;
import javax.swing.JLabel;
import javax.swing.SwingUtilities;

public final class HelloDesktop {
    public static void main(String[] args) {
        SwingUtilities.invokeLater(() -> {
            JFrame frame = new JFrame("Java SE");
            frame.add(new JLabel("Hello"));
            frame.setSize(300, 120);
            frame.setDefaultCloseOperation(
                    JFrame.EXIT_ON_CLOSE);
            frame.setVisible(true);
        });
    }
}
~~~

APIs such as `javax.imageio.ImageIO`, `javax.print`, `javax.sound.midi`, `javax.sound.sampled`, and `javax.accessibility` also have no Jakarta-namespaced replacements.

A project containing both desktop tools and Jakarta EE servers must handle each module according to its dependencies and API contracts rather than applying one global regex across the whole monorepo.

## 10. Real-World Integration Example: Jakarta Servlet and Java SE JDBC

In a Jakarta Servlet application, code validly uses both type families:

~~~java
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import javax.sql.DataSource;
import java.io.IOException;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class StatusServlet extends HttpServlet {
    private final DataSource dataSource;

    public StatusServlet(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    @Override
    protected void doGet(HttpServletRequest request,
                         HttpServletResponse response)
            throws ServletException, IOException {
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(
                     "SELECT status FROM app_status WHERE id = ?")) {
            statement.setLong(1, 1L);
            try (ResultSet result = statement.executeQuery()) {
                response.setContentType("text/plain; charset=UTF-8");
                response.getWriter().write(result.next()
                        ? result.getString("status")
                        : "unknown");
            }
        } catch (SQLException failure) {
            throw new ServletException("Database error", failure);
        }
    }
}
~~~

This snippet illustrates **type compatibility**, not complete servlet registration. In a real container, `DataSource` instantiation/injection must follow the active framework/container; a standard container does not automatically supply arbitrary constructor arguments.

Crucial takeaway: `jakarta.servlet.http.HttpServlet` belongs to Jakarta Servlet; `javax.sql.DataSource` and `java.sql.*` belong to Java SE. **Having both in the same file is not a bug.**

## 11. Consequences of Repository-Wide String Replacement

A dangerous operation:

~~~text
Find:    javax.
Replace: jakarta.
Scope:   all files
~~~

produces invalid edits such as:

~~~text
javax.sql.DataSource
  -> jakarta.sql.DataSource                   (wrong)

javax.net.ssl.SSLContext
  -> jakarta.net.ssl.SSLContext               (wrong)

javax.xml.parsers.DocumentBuilderFactory
  -> jakarta.xml.parsers.DocumentBuilderFactory (wrong)

javax.transaction.xa.XAResource
  -> jakarta.transaction.xa.XAResource        (wrong)

javax.annotation.processing.Processor
  -> jakarta.annotation.processing.Processor  (wrong)

javax.persistence.Entity
  -> jakarta.persistence.Entity               (correct when the target stack uses Jakarta Persistence)
~~~

Invalid replacements typically make the compiler report `package ... does not exist`. Yet not every bug surfaces at compile time: an old binary plugin or service descriptor can fail at runtime execution.

### 11.1. Do Not Use “Zero Occurrences of `javax`” as a Success Gate

A properly migrated Jakarta EE application can legitimately contain numerous `javax` imports. The proper criterion is:

> Enterprise APIs **within the namespace migration scope** have been upgraded in lockstep with the framework/container, while Java SE `javax` APIs keep their contracts and operate properly.

Using “0 `javax` imports” as a build gate pressures teams into breaking Java SE code with nonexistent names.

## 12. Package Renaming Affects Type Identity and Bytecode

Two names:

~~~text
javax.servlet.Servlet
jakarta.servlet.Servlet
~~~

are not aliases for the same interface. The JVM treats them as two distinct fully qualified names.

An extension compiled to implement `javax.servlet.Filter` does not automatically implement `jakarta.servlet.Filter` merely by swapping the servlet container. Similarly, a class annotated with `javax.persistence.Entity` does not automatically act as a Jakarta entity if the provider scans only for `jakarta.persistence.Entity`.

Common failures:

- `ClassNotFoundException` / `NoClassDefFoundError` when a binary's required namespace is absent.
- `ClassCastException` when attempting to cast an object into the other namespace's type.
- `NoSuchMethodError` when descriptors called by older consumers no longer match.
- Annotation scanners failing to detect entities/validators/listeners.
- Frameworks ignoring registrations or SPI providers targeting the wrong interface.
- Code generators emitting old types while runtime requires new ones.

Compiling a single module proves only that inspected sources compile. Test **runtime integration** and precompiled consumers/plugins as well.

## 13. Dependencies and Containers Must Share the Same Generation

When changing enterprise namespaces, choose an API/implementation combination supporting one another:

| Component | What to Verify |
|---|---|
| Jakarta specification API | Correct namespace and version |
| Servlet/JPA/JAX-RS/CDI implementation | Does it support the chosen API generation? |
| Framework/starter | Dependencies and auto-configuration from the same generation |
| Application server/container | Does the runtime recognize the new API namespace? |
| Build plugins | WAR packaging, enhancers, annotation processors, metamodel generation |
| Direct dependencies | No legacy enterprise API remains on migrated paths |
| Transitive dependencies | Does an older extension pull in the previous namespace? |
| External plugins | Have they been rebuilt or upgraded for Jakarta interfaces? |
| JDK | Minimum Java version and supported module APIs |

**Do not remove Java SE modules `java.sql`, `java.xml`, `java.naming` just to erase `javax`.** When deploying a WAR into a container, pick API dependency scopes matching the container contract; a `jakarta.*-api` JAR does not necessarily ship a runtime implementation.

Having both `javax` and `jakarta` APIs on a classpath is not automatically wrong. Determine whether **types participating in the same runtime contract** are mistakenly mismatched.

## 14. Boundary Between JDK Upgrade and Jakarta Namespace Migration

Several shifts often happen together despite different root causes:

| Symptom | Possible Cause | Rename `javax` → `jakarta` Needed? |
|---|---|---|
| `javax.sql.DataSource` compiles normally | Java SE API provided by the JDK | No |
| `javax.xml.bind.JAXBContext` missing post-JDK 11 | JDK dropped bundled JAXB per JEP 320 | Choose dependencies/stack; may move to Jakarta yet not mandatory solely for JDK bump |
| `InaccessibleObjectException` | Deep reflection across module boundaries blocked | Not necessarily; inspect JPMS/framework |
| `SSLHandshakeException` | TLS/certificates/truststore or security policy | No |
| Servlet extension fails on new Jakarta container | `javax.servlet` and `jakarta.servlet` types incompatible | Yes, in the enterprise extension or use a supporting release |
| JPA entity ignored by provider | Annotation API/provider generation mismatch | Likely needs namespace + framework migration |
| `javax.transaction.xa.XAResource` compiles normally | XA interface belongs to Java SE | No |
| Annotation processor cannot find `jakarta.annotation.processing` | Mistakenly renamed Java SE compiler API | Must restore `javax.annotation.processing` |

This demonstrates why every migration error cannot be collapsed into a single “rename packages” step.

## 15. Inventory Imports Before Editing

Create an inventory of **fully qualified names** in use, including:

- Java/Kotlin main and test sources.
- Generated code and annotation processor outputs.
- Dependency JARs.
- XML descriptors and deployment configs.
- Reflection strings such as `Class.forName`.
- `META-INF/services` and SPI provider declarations.
- Annotation class names in metadata or config files.
- Serialization/wire payloads embedding fully qualified class names.
- Independently built plugins/agents/adapters.

Candidate search example with ripgrep (reference commands for real projects):

~~~bash
rg -n '^import (static )?javax\.' src
rg -n 'javax\.' src
~~~

Results only surface **candidates**. A comment or string mentioning `javax` does not prove live API usage; conversely, a precompiled JAR may embed references invisible to source search.

### 15.1. Sample Inventory

| FQCN in Use | Classification | Action |
|---|---|---|
| `javax.sql.DataSource` | Java SE / JDBC | Keep unchanged |
| `javax.net.ssl.SSLContext` | Java SE / TLS | Keep unchanged |
| `javax.xml.parsers.DocumentBuilderFactory` | Java SE / XML | Keep unchanged |
| `javax.transaction.xa.XAResource` | Java SE / XA | Keep unchanged |
| `javax.annotation.processing.Processor` | Java SE / compiler | Keep unchanged |
| `javax.servlet.http.HttpServlet` | Legacy Enterprise | Migrate when target stack uses Jakarta Servlet |
| `javax.persistence.Entity` | Legacy Enterprise | Migrate when target stack uses Jakarta Persistence |
| `javax.xml.bind.JAXBContext` | Legacy JAXB | Pick dependency/namespace per roadmap |
| `javax.annotation.Resource` | Legacy Common Annotations | Migrate when using Jakarta Common Annotations |
| Unknown `javax.*` | Unverified | Mark `NEEDS_VERIFICATION` |

The “unverified” category is critical; never guess mappings just because a name resembles another group.

## 16. How to Verify an API Belongs to Java SE

### 16.1. Inspect Modules on the Target JDK

On JPMS-enabled JDKs:

~~~bash
java --list-modules
java --describe-module java.sql
java --describe-module java.xml
java --describe-module java.transaction.xa
java --describe-module java.compiler
~~~

These commands check modules and exported packages on the inspected runtime. Seeing `javax.sql` inside `java.sql` is a clear signal no Jakarta replacement package is needed.

Minimal runtime images created with `jlink` may omit modules; therefore distinguish a **full JDK** from a **custom image**.

### 16.2. Compile-Probe the API Against Target Compiler/JDK

~~~java
import javax.sql.DataSource;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.transaction.xa.XAResource;

public class SeApiProbe {
    DataSource dataSource;
    XAResource xaResource;

    DocumentBuilderFactory factory() {
        return DocumentBuilderFactory.newInstance();
    }
}
~~~

Example compilation with a `--release`-capable compiler:

~~~bash
javac --release 17 SeApiProbe.java
~~~

With properly configured compilers and environments, the corresponding Java SE types resolve for that release. This does not prove Jakarta Servlet or JPA was upgraded since those come from external dependencies.

### 16.3. Check Resolved Dependencies

With Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --configuration runtimeClasspath \
  --dependency servlet-api
~~~

With Maven:

~~~bash
./mvnw dependency:tree
~~~

These illustrate investigation steps; select the real module/configuration and do not treat sample output as runtime proof. Determine the actual resolved API/implementation artifacts rather than merely versions typed into build scripts.

## 17. Scope Refactoring Instead of Global Replacement

A controlled mapping can start with verified enterprise groups:

~~~text
Enterprise migration candidates:
  javax.servlet.*      -> jakarta.servlet.*
  javax.persistence.*  -> jakarta.persistence.*
  javax.ws.rs.*        -> jakarta.ws.rs.*
  javax.validation.*   -> jakarta.validation.*
  javax.inject.*       -> jakarta.inject.*

Explicit Java SE exclusions:
  javax.sql.*
  javax.transaction.xa.*
  javax.net.*
  javax.crypto.*
  javax.security.auth.*
  javax.naming.*
  javax.management.*
  javax.xml.parsers.*
  javax.xml.transform.*
  javax.xml.validation.*
  javax.xml.stream.*
  javax.annotation.processing.*
  javax.lang.model.*
  javax.tools.*
  javax.swing.*
~~~

This list is **not exhaustive**. For instance, `javax.xml.bind` must be handled separately from `javax.xml.parsers`, and `javax.transaction.xa` must stay intact even when enterprise APIs under `javax.transaction` shift namespaces.

An IDE-aware refactoring tool or migration recipe helps, yet inspect the ruleset and diff carefully. If the tool rewrites Java SE APIs too, fix the recipe instead of searching for nonexistent `jakarta.*` libraries.

## 18. ServiceLoader, Annotation Scanning, and Generated Metadata

Not every migration bug triggers a compile error. Runtime mechanisms referencing class names and annotations can keep pointing at the old namespace:

- Service provider files under `META-INF/services`.
- Framework configs storing fully qualified class names.
- `Class.forName("javax...")` in reflection.
- JPA entity scanning, validation scanning, and CDI discovery.
- Servlet filters, listeners, and extension registrations.
- Annotation processors/metamodel generators.
- Bytecode proxies or instrumentation built against old APIs.

For example, a provider written for the legacy namespace's SPI will not register under the new Jakarta SPI. Meanwhile, Java SE APIs like `javax.script` and `javax.annotation.processing` keep their namespaces in their corresponding Java SE SPIs.

Verify **which API family the metadata refers to**, rather than renaming every service descriptor beginning with `javax`.

## 19. Do Not Confuse Namespace Migration with Wire Data Changes

Changing Java packages alters type identity, yet does not require changing protocol/serialization identifiers accordingly.

With XML and JAXB, business data namespace URIs can remain identical even when implementations switch to Jakarta XML Binding. With JSON, field contracts and datetime formats can stay independent of Java package names. However, if payloads embed Java class names, shifting `javax.*` to `jakarta.*` constitutes a data contract change.

Test:

1. Can data produced by the older version be read by the newer version?
2. Can older consumers read payloads from newer producers during rolling deployments?
3. Did annotations/serializers alter default field names, elements, or namespace URIs?
4. Do serialized objects, caches, or messages store Java class names?
5. If data migration is needed, is there a clear rollback or roll-forward path?

Do not alter business XML namespaces merely because Java imports changed.

## 20. Verifying Migration Across Dimensions

| Check | What to Confirm |
|---|---|
| Source compatibility | Java SE `javax` still compiles; new enterprise APIs resolve cleanly |
| Binary compatibility | Whether legacy plugins/consumers need rebuilding for the new Jakarta namespace |
| Dependency compatibility | APIs, implementations, containers, and extensions share the same generation |
| Annotation metadata | JPA, CDI, validation, and servlet annotations recognized at runtime |
| Database | `jakarta.persistence` works with `javax.sql.DataSource`, XA, and drivers |
| XML/JSON | Schemas, old/new payloads, namespaces, and converters work properly |
| Security | Authn/authz, validation, and TLS policies were not relaxed |
| Runtime/JDK | Minimum Java version, module access, and framework/JDK support |
| CI/build | IDE, CLI, and CI resolve identical graphs and generated code |
| Rolling deployment | Coexisting consumers do not depend on unexpectedly changed contracts |

### 20.1. Positive and Negative Tests

If validation was migrated, test valid **and** invalid inputs. If security annotations/filters were migrated, test authorized **and** unauthorized users. An application whose home page loads while silently skipping validation due to mismatched annotation namespaces has not completed migration.

## 21. Step-by-Step Execution Plan

### Step 1: Lock Source and Target Versions

Document JDK/Jakarta EE generations, containers, frameworks, ORMs, build tools, dependencies, and Java baselines. Avoid vague descriptions like “switch to Jakarta.”

### Step 2: Classify `javax` by API Owner

Use import scans, dependency graphs, JDK module docs, and package metadata. Preserve Java SE packages; convert only in-scope enterprise APIs.

### Step 3: Upgrade the Enterprise Stack Together

Select mutually compatible Jakarta APIs, implementations, extensions, and containers. Never leave legacy `javax.servlet` consumers against a `jakarta.servlet`-only runtime without a verified compatibility strategy.

### Step 4: Update Imports and Metadata Selectively

Update sources, generated code, reflection strings, service descriptors, and configs belonging to target enterprise APIs. Never touch `javax.sql`, `javax.net.ssl`, `javax.xml.parsers`, or other Java SE APIs.

### Step 5: Compile and Test at Runtime

Use explicit target compiler releases/JDKs and resolved dependency graphs. Run startup, ORM mapping, Servlet/JAX-RS, validation, DI, JDBC/XA, XML, and security tests relevant to the app.

### Step 6: Test Consumers and Historical Data

For plugins, test binary/type identity compatibility. For XML/JSON/caches/messages, verify reading historical data and new behaviors.

### Step 7: Record Evidence and Roll Out with Control

Save commits, dependency/JDK versions, test reports, and known limitations. Maintain rollback/roll-forward plans wherever data contracts or plugin namespaces changed.

## 22. Common Mistakes

**“Every `javax.*` must be replaced with `jakarta.*`.”** False: Java SE still includes many supported `javax` packages.

**“Jakarta EE 8 migrated the entire namespace.”** The major shift occurred in Jakarta EE 9.

**“You cannot have `jakarta.persistence` and `javax.sql` in the same app.”** You can, and normally must.

**“`jakarta.sql.DataSource` is the new JDBC API.”** It is not a standard replacement for `javax.sql.DataSource`.

**“All `javax.xml` packages changed.”** False: Java SE's XML parsers/transformers/StAX remain `javax.xml`.

**“Every `javax.transaction` package must change.”** `javax.transaction.xa` belongs to Java SE.

**“`javax.annotation.processing` is Jakarta Common Annotations.”** False: it is the Java SE compiler API.

**“Newer JDKs dropped bundled JAXB, so `javax.xml.parsers` vanished too.”** They are distinct package groups.

**“No more `javax.servlet` imports means every extension is compatible.”** Binary plugins, generated code, and runtime metadata may still reference the old namespace.

**“Compiling cleanly means migration succeeded.”** You must test runtime annotation scanning, containers, data contracts, and security.

**“Any `javax` in code means migration is unfinished.”** True only for in-scope enterprise APIs, false for Java SE.

## 23. Migration Checklist

- [ ] Recorded source/target JDKs and Java EE/Jakarta EE generations.
- [ ] Identified supported APIs, implementations, frameworks, and containers.
- [ ] Classified `javax.*` imports by specification and artifact/module.
- [ ] Preserved `javax.sql`, `javax.net.ssl`, `javax.crypto`, `javax.naming`, and `javax.management`.
- [ ] Preserved `javax.transaction.xa`.
- [ ] Separated `javax.xml.parsers` from `javax.xml.bind`.
- [ ] Preserved `javax.annotation.processing` and `javax.lang.model`.
- [ ] Properly migrated `javax.servlet`, `javax.persistence`, and required enterprise APIs.
- [ ] Avoided blanket `javax.` → `jakarta.` search-and-replace.
- [ ] Audited sources, generated code, reflection strings, and service descriptors.
- [ ] Checked dependency graphs and legacy extensions/plugins.
- [ ] Confirmed JDK module availability if using JPMS.
- [ ] Executed compile, integration, annotation scan, data, and negative security tests.
- [ ] Documented unverified consumers, environments, or code paths.
- [ ] Recorded results and rollout/rollback plans.

## Conclusion

**Moving from Java EE to Jakarta EE namespaces is a scoped transition, not a repository-wide string replacement of `javax`.** Java SE retains official `javax` packages such as `javax.sql`, `javax.transaction.xa`, `javax.net.ssl`, `javax.crypto`, `javax.xml.parsers`, and `javax.annotation.processing`. Meanwhile, enterprise APIs like `javax.servlet` and `javax.persistence` shift to `jakarta` when upgrading to the matching Jakarta EE generation.

Safe migration requires classifying by **API ownership**, upgrading frameworks/implementations in lockstep, renaming only in-scope FQCNs, and verifying source, binary, runtime, metadata, data, and security contracts. The goal is not “zero `javax` lines,” but **an application using both Java SE and Jakarta EE cleanly according to each platform's contract**.
