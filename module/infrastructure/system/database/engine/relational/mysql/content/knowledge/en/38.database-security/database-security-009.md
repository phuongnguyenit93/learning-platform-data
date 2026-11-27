# TLS, Certificate Verification, and Restricting Insecure Connections

When an application connects to MySQL over a network, SQL statements, query results, and authentication credentials travel across a transport channel. If that channel is unprotected, anyone able to observe or intercept network traffic can read data, tamper with exchanged payloads, or impersonate the server. TLS (Transport Layer Security) protects data in transit while also allowing the application to verify the MySQL server it is connecting to.

Operating TLS securely requires three coordinated layers: the server is configured with appropriate certificates and TLS versions; the application verifies the trust chain and hostname; and MySQL rejects connections that fail to meet policy. Enabling encryption while skipping server identity verification can still leave an application connecting to an imposter server.

## 1. Protection Goals and Key Concepts

TLS protects MySQL connections across three primary goals:

- **Confidentiality:** eavesdroppers on the network cannot read SQL statements, returned data, or credentials inside a TLS session.
- **Integrity:** data altered in transit is detected and the connection does not continue as a valid session.
- **Server authentication:** the application can verify that the server it is talking to holds a certificate issued by a trusted CA for the exact DNS name the application uses.

Common terms:

| Term | Meaning in MySQL Connections |
|---|---|
| CA (Certificate Authority) | Organization or internal system that signs certificates and establishes the trust chain. |
| Server certificate | Contains the public key, server identity, and CA signature. MySQL presents this certificate when starting TLS. |
| Private key | Secret corresponding to the public key in the certificate. The `mysqld` process uses this key; it must never be sent to applications. |
| SAN (Subject Alternative Name) | List of DNS names or IP addresses for which the certificate is valid. The address the application connects to must match a SAN. |
| Certificate chain | The server certificate and intermediate certificates leading to a root CA trusted by the application. |
| mTLS | Mutual TLS: in addition to the application verifying the server, the server requests and verifies the application's certificate. |

TLS protects data **in transit**. It does not automatically encrypt data in tablespaces, binary logs, export files, or backups; those storage locations require separate encryption and access control policies. TLS also does not replace MySQL account authentication, least-privilege authorization, firewalls, or monitoring.

## 2. How TLS Works During a MySQL Connection

For TCP connections, MySQL and the client negotiate TLS before exchanging login credentials and SQL statements. At a high level, the sequence is:

1. The client opens a TCP connection to the MySQL host and port.
2. Client and server negotiate a TLS version and cipher suite supported by both.
3. The server presents its certificate. The client verifies the certificate chain's signatures, validity dates, and server identity against the connecting DNS name or IP.
4. If using mTLS, the server requests a client certificate and validates it against its trusted CA and account conditions.
5. Once the TLS handshake succeeds, both sides exchange MySQL authentication data and session traffic inside the encrypted channel.

TLS and MySQL authentication are separate steps. A valid certificate proves identity at the TLS layer; it does not automatically grant schema privileges. Conversely, a correct MySQL password does not prove the client is connecting to the legitimate server.

MySQL client verification modes have different meanings:

| `--ssl-mode` Mode | Encrypts Connection | Verifies CA | Verifies Hostname |
|---|---:|---:|---:|
| `DISABLED` | No | No | No |
| `PREFERRED` | Yes if negotiated; may fall back | Not guaranteed | No |
| `REQUIRED` | Yes | No | No |
| `VERIFY_CA` | Yes | Yes | No |
| `VERIFY_IDENTITY` | Yes | Yes | Yes |

For production applications, prefer `VERIFY_IDENTITY`. `REQUIRED` only asks for an encrypted channel, so a client may still accept an unverified certificate. `VERIFY_CA` checks the trust chain but does not verify the certificate was issued for the intended server. `PREFERRED` can fall back to an unencrypted connection when TLS is unavailable, making it unsuitable as a mandatory data-protection policy.

