# Checking XML Payloads, SOAP Faults, and Error Mapping

Within the **GraphQL and SOAP** group of Spring Boot testing, testing SOAP means more than checking that a Java method returns a value. The contract also lives in the **XML payload, namespaces, SOAP Envelope/Body/Header, XSD/WSDL, SOAP Fault messages, and safe translation of external failures into application errors**. An application can return HTTP 500 while delivering a valid SOAP Fault; conversely, an HTTP error without a SOAP Envelope is **not** a valid SOAP Fault.

The goal of this lesson is to write tests covering both sides:

- **Client/Gateway calling external SOAP:** send the right XML request, parse the XML response, handle SOAP Faults, and map them to application errors; isolate networking with `MockWebServiceServer`.
- **Application's SOAP endpoint:** handle request payloads with the right namespaces and return responses/faults per contract; use `MockWebServiceClient` with an appropriate context when testing annotations, endpoint adapters, and resolvers.
- **Plain Java/XML level:** parse XML safely and inspect fault structure/`detail` without booting a Spring context.

The article provides complete **Java 17+, Spring Boot 3.4/3.5, Spring Web Services (Spring-WS 4.x), and JUnit Jupiter** examples, including real client tests against a mock server, a plain Java SE demo runnable via `javac/java`, and edge cases covering SOAP 1.1/1.2, fault mapping, XXE, and sensitive data.

## 1. Identifying the exact SOAP boundaries

A SOAP message typically contains an Envelope, optional Header, and Body. Example SOAP 1.1 request:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
            xmlns:o="urn:example:orders">
  <s:Header/>
  <s:Body>
    <o:GetOrderRequest>
      <o:orderId>ORD-7</o:orderId>
    </o:GetOrderRequest>
  </s:Body>
</s:Envelope>
```

The business payload in the Body is **`o:GetOrderRequest`**, while Envelope is the SOAP wrapper. When calling `WebServiceTemplate.sendSourceAndReceiveToResult(...)`, pass the **payload `Source`**; Spring-WS wraps it inside the SOAP Body. Never nest a second Envelope inside the payload.

A successful SOAP 1.1 response:

```xml
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
            xmlns:o="urn:example:orders">
  <s:Body>
    <o:GetOrderResponse>
      <o:orderId>ORD-7</o:orderId>
      <o:status>PAID</o:status>
    </o:GetOrderResponse>
  </s:Body>
</s:Envelope>
```

A SOAP 1.1 Fault:

```xml
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
            xmlns:o="urn:example:orders">
  <s:Body>
    <s:Fault>
      <faultcode>s:Client</faultcode>
      <faultstring>Invalid order</faultstring>
      <detail>
        <o:OrderError>
          <o:code>ORDER_NOT_FOUND</o:code>
        </o:OrderError>
      </detail>
    </s:Fault>
  </s:Body>
</s:Envelope>
```

In SOAP 1.1, `faultcode` and `faultstring` sit directly under `Fault`; `detail` carries application-specific error data when defined by the contract. The value `s:Client` **is a QName**, not merely a string with a colon. When parsing, resolve prefix `s` to the SOAP Envelope namespace.

### SOAP 1.1 and SOAP 1.2 are not the same

| Property | SOAP 1.1 | SOAP 1.2 |
| --- | --- | --- |
| Envelope namespace | `http://schemas.xmlsoap.org/soap/envelope/` | `http://www.w3.org/2003/05/soap-envelope` |
| Sender-side input error | `Client` | `Sender` |
| Receiver-side processing error | `Server` | `Receiver` |
| Fault code element | `faultcode` | `Code/Value`, optionally `Subcode` |
| Human-readable message | `faultstring` | `Reason/Text` |
| Application error details | `detail` | `Detail` |
| Common MIME type | `text/xml` | `application/soap+xml` |

Never apply a SOAP 1.1 XPath to SOAP 1.2 and conclude "no fault was returned." SOAP 1.2 example:

```xml
<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope">
  <env:Body>
    <env:Fault>
      <env:Code>
        <env:Value>env:Sender</env:Value>
      </env:Code>
      <env:Reason>
        <env:Text xml:lang="en">Invalid request</env:Text>
      </env:Reason>
    </env:Fault>
  </env:Body>
</env:Envelope>
```

Spring-WS provides `SoapVersion.SOAP_11` and `SoapVersion.SOAP_12` abstractions for comparing fault QNames. With custom parsers, **pick the version and write version-specific tests** rather than mechanically swapping `faultcode` for `Code`.

## 2. Inspecting XML by namespace, not fixed prefixes

These two payloads are **equivalent in element names** when the contract relies on namespace URIs and local names:

```xml
<ord:GetOrderResponse xmlns:ord="urn:example:orders">
  <ord:orderId>ORD-7</ord:orderId>
  <ord:status>PAID</ord:status>
</ord:GetOrderResponse>
```

```xml
<x:GetOrderResponse xmlns:x="urn:example:orders">
  <x:orderId>ORD-7</x:orderId>
  <x:status>PAID</x:status>
</x:GetOrderResponse>
```

Prefixes `ord` and `x` are merely aliases; the **expanded name** of the root element is `{urn:example:orders}GetOrderResponse`. Byte-for-byte XML comparisons break easily when prefixes, namespace declarations, whitespace, or attribute ordering change even though XML semantics remain valid.

Conversely:

```xml
<x:GetOrderResponse xmlns:x="urn:wrong:orders">
  <x:orderId>ORD-7</x:orderId>
  <x:status>PAID</x:status>
</x:GetOrderResponse>
```

**violates the contract** because the namespace URI is wrong. Tests must fail.

**What to verify:**

- Root payload has the exact QName (namespace URI + local name).
- Required elements appear the expected number of times with valid types/values.
- Sensitive elements do not appear outside the schema.
- Response `orderId`/`status` match the request.
- XML validates against the XSD when contractual; application logic handles edge values.
- For full SOAP envelopes: Body holds the exact payload or Fault, and Headers are checked separately when WS-Addressing or WS-Security applies.

In Java/JAXP, enable `DocumentBuilderFactory.setNamespaceAware(true)`. With XPath, register a `NamespaceContext` instead of depending on prefixes in the document:

```java
XPath xpath = XPathFactory.newInstance().newXPath();
xpath.setNamespaceContext(
        new org.springframework.xml.namespace.SimpleNamespaceContext(
                java.util.Map.of("ord", "urn:example:orders")));
String value = xpath.evaluate(
        "/ord:GetOrderResponse/ord:status", document);
```

This is an illustrative snippet inside a Spring-WS project with proper imports and a parsed `document`. The `ord` prefix in the expression is bound by the **test** and need not match the prefix in the raw XML. The standalone Java SE code in section 5 uses DOM APIs and `getNamespaceURI()/getLocalName()` to avoid Spring dependencies.

## 3. SOAP Faults, transport failures, and business errors are three distinct layers

A SOAP integration generally encounters at least three failure categories:

