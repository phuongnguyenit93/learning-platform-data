# TLS, Certificates, and Connection Sessions After a Pause

Java applications commonly use TLS to protect connections to databases, APIs, message brokers, service meshes, or external services. An active TLS connection consists of multiple states on both sides: the TCP socket, TLS encryption state, session keys, record counters, protocol state, and potentially application authentication state. When CRaC creates a checkpoint, the JVM pauses execution while servers, load balancers, firewalls, DNS, certificate issuance systems, and other services continue operating.

During that pause, an open connection may be closed by the other side due to an idle timeout, the session may expire, the server may be redeployed, and certificates may be rotated. Upon restore, a Java object that still holds a reference to a socket or client does not prove that the TLS connection is still usable. The application needs to check and usually create a new connection.

It is also necessary to distinguish between a **TLS connection** and **TLS session resumption**. A TLS connection is a protected data transmission session over a specific network connection. Session resumption uses session information or a ticket to reduce authentication overhead when establishing a new TLS connection. It does not restore the old TCP socket and does not guarantee that authentication conditions, security policies, or server-side state are still valid.

In an application using CRaC, the common approach is to stop and close TLS connections before checkpoint, then after restore recreate the client or connection pool, reload the necessary authentication information, perform a new handshake, and only accept traffic when dependencies are ready.

## 1. Layers of State in a TLS Connection

When an application connects to an HTTPS service, database, or broker over TLS, there are several different layers of state:

| Layer | Examples | Can it change while the JVM is paused? |
|---|---|---|
| Network connection | TCP socket, route, NAT mapping, firewall state | Yes. Network devices or servers may time out, close, or change paths |
| Active TLS connection | Traffic keys, sequence numbers, encryption state, record layer | May no longer be usable if the socket is closed or the peer has terminated the session |
| TLS session | Session ID, session ticket, state used for resumption | Yes. The session or ticket may expire, be revoked, or be rejected by the server |
| Authentication | Server certificate, client certificate, truststore, private key | Yes. Certificates may be rotated, expire, or be revoked; trust material may change |
| Application state | HTTP request, transaction, subscription, authentication token | Yes. Business sessions and transactions may expire or be canceled by the service |

A socket may still exist on the JVM side but no longer be accepted by the peer. Conversely, a TLS session ticket may still be valid while the previous TCP connection has disappeared. These two situations require different handling.

### 1.1. Open TLS Connections

After the TLS handshake completes, both endpoints use the negotiated keys and session state to protect data. Subsequent TLS records depend on the exact state of that connection. If one side closes the socket, restarts, or forgets the connection state, the other side cannot continue exchanging data merely by keeping the socket object in the heap.

During the checkpoint period, external components may:

- Close the connection due to an idle timeout or connection lifetime limit.
- Drop the NAT mapping or firewall state due to lack of traffic.
- Route traffic to another server after the load balancer changes backends.
- Restart the service or replace the pod/container.
- Revoke the session at the application layer or require the client to re-authenticate.

Therefore, you should not assume that a TLS socket opened before checkpoint is still valid after restore. For a connection pool, close or discard open connections according to the pool's guidelines. For a client that manages sockets directly, close the socket in the before-checkpoint callback and create a new socket after restore.

### 1.2. TLS Session Resumption

TLS session resumption allows both sides to use previously established information to reduce handshake overhead when creating a new connection. Depending on the TLS version and implementation, the mechanism may use a session ID, session cache, or session ticket/Pre-Shared Key (PSK).

Key points:

- Resumption still establishes a new network connection; it does not revive the old TCP socket.
- Tickets may have an expiration time, and the server may reject a ticket due to key rotation, a restart, or a policy change.
- The client and server may no longer have compatible session state after a long pause.
- Resumption does not replace hostname verification, authentication policies, and access permissions at the application layer.
- The application must handle the case where resumption fails and a full handshake is performed again.

With TLS 1.3, the server may issue a session ticket after the handshake for the client to use in the next connection. A ticket is a handshake optimization mechanism, not a guarantee that the old connection or application identity remains accepted forever. How certificates and authentication state are verified during resumption also depends on the protocol, library, and server policy; you should not assume every resumption repeats the entire process like a fresh handshake.

