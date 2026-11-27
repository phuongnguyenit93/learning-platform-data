# HTTPS and Client Configuration in Test Environments

## Learning Objectives

**Spring Cloud Contract** describes HTTP or messaging behavior using the **Groovy DSL** and **YAML DSL**, generates producer-side tests, and packages HTTP stubs for consumers via **Stub Runner**. When consumers connect over **HTTPS**, checking the response from WireMock is only part of the picture: the client must also complete **TLS**, verify the server certificate, and perform hostname verification.

This topic belongs to the **WireMock** chapter. We cleanly separate **contracted HTTP behavior** from **connection security configuration**, so a stub returning HTTP 200 is never mistaken for proof that TLS was verified properly.

After this lesson, you will be able to:

- Start WireMock with an HTTPS listener and determine the right port.
- Distinguish **server keystore**, **client truststore**, **SAN**, and hostname verification.
- Configure a Java HTTP client to use a test truststore without disabling TLS validation.
- Guide HTTPS configuration for RestTemplate, RestClient, WebClient, and Feign.
- Explain the differences between a **self-managed `WireMockServer`** and **WireMock inside Stub Runner**.
- Write positive/negative tests, handle mTLS, container hostnames, CI, and connection errors.

## 1. TLS happens before HTTP matchers

A call to:

~~~text
https://localhost:8443/api/orders/ORD-1001
~~~

must complete the TLS handshake before the HTTP request ever reaches WireMock matchers.

~~~mermaid
sequenceDiagram
    participant C as Consumer HTTP client
    participant S as WireMock TLS listener
    participant W as WireMock matcher
    C->>S: TLS ClientHello
    S-->>C: Server certificate
    C->>C: Verify chain + trust + hostname
    alt Valid TLS
        C->>W: GET /api/orders/ORD-1001
        W->>W: Match method/path/headers
        W-->>C: HTTP 200 + JSON
    else Invalid TLS
        C--xS: Abort handshake
    end
~~~

Example Spring Cloud Contract HTTP contract:

~~~yaml
description: "Fetch paid order"
name: get_paid_order
request:
  method: GET
  url: /api/orders/ORD-1001
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: ORD-1001
    status: PAID
~~~

The contract describes **HTTP method, path, headers, status, and body**. It does not generate HTTPS certificates and does not automatically make Stub Runner open an HTTPS listener. The same mapping can work over HTTP or HTTPS once the server is configured appropriately.

| Test aspect | Example | Required evidence |
| --- | --- | --- |
| TLS identity | Certificate trusted, SAN matches hostname | HTTPS client integration test |
| HTTPS connectivity | Correct host, port, protocol | Client actually completes handshake |
| HTTP contract | GET on right path returns 200, contracted JSON | Producer contract tests and WireMock stub tests |
| Consumer behavior | Checkout handles `PAID` properly | Consumer integration assertions |
| Production config | TLS at ingress, renewal, cipher policy | Separate deployment and security tests |

**A passing HTTP contract test does not automatically prove HTTPS is configured correctly.** Conversely, a successful TLS handshake does not prove URLs or JSON responses are compatible.

## 2. Running WireMock over HTTPS

WireMock's Java API supports an HTTPS port. With a self-managed `WireMockServer` in tests, use dynamic ports to avoid collisions during parallel runs.

~~~java
import com.github.tomakehurst.wiremock.WireMockServer;

import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.wireMockConfig;
import static com.github.tomakehurst.wiremock.client.WireMock.*;

WireMockServer stub = new WireMockServer(
    wireMockConfig().dynamicPort().dynamicHttpsPort()
);

stub.start();
try {
    stub.stubFor(get(urlEqualTo("/api/orders/ORD-1001"))
        .willReturn(aResponse()
            .withStatus(200)
            .withHeader("Content-Type", "application/json")
            .withBody("{\"id\":\"ORD-1001\",\"status\":\"PAID\"}")));

    String httpsBaseUrl =
        "https://localhost:" + stub.httpsPort();

    // Use an HTTP client configured with an appropriate TLS truststore
    // to call httpsBaseUrl.
} finally {
    stub.stop();
}
~~~

