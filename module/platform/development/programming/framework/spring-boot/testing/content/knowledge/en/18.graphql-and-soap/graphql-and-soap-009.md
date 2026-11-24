# Spring Boot Testing — @WebServiceServerTest and MockWebServiceClient by Supported Version

## 1. The problem: testing a SOAP endpoint without starting an HTTP server

When a Spring Boot application **exposes** a SOAP Web Service via Spring Web Services (Spring-WS), we need to verify that an XML request routes to the right `@Endpoint` and namespace, calls the expected business collaborator, and produces an XML/SOAP response conforming to the contract.

In REST, many developers are familiar with `@WebMvcTest` + `MockMvc`. For **SOAP server-side** testing, the equivalent pair is:

- **`@WebServiceServerTest`:** Spring Boot's test slice focused on Spring-WS `@Endpoint` and `EndpointInterceptor` beans.
- **`MockWebServiceClient`:** a simulated client sending SOAP messages to the Spring-WS `MessageDispatcher` **inside the Spring context**, without opening a real HTTP socket.
- **`RequestCreators`:** builds SOAP requests from an XML **payload** (usually via `StringSource` or a resource).
- **`ResponseMatchers`:** asserts response payloads, SOAP Faults, XPath, XSD schemas, or SOAP headers.

A typical test statement:

```java
client.sendRequest(
          RequestCreators.withPayload(
              new StringSource("<g:GreetRequest xmlns:g='urn:demo:greeting:v1'>...</g:GreetRequest>")))
      .andExpect(ResponseMatchers.noFault())
      .andExpect(ResponseMatchers.payload(expectedPayload));
```

This snippet illustrates the API only, omitting the full payload and variables. The **runnable** Java 17 project in sections 9–13 includes all files, imports, and dependencies.

### Learning objectives

1. Distinguish Spring-WS SOAP **server tests** from SOAP **client tests** and Spring GraphQL tests.
2. Select dependencies and annotation packages matching **Spring Boot 3.5** vs. **Spring Boot 4**.
3. Understand `@Endpoint` + `@PayloadRoot` + `@RequestPayload` + `@ResponsePayload`.
4. Use `MockWebServiceClient` to assert **namespaces**, XML contents, escaping, and XSD validity.
5. Use `@MockitoBean` for service collaborators when the test slice excludes regular beans.
6. Understand how to test SOAP Faults, SOAP 1.1/1.2, headers, SOAPAction, and WS-Security when required.
7. Move to `@SpringBootTest + @AutoConfigureMockWebServiceClient` when full application wiring is needed.
8. Move to **real HTTP integration tests** when wire-level HTTP, TLS, WSDL endpoints, or gateways matter.
9. Avoid "false green" tests caused by wrong namespaces, asserting non-null only, or confusing server and client mocks.

## 2. Choosing the right tool: SOAP, GraphQL, REST, or outbound SOAP?

| What is the application doing? | Test API or annotation | What is simulated? | Evidence |
| --- | --- | --- | --- |
| **Exposing a Spring-WS SOAP endpoint** | `@WebServiceServerTest` + `MockWebServiceClient` | SOAP request entering Spring-WS dispatcher in context | Mapping by payload QName, XML response/fault |
| **Calling an external SOAP endpoint** | `@WebServiceClientTest` + `MockWebServiceServer` | **External** SOAP server replying to `WebServiceTemplate` | Client builds valid XML requests and parses responses |
| Exposing a REST/MVC controller | `@WebMvcTest` + `MockMvc` | Servlet MVC request | HTTP mapping/status/JSON |
| Exposing a GraphQL resolver | `@GraphQlTest` + `GraphQlTester` | GraphQL execution | Query/mutation schema, data, and GraphQL errors |
| Full Spring-WS application wiring | `@SpringBootTest` + `@AutoConfigureMockWebServiceClient` | Full context, though SOAP dispatcher remains mock-bound | Endpoint + real service/config beans |
| SOAP over a real HTTP socket | `@SpringBootTest(RANDOM_PORT)` + real HTTP/SOAP client | Embedded server + `MessageDispatcherServlet` | URL, SOAP envelope, Content-Type, HTTP status |
| WSDL/XSD/WS-Security deployment contract | Integration test with schema, certs, proxy, gateway | Matching infrastructure | Live compatibility and security |

Point to emphasize: **`MockWebServiceClient` differs from `MockWebServiceServer`.**

- `org.springframework.ws.test.server.MockWebServiceClient` is used to **test your application's server endpoint**.
- `org.springframework.ws.test.client.MockWebServiceServer` is used to **mock an external server** when your application acts as a **SOAP client**.
- Both classes live in `org.springframework.ws:spring-ws-test`, yet their packages, APIs, and simulation directions are opposites.

`MockWebServiceClient` is not an HTTP client with a base URL or port; requests dispatch directly to the endpoint without starting Tomcat, Jetty, or Netty. A passing test with it **does not prove** `/services` URL routing, networking, TLS, HTTP headers, or production gateways.

## 3. Version support — verify before copying imports

### 3.1. Spring Boot 3.5.x

Test annotations:

```java
import org.springframework.boot.test.autoconfigure.webservices.server.WebServiceServerTest;
import org.springframework.boot.test.autoconfigure.webservices.server.AutoConfigureMockWebServiceClient;
import org.springframework.ws.test.server.MockWebServiceClient;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
```

Common Maven dependencies:

```xml
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
```

- `spring-boot-starter-web-services` has a hyphen between `web` and `services` in **Boot 3.x**.
- `spring-ws-test` adds `MockWebServiceClient`, `RequestCreators`, and `ResponseMatchers` to the test classpath; declare it **explicitly** so examples do not rely on transitive starter dependencies.
- `spring-boot-starter-test` supplies JUnit Jupiter, Spring Boot test, and Mockito.
- `@WebServiceServerTest` was introduced in **Spring Boot 2.6**; for older versions, assemble the Spring test context and call `MockWebServiceClient.createClient(...)` manually (see section 16).
- `@MockitoBean` comes from **Spring Framework 6.2+**, matching Boot 3.4/3.5. Boot's legacy `@MockBean` was deprecated in 3.4; for Boot 3.5, write new examples with `@MockitoBean`.

