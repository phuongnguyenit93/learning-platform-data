# Changes to API dependencies, implementations, and packaging scope

When migrating an application from Java EE to Jakarta EE or upgrading the JDK, changing `import javax.*` lines to `import jakarta.*` is only part of the work. An application must also determine **which API is used to compile**, **which implementation executes at runtime**, **who supplies that implementation**, and **which libraries are actually packaged into the JAR/WAR/EAR**. Misconfiguring any of these four layers can lead to confusing failures: the IDE compiles cleanly yet WAR deployment fails, unit tests pass yet production lacks a provider, or the application bundles two conflicting API versions against the application server.

In the context of *Java Advance Compatibility Migration*, it is critical not to choose scopes out of habit. Scope depends on the **deployment model**: a full Jakarta EE application server, a servlet container, a Spring Boot executable JAR/WAR, a standalone Java SE application, or a library module consumed by another system. The same API such as Jakarta Servlet may require `provided` when deployed to a server that supplies it, whereas an executable JAR must carry an embedded servlet engine or equivalent runtime mechanism.

This lesson explains how to separate API dependencies from implementations/providers, choose Maven/Gradle scopes, transition from `javax.*` to `jakarta.*`, detect duplicate classes/providers, inspect final artifacts, and build an evidence-backed packaging strategy.

## 1. Four questions before changing dependencies

For every Java EE/Jakarta EE technology the application uses, you should be able to answer:

1. **Which API?** From which artifact does source code import public interfaces, annotations, or classes?
2. **Which implementation?** Which library or application server provides the actual runtime code and corresponding provider?
3. **Who owns the runtime?** Does the application bundle the implementation itself, or does the container supply and manage its lifecycle?
4. **Which scope?** Is the dependency needed on the compile classpath, runtime classpath, test classpath, or only in certain environments?

For example, when code calls:

```java
import jakarta.validation.Validation;
import jakarta.validation.Validator;

Validator validator = Validation
        .buildDefaultValidatorFactory()
        .getValidator();
```

`jakarta.validation-api` provides the API. However, for `buildDefaultValidatorFactory()` to locate an implementation, the runtime needs a compatible Bean Validation provider — either supplied by the server or carried by the application, such as Hibernate Validator in an appropriate stack. Having only the API JAR is usually insufficient.

Another example:

```java
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
```

The `HttpServlet` class belongs to the Servlet API, yet the code above does not create an HTTP server on its own. A Jakarta EE server, servlet container, or embedded container/framework must manage listeners, request dispatch, sessions, and servlet lifecycles.

**Having the API on the compile classpath does not prove an implementation will exist upon deployment.**

## 2. Java EE and Jakarta EE: changing namespaces is a binary type change

### 2.1. From `javax.*` to `jakarta.*`

Java EE previously used many `javax.*` packages. Jakarta EE 8 preserved many `javax.*` packages to maintain compatibility during the transition; **Jakarta EE 9** moved many enterprise APIs to the `jakarta.*` namespace.

Examples:

| Technology | Old package | New package |
|---|---|---|
| Servlet | `javax.servlet.*` | `jakarta.servlet.*` |
| Persistence/JPA | `javax.persistence.*` | `jakarta.persistence.*` |
| Bean Validation | `javax.validation.*` | `jakarta.validation.*` |
| CDI | `javax.enterprise.*` | `jakarta.enterprise.*` |
| JAX-RS | `javax.ws.rs.*` | `jakarta.ws.rs.*` |
| JAXB | `javax.xml.bind.*` | `jakarta.xml.bind.*` |
| JAX-WS | `javax.xml.ws.*` | `jakarta.xml.ws.*` |
| Activation | `javax.activation.*` | `jakarta.activation.*` |
| Transaction/JTA | `javax.transaction.*` | `jakarta.transaction.*` |
| Common Annotations | `javax.annotation.*` | `jakarta.annotation.*` |

The fully qualified names `javax.servlet.http.HttpServlet` and `jakarta.servlet.http.HttpServlet` are **two different binary names**. The JVM does not map them to each other. A framework compiled to look for `jakarta.servlet.Filter` cannot automatically use an implementation that only implements `javax.servlet.Filter`.

Changing namespaces is therefore an **API/binary compatibility change**, not a cosmetic import rename.

### 2.2. Do not mechanically rename every `javax.*`

Not all `javax.*` packages belong to Java EE and move to Jakarta. Several Java SE APIs retain their old names, for example:

- `javax.net.ssl.*`.
- `javax.crypto.*`.
- `javax.xml.parsers.*`, `javax.xml.transform.*`.
- `javax.sql.*`.
- `javax.naming.*`.

These APIs must be treated per JDK/Java SE contracts. Blindly replacing every `javax.` with `jakarta.` via string find-and-replace will cause errors and break valid code.

### 2.3. Artifact names do not always indicate the package

During the transition period, some artifacts carry `jakarta` in their name or groupId while older versions still contain `javax.*` packages. Do not decide namespaces solely from Maven artifact names.

When selecting versions, inspect:

- Documentation/version lines of the Jakarta EE specification and implementation.
- Actual classes inside the JAR.
- Framework major versions.
- Generated code and annotations.
- APIs officially declared as supported by the server/runtime.

A stack often has generational boundaries: 2.x JAXB/JAX-WS API branches primarily use `javax`, while newer branches use `jakarta`. However, exact version matrices must be confirmed for each specific artifact.

## 3. Where do API, implementation, provider, and container differ?

### 3.1. API artifacts

An API artifact contains the contracts used by developers: interfaces, annotations, exceptions, common types, and sometimes factory/delegation classes.

Examples:

```text
jakarta.servlet:jakarta.servlet-api
jakarta.persistence:jakarta.persistence-api
jakarta.validation:jakarta.validation-api
jakarta.ws.rs:jakarta.ws.rs-api
jakarta.enterprise:jakarta.enterprise.cdi-api
jakarta.xml.bind:jakarta.xml.bind-api
```

These artifacts allow code to compile, yet do not necessarily implement the full contract.

### 3.2. Implementation artifacts

Implementations supply real behavior. Examples:

