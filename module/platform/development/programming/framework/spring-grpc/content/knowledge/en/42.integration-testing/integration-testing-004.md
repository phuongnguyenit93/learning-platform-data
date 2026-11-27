# Testing TLS with Test Certificates

## Learning Objectives

After this lesson, you will be able to:

- Explain the TLS handshake and the role of certificates in gRPC over HTTP/2.
- Generate a CA and server certificate dedicated to integration testing.
- Configure a Netty gRPC server to use the test certificate and its corresponding private key.
- Configure the client to trust the CA and connect using a hostname matching the Subject Alternative Name (SAN).
- Test both valid connections and cases with untrusted certificates or mismatched hostnames.
- Manage certificates, channels, and servers according to the Spring test context lifecycle.
- Distinguish server-authenticated TLS from mutual TLS (mTLS), which authenticates the client as well.

## 1. Why Test TLS Over gRPC?

gRPC uses HTTP/2 as its transport. In secure deployments, the client and server typically establish TLS before exchanging HTTP/2 frames and Protobuf messages. An integration test using plaintext only confirms that RPCs work over unencrypted transport; it does not verify the certificate chain, hostname verification, trust store, or TLS handshake.

With **SPRING_GRPC**, TLS can be configured on the starter-managed server or on the Netty server/channel. Tests need to go through the exact TLS connection path the application uses, invoke real RPCs to trigger the handshake, and confirm the client only trusts servers with valid certificates.

A channel can be constructed before any handshake takes place. Therefore, calling **build()** successfully does not prove TLS is established. Execute at least one RPC and verify the result.

## 2. What Components Make Up a Test Certificate Setup?

A server-auth TLS configuration typically consists of:

- **CA certificate**: the CA certificate trusted by the client.
- **Server certificate**: the certificate identifying the server, signed by the CA.
- **Server private key**: the private key corresponding to the server certificate.
- **Subject Alternative Name (SAN)**: the DNS name or IP address the client uses to connect.
- **Certificate chain**: the server certificate along with any intermediate certificates needed for the client to build a trust chain.

The client holds the CA certificate in its trust store. The server holds the certificate chain and private key. The server does not need the CA's private key; the CA private key is only used when signing certificates and must be protected separately.

The hostname the client uses to connect must match a SAN in the server certificate. If tests connect to **localhost**, the certificate needs **DNS:localhost**. If connecting to **127.0.0.1**, the certificate needs a corresponding IP SAN. The Common Name (CN) field does not replace SAN in modern hostname verification.

## 3. Creating a Test CA and Server Certificate

You can create a local test CA and then sign a server certificate with the **localhost** SAN. The example below requires OpenSSL support for the **-addext** option:

~~~bash
mkdir -p src/test/resources/tls
cd src/test/resources/tls

# Create a test CA. Never use this CA private key for production.
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout test-ca.key \
  -out test-ca.crt \
  -days 30 \
  -subj "/CN=Spring gRPC Test CA" \
  -addext "basicConstraints=critical,CA:TRUE" \
  -addext "keyUsage=critical,keyCertSign,cRLSign"

# Create the private key and CSR for the server.
openssl req -newkey rsa:2048 -nodes \
  -keyout server.key \
  -out server.csr \
  -subj "/CN=localhost"

# Server certificate extensions.
cat > server.ext <<'EOF'
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=DNS:localhost
EOF

# Sign the server certificate with the test CA.
openssl x509 -req \
  -in server.csr \
  -CA test-ca.crt \
  -CAkey test-ca.key \
  -CAcreateserial \
  -out server.crt \
  -days 30 \
  -sha256 \
  -extfile server.ext
~~~

Place **server.crt**, **server.key**, and **test-ca.crt** into test resources according to repository policy. **test-ca.key**, the CSR, and the serial file are only needed during certificate generation; do not commit the CA private key. Server private keys in test fixtures must never be reused in real environments.

Short-lived certificates help avoid long-lived test credentials. When certificates are generated dynamically during tests, preserve proper SAN, key usage, and extended key usage values; server certificates require **serverAuth**.

If signed via an intermediate CA, the server should send the leaf certificate along with intermediate certificates in proper chain order. The client usually only needs to trust the root CA. Do not fix chain errors by disabling certificate verification.

## 4. Starting a Netty gRPC Server with a Test Certificate

With a self-managed server fixture, the Netty server accepts the certificate chain and private key:

~~~java
import io.grpc.BindableService;
import io.grpc.Server;
import io.grpc.netty.GrpcSslContexts;
import io.grpc.netty.NettyServerBuilder;
import io.netty.handler.ssl.SslContext;
import java.io.File;
import java.util.concurrent.TimeUnit;
import org.springframework.context.SmartLifecycle;

final class TlsTestGrpcServer implements SmartLifecycle {
    private final BindableService service;
    private final File certificateChain;
    private final File privateKey;
    private volatile Server server;

    TlsTestGrpcServer(
            BindableService service,
            File certificateChain,
            File privateKey) {
        this.service = service;
        this.certificateChain = certificateChain;
        this.privateKey = privateKey;
    }

    @Override
    public synchronized void start() {
        if (server != null && !server.isShutdown()) {
            return;
        }
        try {
            SslContext sslContext = GrpcSslContexts
                .forServer(certificateChain, privateKey)
                .build();

            server = NettyServerBuilder.forPort(0)
                .sslContext(sslContext)
                .addService(service)
                .build()
                .start();
        } catch (Exception ex) {
            throw new IllegalStateException(
                "Cannot start TLS gRPC test server", ex);
        }
    }

    int port() {
        Server current = server;
        if (current == null || current.isShutdown()) {
            throw new IllegalStateException("TLS gRPC server is not running");
        }
        return current.getPort();
    }

    @Override
    public synchronized void stop() {
        Server current = server;
        server = null;
        if (current == null) {
            return;
        }
        current.shutdown();
        try {
            if (!current.awaitTermination(5, TimeUnit.SECONDS)) {
                current.shutdownNow();
            }
        } catch (InterruptedException ex) {
            current.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }

    @Override
    public boolean isRunning() {
        Server current = server;
        return current != null && !current.isShutdown();
    }
}
~~~

**forServer(...)** creates the TLS context from the certificate chain and private key. **forPort(0)** lets the OS allocate a dynamic port; the test reads the actual port after the server has started.

This fixture is for tests that manage their own server. If the Spring gRPC starter already starts the server, configure TLS on the starter-managed server and use the starter's test support to get the port. Do not create a second Netty server for the same service just to test TLS.

## 5. Registering the Fixture in the Spring Test Context

The test configuration can inject the service bean and certificates from test resources:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class TlsGrpcTestConfiguration {
    @Bean
    TlsTestGrpcServer tlsTestGrpcServer(
            GreeterServiceImpl greeter) throws IOException {
        File cert = new ClassPathResource("tls/server.crt").getFile();
        File key = new ClassPathResource("tls/server.key").getFile();
        return new TlsTestGrpcServer(greeter, cert, key);
    }
}
~~~

Using **ClassPathResource.getFile()** works when test resources are unpacked as files on the test classpath. If tests run from an archive where resources lack a filesystem path, copy the resource to a temporary file and delete it when the context closes.

With Spring Boot, **@SpringBootTest** creates the context, and the **SmartLifecycle** fixture starts the server after beans are created. Spring calls **stop()** when the context closes. If the starter already registers services and the server automatically, replace the fixture with the starter's TLS configuration and port accessor; a context should only have one server lifecycle owner.

## 6. Configuring the Client to Trust the Test CA

The client uses the CA certificate as its trust anchor and connects using a hostname present in the SAN:

~~~java
File caCertificate =
    new ClassPathResource("tls/test-ca.crt").getFile();

SslContext clientSslContext = GrpcSslContexts.forClient()
    .trustManager(caCertificate)
    .build();

ManagedChannel channel = NettyChannelBuilder
    .forAddress("localhost", tlsServer.port())
    .sslContext(clientSslContext)
    .build();

GreeterGrpc.GreeterBlockingStub stub =
    GreeterGrpc.newBlockingStub(channel)
        .withDeadlineAfter(3, TimeUnit.SECONDS);
~~~

Here, the client only trusts certificate chains signed by the test CA. The hostname **localhost** must match the server certificate's SAN. Netty/gRPC performs chain and hostname verification per the TLS configuration; there is no need to disable verification for the test to connect.

Do not call **usePlaintext()** in a TLS test. Also do not use **overrideAuthority()** to hide a hostname mismatch in regular tests. If production uses special authority routing, write a dedicated test for that authority and ensure the certificate is still verified against the expected identity.

## 7. Executing an RPC to Trigger the Handshake

The TLS handshake typically happens when the channel begins connecting, not necessarily at channel creation time. Therefore, invoke an RPC to force the client to connect and verify the certificate:

~~~java
@SpringBootTest
@Import(TlsGrpcTestConfiguration.class)
class GreeterTlsIntegrationTest {
    @Autowired
    TlsTestGrpcServer tlsServer;