**Do not** use `org.springframework.boot.webservices.test.autoconfigure...` in a 3.5 project: that package belongs to Boot 4's modularized layout.

### 3.2. Spring Boot 4.x

Test infrastructure modules are split by technology:

```java
import org.springframework.boot.webservices.test.autoconfigure.server.WebServiceServerTest;
import org.springframework.boot.webservices.test.autoconfigure.server.AutoConfigureMockWebServiceClient;
import org.springframework.ws.test.server.MockWebServiceClient;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
```

Starter names in Boot 4:

```xml
<!-- Boot 4 orientation snippet; do not paste into a Boot 3.5 POM. -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webservices</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webservices-test</artifactId>
    <scope>test</scope>
</dependency>
```

- `spring-boot-starter-webservices` has **no** hyphen between `web` and `services`.
- `spring-boot-starter-webservices-test` is Boot 4's focused test starter for Spring Web Services testing.
- Annotation packages moved from `org.springframework.boot.test.autoconfigure.webservices.server` to `org.springframework.boot.webservices.test.autoconfigure.server`.
- `MockWebServiceClient`, `RequestCreators`, and `ResponseMatchers` stay in Spring-WS namespace `org.springframework.ws.test.server`.
- Align parent/BOM and dependencies on the **same major version**; never mix a Boot 3.5 POM with a Boot 4 test starter.
- Spring Boot 4 also provides module `spring-boot-webservices-test`; standard Maven projects should use the focused starter instead of manually assembling individual modules that may miss dependencies.

**Version 2.5 and earlier:** `@WebServiceServerTest` did not exist in its 2.6+ form, so merely adding `spring-ws-test` will not provide the import. Instead, use `@SpringJUnitConfig`/`@ContextConfiguration` with your Spring-WS config and call `MockWebServiceClient.createClient(context)` for legacy projects.

### 3.3. Quick lookup table

| Boot line | Server test annotation | Test dependencies | Collaborator mocking |
| --- | --- | --- | --- |
| Boot 2.5 and earlier | No 2.6+-style `@WebServiceServerTest` slice | `spring-ws-test` + Spring test, manual setup | Mockito `@Mock`/test beans or version-appropriate tools |
| Boot 2.6–3.3 | `org.springframework.boot.test.autoconfigure.webservices.server.WebServiceServerTest` | Starter test + `spring-ws-test` | `@MockBean` if supported by that release |
| Boot 3.4–3.5 | Same 3.x package | `spring-boot-starter-test` + `spring-ws-test` | Prefer `@MockitoBean` |
| Boot 4.x | `org.springframework.boot.webservices.test.autoconfigure.server.WebServiceServerTest` | `spring-boot-starter-webservices-test` | `@MockitoBean` |

When a project fails with `package ...WebServiceServerTest does not exist`, first verify the **Boot parent/BOM, dependencies, and package** rather than guessing by mixing imports from two major lines. When starter POM artifact names differ by version, check the dependency tree and reference docs for your exact version.

## 4. How SOAP endpoints work and what the slice actually tests

Spring Web Services uses the **payload root QName** to route to an endpoint. A QName consists of a **namespace URI** and a **local name**:

```xml
<g:GreetRequest xmlns:g="urn:demo:greeting:v1">
    <g:name>Lan</g:name>
</g:GreetRequest>
```

Here:

- Namespace URI = `urn:demo:greeting:v1`.
- Local name = `GreetRequest`.
- Prefix `g` is just an XML shorthand; changing it to `x` while keeping the **same namespace URI** preserves the QName.
- `g:name` is a child element in the **same namespace**, distinct from an unnamespaced `<name>`.

An endpoint:

```java
@Endpoint
public class GreetingEndpoint {
    @PayloadRoot(
        namespace = "urn:demo:greeting:v1",
        localPart = "GreetRequest")
    @ResponsePayload
    public Element greet(@RequestPayload Element payload) {
        // Build XML response.
    }
}
```

Spring-WS `MessageDispatcher` selects the method via `@PayloadRoot`, converts the request payload into `org.w3c.dom.Element` (or a matching JAXB/Source type), and writes the `@ResponsePayload` return value into the SOAP Body.

**Never use `@RestController`/`@PostMapping` in place of `@Endpoint`/`@PayloadRoot` for a contract-first SOAP server test.** Spring MVC and Spring-WS use different mapping and serialization models even when running in the same Servlet container.

### Which beans does @WebServiceServerTest load?

`@WebServiceServerTest(GreetingEndpoint.class)` configures the Spring-WS server infrastructure for the endpoint under test and auto-configures `MockWebServiceClient`. It restricts scanning to relevant components (notably `@Endpoint` and `EndpointInterceptor`), without loading the application's repositories, services, controllers, or brokers.

Practical consequences:

- If the endpoint constructor depends on `GreetingService`, the slice test must provide it via `@MockitoBean` or `@Import` of a test config/bean.
- Do not put `@SpringBootTest` on the **same class** as `@WebServiceServerTest`: the two bootstrap modes conflict in purpose.
- If you want real beans and full auto-configuration, use `@SpringBootTest + @AutoConfigureMockWebServiceClient` (section 13).
- The slice does not verify external HTTP/Servlet URLs; if the real requirement is `/ws/*` or `/services`, write a real HTTP integration test.
- A mocked business service returning the expected value does not prove database queries or outbound SOAP calls work.

### MockWebServiceClient workflow

```mermaid
flowchart LR
    A[JUnit test] --> B[RequestCreators.withPayload]
    B --> C[MockWebServiceClient]
    C --> D[MessageDispatcher in Spring context]
    D --> E[Endpoint mapping by QName]
    E --> F[@Endpoint method]
    F --> G[Mock or real bean]
    G --> H[Spring-WS response message]
    H --> I["ResponseMatchers: payload, XSD, XPath, Fault"]
```

