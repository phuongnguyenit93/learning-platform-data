# Testing Request, Response, and Contract Error Messages

In Spring Boot SOAP integrations, an HTTP 200 status is not enough to prove two systems understand each other properly. The application might send the wrong XML element name, use the wrong namespace, misread a response field, or miss a business SOAP Fault. Even when XML is syntactically valid, messages can still violate the **WSDL/XSD contract** or partner processing rules.

This lesson belongs to the **SOAP and XML** chapter of the **SPRING_BOOT_INTEGRATION** module. Across system integrations involving HTTP clients, databases, caches, message brokers, and Spring Integration adapters, SOAP testing safeguards data contracts, error classification, transactions, duplicate prevention, and observability in real-world flows.

## 1. Testing Objectives and Boundaries

After this lesson, you will be able to:

- Identify what must be verified at the XML, WSDL/XSD, SOAP, and HTTP layers.
- Build fixture suites for requests, successful responses, and SOAP Faults.
- Test SOAP clients with **MockWebServiceServer** and SOAP endpoints with **MockWebServiceClient**.
- Detect compatibility-breaking contract changes and distinguish SOAP Faults from connection errors.
- Design tests for errors, retries, idempotency, and observability aligned with Spring Boot integration flows.

A solid test suite answers at least three independent questions:

| Question | Specific checks | Risk if skipped |
| --- | --- | --- |
| **Does the message match the contract?** | Well-formed XML, QName/namespace, data types, ordering, XSD constraints, operations, and faults declared in WSDL | Partner rejects messages; both sides interpret structure differently |
| **Does the application handle it right?** | Request construction, response mapping, error code interpretation, retry decisions, and business return values | Corrupts saved state, drops business errors, triggers unnecessary retries |
| **Does cross-boundary exchange work?** | URL, SOAP version, Content-Type, SOAPAction, headers, HTTP status, timeouts, TLS, logging, and correlation ID | Passes under mocks but fails over real connections |

Commonly confused concepts:

- **Well-formed XML**: properly matched open/close tags without syntax errors; says nothing about business validity.
- **XSD-valid XML**: elements, namespaces, types, and constraints comply with the matching schema.
- **WSDL**: describes operations, messages/bindings, endpoints, and declared faults; an XSD-valid payload can still specify the wrong operation or SOAPAction.
- **SOAP Fault**: protocol-level SOAP error message. A fault declared in the WSDL can be a valid contract-defined business outcome.
- **Contract error**: malformed request/response structure, wrong namespace, wrong type, or uncontrolled breaking change; not identical to all SOAP Faults.

## 2. A Running Illustrative Contract

Suppose Spring Boot calls an order-status lookup service using operation **GetOrder**, application namespace **urn:demo:orders:v1**, and SOAP 1.1. This is a learning example; in real projects, use the WSDL/XSD provided by the partner system as the source of truth.

### 2.1. Valid SOAP Request

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:demo:orders:v1">
  <soap:Header/>
  <soap:Body>
    <ord:GetOrderRequest>
      <ord:orderId>ORD-1024</ord:orderId>
    </ord:GetOrderRequest>
  </soap:Body>
</soap:Envelope>
~~~

Verify: exact root element **GetOrderRequest**, accurate namespace, presence of **orderId**, and value matching contract constraints. If the partner requires auth headers, timestamps, or correlation IDs, test those headers and sensitive-data protection rules too.

### 2.2. Successful Response

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:demo:orders:v1">
  <soap:Body>
    <ord:GetOrderResponse>
      <ord:orderId>ORD-1024</ord:orderId>
      <ord:status>CONFIRMED</ord:status>
    </ord:GetOrderResponse>
  </soap:Body>
</soap:Envelope>
~~~

Do not assert HTTP 200 alone. Tests must verify the body belongs to the right operation, extract **orderId** and **status**, verify status is within allowed values, and assert accurate translation to the internal model.

