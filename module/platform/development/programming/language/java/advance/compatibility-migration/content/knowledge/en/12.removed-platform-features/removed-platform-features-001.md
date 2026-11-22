# Java EE and CORBA are no longer bundled with the JDK: identifying replacement dependencies

## 1. Context: why do old Java applications suddenly lack APIs?

When moving a system from JDK 8 to JDK 11 or newer versions, many projects encounter compilation or startup errors even though the business code barely changed. Typical errors include missing packages javax.xml.bind, javax.xml.ws, javax.activation, or org.omg.CORBA; disappearing wsimport/xjc tools; or the application failing to find a JAXB/JAX-WS implementation at runtime.

A key cause is **JEP 320 — Remove the Java EE and CORBA Modules**: starting in **JDK 11**, a set of Java EE and CORBA modules previously distributed with the JDK was removed. Earlier, in JDK 9 and 10, these modules were still present but marked deprecated for removal. Some JDK 8 applications used them without ever declaring external dependencies, so upgrading the JDK exposes those implicit dependencies.

This change does not mean all of Java EE vanished, nor does it mean all packages starting with javax ceased to exist. It means the specific APIs, tools, and implementations previously provided by the JDK are no longer guaranteed to be present on the classpath/module path. To continue using the corresponding functionality, the application needs to **identify standalone dependencies or choose alternative technologies**.

Lesson objectives:

- Accurately identify the Java EE/CORBA modules and tools removed from the JDK.
- Distinguish Java SE APIs that still exist from Java EE APIs separated from the JDK.
- Find API dependency sources and runtime implementations matching the javax or jakarta generation.
- Handle cases where libraries, generated code, build plugins, and containers still depend on legacy technologies.
- Evaluate when adding dependencies suffices and when changing frameworks/protocols is needed.
- Create a replacement matrix and verify the migration on the target JDK.

## 2. Modules removed when moving to JDK 11

The following modules form the primary scope to audit when upgrading from JDK 8/9/10:

| Module previously in JDK 9/10 | Common technologies or packages | Replacement approach |
|---|---|---|
| java.xml.bind | JAXB; javax.xml.bind and related annotations | Use standalone JAXB API and JAXB runtime, selecting the appropriate javax or jakarta generation. |
| java.xml.ws | JAX-WS; javax.xml.ws, SOAP service/client | Use standalone JAX-WS API and runtime or a SOAP framework such as Apache CXF. |
| java.activation | JavaBeans Activation Framework; javax.activation | Add the appropriate Activation API and implementation, or Jakarta Activation on newer stacks. |
| java.xml.ws.annotation | Certain Common Annotations, e.g. javax.annotation.Resource / PostConstruct | Use standalone Common Annotations API matching the framework generation. |
| java.transaction | Subset of Java Transaction API previously provided by the JDK | Use standalone transaction API when the application needs JTA; clearly identify which parts are used. |
| java.corba | CORBA, IIOP, org.omg.*, javax.rmi.CORBA types | Choose a maintained and compatible standalone ORB, or migrate protocol/architecture. |
| java.se.ee | Aggregator module grouping the modules above | Remove the aggregator dependency and declare each required API individually; there is no 1:1 replacement JAR. |

Two tool modules were also removed:

| Tool module | Legacy JDK tools | Solution |
|---|---|---|
| jdk.xml.bind | xjc, schemagen | Use standalone-distributed JAXB code-generation tools/plugins. |
| jdk.xml.ws | wsimport, wsgen | Use standalone JAX-WS/Metro or CXF tooling/plugins. |

Some older JDKs also bundled related implementations or tools as implementation details. After JDK 11, do not assume the runtime only needs an API JAR to automatically have the appropriate provider.

### 2.1. Do not equate every javax.* package with the removed parts

Many javax packages still belong to Java SE and remain in modern JDKs, for example:

- javax.xml.parsers, javax.xml.transform, javax.xml.stream, and javax.xml.namespace belong to Java SE XML processing APIs.
- javax.crypto belongs to Java SE cryptography APIs.
- javax.sql and JDBC-related APIs belong to Java SE.
- javax.transaction.xa belongs to XA support in Java SE's java.sql module.
- javax.annotation.processing belongs to the Java compiler API, not Java EE Common Annotations.

Conversely, APIs such as javax.servlet or javax.persistence were never default JDK SE APIs, even though they use the javax prefix. Some APIs were split out of the JDK starting in Java 11; others were never in the JDK to begin with.

Therefore, finding and replacing all javax occurrences with jakarta is wrong. You must classify by **specific API, framework version, owning module, current dependencies, and compatibility contract**.

### 2.2. --add-modules cannot restore removed modules

On JDK 9/10, an application could temporarily enable deprecated JDK modules using an option like:

~~~bash
java --add-modules java.xml.bind -jar application.jar
~~~

On JDK 11 and later, the JDK's java.xml.bind module no longer exists to be enabled. If you still request that module by its old name, the application can fail during layer/module initialization because the requested module is not found.