1. **Transport failure:** DNS, TLS, connection timeout, proxy failure, or an HTTP response lacking a valid SOAP message. A SOAP Fault may not exist at all.
2. **Protocol/SOAP Fault:** the server returns a SOAP Envelope containing a `Fault` with code `Client/Server` or `Sender/Receiver`. This error is represented **inside SOAP**, and cannot be inferred from HTTP status alone.
3. **Business error detail:** a SOAP Fault may carry `detail` with `ORDER_NOT_FOUND`, `VALIDATION_FAILED`, or an application-defined schema code. This is a **WSDL/XSD-specific** business layer outside SOAP's standard fault codes.

Illustrative mapping table **for a gateway policy**:

| External input | Suggested internal code | Retry? | Notes |
| --- | --- | --- | --- |
| SOAP 1.1 `Client` / SOAP 1.2 `Sender`, no special detail | `INVALID_SOAP_REQUEST` | Usually no | Bad request/contract; do not infer HTTP 400 solely from SOAP faultcode |
| Client/Sender with verified `detail.code=ORDER_NOT_FOUND` | `ORDER_NOT_FOUND` | No | Mapping driven by business contract |
| SOAP 1.1 `Server` / SOAP 1.2 `Receiver` | `UPSTREAM_FAILURE` | Conditional | Retry only when operation/idempotency policy allows |
| `VersionMismatch`, `MustUnderstand` | `SOAP_PROTOCOL_FAILURE` | Usually no | Fix version, headers, or client config |
| Unparseable XML response / wrong namespace | `SOAP_PROTOCOL_FAILURE` | Usually no | Fail closed; never treat as a valid order |
| Network timeout / TLS / 503 without SOAP envelope | `SOAP_TRANSPORT_FAILURE` | Conditional | Verify transport, timeouts, and retries separately |
| Application detects invalid internal data | `INTERNAL_FAILURE` | Per policy | Never echo exceptions/stack traces into SOAP faultstring |

**Do not mechanically map `Client → 400` or `Server → 500` for every system.** In SOAP 1.1, HTTP 500 commonly accompanies any SOAP Fault, including a `Client` fault. When SOAP sits behind a REST gateway, **HTTP 400/404/502/503** reflects the gateway's own API policy, not a universal SOAP standard rule.

Also never use the `faultstring` prose as a business error identifier: it is human-readable, may be localized, can change wording, or may expose internal details. To identify `ORDER_NOT_FOUND`, rely on structured codes inside `detail` or an explicit contract.

## 4. Choosing test layers to avoid false greens

| Goal | Appropriate tool | What is verified |
| --- | --- | --- |
| XML parser, namespaces, fault detail, XXE | JUnit + JAXP/DOM | Real XML structure and pure Java mapping |
| SOAP client sending requests/handling responses/faults | `MockWebServiceServer` + `WebServiceTemplate` | Client XML payload and fault handling, **no network calls** |
| Spring-WS endpoint mapping, response, and fault resolver | `MockWebServiceClient` + context | `@Endpoint`/`@PayloadRoot`/resolver per test config |
| XSD/WSDL contract | XML schema validator + Spring-WS test matchers | Compliance with contractual types and schemas |
| Real HTTP Content-Type/SOAPAction/TLS/proxy/server | Integration/E2E HTTP test | Transport and deployment config in the active environment |
| REST facade calling SOAP and returning error responses | Matching MVC/WebFlux test | Mapping SOAP domain errors into the facade's HTTP/JSON API |

**Do not use `MockMvc` as if it tested native Spring-WS SOAP endpoints.** `MockMvc` targets Spring MVC controllers, whereas Spring-WS SOAP endpoints run through `MessageDispatcher` and `MessageDispatcherServlet`. For SOAP endpoints, `MockWebServiceClient` is the right tool.

Conversely, `MockWebServiceServer` is a **server-side mock for testing SOAP clients**, not an embedded SOAP service listening on a TCP port. The word "Server" describes the role simulated for the client test; no real networking takes place.

## 5. Plain Java 17 demo: inspecting XML payloads and SOAP Faults safely

Before starting a Spring context, let us build a standalone Java SE parser. It **intentionally supports SOAP 1.1** for fault fixtures; SOAP 1.2 needs a separate parsing branch due to different namespaces and elements.

### 5.1. File structure

```text
src/
├── main/java/example/testing/soap/
│   ├── OrderXml.java
│   ├── SoapContractDemo.java
│   └── OrderSoapClient.java
└── test/java/example/testing/soap/
    ├── OrderXmlTest.java
    └── OrderSoapClientTest.java
```

`OrderXml.java` and `SoapContractDemo.java` depend only on Java SE and compile/run with `javac/java` on JDK 17+ to verify XML structure and mapping policy. `OrderSoapClient.java` and its tests require Spring Web Services dependencies via Gradle.

### 5.2. Safe parser: OrderXml.java

Create `src/main/java/example/testing/soap/OrderXml.java`:

