# Managing Secrets and Certificates in Spring Integration Adapters

## 1. Production Context: External Connections Mean Managing Trust

In the **SPRING_INTEGRATION_ADAPTERS** module, Spring Integration applications connect external systems via **inbound/outbound adapters**, **gateways**, **pollers**, and **`MessageChannel`**. A single flow might fetch files over SFTP, write to JDBC, call a partner HTTP API, publish to JMS/AMQP/Kafka, and return a response. To operate reliably in production, every connection boundary must answer two independent questions:

1. **Are we connecting to the authentic target system over a protected channel?**
2. **Is the application identity authorized to perform that action?**

That is why **secrets** and **certificates** must be designed as first-class parts of integration architecture, rather than just a few config strings.

A leaked DB password can expose or alter business tables. A leaked API token enables forged outbound requests. An expired server certificate can halt thousands of HTTP/SFTP requests across pollers. A misconfigured truststore can make clients reject legitimate servers—or worse, accept spoofed servers if operators disable verification as a temporary workaround.

### Learning Objectives

After this lesson, learners will be able to:

1. Distinguish **secret, credential, private key, public key, certificate, truststore, keystore, CA**, and how SSH differs from TLS.
2. Identify authentication credentials and trust material for File, SFTP, HTTP, JMS, AMQP, Kafka, and JDBC adapters.
3. Source secrets outside source code with environment isolation, clear ownership, and least-privilege permissions.
4. Design **TLS/mTLS**, hostname verification, certificate chains, and SFTP host-key verification at the right boundaries.
5. Execute **rotation/renewal** with overlap windows, connection reloads, and safe rollbacks.
6. Monitor expiry, authentication errors, TLS handshakes, pinning, secret exposure, and incident response.
7. Write integration tests covering secret/certificate lifecycles rather than only happy-path connections.

**Guiding principle:** this guide teaches how to structure security for real systems; examples contain zero real passwords, tokens, or private keys. Provider- and version-specific details must be verified against the corresponding adapter, driver, and broker APIs.

## 2. Terminology to Distinguish

| Concept | Nature | What to Protect / Verify |
|---|---|---|
| Secret | Data that must never leak | Passwords, API keys, tokens, private keys, SASL credentials |
| Credential | Proof of identity | Passwords, bearer tokens, SSH key pairs, client certificates |
| Public key | Public half of a key pair | Must bind to the right subject; does not need secrecy |
| Private key | Secret half of a key pair | Strictly protected, never logged/committed; may reside in HSM |
| X.509 certificate | Binds a public key to subject/SAN and validity window | Verify signature, chain, target name, key usage |
| CA | Certificate issuer/signer | Trust only approved CAs/anchors |
| Truststore | Set of trust anchors/certificates trusted by a client | Never confuse with private keys used for client authentication |
| Keystore | Store holding keys and certificates for an identity | Protect private key access and store passphrase |
| TLS | Transport security protocol | Peer authentication, encryption, integrity, version/cipher policy |
| mTLS | TLS authenticating both client and server via certificates | Both sides must validate peer identity |
| SSH host key | Public key authenticating an SSH/SFTP server | Verify fingerprint/`known_hosts` against exact target |
| SSH client key | Key pair authenticating an SSH user/client | Keep private key secret; register public key on server |
| OAuth access token | Bearer or proof-of-possession token granting API access | Scope, lifetime, storage/renewal |
| SASL | Authentication framework used by Kafka/brokers | Specific credentials and mechanisms, usually paired with TLS |

### 2.1. Certificates Are Not Always Secrets

Public certificates can generally be shared openly. **The paired private key is what must stay secret**. Even so, trust anchors, hostname/fingerprint pinning lists, and related config files require integrity protection: swapping a trusted CA allows accepting spoofed peers.

### 2.2. mTLS Does Not Replace Authorization

An HTTP client presenting a valid certificate proves an accepted identity, yet **is not automatically authorized to call every endpoint or access every tenant**. Enforce separate authorization by principal, scope, role, resource, and business contract.

### 2.3. SFTP Uses SSH, Not HTTPS-Style X.509 TLS

SFTP runs over SSH. **SSH host key verification** (`known_hosts`/fingerprints) is not **TLS certificate chain verification**. Nor is an SSH private key for client authentication an mTLS PEM certificate chain, even though both use public/private key concepts.

Never use a generic "trust all certificates" mindset to fake SFTP host-key checking; each protocol must verify peers in its own way.

## 3. Secret and Certificate Map Across Adapters

| Adapter / Boundary | Material Required | Target to Verify | Primary Risks |
|---|---|---|---|
| Local File | Filesystem permissions, storage encryption keys if used | Path, ownership, permissions | Reading wrong/sensitive files, symlinks, overly broad permissions |
| SFTP inbound/outbound | SSH private key or password; passphrase if set | SSH server host key, partner identity | MITM, unapproved host-key changes, leaked private key |
| HTTP outbound | API tokens, OAuth client credentials; client cert/key for mTLS | Server TLS certificate, SAN/hostname | Token leak, trust-all TLS, excessive scope |
| HTTP inbound gateway | Server TLS private key/cert; client CA if mTLS | Client certificate, OAuth/JWT if used | Lost server key, missing client auth, wrong tenant routing |
| JMS | Broker credentials, provider-specific TLS key/trust material | Broker certificate, auth principal | Wrong broker connection, expired password, stalled listeners |
| AMQP/RabbitMQ | Username/password or other RabbitMQ auth; TLS certs | RabbitMQ broker, client cert if required | Leaked credentials, overly broad vhost permissions |
| Kafka | SASL credentials/OAuth tokens or client certs; TLS trust | Bootstrap brokers and broker connections | Broken auth, wrong principal, rotating broker cert errors |
| JDBC | DB credentials/tokens/certificates | DB server certificate and hostname | Exposed DB privileges, failover endpoint TLS mismatch |
| Secret manager | Workload identity or controlled bootstrap credentials | Secret manager endpoint and IAM policy | Leaked bootstrap token, overly broad read access |

Configuring TLS on **only one side** is insufficient. Understand which endpoint acts as client vs. server, where TLS terminates (app, reverse proxy, service mesh, broker), and whether hops behind termination also require protection.

### 3.1. A `MessageChannel` Does Not Provide Transport Security

Inside one application, `DirectChannel` or `QueueChannel` passes messages between endpoints; security lives at **the adapters and application boundaries**. When messages cross HTTP/Kafka/SFTP, secrets and TLS guarantees belong to the corresponding connection factories, clients, and servers.

Never assume every hop in an `IntegrationFlow` shares the same credentials, CAs, or authorization policies.

### 3.2. Example Flow

~~~mermaid
flowchart LR
    SFTP["Partner SFTP"] --> S["SFTP inbound adapter"]
    S --> CH["MessageChannel"]
    CH --> DB["JDBC outbound"]
    DB --> HTTP["HTTP outbound gateway"]
    HTTP --> K["Kafka outbound"]
    SEC["Secret manager + identity"] -. "SSH key + known_hosts" .-> S
    SEC -. "DB credential + DB CA" .-> DB
    SEC -. "OAuth token / mTLS" .-> HTTP
    SEC -. "SASL/TLS material" .-> K
    AUDIT["Audit + metrics"] -. "metadata, never secrets" .-> SEC
~~~

This diagram shows **separate security contexts**. Never create a single "super integration" account shared across SFTP, DB, HTTP, and Kafka.

## 4. Threat Model and Asset Classification

### 4.1. Common Threats

- **Credential leakage:** tokens exposed via Git, Docker images, CI logs, app logs, traces, exceptions, actuator dumps, or heap snapshots.
- **Machine impersonation / MITM:** disabling hostname/host-key checks or trusting overly broad roots.
- **Privilege escalation:** DB accounts granted DDL/admin when the adapter only needs narrow SELECT/UPDATE.
- **Cross-environment access:** production credentials accidentally reused in staging.
- **Long-lived access:** tokens or SSH private keys with no lifecycle, never revoked after partner changes.
- **Compromised supply chain:** secret files baked into artifacts, backups, or widely readable images.
- **Availability failure:** expired certificates, unannounced CA rotations, or secrets revoked before consumers reload.
- **Replay/misrouting:** messages retried under the wrong tenant or service credentials.

### 4.2. Asset Inventory

Every connection should maintain a record:

| Field | Example Description |
|---|---|
| Connection ID | `sftp-orders-partner-b` |
| Owner | Integration team + partner system owner |
| Environment | `production` |
| Adapter and direction | SFTP inbound |
| Authentication type | SSH public-key |
| Secret reference | Secret manager path/ID—never raw values |
| Trust reference | Pinned/approved host key or `known_hosts` path |
| Rotation policy | Cadence aligned with risk classification and contract |
| Expiry / review | Certificate/token expiration date or key review date |
| Blast radius | Flows/tenants impacted if credentials stop working |
| Revocation owner | Who holds revocation authority on client and server sides |

### 4.3. Least-Privilege Principles

- Use **distinct identities per workload, partner system, and environment** where appropriate.
- Grant SFTP accounts access only to required folders—never shell or admin rights unless needed.
- Scope DB accounts to specific schemas/tables/operations—never default superuser.
- Restrict Kafka principals via ACLs to exact topics/groups; restrict AMQP users to exact vhosts/exchanges/queues.
- Scope OAuth tokens tightly by audience, scope, and lifetime—never share one token across unrelated APIs.
- Restrict secret manager IAM policies so each workload reads only its assigned secret references.

### 4.4. Separation of Duties

**Security/PKI teams** govern CAs, policies, and issuance; **platform teams** manage secret delivery/workload identity; **integration owners** manage flows and operational health; **partner owners** coordinate partner rollovers. In smaller orgs one team may wear multiple hats, yet **approvals and audit trails** must stay explicit.

## 5. TLS, mTLS, and Certificate Trust Chains

### 5.1. What Must a Client Verify?

When connecting to an API/DB/broker, a TLS client must verify at minimum:

