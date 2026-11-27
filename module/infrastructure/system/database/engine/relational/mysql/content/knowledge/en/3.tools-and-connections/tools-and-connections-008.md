# Configuring TLS, Server Identity Verification, and Certificate Management

## Objectives

After this lesson, you will be able to:

- Explain how TLS protects MySQL connections and distinguish transport encryption from server identity verification.
- Identify the roles of the CA, server certificate, private key, and client certificate.
- Configure basic TLS on MySQL Server and require remote connections to use a secure channel.
- Connect using the MySQL client and JDBC with certificate and hostname verification enabled.
- Inspect an active TLS session, troubleshoot verification errors, and plan certificate renewal and rotation.

## 1. Why Do MySQL Connections Need TLS?

Applications typically connect to MySQL over TCP/IP networks. Without proper protection, data in transit can be observed or tampered with by a party capable of intercepting network traffic. TLS (Transport Layer Security) establishes an encrypted channel between client and server while providing a certificate-verification mechanism so the client can verify the server it is connecting to.

TLS addresses three related goals:

- **Confidentiality in transit:** network eavesdroppers cannot read exchanged traffic when the TLS session is properly established.
- **Data integrity:** data sent over a TLS channel is protected against undetected tampering.
- **Identity authentication:** the client can verify that the server certificate was issued by a CA trusted by the client and matches the intended target hostname.

The final point is critical. An encrypted connection does not guarantee you are connected to the right server. If the client only requires encryption without verifying the certificate and hostname, an attacker can impersonate the server in a man-in-the-middle attack and still establish a separate TLS connection with the client.

Therefore, in production environments, the goal should be **encrypting the connection and verifying server identity**.

## 2. Components of a Certificate System

### 2.1. CA and Chain of Trust

A CA (Certificate Authority) is an organization or system that issues digital certificates. The client stores or is configured to trust CA certificates. Upon receiving the server certificate, the client validates the signature and certificate chain to confirm the certificate was issued by a trusted CA.

A common model:

```text
Client trust store
       |
       v
Root CA (trusted root CA)
       |
       v
Intermediate CA (if present)
       |
       v
Server certificate (certificate for db.example)
       |
       +-- Subject Alternative Name: DNS:db.example
       +-- Public key
       +-- Validity: Not Before / Not After

MySQL Server holds the private key matching the public key in the server certificate.
```

Key components:

| Component | Where It Is Used | Role |
|---|---|---|
| Root CA certificate | Client trust store; server side when verifying client certificates | Trust anchor for verifying signatures in the certificate chain |
| Intermediate CA certificate | Certificate chain sent with the server certificate or trust bundle per policy | Links the server certificate to the root CA |
| Server certificate | Sent by MySQL Server to the client during the TLS handshake | Contains server identity, public key, validity period, and signing CA info |
| Server private key | Readable only by MySQL Server | Proves the server possesses the corresponding private key; never shared with clients |
| Client certificate and private key | Application/client when using mutual TLS authentication | Allows the server to verify client identity via certificate |

The server certificate must include the exact DNS name the application connects to in the Subject Alternative Name (SAN) field. For instance, if the application connects to `db.example.internal`, the SAN must include that name. If connecting by IP address, the certificate must contain a matching IP SAN. Do not rely on the legacy Common Name (CN) in place of SAN.

Private keys must be protected via OS file permissions. Only the MySQL service account and authorized administrators should be able to read the key. Never commit private keys to Git, public container images, tickets, or logs.

### 2.2. One-Way TLS and Mutual TLS

In the common setup, the server presents a certificate to the client and the client verifies the server certificate. This is server authentication, often called one-way TLS.

With mutual TLS (mTLS), the client also presents its own certificate. The server verifies the client certificate against a configured CA. mTLS adds an authentication layer at the connection transport level; MySQL still performs account authentication and SQL privilege checks through its own mechanisms.

Do not confuse these three steps:

1. TLS encrypts the transport channel.
2. The client verifies the server's identity.
3. The server verifies the client's certificate (if mTLS is enabled).

A system can use the first two steps without requiring client certificates. Deploy mTLS only when you need device or application identity enforcement at the connection layer and already have a process for issuing, renewing, and revoking client certificates.