Therefore, **--add-modules is not a long-term migration solution** for removed components. You must add dependencies or switch technologies while updating build and runtime packaging.

## 3. Identifying dependencies before choosing replacement libraries

Do not start by randomly adding multiple JARs named JAXB, Jakarta, or CORBA. Identify the exact functionality the application depends on.

### 3.1. Inspecting source code

Search for common imports, fully qualified names, configurations, and API call strings:

~~~text
javax.xml.bind.*
javax.xml.ws.*
javax.activation.*
javax.annotation.*
javax.transaction.*
org.omg.*
javax.rmi.CORBA.*
com.sun.xml.internal.*
com.sun.xml.bind.internal.*
~~~

In environments with ripgrep:

~~~bash
rg -n "javax[.]xml[.](bind|ws)|javax[.]activation|javax[.]annotation|javax[.]transaction|org[.]omg|javax[.]rmi\.CORBA|com[.]sun[.]xml[.].*internal" src
~~~

In PowerShell, you can search within Java source:

~~~powershell
Get-ChildItem -Recurse -File -Filter *.java -Path src |
    Select-String -Pattern 'javax\.xml\.(bind|ws)|javax\.activation|javax\.annotation|javax\.transaction|org\.omg|javax\.rmi\.CORBA'
~~~

Note that regex is only a starting point. Code may use reflection, class names in XML/YAML, generated code, service provider configurations, WSDL/XSD, or separately packaged modules.

### 3.2. Inspecting compiler and runtime errors

| Symptom | Initial hypothesis | What to verify |
|---|---|---|
| package javax.xml.bind does not exist | Missing JAXB API on compile classpath. | Build dependencies and the namespace used by source code. |
| NoClassDefFoundError: javax/xml/bind/JAXBContext | Runtime artifact lacks JAXB API or loads the wrong version. | Runtime classpath, fat JAR/container image, dependency conflicts. |
| JAXBException cannot find implementation/provider | API is present but JAXB runtime is missing or provider is not discovered. | Runtime dependencies, service provider files, module path/classloader. |
| package javax.xml.ws does not exist | Missing JAX-WS API. | SOAP framework in use and compatible version. |
| wsimport or xjc: command not found | Tool previously bundled with the JDK is gone. | Build plugin/code-generation workflow. |
| package org.omg.CORBA does not exist | CORBA/IIOP dependency was removed from the JDK. | ORB, IDL stubs, and actual communication protocol. |
| javax.annotation.PostConstruct does not exist | Common Annotations API has not been added or namespace changed. | Framework version and annotations dependency. |
| ClassNotFoundException: jakarta.xml.bind.* | Runtime/compile stack uses Jakarta namespace, but the artifact lacks the corresponding API/implementation. | Library version and runtime provider. |

A similar exception can also result from conflicting dependencies or runtime loading a different JAR version than compile time. Therefore, before deciding to add a dependency, inspect the actual classpath.

### 3.3. Inspecting the dependency graph

For Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jaxb --configuration runtimeClasspath
~~~

For Maven:

~~~bash
./mvnw dependency:tree
~~~

These commands are merely tools for migration engineers to use in real projects; adjust the configuration/module if the project lacks runtimeClasspath or does not use the Java plugin.

The goal is to detect:

- API JARs present at compile time but missing at runtime.
- Both javax and jakarta generations appearing unintentionally.
- Multiple versions of JAXB/JAX-WS/Activation pulled in transitively.
- Dependencies declared with provided scope even though the deployment environment does not supply them.
- An application server or framework providing its own provider and conflicting with the packaged provider.

### 3.4. Analyzing compiled artifacts

For JARs without source, you can use jdeps:

~~~bash
jdeps --multi-release 11 --missing-deps --class-path "lib/*" application.jar
~~~

On Windows, the classpath separator and paths need to be adjusted. When analyzing Java bytecode, jdeps helps find unresolved dependencies given the supplied classpath, though a warning-free result does not prove all dynamic/reflection functionality is compatible.

When you need to identify missing classes, you can inspect:

~~~bash
jar tf application.jar
javap -classpath application.jar -verbose com.example.LegacyClient
~~~

Do not confuse jdeps --jdk-internals with a full inventory of Java EE APIs: that option focuses on JDK internal APIs, whereas JEP 320 mainly concerns modules that were once officially distributed and then removed.

## 4. Identifying replacement dependencies for JAXB

### 4.1. JAXB has two layers: API and implementation

JAXB (Java Architecture for XML Binding) converts between XML and Java objects, typically using JAXBContext, Marshaller, Unmarshaller, and XML annotations.

To run outside an old JDK, an application usually needs:

1. **JAXB API:** provides types, annotations, and interfaces for source compilation.
2. **JAXB runtime implementation:** performs binding/marshalling at runtime.

Adding only the API without the runtime can lead to provider/implementation errors. Adding only the runtime while picking an incompatible API can also cause linking errors or failure to locate the service.