If the application needs to immediately apply a new truststore or certificate after restore, consider the session cache and ticket lifetime. A new SSLContext usually creates a new session context on the client side and helps avoid reusing the cache belonging to the old context. Server-side policies still need to be configured appropriately, especially when immediate revocation or identity changes are required.

### 1.3. TLS 1.3 and 0-RTT Data

TLS 1.3 can support early data (0-RTT) during resumption. Sending data early reduces latency, but carries a replay risk in certain attack models. Therefore, operations with non-idempotent side effects such as payments, order creation, money transfers, or critical state updates should not be sent as early data if the system does not have an appropriate anti-replay mechanism.

After a pause, if the client or library automatically uses 0-RTT, check the policies of both the library and the server. For business operations with side effects, prefer a normal handshake and send the request after the connection is authenticated; also use an idempotency key at the application layer when a request might be resent.

## 2. Certificates Can Change While the JVM Is Stopped

TLS relies on digital certificates and trust chains to verify identity. Certificates have a validity period and can be rotated or revoked. The application's truststore and keystore can also be updated independently of the Java process.

### 2.1. Expired or Rotated Server Certificates

In a full handshake, the client verifies the server certificate according to the trust manager configuration and identity verification rules. Common checks include:

- The certificate chain leads to a trusted trust anchor.
- The current time falls within the certificate's validity period.
- The hostname matches the Subject Alternative Name (SAN) for the connected hostname.
- Key usage, extended key usage, and algorithms meet the security policy.
- Revocation status is checked if the application and environment have configured OCSP, CRL, or an equivalent mechanism.

If the server certificate is replaced while the JVM is stopped, new connections after restore will encounter the new certificate. If the truststore does not trust the new CA, the handshake will fail. If the hostname does not match, trusting the CA is also not enough for a secure connection.

An expired certificate does not necessarily cause an already established TLS connection to stop automatically at the exact moment of expiration. Certificate verification usually occurs during the handshake; an existing connection may continue until one endpoint closes it or an application-layer policy terminates the session. However, when reconnecting, the certificate is checked against the current time and policies of the new handshake.

That makes restore the moment when connections and authentication must be re-verified. If the application keeps the old socket, it might continue using a session that was authenticated before the certificate changed. If the application closes the socket and performs a new handshake, it will verify against the new certificate state and trust material currently in use.

### 2.2. Updated Truststore

The truststore contains the CAs or certificates trusted by the application. Many applications load the truststore when creating the SSLContext or at JVM startup. Once the trust manager has been initialized, changing the truststore file on disk usually does not automatically update the objects in the heap.

For example:

1. The JVM starts and reads a truststore containing the old CA.
2. An administrator replaces the truststore on the volume to trust a new CA.
3. The JVM continues running or is restored from a checkpoint.
4. The old SSLContext may still use the TrustManager created from the old content.
5. Connecting to a server using a certificate issued by the new CA may fail even though the truststore file on disk has been updated.

To use the new truststore, the application needs to reload the KeyStore, create a new TrustManagerFactory, and initialize a new SSLContext. Merely reopening a socket with the old SSLContext does not make the trust manager re-read the file.

### 2.3. Client Certificates and Mutual TLS

In mutual TLS (mTLS), both the client and the server verify each other's certificate. The client may need a private key and a client certificate to prove its identity to the server.

During the checkpoint period, the client certificate may be rotated, the private key may change, or the old certificate may be revoked. After restore, if the application continues using a KeyManager initialized from the old keystore, it may present a certificate that is no longer accepted by the server.

To use the new client certificate, reload the keystore, create a new KeyManagerFactory, and initialize a new SSLContext with both key managers and trust managers. Private keys must be protected; do not write them to logs and do not embed secrets into the checkpoint image if they can be retrieved from a secret manager after restore.

### 2.4. Certificate Revocation and Revocation Status Checking