This is **WireMock's Java DSL**, distinct from Spring Cloud Contract's Groovy DSL. Ensure exact APIs match the WireMock version used by your project.

### HTTP port and HTTPS port are two different values

| Value | Meaning |
| --- | --- |
| `stub.port()` | HTTP port (if the HTTP listener is enabled) |
| `stub.httpsPort()` | HTTPS port |
| `http://localhost:<httpPort>` | HTTP connection without TLS |
| `https://localhost:<httpsPort>` | HTTPS connection with TLS handshake |

The snippet above enables **both HTTP and HTTPS** on two dynamic ports. Enabling HTTPS does not automatically disable HTTP. If serving HTTPS exclusively is required, check the HTTP-disabling option for your exact version and verify it in a test.

**Never take `stub.port()` and just swap `http` to `https`.** A TLS connection sent to an HTTP port will fail before any HTTP matcher runs.

## 3. Certificates, keystores, truststores, and SANs

When WireMock acts as an HTTPS server, it needs a **private key** and **certificate**. The client must trust that certificate or an appropriate CA, and the URL's hostname must be authorized by the certificate.

| Component | Belongs to | Contents/function |
| --- | --- | --- |
| **Server keystore** | WireMock | Server's private key and certificate chain |
| **Client truststore** | Consumer test | CA/certificates trusted to verify the server |
| **Subject Alternative Name (SAN)** | Server certificate | Valid DNS hostnames or IP addresses |
| **Client keystore** | Consumer (when using mTLS) | Client's private key and certificate |
| **Server truststore** | WireMock (when using mTLS) | CA/certificates used to verify the client |

For instance, if a test calls `https://localhost`, the certificate should include `DNS:localhost`. If a test calls `https://127.0.0.1`, the certificate needs `IP:127.0.0.1`. A certificate with `CN=localhost` and no matching SAN **should not be considered sufficient** for modern hostname verification.

In some setups, WireMock may use a default test certificate. Do not assume that certificate is trusted by the JVM or has a SAN matching your test URL. Inspect the actual certificate and supply explicit trust material.

### Can self-signed certificates be used?

**Yes**, if the test client intentionally trusts that test certificate while keeping hostname verification enabled. A self-signed certificate is not trusted automatically; the client needs a truststore holding that certificate or matching trust anchor.

Recommended sequence:

1. Generate a test-specific certificate with the right SANs.
2. Place the private key and certificate in the server keystore.
3. Export the public certificate/CA and add it to the client truststore.
4. Configure the **test HTTP client** to trust this truststore.
5. Verify hostname verification remains enabled.
6. Also test a wrong certificate or wrong hostname to ensure the connection is rejected.

## 4. Creating test keystores and truststores with keytool

The commands below are **examples for POSIX-style shells**. On PowerShell, run one line per command or use appropriate line-continuation syntax. You do not need to run them while reading.

~~~bash
# 1. Test-only server keypair/certificate.
keytool -genkeypair -alias wiremock-local \
  -keyalg RSA -keysize 2048 -validity 30 \
  -storetype JKS -keystore wiremock-server.jks \
  -storepass test-only -keypass test-only \
  -dname "CN=localhost" \
  -ext "SAN=dns:localhost,ip:127.0.0.1"

# 2. Export only the public certificate, not the private key.
keytool -exportcert -rfc -alias wiremock-local \
  -keystore wiremock-server.jks -storepass test-only \
  -file wiremock-local.crt

# 3. Client truststore trusting the test certificate.
keytool -importcert -noprompt -alias wiremock-local \
  -file wiremock-local.crt -storetype PKCS12 \
  -keystore wiremock-client-trust.p12 \
  -storepass trust-test-only
~~~