    private ManagedChannel channel;
    private GreeterGrpc.GreeterBlockingStub stub;

    @BeforeEach
    void connect() throws Exception {
        File ca = new ClassPathResource("tls/test-ca.crt").getFile();
        SslContext ssl = GrpcSslContexts.forClient()
            .trustManager(ca)
            .build();

        channel = NettyChannelBuilder
            .forAddress("localhost", tlsServer.port())
            .sslContext(ssl)
            .build();

        stub = GreeterGrpc.newBlockingStub(channel)
            .withDeadlineAfter(3, TimeUnit.SECONDS);
    }

    @Test
    void acceptsCertificateSignedByTrustedTestCa() {
        HelloReply reply = stub.sayHello(
            HelloRequest.newBuilder().setName("Linh").build());

        assertEquals("Hello, Linh", reply.getMessage());
    }

    @AfterEach
    void closeChannel() throws InterruptedException {
        if (channel == null) {
            return;
        }
        channel.shutdown();
        if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
            channel.shutdownNow();
        }
    }
}
~~~

Generated service, request, and response names in the example should be replaced with the types generated from your project's Protobuf files. Set a finite deadline so tests do not hang if the handshake or RPC does not complete. Channels created by tests must be shut down; servers managed by the Spring context stop when the context closes.

## 8. Testing Untrusted Certificates

A negative test should use a different CA that did not sign the server certificate. When the client invokes an RPC, the TLS handshake must fail before the business method is executed.

~~~java
File unrelatedCa =
    new ClassPathResource("tls/unrelated-ca.crt").getFile();

SslContext untrustedSsl = GrpcSslContexts.forClient()
    .trustManager(unrelatedCa)
    .build();

ManagedChannel untrustedChannel = NettyChannelBuilder
    .forAddress("localhost", tlsServer.port())
    .sslContext(untrustedSsl)
    .build();

try {
    GreeterGrpc.GreeterBlockingStub untrustedStub =
        GreeterGrpc.newBlockingStub(untrustedChannel)
            .withDeadlineAfter(3, TimeUnit.SECONDS);

    assertThrows(StatusRuntimeException.class, () ->
        untrustedStub.sayHello(
            HelloRequest.newBuilder().setName("Linh").build()));
} finally {
    untrustedChannel.shutdownNow();
}
~~~

Handshake errors are usually observed by the client as an RPC status such as **UNAVAILABLE** with the TLS error in the cause chain; exact status/message details may depend on transport and version. The primary assertion is that the RPC never reaches the service method when the trust chain is invalid.

To verify hostname verification, use a client target that differs from the SAN, such as connecting to **127.0.0.1** when the certificate only lists **DNS:localhost**. The test must fail. Do not fix the test by disabling hostname verification.

## 9. Certificate Properties to Verify

| Property | What to verify |
| --- | --- |
| Trust chain | Client trusts the CA signing the server certificate; required intermediates are sent by the server. |
| SAN | Contains the DNS/IP that the client actually uses to connect. |
| Validity | Current timestamp falls within Not Before/Not After. |
| Key pair | Private key matches the public key in the server certificate. |
| Extended Key Usage | Server certificate includes **serverAuth**. |
| Key Usage | Matches the key exchange and signature algorithms in use. |
| Chain order | Leaf certificate precedes intermediate certificates in the sent chain. |

Expired or not-yet-valid certificates must be rejected. Do not work around trust failures by arbitrarily adding leaf certificates to the trust store when the goal is to test the CA chain.

## 10. Mutual TLS When the Server Requires a Client Certificate

Server-auth TLS only authenticates the server to the client. If the system requires mTLS, the server also requires the client to present a certificate signed by a CA the server trusts.

Example server configuration requiring a client certificate:

~~~java
SslContext serverSsl = GrpcSslContexts
    .forServer(serverCertificate, serverPrivateKey)
    .trustManager(clientCaCertificate)
    .clientAuth(ClientAuth.REQUIRE)
    .build();
~~~

The client provides its own certificate and private key:

~~~java
SslContext clientSsl = GrpcSslContexts.forClient()
    .trustManager(serverCaCertificate)
    .keyManager(clientCertificate, clientPrivateKey)
    .build();
~~~

The client certificate needs an appropriate Extended Key Usage, typically **clientAuth**. The server trusts the CA that signed the client certificate. Write separate tests for:

- Valid client certificates are accepted.
- Missing client certificates are rejected.
- Client certificates signed by an untrusted CA are rejected.
- The server certificate is still verified independently by the client.