## 3. Preparing Certificates for MySQL Server

Before configuring MySQL, you need:

- The root CA certificate that clients will trust (`ca.pem` or an equivalent CA bundle).
- A server certificate signed by that CA or its intermediate CA (`server-cert.pem`).
- The matching server private key (`server-key.pem`).
- Any intermediate certificate required by the certificate chain.

In enterprise environments, use a centrally managed internal CA or a public CA appropriate for your domain and policy. For development environments, a dedicated test CA may be used. Do not use ad-hoc self-signed certificates as a long-term production solution.

When requesting a server certificate, provide the exact hostname clients will use to connect. The certificate should have appropriate key usage/extended key usage for TLS server authentication, a sensible validity period, and a complete CA chain. If there are multiple endpoints or DNS aliases, ensure every name used by clients is listed in the SAN.

### 3.1. Inspecting Certificates and Private Keys

You can use OpenSSL to inspect certificate details:

```bash
openssl x509 -in server-cert.pem -noout -subject -issuer -dates -ext subjectAltName
```

This checks the subject, issuing CA, validity dates, and SANs. Validate the private key without printing the key material:

```bash
openssl pkey -in server-key.pem -check -noout
```

Verify the certificate signature against the CA. If there is an intermediate CA, pass it with `-untrusted`:

```bash
# When signed directly by the CA
openssl verify -CAfile ca.pem server-cert.pem

# When an intermediate CA is used
openssl verify -CAfile root-ca.pem -untrusted intermediate-ca.pem server-cert.pem
```

An `OK` result indicates chain verification succeeded for the provided CA and inputs. This is not the whole TLS check: you still must verify that the SAN matches the hostname used by clients, check certificate expiration, verify extended usage, and verify MySQL's actual runtime configuration.

If the server certificate must send an intermediate certificate, format the certificate file as the chain required by MySQL and your CA. Never substitute a leaf server certificate for the root CA in a trust store just to make verification pass.

## 4. Configuring TLS on MySQL Server

Filenames and paths below are Linux examples. On Windows or in containers, replace them with actual paths readable by the MySQL process.

In the MySQL configuration file—usually `my.cnf` or an included file—place options under `[mysqld]`:

```ini
[mysqld]
ssl_ca=/etc/mysql/certs/ca.pem
ssl_cert=/etc/mysql/certs/server-cert.pem
ssl_key=/etc/mysql/certs/server-key.pem

# Accept only connections using secure transport
require_secure_transport=ON

# Restrict TLS versions per environment policy
tls_version=TLSv1.2,TLSv1.3
```

Meaning:

- `ssl_ca`: CA or CA bundle used for certificate verification in the server's TLS configuration; especially required when the server verifies client certificates.
- `ssl_cert`: server certificate and, when needed, intermediate certificate chain.
- `ssl_key`: private key corresponding to the server certificate.
- `require_secure_transport`: requires connections to use a transport MySQL considers secure. Non-TLS TCP connections are rejected; some local transports such as Unix sockets may still be considered secure.
- `tls_version`: list of TLS versions permitted by the server. Enable only versions supported by your MySQL release, TLS library, and system clients.

Ensure the MySQL process can read the CA and certificate while unauthorized users cannot read the private key. On Linux, file ownership and permissions typically match the installation's MySQL service account—for example `mysql:mysql` and restricted read permissions on the private key. On Windows, configure ACLs for the service account.

After changing configuration, reload or restart according to operational procedures and your MySQL version's capabilities. Some MySQL versions support reloading TLS configuration without a restart; do not assume reload commands are identical across MySQL, MariaDB, and all versions. Check the error log if the server fails to start or load certificates.

### 4.1. Verifying Loaded Server Configuration

Connect with an appropriate administrative account and inspect the variables:

```sql
SHOW GLOBAL VARIABLES LIKE 'ssl_ca';
SHOW GLOBAL VARIABLES LIKE 'ssl_cert';
SHOW GLOBAL VARIABLES LIKE 'ssl_key';
SHOW GLOBAL VARIABLES LIKE 'tls_version';
SHOW GLOBAL VARIABLES LIKE 'require_secure_transport';
```