1. Server certificate chain leads to an accepted trust anchor.
2. Certificate is within its validity window and complies with policy.
3. Certificate matches the target hostname/service identity, typically via **SAN**, not just CN.
4. Key usage and cryptographic algorithms satisfy policy.
5. Revocation rules where infrastructure/policy mandates revocation checks.

**Never check only expiration.** A valid, unexpired certificate belonging to another hostname must not be trusted as the target server.

### 5.2. Server and Client in mTLS

~~~mermaid
sequenceDiagram
    participant C as Spring Integration HTTP client
    participant S as Partner HTTPS server
    C->>S: ClientHello
    S-->>C: Server cert chain + TLS handshake
    Note over C: Validate chain, SAN/hostname, validity, policy
    S-->>C: CertificateRequest if mTLS required
    C->>S: Client certificate + proof of private key
    Note over S: Validate client cert, trust, mapped identity
    C->>S: Protected HTTP request
    S-->>C: Protected HTTP response
~~~

Conceptual diagram; exact handshake messages depend on TLS version. Private keys are **never transmitted over the network** during TLS handshakes; clients prove key possession cryptographically.

### 5.3. Certificate Chains and CA Rotation

Servers typically present leaf certificates plus intermediates; clients hold trusted root anchors. Missing intermediates or unannounced CA swaps break handshakes. During CA rotation, maintain an approved **trust overlap window** where clients trust both old and new chains before retiring the old CA.

Never dump "all public CAs" into an internal truststore just to silence a chain error. Overly broad trust roots expand your attack surface.

### 5.4. Truststores Differ from Keystores

| Scenario | Truststore | Keystore / Key Material |
|---|---|---|
| HTTP outbound TLS | CA trusting server | No client key needed for server-auth-only TLS |
| HTTP outbound mTLS | CA trusting server | Client private key + client certificate chain |
| HTTP inbound TLS | Per server infrastructure | Server private key + server certificate chain |
| HTTP inbound mTLS | CA trusting client | Server key/cert and client identity mapping |
| Kafka/AMQP/JMS TLS | CA trusting broker | Client key/cert if broker requires mTLS |
| JDBC TLS | CA trusting DB | Client key/cert if driver/server requires |

JKS, PKCS#12, PEM, or HSM/PKCS#11 are merely **storage formats/backends**. File format does not prove a certificate belongs to the right peer, that keys haven't leaked, or that hostname verification is active.

### 5.5. Revocation, Pinning, and Clocks

- **Revocation:** certificates revoked before expiry may require CRL/OCSP or alternative revocation mechanisms per policy; support depends on the TLS stack.
- **Pinning:** pinning a leaf fingerprint can trigger outages on every partner renewal; if pinning is mandatory, design overlap pins and out-of-band verification workflows.
- **Clock skew:** drifted clocks skew `notBefore`/`notAfter` checks. Synchronize production time and monitor clock drift errors.
- **Short-lived certificates:** cut exposure windows but demand reliable automated issuance and reloads.

### 5.6. Never Disable Verification as a "Quick Fix"

Workarounds like trust-all `TrustManager`s, disabling hostname verification, accepting arbitrary SSH host keys, or downgrading TLS to plaintext **are not valid fixes**. Diagnose the broken CA, SAN, chain, expiry, system clock, or identity mapping and fix the root cause.

## 6. Fetching and Provisioning Secrets: Keep Secrets Out of Artifacts

### 6.1. Four Common Provisioning Sources

| Source | Advantages | Risks / Caveats |
|---|---|---|
| Runtime-injected environment variables | Easy deployment integration | Can leak via process inspection, crash dumps, support tools; hard to reload |
| Read-only files / mounted volumes | Supports PEM/keystores; controlled updates | File permissions, mount timing, atomic updates and reloads |
| Secret manager API | IAM policies, audits, versioning, rotation lifecycles | Bootstrap identity, network dependency, caching, quotas, outages |
| HSM/KMS or managed identities | Keeps private keys inside hardware/service boundaries | Provider integration, latency, lifecycle, cost |

**No source is safe by default if mismanaged.** Environment variables can still be read by authorized processes/tools. Mounted files can leak via image layers, backups, or loose permissions. Secret managers can be read by over-privileged workload identities.

### 6.2. Distinguish Bootstrap Identity from Application Secrets

When an app fetches secrets from a secret manager, it needs credentials to authenticate first. Never solve that by hard-coding a **long-lived bootstrap root token** inside the JAR. Prefer short-lived workload/deployment identities scoped by audience/role and automatically revoked when the workload terminates.

Conceptual sequence:

~~~mermaid
sequenceDiagram
    participant W as Application workload
    participant IAM as Workload identity issuer
    participant SM as Secret manager
    participant A as SFTP/DB/HTTP adapter
    W->>IAM: Request runtime identity/attestation
    IAM-->>W: Short-lived policy-scoped credential
    W->>SM: Read authorized secret reference
    SM-->>W: Permitted secret version
    W->>A: Initialize connector with in-memory or mounted secret
    A-->>W: Connection result
~~~

This diagram does not imply copying secrets into logs or persisting plaintext caches. Design session lifetimes, cache TTLs, and reload hooks intentionally.

### 6.3. One Source of Truth per Credential

Establish clear conventions:

- Every secret has an **owner, scope, environment, version, rotation policy**, and lifecycle state (`active`/`deprecated`/`revoked`).
- Applications store **references or config paths**, never raw secret values.
- During rotation, multiple versions may be **simultaneously valid over an overlap window**.
- Secret access binds to specific workload roles—never wildcard access across environments.
- Never commit real secrets into tutorial YAML, shared docs, Git, tickets, or test fixtures.

### 6.4. Separate Secret from Non-Secret Configuration

**Non-secret:** hostnames, ports, topics, queues, channel names, retry policies, timeouts, trust references (depending on org classification).

**Secret:** passwords, API keys, refresh tokens, OAuth client secrets, SASL passwords, SSH private keys, TLS private keys, private-key passphrases.

Some metadata such as tenant IDs, private endpoints, or file paths may still be classified sensitive by your org even when not authentication secrets—apply appropriate data classification and read controls.

### 6.5. Secrets Can Expire While the App Is Running

If an app reads secrets only at startup and holds connectors open for weeks, a new version in the secret manager **does not automatically propagate to open sessions**. Plan explicit refresh/reconnect strategies per adapter instead of assuming updating the secret reference suffices.

## 7. Spring Boot and Spring Integration Configuration Conventions

### 7.1. Never Hard-Code Credentials in `IntegrationFlow`

Never put passwords in Java code, PEM private keys in `String` literals, or tokens into logs/exceptions. An integration flow should depend on **securely configured connection factories and client beans**:

~~~text
Configuration properties
        |
        +--> Secret references / mounted key material
        |
        v
Validated connector configuration
        |
        +--> SFTP session factory
        +--> HTTP client / request factory / gateway
        +--> JMS/AMQP connection factory
        +--> Kafka producer/consumer factory
        +--> JDBC DataSource/pool
        |
        v
Spring Integration endpoints + MessageChannels
~~~

### 7.2. YAML Holds Placeholders and References Only

~~~yaml
integration:
  partner-b:
    sftp:
      host: sftp.partner.example
      port: 22
      username: order-importer
      private-key: file:/run/secrets/sftp-client-key
      known-hosts: file:/etc/integration/ssh/known_hosts
    http:
      base-url: https://api.partner.example
      ssl-bundle: partner-b-client
      oauth-client-registration: partner-b
  jdbc:
    credential-reference: prod/integration/orders-db
~~~

This is an **illustrative application-specific schema**; Spring Boot/Spring Integration does not automatically bind keys under `integration.partner-b` unless your app defines property binding. URLs use example domains, not real endpoints. File paths reference locations rather than inline keys; enforce tight filesystem permissions on secret files.

### 7.3. Spring Boot SSL Bundles for PEM

In modern Spring Boot versions supporting **SSL bundles**, you can define a PEM bundle referencing certificate/private-key/trust-anchor files and **wire that bundle into supported HTTP clients or adapters**.

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        partner-b-client:
          keystore:
            certificate: file:/run/secrets/partner-client-chain.pem
            private-key: file:/run/secrets/partner-client-key.pem
          truststore:
            certificate: file:/etc/integration/ca/partner-server-ca.pem
~~~

Here:

- **Keystore** holds the client certificate chain and private key for mTLS client authentication;
- **Truststore** holds the certificates/CAs used to verify the server;
- **Bundle name** is purely a config reference—it **does not automatically apply** to every `RestTemplate`, `WebClient`, Kafka, or SFTP connector.

**Important:** declaration syntax, bundle wiring APIs, and live reload support vary by Spring Boot version and client library. Configure each HTTP client/connection factory explicitly; if a connector lacks direct bundle support, bridge it using your version's supported APIs.

### 7.4. Typed Configuration Properties and Validation

Example using Spring Boot `@ConfigurationProperties` for **non-secret metadata**:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "integration.partner-b")
public record PartnerConnectionProperties(
        Sftp sftp,
        Http http) {

    public record Sftp(
            String host,
            int port,
            String username,
            String privateKey,
            String knownHosts) {}

    public record Http(
            String baseUrl,
            String sslBundle,
            String oauthClientRegistration) {}
}
~~~

This is a structural model omitting binding/validation wiring. In real code, enable/scan configuration properties, validate required fields, and **never dump the whole object to logs/actuators** if secret fields are ever added later. The record holds String references, not private-key bytes.

### 7.5. Do Not Confuse Log Masking with Secret Protection

Masking passwords with `******` in logs plugs only one leak vector. Also secure:

- Actuator endpoints and access controls over configuration/environment views;
- Debug logs in HTTP/JDBC clients, broker libraries, and connection URLs;
- Exception serialization, tracing tags, and heap/thread dumps;
- Customer-support config export workflows;
- Build logs, CI variables, artifact caches, and deployment manifests;
- Process/runtime filesystem permissions and backups.

## 8. HTTPS Inbound/Outbound: TLS, mTLS, and OAuth