| Technology | API | Common runtimes/implementations |
|---|---|---|
| Servlet | `jakarta.servlet-api` | Tomcat, Jetty, Undertow, or a Jakarta EE server |
| Persistence | `jakarta.persistence-api` | Hibernate ORM, EclipseLink, or server provider |
| Bean Validation | `jakarta.validation-api` | Hibernate Validator or compatible provider |
| JAX-RS | `jakarta.ws.rs-api` | Jersey, RESTEasy, Apache CXF, or server |
| CDI | `jakarta.enterprise.cdi-api` | Weld, OpenWebBeans, or server |
| JAXB | `jakarta.xml.bind-api` | GlassFish JAXB Runtime or compatible provider |
| JAX-WS | `jakarta.xml.ws-api` | Metro, CXF, or server |
| Activation | `jakarta.activation-api` | Angus Activation or matching provider |
| Transaction | `jakarta.transaction-api` | Container transaction manager/runtime or dedicated stack |

The implementations listed are common examples; they are not blindly interchangeable without verifying configuration. An application server typically integrates providers alongside lifecycle management, transaction boundaries, and classloading policies.

### 3.3. Provider discovery

Several APIs locate implementations via the service-provider mechanism, framework configuration, or API factories. For example, Bean Validation, JAXB, JAX-RS client/runtime, and other Java EE stacks may use provider discovery.

If only the API is present:

- The compiler still recognizes the interfaces.
- The class loader may load API classes.
- Errors may surface only when invoking factories or initializing services.

Common symptoms include failing to find a provider, `ServiceConfigurationError`, `NoProviderFoundException`, `JAXBException`, or framework startup failures.

Conversely, if **multiple competing providers** are present, behavior also depends on provider selection mechanisms, class loaders, ServiceLoader metadata, and configuration. Do not assume "more implementations are safer."

### 3.4. Containers provide both APIs and operational behavior

A Jakarta EE application server can supply multiple specification implementations, managing:

- Servlet lifecycle, request routing, and threading.
- Dependency injection/CDI.
- Transactions and persistence contexts.
- JNDI resources and connection pools.
- Security, authentication/authorization.
- REST endpoint dispatch and validation.
- Messaging and other platform services.

A minimal servlet container like Tomcat/Jetty **is not equivalent** to a full Jakarta EE application server. It typically provides Servlet and a few related technologies at its supported container level, rather than supplying full JPA, CDI, JAX-RS, EJB, messaging, or Bean Validation by default.

Hence the same `WAR` running on a full Jakarta EE server may need a different dependency scope than a WAR running on a servlet container.

## 4. Maven scopes: compile, provided, runtime, test

### 4.1. Scopes govern classpaths and transitivity

Maven provides common scopes:

| Scope | Compile classpath | Project runtime classpath | Test classpath | Packaging meaning |
|---|---|---|---|---|
| `compile` (default) | Yes | Yes | Yes | Dependency needed by the application and typically packaged into WAR if applicable |
| `provided` | Yes | Not treated by Maven as a standard runtime dependency | Yes | Expected to be supplied by runtime/container; omitted from `WEB-INF/lib` in standard WAR packaging |
| `runtime` | Not directly for main compilation | Yes | Yes | Library needed only at runtime; typically goes into WAR if applicable |
| `test` | Not for main compilation | No | Yes | Test only |
| `system` | Legacy mechanism relying on local paths | Hard to reproduce | Context-dependent | Should be avoided since artifacts are not managed via normal repositories |
| `import` | Not an application dependency | No | No | Used only for `pom`-type BOMs inside `dependencyManagement` |

The "packaging" column also depends on plugins and packaging types. For instance, the default jar plugin creates a thin JAR without embedding every `compile`/`runtime` dependency; the WAR plugin typically packages matching dependencies into `WEB-INF/lib`.

Do not treat scope as a single command forcing every packaging plugin on the market to behave identically.

### 4.2. Example: Servlet API supplied by the container

```xml
<dependencies>
    <dependency>
        <groupId>jakarta.servlet</groupId>
        <artifactId>jakarta.servlet-api</artifactId>
        <version>${servlet.api.version}</version>
        <scope>provided</scope>
    </dependency>
</dependencies>
```

This is typical if the WAR deploys onto a server/container **that genuinely provides the same generation of Jakarta Servlet API**.

Implications:

1. Source compiles against `HttpServlet`.
2. Test classpath can have the API per Maven scope.
3. The WAR artifact does not need—and generally should not carry—its own Servlet API copy.
4. The runtime server must supply the matching API/implementation.

If deploying the WAR onto a container still using `javax.servlet.*`, `provided` scope will not make Jakarta APIs materialize. The application will be incompatible with the target container and may fail to deploy.

### 4.3. API needed at compile time, implementation packaged by the application

Suppose a Java SE application wants to use Jakarta JAXB:

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

The API resides on compile/runtime for the application; the runtime provider is declared under `runtime` if code does not directly call implementation APIs. Still, a default thin JAR requires a mechanism to place both onto the runtime classpath, such as a distribution, lib directory, container image, or packaging plugin.

Placeholder versions must be selected according to compatible `jakarta` generations and the project's vendor/platform BOM. Do not arbitrarily combine an API version with a runtime version and assume they match.

### 4.4. Optional does not replace provided

Maven `<optional>true</optional>` is typically used to prevent a dependency from propagating automatically to downstream consumers. It is **not equivalent** to `provided` and does not mean the application runtime will supply that dependency.

If a library uses an optional driver/protocol, optional may fit the library module; yet the executable application must still declare the module it selects. When a server supplies an API, `provided` reflects traditional application compile-only packaging intent.

## 5. Gradle scopes: implementation, compileOnly, runtimeOnly, and provided

### 5.1. Basic configurations

In a Java or Java Library project:

| Gradle configuration | Main compile | Main runtime | Typical meaning |
|---|---|---|---|
| `implementation` | Yes | Yes | Internal dependency used by the project at both compile and runtime |
| `api` with `java-library` | Yes | Yes | Dependency exposed in the public API for consumer compilation |
| `compileOnly` | Yes | No | API needed only to compile; runtime supplied elsewhere |
| `runtimeOnly` | No | Yes | Runtime provider/driver/plugin not referenced directly from source |
| `testImplementation` | Test compilation | Test runtime | Dependency for tests |
| `testRuntimeOnly` | Not a test compilation dependency | Test runtime | Test engine/provider needed only when executing tests |

Depending on plugins and Gradle versions, additional configurations exist. Do not translate Maven scopes to Gradle mechanically by swapping names without reviewing packaging and publication.

### 5.2. Gradle WAR and provided configurations

When applying the `war` plugin, Gradle provides dedicated configurations such as `providedCompile` and `providedRuntime` to express dependencies supplied by the container upon WAR deployment.

Groovy DSL example:

```groovy
plugins {
    id "war"
}

dependencies {
    providedCompile(
        "jakarta.servlet:jakarta.servlet-api:${servletApiVersion}"
    )

    implementation(
        "org.glassfish.jersey.containers:jersey-container-servlet:${jerseyVersion}"
    )
}
```