These variables report the paths and policies advertised by the server. They do not by themselves prove clients are using TLS; you must inspect the status of an actual session in the next step.

## 5. Connecting with the MySQL Client and Verifying the Server

### 5.1. MySQL Client SSL Modes

Modern MySQL clients support `--ssl-mode` with the following common values:

| Mode | Behavior |
|---|---|
| `DISABLED` | Do not use TLS |
| `PREFERRED` | Prefer TLS, but fall back to an unencrypted connection if the server does not support TLS |
| `REQUIRED` | Require TLS, but do not verify the CA chain and server hostname like the verify modes |
| `VERIFY_CA` | Require TLS and verify the certificate against a trusted CA |
| `VERIFY_IDENTITY` | Require TLS, verify the CA chain, and verify the hostname the client connects to matches the identity in the certificate |

`REQUIRED` guarantees the channel is encrypted, but is insufficient to verify the server is the intended host. For production connections, use `VERIFY_IDENTITY` and provide the appropriate trusted CA.

### 5.2. Connecting with Hostname Verification

Example connecting to `db.example.internal`:

```bash
mysql \
  --host=db.example.internal \
  --port=3306 \
  --user=app_user \
  --password \
  --ssl-mode=VERIFY_IDENTITY \
  --ssl-ca=/etc/myapp/certs/ca.pem \
  app_db
```

The client prompts for the password interactively. Never write passwords directly in commands or unprotected configuration files. `--ssl-ca` specifies the CA used by the client to verify the server certificate.

The hostname in `--host` must match a SAN in the server certificate. If the certificate contains `DNS:db.example.internal` but the application connects using an IP or another alias missing from the SAN, `VERIFY_IDENTITY` will reject the connection. The proper fix is to issue a certificate whose SAN covers the endpoints in use, or connect via the canonical hostname listed in the certificate.

The `--ssl-mode` options belong to the MySQL client. The MariaDB client and other connectors may use different option names or configuration syntax; check the documentation for the exact client rather than copying this command verbatim.

### 5.3. Checking Whether the Current Session Uses TLS

After connecting, run:

```sql
SHOW SESSION STATUS LIKE 'Ssl_cipher';
SHOW SESSION STATUS LIKE 'Ssl_version';
```

`Ssl_cipher` shows the session's cipher suite; an empty value normally indicates the current session is not using TLS. `Ssl_version` shows the negotiated TLS version. You can also run `\s` in the MySQL client to view a connection summary; the output typically includes an SSL line when the session uses TLS.

Verify from the actual application connection or a test connection using the same hostname, CA, and SSL mode. One administrative session over TLS does not prove every connection in an application's connection pool has TLS configured.

## 6. Configuring TLS in Java Applications

With MySQL Connector/J, a JDBC URL can enforce server identity verification using the `sslMode` property:

```properties
jdbc:mysql://db.example.internal:3306/app_db?sslMode=VERIFY_IDENTITY
```

When the CA is already installed in the JVM's default trust store, Connector/J can rely on that trust store to verify the certificate chain. If using a private internal CA, configure a dedicated trust store for the application. Example creating a PKCS12 trust store from a CA certificate:

```bash
keytool -importcert \
  -alias mysql-private-ca \
  -file ca.pem \
  -keystore mysql-truststore.p12 \
  -storetype PKCS12
```

Then configure Connector/J to use the trust store. Illustrative Java example:

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.util.Properties;

String url = "jdbc:mysql://db.example.internal:3306/app_db";

Properties properties = new Properties();
properties.setProperty("sslMode", "VERIFY_IDENTITY");
properties.setProperty(
    "trustCertificateKeyStoreUrl",
    "file:/etc/myapp/certs/mysql-truststore.p12"
);
properties.setProperty("trustCertificateKeyStoreType", "PKCS12");
properties.setProperty(
    "trustCertificateKeyStorePassword",
    System.getenv("DB_TRUSTSTORE_PASSWORD")
);