## 3. Preparing and Inspecting Certificates

In production, use certificates issued by an enterprise CA or an organization-trusted CA. The server needs its certificate, matching private key, and required CA chain. The client needs the root CA or trust store containing the organization-approved CA.

Names in the certificate's SAN must match the address the client uses to connect. For example, if the application connects to `db.example.internal`, the certificate needs a SAN of `DNS:db.example.internal`. If the application connects by IP, the certificate must contain the corresponding IP SAN. Do not rely on the hostname happening to match the Common Name; issue certificates with explicit SANs.

You can inspect certificate details with OpenSSL:

```bash
openssl x509 -in server-cert.pem -noout -subject -issuer -dates -ext subjectAltName
```

This command shows the subject, issuing CA, validity dates, and SANs. Verify the trust chain and DNS name using:

```bash
openssl verify -CAfile ca.pem -verify_hostname db.example.internal server-cert.pem
```

Hostname verification requires an OpenSSL version supporting `-verify_hostname`. If your organization uses intermediate CAs, provide the intermediate chain in the format required by the tool. Verifying a certificate with OpenSSL is one check; you still need to test connecting with the actual MySQL client or driver the application uses.

MySQL can automatically generate self-signed certificates when initializing the data directory if no operator-provided certificates exist. These are useful in some test environments, but should not be treated by default as client-trusted server identities in production. Deploy CAs and certificates according to your organization's key management process.

Private keys must be strictly protected:

- Only the OS account running `mysqld` and authorized administrators should have read permissions on the key.
- Never place private keys in Git, shared container images, logs, tickets, or public artifact stores.
- Do not share one server private key across multiple servers when PKI workflows can issue distinct keys.
- Monitor expiration dates and plan replacement well before certificates expire.

## 4. Configuring TLS and Enforcing Secure Connections on the Server

Example configuration in the MySQL config file, typically under the `[mysqld]` section:

```ini
[mysqld]
ssl_ca=/etc/mysql/tls/ca.pem
ssl_cert=/etc/mysql/tls/server-cert.pem
ssl_key=/etc/mysql/tls/server-key.pem
tls_version=TLSv1.2,TLSv1.3
require_secure_transport=ON
```

Meaning of the options:

- `ssl_ca` specifies the CA the server uses to verify client certificates when client certificate authentication is required.
- `ssl_cert` points to the server certificate.
- `ssl_key` points to the private key matching the server certificate.
- `tls_version` restricts which TLS versions may be negotiated. The list must be compatible with your MySQL version, SSL/OpenSSL library, and active clients.
- `require_secure_transport=ON` requires connections to use a secure transport. For remote TCP connections, clients must use TLS; local connections via Unix socket (and other secure local transports supported by MySQL) can still be accepted.

Do not enable legacy TLS versions just to let an outdated client connect. If a client does not support TLS 1.2 or TLS 1.3 per policy, upgrade the client or driver. TLS 1.3 availability depends on the MySQL version and the SSL/OpenSSL library in the build; check the documentation for your exact running version before configuring it.

After deployment, ensure file paths exist, certificate formats are valid, the key matches the certificate, and key file permissions are appropriate. Changes to certificate files or startup options may require reloading TLS configuration or restarting the server depending on version and option. Perform changes within a controlled maintenance window and verify with a new connection.

`require_secure_transport` is a server-level control. When enabled, it prevents remote TCP clients from downgrading to unencrypted connections even if the client does not request TLS. It does not replace client-side identity verification: clients must still configure the CA and `VERIFY_IDENTITY` mode.

## 5. Configuring the MySQL Client to Verify the Server

Example connecting with the MySQL command-line client:

```bash
mysql \
  --protocol=TCP \
  --host=db.example.internal \
  --port=3306 \
  --user=orders_app \
  --password \
  --ssl-mode=VERIFY_IDENTITY \
  --ssl-ca=/etc/app/pki/company-root-ca.pem
```