This example illustrates a **WAR deployed to a Jakarta-compatible servlet container**: the container supplies the Servlet API, while the application carries the Jersey/JAX-RS implementation if the container does not supply JAX-RS. Check transitive dependencies and required Jersey modules for your specific stack.

Do not use this example as a fixed configuration for a full Jakarta EE server with its own JAX-RS provider. If the server supplies JAX-RS, bundling Jersey too can create provider conflicts or altered behavior.

### 5.3. compileOnly and the test classpath

Example:

```groovy
plugins {
    id "java"
}

dependencies {
    compileOnly(
        "jakarta.servlet:jakarta.servlet-api:${servletApiVersion}"
    )
}
```

`compileOnly` does not mean the API automatically appears in test compilation/runtime configurations across all setups. If tests need direct access to those types or launch a servlet container, configure appropriate test dependencies/test runtimes separately.

For example, tests starting an embedded servlet container need an implementation to execute, not just the Servlet API. Conversely, unit tests using mock requests/responses may only require the API and a mocking library.

### 5.4. api and public signatures of reusable libraries

With the `java-library` plugin, `api` exposes dependencies appearing in a library's public API so consumers can compile against them. However, using `api` with Jakarta APIs may also pull in runtime dependencies depending on the dependency metadata model.

If a library only needs an API to compile and intends consumers to pick their own container, design appropriate publication metadata. Gradle versions supporting `compileOnlyApi` address the use case "API exposed in public signatures yet not provided at runtime." This mechanism is useful where supported, though actual publication and Maven/Gradle consumers should be verified.

Do not choose `implementation`, `api`, or `compileOnly` purely to make code compile. Consider whether consumers need the type at compile time, who supplies it at runtime, and whether published metadata conveys that intent accurately.

### 5.5. Distinguishing BOMs/platforms from scope

Gradle:

```groovy
dependencies {
    implementation platform(
        "com.example.platform:example-dependencies:1.0.0"
    )

    implementation "com.example:example-client"
}
```

A platform manages version constraints; it **does not decide** whether a dependency belongs in `compileOnly`, `runtimeOnly`, or `providedCompile`. Similarly, Maven `dependencyManagement` does not bundle implementations by itself.

To manage Java EE/Jakarta dependencies correctly, decide both the **version family** and the **deployment-model scope**.

## 6. Model A: WAR/EAR on a Jakarta EE application server

### 6.1. The server owns platform APIs and implementations

Suppose an application deploys onto a Jakarta EE server verified to support the matching profile/specification version. The server can supply Servlet, CDI, JPA, JTA, Bean Validation, JAX-RS, or other capabilities per its profile and configuration.

In that case, the application can compile against platform APIs and **omit server-provided APIs/platform implementations from its package**.

Maven:

```xml
<packaging>war</packaging>

<dependencies>
    <dependency>
        <groupId>jakarta.platform</groupId>
        <artifactId>jakarta.jakartaee-api</artifactId>
        <version>${jakarta.ee.version}</version>
        <scope>provided</scope>
    </dependency>
</dependencies>
```

This is a general example for applications targeting compatible Jakarta EE servers. Avoid declaring the umbrella API if the application only uses a small subset of specifications, or if the actual server only supports a narrower profile. Compiling against the full API does not prove the server provides all of those APIs.

### 6.2. Do not unintentionally bundle duplicate providers with the server

Suppose the server already provides a JPA provider and transaction manager. If the application also adds `hibernate-core`, another JPA API JAR, and a transaction implementation to `WEB-INF/lib`, risks include:

- Two providers or two API versions across different class loaders.
- The server picking a different provider than intended by the application.
- The application's provider failing to integrate properly with server-managed transactions/data sources.
- `ClassCastException`, `LinkageError`, or `NoSuchMethodError`.
- Persistence context/lazy-loading behavior diverging from baseline.

There is no absolute rule that "every implementation inside a WAR is wrong": some servers let applications supply their own providers with proper classloading and integration configs. However, this must be a documented decision, not an accidental side effect of the dependency graph.

### 6.3. Check the real server profile

"Jakarta EE compatible" is version- and profile-specific. A server supporting Web Profile or a particular specification subset might not supply the entire full-platform API set. Inspect:

- Server vendor/version.
- Jakarta EE platform/profile version.
- Servlet/JPA/CDI/Validation/JAX-RS spec levels.
- Actual providers, classloading policies, and deployment descriptors.
- Resource configurations such as data sources, transaction managers, and security.

If an application compiles against a newer Jakarta EE API generation than the server supports, using `provided` merely hides the missing dependency at build time without fixing the deployment mismatch.

## 7. Model B: WAR on a servlet container

### 7.1. A servlet container is not a full Jakarta EE platform

Consider an application deploying to a Jakarta-generation Tomcat or Jetty. The container supplies the Servlet API and engine, yet does not automatically provide full CDI/JPA/JAX-RS/Bean Validation depending on product/version.

An application needing JAX-RS or JPA may have to package the corresponding implementations.

Illustrative Maven snippet:

```xml
<packaging>war</packaging>

<dependencies>
    <!-- Container provides Servlet API -->
    <dependency>
        <groupId>jakarta.servlet</groupId>
        <artifactId>jakarta.servlet-api</artifactId>
        <version>${servlet.api.version}</version>
        <scope>provided</scope>
    </dependency>

    <!-- Example where the application bundles JAX-RS runtime -->
    <dependency>
        <groupId>org.glassfish.jersey.containers</groupId>
        <artifactId>jersey-container-servlet</artifactId>
        <version>${jersey.version}</version>
    </dependency>
</dependencies>
```

The Jersey version and companion modules must match the Servlet version/container. If a JAX-RS library pulls a transitive dependency on Servlet API, inspect the packaged WAR to avoid unwanted APIs or conflicts.

### 7.2. Choosing scope based on each service's owner

| Technology | Usually supplied by servlet container? | If the application needs it |
|---|---|---|
| Servlet API/engine | Yes, per container version | API `provided`; do not bundle a duplicate servlet engine |
| JPA provider | Not by default | Package the provider yourself/supply external service runtime |
| CDI | Not by default | Choose a CDI implementation and integration |
| JAX-RS | Not by default | Choose Jersey/RESTEasy/CXF or framework |
| Bean Validation | Not by default | Choose an appropriate provider and dependencies |
| JAXB/JAX-WS | Not by default merely because it is a servlet container | Supply the corresponding API/runtime/tools when needed |
| JTA transaction manager | Not necessarily like a full Jakarta EE server | Use a transaction stack supported by the framework |