```java
package example.testing.soap;

import java.io.StringReader;
import java.util.Objects;

import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;

import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.xml.sax.InputSource;

public final class OrderXml {
    public static final String ORDERS_NS = "urn:example:orders";
    public static final String SOAP11_NS =
            "http://schemas.xmlsoap.org/soap/envelope/";

    private OrderXml() {
    }

    public record OrderStatus(String orderId, String status) {
    }

    public record FaultView(
            String faultCode, String detailCode, String reason) {
    }

    public enum ErrorKind {
        NOT_FOUND,
        INVALID_REQUEST,
        UPSTREAM_FAILURE,
        PROTOCOL_FAILURE
    }

    public static Document parseSecure(String xml) {
        Objects.requireNonNull(xml, "xml");
        if (xml.length() > 100_000) {
            throw new IllegalArgumentException("XML too large");
        }

        try {
            DocumentBuilderFactory factory =
                    DocumentBuilderFactory.newInstance();
            factory.setNamespaceAware(true);
            factory.setFeature(
                    XMLConstants.FEATURE_SECURE_PROCESSING, true);
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
            factory.setXIncludeAware(false);
            factory.setExpandEntityReferences(false);
            factory.setAttribute(
                    XMLConstants.ACCESS_EXTERNAL_DTD, "");
            factory.setAttribute(
                    XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

            return factory.newDocumentBuilder().parse(
                    new InputSource(new StringReader(xml)));
        } catch (Exception error) {
            throw new IllegalArgumentException(
                    "Invalid or unsafe XML", error);
        }
    }

    private static Element directChild(
            Element parent, String ns, String localName) {
        Element found = null;
        for (Node node = parent.getFirstChild();
                node != null; node = node.getNextSibling()) {
            if (node instanceof Element element
                    && Objects.equals(ns, element.getNamespaceURI())
                    && localName.equals(element.getLocalName())) {
                if (found != null) {
                    throw new IllegalArgumentException(
                            "Duplicate element: " + localName);
                }
                found = element;
            }
        }
        return found;
    }

    private static Element requiredChild(
            Element parent, String ns, String localName) {
        Element found = directChild(parent, ns, localName);
        if (found == null) {
            throw new IllegalArgumentException(
                    "Missing element: " + localName);
        }
        return found;
    }

    private static String text(Element element) {
        return element.getTextContent().trim();
    }

    public static OrderStatus readPayload(String xml) {
        Element root = parseSecure(xml).getDocumentElement();
        if (!ORDERS_NS.equals(root.getNamespaceURI())
                || !"GetOrderResponse".equals(root.getLocalName())) {
            throw new IllegalArgumentException(
                    "Unexpected response QName");
        }

        String id = text(requiredChild(root, ORDERS_NS, "orderId"));
        String status = text(
                requiredChild(root, ORDERS_NS, "status"));

        if (!id.matches("ORD-[0-9]{1,6}")
                || !(status.equals("PAID")
                     || status.equals("PENDING"))) {
            throw new IllegalArgumentException(
                    "Invalid order response fields");
        }

        return new OrderStatus(id, status);
    }

    public static FaultView readSoap11Fault(String envelopeXml) {
        Element envelope = parseSecure(envelopeXml)
                .getDocumentElement();
        if (!SOAP11_NS.equals(envelope.getNamespaceURI())
                || !"Envelope".equals(envelope.getLocalName())) {
            throw new IllegalArgumentException(
                    "Not a SOAP 1.1 Envelope");
        }

        Element body = requiredChild(
                envelope, SOAP11_NS, "Body");
        Element fault = requiredChild(
                body, SOAP11_NS, "Fault");
        Element faultCode = requiredChild(
                fault, null, "faultcode");

        String lexicalCode = text(faultCode);
        int separator = lexicalCode.indexOf(':');
        if (separator <= 0 || separator == lexicalCode.length() - 1) {
            throw new IllegalArgumentException(
                    "Fault code needs a bound prefix");
        }

        String prefix = lexicalCode.substring(0, separator);
        String localCode = lexicalCode.substring(separator + 1);
        String namespace = faultCode.lookupNamespaceURI(prefix);

        if (!SOAP11_NS.equals(namespace)) {
            throw new IllegalArgumentException(
                    "Fault code namespace mismatch");
        }

        String reason = text(requiredChild(
                fault, null, "faultstring"));

        String detailCode = "";
        Element detail = directChild(fault, null, "detail");
        if (detail != null) {
            Element orderError = directChild(
                    detail, ORDERS_NS, "OrderError");
            if (orderError != null) {
                detailCode = text(requiredChild(
                        orderError, ORDERS_NS, "code"));
            }
        }

        return new FaultView(localCode, detailCode, reason);
    }

    public static ErrorKind classify(FaultView fault) {
        return switch (fault.faultCode()) {
            case "Client" ->
                    "ORDER_NOT_FOUND".equals(fault.detailCode())
                            ? ErrorKind.NOT_FOUND
                            : ErrorKind.INVALID_REQUEST;
            case "Server" -> ErrorKind.UPSTREAM_FAILURE;
            default -> ErrorKind.PROTOCOL_FAILURE;
        };
    }
}
```

**Testable design choices in the parser:**

- `setNamespaceAware(true)` makes DOM evaluate namespace URI and local name instead of prefix strings.
- `disallow-doctype-decl` blocks DOCTYPE declarations, mitigating **XXE/SSRF/file disclosure**. Flags disabling external entities/DTDs and `ACCESS_EXTERNAL_DTD/SCHEMA` add defense-in-depth. If a provider lacks support for security settings, the code **fails closed** with an exception rather than silently enabling unsafe parsing.
- `directChild(...)` inspects **immediate children only**, avoiding `getElementsByTagNameNS(...)` over all descendants which could pick up a same-named element at another depth.
- If **two required elements share the same name** under one parent, the parser rejects it instead of silently picking the first one.
- `FaultView` retains the fault code, business `detail` code, and reason for inspection. `classify(...)` relies exclusively on **structured codes**, never classifying by English prose inside reason.
- This parser limits `readSoap11Fault` to SOAP **1.1**. SOAP 1.2 requires parsing `env:Code/env:Value`, `env:Reason/env:Text`, and `env:Detail` separately or using Spring-WS abstractions.

**Important limitations:** this is a minimal illustrative parser and does not replace **XSD/WSDL validation** or full production schema/size/depth constraints. When parsing untrusted partner XML, enforce request size bounds, nesting/node depth limits, parse timeouts, and transport policies. Never log raw payloads containing tokens, addresses, or PII.

### 5.3. Java SE demo: SoapContractDemo.java

Create `src/main/java/example/testing/soap/SoapContractDemo.java`:

```java
package example.testing.soap;

public class SoapContractDemo {
    public static void main(String[] args) {
        String payload = """
                <o:GetOrderResponse xmlns:o="urn:example:orders">
                  <o:orderId>ORD-7</o:orderId>
                  <o:status>PAID</o:status>
                </o:GetOrderResponse>
                """;

        String clientFault = """
                <s:Envelope
                  xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:o="urn:example:orders">
                  <s:Body>
                    <s:Fault>
                      <faultcode>s:Client</faultcode>
                      <faultstring>Invalid order</faultstring>
                      <detail>
                        <o:OrderError>
                          <o:code>ORDER_NOT_FOUND</o:code>
                        </o:OrderError>
                      </detail>
                    </s:Fault>
                  </s:Body>
                </s:Envelope>
                """;

        String serverFault = """
                <s:Envelope
                  xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
                  <s:Body>
                    <s:Fault>
                      <faultcode>s:Server</faultcode>
                      <faultstring>Temporary failure</faultstring>
                    </s:Fault>
                  </s:Body>
                </s:Envelope>
                """;

        OrderXml.OrderStatus order =
                OrderXml.readPayload(payload);
        OrderXml.FaultView fault =
                OrderXml.readSoap11Fault(clientFault);

        System.out.println(
                order.orderId() + " | " + order.status());
        System.out.println(
                fault.faultCode() + " | " + fault.detailCode());
        System.out.println(OrderXml.classify(fault));
        System.out.println(OrderXml.classify(
                OrderXml.readSoap11Fault(serverFault)));
    }
}
```

Compile and run with **JDK 17+** from the project root:

```bash
javac -d out src/main/java/example/testing/soap/OrderXml.java src/main/java/example/testing/soap/SoapContractDemo.java
java -cp out example.testing.soap.SoapContractDemo
```

Exact stdout:

```text
ORD-7 | PAID
Client | ORDER_NOT_FOUND
NOT_FOUND
UPSTREAM_FAILURE
```

This is a **complete Java SE demo** without Spring. It exercises the parser, SOAP 1.1 Fault QNames, and the illustrative business error mapping table. It **does not prove** a real SOAP HTTP request was sent or a Spring-WS endpoint was registered—that belongs to the Spring-WS tests and integration tests.

## 6. XML unit tests: valid payloads, namespaces, and XXE

Create `src/test/java/example/testing/soap/OrderXmlTest.java`:

```java
package example.testing.soap;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class OrderXmlTest {

    @Test
    void acceptsDifferentPrefixWithSameNamespace() {
        String payload = """
                <x:GetOrderResponse xmlns:x="urn:example:orders">
                  <x:orderId>ORD-7</x:orderId>
                  <x:status>PAID</x:status>
                </x:GetOrderResponse>
                """;

        assertEquals(
                new OrderXml.OrderStatus("ORD-7", "PAID"),
                OrderXml.readPayload(payload));
    }

    @Test
    void rejectsWrongNamespace() {
        String payload = """
                <x:GetOrderResponse xmlns:x="urn:wrong:orders">
                  <x:orderId>ORD-7</x:orderId>
                  <x:status>PAID</x:status>
                </x:GetOrderResponse>
                """;

        assertThrows(IllegalArgumentException.class,
                () -> OrderXml.readPayload(payload));
    }

    @Test
    void rejectsDuplicateRequiredElement() {
        String payload = """
                <o:GetOrderResponse xmlns:o="urn:example:orders">
                  <o:orderId>ORD-7</o:orderId>
                  <o:orderId>ORD-8</o:orderId>
                  <o:status>PAID</o:status>
                </o:GetOrderResponse>
                """;

        assertThrows(IllegalArgumentException.class,
                () -> OrderXml.readPayload(payload));
    }

    @Test
    void rejectsDoctypeBeforeEntityExpansion() {
        String payload = """
                <!DOCTYPE data [
                  <!ENTITY example SYSTEM "file:///no-such-file">
                ]>
                <o:GetOrderResponse xmlns:o="urn:example:orders">
                  <o:orderId>&example;</o:orderId>
                  <o:status>PAID</o:status>
                </o:GetOrderResponse>
                """;

        assertThrows(IllegalArgumentException.class,
                () -> OrderXml.readPayload(payload));
    }

    @Test
    void mapsBusinessCodeFromSoap11Detail() {
        String xml = """
                <s:Envelope
                  xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:o="urn:example:orders">
                  <s:Body>
                    <s:Fault>
                      <faultcode>s:Client</faultcode>
                      <faultstring>Readable reason</faultstring>
                      <detail>
                        <o:OrderError>
                          <o:code>ORDER_NOT_FOUND</o:code>
                        </o:OrderError>
                      </detail>
                    </s:Fault>
                  </s:Body>
                </s:Envelope>
                """;

        OrderXml.FaultView fault =
                OrderXml.readSoap11Fault(xml);

        assertEquals("Client", fault.faultCode());
        assertEquals("ORDER_NOT_FOUND", fault.detailCode());
        assertEquals(
                OrderXml.ErrorKind.NOT_FOUND,
                OrderXml.classify(fault));
    }
}
```

**These five test methods** verify:

1. XML with the same namespace and a different prefix is accepted.
2. Wrong namespace is rejected.
3. Duplicate `orderId` elements are rejected (preventing data ambiguity).
4. DOCTYPE/external entities are blocked, demonstrating XXE mitigation.
5. SOAP 1.1 Fault with `detail.code=ORDER_NOT_FOUND` maps to `NOT_FOUND`.

A test checking only `assertTrue(xml.contains("PAID"))` misses wrong namespaces or misplaced nested elements. Safe DOM parsing and QName/cardinality checks ensure assertions truly guard **message structure**.

## 7. Spring-WS client: building payloads, reading results, and mapping SOAP Faults

### 7.1. Decoupling business errors from raw faults

To keep controllers decoupled from SOAP infrastructure, the client translates `SoapFaultClientException` into an integration-layer exception:

| `GatewayError` | Meaning | Default `retryable` |
| --- | --- | --- |
| `INVALID_REQUEST` | Upstream returned Sender/Client fault | `false` |
| `UPSTREAM_UNAVAILABLE` | Upstream returned Receiver/Server fault or I/O failure | `true` **is only a signal**; still requires an idempotency policy |
| `SOAP_PROTOCOL_ERROR` | Unrecognized fault code, invalid XML QName/schema | `false` |
| `EMPTY_RESPONSE` | Request completed without a contractual payload | `false` |

**Note:** the Spring-WS client below maps by **standard SOAP fault QNames**. It does not read the `ORDER_NOT_FOUND` business detail automatically; if a partner requires 404 classification from `detail`, extend the gateway to parse `SoapFault.getFaultDetail()` per the agreed schema and test it explicitly. Never guess `NOT_FOUND` because the reason string contains `"not found"`.

### 7.2. Spring-WS file: OrderSoapClient.java

Create `src/main/java/example/testing/soap/OrderSoapClient.java`:

```java
package example.testing.soap;

import java.io.StringWriter;
import java.util.Objects;

import javax.xml.namespace.QName;
import javax.xml.transform.stream.StreamResult;

import org.springframework.ws.client.WebServiceIOException;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.soap.SoapVersion;
import org.springframework.ws.soap.client.SoapFaultClientException;
import org.springframework.xml.transform.StringSource;

public final class OrderSoapClient {
    private final WebServiceTemplate template;

    public OrderSoapClient(WebServiceTemplate template) {
        this.template = Objects.requireNonNull(
                template, "template");
    }

    public OrderXml.OrderStatus fetch(String orderId) {
        if (orderId == null
                || !orderId.matches("ORD-[0-9]{1,6}")) {
            throw new IllegalArgumentException(
                    "Invalid orderId");
        }

        String requestXml = """
                <o:GetOrderRequest xmlns:o="urn:example:orders">
                  <o:orderId>%s</o:orderId>
                </o:GetOrderRequest>
                """.formatted(orderId);

        StringWriter responseWriter = new StringWriter();

        try {
            boolean received =
                    template.sendSourceAndReceiveToResult(
                            new StringSource(requestXml),
                            new StreamResult(responseWriter));

            if (!received) {
                throw new GatewayException(
                        GatewayError.EMPTY_RESPONSE, false);
            }

            OrderXml.OrderStatus result =
                    OrderXml.readPayload(
                            responseWriter.toString());

            if (!orderId.equals(result.orderId())) {
                throw new GatewayException(
                        GatewayError.SOAP_PROTOCOL_ERROR, false);
            }

            return result;
        } catch (SoapFaultClientException fault) {
            throw mapFault(fault);
        } catch (WebServiceIOException transport) {
            throw new GatewayException(
                    GatewayError.UPSTREAM_UNAVAILABLE, true);
        } catch (IllegalArgumentException badPayload) {
            throw new GatewayException(
                    GatewayError.SOAP_PROTOCOL_ERROR, false);
        }
    }

    private static GatewayException mapFault(
            SoapFaultClientException fault) {
        QName code = fault.getFaultCode();

        if (SoapVersion.SOAP_11
                    .getClientOrSenderFaultName().equals(code)
                || SoapVersion.SOAP_12
                    .getClientOrSenderFaultName().equals(code)) {
            return new GatewayException(
                    GatewayError.INVALID_REQUEST, false);
        }

        if (SoapVersion.SOAP_11
                    .getServerOrReceiverFaultName().equals(code)
                || SoapVersion.SOAP_12
                    .getServerOrReceiverFaultName().equals(code)) {
            return new GatewayException(
                    GatewayError.UPSTREAM_UNAVAILABLE, true);
        }

        return new GatewayException(
                GatewayError.SOAP_PROTOCOL_ERROR, false);
    }
}

enum GatewayError {
    INVALID_REQUEST,
    UPSTREAM_UNAVAILABLE,
    SOAP_PROTOCOL_ERROR,
    EMPTY_RESPONSE
}

final class GatewayException extends RuntimeException {
    private final GatewayError code;
    private final boolean retryable;

    GatewayException(GatewayError code, boolean retryable) {
        super(code.name());
        this.code = code;
        this.retryable = retryable;
    }

    public GatewayError code() {
        return code;
    }

    public boolean retryable() {
        return retryable;
    }
}
```

