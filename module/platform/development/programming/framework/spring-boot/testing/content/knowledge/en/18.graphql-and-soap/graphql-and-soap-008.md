# @WebServiceClientTest for SOAP Client Applications in Spring Boot

## 1. Objectives and real-world problem

A Spring Boot application may expose REST or GraphQL APIs to customers while needing to call accounting, payment, insurance, or ERP systems over **SOAP** behind the scenes. That integration is typically encapsulated in a client bean built with Spring Web Services (`Spring-WS`), `WebServiceTemplate`, and `WebServiceTemplateBuilder`.

Testing challenges:
- You do not want every `mvn test` run hitting a partner's live SOAP server.
- You need to verify the client generates a **SOAP body** with the right namespaces, elements, and values.
- You need to verify the client calls the right **destination URI** and SOAPAction (if required by the partner), maps the response to domain types, and handles SOAP Faults.
- Tests must be deterministic and independent of DNS, proxies, VPNs, TLS handshakes, or live partner data.
- You do not want `@SpringBootTest` loading the entire database, messaging stack, and web server when testing only a SOAP adapter.

Spring Boot provides **`@WebServiceClientTest`**, a **test slice** for Spring-WS clients. In Spring Boot **3.5.x**, this annotation brings in `MockWebServiceServer` and customizes `WebServiceTemplateBuilder` inside the slice so you can test SOAP requests and responses in-JVM.

Conceptual example:

```java
@WebServiceClientTest(ExchangeRateSoapClient.class)
class ExchangeRateSoapClientTest {

    @Autowired MockWebServiceServer server;
    @Autowired ExchangeRateSoapClient client;

    @Test
    void convertsSoapResponseToDomainValue() {
        server.expect(payload(new StringSource("""
                <fx:GetRateRequest xmlns:fx="urn:example:fx">
                  <fx:currency>USD</fx:currency>
                </fx:GetRateRequest>
                """)))
            .andRespond(withPayload(new StringSource("""
                <fx:GetRateResponse xmlns:fx="urn:example:fx">
                  <fx:rate>1.25</fx:rate>
                </fx:GetRateResponse>
                """)));

        assertThat(client.getRate("USD"))
                .isEqualByComparingTo("1.25");

        server.verify();
    }
}
```

This is a condensed version; full imports, application code, real client, and runnable tests appear in the hands-on section.

**After this lesson, you should be able to distinguish:**
1. `@WebServiceClientTest` tests a **SOAP client**; `@WebServiceServerTest` tests a **SOAP server endpoint**.
2. `MockWebServiceServer` replies to a `WebServiceTemplate` invoked by the client, not a real HTTP server.
3. `WebServiceTemplateBuilder` is the hook Spring Boot customizes to attach the mock sender; `new WebServiceTemplate()` created outside the builder may bypass interception.
4. `server.expect(...).andRespond(...)` registers simulated requests/responses; `server.verify()` confirms every expectation was consumed.
5. SOAP **Envelope/Header/Body**, **XML payloads**, **WSDL/XSD**, SOAPAction, **SOAP Faults**, and transport errors are separate layers requiring intentional tests.
6. Passing slice tests do not prove production credentials, WS-Security, TLS, the partner's live WSDL, or true cross-system compatibility.

## 2. Background: SOAP and classes in Spring Web Services

### 2.1. SOAP uses XML messages, not REST JSON

A typical SOAP 1.1 request structure:

```xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:fx="urn:example:fx">
  <soapenv:Header>
    <!-- SOAP headers, if required by contract -->
  </soapenv:Header>
  <soapenv:Body>
    <fx:GetRateRequest>
      <fx:currency>USD</fx:currency>
    </fx:GetRateRequest>
  </soapenv:Body>
</soapenv:Envelope>
```

In Spring-WS:
- `WebServiceTemplate` drives message creation, sending requests, and receiving responses.
- `WebServiceMessageFactory` creates SOAP messages, typically via SAAJ when matching dependencies are present.
- `WebServiceMessageSender` transports messages over HTTP or another transport.
- `Marshaller`/`Unmarshaller` converts Java objects to XML and back when using `marshalSendAndReceive(...)`.
- `WebServiceTemplateBuilder` is Boot's auto-configured builder for creating and customizing templates.
- `MockWebServiceServer` replaces the **client-side transport** to intercept requests and return mock responses.

When you write `RequestMatchers.payload(new StringSource(...))`, you match the **payload inside the SOAP Body**, not necessarily the full Envelope, HTTP headers, TLS, or WS-Security signatures. This benefits unit/slice tests by avoiding fragile coupling to out-of-scope details. However, if SOAP headers or signatures are mandatory, add dedicated matchers and integration tests.

### 2.2. Namespaces matter more than prefixes

The following two XML snippets have identical element meanings when their namespace URIs match:

```xml
<fx:GetRateRequest xmlns:fx="urn:example:fx">
  <fx:currency>USD</fx:currency>
</fx:GetRateRequest>
```

```xml
<GetRateRequest xmlns="urn:example:fx">
  <currency>USD</currency>
</GetRateRequest>
```

An element's qualified name is **`{namespaceURI}localName`**, not merely the `fx` prefix string. When asserting, use XML-aware matchers or namespace-aware XPath/DOM. Never compare raw XML strings when a test cares only about structure/semantics; attribute order, namespace prefixes, and whitespace can vary across serializers.

**Warning:** Do not assume every XML structural comparator ignores all whitespace or prefixes under every configuration; matching strictness depends on XMLUnit's comparator and matcher configuration. If whitespace or signature canonicalization is required, write dedicated checks.

### 2.3. SOAP Body vs. SOAP Envelope

`<fx:GetRateRequest>` is the **payload** inside `soapenv:Body`. `WebServiceTemplate.sendSourceAndReceiveToResult(...)` accepts the payload `Source` and wraps it in a SOAP Envelope via the message factory; client code normally does not assemble the Envelope manually.

Passing a full `<soapenv:Envelope>` into `StringSource` as if it were the body payload can create a malformed message (an Envelope nested inside Body). Before writing a test, verify whether the API expects a **payload**, a SOAP message, or a raw HTTP request.

### 2.4. SOAPAction and WS-Addressing are not the same

- **SOAPAction** in SOAP 1.1 is an HTTP header expressing the contract action, set via `SoapActionCallback`.
- **WS-Addressing Action** is a SOAP header defined by WS-Addressing specs; Spring-WS provides a separate `ActionCallback`.
- They can relate yet are not interchangeable; never assume checking the SOAPAction HTTP header verifies WS-Addressing.
- SOAP 1.2 attaches action rules to Content-Type differently than SOAP 1.1.

When a partner supplies a WSDL/policy, inspect the exact **binding**, **SOAP version**, action, and header rules before writing tests.

## 3. What does @WebServiceClientTest actually do?

### 3.1. Exact annotations and packages in Spring Boot 3.5

```java
import org.springframework.boot.test.autoconfigure.webservices.client.WebServiceClientTest;
import org.springframework.ws.test.client.MockWebServiceServer;
```

A typical test class:

```java
@WebServiceClientTest(ExchangeRateSoapClient.class)
class ExchangeRateSoapClientTest {
    @Autowired ExchangeRateSoapClient client;
    @Autowired MockWebServiceServer server;
}
```

Per the 3.5 Javadoc, `@WebServiceClientTest` is composed of these meta-annotations:

```java
@OverrideAutoConfiguration(enabled = false)
@TypeExcludeFilters(WebServiceClientExcludeFilter.class)
@AutoConfigureCache
@AutoConfigureMockWebServiceServer
@AutoConfigureWebServiceClient
@ImportAutoConfiguration
```

This block shows the annotation's composition, not a standalone Java file. It means:
- Disables broad auto-configuration from `@EnableAutoConfiguration`.
- Narrows component scanning via the slice's filter rules.
- Imports auto-configurations relevant to the client, mock server, and supporting infrastructure.
- Avoids spinning up a full production-like application context.

**Do not** treat this as `@SpringBootTest` "with an extra annotation." It is a **slice with a distinct set of beans**.

### 3.2. Selecting the exact component under test

Syntax:

```java
@WebServiceClientTest(ExchangeRateSoapClient.class)
```

or:

```java
@WebServiceClientTest(components = ExchangeRateSoapClient.class)
```

