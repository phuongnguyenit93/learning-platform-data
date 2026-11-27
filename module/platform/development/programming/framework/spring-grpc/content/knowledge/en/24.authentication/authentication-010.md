# Insecure Metadata When Using Plaintext

## 1. Metadata is not encrypted by default

In **Spring gRPC**, metadata carries auxiliary information for RPCs such as bearer tokens, tenant context, correlation IDs, locales, or tracing info. Metadata is transmitted alongside gRPC's HTTP/2 headers and trailers. The Metadata API only provides a way to represent and transport values; it does not encrypt or authenticate the data.

If a client connects using plaintext HTTP/2 (h2c), all traffic on the connection is unprotected by TLS. This includes:

- Request metadata such as authorization, tenant, or API keys.
- Response metadata/trailers such as error details or refresh tokens if placed there by the application.
- Protobuf message bodies and response messages.
- Protocol information that can reveal methods, payload sizes, and communication cadence.

Therefore, a bearer token placed in metadata is not safe merely because it lives in a header instead of the Protobuf body. On a plaintext transport, anyone able to observe or intercept the network can read or modify the data.

## 2. What risks does plaintext (h2c) create?

When using plaintext, the client does not establish TLS for the gRPC connection. On an untrusted network, a party in an observation position can:

- **Read credentials:** capture bearer tokens, API keys, or identifying information sent in metadata.
- **Read business data:** inspect request/response bodies even when metadata contains no sensitive values.
- **Tamper with data in transit:** modify metadata or messages if capable of intercepting the connection.
- **Impersonate peers:** the client does not verify the server's certificate because no TLS handshake occurs.
- **Replay exposed credentials:** reuse still-valid tokens to invoke services within the token's scope of permissions.

H2c does not merely expose metadata. All application data crossing the connection lacks the confidentiality and integrity provided by TLS.

~~~mermaid
flowchart LR
    C[gRPC client] -->|HTTP/2 plaintext| N((Network))
    N --> S[Spring gRPC server]
    A[Observer or attacker] -.->|Can read or modify| N
~~~

Do not treat an internal network, VPC, or Kubernetes cluster as an automatically safe zone. A compromised workload, shared node, network misconfiguration, or untrusted proxy can create a path for traffic observation.

## 3. Which metadata is commonly sensitive?

| Metadata | Example | Risk under plaintext |
| --- | --- | --- |
| Authorization | Bearer access token | Hijacks API call privileges until token expires/is revoked |
| API key | Integration application key | Impersonates the application or exceeds quotas |
| Tenant/user context | Tenant ID, user ID, role | Exposes customer structure and access context |
| Session/correlation token | Token linking multiple operations | Enables session linking or hijacking if the token carries privileges |
| Internal routing data | Service name, cluster, route | Reveals topology and internal details |
| Custom response trailers | Error details or business data | Data leakage through response metadata |

Not all metadata is secret. Request IDs or trace IDs can often be used for correlation, yet privacy policies and data linkability still require evaluation. Classify metadata by sensitivity instead of assuming every header is harmless.

## 4. ASCII and binary metadata are not security mechanisms

gRPC Java represents metadata as typed keys and values:

- Metadata keys are lowercase ASCII names.
- ASCII values use Metadata.ASCII_STRING_MARSHALLER.
- Binary metadata uses keys ending in -bin and Metadata.BINARY_BYTE_MARSHALLER.

Example:

~~~java
import io.grpc.Metadata;

Metadata headers = new Metadata();

Metadata.Key<String> authorization =
        Metadata.Key.of(
                "authorization",
                Metadata.ASCII_STRING_MARSHALLER);

Metadata.Key<byte[]> opaqueContext =
        Metadata.Key.of(
                "app-context-bin",
                Metadata.BINARY_BYTE_MARSHALLER);

headers.put(authorization, "Bearer <access-token>");
headers.put(opaqueContext, new byte[] { 1, 2, 3 });
~~~

The -bin suffix only indicates the metadata value is binary data serialized per gRPC rules. It does not encrypt, sign, or conceal the value. Base64, encoding, or converting a token into a byte array does not provide confidentiality either.

Do not place large payloads into metadata. Metadata is transmitted as HTTP/2 headers/trailers and is typically subject to size limits on clients, servers, or proxies. Business payloads belong in Protobuf messages; credentials and sensitive metadata must be protected with TLS.

## 5. TLS protects metadata and messages in transit

TLS provides three essential properties for a connection:

- **Confidentiality:** encrypts metadata, message bodies, and trailers across the protected connection segment.
- **Integrity:** detects data tampering in transit.
- **Server authentication:** the client verifies the server via its certificate and hostname.