**There is no HTTP socket** in this flow. Messages travel through Spring-WS processing, not a browser or remote SOAP client.

## 5. Distinguishing XML payload from SOAP envelope

A complete SOAP 1.1 message looks like:

```xml
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
    <soap:Header/>
    <soap:Body>
        <g:GreetRequest xmlns:g="urn:demo:greeting:v1">
            <g:name>Lan</g:name>
        </g:GreetRequest>
    </soap:Body>
</soap:Envelope>
```

However, `RequestCreators.withPayload(new StringSource(...))` **expects only the payload**:

```xml
<g:GreetRequest xmlns:g="urn:demo:greeting:v1">
    <g:name>Lan</g:name>
</g:GreetRequest>
```

Spring-WS's test message factory builds the SOAP message/envelope and inserts the payload into the body. Passing an entire `<soap:Envelope>` to `withPayload` treats the Envelope as the **payload root**, breaking endpoint mapping (or producing an envelope nested inside an envelope). This is a very common error.

| What to assert | Matching matcher | Watch out for |
| --- | --- | --- |
| XML payload root/children | `ResponseMatchers.payload(Source)` | Namespace URI/QName and values must match |
| XML child node/value | `ResponseMatchers.xpath(...)` | Namespace map must be right; avoid prefix coupling |
| SOAP 1.1/1.2 envelope | `ResponseMatchers.soapEnvelope(...)` | Verify matching SOAP version and headers if required |
| SOAP header presence | `ResponseMatchers.soapHeader(QName)` | Does not prove WS-Security signatures are valid |
| Payload conforms to XSD | `ResponseMatchers.validPayload(Resource)` | Ensure XSD is actually loaded with right `targetNamespace` |
| No SOAP Fault | `ResponseMatchers.noFault()` | Only rules out SOAP Faults; does not verify payload content |
| Client/sender fault | `ResponseMatchers.clientOrSenderFault()` | Requires proper exception-to-fault mapping |
| Server/receiver fault | `ResponseMatchers.serverOrReceiverFault()` | Depends on resolver and SOAP version |

`ResponseMatchers.payload` compares XML payloads using XML semantics/matchers, not HTTP status 200 or raw JSON. `noFault` passes even if the payload is wrong, so always **chain at least two matchers**.

### Notes on SOAP 1.1 and SOAP 1.2

- SOAP 1.1 uses envelope namespace `http://schemas.xmlsoap.org/soap/envelope/` and typically `Content-Type: text/xml` over HTTP.
- SOAP 1.2 uses namespace `http://www.w3.org/2003/05/soap-envelope` and typically `Content-Type: application/soap+xml`.
- SOAP 1.1 fault codes `Client`/`Server` correspond to SOAP 1.2 `Sender`/`Receiver` in Spring-WS matchers.
- `MockWebServiceClient` tests the configured message factory; it **does not prove** external HTTP clients/proxies negotiate SOAP 1.1/1.2 properly.
- If the production contract requires SOAPAction, MIME attachments, WS-Addressing, or WS-Security, add dedicated tests rather than only comparing XML payloads.

## 6. Creating requests and asserting responses

Shortest form:

```java
import org.springframework.ws.test.server.MockWebServiceClient;
import org.springframework.ws.test.server.RequestCreators;
import org.springframework.ws.test.server.ResponseMatchers;
import org.springframework.xml.transform.StringSource;

// Inside a test with an injected MockWebServiceClient client:
client.sendRequest(
          RequestCreators.withPayload(
              new StringSource(requestXml)))
      .andExpect(ResponseMatchers.noFault())
      .andExpect(ResponseMatchers.payload(
              new StringSource(expectedResponseXml)));
```

This is an **excerpt** requiring `requestXml`, `expectedResponseXml`, and a configured client.

### With XPath

```java
client.sendRequest(RequestCreators.withPayload(
        new StringSource(requestXml)))
      .andExpect(
          ResponseMatchers.xpath(
                  "/g:GreetResponse/g:message",
                  Map.of("g", "urn:demo:greeting:v1"))
              .evaluatesTo("Hello, Lan"));
```

XPath uses the namespace mapping supplied by the test. Avoid running an unmapped XPath query against a namespaced element, because XPath without namespace context may fail to match as expected. Alternatively, use `local-name()` and `namespace-uri()` when asserting namespaces independent of prefixes.

### With XSD

```java
client.sendRequest(RequestCreators.withPayload(
        new StringSource(requestXml)))
      .andExpect(ResponseMatchers.validPayload(
              new ClassPathResource("greeting.xsd")));
```

Response XSD validation catches structural, character, and nested-element bugs. It does not replace business value checks: if the schema allows any string, `"wrong name"` still passes XSD validation. Use **both `payload`/`xpath` and `validPayload`** when schemas are contractual.

### When should you inspect the raw SOAP envelope?

Inspect `soapEnvelope` only when the contract mandates specific SOAP headers, `mustUnderstand`, fault codes, or SOAP versions. For business messages, asserting the payload is cleaner and less coupled to serialization formatting.

## 7. SOAP Faults: configure a resolver rather than assuming "every exception is a Client Fault"

A SOAP Fault is an error response **at the SOAP layer**; HTTP status codes vary by SOAP version and transport. Input/business errors such as a missing name can map to a Client/Sender Fault, while unexpected server failures map to a Server/Receiver Fault.

Example matcher:

```java
client.sendRequest(
        RequestCreators.withPayload(
                new StringSource(invalidRequestXml)))
      .andExpect(ResponseMatchers.clientOrSenderFault());
```

This is an **illustrative excerpt**, valid only when the app configures exception-to-SOAP-Fault mapping (e.g., `SoapFaultAnnotationExceptionResolver`, `SoapFaultMappingExceptionResolver`, or a custom resolver) and the invalid payload reaches that resolver.

**Do not guess:** depending on the framework, resolver, and configuration, an `IllegalArgumentException` may become a Server/Receiver fault rather than Client/Sender. For precision, declare a dedicated domain exception with explicit mapping, then assert fault code, reason text, detail structure, and zero leaked stack traces.