These are general principles. Extended servlet container distributions or companion frameworks may supply some of these technologies; always verify the actual runtime.

### 7.3. Common pitfalls

A WAR on a servlet container includes `jakarta.persistence-api` yet lacks a Hibernate/EclipseLink provider. Code compiles, yet creating `EntityManagerFactory` fails. This is not a "missing API version" issue, but a **missing implementation or bootstrap configuration**.

Similarly, having `jakarta.validation-api` without a Bean Validation provider leads to provider-lookup failures. Add the runtime implementation or move to an environment providing it.

## 8. Model C: Executable JAR with embedded runtime

### 8.1. The application owns its runtime

An executable JAR such as Spring Boot or an embedded framework typically packages the servlet engine, JSON stack, validation, JPA provider, and other libraries depending on selected starters/modules.

For a Spring Boot embedded web app, a typical dependency is:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
```

Versions and dependency management are handled by the appropriate framework/parent/BOM. The web starter usually brings the embedded servlet runtime under the stack's default configuration.

If a developer changes the Servlet engine/runtime dependency to `provided` without an external container, the executable JAR may miss classes at runtime. Conversely, attempting to bundle a standalone server plus incompatible server libraries into the JAR can cause classpath conflicts.

### 8.2. Do not overuse the umbrella Jakarta EE API

An executable JAR should not simply add `jakarta.jakartaee-api` in `compile` scope expecting every platform technology to materialize. An umbrella API creates no CDI container, transaction manager, JPA provider, or SOAP runtime.

A better approach is using **starters/modules/providers recommended by the framework** for actual needed capabilities, letting the framework align APIs and implementations.

### 8.3. Framework WARs have specialized packaging rules

Some frameworks can build executable WARs that run both standalone and deployed on servlet containers, using dedicated library regions or `providedRuntime` for the embedded server. For example, in Spring Boot Gradle WAR packaging, the Tomcat starter may be placed in `providedRuntime` per that framework version's guide.

Verify the real artifact and deployment workflow supported by the framework. Do not generalize traditional servlet-container WAR rules to every executable WAR.

## 9. Model D: Java SE applications, batch jobs, and CLIs

### 9.1. No implicit Jakarta EE container

A CLI or batch service launched with:

```bash
java -jar migration-tool.jar
```

does not automatically include CDI, Bean Validation, JPA, JAXB, or JAX-WS runtimes unless packaged or supplied on the classpath/module path.

Example data tool using JAXB:

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

If creating a thin JAR, provide a distribution/lib directory, launcher classpath, or packaging mechanism so runtime finds both API and provider. Running `mvn package` to build a JAR does not automatically embed dependencies inside the JAR.

### 9.2. JDK 11 removed previously bundled APIs

JEP 320 removed JDK-bundled Java EE/CORBA modules—including JAXB, JAX-WS, Activation, and related tools—starting in **JDK 11**. When upgrading from JDK 8 to 17/21, applications that previously relied on them from the JDK must manage external dependencies themselves.

However, do not assume every Jakarta API used to ship with the JDK. Servlet, CDI, JPA, and JAX-RS were never services universally built into every Java SE JDK.

Errors such as:

```text
package javax.xml.bind does not exist
NoClassDefFoundError: javax/activation/DataHandler
```

must be classified: missing API on the compile classpath, missing implementation/runtime, or namespace mismatch. Adding an arbitrary API JAR will not fix all three.

## 10. Scopes for reusable libraries differ from application scopes

### 10.1. Public APIs exposing Jakarta types

Suppose a shared SDK declares:

```java
package com.example.sdk;

public interface RequestCustomizer {
    void customize(jakarta.servlet.http.HttpServletRequest request);
}
```

Consumers compiling sources against `RequestCustomizer` may need access to `HttpServletRequest` to resolve signatures. If the SDK uses Maven `provided` for the Servlet API, that dependency is not propagated as an ordinary runtime/compile dependency to every consumer. Consumers must declare an appropriate API themselves or obtain it via their platform/framework.

If a Gradle library uses `compileOnly`, the type is usually not published automatically as an API dependency for consumers. On Gradle releases supporting it, `compileOnlyApi` can better represent a compile-time public surface excluded from runtime, though published metadata and real consumers must still be verified.

### 10.2. Do not force consumers to carry the SDK's provider

An SDK exposing only JPA/JAX-RS interfaces should not inadvertently lock every consumer onto a specific implementation when the architecture expects the application server to choose the provider.

Conversely, if the SDK performs serialization through a mandatory provider, document its runtime dependency and support terms explicitly. The difference lies in the SDK's contract, not merely artifact names.

### 10.3. API compile compatibility does not replace the runtime contract

Suppose an SDK compiles against Jakarta EE 10 APIs while a consumer deploys onto a server running a lower Jakarta EE version. The SDK can still publish successfully; errors arise when the consumer compiles or deploys.

Library publishers should document:

- Minimum JDK and class-file target.
- Required Jakarta API/specification level.
- Published dependency scopes.
- Which API implementations must be supplied by the consumer/container.
- Tested server/framework matrix.
- `javax`/`jakarta` compatibility and current limitations.

## 11. Scope changes can break an application even without changing versions

### 11.1. From compile to provided

Changing a Maven dependency from:

```xml
<scope>compile</scope>
```

to:

```xml
<scope>provided</scope>
```

can avoid bundling the Servlet API into the WAR when the server supplies it. However, if the same artifact runs as a standalone Java application, runtime will lack that dependency unless supplied another way.

**Changing scope is a deployment change**, not merely POM cleanup.

### 11.2. From provided to compile

Switching to `compile` can cause the WAR to start carrying APIs/implementations already supplied by the server. On several servers, this causes class loader or provider conflicts.

The build command may pass because the project classpath is complete, while server deployment reveals the error. Inspect WAR contents before and after.

### 11.3. Runtime provider only, missing compile API

If source directly calls an API yet the dependency sits only in `runtime`/`runtimeOnly` with no API supplied elsewhere, the compiler reports missing packages. The API must exist on the compile classpath (via a direct dependency or another permitted dependency) and the provider at runtime.

### 11.4. Compile API only, missing runtime provider

This is the most common Java EE/Jakarta failure when moving from a full server to a servlet container or CLI. Code compiles yet factory initialization fails. The fix is identifying the runtime owner and supplying a compatible implementation, not just changing the API version.

## 12. Class loading and duplicate classes inside a server

### 12.1. Container classloaders differ from application classloaders

In a WAR/EAR, the server usually has class loaders supplying platform APIs and implementations; the application has class loaders loading `WEB-INF/classes` and `WEB-INF/lib`. Precedence and isolation rules depend on server/version/config.

If the same class or package appears in multiple places, you may encounter:

- API loaded from the server, provider from the application.
- A provider library compiled against a different API version.
- Two classes with the same binary name defined by different class loaders.
- Mismatched method signatures/type identities.
- SPI/provider registration discovering a class that cannot cast to the active interface.

In the JVM, **class identity consists of both binary name and defining class loader**. Sharing a class name across different defining loaders does not make them the same type.

### 12.2. Do not look only at the dependency tree

The build tool only knows the graph it resolves. It does not necessarily know about JARs placed by the server in global library folders, domain configurations, shared lib directories, or separate class loaders.

Therefore inspect:

1. Dependency tree/build graph.
2. Actual files inside the WAR/JAR/EAR.
3. JARs/modules provided by the server.
4. Server class loader policies.
5. Runtime class-loading sources when necessary.

On modern JDKs, JVM class-loading logs can be enabled in appropriate environments, for example:

```bash
java -Xlog:class+load=info -jar app.jar
```

For servers, configure JVM logging via server-supported startup mechanisms. Logs can be very large, so enable them only in controlled investigation sessions.

### 12.3. Linkage errors differ from dependency resolution errors

- `ClassNotFoundException`: usually appears when code/frameworks try loading a class by name and fail to find it.
- `NoClassDefFoundError`: the JVM needs a class at runtime yet it is absent or cannot be loaded as required.
- `NoSuchMethodError`: the runtime class lacks the method descriptor expected by bytecode callers.
- `AbstractMethodError`: an implementation does not satisfy a required method during dispatch.
- `ClassCastException`: an object does not match the target cast type, including across differing classloaders.
- `ServiceConfigurationError`: invalid provider discovery or initialization.
- `IllegalAccessError` or module access errors: class/member cannot be accessed under runtime rules.

These errors do not prove "JAR X is missing" from the message alone. Trace back dependency versions, binary names, classloaders, and failure timing.

## 13. Inspecting artifacts: what is inside WAR, JAR, and EAR?

### 13.1. Traditional WARs

A WAR typically has the structure:

```text
application.war
├── WEB-INF/
│   ├── classes/
│   ├── lib/
│   │   ├── application-library.jar
│   │   └── provider-runtime.jar
│   └── web.xml       (if used)
└── ...
```

For WARs deployed to a server, know which dependencies should and **should not** live inside `WEB-INF/lib`.

For example, the container-provided Servlet API normally does not belong there. An application-selected JPA provider may need to be there if the container does not supply one, though additional dependencies and integrations must be managed.

### 13.2. Inspecting with archive tools

Reference commands:

```bash
jar tf build/libs/application.war
jar tf target/application.war