`value` and `components` are aliases. Specify the component explicitly to keep test scope controlled; avoid writing bare `@WebServiceClientTest` assuming every `@Service` or repository in the app will be scanned. The Javadoc notes default scanning primarily includes `@JsonComponent` and Jackson `Module`s; specific client beans should be named explicitly.

Other attributes include `properties`, `includeFilters`, `excludeFilters`, `excludeAutoConfiguration`, and `useDefaultFilters`. Avoid widening filters indiscriminately just to silence missing-bean errors: add only the exact dependencies required by the client under test.

### 3.3. MockWebServiceServer provided by Boot

Spring Boot 3.5 auto-configures `MockWebServiceServer` and customizes the `WebServiceTemplateBuilder` used in the slice. This allows:

```java
server.expect(payload(new StringSource("<request/>")))
      .andRespond(withPayload(new StringSource("<response/>")));
```

This illustrates the structure. When the client uses a template built from Boot's builder, the mock sender intercepts the request with no real TCP connection to the partner. If the request violates an expectation, the test fails; if the client fails to send an expected request, `verify()` catches the unconsumed expectation.

### 3.4. WebServiceTemplateBuilder is the critical link

Spring Boot provides the **builder**, yet normally **does not auto-register a single `WebServiceTemplate` bean** because applications often require different destinations, marshallers, interceptors, or credentials.

Production code should look like:

```java
@Service
public class ExchangeRateSoapClient {
    private final WebServiceTemplate template;

    public ExchangeRateSoapClient(WebServiceTemplateBuilder builder) {
        this.template = builder
                .setDefaultUri("https://soap.partner.test/fx")
                .build();
    }
}
```

This is an illustrative excerpt; the complete class is in section 8. The builder configures default URI, message senders, customizers, interceptors, marshallers/unmarshallers, and HTTP client settings. During testing, Boot customizes the builder to attach the mock transport.

**Distinction:** Injecting `WebServiceTemplateBuilder` and calling `build()` differs fundamentally from `new WebServiceTemplate()` configured manually outside Boot's mechanism. The latter can hit the real network or escape mock server interception.

### 3.5. What if a client injects WebServiceTemplate directly?

Boot 3.5 Javadoc states that if a client **does not use the builder** and instead injects a `WebServiceTemplate` bean, you can add:

```java
@WebServiceClientTest(LegacySoapClient.class)
@AutoConfigureWebServiceClient(registerWebServiceTemplate = true)
class LegacySoapClientTest {
    @Autowired MockWebServiceServer server;
    @Autowired LegacySoapClient client;
}
```

`LegacySoapClient` is an example name, absent from the runnable project in section 8. Import:

```java
import org.springframework.boot.test.autoconfigure.webservices.client.AutoConfigureWebServiceClient;
```

`registerWebServiceTemplate` defaults to **false** because the recommended design constructs templates via the builder. Enable this flag when the client legitimately injects a template directly. Never enable it blindly in an app with multiple templates or custom wiring: confirm which template is mocked and where the bean originates.

### 3.6. What the test slice does not do automatically

`@WebServiceClientTest` does not automatically:
- Start a real SOAP server or deploy a partner's `MessageDispatcherServlet`.
- Fetch a production WSDL URL and verify the live binding.
- Instantiate all application `@Service`/`@Repository`/`@ConfigurationProperties` beans.
- Supply production secrets, tokens, truststores/keystores, or WS-Security policies.
- Replicate every SOAP transport detail, timeout, retry, or multi-hop gateway.
- Replace end-to-end integration tests against a partner sandbox.

Those are **intentional** slice boundaries, not bugs.

## 4. How MockWebServiceServer tests the client

```text
JUnit @Test
  |
  |  server.expect(connectionTo(...))
  |        .andExpect(payload(...))
  |        .andRespond(withPayload(...))
  |
  v
ExchangeRateSoapClient.getRate("USD")
  |
  v
WebServiceTemplate (created by builder)
  |
  v
Mock WebServiceMessageSender / MockWebServiceServer
  |
  +--> checks URI, XML payload, SOAP metadata if matched
  +--> returns simulated SOAP response payload or SOAP Fault
  |
  v
WebServiceTemplate receives and processes message
  |
  v
Client parses/maps response into BigDecimal/domain result
  |
  v
AssertJ asserts domain result
  |
  v
server.verify() confirms all expectations were consumed
```

The biggest benefit: you verify the **exact XML produced by the client**, how it invokes `WebServiceTemplate`, and how it parses/unmarshals responses, **without** a real server.

### 4.1. Standard steps

1. Inject the configured `MockWebServiceServer`.
2. Declare one or more `expect(RequestMatcher)` rules.
3. Chain `andExpect(RequestMatcher)` as needed.
4. Define `andRespond(ResponseCreator)`.
5. Invoke the client method under test.
6. Assert the domain return value or thrown exception.
7. Call `server.verify()` to confirm every expectation was executed.

When reusing the same mock server across methods in a cached Spring context, reset expectations cleanly per test; the runnable example uses `@BeforeEach server.reset()`.

### 4.2. Common request matchers

| Matcher | What it verifies | Value |
| --- | --- | --- |
| `connectionTo("https://...")` | Destination URI used by the client | Catches calling the wrong sandbox/production endpoint |
| `payload(new StringSource(xml))` | XML payload inside SOAP Body | Namespaces, elements, business fields |
| `validPayload(resource)` | Payload conforms to XSD | Schema contract when XSD resource is available |
| `xpath(expression, ...)` | Node/value via XPath | Dynamic fields, namespaces, paths |
| `soapHeader(...)` | SOAP header presence/value | Partial metadata contract verification |
| `anything()` | No request constraint | Use only when the request itself is genuinely not under test |

`validPayload`/`xpath` have specific overloads and semantics by Spring-WS version; provide matching Resources/namespace contexts and XML test dependencies. Never copy a placeholder matcher and claim the entire WSDL is validated.

### 4.3. Common response creators

| Creator | Meaning | When to use |
| --- | --- | --- |
| `withPayload(new StringSource(xml))` | Returns SOAP response with XML payload | Happy paths / mapping |
| `withClientOrSenderFault(reason, locale)` | SOAP Client/Sender fault | Input/business validation errors from partner |
| `withServerOrReceiverFault(reason, locale)` | SOAP Server/Receiver fault | Partner server-side errors |
| `withError(message)` | Simulates transport connection error | Connection failure paths |
| `withException(exception)` | Simulates exception during transport | Exception-typed fault injection |
| `withVersionMismatchFault(...)` | SOAP version mismatch | Testing SOAP version incompatibility handling |

**Do not equate SOAP Faults with HTTP 500:** SOAP servers return fault envelopes per SOAP protocol, and HTTP status codes depend on SOAP version and transport. Spring-WS typically throws `SoapFaultClientException` by default. `withError` simulates a transport failure with no SOAP Fault payload.

## 5. SOAP client tests vs. SOAP server tests

| Question | Client test | Server test |
| --- | --- | --- |
| Boot annotation | `@WebServiceClientTest` | `@WebServiceServerTest` |
| Subject under test | Bean using `WebServiceTemplate` for outbound calls | Spring-WS `@Endpoint` receiving SOAP requests |
| Simulated party | External SOAP server | SOAP caller/client |
| Test utility | `MockWebServiceServer` | `MockWebServiceClient` |
| Test flow | Expect outbound SOAP request; simulate response | Send inbound SOAP request; expect server response |
| Does client transport use network? | No, when using the mock builder properly | No, endpoint runs inside test context |
| Real partner SOAP server needed? | No | No |
| Core verification focus | Body/URI/headers client builds and response/fault handling | Payload routing, endpoint adapter, marshalling, server response/faults |

**Common mistake:** injecting `MockWebServiceClient` inside `@WebServiceClientTest` expecting it to intercept outbound calls. The two classes have opposite directions. `MockWebServiceServer` is the right class for testing an **outbound client**.

### 5.1. Comparison with REST/GraphQL testing

- Boot REST clients use `@RestClientTest` with `MockRestServiceServer` or matching REST builders.
- Spring MVC controllers use `@WebMvcTest` + `MockMvc`/`MockMvcTester`.
- Spring WebFlux controllers use `@WebFluxTest` + `WebTestClient`.
- GraphQL servers use `@GraphQlTest` + `GraphQlTester`.
- SOAP clients use `@WebServiceClientTest` + `MockWebServiceServer`.