### Configuring a fault via annotation

Orientation snippet (requires imports and Spring context wiring):

```java
@SoapFault(
        faultCode = FaultCode.CLIENT,
        faultStringOrReason = "Invalid greeting request")
public class InvalidGreetingRequestException
        extends RuntimeException {
    public InvalidGreetingRequestException() {
        super("invalid greeting");
    }
}
```

For this annotation to take effect, a Spring-WS resolver such as `SoapFaultAnnotationExceptionResolver` must be registered in the context with an order that does not get shadowed. Without the resolver, annotating the exception class alone does not guarantee a Client Fault.

**Do not expect HTTP REST `@RestControllerAdvice` to handle SOAP faults:** Spring-WS endpoint dispatching and exception resolution follow Spring-WS pipelines, separate from MVC controller exception resolvers.

### Faults do not replace XSD/schema validation tests

A request missing `<g:name>` can still reach the endpoint and cause a runtime exception if the server **does not** enable inbound schema validation. Specifying an XSD in `ResponseMatchers.validPayload` validates the **response**, not **incoming requests**. To verify inbound validation, configure an interceptor such as `PayloadValidatingInterceptor` (or another validation mechanism) and test invalid requests and resulting faults.

## 8. Verifying namespaces: the URI is the identity, not the prefix

These three payloads carry different meanings:

```xml
<!-- 1. Valid namespace -->
<g:GreetRequest xmlns:g="urn:demo:greeting:v1">
    <g:name>Lan</g:name>
</g:GreetRequest>
```

```xml
<!-- 2. Still valid namespace even though prefix changed -->
<x:GreetRequest xmlns:x="urn:demo:greeting:v1">
    <x:name>Lan</x:name>
</x:GreetRequest>
```

```xml
<!-- 3. Wrong namespace URI, so it will not match @PayloadRoot -->
<g:GreetRequest xmlns:g="urn:demo:other:v1">
    <g:name>Lan</g:name>
</g:GreetRequest>
```

Include a happy-path test using a different prefix with the same namespace to catch logic hardcoded to `"g:"`. A wrong namespace typically fails endpoint mapping altogether; it is not a "valid request with a wrong response," and tests must verify exception/fault behavior per actual config.

When using JAXB classes generated from XSD, namespaces, `elementFormDefault`, local names, and root element annotations must align between schema and DTOs. With DOM as in the sample, `getElementsByTagNameNS` reads fields by namespace URI instead of prefix strings.

## 9. Complete Maven/Java 17 project (Spring Boot 3.5)

This example provides a **SOAP greeting endpoint** and a business service:

- `GreetRequest` carries a `name`.
- `GreetingService.greet(name)` returns `"Hello, <name>"` (trimming whitespace).
- `GreetResponse` carries a `message`.
- `@WebServiceServerTest` mocks the service to verify routing and the XML contract.
- `@SpringBootTest + @AutoConfigureMockWebServiceClient` uses the real service to verify wiring while still **opening no HTTP socket**.
- An XSD test fixture confirms the response XML matches the expected schema.

No JAXB classes are used in this project: Spring-WS supports `org.w3c.dom.Element` directly as request/response payloads, fitting a lesson on client tests and namespaces without code generators.

### 9.1. File tree

```text
soap-slice-demo/
├── pom.xml
└── src/
    ├── main/java/example/soapdemo/
    │   ├── SoapDemoApplication.java
    │   ├── GreetingService.java
    │   └── GreetingEndpoint.java
    └── test/
        ├── resources/greeting.xsd
        └── java/example/soapdemo/
            ├── GreetingEndpointSliceTest.java
            ├── GreetingEndpointFullContextTest.java
            └── GreetingServiceUnitTest.java
```

### 9.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>soap-slice-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

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
</project>
```

The Spring Boot parent/BOM manages versions for Spring-WS, JUnit, Mockito, and Spring Framework. Never pick a `spring-ws-test` version from a different Spring-WS major line than the Boot-managed `spring-ws-core`.

### 9.3. SoapDemoApplication.java

`src/main/java/example/soapdemo/SoapDemoApplication.java`:

```java
package example.soapdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SoapDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SoapDemoApplication.class, args);
    }
}
```

Spring Boot auto-configures Spring-WS infrastructure when the starter is present. To publish a WSDL over HTTP in a real app, you also configure schema/WSDL definitions and endpoint URL mappings matching the contract; this slice test **does not automatically generate or verify WSDL publication**.

### 9.4. GreetingService.java

`src/main/java/example/soapdemo/GreetingService.java`:

```java
package example.soapdemo;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException(
                    "name must not be blank");
        }
        return "Hello, " + name.strip();
    }
}
```

The slice test replaces this service with `@MockitoBean`. The full-context test exercises the real service. Separating them avoids assuming "seeing an XML response means business logic was tested."

### 9.5. GreetingEndpoint.java

`src/main/java/example/soapdemo/GreetingEndpoint.java`:

```java
package example.soapdemo;

import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.parsers.ParserConfigurationException;

import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;

@Endpoint
public class GreetingEndpoint {

    static final String NAMESPACE = "urn:demo:greeting:v1";

    private final GreetingService service;

    public GreetingEndpoint(GreetingService service) {
        this.service = service;
    }