### 2.3. SOAP 1.1 Error Response

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:demo:orders:v1">
  <soap:Body>
    <soap:Fault>
      <faultcode>soap:Client</faultcode>
      <faultstring>Order not found</faultstring>
      <detail>
        <ord:OrderNotFoundFault>
          <ord:errorCode>ORDER_NOT_FOUND</ord:errorCode>
          <ord:orderId>ORD-1024</ord:orderId>
        </ord:OrderNotFoundFault>
      </detail>
    </soap:Fault>
  </soap:Body>
</soap:Envelope>
~~~

Here verify **faultcode**, **faultstring**, **detail** structure, and code **ORDER_NOT_FOUND** per contract. The application should map it to a deterministic business error instead of assuming every HTTP 500 is a retryable outage.

**Version note:** SOAP 1.1 uses the envelope namespace above, usually paired with Content-Type **text/xml** and the **SOAPAction** header. SOAP 1.2 uses namespace **http://www.w3.org/2003/05/soap-envelope**, typically **application/soap+xml**, and a different Fault layout (**Code/Reason/Detail**, codes **Sender/Receiver**). Do not mix fixtures or claim support for both versions if an endpoint exposes only one.

## 3. Standardizing Contracts and Test Fixtures

Store accepted contracts in source control with clear versioning and update processes. An example layout:

~~~text
src/test/resources/
  contracts/
    orders.wsdl
    orders.xsd
  soap/
    request-get-order.xml
    response-get-order.xml
    fault-order-not-found.xml
    invalid-missing-order-id.xml
    invalid-wrong-namespace.xml
~~~

Contracts and fixtures have different origins: **WSDL/XSD** comes from the service owner or agreed contract; **fixtures** are created by the integration team to reproduce scenarios. Avoid tweaking fixtures just to match buggy code without checking the official contract.

Example partial XSD for the *payload* inside SOAP Body:

~~~xml
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:ord="urn:demo:orders:v1"
           targetNamespace="urn:demo:orders:v1"
           elementFormDefault="qualified">

  <xs:simpleType name="OrderId">
    <xs:restriction base="xs:string">
      <xs:pattern value="ORD-[0-9]{4}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:simpleType name="OrderStatus">
    <xs:restriction base="xs:string">
      <xs:enumeration value="PENDING"/>
      <xs:enumeration value="CONFIRMED"/>
      <xs:enumeration value="CANCELLED"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="GetOrderRequest">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="orderId" type="ord:OrderId"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

  <xs:element name="GetOrderResponse">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="orderId" type="ord:OrderId"/>
        <xs:element name="status" type="ord:OrderStatus"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

  <xs:element name="OrderNotFoundFault">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="errorCode" type="xs:string"/>
        <xs:element name="orderId" type="ord:OrderId"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
~~~

With this schema, a request missing **orderId**, passing code **1024**, or a response returning **UNKNOWN** for **status** must be caught. For SOAP Faults, the **OrderNotFoundFault** element's XSD alone does not prove the operation declares that fault: also verify the corresponding message/fault/binding in the WSDL.

When comparing XML, match by **namespace URI + local name** or structural XML comparisons. Prefixes **ord** and **o** can point to the exact same namespace; raw string comparison tests produce false failures due to whitespace, attribute ordering, or prefix names.

Cases requiring explicit decisions from the contract:

- **Absent**, **empty element**, and **xsi:nil="true"** are not automatically equivalent; check **minOccurs**, **nillable**, and default/fixed values.
- **xs:sequence** enforces element order; a serializer can emit the wrong order even when all fields are present.
- Dates/times must standardize types, timezones, and formatting; decimals must never lose precision when mapped to internal numeric types.
- For SOAP Headers, verify namespaces, required fields, and behavior when headers are missing or invalid. With WS-Security, test signatures, timestamps, and auth configuration at the real execution layer.

