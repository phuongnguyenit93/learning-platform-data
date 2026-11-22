# Code Generated from OpenAPI, JAXB, or Protocol Buffers

## 1. Why Is Generated Code Easily Overlooked When Upgrading the JDK?

In many Java projects, part of the source code is not written directly by developers. It is **generated from a contract description** such as OpenAPI, XML Schema (XSD), or `.proto` files. Related DTO classes, HTTP clients, controller interfaces, JAXB bindings, protobuf messages, and adapters may be regenerated on every build or committed to the repository.

When changing JDKs, a development team might notice an error inside a generated Java file and edit that file directly. That fix is rarely sustainable: the next generator run can overwrite everything. The root issue may lie in the version of the **generator**, **templates**, **schema**, **build plugin**, **runtime library**, or **Java level the generator targets**.

A simple example:

- The application upgrades its runtime from JDK 17 to JDK 21.
- An older OpenAPI generator emits code importing `javax.annotation.Generated` or `javax.validation.*`, while the newer framework uses the corresponding `jakarta.*` APIs.
- An XJC plugin still assumes JAXB is built into the JDK, whereas the target runtime does not bundle JAXB as older Java releases did.
- A build plugin invokes a `protoc` version different from the protobuf Java runtime used by the application.
- Generated source was committed beforehand; CI does not run the generator so the build passes, yet freshly generated files on a developer machine differ.
- Renaming a field in a schema changes the generated getter name; the Java compiler fails even though the wire format might still read older data.

That is why generated code should be treated as **the output of a versioned, contract-driven pipeline**, not as standalone handwritten source code.

This lesson focuses on three common ecosystems:

1. **OpenAPI:** generating Java HTTP clients, server stubs, interfaces, models, and integration code based on REST API specifications.
2. **JAXB/XJC:** generating Java binding classes from XSD or mapping Java objects with XML via JAXB.
3. **Protocol Buffers:** generating Java message classes, builders, parsers, and supporting components from `.proto` schemas.

The goal is to inventory the pipeline, identify compatibility blockers, and organize safe code regeneration when upgrading the JDK, compiler, frameworks, or dependencies.

## 2. Five Compatibility Layers That Must Be Checked Separately

Saying "the generator supports Java 21" is not enough to conclude the project can upgrade the JDK. Distinguish:

| Layer | Question to Answer | Typical Risk |
| --- | --- | --- |
| Schema/contract | Are OpenAPI, XSD, or `.proto` still compatible with existing clients and old data? | Removed fields, changed data types, changed status codes |
| Generator executable | Can the generator, plugin, `protoc`, or XJC run on the target build JDK? | Plugin fails to start, internal compiler APIs changed |
| Generated Java source | Does the new Java code compile with the source/release target? | Missing imports, new keywords, unsupported API types |
| Generated runtime dependencies | Are the libraries used by generated code compatible with the JDK/framework? | `javax`/`jakarta` mismatch, incompatible Jackson/OkHttp/protobuf runtime |
| Consumer compatibility | Do compiled modules and released data continue to work? | Renamed getters/classes, changed API descriptors, unreadable payloads |

A very important sixth layer is **behavioral compatibility**: given the same schema, a new generator may represent `null`, default values, collections, date/time, enums, or HTTP errors differently than before. Successful source compilation does not prove the application still behaves as expected.

For example, a `String` in a generated model might switch from a nullable field to a different wrapper, or new code might switch from field-based JSON mapping to constructor-based mapping. The call path still compiles and runs, yet the semantics of absent data have changed.

## 3. Code Generation Pipeline and Version-Pinning Points

High-level workflow:

~~~text
            Contract source
      OpenAPI | XSD | *.proto
                |
                v
      Generator + templates
       + configuration
                |
                v
       Generated Java source
                |
                v
      javac / language compiler
                |
                v
       Generated class files
                |
                v
      Runtime dependencies
       + deployed JDK/JRE
                |
                v
          Application
~~~

Every input needs clear provenance:

- **Schema:** path, repository/commit, schema version, contract owner.
- **Generator:** name, exact version, distribution/checksum, or installation method.
- **Templates:** default or custom templates, version, and specific overrides.
- **Configuration:** target language, packages, transport library, annotation strategy, nullability/date options.
- **Build environment:** JDK running the generator, Maven/Gradle/plugin versions, operating system when relevant.
- **Compiler:** compiler JDK, `--release`, language level.
- **Runtime:** JSON/XML/protobuf libraries, framework, JDK image, and environment.

Pinning only the schema while omitting the generator version can still produce different output on a later build. Conversely, pinning the generator while fetching the contract from an unpinned "latest" URL also makes the build non-reproducible.

## 4. Inventorying Generated Code in a Project

Before making changes, determine three things: what code is generated, which tool generates it, and where the contract source lives.

Common locations:

~~~text
src/main/openapi/*.yaml
src/main/resources/xsd/*.xsd
src/main/proto/*.proto
build/generated/
target/generated-sources/
generated-src/
src/generated/java/
gradle build scripts / pom.xml
custom template directories
~~~

Not every project follows this layout; code may be generated in a separate repository and packaged as a dependency JAR. In that case, upgrading the application's JDK also involves the release pipeline of that generated JAR.

Inventory template:

| Attribute | Example to Record |
| --- | --- |
| Generated module | `orders-api-client` |
| Contract source | `src/main/openapi/orders.yaml` |
| Contract revision | Approved commit/tag |
| Generator | OpenAPI Generator/XJC/`protoc` |
| Generator version | Version pinned in wrapper/plugin |
| Build integration | Gradle task or Maven phase/goal |
| Output path | `build/generated/...` |
| Target package | `com.example.api.generated` |
| Runtime libraries | Jackson, JAXB Runtime, protobuf-java, HTTP client |
| Java compatibility | Build JDK, compiler JDK, `--release`, minimum runtime |
| Consumers | Server, mobile backend, plugin, downstream JAR |
| Owner | Team maintaining the contract and generated artifact |

A repository may use all three tools at once. Maintain a separate record for each pipeline, because the same JDK migration can require three different changes.

## 5. Fundamental Principle: Fix the Generation Source, Not the Output Manually

Suppose code is generated:

~~~java
// Generated code. Do not edit directly.
public class OrderDto {
    private String orderId;

    public String getOrderId() {
        return orderId;
    }
}
~~~

If you need to rename `getOrderId()` or change class annotations, do not open the generated file, edit it directly, and treat the task as done. Those edits can be wiped out on the next generator run or cause divergence between local machines and CI.

Typical places to apply fixes:

1. **Schema:** field names/types, constraints, operations, or messages when the contract needs updating.
2. **Generator configuration:** generator type, library, naming, serialization, nullable, and package options.
3. **Template customization:** only when standard options do not suffice and the team is prepared to maintain custom templates.
4. **Handwritten adapters/wrappers:** placed outside generated directories to avoid modifying generated APIs directly.
5. **Generator/runtime versions:** choose a supported version pair accompanied by tests.

Some projects intentionally commit generated sources so users do not have to install code generation tools. Even then, follow a **regenerate → review diff → commit** workflow with pinned versions rather than treating generated files as the sole source of truth.

## 6. What Components Does OpenAPI Generate?

OpenAPI describes HTTP endpoints, methods, paths, parameters, request/response bodies, schemas, authentication, and related constraints. A generator can produce:

- Java API clients with HTTP call methods.
- Models/DTOs using Jackson/Gson or a configured serializer.
- Server stubs/controller interfaces.
- Validation annotations and API documentation annotations.
- Exception/response wrappers.
- Build metadata or test scaffolding.

The output set depends on the **generator name**, version, library template, and options. Not all generators produce the same structure, annotations, or transport client.

Minimal OpenAPI contract example:

~~~yaml
openapi: 3.0.3
info:
  title: Orders API
  version: 1.0.0
paths:
  /orders/{id}:
    get:
      operationId: getOrderById
      parameters:
        - in: path
          name: id
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Order found
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Order'
        '404':
          description: Order not found
components:
  schemas:
    Order:
      type: object
      required: [id, totalCents]
      properties:
        id:
          type: string
        totalCents:
          type: integer
          format: int64
        createdAt:
          type: string
          format: date-time
~~~

Depending on configuration, the Java model may contain `String id`, `Long totalCents` or primitive `long`, and an appropriate Java time type. Do not guess exact generated types solely from the schema without checking the chosen generator/version options.

### 6.1. A client generation example

With OpenAPI Generator CLI installed and version-pinned:

~~~bash
openapi-generator-cli generate \
  -i src/main/openapi/orders.yaml \
  -g java \
  -o build/generated/openapi-client
~~~

This command illustrates the input, generator name, and output parameters. In a real project, pin the CLI version, pick suitable library/serialization options, configure package names, and integrate the generated source path into the build.

A generator may produce build files and documentation alongside `.java` files. Identify which files are output for compilation and which are only documentation or configuration.

## 7. OpenAPI Choices That Affect Compatibility

Certain configurations or schema edits can alter the generated Java API significantly:

| Adjustment | Potential Impact |
| --- | --- |
| `operationId` | Renames the generated Java method |
| Schema name | Renames the generated class or references |
| `required` / optional | Changes constructors, validation, and nullability |
| `nullable` / union type | Changes null representation, wrappers, and JSON mapping |
| `format: date-time` | Changes time type and serializer depending on config |
| `type: integer`, `format: int64` | Changes `Integer`/`Long`/primitive and overflow semantics |
| `enum` | Changes generated enum and handling of unknown values |
| `oneOf` / `anyOf` / `allOf` | Changes hierarchy, wrappers, or discriminator logic |
| `additionalProperties` | Changes handling of undeclared fields |
| HTTP library template | Changes client class, return types, async support, exception mapping |
| Package/module config | Changes fully qualified class name and binary API |
| Annotation family | `javax.*` vs `jakarta.*`, Jackson/JAXB/validation imports |

For example, schema v1 has:

~~~yaml
properties:
  totalCents:
    type: integer
    format: int32
~~~

V2 changes it to `int64`. Even though HTTP JSON still represents a number, the Java client may change the getter from `Integer` to `Long`, bringing source/binary incompatibility and data conversion risks. Test actual responses rather than looking only at the YAML diff.

### 7.1. Renaming is not the same as adding an alias

Changing `operationId: getOrderById` to `fetchOrder` can rename the generated Java method, even though the `GET /orders/{id}` endpoint did not change. The HTTP server remains compatible, yet source code of consumers using the Java SDK breaks. A contract change can be **wire-compatible yet generated-source-incompatible**.

Possible solutions include keeping the operation name in the public schema, adding an adapter in the new SDK, or releasing a major version with a migration guide.

### 7.2. `required` and `nullable` are two distinct concepts

A field declared `required` means it must appear according to the corresponding schema; it does not automatically mean "never null" across all OpenAPI versions and all representations. In OpenAPI 3.0, `nullable` is a dedicated mechanism; in OpenAPI 3.1, schemas aligned with JSON Schema represent null differently, such as via union types.

Do not blindly copy options or assume a generator interprets both specification versions identically. When upgrading the OpenAPI document version or generator, test:

- Absent field.
- Field present with `null`.
- Field present with empty string, 0, or false.
- Field containing an invalid value.

## 8. OpenAPI: Runtime Risks Less Visible to the Compiler

### 8.1. JSON serializer

Generated clients/servers may use Jackson, Gson, or another serialization library. Changing the generator or template can alter:

- Property names and naming strategy.
- Null inclusion/exclusion.
- Default values when a field is absent in the payload.
- `OffsetDateTime`, `LocalDate`, or wrapper classes.
- Unknown enum handling.
- Unknown properties policy.
- Serialization of polymorphic models/discriminators.

A new DTO may compile yet emit different JSON than before. For public APIs, keep golden JSON fixtures and contract tests verifying both reading and writing.

### 8.2. HTTP transport

Generated Java clients may use different HTTP libraries depending on the generator template. Changing the template can alter:

- Sync/async method signatures.
- Exception types on unsuccessful HTTP statuses.
- Timeout, connection pooling, retry, and redirect policies.
- TLS, proxy, cookie, and authentication behavior.
- How path/query parameters are encoded.
- Multipart upload/download and resource closing.

Do not treat changing the generator as merely changing DTOs if generated code also contains the HTTP client runtime.

### 8.3. Unknown enums and server evolution

A server may add a new enum value while older Java clients were generated from a fixed enum list. Depending on the library/options, the client might fail deserialization, return null, map to an unknown sentinel, or use another mechanism. If a service needs forward compatibility, explicitly decide unknown-value behavior and test with payloads containing new values.

### 8.4. Error models and response wrappers

One generator version may return the DTO directly, while another generates `ApiResponse<T>` or a wrapper for HTTP status/headers. This change can break Java source even when the OpenAPI response stays unchanged. Compare the SDK's public Java API before and after, not just swagger/openapi YAML.

## 9. OpenAPI and the `javax.*` / `jakarta.*` Boundary

When moving frameworks to the Jakarta generation, generated source may need to use:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
~~~

instead of the corresponding `javax.validation.*` imports. The same can happen for annotations related to Servlet, Persistence, or other framework APIs, depending on generator type.

This is not a rule to "turn every `javax` into `jakarta`". Some `javax.*` packages belong to Java SE and remain standard APIs; other Jakarta packages have their own versions/namespaces. With OpenAPI Generator, options like `useJakartaEe` or `useSpringBoot3` may exist in **certain generators/versions**; check the options of the specific generator.

An investigation approach:

1. Identify the server/client framework that will run.
2. Identify the actual generated imports after generation.
3. Identify the dependencies providing those annotations/APIs.
4. Choose generator/options and runtime libraries under the same namespace family.
5. Clean-regenerate and run compile/integration tests.

Do not simply add every `javax` and `jakarta` JAR at the same time to silence compiler errors. That can introduce two annotation families not uniformly recognized by the framework, causing validation or dependency injection not to work as expected.

## 10. OpenAPI Generator in Maven and Gradle

### 10.1. Illustrative Maven plugin

Example configuration structure, **replace the placeholder version with an approved version**:

~~~xml
<plugin>
  <groupId>org.openapitools</groupId>
  <artifactId>openapi-generator-maven-plugin</artifactId>
  <version>PINNED_GENERATOR_VERSION</version>
  <executions>
    <execution>
      <id>generate-orders-client</id>
      <goals>
        <goal>generate</goal>
      </goals>
      <configuration>
        <inputSpec>src/main/openapi/orders.yaml</inputSpec>
        <generatorName>java</generatorName>
        <apiPackage>com.example.orders.client.api</apiPackage>
        <modelPackage>com.example.orders.client.model</modelPackage>
        <output>target/generated-sources/orders-client</output>
      </configuration>
    </execution>
  </executions>
</plugin>
~~~

This example focuses on input/output paths and version pinning. Library/serialization options, source roots, and runtime dependencies must be configured for the actual plugin/generator. Do not put placeholders into a production build without replacing them with concrete versions.

### 10.2. Illustrative Gradle plugin

A project may use the corresponding plugin's `openApiGenerate` task and configure `inputSpec`, `generatorName`, `outputDir`, and package options. The plugin version, DSL style, and registration of generated sources into `sourceSets` can vary across versions.

Technical principle:

~~~text
compileJava
  dependsOn generateOpenApi

generateOpenApi
  inputs:  pinned orders.yaml + templates + options + generator version
  outputs: build/generated/openapi/...

sourceSets.main.java
  includes generated Java source directory
~~~

The critical condition is that the compile task must have an **explicit task dependency**, not just point to a directory that happens to hold generated files from a previous build. After a clean build, the generator must run before the compiler.

If the generator also emits its own `pom.xml`/Gradle build metadata, distinguish which output is used as a standalone SDK and which is compiled directly inside the application.

## 11. JAXB: XML Binding and Why Migration Is Harder Than Changing Imports

JAXB (*Java Architecture for XML Binding*) provides mapping between XML and Java objects. XJC is commonly used to generate Java classes from XSD. JAXB may be involved in:

- SOAP/XML service integration.
- XML configuration or document processing.
- Legacy XML storage/exchange systems.
- Generated clients from WSDL/XSD and schemas with complex namespaces.
- Framework tools generating models from XML contracts.

On older JDKs, certain JAXB components used to ship with the JDK. Starting in Java 11, related Java EE/CORBA modules (including `java.xml.bind`) are no longer bundled in the legacy way. Therefore, code that previously compiled without declaring a JAXB dependency may encounter:

~~~text
package javax.xml.bind does not exist
~~~

or:

~~~text
java.lang.NoClassDefFoundError: javax/xml/bind/JAXBContext
~~~

Do not react by switching all XML code to an arbitrary package. Identify **which JAXB API generation** is in use, which XJC tool, which runtime implementation, and which namespace the framework depends on.

## 12. Distinguishing JAXB API, Runtime Implementation, and XJC

Three components that are often confused:

1. **JAXB API:** types such as `JAXBContext`, `Marshaller`, `Unmarshaller`, and annotations.
2. **JAXB runtime implementation:** the provider executing binding/marshalling/unmarshalling at runtime.
3. **XJC/schema compiler:** the tool reading XSD and generating Java sources at build time.

Adding only the API dependency may let source compile, yet still not suffice to execute all JAXB operations. Installing only XJC for generation does not automatically supply the right runtime for the application either.

Examples of the two namespace families:

~~~java
// Legacy JAXB generation
import javax.xml.bind.JAXBContext;
import javax.xml.bind.annotation.XmlRootElement;
~~~

~~~java
// Corresponding newer Jakarta XML Binding generation
import jakarta.xml.bind.JAXBContext;
import jakarta.xml.bind.annotation.XmlRootElement;
~~~

These packages differ at the Java type level. A class annotated with `javax.xml.bind.annotation.XmlRootElement` is not automatically recognized as the corresponding annotation by a Jakarta-version JAXB runtime.

### 12.1. Verification matrix

| Component | What to Record |
| --- | --- |
| XSD/WSDL | Schema revision, XML namespace, imported schemas |
| XJC tool/plugin | Distribution, version, build JDK, binding files |
| Generated sources | Package and annotation imports |
| JAXB API | `javax.xml.bind` or `jakarta.xml.bind` |
| JAXB runtime provider | Implementation and dependency version matching the API |
| Application/framework | Whether it recognizes the same JAXB namespace |
| Runtime JDK | Target JDK, modules, classpath/module path |

An XJC plugin may run on a newer JDK yet generate legacy annotations; a newer JAXB runtime may use the Jakarta namespace while an older framework expects Javax. Those two cases require different fixes.

## 13. How Are XSDs and Java Classes Generated?

A minimal XSD:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           targetNamespace="urn:example:orders"
           xmlns="urn:example:orders"
           elementFormDefault="qualified">
  <xs:element name="order" type="OrderType"/>

  <xs:complexType name="OrderType">
    <xs:sequence>
      <xs:element name="id" type="xs:string"/>
      <xs:element name="totalCents" type="xs:long"/>
      <xs:element name="note"
                  type="xs:string"
                  minOccurs="0"
                  nillable="true"/>
    </xs:sequence>
  </xs:complexType>
</xs:schema>
~~~

XJC can create classes containing fields and matching JAXB annotations, plus `ObjectFactory`, `package-info.java`, and other types depending on schema/tool options.

Java code example solely to illustrate structure (not guaranteed output of a specific XJC version):

~~~java
@XmlAccessorType(XmlAccessType.FIELD)
@XmlType(name = "OrderType", propOrder = {
        "id", "totalCents", "note"
})
public class OrderType {
    protected String id;
    protected long totalCents;
    protected JAXBElement<String> note;
}
~~~

In a real schema, whether `note` becomes `String`, `JAXBElement<String>`, or another representation depends on XJC version and binding customizations. Do not write business logic based on assumptions about a class that has not actually been regenerated.

### 13.1. XML namespaces are part of the contract

An XML namespace like `urn:example:orders` belongs to the XML format; it is **not** a Java package. A generator may map the namespace to a Java package using default rules or binding files. Changing the Java package can break source/binary clients even when the XML namespace remains unchanged.

Conversely, changing the XML namespace in XSD can prevent older XML data from unmarshalling properly even if Java class names remain unchanged. Manage these two compatibility layers separately.

### 13.2. `minOccurs`, `nillable`, and null representation

XML allows distinguishing an **absent** element from an element present with `xsi:nil="true"` when the schema permits. Generated models/runtimes may use wrappers to preserve this state information.

For example:

~~~xml
<order xmlns="urn:example:orders"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <id>O-10</id>
  <totalCents>1200</totalCents>
  <note xsi:nil="true"/>
</order>
~~~

is not necessarily equivalent to XML lacking the `note` element. An XJC/generator change can lose that distinction if a different Java type is chosen.

## 14. JAXB: XJC Version, Runtime, and Binding Customizations

### 14.1. XJC should not be assumed to be an always-available JDK command

On modern JDKs, do not assume `xjc` is bundled as an out-of-the-box command in every JDK distribution. Development teams typically use Maven/Gradle plugins or standalone XJC distributions.

An illustrative command when the right version of XJC is installed:

~~~bash
xjc -d target/generated-sources/xjc \
    src/main/resources/schema/orders.xsd
~~~

In CI, pin the plugin/tool version, input schemas, and output directory; do not rely on an arbitrary `xjc` sitting on `PATH`.

### 14.2. External binding files

`.xjb` files can customize packages, class names, or schema → Java mappings. When upgrading JAXB/XJC across generations, binding language syntax, namespaces, and versions can change.

Inventory should record:

- `.xjb` files currently applied.
- Schema locations referenced by customizations.
- Package/class naming rules.
- XJC extensions/vendor plugins.
- Runtime namespace (`javax` or `jakarta`) that generated code will use.

Do not automatically replace namespaces across all binding files and declare migration finished. Check the syntax for the exact XJC version and regenerate code to confirm bindings are actually applied.

### 14.3. JAXB API and runtime dependencies

If choosing the Jakarta XML Binding family, include both the API dependency and an implementation aligned with the BOM/support policy:

~~~xml
<!-- Versions are managed by the approved BOM/dependencyManagement. -->
<dependencies>
  <dependency>
    <groupId>jakarta.xml.bind</groupId>
    <artifactId>jakarta.xml.bind-api</artifactId>
  </dependency>
  <dependency>
    <groupId>org.glassfish.jaxb</groupId>
    <artifactId>jaxb-runtime</artifactId>
  </dependency>
</dependencies>
~~~

This example assumes the project has a BOM or `dependencyManagement` managing versions; otherwise, approved versions must be declared. Choosing an incompatible API/runtime pair can cause class loading or provider discovery errors.

If the system still requires the `javax.xml.bind` JAXB API because of an older framework, it cannot directly swap in the new Jakarta artifacts without migrating the corresponding frameworks/consumers.

## 15. JAXB: Serialized XML Changes Requiring Testing

A passing build is not enough to conclude XML compatibility. Check:

| Change | Risk |
| --- | --- |
| `@XmlElement` name/namespace | XML producer/consumer no longer match |
| `@XmlType(propOrder)` | XML element order differs from schema |
| `minOccurs`, `maxOccurs` | Optional/repeated fields change Java API |
| `nillable` | Loses distinction between missing and nil |
| XSD type `int` ↔ `long` | Java field/getter and value range change |
| `xs:dateTime` mapping | Timezone and temporal type change |
| XML attributes ↔ elements | Data format changes |
| Enumeration restriction | Newer XML values absent in older generated enum |
| Namespace/package binding | XML or Java ABI may be affected |
| Custom adapters | Value parsing/formatting behavior may change |

For example, a schema changes `totalCents` from `xs:int` to `xs:long`. XML containing numbers may still be readable in some cases, yet Java getters/setters may change from `int` to `long`, breaking source/binary clients using the generated class.

### 15.1. Validation does not happen automatically on every unmarshalling path

Verify whether the system configures XML Schema validation on `Unmarshaller`/`Marshaller`. Having JAXB annotations on code does not guarantee every input is thoroughly validated against XSD at runtime.

When tightening validation, XML previously accepted may be rejected. This is a behavioral change requiring contract tests and release notes.

### 15.2. XML processing security

Do not use old XML schemas/compilers/runtimes with open default configurations without considering data sources and XML parser security. Risks such as external entity resolution, unintended schema loading, or resource exhaustion must be evaluated against the specific parser/validator.

When upgrading JAXB or frameworks, inspect XML parser policies, external schema access, and handling of untrusted documents. Do not just fix imports to make the compiler pass.

## 16. Protocol Buffers: Schema and Code Generation

Protocol Buffers uses `.proto` schemas to describe messages, field numbers, types, and data structures. `protoc` together with the Java code generator emits classes supporting builders, parsers, serialization, and field accessors.

Example proto3 schema:

~~~proto
syntax = "proto3";

package lesson.orders.v1;

option java_package = "com.example.orders.v1";
option java_multiple_files = true;

message Order {
  string id = 1;
  int64 total_cents = 2;
  repeated string tags = 3;
  optional string note = 4;
  reserved 5, 6;
  reserved "legacy_status";
}
~~~

The numbers `1`, `2`, `3`, `4` are **field numbers in the wire format**, not merely declaration order in the file. They are a critical part of the binary protocol contract.

Illustrative command:

~~~bash
protoc \
  --proto_path=src/main/proto \
  --java_out=build/generated/source/proto/main/java \
  src/main/proto/orders.proto
~~~

The command assumes the right version of `protoc` is installed and the input is named `orders.proto`. In a real project, manage binary/tool versions through plugins, wrappers, or a reproducible build environment.

### 16.1. Generated Java API

With the options above, usage code can look like:

~~~java
Order order = Order.newBuilder()
        .setId("O-100")
        .setTotalCents(2500L)
        .addTags("priority")
        .setNote("Express")
        .build();

byte[] payload = order.toByteArray();
Order decoded = Order.parseFrom(payload);

System.out.println(decoded.getId());
System.out.println(decoded.getTotalCents());
System.out.println(decoded.hasNote());
~~~

With `optional string note` supported under proto3 field presence, the generated API can provide `hasNote()`. Removing `optional` or altering schema syntax/semantics can affect client code relying on presence even though the payload is still protobuf.

## 17. `protoc`, Generated Java Code, and Protobuf Runtime Are Three Distinct Components

Track separately:

- **`protoc` compiler:** the executable reading `.proto` and orchestrating plugins.
- **Java code generator:** the component emitting `.java`, which may be tied to the `protoc`/plugin version.
- **`protobuf-java` runtime:** the Java library used by generated classes at compile/runtime.

In other configurations, a project may select the lite protobuf runtime or a gRPC plugin with its own version. Do not assume a class generated with the latest tool will be compatible with every older protobuf Java runtime.

### 17.1. Version selection rules

Prefer using generator/runtime combinations announced as supported by the protobuf project and integrating frameworks. Read release notes when changing major versions. Do not arbitrarily mix one version of `protoc`, another version of `protobuf-java`, and a third version of the gRPC plugin solely because each tool happens to run individually.

An error can appear when generated source invokes a method absent in the resolved protobuf runtime. In that case source compilation can fail; if classes were compiled against another runtime and deployed with an older JAR, `NoSuchMethodError` can occur.

### 17.2. Inventorying outputs and packages

Options such as `java_package`, `java_multiple_files`, and `java_outer_classname` affect Java class names and file layout. They can change the Java consumer API **without changing field numbers or wire schema**.

For example, switching from nested message classes inside an outer class to top-level classes using `java_multiple_files = true` can force client code to update imports and class references. Do not equate protobuf wire compatibility with Java source/binary compatibility.

## 18. Protobuf: Field Number Rules and Schema Evolution

### 18.1. Do not reuse field numbers

Suppose v1:

~~~proto
message Customer {
  string id = 1;
  string email = 2;
}
~~~

V2 no longer uses `email`. Do not assign field `2` to a new meaning:

~~~proto
// Risk: reusing tag 2 with a different meaning.
message Customer {
  string id = 1;
  string phone_number = 2;
}
~~~

An older consumer can read `phone_number` data as `email` because of the matching field number and wire type. No exception occurs, yet semantics are wrong.

A safer approach is to reserve the old tag/name:

~~~proto
message Customer {
  string id = 1;
  reserved 2;
  reserved "email";
  string phone_number = 3;
}
~~~

`reserved` helps the schema compiler catch some accidental reuses of tags or names. It does not automatically migrate historical data into the new field.

### 18.2. Adding fields is usually more compatible than removing/changing meaning

A v2 message can add a new field number:

~~~proto
message Customer {
  string id = 1;
  string email = 2;
  string display_name = 3;
}
~~~

An old reader unaware of `display_name` can handle it as an unknown field per protobuf mechanics. A new reader reading v1 messages will not see the new field, so appropriate default/presence rules must be used.

However, "adding a field" does not mean business logic is automatically safe: if the server starts requiring `display_name` always be present, v1 clients cannot automatically supply the new information. Distinguish wire-level compatibility from **semantic compatibility**.

### 18.3. Changing types is not a harmless refactor

Some protobuf field types share the same wire type, yet switching between them can still introduce range mismatches, decoding errors, and semantic differences. For example, `int32` → `int64` should not be treated as completely safe just because both use varint; values outside the int32 range may not be understood properly by old readers.

When needing a major type change, field rename/reinterpretation, or repeated/singular conversion, the lower-risk approach is usually to **add a new field with a new tag, support reading both old and new during a transition phase**, and then reserve the old field once retired.

### 18.4. Protobuf field names and Java getters

In protobuf binary wire format, field numbers matter more than field name spelling. However, field names affect generated getters and JSON mapping. Renaming `total_cents` to `amount_cents` in `.proto` while keeping the tag may remain compatible at a certain binary wire level, yet `getTotalCents()` turns into `getAmountCents()`, breaking Java source/binary clients.

With protobuf JSON mapping, field names also relate to property names. Therefore, a "rename-only" change must be tested for both Java API and JSON if the system uses both encodings.

## 19. Proto3 Presence, Defaults, `oneof`, and Enum Evolution

### 19.1. Default values do not necessarily mean "was sent"

For many scalar fields in proto3 without explicit presence, the getter returns the default (such as `0`, `false`, empty string) when the field is absent. Do not infer that:

~~~java
order.getTotalCents() == 0L
~~~

means the producer intentionally sent a total amount of 0. If you need to distinguish absence from a 0 value, design explicit field presence in the schema, such as using `optional` where appropriate or a different message model.

When upgrading the generator or changing the schema, verify whether consumers rely on `hasX()`, `getX()`, or `getXCount()` with specific assumptions.

### 19.2. `oneof`

`oneof` expresses a group of fields where at most one choice is present at a time. Generated code typically includes APIs to check the active case. Moving fields into/out of a `oneof`, or changing tags/meanings, can impact default and presence semantics.

For example:

~~~proto
message PaymentMethod {
  oneof method {
    string card_token = 1;
    string bank_account = 2;
  }
}
~~~

Consumers must handle both the case where no option is set and unknown states. Do not assume adding a new option to a `oneof` is always handled safely in business logic by older consumers.

### 19.3. Enums

A proto3 enum should define a 0 value as default, with an appropriate name such as `UNSPECIFIED`:

~~~proto
enum OrderState {
  ORDER_STATE_UNSPECIFIED = 0;
  ORDER_STATE_CREATED = 1;
  ORDER_STATE_PAID = 2;
}
~~~

When adding enum values, Java code generated from older schemas may encounter unrecognized values represented differently depending on runtime/API. Consumers should not assume every enum number matches a known constant. Test parsing and fallback paths, especially when messages may come from a newer server.

Changing the meaning of an existing enum number breaks the semantic contract even though wire bytes are valid.

## 20. Protobuf Wire Compatibility vs. Java Class Compatibility

This is an important distinction:

| Change | Protobuf Wire | Java Generated API | Business Behavior |
| --- | --- | --- | --- |
| Add field with new tag | Usually cross-readable, depending on usage | Gains new getter/builder | Requires default/presence logic |
| Change `java_package` | Binary message format may not change | Fully qualified class changes | Consumers must update imports/dependencies |
| Change `java_multiple_files` | Wire format unchanged | Class layout/names change | Requires Java client migration |
| Rename field, keep tag and type | Binary wire may not change | Getter/setter names change | JSON mapping/semantics need checking |
| Reuse old tag | Very dangerous | May still compile | Data may be misinterpreted |
| Change field type | Depends on types, high risk | Getter and builder signatures change | Overflow/precision/meaning |
| Add enum number | Wire format may contain new number | Old consumer may not recognize new enum | Requires fallback/unknown handling |
| Change RPC service/method name | Message schema may not change | Stub/API and service routing change | RPC contract may break |

Even when the protobuf binary decoder can read older messages, a Java module may fail to compile if generated classes were renamed. Conversely, Java code may compile and parse bytes yet misinterpret a reused tag.

Do not judge migration solely by the single dimension "`protoc` succeeded".

## 21. Generated Code in the gRPC Ecosystem and Additional Plugins

A project using protobuf over gRPC usually also has `service` definitions:

~~~proto
service OrderService {
  rpc GetOrder (GetOrderRequest) returns (Order);
}

message GetOrderRequest {
  string id = 1;
}
~~~

In that case the pipeline may include:

~~~text
*.proto
 ├─ protoc Java message generator
 │     └─ protobuf-java runtime
 └─ protoc gRPC Java plugin
       └─ grpc-java runtime/stubs
~~~

`protoc-gen-grpc-java` and the gRPC Java runtime are separate components whose versions/support must be checked. Do not assume upgrading `protobuf-java` automatically upgrades the entire gRPC stack.

Breaking changes may involve:

- Service or method names.
- Request/response types.
- Streaming mode (unary/server-streaming/client-streaming/bidirectional).
- Error/status mapping.
- Deadlines, cancellation, retries, and authentication.
- gRPC stubs/runtime versions and transport providers.

Changing JDKs can surface errors in Netty/TLS/native transport or executors, even when `.proto` files and generated messages remain valid.

## 22. Controlling the Java Source Target of Generated Code

Not every generator offers an option named "target Java version", and the same option name can mean different things across generators. Check:

- Java syntax emitted by templates: records, var, switch expressions, pattern matching, sealed types...
- JDK APIs called in output: `java.time`, `java.net.http.HttpClient`, `List.of`, `Stream.toList`...
- Annotations, JSR APIs, or framework types imported.
- Bytecode level produced by the compiler.
- Minimum Java runtime committed by the product.

For example, the build runs on JDK 21 while the library must support Java 17:

~~~text
Generator JVM:    JDK 21
Compiler JDK:     JDK 21
--release:        17
Production floor: JDK 17
~~~

In that case generated source must not use APIs introduced only after Java 17. Compiling with `--release 17` can catch many usages of non-Java-17 APIs, though dependencies and runtime behavior still need checking.

### 22.1. Why is `sourceCompatibility` not equivalent to `--release`?

Selecting a source language level only governs part of syntax/bytecode. `javac --release N` also constrains usage of Java platform APIs to the corresponding release. When the goal is preserving compatibility with older runtimes, prefer the appropriate release target mechanism rather than relying solely on source flags.

However, `--release` does not automatically detect every third-party library whose bytecode requires a higher runtime. Check dependency JARs and run tests on the lowest Java version committed by the product.

## 23. Generated Code and the Module System

With the Java Module System (JPMS), generated code may require modules for runtime libraries or use reflection. Potential issues:

- Generated JAXB models require runtime access to fields/constructors via reflection.
- Model packages inside a named module may need to be `opens` to the module performing binding/serialization.
- Placing dependencies on classpath vs. module path affects class loading.
- Automatic module names and service provider discovery may change after upgrading dependencies.

Illustrative module configuration example:

~~~java
module com.example.orders {
    requires java.xml;
    requires jakarta.xml.bind;

    opens com.example.orders.generated
            to jakarta.xml.bind;
}
~~~

Exact module names depend on chosen artifacts, and some implementations use different module names. This snippet does not replace inspecting descriptors of the actual JARs.

Do not open every package to `ALL-UNNAMED` as a default workaround if only one generated package needs reflection access. Likewise, do not arbitrarily alter a library's module attributes just because a new dependency appears; understand the classpath/module path being deployed.

## 24. Making Builds Reproducible Without Relying on Stale Caches

A good pipeline should satisfy:

1. Contract inputs live in version control or point to immutable revisions.
2. Generator/plugin/tool versions are pinned.
3. Templates/customizations are versioned.
4. Generated outputs reside in build-managed directories.
5. Compile tasks depend properly on generation tasks.
6. Runtime libraries are managed consistently with generated sources.
7. A clean build can regenerate code from scratch.
8. Generated outputs are reviewed whenever schemas/tools/configs change.

### 24.1. Avoiding builds that reuse output from previous runs

Example layout:

~~~text
src/main/openapi/orders.yaml
src/main/proto/orders.proto
src/main/resources/xsd/orders.xsd
build/generated/openapi/
build/generated/proto/
build/generated/xjc/
~~~

If `compileJava` merely adds `build/generated` to source roots without a task dependency on the generators, local builds may pass because old files remain on disk. Yet a clean CI build will fail, or worse, compile against a generated code version that does not match the current schema.

In Gradle, wire source directories to the corresponding task outputs via supported build APIs; in Maven, bind generator goals to the right phase and confirm output source roots are registered.

### 24.2. Deterministic generation

Output can differ between two generation runs due to:

- Different generator/template versions.
- Schemas fetched from unpinned URLs.
- Timestamps, absolute paths, banners, or metadata inside generated files.
- Sort order of models/operations/properties.
- Locale/charset and line endings.
- Plugin extensions and code formatting versions.

Configure deterministic output when tools support it. If output includes timestamps, know how to disable or strip that metadata during comparisons rather than treating every diff as a real API change.

A commonly useful CI check: **generate from clean and verify output produces no unexpected diff**. If a project commits generated code, this helps catch cases where source/schema was updated yet generated code was not regenerated.

## 25. Commit Generated Sources or Generate on Every Build?

There is no single universally right choice:

| Approach | Pros | Risks / Controls Needed |
| --- | --- | --- |
| Commit generated code | Consumers can build without installing generators; convenient diff review | Easily goes stale if schema changes without regenerating; large diffs |
| Generate during build | Clear source of truth; fewer generated files in repo | Build must have tools/plugins, immutable schema sources, reproducible config |
| Publish generated SDK as separate artifact | Consumers use stable dependency versions | Must synchronize SDK/schema/server, manage separate releases |

The decision should rest on repository organization, offline build requirements, number of consumers, and SDK release policy. Whichever approach is chosen, make explicit:

- Who is authorized to modify schemas.
- Who is responsible for regenerating/releasing.
- How generator versions are pinned.
- How stale output is detected.
- How breaking changes are reviewed.

Do not let one module silently generate code from a new spec while another module still uses an old client JAR without a compatibility contract.

## 26. Testing Migration from Four Perspectives

### 26.1. Generated source compilation

Confirm the new output compiles with the target compiler/toolchain:

- No imports referencing missing APIs.
- No duplicate class names or keyword conflicts.
- Valid API annotations and generated models.
- Matching Java release target and dependencies.

This is the first step, not proof that the HTTP/XML/protobuf contract still holds.

### 26.2. Contract tests from real data

**OpenAPI:** verify request/response JSON, status codes, query/path encoding, auth headers, missing/null, new enums, pagination, and exception mapping.

**JAXB:** use XML fixtures from old and new schemas/versions; check namespaces, optional/nil, element order, validation, date/time, and unmarshalling → marshalling.

**Protocol Buffers:** use binary fixtures created with generated v1 writers and v2 readers; verify field numbers, unknown fields, presence, enums, repeated/oneof, and data semantics.

Do not use a v2 generator to fabricate a fixture labeled v1. Compatibility tests need **actual bytes/JSON/XML produced by the old version** or a validated representative fixture.

### 26.3. Java consumer compatibility

If the generated SDK is a public artifact, create a consumer compiled against the old SDK and run or compile it across the supported matrix. Changes such as package, return types, or method names can break source/binary compatibility while the HTTP/XML/proto contract remains fully compatible.

Compare the public Java API of the v1/v2 generated JARs using an appropriate API diff tool when the library is distributed to downstream consumers.

### 26.4. Runtime integration

Run tests on the actual runtime image:

- HTTP client against real server, TLS/proxy/auth.
- JAXB implementation/provider loaded properly.
- Protobuf/gRPC runtime/stubs and transport.
- Related native libraries and Java agents.
- JDK module access and serialization behavior.

A test comparing only generated source files cannot detect runtime errors like `NoClassDefFoundError` or provider mismatch.

## 27. Compatibility Matrix Across Versions

| Contract/writer | Generated code/reader | Runtime | Question |
| --- | --- | --- | --- |
| Schema v1 | Generator v1 | Old JDK | Does the baseline run properly? |
| Schema v1 | Generator v2 | Target JDK | Does changing only generator/JDK alter Java API or behavior? |
| Schema v2 | Generator v2 | Target JDK | Does the target state run properly? |
| Payload v1 | Generated reader v2 | Target JDK | Can legacy data still be read? |
| Payload v2 | Generated reader v1 | Old/target JDK, if required to support | Is rolling deployment/rollback safe? |
| Java SDK v1 | Server/API v2 | Actual runtime | Can legacy clients still invoke it? |

Not every combination must be supported; the matrix must derive from the product contract. If the application does not permit rolling back to an old runtime, state that explicitly rather than assuming rollback works simply by swapping Docker images.

For gRPC/Protobuf systems, add **wire compatibility** tests. For OpenAPI, test both **HTTP behavior** and **generated Java SDK compatibility**. For JAXB, test XML schema and provider/runtime compatibility.

## 28. Controlled Schema Evolution Handling

### 28.1. OpenAPI

An easier-to-maintain compatible change can be adding an optional response property, provided older clients tolerate unknown properties and semantics do not require the new field. Changing endpoint paths, removing required properties, or changing authentication usually has broader impact.

When a breaking change is necessary, consider a new endpoint/version, adapters, or a dual-support period. Do not expect changing a generated client SDK alone to make an old server understand a new schema.

### 28.2. JAXB/XSD

Adding an optional element may be compatible with some readers, yet XML Schema validation or `xs:sequence` ordering can cause new data to be rejected by older readers. XML namespaces, nillability, and adapter behavior must be tested in practice. A "valid" schema does not mean an old Java JAXB class can accept it.

### 28.3. Protobuf

Keep field numbers stable, never reuse tags, reserve removed fields when appropriate, and add new fields with new numbers. For incompatible semantic changes, use new message/service versions or a phase where readers understand both old and new formats. Test binary and JSON encoding separately if both are used.

## 29. Rollout Across Multiple Services: expand → migrate → contract

A general strategy:

**Expand:** first update readers/servers to accept both old and new payloads, or release a new API version without removing the old version yet.

**Migrate:** upgrade clients one by one, regenerate SDKs, and roll out in batches; monitor decode errors, validation, HTTP status, gRPC status, and latency.

**Contract:** remove legacy schema fields, endpoints, Java adapters, or dependencies only after confirming no consumers still need them.

For example, when transitioning from a JSON field `amount` to `amountCents`:

1. The server temporarily supports both representations under clear rules.
2. Update the OpenAPI contract and generate a new SDK.
3. Roll out new clients in waves.
4. Monitor traffic still using the old field.
5. Remove the old field only when support policy allows.

With protobuf, do not reuse old field numbers after contracting; with JAXB, schema namespaces and XML compatibility must be managed separately. The expand/contract pattern is a guideline, not a replacement for format-specific rules.

## 30. Common Real-World Errors

| Symptom | Common Cause | Investigation Direction |
| --- | --- | --- |
| `package javax.xml.bind does not exist` | JAXB no longer bundled in JDK; wrong dependency generation selected | JAXB API/runtime/XJC stack and JDK |
| `ClassNotFoundException: jakarta.xml.bind...` | Generated source/runtime dependency mismatch | Resolved runtime graph, provider |
| `NoSuchMethodError` in protobuf runtime | Generated classes and protobuf runtime incompatible | `protoc`/plugin/runtime versions |
| Compile error on DTO getters | Schema/options changed generated methods | Generated API diff, schema revision |
| Unknown enum causes decode failure | Server/payload has a new enum | Serializer/runtime and fallback policy |
| JSON null/missing handled differently | Generator or serialization options changed | Golden fixtures, nullable/required |
| XML validation fails after regenerate | Namespace, element order, or XSD changed | Schema diff and XML fixtures |
| Clean CI build fails while local passes | Old generated sources remain in build dir, missing task dependency | Clean generation graph |
| Build passes but production fails to start | Agent/native/JAXB provider or JDK modules differ | Runtime image and deployment classpath |
| gRPC stub compile error | gRPC plugin/protobuf runtime version or schema API changed | Compiler/plugin/runtime matrix |
| Diff across thousands of generated lines | Generator/templates version changed or output non-deterministic | Pin tools, review diff by group |

Do not edit generated Java files to hide an error belonging to the schema, compiler plugin, or runtime dependency. Find the right layer and keep evidence.

## 31. Comprehensive Migration Example

Suppose an ordering system runs on JDK 17 and plans to move to JDK 21. It has:

~~~text
orders-service
  src/main/openapi/orders.yaml      -> Java HTTP SDK/server API
  src/main/resources/xsd/order.xsd  -> JAXB order document binding
  src/main/proto/order.proto        -> Order events and gRPC messages
  Gradle plugins + codegen tasks
  runtime: framework, Jackson, JAXB, protobuf-java, gRPC
~~~

### 31.1. Before migration

The team records the baseline:

- Source contract revisions of all three schemas.
- Generator/plugin/`protoc`/XJC versions.
- Generated Java packages, imports, and API signatures.
- JDK running the build, compiler JDK, and Java release target.
- Resolved runtime dependencies.
- JSON/XML/protobuf fixtures from the released version.
- Which consumers use the SDK and messages.

### 31.2. Identifying blockers

In the hypothetical example:

- The old OpenAPI server generator emits `javax.validation`, while the target framework uses Jakarta Validation.
- Old JAXB code imports `javax.xml.bind`, while the team is migrating to Jakarta XML Binding.
- Protobuf Java code still compiles, yet `protoc` and runtime are not version-managed together.
- A Gradle task compiles pre-generated files without declaring a dependency on the generate task.

Do not solve this by directly editing hundreds of generated files or dumping all legacy libraries onto the classpath.

### 31.3. Technical plan

1. Finalize the minimum Java level and choose a supported framework/generator/runtime combination.
2. Pin schema revisions, tools, and templates.
3. Select OpenAPI generator/options matching Jakarta/HTTP transport, and clean-regenerate.
4. Select consistent XJC/JAXB API/runtime, update bindings if needed, and clean-regenerate.
5. Select `protoc`, protobuf runtime, and gRPC plugin according to the compatibility policy.
6. Fix the build graph so generation runs before compilation without relying on stale output.
7. Run Java API diff and JSON/XML/protobuf fixture tests.
8. Run smoke/integration tests on JDK 21 together with container runtime/agents.
9. Deploy compatible readers/servers first, then update SDK consumers.

### 31.4. Completion criteria

It is not merely "it compiles". Prove:

- Clean builds on the target JDK/CI regenerate code successfully.
- No generated source unexpectedly depends on missing APIs.
- Generated runtime libraries align with tools and frameworks.
- Supported Java clients still compile/link under the published policy.
- Legacy JSON/XML/protobuf data can be read by the new version if required by the product.
- HTTP/gRPC behavior and authorization do not change outside approved scope.
- The production runtime image has the right dependencies, modules, and agents.
- Clear rollback or roll-forward plan exists if new payloads are unsupported by old readers.

## 32. Checklist Before Approving Changes

- [ ] Identified all contract sources: OpenAPI, XSD/WSDL, `.proto`.
- [ ] Distinguished schema revisions from generator/tool/plugin versions.
- [ ] Recorded generator JDK, compiler JDK, `--release`, and minimum Java runtime.
- [ ] Pinned generator/plugin/XJC/`protoc` versions.
- [ ] Inventoried and versioned custom templates/bindings.
- [ ] Explicitly configured output paths and generated source registration.
- [ ] Compile tasks depend properly on generation tasks.
- [ ] Clean builds do not use stale generated files.
- [ ] Reviewed generated Java API diffs, package/class/getter changes.
- [ ] OpenAPI generator options match HTTP library, Jackson, and target framework.
- [ ] Checked `javax`/`jakarta` imports, avoiding inconsistent mixing of both families.
- [ ] Checked JAXB API, runtime implementation, and XJC tool separately.
- [ ] Tested XSD XML namespaces, optional/nillable, ordering, and adapters.
- [ ] `protoc`/protobuf runtime/gRPC plugin follow a unified compatibility policy.
- [ ] Reused no protobuf field numbers; reserved removed fields where appropriate.
- [ ] Tested proto presence, unknown fields, and enum evolution.
- [ ] Tested both wire compatibility and Java generated API compatibility.
- [ ] Maintained golden JSON/XML/binary fixtures from released versions.
- [ ] Inspected runtime images, modules, agents, and native components where relevant.
- [ ] Reviewed security of HTTP clients, XML parsing, and dependency/tool supply chain.
- [ ] Established consumer inventory, version support policy, and rollout/rollback plan.
- [ ] Release notes distinguish schema, generator, and Java runtime changes.

## 33. Official Documentation to Consult

Because generator options and compatibility policies change across versions, consult release-specific documentation during migration:

- **OpenAPI Specification:** semantics of operations, schemas, required/nullable, responses, and versions 3.0/3.1.
- **OpenAPI Generator Documentation:** CLI/Maven/Gradle integration, generator-specific options, supported libraries, and migration guides.
- **Jakarta XML Binding Specification and JAXB/XJC documentation:** API/runtime, binding files, XSD ↔ Java mapping, and serialization semantics.
- **JDK migration guides:** modules formerly bundled with the JDK, the Java Module System, and `--release`.
- **Protocol Buffers Language Guide:** field numbers, reserved tags, presence, oneof, enums, and compatibility.
- **Protocol Buffers Java Generated Code Guide:** Java packages, generated getters/builders, and runtime compatibility.
- **gRPC Java documentation:** generated stubs, transport/runtime versions, deadlines, and status semantics.
- **Maven/Gradle documentation:** lifecycle, source roots, task dependencies, and reproducible builds.

Do not take a configuration snippet from an old plugin version and apply it to a new version without verifying options and runtime constraints. With code generation tools, **the tool version is part of the generated artifact's provenance**.

## 34. Conclusion

Java code generated from OpenAPI, JAXB, or Protocol Buffers sits at the intersection of **data contracts**, **code generation tools**, **compilers**, and **runtime libraries**. Upgrading the JDK can break any layer; meanwhile, a schema or generator change can also break the Java source/binary API even while the HTTP/XML/protobuf wire format remains compatible.

To migrate safely, inventory each pipeline, pin schema and tool versions, regenerate code via clean builds, never edit generated files manually, and test across three distinct dimensions: **code generation and compilation**, **running with the right dependencies/JDK**, and **exchanging data with released versions**.

In particular, for OpenAPI inspect HTTP client/server semantics and nullability; for JAXB inspect `javax`/`jakarta`, XJC bindings, and XML namespaces; for protobuf protect field numbers/presence and keep the `protoc`–runtime–gRPC stack aligned. A versioned workflow, contract tests, and clear rollout plan make JDK changes possible without letting generated code become a silent source of failures across services.