### 8.1. HTTP Outbound Gateway: Verify Server Before Sending Credentials

An HTTP outbound gateway may use `RestTemplate` or another configured client. The client must validate the server TLS chain and hostname before transmitting `Authorization` headers over the protected channel. **Never transmit Bearer tokens to mismatched hostnames or untrusted redirect targets**.

Checklist:

1. Enforce **HTTPS** URLs per policy;
2. Manage and update server-verification trust roots safely;
3. Keep hostname/SAN verification enabled;
4. For mTLS, ensure client private key/cert match the partner and scope;
5. Scope OAuth clients/tokens tightly by audience, scope, and expiry;
6. Ensure HTTP redirects, proxies, and retries never leak `Authorization` headers to other hosts;
7. Configure timeouts and idempotency so retries never duplicate side effects.

### 8.2. HTTP Inbound Gateway: Where TLS Terminates

When APIs sit behind a reverse proxy, ingress controller, or service mesh, TLS often terminates at that edge. Applications must clarify:

- Who owns the server private key and certificate?
- Is traffic from proxy to app still encrypted and authenticated?
- How is client certificate identity (if mTLS) passed to the backend over a trusted channel?
- Could clients spoof headers to impersonate certificate principals if the backend trusts raw headers?
- At which layer is endpoint/tenant authorization enforced?

When the application terminates TLS directly, key/cert lifecycles belong to app server config. When a proxy terminates TLS, define proxy ownership and rotation workflows without neglecting internal hops.

### 8.3. mTLS and OAuth Complement Each Other

**mTLS** authenticates the connection or workload identity; **OAuth**/JWT expresses scopes and API permissions. Holding a valid client certificate does not inherently permit calling `/admin`. Conversely, never send a valid token over an unverified server connection. Combine both as required rather than treating them as interchangeable.

### 8.4. Token Lifecycles

A long-running integration flow needs:

- Token caching scoped by expiry and audience without logging refresh credentials;
- Proactive refresh **before expiry** with safety margins and thread synchronization under concurrency;
- Strict isolation so one tenant's tokens/refresh tokens never serve another tenant;
- Clear distinction between 401 (expired token) and 403 (insufficient permissions);
- Alerts when Identity Providers or token endpoints fail;
- Safeguards ensuring queued tasks/retries do not carry stale revoked tokens too long.

### 8.5. Structural HTTP Sample

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class PartnerOrderPublisher {

    private final PartnerApiClient partnerApiClient;

    public PartnerOrderPublisher(PartnerApiClient partnerApiClient) {
        this.partnerApiClient = partnerApiClient;
    }

    @ServiceActivator(inputChannel = "partnerOrders")
    public void publish(Message<OrderCommand> message) {
        OrderCommand command = message.getPayload();
        partnerApiClient.sendOrder(command);
    }
}

interface PartnerApiClient {
    void sendOrder(OrderCommand command);
}

record OrderCommand(String orderId, String partnerId) {}
~~~

This snippet illustrates **separating business logic from credential plumbing**. `PartnerApiClient` must be backed by an HTTPS client enforcing TLS verification, token suppliers/mTLS credentials, and idempotency policies. The snippet does not build a secure client by itself—configure that explicitly before use.

## 9. SFTP: Managing SSH Private Keys and Server Host Keys

### 9.1. Distinguish Both Authentication Directions

**Server authentication:** the SFTP client confirms it is talking to the partner's authentic SSH server, typically via **`known_hosts` or approved host-key fingerprints**.

**Client authentication:** the SFTP server verifies a username/password or proof-of-possession of the SSH private key matching a registered public key.

These two checks are independent. Possessing a valid client private key **does not make the connection safe if server host-key checking is disabled**.

### 9.2. Provisioning Trusted Host Keys

Obtain partner fingerprints/host keys via **verified out-of-band channels** (authenticated admin portals, approved change requests). Store them in `known_hosts` or equivalent config bound to the exact hostname and port. Never auto-accept a host key on first untrusted connection when strong peer authentication is required.

### 9.3. Conceptual SFTP Session Factory Configuration

~~~text
SftpSessionFactory
  host: sftp.partner.example
  port: 22
  user: integration-reader
  client private key: /run/secrets/sftp-client-key
  private key passphrase: from secret manager if needed
  known hosts: /etc/integration/ssh/known_hosts
  host key verification: ENABLED
  session cache: bounded + reconnect/recreate strategy
~~~

Exact Java API names vary across Spring Integration generations (especially when underlying SSH libraries change). **Never copy an old example and disable host-key checking when errors appear**; consult docs for your exact Spring Integration SFTP and SSH client versions.

### 9.4. Rotating Client SSH Keys

1. Generate a new key pair in an approved environment; keep the private key out of repos.
2. Register the **new public key** with the partner while keeping the old key active during overlap.
3. Update the secret reference and trigger the connector to open **new sessions** with the new key.
4. Verify download/upload/read-only permissions and host-key verification.
5. Confirm all instances have switched; revoke the old public key on the SFTP server.
6. Purge old keys from secret stores/backups per retention rules and audit the change.

### 9.5. Rotating Server Host Keys

When the server changes its SSH host key, clients must verify the new key **out-of-band before accepting it**. You can stage `known_hosts` with both old and new keys where supported by client/policy, roll out gradually, and drop the old key afterward.

**Never wipe `known_hosts` or set `allowUnknownKeys=true` in production just to restore connectivity**, as that strips SSH server authentication.

### 9.6. SFTP Pollers, Caches, and Session Lifetimes

Existing open sessions keep running even after a private key file on disk rotates; the new key takes effect when **new sessions open**. With `CachingSessionFactory`, verify cache eviction/reconnects and adapter lifecycles during rotation. Check:

- Are any cached sessions holding old credentials?
- Could closing/refreshing sessions interrupt mid-flight transfers?
- Do pollers back off cleanly on auth failures?
- Are file filters/metadata affected by restarts?
- Can two client key versions coexist during transition?

**Never treat one successful poll tick as proof that every cached session switched to the new key.**

## 10. JMS: Broker Authentication, TLS, and Listener Lifecycles

### 10.1. JMS Has No Single Universal TLS Property Set

JMS is a messaging API. Configuring TLS, truststores, mTLS, and authentication depends on **ActiveMQ, IBM MQ, Artemis, or your specific provider**. Spring Integration JMS inbound/outbound adapters usually wrap an already-configured **JMS `ConnectionFactory`** or listener container.

Split responsibilities cleanly:

- **Provider `ConnectionFactory`:** broker URL, TLS trust/key material, auth mechanisms, reconnect policies.
- **Spring Integration JMS adapter:** destinations, inbound/outbound mapping, channels, ack/transactions, and error handling.
- **Secret manager:** supplies credential/keystore references and supports rotation.

### 10.2. Mandatory Tests

| Scenario | Expected Outcome |
|---|---|
| Valid broker cert, matching hostname | TLS handshake succeeds |
| Broker cert signed by untrusted CA | Connection rejected; no plaintext fallback |
| Valid cert with wrong hostname | Connection rejected per policy |
| Username/password revoked | Authentication fails; alerts target right identity |
| New client cert during overlap | New connections use new identity |
| Old client cert revoked | New connections reject old key |
| Broker failover | Failover endpoint still undergoes full verification |
| Listener reconnect after rotation | Container recovers cleanly without duplicate side effects |

### 10.3. Connection Pooling and Stale Credentials

A JMS `ConnectionFactory`/pool can hold long-lived authenticated physical connections. **Updating passwords/keystores in the secret store does not automatically refresh existing open connections.** Plan controlled connection closes/reopens or rolling restarts, verifying redelivery/transaction safety for in-flight messages.

### 10.4. JMS Authorization

Broker users/principals should only read/write their designated queues/topics. Never share one admin account across all inbound/outbound adapters. During credential swaps, test ACLs and identity mapping—not just TLS handshakes.

## 11. AMQP/RabbitMQ: Connection Factories, Vhosts, and TLS

### 11.1. Three Layers of Protection

1. **Transport:** TLS and broker certificate validation.
2. **Authentication:** username/password, client certificates, or RabbitMQ-supported mechanisms.
3. **Authorization:** vhosts, exchanges, queues, and fine-grained permissions.

Connecting successfully to RabbitMQ as an admin user **does not mean your setup follows least privilege**.

### 11.2. Conceptual Configuration

~~~yaml
spring:
  rabbitmq:
    host: rabbitmq.internal.example
    port: 5671
    virtual-host: /orders
    username: order-integration
    ssl:
      enabled: true
    # Passwords and trust/key material are injected via secret/config systems.
    # Never commit plaintext passwords in YAML files.
~~~

This illustrates common Spring Boot properties for Spring AMQP; **never assume simply enabling SSL enforces hostname verification or custom trust anchors across all versions**. Cross-check Spring Boot/Spring AMQP versions, SSL bundles, or RabbitMQ Java client config, and test that invalid certificates fail.

### 11.3. Credential Rotation and Reconnection

When rotating RabbitMQ passwords or certificates:

- Provision new credentials with matching least-privilege permissions;
- Roll out new instances gradually to prevent reconnect storms;
- Watch connection/channel counts, unacked messages, and consumer recovery;
- Ensure consumers do not lose messages when connections close;
- Revoke old credentials only after verifying zero usage and overlap completion;
- Verify publisher confirms/returns and DLX/DLQ behavior throughout rotation.

### 11.4. Do Not Mistake TLS Errors for Broker Backpressure

Handshake failures happen during connection setup. A publish timeout typically points to broker flow control, network issues, or slow consumers—not necessarily expired secrets. Use accurate error taxonomies and metrics so you don't trigger pointless password rotations.

## 12. Kafka: `SASL_SSL`, `SSL`, and ACLs

### 12.1. Two Common Models

**SSL + client certificate:** Kafka brokers authenticate clients via TLS certificates when configured; requires client key/cert and truststore.

**`SASL_SSL`:** TLS secures the transport while SASL authenticates principals via mechanisms like SCRAM or OAuth per broker/platform. Never confuse **`SASL_SSL`** with **`SASL_PLAINTEXT`**; production should enforce transport security matching policy and broker support.