Even when these technologies coexist in one app, never stack multiple slice annotations like `@RestClientTest` and `@WebServiceClientTest` on one class to "combine everything." Test each boundary properly; when true multi-layer integration is required, use `@SpringBootTest` with targeted mock integrations.

## 6. Maven dependencies and Spring Boot 3.5 packages

### 6.1. Production dependency

In Spring Boot **3.5**, the exact Spring Web Services starter artifact is:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web-services</artifactId>
</dependency>
```

Note the hyphen between `web` and `services` in **Boot 3.5**. Spring Boot 4 reorganizes starter and module naming; always use artifact names and packages matching your project's major version rather than copying Boot 4 docs into Boot 3.5.

### 6.2. Test dependency

`spring-boot-starter-test` brings in JUnit Jupiter, AssertJ, Mockito, and Spring Boot test support. The library containing `MockWebServiceServer` is:

```xml
<dependency>
    <groupId>org.springframework.ws</groupId>
    <artifactId>spring-ws-test</artifactId>
    <scope>test</scope>
</dependency>
```

Declaring `spring-ws-test` explicitly avoids assuming `spring-boot-starter-test` pulls the Spring-WS testing module transitively. The Spring Boot 3.5 BOM manages `spring-ws-test`'s version; do not pin a separate version without a specific compatibility reason.

### 6.3. Key class names and packages

| Class/annotation | Package in Boot 3.5 / Spring-WS |
| --- | --- |
| `@WebServiceClientTest` | `org.springframework.boot.test.autoconfigure.webservices.client` |
| `@AutoConfigureWebServiceClient` | `org.springframework.boot.test.autoconfigure.webservices.client` |
| `@AutoConfigureMockWebServiceServer` | `org.springframework.boot.test.autoconfigure.webservices.client` |
| `WebServiceTemplateBuilder` | `org.springframework.boot.webservices.client` |
| `WebServiceTemplate` | `org.springframework.ws.client.core` |
| `SoapActionCallback` | `org.springframework.ws.soap.client.core` |
| `SoapFaultClientException` | `org.springframework.ws.soap.client` |
| `MockWebServiceServer` | `org.springframework.ws.test.client` |
| `RequestMatchers` | `org.springframework.ws.test.client` |
| `ResponseCreators` | `org.springframework.ws.test.client` |
| `StringSource` / `StringResult` | `org.springframework.xml.transform` |
| `Jaxb2Marshaller` | `org.springframework.oxm.jaxb` |

Import errors commonly happen when mixing Spring Boot 4 examples (new test module packages) into a Spring Boot 3.5 project.

## 7. Hands-on lab design

The sample application has a client calling an exchange-rate partner. The client accepts a currency code such as `USD` and returns a `BigDecimal` parsed from XML.

### 7.1. XML contract used in the example

Outbound request payload:

```xml
<fx:GetRateRequest xmlns:fx="urn:example:fx">
  <fx:currency>USD</fx:currency>
</fx:GetRateRequest>
```

Inbound success payload:

```xml
<fx:GetRateResponse xmlns:fx="urn:example:fx">
  <fx:rate>1.25</fx:rate>
</fx:GetRateResponse>
```

Test specification:
- Destination: `https://soap.partner.test/fx` — sample URI only, **no network call occurs in mock tests**.
- SOAPAction: `urn:example:fx/GetRate` — set via `SoapActionCallback`.
- Business input: exactly three uppercase ASCII letters `[A-Z]{3}`.
- Output: `BigDecimal`; never convert exchange rates via `double`.
- XML namespace URI: `urn:example:fx`; the client checks the namespace when parsing responses.
- If the response lacks a single `<fx:rate>` or contains an invalid number, the client throws `IllegalStateException`.
- If the SOAP server returns a Fault, Spring-WS handles it through the fault resolver and client tests verify the exception.

### 7.2. Why use Source/Result instead of JAXB in the runnable project?

Spring-WS supports two common styles:
1. `marshalSendAndReceive` using `Jaxb2Marshaller` and classes generated from XSD/WSDL.
2. `sendSourceAndReceiveToResult` using XML `Source` and `Result` directly.

This lesson chooses the **second** for the runnable project: fewer generated JAXB dependencies and clearer visibility into the SOAP payload and mock server role. That does not mean manual XML handling should be the production default; when stable WSDL/XSD schemas exist, contract-first JAXB classes and schema validation are usually preferred. Later sections explain how to extend toward that style.

## 8. Complete Maven project: Java 17 + Spring Boot 3.5.16

### 8.1. Directory layout

```text
soap-client-test-lab/
├── pom.xml
├── src/main/java/com/example/soaplab/
│   ├── SoapClientLabApplication.java
│   └── ExchangeRateSoapClient.java
└── src/test/java/com/example/soaplab/
    ├── ExchangeRateSoapClientTest.java
    └── ExchangeRateParseTest.java
```

All Java files reside in `package com.example.soaplab`; test classes end with `Test` for Maven Surefire discovery. There are no controllers or server endpoints in this app; it is purely an **outbound SOAP client**.

### 8.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>soap-client-test-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web-services</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.ws</groupId>
            <artifactId>spring-ws-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Explanation:
- Spring Boot parent/BOM manages dependency versions.
- `spring-boot-starter-web-services` pulls in Spring-WS, XML support, and matching SOAP runtime libraries.
- `spring-boot-starter-test` supplies JUnit Jupiter, AssertJ, and Spring Test.
- `spring-ws-test` supplies the client-side mock server.
- No database, Spring Data, or Kafka is declared since none is needed.
- `spring-boot-maven-plugin` supports running as a Spring Boot application, even though unit/slice tests do not launch a partner server.

### 8.3. Application class

`src/main/java/com/example/soaplab/SoapClientLabApplication.java`:

```java
package com.example.soaplab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SoapClientLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(SoapClientLabApplication.class, args);
    }
}
```

In `@WebServiceClientTest`, Boot uses this application configuration class to locate context configuration, while **slice filters** control which beans are loaded rather than running full production component scanning.

### 8.4. ExchangeRateSoapClient.java

`src/main/java/com/example/soaplab/ExchangeRateSoapClient.java`:

```java
package com.example.soaplab;

import java.io.IOException;
import java.io.StringReader;
import java.math.BigDecimal;

import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.parsers.ParserConfigurationException;

import org.springframework.boot.webservices.client.WebServiceTemplateBuilder;
import org.springframework.stereotype.Service;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.soap.client.core.SoapActionCallback;
import org.springframework.xml.transform.StringResult;
import org.springframework.xml.transform.StringSource;

import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;
import org.xml.sax.InputSource;
import org.xml.sax.SAXException;

@Service
public class ExchangeRateSoapClient {

    private static final String NS = "urn:example:fx";
    private static final String SOAP_URI = "https://soap.partner.test/fx";
    private static final String SOAP_ACTION = "urn:example:fx/GetRate";

    private final WebServiceTemplate template;

    public ExchangeRateSoapClient(WebServiceTemplateBuilder builder) {
        this.template = builder
                .setDefaultUri(SOAP_URI)
                .build();
    }

    public BigDecimal getRate(String currency) {
        // Allow only 3 uppercase ASCII letters to prevent
        // injecting arbitrary XML when building StringSource.
        if (currency == null || !currency.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException(
                    "Currency must contain exactly three uppercase letters");
        }

        String requestXml = """
                <fx:GetRateRequest xmlns:fx="urn:example:fx">
                  <fx:currency>%s</fx:currency>
                </fx:GetRateRequest>
                """.formatted(currency);

        StringResult result = new StringResult();

        boolean responseReceived =
                template.sendSourceAndReceiveToResult(
                        new StringSource(requestXml),
                        new SoapActionCallback(SOAP_ACTION),
                        result);

        if (!responseReceived) {
            throw new IllegalStateException("SOAP response payload is missing");
        }

        return parseRate(result.toString());
    }

    // Package-private so unit tests can test the parser directly
    // without starting a Spring context or SOAP transport.
    static BigDecimal parseRate(String xml) {
        try {
            DocumentBuilderFactory factory =
                    DocumentBuilderFactory.newInstance();
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
            factory.setXIncludeAware(false);
            factory.setExpandEntityReferences(false);

            Document document = factory.newDocumentBuilder()
                    .parse(new InputSource(new StringReader(xml)));

            Element root = document.getDocumentElement();
            if (root == null
                    || !"GetRateResponse".equals(root.getLocalName())
                    || !NS.equals(root.getNamespaceURI())) {
                throw new IllegalStateException(
                        "Unexpected SOAP response root or namespace");
            }

            NodeList rates = root.getElementsByTagNameNS(NS, "rate");
            if (rates.getLength() != 1) {
                throw new IllegalStateException(
                        "Expected exactly one rate element");
            }

            String value = rates.item(0).getTextContent().trim();
            if (value.isEmpty()) {
                throw new IllegalStateException(
                        "SOAP rate must not be empty");
            }
            return new BigDecimal(value);
        }
        catch (ParserConfigurationException
                | SAXException
                | IOException
                | NumberFormatException ex) {
            throw new IllegalStateException(
                    "Invalid SOAP rate response", ex);
        }
    }
}
```