    @PayloadRoot(
            namespace = NAMESPACE,
            localPart = "GreetRequest")
    @ResponsePayload
    public Element greet(@RequestPayload Element request)
            throws ParserConfigurationException {

        NodeList names = request.getElementsByTagNameNS(
                NAMESPACE, "name");

        if (names.getLength() != 1) {
            throw new IllegalArgumentException(
                    "exactly one name element required");
        }

        String greeting = service.greet(
                names.item(0).getTextContent());

        // Create a fresh DOM response; never parses untrusted XML.
        Document document = DocumentBuilderFactory
                .newInstance()
                .newDocumentBuilder()
                .newDocument();

        Element response = document.createElementNS(
                NAMESPACE, "g:GreetResponse");
        document.appendChild(response);

        Element message = document.createElementNS(
                NAMESPACE, "g:message");
        message.setTextContent(greeting);
        response.appendChild(message);

        return response;
    }
}
```

Key takeaways:

- `@Endpoint` marks the class as a Spring-WS endpoint.
- `@PayloadRoot` routes by QName `{urn:demo:greeting:v1}GreetRequest`.
- `@RequestPayload Element` receives the **root element of the SOAP Body payload**, not the `SOAP Envelope`.
- `@ResponsePayload` writes the returned Element as the XML payload inside the SOAP response.
- `getElementsByTagNameNS` uses the **namespace URI** and local name, independent of prefixes `g`/`x`.
- `setTextContent` writes content as a **text node**, so `&` is escaped properly by the XML serializer; never build XML via string concatenation to prevent injection.
- `DocumentBuilderFactory.newDocumentBuilder().newDocument()` **only creates** an empty DOM; it does not parse untrusted documents. If you later parse external XML, configure XML parser protections against XXE/DTDs and resource limits.

Throwing `IllegalArgumentException` when `name` is missing is not mapped to a custom Client Fault in this example. To test a stable "invalid input" fault contract, register an exception resolver before asserting fault types; see sections 7 and 15.

### 9.6. greeting.xsd

`src/test/resources/greeting.xsd`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:g="urn:demo:greeting:v1"
    targetNamespace="urn:demo:greeting:v1"
    elementFormDefault="qualified">

    <xs:element name="GreetRequest">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="name" type="xs:string"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>

    <xs:element name="GreetResponse">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="message" type="xs:string"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>

</xs:schema>
```

Setting `elementFormDefault="qualified"` means child elements like `g:name` and `g:message` also belong to namespace `urn:demo:greeting:v1`. Unnamespaced `<name>Lan</name>` **fails** this XSD.

The XSD in `src/test/resources` is loaded by `ClassPathResource("greeting.xsd")`. For production WSDL publication, keep schemas in version-controlled main resources/configuration; having an XSD in tests does not prove the server publishes a WSDL.

## 10. @WebServiceServerTest: testing the SOAP endpoint slice

`src/test/java/example/soapdemo/GreetingEndpointSliceTest.java`:

```java
package example.soapdemo;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoMoreInteractions;
import static org.mockito.Mockito.when;

import java.io.IOException;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.webservices.server.WebServiceServerTest;
import org.springframework.core.io.ClassPathResource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.ws.test.server.MockWebServiceClient;
import org.springframework.ws.test.server.RequestCreators;
import org.springframework.ws.test.server.ResponseMatchers;
import org.springframework.xml.transform.StringSource;

@WebServiceServerTest(GreetingEndpoint.class)
class GreetingEndpointSliceTest {

    private static final String NS = "urn:demo:greeting:v1";

    @Autowired
    MockWebServiceClient client;

    @MockitoBean
    GreetingService service;

    @Test
    void routesSoapPayloadAndReturnsExpectedXml() {
        when(service.greet("Lan"))
                .thenReturn("Hello, Lan");

        String request = """
            <g:GreetRequest xmlns:g="urn:demo:greeting:v1">
                <g:name>Lan</g:name>
            </g:GreetRequest>
            """;

        String expected = """
            <g:GreetResponse xmlns:g="urn:demo:greeting:v1">
                <g:message>Hello, Lan</g:message>
            </g:GreetResponse>
            """;

        client.sendRequest(
                RequestCreators.withPayload(
                        new StringSource(request)))
              .andExpect(ResponseMatchers.noFault())
              .andExpect(ResponseMatchers.payload(
                      new StringSource(expected)));

        verify(service).greet("Lan");
        verifyNoMoreInteractions(service);
    }

    @Test
    void prefixDoesNotChangeNamespaceMapping() {
        when(service.greet("Minh"))
                .thenReturn("Hello, Minh");

        // Prefix x differs from g, yet namespace URI is identical.
        String request = """
            <x:GreetRequest xmlns:x="urn:demo:greeting:v1">
                <x:name>Minh</x:name>
            </x:GreetRequest>
            """;

        client.sendRequest(
                RequestCreators.withPayload(
                        new StringSource(request)))
              .andExpect(ResponseMatchers.noFault())
              .andExpect(ResponseMatchers.xpath(
                      "/g:GreetResponse/g:message",
                      Map.of("g", NS))
                      .evaluatesTo("Hello, Minh"));

        verify(service).greet("Minh");
    }

    @Test
    void xmlSpecialCharactersAreEscapedAsData() {
        when(service.greet("An & Binh"))
                .thenReturn("Hello, An & Binh");

        String request = """
            <g:GreetRequest xmlns:g="urn:demo:greeting:v1">
                <g:name>An &amp; Binh</g:name>
            </g:GreetRequest>
            """;

        String expected = """
            <g:GreetResponse xmlns:g="urn:demo:greeting:v1">
                <g:message>Hello, An &amp; Binh</g:message>
            </g:GreetResponse>
            """;

        client.sendRequest(
                RequestCreators.withPayload(
                        new StringSource(request)))
              .andExpect(ResponseMatchers.noFault())
              .andExpect(ResponseMatchers.payload(
                      new StringSource(expected)));

        verify(service).greet("An & Binh");
    }

    @Test
    void responsePayloadConformsToXsd() throws IOException {
        when(service.greet("Linh"))
                .thenReturn("Hello, Linh");

        String request = """
            <g:GreetRequest xmlns:g="urn:demo:greeting:v1">
                <g:name>Linh</g:name>
            </g:GreetRequest>
            """;

        client.sendRequest(
                RequestCreators.withPayload(
                        new StringSource(request)))
              .andExpect(ResponseMatchers.noFault())
              .andExpect(ResponseMatchers.validPayload(
                      new ClassPathResource("greeting.xsd")))
              .andExpect(ResponseMatchers.xpath(
                      "/g:GreetResponse/g:message",
                      Map.of("g", NS))
                      .evaluatesTo("Hello, Linh"));

        verify(service).greet("Linh");
    }
}
```