## 4. Schema Testing: Catching Contract Mismatches Before Network Calls

An XSD test runs quickly in CI without needing a live SOAP provider. JUnit 5 example using Java JAXP; **/contracts/orders.xsd** resides in test resources per the layout above.

~~~java
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.io.InputStream;
import java.io.StringReader;
import javax.xml.XMLConstants;
import javax.xml.transform.stream.StreamSource;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;
import javax.xml.validation.Validator;
import org.junit.jupiter.api.Test;

class OrderSchemaTest {
    @Test
    void responsePayloadMustMatchXsd() throws Exception {
        String responsePayload = """
            <ord:GetOrderResponse xmlns:ord="urn:demo:orders:v1">
              <ord:orderId>ORD-1024</ord:orderId>
              <ord:status>CONFIRMED</ord:status>
            </ord:GetOrderResponse>
            """;

        SchemaFactory factory = SchemaFactory.newInstance(
                XMLConstants.W3C_XML_SCHEMA_NS_URI);
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        try (InputStream xsd = getClass()
                .getResourceAsStream("/contracts/orders.xsd")) {
            assertNotNull(xsd, "Missing orders.xsd contract");

            Schema schema = factory.newSchema(new StreamSource(xsd));
            Validator validator = schema.newValidator();
            validator.validate(new StreamSource(
                    new StringReader(responsePayload)));
        }
    }
}
~~~

**Key point:** the business XSD above declares elements inside the **SOAP Body**, so the code validates **responsePayload**, not the whole SOAP Envelope. When reading full XML envelopes over HTTP, parse safely and extract the payload element before applying the business XSD; validating the SOAP envelope structure is a separate step. When schemas use **xs:include/xs:import**, configure system IDs and local resolvers rather than letting the validator fetch untrusted network resources.

Add negative cases to prove the validator *actually* catches errors: replace **CONFIRMED** with **UNKNOWN**, remove **orderId**, change namespaces, or reorder elements. In JUnit use **assertThrows(SAXException.class, ...)** for each invalid payload. Feeding only valid data into a validator does not prove constraints are enforced accurately.

## 5. Testing SOAP Clients in Spring Boot

For applications using **WebServiceTemplate**, Spring Web Services provides **MockWebServiceServer** to mock the SOAP server at the client boundary. Tests verify outbound requests from the client and simulate responses/faults without network calls.

Example Gradle dependencies (versions managed by Spring Boot):

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-webservices'
testImplementation 'org.springframework.boot:spring-boot-starter-test'
testImplementation 'org.springframework.ws:spring-ws-test'
~~~

### 5.1. Valid Request and Successful Response

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.ws.test.client.RequestMatchers.payload;
import static org.springframework.ws.test.client.ResponseCreators.withClientOrSenderFault;
import static org.springframework.ws.test.client.ResponseCreators.withPayload;

import java.util.Locale;
import org.junit.jupiter.api.Test;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.soap.client.SoapFaultClientException;
import org.springframework.ws.test.client.MockWebServiceServer;
import org.springframework.xml.transform.StringResult;
import org.springframework.xml.transform.StringSource;

class OrderSoapClientContractTest {
    private static final String REQUEST = """
        <ord:GetOrderRequest xmlns:ord="urn:demo:orders:v1">
          <ord:orderId>ORD-1024</ord:orderId>
        </ord:GetOrderRequest>
        """;

    private static final String RESPONSE = """
        <ord:GetOrderResponse xmlns:ord="urn:demo:orders:v1">
          <ord:orderId>ORD-1024</ord:orderId>
          <ord:status>CONFIRMED</ord:status>
        </ord:GetOrderResponse>
        """;

    private final WebServiceTemplate template = createTemplate();
    private final MockWebServiceServer server =
            MockWebServiceServer.createServer(template);

    private static WebServiceTemplate createTemplate() {
        WebServiceTemplate template = new WebServiceTemplate();
        template.setDefaultUri("http://example.test/soap/orders");
        return template;
    }

