# Message Senders, HTTP Connections, Authentication, and Timeouts

## Objectives and Context

In the **SPRING_BOOT_INTEGRATION** module, Spring Boot orchestrates system integrations across HTTP clients, databases, caches, message brokers, and Spring Integration adapters. Alongside REST/JSON, many ERPs, banking systems, insurers, and enterprise platforms expose **SOAP Web Services** over HTTP(S). Calling a SOAP service reliably takes more than JAXB marshalling valid XML: the application must also manage the **message sender**, TCP/TLS connections, authentication, timeouts, SOAP Faults, retries, and observability.

Suppose an Order Service must send a `SubmitOrder` request to an ERP:

- Input: a validated business command with a unique business key.
- Payload: XML matching the partner's WSDL/XSD.
- Transport: HTTPS, possibly via a proxy, with HTTP Basic/Bearer or mTLS.
- SOAP layer: SOAP 1.1/1.2, SOAPAction, or WS-Security if required by the partner.
- Output: SOAP response, SOAP Fault, HTTP error, or timeout.
- Operations: bounded timeouts, connection pooling, retries/idempotency, metrics, and auditability.

This lesson belongs to the **SOAP and XML** chapter and focuses directly on **message senders, HTTP connections, authentication, and timeouts** in Spring Web Services on Spring Boot. After this lesson, you will be able to:

1. Explain how `WebServiceTemplate`, `WebServiceMessageSender`, message factories, marshallers, and fault resolvers differ.
2. Configure the default HTTP sender and connection-pooled senders according to your Spring-WS version.
3. Configure connect/read/connection-pool timeouts, total budgets, and concurrency policies.
4. Distinguish HTTP Basic/Bearer, mTLS, SOAP UsernameToken/Signature, and application authorization.
5. Use SOAPAction, SOAP Envelope version, Content-Type, and endpoint URIs accurately.
6. Classify connection, TLS, HTTP, and SOAP Fault errors; avoid retries that duplicate business side effects.
7. Write tests without calling the real ERP, and separately test transport/TLS/auth/timeouts.
8. Add observability at the HTTP/SOAP boundary and protect secrets and sensitive payloads.

> **Principle:** `WebServiceTemplate.marshalSendAndReceive(...)` returning without throwing an exception only indicates that the request/response completed as handled on the client; it does **not** automatically guarantee the remote transaction committed or that retries cannot create duplicates.

## 1. Separating the SOAP Payload from HTTP Transport

A SOAP call flows through these layers:

~~~mermaid
flowchart LR
    A["Order command"] --> B["SOAP gateway"]
    B --> C["JAXB Marshaller"]
    C --> D["SOAP message factory"]
    D --> E["WebServiceTemplate"]
    E --> F["WebServiceMessageSender"]
    F --> G["HTTP connection + TLS"]
    G --> H["ERP SOAP endpoint"]
    H --> I["SOAP response / Fault"]
    I --> J["Unmarshaller + outcome mapping"]
    J --> K["Business result"]
    B -.-> L["Outbox / retry / observability"]
~~~

| Layer | Representative API | What does it decide? |
| --- | --- | --- |
| XML mapping | `Jaxb2Marshaller` | DTO ↔ XML root, QName, namespace |
| SOAP message | `SoapMessage`, `SaajSoapMessageFactory` | SOAP Envelope, Body, Header, version |
| SOAP client orchestration | `WebServiceTemplate` | Send request, receive response, fault handling |
| HTTP transport | `WebServiceMessageSender` | Connections, HTTP headers, TLS, timeouts, proxy, pool |
| Application adapter | `ErpSoapGateway` | Business key, validation, error mapping, retry policy |
| Data/messaging | SQL outbox, broker consumer | Durable intent, acknowledgement, idempotency |

`RestClient` or `WebClient` can send XML over HTTP, but **they do not provide SOAP marshalling, SOAP message factories, SOAP Fault resolvers, or WS-Security out of the box**. When a partner uses WSDL/SOAP, `WebServiceTemplate` is the appropriate choice; HTTP transport can still leverage similar HTTP client libraries underneath.

### 1.1. What Is `WebServiceMessageSender`?

`WebServiceMessageSender` is Spring-WS's abstraction for sending and receiving a `WebServiceMessage` over a destination identified by a URI. For SOAP over HTTP, the sender creates the connection, writes the request (HTTP headers + SOAP Envelope), reads the response, and hands SOAP Fault resolution to upper layers.

A sender does not decide which data constitutes a valid order, does not manage SQL transactions, and does not provide business-level retry or idempotency on its own.

### 1.2. A SOAP Request on the Wire

~~~http
POST /soap/orders HTTP/1.1
Host: erp.example.org
Content-Type: text/xml; charset=utf-8
SOAPAction: "urn:SubmitOrder"
Authorization: Basic <redacted>

<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:o="urn:example:orders:v1">
  <soapenv:Header/>
  <soapenv:Body>
    <o:SubmitOrderRequest>
      <o:orderId>ORD-100</o:orderId>
    </o:SubmitOrderRequest>
  </soapenv:Body>
</soapenv:Envelope>
~~~

This is an **illustrative structural example, not a request to copy verbatim**, and `Authorization` is redacted. `SOAPAction`, namespace, and operation names must come from the WSDL. With SOAP 1.2, HTTP `Content-Type` is typically `application/soap+xml` and the action may appear as a Content-Type parameter; do not copy SOAP 1.1 rules blindly.

## 2. Dependencies and Spring Boot/Spring-WS Compatibility

### 2.1. Core Dependencies

Gradle Groovy DSL example for Spring Boot 3.x and Java 17+:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web-services'

    // Needed when using JAXB/Jaxb2Marshaller directly:
    implementation 'jakarta.xml.bind:jakarta.xml.bind-api'
    runtimeOnly 'org.glassfish.jaxb:jaxb-runtime'

    // Optional for metrics:
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.ws:spring-ws-test'
}
~~~

The Web Services starter pulls in Spring-WS infrastructure; JAXB dependencies may already be brought in transitively in a given project. Inspect the dependency tree and let the **Spring Boot BOM** manage compatible versions whenever possible.

Core classes:

~~~java
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.transport.WebServiceMessageSender;
import org.springframework.ws.transport.http.HttpUrlConnectionMessageSender;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.soap.client.core.SoapActionCallback;
~~~

### 2.2. Version Matters

| Platform line | Points to watch |
| --- | --- |
| Spring Boot 2 / Spring-WS 3 legacy | JAXB usually uses `javax.xml.bind`; Apache HttpClient 4 senders appear in older code |
| Spring Boot 3 / Spring-WS 4 | Java 17+, `jakarta.xml.bind` namespace; Apache HttpClient 5 senders available in supported releases |
| Spring Boot 4 / next-gen Spring-WS | Some auto-config packages, constructors, and transport APIs may change; check the exact version's Javadoc |
| JDK HTTP URLConnection | No external Apache client needed, suitable for simple cases; limited pool/transport controls |
| Apache HttpClient sender | Supports pooling, proxies, credentials, and fine-grained timeouts; match major HttpClient/Spring-WS versions |

The name `HttpComponentsMessageSender` in older articles is **not synonymous** with `HttpComponents5MessageSender` using Apache HttpClient 5. Never mix Apache `org.apache.http.*` (4.x) with `org.apache.hc.client5.*` (5.x). For version-sensitive APIs, verify exact method signatures against your project's resolved dependencies.

**Never choose a sender by library name alone:** determine whether the system needs proxies, mTLS, connection pooling, concurrency caps, streaming, compression, and which auth scheme applies.

## 3. Configuring `WebServiceTemplate` from Spring Boot

A SOAP client typically comprises:

- Endpoint URI.
- Message factory selecting SOAP 1.1/1.2.
- Marshaller/unmarshaller from JAXB-generated classes.
- HTTP sender with TLS/auth/timeouts.
- Fault resolver/interceptors if needed.
- Adapter mapping business data.

### 3.1. Externalized Configuration

~~~yaml
integrations:
  erp:
    uri: ${ERP_SOAP_URL:https://erp.example.org/soap/orders}
    connect-timeout: 3s
    read-timeout: 12s
    max-attempts: 3
~~~

`ERP_SOAP_URL` here is an illustrative endpoint. Production must supply URLs from environment configuration and never embed credentials in URLs like `https://user:pass@host` or log full URLs containing query tokens.

Bind configuration into a record (example on Boot 3/Java 17+):

~~~java
// ErpSoapProperties.java
import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "integrations.erp")
public record ErpSoapProperties(
        URI uri,
        Duration connectTimeout,
        Duration readTimeout,
        int maxAttempts) {
}
~~~

Register the properties using `@EnableConfigurationProperties(ErpSoapProperties.class)` or `@ConfigurationPropertiesScan`. In production, validate that the URI scheme is HTTPS, timeouts are positive with an upper bound, and the hostname is on an allowlist of permitted endpoints.

### 3.2. JAXB Marshaller for Payloads

Suppose `com.example.erp.generated` is the XJC-generated package from the WSDL/XSD containing `ObjectFactory`:

~~~java
// ErpSoapConfiguration.java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;

@Configuration(proxyBeanMethods = false)
public class ErpSoapConfiguration {

    @Bean
    Jaxb2Marshaller erpMarshaller() {
        Jaxb2Marshaller mapper = new Jaxb2Marshaller();
        mapper.setContextPath("com.example.erp.generated");
        mapper.setSupportDtd(false);
        mapper.setProcessExternalEntities(false);
        return mapper;
    }
}
~~~

This is a Jakarta JAXB example suited for modern Boot. If generated DTOs lack `ObjectFactory`/`jaxb.index`, use `setClassesToBeBound(...)` for the exact JAXB classes. Disabling DTDs and external entities is necessary, though you must still control input parsers and any XSD imports.

## 4. Simple Sender: `HttpUrlConnectionMessageSender`

`HttpUrlConnectionMessageSender` uses the JDK's `HttpURLConnection`. It is a straightforward option for SOAP workloads with moderate concurrency that do not require complex pooling, proxies, or credential scopes.

With Spring-WS versions **providing setters accepting `Duration`**, an illustrative configuration is:

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.ws.transport.WebServiceMessageSender;
import org.springframework.ws.transport.http.HttpUrlConnectionMessageSender;

@Bean
WebServiceMessageSender erpMessageSender(
        ErpSoapProperties props) {

    HttpUrlConnectionMessageSender sender =
            new HttpUrlConnectionMessageSender();

    sender.setConnectionTimeout(props.connectTimeout());
    sender.setReadTimeout(props.readTimeout());

    return sender;
}
~~~

**Check API version:** in some older Spring-WS releases, timeout setters take an `int` in milliseconds instead of `Duration`. On older lines, adjust types/units per Javadoc; never blindly cast a `Duration` or confuse seconds with milliseconds.

### 4.1. Wiring into `WebServiceTemplate`

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.transport.WebServiceMessageSender;

@Bean
WebServiceTemplate erpWebServiceTemplate(
        ErpSoapProperties props,
        Jaxb2Marshaller erpMarshaller,
        WebServiceMessageSender erpMessageSender) {

    WebServiceTemplate template = new WebServiceTemplate();
    template.setDefaultUri(props.uri().toString());
    template.setMarshaller(erpMarshaller);
    template.setUnmarshaller(erpMarshaller);
    template.setMessageSender(erpMessageSender);
    return template;
}
~~~

These `@Bean` methods belong inside a `@Configuration` class (such as `ErpSoapConfiguration`) with `ErpSoapProperties` enabled. Do not register two sender beans of the same type without `@Qualifier` or explicit injection rules.

### 4.2. URLConnection Timeouts

| Timeout | Meaning | What it does NOT guarantee |
| --- | --- | --- |
| Connect timeout | Bounds time to open the network connection (per HTTP stack/JDK) | That the entire SOAP call finishes in that time |
| Read timeout | Bounds time waiting to read response data | Total request deadline |
| DNS resolution | Hostname lookup prior to connecting | May not be strictly bounded by connect timeout |
| TLS handshake | Secure session setup, chain/hostname verification | Not bounded by an independent deadline in all senders |
| Client total deadline | Overall budget for the SOAP operation | Must be designed in application/transport per stack |

With `HttpUrlConnectionMessageSender`, do not assume a configurable connection pool like Apache HttpClient. JDK keep-alive can reuse sockets, but pending acquisition bounds and connection counts are controlled differently from a dedicated pool.

### 4.3. When Not to Choose This Sender?

If your workload has hundreds of concurrent SOAP calls, multiple proxies, credential scopes, or requires pool metrics, an Apache HttpClient sender generally provides better control. However, adding a pool does not fix long SQL transactions or low downstream throughput; measure actual behavior.

## 5. Senders Using Apache HttpClient and Connection Pooling

Spring-WS provides Apache HttpClient senders by version:

- Legacy `HttpComponentsMessageSender` tied to Apache HttpClient 4 in older projects.
- `HttpComponents5MessageSender` using the Apache HttpClient 5 API in supported Spring-WS releases.
- Exact class/package names, constructors, and HTTP client builders **must be verified against your actual dependency graph**.

With Apache HttpClient 5, three timeouts are commonly distinguished:

| Concept | Failure example | Controlled by |
| --- | --- | --- |
| **Pool acquisition / connection request timeout** | No free connections; caller waited too long for a lease | `RequestConfig` / pool client |
| **Connect timeout** | Unable to open socket to host/proxy | `ConnectionConfig` / transport client per version |
| **Response/read timeout** | Endpoint slow to return SOAP response or socket stalls | `RequestConfig`/`SocketConfig` per version |
| **TLS handshake timeout** | Slow handshake/certificate exchange | TLS strategy/socket policy per client |
| **Total budget** | Multiple stages or retries exceed business window | Deadline in adapter/caller |

Example wiring **at the sender layer only**, assuming the application has already built and configured a pooled Apache 5 `HttpClient`:

~~~java
import org.apache.hc.client5.http.classic.HttpClient;
import org.springframework.context.annotation.Bean;
import org.springframework.ws.transport.WebServiceMessageSender;
import org.springframework.ws.transport.http.HttpComponents5MessageSender;

@Bean
WebServiceMessageSender pooledErpSender(
        HttpClient erpApacheHttpClient) {
    return new HttpComponents5MessageSender(
            erpApacheHttpClient);
}
~~~

This snippet depends on a Spring-WS version containing `HttpComponents5MessageSender` and HttpClient 5; it **does not automatically configure pooling, TLS, Basic auth, or timeouts**. Those belong inside the `erpApacheHttpClient` built by your application. Do not register this sender alongside `erpMessageSender` from section 4 if the template only needs one sender, unless using explicit `@Qualifier`.

### 5.1. Pool Configuration Principles

Suppose an Inventory API has fixed capacity and you choose:

~~~text
Max connections total       : 80
Max connections per route   : 20
Max SOAP calls per worker   : 8
Pool acquisition timeout   : 1 second
Connect timeout            : 2 seconds
Response timeout           : 10 seconds
~~~

Values are illustrative; factor in replica counts, QPS, response times, downstream counts, and ERP quotas. With 10 pods and `maxPerRoute=20`, total potential connections to the ERP can reach 200, not 20.

A pool should:

- Cap max total and max per route.
- Enforce a connection request timeout so callers do not wait indefinitely under saturation.
- Evict idle/stale connections and manage connection TTL per HTTP client settings.
- Preserve hostname verification, truststore, and client identity when reusing TLS connections.
- Track leased, pending, available, and timeout errors from the pool/transport.
- Close resources on shutdown; when creating a custom `CloseableHttpClient`, manage lifecycle shutdown properly.

**Never share a single `HttpClient` configured with ERP credentials across Payment or HR downstreams.** Isolate client/credential scopes by trust boundary.

### 5.2. HTTP/1.1 Keep-Alive Does Not Mean a SOAP Session

HTTP keep-alive can reuse sockets across multiple SOAP requests, reducing TCP/TLS handshake overhead. However:

- Each SOAP request still needs business-level identity/idempotency.
- Connection reuse does not mean the server maintains a business session.
- Certificate rotation may not affect already-open TLS connections; verify connection lifecycle.
- Stale connection errors in a pool can complicate retries because a request may have been partially sent.

Never use a TLS session ID or connection object identity as a SOAP deduplication key.

## 6. SOAP Message Factory, SOAP Version, and SOAPAction

`WebServiceTemplate` operates on `WebServiceMessage`, while `SoapMessageFactory` creates SOAP Envelopes. If a partner expects SOAP 1.2 but the client sends SOAP 1.1, the server may return HTTP 415, a SOAP `VersionMismatch` Fault, or another contract error.

### 6.1. SOAP 1.1 and SOAP 1.2

| Property | SOAP 1.1 | SOAP 1.2 |
| --- | --- | --- |
| Envelope namespace | `http://schemas.xmlsoap.org/soap/envelope/` | `http://www.w3.org/2003/05/soap-envelope` |
| Common HTTP Content-Type | `text/xml` | `application/soap+xml` |
| SOAPAction | HTTP header typically present per binding | Action may reside in Content-Type parameter/binding |
| Fault structure | `faultcode`, `faultstring`, `detail` | `Code`, `Reason`, `Detail` |
| Source of truth | WSDL/binding and partner contract | WSDL/binding and partner contract |

In Spring-WS, you can configure an explicit message factory; for example, for SOAP 1.1:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.ws.soap.SoapVersion;
import org.springframework.ws.soap.saaj.SaajSoapMessageFactory;

@Bean
SaajSoapMessageFactory erpSoapMessageFactory() {
    SaajSoapMessageFactory factory =
            new SaajSoapMessageFactory();
    factory.setSoapVersion(SoapVersion.SOAP_11);
    return factory;
}
~~~

For SOAP 1.2, select `SoapVersion.SOAP_12` if supported by your SOAP message factory and Jakarta SOAP implementation. Some integration providers require very specific Content-Type/action formatting; never switch SOAP versions blindly to "fix" an HTTP 500 without reading the WSDL.

Pass the message factory into the template via the constructor or setter supported by your Spring-WS version:

~~~java
WebServiceTemplate template =
        new WebServiceTemplate(erpSoapMessageFactory);

template.setMarshaller(erpMarshaller);
template.setUnmarshaller(erpMarshaller);
template.setMessageSender(erpMessageSender);
template.setDefaultUri(props.uri().toString());
~~~

This configuration is an **alternative to how the template was created in section 4.1**, not a requirement to create a second template.

### 6.2. SOAPAction Is Not the Endpoint URL

Example calling `SubmitOrder`:

~~~java
import org.springframework.ws.soap.client.core.SoapActionCallback;

Object response =
        erpWebServiceTemplate.marshalSendAndReceive(
                request,
                new SoapActionCallback("urn:SubmitOrder"));
~~~

- `https://erp.example.org/soap/orders` is the transport URL.
- `urn:SubmitOrder` is the SOAPAction **specified by the WSDL**, not a network URL.
- `SubmitOrderRequest` is the XML root element defined by the XSD.
- These values can all differ and cannot be guessed universally across partners.

Do not set SOAPAction to the Java method name if the WSDL specifies another action. For SOAP 1.2 or other bindings, verify that Spring-WS emits the action according to the active standard.

## 7. Authentication: HTTP Basic, Bearer, mTLS, and WS-Security

A SOAP system may enforce **multiple authentication layers simultaneously**. When calls fail with 401/403 or security-related SOAP Faults, identify which layer rejected the request.

~~~mermaid
flowchart TD
    A["SOAP client"] --> B["TLS/mTLS handshake"]
    B --> C["HTTP Authorization"]
    C --> D["SOAP Envelope Header"]
    D --> E["Application authorization"]
    E --> F["SOAP business handler"]
~~~

### 7.1. HTTP Basic Authentication

HTTP Basic places `Authorization: Basic base64(username:password)` on the HTTP request. Base64 is **not encryption**; use it only over HTTPS and protect credentials.

~~~http
POST /soap/orders HTTP/1.1
Host: erp.example.org
Authorization: Basic <redacted>
Content-Type: text/xml; charset=utf-8
SOAPAction: "urn:SubmitOrder"
~~~

Key points:

- Configure credentials on the **HTTP client/message sender**, not inside the JAXB request DTO.
- Use a secret manager or environment variables; never hardcode passwords in `application.yml`.
- Determine whether the provider uses challenge/response or requires preemptive Basic auth; challenge/response adds a round trip and interacts with HTTP client pooling.
- Never log `Authorization` headers, wire requests, or raw credentials.
- Rotating credentials may require restarting or reconfiguring the client/pool depending on the implementation.

**A SOAP `<UsernameToken>` header is not equivalent to HTTP Basic.** If the partner requires WS-Security, sending HTTP Basic—even with the right username and password—can still fail.

### 7.2. Bearer / OAuth2 Client Credentials

Some modern SOAP endpoints use OAuth2 at the HTTP layer:

~~~http
Authorization: Bearer <redacted-access-token>
~~~

Typical service-to-service flow:

1. The client is provisioned with client credentials or a workload identity.
2. A token client obtains an access token from the authorization server.
3. The token is attached to HTTP requests sent to the SOAP endpoint.
4. The partner validates signature/introspection, `aud`, `scope`, expiration, and partner policy.
5. Tokens are cached/refreshed in a controlled way rather than minted per item unnecessarily.

Tokens must be attached at the **HTTP transport layer**, for example via a request-level interceptor capable of setting HTTP headers on the sender or custom HTTP client. Spring-WS `ClientInterceptor` operates at the SOAP message level; do not assume every SOAP interceptor can cleanly manage HTTP `Authorization` headers.

### 7.3. mTLS (Mutual TLS)

With mTLS:

- The SOAP client verifies the **server certificate chain + hostname SAN**.
- The HTTP sender presents the **client certificate/private key** when requested by the server.
- The server verifies the client certificate against its CA/usage/policy.
- The application may authorize requests based on certificate identity and tokens.

This occurs during the **TLS handshake**, not inside a SOAP element. Spring Boot's `spring.ssl.bundle.*` helps manage key/trust material, but **does not automatically attach every SSL bundle to `WebServiceTemplate`**. Configure the **message sender/underlying HTTP client** to use the corresponding SSL context/bundle.

~~~text
SOAP gateway
    |
    +-- WebServiceTemplate
         |
         +-- WebServiceMessageSender
              |
              +-- HTTP client TLS context
                   +-- KeyManager: client private key + certificate chain
                   +-- TrustManager: approved server CA(s)
                   +-- Hostname verification: enabled
~~~

Never fix `PKIX path building failed` with a trust-all manager or by disabling hostname verification. Supply the proper CA chain/trust anchor, verify SAN/expiry/EKU, and test negative handshakes.

### 7.4. WS-Security Lives in the SOAP Header

Common mechanisms:

| WS-Security mechanism | Role | Notes |
| --- | --- | --- |
| UsernameToken | Identity/credentials in SOAP header | Supports PasswordText/PasswordDigest per contract; needs TLS and replay protection |
| Timestamp | Bounds message validity window | Requires clock synchronization and clock-skew handling |
| XML Signature | Signs selected XML parts | Must verify signed parts/keys and canonicalization |
| XML Encryption | Encrypts selected XML content | Distinct from hop-to-hop TLS |
| SecurityTokenReference | References certificates or tokens | Depends on WSDL/WS-Policy profile |

Spring Web Services supports a **WSS4J security interceptor** in the appropriate security module. Conceptual configuration (verify API and action strings against your Spring-WS/WSS4J version):

~~~java
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;

// Illustrative configuration inside a @Bean method with
// username/password injected from secrets/config:
Wss4jSecurityInterceptor security =
        new Wss4jSecurityInterceptor();

security.setSecurementActions("UsernameToken Timestamp");
security.setSecurementUsername(serviceUsername);
security.setSecurementPassword(servicePassword);
~~~

This is a **snippet**, not a complete security configuration: `serviceUsername`/`servicePassword` must come from secrets, and password type, nonce/timestamp/signature/crypto settings must comply with the partner's WS-SecurityPolicy. Attach the interceptor to `WebServiceTemplate`, e.g. `template.setInterceptors(...)`, per contract.

For digital signatures and WS-Security headers, never concatenate XML strings manually hoping to match a signature; use standard libraries and verify signed elements, certificate trust, and replay policies.

### 7.5. Authorization Remains a Separate Layer

A client with a valid certificate or authenticated token may still **not be authorized to submit an order for another tenant**. The server must check resource ownership, operation scope, partner identity, and environment. On the client side, do not store raw bearer tokens or credentials inside domain messages persisted to a SQL outbox or broker.

## 8. Proxies, Firewalls, and Connection Routing

In enterprise networks, outbound HTTPS often passes through an egress proxy:

~~~text
Order Service → Egress proxy → Firewall → ERP SOAP endpoint
~~~

Proxies affect:

- DNS/hostname resolution, routing, and CONNECT tunnels.
- Proxy authentication (HTTP 407), distinct from HTTP 401 from the ERP.
- TLS termination/re-encryption per corporate policy.
- Connection pooling per route/proxy.
- Per-hop timeouts.
- Observability and identity propagation.

Never assume a proxy only forwards raw bytes. If a proxy performs TLS termination, determine **whether the client verifies the proxy's certificate or the ERP's**, which hop handles mTLS, and whether the app still presents the identity expected by the partner.

### 8.1. Endpoint Allowlists and SSRF

Never let users pass arbitrary URLs for `WebServiceTemplate` to invoke. If an API lets callers pick `targetUrl`, an attacker can point the server at metadata services or internal endpoints.

Prefer configured URLs per approved partner; when dynamic endpoints are truly necessary:

- Allow only `https` and explicitly permitted hostnames/ports.
- Restrict redirects; never trust redirects to private IPs or unknown hosts.
- Guard against DNS rebinding, proxy bypasses, and unintended network egress.
- Never send ERP credentials to non-partner domains.
- Log endpoints by logical name rather than sensitive credentials or URLs.

## 9. Timeouts: Connect, Read, Pool, and Overall Deadlines

Timeouts are an operational contract, not just a few properties.

~~~mermaid
sequenceDiagram
    participant A as SOAP Gateway
    participant P as HTTP pool
    participant N as DNS/TCP/TLS
    participant E as ERP Server
    A->>P: Borrow connection (pool acquisition timeout)
    P-->>A: Connection/slot
    A->>N: Resolve + connect + TLS handshake
    N-->>A: Connected/verified
    A->>E: POST SOAP payload
    E-->>A: SOAP response
    Note over A,E: Response/read timeout, operation deadline
~~~

### 9.1. Types of Timeouts

| Timeout | When it applies | Common mistake |
| --- | --- | --- |
| **Connection request / lease timeout** | Waiting for a connection from the client pool | Confusing it with connect timeout to the server |
| **TCP connect timeout** | Opening a socket/connection to the proxy/server | Thinking it caps the entire request |
| **TLS handshake timeout** | Waiting for authentication/cipher negotiation | Setting only read timeout without testing real behavior |
| **Socket/response/read timeout** | Waiting for data from the server | Treating it as an absolute deadline for the full body |
| **Write timeout** | Pushing a large request body over the network | Ignoring it because test requests are small |
| **Total operation deadline** | Entire SOAP operation across all stages | Forgetting DNS, pool wait, or retries |
| **Retry budget** | Total attempts and backoff | Stacking retries across multiple layers |
| **Business SLA** | From receiving the event to ERP confirmation | Treating a TCP timeout as the final SLA |

Example timeout policy for a command with a 30s SLA:

~~~text
Business deadline         : 30 s
Pool acquisition timeout  : 1 s
TCP connect timeout       : 3 s
Read/response timeout     : 8 s
Backoff                   : with jitter
Max attempts              : at most 2 or 3 within remaining budget
~~~

Numbers are illustrative; real total duration can be higher since each attempt has multiple stages and backoff. Never take "3 attempts × 8s = 24s" as a hard ceiling because pool wait, DNS, TLS, connect, and scheduling add time.

### 9.2. Distinguish Two Kinds of Read Timeout

A **socket inactivity timeout** typically bounds gaps with no data arriving on the socket; it does not necessarily cap total duration for a trickle-fed slow response. A **response deadline** or application-level cancellation can bound the entire operation.

For large SOAP responses, also cap body size, parse depth, and XML element count; a huge response can burn CPU/RAM after socket reads finish.

### 9.3. Do Not Configure Timeouts on `WebServiceTemplate` When the Sender Enforces Them

`WebServiceTemplate` is the SOAP orchestration layer, whereas HTTP timeouts must be configured on the **HTTP sender/client/connection manager** used by the template.

If you swap `HttpUrlConnectionMessageSender` for `HttpComponents5MessageSender`, the old timeout settings do not carry over automatically. Remap your policy to Apache HttpClient 5's `ConnectionConfig`, `RequestConfig`, TLS strategy, or version-equivalent configuration classes.

### 9.4. Timeout Does Not Mean No Side Effects

~~~mermaid
sequenceDiagram
    participant O as Order Service
    participant E as ERP
    participant D as ERP Database
    O->>E: SubmitOrder ORD-100
    E->>D: COMMIT order
    Note over O,E: Response lost due to read timeout
    O->>O: Receives timeout (outcome unknown)
    O->>E: Retry ORD-100
    E->>D: May insert duplicate if not deduplicated
~~~

In this situation, retrying the same request can create **two orders** if the ERP lacks idempotency or lookup support. **A timeout is missing information about the outcome**, not proof that the request never reached the partner.

## 10. Mapping Responses, HTTP Statuses, and SOAP Faults

A SOAP client must separate **transport outcome** from **business outcome**.

| Observation | Example | Reaction |
| --- | --- | --- |
| HTTP success + valid SOAP response | `SubmitOrderResponse accepted=true` | Map success outcome |
| HTTP success + business rejection in XML | `accepted=false` | Business outcome, not a network failure |
| SOAP Fault (Client/Sender) | Invalid orderId | Do not retry invalid data |
| SOAP Fault (Server/Receiver) | ERP internal error | May retry per policy and idempotency |
| HTTP 401/403 | Wrong credentials/token/policy | Fix auth; avoid rapid retries |
| HTTP 407 | Proxy authentication required | Check proxy credentials |
| HTTP 404/415 | Wrong endpoint or SOAP content type | Check URL, SOAP version, WSDL |
| HTTP 429/503 | Rate limit / unavailable | Bounded backoff per contract |
| `SSLHandshakeException` | Untrusted CA/SAN/client cert | Fix TLS materials |
| `SocketTimeoutException` | Connect/read timeout | Distinguish phase and side-effect state |
| `XmlMappingException` | XML mismatches JAXB/XSD | Fix contract; do not retry blindly |

### 10.1. Key Spring-WS Exceptions

Spring-WS exposes exceptions at different layers, such as:

- `WebServiceIOException`: I/O error during transport invocation.
- `WebServiceTransportException`: transport returned an error status not handled as a valid SOAP Fault.
- `SoapFaultClientException`: SOAP Fault converted to an exception by the resolver (under default policy).
- `XmlMappingException` and OXM subtypes: marshalling/unmarshalling errors.
- `WebServiceClientException`: Spring-WS client exception hierarchy.

Exact exception classes can depend on the sender, resolver, and Spring-WS version. When handling errors, never just `catch (Exception)` and label everything a "network timeout." Preserve the **cause chain** responsibly to classify root causes without logging sensitive data.

### 10.2. SOAP Faults Often Arrive with HTTP 500

Under SOAP 1.1, servers commonly return HTTP 500 with a valid SOAP Fault:

~~~http
HTTP/1.1 500 Internal Server Error
Content-Type: text/xml; charset=utf-8

<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <soap:Fault>
      <faultcode>soap:Client</faultcode>
      <faultstring>Order amount invalid</faultstring>
    </soap:Fault>
  </soap:Body>
</soap:Envelope>
~~~

This is a Fault example, **not an empty HTTP 500**. `WebServiceTemplate` includes SOAP Fault/connection error detection; do not disable HTTP status or fault checks casually just to satisfy a non-standard partner test.

SOAP 1.2 uses a different Fault layout; check the WSDL and specification, and test against real response fixtures.

### 10.3. An Explicit Result Type

Distinguish outcomes explicitly:

~~~java
public sealed interface ErpSubmitOutcome
        permits ErpSubmitOutcome.Accepted,
                ErpSubmitOutcome.Rejected,
                ErpSubmitOutcome.Unknown {

    record Accepted(String reference)
            implements ErpSubmitOutcome {}

    record Rejected(String businessCode)
            implements ErpSubmitOutcome {}

    record Unknown(String reasonCode)
            implements ErpSubmitOutcome {}
}
~~~

- `Accepted`: received valid business confirmation.
- `Rejected`: partner explicitly declined due to business rules.
- `Unknown`: uncertain whether the partner committed, e.g., timeout after sending.

Never turn every `Unknown` into `Rejected`. For payments, bookings, or order creation, look up the result or rely on the partner's idempotency contract.

## 11. Retries, Circuit Breakers, and Idempotency

Retries help recover from transient failures, but they can amplify load and duplicate side effects.

### 11.1. Minimum Prerequisites

Before retrying a side-effecting SOAP command, verify:

1. **Is the operation idempotent?** `GET status` is safer to retry than `SubmitPayment`.
2. **Is there a business idempotency key?** For example, `operationId`/`orderId` stored uniquely by the partner.
3. **Is there a status lookup API?** Needed when responses are lost.
4. **Is the error retryable?** Transient 503/timeout vs. 401/validation fault.
5. **Is there budget left in the total deadline?** Do not attempt after the SLA expires.
6. **Can multiple attempts run concurrently?** Prevent retry storms.
7. **Does a broker consumer redeliver independently of HTTP client retries?**

### 11.2. Example Policy

| Error | Auto-retry | Notes |
| --- | --- | --- |
| Wrong QName/XSD | No | Fix payload/version |
| Wrong HTTP Basic credentials | No | Rotate/fix secret |
| Untrusted TLS certificate | No | Fix CA/truststore |
| Business-rejected SOAP Fault | No | Business outcome |
| Transient Server/Receiver Fault | Maybe | Depends on operation contract and idempotency |
| HTTP 503/429 | Bounded | Backoff/jitter; respect `Retry-After` if applicable |
| Connection refused before sending | Maybe | Usually no side effect created yet |
| Read timeout after write | Only if safe | Outcome may already be committed |
| Connection pool exhausted | Shed/throttle load first | Immediate retries worsen overload |

Place retry orchestration at **one explicit layer**, such as the integration adapter or message consumer. If the HTTP client, Resilience4j, Spring Retry, and the broker each retry 3 times, a single message can trigger 27 unintended attempts.

### 11.3. Circuit Breakers Differ from Timeouts

A circuit breaker reduces calls to a failing downstream and allows controlled recovery. It **does not** replace timeouts: without network timeouts, requests can hang indefinitely.

Keep responsibilities separate:

- Timeouts cap wait times for a phase/operation.
- Bulkheads/concurrency caps limit simultaneous in-flight requests.
- Circuit breakers temporarily trip calls when downstream error rates spike.
- Retries repeat safe transient errors.
- Outbox/brokers ensure integration intent survives process crashes.
- Idempotency/reconciliation protect business correctness under duplicates or unknown outcomes.

## 12. Transactions with SQL, Outbox, and SOAP

An easy-to-spot anti-pattern:

~~~java
@Transactional
public void confirmOrder(String orderId) {
    orderRepository.markConfirmed(orderId);
    erpWebServiceTemplate.marshalSendAndReceive(
            buildSubmitRequest(orderId));
}
~~~

If the ERP processes the request and the SQL transaction then rolls back, the two systems have contradictory state. Conversely, if SQL commits and SOAP times out, the caller does not know the outcome.

A more durable architecture:

~~~mermaid
flowchart LR
    A["Order command"] --> B["SQL transaction"]
    B --> C["Update order state"]
    B --> D["Insert SOAP outbox intent"]
    D --> E["Outbox relay / broker"]
    E --> F["ERP SOAP gateway"]
    F --> G["ERP"]
    F -.-> H["Retry + status lookup"]
    H -.-> I["Persist outcome / DLQ"]
~~~

In the same SQL transaction, persist the order and the intent to call the ERP. A worker processes the outbox after commit, reusing a stable `operationId` across all attempts. On timeout, transition to `UNKNOWN` and reconcile before creating any new side effect.

**Note:** mTLS, HTTP Basic, JAXB, `WebServiceTemplate`, or the SOAP protocol **do not create a distributed transaction** with the database. Even on HTTP 200, read the response contract to verify the ERP actually recorded the transaction.

### 12.1. Exactly-Once Does Not Come from SOAP Alone

A business operation can be re-sent when:

- The broker redelivers.
- The client retries after a timeout.
- A worker crashes between "ERP accepted" and "outbox marked success."
- A scheduled reconciliation job reruns.
- A caller sends the same request body with a newly generated `operationId`.

Deduplication keys must be **durable business identities** (such as a partner operation ID or a unique business command ID), never a TLS session ID, HTTP connection ID, or request `traceId`.

If the partner does not support idempotency keys, you need a status lookup API or a manual reconciliation workflow—especially for payments, invoicing, and bookings.

## 13. Data Security and Logs

SOAP XML often contains more sensitive data than simple payloads:

- Buyers, addresses, ID numbers, transaction details.
- HTTP Authorization/Bearer tokens.
- SOAP Headers carrying WS-Security UsernameTokens/Signatures.
- Certificate details or transport metadata.
- Business identifiers that can trace individuals.

**Never enable full request/response wire logging in production** just for debugging. When investigation is needed, configure redaction and retention, and enable it temporarily with access controls.

Required practices:

1. HTTPS/TLS with proper hostname verification and CA trust.
2. Credential storage via vault/secret manager; never commit to repositories.
3. Isolate client identities and truststores across environments and partners.
4. Cap request/response sizes, XML depth, and block XXE.
5. Validate XSDs and SOAP/WS-Security signatures when required by the contract.
6. Never write raw XML, tokens, or PII into metric tags.
7. Restrict outbound endpoints with allowlists to prevent SSRF.
8. Authenticate callbacks/webhooks if the ERP sends asynchronous notifications.
9. Use TLS and WS-Security according to your threat model; hop-to-hop TLS does not replace XML Signatures when non-repudiation or message-level security is needed.

### 13.1. mTLS and Certificate Rotation

When a sender uses an `SSLContext` with a client certificate, certificate rotation requires checking:

- Has the new key/trust material been loaded into the HTTP client?
- Does the connection pool still hold old TLS sessions or certificates?
- Does the downstream already trust the new issuing CA?
- Must the `HttpClient`/`WebServiceMessageSender` be rebuilt or the pod restarted?
- Are positive and negative tests run after rotation?

Do not assume changing a file on disk under `spring.ssl.bundle` automatically updates every open sender or connection. Some Boot integrations support reload, while custom Apache clients/`SSLContext` instances may not.

## 14. Testing SOAP Payloads with `MockWebServiceServer`

Spring-WS's `MockWebServiceServer` lets you test SOAP payloads and responses **without opening real HTTP sockets**.

Assumptions:

- `com.example.erp.generated` contains JAXB root classes for `SubmitOrderRequest` and `SubmitOrderResponse`.
- `Jaxb2Marshaller` can marshal/unmarshal both roots.
- `spring-ws-test` is on the test classpath.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.test.client.MockWebServiceServer;
import org.springframework.xml.transform.StringSource;

import static org.springframework.ws.test.client.RequestMatchers.payload;
import static org.springframework.ws.test.client.ResponseCreators.withPayload;

class ErpSoapGatewayTest {

    @Test
    void sendsSoapPayloadAndReadsResponse() throws Exception {
        Jaxb2Marshaller mapper = new Jaxb2Marshaller();
        mapper.setContextPath("com.example.erp.generated");
        mapper.afterPropertiesSet();

        WebServiceTemplate template =
                new WebServiceTemplate();
        template.setMarshaller(mapper);
        template.setUnmarshaller(mapper);
        template.setDefaultUri(
                "https://erp.test/soap/orders");

        MockWebServiceServer server =
                MockWebServiceServer.createServer(template);

        String requestXml =
                "<e:SubmitOrderRequest "
                + "xmlns:e=\"urn:example:orders:v1\">"
                + "<e:orderId>ORD-100</e:orderId>"
                + "</e:SubmitOrderRequest>";

        String responseXml =
                "<e:SubmitOrderResponse "
                + "xmlns:e=\"urn:example:orders:v1\">"
                + "<e:accepted>true</e:accepted>"
                + "<e:reference>ERP-55</e:reference>"
                + "</e:SubmitOrderResponse>";

        server.expect(payload(new StringSource(requestXml)))
                .andRespond(
                        withPayload(
                                new StringSource(responseXml)));

        Object result =
                template.marshalSendAndReceive(
                        new SubmitOrderRequest("ORD-100"));

        org.junit.jupiter.api.Assertions.assertNotNull(result);
        server.verify();
    }
}
~~~

This is a **test skeleton depending on real generated DTOs**. `new SubmitOrderRequest("ORD-100")` only compiles if the generated class has that constructor; XJC typically generates a no-arg constructor and setters, so construct DTOs per your actual generated code. The example demonstrates matchers and response handling, not a standalone runnable class.

**Key limitation:** `MockWebServiceServer` replaces the connection layer to mock transport, so it **does not prove** that the HTTP sender correctly configures Basic/Bearer auth, TLS/mTLS, proxies, pools, or read timeouts. Separate integration tests are required.

## 15. Testing HTTP Transport, Auth, and Timeouts

### 15.1. Using a SOAP HTTP Stub or Local Server

Use WireMock, MockWebServer, or a test HTTP server capable of returning real SOAP Envelopes. Steps:

1. Start the stub on a dynamic port.
2. Point `integrations.erp.uri` to the test server, never to production.
3. Assert HTTP method POST, Content-Type, SOAPAction, and HTTP Authorization policy.
4. Stub valid SOAP 1.1/1.2 responses, HTTP 500 SOAP Faults, 401, 503, and 415.
5. Simulate connect/read timeouts at the transport level supported by the test server.
6. Verify retry budgets, error classification, and that secrets are never logged.
7. Shut down the test server and HTTP client pool after the test.

**Never test authentication by placing real production credentials inside the test suite.**

### 15.2. mTLS Tests Must Use a Real TLS Handshake

Mocking SOAP payloads cannot verify certificates. Use a TLS-enabled server with test certificates, a trust chain, and required client authentication:

| Test case | Expectation |
| --- | --- |
| Valid server cert + trusted client cert | Handshake passes |
| Client without certificate | Handshake rejected when server requires mTLS |
| Untrusted CA | Client or server rejects the chain |
| Hostname absent from SAN | Client rejects |
| Expired client cert | Handshake rejected |
| Server requires WS-Security in addition to mTLS | Handshake passes, but SOAP security validation fails if header is missing |

When TLS terminates at a proxy or service mesh, test each TLS hop separately; the JVM may not see the original caller's client certificate directly.

### 15.3. Testing Connection Pool Saturation

A load/integration test can:

- Set a low `maxPerRoute` and increase concurrency.
- Measure connection acquisition wait times.
- Enable bounded timeouts so requests do not wait forever.
- Verify rejected/timed-out requests are classified accurately.
- Verify retries do not amplify traffic past the budget.
- Verify connections are returned to the pool on SOAP Faults or XML parse errors.

Never run saturation tests against a live ERP without explicit permission and load caps.

### 15.4. Testing Unknown Outcomes and Idempotency

An essential test:

~~~text
Given: ERP stub has recorded operationId=ORDER-100
And:   ERP intentionally drops/holds response
When:  Client receives read timeout
Then:  Adapter records UNKNOWN
And:   Client does not blindly create a new operationId
When:  Worker retries or reconciles
Then:  One business operation is recorded according to contract
~~~

If the partner has no idempotency API, test the `UNKNOWN → manual reconciliation` or status-lookup path instead. Never treat "one HTTP call" as proof of exactly-once delivery.

## 16. Observability and Signals to Monitor

Measure at two levels: transport and business.

| Metric/Observation | Meaning |
| --- | --- |
| `integration.soap.request.duration` | Synchronous SOAP client call latency |
| `integration.soap.request.count` | Attempt count |
| `integration.soap.fault.count` | SOAP Faults categorized by fault code |
| `integration.soap.transport.error` | TLS, timeout, connect errors |
| HTTP connection pool leased/pending | Connection contention |
| Retry attempts and next retry age | Recovery progress |
| Outbox pending / oldest age | Backlog of ERP call intents |
| Business confirmation lag | Time from command commit to ERP confirmation |
| Reconciliation pending/failed | Unknown outcomes needing attention |

Micrometer `Observation` can wrap a call:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.ws.client.core.WebServiceTemplate;

public Object submitObserved(
        WebServiceTemplate template,
        ObservationRegistry registry,
        Object request) {

    return Observation.createNotStarted(
                    "integration.soap.submit", registry)
            .lowCardinalityKeyValue("partner", "erp")
            .lowCardinalityKeyValue("operation", "submitOrder")
            .observe(() ->
                    template.marshalSendAndReceive(request));
}
~~~

Observation measures **synchronous duration from call entry to return/exception**; it does not confirm business commit inside the ERP. If the project has not configured meter/tracing handlers on `ObservationRegistry`, timers and spans will not automatically export to backends.

Tags must have bounded cardinality:

~~~text
partner   = erp
operation = submitOrder
result    = success | soap_fault | transport_error
~~~

Never include `orderId`, `operationId`, XML payloads, emails, access tokens, certificate serials, or raw URLs with query strings in metric labels. Put IDs needed for audit/correlation in protected logs/audit stores with retention and redaction policies.

### 16.1. Correlation Across SOAP/Headers

A stable `operationId` can be placed in the **business payload or SOAP header per WSDL/WS-Policy** and stored in the outbox. It enables partner lookup and reconciliation.

Distinguish:

- `traceId`: links observability for **a single attempt**; may change across retries.
- `operationId`: identifies the **business intent**; must stay stable across retries.
- `SOAPAction`: selects the operation per binding; not a correlation ID.
- WS-Addressing `Message-ID` (if used): protocol metadata; does not create idempotency in the ERP automatically.

### 16.2. Boundary-Focused Dashboards

A useful dashboard includes:

- Inbound business command throughput and errors.
- Outbox age and retry backlog.
- SOAP transport latency p95/p99, connect/read/pool timeouts.
- HTTP 401/403/429/503 rates and SOAP Fault code rates.
- TLS certificate expiry and handshake failures per downstream.
- ERP business accept/reject/unknown counts.
- Deployment, credential, and certificate rotation timelines.

A spike in `SOAP Fault Sender` right after a deployment points to a mapping/WSDL change; rising `connect timeout` alongside DNS errors points to network/endpoint issues; rising `pool pending` points to connection limits or a slow downstream. Never lump all signals together as "SOAP is flaky."

## 17. Error Diagnostic Runbook

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `UnknownHostException` | Wrong DNS/endpoint or unresolvable host | Check DNS, config, and egress |
| `ConnectException: Connection refused` | Wrong port, service down, firewall/proxy | Check route and listening endpoint |
| `Connect timed out` | Network cannot open connection in time | Check connect timeout, routing, proxy |
| `Read timed out` | Slow ERP, hung response, network stall | Check SLA, server logs, treat outcome as unknown |
| Pool acquire timeout | No idle connections or excess concurrency | Inspect leased/pending, pool sizing, bulkheads |
| `PKIX path building failed` | Truststore missing CA/intermediate cert | Install proper chain; never trust-all |
| `No subject alternative DNS name matching` | Hostname mismatches cert SAN | Fix URL/cert SAN; never disable hostname verification |
| TLS client cert rejected | Wrong client key/cert/CA/EKU/policy | Check mTLS config |
| HTTP 401 | Wrong Basic/Bearer credentials or token | Check secrets, audience/scope |
| HTTP 407 | Proxy requires authentication | Configure proxy credentials properly |
| HTTP 403 | Authenticated but unauthorized | Check ERP/gateway authorization policy |
| HTTP 415 | SOAP 1.1/1.2 Content-Type mismatch | Check message factory and WSDL |
| HTTP 500 + SOAP Fault | SOAP protocol/business/service error | Classify fault by code/detail |
| HTTP 500 + HTML body | Proxy/app server error, not SOAP | Inspect response and content type |
| JAXB unexpected element | Root QName/schema mismatch | Regenerate/validate XSD |
| Error after HTTP library upgrade | Apache HttpClient 4/5 API mismatch | Check dependencies and sender class |
| Credentials leaked in logs | Unredacted wire logging or exception messages | Disable/restrict logging |
| Duplicate orders after timeout | Missing idempotency/reconciliation | Use stable operationId/outbox |

### 17.1. Ordered Diagnostic Steps

1. Verify URI, DNS, port, and proxy without logging secrets.
2. Check TLS certificate chain, hostname SAN, and mTLS client identity.
3. Check HTTP credentials/headers (redacted metadata only).
4. Verify SOAP version, SOAPAction, and WSDL/XSD alignment.
5. Inspect connect, pool acquisition, and read timeouts separately.
6. Read any SOAP Fault; distinguish it from HTTP proxy errors.
7. Check idempotency key/ERP status before retrying side-effecting commands.
8. Reproduce using SOAP fixtures or HTTP stubs rather than hitting production.
9. Monitor metrics after fixing to confirm error rates actually drop.

**Never remediate** by disabling hostname verification, clearing truststores, raising all timeouts to infinity, enabling DTDs, or retrying all exceptions.

## 18. SOAP HTTP Sender Deployment Checklist

- [ ] Verified exact endpoint URI, SOAP 1.1/1.2, WSDL/XSD, and SOAPAction.
- [ ] `WebServiceTemplate` wired to the right marshaller, message factory, and sender.
- [ ] Selected `HttpUrlConnectionMessageSender` or Apache HttpClient sender matching project needs and **exact library version**.
- [ ] Explicitly configured connect, read, pool acquisition, and handshake timeouts plus total deadline.
- [ ] Connection pool caps per-route, max total, idle cleanup, and shutdown lifecycle.
- [ ] HTTP Basic/Bearer, mTLS, and WS-Security distinguished and configured at the right layer.
- [ ] No hardcoded or logged credentials, bearer tokens, SOAP security headers, or sensitive payloads.
- [ ] CA chain and hostname verification always enabled; certificate rotation tested with connection pools.
- [ ] Proxy/egress rules and endpoint allowlists against SSRF configured.
- [ ] SOAP Faults, HTTP statuses, and XML binding errors classified separately.
- [ ] Retries have budgets, backoff, and idempotency/unknown-outcome policies; no stacked multi-layer retries.
- [ ] SQL outbox / broker acknowledgements align with transaction and durability contracts.
- [ ] Both `MockWebServiceServer` payload tests **and** transport integration tests for auth/TLS/timeouts exist.
- [ ] Observability covers latency, pool saturation, fault types, retries, outbox age, and business outcomes.
- [ ] Dashboards and logs avoid leaking PII or creating high-cardinality metric labels.

**Key takeaway:** In Spring Web Services, `WebServiceTemplate` orchestrates SOAP requests/responses, `Jaxb2Marshaller` handles object–XML conversion, and **`WebServiceMessageSender` handles the HTTP connection**. Securing a production integration takes more than an HTTPS URL: it requires a version-matched sender, layered authentication, bounded timeouts, SOAP Fault handling, idempotent retries, real transport tests, and observability. These practices keep SOAP/HTTP flows consistent with the broader principles of Spring Boot Integration around **configuration, data contracts, transactions, errors, and deduplication**.

## References

- [Spring Web Services — Client-side Web Services](https://docs.spring.io/spring-ws/docs/current/reference/html/#client): `WebServiceTemplate`, callbacks, senders, and fault handling.
- [Spring Web Services — API: WebServiceTemplate](https://docs.spring.io/spring-ws/docs/current/api/org/springframework/ws/client/core/WebServiceTemplate.html): configuring senders, marshallers, and fault resolvers.
- [Spring Web Services — API: WebServiceMessageSender](https://docs.spring.io/spring-ws/docs/current/api/org/springframework/ws/transport/WebServiceMessageSender.html): transport abstraction.
- [Spring Web Services — API: HttpUrlConnectionMessageSender](https://docs.spring.io/spring-ws/docs/current/api/org/springframework/ws/transport/http/HttpUrlConnectionMessageSender.html): HTTP URLConnection sender and timeouts.
- [Spring Boot — Web Services](https://docs.spring.io/spring-boot/reference/io/webservices.html): Spring-WS auto-configuration and client support.
- [Spring Framework — O/X Mapping](https://docs.spring.io/spring-framework/reference/data-access/oxm.html): JAXB/`Jaxb2Marshaller` and XML contracts.
- [Spring Boot — SSL](https://docs.spring.io/spring-boot/reference/features/ssl.html): SSL bundles, CA trust, and key materials.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): client credentials and token lifecycle.
- [Apache HttpClient 5 — Project](https://hc.apache.org/httpcomponents-client-5.5.x/index.html): connection pooling, TLS, credentials, and transport.
- [Spring Web Services — WS-Security](https://docs.spring.io/spring-ws/docs/current/reference/html/#security): WSS4J, SOAP signatures, timestamps, and security policies.
- [Micrometer — Observation](https://docs.micrometer.io/micrometer/reference/observation.html): observation lifecycle and metrics/traces.
- [OWASP — Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): TLS versions, certificate verification, and configuration safety.