A certificate can be revoked before its expiration date. OCSP or CRL checking depends on the TLS provider configuration, trust manager, application policy, and reachability of the revocation checking service.

Do not assume that simply creating a new connection causes every Java implementation to check revocation status in the same way. Verify the actual revocation checking configuration. If the trust manager or provider caches OCSP/CRL results, understand the cache lifetime and how to refresh it after restore.

If security policy requires revocation to take effect immediately, align the lifetime of TLS sessions, session tickets, caches, and connections with that requirement. Session resumption can change how the handshake handles authentication; deciding whether to allow resumption must align with the system's identity verification policy.

## 3. How Does Pause Duration Affect Connections?

The JVM does not process callbacks, heartbeats, or requests while the process is stopped for checkpointing. Meanwhile, the system clock and external services continue running. This elapsed time can expire many states:

- TCP connections closed due to idle timeout.
- Connection pools evicting connections due to max lifetime.
- TLS sessions or tickets expiring.
- Access tokens expiring.
- Certificates passing `notAfter` or not yet reaching `notBefore` according to the current clock.
- Login sessions or application-layer leases expiring.
- DNS records or load balancer backends changing.
- Servers redeploying and no longer holding the previous session cache.

Upon restore, use the current time to determine valid state. Do not continue using an in-heap timer counter or boolean flag to conclude that a token, session, or lease is still valid.

The system clock is also critical for certificate verification. If the restore machine has an incorrect clock, a certificate may be treated as not yet valid or already expired even though the certificate content has not changed. The deployment environment needs synchronized time, and the application needs to handle verification errors in a diagnosable way.

## 4. TLS Information That Needs Refreshing After Restore

Not every TLS component needs to be recreated in every application. The decision depends on how the client and library manage state. The table below serves as a guide for classification:

| Component | Action typically needed after restore | Reason |
|---|---|---|
| Open TCP/TLS socket | Close before checkpoint, create a new connection after restore | The peer, firewall, or NAT may have closed the old state |
| HTTP/database/broker connection pool | Drain and close the pool, create a new pool | The pool may hold many old sockets and old authentication state |
| SSLContext | Consider creating a new one if truststore, keystore, or policies may have changed | TrustManager, KeyManager, and session cache are initialized with the context |
| Truststore | Reload when CA or trust policy is rotated | File changes on disk do not automatically update an already created trust manager |
| Keystore and private key | Reload when client certificate or key is rotated | An old KeyManager may continue presenting the old certificate |
| TLS session cache/ticket | Check expiration and resumption policy | Sessions may expire or no longer fit the new policy |
| DNS and endpoint | Re-resolve hostname when creating a new connection | The backend or IP address may have changed |
| Application-layer token | Refresh or re-authenticate | Tokens may expire independently of TLS |
| ALPN and protocol policy | Renegotiate when creating a new connection | The server or configuration may have changed supported protocols |

An SSLContext can be used to create multiple connections. If the application keeps the old context and only creates new sockets, the new connections may still use old trust/key material and the old session cache. When certificate or truststore changes need to be picked up, recreate the context from the current configuration source.

## 5. Managing TLS with a CRaC Resource

A resource responsible for managing TLS can implement `org.crac.Resource` and register with the global context:

~~~java
Core.getGlobalContext().register(tlsResource);
~~~

`beforeCheckpoint()` should:

1. Stop accepting new requests or messages through the managed client.
2. Wait for in-flight requests to complete within a defined timeout.
3. Flush or complete any necessary operations per the application protocol.
4. Close TLS sockets and pool connections.
5. Clear references to old connection state to prevent business code from reusing them.

`afterRestore()` should:

1. Re-read endpoint, truststore, and keystore configurations if they may have changed.
2. Create new KeyManagerFactory and TrustManagerFactory when needed.
3. Initialize a new SSLContext according to the current TLS policy.
4. Create a new connection pool or socket and perform the handshake.
5. Verify hostname, certificates, mTLS, and application authentication state.
6. Only open readiness when required dependencies are ready.

