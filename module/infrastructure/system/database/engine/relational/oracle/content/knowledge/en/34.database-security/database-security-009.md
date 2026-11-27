# Oracle Net encryption, TLS/TCPS, wallets, and certificate management

Oracle Net connections traverse networks between clients, listeners, and database services. If network traffic is unprotected, anyone able to observe the path can read sensitive information; if the client does not properly verify the server, it also risks connecting to a spoofed endpoint. A secure configuration must clearly address two goals: **data confidentiality/integrity in transit** and **identity verification of the peer**.

Oracle supports two common protection approaches:

- **Native Network Encryption (NNE)**: encryption and integrity checking at the Oracle Net layer over TCP connections. Configured using `SQLNET.ENCRYPTION_*` and `SQLNET.CRYPTO_CHECKSUM_*` parameters; does not require TLS certificates.
- **TLS over TCPS**: Oracle Net running over TLS. TLS protects the transport channel, authenticates the server via certificates, and can require client certificates for mutual TLS (mTLS). Listener and client are configured using the TCPS protocol and an appropriate wallet or trust store.

An Oracle Wallet can hold private keys, user certificates, and trusted certificates. Wallets must be created, protected, distributed, renewed, and revoked according to PKI procedures. A wrong wallet path, missing intermediate CA, expired certificate, or hostname mismatch can cause connection failures.

This lesson uses Oracle Database 19c as the reference baseline and covers:
- Distinguishing NNE, TLS, and TCPS.
- Configuring encryption/integrity for TCP.
- Configuring a TCPS listener, client connect descriptor, and wallet.
- Generating private keys/CSRs, importing CA chains and user certificates with orapki.
- Server-auth TLS and mutual TLS.
- Verifying hostname/SAN/DN, expiry, trust chains, and TLS policies.
- Connecting via SQL*Plus, JDBC Thin, and OCI.
- Renewing, rotating, backing up, and revoking certificates.
- Verifying connections, diagnosing errors, and operating securely.

Exact parameter syntax, TLS versions/ciphers, and driver behavior depend on the Oracle release, Release Update, JDK, and platform. Always consult the Oracle Net Services Administrator's Guide, JDBC Developer's Guide, and PKI documentation for your exact version before applying in production.

## 1. Security goals of an Oracle Net connection

A secure database connection typically requires the following properties:

1. **Confidentiality**: transmitted data cannot be read if eavesdropped on the network.
2. **Integrity**: data cannot be tampered with without client/server detection.
3. **Server authentication**: the client verifies it is connecting to the legitimate database endpoint.
4. **Client authentication**: the server verifies the client's identity if the model requires it.
5. **Lifecycle management**: certificates and keys are renewed, replaced, and revoked on schedule.
6. **Operational control**: logs, wallet passwords, private keys, file permissions, and configuration changes are governed.

Encryption alone does not solve every problem. For example, TCPS protects data in transit, but does not prevent an overly privileged database account from reading data after connecting. Nor does TLS replace database authentication/authorization, auditing, network segmentation, or endpoint protection.

### 1.1. Protecting data in transit and at rest

| Scope | Commonly used technology/controls |
| --- | --- |
| Client ↔ listener/database | TCPS/TLS or Native Network Encryption |
| Data in datafiles/backups | Transparent Data Encryption (TDE), backup encryption |
| Database user authentication | Passwords, Kerberos, certificate/external authentication, enterprise identity |
| Access privileges | Roles, privileges, schemas, Database Vault if applicable |
| Application secrets | Secret manager, Oracle Wallet/external password store, OS permissions |

Do not confuse an Oracle Net wallet with a TDE keystore. Both may use wallet/keystore terminology, yet they serve different purposes and configurations. A wallet used for TLS/Oracle Net holds certificates and private keys to secure connections; a TDE keystore holds master encryption keys for data at rest.

## 2. How do NNE, TLS, and TCPS differ?

### 2.1. Native Network Encryption

NNE is Oracle Net's native mechanism to encrypt data and optionally check integrity over TCP. Both sides negotiate algorithms based on client/server policies.

Characteristics:
- Configured via `sqlnet.ora`.
- Can use AES for encryption and SHA for crypto-checksum.
- Does not require CA certificates or TLS wallets.
- Protects Oracle Net payload in transit.
- Does not provide TLS-style certificate-based server identity validation.

NNE is suitable when Oracle Net encryption over TCP is needed in environments that already have other endpoint verification mechanisms and want to use Oracle's native encryption.

### 2.2. TLS

TLS is a transport-layer security protocol. It provides encryption, integrity, and certificate-based authentication. During a TLS handshake, client and server negotiate protocol version/cipher suite, verify certificates, and establish session keys.

Server certificates are typically signed by a CA. Clients must trust the CA chain and verify the server identity. When mTLS is enabled, the server also requests and verifies the client's certificate.

### 2.3. TCPS

TCPS is the Oracle Net protocol that uses TLS. When a connect descriptor specifies `PROTOCOL=TCPS`, Oracle Net establishes a TLS connection before exchanging Oracle Net protocol messages.

For example:
- TCP listeners commonly use port 1521.
- TCPS is commonly configured on port 2484.

Port 2484 is a common convention, not a mandatory requirement. Another port can be used if the listener, firewall, load balancer, and clients are configured consistently.

### 2.4. Comparison

| Criterion | NNE over TCP | TLS over TCPS |
| --- | --- | --- |
| Network protocol | TCP | TCPS |
| Data encryption | Yes | Yes |
| Integrity | Crypto-checksum | TLS record integrity |
| Certificate/CA | Not required | Required |
| Server identity verification via certificate | No | Yes |
| Mutual TLS | Not via TLS mechanism | Can be enabled |
| Primary configuration | SQLNET.ENCRYPTION/CRYPTO_CHECKSUM | TCPS listener, wallet, TLS parameters |
| Client compatibility | Oracle Net clients supporting NNE | Clients/drivers supporting TCPS and trust stores |

Do not infer that enabling NNE means TLS server identity validation is active. Nor should TCPS be treated as merely another name for NNE. Choose a model based on security requirements, compatibility, and your organization's PKI policy.

## 3. Native Network Encryption over TCP

If only Oracle Net layer encryption and integrity are needed, NNE can be configured without switching the TCP listener to TCPS.

### 3.1. Server-side configuration

In the Oracle server's `sqlnet.ora`:

~~~text
SQLNET.ENCRYPTION_SERVER = REQUIRED
SQLNET.ENCRYPTION_TYPES_SERVER = (AES256, AES192, AES128)

