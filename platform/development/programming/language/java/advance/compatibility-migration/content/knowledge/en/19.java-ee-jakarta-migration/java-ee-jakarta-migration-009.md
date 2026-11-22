# Namespace migration tools and the limits of automated transformation

When upgrading a Java EE application to Jakarta EE within a **Java Advance Compatibility Migration** project, common failures involve more than missing libraries or JDK incompatibilities. Many APIs previously under `javax.*` packages moved to `jakarta.*` starting in **Jakarta EE 9**. Classes that look identical in name and methods still become **two distinct types** inside the JVM: `javax.servlet.http.HttpServletRequest` cannot automatically substitute for `jakarta.servlet.http.HttpServletRequest`; a bean using `javax.persistence.Entity` is not recognized as an entity by a newer Jakarta Persistence provider expecting `jakarta.persistence.Entity`.

Automated tools such as **OpenRewrite**, IDE refactoring capabilities, **Eclipse Transformer**, and **Apache Tomcat Jakarta EE Migration Tool** can significantly cut down the work of updating imports, dependencies, descriptors, and bytecode. However, **automated transformation does not guarantee behavioral compatibility**: a tool can rewrite symbols it recognizes, yet cannot decide on its own whether an annotation carries new semantics, whether an old framework supports Jakarta, or whether a protocol passing serialized Java objects between two versions remains readable.

This lesson focuses on **choosing the right namespace migration tool, understanding the scope of each transformation method, handling parts that cannot be converted automatically, and verifying against the target Jakarta runtime**. The content belongs to the **Java EE and Jakarta** chapter, where package renaming is just one step alongside API, dependency, container, and framework-ecosystem migration.

## 1. Context: Java EE, Jakarta EE 8, and Jakarta EE 9+

Distinguish three eras to avoid confusing **artifact names** with **package names**:

| Era | Common enterprise API namespace | Migration implication |
|---|---|---|
| Java EE 7/8 | `javax.servlet.*`, `javax.persistence.*`, `javax.ws.rs.*`, ... | Legacy applications are typically compiled against the `javax` namespace |
| **Jakarta EE 8** | **Still `javax.*`** across transferred APIs | Having “Jakarta” in the group/artifact or product name **does not yet mean** packages are `jakarta` |
| **Jakarta EE 9/9.1** | Relevant Jakarta EE APIs rename to **`jakarta.*`** | Major namespace milestone; sources and binaries must be adjusted |
| Jakarta EE 10/11+ | Continues under the `jakarta.*` namespace | Adds specification version, method, and Java baseline changes; not merely import updates |

For example, a dependency whose groupId starts with `jakarta` **is not enough** to conclude the JAR contents live under `jakarta.servlet`. Several Jakarta EE 8 artifacts still contain classes under `javax.servlet`. Conversely, a newer application server supporting Jakarta Servlet 6 may not expose `javax.servlet` classes to a web app compiled for Java EE 8.

**Working rule:** choose the **target Jakarta EE platform/profile and container/framework versions first**, and from there determine API artifact versions, implementation dependencies, and conversion steps. Never start with a repository-wide string replacement.

### 1.1. Changing the JDK and changing the Jakarta namespace are two distinct axes

Upgrading from Java 8 to Java 17 does not automatically turn `javax.servlet` into `jakarta.servlet`. An application can run on JDK 17 while staying on a `javax` stack if its server/framework still supports it. Conversely, newer Jakarta frameworks may require a higher minimum JDK even if source code uses no new Java syntax.

Examples:
- A WAR app using Servlet 4 on a container supporting `javax.servlet` can upgrade its JDK per the support matrix before moving to Jakarta.
- An app moving to Tomcat 10.1 using Jakarta Servlet 6 requires the **`jakarta.servlet` namespace** and matching dependencies.
- A Spring Boot 2.x project generally belongs to the Java EE/`javax` stack for relevant APIs; Spring Boot 3.x belongs to the Jakarta/`jakarta` stack and brings distinct Java/framework requirements. Bumping the Boot major version is not just changing imports.

Therefore, construct a matrix across at least three dimensions: **runtime JDK**, **platform/container/framework**, and **namespace/API version**.

## 2. Which packages move, and which must not be replaced?

Running `replaceAll("javax.", "jakarta.")` across every Java file is dangerous. **Jakarta EE renames the namespaces of Jakarta EE APIs**, whereas many `javax.*` packages belonging to **Java SE** remain unchanged.

### 2.1. Jakarta EE APIs commonly needing conversion

| API/domain | Java EE/Jakarta EE 8 namespace | Jakarta EE 9+ namespace |
|---|---|---|
| Servlet | `javax.servlet.*` | `jakarta.servlet.*` |
| Persistence/JPA | `javax.persistence.*` | `jakarta.persistence.*` |
| CDI | `javax.enterprise.*` | `jakarta.enterprise.*` |
| Dependency Injection | `javax.inject.*` | `jakarta.inject.*` |
| Bean Validation | `javax.validation.*` | `jakarta.validation.*` |
| REST/JAX-RS | `javax.ws.rs.*` | `jakarta.ws.rs.*` |
| WebSocket | `javax.websocket.*` | `jakarta.websocket.*` |
| JMS/Messaging | `javax.jms.*` | `jakarta.jms.*` |
| JAXB/XML Binding | `javax.xml.bind.*` | `jakarta.xml.bind.*` |
| SOAP/JAX-WS | `javax.xml.ws.*` | `jakarta.xml.ws.*` |
| Mail | `javax.mail.*` | `jakarta.mail.*` |
| Activation | `javax.activation.*` | `jakarta.activation.*` |
| JSON-P | `javax.json.*` | `jakarta.json.*` |
| JSON-B | `javax.json.bind.*` | `jakarta.json.bind.*` |
| Faces/JSF | `javax.faces.*` | `jakarta.faces.*` |
| EJB | `javax.ejb.*` | `jakarta.ejb.*` |
| Jakarta Transactions/JTA | `javax.transaction.*` (Jakarta-governed subset) | `jakarta.transaction.*` |
| Jakarta Security | `javax.security.enterprise.*` | `jakarta.security.enterprise.*` |
| Expression Language | `javax.el.*` | `jakarta.el.*` |
| Common Annotations | `javax.annotation.*` under Jakarta Annotations | Corresponding `jakarta.annotation.*` |