Do not enable **ClientAuth.REQUIRE** in regular server-auth tests if the client is not configured with an identity certificate.

## 11. Storing Certificates and Private Keys in Tests

Test certificates are not production secrets, but private keys still need deliberate management:

- Only place fixtures in **src/test/resources** or generate them in a temporary test directory.
- Never use production private keys or production CAs in tests.
- Do not commit CA private keys capable of signing other certificates; clients only need the CA certificate to trust.
- Restrict read permissions on private key files if tests run on shared machines.
- Do not log private key contents or full TLS handshake secrets.
- Regenerate test certificates upon expiration instead of setting infinite validity periods.

If certificates are generated at test runtime, track temporary file paths in the fixture and delete the files when the context closes. Ensure the server has shut down before deleting certificates/keys that the transport might still need.

## 12. Common Mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Using **usePlaintext()** in TLS tests | No TLS handshake is tested | Use a Netty TLS channel and trust the CA. |
| Certificate has only CN, missing SAN | Hostname verification fails | Add SAN matching the client's hostname/IP. |
| Client trusts wrong certificate/CA | Handshake fails or trust is overly broad | Trust the exact test CA and verify the chain. |
| Using **localhost** when cert only has IP SAN | Hostname mismatch | Align the target host and SAN. |
| Creating a channel without calling an RPC | Does not prove handshake succeeded | Call an RPC with a deadline to trigger connection. |
| Disabling hostname verification to pass tests | Skips server identity verification | Fix the SAN or target host properly. |
| Server omits intermediate certificate | Client cannot build trust chain | Configure the full certificate chain. |
| Using production private keys in tests | Risk of credential exposure | Generate dedicated keys for tests only. |
| Confusing server-auth TLS with mTLS | Tests do not verify client identity | Add dedicated tests with client certificates and ClientAuth.REQUIRE. |
| Stopping the server before channels or in-flight calls | Unstable test teardown | Close channels/calls, then let Spring stop the server. |

## 13. TLS Testing Matrix

A basic integration test suite should cover:

1. Trusted test CA, matching SAN: RPC succeeds.
2. Untrusted CA: handshake fails.
3. Hostname does not match SAN: handshake fails.
4. Expired or not-yet-valid certificate: handshake fails.
5. Chain missing intermediate: handshake fails when the chain requires that intermediate.
6. If mTLS is enabled: valid client certificate is accepted.
7. If mTLS is enabled: missing or invalid client certificate is rejected.
8. Channels/servers are closed per lifecycle, leaving no lingering threads or temporary files after tests.

Negative tests should verify that the service method is not invoked when the TLS handshake fails. You can use a spy/counter on the service bean to confirm the request never reached the application layer.

## 14. Hands-On Exercise

Create a TLS integration test for a Spring gRPC service:

1. Generate a test CA and server certificate with SAN **DNS:localhost** and EKU **serverAuth**.
2. Register the service implementation on a starter-managed TLS server or a Netty test fixture with Spring lifecycle.
3. Bind a dynamic port and retrieve the actual port after the server starts.
4. Create a client channel trusting the test CA, connect via **localhost**, and call a unary RPC with a deadline.
5. Verify the RPC succeeds with the valid certificate.
6. Create a client trusting a different CA and verify the handshake fails.
7. Connect using a hostname not in the SAN and verify it is rejected.
8. If the application uses mTLS, add tests for valid and invalid client certificates.
9. Shut down the channel and verify Spring stops the server when the context closes.

**Completion criteria:** tests demonstrate real TLS handshakes, trust chain and hostname verification are enforced, negative tests fail for the expected reason, and all certificates, channels, and server fixtures are lifecycle-managed.

## 15. Takeaways

- TLS tests must invoke RPCs over Netty TLS transport; building a channel alone does not prove the handshake succeeded.
- The server provides the certificate chain and private key; the client trusts the CA that signed the certificate.
- SAN must match the hostname/IP used by the client; CN does not substitute for SAN.
- Check validity, key pair, EKU, key usage, and intermediate chain.
- Never use plaintext, disable hostname verification, or trust all certificates just to make tests pass.
- Server-auth TLS and mTLS serve different goals; mTLS requires a client certificate and server trust of the client CA.
- Test certificates/private keys must be kept separate from production credentials.
- Close test channels and let Spring or the starter manage server shutdown.

Testing TLS with test certificates confirms that the gRPC server only accepts verified connections, clients trust the intended CA, and Spring safely manages the lifecycle of both the server and TLS resources.
