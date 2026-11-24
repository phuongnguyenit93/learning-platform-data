# Marshalling, Unmarshalling, and Configuring JAXB for Your Java Version

## Objectives and Context

In the **SPRING_BOOT_INTEGRATION** module, Spring Boot connects HTTP clients, databases, caches, message brokers, and Spring Integration adapters into business flows with explicit contracts. Many ERP systems, banks, and legacy partners still use **SOAP/XML** with WSDL/XSD. Exchanged data must not only be syntactically valid XML: element names, namespaces, data types, element ordering, and business semantics must all match the contract.

**JAXB** (Java Architecture for XML Binding, now part of Jakarta XML Binding) supports both directions:

- **Marshalling:** converting Java objects into XML according to binding metadata.
- **Unmarshalling:** reading XML and instantiating Java objects according to binding metadata.

In Spring, `Jaxb2Marshaller` from **Spring OXM** wraps JAXB to integrate with `WebServiceTemplate` or XML integration flows. Despite having "2" in its name, this class remains in modern Spring and works with the JAXB/Jakarta XML Binding generation appropriate for your framework version.

This lesson belongs to the **SOAP and XML** chapter, covering **Marshalling, unmarshalling, and configuring JAXB for your Java version**. It focuses on DTO mapping, choosing the right API/runtime for Java 8, 11, 17, and newer versions; namespaces and XSDs, XML parsing security, SOAP transport, errors, timeouts, idempotency, testing, and observability.

After this lesson, you will be able to:

1. Distinguish the JAXB API, implementation/runtime, XJC, and JDK built-in XML APIs.
2. Choose `javax.xml.bind` or `jakarta.xml.bind` correctly for your Java/Spring Boot version.
3. Create DTOs using `@XmlRootElement`, `@XmlAccessorType`, `@XmlElement`, and `@XmlType`.
4. Marshal and unmarshal using plain JAXB or Spring's `Jaxb2Marshaller`.
5. Use `JAXBElement`/`ObjectFactory` for generated classes without a root annotation.
6. Configure a Spring-WS SOAP client and understand the SOAP Envelope/Body boundary.
7. Validate against XSD, defend against XXE, and classify SOAP Faults and mapping errors.
8. Test XML contracts independently of a server and operate adapters with retries/idempotency.

> **Boundary:** JAXB transforms objects ↔ XML; it does not construct SOAP Envelopes, sign WS-Security headers, authenticate partners, run database transactions, or guarantee exactly-once processing.

## 1. Where Does JAXB Fit in the Integration Flow?

~~~mermaid
flowchart LR
    A["HTTP/Broker Order event"] --> B["Order service"]
    B --> C["Business DTO → SOAP DTO"]
    C --> D["JAXB marshalling"]
    D --> E["SOAP Body"]
    E --> F["Spring WebServiceTemplate"]
    F --> G["ERP SOAP endpoint"]
    G --> H["SOAP response / Fault"]
    H --> I["JAXB unmarshalling"]
    I --> J["Response DTO → Business result"]
    B -.-> K["SQL inbox/outbox + transaction"]
    F -.-> L["Tracing, metrics, retry"]
~~~

Three layers have distinct responsibilities:

| Layer | Input/output | Responsibility |
| --- | --- | --- |
| **XML contract** | XSD/WSDL | QName, element order, minOccurs, types, schema version |
| **Object/XML mapping** | Java ↔ XML payload | JAXB, annotations, `Jaxb2Marshaller` |
| **SOAP/HTTP transport** | Envelope, header, action, TLS, response/fault | Spring-WS, message sender, security |

JAXB can also be used for **non-SOAP XML**, such as file imports, message broker payloads, or HTTP endpoints returning XML. A JAXB class by itself does not open a server endpoint or send HTTP requests.

## 2. Java Version and JAXB: Choosing the Right Generation

### 2.1. Why Can't Java 17 Find JAXB?

An important historical change is that JAXB used to be bundled in the JDK, but was removed from the JDK starting in Java 11.

| Platform | JAXB status in JDK | Typical package |
| --- | --- | --- |
| **Java 8** | Bundled JAXB 2.x | `javax.xml.bind.*` |
| **Java 9–10** | Module `java.xml.bind` deprecated and not resolved by default like Java 8 | `javax.xml.bind.*` |
| **Java 11+** | JAXB module **removed** | Must use an external JAXB library |
| **Spring Boot 2.x / Framework 5.x** | Depends on JDK/build; legacy JAXB | Primarily `javax.xml.bind.*` |
| **Spring Boot 3.x / Framework 6.x** | Boot 3 requires Java 17+ | `jakarta.xml.bind.*` |
| **Spring Boot 4.x / Framework 7.x** | Modern Spring generation | `jakarta.xml.bind.*` |

Common points of confusion:

- `jakarta.xml.bind-api` had transitional 2.3.x releases whose Java package was still `javax.xml.bind`; **the artifact name alone is not enough** to confirm the namespace.
- Starting with **Jakarta XML Binding 3.0**, the JAXB package moved to `jakarta.xml.bind`; JAXB 4.x continues using the new package.
- `javax.xml.parsers`, `javax.xml.transform`, `javax.xml.namespace.QName`, and `javax.xml.validation` **still** belong to the `java.xml` module in modern JDKs. Do not replace every `javax.xml` with `jakarta.xml`.
- Passing `--add-modules java.xml.bind` cannot restore JAXB on JDK 17 because that module no longer exists.
- The JAXB API and runtime are two separate artifacts: **compiling cleanly does not mean a provider is available at runtime**.

### 2.2. Jakarta-Generation Dependencies, e.g. Boot 3 + Java 17

Gradle Groovy DSL when integrating SOAP with Spring Web Services:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web-services'
    implementation 'jakarta.xml.bind:jakarta.xml.bind-api'
    runtimeOnly 'org.glassfish.jaxb:jaxb-runtime'
}
~~~

For applications that only need OXM without SOAP transport:

~~~groovy
dependencies {
    implementation 'org.springframework:spring-oxm'
    implementation 'jakarta.xml.bind:jakarta.xml.bind-api'
    runtimeOnly 'org.glassfish.jaxb:jaxb-runtime'
}
~~~