Kafka supports several authentication mechanisms; exact models depend on cluster/platform setup. Never assume every Kafka cluster uses username/password or every cluster enables mTLS.

### 12.2. Sample Client Config with Placeholders

~~~properties
bootstrap.servers=kafka-1.internal.example:9093,kafka-2.internal.example:9093
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-512
ssl.truststore.location=/run/trust/kafka-client-truststore.p12
ssl.truststore.type=PKCS12
# sasl.jaas.config and truststore passwords are injected via secret sources.
# Never commit SASL usernames/passwords into properties files.
~~~

These are **illustrative Kafka client properties**, not a complete runnable config: configure JAAS/callbacks/credentials for your chosen SASL mechanism and runtime permissions. Layouts differ for PEM or SSL bundles—consult Kafka client and Spring for Apache Kafka docs for your exact version.

### 12.3. Kafka Principals and ACLs

- **Producer:** `WRITE`/`DESCRIBE` on required topics only;
- **Consumer:** `READ` on required topics and consumer groups;
- **Transactional producer:** permissions for transactional IDs if used;
- **Admin client:** administrative privileges only when explicitly required;
- **Cross-tenant:** isolate topics/ACLs, authorization, and keys per design.

A valid client certificate or successful SASL login proves only **authentication**. ACLs decide where you can publish or consume.

### 12.4. Rotating Kafka Consumer/Producer Credentials

When certificates, SASL passwords, or OAuth tokens change:

1. Inventory producer/consumer factories and active app instances;
2. Provision new credentials and ACLs ahead of rollout;
3. Roll instances in batches, refreshing/recreating clients per supported APIs;
4. Watch rebalances, consumer lag, in-flight records, and producer errors;
5. Verify Kafka offsets/acks, retries, and DLT behavior after reconnects;
6. Revoke old versions once all producers/consumers have migrated.

**Mutating Kafka client properties at runtime does not automatically reload `SSLContext` or SASL credentials inside live `KafkaProducer`/`KafkaConsumer` instances.** Use supported client refresh hooks or recreate clients.

### 12.5. Handshake Succeeds Yet Authorization Fails

If a Kafka client authenticates yet throws `TopicAuthorizationException` or `GroupAuthorizationException`, the issue is typically **ACLs or principal mapping**, not certificate chains. Never "fix" it by disabling TLS.

## 13. JDBC: Passwords, Short-Lived Tokens, and Server Verification

### 13.1. `DataSource` Owns Credentials

Spring Integration JDBC inbound/outbound adapters rely on a `DataSource`. The `DataSource`/pool governs connections, credentials, and TLS settings. Ensure:

- Each app/workload uses a DB principal restricted to required SELECT/INSERT/UPDATE privileges;
- Usernames/passwords never appear in SQL statements or logs;
- Trust CAs and hostnames match DB servers and failover endpoints;
- Explicit policies cover TLS, auth, credential expiry, and pool eviction;
- Error handlers never escalate to admin DB credentials when normal flows fail.

### 13.2. Driver-Specific TLS Configuration

Properties vary across JDBC drivers. For example, PostgreSQL JDBC offers SSL modes where **`verify-full`** validates both certificate chains and hostnames per driver rules; MySQL, SQL Server, Oracle, and others use different property names and policies.

Never assume a generic `encrypt=true` flag enforces certificate hostname verification if the driver also defaults to trusting server certificates. Test that **untrusted CAs and mismatched hostnames fail**.

### 13.3. Credential Rotation with Connection Pools

HikariCP and similar pools hold long-lived authenticated connections. When rotating passwords:

1. Ensure the DB accepts the new credential during overlap or use alternating identities;
2. App fetches the new version and opens new physical connections;
3. Gradually drain/evict older connections per pool lifecycle;
4. Avoid killing active transactions mid-flight whenever possible;
5. Validate connection health and real business queries;
6. Revoke the old credential once unused;
7. Monitor connection errors, pool exhaustion, and transaction rollbacks.

If a DB cannot hold two active passwords for one principal simultaneously, consider **dual rotating principals** or provider-supported mechanisms per governance rules. Never assume updating a secret manager password automatically keeps existing DB sessions and reconnects alive.

### 13.4. Database Failover and Certificates

When failing over to standby/replica hosts, certificates must match the service endpoint/hostname per TLS rules. Never disable verification to "help failover". Test primary, replica, DNS aliases, load balancers, and managed DB certificate models.

### 13.5. SQL Queries, `errorChannel`, and Secrets

A `DataAccessException` in a poller may publish an `ErrorMessage` to `errorChannel` depending on error strategy. Exception messages can expose SQL, DB URLs, or parameters. Error handlers should log **error category, stage, connection alias, and correlation**—never raw full stack traces on unrestricted channels.

## 14. File Adapters and Sensitive Data on Filesystems

### 14.1. File-Based Secrets Are Production Assets

File adapters process CSV, XML, JSON, or binary payloads containing sensitive data. **Connection secrets** and **business data** are separate layers, yet both require filesystem protection:

- Least-privilege owner/group permissions;
- Never write to world-readable directories or public log paths;
- Encrypt at rest per policy if required;
- Guard against symlinks, path traversal, and unsafe filenames via canonical paths;
- Use atomic write/rename or ready markers so partial files aren't read;
- Enforce clear quarantine and retention after failures;
- Restrict access to backups and archives.

### 14.2. Never Store Private Keys Inside Inboxes

If an SFTP client private key and an inbound File adapter watch overlapping directories, a loose filter can ingest the private key into your pipeline or archive. **Keep secret-material directories completely separate from inbound/outbound data directories**, and never point file pollers at secret folders or filesystem roots.

### 14.3. Keep Secrets Out of `Message` Headers

Flows attach API tokens to HTTP outbound requests, yet should avoid placing tokens inside long-lived Spring `Message` headers that can propagate into `ErrorMessage`s or logs. Let an **outbound HTTP client/token interceptor** fetch short-lived tokens narrowly at send time.

### 14.4. File Encryption Does Not Replace TLS

Files encrypted at rest still require verified SFTP/TLS during transit. Conversely, TLS in transit does not encrypt files on disk at the destination. When partners require **message-level encryption/PGP**, treat it as an extra layer with its own key lifecycle—not a substitute for SSH host-key verification.

## 15. Secret and Certificate Lifecycle

### 15.1. From Issuance to Revocation

~~~mermaid
flowchart LR
    PLAN["Request + approve"] --> ISSUE["Generate / Issue"]
    ISSUE --> STORE["Store securely"]
    STORE --> DISTR["Distribute via workload IAM"]
    DISTR --> ACT["Activate + verify"]
    ACT --> OBS["Monitor + review"]
    OBS --> ROTA["Rotate / Renew"]
    ROTA --> DISTR
    OBS --> REVOKE["Revoke / Expire"]
    REVOKE --> CLEAN["Disable + remove references + audit"]
~~~

**Issue:** generate new secrets/private keys and certificates with clear owners. **Store:** encrypted, access-controlled, audited storage. **Distribute:** deliver strictly to authorized workloads. **Activate:** connect and verify identity. **Monitor:** track expiry, failures, and usage. **Rotate:** deploy new versions with overlap. **Revoke:** disable retired versions, including on partner sides.

### 15.2. Time Dimensions

| Lifetime | Characteristics | Risk If Ignored |
|---|---|---|
| Certificate `notBefore`/`notAfter` | Validity window of the cert | New connections fail outside window |
| OAuth access token expiry | Short-lived token | 401 errors and retry storms on expiry |
| Refresh token / client secret validity | Credentials to mint new tokens | Refresh breaks during rotation |
| SSH private key policy | Keys may lack built-in technical expiry | Stale keys linger forever without policy |
| SASL / DB password policy | Enforced by broker/DB/IdP | Listener/pool reconnects fail |
| Session / connection lifetime | Connections outlive config updates | Rotated keys skip active sessions or old sessions linger |
| Trust anchor lifecycle | Accepted CAs/intermediates/host keys | Clients reject new endpoints or trust retired anchors |

### 15.3. Rotation vs. Renewal Have Different Implications

**Renewal** issues a new certificate with or without changing the key pair; **key rotation** replaces the private key. After a private-key compromise, merely renewing the certificate while **reusing the leaked key** solves nothing. Policies must specify when fresh key generation and old-key revocation are mandatory.

### 15.4. Secret Versioning

Secret managers commonly track versions:

~~~text
orders-db-credential
  version 12: previous, scheduled for revocation
  version 13: current, verified in canary
  version 14: pending (not active)
~~~

This illustrates conceptual version states; real APIs/aliases vary by secret manager. If apps point to a `latest` alias, know when aliases flip and whether runtimes reload them. Version pinning aids rollbacks, yet **never leave pins stuck on old keys indefinitely**.

### 15.5. Risk-Based Rotation Cadence

No single day count fits all secrets. Base cadence on credential type, short-lived capability, exposure risk, partner SLAs, compliance policies, and automation maturity. **Immediate rotation on suspected compromise** always overrides routine schedules.

## 16. Zero-Downtime Rotation Runbook

### 16.1. Prerequisites Before Starting

1. Inventory exact connection IDs, app instances, and affected adapters.
2. Confirm owners and revocation rights on both ends of the connection.
3. Verify whether **old and new can coexist** during overlap.
4. Confirm whether connectors reload live or require restart/recreation.
5. Capture baselines for latency, error rates, consumer lag, and poller health.
6. Prepare a canary instance or equivalent verification channel.
7. Design a **safe rollback** plan before revoking old credentials.

### 16.2. Transition Sequence

~~~mermaid
sequenceDiagram
    participant OPS as Operator / automation
    participant ID as Secret/PKI provider
    participant REM as Remote SFTP/DB/HTTP/broker
    participant APP as Integration app
    OPS->>ID: Issue version NEW
    OPS->>REM: Enable NEW identity/trust
    ID-->>APP: NEW reference available
    OPS->>APP: Canary reload/restart connector
    APP->>REM: Connect with NEW
    REM-->>APP: Auth + authorization verified
    OPS->>APP: Rollout all instances
    APP->>REM: New sessions use NEW
    OPS->>REM: Revoke OLD after verification
    OPS->>ID: Retire OLD version and audit