`test-only` and `trust-test-only` are purely **illustrative passwords**, not for production. The server JKS containing a private key must be protected; never copy production private keys into test fixtures or repositories. Under strict policies, generate test certificates dynamically in CI with short lifetimes and clean them up afterward.

In supported WireMock versions, keystore configuration can look like:

~~~java
WireMockServer stub = new WireMockServer(
    wireMockConfig()
        .dynamicPort()
        .dynamicHttpsPort()
        .keystorePath("src/test/resources/tls/wiremock-server.jks")
        .keystorePassword("test-only")
);
~~~

The path must point to the actual generated JKS. Depending on version, options for keystore type, key manager password, and TLS listener may differ; check startup logs and your WireMock version's API. **Never fix certificate errors by disabling hostname verification.**

## 5. Using `SSLContext` for Java 11+ HttpClient

A clean strategy is configuring an `SSLContext` **scoped specifically to the test's HTTP client**, avoiding mutating the JVM-wide truststore and affecting other tests.

~~~java
import java.io.InputStream;
import java.net.http.HttpClient;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public final class TestHttpsClientFactory {

    public static HttpClient create(Path truststoreFile,
                                    char[] password) throws Exception {
        KeyStore trustStore = KeyStore.getInstance("PKCS12");

        try (InputStream input =
                 Files.newInputStream(truststoreFile)) {
            trustStore.load(input, password);
        }

        TrustManagerFactory trustManagers =
            TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm()
            );
        trustManagers.init(trustStore);

        SSLContext tlsContext = SSLContext.getInstance("TLS");
        tlsContext.init(
            null,
            trustManagers.getTrustManagers(),
            new SecureRandom()
        );

        return HttpClient.newBuilder()
            .sslContext(tlsContext)
            .build();
    }
}
~~~

Example sending an HTTP request over HTTPS to WireMock:

~~~java
import java.net.URI;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Path;

var client = TestHttpsClientFactory.create(
    Path.of("src/test/resources/tls/wiremock-client-trust.p12"),
    "trust-test-only".toCharArray()
);

var request = HttpRequest.newBuilder()
    .uri(URI.create("https://localhost:" + stub.httpsPort()
        + "/api/orders/ORD-1001"))
    .header("Accept", "application/json")
    .GET()
    .build();

HttpResponse<String> response = client.send(
    request, HttpResponse.BodyHandlers.ofString()
);

if (response.statusCode() != 200 ||
    !response.body().contains("\"PAID\"")) {
    throw new AssertionError("HTTPS response did not match expected scenario");
}
~~~

For solid consumer assertions, parse JSON and check `$.id` and `$.status` rather than using `contains`. This example only highlights client TLS configuration.

**This truststore specifies trusted certificates; it is not "trust all".** Ensure hostname verification remains active and include negative tests in the real HTTP client environment.

## 6. Never use trust-all or bypass hostname verification

Online snippets often show a `TrustManager` accepting all certificates or "relaxed HTTPS validation" to get past self-signed certificates in tests.

Doing so strips HTTPS tests of value:

- Accepts spoofed, expired, or out-of-policy certificates.
- Masks mismatches between URL hostname and SAN.
- Fails to verify the consumer's truststore is configured correctly.
- Risks being copied into staging/production code.
- Can keep CI green even when real TLS connections would fail.

**The right approach:** use a known test CA or certificate, load it into the specific HTTP client's truststore, keep hostname verification enabled, and add negative tests that fail on wrong trust or hostname.

| Scenario | Expected outcome |
| --- | --- |
| Valid test certificate + `localhost` in SAN | TLS succeeds |
| Truststore does not trust server cert/CA | TLS handshake fails |
| URL host missing from SAN | Hostname verification rejects |
| HTTPS client connects to HTTP port | Protocol/TLS error before HTTP matching |
| Valid TLS but wrong URL path | HTTP request fails to match stub |
| Trust-all enabled accidentally | Negative tests expose the flaw by still connecting |

You do not need a full production PKI to test with WireMock. You must, however, **keep identity verification principles intact**.