This is an **illustration for the Jakarta generation**. Some starters may already bring in JAXB libraries transitively; inspect your actual dependency tree and use Spring Boot's BOM/dependency management plugin rather than manually mixing incompatible versions.

In legacy Boot 2/JAXB 2 projects, imports are:

~~~java
// Java/Spring legacy, JAXB 2.x:
import javax.xml.bind.JAXBContext;
import javax.xml.bind.Marshaller;
import javax.xml.bind.Unmarshaller;
~~~

In Boot 3/4:

~~~java
// Jakarta XML Binding 3/4:
import jakarta.xml.bind.JAXBContext;
import jakarta.xml.bind.Marshaller;
import jakarta.xml.bind.Unmarshaller;
~~~

**Never mix** `javax.xml.bind.annotation.XmlRootElement` annotations from legacy code with a `jakarta.xml.bind.JAXBContext` from a modern runtime. Java treats them as completely different annotation types; the mapping will fail to recognize the class properly.

### 2.3. Safe Version-Selection Process

1. Verify the **Java runtime** of the container/server, not just the compile source level.
2. Verify the **Spring Boot + Spring Framework + Spring-WS** line in use.
3. Choose the **same-generation** JAXB API/runtime, e.g. Jakarta JAXB 4 API/runtime 4 matching the BOM.
4. If using XJC for code generation, select **XJC from the same JAXB generation** so generated imports match.
5. Audit older libraries pulling `javax.xml.bind` and newer ones pulling `jakarta.xml.bind` to prevent one model from hitting two different mechanisms.
6. Run contract tests on the exact production JDK and dependency graph.

Do not pin a JAXB version higher than the BOM just because it is the latest release. For Boot 3 or Boot 4, align with the Jakarta/JAXB and transport versions actually supported.

## 3. XML Contract, Namespace, and QName

Suppose the ERP requires this payload:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<m:SubmitOrderRequest xmlns:m="urn:example:orders:v1">
  <m:orderId>ORD-100</m:orderId>
  <m:amountMinor>1890000</m:amountMinor>
  <m:currency>VND</m:currency>
</m:SubmitOrderRequest>
~~~

Constraints to respect:

- The root element has local name `SubmitOrderRequest` and namespace URI `urn:example:orders:v1`.
- Child elements are namespace-qualified according to this XSD.
- Child element order may be mandatory because the XSD uses `xs:sequence`.
- The prefix `m` is merely an alias for the namespace URI; another prefix can still produce the **exact same QName** if the URI and local name remain unchanged.
- `amountMinor` uses an integer in minor currency units as defined by the contract, not automatically equivalent to `xs:decimal`.
- XML encoding and HTTP charset must agree; UTF-8 handles Vietnamese and international text properly.

**Do not judge XML validity by raw byte strings or prefixes.** Parse with a secure parser, compare expanded QNames, and validate against the XSD.

## 4. Annotated JAXB DTOs

A class representing the payload:

~~~java
// SubmitOrderRequest.java
import jakarta.xml.bind.annotation.XmlAccessType;
import jakarta.xml.bind.annotation.XmlAccessorType;
import jakarta.xml.bind.annotation.XmlElement;
import jakarta.xml.bind.annotation.XmlRootElement;
import jakarta.xml.bind.annotation.XmlType;

@XmlRootElement(
        name = "SubmitOrderRequest",
        namespace = "urn:example:orders:v1")
@XmlAccessorType(XmlAccessType.FIELD)
@XmlType(
        name = "SubmitOrderRequestType",
        namespace = "urn:example:orders:v1",
        propOrder = {"orderId", "amountMinor", "currency"})
public class SubmitOrderRequest {

    @XmlElement(
            name = "orderId",
            namespace = "urn:example:orders:v1",
            required = true)
    private String orderId;

    @XmlElement(
            name = "amountMinor",
            namespace = "urn:example:orders:v1",
            required = true)
    private Long amountMinor;

    @XmlElement(
            name = "currency",
            namespace = "urn:example:orders:v1",
            required = true)
    private String currency;

    public SubmitOrderRequest() { }

    public SubmitOrderRequest(
            String orderId,
            Long amountMinor,
            String currency) {
        this.orderId = orderId;
        this.amountMinor = amountMinor;
        this.currency = currency;
    }

    public String getOrderId() { return orderId; }
    public Long getAmountMinor() { return amountMinor; }
    public String getCurrency() { return currency; }

    public void setOrderId(String value) { this.orderId = value; }
    public void setAmountMinor(Long value) { this.amountMinor = value; }
    public void setCurrency(String value) { this.currency = value; }
}
~~~

| Annotation | Role |
| --- | --- |
| `@XmlRootElement` | Identifies the XML root QName of the object |
| `@XmlAccessorType(FIELD)` | Maps fields directly, avoiding reliance on public getters |
| `@XmlType(propOrder=...)` | Sets element ordering according to the complex type |
| `@XmlElement(name, namespace)` | Specifies the XML element mapped to the field |
| `@XmlElement(required=true)` | Constraint metadata for schema generation / binding |

**Warning:** `required=true` does **not** mean the JAXB runtime automatically fails when XML omits that field. XML missing `amountMinor` can still unmarshal into an object with `null` unless schema validation is enabled. Both XSD validation and business validation are needed.

Using a no-arg constructor (public or protected as required by the binding) and mutable fields/setters avoids reflection surprises. Do not assume an immutable Java `record` can be deserialized by every JAXB version without custom adapters.

### 4.1. Default Namespace in package-info.java

If a package contains multiple DTOs sharing the same namespace:

~~~java
// package-info.java
@jakarta.xml.bind.annotation.XmlSchema(
        namespace = "urn:example:orders:v1",
        elementFormDefault =
                jakarta.xml.bind.annotation.XmlNsForm.QUALIFIED)
package com.example.integration.erp.xml;
~~~

With a package-level schema declaration, you do not need to repeat the namespace on every child element if annotations are structured cleanly. However, only use `QUALIFIED` when the real XSD specifies it; schemas with unqualified elements require different handling.