### 4.2. Keeping javax.xml.bind code

If the goal is to upgrade the JDK without **yet changing frameworks, packages, and source APIs**, you can choose a JAXB 2.x branch compatible with javax.xml.bind code and related dependencies.

Legacy source example:

~~~java
import javax.xml.bind.JAXBContext;
import javax.xml.bind.Marshaller;

public final class XmlWriter {
    public static void write(Object object, java.io.OutputStream output)
            throws Exception {
        JAXBContext context = JAXBContext.newInstance(object.getClass());
        Marshaller marshaller = context.createMarshaller();
        marshaller.marshal(object, output);
    }
}
~~~

A Gradle Groovy configuration **illustrating an older version family**:

~~~groovy
dependencies {
    implementation "javax.xml.bind:jaxb-api:2.3.1"
    runtimeOnly "org.glassfish.jaxb:jaxb-runtime:2.3.8"
}
~~~

The versions above are examples illustrating an API/runtime generation; when deploying, select permitted versions and evaluate security, version compatibility, and transitive dependencies according to your actual BOM/framework. Do not treat example versions as “latest” recommendations.

### 4.3. Migrating to jakarta.xml.bind

If the system proactively upgrades to a framework using the Jakarta namespace, source code may need to change:

~~~java
import jakarta.xml.bind.JAXBContext;
import jakarta.xml.bind.Marshaller;
~~~

Gradle example when managed aliases/versions are defined in a version catalog:

~~~kotlin
dependencies {
    implementation(libs.jakarta.xml.bind.api)
    runtimeOnly(libs.glassfish.jaxb.runtime)
}
~~~

The version catalog must map the exact artifacts:

~~~text
jakarta.xml.bind:jakarta.xml.bind-api
org.glassfish.jaxb:jaxb-runtime
~~~

Choose an API and runtime pair belonging to a generation compatible with your framework, target JVM, and running libraries. Do not simply change the groupId to jakarta while leaving all old dependencies unchanged.

### 4.4. Specific checks for JAXB

- Do XML annotations on DTOs/entities use javax.xml.bind.annotation or jakarta.xml.bind.annotation?
- Which namespace do classes generated from XSD use?
- How is the JAXB provider discovered via ServiceLoader or runtime configuration?
- Does it run on the classpath, module path, or an environment with a custom classloader?
- Does the runtime require Activation or auxiliary modules?
- Is Jakarta XML Binding used alongside Spring, JPA, SOAP, or JSON/XML converters?
- Are XML schemas, namespaces, element names, and time formats preserved after upgrading?

When using JPMS, review module-info.java, requires, opens, and reflective access so JAXB can access the classes to bind. Simply adding JARs does not automatically resolve all reflection errors under strong encapsulation.

## 5. Identifying replacement dependencies for JAX-WS and SOAP

JAX-WS provides APIs for SOAP services/clients, web service endpoints, and code generated from WSDL. On newer JDKs, both the APIs and tools formerly bundled with the JDK may be gone.

### 5.1. API and runtime

For legacy code using javax.xml.ws, you may need:

- A JAX-WS API from the javax.* generation.
- A runtime implementation such as a compatible Metro/JAX-WS RI version, or an equivalent SOAP framework.
- JAXB, Activation, SAAJ, and WS-* dependencies as required by the runtime.

With modern Jakarta EE stacks, packages typically change to jakarta.xml.ws, jakarta.xml.soap, jakarta.xml.bind, and jakarta.activation. Choose a framework/runtime suite with compatible modules rather than randomly mixing various APIs and providers.

| Need | Legacy branch | Direction for Jakarta stack |
|---|---|---|
| SOAP API | javax.xml.ws.* | jakarta.xml.ws.* |
| SOAP message API | javax.xml.soap.* | jakarta.xml.soap.* |
| XML binding | javax.xml.bind.* | jakarta.xml.bind.* |
| Activation | javax.activation.* | jakarta.activation.* |
| SOAP runtime | Metro/JAX-WS RI or CXF version still supporting javax | Metro/CXF or Jakarta-compatible platform |
| Generated stub | Code generated with javax | Regenerate stubs with a tool version targeting jakarta |

Some SOAP frameworks include the API and provider transitively. In that case, adding every API directly is not always necessary. However, you must confirm the actual runtime combination, not rely solely on compilation success.

### 5.2. wsimport and wsgen are no longer default JDK commands

In the old workflow:

~~~bash
wsimport -keep -p com.example.soap.generated https://example.invalid/service?wsdl
~~~

After JDK 11, do not assume wsimport is in the JDK bin directory. Move code generation to a plugin from the appropriate SOAP ecosystem, such as the Metro/JAX-WS RI or Apache CXF plugin.

The workflow should become:

~~~text
WSDL / XSD in repository or versioned source
                     |
                     v
        Maven/Gradle code-generation plugin
                     |
                     v
            Generated Java source
                     |
                     v
          Compiler + packaging + tests
~~~