Runnability notes:

- The file defines one top-level `public` class `OrderSoapClient`; `GatewayError` and `GatewayException` are package-private so JUnit tests in the same package can access them.
- The client accepts `WebServiceTemplate` via constructor, making it easy to test with `MockWebServiceServer` without an `ApplicationContext`.
- `orderId.matches(...)` **allowlists characters** before inserting the ID into the XML text block. This prevents XML injection in the demo; production apps with richer data should use JAXB or a safe DOM/StAX XML writer instead of string formatting.
- `sendSourceAndReceiveToResult(...)` sends the **XML payload** and writes the response payload into `StreamResult`; Spring-WS manages the SOAP Envelope and Faults.
- `OrderXml.readPayload(...)` verifies root QName, fields, and namespaces; the client also checks that the response `orderId` matches the request.
- `SoapFaultClientException.getFaultCode()` returns a `QName`; compare using `SoapVersion`, **never compare only the local part** or inspect `faultstring`.
- Outbound errors expose controlled codes; **never copy raw `fault.getFaultStringOrReason()`** into messages returned to REST/UI or unredacted logs.
- `GatewayError.UPSTREAM_UNAVAILABLE` sets `retryable=true` in the example, yet actual retries **are only safe** when the operation is read-only/idempotent or uses an idempotency key with deduplication.

This client defaults to **Spring-WS SOAP 1.1** in the tests below. For production SOAP 1.2, configure a matching `SoapMessageFactory` and test Content-Type and Faults explicitly rather than assuming both versions share one Envelope.

### 7.3. Gradle configuration for Spring Boot 3.4/3.5

In a project already configured with the Spring Boot Gradle plugin, repositories, Java toolchain, and dependency management, the relevant block in `build.gradle` (Groovy DSL) is:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web-services'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.ws:spring-ws-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is an **additional dependency snippet** for a complete Spring Boot project, not a standalone build file. `spring-boot-starter-web-services` provides Spring-WS integration and compatible SAAJ dependencies in Boot 3.4/3.5. `spring-ws-test` provides `MockWebServiceServer`/`MockWebServiceClient`. The examples do not require JAXB classes generated from XSD because they use `Source/Result`; real projects often use JAXB and WSDL code generation for type-safe contracts.

In Spring Boot 4.x, starter/test auto-configuration modules and packages may differ; check the exact Boot BOM and version docs instead of blindly copying older dependency coordinates.

## 8. Client-side test suite: MockWebServiceServer

Create `src/test/java/example/testing/soap/OrderSoapClientTest.java`:

```java
package example.testing.soap;

import java.util.Locale;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.test.client.MockWebServiceServer;
import org.springframework.xml.transform.StringSource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.ws.test.client.RequestMatchers.payload;
import static org.springframework.ws.test.client.ResponseCreators.withPayload;
import static org.springframework.ws.test.client.ResponseCreators.withClientOrSenderFault;
import static org.springframework.ws.test.client.ResponseCreators.withServerOrReceiverFault;

class OrderSoapClientTest {
    private static final String REQUEST = """
            <o:GetOrderRequest xmlns:o="urn:example:orders">
              <o:orderId>ORD-7</o:orderId>
            </o:GetOrderRequest>
            """;

    private static final String RESPONSE = """
            <o:GetOrderResponse xmlns:o="urn:example:orders">
              <o:orderId>ORD-7</o:orderId>
              <o:status>PAID</o:status>
            </o:GetOrderResponse>
            """;

    private MockWebServiceServer server;
    private OrderSoapClient client;

    @BeforeEach
    void setUp() {
        WebServiceTemplate template = new WebServiceTemplate();
        template.setDefaultUri(
                "https://soap.example.invalid/orders");
        server = MockWebServiceServer.createServer(template);
        client = new OrderSoapClient(template);
    }

    @Test
    void matchesRequestAndParsesSuccessPayload() {
        server.expect(payload(new StringSource(REQUEST)))
                .andRespond(withPayload(
                        new StringSource(RESPONSE)));

        OrderXml.OrderStatus result =
                client.fetch("ORD-7");

        assertEquals("ORD-7", result.orderId());
        assertEquals("PAID", result.status());
        server.verify();
    }

    @Test
    void clientFaultMapsToNonRetryableInvalidRequest() {
        server.expect(payload(new StringSource(REQUEST)))
                .andRespond(withClientOrSenderFault(
                        "Invalid SOAP request",
                        Locale.ENGLISH));

        GatewayException error = assertThrows(
                GatewayException.class,
                () -> client.fetch("ORD-7"));

        assertEquals(GatewayError.INVALID_REQUEST,
                error.code());
        assertFalse(error.retryable());
        server.verify();
    }

    @Test
    void serverFaultMapsToUpstreamUnavailable() {
        server.expect(payload(new StringSource(REQUEST)))
                .andRespond(withServerOrReceiverFault(
                        "Temporary SOAP failure",
                        Locale.ENGLISH));

        GatewayException error = assertThrows(
                GatewayException.class,
                () -> client.fetch("ORD-7"));

        assertEquals(GatewayError.UPSTREAM_UNAVAILABLE,
                error.code());
        assertTrue(error.retryable());
        server.verify();
    }

    @Test
    void malformedResponseQNameIsProtocolError() {
        String wrongResponse = """
                <x:GetOrderResponse xmlns:x="urn:wrong:orders">
                  <x:orderId>ORD-7</x:orderId>
                  <x:status>PAID</x:status>
                </x:GetOrderResponse>
                """;

        server.expect(payload(new StringSource(REQUEST)))
                .andRespond(withPayload(
                        new StringSource(wrongResponse)));

        GatewayException error = assertThrows(
                GatewayException.class,
                () -> client.fetch("ORD-7"));

        assertEquals(GatewayError.SOAP_PROTOCOL_ERROR,
                error.code());
        server.verify();
    }

    @Test
    void rejectsInvalidIdBeforeSendingAnyRequest() {
        assertThrows(IllegalArgumentException.class,
                () -> client.fetch("<bad>"));

        // No requests declared or sent.
        server.verify();
    }
}
```

These **five test methods** never open a real connection to `soap.example.invalid`. `MockWebServiceServer.createServer(template)` replaces the template's message sender with a mock, checks the SOAP request payload, and serves scripted responses/faults.

Evidence levels:

1. `matchesRequestAndParsesSuccessPayload`: the XML request has the right namespace/structure, the response payload parses into `OrderStatus`, and the method returns the expected data. `server.verify()` confirms the outbound expectation was exercised.
2. `clientFaultMapsToNonRetryableInvalidRequest`: a SOAP 1.1 `Client` fault from the mock server makes `WebServiceTemplate` throw `SoapFaultClientException`; the gateway maps it to `INVALID_REQUEST`, non-retryable.
3. `serverFaultMapsToUpstreamUnavailable`: a `Server` fault maps to `UPSTREAM_UNAVAILABLE` with the demo's retryable flag; **does not trigger actual retries**.
4. `malformedResponseQNameIsProtocolError`: a SOAP response whose root payload has the wrong namespace is rejected instead of returning a fake successful order.
5. `rejectsInvalidIdBeforeSendingAnyRequest`: an ID containing disallowed characters is blocked before building or sending XML; no expectations are registered on the mock server.