~~~

**Systems lacking overlap support** need tailored cutover plans (e.g., blue/green principals, dual certificate chains, controlled intake pauses, or maintenance windows). Never promise zero downtime when protocols or providers don't support overlap.

### 16.3. Per-Adapter Verification

| Adapter | Action After Injecting NEW | Proof of Cutover |
|---|---|---|
| SFTP | Open new sessions, refresh session caches | Auth succeeds with NEW; host key verified |
| HTTP outbound | Swap token supplier/`SSLContext` or rebuild client | TLS/mTLS handshake and API call succeed |
| HTTP inbound | Reload proxy/server TLS listener per infra | New clients validate chain/SAN and mTLS auth |
| JMS | Rebuild/reconnect `ConnectionFactory`/container if needed | Listeners receive/send cleanly; acks/tx healthy |
| AMQP | Recreate connections/channels per client policy | Consumers recover; zero lost unacked messages |
| Kafka | Recreate producer/consumer/streams per runtime | SASL/TLS, ACLs, lag, and offsets healthy |
| JDBC | Pool opens new connections using NEW credentials | Queries pass, pool healthy, no mass rollbacks |

### 16.4. Protecting Transactions and In-Flight Messages

If a JMS listener is mid-transaction or a poller is downloading a large file, forcefully killing connections triggers retries/redeliveries. Rotation should include **draining or graceful stops**:

- Pause new message intake where endpoints support it;
- Wait a bounded grace period for in-flight operations to finish;
- Close sessions/pools in order;
- Rebuild connection factories/clients with NEW credentials;
- Resume intake and watch recovery;
- Rely on idempotency to block duplicate effects if redeliveries happen.

### 16.5. True Rollbacks

If NEW fails, you may revert to OLD **only if OLD remains valid and uncompromised**. If OLD was compromised, never "roll back" by re-enabling the leaked key; issue a fresh safe key and follow emergency access procedures.

### 16.6. When Is It Safe to Revoke OLD?

Only when:

- All target instances/regions/tenants use NEW or are isolated;
- New connections authenticate cleanly with NEW;
- No legacy sessions remain beyond approved limits;
- Metrics and functional smoke tests pass across critical adapters;
- The owner signs off on revocation per change record;
- Post-revocation recovery paths have been reviewed.

**A passing `GET /health` is not enough** if health endpoints don't perform handshakes using the new key. Run authenticated smoke tests against every real external dependency.

## 17. Certificate Expiry, Trust Rollovers, and Renewals

### 17.1. Manage Expiry Like a Hard Deadline

Certificate inventories should track:

- Subject, SAN, issuer, serial, or reference fingerprint;
- Where used: ingress, HTTP client, broker, DB, proxy;
- `notBefore`/`notAfter` and discovery timestamp;
- Owner, renewal method, deploy schedule, and exceptions;
- CA/intermediate chains and associated trust anchors;
- Reload/restart mechanism;
- Canary/negative tests prior to expiration.

### 17.2. Verify Certificate Identity, Not Just Expiry

~~~text
Certificate checks:
  trusted chain?                 YES
  hostname/SAN match?            YES
  time valid?                    YES
  correct key usage/policy?      YES
  relevant revocation policy?    SATISFIED
  peer mapped to expected ID?    YES
~~~

This is a conceptual checklist. Revocation checking and EKU/algorithm policies vary across TLS stacks and orgs—never assume every JVM enables OCSP/CRL out of the box.

### 17.3. Two-Phase CA Rollover

1. **Client trust preparation:** update truststores/bundles to trust both old and new CAs during overlap;
2. **Server certificate switch:** switch server leaf/intermediates to the new CA;
3. **Verification:** confirm all clients/instances handshake cleanly with the new cert;
4. **Trust cleanup:** remove the old CA from truststores once unused;
5. **Audit:** confirm zero leftover trust anchors remain.

A classic mistake is swapping server certs before clients trust the new CA, knocking out every poller and client at once.

### 17.4. Certificate Pinning and Renewals

If clients pin leaf fingerprints, every renewal mints a new fingerprint and breaks connections even when the CA is trusted. Pin only when policy genuinely demands it; prefer standard CA/identity verification, or build backup pins and out-of-band rollover procedures.

### 17.5. Time Synchronization

TLS, SSH, certs, and tokens are time-sensitive. Monitor clock drift across app hosts, proxies, and brokers; enforce NTP sync per standards. Never "fix" `notBefore` failures by manually shifting system clocks.

## 18. Managing Connection Lifecycles When Secrets Change

### 18.1. Cached Secrets Do Not Equal Active Connections

A connector stack may hold state across six layers:

1. Secret reference and fetched version;
2. In-memory secret bytes;
3. `SSLContext`/SSH identity built from the secret;
4. Open connections/sessions;
5. Pool caches and in-flight messages;
6. Retry tasks retaining old credentials or sessions.

Rotation must verify **which layers updated and which didn't**. Updating a mounted secret file does not automatically rebuild `SSLContext`; rebuilding `SSLContext` does not automatically close existing sessions.

### 18.2. Refresh Behavior Matrix

| Change | What to Check |
|---|---|
| API token expires naturally | Token supplier, proactive refresh-before-expiry, thread synchronization |
| OAuth client secret changes | Token client config, refresh credentials, in-flight requests |
| Server CA changes | Client truststore/`SSLContext`, opening new connections |
| Client cert/key changes | Keystore/`SSLContext` and identity on new connections |
| SFTP SSH key changes | `SessionFactory`/cache, opening new SSH sessions |
| Broker password changes | `ConnectionFactory`/pool reconnects |
| DB password changes | `DataSource`/pool opening new physical connections |

### 18.3. Hot Reload or Rolling Restart?

**Hot reload** reduces downtime yet demands explicit library support, thread-safety under concurrent traffic, and clear rollbacks.

**Rolling restart** is often easier to reason about for libraries lacking live reloads, provided:

- Sufficient replicas/consumers stay up to serve traffic;
- Graceful stops drop zero messages;
- Health/readiness probes accurately validate external connections;
- Kafka rebalances, JMS/AMQP redeliveries, and poller leases are accounted for;
- Idempotency protects against duplicate side effects.

### 18.4. Secret Manager Failure Modes

If the secret manager becomes temporarily unreachable, define clear policy:

- Cached valid secrets: may continue operating within approved bounds;
- Expired or revoked secrets: **never keep using them just to avoid an outage**;
- Booting instances unable to fetch secrets: fail startup or readiness cleanly;
- Ongoing rotations: back off with jitter/quotas to avoid stampedes;
- Secret manager compromise: halt issuance, isolate identities, follow incident runbook.

Never extend cache TTLs infinitely during provider outages. **Availability must balance against security policy and revocation lifecycles.**

### 18.5. Long-Lived Connections and Observability

Track when credential versions apply inside the app, live connection counts per client generation (without attaching secret values), latest handshake timestamps, reload outcomes, and authentication failure rates. All traffic might quietly ride old sessions with zero fresh handshakes proving the new key actually works.

## 19. Observability: Monitoring Secrets, Certificates, and Connections Without Leaking Data

### 19.1. Measure Both Security and Availability

| Metric / Signal | Operational Value |
|---|---|
| `cert_days_until_expiry` per connection ID | Catches upcoming certificate expirations |
| `secret_rotation_age` per credential type | Spots stale unrotated secrets |
| `credential_refresh_success_total` / `failure_total` | Tracks token/password refresh health |
| `tls_handshake_failure_total` per adapter | Spots cert/trust/hostname failures |
| `ssh_host_key_verification_failure_total` | Alerts on SSH server identity changes |
| `authentication_failure_total` | Separates login errors from network faults |
| `authorization_denied_total` | Spots missing or abused roles/scopes/ACLs |
| `active_connections` per connector generation | Shows lingering legacy connections |
| `connection_reconnect_total` | Watches for reconnect storms |
| `poller_last_success_timestamp` | Confirms SFTP/File/JDBC pollers stay productive |
| `kafka_consumer_lag` / `amqp_unacked` / `jdbc_pool_wait` | Measures post-rotation backlog |
| `secret_access_denied_total` | Catches broken secret-manager IAM permissions |

Metric names are **implementation suggestions**, not guaranteed defaults from Spring Integration/Micrometer. Instrument reliable sources without embedding secret values in tags.

### 19.2. Never Put Sensitive Identifiers in Metric Labels

Labels like `accessToken` or full certificate subjects cause **high cardinality** and data leaks. Use safe labels:

- Governed connection ID;
- Adapter type and environment;
- Failure category;
- Client generation status;
- Approved certificate inventory ID.

Fingerprints/serials can help audits if classified properly, not dumped casually onto public dashboards.

### 19.3. Diagnostic Error Classification

| Observed Error | Likely Cause | First Step |
|---|---|---|
| `PKIX path building failed` | Broken chain or missing trust anchor | Inspect chain/CA/truststore |
| Certificate expired / not yet valid | `notBefore`/`notAfter` or skewed clock | Check actual cert and host clock |
| No SANs / hostname mismatch | Server identity mismatches URL | Fix server cert/SAN or endpoint URL |
| TLS handshake alert `bad_certificate` | Rejected mTLS client cert/chain/usage | Check client cert and trust policy on both sides |
| SSH host key mismatch | Server key rotated, wrong host, or MITM | Halt connections; verify fingerprint out-of-band |
| HTTP 401 | Expired token, wrong audience, bad credential | Check token issuer, expiry, and config |
| HTTP 403 | Authenticated identity lacks permissions | Check scope/policy—never disable TLS |
| Kafka authentication failed | SASL/client-cert/identity mapping fault | Check auth mechanism and secret version |
| Kafka topic authorization failed | Missing topic/group ACL | Grant least-privilege ACLs |
| JDBC login failed | Invalid password/token/principal | Check pool generation and DB auth |
| Timeout / connection refused | Network, firewall, DNS, overload | Check infra before rotating secrets |