`--password` prompts interactively, avoiding putting the password directly on the command line or in shell history. `--ssl-ca` specifies the CA trusted by the client to verify the server certificate. `--host` must be a name present in the certificate's SAN; if using another DNS alias, the certificate must cover that alias as well.

If you only run:

```bash
mysql --host=db.example.internal --user=orders_app --password --ssl-mode=REQUIRED
```

the client requests encryption without fully verifying server identity. That setting may be acceptable for temporary checks in a controlled environment, but does not achieve server anti-impersonation protection like `VERIFY_IDENTITY`.

Application libraries use different property names. For example, MySQL Connector/J uses `sslMode`; other drivers may use separate CA, trust store, or certificate-verification flags. When configuring a driver, confirm all three things: TLS is enabled, the CA chain is verified, and the hostname is verified. A generic flag like `ssl=true` does not necessarily imply hostname verification. Check the documentation for the specific driver and version you are deploying.

## 6. Enforcing TLS per MySQL Account

In addition to server-wide policy, MySQL lets you require TLS per account. Example creating an application account restricted to one source IP and required to use TLS:

```sql
CREATE USER 'orders_app'@'10.20.30.41'
  IDENTIFIED BY RANDOM PASSWORD
  REQUIRE SSL;

GRANT SELECT, INSERT, UPDATE, DELETE
  ON orders.*
  TO 'orders_app'@'10.20.30.41';
```

`IDENTIFIED BY RANDOM PASSWORD` instructs MySQL to generate a random password; store the returned password in your secret manager per organizational workflow. In practice, replace the sample host with your real source address or range and grant only the SQL privileges the application needs.

If an account must present a valid client certificate, use `REQUIRE X509`:

```sql
CREATE USER 'batch_client'@'10.20.30.52'
  IDENTIFIED BY RANDOM PASSWORD
  REQUIRE X509;
```

The client must then present its own certificate and private key. Example:

```bash
mysql \
  --protocol=TCP \
  --host=db.example.internal \
  --user=batch_client \
  --password \
  --ssl-mode=VERIFY_IDENTITY \
  --ssl-ca=/etc/app/pki/company-root-ca.pem \
  --ssl-cert=/etc/app/pki/batch-client-cert.pem \
  --ssl-key=/etc/app/pki/batch-client-key.pem
```

`REQUIRE X509` requires the client to hold a certificate verified by a CA trusted by the server. You can constrain it further by subject or issuing CA:

```sql
ALTER USER 'batch_client'@'10.20.30.52'
  REQUIRE SUBJECT '/CN=batch-client'
  AND ISSUER '/CN=Company Client CA';
```

The `SUBJECT` and `ISSUER` values must match the actual Distinguished Names in the certificate as compared by MySQL. Extract the exact values from the CA-issued certificate and test before applying to a production account; the strings above only illustrate syntax.

Distinguish the requirements:

- `REQUIRE SSL`: requires the account's connections to use SSL/TLS, without requiring a client certificate.
- `REQUIRE X509`: requires the client to present a valid certificate.
- `REQUIRE SUBJECT` and `REQUIRE ISSUER`: further restrict the identity or issuing CA of the client certificate.
- `require_secure_transport=ON`: enforces secure transport policy at the server level, useful for blocking unencrypted TCP connections system-wide.

Note: `REQUIRE SSL` is an account-level SSL/TLS condition. A local connection over a Unix socket is not a TLS session, so it may not satisfy that condition even though `require_secure_transport` treats Unix sockets as a secure transport. When modifying account requirements, also check local administrative tasks that use that account.

Inspect current account definitions and privileges:

```sql
SHOW CREATE USER 'orders_app'@'10.20.30.41';
SHOW GRANTS FOR 'orders_app'@'10.20.30.41';
```

Avoid sharing one application account across multiple services whenever identities can be separated. When revoking or replacing client certificates, update the corresponding accounts and certificate provisioning workflows.