Pin the plugin version, API/runtime versions, and input WSDL/XSD. Do not rely on tools manually installed on a developer's machine, as CI can easily produce different generated code.

If a WSDL is supplied by a partner over the network, consider storing a version-controlled snapshot for reproducible builds; follow usage rights and data contract update procedures.

### 5.3. Verifying the SOAP contract

Changing the SOAP provider can introduce differences even when Java source compiles:

- XML namespaces, SOAPAction, endpoint URL, encoding, and schema validation.
- WSDL compatibility and generated data types.
- HTTP transport, timeouts, proxies, TLS, and authentication.
- SOAP headers, attachments/MTOM, SAAJ, SOAP handlers.
- WS-Security, WS-Addressing, transaction, and interoperability policies.
- Exception mapping and SOAP Fault errors.

If the system exchanges messages with external partners, store permitted sample requests/responses and run interoperability tests against the corresponding endpoint or mock. A unit test instantiating generated stub objects does not prove the SOAP contract works.

## 6. Java Activation Framework

Activation supports representing data types/content sources and commonly appears alongside JAXB, JAX-WS, SOAP attachments, or mail stacks.

On older JDKs, javax.activation could be available out of the box; after JDK 11, you must check which library actually provides the API/runtime. In the newer Jakarta generation, the package and artifact may move to jakarta.activation.

Approaches:

1. If still using javax.activation.* code, pick an API/implementation from the javax generation compatible with the legacy stack.
2. If the entire framework already uses jakarta.activation.*, choose Jakarta Activation and the corresponding provider.
3. If Activation is only a transitive dependency from JAXB/JAX-WS, check the framework's BOM before adding a version manually.
4. Check runtime packaging if the API is present at compile time but the provider or DataHandler/DataSource is missing at runtime.

Do not confuse the Activation change with JavaMail. Mail API is a related technology that can pull in Activation as a dependency, yet JavaMail was not one of the Java EE modules removed in JDK 11 under JEP 320.

## 7. Common Annotations and javax.annotation

Some projects use:

~~~java
import javax.annotation.PostConstruct;
import javax.annotation.PreDestroy;
import javax.annotation.Resource;
~~~

These annotations belong to Common Annotations, not to be confused with javax.annotation.processing in the Java compiler.

Resolution approach:

- For Java EE/legacy stacks using javax.annotation.*, choose the corresponding javax-generation Common Annotations API.
- For frameworks supporting the Jakarta namespace, use jakarta.annotation.* and the appropriate Jakarta Annotations API.
- Check whether the framework/container actually processes lifecycle and injection annotations.

Common pitfall: adding the annotation API may let the code compile, yet does not guarantee PostConstruct or Resource will be executed. A plain Java SE application does not inherently have a container to inject resources or invoke lifecycle callbacks. Behavior depends on the framework or runtime in use.

In Spring/Jakarta applications, when changing namespaces, verify the framework version, bean lifecycle, and generated code; changing only imports while the runtime container does not yet support the new namespace can cause callbacks not to run.

## 8. Java Transaction API and javax.transaction

Older JDKs had a java.transaction module providing a subset of transaction-related APIs. When upgrading the JDK, the javax.transaction.* types supplied by that module may no longer be present.

However, a distinction is needed:

- **High-level JTA APIs** such as UserTransaction, TransactionManager, or transaction-related exceptions require the corresponding Java EE/Jakarta Transactions dependency when used by the application.
- **XA APIs** in javax.transaction.xa remain a Java SE component related to JDBC/XA in the java.sql module; do not remove or rename them just because of the javax prefix.

If the application operates inside an application server, the server may provide the transaction API and implementation. If the application runs embedded/standalone, it may need a separate transaction manager implementation, not just the API JAR.

Questions to ask before choosing a dependency:

1. Does the application call UserTransaction/TransactionManager directly, or only use a framework's @Transactional?
2. Is the transaction manager currently managed by an app server, Spring, or an external library?
3. Are distributed transactions/XA across multiple resources needed?
4. Does the framework use javax.transaction or jakarta.transaction?
5. Does provided scope fit the actual deployment environment?

Do not add both javax.transaction and jakarta.transaction along with different managers without first determining who owns the transaction boundary. Keeping code compiling while swapping transaction managers can affect commit/rollback, timeouts, isolation, and production data.

## 9. CORBA and RMI-IIOP: cases that usually have no 1:1 replacement

CORBA (Common Object Request Broker Architecture) allows distributed components to communicate over ORB/IIOP. In legacy Java, an application might use:

~~~java
import org.omg.CORBA.ORB;
import org.omg.CosNaming.NamingContextExt;
import javax.rmi.CORBA.Stub;
~~~

After JDK 11, the CORBA/IDL APIs and tools bundled with the JDK are gone. Unlike JAXB, **you cannot assume that simply adding an API JAR will make all legacy ORB/RMI-IIOP functionality work again**.

### 9.1. Identifying CORBA scope

Inspect:

- Code calling ORB.init, narrow, Naming Service, Portable Object Adapter (POA).
- .idl files, generated stubs/skeletons, IDL-to-Java mappings.
- ORB bootstrap and configuration, naming service, IIOP endpoints.
- Interfaces between Java and external systems written in other languages.
- RMI-IIOP or legacy EJB using CORBA underneath.
- Security, transactions, SSL/TLS, object references, and interoperability requirements.

If CORBA is merely an unused dependency, you can replace/remove it. If it is a protocol actively serving an external system, treat it as a protocol-compatibility and integration project, not merely an import fix.

### 9.2. Option A: standalone ORB

You can evaluate standalone ORB implementations such as JacORB or Apache Yoko depending on release status, supported Java versions, and project requirements.

Before choosing, verify:

- Are the current packages/APIs and IDL mappings supported?
- Are the stub/skeleton generation tools compatible with legacy IDL?
- Are Naming Service, POA, portable interceptors, and transactions/security adequately supported?
- Does data exchanged with non-Java partners remain interoperable?
- Have deployment on the target JDK, module path/classpath, and containers been tested?
- Do licensing, CVEs, maintenance policies, and long-term roadmaps fit?

Do not rely on a library's name to conclude compatibility. An ORB may support CORBA generally without supporting the full feature set or RMI-IIOP used by the legacy application.

### 9.3. Option B: phased protocol replacement

If CORBA has become a long-term risk, you can migrate services to:

- HTTP/REST for simple request/response APIs with public contracts.
- gRPC for RPC communication needing explicit schemas, streaming, or appropriate performance.
- Messaging/events for asynchronous interactions.
- An adapter/gateway keeping a CORBA boundary while clients have not yet migrated.

A common strategy:

~~~text
Old CORBA client ── IIOP ─ Legacy CORBA Gateway ── Application Service
                                               ▲
                                               │
New client ───────────── REST/gRPC/Message ────┘
~~~

A gateway supports the transition phase but introduces latency, operational overhead, and its own security requirements. You must design authentication, rate limiting, timeouts, error mapping, retry/idempotency, and transaction semantics.

### 9.4. Java SE RMI is not the same as RMI-IIOP

Some basic Java RMI technologies still remain in Java SE via the java.rmi module. That **does not mean the RMI-IIOP/CORBA previously provided by the JDK still exists**. When inventorying, explicitly distinguish ordinary Java RMI from javax.rmi.CORBA, IIOP, and CORBA's IDL tools.

## 10. javax.* and jakarta.*: choosing the right generation

Splitting APIs out of the JDK and renaming the namespace from javax to jakarta are **two different changes**, even though they often appear together during a migration.

### 10.1. Two stages to understand

1. JDK 11 removed the Java EE/CORBA modules under JEP 320. Applications can still keep javax.* source code by adding standalone APIs and runtimes of the matching generation.
2. Jakarta EE 9 and newer versions moved many Java EE APIs from javax.* packages to jakarta.*. This change affects imports, class signatures, annotations, and binary compatibility.

In particular, an artifact whose groupId starts with jakarta does not necessarily contain jakarta packages in every version. Some Jakarta EE 8 releases still retain javax.* packages; check the **actual major version of the API** and class contents rather than inferring solely from the artifact name.

### 10.2. Quick selection table

| When source/framework uses | Prefer considering | Avoid |
|---|---|---|
| javax.xml.bind.* | JAXB API/runtime of the same javax generation (typically JAXB 2.x). | Pulling in Jakarta JAXB 3.x/4.x without migrating source/framework. |
| jakarta.xml.bind.* | Jakarta XML Binding API/runtime of the same jakarta generation. | Keeping a provider that only supports javax.xml.bind. |
| javax.xml.ws.* | JAX-WS/Metro/CXF of the javax generation. | Randomly pairing Jakarta JAX-WS 3+ with old javax generated stubs. |
| jakarta.xml.ws.* | Appropriate Jakarta XML Web Services provider/tooling. | Using javax generated code without regenerating/converting. |
| javax.annotation.* | Common Annotations API of the javax generation when required by the framework. | Changing annotation imports while the container still processes javax. |
| jakarta.annotation.* | Jakarta Annotations and a Jakarta-capable framework. | Adding only the API JAR and assuming lifecycle/injection works. |
| org.omg.CORBA.* | Evaluate standalone ORB/IDL toolchain or a protocol-replacement plan. | Assuming a Jakarta library completely replaces legacy CORBA. |

### 10.3. Do not migrate everything at once if verification capability is lacking

A large migration can be split into:

~~~text
JDK 8, JDK-provided Java EE APIs
          │
          ▼
Newer JDK + standalone javax API/runtime, keeping old contracts
          │
          ▼
Upgrade framework, codegen tools, and dependencies to Jakarta ecosystem
          │
          ▼
Migrate imports/annotations/generated code + contract testing
          │
          ▼
Remove unused legacy dependencies
~~~