**What this code demonstrates:**
- The client accepts `WebServiceTemplateBuilder` via constructor injection, letting Boot customizers swap in the mock transport.
- `setDefaultUri` configures the SOAP endpoint, which tests verify with `connectionTo`.
- `SoapActionCallback` sets the action per the sample contract; real partners may specify a different action.
- `sendSourceAndReceiveToResult` sends a **payload Source**, not a raw SOAP Envelope.
- `StringResult` receives the response payload extracted from the SOAP Body by `WebServiceTemplate`.
- `parseRate` checks the root QName (local name + namespace URI), exactly one `rate` element, and numeric content rather than comparing raw XML text.
- The XML parser disables DOCTYPE declarations and external entities to mitigate XXE risks on untrusted XML; production requires secure parsing combined with marshalling/validation per security standards.
- Because `currency` allows only `[A-Z]{3}`, characters like `<`, `&`, or quotes cannot corrupt XML structure. For free-form inputs (names, addresses), **never** concatenate XML strings manually; use `XMLStreamWriter`, a JAXB marshaller, or proper XML escaping.
- `parseRate` is package-private for standalone unit testing; in production you can extract the XML decoder into a dedicated testable component/module.

**Security scope:** Validating inputs against XML injection and disabling DOCTYPE on the parser are essential, yet they do not replace schema validation, WS-Security signature verification, or XML size limits.

### 8.5. ExchangeRateSoapClientTest.java

`src/test/java/com/example/soaplab/ExchangeRateSoapClientTest.java`:

```java
package com.example.soaplab;

import java.util.Locale;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.webservices.client.WebServiceClientTest;
import org.springframework.ws.soap.client.SoapFaultClientException;
import org.springframework.ws.test.client.MockWebServiceServer;
import org.springframework.xml.transform.StringSource;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.ws.test.client.RequestMatchers.connectionTo;
import static org.springframework.ws.test.client.RequestMatchers.payload;
import static org.springframework.ws.test.client.ResponseCreators.withPayload;
import static org.springframework.ws.test.client.ResponseCreators.withServerOrReceiverFault;

@WebServiceClientTest(ExchangeRateSoapClient.class)
class ExchangeRateSoapClientTest {

    private static final String DESTINATION =
            "https://soap.partner.test/fx";

    private static final String USD_REQUEST = """
            <fx:GetRateRequest xmlns:fx="urn:example:fx">
              <fx:currency>USD</fx:currency>
            </fx:GetRateRequest>
            """;

    private static final String USD_RESPONSE = """
            <fx:GetRateResponse xmlns:fx="urn:example:fx">
              <fx:rate>1.25</fx:rate>
            </fx:GetRateResponse>
            """;

    @Autowired
    MockWebServiceServer server;

    @Autowired
    ExchangeRateSoapClient client;

    @BeforeEach
    void resetExpectations() {
        server.reset();
    }

    @Test
    void sendsExpectedPayloadToExpectedUri() {
        server.expect(connectionTo(DESTINATION))
                .andExpect(payload(new StringSource(USD_REQUEST)))
                .andRespond(withPayload(
                        new StringSource(USD_RESPONSE)));

        assertThat(client.getRate("USD"))
                .isEqualByComparingTo("1.25");

        server.verify();
    }

    @Test
    void mapsDifferentRateWithoutDependingOnWhitespace() {
        String eurRequest = """
                <fx:GetRateRequest xmlns:fx="urn:example:fx">
                  <fx:currency>EUR</fx:currency>
                </fx:GetRateRequest>
                """;
        String eurResponse = """
                <fx:GetRateResponse xmlns:fx="urn:example:fx">
                  <fx:rate>0.9250</fx:rate>
                </fx:GetRateResponse>
                """;

        server.expect(payload(new StringSource(eurRequest)))
                .andRespond(withPayload(
                        new StringSource(eurResponse)));

        assertThat(client.getRate("EUR"))
                .isEqualByComparingTo("0.925");

        server.verify();
    }

    @Test
    void propagatesSoapServerFaultAsException() {
        server.expect(payload(new StringSource(USD_REQUEST)))
                .andRespond(withServerOrReceiverFault(
                        "Partner temporarily unavailable",
                        Locale.ENGLISH));

        assertThatThrownBy(() -> client.getRate("USD"))
                .isInstanceOf(SoapFaultClientException.class)
                .hasMessageContaining("Partner temporarily unavailable");

        server.verify();
    }

    @Test
    void rejectsInvalidCurrencyBeforeSoapCall() {
        assertThatThrownBy(() -> client.getRate("US<"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("three uppercase letters");

        // No expectations registered; verify() confirms
        // no pending required requests remain.
        server.verify();
    }

    @Test
    void rejectsSuccessPayloadWithoutRate() {
        String invalidResponse = """
                <fx:GetRateResponse xmlns:fx="urn:example:fx">
                  <fx:status>OK</fx:status>
                </fx:GetRateResponse>
                """;

        server.expect(payload(new StringSource(USD_REQUEST)))
                .andRespond(withPayload(
                        new StringSource(invalidResponse)));

        assertThatThrownBy(() -> client.getRate("USD"))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("Expected exactly one rate element");

        server.verify();
    }

    @Test
    void rejectsNonNumericRate() {
        String invalidResponse = """
                <fx:GetRateResponse xmlns:fx="urn:example:fx">
                  <fx:rate>not-a-number</fx:rate>
                </fx:GetRateResponse>
                """;

        server.expect(payload(new StringSource(USD_REQUEST)))
                .andRespond(withPayload(
                        new StringSource(invalidResponse)));

        assertThatThrownBy(() -> client.getRate("USD"))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("Invalid SOAP rate response");

        server.verify();
    }
}
```

**Why does this test the real client?**
- `ExchangeRateSoapClient` is instantiated by Spring as the real bean.
- `WebServiceTemplate` is built via Boot's real builder (customized for mocking).
- `MockWebServiceServer` validates the outbound XML and URI and supplies scripted replies/faults.
- The real `parseRate` converts the XML response into a `BigDecimal`.
- Assertions verify domain outcomes/exceptions instead of mocking the client itself.

With `@WebServiceClientTest`, unrelated beans such as repositories or database services stay out of the context. This keeps tests focused and faster than full-context integration tests in large applications.

**Note on `@BeforeEach server.reset()`:** Resetting isolates expectations when the Spring TestContext cache reuses the same instance across methods. Each test still calls `server.verify()` to confirm the request ran. When multiple test classes share a context, structure the suite so they do not run in parallel against a single mock server with mutable expectations unless isolated.

### 8.6. ExchangeRateParseTest.java: unit test without Spring

`src/test/java/com/example/soaplab/ExchangeRateParseTest.java`:

```java
package com.example.soaplab;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class ExchangeRateParseTest {

    @Test
    void parsesXmlWithDefaultNamespace() {
        String xml = """
                <GetRateResponse xmlns="urn:example:fx">
                  <rate>1.2500</rate>
                </GetRateResponse>
                """;

        assertThat(ExchangeRateSoapClient.parseRate(xml))
                .isEqualByComparingTo("1.25");
    }

    @Test
    void refusesUnexpectedNamespace() {
        String xml = """
                <GetRateResponse xmlns="urn:wrong:namespace">
                  <rate>1.25</rate>
                </GetRateResponse>
                """;

        assertThatThrownBy(
                () -> ExchangeRateSoapClient.parseRate(xml))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("root or namespace");
    }

    @Test
    void refusesDtdAndExternalEntityPayload() {
        String xml = """
                <!DOCTYPE GetRateResponse [
                  <!ENTITY hidden SYSTEM "file:///etc/passwd">
                ]>
                <GetRateResponse xmlns="urn:example:fx">
                  <rate>&hidden;</rate>
                </GetRateResponse>
                """;

        assertThatThrownBy(
                () -> ExchangeRateSoapClient.parseRate(xml))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("Invalid SOAP rate response");
    }

    @Test
    void refusesEmptyRate() {
        String xml = """
                <GetRateResponse xmlns="urn:example:fx">
                  <rate></rate>
                </GetRateResponse>
                """;

        assertThatThrownBy(
                () -> ExchangeRateSoapClient.parseRate(xml))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("must not be empty");
    }
}
```