## 7. RestTemplate, RestClient, WebClient, and Feign

There is no single Spring Cloud Contract property that automatically configures TLS for every HTTP client. Identify the **actual HTTP transport** the consumer uses.

| HTTP client | Where to supply TLS trust material |
| --- | --- |
| Java `HttpClient` | Instance `SSLContext` |
| `RestTemplate` | `ClientHttpRequestFactory` / underlying HTTP transport |
| Spring `RestClient` | Request factory or client builder |
| Spring `WebClient` | `ClientHttpConnector` / Reactor Netty SSL context |
| OpenFeign | Underlying HTTP client implementation/transport used by Feign |
| Discovery-backed client | Also scheme, URI, secure flag, and port on `ServiceInstance` |

Merely changing one property:
 
~~~yaml
orders:
  base-url: "https://localhost:8443"
~~~

**is not enough** if the client does not yet trust the certificate. Likewise, configuring a truststore for Java `HttpClient` does not change WebClient or Feign if they use a different transport.

### WebClient / Reactor Netty

With Spring WebFlux, you can supply a test CA/certificate PEM when building Reactor Netty's `SslContext`:

~~~java
import io.netty.handler.ssl.SslContext;
import io.netty.handler.ssl.SslContextBuilder;
import java.io.File;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

File certFile = new File(
    "src/test/resources/tls/wiremock-local.crt"
);

SslContext testSsl = SslContextBuilder.forClient()
    .trustManager(certFile)
    .build();

HttpClient nettyClient = HttpClient.create()
    .secure(spec -> spec.sslContext(testSsl));

WebClient client = WebClient.builder()
    .clientConnector(new ReactorClientHttpConnector(nettyClient))
    .baseUrl("https://localhost:" + stub.httpsPort())
    .build();
~~~

This is a client configuration skeleton; your project needs appropriate dependencies, lifecycle management, and error handling. With your version of Reactor Netty, **verify that hostname verification is genuinely enabled when using a custom SSL context**; some ways of building SSL handlers require enabling it explicitly. Using `trustManager(certFile)` alone does not prove hostname verification ran.

### RestTemplate and RestClient

These clients typically use a `ClientHttpRequestFactory`. The HTTPS truststore must be supplied to the **HTTP library behind the request factory**, such as Apache HttpClient, JDK transport, or another library.

APIs differ between Apache HttpClient 4 and 5, and across Spring Boot versions. Check the exact version in your project before configuring; never copy an "SSL socket factory" snippet from a different dependency blindly.

### Feign and service discovery

With `@FeignClient(name = "orders-api")`, the client may use Spring Cloud LoadBalancer to pick a server. Beyond the TLS truststore, verify:

1. Service ID `orders-api` resolves to the right stub instance.
2. The instance exposes an **HTTPS scheme/HTTPS port** and secure metadata if required by the client.
3. Feign actually uses the transport configured with certificate trust.
4. No silent fallback occurs to staging/production services.

If Feign is configured with a **static URL**, the test bypasses service discovery. That can be useful for an isolated HTTPS test, but do not claim discovery was verified in that case.

## 8. Dynamic ports, CI, and hostnames in containers

With `dynamicHttpsPort()`, WireMock uses an OS-assigned HTTPS port. Never hardcode `8443` in consumer tests; read the port from WireMock and pass it into client configuration.

~~~text
WireMockServer.start()
    |
    +--> WireMockServer.httpsPort()
    |
    +--> https://localhost:<httpsPort>
    |
    +--> HTTP client configured with truststore
    |
    +--> Consumer assertions
    |
    +--> WireMockServer.stop()
~~~

In Spring Boot integration tests, register the dynamic URL via `@DynamicPropertySource`, provided the server starts before Spring reads properties:

~~~java
// Sketch: "stub" is an already-started WireMockServer
// whose lifecycle is managed in the test class.
@DynamicPropertySource
static void register(DynamicPropertyRegistry registry) {
    registry.add("orders.base-url",
        () -> "https://localhost:" + stub.httpsPort());
}
~~~