**Never label this an E2E SOAP server test**: the mock server skips networking, TLS, proxies, X.509, WS-Security, and deployment. It is a **client integration test with mocked transport**. To prove live partner communication, add contract/HTTP integration tests in a secure environment with test data.

### 8.1. Running the tests with Gradle

From the project root containing the Gradle Wrapper:

```bash
./gradlew test --tests example.testing.soap.OrderXmlTest
./gradlew test --tests example.testing.soap.OrderSoapClientTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.testing.soap.OrderXmlTest"
.\gradlew.bat test --tests "example.testing.soap.OrderSoapClientTest"
```

**Expected:** `OrderXmlTest` has 5 methods and `OrderSoapClientTest` has 5 methods, totaling **10 JUnit tests** passing when sources and dependencies match the example. Do not hardcode a fixed Gradle/JUnit stdout string since runners and loggers differ.

If client tests fail to create a SOAP message factory, verify the starter and SAAJ implementation in dependencies. If a payload matcher fails, check QName, namespace URI, and element order against the contract instead of ignoring the XML body. If fault tests fail to throw `SoapFaultClientException`, check the message factory, template fault resolver, and configured SOAP version.

## 9. Server-side SOAP endpoints: exception → SOAP Fault

For a **SOAP server** that you implement, Spring-WS provides dedicated mapping annotations and exception resolvers. The samples below are **illustrative snippets**, not standalone configured classes: they require endpoint config, schemas, message factories, resolvers, and bean scanning.

An exception with a public fault policy:

```java
@SoapFault(
        faultCode = FaultCode.CLIENT,
        faultStringOrReason = "Invalid order request",
        locale = "en")
public class InvalidOrderException extends RuntimeException {
    public InvalidOrderException() {
        super("Internal validation failed");
    }
}
```

This requires importing `org.springframework.ws.soap.server.endpoint.annotation.SoapFault` and `FaultCode`, in a Java file matching the class name. For this annotation to apply, Spring-WS needs `SoapFaultAnnotationExceptionResolver` in the context. **Annotating an exception alone does not guarantee the resolver is registered.**

Example resolver registration inside a `@Configuration`:

```java
@Bean
SoapFaultAnnotationExceptionResolver soapFaultResolver() {
    SoapFaultAnnotationExceptionResolver resolver =
            new SoapFaultAnnotationExceptionResolver();
    resolver.setOrder(1);
    return resolver;
}
```

This is an illustrative method inside a configuration class, requiring `@Bean` and `SoapFaultAnnotationExceptionResolver` imports. If other resolvers exist in the app, verify ordering so a generic resolver does not intercept the exception first and bypass your mapping.

**Security trap:** default behavior on some resolvers can copy the Java exception message into the fault reason when no public reason is specified. Never push raw SQL, JWTs, tokens, stack traces, or table names into SOAP Faults. Set a controlled `faultstring`/reason, keeping detailed diagnostics in secure, masked logs.

### 9.1. MockWebServiceClient vs. MockWebServiceServer

| Tool | Which side is tested? | What do you simulate? |
| --- | --- | --- |
| `org.springframework.ws.test.client.MockWebServiceServer` | SOAP **client** | Simulated server returning payloads or faults |
| `org.springframework.ws.test.server.MockWebServiceClient` | SOAP **server/endpoint** | Simulated request entering the context's dispatcher/endpoint |
| `MockMvc` | Spring MVC REST controller | HTTP servlet request targeting MVC mappings |
| Real HTTP client + server test | SOAP transport over network | Content-Type, SOAPAction, TLS, reverse proxies, status codes |

Server-side syntax example:

```java
MockWebServiceClient mockClient =
        MockWebServiceClient.createClient(applicationContext);

mockClient.sendRequest(
                RequestCreators.withPayload(
                        new StringSource(requestPayload)))
        .andExpect(ResponseMatchers.payload(
                new StringSource(expectedPayload)))
        .andExpect(ResponseMatchers.noFault());
```

This is an illustrative snippet inside a JUnit test with `ApplicationContext`, `requestPayload`, `expectedPayload`, and Spring-WS imports. It **does not run standalone** without `@Endpoint`/`@PayloadRoot`/resolvers configured in the context. The goal is verifying the real endpoint produces the expected response payload, without mocking your own server.

### 9.2. Testing an endpoint's SOAP Fault

When the endpoint throws `InvalidOrderException` and the resolver emits a Client/Sender fault:

```java
mockClient.sendRequest(
                RequestCreators.withPayload(
                        new StringSource(invalidRequest)))
        .andExpect(
                ResponseMatchers.clientOrSenderFault(
                        "Invalid order request"));
```

This snippet requires `invalidRequest` to trigger the real exception and have the resolver loaded. It checks the **fault type and public fault reason**. If the contract also mandates `detail.code`, add matchers for the SOAP Envelope/Detail/XPath or parse the fault to verify the namespaced business code.

**Do not assert response status alone:** a Spring-WS endpoint can return a completely valid SOAP Fault where REST-style `status().isBadRequest()` does not apply. Assert the **SOAP Fault in the Body**, and verify transport status separately when contractual.

## 10. Testing XSD/WSDL contracts rather than checking just a few fields

A reliable SOAP integration verifies **message shape** against the agreed XSD/WSDL:

- Element names and namespaces; required/optional fields, `minOccurs`/`maxOccurs`.
- Number types, date/time formats, decimal precision, enum values, `nillable`, empty string vs. omitted element.
- Element sequence order when the XSD uses `xs:sequence`.
- Fault `detail` structure, business error codes, and namespaces.
- Headers, WS-Addressing, actions, and WS-Security when required by the endpoint.
- Endpoint URL, SOAP 1.1/1.2 binding, Content-Type, and SOAPAction in transport tests.

In Spring-WS test matchers, `validPayload(schemaResource)`, `payload(expectedSource)`, and XPath matchers help assert XSD and structure. Using `payload(...)` against a single fixture checks **one XML example** and may miss other XSD constraints. Conversely, an XSD test can pass while `ORDER_NOT_FOUND` business mapping is still wrong.

**Three-layer strategy:**

1. **Schema contract tests:** requests, responses, and fault details validate against XSD with the right namespaces.
2. **Behavior tests:** valid IDs yield right statuses; missing IDs return the contracted fault/response without leaking sensitive info.
3. **Transport/integration tests:** HTTP status, Content-Type, SOAPAction, TLS, WS-Security, and real retries/timeouts; never expect a mock server test to prove these.

When a partner's WSDL changes, update generated types/fixtures and run regression tests. Never "loosen" XPath to ignore wrong namespaces just because a new WSDL broke compatibility; evaluate contract versioning intentionally.

## 11. Mapping errors into a REST/GraphQL facade