These tests do not exercise SOAP transport or the Spring Boot builder; they strictly test the XML decoder. Separating them avoids spinning up a Spring context for every edge case in the response parser while verifying namespace checks, empty values, and XXE defenses.

### 8.7. Running the tests

From `soap-client-test-lab` with JDK 17+, Maven, and access to the dependency repository:

```bash
mvn -q clean test

mvn -q -Dtest=ExchangeRateSoapClientTest test
mvn -q -Dtest=ExchangeRateParseTest test
```

Inspect reports:

```text
target/surefire-reports/
```

These classes are designed to PASS under the contract described in the lesson. If a build fails, examine the actual compiler/log/root cause; do not expect identical stdout across every machine. **The example needs no live SOAP server and sends zero requests to `https://soap.partner.test/fx` during mock tests.**

You can start the application with:

```bash
mvn spring-boot:run
```

However, the demo application **has no REST controller or console runner calling SOAP automatically**, so Boot run merely starts the context without invoking `getRate`. To test integration with a real partner, obtain a partner-provided sandbox endpoint and write dedicated integration tests; never use the placeholder example address for live network tests.

## 9. SOAPAction, headers, and XSD: raising verification depth

### 9.1. When a partner requires SOAPAction

The example production client invokes:

```java
template.sendSourceAndReceiveToResult(
        requestSource,
        new SoapActionCallback("urn:example:fx/GetRate"),
        responseResult);
```

This snippet assumes `template`, `requestSource`, and `responseResult` are declared. `SoapActionCallback` sets the contract action, yet `payload(...)` only inspects the body and **does not prove the action was sent**.

Therefore, when a partner enforces `SOAPAction`, add a custom matcher at the Spring-WS message level:

```java
server.expect(payload(new StringSource(USD_REQUEST)))
      .andExpect((uri, message) -> {
          if (!(message instanceof SoapMessage soap)) {
              throw new AssertionError("Expected SOAP message");
          }
          assertThat(soap.getSoapAction())
                  .contains("urn:example:fx/GetRate");
      })
      .andRespond(withPayload(
              new StringSource(USD_RESPONSE)));
```

This is an **extended snippet for `ExchangeRateSoapClientTest`**; import `org.springframework.ws.soap.SoapMessage` and AssertJ. Using `contains` here avoids coupling to optional HTTP SOAPAction quotation marks; when an exact contract is required, normalize the representation, assert exact equality, and verify the SOAP version. Never mistake `SOAPAction` for `WS-Addressing Action`.

### 9.2. SOAP headers and WS-Security

A real client may attach:
- WS-Security `UsernameToken`.
- Signed `Timestamp`.
- X.509 digital signature.
- WS-Addressing `To`/`Action`/`MessageID`.
- Correlation IDs or partner-specific SOAP headers.

`MockWebServiceServer` can inspect parts of messages and headers via `soapHeader` or custom `RequestMatcher`s, yet a mock server cannot prove:
- That the real server validates signatures, certificate chains, and timestamp clock skew.
- That mutual TLS authentication succeeds in the deployment environment.
- That live credentials remain valid and the partner account holds the right permissions.
- That proxies or load balancers do not alter SOAP envelopes or HTTP headers.

For those risks, run integration/contract tests against an authorized sandbox with fake credentials, test keystores/truststores, and redacted logging. Never place real passwords, private keys, or tokens in test fixtures.

### 9.3. XSD validation

When a WSDL defines a stable `XSD`, store a contract copy in `src/test/resources` and use `RequestMatchers.validPayload(...)` or an equivalent validator to check payloads.

Conceptual example:

```java
// Illustration: "schemas/fx.xsd" must be the partner's real XSD
// and the method signature must match your Spring-WS version's overload.
Resource xsd = new ClassPathResource("schemas/fx.xsd");
server.expect(validPayload(xsd))
      .andRespond(withPayload(new StringSource(USD_RESPONSE)));
```

This is an **optional pattern** outside the section 8 runnable project since no partner XSD is included. XSD tests are meaningful only when the schema matches the namespace/element contract. Never invent a fake XSD or drop required elements just to keep tests green.

A **SOAP body payload** can pass XSD validation while SOAP headers or actions are still wrong. Conversely, a valid `SOAPAction` does not guarantee valid request XML. Verify each risk separately.

### 9.4. Namespace-aware XPath

When elements carry dynamic values (requestId, timestamp), matching full XML payloads becomes hard to maintain. Use an XPath matcher with a namespace map or inspect the DOM directly; never drop namespaces unintentionally.

**Conceptual XPath example:**

```xpath
/fx:GetRateRequest/fx:currency
```

The XPath `fx` prefix in the expression must be bound to namespace URI `urn:example:fx` in the evaluation context. Without namespace mapping, XPath can fail to find nodes even in valid XML. For tests with static business constants like `USD`, `payload(...)` is usually simpler and clearer.

## 10. Testing SOAP failure scenarios

### 10.1. SOAP Faults

A SOAP Fault is a valid SOAP message describing an error. When the mock server replies:

```java
server.expect(payload(new StringSource(USD_REQUEST)))
      .andRespond(withServerOrReceiverFault(
              "Partner temporarily unavailable",
              Locale.ENGLISH));
```

With default `WebServiceTemplate` configuration, Spring-WS's fault resolver normally throws `SoapFaultClientException`. Tests should verify the exception and error semantics rather than assuming every Fault returns `null` or `BigDecimal.ZERO`.

If the business layer translates Faults into domain exceptions such as `PartnerUnavailableException`, place that translation in the adapter and write tests verifying the mapping. Never auto-retry non-idempotent SOAP Faults when the action creates side effects.

### 10.2. Transport errors differ from SOAP Faults

```java
server.expect(payload(new StringSource(USD_REQUEST)))
      .andRespond(withError("Simulated transport failure"));
```

This is an **illustrative snippet**; Spring-WS can throw `WebServiceTransportException` depending on the simulated failure and error handler setup. This is not an XML SOAP Fault and does not verify an actual N-second network timeout.

For real DNS, connection timeout, or socket reset errors, network-level integration tests or dedicated transport-abstraction tests are far more reliable. Slice/unit tests only verify that the client handles the thrown exception appropriately.

### 10.3. XML success response missing a field

If the SOAP server sends:

```xml
<fx:GetRateResponse xmlns:fx="urn:example:fx">
  <fx:status>OK</fx:status>
</fx:GetRateResponse>
```

The client must not treat it as rate `0` or "success" merely because no SOAP Fault arrived. The runnable test `rejectsSuccessPayloadWithoutRate` catches this exact mistake. Distinguish:
- Protocol-valid SOAP message **missing `rate`**.
- Valid XML violating the **business contract**.
- Missing response payload / one-way operation.
- Transport/timeout error.
- SOAP Fault.

Never collapse all of these into one ambiguous `null`.

### 10.4. XML with the wrong namespace

```xml
<GetRateResponse xmlns="urn:another:fx">
  <rate>1.25</rate>
</GetRateResponse>
```

Same local name, different namespace URI. If the API contract requires `urn:example:fx`, the client must reject it or apply an explicitly defined version-compatibility policy. The runnable `ExchangeRateParseTest` tests this case to ensure parsers do not mistakenly use `getElementsByTagName("rate")`.

### 10.5. Response with multiple rate elements

If a payload contains two `rate` elements, the sample parser rejects it instead of picking the first one. In real SOAP schemas, cardinality is dictated by the XSD. Never silently pick the first element when the contract expects exactly one; if the response is a collection, model it with explicit cardinality validation.

### 10.6. SOAP request never sent

A test might register an expectation and forget to invoke the client:

```java
server.expect(payload(new StringSource(USD_REQUEST)))
      .andRespond(withPayload(new StringSource(USD_RESPONSE)));

// Did not call client.getRate("USD")
server.verify();  // Must report the unused expectation
```

This is an **intentionally failing example**, not part of the runnable project. It demonstrates why `verify()` matters: mocking a response without asserting client calls or calling `verify()` allows false passes.

### 10.7. Client sending to the wrong destination URI

If the client switches to `https://wrong.partner.test/fx`, `connectionTo("https://soap.partner.test/fx")` fails. However, if the client uses a destination provider, routing logic, or per-call URI, match expectations to the behavior under test and never hardcode secret production URLs in tests. When hosts come from configuration properties, use sandbox or placeholder test properties.

## 11. When the client needs JAXB marshalling

### 11.1. Contract-first approach

When a partner supplies a WSDL/XSD, teams commonly generate Java classes from the schema and use `Jaxb2Marshaller`:

```java
Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
marshaller.setContextPath("com.example.partner.generated");
marshaller.afterPropertiesSet();

WebServiceTemplate template = builder
        .setMarshaller(marshaller)
        .setUnmarshaller(marshaller)
        .setDefaultUri("https://soap.partner.test/fx")
        .build();
```

This is an **illustrative snippet**, outside the runnable project in section 8: package `com.example.partner.generated` and generated JAXB classes must exist, along with compatible JAXB dependencies. In Spring Boot 3.x, JAXB namespaces use **`jakarta.xml.bind`**, never mixing legacy `javax.xml.bind`.

With JAXB, `marshalSendAndReceive(requestDto, new SoapActionCallback(...))` performs:
1. Marshals the DTO into an XML payload.
2. Wraps the payload in a SOAP Body and adds SOAP headers/action.
3. Sends via the configured sender.
4. Receives the SOAP response and unmarshals it back to a DTO.
5. Processes Faults via the resolver.

`@WebServiceClientTest` still works when Boot's builder is customized properly. Using `payload(...)` verifies the actual XML generated by JAXB, which is far more valuable than mocking `WebServiceTemplate.marshalSendAndReceive(...)` and verifying the method call.

### 11.2. Why not mock WebServiceTemplate completely in every test?

If a pure Mockito test writes:

```java
when(template.marshalSendAndReceive(any()))
        .thenReturn(new GetRateResponse());
```

This is only an **illustrative snippet**; there are no generated classes in the project. It verifies how a service handles a response DTO, yet **proves nothing** about request XML, namespaces, JAXB annotations, SOAPAction, message senders, or fault resolvers. When risk lies in serialization or protocol, `MockWebServiceServer` is superior.

Large systems can use both layers:
- Business service unit tests mock the SOAP adapter interface.
- SOAP client slice tests use `MockWebServiceServer` to verify XML, headers, and faults.
- Partner sandbox integration/contract tests verify TLS, WSDL, and security interoperability.

### 11.3. @ConfigurationProperties and marshaller beans in the slice

`@WebServiceClientTest` does not automatically scan every `@ConfigurationProperties` or `@Configuration` in the app. If the client constructor needs a properties class, add `@EnableConfigurationProperties(PartnerSoapProperties.class)` alongside the slice's `properties=...`. If the client needs a marshaller bean from a custom config, use `@Import(TestMarshallerConfiguration.class)` or an explicitly included `@TestConfiguration`.

Never import the entire application configuration into the slice just for one properties bean: that pulls in database/messaging dependencies and slows tests down. Avoid hardcoding private endpoints or credentials in tests; use mock URIs and test-only values.

## 12. When to use @SpringBootTest instead of @WebServiceClientTest?

| Need | Test slice | Full test / integration |
| --- | --- | --- |
| Client builds proper request XML | `@WebServiceClientTest` fits | Full context unnecessary |
| Client reads responses and handles Faults | `@WebServiceClientTest` fits | Full when coordinating multi-layer policies |
| Client needs a few helper configs/properties | Slice + `@Import`/`@EnableConfigurationProperties` | Full if wiring graph is genuinely complex |
| Real service + repository + SOAP adapter wiring | Slice scope insufficient | `@SpringBootTest` with fake external dependencies |
| Spring Security/WS-Security interceptors in app graph | Slice needs imported config | Full/contract when security is central |
| TLS/truststore/mTLS with partner sandbox | Mock server does not verify | Controlled network integration |
| End-to-end testing of a SOAP endpoint exposed by your app | `@WebServiceServerTest` for server slice | Full server integration |
| Partner's live WSDL and XSD compatibility | Can validate stored contract copies | Authorized, stable sandbox checks |

The Spring Boot reference recommends `@WebServiceClientTest` for SOAP clients. `@SpringBootTest` does not auto-provide a mock server bean; when you need mock support inside a full context, add `@AutoConfigureMockWebServiceServer` when templates follow the compatible builder path, taking care to manage multiple templates, customizers, and context caching.

**Never** combine `@WebServiceClientTest` and `@SpringBootTest` on the same class to get "both slice and full." Each carries its own bootstrap and auto-configuration semantics; choose one boundary and wire the appropriate test support.

### 12.1. Two clients using two different templates

`@AutoConfigureMockWebServiceServer` configures **one** mock server by default. In an app with multiple SOAP clients using separate templates, do not assume every template is intercepted independently by the same server; when testing multiple clients, create dedicated mock servers per template (e.g., `MockWebServiceServer.createServer(template)`) or separate test contexts/methods.

If client A executes against an expectation set for client B, the test fails; never "reset" everything to hide broken routing logic. In production apps routing by tenant, data center, or version, add dedicated tests verifying destination selection.

### 12.2. WebServiceGatewaySupport

Legacy SOAP gateways sometimes extend `WebServiceGatewaySupport` instead of injecting the builder. `MockWebServiceServer` offers factory methods `createServer(WebServiceGatewaySupport)` and `createServer(WebServiceTemplate)` for manual wiring. Ensure the mock sender attaches to the exact template instance in use; merely annotating with `@WebServiceClientTest` does not guarantee interception if a template was instantiated outside Boot's builder.

### 12.3. REST client vs. SOAP client

`MockRestServiceServer` targets REST clients (`RestTemplate`/`RestClient`) using HTTP methods, URIs, and JSON; `MockWebServiceServer` targets Spring-WS SOAP `WebServiceTemplate` using XML, Envelopes, and Faults. Despite similar names, they are not interchangeable.

## 13. Common errors and troubleshooting

### 13.1. No qualifying bean of type MockWebServiceServer

**Causes:**
- Using `@SpringBootTest` while forgetting `@AutoConfigureMockWebServiceServer`.
- Using `@WebServiceServerTest` (server slice) instead of the client slice.
- Missing `spring-ws-test` on the test classpath.
- Test not running through Spring Boot TestContext / mismatched Spring Boot versions.
- `@AutoConfigureMockWebServiceServer(enabled=false)` or custom exclusions disabled support.

**Resolution:** Verify exact Boot 3.5 annotations/packages, `spring-ws-test`, and test configuration; avoid manually declaring a detached mock server bean just to satisfy autowiring.

### 13.2. Client bean not found

`@WebServiceClientTest` loads only components matching its scope. If the client sits outside the scanned package or `components` is wrong, Spring will not instantiate it. Pass `@WebServiceClientTest(MyClient.class)` or `@Import(MyClient.class)`. If the client depends on services or repositories, add `@MockitoBean` or `@Import` specific collaborators rather than opening full component scanning.

### 13.3. No qualifying bean of type WebServiceTemplate

The client constructor injects the template directly while Boot creates only the builder by default. Add:

```java
@AutoConfigureWebServiceClient(registerWebServiceTemplate = true)
```

to the client test, or declare a proper `@Bean WebServiceTemplate` for custom setups. When multiple named templates exist, use explicit `@Qualifier` annotations. Never register an unconfigured template lacking marshaller/URI just to make context startup pass.

### 13.4. Mock server receives no request, yet connection refused occurs

Common causes: the client instantiated `new WebServiceTemplate()`, built the template before mock customizers attached, or injected a different template instance than the mocked one. Network errors indicate traffic escaped to real transport.

Check:
1. Does the client constructor accept Spring's `WebServiceTemplateBuilder`?
2. Is the template built cleanly during builder lifecycle?
3. Was `MockWebServiceServer` bound to the exact `WebServiceTemplate` instance being called?
4. Did custom code overwrite `setMessageSender` after the mock customizer ran?
5. Are there multiple template beans where the client invokes the wrong one?