Never turn on full exception dumps or long-lived production wire logging just to "spot a bad password". Any sensitive debugging needs formal approval, time limits, redaction, and prompt cleanup afterward.

### 19.4. Time- and Impact-Based Alerting

Configure expiry alerts **far enough ahead of expiration** to issue and roll out changes within org SLAs. Combine with:

- Pollers stuck unable to connect;
- HTTP auth error rates exceeding thresholds;
- Kafka lag or inactive consumer groups post-rollout;
- Abnormal JMS/AMQP reconnects or redeliveries;
- JDBC pools unable to open new physical connections;
- Spikes in secret manager access denials;
- Incomplete rollovers nearing OLD revocation deadlines;
- Canary failures even after publishing new certificates.

Never fire a vague "certificate expires soon" alert without connection ID, owner, issuer, environment, renewal method, and blast radius.

### 19.5. `ErrorMessage` and `errorChannel` Can Leak Secrets

When adapters/pollers throw exceptions, Spring Integration may publish an `ErrorMessage` to the default `errorChannel` or a custom error channel. `ErrorMessage` carries a `Throwable` payload and often `failedMessage`/`originalMessage`, which can contain HTTP headers, JDBC URLs, filenames, request metadata, or sensitive payloads placed in the `Message`.

Therefore:

- Never use `errorChannel` as an unfiltered sink/forwarder for credentials or sensitive messages.
- Never log raw `ErrorMessage`, `MessageHeaders`, `Throwable` messages, or payloads uninspected.
- Never ship stack traces holding tokens/passwords to unrestricted alerting tools or dead-letter topics.
- Emit structured error categories, connection IDs, adapters, correlation IDs, and redacted details.
- Protect logs, traces, metrics, and error recovery queues with strict retention and access controls.

Publishing an `ErrorMessage` **does not refresh tokens, rotate certificates, roll back transactions, or retry source messages**. Error handling must coordinate with connection lifecycles and per-adapter business state across File/SFTP/HTTP/JMS/AMQP/Kafka/JDBC.

## 20. Security and Negative Testing

### 20.1. Why Happy-Path Connection Tests Are Insufficient

A trust-all client still connects happily to a real server. An SFTP client skipping host-key checks still downloads files. An admin broker user publishes/consumes everywhere. Pair **positive tests** with **negative tests** proving untrusted peers and unauthorized calls get rejected.

### 20.2. TLS and Certificate Test Matrix

| Test Case | Setup | Expected Outcome |
|---|---|---|
| Valid TLS chain | Valid server cert, matching SAN | Connects cleanly |
| Unknown CA | Server cert signed by untrusted CA | Handshake fails; no fallback |
| Wrong hostname | Valid cert with mismatched SAN | Verification fails |
| Expired cert | Expired test fixture cert | Rejected per policy |
| Missing intermediate | Incomplete server chain | Fails when chain cannot build |
| Future `notBefore` | Cert not yet valid | Rejected; clock check verified |
| Missing client cert | mTLS server requires client cert | Authentication fails |
| Revoked client identity | Identity revoked on server/broker | New sessions rejected per mechanism |
| CA rollover overlap | Client trusts both old and new CAs | Both valid endpoints trusted |
| CA cleanup | Old CA removed post-migration | Old-CA endpoint certs rejected |

Revocation outcomes depend on **enforced policies and available revocation mechanisms**—never assume every TLS client queries OCSP/CRL automatically. Build test cert fixtures with realistic SANs, key usages, and validity dates.

### 20.3. SFTP Test Matrix

- Valid host key + valid client key → connects and executes allowed operations.
- Wrong host key → client **rejects** even with valid username/private key.
- Wrong or revoked private key → authentication fails.
- New key coexists with old key during overlap → both authenticate as planned.
- Old key revoked → **new sessions** cannot use the old key.
- Session cache refreshed → new sessions use new key without corrupting active transfers.
- Network drop mid-transfer → partial files never marked processed.

### 20.4. Secret Manager Tests

1. Correct workload identity reads only its own secret references.
2. Different or staging identities **cannot** read production secrets.
3. Secret version NEW injects cleanly into canary.
4. Secret manager unavailable → app obeys startup/runtime policy without leaking secrets.
5. Secret revoked → refresh/reconnect stops using revoked credentials.
6. Audit trails record principal, connection ID, timestamp, and action with **zero secret values**.

### 20.5. Connection Lifecycle Tests During Rotation

Tests must go beyond reading config properties after rotation—open **real new connections** and verify:

~~~text
Given OLD credential currently used by connector
And NEW credential issued and enabled at remote system
When application reloads/recreates connection client
Then new physical connection authenticates with NEW
And application can send/receive an authorized test message
When OLD is revoked
Then no new connection succeeds with OLD
And normal traffic remains healthy under NEW
~~~

This is a behavioral test scenario, not runnable code. Verify acks/offsets and redeliveries on Kafka/JMS/AMQP; verify transactions on DB; verify file lifecycles on SFTP; verify idempotency on HTTP test calls.

### 20.6. Testing That Logs Never Leak Secrets

Inject a **fake canary secret (never a real production credential)** into the test secret provider. Exercise success paths, auth-failure paths, retries, exceptions, and `ErrorMessage` flows. Assert the canary string **never appears** in app logs, tracing spans, actuator outputs, diagnostics, or serialized error events.

Never put real secrets into snapshot tests or CI artifacts. Clean up test volumes, cert fixtures, and mock-sensitive logs per policy.

### 20.7. Load and Failure Injection

When dozens of pollers/consumers rotate together:

- Do reconnect storms hit brokers or secret managers?
- Do OAuth token refresh bursts overload the issuer?
- Do any workers hold stale `SSLContext`s past deadlines?
- Does pool eviction drain DB connections dangerously low?
- Do HTTP retries duplicate side effects?
- Do broker redeliveries handle idempotently?

The goal is proving both the **security invariant** (reject wrong identities) and the **availability invariant** (valid traffic recovers within SLA).

## 21. Case Study: SFTP → JDBC → HTTPS → Kafka Chain

### 21.1. Context

An enterprise receives order files from partner B over SFTP, stores data in DB, calls logistics partner C over HTTPS, and publishes events to Kafka. The system runs multiple instances and must rotate credentials without dropping orders.

Connection inventory:

| Connection | Identity / Trust Type | Owner |
|---|---|---|
| Partner B SFTP | SSH client private key + verified server host key | Partner integration |
| Orders JDBC | DB service principal + TLS server CA | Data platform |
| Logistics C HTTPS | OAuth client credentials + mTLS cert/trust CA | API integration + security |
| Kafka events | `SASL_SSL` or mTLS + topic ACLs | Messaging platform |
| Secret manager | Workload identity + scoped secret references | Platform security |

### 21.2. A Rotation Incident

Upcoming changes:

1. Partner SFTP requires rotating the SSH client key.
2. Partner C is migrating server certificates to a new CA.
3. DB password rotates per policy.
4. Kafka SASL principal changes due to per-app privilege separation.

Executing everything simultaneously without staging can cause:

- SFTP pollers stopping because old keys are revoked before new sessions pick up new keys;
- HTTPS client rejecting the new CA;
- DB pools failing to open fresh connections even while old ones linger;
- Kafka consumers hitting auth failures and spiking lag;
- Uncontrolled retries creating duplicate side effects.

### 21.3. Safe Change Plan

**Preparation:** inventory each connection, issue NEW credentials/certs, document rollback plans and owners. SFTP server accepts new public key; HTTPS client trusts both old/new CAs; DB provisions alternating identity or overlap; Kafka ACLs granted to new principal.

**Canary:** one instance/connector tests new versions—verifying SFTP list/download, JDBC queries, authenticated HTTP calls, and Kafka produce/consume on test targets. Negative tests confirm bad host keys, untrusted CAs, and under-privileged principals fail.

**Rollout:** deploy in waves, draining in-flight requests/transactions and opening new sessions/connections. Monitor SFTP last-success, DB pool errors, HTTP 401/403/TLS errors, Kafka lag, and retries.

**Retirement:** verify all instances run NEW, instruct partners to revoke OLD, remove legacy CAs/host keys after overlap completes, and confirm logs contain zero secrets.

### 21.4. When CA Rotates Before Apps Update

HTTPS outbound starts failing certificate path validation. **Never disable hostname verification or enable trust-all.** Operations halts server cert rollout if coordinated, or pushes approved trust anchors, rebuilds the HTTPS client/`SSLContext`, verifies SAN/hostname matching, and confirms API responses.

For requests with unclear outcomes, run **reconciliation/idempotency** before replaying. Handshake TLS failures normally occur before HTTP transmission, yet never assume every concurrent timeout failed at handshake.

### 21.5. When DB Password Rotates While Old Connections Run

Metric queries still succeed on existing pooled connections. Hours later, an autoscaled instance or pool refill hits auth errors, triggering a delayed outage. **Smoke tests must force opening fresh physical connections** with NEW credentials—never trust queries on pre-warmed connections.

### 21.6. When SFTP Host Key Changes Unannounced

Clients hit host-key mismatches. **Stop and verify out-of-band**, as this could be either an unannounced server migration or a MITM attack. Never update `known_hosts` using fingerprints pulled from the untrusted connection itself. Once the owner confirms the key, roll out carefully, check file state, and restart pollers cleanly.

### 21.7. Handover Evidence

A rotation change is complete only with:

- Secret/certificate references and versions (values omitted);
- Verified trust identities per adapter;
- Smoke test results on **new connections**;
- Required negative test results;
- Evidence every instance/region cut over;
- Proof OLD was retired or an open deadline-tracked ticket;
- Audit record noting owner, approver, timestamp, and impact;
- Zero SLA-breaching backlogs, retries, or unknown outcomes.

## 22. Incident Response: Leaked Secret or Compromised Certificate