SQLNET.CRYPTO_CHECKSUM_SERVER = REQUIRED
SQLNET.CRYPTO_CHECKSUM_TYPES_SERVER = (SHA512, SHA384, SHA256)
~~~

Meaning:
- REQUIRED requires the connecting peer to negotiate the corresponding service.
- ENCRYPTION_TYPES_SERVER lists accepted encryption algorithms.
- CRYPTO_CHECKSUM_SERVER requires integrity checking.
- CRYPTO_CHECKSUM_TYPES_SERVER lists accepted checksum algorithms.

Algorithm names and support levels must match the release/RU on both client and server. The example above illustrates a modern policy; verify the supported algorithm list in your actual environment.

### 3.2. Client-side configuration

In the client's `sqlnet.ora`:

~~~text
SQLNET.ENCRYPTION_CLIENT = REQUESTED
SQLNET.ENCRYPTION_TYPES_CLIENT = (AES256, AES192, AES128)

SQLNET.CRYPTO_CHECKSUM_CLIENT = REQUESTED
SQLNET.CRYPTO_CHECKSUM_TYPES_CLIENT = (SHA512, SHA384, SHA256)
~~~

REQUESTED indicates the client requests the service while still permitting negotiation according to policy. When the server sets REQUIRED, the client must support and negotiate a compatible algorithm; otherwise, the connection is rejected.

REQUIRED can be set on both sides if policy mandates it and all clients have been inventoried/tested. Do not switch the server to REQUIRED before confirming that all applications, batch jobs, monitoring agents, and administrative tools support it.

### 3.3. ACCEPTED, REQUESTED, and REQUIRED

The policy values have distinct meanings:
- ACCEPTED: accepts the service if requested by the peer and negotiable.
- REQUESTED: requests the service, though negotiation still depends on the peer's policy.
- REQUIRED: the connection must use the service, otherwise it fails.

Exact negotiation outcomes when client and server use different settings should be checked against the compatibility matrix in the Oracle Net Services Reference. Do not conclude encryption is active simply because "the connection still succeeds."

### 3.4. Verifying NNE

After connecting, inspect the session's network service banners:

~~~sql
SELECT
    sid,
    serial#,
    network_service_banner
FROM v$session_connect_info
WHERE sid = SYS_CONTEXT('USERENV', 'SID');
~~~

Output typically includes lines describing the Encryption service and Crypto-checksumming service along with the negotiated algorithm. Exact banner content depends on version and configuration.

If expected encryption/integrity services are not shown:
- Confirm the client is reading the intended `sqlnet.ora`.
- Confirm the server is reading the intended `sqlnet.ora`.
- Check the process's Oracle Home/TNS_ADMIN.
- Check whether client and server policies and algorithm lists intersect.
- Verify the connection actually goes through the configured Oracle Net client.
- Check listener/server logs if negotiation fails.

NNE does not use a TLS wallet. Do not create a wallet solely to enable `SQLNET.ENCRYPTION_*`.

## 4. TLS handshake and digital certificates

TLS relies on public key infrastructure (PKI). A certificate binds an identity to a public key and is signed by a CA so recipients can verify trust.

### 4.1. Certificate components

An X.509 certificate typically contains:
- Subject: identity of the subject.
- Issuer: CA that issued the certificate.
- Subject Public Key Info: the public key.
- Serial Number: serial number assigned by the CA.
- Validity: Not Before and Not After.
- Subject Alternative Name (SAN): DNS names/IPs represented by the certificate.
- Key Usage and Extended Key Usage.
- Signature Algorithm and CA signature.

The corresponding private key is not included in the public certificate. The private key must be protected inside a wallet or keystore.

### 4.2. Root CA, intermediate CA, and leaf certificate

A trust chain typically looks like:

~~~text
Client trust store
       |
       v
Root CA (trust anchor)
       |
       v
Intermediate CA
       |
       v
Server leaf certificate
       |
       v
TLS endpoint: db.example.com
~~~

The Root CA is the trust anchor trusted by the client. The Intermediate CA is signed by the root or a higher CA. The leaf certificate is issued to the server or client endpoint.

If the server sends only the leaf certificate without the intermediate, some clients cannot build the chain and will fail validation. Install the full chain following CA and Oracle Wallet guidelines.

### 4.3. Server certificate and SAN

The server certificate must represent the hostname the client uses to connect. If an application connects to `db-prod.example.com`, the certificate needs a matching DNS SAN. Do not rely solely on the Common Name (CN); SAN is the modern standard for identifying DNS/IP identities.

If clients connect by IP, the certificate must include the corresponding IP SAN or the application must use a DNS name listed in the SAN. DNS aliases, load balancers, and failover endpoints must be accounted for in the SAN/identity list according to the actual architecture.

### 4.4. DN matching

Oracle Net provides the `SSL_SERVER_DN_MATCH` parameter to require the client to verify the server identity in the certificate. You can specify `SSL_SERVER_CERT_DN` in the connect descriptor to pin the expected DN.

Connect descriptor example:

~~~text
ORCL_TCPS =
  (DESCRIPTION =
    (ADDRESS =
      (PROTOCOL = TCPS)
      (HOST = db-prod.example.com)
      (PORT = 2484)
    )
    (CONNECT_DATA =
      (SERVICE_NAME = orclpdb.example.com)
    )
    (SECURITY =
      (SSL_SERVER_DN_MATCH = YES)
    )
  )
~~~

When using explicit DN pinning, add `SSL_SERVER_CERT_DN` matching the exact DN of the server certificate and the syntax supported by the client in use. Do not copy sample DNs into production; extract the real DN from the certificate and verify how the driver/release performs matching.

Enabling server DN matching is a critical step to prevent connecting to the wrong endpoint. Encrypting with TLS without verifying server identity can still leave man-in-the-middle exposure if trust/identity validation is skipped.

## 5. What is an Oracle Wallet?

An Oracle Wallet is a secure container used to store certificates, private keys, and trusted certificates. Wallets can also be used for other purposes such as a secure external password store; exact functionality depends on contents and application configuration.

### 5.1. Common files

A PKCS#12 wallet may contain:
- `ewallet.p12`: password-protected wallet.
- `cwallet.sso`: auto-login wallet, allowing processes to access the wallet via auto-login without entering the password each time.

File names and creation methods depend on the wallet type/tool. Do not modify or rename wallet files arbitrarily.

### 5.2. What does a wallet contain?