Never "fix" this by enabling internet access in CI or calling a live production partner from tests.

### 13.5. Request does not match expected XML

Possible reasons:
- Wrong namespace URI despite matching local name.
- Wrong root element, field name, or schema sequence order.
- XML marshalling changed `@XmlElement` or `@XmlSchema`/JAXB package context.
- Prefix, whitespace, or attribute representation differs under the XML comparator.
- SOAP Body accidentally includes a nested Envelope.
- Input values differ due to profile, properties, or clock.

Use XML-aware comparators and read diffs carefully; use `xpath` or schema validation when payloads contain dynamic fields. Never blindly update expected XML to match actual output when the actual output violates the partner contract.

### 13.6. SOAPAction is set in code, yet partner rejects the call

`SoapActionCallback` sets the action, yet the partner may require:
- A different action URI matching the WSDL.
- SOAP 1.1 vs. 1.2 header semantics.
- A separate WS-Addressing Action.
- Content-Type, authentication, or signed headers per policy.

Mock server tests prove the client sets the action; only sandbox integration tests prove the partner accepts all wire-level requirements.

### 13.7. server.verify() reports an unconsumed expectation

Check whether the client method actually called `WebServiceTemplate`, or returned early due to validation, an open circuit breaker, or a cache hit. A SOAP client returning a cached value may legitimately skip outbound calls, so test expectations must match the scenario. Never delete `verify()` to silence failures; align expectations with the path under test.

### 13.8. SOAP Fault treated as a parse error

`WebServiceTemplate` normally uses `FaultMessageResolver` to throw an exception before you parse a success body. If client code catches all `Exception`s and returns a default rate of `0`, errors are swallowed; separate Faults from transport errors and invalid payloads. For custom mapping, catch specific exceptions or inspect fault codes/details rather than swallowing everything.

### 13.9. Duplicate SOAP expectations when tests run in parallel

`MockWebServiceServer` holds mutable expectations. If two test methods share the same context/mock server concurrently, `reset`/`expect`/`verify` race against each other. Disable parallel execution for those tests or isolate contexts/mock servers rather than sharing one stateful singleton mock across concurrent tests.

### 13.10. @WebServiceClientTest is slow due to loading too many beans

Inspect custom `@ComponentScan` annotations on the root app, broad `@Import`s, deep constructor dependency chains, and unneeded auto-configurations. Slices stay fast only when boundaries stay tight; keep the SOAP adapter focused on SOAP mapping and test business services separately.

### 13.11. XML parser fails on DTD or external entities

This is often the **desired security behavior** when untrusted XML carries DOCTYPE/XXE. Never disable secure parser features just to make a test pass. If a legitimate partner truly requires DTDs, perform risk analysis and configure safe allowlist resolvers rather than permitting arbitrary external entity resolution.

### 13.12. JAXB javax/jakarta errors

Spring Boot 3.x / Spring Framework 6 use modern Jakarta APIs. Legacy generated classes using `javax.xml.bind.*` can clash with `jakarta.xml.bind.*` runtimes and marshallers. Generate classes from XSD using a Jakarta-compatible JAXB plugin and inspect the Maven dependency tree instead of pinning conflicting JAXB runtime versions against the Boot BOM.

### 13.13. Cannot find XSD or WSDL in tests

`ClassPathResource("schemas/partner.xsd")` succeeds only when the file sits at `src/test/resources/schemas/partner.xsd` or a valid classpath location. Avoid referencing live production WSDL URLs inside unit tests. Store versioned partner schemas with checksums/versions and review contract updates explicitly.

### 13.14. Mockito test passes, yet SOAP XML is wrong

Mocking `WebServiceTemplate` to return a prebuilt DTO never tests the marshaller or SOAP message. Add `MockWebServiceServer` tests for outbound wire-level XML contracts rather than treating business-logic unit tests as a substitute for client slice tests.

### 13.15. Errors from missing endpoint configuration in tests

If the client reads its URI from `partner.soap.uri` and the test omits that property, the builder may lack a default URI; `sendSourceAndReceiveToResult(Source,Result)` requires one. Supply the property via `@WebServiceClientTest(properties="partner.soap.uri=https://...")` or an appropriate test bean. Never hardcode secret production URIs in test sources.

## 14. Testing negative paths and reliability

### 14.1. Input validation before network calls

In the project, `getRate("US<")` throws `IllegalArgumentException` before building XML or calling the template. That prevents raw XML injection and avoids wasted outbound calls.

However, regex `[A-Z]{3}` checks format only; it still accepts non-existent three-letter codes. When the domain requires valid ISO 4217 codes, validate against an explicit allowlist/business rule rather than claiming the regex guarantees a real currency.

### 14.2. Retries and idempotency

For a **read-only** SOAP operation like `GetRate`, retrying transient errors can make sense; for **payment or create-order** SOAP operations, blind retries risk duplicate transactions. When implementing retries or circuit breakers:
- Verify call counts using sequential mock expectations.
- Classify precisely which errors are retryable.
- Use idempotency keys when supported by the partner.
- Test timeouts and backoff with virtual time or test clocks when needed.
- Never conclude from `withError(...)` that real TLS/networking is tested.

In `MockWebServiceServer`, multiple expectations match sequentially in declared order. To test three retry attempts, register three chained responses/errors and call `verify()`; do not register one expectation expecting it to absorb three calls.

### 14.3. Circuit breakers and fallbacks

When a circuit breaker is open, the client may skip sending a SOAP request. A test verifying the open-circuit fallback should **not** register outbound expectations, or should assert zero outbound calls via appropriate instrumentation. Avoid cramming circuit-breaker state logic and XML payload structure into one hard-to-read test.

### 14.4. Timeouts exist at multiple layers

Different timeout layers include:
- Connection timeout on the HTTP message sender.
- Read/response timeout on the message sender.
- Business operation / future timeout.
- Test runner timeout.

`@WebServiceClientTest` with a mock sender runs without real network latency. Setting tiny timeouts in unit tests does not verify production timeout configuration; inspect builder configuration and add bounded integration tests when needed.

### 14.5. SOAP logging and sensitive data

SOAP bodies often carry PII, account numbers, auth codes, and SOAP security tokens. When tests fail, avoid dumping entire XML fixtures containing real secrets. Use synthetic identifiers and redact `Authorization`, `UsernameToken`, `Signature`, or private request bodies before archiving CI logs.

## 15. Multi-layer test plan for a SOAP adapter

| Layer | Tool | Verifies | Does not verify |
| --- | --- | --- | --- |
| Pure domain unit | JUnit/AssertJ | Business rules, rounding, validation | SOAP requests/transport |
| XML parser/marshaller unit | JUnit + XML/JAXB | XML QNames, schema fields, Java mapping | Destination URI/network |
| SOAP client slice | `@WebServiceClientTest + MockWebServiceServer` | Outbound request XML/URI/action, response/fault mapping | Real SOAP server, TLS |
| Full Spring wiring | `@SpringBootTest` + fake outbound | Multi-bean wiring, configs, and adapters together | Live production partner |
| Partner sandbox contract | Real HTTP/SOAP client in controlled environment | TLS, auth, WSDL, policies, sandbox compatibility | Does not guarantee production matches sandbox |
| Production smoke/monitoring | Authorized non-mutating probe | Basic availability | Never replaces test suites or sends risky payloads |

Never run side-effecting payment or cancel-order SOAP tests against production without explicit authorization and isolation. Use sandbox/synthetic test accounts, correlation IDs, and cleanup.

### 15.1. When should you verify the full SOAP Envelope?

`payload(...)` suffices for many contract-first operations, yet it does not cover:
- SOAP 1.1 vs. SOAP 1.2 envelope namespaces and Content-Type.
- SOAP headers with `mustUnderstand` or `role`.
- Attachments/MTOM.
- WS-Security signatures, digests, and canonicalization.
- WS-Addressing `Action`, `To`, and `MessageID`.
- Transport-level authentication.

Whenever one of those is a major risk, add message/header matchers and targeted integration tests at the right layer. Avoid forcing every unit test to compare full Envelopes byte-for-byte, which makes suites brittle and slow.

### 15.2. Contract evolution and schema versioning