    @Test
    void sendsCorrectPayloadAndReadsResponse() {
        server.expect(payload(new StringSource(REQUEST)))
              .andRespond(withPayload(new StringSource(RESPONSE)));

        StringResult actual = new StringResult();
        boolean received = template.sendSourceAndReceiveToResult(
                new StringSource(REQUEST), actual);

        assertThat(received).isTrue();
        assertThat(actual.toString()).contains("CONFIRMED");
        server.verify();
    }

    @Test
    void exposesSoapFaultToErrorHandler() {
        server.expect(payload(new StringSource(REQUEST)))
              .andRespond(withClientOrSenderFault(
                      "Order not found",
                      Locale.ENGLISH));

        SoapFaultClientException exception = assertThrows(
                SoapFaultClientException.class,
                () -> template.sendSourceAndReceiveToResult(
                        new StringSource(REQUEST), new StringResult()));

        assertThat(exception.getFaultStringOrReason())
                .contains("Order not found");
        server.verify();
    }
}
~~~

In this sample, **REQUEST** and **RESPONSE** are the *payload elements inside the SOAP Body*. Spring Web Services wraps the envelope for the exchange. **MockWebServiceServer** verifies the payload and simulates responses; the fault test confirms exception throwing. Move **REQUEST/RESPONSE** into shared fixtures so individual tests do not define conflicting versions of the contract.

The test above verifies basic SOAP client mechanics; full business testing should invoke **the application's client adapter**, verifying mapped domain values and domain error types. If the client attaches SOAPAction, WS-Addressing, or security headers, add matching assertions. Checking the substring **CONFIRMED** is illustrative only; production suites should parse XML, assert fields by namespace/XPath, and validate responses against the XSD.

### 5.2. Testing Endpoints Exposed by the Application

When Spring Boot itself acts as a SOAP provider with **@Endpoint**, use **MockWebServiceClient** to send requests to endpoints inside the application context and assert returned payloads without opening an HTTP port.

~~~java
import static org.springframework.ws.test.server.RequestCreators.withPayload;
import static org.springframework.ws.test.server.ResponseMatchers.payload;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.ws.test.server.MockWebServiceClient;
import org.springframework.xml.transform.StringSource;

@SpringBootTest
class OrderSoapEndpointTest {
    @Autowired
    private ApplicationContext context;

    @Test
    void returnsOrderStatusFromEndpoint() {
        String request = """
            <ord:GetOrderRequest xmlns:ord="urn:demo:orders:v1">
              <ord:orderId>ORD-1024</ord:orderId>
            </ord:GetOrderRequest>
            """;
        String expected = """
            <ord:GetOrderResponse xmlns:ord="urn:demo:orders:v1">
              <ord:orderId>ORD-1024</ord:orderId>
              <ord:status>CONFIRMED</ord:status>
            </ord:GetOrderResponse>
            """;

        MockWebServiceClient client =
                MockWebServiceClient.createClient(context);
        client.sendRequest(withPayload(new StringSource(request)))
              .andExpect(payload(new StringSource(expected)));
    }
}
~~~

This example assumes the application already configured **@Endpoint** and Spring WS message dispatching; order data must be seeded via a mock repository or controlled test fixtures. Add endpoint tests verifying SOAP Fault responses for invalid inputs or contracted internal service errors.

### 5.3. When the Application Uses JAXB or WSDL-Generated Clients

When an adapter uses **marshalSendAndReceive**, test the adapter's real execution path: domain object → mapper → JAXB marshaller → SOAP request → unmarshaller → domain object. Do not test only static XML strings, because common bugs hide in JAXB annotations, field ordering, enums, datetime formatting, and exception mapping.

Recommended workflow:

1. Initialize the client adapter with production-like **WebServiceTemplate** and marshaller.
2. Use **MockWebServiceServer** to intercept the marshalled request and return response/fault fixtures.
3. Match request structure/namespaces, and verify the returned domain model and error handling rules.
4. Verify WSDL/XSD-generated code is regenerated cleanly when contract versions change.

If returned data updates a database, emits broker events, or feeds a Spring Integration flow, add tests verifying those effects—especially transactions, retries, and duplicate handling.

## 6. Systematic Testing of Contract Errors and SOAP Faults

Do not lump every error case into a generic **throws Exception** test. Negative test suites should separate structural, protocol, business, and infrastructure failures.

| Scenario | Test expectation |
| --- | --- |
| XML missing **orderId**, wrong pattern, or wrong order | Rejected by XSD; business service/writes are not invoked |
| Wrong namespace or operation name | Caught by XSD/WSDL or dispatch layer with clear diagnostics |
| SOAPAction or Content-Type mismatches binding | Caught at HTTP/SOAP layer; never silently treated as success |
| Response missing required field or carrying unknown enum | Client does not update state as succeeded; raises classified integration error |
| SOAP Fault **Client/Sender** with declared business code | Maps to deterministic business error; typically does not retry same request |
| SOAP Fault **Server/Receiver** from transient error | Classified and bounded-retried when operation is safe |
| HTTP 500 without a valid SOAP Fault | Classified as protocol/transport error; never parsed as a business fault |
| Timeout, connection reset, TLS/DNS error | Raises contextual connection error; never assumes server did not process request |
| Partner changes WSDL/XSD altering QName, type, or adding required field | Compatibility tests fail and block deployment until migration is planned |
| XML contains DTD, external entities, or oversized payload | Parser rejects unsafe/over-limit input without data leaks or resource exhaustion |

Define retry policies based on **operation semantics**. For mutating operations like creating payments or orders, timeouts can occur *after the partner succeeded*. Blind retries create duplicates; use idempotency keys if supported by contract, status lookups, or receiver-side deduplication. For broker-backed flows, test redelivery and state/checkpoint persistence so completed tasks are not re-executed.

### SOAP Faults and What to Assert

A reliable fault test asserts simultaneously:

- Protocol and SOAP version, **faultcode** or **Code**, error reason, and XML **detail** if declared by contract.
- Partner error code, accurate mapping to domain error types, and upstream API or flow behavior.
- Retry/no-retry rules, safe logging, and correlation IDs for tracing.
- Missing or schema-invalid detail cases: the application must degrade gracefully without losing the root cause.

With SOAP 1.1, never hardcode **HTTP 500 = retryable technical error**; the exact same status code can carry a business SOAP Fault. With SOAP 1.2, fault code names and structure differ. Assert against the real contract and adapter rules rather than HTTP status alone.

## 7. Testing HTTP Boundaries and Real Systems

Spring-WS mocks test the message/client or endpoint layers well, yet omit TLS, HTTP connections, proxies, timeout settings, and live partner behavior. Add these testing tiers:

~~~mermaid
flowchart LR
    A["WSDL/XSD fixtures"] --> B["XSD and serializer tests"]
    B --> C["MockWebServiceServer or MockWebServiceClient"]
    C --> D["HTTP mock server with real envelopes and headers"]
    D --> E["Partner sandbox / contract tests"]
    E --> F["Post-deploy observability"]
~~~

**HTTP mock servers** (such as WireMock or MockWebServer) let you verify real request envelopes, paths, SOAPAction, Content-Type, HTTP 200/500 responses, timeouts, and error XML over transport. Use full **Envelope/Body/Header** fixtures at this layer. String-matching HTTP mocks do not validate XSD compliance on their own, so pair them with schema validation.

**Sandbox/contract tests** running against a partner-controlled environment catch WSDL version drift, certificate issues, routing quirks, required headers, and real data shapes. These tests need non-sensitive data, explicit timeouts, cleanup if mutating state, and should never replace fast CI unit/integration tests.