try (Connection connection = DriverManager.getConnection(url, properties)) {
    System.out.println("Connected with verified TLS");
}
```

The example assumes the `DB_TRUSTSTORE_PASSWORD` environment variable is supplied via a secret manager or deployment secrets mechanism. Never commit trust store passwords to source code. Verify property names and TLS behavior against your actual MySQL Connector/J version; the MariaDB driver uses separate configuration options.

If the application requires mTLS, in addition to the trust store for server verification, configure a client key store containing the client certificate and private key. Never use the server private key as a client key; they represent separate identities and purposes.

## 7. Enabling Mutual TLS (mTLS) When Needed

To require a client to present a valid certificate, a MySQL account can be configured with a certificate requirement. Example:

```sql
ALTER USER 'app_user'@'%' REQUIRE X509;
```

`REQUIRE X509` requires the client to present a valid X.509 certificate under the server's TLS policy. MySQL also supports issuer or subject constraints in compatible versions; consult your version's documentation before using those finer-grained requirements.

The client must supply a client certificate and private key, for example with the MySQL client:

```bash
mysql \
  --host=db.example.internal \
  --user=app_user \
  --password \
  --ssl-mode=VERIFY_IDENTITY \
  --ssl-ca=/etc/myapp/certs/ca.pem \
  --ssl-cert=/etc/myapp/certs/client-cert.pem \
  --ssl-key=/etc/myapp/certs/client-key.pem \
  app_db