jar tf target/application.war | grep "WEB-INF/lib"
```

On Windows PowerShell, `Select-String` can be used instead of `grep`. These commands only illustrate the workflow; use actual artifact names from your build.

Minimum checks:

- Runtime providers required from application packaging are present.
- Server-supplied APIs/providers are not accidentally duplicated.
- Conflicting versions of the same library family are absent.
- `META-INF/services` or provider service metadata are present.
- Generated classes, resources, and deployment descriptors are complete.
- Test-only or build-only libraries/tools are absent from production artifacts.

### 13.3. Thin JARs and fat JARs

JARs built by the Maven jar plugin normally do not embed all transitive runtime dependencies. A fat JAR/uber-JAR or framework-built executable JAR can bundle them into one artifact, though internal layout varies by plugin.

When switching from a multi-JAR classpath launch command to `java -jar`, confirm that providers and libraries are discovered. Having the same scope does not mean every packaging mode yields the same runtime graph.

### 13.4. Shading and ServiceLoader

Shading can merge/relocate classes yet strip `META-INF/services` files if plugins fail to merge properly. API/implementation JARs are present, yet provider discovery still fails.

Do not arbitrarily relocate `jakarta.*` or `javax.*` API packages to "avoid conflicts": frameworks and containers look up exact standard binary names. A relocated API is no longer the contract expected by the platform.

## 14. BOMs, platforms, and version matrices do not decide scope

### 14.1. BOMs manage versions, not runtime presence automatically

Maven example:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example.platform</groupId>
            <artifactId>example-bom</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

A BOM typically manages dependency versions under Maven rules. It does not place `jakarta.validation-api` or a Bean Validation provider onto runtime by itself; the application must still declare dependencies and proper scopes.

### 14.2. Gradle platforms behave similarly

```groovy
dependencies {
    implementation platform(
        "com.example.platform:example-bom:1.0.0"
    )

    compileOnly "jakarta.servlet:jakarta.servlet-api"
}
```

Platforms supply version constraints when the BOM manages that module, yet do not turn `compileOnly` into a runtime dependency. Ensure versions exist via platform/constraints or explicit declarations. The `example-bom` artifact here is purely hypothetical.

### 14.3. Choosing framework-supported version sets

A system may need to align:

- Jakarta Servlet API and container.
- JPA API/provider/transaction integration.
- Bean Validation API/provider and expression language dependencies if needed.
- JAX-RS API/runtime.
- JAXB/JAX-WS/Activation API/runtime/tools.
- CDI API/implementation and extensions.
- Spring/Jakarta EE/framework versions.
- Minimum JDK and class-file target.

Version numbers do not have to match identically; what matters is a **vendor/framework-supported and verified compatibility matrix**.

## 15. How to migrate from javax to jakarta at the dependency layer

### 15.1. Capture a real baseline

Before changing anything:

- Record JDK vendor/version, build tool, and framework.
- Record runtime owner: full Jakarta EE server, servlet container, or embedded.
- Save Maven/Gradle dependency trees, plugin versions, and artifact contents.
- Record the application server version/profile.
- Inventory generated sources and compile-time annotations.
- Save contract integration tests and existing runtime errors.

Do not rely on IDE build success as your sole baseline.

### 15.2. Choose the target before rewriting namespaces

Three common scenarios:

**Scenario 1 — Keep Java EE/Javax:** Upgrade the JDK while keeping supported `javax.*` frameworks/containers. Use `javax`-compatible APIs/implementations; for JAXB/JAX-WS/Activation on JDK 11+, supply external dependencies where needed.

**Scenario 2 — Move entirely to Jakarta:** Upgrade containers/frameworks/runtimes and dependencies to the `jakarta.*` generation. Sources, generated sources, annotations, configs, and extensions must transition together.

**Scenario 3 — Intentional coexistence of both:** Some modules/integrations still depend on `javax` while new parts use `jakarta`. Establish clear boundaries, adapters, or separate processes/modules; never assume the two namespaces implement the same interfaces.

### 15.3. Inventory sources and API signatures

Search for:

```text
javax.servlet
javax.persistence
javax.validation
javax.ws.rs
javax.enterprise
javax.xml.bind
javax.xml.ws
javax.activation
javax.transaction
javax.annotation
```

At the same time, search for `jakarta.*` and inspect where both mix. Audit public method signatures, generated bytecode, annotation processors, ORM metadata, and resource/service configurations.

### 15.4. Upgrade the runtime owner before setting provided

If the deployment target remains a `javax.servlet` container, switching source code to `jakarta.servlet` and marking it `provided` will not conjure a Jakarta container. The container must be upgraded to a compatible version, or a different migration plan chosen.

Conversely, if the application becomes an executable JAR with an embedded runtime, an API previously marked `provided` may need to be included through new framework starters/runtime dependencies.

**Scopes must reflect post-migration infrastructure**, not legacy infrastructure.

### 15.5. Swap APIs and implementations as matched sets

JPA example:

- Switch `javax.persistence.*` to `jakarta.persistence.*` when required by the target framework.
- Use the matching generation of `jakarta.persistence-api`.
- Pick a compatible Hibernate/EclipseLink provider.
- Verify transaction/connection-pool integration.
- Run DDL/mapping/lazy-loading and transaction tests.

Bean Validation example:

- Use `jakarta.validation-api` alongside an appropriate provider.
- Update `@NotNull`/`@Valid` annotations to the right namespace.
- Check validation interception and error mapping.
- Check provider discovery and related extensions.

JAX-RS example:

- Use `jakarta.ws.rs-api`.
- Ensure a compatible JAX-RS container/provider exists.
- Check resource registration, filters/interceptors, and serializers.
- Run HTTP contract tests against a real deployment.

### 15.6. Verify versions and scopes module by module

A test module might use `jakarta` APIs while the production artifact still packages a `javax` JAR via a transitive library. A library module might hide a provider dependency in `test` scope so unit tests pass while consumer runtimes fail.

Inspect every compile/runtime/test configuration and how final packages are built, not merely the root POM or Gradle build file.

## 16. Maven verification workflow

### 16.1. Effective POM and dependency graph

Reference commands:

```bash
./mvnw -version
./mvnw help:effective-pom
./mvnw dependency:tree
./mvnw dependency:tree -Dscope=runtime
```

From the output, record:

- Which API version is selected?
- Is the scope `compile`, `provided`, or `runtime`?
- Does the implementation/provider come from a direct or transitive dependency?
- Which BOM/parent manages the version?
- Are dependencies overridden/excluded?
- What will WAR/JAR/shade plugins package?

Do not assume every version of `dependency:tree` displays scopes/conflicts identically; record the plugin version if reports require comparison.

### 16.2. Inspecting the WAR artifact

After building in an authorized pipeline, list WAR contents:

```bash
jar tf target/application.war
```

Compare against packaging policy:

- Is a server-supplied Servlet API present inside the WAR?
- Are JPA/CDI/Validation/JAX-RS providers packaged properly?
- Do any packaged Jakarta APIs duplicate server libraries?
- Did test-only libraries leak into production?

If the organization uses EARs, inspect `EAR/lib`, each WAR module, and server classloading policies.

### 16.3. Separating plugin scope

Maven `dependencyManagement` and project dependencies do not directly govern plugin realm dependencies. Compilers, code generators, test runners, and packaging plugins require separate versions and plugin dependencies when needed.

For instance, an XML codegen plugin failing to locate a class at build time may be a plugin-realm issue rather than a missing implementation in the application's `WEB-INF/lib`.

## 17. Gradle verification workflow

### 17.1. Checking specific configurations

Reference commands:

```bash
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencies --configuration testRuntimeClasspath
./gradlew :app:dependencyInsight \
    --dependency jakarta.servlet-api \
    --configuration runtimeClasspath