This table guides **APIs owned by Jakarta EE**, not context-blind string replacement rules. Each project must confirm the exact specification version and actual classes inside target JARs.

### 2.2. Java SE `javax.*` packages that must stay intact

Examples:

| Package not to replace wholesale | Role |
|---|---|
| `javax.crypto.*` | Java SE/JCA cryptography |
| `javax.net.ssl.*` | TLS/JSSE |
| `javax.swing.*` | Swing desktop UI |
| `javax.sql.*` | JDBC DataSource and related APIs |
| `javax.naming.*` | JNDI |
| `javax.management.*` | JMX |
| `javax.xml.parsers.*` | Java SE XML parser APIs |
| `javax.xml.transform.*` | XSLT/transformer APIs |
| `javax.xml.namespace.*` | XML namespaces |
| `javax.xml.stream.*` | StAX |
| `javax.annotation.processing.*` | Java compiler annotation processing |
| `javax.lang.model.*` | Compiler language model |
| `javax.transaction.xa.*` | Java SE XA APIs (`java.transaction.xa` in Java 9+) |

For example, this code must **not** be changed to `jakarta.xml.parsers.DocumentBuilderFactory`:

~~~java
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.parsers.DocumentBuilder;

// Java SE XML parsing API; keep javax.* unchanged
DocumentBuilder builder =
        DocumentBuilderFactory.newInstance().newDocumentBuilder();
~~~

Nor should `javax.crypto.Cipher` be changed to `jakarta.crypto.Cipher`, because no such Jakarta API exists.

### 2.3. Shared prefixes with different ownership

An especially error-prone case:
- `javax.annotation.PostConstruct` belonged to legacy Common Annotations and moves to `jakarta.annotation.PostConstruct` in Jakarta Annotations.
- `javax.annotation.processing.Generated` belongs to the Java SE annotation processing API and **stays unchanged**.
- Java EE's `javax.transaction.Transactional` moves to `jakarta.transaction.Transactional`.
- `javax.transaction.xa.XAResource` is a Java SE API and **does not move** to `jakarta.transaction.xa.XAResource`.

If a tool blindly rewrites the entire `javax.annotation` or `javax.transaction` prefix, it can break valid Java SE code. This is why API-aware recipes plus dependency/compilation verification are essential instead of plain text find-and-replace.

## 3. Why does namespace renaming cause binary incompatibility?

The JVM identifies classes by their **fully qualified name**, including the package. These two names represent distinct types:

~~~text
javax.servlet.http.HttpServletRequest
jakarta.servlet.http.HttpServletRequest
~~~

At the class-file level, JVM/internal descriptors also change:
 
~~~text
Ljavax/servlet/http/HttpServletRequest;
Ljakarta/servlet/http/HttpServletRequest;
~~~

For instance, an old library method:

~~~java
public void handle(javax.servlet.http.HttpServletRequest request)
~~~

no longer shares a descriptor with the new version:

~~~java
public void handle(jakarta.servlet.http.HttpServletRequest request)
~~~

A Java consumer compiled against the `javax` descriptor **cannot automatically link** to the new method accepting `jakarta`. Failures that may arise:
- `NoClassDefFoundError` or `ClassNotFoundException` if the old API is missing.
- `NoSuchMethodError` if the method expected under the legacy descriptor no longer exists.
- `ClassCastException` if the system attempts to cast between two non-equivalent objects/classes.
- Failures loading annotations, CDI injection, provider discovery, or framework integrations.
- `LinkageError` when the classpath/module path produces an invalid mixed graph.

**You cannot fix this by adding both API JARs and casting an object from `javax` to `jakarta`.** Both types may coexist as distinct classes, yet old and new containers still demand their own matching API contracts.

### 3.1. Source migration, binary migration, and runtime migration differ

| Activity | What changes | What is not automatically guaranteed |
|---|---|---|
| Source transformation | Imports, type names, annotations, dependency declarations | That runtime libraries and containers are compatible |
| Bytecode transformation | Constant pool, references, annotation descriptors, and supported resources | That behavior, framework structures, and protocols are compatible |
| Runtime migration | Container/framework using `jakarta`, JVM, and new deployment config | That legacy clients/data can read new objects |
| Semantic migration | API behavior, serialization, validation, auth, transactions, provider config | Cannot be proved merely via namespace substitution |

Separating these activities helps migration teams pick the right tools and recognize what still requires manual work.

## 4. Inventorying before running tools

Before converting anything, catalog sources, libraries, descriptors, generated code, and deployment configurations.

### 4.1. Finding usages in source

Example import search:

~~~bash
rg -n --glob '*.java' \
  '(^|[[:space:]])import[[:space:]]+javax\.' src
~~~

Searching for class names as strings or in configuration:

~~~bash
rg -n --hidden \
  -g '!**/.git/**' \
  'javax\.(servlet|persistence|validation|ws\.rs|enterprise|inject|jms|xml\.bind|mail)' .
~~~

Searching for reflective class/provider loading points:

~~~bash
rg -n --glob '*.java' \
  'Class\.forName|ServiceLoader|loadClass|forName|MethodHandles' src
~~~

Text search provides only partial coverage:
- Class names may be constructed dynamically, fetched from a DB/config, or generated by a framework.
- Pre-compiled dependency JARs lack source inside the repository.
- XML/JSP/TLD/property files may embed class names or namespace URIs.
- Test fixtures may embed class names or JSON polymorphic type identifiers.
- Java SE `javax.*` packages must not be added to replacement lists merely because a regex matched them.

### 4.2. Inventorying resolved dependencies

With Maven:

~~~bash
./mvnw dependency:tree
~~~

With Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency jakarta.servlet-api \
  --configuration runtimeClasspath
~~~

The commands above serve real-world projects; when writing an article at STEP 4, you do not need to run them.

Focus on:
- API JARs: `javax.servlet-api`, `jakarta.servlet-api`, JPA, Validation, JMS, JAXB, JAX-RS.
- Implementations/runtimes: Hibernate ORM, Jersey/RESTEasy, Weld/CDI, Faces, JSON-B, Mail, JAX-WS.
- Frameworks: Spring Framework/Boot, application server libraries, plugins/agents.
- Transitive dependencies still importing `javax` in bytecode.
- Generated sources and annotation processors.
- Drivers/native libraries and test integrations.

### 4.3. Inspecting classes inside JARs, not just groupIds

You can inspect:

~~~bash
jar --list --file path/to/api-or-library.jar
~~~

Check the real package paths:
 
~~~text
javax/servlet/...
jakarta/servlet/...
~~~

Or use:
 
~~~bash
jdeps --recursive --class-path "lib/*" app.jar
~~~

`jdeps` is useful for static references across classes/modules. It **does not reliably detect** class names loaded via reflection, `META-INF/services` files, resource strings, or scripts. If a JAR has been transformed, re-analyze its output rather than guessing from artifact names alone.

### 4.4. Recording scope before converting

A practical inventory table:

| Component | Current state | Target | Owner |
|---|---|---|---|
| Web module | `javax` Servlet WAR | Jakarta Servlet 6/Tomcat 10.1 | Web team |
| Persistence | JPA `javax.persistence` | Compatible Jakarta Persistence provider | Data team |
| REST endpoints | JAX-RS `javax.ws.rs` | Compatible Jakarta REST runtime | API team |
| Validation | `javax.validation` | New Jakarta Validation provider | API team |
| XML descriptors | Old `web.xml`, `persistence.xml` | Target platform schemas/namespaces | Platform team |
| Internal libraries | `javax`-only JARs | Rebuild from source or temporary transform | Shared library team |
| External plugins | No Jakarta release yet | Upgrade, adapter, or replace | Integration team |
| Tests | `javax` mock containers | `jakarta` runtime tests and contract tests | QA/dev team |

Do not turn the table immediately into an automated action list. First verify the **exact Java EE/Jakarta EE target** and runtime support.

## 5. Choosing tools by input type

No single tool handles every layer of migration.

| Tool/category | Suitable inputs | Typical expected outcome | Primary limitation |
|---|---|---|---|
| **OpenRewrite** | Java sources, build files, select config/resources with recipes | Updates APIs/imports/dependencies via structured recipes | Does not grasp full business semantics, dynamic reflection, or every schema |
| **IDE refactoring** (IntelliJ IDEA/Eclipse IDE) | Owned source code | Updates imports/types and supports reviewable edits | Depends on indexing/config; does not alter external JARs |
| **Eclipse Transformer** | JAR/WAR archives, classes, and supported resources | Converts select binary/package-level references and resources | Does not guarantee every library, signature, reflection call, or behavior |
| **Apache Tomcat Jakarta EE Migration Tool** | Applicable Java EE web apps/WARs/JARs | Converts artifacts for Tomcat Jakarta environments | Bounded by Tomcat/Jakarta rules; does not fix business semantics |
| **Compiler + dependency analysis** | Post-conversion sources and artifacts | Surfaces missing types, wrong APIs/bytecode | Does not prove runtime behavior |
| **Integration/contract tests** | App deployed in target runtime | Verifies business flows | Does not perform migration itself |

**Preferred strategy:** where you have source and maintained dependencies, prioritize **upgrading dependencies to official Jakarta releases and converting sources in a controlled pass**. Binary transformers are useful for legacy artifacts lacking a Jakarta variant, yet should be treated as a temporary measure with an owner and support constraint.

## 6. OpenRewrite: structured recipe-based source migration

OpenRewrite is a recipe-driven transformation platform well suited for multi-module repositories, Java/framework upgrades, and rule-expressible API/dependency changes. It transforms Java syntax trees and compatible build/config files according to specific recipes instead of context-blind global text search-and-replace.

### 6.1. Structuring an OpenRewrite migration pass

A safe workflow:
1. Lock down target JDK, Jakarta platform, framework, and dependency versions.
2. Check the list of recipes **actually present in the exact `rewrite-migrate-java` version in use**.
3. Run recipes on a dedicated branch to produce a reviewable diff.
4. Review changes across imports, annotations, field/method types, dependency declarations, and XML/configs.
5. Build and run tests in the target environment, then fix gaps not covered by recipes.
6. Pin recipe/plugin versions so results are reproducible.

Do not guess recipe IDs from documentation titles or old blog examples. Recipes can be renamed, split into sub-recipes, restricted by version predicates, or shifted in scope across releases. Consult the official catalog for the **exact pinned recipe artifact version**.

### 6.2. Before/after source conversion example

Before:

~~~java
import javax.servlet.annotation.WebServlet;
import javax.servlet.http.HttpServlet;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

@WebServlet("/health")
public class HealthServlet extends HttpServlet {
    @Override
    protected void doGet(
            HttpServletRequest req,
            HttpServletResponse resp
    ) throws java.io.IOException {
        resp.getWriter().write("OK");
    }
}
~~~

After migrating to the Jakarta Servlet API:

~~~java
import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

@WebServlet("/health")
public class HealthServlet extends HttpServlet {
    @Override
    protected void doGet(
            HttpServletRequest req,
            HttpServletResponse resp
    ) throws java.io.IOException {
        resp.getWriter().write("OK");
    }
}
~~~

Here most changes are packages/imports. Yet this code runs only inside a servlet container supporting the corresponding **Jakarta Servlet** release. If the server still supplies `javax.servlet`, a clean compilation does not guarantee deployment succeeds.

### 6.3. Dependency/build files must change too

With Maven, example WAR targeting a runtime supporting Jakarta Servlet 6:

~~~xml
<dependency>
    <groupId>jakarta.servlet</groupId>
    <artifactId>jakarta.servlet-api</artifactId>
    <version>6.0.0</version>
    <scope>provided</scope>
</dependency>
~~~

`provided` fits when the container manages the Servlet API; however, executable JARs or embedded servers have different packaging and dependency strategies. Do not apply `provided` blindly to every Jakarta API, because JPA/Validation/JAXB may require packaged runtime implementations/providers.

Gradle example for a WAR deployed to a Servlet 6 container:

~~~groovy
plugins {
    id 'java'
    id 'war'
}

dependencies {
    providedCompile 'jakarta.servlet:jakarta.servlet-api:6.0.0'
}
~~~

These examples show that **import updates and dependency updates must stay aligned**. If sources use `jakarta.servlet` while runtime JARs only carry `javax.servlet`, failures often wait until startup or deployment.

### 6.4. Diff review: not every change can be applied mechanically

An OpenRewrite pass may miss:
- Class names passed as strings.
- Static resources/configs lacking dedicated recipes.
- Generated code recreated from an older plugin.
- Internal libraries with similar APIs yet different semantics.
- Custom extensions/reflective providers.
- Binary-only dependencies outside source control.