A TLS wallet can hold:
- User certificate of the server or client.
- Private key corresponding to the user certificate.
- Trusted root CA certificates.
- Trusted intermediate CA certificates.
- Certificate revocation information if configured/supported.

The server wallet needs the TLS server identity certificate/private key. The client trust wallet needs the CA chain to verify the server. In mTLS, the server also needs to trust the client CA, and the client needs its identity certificate/private key along with the server's trust chain.

### 5.3. Wallet password and auto-login

The wallet password protects the password-protected wallet file. An auto-login wallet enables listener/client processes to open the wallet without interactive password entry. In return, file permissions on the auto-login file become a critical part of the security boundary.

- Restrict read permissions on the wallet directory and files to required OS accounts.
- Never commit wallets to Git or bake them into public images/containers.
- Never send private keys over email/chat.
- Encrypt backups and restrict who can restore them.
- Verify file permissions after copying/restoring.
- If using local auto-login, note that the wallet is tied to the host/environment where it was created per Oracle mechanisms; test usability when migrating hosts.

## 6. Creating wallets and preparing CA chains with orapki

`orapki` is Oracle's PKI utility for managing wallets, certificate requests, trusted certificates, and CRLs. The executable path depends on the Oracle Home, usually under `ORACLE_HOME/bin`.

The commands below are examples for Linux environments. Use separate wallet directories for each purpose and replace passwords/paths with securely managed secrets. Never put real passwords in documentation, source code, or shell history.

### 6.1. Creating the wallet directory

Example:

~~~bash
mkdir -p /u01/app/oracle/admin/ORCL/wallet/tcps_server
chmod 700 /u01/app/oracle/admin/ORCL/wallet/tcps_server
~~~

The directory must belong to the OS account required by the listener/database processes. On Windows, apply corresponding ACLs instead of `chmod`.

### 6.2. Creating the wallet

~~~bash
orapki wallet create \
  -wallet /u01/app/oracle/admin/ORCL/wallet/tcps_server \
  -pwd '<WALLET_PASSWORD>' \
  -auto_login
~~~

The command creates a password-protected wallet and an auto-login file. Inspect the output and generated files. Some environments use `-auto_login_local` to bind the auto-login wallet to the host; use it only when required by deployment standards and after testing recovery/migration.

Do not use placeholder passwords in production. Supply passwords via a secure mechanism compliant with environment and shell/automation policies.

### 6.3. Importing root CA and intermediate CA

Assume the CA provides:
- `root-ca.pem`
- `issuing-ca.pem`

Add the trusted certificates:

~~~bash
orapki wallet add \
  -wallet /u01/app/oracle/admin/ORCL/wallet/tcps_server \
  -trusted_cert \
  -cert root-ca.pem \
  -pwd '<WALLET_PASSWORD>'

orapki wallet add \
  -wallet /u01/app/oracle/admin/ORCL/wallet/tcps_server \
  -trusted_cert \
  -cert issuing-ca.pem \
  -pwd '<WALLET_PASSWORD>'
~~~

Root and intermediate certificates must come from a trusted PKI source. Verify fingerprints out-of-band before trusting; do not import a certificate merely because it arrived in an unverified email/request.

### 6.4. Generating a private key and certificate request

Create a key pair in the wallet and generate a certificate request:

~~~bash
orapki wallet add \
  -wallet /u01/app/oracle/admin/ORCL/wallet/tcps_server \
  -dn "CN=db-prod.example.com,OU=Database,O=Example Corp,C=VN" \
  -keysize 2048 \
  -pwd '<WALLET_PASSWORD>'

orapki wallet export \
  -wallet /u01/app/oracle/admin/ORCL/wallet/tcps_server \
  -dn "CN=db-prod.example.com,OU=Database,O=Example Corp,C=VN" \
  -request /secure/requests/db-prod.csr \
  -pwd '<WALLET_PASSWORD>'
~~~

The private key is created inside the wallet; the CSR contains the public key and subject info, not the private key. Submit the CSR to the CA per issuance procedures. The CA must include appropriate DNS SANs, Key Usage, and Extended Key Usage for a TLS server.

Do not generate a private key with another tool and import it separately unless you understand wallet key/certificate pairing procedures. Generating the key in the wallet and exporting the CSR helps Oracle keep the private key in the proper place.

### 6.5. Importing the CA-signed certificate

After the CA returns the leaf certificate and chain:

~~~bash
orapki wallet add \
  -wallet /u01/app/oracle/admin/ORCL/wallet/tcps_server \
  -user_cert \
  -cert db-prod-server.crt \
  -pwd '<WALLET_PASSWORD>'
~~~

The leaf certificate must match the public key of the CSR generated in the wallet. Importing a mismatched certificate/key pair can be rejected by the wallet or cause TLS handshake failures.

### 6.6. Viewing wallet contents

~~~bash
orapki wallet display \
  -wallet /u01/app/oracle/admin/ORCL/wallet/tcps_server \
  -complete \
  -pwd '<WALLET_PASSWORD>'
~~~

Verify:
- User certificate has the right Subject/SAN.
- Issuer matches the CA.
- Validity is active.
- Trusted certificates include required root/intermediate CAs.
- Wallet holds the matching identity private key.
- No expired certificates or unauthorized CAs remain trusted.

You can also inspect a certificate file with OpenSSL:

~~~bash
openssl x509 -in db-prod-server.crt -noout -subject -issuer -dates -ext subjectAltName
~~~

If the file is DER-encoded, pass the appropriate option to read it. OpenSSL is only an inspection tool; the wallet must still be managed through the Oracle PKI workflow.

## 7. Configuring the server-side TCPS listener

The listener must listen on a TCPS address. Both TCP and TCPS can remain active during migration, but plan to decommission TCP if policy requires all clients to use TLS.

### 7.1. listener.ora example

~~~text
LISTENER_TCPS =
  (DESCRIPTION_LIST =
    (DESCRIPTION =
      (ADDRESS =
        (PROTOCOL = TCPS)
        (HOST = db-prod.example.com)
        (PORT = 2484)
      )
    )
  )
~~~

HOST must be the hostname clients use and that the certificate can validate. If multiple NICs, VIPs, SCANs, or load balancers exist, configuration must reflect the actual endpoints.

### 7.2. Wallet location in sqlnet.ora

Server-side Oracle Net configuration example:

~~~text
WALLET_LOCATION =
  (SOURCE =
    (METHOD = FILE)
    (METHOD_DATA =
      (DIRECTORY = /u01/app/oracle/admin/ORCL/wallet/tcps_server)
    )
  )