These steps are not mandatory for every system. If the target framework requires Jakarta immediately, the namespace migration may need to happen simultaneously. However, separating change groups in planning and testing helps determine whether errors stem from the JDK or from API/framework versions.

## 11. Designing dependencies and scopes in Maven/Gradle

### 11.1. API and implementation have different roles

For libraries using JAXB or JAX-WS:

- The API dependency is usually needed on the compile classpath because source code references public types.
- The runtime implementation must be on the runtime classpath or supplied by the platform/container.
- If the application server already supplies the API and provider, do not bundle duplicates without verifying the classloader and server policies.
- For executable JARs or standalone Docker images, the required runtime dependencies usually must be packaged.

In Gradle:

~~~groovy
dependencies {
    // API: used when compiling source referencing JAXB.
    implementation "javax.xml.bind:jaxb-api:2.3.1"

    // Provider: required for JAXBContext to execute at runtime.
    runtimeOnly "org.glassfish.jaxb:jaxb-runtime:2.3.8"
}
~~~

In Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>javax.xml.bind</groupId>
        <artifactId>jaxb-api</artifactId>
        <version>2.3.1</version>
    </dependency>
    <dependency>
        <groupId>org.glassfish.jaxb</groupId>
        <artifactId>jaxb-runtime</artifactId>
        <version>2.3.8</version>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

The versions above are only **an example of the same JAXB 2.x generation**. In a real project, use dependency constraints/BOMs or verified version sets while reviewing CVEs and support policies. Do not hardcode versions blindly while ignoring the framework managing dependencies.

### 11.2. Avoid overusing provided

The provided scope makes sense when the deployment environment **actually** supplies the required API/implementation. It does not mean JDK 11+ automatically provides removed APIs.

For example, an application running Java 21 in a self-managed container cannot rely on the assumption that javax.xml.bind is built into the JDK. If runtime dependencies are stripped from the artifact due to provided scope while the container does not supply them, the application may build successfully and then fail at runtime.

### 11.3. Unified version management

Use a BOM or dependency management matching the framework and lock down:

- The API major version matching the javax or jakarta namespace.
- A runtime implementation compatible with the API.
- Build plugins/code generators producing source in the same namespace.
- The minimum Java runtime of all dependencies.
- Security-patched versions within the support window.

If you need to override a dependency, document the reason and test compatibility. Do not accidentally pull both major APIs with different packages into runtime and assume they are interchangeable; JAXBContext objects from javax and jakarta are **two different Java types**.

### 11.4. JPMS and the module path

On Java 9+, projects can use module-info.java and the module path. Adding dependencies is not only a classpath concern:

- API and runtime module names may differ across releases.
- Automatic module names may differ from artifact names.
- Libraries may require opens for reflection or JAXB binding.
- The module path can surface split packages, duplicate modules, or missing required modules.
- Service provider discovery may require declaring uses/provides or valid module configuration.

If using JPMS, inspect the module name with tooling on the chosen artifact itself rather than guessing from the JAR name. On the classpath, issues are more often class-loading order and duplicate versions; the two packaging models have different handling approaches.

## 12. Build-time tools and generated code

Legacy Java EE projects often have source generated from XSD/WSDL/IDL. When changing the JDK, generated source may still reference old APIs even after hand-written source has been updated.

| Code generation source | Legacy tool | Resolution approach |
|---|---|---|
| XSD → JAXB model | xjc from JDK/legacy tool | Add a standalone JAXB code-generation plugin/tool matching the target namespace. |
| Java model → schema | schemagen from JDK/legacy tool | Switch to the plugin of the appropriate JAXB implementation. |
| WSDL → SOAP client | wsimport | Switch to JAX-WS RI/Metro or CXF codegen. |
| Java service → WSDL | wsgen | Use a tool/plugin matching the SOAP stack in use. |
| IDL → Java stubs | Legacy CORBA idlj/toolchain | Evaluate a standalone ORB/IDL generator or migrate the contract to a new protocol. |

The workflow should separate:

1. Input schemas (WSDL/XSD/IDL) are version-controlled.
2. Tools and versions are pinned in the build.
3. Generated source resides in the generated sources directory and is not hand-edited.
4. Compiler and runtime use APIs from the same package family.
5. Contract tests confirm wire format and compatibility with external systems.

If upgrading code generators, compare generated sources in API surface, annotations, and serialization mappings. Generated method names and data types can change due to the generator, even though the WSDL/XSD did not change.

Do not run tools from PATH without knowing where they are installed; developer machines and CI may pick different wsimport/xjc versions.

## 13. Step-by-step migration for systems with Java EE/CORBA

### Step 1 — Lock down the current baseline

Record the current JDK and target JDK, source/bytecode target, framework/application server, dependency graph, artifact packaging, and runtime environment. Save a baseline build and test result.

### Step 2 — Find all references

Scan imports in source code, generated code, configuration files, and class files. Search for uses of javax.xml.bind, javax.xml.ws, javax.activation, javax.annotation, javax.transaction, and org.omg.*. Record which module/service owns each reference.