Before accepting contract changes, evaluate:

| Change from provider | Typical assessment |
| --- | --- |
| Adding an **optional** element with `minOccurs=0` | Potentially compatible; still test old clients and parser acceptance of the new element |
| Changing namespace or operation QName | Usually a breaking change |
| Changing an optional element to required | Risks breaking older requests |
| Removing fields or changing types/enums | Risks breaking existing clients |
| Switching SOAP 1.1 to SOAP 1.2, actions, or bindings | Re-verify message factories, headers, and faults |
| Renaming XML prefixes while keeping the namespace URI | Does not inherently change semantics; avoid brittle hardcoded string tests |

**Consumer-driven contracts** help when consumers publish key assumptions to providers. With SOAP, however, the primary contract still requires verifying the agreed WSDL/XSD and business rules; consumer sample sets cannot replace the full provider contract.

## 8. Integrating into Development and Operations Workflows

In Spring Boot projects with multiple adapters, place SOAP tests close to the integration adapter and continue verifying behavior as data flows through downstream layers:

1. **Pull request:** run parser/schema tests with valid and invalid fixtures, mapper/JAXB unit tests, and **MockWebServiceServer** or **MockWebServiceClient** tests.
2. **Integration tests:** run HTTP mocks to verify bindings, headers, TLS configs, timeouts, faults, and retries; if flows write to databases or publish messages, verify transactions and idempotency.
3. **Pre-deploy:** cross-check active WSDL/XSD against the partner's published version and run key sandbox checks.
4. **Post-deploy:** monitor SOAP Fault rates by code, validation/unmarshal errors, timeouts, retry counts, latency, and dead-letter queue volume.

Design principles for testing and observability:

- **Classify errors immediately at the adapter:** contract violations, business SOAP faults, server SOAP faults, timeouts/transport errors, and mapping errors need distinct types or codes.
- **Keep diagnostic context concise and safe:** operation, contract version, endpoint alias, correlation ID, fault code, latency, and retry count. Mask/strip tokens, signatures, personal identifiers, and sensitive contents before logging.
- **Constrain untrusted XML inputs:** configure parsers/validators against DTDs and external entities, and cap sizes/depths where appropriate. Test security independently from XSD tests, because schema-valid XML is not automatically safe.
- **Avoid unintended shared state:** use versioned fixtures, fixed clocks, and explicit test setup/cleanup so tests never depend on implicit execution order.
- **Maintain contract history:** when updating WSDLs/XSDs, record the version, change origin, compatibility assessment, and tests proving legacy clients still work.

## 9. Suggested Practice Exercise

Using the **GetOrder** operation and illustrative contract above, build a small test suite:

1. Create fixtures for a valid request, a **CONFIRMED** response, and an **ORDER_NOT_FOUND** SOAP Fault.
2. Create at least three invalid fixtures: missing **orderId**, wrong namespace, and a response with **status=UNKNOWN**. Validate each against the XSD and confirm all three failures are caught.
3. Build a SOAP client adapter using **WebServiceTemplate**; verify requests and mapped results with **MockWebServiceServer**.
4. Test faults: the adapter must return an **OrderNotFound** domain error (or equivalent) and never retry that business error.
5. Use an HTTP mock returning a valid SOAP Fault with HTTP 500 and an HTTP 500 with a non-SOAP body. Prove both cases are classified differently.
6. Change the namespace or turn **orderId** into a new required field in a test copy of the contract. Observe which tests fail and describe a compatibility strategy.

**Completion criteria:** valid requests/responses pass and map accurately; invalid payloads are blocked; faults are classified per contract; timeouts/retries never cause duplicate processing; and compatibility-breaking WSDL/XSD changes are caught before integrating with the partner.

A reliable SOAP flow does not stop at "sending XML." It proves **contract compliance**, **correct behavior on both success and failure**, and **safe impact on the rest of the Spring Boot system**.