An application can expose REST or GraphQL to clients while calling SOAP downstream. In that architecture, **isolate SOAP exceptions inside the adapter layer**:

```text
SOAP external service
    |
    +-- Success XML payload
    |       --> OrderStatus (domain DTO)
    |
    +-- SOAP Client/Sender Fault
    |       --> INVALID_REQUEST / business detail mapping
    |
    +-- SOAP Server/Receiver Fault
    |       --> UPSTREAM_UNAVAILABLE
    |
    +-- Transport failure
    |       --> SOAP_TRANSPORT_FAILURE
    |
    +-- Malformed XML / wrong namespace
            --> SOAP_PROTOCOL_ERROR

Domain/port layer
    |
    +-- REST API: map stable codes -> HTTP status + safe JSON
    |
    +-- GraphQL API: map stable codes -> GraphQL errors/extensions policy
```

For a REST facade, an **example policy** (not a fixed rule of SOAP itself):

| Domain error | Suggested facade HTTP status | Public response |
| --- | ---: | --- |
| `INVALID_REQUEST` from invalid client request | 400 | `{"code":"INVALID_ORDER_REQUEST"}` |
| `NOT_FOUND` confirmed from fault detail | 404 | `{"code":"ORDER_NOT_FOUND"}` |
| `UPSTREAM_UNAVAILABLE` | 502 or 503 depending on cause | `{"code":"ORDER_SERVICE_UNAVAILABLE"}` |
| `SOAP_PROTOCOL_ERROR` | 502 | `{"code":"UPSTREAM_PROTOCOL_ERROR"}` |

**For GraphQL**, responses may return HTTP 200 with an `errors` array depending on failure type and GraphQL transport policy; never apply a REST HTTP mapping table blindly to GraphQL without reviewing its contract. Verify `errors[].extensions.code` and field-level partial data cleanly, **without echoing raw SOAP fault reasons**.

**Crucially:** a SOAP `Client` fault can occur because **your own adapter generated a bad request**, not because of bad end-user input. Never return HTTP 400 to the user when the bug sits in your serializer or wiring. Distinguish "invalid user input," "invalid SOAP request from adapter," and "business not found" using detail codes and verified boundaries.

### Retries and idempotency

`UPSTREAM_UNAVAILABLE` does not mean retrying is always safe. For SOAP actions that transfer money, place orders, or write state, the server may already have processed the request before a timeout; blind retries create duplicate transactions. Only retry when:

- The operation is read-only/idempotent or the upstream supports idempotency keys/deduplication.
- The error falls under the retryable contract, paired with backoff, retry caps, and a circuit breaker.
- Safe metrics/trace logs exist for diagnostics without logging raw credentials, WS-Security headers, or PII.

Every one of those policies needs **its own risk-based test**; asserting `GatewayException.retryable()==true` only checks flag mapping, not that the system actually retries safely without double side effects.

## 12. SOAP Fault detail: do not confuse standard codes with application codes

Returning to the fixture:

```xml
<s:Fault xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
         xmlns:o="urn:example:orders">
  <faultcode>s:Client</faultcode>
  <faultstring>Order was not found</faultstring>
  <detail>
    <o:OrderError>
      <o:code>ORDER_NOT_FOUND</o:code>
    </o:OrderError>
  </detail>
</s:Fault>
```

There are two code levels:

- **`faultcode=s:Client`**: SOAP 1.1 request-category fault; many unrelated errors share this code.
- **`detail/o:OrderError/o:code=ORDER_NOT_FOUND`**: application error code **when defined by the WSDL/XSD**.

`OrderXml.readSoap11Fault(...)` parses the **full Envelope**, resolves prefix `s`, reads `detail`, and classifies `ORDER_NOT_FOUND`. Meanwhile, `OrderSoapClientTest` builds faults with `withClientOrSenderFault(...)` **without custom detail**; that test verifies standard fault-code mapping only.

**Never claim client tests guard `ORDER_NOT_FOUND` unless detail parsing runs through the real SOAP client path.** When the integration contract requires it, extend the adapter to read `SoapFaultClientException.getSoapFault().getFaultDetail()`, pass `SoapFaultDetailElement`s through a controlled schema parser, and add a mock SOAP envelope fixture containing `detail`—only then is full client mapping protected.

**Never match reason strings** like `contains("not found")`, since wording varies, may be localized, or differs between sandbox and production.

## 13. XML security and differences between test and production

XML carries more features than JSON, including entities and DTDs. When parsing XML from untrusted partners:

- **Block DTDs/external entities** to mitigate XXE, SSRF, and local file reads. In JAXP use `FEATURE_SECURE_PROCESSING` and flags disabling external entities/DTDs; fail closed if the provider lacks support.
- **Bound document size and nesting depth** to prevent CPU/RAM exhaustion; the demo limits character count, while production needs HTTP/message-level limits.
- **Enable namespace-aware parsing** so elements with matching local names in different namespaces are never confused.
- **Validate against XSD** when contractual; note that XSDs can also import/include resources, so restrict schema resolver external access safely.
- **Never log raw SOAP Envelopes** carrying `Authorization`, WS-Security `UsernameToken`, signatures, account numbers, or PII. When tracing, mask secrets and restrict log retention and access.
- **Avoid manual string interpolation** for flexible inputs. The demo client restricts IDs to `ORD-[0-9]{1,6}`, making XML text safe. For rich fields/arbitrary UTF-8, use JAXB/DOM/StAX writers and test `&`, `<`, and Unicode escaping.
- **Do not ignore SOAP Headers** when contracts mandate `mustUnderstand`, WS-Addressing, signatures, or timestamps. Payload-only tests do not verify security headers.

**Watch out for Spring-WS/JAXB parsers:** `OrderXml.parseSecure(...)` secures only the parser **that your code explicitly invokes**. SOAP libraries, transports, and SAAJ run their own parsers; verify and harden XXE/DTD settings across message ingestion, schema validators, and marshallers/unmarshallers per documentation and version. A passing DOM parser unit test alone does not prove the entire production SOAP stack resists XXE.

## 14. Avoiding weak or misleading SOAP tests

### 14.1. Checking only that the XML string contains "PAID"

```java
assertTrue(xml.contains("PAID"));
```

Insufficient because `PAID` could sit inside a comment, the wrong element, the wrong namespace, or an error message. Replace with namespace-aware DOM/XPath assertions and explicit root QName checks.

### 14.2. Comparing XML byte-for-byte

Raw string equality fails when the server changes prefixes or indentation while keeping XML semantics identical. For payload contracts, favor `MockWebServiceServer.expect(payload(...))`/XMLUnit or namespace-aware DOM/XPath alongside key field checks. **Never skip schema type or element-order checks** when contractual.

### 14.3. Asserting HTTP 500 alone to confirm a SOAP Fault

HTTP status is only a transport signal. Verify the Envelope holds a SOAP Fault, the right QName, and valid fault details. An HTTP 500 returning an HTML error page is not a SOAP Fault.

### 14.4. Using SOAP 1.1 XPaths for SOAP 1.2

`faultcode/faultstring/detail` differ from `Code/Reason/Detail`, and Envelope namespaces differ too. Tests must specify the SOAP version explicitly.