**There are 4 JUnit methods** in the slice test. Verified behaviors:

1. A SOAP request payload with the right QName dispatches to `GreetingEndpoint`.
2. The mocked service receives the expected argument; the XML response has the right namespace and payload.
3. Changing the prefix while preserving the namespace URI does not break mapping.
4. An `&` in business text does not produce malformed XML; the payload is properly XML-escaped.
5. The XML response validates against XSD and also contains the exact business value via XPath.

Note on `verifyNoMoreInteractions`: use only after `verify`-ing contractual calls; this test does not depend on interaction counts across **test methods** because Spring TestContext/Mockito resets mocks between tests.

### Why is the service mocked?

`@WebServiceServerTest` does not load regular `@Service` beans. If the endpoint constructor requires `GreetingService` and no bean exists, Spring fails context creation with `NoSuchBeanDefinitionException`/`UnsatisfiedDependencyException`. `@MockitoBean` supplies the mock **inside the Spring context**, unlike `@Mock` which creates only a Java field on the test class that the endpoint never receives.

`@WebServiceServerTest(GreetingEndpoint.class)` is intentional slicing; avoid adding `@Import(WholeApplicationConfiguration.class)` just to "make it pass," as that pulls in databases, schedulers, and external clients beyond the slice's scope.

## 11. Testing pure business logic: skip Spring when unnecessary

`src/test/java/example/soapdemo/GreetingServiceUnitTest.java`:

```java
package example.soapdemo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class GreetingServiceUnitTest {

    private final GreetingService service =
            new GreetingService();

    @Test
    void trimsNameWithoutSpringContext() {
        assertEquals("Hello, Lan",
                service.greet("  Lan  "));
    }

    @Test
    void rejectsBlankName() {
        IllegalArgumentException exception =
                assertThrows(IllegalArgumentException.class,
                        () -> service.greet("   "));
        assertEquals("name must not be blank",
                exception.getMessage());
    }
}
```

There are **2 pure unit tests**. They verify text normalization and validation in the service. They **do not verify** the SOAP dispatcher, XML namespaces, or SOAP Fault mapping. Clean separation between unit and slice tests avoids starting a Spring context just to test `strip()`.

## 12. Full context + MockWebServiceClient: still opens no HTTP socket

When the endpoint needs real beans, properties, repositories, interceptors, or Boot auto-configuration outside the slice, use:

```java
@SpringBootTest
@AutoConfigureMockWebServiceClient
class FullSoapTest {
    @Autowired
    MockWebServiceClient client;
}
```

In Boot 3.5, `@AutoConfigureMockWebServiceClient` resides in `org.springframework.boot.test.autoconfigure.webservices.server`; in Boot 4 it resides in `org.springframework.boot.webservices.test.autoconfigure.server`.

**Important:** `@SpringBootTest` defaults to `WebEnvironment.MOCK` and does not start a TCP server. `MockWebServiceClient` still dispatches in-context. If your goal is testing real HTTP transport, **do not call this a real-server test**.

### Project: GreetingEndpointFullContextTest.java

`src/test/java/example/soapdemo/GreetingEndpointFullContextTest.java`:

```java
package example.soapdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.webservices.server.AutoConfigureMockWebServiceClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ws.test.server.MockWebServiceClient;
import org.springframework.ws.test.server.RequestCreators;
import org.springframework.ws.test.server.ResponseMatchers;
import org.springframework.xml.transform.StringSource;

@SpringBootTest
@AutoConfigureMockWebServiceClient
class GreetingEndpointFullContextTest {

    @Autowired
    MockWebServiceClient client;

    @Test
    void fullApplicationUsesRealGreetingService() {
        String request = """
            <g:GreetRequest xmlns:g="urn:demo:greeting:v1">
                <g:name>  Hoa  </g:name>
            </g:GreetRequest>
            """;

        String expected = """
            <g:GreetResponse xmlns:g="urn:demo:greeting:v1">
                <g:message>Hello, Hoa</g:message>
            </g:GreetResponse>
            """;

        client.sendRequest(
                RequestCreators.withPayload(
                        new StringSource(request)))
              .andExpect(ResponseMatchers.noFault())
              .andExpect(ResponseMatchers.payload(
                      new StringSource(expected)));
    }
}
```

There is **1 full-context test**. It invokes the real `GreetingService` without `@MockitoBean`, proving Boot bean wiring and SOAP dispatching work together. Yet as emphasized, this still does not test live URLs, WSDL publication, HTTP, or TLS security.

### When should you move to RANDOM_PORT?

When you need to verify:

- The SOAP servlet maps to `spring.webservices.path` as expected.
- HTTP POST to `/services` actually accepts SOAP 1.1/1.2 envelopes.
- `Content-Type`, HTTP status, SOAPAction, authentication, or CORS/proxy routing.
- The WSDL document is actually reachable at its published path.
- Client certificates, TLS, or WS-Security over real infrastructure.

Then use `@SpringBootTest(webEnvironment=RANDOM_PORT)`, `@LocalServerPort`, and a real HTTP/SOAP client. Tests must send a **full SOAP Envelope** for the appropriate version—never pass `RequestCreators.withPayload` as a raw HTTP request. Properties such as path and auth must come from real application config. Never hardcode port 8080 in CI.

## 13. Running Maven and expected results

Requires JDK 17+, Maven, and initial dependency download access. From `soap-slice-demo`:

```bash
mvn test
```

Run individual classes:

```bash
mvn test -Dtest=GreetingEndpointSliceTest
mvn test -Dtest=GreetingEndpointFullContextTest
mvn test -Dtest=GreetingServiceUnitTest
```

Test method counts:

| Class | Test count | What is actually verified |
| --- | ---: | --- |
| `GreetingEndpointSliceTest` | 4 | SOAP QName mapping, XML response, escaping, XSD |
| `GreetingEndpointFullContextTest` | 1 | Full context, real service, SOAP response |
| `GreetingServiceUnitTest` | 2 | Business string normalization and blank rejection |
| **Total** | **7** | No real HTTP server, DB, or Docker needed |