Reviewing diffs means verifying the **transformed scope**, not merely counting replaced imports. Document file groups untouched by recipes so they can be handled manually or covered by custom tested recipes.

## 7. IDE refactoring: suited for context-sensitive changes

IntelliJ IDEA or Eclipse IDE offer import updates, find usages, rename/refactor tools, and inspections. They excel when:
- A repository is small or scoped to one module.
- Framework-specific source logic needs editing.
- Immediate in-editor compile feedback is needed.
- Certain APIs change method signatures or annotation semantics, not just packages.
- Someone with domain knowledge must decide ambiguous cases.

However:
- The IDE may fail to index Jakarta dependencies accurately before build files are updated.
- Text-based package renames risk touching Java SE `javax` packages.
- Editing source does not transform external binary JARs.
- Developers running different IDE versions/settings can generate inconsistent diffs.

In multi-module migrations, you can combine OpenRewrite for baseline diffs, the IDE for edge cases, and code review to unify semantics.

### 7.1. Example requiring manual judgment

Old code:

~~~java
import javax.annotation.PostConstruct;
import javax.annotation.processing.Generated;

@Generated("legacy-codegen")
public class CustomerCache {
    @PostConstruct
    public void initialize() {
        // ...
    }
}
~~~

After moving the component into a compatible Jakarta container:
- `PostConstruct` moves to `jakarta.annotation.PostConstruct`.
- `Generated` from `javax.annotation.processing` belongs to Java SE and **must not change**.

A naive string replacement of `javax.annotation` with `jakarta.annotation` would break `Generated`'s package. API-aware tools and developer review are essential.

## 8. Eclipse Transformer: bytecode-level artifact transformation

**Eclipse Transformer** provides rule-driven transformation of namespaces and resources applicable to certain JAR/WAR/archive formats or compiled bytecode artifacts. It helps when:
- A legacy library exists only as a compiled binary artifact.
- You do not control the source to rebuild immediately.
- You need to test converting between namespaces using a rule set.
- The vendor has not yet shipped a Jakarta-compatible version.
- The team creates a short-lived adapter artifact during migration.

### 8.1. Areas a binary transformer can process

Depending on version, configuration, and rule sets, the tool can transform:
- Class/package names in constant pools and bytecode references.
- Method/field descriptors, signatures, and annotation descriptors.
- Resource paths and class names in supported text resources.
- Manifest headers and service/provider metadata.
- Archive entry names and select text resources per configured rules.

**Never claim all items above always convert automatically.** Exact coverage depends on tool version, rule files, archive layout, and resource types. During migration, inspect actual output with `jar`/`javap`/`jdeps` and runtime tests.

### 8.2. Binary transformation differs from rebuilding from source

With source migration:
 
~~~text
Legacy source -> Jakarta imports -> javac -> Jakarta JAR
~~~

With binary transformation:

~~~text
Legacy Java EE JAR
      |
      v
Transformer + namespace/resource rules
      |
      v
Transformed JAR (Jakarta-facing)
      |
      v
Verify bytecode, dependencies, resources, runtime behavior
~~~

A transformed JAR is not equivalent to an official vendor release. When the vendor already supports Jakarta, **prefer the official Jakarta artifact** to receive bug fixes, security patches, and compatibility support.

### 8.3. Do not fabricate exact CLI commands without knowing the distribution

CLI packaging, artifact names, entrypoints, and rule files vary across Eclipse Transformer releases. Therefore, a runbook should record:
- Pinned tool version.
- Source distribution/URL/checksum.
- Input artifact checksum.
- Rule set applied.
- Exact CLI verified for that version.
- Output artifact name, hash, and test evidence.

Conceptual command pattern:

~~~text
transformer-cli <input-artifact> <output-artifact> <jakarta-rules>
~~~

This is a **pseudocommand**, not a copy-paste command. When executing, obtain exact CLI syntax for your release from official documentation.

### 8.4. Limits with signed JARs and provenance

If a JAR is cryptographically signed, modifying bytes post-signing invalidates its signature. You must:
1. Check whether the artifact carries signatures/related manifest entries.
2. Never treat transformed output as retaining original signature trust.
3. Re-sign strictly per organizational artifact-signing/publishing policy if needed.
4. Record provenance: source artifact, rule set, tool version, output artifact.
5. Check license, SBOM, and supply-chain policy for the transformed build.

Binary transformation does not patch security vulnerabilities inside a library. An EOL dependency can still harbor bugs even after its package name becomes `jakarta`.

## 9. Apache Tomcat Jakarta EE Migration Tool

Apache Tomcat provides the **Jakarta EE Migration Tool** to convert Java EE web applications to the Jakarta namespace within its supported scope. It is useful when migrating a WAR/JAR without source access or quickly evaluating compatibility with Tomcat using the Jakarta Servlet API.