### Step 3 — Classify impact

| Group | Decision questions | Implementation approach |
|---|---|---|
| Direct JAXB | Does source use javax or jakarta? Is there an external provider outside the JDK? | Choose API/runtime of the same family, test XML contract. |
| SOAP/JAX-WS | What generated stubs and WS-* features do client/server need? | Choose aligned SOAP framework + codegen + runtime. |
| Activation | Used directly or only through SOAP/JAXB/mail? | Choose dependency according to the framework BOM. |
| Annotations | Which container/framework handles lifecycle/injection? | Choose Common Annotations matching the actual namespace. |
| Transactions | App server or embedded transaction manager? Is XA used? | Choose appropriate JTA API + implementation, test transactions. |
| CORBA | Are there ORB/IIOP and dependent partners? | Evaluate standalone ORB or gateway/protocol-change plan. |

### Step 4 — Decide on the javax or jakarta phase

If the immediate goal is only to run on a newer JDK, prioritize standalone dependencies of the javax generation compatible with legacy source/frameworks. If upgrading frameworks to newer Jakarta EE, plan package renaming alongside generated code and runtime providers.

Do not write “change all javax to jakarta” as a single task. Each technology and dependency has its own major version, package name transition, and runtime requirements.

### Step 5 — Replace toolchains and dependencies

Remove the assumption that Java EE/CORBA tools reside in the JDK. Add codegen plugins, APIs, implementations, and appropriate transitive dependencies. Lock versions, scopes, runtime packaging, and classpath/module path.

### Step 6 — Compile and run target tests

Run the build on the target JDK, then test:

- XML marshalling/unmarshalling with historical schemas/fixtures.
- Real SOAP requests/responses or reliable contract mocks.
- Annotation lifecycle and resource injection on the actual framework.
- Transaction commit/rollback, timeouts, retries, and XA if applicable.
- CORBA naming, IDL stubs, ORB/IIOP interoperability if keeping the protocol.
- Executable JAR/container packaging and runtime startup in the corresponding environment.

### Step 7 — Phased rollout

Test in staging and canary where appropriate; monitor class loading, errors, runtime provider discovery, and partner contracts. For SOAP/CORBA or data changes, have a rollback plan covering both protocol and state, not just reverting the JDK.

### Step 8 — Remove redundant dependencies

Once functionality is stable, inspect the dependency graph to remove duplicate providers, unused old APIs, or migration-only tools. Retain evidence of the verified version set and exception cases.

## 14. Replacement dependency decision matrix

An inventory template you can use directly in a migration plan:

| Component / package | Current dependency source | Target runtime | Replacement direction | Verification status |
|---|---|---|---|---|
| javax.xml.bind.* | JDK 8 or legacy API | JDK 17/21 | JAXB API 2.x + matching runtime if keeping javax; or migrate to Jakarta XML Binding in sync. | Not started / Compiled / XML tested. |
| javax.xml.ws.* | JDK/legacy tool | JDK 17/21 | JAX-WS RI/Metro or CXF matching source/namespace; standalone codegen tool. | Not started / SOAP tested. |
| javax.activation.* | JDK 8/transitive | JDK 17/21 | Corresponding javax/jakarta Activation API/provider. | Not started / Runtime tested. |
| javax.annotation.* | Java EE module or framework | JDK 17/21 | Common Annotations API and appropriate callback-handling framework. | Not started / Lifecycle tested. |
| javax.transaction.* | Old JDK / container | JDK 17/21 | JTA/Transaction API and manager if needed, matching framework generation. | Not started / Commit/rollback tested. |
| org.omg.* | JDK 8 CORBA / old ORB | JDK 17/21 | Standalone ORB or gateway/REST/gRPC; verify IDL/IIOP. | Not started / Interoperability tested. |
| wsimport / xjc | JDK tools | Build on newer JDK | JAX-WS/JAXB Maven/Gradle plugin; pin version. | Not started / Regenerated. |

Each actual implementation row should also include:

- Module/service name and owner.
- Source, JDK, framework, and dependency versions.
- Chosen dependency with groupId/artifactId/version or ORB/framework name.
- compile/runtime/provided scope and container packaging method.
- Whether package namespace changes; whether there are breaking binary/API changes.
- Test/CI evidence, open issues, rollback conditions.

Do not fill in a version “by intuition” just to make the table look complete. If no verified option exists yet, explicitly note “needs evaluation” and the reason.

## 15. Common pitfalls and how to avoid them

### 15.1. Adding only the API without the implementation

This is a common issue with JAXB and JAX-WS: compilation succeeds without errors, yet startup or actual API usage fails reporting no provider found.

Solution: distinguish compile-time API dependencies from runtime providers; verify service discovery on the actual deployed artifact and runtime classpath.

### 15.2. Mixing javax API with incompatible jakarta runtime

The classes javax.xml.bind.JAXBContext and jakarta.xml.bind.JAXBContext do not share the same binary name. Frameworks or generated code compiled against one generation are not automatically compatible with the other.