Long-lived SOAP integrations may upgrade namespaces from `v1` to `v2`, rename operations, reorder elements, or toggle optional fields. When contracts evolve:
1. Diff old and new WSDL/XSD files.
2. Identify breaking vs. additive schema changes.
3. Regenerate JAXB sources if applicable.
4. Update request XML fixtures to the new version.
5. Add negative tests for critical incompatibilities.
6. Run slice tests first, followed by sandbox compatibility tests.

A mock server passing with old fixtures cannot detect that a partner deployed WSDL v2; when version drift is a risk, maintain an explicit contract refresh and review process.

## 16. Anti-patterns and better alternatives

| Anti-pattern | Consequence | Better approach |
| --- | --- | --- |
| `new WebServiceTemplate()` in client alongside auto mock server | Mock may fail to intercept; sends real HTTP | Inject Boot's builder or call `createServer(template)` explicitly |
| Using `@WebServiceServerTest` for an outbound client | Tests server endpoints; wrong boundary | `@WebServiceClientTest` |
| Mocking the SOAP client itself under test | Never verifies generated request XML | Keep client real + `MockWebServiceServer` |
| Setting `andRespond` without `verify()` | Skips detecting unexecuted requests | Assert outcomes and call `server.verify()` |
| Comparing raw XML strings | Fails on benign prefix/whitespace differences | XML-aware `payload`/`XPath`/`XSD` matchers |
| Asserting payload only, omitting required URI | Client could call wrong endpoint | Add `connectionTo` |
| Asserting payload only, omitting SOAPAction/policy | Misses contract headers | Custom header/action matchers or sandbox tests |
| Hitting live partner server during `mvn test` | Flaky, slow, risks real data | Mock server in slices |
| Booting full app context for every SOAP client test | Pulls unrelated DB/messaging dependencies | Slice + selective collaborators |
| Ignoring SOAP Faults and timeouts | Broken fallbacks/retries when partner fails | Test faults and transport errors explicitly |
| Using `String.format` with free-form XML input | XML injection / malformed requests | JAXB / XML writer or proper escaping |
| Parsing XML without blocking external entities | XXE vulnerability | Secure parser + schema validation |
| Using JSONPath on XML | Wrong tool | XPath / XMLUnit / DOM |
| Equating SOAPAction with WS-Addressing | Wrong header contract | Check separately per WSDL/policy |
| Mixing `javax` and `jakarta` JAXB packages | Classloading/marshalling failures | Align Jakarta APIs with Boot 3.x |
| Running tests concurrently against one mock server | Mutable expectations collide | Isolate or run sequentially |

## 17. Hands-on exercises

1. Create `@WebServiceClientTest(ExchangeRateSoapClient.class)` and inject `MockWebServiceServer`. Explain why no partner server is needed.
2. Change the `USD_REQUEST` fixture to `EUR` while still calling `client.getRate("USD")`. Observe the XML matcher failure and explain why.
3. Pass a different URL to `connectionTo`; explain why the test fails even though a mock response is configured.
4. Return a response with namespace `urn:example:fx:v2`. Observe how the client parser reacts and propose a version-migration strategy.
5. Trigger SOAP Faults with `withClientOrSenderFault` and compare the resulting exception with `withServerOrReceiverFault`.
6. Refactor the client to inject `WebServiceTemplate` directly, run the slice, and apply `@AutoConfigureWebServiceClient(registerWebServiceTemplate=true)`.
7. Add a test using `@MockitoBean` for a secondary client collaborator; explain why you should not import a real repository.
8. Add a custom matcher verifying `SoapMessage.getSoapAction()`. Distinguish SOAPAction from WS-Addressing Action.
9. Place an XSD in `src/test/resources`; use `validPayload` matching your Spring-WS version to check elements and namespaces.
10. Register two expectations for two sequential SOAP calls; verify call order and `server.verify()`.
11. Simulate a transport error and decide which exceptions map to business errors and which should retry.
12. Write parser unit tests for empty `rate`, multiple `rate` elements, wrong QName, malformed XML, and DOCTYPE.
13. Explain why a passing `@WebServiceClientTest` does not prove partner sandbox truststores/mTLS work.
14. If a SOAP client uses JAXB generated classes, verify the marshalled request XML with `payload(...)` instead of merely mocking `marshalSendAndReceive`.
15. Compare `MockWebServiceServer` with `MockRestServiceServer`, `MockWebServiceClient`, and `MockMvc` in terms of boundaries.

You have mastered this lesson when you can clearly explain **client/template/mock server/transport**, classify **payload/header/fault**, and write deterministic tests relying only on controlled fixtures.

## 18. Pre-merge checklist

- [ ] Are Spring Boot/JDK/dependencies identified clearly with `@WebServiceClientTest` imported from the right package?
- [ ] Do tests include `spring-ws-test` and `spring-boot-starter-web-services` matching Boot 3.5?
- [ ] Is the real client named in `value`/`components` instead of mocking the SUT?
- [ ] Does the client construct `WebServiceTemplate` using Boot's `WebServiceTemplateBuilder`?
- [ ] If injecting `WebServiceTemplate` directly, was `registerWebServiceTemplate=true` evaluated?
- [ ] Is `MockWebServiceServer` bound to the exact template being invoked?
- [ ] Is the outbound URI verified when contractual?
- [ ] Is XML payload checked for namespaces, root element, and business fields?
- [ ] Are SOAPAction/WS-Addressing headers tested if required by the partner?
- [ ] Is XML/JAXB-to-domain response mapping asserted?
- [ ] Are SOAP Faults and transport errors covered as separate test cases?
- [ ] Is `server.verify()` invoked without ignoring unused expectations?
- [ ] Are invalid inputs tested to ensure bad requests are rejected before sending?
- [ ] Are real secrets and customer data excluded from XML test fixtures?
- [ ] Do unit/slice tests avoid sending live HTTP requests to production?
- [ ] Have DAOs, databases, and full app contexts been kept out of the SOAP client slice when unneeded?
- [ ] Are XML schemas/namespace versions validated when contractual?
- [ ] Are secure XML parsing and XML injection protections in place?
- [ ] Do concurrent tests avoid sharing mutable mock server expectations unsafely?
- [ ] Are XML parser unit tests separated from SOAP transport tests to minimize context cost?
- [ ] Are sandbox integration tests maintained separately for TLS, WS-Security, and interoperability?
- [ ] Were Maven tests executed and any actual failures reviewed before finalizing?

**Conclusion:** `@WebServiceClientTest` is **Spring Boot's dedicated test slice for Spring-WS SOAP clients**. It works best when clients construct `WebServiceTemplate` via Boot's `WebServiceTemplateBuilder` and tests use `MockWebServiceServer` to verify outbound request XML/URI/headers while simulating responses and faults. Combining `server.verify()`, error-path tests, and XML parsing/schema checks yields fast, isolated suites that guard vital SOAP contracts. When verifying mTLS, live SOAP endpoints, or partner WSDL compatibility, add sandbox integration tests rather than inferring network verification from passing mock tests.

## 19. Official documentation

- Spring Boot 3.5 — Testing Spring Boot Applications, Auto-configured Spring Web Services Client Tests: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 — Web Services, Calling Web Services with WebServiceTemplate: https://docs.spring.io/spring-boot/3.5/reference/io/webservices.html
- Spring Boot 3.5 Javadoc — WebServiceClientTest: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/webservices/client/WebServiceClientTest.html
- Spring Boot 3.5 Javadoc — AutoConfigureWebServiceClient: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/webservices/client/AutoConfigureWebServiceClient.html
- Spring Boot 3.5 Javadoc — AutoConfigureMockWebServiceServer: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/webservices/client/AutoConfigureMockWebServiceServer.html
- Spring Boot 3.5 Javadoc — WebServiceTemplateBuilder: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/webservices/client/WebServiceTemplateBuilder.html
- Spring Boot 3.5 — Managed dependency coordinates (spring-ws-test, starter): https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html
- Spring Web Services — Reference, Client-side Testing / MockWebServiceServer: https://docs.spring.io/spring-ws/docs/4.0.10/reference/html/
- Spring Web Services — MockWebServiceServer API: https://www.springframework.org/spring-ws/docs/4.0.11/api/org/springframework/ws/test/client/MockWebServiceServer.html
- Spring Web Services — WebServiceTemplate API: https://docs.spring.io/spring-ws/docs/4.0.17/api/org/springframework/ws/client/core/WebServiceTemplate.html
- Spring Boot 4 migration guide: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide