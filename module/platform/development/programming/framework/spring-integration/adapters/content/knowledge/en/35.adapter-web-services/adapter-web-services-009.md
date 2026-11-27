# Client interceptors and security

## Objectives

After this lesson, you will be able to:

- Locate client interceptors within an outbound SOAP call from Spring Integration.
- Distinguish Spring Web Services interceptors from HTTP interceptors and `MessageChannel` interceptors.
- Configure interceptors to add headers, record operational metadata, and apply WS-Security.
- Choose the proper protection layer for SOAP headers, HTTP transport, and TLS connections.
- Handle SOAP Faults, authentication errors, and connection errors without leaking sensitive information.

In the **SPRING_INTEGRATION_ADAPTERS** module, outbound adapters and gateways send messages from internal systems to external systems. For Web Services, most cases use SOAP: payloads are marshalled to XML, sent over HTTP or HTTPS, and responses are unmarshalled back into objects. Client interceptors let you apply cross-cutting behavior around SOAP calls without embedding security and observability logic inside every business flow.

The module also covers file, SFTP, HTTP, JMS, AMQP, Kafka, and database adapters. Each connector has its own authentication, transport protection, and connection management mechanisms. **`ClientInterceptor`** in this lesson applies to Spring Web Services SOAP clients; do not apply it to every adapter merely because all adapters exchange messages with external systems.

## 1. Where do interceptors sit in an integration flow?

An outbound SOAP flow typically follows these steps:

1. A message enters a Spring Integration request channel.
2. The outbound gateway takes the payload and turns it into a SOAP request via a marshaller.
3. `WebServiceTemplate` executes the `ClientInterceptor` chain.
4. `WebServiceMessageSender` sends the SOAP envelope over HTTP or HTTPS.
5. A response or SOAP Fault comes back; interceptors process the outcome.
6. The gateway converts the response into a payload and emits it on the reply channel. Errors become exceptions for the flow to handle.

The diagram below shows where interceptors sit:

~~~mermaid
sequenceDiagram
    participant Flow as Spring Integration flow
    participant Gateway as Web Services outbound gateway
    participant Template as WebServiceTemplate
    participant Interceptor as ClientInterceptor chain
    participant Sender as WebServiceMessageSender
    participant Partner as SOAP service

    Flow->>Gateway: Message request
    Gateway->>Template: SOAP payload
    Template->>Interceptor: handleRequest
    Template->>Sender: Send SOAP request
    Sender->>Partner: HTTPS / SOAP
    Partner-->>Sender: SOAP response or Fault
    Sender-->>Template: WebServiceMessage
    alt Successful response
        Template->>Interceptor: handleResponse
    else SOAP Fault
        Template->>Interceptor: handleFault
    end
    Template->>Interceptor: afterCompletion
    Template-->>Gateway: Result or exception
    Gateway-->>Flow: Reply or error flow
~~~

Interceptors belong to the Spring Web Services SOAP client. They do not replace `MessageChannel`s, do not control routing between channels, and are not the place to implement application business rules.

## 2. Lifecycle of `ClientInterceptor`

Spring Web Services defines the contract **org.springframework.ws.client.support.interceptor.ClientInterceptor**. An interceptor can implement four callbacks:

| Callback | Timing | Appropriate purpose |
|---|---|---|
| `handleRequest` | Before sending the request | Add SOAP headers, check call preconditions, record metadata |
| `handleResponse` | On receiving a successful response | Inspect or record the response |
| `handleFault` | On receiving a SOAP Fault | Record the fault and enrich diagnostic context |
| `afterCompletion` | When the invocation completes | Clean up resources or record the final outcome |

Request callbacks run in the order interceptors are registered. Response, fault, and `afterCompletion` callbacks run in reverse order. This allows interceptors to nest like a processing chain.

Two important rules:

- Returning **false** from `handleRequest` halts further processing and prevents the request from being sent. Use this only when intentionally rejecting or short-circuiting a call.
- Never catch and swallow security exceptions. If signature, certificate, or token verification fails, the call must fail so upstream flows handle it properly.

Interceptors are normally registered as shared Spring beans. Because multiple messages may run concurrently, never store per-request state in mutable fields on a singleton interceptor. To measure latency or correlate requests, use a per-invocation context mechanism and ensure cleanup in `afterCompletion`.

### Example: interceptor logging the call lifecycle

The example below logs outcome types and exceptions without reading or logging the full SOAP envelope:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ws.client.WebServiceClientException;
import org.springframework.ws.client.support.interceptor.ClientInterceptor;
import org.springframework.ws.context.MessageContext;

public final class SoapAuditInterceptor implements ClientInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(SoapAuditInterceptor.class);

    @Override
    public boolean handleRequest(MessageContext messageContext)
            throws WebServiceClientException {
        log.debug("Preparing outbound SOAP request");
        return true;
    }

    @Override
    public boolean handleResponse(MessageContext messageContext)
            throws WebServiceClientException {
        log.debug("Received outbound SOAP response");
        return true;
    }

    @Override
    public boolean handleFault(MessageContext messageContext)
            throws WebServiceClientException {
        log.warn("Received SOAP Fault from partner");
        return true;
    }

    @Override
    public void afterCompletion(
            MessageContext messageContext, Exception exception)
            throws WebServiceClientException {
        if (exception != null) {
            log.warn("SOAP invocation failed: {}",
                    exception.getClass().getSimpleName());
        }
    }
}
~~~

In real environments, logs should include correlation ID, partner name, operation, duration, and error category. Obtain correlation IDs from a context designed to flow through the integration pipeline; never use a mutable field in an interceptor to pass IDs between requests. Never log passwords, access tokens, `UsernameToken`s, private keys, or SOAP payloads containing personal or payment data.

### Example: adding a SOAP header

When a partner's contract requires an application header, an interceptor can add it to the SOAP message:

~~~java
import java.util.UUID;
import javax.xml.namespace.QName;
import org.springframework.ws.client.WebServiceClientException;
import org.springframework.ws.client.support.interceptor.ClientInterceptor;
import org.springframework.ws.context.MessageContext;
import org.springframework.ws.soap.SoapMessage;

public final class PartnerHeaderInterceptor implements ClientInterceptor {

    private static final QName REQUEST_ID =
            new QName("urn:example:integration", "RequestId", "int");

    @Override
    public boolean handleRequest(MessageContext messageContext)
            throws WebServiceClientException {
        if (messageContext.getRequest() instanceof SoapMessage) {
            SoapMessage soapMessage = (SoapMessage) messageContext.getRequest();
            soapMessage.getSoapHeader()
                    .addHeaderElement(REQUEST_ID)
                    .setText(UUID.randomUUID().toString());
        }
        return true;
    }

    @Override
    public boolean handleResponse(MessageContext messageContext)
            throws WebServiceClientException {
        return true;
    }

    @Override
    public boolean handleFault(MessageContext messageContext)
            throws WebServiceClientException {
        return true;
    }

    @Override
    public void afterCompletion(
            MessageContext messageContext, Exception exception) {
        // Do not hold request data in the interceptor instance.
    }
}
~~~

Header names, namespaces, data types, and value-generation rules must follow the partner's contract. A self-added header does not automatically act as authentication. If the partner requires the header to be digitally signed, configure WS-Security to protect that header per policy.

## 3. Distinguishing security layers

A SOAP call may pass through multiple protection layers. Pick the right layer based on where data is carried and what the integration contract requires.

| Layer | Common mechanisms | What it protects |
|---|---|---|
| SOAP message | WS-Security `UsernameToken`, `Timestamp`, `Signature`, `Encryption` | Message-level identity, integrity, and/or confidentiality |
| HTTP transport | HTTP Basic, Bearer token, API key in HTTP header | HTTP-layer access control |
| TLS | HTTPS, truststore, client certificate (mTLS) | Transport channel, server authentication, and optional client authentication |
| Spring Integration message | `MessageChannel`, headers, and channel security | Permission to send/receive messages inside the app |

These mechanisms do not replace one another:

- HTTPS encrypts the transport channel between two TLS endpoints, but does not produce an XML signature verifiable after a message passes an intermediary gateway.
- WS-Security protects the SOAP message per policy, but does not replace verifying the server certificate during the HTTPS handshake.
- HTTP Bearer tokens live in the HTTP `Authorization` header; WS-Security `UsernameToken`s live in the SOAP header. Sending one does not satisfy the other.
- Spring Integration channel interceptors operate on internal messages. They do not replace Spring Web Services `ClientInterceptor`s.

Do not confuse **org.springframework.http.client.ClientHttpRequestInterceptor** with **org.springframework.ws.client.support.interceptor.ClientInterceptor**. The former belongs to Spring's HTTP client (typically used with `RestTemplate`); the latter operates on SOAP `MessageContext` and is registered on `WebServiceTemplate`. Choose the interface matching the client actually sending the request.

Check the partner contract to see which mechanisms are required, which headers must be signed, which parts must be encrypted, timestamp lifetimes, and which certificates are trusted.

## 4. Configuring `WebServiceTemplate` and interceptors

**WebServiceTemplate** is the central Spring Web Services client. Interceptors must be attached to the exact template used by the outbound gateway or SOAP-calling component. If the application configures one template while the gateway creates and uses a different template, the interceptors will never run.

Example configuring a partner-specific template:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.client.support.interceptor.ClientInterceptor;
import org.springframework.ws.transport.WebServiceMessageSender;

@Configuration
public class PartnerSoapClientConfiguration {

    @Bean
    WebServiceTemplate partnerWebServiceTemplate(
            Jaxb2Marshaller partnerMarshaller,
            @Qualifier("partnerMessageSender")
            WebServiceMessageSender messageSender,
            @Qualifier("partnerHeaderInterceptor")
            ClientInterceptor headerInterceptor,
            @Qualifier("partnerWsSecurityInterceptor")
            ClientInterceptor securityInterceptor) {

        WebServiceTemplate template = new WebServiceTemplate();
        template.setDefaultUri("https://partner.example.com/soap");
        template.setMarshaller(partnerMarshaller);
        template.setUnmarshaller(partnerMarshaller);
        template.setMessageSenders(messageSender);
        template.setInterceptors(new ClientInterceptor[] {
                headerInterceptor,
                securityInterceptor
        });
        return template;
    }
}
~~~

This example assumes `Jaxb2Marshaller`, `partnerMessageSender`, `partnerHeaderInterceptor`, and `partnerWsSecurityInterceptor` beans already exist. `Jaxb2Marshaller` is used for both marshalling requests and unmarshalling responses. Adjust the endpoint and beans to match your application configuration.

In a Spring Integration flow, the outbound gateway must use this configured template. With XML namespace or Java DSL, how the template is passed depends on your Spring Integration version; verify the gateway configuration for your project version and confirm the gateway references the intended bean. For direct illustration, a Service Activator can invoke the same template:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;
import org.springframework.ws.client.core.WebServiceTemplate;

@Component
public class PartnerSoapOperation {

    private final WebServiceTemplate partnerWebServiceTemplate;

    public PartnerSoapOperation(
            @Qualifier("partnerWebServiceTemplate")
            WebServiceTemplate partnerWebServiceTemplate) {
        this.partnerWebServiceTemplate = partnerWebServiceTemplate;
    }

    @ServiceActivator(inputChannel = "partnerSoapRequests")
    public Object invoke(Object request) {
        return partnerWebServiceTemplate.marshalSendAndReceive(request);
    }
}
~~~

The Service Activator above only illustrates calling the template from a Spring Integration endpoint. When using a Web Services outbound gateway, keep the gateway as the dedicated adapter and configure it to use the interceptor-equipped template. Avoid creating a new template per message, as that loses shared configuration, adds initialization overhead, and makes behavior hard to control.

If the application integrates with multiple partners, create separate templates, message senders, and interceptor sets for each contract. Never share one security policy across partners with different `UsernameToken`, signature, certificate, or timeout requirements.

## 5. Protecting SOAP messages with WS-Security

WS-Security defines how security tokens and protections are carried in SOAP headers. Common mechanisms include:

- **UsernameToken**: sends client identity; may use plain-text password or password digest per partner policy.
- **Timestamp**: bounds message validity window, helping detect stale or replayed messages.
- **Signature**: signs specified SOAP parts so the receiver can verify origin and integrity.
- **Encryption**: encrypts specified SOAP parts so only holders of the matching key can read them.

In Spring Web Services, **Wss4jSecurityInterceptor** provides WS-Security integration built on Apache WSS4J. The example below configures a digest `UsernameToken` and timestamp for outbound requests:

~~~java
import org.apache.wss4j.dom.WSConstants;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;

@Bean
Wss4jSecurityInterceptor partnerWsSecurityInterceptor(
        @Value("${partner.soap.username}") String username,
        @Value("${partner.soap.password}") String password) {

    Wss4jSecurityInterceptor interceptor =
            new Wss4jSecurityInterceptor();

    interceptor.setSecurementActions("Timestamp UsernameToken");
    interceptor.setSecurementUsername(username);
    interceptor.setSecurementPassword(password);
    interceptor.setSecurementPasswordType(WSConstants.PW_DIGEST);
    interceptor.setSecurementTimeToLive(300);

    return interceptor;
}
~~~

Securement properties describe security applied to outgoing messages. Password digest is not a substitute for HTTPS; still protect the transport and manage secrets safely. Username, password, and TTL must match the partner's policy. Never hardcode real credentials in source code or committed config files; pull them from a secret manager or controlled environment configuration.

If the partner signs responses, the client must verify signatures using approved trust material. If the contract requires encrypting requests, configure the partner's public certificate and specify the exact SOAP parts to encrypt. Signing and encryption normally require Crypto/keystores, key aliases, key passwords, certificate chains, and lists of protected elements. Manage all of these per environment and certificate lifecycle.

Guidelines for configuring WS-Security:

1. Agree explicitly with the partner on actions and action order. Action names like `Timestamp`, `UsernameToken`, `Signature`, and `Encrypt` must match both sides' policies.
2. Specify clearly which parts of the SOAP Body and SOAP Header must be signed or encrypted. Signing only the Body may be insufficient if the partner requires protecting routing or identity headers.
3. Verify response signatures using the right truststore and certificate. Never trust a certificate merely because it was attached inside the message.
4. Synchronize clocks across systems. Timestamps may be rejected if clock skew exceeds the allowed threshold.
5. Use nonces, timestamps, and anti-replay checks per stack capabilities and partner requirements.
6. Test bad credentials, expired timestamps, untrusted certificates, invalid signatures, and responses violating policy.

Enable validation only for actions the partner commits to sending in responses. If the client expects a signature when the partner does not sign responses, mismatched validation will reject every response. Conversely, if the contract requires signed responses and the client omits verification, the application could accept tampered messages.

## 6. Protecting HTTP transport and TLS

SOAP is usually transmitted over HTTP(S), so message security and transport security must be configured separately.

**HTTPS/TLS** requires verifying the server certificate chain and hostname. The truststore must hold trusted CAs or certificates; for mutual TLS, the client needs a keystore with its private key and certificate. Never disable hostname verification, never use a trust-all `TrustManager`, and never ignore handshake errors just to make an integration pass.

**HTTP Basic, Bearer tokens, or API keys** belong to the HTTP layer. Configure them on the HTTP message sender or transport mechanism matching your Spring-WS version and HTTP client. Never confuse the HTTP `Authorization` header with a SOAP header. For short-lived tokens, implement refresh logic, expiration handling, and log redaction. If the partner uses OAuth2, define where tokens are fetched, audience/scope, lifetime, and refresh flow; never assume WS-Security implements OAuth2 automatically.

The message sender is also where you manage:

- Connection timeout and read/response timeout.
- Connection pooling and max-connection caps under concurrent load.
- Organization-approved TLS protocols and cipher suites.
- Truststores, keystores, and certificate rotation schedules.
- Proxies, DNS, and deployment network settings.

Class names and HTTP client configurations can vary across Spring Web Services versions and chosen HTTP libraries. Use a message sender compatible with your project's versions, then test real TLS in an integration environment. Never copy SSL config from another version without verifying APIs and dependencies.

## 7. Security errors and handling in Spring Integration

Errors can be grouped into three categories to pick the right handling strategy:

| Error group | Examples | Handling direction |
|---|---|---|
| Authentication or policy error | HTTP 401/403, wrong `UsernameToken`, invalid signature | Stop the call, alert on config or credentials, no blind retries |
| Business SOAP error | SOAP Fault, business error code, invalid request | Read fault code/detail per contract, map to domain error |
| Transient transport error | Timeout, temporary DNS error, connection reset, HTTP 5xx | Bounded retries possible if the operation is safe to retry |

A SOAP Fault is a structured error SOAP response. Interceptors receive faults via **handleFault**; transport failures or exceptions during invocation pass through exceptions and are observed in **afterCompletion**. Never treat every error as a SOAP Fault.

In Spring Integration, exceptions from outbound endpoints can be routed to an error channel per flow configuration. When adding retry advice, classify exceptions and cap attempt counts, backoff intervals, and total duration. Retry only transient errors. A timeout does not prove the partner didn't process the request: the server may have executed the business action and lost the response. For transaction creation or data mutation, use an idempotency key or contracted status-lookup mechanism before resending.

Never return internal information such as stack traces, keystore paths, tokens, or certificate details to calling systems. Log correlation IDs and normalized error codes in the error flow so operations teams can trace security logs.

## 8. Testing interceptors and security policies

Tests must verify both acceptance and rejection behavior:

- Requests carry the exact SOAP headers, namespaces, and values defined in the contract.
- `UsernameToken` and `Timestamp` are generated with the expected actions and formats.
- Valid responses are accepted; responses missing or failing signatures are rejected when policy requires signatures.
- SOAP Faults route to the expected error branch.
- HTTP 401/403 responses are not retried as transient network errors.
- Timeouts are bounded by configuration and do not hang the entire flow.
- Logs contain no passwords, tokens, or sensitive SOAP payloads.

Spring-WS provides **MockWebServiceServer** to test `WebServiceTemplate` requests/responses without calling a live partner. You can use request matchers to verify SOAP payloads and headers and return mock responses or SOAP Faults. Testing TLS, mutual TLS, certificate rotation, and WS-Security interoperability still requires an integration environment with certificates and policies close to production.

A solid security test suite should include at least one success case plus negative cases: wrong credentials, stale timestamps, untrusted certificates, tampered signatures, and rejected HTTP authorization. Document which policy each test verifies so the team can update tests intentionally when partner contracts change.

## 9. Common incidents

| Symptom | Root cause to check |
|---|---|
| Interceptor is never called | Outbound gateway uses a different `WebServiceTemplate`; interceptor not registered on the active template |
| Request has SOAP header but partner ignores it | Wrong namespace, element name, SOAP version, or off-contract header |
| Partner returns HTTP 401/403 | Wrong HTTP auth mechanism or credentials; check `Authorization` header and client permissions |
| WS-Security rejects `UsernameToken` | Wrong password type, username, password, nonce, or timestamp rules |
| Signature validation failed | Wrong truststore/certificate, alias, signed elements, action order, or canonicalization config |
| TLS handshake failed | Untrusted certificate chain, hostname mismatch, expired certificate, or incompatible TLS policy |
| Fails only under concurrency | Interceptor holds shared mutable state or non-thread-safe token/context |
| Retries create duplicate records | Non-idempotent operation lacking idempotency key or reconciliation |

When investigating, check in order: endpoint and transport, HTTP status, SOAP Fault, WS-Security policy, and then business payload. Use correlation IDs to link Integration flow logs with SOAP client logs and partner logs.

## 10. Pre-production checklist for the adapter

- [ ] Outbound gateway uses the exact `WebServiceTemplate` configured with interceptors.
- [ ] Interceptors are thread-safe and retain no state from prior requests.
- [ ] SOAP headers use the right namespaces and match the contract.
- [ ] WS-Security actions, signed/encrypted elements, and validation match partner policy.
- [ ] HTTPS verifies certificate chains and hostnames; mTLS is configured where required.
- [ ] HTTP credentials and WS-Security credentials are managed separately from proper secret sources.
- [ ] Timeouts, connection pools, and retry limits align with the SLA.
- [ ] Error flow separates security failures, SOAP Faults, and transport failures.
- [ ] Idempotency or reconciliation exists for side-effecting operations.
- [ ] Logs include correlation IDs without exposing tokens, passwords, private keys, or sensitive SOAP payloads.
- [ ] Negative tests cover credentials, timestamps, signatures, certificates, and HTTP authorization.

A secure SOAP client must simultaneously honor the message contract, WS-Security policy, transport protection, and Spring Integration error handling. When these layers are configured on the exact `WebServiceTemplate` used by the gateway, business flows can consistently reuse security policies with controlled error handling.