The Java package name does not determine the namespace URI. Changing `urn:example:orders:v1` to `urn:example:orders:v2` can be a breaking change even when Java class and field names stay unchanged.

## 5. Plain JAXB: Marshalling Java → XML

~~~java
import jakarta.xml.bind.JAXBContext;
import jakarta.xml.bind.Marshaller;
import java.io.StringWriter;

public class BasicMarshalExample {

    public String marshal(
            SubmitOrderRequest request) throws Exception {

        JAXBContext context =
                JAXBContext.newInstance(SubmitOrderRequest.class);

        Marshaller marshaller =
                context.createMarshaller();

        marshaller.setProperty(
                Marshaller.JAXB_FORMATTED_OUTPUT, Boolean.TRUE);
        marshaller.setProperty(
                Marshaller.JAXB_ENCODING, "UTF-8");

        StringWriter output = new StringWriter();
        marshaller.marshal(request, output);
        return output.toString();
    }
}
~~~

JAXB may produce equivalent XML with different prefixes or whitespace; that does not necessarily violate the XML contract.

**Thread safety and performance:**

- `JAXBContext` is designed to be reused; recreating the context repeatedly wastes time parsing metadata.
- `Marshaller` and `Unmarshaller` are **not thread-safe**. Never store a single instance and share it across concurrent HTTP requests or broker workers.
- With plain JAXB, cache `JAXBContext` and create a new `Marshaller`/`Unmarshaller` per operation.
- With Spring, configure `Jaxb2Marshaller` as a singleton bean so the wrapper manages creating mappers safely.

Marshalling is **structural transformation**, not business rule validation. For instance, `amountMinor=-50` does not become valid simply because JAXB serialized the XML without error.

## 6. Unmarshalling XML → Java

Example with trusted XML in a unit test:

~~~java
import jakarta.xml.bind.JAXBContext;
import jakarta.xml.bind.Unmarshaller;
import java.io.StringReader;

public class BasicUnmarshalExample {

    public SubmitOrderRequest parseTrusted(
            String xml) throws Exception {

        JAXBContext context =
                JAXBContext.newInstance(SubmitOrderRequest.class);

        Unmarshaller unmarshaller =
                context.createUnmarshaller();

        return (SubmitOrderRequest)
                unmarshaller.unmarshal(new StringReader(xml));
    }
}
~~~

**Do not use this pattern as-is for untrusted XML** without controlling DTDs/external entities, size, depth, and validation. Different JAXB providers configure XML parsers differently; you must know which parser handles the input from the start.

After unmarshalling, check for `null`, required values, length limits, enums, and business invariants. Do not pass raw JAXB DTOs directly as domain aggregates before validating and mapping.

### 6.1. JAXBElement When `@XmlRootElement` Is Absent

Some classes generated by XJC from XSD carry `@XmlType` without `@XmlRootElement`. Global elements are represented using `JAXBElement<T>` carrying a QName.

Reading with a declared type:

~~~java
import jakarta.xml.bind.JAXBContext;
import jakarta.xml.bind.JAXBElement;
import jakarta.xml.bind.Unmarshaller;
import java.io.StringReader;
import javax.xml.transform.stream.StreamSource;

JAXBContext context =
        JAXBContext.newInstance(SubmitOrderRequest.class);

Unmarshaller unmarshaller =
        context.createUnmarshaller();

JAXBElement<SubmitOrderRequest> element =
        unmarshaller.unmarshal(
                new StreamSource(new StringReader(xml)),
                SubmitOrderRequest.class);

SubmitOrderRequest request = element.getValue();
~~~

The `xml` variable in this example represents **trusted** or already safely parsed/validated XML. Unmarshalling with a declared type maps into the target class, but **does not automatically verify the root QName**. Compare `element.getName()` against the contract's expected QName.

When marshalling an object without a root annotation:

~~~java
import jakarta.xml.bind.JAXBElement;
import javax.xml.namespace.QName;

JAXBElement<SubmitOrderRequest> root =
        new JAXBElement<>(
                new QName(
                        "urn:example:orders:v1",
                        "SubmitOrderRequest"),
                SubmitOrderRequest.class,
                request);
~~~

`javax.xml.namespace.QName` remains in modern JDKs and did not move to `jakarta`. When using generated classes, `ObjectFactory` usually provides `create...(...)` methods to construct wrappers with the right namespace; prefer those methods over assembling QNames manually.

## 7. XSD, WSDL, and Generated Java Classes

When payloads are large or involve complex types, generate bindings from the official XSD/WSDL instead of writing every annotation by hand:

~~~text
WSDL + XSD (versioned)
    ↓
JAXB/XJC code generation
    ↓
@Generated package + ObjectFactory + XmlSchema
    ↓
Jaxb2Marshaller / JAXBContext
    ↓
SOAP XML payload
~~~

A sample XSD:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    targetNamespace="urn:example:orders:v1"
    xmlns:tns="urn:example:orders:v1"
    elementFormDefault="qualified">

  <xs:element name="SubmitOrderRequest">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="orderId" type="xs:string"/>
        <xs:element name="amountMinor" type="xs:long"/>
        <xs:element name="currency" type="xs:string"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

  <xs:element name="SubmitOrderResponse">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="accepted" type="xs:boolean"/>
        <xs:element name="reference" type="xs:string"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
~~~

Goals of code generation:

- Preserve element/attribute names, namespaces, and ordering per XSD.
- Map constructs such as enums, choices, extensions, lists, and generated factories.
- Reduce the risk of hand-written DTOs drifting out of sync with the partner contract.

**The XJC version must match the runtime:**

- Modern Jakarta JAXB projects need XJC generating `jakarta.xml.bind.annotation.*` imports.
- Legacy JAXB 2 projects use `javax.xml.bind.annotation.*`.
- On Java 11+, the `xjc` tool is no longer bundled with the JDK; configure the appropriate build plugin.
- Never edit generated sources directly. Pin WSDL/XSD and binding customization files (`.xjb`) in the build, and regenerate new versions in a controlled manner.
- Verify against XML fixtures from the partner; a successful DTO round-trip may only prove two directions of **the same wrong mapping**.