SSL_CLIENT_AUTHENTICATION = FALSE
~~~

Place the configuration in the Oracle Net admin directory actually used by the listener process, typically `TNS_ADMIN` or `network/admin` of the Oracle Home. If the listener runs under a different Oracle Home, it may read a different `sqlnet.ora` than the DBA's database client.

For server-auth TLS, `SSL_CLIENT_AUTHENTICATION=FALSE` tells the server not to require a client certificate. Clients can still authenticate to the database using username/password or other configured database authentication methods.

If deploying mTLS, set `SSL_CLIENT_AUTHENTICATION=TRUE` and configure trust for the client CA in the server wallet. Consult Oracle release documentation for authentication service and certificate mapping requirements.

### 7.3. Starting and checking the listener

~~~bash
lsnrctl start LISTENER_TCPS
lsnrctl status LISTENER_TCPS
lsnrctl services LISTENER_TCPS
~~~

If the listener is already running, apply changes via reload/restart per operational procedures and verify the listener uses the right wallet/config. Do not assume editing a file automatically affects running processes.

Inspect listener logs to confirm the TCPS endpoint bound successfully and services registered. If the listener fails to open the wallet, check Oracle Home, `TNS_ADMIN`, directory permissions, and wallet path.

## 8. Configuring clients for TCPS connections

Clients must use the TCPS protocol, verify the server certificate, and trust the CA chain.

### 8.1. Client trust wallet

Create a dedicated wallet for the client and add the server's root/intermediate CAs:

~~~bash
orapki wallet create \
  -wallet /opt/app/oracle/wallet/db_trust \
  -pwd '<CLIENT_WALLET_PASSWORD>' \
  -auto_login

orapki wallet add \
  -wallet /opt/app/oracle/wallet/db_trust \
  -trusted_cert \
  -cert root-ca.pem \
  -pwd '<CLIENT_WALLET_PASSWORD>'

orapki wallet add \
  -wallet /opt/app/oracle/wallet/db_trust \
  -trusted_cert \
  -cert issuing-ca.pem \
  -pwd '<CLIENT_WALLET_PASSWORD>'
~~~

For server-auth TLS using certificates issued by this CA, the client only needs to trust the CA chain. Do not copy the server's private key to clients.

### 8.2. Client sqlnet.ora

~~~text
WALLET_LOCATION =
  (SOURCE =
    (METHOD = FILE)
    (METHOD_DATA =
      (DIRECTORY = /opt/app/oracle/wallet/db_trust)
    )
  )

SSL_SERVER_DN_MATCH = YES
~~~

`SSL_SERVER_DN_MATCH=YES` requires the client to verify the server identity per Oracle Net rules. Connections must use a hostname/DN matching the certificate. Never disable DN matching just to make a mismatched hostname connect.

### 8.3. tnsnames.ora

~~~text
ORCL_TCPS =
  (DESCRIPTION =
    (ADDRESS =
      (PROTOCOL = TCPS)
      (HOST = db-prod.example.com)
      (PORT = 2484)
    )
    (CONNECT_DATA =
      (SERVICE_NAME = orclpdb.example.com)
    )
    (SECURITY =
      (SSL_SERVER_DN_MATCH = YES)
    )
  )
~~~

SERVICE_NAME must be a database service registered with the listener. SID and SERVICE_NAME are not always interchangeable.

If explicit certificate DN pinning is required, add `SSL_SERVER_CERT_DN` inside SECURITY per the syntax of the Oracle Net client in use. Extract the real DN from the certificate; do not use an example DN.

### 8.4. Testing name resolution and connection

~~~bash
tnsping ORCL_TCPS
sqlplus -L app_user@ORCL_TCPS
~~~

`tnsping` is useful for checking alias resolution and listener reachability at the Oracle Net naming level, but does not prove database login succeeds or full certificate validation is correct. Perform an actual login and verify server identity/encryption.

Do not place passwords directly on the command line or in shared scripts. Let the client prompt interactively or use a proper secret store.

## 9. Mutual TLS (mTLS) and client certificate authentication

In standard server-auth TLS, the client verifies the server certificate; the server does not require a client certificate. With mTLS, both sides present certificates:
- The client verifies the server certificate.
- The server verifies the client certificate.

mTLS fits scenarios requiring machine/application identity at the TLS layer, such as service-to-database connections in certificate-controlled environments. It adds a transport authentication layer, but does not automatically replace database user/role authorization.

### 9.1. Server-side wallet

The server wallet needs:
- Server identity certificate/private key.
- Trusted CA chain capable of verifying client certificates.

Server `sqlnet.ora` example:

~~~text
WALLET_LOCATION =
  (SOURCE =
    (METHOD = FILE)
    (METHOD_DATA =
      (DIRECTORY = /u01/app/oracle/admin/ORCL/wallet/tcps_server)
    )
  )

SSL_CLIENT_AUTHENTICATION = TRUE
~~~

If client certificates are issued by a different CA, add that CA's root/intermediate certificates as trusted certificates in the server wallet.

### 9.2. Client-side wallet

The client wallet needs:
- Client identity certificate/private key.
- Trusted CA chain verifying the server certificate.

Generate a key/CSR in the client wallet similarly to the server wallet, but Subject/SAN and certificate policies must represent the client identity per organizational PKI. Submit the CSR to the CA to issue a `clientAuth` certificate and import it into the wallet.

### 9.3. Certificate authentication differs from database authorization

Distinguish three layers:
- TLS handshake: verifies the client certificate was issued by a trusted CA and is valid.
- Oracle authentication: maps the certificate or login credentials to a database identity per configuration.
- Authorization: checks which objects the user is permitted to SELECT/INSERT/EXECUTE.

If using certificates to log in as externally authenticated Oracle users, configure Oracle SSL authentication/enterprise user mapping strictly per documentation. If using mTLS as an additional transport authentication layer alongside database username/password, clearly define both identity layers and how they are audited.

### 9.4. Do not share one client certificate across all applications

Each critical service/application should have its own identity or managed identity group. If every application shares one private key, revoking or investigating a compromised client impacts the entire environment and obscures connection attribution.

## 10. TLS versions, cipher suites, and algorithms

TLS negotiation depends on Oracle Database/RU, Oracle Client, JDBC driver, JDK, wallet provider, and security policy. One side supporting only legacy ciphers/versions can cause handshake failures or force policy downgrades.

### 10.1. TLS version

Prefer TLS versions supported by your Oracle release/RU and client drivers in line with your organization's current security baseline. TLS 1.2 is a common baseline in many Oracle 19c deployments; TLS 1.3 availability depends on exact release/RU and client stack—do not assume all 19c builds support it identically.

If using `SSL_VERSION` in `sqlnet.ora` or equivalent driver properties, verify supported values for the exact Oracle Home/JDBC driver. Do not copy TLS version settings from another Oracle release without checking.

### 10.2. Cipher suites

Cipher suites specify key exchange, authentication, and data encryption algorithms. Allow only organization-approved ciphers supported by both ends. Avoid enabling weak or legacy ciphers just for compatibility with an old client; upgrading the client/RU is usually the sustainable fix.

### 10.3. Certificate signatures and key sizes

PKI policy should define:
- Key algorithm and key size meeting baseline standards.
- Acceptable certificate signature algorithms.
- Validity period.
- Key Usage and Extended Key Usage.
- DNS/IP SANs.
- CA hierarchy and revocation policy.

The RSA 2048-bit CSR example illustrates common compatibility, not a substitute for current key management policy. Some environments may require larger RSA keys or elliptic-curve keys depending on Oracle/driver stack support.

### 10.4. Testing compatibility before enforcing

Before enforcing a stricter server TLS version/cipher policy:
1. Inventory all Oracle Clients, JDBC drivers, JDKs, and integration tools.
2. Check release/RU and cipher capabilities.
3. Test in staging with real wallets/certificates.
4. Test failover, connection pools, and monitoring.
5. Monitor handshake errors after rollout.
6. Remove legacy versions/ciphers only after all clients have migrated.

## 11. JDBC Thin, OCI, and Java applications

Java applications may use Oracle JDBC Thin or OCI drivers. TLS and wallet configuration must match the driver, JDK, and application packaging.

### 11.1. JDBC Thin with TCPS connect descriptor

URL example:

~~~java
String url =
    "jdbc:oracle:thin:@(DESCRIPTION=" +
    "(ADDRESS=(PROTOCOL=TCPS)(HOST=db-prod.example.com)(PORT=2484))" +
    "(CONNECT_DATA=(SERVICE_NAME=orclpdb.example.com))" +
    "(SECURITY=(SSL_SERVER_DN_MATCH=YES)))";
~~~

Set connection properties per JDBC driver documentation. When using an Oracle Wallet, JDBC Thin supports configuring wallet location via the corresponding Oracle Net properties, for example:

~~~java
Properties props = new Properties();
props.setProperty(
    "oracle.net.wallet_location",
    "(SOURCE=(METHOD=FILE)(METHOD_DATA=(DIRECTORY=/opt/app/oracle/wallet/db_trust)))"
);
props.setProperty("oracle.net.ssl_server_dn_match", "true");

// Supply username/password via an appropriate secret provider.
Connection connection =
    DriverManager.getConnection(url, props);
~~~

Property names, wallet reading behavior, and TLS support depend on JDBC driver version. Check the Oracle JDBC Developer's Guide for your exact driver; do not assume older drivers understand newer properties.

### 11.2. JDBC using a Java truststore

Another option is a Java KeyStore (JKS/PKCS12) configured for JSSE via JVM properties:

~~~text
-Djavax.net.ssl.trustStore=/opt/app/security/oracle-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
~~~

If the truststore is password-protected, supply the password through an appropriate runtime secret mechanism rather than exposing it on public command lines or broadly readable config files.

Do not mix wallet location and Java truststore without understanding driver precedence. Choose one driver-supported model, verify server DN matching, and validate the certificate chain.

### 11.3. OCI clients

OCI-based clients such as SQL*Plus can use Oracle Net configuration and wallets from Oracle Home/`TNS_ADMIN`. Ensure:
- The process reads the intended `sqlnet.ora`.
- The wallet path exists and the OS account has read access.
- The TNS alias uses TCPS.
- The client Oracle Home supports the TLS/cipher policy.
- No other `sqlnet.ora` overrides or takes unexpected precedence.

### 11.4. Connection pools

With pools:
- Each physical connection is established over TCPS per configuration.
- Replacing a wallet/certificate may not immediately affect already open connections.
- A pool drain/recycle procedure is needed after certificate rotation if new handshakes must use the new cert.
- Never log wallet passwords or private keys.
- Monitor failures creating new connections, not just existing live connections.

## 12. Wallets, credential stores, and passwords

An Oracle Wallet can hold certificates and private keys, and certain wallets can also serve as a Secure External Password Store for database credentials.

Distinguish the two purposes:
- TLS wallet: trust chain, server/client certificates, and private keys.
- External password store: username/password allowing clients to connect via credential aliases.

Example initializing a credential store with `mkstore` (syntax and behavior vary by Oracle Client):

~~~bash
mkstore -wrl /opt/app/oracle/wallet/credentials -create
mkstore -wrl /opt/app/oracle/wallet/credentials \
  -createCredential ORCL_TCPS app_user
~~~

The command prompts for the password per tool mechanisms. Connecting with an external password store may use:

~~~text
SQLNET.WALLET_OVERRIDE = TRUE
~~~

And clients can use a connect alias syntax like `/@ORCL_TCPS` when wallet/credential mapping is properly configured.

Do not treat storing username/password in a wallet as a replacement for TLS. Both a credential store and TCPS can be used together: one supplies database credentials, while the other encrypts and authenticates the transport channel.

## 13. Certificate lifecycle management

Certificates are not create-once-and-forget assets. A management workflow is needed from issuance request, deployment, expiry monitoring, renewal, and rotation through revocation.

### 13.1. Inventory

Maintain an inventory tracking:
- Wallet name and path.
- Host/service/client identity.
- Certificate subject, issuer, serial, fingerprint.
- DNS/IP SANs.
- Not Before/Not After dates.
- CA chain.
- Technical owner and business owner.
- Oracle Home, listener, JDBC driver, and services in use.
- Renewal schedule and backup location.

### 13.2. Monitoring expiry

Use `orapki display` or PKI/monitoring tools to track validity periods. Example:

~~~bash
orapki wallet display \
  -wallet /u01/app/oracle/admin/ORCL/wallet/tcps_server \
  -complete \
  -pwd '<WALLET_PASSWORD>'
~~~

You can use OpenSSL to check certificate file validity dates:

~~~bash
openssl x509 -in db-prod-server.crt -noout -dates -subject -issuer
~~~

Set expiry alerts early enough to complete CA approval, certificate issuance, staging rollout, production rollout, and rollback. Do not wait until the expiration date to begin renewal.

### 13.3. Renewal and rotation

Recommended procedure:
1. Confirm CA, subject/SAN, key usage, and new validity.
2. Generate key/CSR per policy (decide explicitly whether to reuse or rotate keys).
3. Receive the new certificate and verify chain/fingerprint.
4. Import the certificate into the target wallet.
5. Check wallet display, private key association, and validity.
6. Deploy the wallet to servers/clients in waves.
7. Reload/restart listeners/processes as required.
8. Open fresh connections from each client type.
9. Verify server DN match, trust chain, and service login.
10. Drain old connection pools if needed.
11. Retain rollback wallets/certificates per policy for the allowed window.
12. Remove old certificates once no clients depend on them and the rollback window has passed.

Do not remove old certificates or CA trust anchors before all endpoints have switched over. When root/intermediate CAs change, an overlap period may be needed so clients trust both old and new chains.

### 13.4. Revocation

If a private key is compromised or a certificate is no longer trustworthy, revoke it via the CA process and update revocation state according to configured mechanisms (CRL/OCSP if supported by the stack and required by policy).

Simply deleting a certificate from a wallet is not equivalent to CA revocation. Other clients may continue trusting that certificate until trust/revocation state is updated.

### 13.5. Backup and recovery

Backups should include:
- Password-protected wallet files.
- Auto-login wallets if used and permitted by policy.
- Wallet passwords stored separately in a secret manager.
- Certificate/fingerprint/expiry metadata.
- Recovery procedures tested on appropriate hosts.
- Audited access controls on backups.

Never back up private keys by emailing files or pushing to repositories. Test that backups are actually restorable, not just that files exist.

## 14. Configuring mTLS and database identity

When an organization requires client certificates as identities, design the entire chain:
1. CA issues a client certificate for the workload identity.
2. Client holds the private key in a wallet/keystore.
3. Server trusts the CA that issued the client cert.
4. TLS listener requires client certificates.
5. Oracle authenticates/maps the certificate to a database identity per configuration.
6. The database user is granted minimal roles/privileges.

### 14.1. External user mapping

Oracle supports certificate-based external authentication in appropriate SSL authentication models. User mapping must be configured based on subject/DN or enterprise identity rules per Oracle documentation.

Do not create external users based solely on example DNs from documentation. Verify the exact DN format, mapping rule, certificate chain, and authentication service on both client and server.

### 14.2. Certificate identity and user identity

A certificate can represent a service account or workload. Avoid sharing the same certificate across multiple applications when accurate auditing is required. If one application uses multiple database users, define clearly whether certificates authenticate transport/clients while database credentials identify database users, or use external mapping by design.

### 14.3. Privilege controls

After TLS authentication, still enforce:
- Least privilege.
- Role-based access by function.
- No SYS/SYSTEM for applications.
- Credential rotation.
- Auditing of logon/logoff and privileged operations.
- Network ACLs/firewalls.
- Separation of schema owner and runtime user.

## 15. Verifying connections and encryption

A successful connection alone does not prove security configuration is correct. Verify the listener, TLS handshake, server identity, database login, and negotiated service.

### 15.1. Checking the listener

~~~bash
lsnrctl status LISTENER_TCPS
lsnrctl services LISTENER_TCPS
~~~

Verify:
- TCPS endpoint and port are correct.
- Services are registered.
- Listener uses the expected Oracle Home/`TNS_ADMIN`.
- No errors opening the wallet or loading certificates.

### 15.2. Inspecting the certificate chain with OpenSSL

~~~bash
openssl s_client \
  -connect db-prod.example.com:2484 \
  -servername db-prod.example.com \
  -showcerts
~~~

This command inspects the TLS handshake and certificate chain returned by the endpoint. It does not replace an Oracle Net login test and does not verify that all Oracle Net options are applied. Verification outcomes depend on OpenSSL's trust store and the command environment.

### 15.3. Inspecting the wallet

~~~bash
orapki wallet display \
  -wallet /opt/app/oracle/wallet/db_trust \
  -complete \
  -pwd '<CLIENT_WALLET_PASSWORD>'
~~~

Verify trusted root/intermediate CAs, certificate expiry, and wallet contents. Never expose or export private keys to unprotected locations.

### 15.4. Inspecting the connected session

~~~sql
SELECT
    sid,
    serial#,
    network_service_banner
FROM v$session_connect_info
WHERE sid = SYS_CONTEXT('USERENV', 'SID');
~~~

`V$SESSION_CONNECT_INFO` can show banners for network services, encryption, and crypto-checksumming depending on mechanism/version. Read the actual output; do not infer encryption merely from port number or TNS alias.

### 15.5. Verifying target service and user

~~~sql
SELECT
    SYS_CONTEXT('USERENV', 'DB_NAME') AS db_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user,
    SYS_CONTEXT('USERENV', 'HOST') AS client_host
FROM dual;
~~~

Confirm the client connected to the right database/service/user after the TLS handshake completed.

### 15.6. tnsping is not a complete test

`tnsping` primarily checks Oracle Net naming and listener reachability. It does not prove the user can log in, the database service is operational, the application uses the right wallet, or all certificate validation policies are enforced. Always perform a real login smoke test using the application's actual client/driver.

## 16. Diagnosing TLS/TCPS errors

### 16.1. ORA-29024: Certificate validation failure

Possible causes:
- Missing root/intermediate CA.
- Expired certificate or Not Before date not yet reached.
- Invalid certificate chain.
- Hostname/SAN/DN mismatch.
- Wrong client trust store/wallet.
- Revoked certificate or policy validation rejection.

Investigation steps:
1. Inspect subject, issuer, SAN, dates, and fingerprint.
2. Verify the client wallet contains the full CA chain.
3. Confirm the hostname used by the client matches the SAN.
4. Enable DN matching and check explicit DN pinning if configured.
5. Check CRL/OCSP policy and certificate status.
6. Check listener/client traces when necessary.

Never fix ORA-29024 by disabling server DN matching or blindly trusting every certificate.

### 16.2. ORA-28860: Fatal SSL error

This is a general SSL error. Possible causes:
- No overlapping TLS version.
- Incompatible cipher suites.
- Corrupt certificate/key/chain.
- Unreadable wallet.
- Peer closed the handshake.
- Incompatible client/server libraries.

Inspect listener logs, sqlnet traces, Oracle Home/JDK versions, and handshake output. Enable elevated tracing only briefly and protect trace files as they can contain sensitive metadata.

### 16.3. ORA-28759: Failure to open file

Usually related to wallet/file path or access permissions:
- Wrong DIRECTORY in `WALLET_LOCATION`.
- Process running under an OS account lacking permissions.
- Missing or unreadable `ewallet.p12`/`cwallet.sso`.
- Incorrect `TNS_ADMIN`/Oracle Home.
- Wallet copied with missing files or wrong ownership.

Test under the exact OS account of the listener/client process, not just from a DBA's shell.

### 16.4. ORA-12154 and ORA-12514

- ORA-12154: client cannot resolve the connect identifier/alias.
- ORA-12514: listener received connection but does not recognize the requested service name.

These two errors are typically naming/service registration issues rather than direct certificate errors. Check `tnsnames.ora`, `TNS_ADMIN`, `SERVICE_NAME`, and `lsnrctl services`.

### 16.5. Handshake succeeds but login fails

TLS may have completed while database authentication/authorization failed. Check:
- Username/password or external authentication mapping.
- User account lock/expiry.
- Service/PDB and container.
- Database listener service registration.
- Database audit/error logs.
- Client certificate mapping if using mTLS external authentication.

Do not confuse database login failures with TLS trust failures.

## 17. Securing files and configurations

### 17.1. Wallet permissions

- Only required processes should have read access to wallets.
- Wallet directories must not be writable by unrelated application users.
- Auto-login wallets still require strict OS ACL protection.
- Wallet backups must be encrypted and access-controlled.
- Never put wallets/private keys in source control, public artifacts, or logs.

### 17.2. Protecting sqlnet.ora and tnsnames.ora

These files can contain wallet paths, DNs, encryption policies, and endpoints. Never put real passwords in these files unnecessarily. Manage configs via controlled internal version control; separate secrets from configuration and verify file permissions.

### 17.3. TNS_ADMIN and Oracle Home

A host may have multiple Oracle Homes or applications using separate `TNS_ADMIN` paths. When configuring TCPS, verify exactly which files each process reads. Check service/systemd/container/Windows service environments, not just interactive shells.

### 17.4. Containers and Kubernetes

If applications run in containers:
- Mount wallets from secret volumes or secret manager integrations.
- Never bake private keys into container images.
- Use read-only mounts where appropriate.
- Refresh pods/connection pools per rotation procedures.
- Verify file ownership/UID/GID.
- Never log secrets on startup.
- Ensure the DNS hostname in the certificate matches the service endpoint used by containers.

## 18. Production deployment checklist

### Design
- Decide between NNE and TCPS.
- Decide whether mTLS is needed or server-auth TLS suffices.
- Choose TLS versions/ciphers per security baseline and client capabilities.
- Inventory all Oracle Clients, JDBC drivers, JDKs, and agents.
- Identify hostnames/services, DNS, VIPs, SCANs, and load balancers.

### PKI
- Approved CA available.
- Certificate includes SANs matching endpoints.
- Key Usage/EKU match `serverAuth`/`clientAuth` purposes.
- Full trust chain present.
- Fingerprints verified via an independent channel.
- Private keys generated/stored in protected wallets or keystores.
- Expiry/renewal/revocation have assigned owners and alerts.

### Oracle Net
- TCPS listener open on the intended address/port.
- Listener reads the intended wallet and `sqlnet.ora`.
- Clients use `PROTOCOL=TCPS`.
- Server DN matching enabled.
- Clients trust the CA chain.
- mTLS policy consistent if enabled.
- Service names registered properly.

### Applications
- JDBC/OCI drivers support the chosen configuration.
- Wallets/truststores mounted properly.
- Connection pools can open new connections over TCPS.
- No passwords/private keys in source code/logs.
- Failover/reconnect and rotation tested.

### Operations
- TLS and database login smoke tests in place.
- Logs/traces and diagnostic collection procedures ready.
- Wallet backup/restore tested.
- Certificate overlap plan ready for rotation.
- Rollback configs/wallets prepared.
- Monitoring for handshake failures and certificate expiry active.

## 19. Lab: deploying server-auth TCPS

Perform this in a lab environment you control, with a lab CA or validly issued certificates.

### Step 1: Prepare the endpoint

Choose a lab hostname, e.g., `db-lab.example.test`, and ensure clients resolve it. The server certificate must have a matching DNS SAN.

### Step 2: Create the server wallet and CSR

Use the commands in Section 6 to:
- Create the wallet.
- Import root/intermediate CAs.
- Generate a key pair.
- Export a CSR.
- Submit the CSR to the lab CA.
- Import the signed leaf certificate.

### Step 3: Configure the TCPS listener

Add the `PROTOCOL=TCPS` address to `listener.ora` and configure the wallet location in the listener's `sqlnet.ora`. Start/reload the listener and verify with `lsnrctl status`.

### Step 4: Create the client trust wallet

Create a client-side wallet and import the root/intermediate CAs. Do not copy the server's private key.

### Step 5: Configure the TNS alias

Create an alias using the TCPS port and the right `SERVICE_NAME`. Enable `SSL_SERVER_DN_MATCH=YES`.

### Step 6: Verify the handshake

Use `openssl s_client` to inspect the chain if OpenSSL is available. Then connect using SQL*Plus/SQLcl via the alias. Check `V$SESSION_CONNECT_INFO` and `USERENV` context.

### Step 7: Controlled fault injection

In the lab environment:
- Test an alias using a hostname not in the SAN.
- Test a client trust wallet missing the intermediate CA.
- Test an invalid wallet path.
- Test a nonexistent service name.

Record errors at each layer: name resolution, TLS handshake, certificate validation, listener service registration, or database authentication. Then restore the correct configuration.

## 20. Lab: mTLS and certificate rotation

### 20.1. mTLS

1. Create a dedicated client wallet.
2. Generate a client key/CSR with an identity issued by the lab CA.
3. Import the client certificate into the client wallet.
4. Add the client CA chain to the server wallet's trust store.
5. Set `SSL_CLIENT_AUTHENTICATION=TRUE` on the server.
6. Configure the client to use the wallet holding its private key/client certificate.
7. Verify handshake and database authentication.
8. Attempt a connection without a client certificate to confirm the server rejects it per policy.

If mapping client certificates to database users is needed, follow Oracle SSL external authentication documentation; do not treat a successful handshake as granting database authorization.

### 20.2. Rotation

1. Create a new certificate with matching SAN/identity.
2. Verify chain, dates, fingerprint, and key usage.
3. Import into a new wallet or follow a versioned wallet process.
4. Test in staging with real clients.
5. Deploy the new server wallet.
6. Reload/restart the listener as needed.
7. Open new connections and confirm the new certificate is presented.
8. Recycle connection pools if necessary.
9. Retain rollback capability for the defined period.
10. Remove old certificates/trust anchors once no dependencies remain.

Never modify production wallets directly without backups and a rollback plan.

## 21. Common issues

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| TCP connects, TCPS fails | Listener not listening on TCPS or wrong port | Check `listener.ora` and `lsnrctl status` |
| ORA-29024 | Invalid trust chain, expiry, SAN/DN, or revocation | Check certificates and trust wallet |
| ORA-28860 | TLS/cipher/version mismatch or handshake failure | Check RU, driver, JDK, listener/sqlnet traces |
| ORA-28759 | Wrong wallet path or file permissions | Check `TNS_ADMIN`, Oracle Home, owner/ACLs |
| ORA-12154 | Alias cannot be resolved | Check `tnsnames.ora` and `TNS_ADMIN` |
| ORA-12514 | Service name not registered/incorrect | Check `SERVICE_NAME` and `lsnrctl services` |
| Certificate valid but rejected | SAN/DN/issuer/chain mismatch | Check SAN, trust anchor, and DN matching |
| Only one client host fails | Different wallet, CA bundle, driver, or clock | Compare client environment and system time |
| Listener runs but cannot open wallet | Listener uses different Oracle Home/`TNS_ADMIN` | Check process environment and config files |
| mTLS server rejects client | Missing client cert, untrusted CA, or wrong EKU | Check client wallet and server CA trust |
| JDBC fails while SQL*Plus works | Different driver/JDK properties or truststore | Check JDBC driver config and JVM |
| Rotation breaks connection pool | Old/new connections use different certs | Drain/recycle pool and verify new cert |
| `tnsping` succeeds but login fails | `tnsping` does not test full database authentication | Perform an actual login smoke test |
| NNE fails to negotiate | Client/server policies or algorithms do not intersect | Check `SQLNET.ENCRYPTION`/`CRYPTO_CHECKSUM` on both sides |
| Encryption active without server validation | Only NNE enabled or DN matching disabled | Use TCPS with trust chain and identity validation |

## 22. Practice exercises

### Exercise 1 — Comparing NNE and TCPS

Write a comparison table covering encryption, integrity, server authentication, client authentication, wallets, and client compatibility. Choose a model for an internal service and explain why.

### Exercise 2 — NNE negotiation

Configure server REQUIRED and client REQUESTED with compatible algorithms. Connect and inspect `V$SESSION_CONNECT_INFO`. Remove overlapping algorithms in the lab and record the outcome.

### Exercise 3 — Certificate inspection

Use `orapki` and OpenSSL to inspect Subject, Issuer, SAN, validity, key usage, and fingerprint. Explain root, intermediate, and leaf certificates.

### Exercise 4 — Server-auth TCPS

Create a wallet, CSR, import CA/leaf certificates, open a TCPS listener, and connect from a client trust wallet. Verify hostname matching.

### Exercise 5 — DN matching

Test a hostname matching the SAN and one not matching the SAN. Record the difference when `SSL_SERVER_DN_MATCH` is enabled. Restore the correct hostname afterward.

### Exercise 6 — mTLS

Create a client certificate, enable `SSL_CLIENT_AUTHENTICATION`, and test clients with and without a certificate. Distinguish TLS handshake from database user authentication.

### Exercise 7 — JDBC Thin

Use JDBC Thin to connect over TCPS. Test wallet properties or a Java truststore per driver. Confirm a connection pool can create new connections.

### Exercise 8 — Certificate renewal

Create a new certificate, deploy a new wallet in staging, verify the handshake, and simulate rollback. Document the overlap order for CA and leaf certificates.

### Exercise 9 — Troubleshooting

Simulate wrong wallet path, missing CA, wrong hostname, and wrong service name. Classify each error as naming, listener, TLS trust, or database login.

### Exercise 10 — Production runbook

Write a runbook including inventory, expiry alerts, backups, rotation, validation, pool recycling, rollback, and owners for every certificate.

## 23. Lab environment cleanup

After finishing:
- Stop the lab listener if no longer needed.
- Delete or archive lab wallets per policy.
- Revoke lab certificates if required by PKI.
- Remove unneeded CSRs/test certificates.
- Remove lab secrets/passwords from temporary storage.
- Restore `listener.ora`, `sqlnet.ora`, and `tnsnames.ora`.
- Confirm no clients still point to the lab endpoint.

Do not delete shared wallets, CAs, or certificates belonging to other environments.

## Summary

Oracle Net can protect connections with Native Network Encryption over TCP or TLS over TCPS. NNE is configured via `SQLNET.ENCRYPTION_*` and `SQLNET.CRYPTO_CHECKSUM_*`; it provides encryption/integrity but does not provide TLS-style certificate-based server identity. TCPS uses TLS, wallets/trust stores, and certificate chains to encrypt traffic and authenticate the server; mTLS can be enabled to require client certificates.

Wallets hold private keys, identity certificates, and trusted CA certificates. A secure workflow covers generating keys/CSRs, verifying CAs, importing chains and leaf certificates, configuring listeners/clients, enabling server DN matching, and verifying TLS handshakes and database logins with the right drivers. Certificates require inventory, expiry alerting, renewal, rotation, revocation, backups, and strict file permissions. When troubleshooting, separate name resolution, listener/service, wallet access, TLS validation, and database authentication errors; never disable certificate validation to bypass errors.

## Oracle reference documentation

- [Oracle Database Net Services Administrator's Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/netag/) — Oracle Net, TLS/TCPS, listener, and client configuration.
- [Oracle Database Net Services Reference (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/netrf/) — `sqlnet.ora` parameters, encryption, wallets, and connect descriptors.
- [Oracle Database Security Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/) — authentication, network security, and certificate-based security.
- [Oracle Database JDBC Developer's Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/) — JDBC Thin/OCI and secure connections.
- [Oracle Database Licensing Information User Manual (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/) — licensing information for relevant database options.

When deploying on Oracle releases/RUs other than 19c, consult the Oracle Net Services Administrator's Guide, Net Services Reference, and JDBC driver documentation for the exact version, especially regarding TLS version/cipher support, wallet locations, DN matching, mTLS, and certificate validation.