When the client uses TLS properly, network observers cannot directly read bearer tokens or Protobuf payloads inside the encrypted connection. The client must still verify the certificate chain and hostname. Disabling certificate checks or using a trust-all trust manager forfeits server authentication guarantees.

gRPC Java client example:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;

ManagedChannel channel = ManagedChannelBuilder
        .forAddress("catalog.internal.example", 9090)
        .useTransportSecurity()
        .build();
~~~

The channel uses TLS and verifies certificates according to the runtime's trust configuration. In environments using a private CA, configure the appropriate trust store/certificate authority and ensure the hostname in the certificate matches the address used by the client.

Only use usePlaintext() in controlled local/test environments, such as loopback or test channels carrying no real credentials. Never use it as a way to fix certificate errors in staging/production.

## 6. Sending a bearer token via metadata on a TLS channel

Once the channel is protected with TLS, the client can send the access token in authorization metadata. Illustrative example with a static header:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import io.grpc.Metadata;
import io.grpc.stub.MetadataUtils;
import com.example.catalog.v1.CatalogServiceGrpc;
import com.example.catalog.v1.GetItemRequest;
import com.example.catalog.v1.GetItemResponse;

Metadata headers = new Metadata();
Metadata.Key<String> authorization =
        Metadata.Key.of(
                "authorization",
                Metadata.ASCII_STRING_MARSHALLER);
headers.put(authorization, "Bearer <access-token>");

ManagedChannel channel = ManagedChannelBuilder
        .forAddress("catalog.internal.example", 9090)
        .useTransportSecurity()
        .build();

CatalogServiceGrpc.CatalogServiceBlockingStub stub =
        CatalogServiceGrpc.newBlockingStub(channel)
                .withInterceptors(
                        MetadataUtils.newAttachHeadersInterceptor(headers));

GetItemResponse response = stub.getItem(
        GetItemRequest.newBuilder()
                .setItemId("item-42")
                .build());
~~~

This example illustrates attaching a fixed header to a call. For tokens that expire or vary per user, use CallCredentials to resolve credentials per RPC, refresh according to identity provider policy, and avoid sharing mutable token state across concurrent requests.

TLS protects the token while it travels over the connection. It does not replace verifying signature, issuer, audience, expiry, and authorization on the server. The server must still authenticate the token and check permissions before running business logic.

## 7. TLS termination at a gateway: protecting hop by hop

TLS only protects the connection segment between the two peers performing the handshake. If an architecture terminates TLS at a gateway/proxy and then opens a plaintext connection to the backend, metadata is decrypted at the gateway and traverses the internal network in plaintext.

~~~mermaid
flowchart LR
    C[Client] -->|TLS| G[Gateway / TLS termination]
    G -->|Plaintext h2c| S[Spring gRPC service]
    X[Observer on backend network] -.->|Can read metadata and payload| S
~~~

Deployment options:

1. **End-to-end TLS:** the client establishes TLS directly to the gRPC service, if topology allows.
2. **TLS on both hops:** client-to-gateway uses TLS and gateway-to-service also uses TLS.
3. **mTLS between workloads:** gateway and service verify each other's certificates while encrypting the internal hop.

If the gateway needs to inspect metadata for routing or authentication, the gateway is a trust boundary. Restrict who has administrative access to the gateway, do not write credentials to access logs, and forward only permitted metadata.

## 8. mTLS protects service-to-service communication

Mutual TLS requires both client and server to verify the peer's certificate. It is well suited to protecting connections between gateways, services, and internal workloads:

| Component | Verification |
| --- | --- |
| Client workload | Verifies server certificate and hostname |
| Server workload | Verifies client certificate against trust chain/policy |
| Identity mapping | Maps certificate identity/SAN to a workload principal |
| Authorization | Decides which methods the workload may invoke |

mTLS both encrypts metadata/payloads on the hop and authenticates the workload at the transport layer. However, a gateway's certificate does not prove the end user is allowed to read an order. If the request carries a user access token, the service must still verify the token and enforce authorization for the user or delegated principal.

Do not share one certificate across all workloads when per-service auditing and revocation are needed. Manage certificate lifecycle, rotation, trust bundles, and revocation following your platform's procedures.

## 9. Metadata can still leak after TLS decryption

TLS does not protect metadata from the endpoint itself or a trusted but misconfigured intermediary. Metadata can show up in:

- Gateway access logs or debug logs.
- gRPC interceptors logging full headers/trailers.
- Distributed tracing baggage or span attributes.
- Exception messages and error reporting.
- APM agents, packet captures, or diagnostic dumps at the endpoint.

Therefore:

- Redact authorization, cookies, API keys, and custom secret headers.
- Never log entire Metadata objects.
- Include only an allowlist of safe fields in traces.
- Restrict access to logs/traces and set appropriate retention.
- Never reflect tokens or credentials in response trailers.
- Audit proxy configuration so sensitive headers are not forwarded to services that do not need them.