**Expected: 7 PASS, 0 FAIL, 0 SKIPPED** when the project and build environment match. This is the expected outcome of the example; actually run `mvn test` to confirm. Java code never calls `System.out.println`, so **there is no fixed application stdout**; Maven/Spring-WS log formatting varies. Inspect `target/surefire-reports` to verify executed counts and root causes on failure.

Example XML expected from the real service:

```xml
<g:GreetResponse xmlns:g="urn:demo:greeting:v1">
    <g:message>Hello, Hoa</g:message>
</g:GreetResponse>
```

Actual SOAP messages carry an Envelope and Body built by Spring-WS's message factory. Never assert raw byte identity, XML prefix formatting, or whitespace matching the snippet above. Use proper XML payload matchers per contract.

## 14. Testing XSD, WSDL, and SOAP Faults under broader contracts

### XSD validation of responses

`ResponseMatchers.validPayload(schema)` validates response XML against an XSD. It does not automatically ensure:

- That incoming requests are XSD-validated by the server.
- That a WSDL is published at the right URL or matches the schema.
- That the endpoint declares the right SOAPAction.
- That authentication or WS-Security headers are enforced.
- That the service reads/writes a real database.

If schemas are the source of truth, build contract-first: keep XSD/WSDL in versioned resources, generate DTO/JAXB artifacts where appropriate, and test both endpoint responses and WSDL publication separately.

### Request validation

To enforce incoming request XSD validation:

1. Configure Spring-WS `PayloadValidatingInterceptor` or an inbound schema-validation strategy.
2. Supply invalid payloads (missing required element, wrong type, wrong namespace).
3. Assert the interceptor's fault/client-error policy and confirm **the business service is never invoked**.
4. For valid payloads, assert the service call and response.

Never assume `validPayload` on the **response** protects the server from invalid inbound XML.

### SOAP Fault details

When production requires SOAP Faults on invalid input, verify:

- SOAP 1.1 `Client` or SOAP 1.2 `Sender` matching the version.
- Stable `faultstring`/`Reason` containing no internal stack traces.
- `Detail` holding contract-specific error codes without secrets.
- That the interceptor or resolver is actually registered in the **test slice** or full context.
- Whether wrong SOAPAction/namespace produces the contracted fault type or an unmapped-endpoint error.

`ResponseMatchers.clientOrSenderFault("...")` can match reason text when contractual. Avoid asserting generic English reason strings if localization changes text by locale.

### WS-Security and headers

SOAP security spans multiple layers:

- HTTPS/TLS for transport, optionally with client certificates.
- SOAP Headers holding `UsernameToken`, `Timestamp`, `Signature`, or `Encryption` per WS-Security.
- `EndpointInterceptor` verifying security policy before business methods.
- Tenant/user authorization and anti-replay for signed requests.

`MockWebServiceClient` can test interceptors/header handling with mock messages, yet **does not replace** real TLS, certificate, HTTP, or gateway tests. In unit/slice tests, use proper request/header creators and keep real credentials out of fixtures and logs.

## 15. Troubleshooting: common errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Cannot import `@WebServiceServerTest` | Boot too old, missing test auto-config, or wrong Boot 3/4 package | Check parent/BOM, dependency tree, and version table |
| Cannot find `MockWebServiceClient` | Missing `spring-ws-test` on test classpath | For Boot 3.x add `spring-ws-test` in test scope |
| `NoSuchBeanDefinitionException` for service | Slice does not scan regular `@Service` beans | `@MockitoBean`/`@Import` the needed collaborator |
| `MockWebServiceClient` fails to autowire in full context | Annotated only with `@SpringBootTest` | Add `@AutoConfigureMockWebServiceClient` |
| SOAP request does not match endpoint | QName namespace/localPart differs from `@PayloadRoot` | Verify URI + local name; prefixes may vary |
| Passed `<soap:Envelope>` to `withPayload` | Confused envelope with payload | Pass only the inner XML payload to `withPayload` |
| XSD test fails despite right text | Schema `targetNamespace`/`elementFormDefault` mismatches XML | Align XSD/payload to the contract |
| `xpath` finds no element | XPath namespace mapping is empty or wrong | Supply `Map.of("g", NS)` for namespaces |
| SOAP Fault is not Client | Missing resolver/mapping or exception is a server fault | Check `SoapFault...Resolver` and SOAP version |
| Asserted `noFault` only while payload is wrong | Matcher too weak | Chain `payload`/`xpath` and `validPayload` |
| `@MockitoBean` fails to compile on Boot 3.3 | Older Spring Framework lacks the new annotation | Use the API supported by your version; do not mix test deps |
| Full context loads unneeded DB | Used `@SpringBootTest` for an endpoint slice | Switch to `@WebServiceServerTest` |
| Slice pulls too many auto-configs | Broad app config import or custom component scan | Keep endpoint-specific config; inspect bean graph |
| WSDL URL returns 404 while slice passes | Slice bypasses servlet/network layer | Add HTTP integration test with random port |
| Wrong SOAP version tested | SOAP 1.1/1.2 message factory and envelope differ | Check namespaces, Content-Type, and SOAPAction |
| SOAP Fault text leaks internal info | Resolver exposes exception message/raw stack | Map fault reason and detail safely |
| HTTP 200 test passes despite broken SOAP body | Asserted HTTP status only | Parse and assert SOAP Body/Fault |
| Vulnerable to XXE/XML entity abuse | XML parser/marshaller processes unsafe input | Use secure parser, disable external DTDs/entities, bound size/depth |
| Outbound SOAP test fails while endpoint test passes | Client vs. server direction mismatch | Use `@WebServiceClientTest` + `MockWebServiceServer` |
| GraphQL query fails to execute | Confused SOAP stack with GraphQL | Use `@GraphQlTest` and `GraphQlTester` |
| Tests stay green without running | Wrong Maven/JUnit filter or test naming | Check Surefire reports and executed test counts |
| Boot 4 "package does not exist" | Test modules reorganized | Use focused `webservices-test` starter + new imports |

