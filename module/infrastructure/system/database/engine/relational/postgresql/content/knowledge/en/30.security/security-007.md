# TLS, Certificates, and Server Identity Verification in PostgreSQL

A Java application connects to PostgreSQL over the network to read customer data, receive payment details, or execute transactions. Without proper connection protection, queries, result sets, and authentication material can be observed or tampered with in transit. **TLS (Transport Layer Security)** is the standard protection layer between clients and a PostgreSQL server.

However, merely "enabling SSL" or seeing that a connection is encrypted **is not enough**. The client also needs to know it is talking to **the exact trusted PostgreSQL server**, rather than a spoofed endpoint capable of acting as a *man-in-the-middle* (MITM).

~~~text
Java app / psql                                   PostgreSQL server
       |                                                 |
       |---- TCP connect and request TLS --------------->|
       |<--- TLS negotiation response -------------------|
       |                                                 |
       |<--- Server certificate and intermediate chain --|
       |                                                 |
       |    Client verifies:                             |
       |    1. Does the chain lead to a trusted CA?      |
       |    2. Is the cert valid and right-purposed?     |
       |    3. Does server DNS/IP match SAN?             |
       |                                                 |
       |==== Encrypted, server-verified TLS channel =====|
       |                                                 |
       |---- PostgreSQL auth (e.g., SCRAM) ------------->|
       |<--- Success / failure --------------------------|
       |                                                 |
       |==== Exchange queries and results over TLS ======|
~~~

Example actively verifying the server using `psql`:

~~~bash
psql "host=db.example.internal port=5432 dbname=appdb user=app_user sslmode=verify-full sslrootcert=/etc/postgresql/client/ca.crt"
~~~

With `verify-full`, the client not only requires encryption, but also verifies that the certificate chain comes from a trusted CA and that the server name being dialed matches an identity in the certificate. If either fails, **the connection must fail rather than silently downgrading to an insecure mode**.

> **Scope:** This lesson focuses on PostgreSQL, `libpq`/`psql`, and the PostgreSQL JDBC Driver (PGJDBC). Specific paths, parameters, and capabilities depend on PostgreSQL, OpenSSL, driver, OS, and service provider versions. Certificate generation snippets are strictly for **labs**; in production, follow your organization's PKI and key-management procedures.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **encryption**, **server authentication**, and **user authentication**.
2. Explain the TLS handshake, public/private keys, X.509 certificates, CAs, and certificate chains.
3. Understand **Subject Alternative Name (SAN)** entries, DNS/IP names, validity periods, and trust anchors.
4. Compare the six `sslmode` modes: `disable`, `allow`, `prefer`, `require`, `verify-ca`, and `verify-full`.
5. Explain why `sslmode=require` is not a default substitute for hostname verification.
6. Generate/inspect lab certificates from an internal CA with appropriate SANs.
7. Configure a PostgreSQL server with `ssl=on`, `ssl_cert_file`, `ssl_key_file`, and minimum TLS versions.
8. Distinguish **server** certificate configuration from the CA used by PostgreSQL to verify **client** certificates.
9. Use `pg_hba.conf` and `hostssl` to reject unencrypted network connections.
10. Connect via `psql` and JDBC using `sslmode=verify-full` and a trusted CA.
11. Inspect the active channel using `pg_stat_ssl`, while knowing the limits of server-side observation.
12. Identify expired certificates, untrusted CAs, hostname mismatches, missing intermediates, and key file permission errors.
13. Design certificate rotation/revocation workflows, expiration monitoring, and incident investigations.
14. Know when **mutual TLS (mTLS)** is needed and how it differs from password/SCRAM authentication.

## 2. Three Distinct Security Questions

A secure PostgreSQL connection must answer three separate questions.

### 2.1. Can Traffic in Transit Be Eavesdropped?

**Transport encryption:** TLS provides data confidentiality between the two endpoints of the TLS session, preventing a network eavesdropper from reading plaintext traffic.

### 2.2. Is the Client Connecting to the Right Server?

**Server identity verification:** the client verifies that the server certificate is signed by a trusted CA and matches the requested hostname. This is why `verify-full` matters.

### 2.3. Who May Log into the Database?

**PostgreSQL user authentication:** the server authenticates the role/client using a method from `pg_hba.conf`, such as `scram-sha-256`, certificate authentication, or another suitable mechanism.

| Protection layer | Answers | Example |
| --- | --- | --- |
| TLS encryption | Can traffic be eavesdropped on this network hop? | TLS 1.3 with strong ciphers |
| Server certificate verification | Is this the expected server name signed by a trusted CA? | `sslmode=verify-full` |
| PostgreSQL authentication | Is the client allowed to log in as the claimed user? | `scram-sha-256` |
| Database authorization | Which tables/functions can the user access? | `GRANT`, roles, RLS |
| Application authorization | Which resources can the end user access? | Tenant/ownership/business ACLs |

### 2.4. TLS Does Not Replace SQL Privileges

Even when a connection uses TLS and verifies the server properly, a role holding `SELECT` on a sensitive table can still read that table. Enforce least privilege in both PostgreSQL and the application.

### 2.5. Passwords Alone Do Not Prove Server Identity

An application may run SCRAM authentication against an endpoint it assumes is the real server. Without verifying the TLS endpoint's identity, an attacker can intercept, relay, or attack other application flows. **Server verification must be an active client-side step.**

## 3. Which Threats Does TLS Address?

Suppose the app and database run on different hosts:

~~~text
App host ---- switch/router/proxy ---- DB host
~~~

Network traffic can traverse infrastructure you do not directly control. TLS protects against:

- **Eavesdropping:** observing queries, results, and auth exchanges in transit.
- **In-transit tampering:** an intermediary modifying packets or forging messages.
- **Server impersonation** when the client *actually* verifies both CA and hostname.

### 3.1. TLS Does Not Solve Every Threat

TLS does not prevent:

- Compromised application or database hosts.
- SQL injection in unparameterized SQL queries.
- Over-privileged database roles.
- Application logs accidentally printing passwords or sensitive data.
- Proxies terminating TLS and forwarding plaintext on a downstream segment.
- A rogue trusted CA or a compromised server private key.

### 3.2. Encrypting One Hop Does Not Mean End-to-End Encryption

~~~text
Client ==TLS==> Proxy ----plaintext----> PostgreSQL
~~~

In this topology, TLS terminates at the proxy. If the proxy -> PostgreSQL hop lacks its own protection, data travels in plaintext there. Identify **where TLS truly terminates** and evaluate every hop.

### 3.3. MITM Without Server Verification

~~~text
Client === TLS === Attacker === TLS === Real DB
~~~

An intermediary can present a certificate it generated itself. If the client checks only "is TLS active?" without checking CA and hostname, per-hop encryption **does not guarantee the client is talking directly to the real DB**.

## 4. What Does an X.509 Certificate Contain?

A TLS server certificate contains a public key and identity metadata, signed by a CA or trust chain.

| Component | Role |
| --- | --- |
| Public key | Public key published in the certificate |
| Private key | Secret held by the endpoint, never sent to clients |
| Subject | Identifying attributes in the certificate |
| Subject Alternative Name (SAN) | List of DNS names/IPs the certificate is valid for |
| Issuer | Entity that issued/signed the certificate |
| Validity (`notBefore`/`notAfter`) | Time window during which the certificate is valid |
| Signature | Enables verifying the certificate was signed by the issuer |
| Basic Constraints | Distinguishes CA certificates from end-entity certificates |
| Key Usage / Extended Key Usage | Restricts allowed purposes of the key/certificate |
| Serial number | Unique identifier under the issuer for tracking/revocation |

### 4.1. Public Key vs. Private Key

The server certificate is shared openly with clients, whereas **the private key must remain secret** on the server or in an approved key store. A leaked private key lets attackers impersonate the endpoint if trust checks otherwise pass.

### 4.2. Never Send the Server Private Key to Clients to "Verify the Server"

Clients need the **CA certificate** or trust anchor to verify the server; they must never receive the server's private key.

### 4.3. A Certificate Can Be Structurally Valid Yet Untrusted

Any self-signed certificate can encrypt a TLS channel. However, if its CA is absent from the client's configured trust store, a client using `verify-full` must **reject** it.

## 5. CAs, Intermediate CAs, and Trust Chains

In PKI, a server certificate is often issued by an intermediate CA, which in turn is signed by a root CA.

~~~text
Root CA (client's trust anchor)
        |
        v
Intermediate CA
        |
        v
Server certificate: db.example.internal
        |
        v
Server private key (kept secret on server)
~~~

### 5.1. The Root CA Is the Trust Anchor

Clients must trust the root CA (or a properly configured trust anchor). A certificate merely "being signed" does not make it trustworthy—it must form a valid chain **leading back to a trust anchor accepted by the client**.

### 5.2. Intermediates Must Be Provided Properly

If the server sends only its leaf certificate and the client lacks the matching intermediate certificate, chain validation can fail even when the root CA is trusted.

### 5.3. Internal CAs vs. Public CAs

- **Internal CA:** suits many databases operating strictly on enterprise networks; requires securely distributing the CA certificate to clients.
- **Public CA:** suits valid public DNS names and matching issuance models; clients may rely on system trust stores when drivers support and configure them properly.

### 5.4. Do Not Arbitrarily Assume Public CAs Cover Every Database

Many DBs use internal names or private endpoints; issuance must follow PKI policy and domain-validation rules. Using an internal CA is not less secure if issuance, key storage, trust-anchor distribution, and rotation are well governed.

### 5.5. Never Copy the CA Private Key onto Database Servers

A server needs only its own TLS endpoint private key; the **root CA private key** must stay isolated inside the certificate-issuance system. If the root CA key is stolen, compromise spreads across every server.

## 6. SAN: Verifying the Server Name

A client wants to connect to:

~~~text
db.example.internal:5432
~~~

The server certificate should include a SAN like:

~~~text
DNS:db.example.internal
~~~

### 6.1. The Connection Name Must Match the Certificate Name

With `sslmode=verify-full`, `libpq` checks the requested hostname according to name-verification rules. If the client connects to `db-read.example.internal` while the certificate lists only `db-write.example.internal`, verification fails.

### 6.2. SAN Is Preferred

In modern certificates, put DNS names in `subjectAltName`; never rely on CN as a substitute for SAN. Some client versions retain legacy CN fallback behavior, yet **new PKI designs must never depend on that fallback**.

### 6.3. Connecting via IP Address

If a client runs:

~~~bash
psql "host=192.0.2.10 dbname=appdb sslmode=verify-full ..."
~~~

the certificate needs a matching IP identity per client rules—typically an `IP:192.0.2.10` SAN, not an IP string stuffed into a DNS SAN.

### 6.4. Hostname Aliases and DNS Failover

If applications connect via a stable alias `db.service.internal` pointing to changing backends, the certificate presented at the TLS endpoint must include that name. Across multi-host failover, **every reachable endpoint must present an identity matching the name the client verifies**.

### 6.5. Changing DNS Alone Does Not Fix Certificate Mismatches

Pointing DNS name A at server B does not add SAN A to server B's certificate. Issue or select certificates matching your actual connection names.

## 7. PostgreSQL and TLS Handshake

Over standard PostgreSQL TCP, the client contacts the server and negotiates TLS before sending session startup credentials.

~~~text
Client                           Server
  |---- TCP connect -------------->|
  |---- SSL/TLS request ---------->|
  |<--- Supported / unsupported ---|
  |---- TLS ClientHello ---------->|
  |<--- TLS ServerHello, cert -----|
  |---- Verify chain and SAN ------|
  |<=== TLS session keys =========>|
  |---- PostgreSQL startup ------->|
  |<--- Authentication ------------|
  |---- Credentials -------------->|
  |<--- ReadyForQuery -------------|
~~~

This shows the logical flow; newer releases may support direct TLS negotiation options. Specific parameters such as `sslnegotiation` must match your `libpq`/server version rather than assuming uniform support everywhere.

### 7.1. TLS Handshake and Verification Occur Before SQL

If the CA or server name fails validation under strict client verification, the connection fails **before becoming an accepted PostgreSQL SQL session**.

### 7.2. GSS Encryption Is a Separate Branch

In environments supporting GSSAPI encryption, `libpq` may select GSS encryption instead of TLS depending on settings and priority. When proving **TLS/X.509 compliance specifically**, inspect `gssencmode` and client behavior rather than assuming `sslmode` alone guarantees TLS was used.

### 7.3. TLS Does Not Automatically Authenticate the Database User

After the TLS handshake, PostgreSQL still applies `pg_hba.conf` to select user authentication—unless policy selects certificate authentication or another method.

## 8. The Six libpq sslmode Modes

`sslmode` is the primary client parameter controlling how PostgreSQL protects the transport channel.

| `sslmode` | Primary behavior | Verifies CA? | Verifies hostname? |
| --- | --- | --- | --- |
| `disable` | Never negotiates TLS | No | No |
| `allow` | Tries non-TLS first, may fall back to TLS | Not in this mode | No |
| `prefer` | Tries TLS first, may fall back to non-TLS | Not in this mode | No |
| `require` | Requires TLS | Normally no; legacy behavior if `root.crt` exists | Does not verify hostname like `verify-full` |
| `verify-ca` | Requires TLS; verifies CA chain | Yes | No |
| `verify-full` | Requires TLS; verifies CA and hostname | Yes | Yes |

**Recommendation:** for production TCP connections to PostgreSQL, prefer `sslmode=verify-full` with a properly configured trust anchor.

### 8.1. disable

~~~bash
psql "host=db.example.internal dbname=appdb sslmode=disable"
~~~

Never uses TLS. Suitable only in specifically approved contexts; never use across untrusted networks carrying sensitive data.

### 8.2. allow

Tries unencrypted first, then TLS if the server requires it. Unsuitable when encryption is mandatory.

### 8.3. prefer

Common `libpq` default for TCP, falling back to plaintext if the server lacks TLS. Prioritizes convenience and compatibility—**not enforced security**.

### 8.4. require

`require` prevents plaintext in standard SSL flows, yet **does not by default verify server hostnames**. `libpq` also has legacy backward-compatibility behavior where finding a root CA file in the default location can make `require` behave like `verify-ca` in certain cases. Because of that ambiguity, never use `require` as proof of server identity verification.

### 8.5. verify-ca

The client verifies the server certificate chains to a trusted CA. Yet if the same CA issued certificates for both `db-a.internal` and `db-b.internal`, checking only the CA **cannot stop misdirected connections to the wrong host**, because the target name goes unchecked.

### 8.6. verify-full

Combines **mandatory TLS + valid CA chain + matching DNS/IP name**. Use this whenever the client knows its target endpoint.

## 9. Why Are prefer and require Not Enough Against MITM?

Suppose the client wants `db-prod.internal`.

### 9.1. With prefer

If TLS is unavailable or negotiation is downgraded, the client falls back to plaintext—violating "no plaintext" requirements.

### 9.2. With require

The channel is encrypted, yet the client does not verify **the true identity of `db-prod.internal`**. A rogue endpoint presenting its own certificate can complete TLS if chain/hostname checks are absent.

### 9.3. With verify-ca

Trusting the CA is not enough to prove it is **the right hostname**. When a CA signs certificates for multiple servers, you must prevent another valid server's certificate from being substituted.

### 9.4. With verify-full

The certificate must satisfy both trust-chain and endpoint-name checks simultaneously. If either fails, the client rejects the connection.

### 9.5. Verification Still Depends on a Well-Managed Trust Store

If a client trusts an untrusted CA, or an internal CA is compromised and issues rogue certs, `verify-full` cannot magically rescue broken PKI. Govern issuance, CA distribution, private-key protection, and revocation.

## 10. Configuring Connections with libpq and psql

A practical command:

~~~bash
psql "host=db.example.internal port=5432 dbname=appdb user=app_user sslmode=verify-full sslrootcert=/etc/postgresql/client/ca.crt"
~~~

### 10.1. sslrootcert Is the Trusted CA Certificate

`sslrootcert` points to the CA/trust-anchor file the client uses to verify **the server certificate**.

It is not the server's private key, not a login token, and not a database password.

### 10.2. sslcert and sslkey Are Client Certificates

`sslcert` and `sslkey` are used when **the client must present its own certificate**, such as in mTLS. They do not replace `sslrootcert` for verifying the server.

### 10.3. Never Pass Passwords on the Command Line

Avoid:

~~~bash
# Not recommended:
# psql "host=... user=... password=very_secret ..."
~~~

because passwords leak into shell history, process lists, and logs. Use interactive prompts, protected `.pgpass` files, secret managers, or other secure auth mechanisms.

### 10.4. Default CA Paths Depend on the OS

`libpq` looks by default in the user's PostgreSQL config directory (e.g., `~/.postgresql/root.crt` on Unix). On Windows, paths and defaults differ by client. For reproducible deployments, specify `sslrootcert` explicitly per your driver's documentation.

### 10.5. Do Not Rely on Unix Sockets for TLS Tests

Over a same-host Unix-domain socket, TLS applies to TCP rather than sockets; `sslmode` does not carry the same meaning. To test TLS, specify a TCP `host` explicitly and inspect `pg_stat_ssl`.

## 11. Distinguishing host, hostaddr, and Certificate Name

`libpq` accepts both:

~~~text
host=db.example.internal
hostaddr=192.0.2.10
~~~

### 11.1. host

Logical server name, used for endpoint selection and **hostname verification** in `verify-full`.

### 11.2. hostaddr

Network IP address to open the TCP connection without normal DNS resolution. Useful for special routing or debugging.

### 11.3. Combined Usage

~~~bash
psql "host=db.example.internal hostaddr=192.0.2.10 port=5432 dbname=appdb sslmode=verify-full sslrootcert=/etc/postgresql/client/ca.crt"
~~~

When both are supplied, `libpq` connects TCP to `hostaddr` while still using `host` for identity checks (including hostname verification) per client rules. Handy when debugging DNS or tunnels—never use it to silently route production to unmanaged endpoints.

### 11.4. Do Not Use hostaddr Alone to Mask Certificate DNS Mismatches

If only an IP is used and the certificate lacks a matching IP SAN, `verify-full` fails. That is intended protection, not a bug to work around with `sslmode=require`.

### 11.5. Multi-Host and Failover

When a connection string lists multiple hosts, each server may present a different certificate. Ensure valid certificates exist for every candidate endpoint name; never verify one host and assume the rest are automatically trusted.

## 12. Server-Side TLS Configuration in PostgreSQL

Typical settings in `postgresql.conf`:

~~~conf
# Illustrative only: paths depend on OS and packaging.
ssl = on
ssl_cert_file = '/etc/postgresql/tls/server.crt'
ssl_key_file  = '/etc/postgresql/tls/server.key'
ssl_min_protocol_version = 'TLSv1.2'
~~~

### 12.1. ssl = on

Allows PostgreSQL to accept TLS connections when supported by the build/server. It **does not force every client to use TLS**; configure client policies and `pg_hba.conf` accordingly.

### 12.2. ssl_cert_file

The server certificate file. If intermediate certificates are needed, assemble the PEM chain properly per documentation/PKI. Never place a CA private key in this file.

### 12.3. ssl_key_file

The server's private key. Read access must be restricted to the PostgreSQL OS service account or approved key-management mechanism.

### 12.4. ssl_min_protocol_version

Set the minimum protocol version per organizational policy and client compatibility. TLS 1.2 is a common floor; TLS 1.3 is preferred where both sides support it. Never enable deprecated protocol versions for one legacy client without a risk assessment.

### 12.5. Cipher Parameters

PostgreSQL also provides settings like `ssl_ciphers`, though cipher-suite controls depend on TLS/OpenSSL versions: TLS 1.2 cipher settings do not necessarily govern TLS 1.3 identically. Measure live behavior with `pg_stat_ssl` and crypto policies rather than guessing from one config line.

### 12.6. Never Store Private Keys in Source Repositories

Public certificates and private keys do not share the same sensitivity. Never commit `server.key`, CA private keys, or key passphrases to Git, public images, logs, or shared docs.

## 13. Private Key File Permissions

On Unix systems, using a valid PostgreSQL service account:

~~~bash
# Illustrative on a DBA-managed host.
chown postgres:postgres /etc/postgresql/tls/server.key
chmod 0600 /etc/postgresql/tls/server.key
~~~

### 13.1. Why Mode 0600?

The private key should be readable only by the appropriate service account. PostgreSQL enforces key permission checks on many platforms; overly permissive modes can prevent the server from starting or loading certificates.

### 13.2. Environments with Different Permission Models

Some packaging models allow root-owned keys with specific group permissions where supported; Windows uses ACLs rather than `chmod`. Follow PostgreSQL and OS-specific guidance rather than copying these commands onto hosts with different paths or users.

### 13.3. Containers and Secret Mounts

In containers/Kubernetes, secrets may be mounted at custom paths. Ensure UID/GID, permissions, and secret lifecycle align with the PostgreSQL process—never dump secrets into env vars or bake keys into images just to bypass permission errors.

### 13.4. Backups and Private Keys

Backups containing private keys must be protected as secret material; if a key leaks, restoring the file is not enough—rotate and revoke per PKI procedures.

## 14. What Is Server-Side ssl_ca_file Used For?

This is a frequent point of confusion:

~~~conf
ssl_ca_file = '/etc/postgresql/tls/client-ca.crt'
~~~

### 14.1. The Server's CA Is Not Automatically Trusted by Clients

Configuring `ssl_ca_file` on the PostgreSQL server primarily provides the trust anchor for **the server to verify client certificates** during certificate-based authentication.

### 14.2. Clients Still Need Their Own Trust Anchor

A client running `sslmode=verify-full` must have a valid CA or trust store **on the client side**—for example via `sslrootcert`. Placing a CA on the server does not push a trust anchor out to clients.

### 14.3. Server-Only Verification Needs No Client Cert

If an app uses password/SCRAM and only needs server verification, the client does not need `sslcert`/`sslkey`, nor must the server demand client certificates.

### 14.4. mTLS Requires Client Certificate Policy

When the server must verify client certificates, you need a server-side CA and matching `pg_hba.conf` rules, covered in a dedicated section below.

## 15. pg_hba.conf: Enforcing TLS Server-Side

`sslmode=verify-full` is a client policy. To stop clients from connecting in plaintext, the server needs matching acceptance rules, primarily via `hostssl`.

Example accepting only the application network:

~~~conf
# Example lines in pg_hba.conf; adjust CIDRs and real roles.
hostssl appdb app_user 10.20.0.0/16 scram-sha-256

# Reject non-TLS TCP connections.
hostnossl all all 0.0.0.0/0 reject
hostnossl all all ::/0      reject
~~~

### 15.1. hostssl

`hostssl` matches only TCP connections using TLS, filtered by database/user/address. It does not grant access if authentication fails.

### 15.2. hostnossl

`hostnossl` matches non-TLS TCP connections. Explicit `reject` lines make a no-plaintext policy clear.

### 15.3. Line Order Matters

`pg_hba.conf` is evaluated in order. A broader `host all all ...` line placed higher up can match clients before your intended policy. Always read **the entire ordered sequence of relevant lines** in the live config.

### 15.4. Do Not Forget IPv6

If apps or servers use IPv6, rejecting only `0.0.0.0/0` leaves IPv6 paths uncovered. Check both address families.

### 15.5. Even hostssl Does Not Force Clients to Run verify-full

The server knows whether the connection uses TLS. The server **cannot reliably tell** whether the client verified the server's hostname and CA. Always enforce `verify-full` in app/JDBC configuration too.

## 16. TLS and SCRAM Authentication

Example:

~~~conf
hostssl appdb app_user 10.20.0.0/16 scram-sha-256
~~~

### 16.1. Two Independent Layers

- `hostssl`: the connection must use TLS to match this rule.
- `scram-sha-256`: the server enforces SCRAM password authentication.

### 16.2. SCRAM Does Not Replace TLS

SCRAM improves password authentication over legacy methods, yet does not encrypt SQL queries or results. TLS remains required to protect the data channel.

### 16.3. TLS Does Not Replace SCRAM

A client can connect to the right server over TLS and still be rejected for a wrong password or role—that is proper user authentication.

### 16.4. Channel Binding Adds Another Link

Supported client/server versions offer SCRAM channel binding to bind authentication to the established TLS channel. In `libpq`, `channel_binding` supports options such as `disable`, `prefer`, and `require`.

### 16.5. Channel Binding Does Not Replace verify-full

Channel binding helps counter certain relay/MITM attacks when supported end-to-end. It **is never a reason to skip CA/hostname verification** in `verify-full`.

## 17. Inspecting TLS Connections via pg_stat_ssl

After logging in:

~~~sql
SELECT
    pid,
    ssl,
    version,
    cipher,
    bits
FROM pg_stat_ssl
WHERE pid = pg_backend_pid();
~~~

### 17.1. ssl

If `ssl = true`, the current backend uses TLS as seen by the PostgreSQL server.

### 17.2. version

Shows the negotiated TLS version, such as `TLSv1.3`, when supported.

### 17.3. cipher

Shows the negotiated cipher suite. Never hardcode assertions expecting one exact cipher string across all OS, OpenSSL, and PG versions.

### 17.4. bits

Reports encryption bit strength; never assume "higher bits means the whole connection is secure" without checking protocol versions, authentication, and key management.

### 17.5. Observation Limit

**The server knows whether TLS is active, yet cannot tell from `pg_stat_ssl` whether the client actually used `sslmode=verify-full`.** That is a client-side configuration and verification step.

## 18. SHOW ssl Differs from pg_stat_ssl

~~~sql
SHOW ssl;
~~~

reports whether the server configuration has SSL/TLS support enabled.

~~~sql
SELECT ssl, version, cipher
FROM pg_stat_ssl
WHERE pid = pg_backend_pid();
~~~

reports the state of **the current connection**.

### 18.1. A TLS-Enabled Server Can Still Accept Plaintext

If `ssl = on` while `pg_hba.conf` allows `host` or `hostnossl` without TLS and a client sets `sslmode=disable`, plaintext TCP connections can still be accepted.

### 18.2. Server ssl = on Does Not Prove Apps Use TLS

Never cite `SHOW ssl` alone as compliance proof of encrypted transport.

### 18.3. Check the Actual App Session

A DBA connecting with `psql` over TLS does not prove the application's connection pool uses TLS. Inspect app client configuration and the corresponding backend sessions.

### 18.4. pg_stat_ssl Also Has Client Certificate Columns

In supporting versions, `pg_stat_ssl` exposes `client_dn`, `client_serial`, and `issuer_dn` when client certificates are presented. These relate to mTLS; they say nothing about how the client verified the server certificate.

## 19. Checking TLS Info in psql

Inside a `psql` session, the meta-command:

~~~text
\conninfo
~~~

displays connection details, including SSL/TLS usage and related attributes depending on version.

### 19.1. Combine Client and Server Evidence

A sound verification checklist:

1. Confirm connection strings specify `sslmode=verify-full`.
2. Confirm trust anchor and certificate names match.
3. Connect successfully to the real endpoint.
4. Inspect `\conninfo` and `pg_stat_ssl` for the live TLS session.
5. Run negative tests in a lab: wrong CA or wrong hostname **must fail**.

### 19.2. Why Run Negative Tests?

If you point `sslrootcert` at an unrelated CA and the connection still succeeds, the app is not enforcing `verify-full` as expected or is using a different connection path/trust store. Investigate the client/driver rather than ignoring it.

### 19.3. Never Test by Breaking Production Certificates

Create a lab endpoint or staging environment with an intentionally mismatched host/certificate to verify failure modes. Never break production certificates to watch dashboards turn red.

## 20. Lab: Building a Test CA and Server Certificate with SAN

This section demonstrates PKI for learning on a Unix host with OpenSSL. **Never use test keys in production.** The domain `db.lab.internal` is illustrative: ensure matching DNS/resolution or a controlled test setup.

### 20.1. File Layout

~~~text
pg-tls-lab/
    ca.key          # CA private key: SECRET
    ca.crt          # Public CA certificate: distributed to clients for trust
    server.key      # Server private key: SECRET
    server.csr      # Certificate signing request
    server.ext      # SAN, EKU, key usages
    server.crt      # Server certificate signed by CA
~~~

### 20.2. Creating the Directory

~~~bash
mkdir -p ./pg-tls-lab
cd ./pg-tls-lab
umask 077
~~~

`umask 077` restricts default permissions on newly created files on Unix. Still verify final permissions before PostgreSQL reads the key.

### 20.3. Creating a Test CA

~~~bash
openssl req -x509 -newkey rsa:3072 -nodes \
  -days 90 -sha256 \
  -subj "/CN=PostgreSQL Training Root CA" \
  -addext "basicConstraints=critical,CA:TRUE" \
  -addext "keyUsage=critical,keyCertSign,cRLSign" \
  -keyout ca.key -out ca.crt
~~~

**Explanation:**

- `-x509` creates a self-signed certificate for the test CA.
- `-newkey rsa:3072` generates an example 3072-bit RSA key.
- `-nodes` leaves the key unencrypted without a passphrase; convenient for labs only—not recommended for production CA private keys.
- `-days 90` sets a short validity window for the lab CA.
- `basicConstraints CA:TRUE` marks it as a CA.
- `keyCertSign` grants certificate-signing usage.

`-addext` requires a compatible OpenSSL version. Production environments typically use a managed PKI/CA service rather than manual CLI issuance.

### 20.4. Creating the Server Private Key and CSR

~~~bash
openssl req -new -newkey rsa:3072 -nodes \
  -subj "/CN=db.lab.internal" \
  -keyout server.key -out server.csr
~~~

### 20.5. Creating the server.ext Extension File

~~~ini
basicConstraints = critical, CA:FALSE
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = DNS:db.lab.internal,IP:127.0.0.1
~~~

In practice, the SAN list must match the exact DNS names/IPs **actually used to connect**. `IP:127.0.0.1` here is only for local demo testing when PostgreSQL runs locally or over a controlled tunnel.

### 20.6. Signing the Server Certificate with the CA

~~~bash
openssl x509 -req \
  -in server.csr \
  -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out server.crt \
  -days 30 -sha256 \
  -extfile server.ext
~~~

This certificate is signed by our lab CA. It is **not automatically trusted anywhere**; clients must be given `ca.crt` explicitly and enable verification mode.

### 20.7. Inspecting the Certificate

~~~bash
openssl x509 -in server.crt -noout \
  -subject -issuer -dates -ext subjectAltName
~~~

You should see the issuer pointing to the lab CA and the expected SAN entries.

### 20.8. Verifying Chain and Hostname Outside PostgreSQL

~~~bash
openssl verify \
  -CAfile ca.crt \
  -purpose sslserver \
  -verify_hostname db.lab.internal \
  server.crt
~~~

Compatible OpenSSL versions validate the certificate against the given CA and hostname. This validates **the certificate files**, without replacing a real PostgreSQL connection test via a driver/`sslmode=verify-full`.

## 21. Attaching Test Certificates to PostgreSQL

Assuming you administer a lab database and placed the certificate files in a directory readable by the PostgreSQL process:

~~~conf
ssl = on
ssl_cert_file = '/path/to/lab/server.crt'
ssl_key_file  = '/path/to/lab/server.key'
ssl_min_protocol_version = 'TLSv1.2'
~~~

These paths are **placeholders**; replace them with actual lab paths.

### 21.1. Check Private Key Permissions

`server.key` must have valid ownership and permissions for PostgreSQL on your OS. Never run `chmod 777` to "fix SSL errors."

### 21.2. Applying Configuration

Some SSL parameters take effect on reload while others require a restart depending on context and version. Inspect:

~~~sql
SELECT
    name,
    setting,
    pending_restart
FROM pg_settings
WHERE name IN (
    'ssl',
    'ssl_cert_file',
    'ssl_key_file',
    'ssl_ca_file',
    'ssl_min_protocol_version'
)
ORDER BY name;
~~~

Never assume `pg_reload_conf()` applied everything merely because it returned `true`. Check server logs, active settings, and `pending_restart`.

### 21.3. Connecting with the Lab CA

~~~bash
psql "host=db.lab.internal port=5432 dbname=appdb user=app_user sslmode=verify-full sslrootcert=/path/to/lab/ca.crt"
~~~

`db.lab.internal` must resolve to the server holding `server.crt`, or use a controlled local hosts entry/route.

### 21.4. Include Only the Public Root CA in Distributed Trust Stores

Never copy `ca.key` to clients. Distribute only the public `ca.crt` over a trusted channel and verify its provenance.

## 22. Positive and Negative Tests

Use your **lab database** with the CA/certificates above.

### 22.1. Valid Case

~~~bash
psql "host=db.lab.internal dbname=appdb user=app_user sslmode=verify-full sslrootcert=/path/to/lab/ca.crt"
~~~

Succeeds when DNS/routing, certificate, privileges, and PostgreSQL authentication all align.

### 22.2. Wrong CA

~~~bash
psql "host=db.lab.internal dbname=appdb user=app_user sslmode=verify-full sslrootcert=/path/to/other-ca.crt"
~~~

Since `other-ca.crt` is not the trust anchor for the server certificate, verification must fail.

### 22.3. Wrong Hostname

~~~bash
psql "host=not-db.lab.internal dbname=appdb user=app_user sslmode=verify-full sslrootcert=/path/to/lab/ca.crt"
~~~

Even when routing reaches the same server, `not-db.lab.internal` is absent from SAN, so client verification must reject it.

### 22.4. Expired Certificate

If the server certificate is outside its validity window, strict clients must reject it given accurate clocks and validation.

### 22.5. Intentional Plaintext Attempt

~~~bash
psql "host=db.lab.internal dbname=appdb user=app_user sslmode=disable"
~~~

If server policy blocks plaintext via `pg_hba.conf`, this connection must be rejected.

### 22.6. Never "Fix" a Failing Negative Test with require

If `verify-full` reports a verification error, **never switch to `require` to silently bring production back up**. Find the real cause: SAN, CA, intermediate, hostname, clock, trust store, proxy, or actual certificate.

## 23. PostgreSQL JDBC: Connecting with verify-full

In a Java application:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.util.Properties;

public class SecurePgConnection {
    public static void main(String[] args) throws Exception {
        String url =
            "jdbc:postgresql://db.example.internal:5432/appdb";

        Properties props = new Properties();
        props.setProperty("user", "app_user");
        props.setProperty(
            "password",
            System.getenv("DB_PASSWORD")
        );
        props.setProperty("sslmode", "verify-full");
        props.setProperty(
            "sslrootcert",
            "/etc/postgresql/client/ca.crt"
        );

        try (Connection conn =
                 DriverManager.getConnection(url, props);
             PreparedStatement ps = conn.prepareStatement(
                 "SELECT ssl, version, cipher " +
                 "FROM pg_stat_ssl WHERE pid = pg_backend_pid()"
             );
             ResultSet rs = ps.executeQuery()) {

            if (rs.next()) {
                System.out.println(
                    "TLS=" + rs.getBoolean("ssl")
                    + ", version=" + rs.getString("version")
                );
            }
        }
    }
}
~~~

### 23.1. PGJDBC and libpq Are Different Clients

PGJDBC shares similar properties like `sslmode`/`sslrootcert`, yet its file handling, trust stores, and SSL factories can differ from `libpq`. Never assume "if `psql` works, JDBC works too" when they read different CAs.

### 23.2. sslmode=verify-full in JDBC

Setting it explicitly makes policy clear and avoids relying on driver or pool defaults. Legacy flags like `ssl=true` carry version-dependent semantics in PGJDBC; declare `sslmode=verify-full` explicitly and test.

### 23.3. Certificate Must Match the Host in the URL

`jdbc:postgresql://db.example.internal:5432/appdb` uses `db.example.internal` as the endpoint identity. Switching the URL to an IP without a matching IP SAN causes verification to fail.

### 23.4. Password Handling

This example reads `DB_PASSWORD` for brevity, yet production should use a controlled secret manager/injection mechanism and never log `Properties` containing passwords. If the secret is missing, fail cleanly before attempting to connect.

### 23.5. Use a Supported Driver

Ensure a supported PGJDBC version is on the classpath; verify TLS features, SSL factories, and JDK truststore behavior for your exact driver and JDK versions.

## 24. JDBC URLs, Properties, and Connection Pools

You can configure TLS in the URL:

~~~text
jdbc:postgresql://db.example.internal:5432/appdb?sslmode=verify-full&sslrootcert=/etc/postgresql/client/ca.crt
~~~

Or via `Properties` as shown above.

### 24.1. Watch Special Characters in Query Strings

If the CA path contains spaces, `&`, or special characters, URL-encode it per JDBC URL rules or pass it via `Properties` to avoid parser misinterpretation.

### 24.2. Connection Pools Do Not Automatically Improve Security

HikariCP and other pools manage connections, yet if driver properties specify `sslmode=prefer`, the pool simply maintains many weakly configured sessions. Configure strict TLS directly on the datasource.

### 24.3. Certificate Rotation and Long-Lived Connections

Active TLS sessions retain the cryptographic state from their original handshake. Swapping a server certificate does not immediately force existing pooled connections to re-handshake. Maintain connection max-lifetime policies, staged rollouts, reconnects, and monitoring.

### 24.4. Do Not Check Only Admin Connections

To validate Java environments, test with the application's actual datasource, driver, trust material, and production-like endpoint, then inspect `pg_stat_ssl` on the app's sessions.

## 25. Trust Stores: Custom CAs, OS Stores, and Java

Not all clients read CAs from the same place.

### 25.1. libpq

Uses `sslrootcert` and default CA files in the PostgreSQL client directory. Some versions add system trust-store options with specific semantics; use only after confirming version behavior.

### 25.2. PGJDBC

With standard SSL factories, `sslrootcert` specifies the CA file for certificate verification. Other Java/JSSE setups rely on the JVM truststore or custom SSL factories. Verify **which trust material the driver actually loads**.

### 25.3. OS/Browser Trust Does Not Automatically Apply to Every Java Client

A CA trusted by browsers or OS CLI tools may not be trusted by PGJDBC's active SSL factory, and vice versa.

### 25.4. Avoid Trust-All Configurations

A custom SSL factory accepting every certificate or disabling hostname verification gets the app connecting while destroying server authentication. Never use trust-all outside isolated test harnesses, and keep it out of production builds.

### 25.5. Trust Anchors Are Security Configuration

Treat changes to `ca.crt` or JVM truststores with the same code review, versioning, and rollout rigor as security policies—never as harmless data files.

## 26. What Is Mutual TLS (mTLS)?

Normally TLS authenticates the server while the client logs in to PostgreSQL with SCRAM.

In **mTLS**, the server also requests and verifies **the client's certificate**:

~~~text
Client                                       PostgreSQL
  |---- ClientHello ---------------------------->|
  |<--- Server cert -----------------------------|
  |---- Client verifies CA + hostname -----------|
  |<--- Server requests client certificate ------|
  |---- Client certificate + proof of key ------>|
  |<--- Server verifies client CA / identity ----|
  |==== Mutually authenticated TLS channel ======|
  |---- PostgreSQL auth per pg_hba.conf -------->|
~~~

### 26.1. Two Certificates with Different Roles

| Object | Where does the private key live? | Who trusts its CA? |
| --- | --- | --- |
| Server cert | Server / TLS proxy | Client trusts CA to verify server |
| Client cert | Application / client | PostgreSQL trusts CA to verify client |

### 26.2. Issue Distinct Certificates per Service

Never issue one shared client private key across all applications. Give each service/role its own identity, lifecycle, and revocation boundary so one client can be revoked without breaking everyone else.

### 26.3. mTLS Does Not Replace Authorization

The server verifying a client certificate does not automatically let that role read every table. PostgreSQL authentication/role mapping and `GRANT`/RLS still apply.

### 26.4. mTLS Increases PKI Operational Overhead

You must issue, distribute, rotate, and revoke **client certificates**, monitor expiry, and handle private-key compromise per workload.

## 27. Enabling Client Certificate Verification on the Server

On the server, specify the CA used to verify client certificates:

~~~conf
ssl = on
ssl_cert_file = '/etc/postgresql/tls/server.crt'
ssl_key_file  = '/etc/postgresql/tls/server.key'
ssl_ca_file   = '/etc/postgresql/tls/client-ca.crt'
~~~

### 27.1. Using clientcert in pg_hba.conf

Example requiring **both SCRAM password and client certificate**:

~~~conf
hostssl appdb app_user 10.20.0.0/16 scram-sha-256 clientcert=verify-full
~~~

Under this rule, the client must establish TLS, pass server verification of its client certificate, and pass SCRAM authentication (along with matching identity/mapping rules).

### 27.2. clientcert verify-ca vs. verify-full

In `pg_hba.conf`'s `clientcert` option:

- `verify-ca` verifies the client certificate is signed by a trusted CA.
- `verify-full` additionally enforces that the client certificate's identity matches the requested PostgreSQL role per mapping rules.

Do not confuse these with client-side `sslmode=verify-ca` and `sslmode=verify-full` used to **verify the server**.

### 27.3. Certificate Authentication

PostgreSQL also supports the `cert` method in `pg_hba.conf`, authenticating roles directly from client certificates via mapping rules. That differs from `scram-sha-256 clientcert=verify-full`, which combines certificate verification with password auth.

### 27.4. pg_ident.conf

When mapping certificate identities to PostgreSQL roles, configure `map` and `pg_ident.conf` where supported. Never assume a certificate's CN always matches the database role verbatim without managing mappings.

## 28. Configuring Client Certificates

With `libpq`, an mTLS connection looks like:

~~~bash
psql "host=db.example.internal dbname=appdb user=app_user sslmode=verify-full sslrootcert=/etc/postgresql/client/server-ca.crt sslcert=/etc/postgresql/client/app-client.crt sslkey=/etc/postgresql/client/app-client.key"
~~~

### 28.1. Three Files with Distinct Roles

- `server-ca.crt`: trust anchor allowing the client to verify the server certificate.
- `app-client.crt`: certificate the app presents to the server.
- `app-client.key`: the app's private key; must remain secret.

### 28.2. A Client Certificate Does Not Verify the Server

Even when supplying `sslcert` and `sslkey`, the client **still needs `sslrootcert` and `verify-full`** to protect server identity.

### 28.3. Client Key Permissions

Client private keys also require strict file permissions. PGJDBC, `libpq`, and OSes read keys differently; grant minimum read access to the service process only.

### 28.4. Never Reuse Test Keys

Never copy the lab's `server.key` to use as `app-client.key`. Certificates must carry appropriate key usages and identities rather than reusing one keypair across roles.

## 29. Expired Certificates: Real-World Impact

Certificates carry validity timestamps:

~~~text
notBefore = ...
notAfter  = ...
~~~

Once a server certificate expires according to the client, new verified connections fail.

### 29.1. Monitor Before Expiration

Alert across multiple thresholds (e.g., 30 days, 14 days, 7 days, 1 day) aligned with your issuance cycle. These are illustrative thresholds, not mandatory standards.

### 29.2. System Clocks

Severe clock skew on client or server can make a valid certificate appear "not yet valid" or "expired." Keep NTP synchronized and check system clocks during troubleshooting.

### 29.3. Never Downgrade sslmode During an Outage

An expired certificate signals a rotation/PKI failure to fix—not a reason to downgrade `verify-full` to `prefer`.

### 29.4. Connection Pools Delay Symptoms

Existing pooled connections can keep working while new connections fail due to an expired cert or updated trust store, causing staggered failures across pods/instances.

## 30. Rotating Server Certificates

A rotation workflow should keep client verification working continuously through cutover.

~~~text
1. Audit active DNS/IP names and SANs in use.
2. Issue the new certificate from a trusted CA.
3. Verify key match, chain, validity dates, EKU, and SANs.
4. Store certificate + private key in secure secret storage.
5. Update server via supported reload/restart mechanism.
6. Open fresh verify-full connections from representative clients.
7. Inspect pg_stat_ssl and handshake error logs.
8. Monitor pool reconnects, failover nodes, and replicas.
9. Remove old certificate/key on approved schedule.
~~~

### 30.1. Replacing Only the Leaf Under the Same CA

Clients trusting the existing CA continue verifying the server seamlessly once it presents the new certificate, provided SANs, chain, and dates are valid.

### 30.2. Changing the CA

This is a larger migration: clients must receive the new trust anchor in time. A transition window trusting both old and new CAs in a controlled bundle allows safe rollout; never remove the old CA while servers still present certificates signed by it unless a strict cutover is planned.

### 30.3. Never Rotate One Node and Forget Failover Endpoints

In multi-host clusters or proxies, clients may switch endpoints on failover. All TLS endpoints must hold valid certificates before receiving traffic.

### 30.4. Maintain a Controlled Rollback

If a new certificate has bad SANs, chain, or permissions, keep an approved valid certificate ready for rollback. Never roll back to a compromised key or expired certificate merely for convenience.

## 31. Revoking Certificates and Compromised Keys

A certificate may still be within its validity dates when its private key leaks or an identity is retired.

### 31.1. Deleting the File on the Server Is Not Enough

If an attacker stole the private key, deleting the local copy does not invalidate stolen copies. Issue a new keypair, revoke the old certificate per CA policy, and update trust/revocation controls.

### 31.2. CRL/OCSP and Enforcement Reality

The PostgreSQL/`libpq` ecosystem supports revocation-list options (e.g., `sslcrl`/`sslcrldir` on clients depending on version, `ssl_crl_file` on the server for client certs). Revocation checking differs from browsers/OSes and may not be enabled automatically as assumed.

### 31.3. Test Revocation Enforcement Empirically

If policy requires that revoked certificates cannot log in, confirm clients/servers actively enforce CRL/OCSP via supported options and test a revoked certificate in a lab.

### 31.4. Short-Lived Certificates Still Help

Short validity windows and automated rotation limit how long a compromised certificate remains valid—though they never replace private-key protection and incident response.

## 32. Inspecting Certificates with OpenSSL

Inspect a certificate file:

~~~bash
openssl x509 -in server.crt -noout \
  -subject -issuer -dates -ext subjectAltName
~~~

Verify public certificate and private key match by public key (illustrative; protect the private key):

~~~bash
openssl x509 -in server.crt -pubkey -noout > cert.pub
openssl pkey -in server.key -pubout > key.pub
diff cert.pub key.pub
~~~

If they differ, the certificate and private key are not a matching pair.

### 32.1. Never Upload Private Keys to Online Checkers

Run these commands only in trusted environments. Never paste `server.key` or `ca.key` into public websites to "inspect" them.

### 32.2. Inspect Which Certificate the Server Presents

On compatible OpenSSL versions:

~~~bash
openssl s_client \
  -starttls postgres \
  -connect db.example.internal:5432 \
  -servername db.example.internal \
  -showcerts
~~~

`-starttls postgres`/SNI support and flags depend on OpenSSL version. This diagnoses chains and handshakes, without replacing **real client driver tests** using `verify-full`.

### 32.3. SNI and Multi-Tenant Proxies

When traffic passes through proxies using SNI to choose certificates or backends, ensure clients and proxies forward the expected server name. If a proxy serves a mismatched certificate, fix SNI/certificate config—never disable hostname verification.

## 33. Common TLS Errors

### 33.1. Certificate Verify Failed

Likely causes:

- CA missing from trust anchor.
- Server cert signed by a different CA.
- Missing intermediate certificate.
- Certificate expired or not yet valid.
- Wrong Extended Key Usage/purpose.
- System clock skew.

### 33.2. Hostname Mismatch

The client connected using a name or IP missing from SANs. Often caused by new endpoint aliases, `localhost`, raw IPs, or certificates issued only for backend names.

### 33.3. Server Does Not Support SSL

The server or proxy did not complete TLS negotiation as expected, or TLS is disabled/unsupported. Check server config, TCP path, proxies, and versions.

### 33.4. No pg_hba.conf Entry

The client completed TLS handshake, yet failed to match a rule for database/user/address/SSL state. Inspect HBA rules and ordering—never switch `verify-full` to `disable`.

### 33.5. Could Not Load Private Key

Wrong path, unsupported key format, wrong owner/permissions, or key mismatch with the certificate. Read server logs and check file permissions on the host.

### 33.6. Client Unexpectedly Does Not Use TLS

May be connecting via Unix socket, `sslmode` wasn't passed to the driver, GSS encryption was chosen, or you are inspecting a different session. Check connection properties, `pg_stat_ssl`, and the real network path.

### 33.7. Old Clients Cannot Negotiate Protocol/Cipher

Legacy JDK/OpenSSL/driver builds may lack support for modern TLS policies. The sustainable fix is **upgrading the client/driver** or making a risk-reviewed compatibility adjustment—never blindly enabling TLS 1.0/1.1.

### 33.8. Mismatch Occurs After Failover

The failover node holds a certificate lacking the service alias SAN, signed by another CA, or missing an intermediate. Verify every endpoint and trust chain before cutover.

## 34. Differences Between SSL, TLS, Certificates, and Passwords

| Term | Meaning in PostgreSQL context |
| --- | --- |
| SSL | Legacy name still appearing in parameters like `sslmode` |
| TLS | Modern protocol securing the transport session |
| Server certificate | Public identity/key of the TLS server |
| Server private key | Server secret key used during handshake |
| CA certificate | Trust anchor used to verify issued certificates |
| Server identity | Expected DNS/IP name verified by the client |
| Client certificate | Public identity/key presented by the client for mTLS |
| Client private key | Client's secret key |
| SCRAM password auth | PostgreSQL user authentication mechanism |
| GRANT/RLS | Data authorization after authentication |

### 34.1. "ssl" in Config Names Does Not Mean Obsolete SSL Protocol

PostgreSQL keeps parameter names like `ssl` and `sslmode` for compatibility. Modern connections normally negotiate TLS 1.2 or TLS 1.3 depending on client and server support.

### 34.2. Certificates Are Not User Passwords

A certificate proves the binding between a keypair and an identity in PKI. Depending on `pg_hba.conf`, the server may still require a password and/or a separate client certificate.

### 34.3. Server Authentication Differs from Client Authentication

Client-side `sslmode=verify-full` verifies the server. Server-side `clientcert=verify-full` in `pg_hba.conf` verifies the client certificate's identity under mTLS. Both use the string `verify-full`, yet they verify **opposite directions**.

## 35. TLS Policy in Multi-Hop Environments

Deployments often look like:

~~~text
App -> Sidecar / pooler -> Load balancer -> PostgreSQL
~~~

### 35.1. Map Every TLS Termination Point

For each hop, document:

- Who is the TLS client?
- Who presents the server certificate?
- Which hostname does the client verify?
- Where is the CA/trust store located?
- Is the next hop encrypted independently?

### 35.2. PgBouncer

With PgBouncer, one TLS channel runs from app to PgBouncer, and another from PgBouncer to PostgreSQL. Configure client-side and server-side TLS on the pooler **independently**. The app running `verify-full` against PgBouncer does not prove PgBouncer -> DB verifies the PostgreSQL server.

### 35.3. Cloud-Managed Databases

Providers use custom CA bundles, rotations, and endpoint aliases. Fetch official CAs from verified provider sources per documentation—never download CAs from random links or use trust-all for convenience.

### 35.4. DNS Discovery and Service Meshes

If clients dial a service hostname while TLS terminates at a sidecar/proxy, certificates must match the identity clients verify. Mesh mTLS protects mesh hops, yet does not automatically enforce PostgreSQL hostname verification if the app takes another route.

## 36. TLS for Read Replicas and Failover

When clients switch among:

~~~text
db-primary.example.internal
db-replica-a.example.internal
db-replica-b.example.internal
~~~

manage certificates and trust for every endpoint.

### 36.1. Per-Backend Identities

Each node can hold its own certificate with a SAN matching that node's hostname, supporting host-specific verification.

### 36.2. Shared Service Identity

If apps connect only to `db.service.internal` and a load balancer terminates TLS, the load balancer certificate must carry that service name. If using TLS passthrough to backends, every backend must carry a certificate compatible with the name apps verify.

### 36.3. target_session_attrs Does Not Replace TLS

`libpq` clients often use `target_session_attrs=read-write` to pick a primary server. That selects endpoints **after connecting**; it does not replace verifying each tried host's certificate.

### 36.4. Never Copy One Private Key Across All Nodes Arbitrarily

Sharing one certificate/keypair across every node expands blast radius. Prefer per-node certificates, proper service identities, and approved PKI termination patterns.

## 37. Do Internal Connections Need TLS?

"Running inside a private subnet" does not prove traffic is safe.

### 37.1. Private Networks Are Not Absolute Trust Boundaries

One compromised internal host, misconfigured network ACL, or route change exposes unencrypted internal traffic.

### 37.2. Protection Driven by Data Sensitivity and Compliance

Organizations frequently mandate encryption for all DB connections including internal traffic. Where required, make `verify-full` and server-side TLS-only rules your baseline.

### 37.3. Same-Host Unix Sockets

For Unix-domain sockets, security relies on local OS/socket permissions and PostgreSQL auth; TCP TLS does not apply. Never confuse local socket behavior with accepting plaintext TCP over a network.

### 37.4. Performance Is Rarely a Reason to Skip Hostname Verification

TLS adds handshake and encryption overhead, yet for normal workloads measure real impact before trading away security. Connection pooling and right-sizing beat disabling TLS.

## 38. Observability, Alerting, and Operational Baseline

A TLS governance baseline typically includes:

1. Inventory of approved PostgreSQL endpoints.
2. Centrally managed CA bundles and trust anchors.
3. Mandatory `sslmode=verify-full` across all TCP clients.
4. Server-side `hostssl` and plaintext rejection policies.
5. Approved TLS protocol versions and cipher policies.
6. Certificate expiration tracking and multi-stage alerts.
7. Documented rotation and revocation procedures.
8. Inventory of all TLS termination points and proxies.
9. Live channel monitoring from both app and server sides.
10. Negative CA/hostname tests in staging.

### 38.1. Querying Active TLS Versions

~~~sql
SELECT
    ssl,
    version,
    cipher,
    count(*) AS connections
FROM pg_stat_ssl
GROUP BY ssl, version, cipher
ORDER BY ssl DESC, connections DESC;
~~~

Results reflect observed live connections, not an inventory of every client that might connect later.

### 38.2. Monitoring Non-TLS Connections

~~~sql
SELECT
    count(*) FILTER (WHERE ssl) AS tls_connections,
    count(*) FILTER (WHERE NOT ssl) AS non_tls_connections
FROM pg_stat_ssl;
~~~

**Note:** Background processes and local socket connections show `ssl = false` because they are not network TCP clients; inspect PID, backend type, and client address before treating every non-TLS row as an incident.

### 38.3. Never Use pg_stat_ssl Alone to Certify verify-full

Auditing client-side verification requires inspecting connection strings, driver versions, trust stores, policy checks, and negative tests in pipelines—not just server-side counters.

## 39. Troubleshooting Checklist for verify-full Connections

When an app fails to connect after enabling TLS:

1. **Does TCP reach the right endpoint and port?**
2. **Is there a proxy, load balancer, or sidecar in between?**
3. **What hostname is in the URL or connection string?**
4. **Does the server/proxy certificate include a matching SAN?**
5. **Which CA signed the leaf and intermediate?**
6. **Which CA does the client trust, and from which file or JVM truststore?**
7. **Is an intermediate certificate missing from the chain?**
8. **Is the certificate valid now, and are system clocks accurate?**
9. **Does the server private key match the certificate and have valid permissions?**
10. **Does the server enable compatible TLS versions and ciphers?**
11. **Are `pg_hba.conf` rules ordered properly for IP, DB, user, and method?**
12. **Did SCRAM or client-certificate auth succeed?**
13. **Is the Java app using the intended datasource properties?**
14. **Could a failover node have a different certificate?**
15. **Are GSS encryption or Unix sockets skewing observations?**
16. **In staging, do intentional bad-CA and bad-hostname tests fail?**

### 39.1. Classifying Failures

| Stage | Symptom | Where to check |
| --- | --- | --- |
| DNS/TCP | Unresolved / timeout / refused | Network, DNS, listener |
| TLS handshake | Protocol/cipher/cert mismatch | TLS server/client logs |
| Server identity | CA/hostname verification failed | SAN, CA chain, trust store |
| PostgreSQL authentication | Password/role/cert mapping failed | `pg_hba.conf`, roles |
| SQL authorization | Permission denied for table/schema | `GRANT`, roles, RLS |
| Pool/replica | Only some requests fail | Pool nodes, endpoints, rotation |

### 39.2. Never Expose Private Keys While Debugging

When sharing logs, strip `*.key` files, passwords, secret-bearing connection strings, and restricted internal certificate bundles.

### 39.3. Never Fix Security by Disabling Security

Switching to `sslmode=disable`, `require`, or trust-all just to "make it connect" masks bugs that belong in PKI, SANs, CAs, or endpoints.

## 40. Common Misconceptions

### Mistake 1. Setting ssl=on means every client uses TLS

No. `ssl=on` only enables TLS capability; clients and `pg_hba.conf` may still allow plaintext paths.

### Mistake 2. sslmode=require equals verify-full

No. `require` mandates a TLS channel without enforcing `verify-full`'s hostname/CA checks.

### Mistake 3. sslmode=prefer enforces TLS

No. `prefer` falls back to plaintext and does not satisfy mandatory-encryption policies.

### Mistake 4. verify-ca stops host impersonation

No. A valid certificate from the same CA could belong to another server. Only `verify-full` checks the target name.

### Mistake 5. Certificate CN replaces SAN

Never rely on CN fallback. Issue certificates with proper SANs for all DNS/IP names used.

### Mistake 6. IP literals work as DNS SANs

IP identities should use proper IP SANs. A DNS SAN containing an IP-like string is not reliably treated as an IP identity by clients.

### Mistake 7. Setting ssl_ca_file on the server makes clients trust that CA

No. Server `ssl_ca_file` verifies client certificates; clients need their own trust store to verify the server.

### Mistake 8. sslcert and sslkey verify the server

No. They are **client** identity/key files used for mTLS.

### Mistake 9. A strong password protects server identity

No. PostgreSQL user auth and TLS server verification are separate layers.

### Mistake 10. hostssl forces clients to run verify-full

No. `hostssl` requires TLS on the connection; the server cannot verify whether the client checked the server hostname.

### Mistake 11. psql working over TLS proves the Java app uses TLS

No. The app may use a different driver, trust store, URL, or pool config.

### Mistake 12. pg_stat_ssl.ssl=true proves hostname verification

No. The server cannot observe which `sslmode` the client used.

### Mistake 13. Unix socket connections use TLS

No. `sslmode` does not apply like TCP; inspect socket type and local OS security separately.

### Mistake 14. Public CAs work for every internal name

No. Public CAs enforce domain-validation and naming rules; use appropriate PKI for internal service names.

### Mistake 15. A valid leaf cert without intermediates always works

No. Clients can fail when unable to build a chain to a trusted CA.

### Mistake 16. New certificates don't need SAN checks

No. Rotating a server certificate can introduce hostname mismatches even with a valid issuer.

### Mistake 17. On cert expiry, switch sslmode down to prefer

No. Rotate the certificate, fix clocks/PKI, and keep strict verification enabled.

### Mistake 18. Private keys are safe in a private Git repo

No. Private keys are secrets; repos, CI logs, and container images widen blast radius enormously.

### Mistake 19. chmod 777 fixes key permission errors

No. Server private keys must restrict access; overly loose modes increase risk and cause PostgreSQL to reject the key.

### Mistake 20. TLS to a proxy protects every hop

No. Inspect the hop between proxy and PostgreSQL as well as which hostname each hop verifies.

### Mistake 21. mTLS replaces PostgreSQL GRANT/RLS

No. Client certificates authenticate workloads/services, without granting table read/write rights.

### Mistake 22. Any client cert works for any role

Not by default. `clientcert`, `cert`, subject mapping, and `pg_ident.conf` govern how certificate identities map to database roles.

### Mistake 23. SNI/failover always picks a matching certificate

No. Multi-node setups or proxies may serve different certificates; test every endpoint.

### Mistake 24. Root CA private keys belong alongside server.key

No. Root CA keys belong in secure issuance infrastructure, never deployed across database servers.

### Mistake 25. Short-lived certs make revocation unnecessary

No. Key protection, revocation/incident workflows, and trust governance remain essential.

### Mistake 26. Every client uses the OS CA store

No. `libpq`, PGJDBC, and JSSE select trust stores differently depending on version and configuration.

### Mistake 27. Using a trust-all SSL factory in production

Eliminates server verification and opens the door to MITM despite a successful TLS handshake.

### Mistake 28. Checking certs only at deploy without expiry monitoring

Expired certificates later break new connections; monitor expiry and automate/schedule rotation.

### Mistake 29. Changing PG SSL settings re-handshakes all open sessions

No. Connection pools retain previously handshaken TLS sessions; plan reconnects during rotation or policy changes.

### Mistake 30. TLS prevents SQL injection

No. Parameterize SQL queries and enforce least-privilege grants.

## 41. Hands-On Exercises

These exercises apply to a lab PostgreSQL server with TLS enabled. Server/CA configuration tasks require admin rights—**never modify production** just to practice. Output details vary by PostgreSQL, OpenSSL, and PGJDBC versions.

### Exercise 1. Three Security Layers

Distinguish TLS encryption, server certificate verification, and PostgreSQL user authentication.

### Exercise 2. Two Endpoints

Why can a client and database communicating over TLS still suffer a MITM attack if CA and certificate names are not verified?

### Exercise 3. Server Authentication

Which `sslmode` should you choose when TLS is mandatory and you want to verify the exact database server name?

### Exercise 4. prefer

Does `sslmode=prefer` guarantee plaintext TCP is never used? Why or why not?

### Exercise 5. require

Does `sslmode=require` imply SAN hostname verification?

### Exercise 6. verify-ca

Suppose a CA issued certificates for `db-a` and `db-b`. Why might `verify-ca` fail to catch accidentally connecting to `db-b`?

### Exercise 7. SAN

An app connects to `db.shop.internal`. What SAN should the certificate contain?

### Exercise 8. IP Addresses

An app connects to `192.0.2.10`. Why is `DNS:192.0.2.10` not the standard SAN format for an IP identity?

### Exercise 9. Root CA

Describe the public CA file and the CA private key. Which file does the client need to verify the server?

### Exercise 10. Intermediates

A server certificate is signed by an intermediate CA, yet the server does not send the intermediate. What can happen?

### Exercise 11. Server Config

Write `postgresql.conf` settings enabling TLS, specifying server cert/key, and setting minimum TLSv1.2.

### Exercise 12. ssl_ca_file

What is `ssl_ca_file` on a PostgreSQL server normally used for?

### Exercise 13. hostssl

Write a `pg_hba.conf` rule allowing only user `app_user` from `10.20.0.0/16` to `appdb` over TLS and SCRAM.

### Exercise 14. Plaintext Policy

Write rules rejecting all plaintext IPv4 and IPv6 TCP connections.

### Exercise 15. Inspecting the Active Channel

Write SQL to inspect `ssl`, `version`, and `cipher` for the current backend.

### Exercise 16. SHOW ssl

Why is `SHOW ssl` insufficient to prove an app connection currently uses TLS?

### Exercise 17. Client Verification from the Server

A DBA sees `pg_stat_ssl.ssl = true`. Can they conclude the client used `verify-full`?

### Exercise 18. psql

Write a `psql` connection command to `db.shop.internal` on port `5432`, database `shopdb`, user `shop_app`, `sslmode` `verify-full`, and CA file `/etc/shop/db-ca.crt`.

### Exercise 19. Certificate Expired

State the causes and proper fix when a client reports an expired certificate.

### Exercise 20. Hostname Mismatch

A certificate contains only `DNS:db-a.internal`, while the app dials `db-service.internal`. How do you fix this while preserving `verify-full`?

### Exercise 21. Negative Tests

Propose two negative tests to prove a client genuinely verifies server identity.

### Exercise 22. JDBC URL

Write a JDBC URL connecting to `db.shop.internal:5432/shopdb` with `sslmode` `verify-full` and `sslrootcert`.

### Exercise 23. Java Properties

Set `sslmode` and `sslrootcert` in `Properties` for PGJDBC.

### Exercise 24. Password Handling

Why should database passwords never appear directly in URLs, CLI commands, or logs?

### Exercise 25. mTLS

What extra verification step does mTLS add compared to standard one-way TLS?

### Exercise 26. Client Cert Files

Distinguish `sslrootcert`, `sslcert`, and `sslkey` on the client.

### Exercise 27. SCRAM and clientcert

Write a `hostssl` example requiring both `scram-sha-256` and `clientcert=verify-full`.

### Exercise 28. Identity Mapping

Why does a client certificate with CN `"service-a"` not automatically allow logging in as PostgreSQL role `"app_user"`?

### Exercise 29. Channel Binding

Does channel binding replace CA/hostname verification?

### Exercise 30. PgBouncer

If a client runs `verify-full` on PgBouncer's certificate, does that prove PgBouncer -> PostgreSQL is encrypted and server-verified?

### Exercise 31. Failover

Two failover nodes have separate certificates. When apps connect to a stable service alias, what must you check?

### Exercise 32. CA Rotation

You are migrating from CA A to CA B. Why shouldn't you remove CA A from all clients the moment the first node switches to B?

### Exercise 33. Server Key

Why must `server.key` never be committed to Git or made world-readable?

### Exercise 34. OpenSSL Inspect

Write the command to view subject, issuer, validity dates, and SANs of `server.crt`.

### Exercise 35. pg_stat_ssl Histogram

Write SQL counting connections by TLS version and cipher.

### Exercise 36. Connection Pools

Why does rotating the server certificate not immediately cause all pooled connections to re-handshake?

### Exercise 37. TLS Policy Compliance

List at least five checks required before declaring app -> PostgreSQL secure with TLS.

### Exercise 38. SQL Injection

A system already uses `verify-full`. Does it still need prepared statements and `GRANT`/RLS?

### Exercise 39. Unix Sockets

Why might running `psql` without a host on Unix not be a TLS test?

### Exercise 40. GSS Encryption

If a connection uses GSS encryption instead of TLS, what should you watch out for when auditing organizational X.509/TLS compliance?

## 42. Solution Hints

### Exercises 1–3. Layers and verify-full

TLS encrypts transport, certificate verification confirms server identity by trust chain and name, and PostgreSQL authentication verifies the user/role. TLS without CA/hostname checks is vulnerable to MITM. `sslmode=verify-full` enforces TLS and full server verification.

### Exercises 4–6. sslmode Modes

`prefer` can fall back to plaintext. `require` does not verify hostnames by default, though `libpq` has compatibility behavior with default CA files. `verify-ca` checks the CA without checking `db-a` vs. `db-b`; `verify-full` verifies the name too.

### Exercises 7–8. SAN

For hostname `db.shop.internal`, use `DNS:db.shop.internal`. For IP `192.0.2.10`, use an `IP:192.0.2.10` SAN per certificate/driver standards.

### Exercises 9–10. CA Chain

Clients receive the **public CA certificate/trust anchor**, never the CA private key. Without an intermediate certificate, clients may fail chain validation even when trusting the root CA.

### Exercise 11. Server Config

~~~conf
ssl = on
ssl_cert_file = '/etc/postgresql/tls/server.crt'
ssl_key_file  = '/etc/postgresql/tls/server.key'
ssl_min_protocol_version = 'TLSv1.2'
~~~

Paths are illustrative; real files and permissions must match.

### Exercise 12. ssl_ca_file

It supplies server-side CA trust primarily to verify **client** certificates for certificate authentication. It does not distribute trust anchors to applications.

### Exercises 13–14. pg_hba.conf

~~~conf
hostssl appdb app_user 10.20.0.0/16 scram-sha-256
hostnossl all all 0.0.0.0/0 reject
hostnossl all all ::/0 reject
~~~

Verify actual rule ordering so no earlier `host` rule bypasses the policy.

### Exercise 15. pg_stat_ssl

~~~sql
SELECT ssl, version, cipher
FROM pg_stat_ssl
WHERE pid = pg_backend_pid();
~~~

### Exercises 16–17. Observability Limits

`SHOW ssl` reports server capability, not the current connection. `pg_stat_ssl.ssl = true` shows TLS is active on the connection, yet the server cannot tell whether the client ran `verify-full`.

### Exercise 18. psql

~~~bash
psql "host=db.shop.internal port=5432 dbname=shopdb user=shop_app sslmode=verify-full sslrootcert=/etc/shop/db-ca.crt"
~~~

### Exercises 19–20. Fixing Certificates

Certificate expired: check system clocks, issue and deploy a valid certificate before expiration. Hostname mismatch: issue a server certificate with SAN `db-service.internal` at that TLS endpoint, or update the connection name to match an approved identity; **never downgrade `sslmode`**.

### Exercise 21. Negative Tests

In staging, test with an untrusted CA and a hostname absent from SANs. Both must fail when the app/driver actually uses `verify-full`.

### Exercises 22–23. PGJDBC

~~~text
jdbc:postgresql://db.shop.internal:5432/shopdb?sslmode=verify-full&sslrootcert=/etc/shop/db-ca.crt
~~~

~~~java
Properties props = new Properties();
props.setProperty("sslmode", "verify-full");
props.setProperty("sslrootcert", "/etc/shop/db-ca.crt");
~~~

### Exercise 24. Passwords

URLs, CLI args, and logs leak secrets via shell history, shared configs, or monitoring. Use secret management, prompts, or secure auth mechanisms and never log passwords.

### Exercises 25–27. mTLS

mTLS requires the PostgreSQL server to verify the **client certificate** in addition to the client verifying the server.

`sslrootcert` verifies the server; `sslcert` and `sslkey` are the client's certificate and private key.

~~~conf
hostssl appdb app_user 10.20.0.0/16 scram-sha-256 clientcert=verify-full
~~~

The server needs the matching CA in `ssl_ca_file` and valid identity/mapping rules.

### Exercise 28. Certificate Identity

PostgreSQL maps certificate identities to database roles via auth configuration and `pg_ident.conf`. Holding an arbitrary CN never automatically grants login to `app_user`.

### Exercise 29. Channel Binding

No. It binds authentication to the TLS channel where supported, while CA/hostname verification remains required.

### Exercise 30. PgBouncer

No. Two hops can have two independent TLS sessions and policies. Verify PgBouncer -> PostgreSQL TLS/CA/hostname configuration directly rather than inferring it from app -> PgBouncer.

### Exercises 31–32. Failover/CA Rotation

Every TLS endpoint reachable on failover needs a certificate matching the service hostname or verified client identity. During phased CA rotation, maintain an overlap window trusting both old and new CAs; removing A too early breaks verification against unmigrated nodes.

### Exercise 33. Server Private Key

If leaked, attackers can impersonate the endpoint under PKI rules. Restrict read permissions to the service account and protect keys in secure storage.

### Exercise 34. OpenSSL

~~~bash
openssl x509 -in server.crt -noout \
  -subject -issuer -dates -ext subjectAltName
~~~

### Exercise 35. TLS Inventory

~~~sql
SELECT
    version,
    cipher,
    count(*) AS connections
FROM pg_stat_ssl
WHERE ssl
GROUP BY version, cipher
ORDER BY connections DESC;
~~~

### Exercise 36. Pooling

Open connections keep TLS state from their initial handshake; rotation affects new handshakes. Enforce max connection lifetimes/reconnects and monitor rollout.

### Exercise 37. Baseline

Examples: `verify-full` in apps, right trust anchors, matching SANs, server `hostssl`/TLS-only rules, strong TLS versions/ciphers, failing negative CA/hostname tests, `pg_stat_ssl` checks, CA/key rotation, expiry alerts, and SQL least privilege.

### Exercise 38. Query Security

Yes. TLS never replaces prepared statements for SQL injection defense or `GRANT`/RLS/tenant authorization.

### Exercise 39. Unix Sockets

`libpq` defaults to Unix-domain sockets when no TCP host is given on Unix; TLS targets TCP and does not apply to local sockets. Specify TCP host explicitly and check `pg_stat_ssl` when testing.

### Exercise 40. GSS Encryption

GSS encryption is separate from TLS/X.509; to verify `verify-full` compliance, inspect active connection mechanisms and adjust `gssencmode`/driver settings per supported version instead of relying solely on `sslmode`.

## 43. Quick Reference Table

| Need | Option / tool |
| --- | --- |
| Mandatory TLS + full server verification | `sslmode=verify-full` |
| Verify CA only, not hostname | `sslmode=verify-ca` |
| Require TLS, not equivalent to `verify-full` | `sslmode=require` |
| May fall back to plaintext | `sslmode=prefer` |
| Specify trusted CA on client | `sslrootcert=/path/to/ca.crt` |
| Client certificate for mTLS | `sslcert` |
| Client private key for mTLS | `sslkey` |
| Enable TLS in PostgreSQL | `ssl=on` |
| Specify server certificate | `ssl_cert_file` |
| Specify server private key | `ssl_key_file` |
| Trust client certificates on server | `ssl_ca_file` |
| Set minimum TLS version | `ssl_min_protocol_version` |
| TLS-only TCP rule | `hostssl` in `pg_hba.conf` |
| Plaintext TCP rule | `hostnossl` |
| Require SCRAM | `scram-sha-256` |
| Require client cert with SCRAM | `clientcert=verify-full` |
| Certificate-only authentication | `cert` auth method |
| Identity mapping | `pg_ident.conf` |
| Check if server enables SSL | `SHOW ssl` |
| Check if current session uses TLS | `pg_stat_ssl` + `pg_backend_pid()` |
| Check TLS in `psql` | `\conninfo` |
| Inspect SAN/expiry | `openssl x509` |
| Test chain/hostname in lab | `openssl verify -verify_hostname` |
| Check restart-pending config | `pg_settings.pending_restart` |
| Java PostgreSQL TLS | PGJDBC `sslmode`/`sslrootcert` |
| TLS channel binding with SCRAM | `channel_binding` where supported |
| Restrict data access per user | `GRANT`, RLS, application ACLs |

## 44. Production PostgreSQL TLS Deployment Checklist

1. **Inventory every TCP endpoint** used by apps, admins, batch jobs, ETL, poolers, replicas, and proxies.
2. Confirm whether TLS terminates at PostgreSQL or an intermediate proxy.
3. Map which network hops carry data requiring encryption.
4. Confirm approved CAs and DNS/IP names for every endpoint.
5. Ensure each server certificate carries SANs matching real client connection names.
6. Ensure clients configure `sslmode=verify-full` and valid CA/trust stores.
7. Verify negative tests with wrong CA and wrong hostname **fail**.
8. Ensure the server sets `ssl=on` and an appropriate minimum protocol version.
9. Ensure `pg_hba.conf` accepts only TLS on required networks.
10. Ensure no earlier `host` rule accidentally permits plaintext.
11. Verify both IPv4 and IPv6 rules.
12. Ensure PostgreSQL auth uses approved methods such as SCRAM/mTLS.
13. Issue per-service client certificates if mTLS is used.
14. Confirm `ssl_ca_file` and `sslrootcert` are configured cleanly for their respective directions.
15. Protect server and client private keys against unauthorized reads.
16. Eliminate any trust-all SSL factories or hostname-verification bypasses.
17. Enforce least-privilege SQL permissions on app accounts.
18. Ensure JDBC datasources/pools apply the proper security properties.
19. Verify app sessions in `pg_stat_ssl`, not just DBA sessions.
20. Keep certificates and trust policies consistent across replicas, failovers, and proxies.
21. Maintain rotation schedules and multi-threshold expiry alerts.
22. Plan CA overlap windows when changing trust anchors.
23. Maintain key-compromise and revocation procedures.
24. Handle open TLS sessions during rotation via pool reconnect policies.
25. Audit TLS 1.2/1.3, ciphers, and client compatibility.
26. Synchronize system clocks across clients and servers.
27. Distinguish network, TLS, authentication, and authorization failures.
28. Keep passwords and private keys out of logs, CLI args, and source control.
29. Maintain audit evidence of client-side `verify-full` configuration.
30. Keep a runbook to resolve hostname/CA mismatches without lowering security.

## 45. Summary

To protect PostgreSQL connections over a network, treat TLS as **both transport encryption and endpoint identity verification**, never merely flipping `ssl=on`.

Key principles:

1. **Encryption != server identity verification != user authentication.** TLS protects the wire, certificate verification confirms the server, and PostgreSQL authentication/SQL authorization govern who logs in and what they can touch.
2. **`sslmode=verify-full` is the preferred default for production TCP clients.** It mandates TLS, verifies the chain to a trusted CA, and checks the DNS/IP name. `prefer` can fall back to plaintext; `require` does not replace hostname checks; `verify-ca` does not verify the exact host name.
3. **Server certificates must carry matching SANs** for application connection names. CA private keys, server private keys, and client private keys are all secrets; distribute only public CA certificates/trust anchors to clients.
4. **Servers also need TLS enforcement.** `ssl=on`, valid certs/keys, and `hostssl`/`hostnossl` in `pg_hba.conf` block unauthorized plaintext connections, though the server cannot prove whether clients ran `verify-full`.
5. **mTLS adds client verification**, without replacing `GRANT`/RLS or relieving clients of verifying the server.
6. **TLS operations are continuous:** manage CAs/chains, DNS/SANs, rotation, expiry, revocation, proxy hops, failover, driver/JDK behavior, and negative tests. Never weaken security to bypass a certificate error.

A concise verification flow: **confirm endpoint/name -> issue cert with right SAN -> distribute trusted CA -> configure `verify-full` -> enforce TLS server-side -> verify channel via `pg_stat_ssl` -> assert bad CA/hostname fails -> monitor certificate lifecycle**.

Only when every step is governed consistently from application to PostgreSQL does TLS deliver both **confidentiality in transit** and **confidence that the application is talking to the real database server**.