### 22.1. Distinguish Expiry from Compromise

**Certificate expiry:** an identity passed its validity window; goal is restoring service with valid certs and trusted roots.

**Private key compromise:** attackers may hold key material; you must **revoke/disable the old key or identity** and audit access—never merely renew a leaf cert using the same compromised private key.

**Host key mismatch:** server identity changed unexpectedly; halt and verify peer rather than assuming routine expiry. Unapproved `known_hosts` edits turn mistakes into MITM vulnerabilities.

### 22.2. Runbook on Secret Exposure

1. **Triage:** identify secret type, system, owner, exposure location, and potential exposure window.
2. **Containment:** restrict access paths and disable credentials where possible without worsening blast radius.
3. **Rotate/replace:** generate fresh keys/tokens/passwords from trusted sources with least privilege and deploy to verified workloads.
4. **Revoke old:** revoke on servers/IdPs/brokers/DBs; for compromised private keys, enforce emergency revocation immediately instead of waiting out normal overlap.
5. **Investigate:** inspect audit logs, access logs, token usage, anomalous calls, affected timeframe, and blast radius.
6. **Remediate exposure:** scrub secrets from exposed locations; if committed to Git, **rewriting history is cleanup only**—never a substitute for revocation.
7. **Verify:** confirm NEW works and OLD fails on new sessions per remote controls; audit prior issued sessions/tokens.
8. **Recover business flows:** reconcile File/SFTP/JDBC/broker/HTTP messages that retried, stalled, duplicated, or faced tampering.
9. **Report:** archive evidence and notify incident owners, stakeholders, and legal/compliance per policy.

### 22.3. Tokens Already Issued from Old Credentials

Revoking an OAuth client secret **does not automatically revoke already-issued access tokens** if the token architecture lets them live until expiry. Check IdP and resource-server revocation/session-invalidation mechanisms. Similarly, authenticated broker/DB sessions may remain open until closed or expired.

### 22.4. Never Paste Secrets into Incident Tickets

Incident tickets should record connection IDs, secret versions/references, owners, timestamps, error categories, and approved identifying fingerprints—never private keys, passwords, refresh tokens, SASL JAAS credentials, or access tokens. Chat, email, and ticketing tools become secondary leak surfaces when mishandled.

### 22.5. When Immediate Rotation Is Impossible

Apply approved compensating controls: tighten network ACLs, temporarily disable affected principals, shrink scopes, block high-risk endpoints, and heighten monitoring. Set a hard rotation deadline; **never treat extra logging as a substitute for revoking leaked keys**.

## 23. Production Diagnostics Runbook for Connection and Certificate Errors

### Step A — Classify the Error

- **TCP connection failure:** DNS, firewall, routing, service down, wrong port.
- **TLS handshake failure:** CA chain, hostname/SAN, expiry, cipher/protocol, client cert.
- **SSH host-key verification failure:** host key mismatches `known_hosts`.
- **Authentication failure:** invalid password/key/token/principal.
- **Authorization failure:** insufficient scope/role/ACL/tenant.
- **Operation failure:** connection authenticated cleanly, yet File/SFTP/HTTP/JMS/AMQP/Kafka/JDBC operation failed logically.

Never blindly rotate every secret just because HTTP timed out or a JDBC pool exhausted.

### Step B — Confirm Which Credential Version Is Actually Active

1. Verify secret reference and version provisioned to the workload.
2. Verify whether app/connectors actually reloaded.
3. Check pool/session/`SSLContext`/client generation and lifecycles.
4. Check whether the remote side currently accepts OLD/NEW.
5. Check identity mapping and post-auth authorization.
6. Check host clocks and cert `notBefore`/`notAfter`.

Comparing manifests in Git alone proves nothing if legacy open connections persist in memory.

### Step C — Inspect Every Boundary

| Adapter | Essential Checks |
|---|---|
| SFTP | Out-of-band verified host fingerprint, client key, username, remote permissions, session cache |
| HTTP client | URL host and SAN, CA chain, mTLS key, OAuth token audience/scope, redirects |
| HTTP inbound | Ingress TLS terminator, client cert mapping if used, authorization, proxy trust |
| JMS | Provider-specific trust/keystore, broker principal, destination ACLs, listener reconnects |
| AMQP | Broker TLS, vhost permissions, username/cert, consumer recovery |
| Kafka | `security.protocol`, SASL mechanism/client cert, bootstrap hosts, principal ACLs, offsets/lag |
| JDBC | Driver TLS mode, host verification, `DataSource` credentials, pool eviction, DB roles |
| File | Source path ownership, permissions, secret directory isolation, quarantine |

### Step D — Recover Without Lowering Security

- Fix chains/CAs/SANs or update approved endpoints;
- Provision properly scoped and versioned credentials;
- Refresh/recreate connectors or perform controlled rolling restarts;
- Test fresh connections and real business operations;
- Never disable hostname/host-key verification or fall back to admin accounts long-term;
- Bound retries to avoid reconnect storms that exhaust resources.

### Step E — Verify Business Messages

Once connectivity returns:

1. File/SFTP: any partial downloads or accepted-yet-unprocessed files?
2. HTTP POST: any requests left in `UNKNOWN` outcome?
3. JMS/AMQP: any redelivered, unacked, or DLQ messages?
4. Kafka: any lag spikes, miscommitted offsets, or DLT records?
5. JDBC: any rolled-back transactions or partial effects?
6. Could retries create duplicate orders/shipments?

**A fresh successful handshake does not mean the integration flow has recovered business consistency.**

### Step F — Close the Incident

Document root cause, credential/cert versions, trust verification method, impact window, affected messages, retries/reconciliation, rollback/rotation actions, and preventive measures. Hand over evidence completely free of secrets.

## 24. Anti-Patterns and Fixes

| Anti-Pattern | Risk | Fix |
|---|---|---|
| Committing passwords/API keys/SSH private keys to Git | Exposed across repos, history, CI | Secret manager/identity + revoke leaked keys |
| Baking private keys into JARs/images | Secrets replicated across artifacts | Runtime injection + tight permissions |
| Disabling TLS hostname verification | Server impersonation | Fix SAN/CA/endpoint config |
| Using trust-all `TrustManager` | Accepts untrusted certs | Scoped truststore + negative tests |
| Disabling SSH host-key checking | SFTP MITM attacks | Verified `known_hosts` / host-key policy |
| Sharing credentials across dev and prod | Cross-environment compromise | Separate identities, roles, secret refs |
| Using broker/DB admin credentials | Excessive blast radius | Least-privilege principals and ACLs |
| Hiding public certs while leaving private keys readable | Protecting the wrong asset | Inventory public vs. private keys properly |
| Checking only cert expiry, ignoring SAN/chain | Trusts wrong-identity certs | Full certificate verification |
| Pinning leaf fingerprints without rollover plan | Outages on every renewal | Backup pins/trust policy and overlap |
| Rotating server certs before trusting new CA | Widespread handshake failures | Prepare client trust first, phase rollout |
| Revoking OLD before instances adopt NEW | All connectors lose access | Canary, safe overlap, staged revocation |
| Secret file updated while pool keeps OLD | Delayed outages on reconnect | Recreate physical connections and verify |
| Testing only `GET /health` for new mTLS | Fails to prove client uses NEW | Test fresh handshakes and identity |
| Token expires inside long-running poller | Retry storms, HTTP 401s | Proactive token refresh + metrics |
| Logging full exceptions and `MessageHeaders` | Credential/PII leaks | Structured logging + redaction |
| Storing raw `Throwable` inside Kafka error events | Secret leaks / brittle serialization | Normalized safe error events |
| Granting secret-manager read-all | Compromised app reads everything | Scoped IAM policies, workload identities |
| Ignoring pollers when error count = 0 | Silent dead pollers | Track last-successful-poll and backlogs |
| Skipping failover hostname checks | DB/broker failover breaks TLS | Test SAN/CA across failover endpoints |
| Retrying auth failures infinitely | Account lockouts, overload, masks compromise | Classify errors, back off, alert |
| Rolling back to a compromised key | Reopens active attack vector | Emergency replacement; never reuse leaked keys |
| Sharing file inbox folders with key material | Poller ingests private keys | Separate mounts and filesystem ACLs |
| Forgetting to revoke ex-partner credentials | Lingering unauthorized access | Post-rollout revocation and audits |
| Equating mTLS with authorization | Valid peer gets excessive access | Enforce ACL/scope/tenant authorization |

## 25. Go-Live Checklist for Secret and Certificate Management

### A. Inventory and Accountability

- [ ] Every File/SFTP/HTTP/JMS/AMQP/Kafka/JDBC connection has an ID and owner.
- [ ] Endpoints, environments, protocols, and auth mechanisms are documented.
- [ ] Secret references/versions are stored safely—never raw values in repos.
- [ ] Blast-radius analysis and revocation owners exist.
- [ ] Rotation/renewal SLAs and pre-expiry alerts are configured.

### B. Transport Trust and Identity

- [ ] HTTPS/JMS/AMQP/Kafka/JDBC enforce TLS per security policy.
- [ ] Chains, SAN/hostnames, validity windows, and trust anchors are verified.
- [ ] For mTLS, client keys/certs and server trust policies are configured.
- [ ] SFTP SSH server host keys are verified via trusted `known_hosts`/fingerprints.
- [ ] Zero trust-all, skipped host-key checks, or unapproved plaintext fallbacks exist.
- [ ] Failover endpoints carry valid certificates and identities.

### C. Least Privilege and Secrets

- [ ] Distinct identities separate workloads, environments, and partners as needed.
- [ ] DB roles, Kafka topic ACLs, AMQP vhost permissions, and JMS destination ACLs follow least privilege.
- [ ] OAuth tokens use tight scopes, audiences, and lifetimes.
- [ ] Secret managers use workload identities and scoped read policies.
- [ ] Key files are readable only by the authorized process/owner.
- [ ] Zero secrets enter `MessageHeaders`, logs, traces, actuators, or CI artifacts.