## 7. Verifying That a Session Is Encrypted

After connecting with a client, run these statements inside the **exact session being checked**:

```sql
SHOW SESSION STATUS LIKE 'Ssl_version';
SHOW SESSION STATUS LIKE 'Ssl_cipher';
```

`Ssl_version` shows the negotiated TLS version; `Ssl_cipher` shows the active cipher. If `Ssl_cipher` is empty, the current session is not using TLS. Confirm you are checking the intended TCP connection; a local Unix socket connection will not have a TLS cipher.

Inspect server policy and configuration:

```sql
SHOW GLOBAL VARIABLES LIKE 'require_secure_transport';
SHOW GLOBAL VARIABLES LIKE 'tls_version';
SHOW GLOBAL VARIABLES LIKE 'ssl_ca';
SHOW GLOBAL VARIABLES LIKE 'ssl_cert';
SHOW GLOBAL VARIABLES LIKE 'ssl_key';
```

You can inspect server-level TLS counters with:

```sql
SHOW GLOBAL STATUS LIKE 'Ssl_%';
```

These counters help monitor overall TLS activity, but do not replace checking `Ssl_version` and `Ssl_cipher` on individual sessions. Also verify account policies via `SHOW CREATE USER` and access privileges via `SHOW GRANTS`.

A verification plan should include both positive and negative checks:

1. Connect using `VERIFY_IDENTITY` and the proper CA; confirm the session reports `Ssl_version` and `Ssl_cipher`.
2. Connect using an untrusted CA; the client must reject the handshake.
3. Connect using a hostname not matching the SAN; `VERIFY_IDENTITY` must reject it.
4. On a server with `require_secure_transport` enabled, attempt a TCP connection with `--ssl-mode=DISABLED`; the server must reject it.
5. For an account with `REQUIRE X509`, attempt connecting without sending a client certificate; the server must reject it.

Example testing that the server rejects unencrypted TCP:

```bash
mysql \
  --protocol=TCP \
  --host=db.example.internal \
  --user=orders_app \
  --password \
  --ssl-mode=DISABLED
```

Run negative tests only in test environments or during an agreed test window. Do not use a local socket connection to conclude that the server allows unencrypted TCP.

## 8. Operations, Certificate Rotation, and Troubleshooting

Certificates have expiration dates. Put expiration dates under monitoring, assign an owner, and start renewal early enough to update clients. When rotating certificates or CAs, follow this order:

1. Issue the new certificate with the right SAN, appropriate validity period, and full CA chain.
2. Install the certificate and private key on the server; check file read permissions and confirm the key matches the certificate.
3. Update client trust stores to trust the new CA. If changing CAs, a transition period where clients trust both old and new CAs may be required.
4. Reload TLS using a mechanism supported by your MySQL version or restart the server per operational procedure.
5. Open a new connection with `VERIFY_IDENTITY`, verify version/cipher, and run negative tests.
6. Remove the old CA only after all clients have fully migrated and no dependencies on the old chain remain.

On supported MySQL versions, you can run the following statement to reload TLS configuration after replacing certificate files:

```sql
ALTER INSTANCE RELOAD TLS;
```

Reload support and behavior depend on the MySQL version and the type of change. Check documentation for your exact version before running it; if unsupported or if a restart is required, perform a controlled restart. After reloading, open a new connection to verify the new certificate is in use; existing sessions may continue with the TLS state negotiated earlier.

Common errors:

| Symptom | Possible Cause | How to Check and Resolve |
|---|---|---|
| Client reports untrusted certificate | Missing root or intermediate CA, wrong CA file, incomplete server certificate chain | Check issuer/chain; install approved CA into trust store; configure `--ssl-ca` properly. |
| `VERIFY_IDENTITY` fails while `VERIFY_CA` succeeds | Connecting hostname or IP is not in SAN | Connect using a DNS name listed in SAN or reissue the certificate with the proper SAN. |
| Connections fail after enabling `require_secure_transport` | Client uses unencrypted TCP or driver lacks TLS config | Enable TLS and CA/hostname verification in the driver; verify `Ssl_cipher` after connecting. |
| Account denied even though TLS is enabled | Account has `REQUIRE X509` yet client sends no certificate, or SUBJECT/ISSUER mismatch | Check `SHOW CREATE USER`; verify client certificate and server's trusted CA. |
| MySQL fails to start or fails to load TLS | Wrong path, key read permissions, invalid PEM, key/certificate mismatch | Check error log, file permissions, and cert/key pair; fix config and reload per procedure. |
| Legacy client cannot negotiate TLS | TLS version or cipher is no longer permitted by the server | Upgrade driver/client; adjust policy only after compatibility and risk assessment. |
| Connection succeeds, yet `Ssl_cipher` is empty | Client uses an unencrypted transport or you checked the wrong connection | Verify `--protocol=TCP`, driver SSL mode, and check inside the exact session. |

Never fix certificate errors by disabling CA/hostname verification or lowering `tls_version` to legacy protocols. Find the root cause in the trust chain, SAN, expiration, file permissions, driver, or server configuration.

## 9. Hands-on Scenario

An order service connects to MySQL at `db.example.internal`. Requirements dictate that all TCP connections from the service must be encrypted, the application must verify the server identity, and the server must reject unencrypted TCP connections.

**Step 1 — Prepare certificates.** The operations team issues a server certificate from the internal CA. The SAN contains `DNS:db.example.internal`. Only the OS user running MySQL can read the private key; clients receive the root CA through a trusted distribution channel.

**Step 2 — Enable TLS and server policy.** Configure `ssl_ca`, `ssl_cert`, `ssl_key`, restrict `tls_version` to supported versions, and set `require_secure_transport=ON`. Apply configuration following your environment's change process.

**Step 3 — Create the application identity.** Create `orders_app` with the right source host, `REQUIRE SSL`, and grant only required privileges on the `orders` schema. Store the password in a secret manager.

**Step 4 — Configure the application.** The driver connects via hostname `db.example.internal`, trusts the internal CA, and enables verification of both the CA chain and hostname. Do not treat a generic `ssl` flag alone as sufficient proof.

**Step 5 — Verify.** A successful connection must show the TLS version and cipher in the session. Connections with a wrong CA or mismatched hostname must fail on the client. TCP connections with TLS disabled must be rejected by the server.

If the service requires mutual authentication, issue a separate client certificate, configure `ssl_cert` and `ssl_key` on the application side, and update the account condition to `REQUIRE X509` or appropriate `SUBJECT`/`ISSUER` constraints. This strengthens authentication while making client certificate issuance, revocation, and rotation processes even more critical.

## 10. Pre-Production Checklist

- [ ] Server has a certificate issued by an approved CA; SAN matches the hostname/IP used by clients.
- [ ] Private key has minimal read permissions and does not appear in repositories, logs, or shared artifacts.
- [ ] Server allows only TLS versions still supported by the organization.
- [ ] `require_secure_transport=ON` is enabled and tested with TCP connections.
- [ ] Clients use `VERIFY_IDENTITY` or an equivalent mechanism verifying both CA and hostname.
- [ ] Application accounts have minimal source hosts and SQL privileges; `REQUIRE SSL` or `REQUIRE X509` is applied as required.
- [ ] `Ssl_version` and `Ssl_cipher` have been verified in an actual application session.
- [ ] Negative tests for wrong CA, wrong hostname, missing TLS, and missing client certificate (if using mTLS) are all rejected.
- [ ] Certificate expiration monitoring, renewal workflows, CA rotation, and rollback plans are in place.
- [ ] Separate policies exist to protect stored data, binary logs, and backups.

When these steps are applied consistently, MySQL connections are encrypted, applications have a sound basis to verify the legitimate server, and the server can reject connections that violate transport data-protection policies.