Callbacks are only lifecycle coordination points. Closing a pool must follow the library's API; do not manually close an underlying socket of an HTTP client while the client still holds a reference to that connection. If the library already has CRaC integration, use the supported integration and avoid managing the same resource twice.

## 6. Example: Recreating SSLContext and TLS Socket After Restore

The example below illustrates a client connecting to a TLS service using a custom truststore. The resource closes the socket before checkpoint. After restore, it re-reads the truststore path and password from environment configuration, creates a new TrustManagerFactory, creates a new SSLContext, and performs a new TLS handshake.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.GeneralSecurityException;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.util.Arrays;

import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.TrustManagerFactory;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class TlsConnectionResource implements Resource {
    private final String host;
    private final int port;
    private SSLSocket socket;
    private SSLContext sslContext;

    public TlsConnectionResource(String host, int port)
            throws Exception {
        this.host = host;
        this.port = port;

        openConnection();
        Core.getGlobalContext().register(this);
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws IOException {
        closeConnection();
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        openConnection();
    }

    private synchronized void openConnection() throws Exception {
        SSLContext freshContext = createSslContext();
        Socket transport = new Socket();
        SSLSocket candidate = null;

        try {
            transport.connect(
                    new InetSocketAddress(host, port),
                    5_000
            );

            candidate = (SSLSocket) freshContext.getSocketFactory()
                    .createSocket(transport, host, port, true);
            transport = null; // The TLS socket has taken ownership of the underlying socket.

            candidate.setSoTimeout(5_000);

            SSLParameters parameters = candidate.getSSLParameters();
            parameters.setEndpointIdentificationAlgorithm("HTTPS");
            candidate.setSSLParameters(parameters);

            // Perform the handshake before publishing the connection as ready.
            candidate.startHandshake();

            this.sslContext = freshContext;
            this.socket = candidate;
        } catch (Exception failure) {
            try {
                if (candidate != null) {
                    candidate.close();
                } else if (transport != null) {
                    transport.close();
                }
            } catch (IOException closeFailure) {
                failure.addSuppressed(closeFailure);
            }
            throw failure;
        }
    }

    private SSLContext createSslContext()
            throws IOException, GeneralSecurityException {
        String trustStoreLocation =
                System.getenv("TLS_TRUSTSTORE");
        if (trustStoreLocation == null
                || trustStoreLocation.isBlank()) {
            throw new IllegalStateException(
                    "TLS_TRUSTSTORE is not configured");
        }

        String passwordValue =
                System.getenv("TLS_TRUSTSTORE_PASSWORD");
        char[] password = passwordValue == null
                ? new char[0]
                : passwordValue.toCharArray();

        try {
            KeyStore trustStore =
                    KeyStore.getInstance(KeyStore.getDefaultType());

            try (InputStream input = Files.newInputStream(
                    Path.of(trustStoreLocation))) {
                trustStore.load(input, password);
            }

            TrustManagerFactory trustManagers =
                    TrustManagerFactory.getInstance(
                            TrustManagerFactory.getDefaultAlgorithm());
            trustManagers.init(trustStore);

            SSLContext context = SSLContext.getInstance("TLS");
            context.init(
                    null,
                    trustManagers.getTrustManagers(),
                    new SecureRandom()
            );
            return context;
        } finally {
            Arrays.fill(password, '\0');
        }
    }

    private synchronized void closeConnection() throws IOException {
        SSLSocket current = socket;
        socket = null;
        sslContext = null;

        if (current != null) {
            current.close();
        }
    }
}
~~~

Notable points:

- The resource creates the initial connection and then registers with the global context.
- Before checkpoint, the TLS socket is closed and fields referencing the old connection are cleared.
- After restore, the truststore is re-read from the current path and a new SSLContext is created.
- A new TCP socket is opened with a connection timeout, then wrapped with an SSLSocket.
- Endpoint identification is enabled with the HTTPS algorithm so that the service's hostname is verified during the handshake.
- The connection is only assigned to the resource after the handshake completes.
- If the connection or handshake fails, the socket being created is closed and the error is propagated to the callback.

The example uses a custom truststore and assumes the truststore format matches `KeyStore.getDefaultType()`. In a real system, explicitly configure the keystore type, path, secret provider, algorithms, and TLS policy. The password in the example is only to illustrate loading configuration; `String` environment variables can still remain in the heap. For sensitive secrets, retrieve them from a secret manager using an appropriate mechanism and limit how long copies are kept in memory.

The example also does not configure a client certificate for mTLS. If the server requires a client certificate, load a keystore containing the private key and client certificate, create a `KeyManagerFactory`, and pass the key managers as the first argument to `SSLContext.init()`. Do not use a truststore in place of a keystore: the truststore defines the CAs/certificates the client trusts, whereas the keystore provides the identity and private key that the client can present.

In the example, endpoint identification uses HTTPS. If connecting to another TLS protocol, use the corresponding hostname verification mechanism of that client or protocol library. Do not disable hostname verification to work around certificate errors; fix the hostname, SAN, or trust configuration properly.

## 7. HTTP Clients, Databases, and Connection Pools

In real applications, TLS sockets are often managed indirectly by an HTTP client, JDBC driver, or broker client. The CRaC resource should manage the highest-level object that the library declares as the lifecycle owner.

### 7.1. HTTP Clients

An HTTP client may hold a connection pool, TLS session cache, DNS cache, executor, and open HTTP/2 connections. After restore, an old client may still hold references to connections that the peer has closed or to an old SSLContext.

Approach:

- Stop sending new requests and wait for in-flight requests to finish.
- Close or stop the client according to the API of the JDK/library version in use.
- Create a new client with a new SSLContext if the truststore, keystore, or TLS policy may have changed.
- Re-resolve the hostname and negotiate ALPN when new connections are created.
- Perform a health check before opening readiness.

Do not assume every version of `java.net.http.HttpClient` has the same client-closing API. For example, lifecycle APIs differ across JDK versions. Use the exact API provided by the specific JDK or library.

### 7.2. JDBC and Database Clients

A JDBC connection pool may hold TLS sockets to the database. Before checkpoint, drain transactions and close connections and the pool according to the pool's instructions. After restore, create a new pool so the driver establishes new TLS connections.

If the database uses a rotated CA or server certificate, ensure the driver receives the new truststore. A new pool that still uses an old SSLContext or old trust configuration may continue to fail. Check how the JDBC driver loads the truststore and SSLContext; some drivers have separate configurations or internal caches.

Open transactions are not guaranteed to continue after restore. Complete or roll back transactions before checkpoint and use a transaction ID, idempotency, or an appropriate recovery mechanism if the commit outcome is uncertain.

### 7.3. Message Brokers and Service Meshes

A broker client may hold TLS connections along with consumer groups, heartbeats, and subscriptions. Before checkpoint, stop consumers and handle acknowledgments according to policy. After restore, create new connections, re-authenticate, re-register subscriptions, and verify group state.

In a service mesh environment, TLS may be terminated or re-initiated at the sidecar/proxy. Certificate and connection pool lifecycles may belong to the proxy rather than the application. Determine precisely where TLS is terminated so the application's resource does not attempt to close a resource managed by the sidecar.

## 8. Hostname, SNI, DNS, and ALPN After Restore

A TLS connection does not only verify the CA. Server identity is also tied to the hostname, and the handshake may negotiate the application protocol.

### 8.1. Hostname Verification and SNI

The client needs to verify that the server name matches a SAN in the certificate. The server may use Server Name Indication (SNI) to select the certificate matching the hostname requested by the client.

When reconnecting:

- Use the configured service hostname instead of a fixed IP if the architecture requires name-based routing.
- Ensure the client sends the appropriate SNI.
- Keep hostname verification enabled.
- If the service changes its name or the certificate changes its SAN, update the configuration and test the handshake.

A new connection to the right IP without sending the right SNI or without verifying the hostname can still be insecure.

### 8.2. DNS and Load Balancers

While the JVM is stopped, DNS records may change and the load balancer may shift endpoints to other backends. A client holding old connections does not automatically re-resolve DNS. When creating new connections, check TTLs, DNS caches, and how the library resolves hostnames.

Do not assume that creating a new socket always means DNS is queried again; some HTTP clients or resolvers have their own caches. If you need to pick up new endpoints after restore, check and configure caching according to the client's documentation.

### 8.3. ALPN and TLS Versions

Application-Layer Protocol Negotiation (ALPN) allows both sides to negotiate a protocol such as HTTP/2 or HTTP/1.1 during the TLS handshake. The server or proxy may change supported protocols while the JVM is stopped. A new connection will renegotiate according to the current configuration.

If the application depends on HTTP/2, gRPC, or a specific protocol, verify the negotiation result after restore. At the same time, only allow TLS versions and cipher suites that comply with the organization's security policy; do not downgrade protocols just to make the handshake succeed.

## 9. Handling Handshake Errors and Readiness

TLS connections can fail after restore for many reasons:

| Error or situation | Possible cause | Handling approach |
|---|---|---|
| Certificate expired | Server or client certificate has expired | Issue/deploy new certificate and recreate TLS context |
| PKIX path building failed | Truststore lacks required CA or chain is incomplete | Update truststore and verify certificate chain |
| Hostname mismatch | SAN does not match hostname client connects to | Fix hostname or certificate; keep hostname verification |
| Handshake timeout | Server not ready, slow network, or route changed | Finite timeout, retry with backoff, and health check |
| Peer closed connection | Server, proxy, or firewall closed the old socket | Create a new connection and verify peer state |
| Client certificate rejected | Old mTLS keystore or certificate, wrong EKU, or revoked | Load new key material and check server-side policy |
| Session resumption rejected | Ticket expired, cache lost, or server state changed | Allow library to fall back to a full handshake |
| Unknown CA | Server switched to a CA not yet trusted by client | Update trust chain from a trusted source |
| Protocol/cipher mismatch | Client and server no longer share a common protocol suite | Align TLS policy and server/client configuration |
| DNS resolution failure | DNS or endpoint not yet ready | Bounded retry and check resolver |

`afterRestore()` may run while the database, broker, or API is not yet ready. Do not retry infinitely inside the callback. Use timeouts, backoff, jitter, and a clear readiness state. If the TLS connection is a mandatory dependency, the instance should only accept traffic after the handshake and required verifications have succeeded.

If some services are not required for every request, they can be recovered asynchronously after the JVM restores. In that case, readiness must accurately reflect the application's processing capability; do not mark as ready when a critical business flow still cannot connect.

## 10. Pre-Checkpoint and Post-Restore Workflow

A general workflow:

### Before checkpoint

1. Stop accepting new requests or messages on TLS clients that are about to be closed.
2. Drain in-flight requests, transactions, and operations within a time limit.
3. Complete or roll back transactions; ensure requests can be safely retried if the outcome is unknown.
4. Close the connection pool, HTTP client, broker client, or socket according to the supported lifecycle API.
5. Release sessions and authentication state that cannot be safely reused.
6. Bring the application into a checkpointable state.

### After restore

1. Re-read endpoints, DNS policy, truststore, keystore, and secrets if these configurations may have changed.
2. Create new TrustManagerFactory and KeyManagerFactory when needed.
3. Initialize a new SSLContext if trust/key material or session policy needs refreshing.
4. Create a new client or connection pool.
5. Perform TLS handshake, hostname verification, mTLS, and ALPN negotiation.
6. Refresh application-layer tokens and re-register sessions/subscriptions.
7. Run health checks and only open readiness when mandatory dependencies are ready.

Overall flow:

~~~mermaid
flowchart TD
    A[Application using TLS connection] --> B[Stop accepting new requests]
    B --> C[Drain requests and transactions]
    C --> D[Close client, pool, and socket]
    D --> E[CRaC checkpoint]
    E --> F[Pause duration]
    F --> G[Restore JVM]
    G --> H[Read current configuration and certificates]
    H --> I[Create new SSLContext/client]
    I --> J[TLS handshake and hostname verification]
    J --> K[Refresh application tokens and sessions]
    K --> L[Health check]
    L --> M[Readiness and accept traffic]
~~~

The actual order depends on relationships between clients, pools, token providers, and services. For example, if a client needs a secret manager to load certificates, the secret manager must be ready before the client recovers. If multiple resources depend on each other, register them in the appropriate callback order.

## 11. Testing TLS When the Pause Duration Is Long

Testing only with immediate checkpoint and restore is not enough to simulate operational scenarios. Test across various durations and change external system state while the JVM is stopped.

Some scenarios to test:

- The server closes idle connections while the JVM is stopped. Does the client create a new connection after restore?
- The session ticket expires. Does the client fall back to a full handshake?
- The server replaces its certificate with one issued by a new CA. Does the client load the new truststore and verify properly?
- The mTLS client certificate is rotated. Does the client load the new key material?
- The certificate expires during the pause. Does the new connection fail with a diagnosable error?
- The server revokes a certificate or changes authentication policy. Does the client apply the corresponding revocation/session policy?
- DNS points to a new backend. Does the client resolve and connect to the right endpoint?
- The load balancer or service mesh changes TLS/ALPN configuration. Does the client renegotiate successfully?
- The machine clock changes or drifts. Are `notBefore`/`notAfter` errors detected and handled properly?
- The database or broker is not ready after restore. Does the application keep readiness in the appropriate state?
- A request is resent after its pre-checkpoint outcome was uncertain. Does the idempotency mechanism prevent duplicate effects?
- Multiple replicas restore from the same checkpoint. Does each replica create its own connections and sessions?

Record the checkpoint time, restore time, handshake timestamp, TLS version, ALPN result, and verified certificate details. Do not log private keys, passwords, tokens, or sensitive content.

## 12. Assumptions to Avoid

| Assumption | Reality |
|---|---|
| Keeping a socket in the heap means the connection is still alive | The peer, NAT, firewall, or server may have closed the connection |
| TLS session resumption restores the old socket | Resumption establishes a new connection and only optimizes the handshake |
| An expired certificate immediately cuts all open connections | Certificates are usually verified during the handshake; existing connections may continue until closed or terminated by another policy |
| Replacing the truststore on disk automatically updates SSLContext | An already initialized TrustManager usually keeps old state; you must reload and create a new context |
| Creating a new socket is enough to pick up a new certificate | A new socket may still use the old SSLContext and trust/key manager |
| All TLS tickets remain valid after restore | Tickets have an expiration time and the server may reject them or no longer hold state |
| A successful handshake means application tokens are still valid | Application-layer tokens, sessions, and access permissions have their own lifecycles |
| TLS 1.3 0-RTT is safe for all requests | Early data carries replay risk; operations with side effects need separate policies |
| DNS will automatically refresh on restore | Resolvers or clients may cache DNS; check cache policies |
| Hostname verification can be disabled to fix errors | Doing so removes a critical layer of identity verification |

## 13. Design Principles

- Treat TLS sockets and connection pools as resources that can become invalid during checkpointing.
- Close connections via the client or pool API before checkpoint; do not close internal sockets still managed by the library.
- Create new connections after restore and verify the hostname.
- Reload the truststore/keystore and create a new SSLContext when certificates, CAs, or policies may have changed.
- Distinguish between a truststore (trusted CAs) and a keystore (private key and client identity).
- Treat session resumption as an optimization that can fail; do not rely on tickets for correctness.
- Do not use 0-RTT for business operations with side effects without appropriate replay protection.
- Refresh application-layer tokens and sessions independently of TLS.
- Use timeouts, bounded retries, backoff, and readiness to manage unavailable services.
- Test with pause durations, certificate rotation, DNS changes, and network failures resembling the deployment environment.

CRaC helps the JVM resume quickly from a checkpoint, but external time still passes and TLS participants can still change state. Applications need to separately manage the lifecycle of sockets, TLS sessions, certificates, trust/key material, and business tokens. Closing old connections before checkpoint, recreating the SSLContext or client when needed, performing a new handshake, and verifying dependencies before serving will help the application avoid relying on stale security sessions.