### D. Rotation and Connection Lifecycles

- [ ] End-to-end issue → distribute → activate → verify → revoke → retire path exists.
- [ ] Documented which adapters reload live vs. require restart/recreation.
- [ ] Canary tests verify **real new connections** with NEW.
- [ ] Overlap windows and clean rollbacks (never reusing compromised keys) exist.
- [ ] Pool/session caches refresh in a controlled manner.
- [ ] Post-revocation, OLD cannot open new sessions per design.
- [ ] File/JMS/AMQP/Kafka/JDBC business states are reconciled after reconnects.

### E. Testing and Operations

- [ ] Positive and negative tests cover CA, SAN, expiry, host keys, credentials, and ACLs.
- [ ] Tested mTLS, OAuth refresh, token expiry, and SFTP SSH key rollovers.
- [ ] Tested secret manager unavailability and access denials.
- [ ] Tested rotations across multiple instances with active in-flight messages.
- [ ] Tested no-secrets-in-logs using fake canary values.
- [ ] Metrics track expiry, auth failures, TLS/SSH errors, pool reconnects, and backlogs.
- [ ] Incident runbooks cover compromise, expiry, CA rollover, and failed rotations.
- [ ] Audits, approvers, and evidence are signed off before marking production-ready.

## 26. Self-Check Questions

**Q1. Are secrets and certificates the same thing?**

**Answer:** No. Secrets are data that must remain confidential, such as passwords, tokens, or private keys. An X.509 certificate carries a public key and CA-attested identity attributes; the paired private key is the secret. Certificates and truststores still need integrity protection and lifecycle management.

**Q2. Does using HTTPS mean the API is properly authorized?**

**Answer:** No. HTTPS authenticates the server (and client with mTLS) and encrypts transport. Endpoint/resource authorization still requires scopes, roles, principals, and tenant policies.

**Q3. Why doesn't SFTP use HTTPS's X.509 truststore to verify hosts?**

**Answer:** SFTP runs over SSH. Servers are authenticated using SSH host keys/`known_hosts` or equivalent SSH trust mechanisms, distinct from HTTPS CA/TLS/SAN chains.

**Q4. If an SSH client holds a valid private key but disables host-key checking, is it safe?**

**Answer:** No. It could connect to an attacker's spoofed SSH server. Always verify host keys via trusted out-of-band sources before sending credentials or data.

**Q5. Does mTLS send the client's private key to the server?**

**Answer:** No. The private key proves possession via cryptographic signing; certificates/public keys are exchanged while private keys stay protected locally.

**Q6. How do truststores and keystores differ?**

**Answer:** Truststores hold trust anchors/certificates to verify peers. Keystores/key material hold a client or server identity's private key and certificate chain. An mTLS app typically needs both.

**Q7. Is an unexpired certificate enough to trust a server?**

**Answer:** No. Verify the chain/trust anchor, SAN/hostname, validity window, key-usage policy, and revocation status where required.

**Q8. Why shouldn't you enable trust-all when hitting `PKIX path building failed`?**

**Answer:** Trust-all skips CA verification, letting attackers spoof servers. Fix the chain, trust anchors, and identity properly.

**Q9. Does updating a certificate file on a mounted volume automatically make a running `RestTemplate`/`WebClient` use it?**

**Answer:** Not by default. Clients, `SSLContext`s, and connection pools may cache old key material. Implement real reload hooks or recreate clients/connections per version support.

**Q10. After rotating a DB password, existing queries keep passing. Does that prove the pool uses NEW?**

**Answer:** No. Legacy open physical connections may still be running. Force opening new connections to confirm authentication with NEW, then drain/evict old connections.

**Q11. When should OLD credentials be revoked?**

**Answer:** After all instances are verified on NEW and no callers depend on OLD—unless dealing with a compromise, which requires urgent revocation per incident policy. Never drag overlap out indefinitely.

**Q12. A secret leaked into Git and the commit was deleted. Is the secret safe now?**

**Answer:** No. Secrets linger in history, forks, caches, and artifacts. Revoke/rotate credentials and investigate exposure; repo cleanup is strictly secondary.

**Q13. Are already-issued access tokens automatically revoked when a client secret rotates?**

**Answer:** Not by default. It depends on how the IdP/resource server issues, validates, and revokes tokens. Account for active tokens and open sessions.

**Q14. Why does a secret manager still need least-privilege IAM?**

**Answer:** Because a compromised workload identity can read every secret its policy grants. Secret-manager audit logs do not make broad read policies safe.

**Q15. What does Kafka `SASL_SSL` protect?**

**Answer:** TLS protects the transport channel, while SASL authenticates the principal per chosen mechanism. Topic/group ACLs and transactional authorization still require separate configuration.

**Q16. A Kafka client authenticates cleanly yet hits `TopicAuthorizationException`. Should you disable SSL?**

**Answer:** No. That is an authorization/ACL or principal-mapping error. Configure least-privilege permissions for the right topics and consumer groups.

**Q17. Do JMS and AMQP share the same TLS properties?**

**Answer:** No. JMS spans many providers where TLS is typically configured on the provider's `ConnectionFactory`. AMQP/RabbitMQ has its own client/connection-factory config. Check exact versions and brokers.

**Q18. A certificate CA change breaks clients simultaneously. What is the standard sequence?**

**Answer:** Prepare client trust first, switch server certificates second, verify handshakes, and clean up the old CA last. If overlap isn't possible, plan a maintenance/transition window.

**Q19. Why can leaf fingerprint pinning cause outages during renewals?**

**Answer:** Renewed certificates usually get new fingerprints. Without backup pins/overlap and an update workflow, clients reject legitimate renewed servers.

**Q20. Should an SFTP host-key mismatch be fixed by deleting `known_hosts`?**

**Answer:** No. Stop connecting, verify the new host key via an approved out-of-band channel, and update trust under change control.

**Q21. During a secret manager outage, can you keep using expired tokens indefinitely to stay up?**

**Answer:** No. Caching and fallbacks must obey expiry/revocation policies. If valid credentials cannot be obtained, fail readiness or transition service state safely instead of bypassing security controls.

**Q22. Why shouldn't API keys sit directly inside `MessageHeaders`?**

**Answer:** Headers cross channels, linger in memory, get logged, or surface inside `ErrorMessage`s and traces. Inject credentials narrowly inside outbound clients/interceptors.

**Q23. If an HTTP POST times out after rotation, did the server definitely skip the request?**

**Answer:** No. If sent before timeout, the server may have committed. Use idempotency keys or reconciliation to avoid duplicate side effects.

**Q24. What evidence proves a rotation succeeded end-to-end?**

**Answer:** NEW works on **real fresh connections**, auth and authorization pass, synthetic business smoke tests pass, all instances cut over, OLD is revoked per policy, metrics/backlogs look healthy, and zero messages were lost, duplicated, or corrupted.

**Q25. If zero TLS errors appear, is a poller guaranteed to be healthy?**

**Answer:** No. Pollers can stall or skip files without throwing errors. Track last successful poll, ingested counts, and backlog against SLAs.

## 27. Conclusion and Further Reading

In **Spring Integration Adapters**, managing secrets and certificates is never an isolated config chore. It ties directly into **workload identity, external access permissions, TLS/SSH peer verification, and the lifecycles of connection factories, pools, sessions, listener containers, pollers, and `MessageChannel`s** carrying business payloads.

A production solution should guarantee:

1. **Zero secrets in source code or artifacts;** use permissioned, audited, versioned secret stores.
2. **Strict peer verification** via TLS chains/SANs/hostnames or approved SSH host keys; never trust-all or skipped verification.
3. **Least privilege** across DB, HTTP/OAuth, JMS/AMQP/Kafka, SFTP, and secret managers.
4. **Planned rotations:** issue NEW, stage trust/permissions, canary test, open fresh connections, verify, then revoke OLD.
5. **Respect for long-lived connections:** swapping files/secret references does not automatically refresh open `SSLContext`s, sessions, or pools.
6. **Observability and negative testing:** untrusted peers must fail; canary secrets must stay out of logs; expirations and rotations must alert.
7. **Business-outcome reconciliation:** a reconnected adapter does not prove all files, HTTP calls, JDBC transactions, or broker messages recovered cleanly after an incident.

When operating File, SFTP, HTTP, JMS, AMQP, Kafka, and JDBC flows, manage **credential lifecycles** and **message lifecycles** side by side. Secrets and certificates govern **who may connect and to whom**, while idempotency, acks, transactions, retries, and recovery determine **whether messages stay accurate after connectivity glitches**.

### Official Version-Specific References

- [Spring Integration Reference](https://docs.spring.io/spring-integration/reference/): adapters, endpoint lifecycles, pollers, and channel error handling.
- [Spring Integration SFTP Support](https://docs.spring.io/spring-integration/reference/sftp.html): SSH session factories, host keys, and SFTP connections.
- [Spring Boot SSL](https://docs.spring.io/spring-boot/reference/features/ssl.html): SSL bundles, PEM/keystores, and client/server configuration.
- [Spring Security OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): OAuth client registrations, authorized clients, and token management.
- [Spring AMQP Reference](https://docs.spring.io/spring-amqp/reference/): RabbitMQ connection factories, TLS, lifecycles, and messaging.
- [Spring for Apache Kafka Reference](https://docs.spring.io/spring-kafka/reference/): client/broker security, consumers, producers, and listener containers.
- [Apache Kafka Security](https://kafka.apache.org/documentation/#security): TLS, SASL, and ACLs per Kafka version.
- [PostgreSQL JDBC SSL](https://jdbc.postgresql.org/documentation/ssl/): driver TLS modes and server verification.
- [Java Secure Socket Extension Reference](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html): JSSE, trust/key material, and TLS.

**Note:** YAML, Java, properties, JSON, Mermaid, and diagrams in this lesson are technical illustrations. Exact configurations vary by Spring Boot/Spring Integration version, JDK, SSH library, broker/DB driver, and secret manager provider. Before production, check APIs for your exact versions, enforce security policies, and validate in a representative staging environment.