```

Replace `:app` with your real module and use matching shell syntax. With the WAR plugin, check `providedCompile`/`providedRuntime` alongside the WAR output. With custom packaging, inspect task/plugin configs rather than inferring from `runtimeClasspath` alone.

### 17.2. Locating resolved dependencies

`dependencyInsight` shows version selection reasons, constraints/platforms, and dependency paths. Even if a provider enters via two paths and Gradle picks one version, still inspect the final artifact for embedded/shaded copies or conflicting server-provided versions.

### 17.3. Do not equate buildscripts/plugins with the application

A Gradle plugin might depend on JAXB, validation, or HTTP libraries to **generate sources**. That does not mean the application runtime has those dependencies. Conversely, application runtime providers do not automatically appear in plugin classpaths.

Build logic, annotation processors, test engines, and application runtimes are separate graphs. Manage scope intentionally per graph.

## 18. Common migration errors

| Symptom | Likely cause | Check step |
|---|---|---|
| `package jakarta.servlet does not exist` | Missing API on compile classpath | Check direct dependencies, scope, BOM, and project modules |
| `ClassNotFoundException: jakarta.servlet...` | Running outside Jakarta servlet runtime or wrong packaging | Check deployment model and container version |
| Server fails to deploy Servlet/Filter | Jakarta WAR running on a `javax` server or mismatched descriptor | Check container Jakarta generation |
| Bean Validation `NoProviderFoundException` | API only, missing provider or broken provider discovery | Check runtime implementation JAR and service metadata |
| `JAXBException` missing runtime | API present yet missing JAXB provider | Check runtime graph and namespace |
| JPA fails to build `EntityManagerFactory` | Missing provider or broken transaction/data-source config | Check provider and container ownership |
| REST endpoints return 404 after deploy | JAX-RS provider/resource registration inactive | Inspect servlet/provider registration and scanning |
| `NoSuchMethodError` on Jakarta classes | API/provider version mismatch | Inspect runtime class loading and resolved versions |
| `ClassCastException` between provider types | Class loader isolation or differing API generations | Inspect defining class loaders and artifact sources |
| WAR contains multiple servlet API JARs | Wrong scope or transitive dependency | Inspect `WEB-INF/lib` and exclusions |
| Tests pass yet WAR fails | Test runtime has a different provider than the server | Test the real artifact on the target server |
| Executable JAR reports missing Servlet/JPA runtime | Dependencies wrongly set to `provided`/`compileOnly` | Check embedded runtime packaging |
| `ServiceConfigurationError` | Invalid provider/service descriptor or stripped during shading | Check `META-INF/services` and provider version |
| `UnsupportedClassVersionError` | A dependency uses a higher class-file version than runtime | Compare minimum JDK and target |
| `InaccessibleObjectException`/module access | Mismatched reflection/module policy | Inspect JPMS, `opens`, and framework version |

This table offers investigative hints, not deterministic diagnoses from exception names alone. Use stack traces, dependency graphs, classpaths, and server logs to pinpoint root causes.

## 19. Defining a useful compatibility matrix

A multi-module system needs a clear table showing **who supplies APIs and implementations**, not just a list of versions.

| Component | API namespace | API compile scope | Implementation owner | Package in artifact? | Target runtime |
|---|---|---|---|---|---|
| Servlet | `jakarta.servlet` | `provided` | Servlet container | Do not package duplicate Servlet API/engine | Jakarta servlet container |
| JAX-RS | `jakarta.ws.rs` | Per API exposure | Application (Jersey) | Yes, if container lacks it | Servlet container |
| JPA | `jakarta.persistence` | Provided or compile per model | Full EE server or app/provider | Per owner | Server/embedded |
| Bean Validation | `jakarta.validation` | Per API exposure | Container or app | Per owner | Server/embedded |
| JAXB | `jakarta.xml.bind` | Compile | Application | Yes if standalone needs it | Java SE CLI |
| Transaction | `jakarta.transaction` | Provided or compile per model | Container/transaction framework | Per owner | Server/embedded |

Values in the table illustrate different models, not a single deployment. For real projects, add artifact coordinates, versions, server/framework versions, owners, and test evidence.

### 19.1. Environment-by-environment matrix

Build scopes may stay constant while environments differ:

| Environment | Actual runtime | What to check |
|---|---|---|
| Developer machine | IDE or embedded test server | Do not mask missing production providers |
| Unit tests | Mock/test provider dependencies | Do tests use a different runtime than production? |
| CI integration | Simulated container/service | Versions match production |
| Staging | Application server/servlet container | Real artifact, classloaders, and resources |
| Production | Ops-managed image/server | Matching vendor/update, profile, and providers |
| Rollback | Old runtime/artifact | Are data/APIs compatible when rolling back? |

A test running solely on an embedded container does not prove a WAR behaves identically on a full Jakarta EE server or a different server vendor.

## 20. Regression tests for API/provider and packaging

### 20.1. Compilation and linkage tests

- Compile both handwritten and generated sources.
- Verify `javax` and `jakarta` do not mix outside designed boundaries.
- Run legacy consumer binaries when declaring backward compatibility.
- Verify class-file target and minimum JDK.
- Check API signatures of plugin/extension libraries.

### 20.2. Provider discovery tests

- Bean Validation: create a `ValidatorFactory` and validate real objects.
- JPA: create a persistence context, persist/query within a transaction.
- JAX-RS: register resources/filters and invoke endpoints.
- CDI: resolve/inject beans and check scopes and lifecycles.
- JAXB: marshal/unmarshal DTOs and verify annotations.
- JAX-WS: invoke SOAP endpoints and inspect WSDL/headers/attachments.
- Activation: process MIME/DataHandler payloads if used by the application.

Select tests matching your stack; do not add a technology merely because it exists in Jakarta EE.

### 20.3. Artifact deployment tests

Execute against the exact artifact to be deployed:

1. Build and record checksums.
2. Inspect WAR/JAR/EAR contents.
3. Deploy into the target container/framework version.
4. Confirm logs show zero provider/classloading conflicts.
5. Call smoke endpoints and persistence/validation/security flows.
6. Record runtime class sources when investigating.
7. Test undeploy/redeploy and resource cleanup.

If production deploys multi-module EARs, check classloader isolation and shared libs at the EAR level, not just one inner WAR.

### 20.4. Failure-case tests

- Remove a provider to confirm failures surface clearly in tests.
- Introduce a controlled API/provider version mismatch to understand failure modes.
- Deploy to an incompatible container generation in isolation to verify guardrails.
- Test for duplicate JARs/service metadata under shading.
- Test migration of sessions, transactions, and long-lived state during rolling deployments.

Do not intentionally introduce broken configs into production just to observe exceptions. Negative tests should run in isolated fixtures/staging.

## 21. Release and rollback strategy

### 21.1. When dependency scope changes, the artifact changes too

A migration may keep source code unchanged while modifying:

```text
jakarta.servlet-api: compile -> provided
```

causing the WAR to drop an API JAR; this works well if the container supplies the right version, yet breaks if the target does not.

Therefore, review scope diffs as **deployment changes**. Save before/after:

- Resolved compile/runtime graphs.
- WAR/JAR/EAR contents.
- Runtime container profile.
- Classloader/provider decisions.
- Integration test results.

### 21.2. Rolling deployment between javax and jakarta

A system migrating its container/framework to the Jakarta namespace may be unable to deploy the same WAR simultaneously across `javax` servers and `jakarta` servers. If blue-green/rolling deployment is required, maintain two artifacts or two contract-aligned deployment tracks rather than assuming scope edits alone allow sharing one binary.

Check external API contracts, session/data state, messaging, and database schemas while both versions coexist. Changing internal Java packages does not automatically alter HTTP/JSON contracts, yet can affect serialization, session replication, or framework metadata.

### 21.3. Rollback requires matching infrastructure

When upgrading servers from `javax` to `jakarta`, rolling back simply by swapping the new WAR for the old WAR on the new server may be impossible. Rollback plans must include image/server versions or a compatible deployment track.

Do not assume "keeping the old artifact" suffices if the runtime environment changed API generations.

## 22. End-to-end example: legacy Java EE WAR to Jakarta EE

Suppose the initial project has:

```text
JDK 8 / legacy Java EE application server
  ├── javax.servlet API: provided
  ├── javax.persistence API: provided
  ├── JPA provider: server-managed
  ├── Bean Validation provider: server-managed
  └── WAR: business classes + app-specific libraries