### Ordered debugging workflow

1. Check actual Maven, JDK, and Spring Boot versions plus the dependency tree.
2. Confirm whether you need a **SOAP server test** or a **SOAP client test**.
3. Verify `@Endpoint` is scanned and collaborators are supplied.
4. Send the **payload root with the right namespace** via `withPayload`, never a nested envelope.
5. Combine `noFault` with `payload` or `xpath` to verify business data.
6. When XSD matters, test `validPayload` with the right schema resource.
7. When testing SOAP Faults, confirm the resolver/interceptor is loaded before asserting fault type.
8. If failures happen only over an HTTP socket, isolate servlet path, TLS, auth, or proxy config from slice logic.
9. On version mismatches, fix imports/starters per the version table instead of disabling SOAP tests.
10. Inspect `target/surefire-reports` to verify every test method actually ran.

## 16. Fallback without @WebServiceServerTest

In legacy projects or custom Spring-WS setups incompatible with the slice, you can create the client manually:

```java
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.ws.test.server.MockWebServiceClient;

class ManualSoapTest {

    @Autowired
    ApplicationContext applicationContext;

    private MockWebServiceClient client;

    @BeforeEach
    void setUp() {
        client = MockWebServiceClient.createClient(
                applicationContext);
    }
}
```

This is an **excerpt**, lacking test bootstrap and context configuration. To run it, add `@ContextConfiguration`/`@SpringJUnitConfig` or `@SpringBootTest` with real Spring-WS endpoint mappings, adapters, and message factory in the context.

`createClient(ApplicationContext)` is a Spring-WS API independent of Boot's `@WebServiceServerTest`. It does not auto-scan endpoints or register SOAP adapters by itself. If the context is incomplete, you may see errors about missing dispatchers or endpoint mappings.

`MockWebServiceClient.createClient(WebServiceMessageReceiver, WebServiceMessageFactory)` provides direct control over receiver and factory; that is an advanced option not needed for an introductory test.

## 17. Acceptance checklist

- [ ] Confirmed the application is a **SOAP server**, not an outbound SOAP client?
- [ ] Selected `@WebServiceServerTest` rather than `@WebMvcTest` or `@GraphQlTest`?
- [ ] Do Spring Boot major version and annotation imports match the Boot 3.x/4.x table?
- [ ] Does the test classpath include matching Spring-WS test support, JUnit, and Mockito versions?
- [ ] Do `@Endpoint`, `@PayloadRoot`, `@RequestPayload`, and `@ResponsePayload` match the XML contract?
- [ ] Do tests select endpoints by **namespace URI + local name** without hardcoding prefixes?
- [ ] Do requests pass the XML payload to `RequestCreators.withPayload`, not a full envelope?
- [ ] Does the test inject `MockWebServiceClient` or construct it properly per lifecycle?
- [ ] Are constructor collaborators supplied via `@MockitoBean` or `@Import`?
- [ ] Are happy paths, escaped XML characters, and alternate namespace prefixes covered?
- [ ] Do assertions check `noFault` **and** payload or XPath content?
- [ ] Are response XSDs validated when required by contract?
- [ ] Have I avoided assuming response XSD validation enables **inbound request validation**?
- [ ] Are SOAP Fault mappings/interceptors verified before asserting Client/Sender?
- [ ] Have I kept `MockWebServiceClient` distinct from `MockWebServiceServer`?
- [ ] Do I know when to move to `@SpringBootTest + @AutoConfigureMockWebServiceClient`?
- [ ] Am I clear on what the slice skips: WSDL URLs, HTTP/TLS, SOAPAction, gateways, and real DBs?
- [ ] Are SOAP 1.1/1.2 and SOAP header security covered if required by the system?
- [ ] Are XML parsers protected against XXE/DTDs for untrusted input?
- [ ] Do build/JUnit reports confirm all tests executed with zero hidden skips?
- [ ] When upgrading Boot, do I check test starters and packages before editing test logic?

## 18. Official documentation

1. [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): **Auto-configured Spring Web Services Server Tests** covering Boot 3.x `@WebServiceServerTest` and `MockWebServiceClient` imports.
2. [Spring Boot Reference — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): SOAP client/server testing and updated Boot 4.x imports.
3. [Spring Boot 4 — @WebServiceServerTest API](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/webservices/test/autoconfigure/server/WebServiceServerTest.html): `@Endpoint` scope, collaborators, and full-context options.
4. [Spring Boot 4 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): module, test starter, and package changes.
5. [Spring-WS — MockWebServiceClient API](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/test/server/MockWebServiceClient.html): creating the client and calling `sendRequest`/`andExpect`.
6. [Spring-WS — ResponseMatchers API](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/test/server/ResponseMatchers.html): `payload`, `xpath`, `validPayload`, `noFault`, and fault matchers.
7. [Spring-WS — Reference Documentation](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/): `@Endpoint`, QName mapping, SOAP message factories, and server-side testing.
8. [Spring-WS Project](https://spring.io/projects/spring-ws/): contract-first SOAP services, XML stack, and testing.
9. [XML Schema Primer — W3C](https://www.w3.org/TR/xmlschema-0/): element namespaces, XSD structure, and qualified elements.
10. [Spring Boot Dependency Management](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html): Boot 3.5 managed versions for Spring-WS and Spring Framework.

**Remember:** `@WebServiceServerTest` tests a **SOAP server slice**, and `MockWebServiceClient` dispatches SOAP payloads **inside the Spring context**, not as a real HTTP client. Across Boot 3.5 and Boot 4, **annotation packages and starter names differ**; lock down your version, use the matching imports, and verify outcomes via **namespace + payload/XPath + XSD/Fault expectations** per contract. When real HTTP, WSDL, TLS, or databases are required, add a separate integration tier instead of claiming evidence the slice does not provide.