### 7.1. Potentially Breaking XSD Changes

| Change | Impact |
| --- | --- |
| Changing targetNamespace or root element | QName mismatch |
| Changing minOccurs from 0 to 1 | Legacy XML missing required field |
| Reordering xs:sequence | XSD validation fails |
| Changing xs:decimal to xs:long | Loses ability to represent fractional values |
| Changing timezone constraints | Timestamps may be misinterpreted |
| Adding an enum value | Older clients may fail to parse |
| Changing nillable/optional | Differences among null, absent, and empty elements |

Changes must be verified with contract tests and a compatibility plan, not just a clean Java compile.

## 8. Spring OXM Jaxb2Marshaller

`Jaxb2Marshaller` is an OXM adapter bridging JAXB to Spring's `Marshaller`/`Unmarshaller` interfaces:

~~~java
import org.springframework.oxm.Marshaller;
import org.springframework.oxm.Unmarshaller;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
~~~

Creating a bean for the declared DTOs:

~~~java
// ErpXmlConfiguration.java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;

@Configuration(proxyBeanMethods = false)
public class ErpXmlConfiguration {

    @Bean
    Jaxb2Marshaller erpJaxbMarshaller() {
        Jaxb2Marshaller m = new Jaxb2Marshaller();
        m.setClassesToBeBound(
                SubmitOrderRequest.class,
                SubmitOrderResponse.class);

        m.setSupportDtd(false);
        m.setProcessExternalEntities(false);
        return m;
    }
}
~~~

`SubmitOrderResponse` is the corresponding response DTO, either hand-written or XJC-generated from the XSD. The wrapper bean is shared in Spring; the JAXB context is prepared per configuration, which does not mean the non-thread-safe `Unmarshaller` itself is shared directly.

### 8.1. Three Ways to Create a JAXB Context

| Approach | Best suited for | Notes |
| --- | --- | --- |
| `setClassesToBeBound(...)` | An explicit set of JAXB DTOs | Easy to control scope |
| `setContextPath("com.example.erp.generated")` | Generated package containing `ObjectFactory` or `jaxb.index` | Standard with XJC |
| `setPackagesToScan("com.example.erp.xml")` | Scanning annotated classes in a package | Incurs scan cost and requires valid package setup |

Usually choose **one** primary mechanism per marshaller context. When multiple SOAP partners use different XSDs, create separate beans per adapter instead of mixing unrelated generated classes.

Alternative example:

~~~java
@Bean
Jaxb2Marshaller generatedErpMarshaller() {
    Jaxb2Marshaller m = new Jaxb2Marshaller();
    m.setContextPath("com.example.erp.generated");
    m.setSupportDtd(false);
    m.setProcessExternalEntities(false);
    return m;
}
~~~

This is an **alternative option**, not a requirement to register both beans in the same context.

### 8.2. Marshalling to Result and Unmarshalling from Source

JAXP APIs like `javax.xml.transform.Source`/`Result` remain part of the JDK:

~~~java
import java.io.StringReader;
import java.io.StringWriter;
import javax.xml.transform.stream.StreamResult;
import javax.xml.transform.stream.StreamSource;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;

public class XmlPayloadMapper {

    private final Jaxb2Marshaller mapper;

    public XmlPayloadMapper(Jaxb2Marshaller mapper) {
        this.mapper = mapper;
    }

    public String toXml(SubmitOrderRequest request) {
        StringWriter output = new StringWriter();
        mapper.marshal(request, new StreamResult(output));
        return output.toString();
    }

    public Object fromTrustedXml(String xml) {
        return mapper.unmarshal(
                new StreamSource(new StringReader(xml)));
    }
}
~~~

`fromTrustedXml` only illustrates the API with **trusted XML**. Do not use an uncontrolled `StreamSource` for untrusted XML; see the XXE protection section. Spring provides DTD/external entity safeguards, but a `DOMSource` built elsewhere using an unsafe parser could already have resolved external entities before reaching JAXB.

## 9. JAXB in WebServiceTemplate and SOAP

Spring-WS `WebServiceTemplate` takes a marshaller/unmarshaller to convert XML payloads, while the SOAP message factory and message sender handle the Envelope and transport.

~~~java
// ErpSoapClientConfiguration.java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.client.core.WebServiceTemplate;

@Configuration(proxyBeanMethods = false)
public class ErpSoapClientConfiguration {

    @Bean
    WebServiceTemplate erpWebServiceTemplate(
            @Qualifier("erpJaxbMarshaller")
            Jaxb2Marshaller marshaller) {

        WebServiceTemplate template = new WebServiceTemplate();
        template.setMarshaller(marshaller);
        template.setUnmarshaller(marshaller);
        template.setDefaultUri(
                "https://erp.example.org/soap/orders");
        return template;
    }
}
~~~

`https://erp.example.org/soap/orders` is an illustrative address. In production, read the URL from externalized configuration and configure transport/TLS/credentials/timeouts per your Spring-WS version. The snippet above only demonstrates wiring JAXB into the template.

Calling gateway:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.soap.client.core.SoapActionCallback;

@Component
public class ErpSoapGateway {

    private final WebServiceTemplate template;

    public ErpSoapGateway(WebServiceTemplate template) {
        this.template = template;
    }

    public Object submit(SubmitOrderRequest request) {
        return template.marshalSendAndReceive(
                request,
                new SoapActionCallback("urn:SubmitOrder"));
    }
}
~~~

A real gateway should check/cast `SubmitOrderResponse` or unwrap `JAXBElement<SubmitOrderResponse>`, verify the namespace/type, and convert to a business result. Here it returns `Object` to avoid assuming a particular response binding shape.

**SOAPAction** relates to the binding and SOAP version, not automatically inferred from the JAXB root element. SOAP 1.2 has different action/content-type semantics from SOAP 1.1; follow the WSDL strictly. Do not hardcode an action if the partner uses a different value.

### 9.1. XML Payload Sits Inside the SOAP Body

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:m="urn:example:orders:v1">
  <soapenv:Header/>
  <soapenv:Body>
    <m:SubmitOrderRequest>
      <m:orderId>ORD-100</m:orderId>
      <m:amountMinor>1890000</m:amountMinor>
      <m:currency>VND</m:currency>
    </m:SubmitOrderRequest>
  </soapenv:Body>
</soapenv:Envelope>
~~~

`Jaxb2Marshaller` handles the `SubmitOrderRequest` portion; it does not add Headers, digital signatures, WS-Security UsernameTokens, or the SOAP Envelope. The Spring-WS/message factory/WS-Security layer handles those parts.

### 9.2. Timeouts and SOAP Transport Security

Before deploying:

- Verify HTTPS/TLS, truststore, hostname verification, and certificate policies.
- Configure HTTP connect/read timeouts on a version-compatible client message sender.
- Distinguish HTTP 401/403, HTTP 503, SOAP Faults, and JAXB parse/schema errors.
- If using WS-Security, verify timestamps, signatures, certificates, and replay protection.
- Never log SOAP payloads containing tokens, PII, or financial data.
- Bound concurrent requests, retries, and downstream state transitions.

JAXB does not establish distributed transactions or authentication policies simply because the DTO matches the XSD.

## 10. XSD Validation and Business Validation

The XML below is **well-formed** but missing a required element:

~~~xml
<m:SubmitOrderRequest xmlns:m="urn:example:orders:v1">
  <m:orderId>ORD-100</m:orderId>
  <m:currency>VND</m:currency>
</m:SubmitOrderRequest>
~~~

`@XmlElement(required=true)` does not replace XSD validation. Spring's `Jaxb2Marshaller` can attach a trusted schema:

~~~java
import org.springframework.core.io.ClassPathResource;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;

public Jaxb2Marshaller validatedMapper() {
    Jaxb2Marshaller m = new Jaxb2Marshaller();
    m.setClassesToBeBound(
            SubmitOrderRequest.class,
            SubmitOrderResponse.class);
    m.setSchema(
            new ClassPathResource("xsd/orders-v1.xsd"));
    m.setSupportDtd(false);
    m.setProcessExternalEntities(false);
    return m;
}
~~~

In this example, `xsd/orders-v1.xsd` must exist and declare the root elements the mapper needs to validate. With multiple XSD imports, control the resolver and allowed resources. Use approved schemas packaged with the build.

### 10.1. SchemaFactory with Restricted External Resources

~~~java
import jakarta.xml.bind.JAXBContext;
import jakarta.xml.bind.Unmarshaller;
import java.io.InputStream;
import java.util.Objects;
import javax.xml.XMLConstants;
import javax.xml.transform.stream.StreamSource;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;

SchemaFactory factory =
        SchemaFactory.newInstance(
                XMLConstants.W3C_XML_SCHEMA_NS_URI);

factory.setProperty(
        XMLConstants.ACCESS_EXTERNAL_DTD, "");
factory.setProperty(
        XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

Schema schema;
try (InputStream in = Objects.requireNonNull(
        getClass().getResourceAsStream(
                "/xsd/orders-v1.xsd"))) {
    schema = factory.newSchema(new StreamSource(in));
}

JAXBContext context =
        JAXBContext.newInstance(SubmitOrderRequest.class);

Unmarshaller unmarshaller =
        context.createUnmarshaller();
unmarshaller.setSchema(schema);
~~~

This snippet assumes an instance method (since it uses `getClass()`). If a JAXP provider does not support these security properties, fail fast or choose a provider that does—never silently ignore the error. Schema validation must be combined with a **hardened input parser** and size/depth limits.

A schema only checks what it declares. If `currency` is an unrestricted string or an amount has no `minInclusive`, business rules must still be checked after unmarshalling.

## 11. Preventing XXE and Handling Untrusted XML Parsers

XML input can be dangerous if the parser allows DTDs and external entities. Example of a pattern that **must be rejected** when the contract does not use DTDs:

~~~xml
<?xml version="1.0"?>
<!DOCTYPE payload [
  <!ENTITY external SYSTEM "file:///internal/secret">
]>
<payload>&external;</payload>
~~~

Never run such payloads to read real files. The goal is for the parser to **never resolve external entities** and never expand dangerous DTDs.

A safer `SAXSource` when reading external XML:

~~~java
import jakarta.xml.bind.JAXBContext;
import jakarta.xml.bind.Unmarshaller;
import java.io.StringReader;
import javax.xml.parsers.SAXParserFactory;
import javax.xml.transform.sax.SAXSource;
import org.xml.sax.InputSource;
import org.xml.sax.XMLReader;

public class SecureOrderXmlReader {

    private final JAXBContext context;

    public SecureOrderXmlReader() throws Exception {
        context =
                JAXBContext.newInstance(
                        SubmitOrderRequest.class);
    }

    public SubmitOrderRequest parse(String xml)
            throws Exception {

        SAXParserFactory factory =
                SAXParserFactory.newInstance();
        factory.setNamespaceAware(true);

        factory.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl",
                true);
        factory.setFeature(
                "http://xml.org/sax/features/external-general-entities",
                false);
        factory.setFeature(
                "http://xml.org/sax/features/external-parameter-entities",
                false);
        factory.setFeature(
                "http://apache.org/xml/features/nonvalidating/load-external-dtd",
                false);

        XMLReader reader =
                factory.newSAXParser().getXMLReader();

        SAXSource source = new SAXSource(
                reader,
                new InputSource(new StringReader(xml)));

        Unmarshaller unmarshaller =
                context.createUnmarshaller();

        return (SubmitOrderRequest)
                unmarshaller.unmarshal(source);
    }
}
~~~

Important:

- **Do not catch and ignore** exceptions when setting security features. If the parser does not support them, security is not guaranteed.
- Enforce byte limits **before** reading XML into a `String` so oversized payloads cannot exhaust RAM.
- Cap XML depth, element/attribute counts, and total processing time per workload.
- `Jaxb2Marshaller.setSupportDtd(false)` and `setProcessExternalEntities(false)` are useful defenses, but a parser creating a `DOMSource` elsewhere may already have processed external entities beforehand.
- Never load XSDs from client-supplied URLs; use trusted schemas and restrict external imports.

**Security must start at the very first XML parse point**, not only where JAXB is called.

## 12. Tricky Data Types: Decimals, Dates/Times, and Enums

### 12.1. Decimals and Money

XSD `xs:decimal` typically maps to `BigDecimal`. Never use `double` for monetary values when the contract requires exact decimal precision.

~~~java
import jakarta.xml.bind.annotation.XmlElement;
import java.math.BigDecimal;

// Field snippet inside a DTO:
@XmlElement(name = "amount", required = true)
private BigDecimal amount;
~~~

This example only illustrates the field; set the namespace appropriately for your package/XSD. For money, business logic must still verify sign, precision, scale, currency, and rounding rules.

### 12.2. XMLGregorianCalendar and OffsetDateTime

XSD has `xs:date`, `xs:dateTime`, and `xs:time`. Generated JAXB types often use `XMLGregorianCalendar`, whereas the domain model wants `Instant`, `OffsetDateTime`, or `LocalDate`.

Do not bind `LocalDateTime` to a timezone-bearing timestamp by stripping its offset. When custom mapping is needed, use an `XmlAdapter` matching the lexical representation:

~~~java
import jakarta.xml.bind.annotation.adapters.XmlAdapter;
import java.time.OffsetDateTime;
import java.time.format.DateTimeFormatter;

public class OffsetDateTimeAdapter
        extends XmlAdapter<String, OffsetDateTime> {

    @Override
    public OffsetDateTime unmarshal(String value) {
        return value == null
                ? null
                : OffsetDateTime.parse(
                        value,
                        DateTimeFormatter.ISO_OFFSET_DATE_TIME);
    }

    @Override
    public String marshal(OffsetDateTime value) {
        return value == null
                ? null
                : value.format(
                        DateTimeFormatter.ISO_OFFSET_DATE_TIME);
    }
}
~~~

Attach the adapter to a field:

~~~java
@XmlJavaTypeAdapter(OffsetDateTimeAdapter.class)
@XmlElement(name = "processedAt")
private OffsetDateTime processedAt;
~~~

The field snippet requires importing `jakarta.xml.bind.annotation.adapters.XmlJavaTypeAdapter` and `jakarta.xml.bind.annotation.XmlElement`. Not all partner `xs:dateTime` values contain offsets; the adapter must match the real contract and be tested across UTC and DST transitions.

### 12.3. Enums and Versioning

~~~java
import jakarta.xml.bind.annotation.XmlEnum;
import jakarta.xml.bind.annotation.XmlEnumValue;

@XmlEnum
public enum ErpResult {
    @XmlEnumValue("ACCEPTED") ACCEPTED,
    @XmlEnumValue("REJECTED") REJECTED
}
~~~

If the partner adds `PENDING_REVIEW`, an older JAXB/mapper may not handle it as expected. Establish a contract policy for unknown enum values and compatibility instead of silently coercing unknown values into success.

## 13. Classifying XML and SOAP Errors

| Error category | Examples | Policy |
| --- | --- | --- |
| **Classpath/runtime** | `JAXBException` due to missing provider | Fix dependencies/versions; do not retry the request |
| **Mapping** | Missing `@XmlRootElement`, duplicate property | Fix annotations, `JAXBElement`, or generated model |
| **XML namespace/schema** | Unexpected element, wrong QName, missing required field | Fix contract/payload; do not retry blindly |
| **Business SOAP Fault** | Invalid amount, unknown customer | Map to domain result; do not retry infinitely |
| **Server SOAP Fault** | ERP temporarily unavailable | Bounded retry if side effects are safe |
| **HTTP/TLS transport** | 401/403, timeout, certificate failure | Check auth, network, deadlines |
| **Unknown outcome** | Timeout after sending request | Reconcile/idempotency to avoid duplicate submission |
| **Semantic validation** | Invalid currency despite passing XSD | Check business rules |

Spring OXM typically translates JAXB failures into `XmlMappingException` subclasses. Spring-WS raises `SoapFaultClientException` or corresponding transport errors; never lump everything into `catch(Exception)` and retry.

### 13.1. A SOAP Fault Is Not a Response DTO

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <soap:Fault>
      <faultcode>soap:Client</faultcode>
      <faultstring>Invalid order amount</faultstring>
    </soap:Fault>
  </soap:Body>
</soap:Envelope>
~~~

This is a SOAP 1.1 Fault, not a `SubmitOrderResponse`. Use Spring-WS's fault resolver to separate business faults from infrastructure errors. SOAP 1.2 has a different Fault structure. Never log full fault details containing secrets or expose them directly on public APIs.

## 14. Transactions, Retries, and Idempotency

Suppose a service writes to SQL and then calls ERP SOAP:

~~~text
DB COMMIT succeeds
      |
      +-- SOAP request times out
              |
              +-- ERP may have processed it, but the response was lost
~~~

JAXB only produces XML. A JDBC/JPA `@Transactional` boundary does not include SOAP calls, Redis caches, or broker publishes in a single ACID transaction.

A more reliable pipeline:

~~~mermaid
flowchart LR
    A["Order command"] --> B["SQL transaction"]
    B --> C["Order row"]
    B --> D["Integration outbox"]
    D --> E["Outbox relay / broker"]
    E --> F["SOAP adapter"]
    F --> G["ERP endpoint"]
    F -.-> H["Retry / reconciliation"]
~~~

Design:

1. Within the same SQL transaction, write the business state and an outbox event with a stable operation ID.
2. A worker reads the outbox, maps the JAXB request, and sends the SOAP call.
3. If the ERP supports an idempotency key/`operationId`, reuse **the same key** across retries and redeliveries.
4. If a timeout occurs after sending, attempt a **status lookup** before immediately resending a mutating operation.
5. Track `attempt`/`outcome`/`nextRetryAt`, with backoff/jitter and a DLQ or manual handling path.
6. Acknowledge messages once processing satisfies the contract; consumers must tolerate duplicates.

**There is no automatic exactly-once SOAP delivery.** A call that succeeds on the server but loses its response can be retried and cause duplicate effects unless the ERP supports deduplication or reconciliation.

| Scenario | Retry? | Explanation |
| --- | --- | --- |
| XML violates XSD or QName | No | Contract/data must be fixed |
| SOAP Fault invalid data | No | Business error |
| HTTP 401/403 | Not continuously | Wrong credentials/permissions |
| HTTP 503, transient connect error | Bounded | Backoff and deadline |
| Timeout after write request | Needs idempotency/reconcile | Outcome is unknown |
| ERP returns pending | Follow workflow | Does not mean failure |

Set an **overall retry budget for the whole flow**; avoid letting HTTP transport, broker consumer, and Quartz jobs stack exponential retries uncontrollably.

## 15. Performance, Resources, and Observability

### 15.1. `JAXBContext` Is Expensive; XML Payloads Can Be Large

- Cache `JAXBContext` or use a singleton `Jaxb2Marshaller`; never rebuild the context per event.
- Do not share non-thread-safe JAXB `Marshaller`/`Unmarshaller` instances across threads.
- Enforce byte size and XML depth limits before materializing large object graphs.
- For huge XML or streaming needs, consider SAX/StAX instead of unmarshalling the entire document into RAM.
- Do not mutate schema/context settings on shared beans while traffic is flowing.
- Configure thread pools, HTTP timeouts, and backpressure for the SOAP adapter.

### 15.2. Observing Across Boundaries

| Metric | Meaning |
| --- | --- |
| XML marshal/unmarshal duration | CPU and mapping overhead |
| XSD validation failure count | Broken data contracts |
| SOAP request latency p95/p99 | Network + server + (possibly) mapping |
| SOAP fault rate | Distinguishes business vs. server faults |
| HTTP connect/read timeout count | Transport unresponsiveness |
| Retry/duplicate count | Recovery activity and idempotency hits |
| Outbox oldest age / queue lag | Integration processing delay |
| Business confirmation lag | Time from SQL commit to ERP confirmation |

Example observation around a SOAP call:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.ws.client.core.WebServiceTemplate;

public Object submitObserved(
        WebServiceTemplate template,
        ObservationRegistry registry,
        SubmitOrderRequest request) {

    return Observation.createNotStarted(
                    "integration.soap.submit", registry)
            .lowCardinalityKeyValue("partner", "erp")
            .lowCardinalityKeyValue("operation", "submitOrder")
            .observe(() ->
                    template.marshalSendAndReceive(request));
}
~~~

Observation can emit timers/spans when handlers are configured. It measures the synchronous call and **does not automatically confirm that the final ERP transaction committed**.

Use low-cardinality tags like `partner`, `operation`, and `outcome`. Never put `orderId`, `eventId`, raw XML, credentials, or customer IDs into metric labels. Store those IDs in protected audit logs when needed for reconciliation.

## 16. Testing XML Bindings and SOAP Clients

A round-trip test (object → XML → object) does not prove contract conformance because **the same annotation bug** can exist in both directions. Use official partner XML fixtures and XSDs.

### 16.1. Marshalling Unit Test

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import java.io.StringWriter;
import javax.xml.transform.stream.StreamResult;

import static org.junit.jupiter.api.Assertions.assertTrue;

class JaxbMappingTest {

    @Test
    void writesOrderXml() throws Exception {
        Jaxb2Marshaller mapper = new Jaxb2Marshaller();
        mapper.setClassesToBeBound(
                SubmitOrderRequest.class);
        mapper.afterPropertiesSet();

        SubmitOrderRequest request =
                new SubmitOrderRequest(
                        "ORD-100", 1890000L, "VND");

        StringWriter writer = new StringWriter();
        mapper.marshal(
                request,
                new StreamResult(writer));

        String xml = writer.toString();
        assertTrue(xml.contains("SubmitOrderRequest"));
        assertTrue(xml.contains("ORD-100"));
    }
}
~~~

This test is a smoke test; contract tests should parse the XML with a secure parser and assert **root QName, namespace, child order, and XSD validity**. Substring checks with `contains` cannot catch namespace mismatches.

### 16.2. Testing SOAP Payloads Without a Real Server

Spring-WS provides `MockWebServiceServer` to mock message transport. Example testing the request payload:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.test.client.MockWebServiceServer;
import org.springframework.xml.transform.StringSource;

import static org.springframework.ws.test.client.RequestMatchers.payload;
import static org.springframework.ws.test.client.ResponseCreators.withPayload;

class ErpSoapClientTest {

    @Test
    void submitsOrderPayload() throws Exception {
        Jaxb2Marshaller mapper = new Jaxb2Marshaller();
        mapper.setClassesToBeBound(
                SubmitOrderRequest.class,
                SubmitOrderResponse.class);
        mapper.afterPropertiesSet();

        WebServiceTemplate template = new WebServiceTemplate();
        template.setMarshaller(mapper);
        template.setUnmarshaller(mapper);
        template.setDefaultUri("https://erp.test/soap/orders");

        MockWebServiceServer server =
                MockWebServiceServer.createServer(template);

        String requestXml =
                "<m:SubmitOrderRequest "
                + "xmlns:m=\"urn:example:orders:v1\">"
                + "<m:orderId>ORD-100</m:orderId>"
                + "<m:amountMinor>1890000</m:amountMinor>"
                + "<m:currency>VND</m:currency>"
                + "</m:SubmitOrderRequest>";

        String responseXml =
                "<m:SubmitOrderResponse "
                + "xmlns:m=\"urn:example:orders:v1\">"
                + "<m:accepted>true</m:accepted>"
                + "<m:reference>ERP-55</m:reference>"
                + "</m:SubmitOrderResponse>";

        server.expect(payload(new StringSource(requestXml)))
                .andRespond(
                        withPayload(new StringSource(responseXml)));

        template.marshalSendAndReceive(
                new SubmitOrderRequest(
                        "ORD-100", 1890000L, "VND"));

        server.verify();
    }
}
~~~