TLS protects data while traveling across the network; log/tracing controls protect data after the endpoint decrypts it.

## 10. Choosing minimal and safe metadata

Before adding custom metadata, define its purpose, owner, and lifecycle:

| Field | Should you use it? | Rule |
| --- | --- | --- |
| authorization | Yes when API uses bearer tokens | Send only over TLS; redact in logs |
| traceparent / tracing context | Yes per tracing standard | Never put secrets or PII into baggage |
| x-request-id | Yes if correlation is needed | Use IDs carrying no sensitive data |
| tenant-id | Only when contract requires | Server must cross-check against authenticated principal |
| user-role | Avoid trusting directly | Roles must come from verified credentials/policies |
| password/API secret | Avoid resending via metadata | Prefer short-lived tokens or appropriate credential mechanisms |
| business payload | Do not use metadata | Place inside the Protobuf message |

Client metadata is untrusted input. The server must never use a client-supplied tenant, role, or user ID as the basis for granting permissions without cross-checking the authenticated principal.

## 11. Testing plaintext and TLS

Tests must prove both transport security and metadata behavior:

| Scenario | Expected result |
| --- | --- |
| Plaintext client connects to TLS-only server | Handshake/connection fails; RPC is not processed |
| TLS client with valid server certificate | Connection succeeds |
| Expired certificate or outside trust chain | Client rejects the handshake |
| Hostname does not match certificate | Client rejects server identity |
| Bearer token sent over TLS | Server receives metadata and verifies token |
| Token invalid signature or expired | UNAUTHENTICATED |
| Valid token lacking permission | PERMISSION_DENIED |
| Binary metadata ending in -bin | Parsed by binary marshaller, yet still safe only when transport is protected |
| Gateway terminates TLS then calls backend over plaintext | Explicitly treat backend hop as trust boundary; test TLS/mTLS config if required |
| Debug logging/tracing enabled | Authorization and secret headers are redacted |

In tests, use dedicated synthetic certificates and tokens. Never use production credentials to test plaintext or packet captures. Check both request metadata and response trailers; prevent secrets from being echoed through error paths.

## 12. Common mistakes

1. **Assuming metadata is encrypted automatically.** Metadata is just headers/trailers; plaintext transport exposes its values.
2. **Assuming the -bin suffix means encryption.** Binary marshalling only formats data.
3. **Protecting only metadata while forgetting message bodies.** h2c leaves both request and response payloads without TLS.
4. **Using usePlaintext() in production.** Tokens and business data can be read or altered.
5. **Disabling certificate verification to fix TLS errors.** Clients can connect to the wrong server.
6. **Assuming TLS at the gateway protects the backend hop too.** Each hop must be evaluated and secured independently.
7. **Letting proxies/interceptors log authorization metadata.** Credentials can still leak after TLS termination.
8. **Trusting tenant/role in client-sent metadata.** Metadata is input; authorization must rely on the verified principal.
9. **Treating mTLS as user authorization.** mTLS authenticates a workload/peer, not end-user business permissions.

## 13. Practice exercise

For catalog.v1.CatalogService/GetItem:

1. Create a plaintext channel in a test environment and observe the TLS-only server rejecting the connection.
2. Configure client TLS with an appropriate trust store; test a wrong-CA certificate and a hostname mismatch.
3. Send a bearer token in authorization metadata over TLS; verify the server validates the token.
4. Add a binary metadata key ending in -bin and explain why it is not encryption.
5. Simulate TLS termination at a gateway; inspect whether the gateway-to-service hop uses TLS/mTLS or plaintext.
6. Enable logging/tracing and verify authorization, API keys, and custom secret headers are redacted.
7. Send a client-supplied tenant ID different from the tenant in the principal; verify the server rejects or ignores the untrusted value.

**Completion criteria:** the learner can explain why metadata has no built-in confidentiality, identify the risks of h2c, configure TLS/mTLS properly per hop, send credentials safely via metadata, and prevent leaks through proxies, logs, and traces.

### References

- [gRPC Metadata](https://grpc.io/docs/guides/metadata/): metadata headers/trailers in gRPC.
- [gRPC Authentication](https://grpc.io/docs/guides/auth/): TLS, mTLS, and credentials.
- [gRPC Java Metadata API](https://grpc.github.io/grpc-java/javadoc/io/grpc/Metadata.html): ASCII and binary metadata.
- [gRPC Java ManagedChannelBuilder API](https://grpc.github.io/grpc-java/javadoc/io/grpc/ManagedChannelBuilder.html): configuring transport security on client channels.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): integrating gRPC clients/servers in Spring.