```

Goal: run on a modern JDK and a server supporting the Jakarta namespace.

### 22.1. Step 1: Inventory legacy dependencies

Check the POM:

```xml
<dependencies>
    <dependency>
        <groupId>javax.servlet</groupId>
        <artifactId>javax.servlet-api</artifactId>
        <version>${legacy.servlet.version}</version>
        <scope>provided</scope>
    </dependency>
</dependencies>
```

Locate other annotations such as `javax.persistence.Entity`, `javax.validation.Valid`, CDI injections, REST resources, and generated sources. Identify JPA/Validation providers currently supplied by the server.

### 22.2. Step 2: Lock down the Jakarta server and API version

Select a target server/version supported by infrastructure, verify Java runtime and Jakarta EE profile/specification levels. Only then finalize API dependencies and scopes.

Example using an umbrella API:

```xml
<dependency>
    <groupId>jakarta.platform</groupId>
    <artifactId>jakarta.jakartaee-api</artifactId>
    <version>${jakarta.ee.version}</version>
    <scope>provided</scope>
</dependency>
```

If the application only uses Servlet or the server lacks full-platform support, select targeted APIs per contract instead of an overly broad umbrella.

### 22.3. Step 3: Migrate source code and extensions

Example:

```java
// Old
import javax.persistence.Entity;
import javax.validation.constraints.NotNull;