```

Here `--ssl-ca` lets the client verify the server; `--ssl-cert` and `--ssl-key` supply the client identity for the server to verify. These two verification directions are independent.

Before enabling `REQUIRE X509` for a production application account, issue and distribute client certificates to all instances, verify private-key read permissions, establish renewal and revocation procedures, and test in staging. If an account lacks a valid certificate, connections will fail immediately at the authentication step.

## 8. Enforcing Secure Connections Without Disrupting Applications

Do not abruptly enable `require_secure_transport=ON` on a server that still has older applications. Clients that do not yet support TLS or are using `PREFERRED` may be rejected or connect in a way that fails identity verification requirements.

A safe rollout sequence:

1. **Inventory clients:** identify all applications, jobs, admin tools, connectors, driver versions, and connected endpoints.
2. **Issue CA and server certificates:** ensure certificates have SANs matching actual hostnames and are valid.
3. **Install trust:** distribute the CA certificate to the trust store of every application and tool that connects.
4. **Test verification:** switch clients to `VERIFY_IDENTITY`; check the handshake, hostname, CA chain, and `Ssl_cipher`/`Ssl_version` status.
5. **Update all clients:** confirm every connection pool, background job, backup tool, and monitoring agent connects over TLS.
6. **Enable server policy:** turn on `require_secure_transport` during a planned change window.
7. **Monitor and reconcile:** watch the error log, application connection errors, and active TLS sessions; keep a config rollback plan ready in case an un-updated client surfaces.

Note: certain local connections over Unix sockets may still satisfy MySQL's secure transport requirement even without TLS. If policy mandates TLS for all connections, verify both transport type and how applications connect rather than checking `require_secure_transport` alone.

## 9. Renewing, Rotating, and Revoking Certificates

Certificates have expiration dates. If a server certificate expires, strict verifying clients will reject connections. If a CA expires or is removed from a trust store, certificates signed by that CA may also cease to be trusted.

### 9.1. Lifecycle Tracking

Track at least the following information for every certificate:

- Subject, SANs, and intended usage (server authentication or client authentication).
- Issuing CA and intermediate chain.
- Validity start and expiration timestamps.
- Deployment locations, systems, or services using it.
- Owner or system responsible for renewal, rotation, and revocation.

You can use OpenSSL to check expiration dates:

```bash
openssl x509 -in server-cert.pem -noout -dates
```

Set alerts far enough ahead of expiration to allow re-issuance, distribution, and testing. Do not wait until a certificate expires to begin renewal.

### 9.2. Rotating the Server Certificate

If you replace the server certificate while keeping the current CA, clients normally continue trusting that CA. However, the new certificate must still have accurate SANs, a valid chain, and its matching private key.

When migrating to a new CA, avoid a gap where some clients trust only the old CA while the server has already switched to a new certificate. A common rollout pattern is:

1. Distribute a trust bundle containing both the old CA and the new CA to clients.
2. Confirm all clients have updated their trust stores.
3. Install the new server certificate and reload the TLS context or restart per your version's guidance.
4. Verify clients validate successfully across all endpoints.
5. Once no server or client certificates depend on the old CA, remove the old CA from trust stores on schedule.

Reloading TLS may require administrative privileges and behaves differently across versions. Read the documentation for your exact MySQL version and test the procedure in staging before applying it in production.

### 9.3. Revoking Certificates and Protecting Private Keys

If a private key is compromised or a client is no longer authorized, revoke the certificate according to your CA process. MySQL provides options related to Certificate Revocation Lists (CRLs), such as `ssl_crl` and `ssl_crlpath` on supported versions. Verify CRL configuration and update behavior against your server version, CA, and TLS library.

When a server private key is suspected of compromise, rotate both the key and certificate, update the trust chain if needed, and investigate the scope of impact. Do not merely delete the old key file and consider the incident closed; copies of the key may exist in backups, container images, logs, or secret distribution systems.

## 10. Troubleshooting Common TLS Errors

| Symptom | Possible Cause | How to Check and Fix |
|---|---|---|
| `certificate verify failed` | Untrusted CA, missing intermediate chain, expired certificate, or not yet valid | Inspect issuer, validity, CA bundle, and chain with OpenSSL; update trust with the right CA |
| Hostname verification failed | SAN does not include the hostname or IP used by the client | Connect using a DNS name listed in the SAN, or reissue the certificate with the exact SAN |
| `unknown ca` or CA error | Client lacks the matching CA, or server does not trust the CA issuing the client cert in mTLS | Determine which side is verifying the certificate; add the CA to the right trust store or server CA config |
| `handshake failure` | No common TLS version/cipher suite, invalid cert or key, or mTLS policy unmet | Compare `tls_version`, TLS libraries, server logs, and client certificate configuration |
| Server fails to start after enabling TLS | Wrong path, unreadable file, private key mismatches certificate, or invalid format | Check error log, file permissions, chain, and key/certificate validity |
| App connects from a laptop but fails from the app server | JVM trust store, hostname, DNS, or CA file differs between environments | Inspect JVM/Connector/J configuration and the app's actual target endpoint |
| Connections rejected after enabling `require_secure_transport` | A client is using non-TLS TCP or a driver lacks TLS configuration | Inventory clients, enable TLS, and verify before reapplying the policy |

Never resolve verification errors by disabling certificate checks, downgrading to `VERIFY_CA` when hostname verification is needed, or dropping to `REQUIRED`/`PREFERRED` in production. Fix the CA, SAN, chain, validity period, or client configuration to comply with policy.

## 11. Checklist for Verifying a Secure MySQL Connection

Before promoting a configuration to production, confirm:

- [ ] Server certificate is issued by a CA trusted by clients.
- [ ] SAN includes the exact hostname or IP the application uses.
- [ ] Certificate is within validity, has proper extended usage, and serves the full intermediate chain.
- [ ] Server private key matches the certificate and is readable only by the required service account.
- [ ] Server allows only TLS versions approved by current security policy.
- [ ] MySQL clients use `--ssl-mode=VERIFY_IDENTITY` or an equivalent mode that verifies hostnames.
- [ ] Java applications use `sslMode=VERIFY_IDENTITY` and a trust store with the proper CA.
- [ ] `Ssl_cipher` and `Ssl_version` show valid values in test sessions.
- [ ] If mTLS is enabled, client certificates have dedicated issuance, renewal, and revocation workflows.
- [ ] `require_secure_transport` is enabled only after all required clients have been verified.
- [ ] Certificate expiration alerts, a rotation plan, and a key-compromise response plan are in place.

## 12. Conclusion

TLS protects MySQL traffic in transit, but a truly secure configuration also requires server identity verification. Use a trusted CA, certificates with SANs matching your endpoints, protected private keys, and client modes that validate both the CA chain and hostname.

Certificate management is an ongoing operational responsibility: track expiration dates, renew on time, rotate CA and server certificates cleanly, update trust stores, and revoke compromised certificates when needed. When changing TLS policies or enabling `require_secure_transport`, verify every client and connection pool to maintain secure connectivity without disrupting MySQL applications.