Solution: choose APIs, runtime, generated code, and frameworks consistently. If both must coexist in the same system, isolate the boundary through adapters and test thoroughly rather than treating the two APIs as one.

### 15.3. Replacing every javax with jakarta

Bulk replacement can break javax.xml.parsers, javax.crypto, javax.sql, or javax.annotation.processing, which still belong to Java SE.

Solution: inventory each affected API individually; use specific mappings per framework and major version.

### 15.4. Keeping provided scope from the JDK 8 era

The application builds successfully because CI has the API JAR, yet the Docker runtime lacks the required JAR or implementation.

Solution: verify which components are supplied by the app server/runtime; for standalone deployments, package runtime dependencies completely.

### 15.5. Editing only source code while ignoring generated code

Hand-written source is migrated to Jakarta, but SOAP stubs generated by an old wsimport still import javax.xml.ws; build and runtime keep failing.

Solution: upgrade the codegen plugin and regenerate from version-controlled schemas/WSDLs.

### 15.6. Treating CORBA like an XML dependency

JAXB mainly handles XML binding. CORBA is distributed communication middleware with ORB/IIOP/IDL and may depend on non-Java partners. It cannot be replaced by an XML library.

Solution: find all integration contracts, evaluate a standalone ORB or gateway, and establish a verified protocol plan.

### 15.7. Ignoring runtime and classloader

Unit tests pass on a simplified classpath, yet the application server or module path has duplicate providers, split packages, or reflection restrictions.

Solution: test the actual deployment artifact on a production-equivalent runtime, cross-checking classpath/module path and library versions.

## 16. Examples of reading errors and choosing resolution paths

### Example A — JAXB compilation error after switching JDK

Suppose the source reports:

~~~text
error: package javax.xml.bind does not exist
~~~

Sensible sequence:

1. Confirm the compiling JDK is JDK 11+ and the source still imports javax.xml.bind.
2. Check whether a JAXB API dependency already exists.
3. Check whether the framework belongs to the javax or Jakarta generation.
4. If keeping javax, select a JAXB API/runtime compatible with the legacy generation.
5. If migrating to Jakarta, update imports and annotations/generated code, and choose a matching API/runtime.
6. Run marshalling/unmarshalling tests; do not stop at successful compilation.

### Example B — SOAP client no longer has wsimport

Previously, CI ran:

~~~bash
$JAVA_HOME/bin/wsimport -keep service.wsdl
~~~

After switching to a newer JDK, the command does not exist. The right approach is not copying an executable from an old JDK into the new image and ignoring dependencies.

Move the WSDL into a build workflow with a versioned code generator, choose the corresponding Metro or CXF plugin, pin its version, generate source, and test the SOAP contract on the target JDK.

### Example C — Legacy CORBA client fails at import org.omg

If the system still exchanges IIOP with a CORBA server, a practical option may be a standalone ORB if it supports the existing contract. If the protocol is obsolete and you have authority to modify the server, you can design a gateway and migrate clients in phases.

Inspect IDL, object references, naming service, and security before asserting that replacing the ORB is enough to run. An application using ordinary RMI does not necessarily need CORBA; inspect actual imports and protocols.

## 17. Expected deliverables after auditing and replacing

A well-prepared migration effort should produce:

1. **A list of removed JDK modules/APIs** actually used by each application module.
2. **A dependency mapping table** for JAXB, JAX-WS, Activation, Common Annotations, Transactions, and CORBA with clear namespace, API, runtime, version, and scope.
3. **A list of replacement build tools** for xjc/schemagen/wsimport/wsgen/IDL generation.
4. **A javax vs. jakarta decision** aligned with the target framework version.
5. **A version-locked set of dependencies** and reproducible build artifacts on the target JDK.
6. **Runtime and contract test results** for XML, SOAP, transactions, annotation lifecycle, and IIOP if still used.
7. **A risk mitigation plan** for unmaintained dependencies, missing providers, generated code, and external integrations.
8. **A deployment and rollback plan** accounting for schemas, protocols, and data state.

## 18. Conclusion

Starting in JDK 11, the Java EE and CORBA modules removed under JEP 320 are no longer included in the JDK by default. For JAXB, JAX-WS, Activation, Common Annotations, and Transactions, the standard path is to explicitly declare standalone API and runtime implementations, selecting the same javax or jakarta generation used by the framework and source code. For CORBA, evaluate a standalone ORB/IIOP or a phased protocol migration, since no universal drop-in JAR exists for the entire legacy middleware.

Most importantly, **do not choose dependencies solely based on package names or compilation error messages**. Classify the affected APIs, inspect the dependency graph, separate APIs from implementations, update build-time tools, identify the namespace, and run contract tests on the actual runtime. That approach turns what looks like a simple “missing JDK classes” issue into a controlled migration plan, avoiding fixing compilation while leaving runtime or distributed-system compatibility failures behind.