**Container note:** `localhost` inside a consumer container is not the WireMock container. If the actual URL is `https://wiremock:8443`, the certificate needs `DNS:wiremock` in its SAN. Do not disable hostname verification just to make Docker runs pass; fix the certificate and test DNS/networking properly.

A reproducible pattern is choosing a resolvable test hostname, generating a certificate whose SAN includes that host, having CI supply the truststore path, and using dynamic ports when sharing hosts.

## 9. Standalone WireMockServer vs. WireMock inside Stub Runner

In Spring Cloud Contract, HTTP stubs are typically packaged by artifact coordinates, and **Stub Runner** starts the stub server. However:

| Execution mode | Who manages the server | TLS considerations |
| --- | --- | --- |
| `new WireMockServer(...)` in JUnit | Test code | Can directly enable HTTPS listener, keystore, and port |
| WireMock JUnit extension | Extension | Configure TLS via extension options |
| Spring Cloud Contract **Stub Runner** | Stub Runner | TLS depends on support and config of Stub Runner/WireMock version |
| WireMock behind a test TLS proxy | Proxy + test infrastructure | TLS is tested on consumer–proxy leg; upstream may be HTTP |

Example Stub Runner ID:

~~~java
@AutoConfigureStubRunner(
    ids = "com.example.orders:order-service:1.4.2:stubs:8090",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
~~~

The ID here specifies only the **stub artifact and port in Stub Runner syntax**. It **does not guarantee** the server on 8090 uses HTTPS.

Do not guess properties like `spring.cloud.contract.stubrunner.https.enabled` without checking whether your plugin version supports them. Changing `http://localhost:8090` to `https://localhost:8090` in consumer configuration **does not turn an HTTP listener into HTTPS**.

### When your Stub Runner version does not support the needed HTTPS setup

Split the verification into clear tests:

1. **Producer contract tests** prove the producer fulfills the described HTTP methods/statuses/bodies.
2. **Consumer tests via HTTP Stub Runner** verify consumer logic against the right stub artifact.
3. **Consumer HTTPS tests via a dedicated `WireMockServer`** verify the HTTP client's TLS configuration using the corresponding HTTP scenario.
4. Where needed, **integration tests in a real test environment** verify ingress/proxy/mTLS setup.

Placing a **TLS reverse proxy** in front of HTTP WireMock can also be a test option, provided you document clearly: the HTTPS handshake tests the proxy, **not that upstream WireMock runs HTTPS**.

## 10. mTLS: verifying both directions

Standard HTTPS performs server authentication: the client trusts the server's certificate. With **mutual TLS (mTLS)**, the server also requires the client to present a certificate.

~~~mermaid
flowchart LR
    A["Consumer"] -->|"Verify server cert + hostname"| B["WireMock HTTPS"]
    B -->|"If mTLS: verify client cert"| A
    C["Client truststore"] --> A
    D["Server keystore"] --> B
    E["Client keystore (mTLS)"] --> A
    F["Server truststore (mTLS)"] --> B
~~~

For genuine mTLS evidence:

- WireMock server is configured to **require** client authentication.
- Server truststore holds the CA/certificate used to verify clients.
- Client holds a matching test private key and certificate.
- Client still verifies the server certificate and hostname.
- Negative tests with **missing client cert**, wrong cert, or untrusted cert must fail.

With JDK `SSLContext`, mTLS typically requires adding a `KeyManagerFactory` from the client keystore to pass key managers into `init(...)`:

~~~java
// mTLS sketch, not complete code:
// KeyManagerFactory kmf = ...; // from test client keystore
// TrustManagerFactory tmf = ...; // trusts server certificate
// tlsContext.init(kmf.getKeyManagers(),
//                 tmf.getTrustManagers(), new SecureRandom());
~~~

A passing one-way HTTPS test **does not prove** mTLS is enabled. WireMock's client-certificate enforcement must be verified against that version's API.

## 11. Layered debugging

| Symptom | Where to check first | Common root cause |
| --- | --- | --- |
| `PKIX path building failed` | Truststore/chain | Client does not trust server certificate/CA |
| `No subject alternative names` | Certificate SAN | Host in URL does not match certificate identity |
| `SSLHandshakeException` | TLS config | Trust, TLS version, cipher, or client auth |
| `NotSslRecordException`, `wrong version number` | Protocol/port | Sending HTTPS to an HTTP port |
| `Connection refused` | Network/lifecycle | WireMock not started, wrong port, or wrong bind address |
| TLS succeeds, HTTP 404 | WireMock mappings | Wrong method, path, query, headers, or body |
| Test calls staging server | Discovery/base URL | Not pointing at the right stub instance |
| Local PASS, Docker CI FAIL | Hostname/DNS/SAN | `localhost` vs. container hostname mismatch |
| Passes only with relaxed SSL | Client security | Certificate/hostname verification disabled |
| CI passes with stale stub | Artifact version | Not consuming stubs from the latest producer build |

Diagnostic flow:

~~~mermaid
flowchart TD
    A["Consumer HTTPS test"] --> B{"Does WireMock have an HTTPS listener?"}
    B -->|No| X["Configure server TLS"]
    B -->|Yes| C{"Host + HTTPS port correct?"}
    C -->|No| Y["Fix URL / discovery"]
    C -->|Yes| D{"Certificate trusted and SAN valid?"}
    D -->|No| Z["Fix certificate/truststore"]
    D -->|Yes| E{"TLS handshake succeeds?"}
    E -->|No| U["Check TLS policy/mTLS"]
    E -->|Yes| F{"Request matches stub?"}
    F -->|No| V["Check method/path/headers/body"]
    F -->|Yes| G["Assert consumer behavior"]
~~~

When the TLS handshake fails, the request usually **never reaches HTTP matchers**, so WireMock serve events may contain no request entry. Tweaking regexes or body matchers will not fix a handshake failure.

## 12. What must CI prove?

A pipeline can separate HTTP compatibility and HTTPS client behavior into distinct verification gates:

~~~mermaid
flowchart TD
    A["Reviewed Groovy/YAML Contracts"] --> B["Generate producer contract tests"]
    B --> C{"Producer tests PASS and not skipped?"}
    C -->|No| X["BLOCK"]
    C -->|Yes| D["Generate/publish versioned stub artifact"]
    D --> E["Consumer test via Stub Runner"]
    E --> F{"Consumer assertions PASS?"}
    F -->|No| X
    F -->|Yes| G["HTTPS WireMock client integration test"]
    G --> H{"TLS trust/SAN and HTTP assertions PASS?"}
    H -->|No| X
    H -->|Yes| I["Archive evidence and evaluate rollout"]
~~~

Reports can record:

~~~yaml
# Example project-designed evidence record.
producer_revision: "order-service@abc123"
contracts_revision: "contracts@def456"
stub_artifact: "com.example.orders:order-service:1.4.2:stubs"
consumer_revision: "checkout-service@cde789"
wiremock_https_enabled: true
test_hostname: localhost
test_certificate_san:
  - "DNS:localhost"
test_truststore: "wiremock-client-trust.p12"
hostname_verification_checked: true
producer_contract_tests: PASS
consumer_stub_tests: PASS
https_client_integration_tests: PASS
~~~

Never put passwords or private keys into evidence records. A claim like `hostname_verification_checked: true` is only credible when backed by **negative tests** or actual verification checks. Results must also be tied to the exact producer build, stub artifact version, consumer commit, and test configuration.

**State the scope:** HTTPS with WireMock proves connectivity to the configured test endpoint; it does not prove that production ingress TLS/certificates are properly managed or that every consumer is compatible.

## 13. Practice exercises

### Exercise A — Picking the right port

WireMock runs HTTP on `10876` and HTTPS on `11443`. The consumer calls `https://localhost:10876/api/orders/ORD-1001` and hits a TLS error.

**Task:** fix the URL, explain why `stub.port()` cannot substitute for `stub.httpsPort()`, and add JSON assertions.

**Hint:** use `https://localhost:11443`, an appropriate test truststore, and assert status 200 and `status: PAID`.

### Exercise B — Wrong certificate SAN

The server holds a certificate with SAN `DNS:localhost`; the consumer container calls `https://wiremock:8443`.

**Task:** explain why a valid truststore still fails and propose a safe fix.

**Hint:** generate a test cert with `DNS:wiremock` or align the hostname/URL with the SAN. Never disable hostname verification.

### Exercise C — TLS succeeds, yet 404

The HTTPS handshake succeeds. The stub defines only `GET /api/orders/ORD-1001`, while the consumer sends `GET /api/orders/ORD-9999`.

**Task:** identify which layer failed and where to investigate.

**Hint:** HTTP WireMock mapping, not TLS; check the request journal and method/path/headers/body.

### Exercise D — Truststore and server keystore

A teammate commits a copy of a production private key into the test repository and lets every client use it to connect over HTTPS.

**Task:** list the risks and propose a remediation.

**Hint:** use a dedicated test keypair, distribute only the public CA/cert to clients, protect private keys, and enforce proper permissions.

### Exercise E — Stub Runner opens HTTP only

The consumer requires HTTPS. The current Stub Runner version runs a plain HTTP stub server.

**Task:** propose a way to verify both HTTP contracts and the HTTPS client without falsely claiming Stub Runner opened TLS.

**Hint:** run Stub Runner for HTTP compatibility and a dedicated HTTPS `WireMockServer` for the TLS client; or verify and use an HTTPS option supported by your Stub Runner version.

### Exercise F — Negative TLS test

An HTTPS test PASSes after enabling relaxed SSL, yet FAILs when using a narrow truststore.

**Task:** is there enough evidence to ship this HTTPS configuration? List the next steps.

**Hint:** not yet. Configure a valid server cert/SAN and client truststore, enable hostname verification, and test both valid and invalid certs/hostnames.

## 14. Checklist before signing off on HTTPS tests

- [ ] Separated TLS test goals from HTTP contract goals.
- [ ] WireMock runs an actual **HTTPS listener**, not just mappings.
- [ ] Client uses `httpsPort()`, not `port()`.
- [ ] Server certificate is a **test certificate** and uses no production private key.
- [ ] URL hostname/IP matches the certificate's SAN.
- [ ] Client trusts the test CA/certificate via a narrowly scoped truststore.
- [ ] Hostname verification is enabled and covered by negative tests.
- [ ] Trust-all or relaxed HTTPS validation is not used as TLS evidence.
- [ ] RestTemplate/RestClient/WebClient/Feign actually uses an HTTP transport with proper TLS config.
- [ ] With discovery/load balancing, instance scheme and port are HTTPS-compatible.
- [ ] With mTLS, the server enforces client certificates and has negative tests.
- [ ] Dynamic ports, hostnames, and container networking are handled reproducibly.
- [ ] Handshake errors are distinguished from mapping/HTTP 404 errors.
- [ ] Stub Runner was checked for **actual HTTPS configuration support** rather than guessing properties.
- [ ] Generated producer contract tests actually run and PASS.
- [ ] Consumer tests use the right stub artifact/version and assert application logic.
- [ ] CI records evidence scope without exposing private keys or secrets.
- [ ] Production ingress TLS properties are tested separately where needed.

**Remember:** WireMock HTTPS covers **server TLS configuration and client trust/hostname verification**, whereas Spring Cloud Contract primarily protects **agreed HTTP behavior**. Reliable compatibility evidence requires verifying generated producer tests, stub/consumer behavior, and the client's HTTPS connection path—never conflating them or disabling TLS validation just to make CI green.