This snippet assumes `SubmitOrderResponse` is JAXB-annotated/generated per the XSD and `spring-ws-test` is on the test classpath. It illustrates payload verification; production tests should assert the response object, SOAPAction, headers, SOAP Faults, and transport errors. Check the corresponding matcher APIs if using a different Spring-WS version.

### 16.3. Key Test Matrix

| Scenario | Expectation |
| --- | --- |
| Object → XML | Correct QName, element order, and encoding |
| XML fixture → object | No lost fields, accurate types |
| JAXBElement/generated root | Accurate QName and unwrapping |
| Missing required / invalid type | Schema validation fails |
| Unknown namespace / schema version | Responds per compatibility policy |
| UTF-8 Vietnamese text | No character corruption |
| XML with DTD/XXE | Rejected; no external URL/file reads |
| Oversized XML | Blocked before exhausting RAM |
| SOAP Fault | Accurate error mapping |
| HTTP timeout / 503 | Bounded retries, accurate idempotency |
| Broker redelivery | No duplicate side effects |
| Mapping on Java 17/21 | No accidental javax/Jakarta mixup |
| SQL commit + SOAP failure | Outbox preserves send intent for retry |

## 17. Diagnosing Version and Configuration Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `package javax.xml.bind does not exist` | Legacy JAXB used on a newer JDK without the module | Add compatible JAXB 2 dependency or migrate to Jakarta |
| `ClassNotFoundException jakarta.xml.bind.JAXBContext` | Missing Jakarta JAXB API | Add matching API version |
| JAXB API provider not found | API present without implementation/runtime | Add matching JAXB runtime |
| `NoClassDefFoundError javax/xml/bind/...` | Legacy dependency or generated code inside a Jakarta stack | Select/regenerate JAXB in the matching namespace |
| No root element / unexpected element | Missing `@XmlRootElement`, wrong QName, or `JAXBElement` | Check XSD, `ObjectFactory`, and annotations |
| Syntactically valid XML with null business fields | Schema validation disabled or missing fields | Enable XSD and business validation |
| `IllegalAnnotationsException` | Duplicate field/getter or wrong access strategy | Pick the right `@XmlAccessorType` |
| Compiles on Java 17 but fails at runtime | Wrong runtime classpath/JAXB provider | Inspect runtime dependencies and container JDK |
| XJC generates javax imports on Boot 3 | Outdated codegen tool | Regenerate using Jakarta XJC |
| SOAP Fault treated as mapping error | Unmarshalling a Fault into a response DTO | Use Spring-WS fault resolver |
| XXE vulnerability | XML parser permits DTD/external entities | Harden parser at the first parse boundary |
| Timeout after sending SOAP transaction | ERP may have executed it | Idempotency/reconciliation |
| Memory/CPU spike on large XML | Materializing object graph, recreating `JAXBContext` | Cap input size, reuse context, stream |

Diagnostic order: verify JDK → Spring/WS/JAXB versions → runtime classpath → JAXB namespace/annotations → XSD/QName → SOAP/HTTP faults → business retry/idempotency. Never "fix" errors by disabling validation, enabling DTDs, or retrying all requests infinitely.

## 18. SOAP/JAXB Implementation Checklist

- [ ] Verified Java runtime and `javax`/`jakarta` JAXB generation.
- [ ] JAXB API/runtime/XJC/generated sources match the Spring Boot/Framework version.
- [ ] WSDL/XSD are versioned and XML QNames/namespaces/ordering match the contract.
- [ ] Clear understanding of when classes need `@XmlRootElement` vs. `JAXBElement`/`ObjectFactory`.
- [ ] `JAXBContext`/Spring `Jaxb2Marshaller` is shared; non-thread-safe JAXB mappers are not shared.
- [ ] Separate XSD validation and business validation exist, not just `required=true`.
- [ ] External XML passes through a parser blocking DTDs/external entities with byte and depth limits.
- [ ] SOAP Envelope, SOAP version, action, and WS-Security are handled in Spring-WS per WSDL.
- [ ] TLS, auth, connect/read timeouts, and retry budgets are configured per environment.
- [ ] SOAP Faults, XML mapping errors, transport errors, and business rejections are distinguished.
- [ ] SQL transactions/outbox are not confused with SOAP transactions.
- [ ] Idempotency/reconciliation is designed for timeouts after sending.
- [ ] Unit/XSD/fixture and `MockWebServiceServer` integration tests are in place.
- [ ] Metrics exist for mapping latency, SOAP faults, retries, and outbox lag without leaking payloads/PII.

**Conclusion:** JAXB is the tool for **marshalling and unmarshalling between Java and XML**. To use it effectively in Spring Boot, configure JAXB for your **Java version and `javax`/`jakarta` generation**, map accurately to the XSD, handle `JAXBElement`/generated models properly, and harden the XML parser. `Jaxb2Marshaller` connects JAXB to Spring OXM/Spring-WS; transport, security, retries, transactions, and idempotency remain distinct responsibilities of the integration flow.

## References

- [Spring Framework — O/X Mapping](https://docs.spring.io/spring-framework/reference/data-access/oxm.html): `Jaxb2Marshaller`, Spring OXM, and binding.
- [Spring Web Services — Reference](https://docs.spring.io/spring-ws/docs/current/reference/html/): `WebServiceTemplate`, SOAP clients, and faults.
- [Spring Boot — Web Services](https://docs.spring.io/spring-boot/reference/io/webservices.html): Boot/Spring-WS integration.
- [Jakarta XML Binding — Specifications](https://jakarta.ee/specifications/xml-binding/): API and JAXB/Jakarta versions.
- [JAXB Reference Implementation](https://eclipse-ee4j.github.io/jaxb-ri/): JAXB runtime and XJC code generation.
- [JEP 320 — Remove the Java EE and CORBA Modules](https://openjdk.org/jeps/320): removal of the JAXB module in JDK 11.
- [Java XMLConstants](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/XMLConstants.html): restricting external DTDs/XSDs.
- [OWASP — XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html): secure parsing and XXE mitigation.
- [Spring-WS MockWebServiceServer](https://docs.spring.io/spring-ws/docs/current/api/org/springframework/ws/test/client/MockWebServiceServer.html): isolated SOAP client testing.