Documentation and scope should be retrieved from the [Apache Tomcat Jakarta EE Migration Tool](https://github.com/apache/tomcat-jakartaee-migration) project.

### 9.1. Inputs and goals

Conceptual illustration:

~~~text
legacy-app.war (javax.servlet.*)
        |
        v
Tomcat Jakarta migration tool + appropriate profile/rules
        |
        v
migrated-app.war (jakarta.servlet.*)
        |
        v
Deploy to target Tomcat supporting Jakarta Servlet
~~~

The tool can transform class files and selected web-app components per profile, yet:
- It does not upgrade framework libraries to officially supported releases.
- It does not fix business logic where semantics changed.
- It does not synthesize missing compatible runtime providers.
- It does not guarantee pre-migration serialized Java objects remain readable.
- It does not guarantee the bytecode-transformed WAR runs on every Jakarta EE server.

**Use it properly by treating it as a tested artifact conversion step**, not standalone proof of compatibility.

### 9.2. When is the container's tool appropriate?

- Running a legacy WAR on a Tomcat version moved to Jakarta Servlet when source cannot be rebuilt immediately.
- Defining explicitly which WARs are transformed, which rule profiles are used, and an expiration timeline.
- Pairing with integration tests and a follow-up plan to migrate to proper source/Jakarta dependencies.

Where projects control their source and build pipelines, updating official imports/dependencies and rebuilding cleanly is far more maintainable than transforming WARs on every deployment.

## 10. Limit 1: reflection and string-based class names

Source transformers handle **AST type references** well and bytecode transformers update **descriptors**, yet reflection creates hard edge cases:

~~~java
Class<?> type = Class.forName(
        "javax.servlet.http.HttpServletRequest"
);
~~~

A tool may recognize and rewrite the literal string above under a rule, yet offers no guarantees if the name is:
- Concatenated from multiple variables.
- Read from a DB, YAML, XML, or system property.
- Loaded over the network or via a plugin.
- Encoded/packed inside a custom resource.
- Emitted by an annotation processor or code generator.

Example:

~~~java
String namespace = config.get("servletNamespace");
String typeName = namespace + ".http.HttpServletRequest";
Class<?> type = Class.forName(typeName);
~~~

You cannot declare migration sound merely because `jdeps` no longer reports a `javax.servlet` dependency. You must test reflective loading paths, plugin discovery, DI/proxies, and metadata sources.

### 10.1. Class loaders are also part of the contract

Even after type names change, class loaders still affect execution:
- Which library loads first.
- Whether redundant API JARs were packaged inside the WAR.
- Whether multiple incompatible framework versions coexist.
- Whether classes belong to expected module or application server class loaders.
- Which plugins/JDBC/JPA providers are discovered via `ServiceLoader` or resources.

The same fully qualified class name loaded by two separate class loaders can still be mutually incompatible. Inspect both **classloader identity** and binary dependencies, not just namespace strings.

## 11. Limit 2: META-INF/services and provider discovery

Java `ServiceLoader` and many frameworks locate providers via files:

~~~text
META-INF/services/<fully.qualified.InterfaceName>
~~~

Suppose an old JAR has an entry:

~~~text
META-INF/services/javax.example.LegacyService
~~~

If the corresponding interface moves to `jakarta.example.NewService`, both the resource filename and provider implementations may need updates matching the new contract. A transformer may support select rules, yet cannot know custom provider contracts of every framework.

Items to audit:
- `META-INF/services`.
- `module-info.class` `uses`/`provides` under JPMS.
- CDI/JPA/Validation/JAX-RS metadata files.
- Framework-specific custom SPIs.
- Manifest entries or application configurations.
- Generated service registries and annotation indexes.

In particular, **not every service interface containing `javax` belongs to Jakarta EE**. If a tool rewrites `javax.xml.parsers.SAXParserFactory` or another Java SE SPI through unselective text matching, it can break provider discovery.

## 12. Limit 3: deployment descriptors, XML namespaces, and schema versions

Enterprise Java relies on multiple XML descriptors:
- `web.xml`.
- `persistence.xml` and `orm.xml`.
- `beans.xml` for CDI.
- `faces-config.xml`.
- `validation.xml`.
- EJB/JMS/JAX-RS deployment resources.
- JSP/TLD/taglib files.

Beyond Java packages, these files use distinct XML namespace URIs, schema locations, and version attributes. **Do not rewrite URIs with a generic text replacement**: each specification defines its own schema/version and potentially new validation rules.

### 12.1. Example web.xml for Jakarta Servlet 6

A `web.xml` written against the Jakarta Servlet 6 schema might start with:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<web-app
    xmlns="https://jakarta.ee/xml/ns/jakartaee"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        https://jakarta.ee/xml/ns/jakartaee
        https://jakarta.ee/xml/ns/jakartaee/web-app_6_0.xsd"
    version="6.0">

    <display-name>Orders Service</display-name>
</web-app>
~~~

**Do not blindly copy this Servlet 6 example to Servlet 5 or every Jakarta EE profile.** Projects targeting Jakarta EE 9/Servlet 5 must use the matching schema/version, while other runtimes may handle descriptors differently.

### 12.2. Persistence, CDI, and validation span multiple configuration layers

After changing `javax.persistence.Entity` to `jakarta.persistence.Entity`, verify:
- `persistence.xml` and `orm.xml` declare the proper schema/version.
- A matching Jakarta Persistence provider is present.
- Entity scanning and transaction integration continue working.
- Named queries, converters, listeners, and validation hooks work.
- Database dialects, JDBC drivers, and schema migrations align.
- Provider reflection, proxies, and bytecode enhancement succeed.

A recipe updating only annotations does not prove the entity manager factory bootstraps cleanly, SQL mappings stay unchanged, or data remains safe.

Similarly, for CDI:
- `javax.inject.Inject` → `jakarta.inject.Inject` where applicable to APIs being migrated.
- `beans.xml` and bean discovery mode match runtime expectations.
- Scope lifecycles, interceptors, decorators, and extension SPIs require tests.
- Extensions using legacy `javax.enterprise.inject.spi` must be updated or replaced.

## 13. Limit 4: generated code and annotation processors

Many applications generate code from:
- OpenAPI/Swagger generators.
- JAXB/XJC.
- JAX-WS tools.
- QueryDSL, MapStruct, or custom annotation processors.
- GraphQL/REST code generators.
- Build plugins generating DTOs, clients, or sources.

If you edit files only under `target/generated-sources` or `build/generated`, the next build may **regenerate `javax` imports**.

Proper workflow:
1. Identify the generator/tool and version producing the sources.
2. Check whether the generator supports outputting Jakarta namespaces.
3. Upgrade the generator/plugin or customize its templates appropriately.
4. Clean old generated outputs and regenerate from scratch.
5. Compile the newly generated sources.
6. Pin generator/template versions for pipeline reproducibility.

If the generator lacks Jakarta support, post-processing transformations can serve as a temporary measure with tests and an owner. Never commit manual edits inside generated source folders without fixing the upstream generator.

### 13.1. javax.annotation.processing remains Java SE

Many annotation processors use `javax.annotation.processing.*` or `javax.lang.model.*`. They do not need changing just because the project migrates to Jakarta. Meanwhile, annotations emitted onto domain code may move to `jakarta.annotation.*` or `jakarta.persistence.*`. This is a frequent distinction in projects using multiple code generators.

## 14. Limit 5: dependency graphs and implementation providers

An API JAR only describes interfaces/annotations/contracts. Many Jakarta APIs require a **runtime implementation/provider**:
- JPA requires a compatible persistence provider.
- Bean Validation requires a validation provider.
- JAXB may require a runtime implementation.
- JAX-RS requires a runtime/client implementation.
- JMS requires a messaging provider/client supporting the Jakarta namespace.
- CDI requires a container or compatible implementation.

For example, adding:

~~~xml
<dependency>
    <groupId>jakarta.persistence</groupId>
    <artifactId>jakarta.persistence-api</artifactId>
    <version>3.1.0</version>
</dependency>
~~~

allows code using `jakarta.persistence.Entity` to compile, yet **does not create a JPA runtime**. If deploying as a WAR onto a Jakarta EE full-platform server, the container may supply the provider per profile. For standalone/Spring Boot apps, you need a matching ORM implementation and framework-managed configuration.

### 14.1. Avoid mixing two API namespaces inside one contract

An error scenario:

~~~text
Web container API:     jakarta.servlet.*
Library A filter:      javax.servlet.Filter
Application endpoint:  jakarta.servlet.http.HttpServlet
~~~

Library A was compiled against `javax.servlet.Filter`. Adding `javax.servlet-api.jar` to `WEB-INF/lib` does not turn Library A into a filter implementing `jakarta.servlet.Filter` for the Jakarta container.

Valid options:
- Upgrade Library A to a Jakarta release.
- If none exists, assess binary artifact transformation with tests and strict boundaries.
- Write an adapter when two systems exchange data through a contract that is **not a direct cast**.
- Replace an unmaintained library.

### 14.2. Jakarta EE 8 artifacts are not the target for Jakarta EE 9+

Do not pick a dependency merely because its groupId starts with `jakarta.*`. Check **JAR contents and API major versions**. A Jakarta EE 8 artifact can still hold `javax.*` inside class files because the namespace cutover started at Jakarta EE 9. This pitfall is especially common when dependency management/BOMs pull older artifacts.

### 14.3. Managing versions via BOMs and parent POMs/frameworks

When using a Maven BOM, Gradle platform, or Spring Boot dependency management, avoid overriding an isolated dependency without reviewing the entire aligned stack:
- Jakarta API versions.
- Implementation/provider versions.
- Servlet container version.
- Minimum JDK.
- ORM/Validation/Jackson/Jersey/RESTEasy integrations.
- Test frameworks/mocks/instrumentation.

A graph mixing new Jakarta APIs with old `javax` implementations may still partially compile and fail only at runtime.

## 15. Limit 6: serialized data and cross-service protocols

Changing packages alters **class identity**. If a system transmits Java native serialized objects over RMI, JMS ObjectMessage, caches, or database BLOBs, an old object carrying a `javax.*` class name—or a domain class referencing `javax` types—may no longer deserialize on the new runtime.

Risks include:
- `ClassNotFoundException` or `InvalidClassException`.
- Changes in `serialVersionUID`, object graphs, or field types.
- Session replication across `javax` and `jakarta` containers.
- Distributed caches holding objects from prior versions.
- Message queues replaying legacy entries post-upgrade.
- Legacy consumers unable to read new payloads.

### 15.1. Correct source code does not guarantee smooth session/state migration

For example, a web app stores serialized HTTP sessions containing objects from an old framework library. When deploying the new Jakarta WAR, sessions restored by the new classloader may fail to read old classes. This requires planning:
- Controlled session invalidation or forcing re-login if acceptable.
- Migrating session payloads to a format independent of Java class names (such as schema-backed JSON) where suitable.
- Explicit session schema versioning.
- Never forcing a session serializer to blindly rewrite class names while ignoring behavioral changes.

For zero-downtime/rolling deployments, state separation or coexistence preparation may be needed before switching namespaces. Never assume `javax` and `jakarta` WAR versions can exchange serialized session objects directly.

### 15.2. Keeping wire contracts decoupled from Java APIs

HTTP/JSON, Protobuf, or Avro with explicit schemas rely less on Java package names, provided type names are not embedded into payloads. Even so, verify:
- JSON polymorphic type discriminators may contain fully qualified class names.
- JAXB/XML payload namespaces may differ from Java package names.
- Serialization defaults may change when upgrading frameworks.
- Timestamps, enums, validation rules, and API error formats may shift semantics.
- Older consumers may continue running during phased rollouts.

**Do not equate changing Java namespaces with breaking every external protocol.** A stable REST API can keep its wire payload intact while the server upgrades Servlet/JAX-RS implementations, provided contract tests verify it.

## 16. Limit 7: framework behavior changes alongside migration

Moving to Jakarta EE 9+ often coincides with upgrading:
- Servlet containers and HTTP stacks.
- CDI implementations and bean discovery.
- Persistence providers (such as a Hibernate major version).
- Bean Validation providers.
- JAX-RS runtimes and JSON mappers.
- Security/TLS/session integrations.
- Build plugins and test frameworks.

These upgrades can introduce:
- New default configurations/validations.
- Altered transaction boundaries and exception wrapping.
- Different queries, SQL dialects, or schema generation.
- Changed URI mapping, URL encoding, and filter ordering.
- Changed serialization precision/null handling.
- Reflection/JPMS strong encapsulation issues.
- Altered class-loader behavior and service discovery.
- Newer Java baselines, bytecode targets, or TLS defaults.

Namespace migration tools normally **do not** resolve behavioral changes automatically. Read the migration guides for your target framework/runtime and run characterization/integration tests.

### 16.1. Example: imports update cleanly yet validation stops enforcing

An old DTO:

~~~java
import javax.validation.constraints.NotBlank;

public class RegisterRequest {
    @NotBlank
    public String email;
}
~~~

After source transformation:

~~~java
import jakarta.validation.constraints.NotBlank;

public class RegisterRequest {
    @NotBlank
    public String email;
}
~~~

Compilation succeeds when Jakarta Validation API is present. However, if the runtime still only ships an older provider recognizing `javax.validation`, the new annotation may be ignored or bootstrap may fail. Choose a Jakarta-compatible provider, check framework integration, and execute real request-validation tests.

**Do not merely assert the annotation exists in bytecode**; verify invalid inputs are rejected per endpoint contracts.

### 16.2. Example: JPA compiles cleanly yet mappings fail

Code updated from `javax.persistence.Entity` to `jakarta.persistence.Entity` may compile while entity manager initialization fails because:
- The provider does not support the Jakarta Persistence version.
- `persistence.xml`/`orm.xml` schemas were not migrated.
- Runtime classpath retains an old ORM plugin.
- Envers/QueryDSL/bytecode enhancers are on mismatched versions.
- Default naming strategies, dialects, or schema generation changed.

Run queries and transaction/integration tests against a representative database. Never let migration tooling execute automatic DDL schema updates in production without a data plan.

## 17. Practical rollout: from a `javax` WAR to Jakarta Servlet 6

Suppose a legacy WAR runs on a Servlet 4 container using Java EE-style annotations and internal libraries. The target is Jakarta Servlet 6 on Tomcat 10.1 or a compatible container.

### Step 1: Capture the baseline

Record:
- Current and target JDK/runtimes.
- Servlet container/version.
- Full dependency tree and compile/runtime JARs.
- `web.xml`, TLDs, JSPs, properties, and provider metadata.
- Existing tests for URL mapping, auth/session, and filters.
- Any consumers/sidecars still relying on legacy APIs/vocabularies.

### Step 2: Update runtime dependencies

Select a compatible container and Jakarta API artifacts. Audit libraries: logging, security filters, ORM, Validation, JSON, JSP taglibs, and REST runtimes. If a library lacks a Jakarta release, decide whether to replace, upgrade, or apply bounded transformation.

### Step 3: Transform sources systematically

Run OpenRewrite/IDE refactoring to rewrite **only** Jakarta-owned `javax.*`. Keep `javax.xml.parsers`, `javax.net.ssl`, `javax.sql`, `javax.annotation.processing`, and other Java SE APIs unchanged.

### Step 4: Update descriptors and resources

Update `web.xml` and related resources for the target Jakarta Servlet version; audit class names in configs, filters, listeners, taglibs, service registries, and generated code. Do not modify schema URIs in unrelated XML files.

### Step 5: Rebuild cleanly

Use the compiler JDK and `--release` matching your runtime floor, ensuring the WAR does not redundantly bundle Servlet API JARs supplied by the container. Inspect class/JAR outputs and dependency graphs post-build.

### Step 6: Run integration tests in the target container

Verify:
- Deployment succeeds with zero missing classes.
- Servlet/filter/listener lifecycles run cleanly.
- Routes/controller mappings resolve properly.
- Authentication, authorization, sessions, and cookies behave properly.
- Request/response serialization and validation pass.
- File uploads, multipart, and async requests work.
- DB transactions/persistence function properly.
- Logging, tracing, and metrics operate cleanly.

### Step 7: Canary and rollback

If parallel running is necessary:
- Avoid sharing serialized session objects directly across both stacks.
- Enforce sticky sessions or external session formats/adapters if needed.
- Maintain API contracts for legacy consumers.
- Deploy limited canary routing while watching errors/latency.
- Ensure databases, caches, and message formats remain rollback-compatible.

### Step 8: Retire temporary transformers

If an initial phase required binary-transforming a JAR, track an owner, input version, checksum, and retirement deadline. Once the vendor ships an official Jakarta build or source is migrated, swap in the standard dependency and re-run tests.

## 18. Post-transformation verification: beyond green compilation

### 18.1. Build/runtime matrix

| Check | Required evidence |
|---|---|
| Source | No remaining Jakarta-owned `javax.*` imports outside deliberate exceptions |
| Java SE | Java SE `javax.*` packages remain intact |
| Dependencies | No mixed `javax`/`jakarta` APIs and implementations inside the same contract |
| Bytecode | Method/field descriptors and annotation references updated properly |
| Resources | `META-INF/services`, XML, properties, JSP/TLD, and generated outputs match |
| Container | Clean deployment onto the target Jakarta runtime |
| Reflection | `Class.forName`, CDI scan, ORM entity discovery, and SPIs succeed |
| Business contract | HTTP status/bodies, validation, transactions, security, and serialization pass |
| Legacy consumers | Clients/events still inside support windows communicate cleanly |
| Rollback | Session/cache/database/message state permits planned rollback |

### 18.2. Using javap to inspect descriptors

After building, inspect classes:

~~~bash
javap -classpath target/classes -p -s \
  com.example.web.HealthServlet
~~~

`-s` prints JVM descriptors, confirming method signatures. For binary-transformed JARs:

~~~bash
javap -classpath transformed.jar -verbose \
  com.example.library.SomeAdapter
~~~

Check references to `javax/servlet` or `jakarta/servlet` as intended. Even after references update, verify runtime behavior and provider compatibility.

### 18.3. Real HTTP integration tests

An HTTP contract test might assert:

~~~text
GET /health
Expect: 200
Content-Type: text/plain
Body: OK
~~~

For complex endpoints, verify filter chains, authentication, validation, headers, cookies, content negotiation, JSON formatting, and status codes. Projects using JAX-RS/JPA must include provider/transaction tests rather than stopping at a health endpoint.

### 18.4. Testing failure modes and legacy data

Test suites should cover:
- Invalid requests rejected by validation.
- Invalid tokens still denied.
- Legacy JSON/XML payloads still parsed properly.
- Session/cache state migration policies.
- Message replay from legacy releases.
- SQL transactions/rollbacks and optimistic locking.
- Plugin/provider discovery.
- Classpaths free of wrong-namespace APIs.
- Target runtime startup and shutdown.

During migration, **negative tests** around security and validation matter just as much as happy-path tests.

## 19. Explaining common failure cases

| Symptom | Cause to investigate | Resolution path |
|---|---|---|
| `ClassNotFoundException: javax.servlet...` on newer Tomcat | Artifact/dependency still uses `javax` Servlet | Upgrade library, migrate source, or apply verified transform |
| `NoClassDefFoundError: jakarta.servlet...` on older server | App compiled for Jakarta on a runtime providing only Java EE `javax` | Pick matching container version or adjust deployment strategy |
| `NoSuchMethodError` with `javax/jakarta` types | Library/consumer descriptors use different namespaces | Align entire API/implementation stack and rebuild consumers |
| CDI injection stops working | Annotations/SPI/configs unmigrated or old implementation | Check `jakarta.inject`, `beans.xml`, CDI provider |
| Bean Validation fails to trigger | `javax` provider receives `jakarta` annotations or missing integration | Upgrade provider/framework and test invalid inputs |
| EntityManager factory error | JPA provider/XML/entity enhancer mismatch | Synchronize persistence stack and mappings |
| ServiceLoader finds no provider | `META-INF/services` or module descriptor uses old names | Update metadata and inspect classloaders |
| JSP/TLD tag failures | Outdated taglibs/TLDs or dependencies | Upgrade taglib/JSP artifacts, test rendering |
| Session deserialization failures | Incompatible serialized class identities | Establish session migration/invalidation policies |
| Build regenerates `javax` imports | Outdated generator/annotation processor | Upgrade generator and regenerate sources |
| “Cannot cast javax X to jakarta X” | Two distinct types | Standardize on the same Jakarta API or bridge via data |
| “Signed JAR verification failed” | Binary transformation broke original signature | Govern provenance, re-sign per policy, or fetch upstream artifact |
| Compilation passes yet tests fail | Runtime/framework behavior changed | Run integration/contract tests and check migration guides |
| Dependency named jakarta still contains javax | Jakarta EE 8 artifact or wrong version | Inspect JAR contents and API major versions |

**Read stack traces by class and method descriptor**, not merely by JAR filename. Namespace errors can surface deep inside frameworks during lazy loading rather than at startup.

## 20. Common mistakes

- **Replacing every `javax.` string with `jakarta.`:** breaks Java SE APIs such as `javax.crypto`, `javax.xml.parsers`, or `javax.annotation.processing`.
- **Seeing groupId `jakarta` and assuming namespaces changed:** Jakarta EE 8 still uses `javax` packages.
- **Updating imports only in application sources:** dependencies, providers, containers, XMLs, and SPIs may still be `javax`.
- **Adding both Servlet API JARs to fix cast errors:** distinct class names remain incompatible in type identity.
- **Transforming a WAR and declaring it production-ready:** altered bytecode does not prove security, validation, transactions, sessions, or contracts work.
- **Transforming a signed JAR while trusting the old signature:** modified contents require proper provenance/signing policies.
- **Hand-editing generated sources:** the next build may regenerate `javax`.
- **Rewriting schema URLs via broad regexes:** every Jakarta specification has its own schema/version.
- **Skipping reflection/`ServiceLoader` testing:** static compiler checks miss dynamic metadata.
- **Adding `jakarta.*-api` without a provider:** APIs alone are not runtime implementations.
- **Upgrading JDK and renaming namespaces in one giant unbaselined diff:** makes diagnosing regressions difficult.
- **Skipping legacy consumer tests:** JSON/serialized objects/events can break contracts during coexistence.
- **Overusing binary transformers instead of official Jakarta releases:** raises maintenance and security-patching risks.
- **Failing to record tool versions/rule sets/checksums:** makes transformed artifacts irreproducible.
- **Testing only application startup:** many JPA/CDI/Validation/JMS failures trigger only along live execution paths.

## 21. Implementation checklist

- [ ] Locked target JDK, Jakarta platform/profile, and container/framework versions.
- [ ] Distinguished Java EE 8, Jakarta EE 8, and Jakarta EE 9+.
- [ ] Enumerated Jakarta-owned namespaces requiring migration.
- [ ] Preserved Java SE `javax.*` packages unchanged.
- [ ] Inventoried sources, generated code, JARs, runtime dependencies, and transitive graphs.
- [ ] Identified runtime providers/implementations for every Jakarta API.
- [ ] Selected OpenRewrite/IDE refactoring where sources are owned and rebuildable.
- [ ] If using Eclipse Transformer/Tomcat migration tool, pinned tool versions/rule sets and documented scope.
- [ ] Governed JAR signatures, checksums, licenses, SBOMs, and post-transform provenance.
- [ ] Audited class names inside reflection strings, properties, and custom metadata.
- [ ] Audited `META-INF/services`, module-info, and CDI/JPA/Validation SPIs.
- [ ] Updated XML descriptors and schemas per exact specification/version.
- [ ] Updated upstream generators or templates for generated code rather than editing outputs only.
- [ ] Confirmed no consumers directly mix `javax`/`jakarta` for the same API.
- [ ] Verified compiled bytecode and dependency graphs post-build.
- [ ] Deployed and ran integration tests on the target Jakarta runtime.
- [ ] Tested sessions, caches, serialized objects, replays, and protocol compatibility where applicable.
- [ ] Tested validation, security, CDI, ORM, transactions, endpoints, and error paths.
- [ ] Prepared rollout/rollback plans and coexistence data strategies.
- [ ] Assigned owners, versions, and retirement criteria to every temporary binary transformation.
- [ ] Documented parts missed by automation and manual changes needing ongoing maintenance.

## 22. References

- [Jakarta EE Platform 9](https://jakarta.ee/specifications/platform/9/) — the `jakarta.*` namespace milestone.
- [Jakarta EE Specifications](https://jakarta.ee/specifications/) — selecting exact specifications and API versions.
- [Jakarta Servlet 6.0](https://jakarta.ee/specifications/servlet/6.0/) — API/spec for Servlet 6.
- [OpenRewrite Recipes](https://docs.openrewrite.org/recipes) — recipe catalog and migration tooling.
- [OpenRewrite — Running Recipes](https://docs.openrewrite.org/running-recipes) — executing recipes via build tools/CLI.
- [Eclipse Transformer](https://github.com/eclipse-transformer/transformer) — binary/resource transformations and rules.
- [Apache Tomcat Jakarta EE Migration Tool](https://github.com/apache/tomcat-jakartaee-migration) — converting web-app artifacts.
- [Apache Tomcat Migration Guide](https://tomcat.apache.org/migration-10.html) — Java EE/Jakarta Servlet differences on Tomcat.
- [OpenJDK jdeps Tool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeps.html) — bytecode dependency analysis.

Reference URLs help locate product documentation. When implementing, read **documentation matching the exact versions** of the tools, Jakarta specs, containers, and frameworks your project uses; never assume commands or rule sets from another release behave identically.

## 23. Conclusion

**Migrating `javax.*` to `jakarta.*` is a migration of API identity and runtime ecosystems, not a pure text substitution.** OpenRewrite and IDEs suit structured source/build edits; Eclipse Transformer and Apache Tomcat Jakarta EE Migration Tool help when converting pre-compiled artifacts. Yet none can independently verify business contracts, reflection, providers, XML schemas, serialization, security, or rollback readiness.

The sustainable path is **selecting the right Jakarta version → inventorying sources and dependencies → applying scoped tooling → upgrading providers/containers → verifying bytecode, configs, and real behavior → retiring temporary adapters/transformers**. In particular, keep Java SE `javax.*` intact, never mix `javax`/`jakarta` types in one contract, and favor vendor-maintained Jakarta dependencies. Only when backed by build, integration, and compatibility test evidence does namespace migration become a maintainable, reliable Java/Jakarta upgrade.