### 14.5. Returning raw exception messages in faultstring

Raw messages can expose SQL, tokens, or internal class names; contracts should return safe public codes/reasons while logging full diagnostics securely. Sentinel-secret tests can prove faults leak no sensitive data.

### 14.6. Unit testing a fault mapper and concluding client transport works

Mapper tests verify only code → domain classification; they do not verify SOAP headers, SOAPAction, SAAJ marshalling, TLS, or real servers. Pair `MockWebServiceServer` tests with transport integration tests when risks demand them.

### 14.7. Calling verify() on MockWebServiceServer without validating the payload

Using only `expect(anything())` fails to check request namespaces, element ordering, or ID values. Use `payload(expectedSource)` plus XPath/header matchers per contract.

### 14.8. Forgetting to call server.verify()

Unverified mock server expectations allow false-green tests. After invoking the action under test, **always call `server.verify()`**; in negative/no-request tests, it likewise proves no unexpected outbound request was queued or skipped.

### 14.9. Retrying non-idempotent SOAP write operations

A timeout never guarantees the server rolled back. Never retry a mutating SOAP operation just because the fault code says "Server" unless an idempotency or compensation policy is in place.

## 15. Common mistakes and fixes

**1. Confusing namespaces with prefixes.** Tests matching `"ord:"` text instead of URI `urn:example:orders`; switch to QName or `NamespaceContext`.

**2. Passing a full SOAP Envelope to payload APIs.** `WebServiceTemplate.sendSourceAndReceiveToResult` places the payload inside Body; never wrap it in a second Envelope.

**3. Using SOAP 1.2 fault paths on SOAP 1.1 messages.** Check Envelope namespaces and parse per version.

**4. Checking HTTP status while ignoring the SOAP Fault body.** SOAP-level failures must assert fault code, reason, and detail.

**5. Equating transport exceptions with SOAP Fault exceptions.** Network timeouts/TLS errors may carry no XML at all; handle separately from `SoapFaultClientException`.

**6. Matching `faultstring` to detect ORDER_NOT_FOUND.** Use structured `detail.code` per schema; reasons are prose that can change or be localized.

**7. Mapping every Client fault to a user error.** Your adapter may have generated invalid XML; distinguish error sources via detail codes and validation contracts.

**8. Ignoring nested `detail`.** Many business codes live inside SOAP fault details; checking only standard Client/Server codes misses them.

**9. Omitting `server.verify()` with MockWebServiceServer.** Leaves unconsumed expectations undetected.

**10. Skipping negative namespace tests.** Payloads with matching local names and wrong namespaces must be rejected.

**11. Calling `getElementsByTagNameNS` unbounded to pick fields.** Risks matching a deeper nested element of the same name; check direct children/exact QNames.

**12. Leaving default XML parsers enabled for untrusted input.** Risks XXE/DTD attacks; harden JAXP, bound sizes, and test DOCTYPE rejection.

**13. Hardening only business-layer parsers.** SAAJ and XML libraries run separate parsers; protect the entire stack.

**14. Hitting live networks in every SOAP client unit test.** Slow and flaky; use `MockWebServiceServer` for request/response/faults and selective real integrations.

**15. Assuming SOAP Faults always include `detail`.** Faults may omit application details; mapping must handle missing details gracefully.

**16. Assuming Server/Receiver faults are always retryable.** Retries depend on idempotency, rate limits, backoff, side effects, and partner rules.

**17. Using MockMvc to test SOAP `@Endpoint`s.** For Spring-WS `MessageDispatcher`, use `MockWebServiceClient`; `MockMvc` is for Spring MVC.

**18. Exposing raw exception messages in JSON/GraphQL/HTTP errors.** Sanitize and map to stable public error codes.

## 16. QA checklist for SOAP XML/Faults

**XML contract:**

- Are we targeting SOAP 1.1 or 1.2? Is the Envelope namespace right?
- Do tests distinguish the **SOAP Envelope** from the **business payload**?
- Does the root payload QName match the namespace URI and local name?
- Do required elements match schema types, occurrences, and sequence order?
- Do tests include a fixture changing prefixes (passes) and changing namespace URI (fails)?
- Is the XML parser tested to reject DOCTYPE/external entities?
- When using schema validation, are XSD imports and external access locked down?

**Fault/error mapping:**

- Are Client/Sender, Server/Receiver, MustUnderstand, and VersionMismatch covered where applicable?
- Are standard fault codes kept distinct from application `detail.code`?
- Are missing fault details and changing reason prose handled cleanly?
- Are full `QName`s compared instead of local parts alone?
- Are raw `faultstring`, exceptions, SQL, and tokens prevented from leaking in public errors?
- Do mappings to REST/GraphQL follow each API's contract instead of applying rigid HTTP status defaults?
- Is there an explicit retry and idempotency policy?

**Testing boundaries:**

- Do SOAP client tests use `MockWebServiceServer`, request payload matchers, fault fixtures, and `server.verify()`?
- Do SOAP endpoint tests use `MockWebServiceClient` with real endpoints and resolvers loaded?
- When HTTP headers, SOAPAction, WS-Security, or TLS are contractual, are matching transport tests present?
- Do mocks/fixtures reflect the actually deployed WSDL/XSD version?
- Is state isolated, with no real user data or tokens in tests?
- Are passing tests cited strictly for the **boundaries they actually executed**?

**Conclusion:** reliable SOAP testing verifies **XML payloads by QName/XSD**, separates **SOAP Faults, HTTP/transport failures, and business details**, and maps them into **stable, safe, idempotency-aware application errors**. Use JAXP/XML tests for parsers, `MockWebServiceServer` for SOAP clients, `MockWebServiceClient` for endpoints, and targeted HTTP integration tests for transport and security. Never skip versions, namespaces, fault details, or XXE protections just to turn assertions green.

## 17. References

- [Spring Web Services Reference — Testing Client/Server](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/): using `MockWebServiceServer`, `MockWebServiceClient`, SOAP Faults, and payload matchers.
- [Spring-WS — WebServiceTemplate API](https://docs.spring.io/spring-ws/docs/4.0.11/api/org/springframework/ws/client/core/WebServiceTemplate.html): `sendSourceAndReceiveToResult` and fault handling.
- [Spring-WS — SoapFaultClientException API](https://docs.spring.io/spring-ws/docs/4.0.9/api/org/springframework/ws/soap/client/SoapFaultClientException.html): `getFaultCode`/`getFaultStringOrReason`/`getSoapFault`.
- [Spring-WS — MockWebServiceServer API](https://docs.spring.io/spring-ws/docs/4.0.9/api/org/springframework/ws/test/client/MockWebServiceServer.html): creating the mock server, expectations, and verify.
- [Spring-WS — ResponseCreators API](https://docs.spring.io/spring-ws/docs/4.0.9/api/org/springframework/ws/test/client/ResponseCreators.html): `withPayload`, `withClientOrSenderFault`, and `withServerOrReceiverFault`.
- [Spring Boot 3.5 — Managed Dependencies](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html): Boot-managed versions for Spring-WS and Spring test.