// New
import jakarta.persistence.Entity;
import jakarta.validation.constraints.NotNull;
```

Do not place both imports in the same class just to illustrate compilation. Check generated sources, annotation processors, XML descriptors, persistence configs, CDI extensions, and ORM/Validation integrations of the same generation.

### 22.4. Step 4: Choose provider owners

If the target server manages JPA/Validation, keep APIs in compile/provided scope by design and avoid unintentionally packaging application-level providers.

If migrating to a servlet container supplying only Servlet, add JPA/Validation implementations and suitable transaction integration. This is a **runtime model change**, not solvable by namespace renaming alone.

### 22.5. Step 5: Build and inspect the WAR

Check `WEB-INF/lib` post-migration:

- No Servlet API duplicating the server.
- Required app-specific providers (if any) are present.
- No two conflicting runtime implementations coexist.
- No test/build-only libraries present.
- Service metadata, resources, and framework descriptors are accurate.

### 22.6. Step 6: Deploy and verify

Run smoke tests, persistence transactions, Bean Validation, authentication, REST endpoints, and integration tests inside a real container. Record server logs and resolved dependency versions.

The expected outcome is not merely a WAR that deploys "successfully," but **compile-time APIs matching runtime-supplied capabilities and providers**.

## 23. Misconceptions to avoid

| Misconception | Reality |
|---|---|
| "Having the Jakarta API JAR means having a Jakarta EE server" | An API only declares the contract; an implementation/container is needed |
| "Marking dependencies provided is always better" | Only true when the runtime genuinely supplies that dependency |
| "WARs and executable JARs should use the same scopes" | Packaging and runtime ownership differ |
| "Tomcat provides all of Jakarta EE" | A servlet container is not a full Jakarta EE platform by default |
| "Just bundle every provider into WEB-INF/lib to be safe" | Can cause duplicates or conflicts with the server |
| "A BOM solves both version and scope" | BOMs manage versions; scope and provider ownership must be decided separately |
| "Maven optional equals provided" | Two distinct semantics |
| "Gradle implementation is like Maven provided" | `implementation` normally participates in the runtime graph |
| "Migrating javax to jakarta only means editing imports" | Binary names, annotations, implementations, and servers must all align |
| "Same class name means compatible across any classloader" | Class identity also depends on the defining class loader |
| "Passing unit tests means production providers suffice" | Test dependencies can mask missing runtime providers |
| "New JDKs include JAXB/JAX-WS automatically" | Previously bundled modules were removed from the JDK starting in Java 11 |
| "Building a fat JAR prevents all provider errors" | Shading can strip SPI metadata or create conflicts |
| "Successful compilation guarantees the WAR will run" | Deploy/test artifacts with the real runtime owner |

## 24. Handoff record for a dependency scope change

Before signing off on the migration, prepare:

1. **Deployment model:** full Jakarta EE server, servlet container, executable JAR/WAR, or Java SE CLI.
2. **Target matrix:** runtime JDK, framework, server/profile, API namespace/specification version.
3. **Dependency inventory:** group/artifact/version, direct/transitive, compile/runtime/test scopes.
4. **Ownership matrix:** which technologies are server-supplied and which are application-packaged.
5. **API/implementation pairing:** provider/version and which module executes.
6. **Namespace migration diff:** `javax.*`/`jakarta.*` across source code, generated sources, and dependencies.
7. **Artifact report:** `WEB-INF/lib` listing or JAR/EAR runtime contents.
8. **Classloading evidence:** class sources, providers, conflict resolutions, and module/server policies.
9. **Verification:** compile, provider discovery, integration, deployment, smoke, and regression tests.
10. **Release and rollback plan:** whether both environments are compatible during rolling deployments, which artifacts/runtimes to retain.
11. **Security/supply-chain review:** dependency provenance, CVEs, lockfiles, SBOMs, and container hardening.
12. **Ownership:** owners of the server runtime, build platform, and application.

### Pre-release checklist

- [ ] Identified the runtime owner and Jakarta EE profile/specification version.
- [ ] Selected a consistent `javax` or `jakarta` namespace generation at each boundary.
- [ ] Distinguished API, implementation, provider, and container capabilities.
- [ ] Chose Maven/Gradle scopes according to the actual deployment model.
- [ ] Servlet API is not unintentionally packaged alongside container libraries.
- [ ] Required providers are present at runtime, not just the compile classpath.
- [ ] JPA/Validation/CDI/JAX-RS providers integrate cleanly with transactions/containers.
- [ ] Did not treat umbrella APIs/BOMs as runtime implementations.
- [ ] Checked transitive dependencies for APIs/providers from the wrong generation.
- [ ] Checked Gradle WAR provided configurations or Maven provided behavior.
- [ ] For reusable libraries, reviewed public signatures and published dependency metadata.
- [ ] Inspected `WEB-INF/lib`, fat/thin JAR, or EAR library layouts.
- [ ] Checked `META-INF/services` and provider discovery inside final artifacts.
- [ ] Verified JDK/class-file level of dependencies and runtime.
- [ ] Ran integration tests on the real target server/container/embedded runtime.
- [ ] Checked for classloader conflicts, duplicate JARs, and provider versions.
- [ ] Have a rolling deployment/rollback strategy when changing API generations.
- [ ] Archived dependency graphs, compatibility matrices, and release evidence for traceability.

**Conclusion:** Migrating Java EE to Jakarta EE and upgrading the JDK goes beyond swapping Maven/Gradle coordinates. API dependencies solve compilation; implementations/providers and runtime containers solve execution; packaging scopes determine what enters the artifact and what the environment must supply. Only by selecting scopes to match the real deployment model, aligning namespaces/versions, and inspecting **final artifacts on real runtimes** can a team prove migration compatibility instead of settling for a successful build alone.
