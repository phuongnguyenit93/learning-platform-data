# TLS, sslMode, Truststores, and Server Identity Verification

In the `DATABASE_MYSQL` module, learners master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query optimization, authorization, backups, and relational database operational issues. This lesson focuses on securing JDBC connections between Java applications and MySQL with TLS, configuring MySQL Connector/J's `sslMode`, managing CAs in Java truststores, and verifying server identity.

TLS protects data in transit and enables clients to verify the server they are connecting to. Enabling encryption alone is not enough to defend against spoofed servers or man-in-the-middle attacks. Applications must validate the certificate chain and the server name against the exact hostname in the certificate. With MySQL Connector/J, `sslMode=VERIFY_IDENTITY` is the right choice for production connections once certificates and DNS are configured properly.

## 1. How Does TLS Protect a JDBC Connection?

When a Java application connects to MySQL over TCP, Connector/J and MySQL negotiate a TLS session before exchanging SQL data. After the handshake, query payloads, result sets, and authentication data travel over the encrypted channel using the negotiated TLS protocol.

A secure session must satisfy several distinct requirements:

1. **Encryption:** data cannot be read directly while traversing the network.
2. **Integrity:** data cannot be modified without detection.
3. **Server authentication:** the application verifies that the server certificate was issued by a CA it trusts.
4. **Identity verification:** the DNS name used by the application must match an identity recorded in the server certificate.
5. **Certificate lifecycle management:** certificates remain valid, have the proper purpose, include a complete CA chain, and are rotated on time.

Encryption and identity verification are two different concerns. A connection can be encrypted without checking certificates or hostnames. In that case, an application could still encrypt data with an attacker-controlled spoofed server.

## 2. sslMode Options in Connector/J

The `sslMode` property has been supported since MySQL Connector/J 8.0.13. It determines whether Connector/J uses TLS and to what extent it verifies the server certificate.

| Value | Behavior | When appropriate |
|---|---|---|
| `DISABLED` | Does not use TLS. | Only in isolated test environments or when another evaluated protection mechanism is in place. |
| `PREFERRED` | Prefers TLS if supported by the server; falls back to an unencrypted connection if the server does not support TLS. | Legacy compatibility; should not be used as a production security policy. |
| `REQUIRED` | Requires TLS but does not verify the server certificate chain. | When encryption is required but certificate verification is managed at another layer; does not fully protect against spoofed servers. |
| `VERIFY_CA` | Requires TLS and verifies the server certificate is signed by a trusted CA. | When CA chain verification is needed without checking the hostname. |
| `VERIFY_IDENTITY` | Requires TLS, verifies the certificate chain, and checks server identity against the hostname. | The preferred choice for production application connections. |

Quick configuration example in a JDBC URL:

```text
jdbc:mysql://db.example.com:3306/shop?sslMode=VERIFY_IDENTITY
```

`PREFERRED` can silently downgrade to a non-TLS connection if the server does not support TLS. `REQUIRED` encrypts without verifying the server. `VERIFY_CA` verifies the CA but may still accept a valid certificate issued to a different hostname. `VERIFY_IDENTITY` performs both checks, so the hostname in the JDBC URL must match a name in the certificate.

In production configurations, do not use `PREFERRED` merely so the application keeps connecting when TLS fails. Use a mode that enforces verification and resolve the underlying certificate or server configuration issue when handshakes fail.

## 3. Server Certificates and Hostname Verification

MySQL Server needs a valid server certificate and its corresponding private key. The certificate is usually signed by an internal CA or a public CA. The DNS name the application uses to connect must be present in the certificate's Subject Alternative Name (SAN).

Example certificate SANs:

```text
DNS:db.example.com
DNS:mysql-prod.internal.example.com
```

If the JDBC URL uses `db.example.com`, Connector/J with `VERIFY_IDENTITY` can verify that name. If the application connects using `10.20.5.10` while the certificate only has DNS SANs, IP identity verification can fail. Use a hostname included in the SAN or issue a certificate with an appropriate IP SAN if connecting by IP address is an actual requirement.

Do not rely on the legacy Common Name (CN) instead of SAN. When issuing new certificates, include the hostnames actually used in SAN and drop aliases that are no longer valid. If the application connects through a DNS alias, proxy, or load balancer, the certificate presented at the TLS endpoint seen by the client must validate against that exact URL name.

### Configuring TLS on MySQL Server

Example server configuration in an option file:

```ini
[mysqld]
ssl_ca=/etc/mysql/certs/client-ca.pem
ssl_cert=/etc/mysql/certs/server-cert-chain.pem
ssl_key=/etc/mysql/certs/server-key.pem
tls_version=TLSv1.2,TLSv1.3
require_secure_transport=ON
```

These paths are Linux examples. `ssl_cert` points to the server certificate (which can contain the chain sent to clients); `ssl_key` points to the matching private key; `ssl_ca` is used in client certificate validation when deploying mutual TLS. The CA that Java uses to verify the server certificate must be trusted in the client-side truststore.

`require_secure_transport=ON` requires remote connections to use a secure transport supported by MySQL, such as TCP with TLS. Local connections over Unix sockets or named pipes may be considered secure by their respective transport mechanisms; this option does not mean every local connection must perform a TLS handshake.

Check server configuration:

```sql
SHOW GLOBAL VARIABLES LIKE 'require_secure_transport';
SHOW GLOBAL VARIABLES LIKE 'tls_version';
SHOW GLOBAL VARIABLES LIKE 'ssl_ca';
SHOW GLOBAL VARIABLES LIKE 'ssl_cert';
SHOW GLOBAL VARIABLES LIKE 'ssl_key';
```

Filenames, permissions, and syntax should be adapted to your OS, MySQL version, and organization's certificate management practices. The server private key must be protected so only the MySQL service account and authorized administrators can read it.

### Requiring TLS per MySQL Account

In addition to server-wide policy, MySQL can set security requirements per account:

```sql
CREATE USER 'app_user'@'10.20.5.%'
    IDENTIFIED BY 'PASSWORD_FROM_SECRET_STORE'
    REQUIRE SSL;
```

`REQUIRE SSL` forces the account to use an encrypted connection. It does not mean the client must present an X.509 certificate. If deploying mutual TLS and you want the account to require a valid client certificate, use:

```sql
ALTER USER 'app_user'@'10.20.5.%' REQUIRE X509;
```

Privileges and hosts in this example should be narrowed for your actual environment. `REQUIRE X509` requires the client to supply a valid certificate; for tighter binding, MySQL also supports issuer or subject conditions. Enable this requirement only after issuing client certificates, configuring the CA on the server, and testing certificate rotation.

## 4. Truststores and Keystores in Java

Java uses certificate stores to determine which CAs are trusted and, if needed, keystores to provide client certificates.

| Store | What does it hold? | Role in TLS |
|---|---|---|
| Truststore | CA certificates or certificates chosen as trust anchors. Usually contains no private keys. | Enables Java to verify the certificate chain sent by MySQL Server. |
| Client keystore | Client certificate and its corresponding private key. | Enables the application to present client identity when the server requires mutual TLS. |
| Server keystore/certificate files | Server certificate and private key. | Used by MySQL to prove server identity during the TLS handshake. |

A truststore is not a place to store MySQL passwords. A client keystore also does not replace SQL username/password authentication unless the application has a separately configured authentication mechanism.

Common formats include JKS and PKCS12. PKCS12 is the standard interchange format and is widely supported by Java. Standardize on one format, protect store passwords, and restrict file read permissions.

### Creating a Truststore from a CA

First, obtain the correct root or intermediate CA certificate from the PKI/infrastructure team through a trusted channel. Verify the certificate's fingerprint against an independent source before importing.

Example of creating a PKCS12 truststore:

```bash
keytool -importcert \
  -alias mysql-issuing-ca \
  -file mysql-issuing-ca.pem \
  -keystore mysql-truststore.p12 \
  -storetype PKCS12
```

`keytool` will prompt for a password and ask you to confirm trusting the certificate. Only accept the import after verifying the fingerprint. It is generally better to trust the issuing CA rather than importing a fixed leaf server certificate, unless you intentionally practice certificate pinning with a matching rotation workflow.

Inspect truststore contents:

```bash
keytool -list -v \
  -keystore mysql-truststore.p12 \
  -storetype PKCS12
```

This command displays aliases, subjects, issuers, validity dates, and fingerprints. Never pass real passwords in command-line arguments or shell history; let `keytool` prompt interactively or use a secret mechanism appropriate for your deployment platform.

## 5. Configuring Connector/J with sslMode=VERIFY_IDENTITY

The following example uses JDBC `DriverManager` and a dedicated truststore. Passwords come from a secret manager or environment variables provided by the deployment environment; do not hard-code them in source code.

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.Statement;
import java.util.Properties;

public class SecureMysqlConnection {
    public static void main(String[] args) throws Exception {
        String url = "jdbc:mysql://db.example.com:3306/shop";

        Properties props = new Properties();
        props.setProperty("user", System.getenv("DB_USER"));
        props.setProperty("password", System.getenv("DB_PASSWORD"));
        props.setProperty("sslMode", "VERIFY_IDENTITY");
        props.setProperty(
            "trustCertificateKeyStoreUrl",
            "file:/etc/myapp/certs/mysql-truststore.p12"
        );
        props.setProperty("trustCertificateKeyStoreType", "PKCS12");
        props.setProperty(
            "trustCertificateKeyStorePassword",
            System.getenv("MYSQL_TRUSTSTORE_PASSWORD")
        );

        try (Connection connection = DriverManager.getConnection(url, props);
             Statement statement = connection.createStatement();
             ResultSet rs = statement.executeQuery(
                 "SHOW SESSION STATUS LIKE 'Ssl_cipher'")) {
            while (rs.next()) {
                System.out.println(rs.getString("Variable_name") + "="
                    + rs.getString("Value"));
            }
        }
    }
}
```

This example assumes Connector/J is on the classpath and environment variables are securely supplied. `db.example.com` must appear in the server certificate's SAN. The `file:/...` path must point to a truststore readable by the Java process. Property names must match the exact capitalization documented by Connector/J.

You can configure a truststore at the JVM level using JSSE properties such as `javax.net.ssl.trustStore`, `javax.net.ssl.trustStoreType`, and `javax.net.ssl.trustStorePassword`. This affects other TLS connections within the same JVM if they rely on the default truststore. When an application runs multiple services or connects to multiple systems with different CAs, a dedicated truststore for Connector/J scopes trust boundaries more cleanly.

Do not configure multiple truststore mechanisms simultaneously without verifying the precedence order of Connector/J and JSSE. Check the exact documentation for the Connector/J version you use, then test with real certificates in staging.

## 6. Mutual TLS: Authenticating Both Client and Server

In standard TLS, the client verifies the server certificate. With mutual TLS (mTLS), the server also requires the client to present a certificate to verify the application's identity.

General flow:

1. MySQL Server presents the server certificate; Connector/J verifies the CA and hostname per `VERIFY_IDENTITY`.
2. MySQL requests a client certificate based on account policy or connection configuration.
3. Connector/J loads the certificate and private key from the client keystore.
4. MySQL validates the client certificate against the CA configured on the server.
5. After the TLS handshake, MySQL still performs account authentication and SQL privilege checks according to the configured mechanism.

Example client keystore configuration in Connector/J:

```java
props.setProperty("sslMode", "VERIFY_IDENTITY");
props.setProperty(
    "trustCertificateKeyStoreUrl",
    "file:/etc/myapp/certs/mysql-truststore.p12"
);
props.setProperty("trustCertificateKeyStoreType", "PKCS12");
props.setProperty(
    "trustCertificateKeyStorePassword",
    System.getenv("MYSQL_TRUSTSTORE_PASSWORD")
);
props.setProperty(
    "clientCertificateKeyStoreUrl",
    "file:/etc/myapp/certs/app-client-keystore.p12"
);
props.setProperty("clientCertificateKeyStoreType", "PKCS12");
props.setProperty(
    "clientCertificateKeyStorePassword",
    System.getenv("MYSQL_CLIENT_KEYSTORE_PASSWORD")
);
```

The server must configure a trusted CA to validate the client certificate, and the account must require X.509 if policy mandates it:

```sql
ALTER USER 'app_user'@'10.20.5.%' REQUIRE X509;
```

The client keystore must contain the matching private key and certificate chain. Do not share one private key across multiple applications if independent revocation and auditability are needed. Issue separate certificates per service, set reasonable lifetimes, and plan renewal before expiration.

## 7. Selecting the TLS Protocol and Verifying the Active Version

The TLS protocol used by a connection depends on several components: MySQL Server, OpenSSL or the server's TLS library, the JDK, Connector/J, and allowed configuration on both sides.

Connector/J provides the `tlsVersions` property to restrict which TLS versions the client is allowed to negotiate. Example:

```java
props.setProperty("tlsVersions", "TLSv1.2,TLSv1.3");
```

Configure only protocols supported by both the server and the JDK. Do not re-enable legacy TLS solely to let an outdated client connect; upgrade the JDK or Connector/J if necessary. On the server, the `tls_version` variable defines allowed protocols.

After connecting, verify the actual TLS session:

```sql
SHOW SESSION STATUS LIKE 'Ssl_version';
SHOW SESSION STATUS LIKE 'Ssl_cipher';
```

`Ssl_version` shows the negotiated protocol, and `Ssl_cipher` shows the active cipher suite. If `Ssl_cipher` is empty, the current session is not using TLS. Do not rely only on the configured URL; verify the status on the application's actual session.

## 8. Legacy Properties and Configurations to Avoid

Connector/J has legacy SSL properties such as `useSSL`, `requireSSL`, and `verifyServerCertificate`. Since Connector/J 8.0.13, `sslMode` has been the unified property describing TLS policy; the older properties are retained primarily for compatibility and are marked deprecated in the corresponding documentation.

When migrating configurations, do not mix legacy properties with `sslMode` in conflicting combinations. Switch to a clear `sslMode` value and remove legacy parameters after testing.

Example configuration to avoid:

```text
jdbc:mysql://db.example.com:3306/shop?useSSL=true&verifyServerCertificate=false
```

This URL enables SSL but disables server certificate verification. It does not satisfy identity authentication requirements. Replacement configuration:

```text
jdbc:mysql://db.example.com:3306/shop?sslMode=VERIFY_IDENTITY
```

If using a custom truststore, configure truststore properties separately in `Properties` or a properly URL-encoded string. Avoid concatenating passwords, tokens, or secrets into the JDBC URL because URLs often appear in logs, exceptions, metrics, or connection pool admin screens.

## 9. Verifying TLS in Applications and Operations

A connection verification checklist should include these steps:

1. Confirm the JDBC URL uses a hostname included in the certificate's SAN.
2. Confirm `sslMode=VERIFY_IDENTITY` is applied to every physical connection in the pool.
3. Confirm the truststore contains the right CA and the server sends a complete certificate chain.
4. Confirm the JDK and Connector/J support the selected TLS protocol.
5. Open a connection using the actual driver and application account.
6. Run `SHOW SESSION STATUS LIKE 'Ssl_version'` and `Ssl_cipher` on that session.
7. Test connecting with a wrong CA or mismatched hostname in a test environment; the connection must fail.
8. Verify the server rejects non-TLS connections when `require_secure_transport=ON` or the account has `REQUIRE SSL`.
9. Verify the connection pool recreates connections after updating the truststore or certificate.
10. Document certificate expiration dates, expiration alerts, and the owners responsible for rotation.

The TLS handshake normally occurs when creating a physical connection. A connection pool may reuse already-open connections, so replacing a certificate or truststore does not automatically update existing sessions. After rotating a CA/certificate, use an old/new CA overlap strategy, recycle physical connections in a controlled manner, and verify new connections.

## 10. Common Errors and Troubleshooting

| Symptom | Possible cause | Resolution |
|---|---|---|
| `PKIX path building failed` or `unable to find valid certification path` | Truststore missing root/intermediate CA, wrong truststore, or incomplete server chain. | Verify CA/fingerprint, import the right CA into the truststore, and check the chain sent by the server. |
| Hostname verification failed | Hostname in JDBC URL does not match the certificate's SAN. | Use a valid DNS name or reissue the certificate with the accurate SAN. Do not downgrade to `VERIFY_CA` just to bypass identity checks. |
| TLS handshake failure | No overlapping protocol/cipher, expired certificate, wrong key usage, or incompatible server/client config. | Check JDK, Connector/J, `tlsVersions`, `tls_version`, expiration dates, and logs on both sides. |
| Connection still works when server has no TLS | Client is using `PREFERRED` and fell back to plaintext. | Switch to `REQUIRED`, `VERIFY_CA`, or `VERIFY_IDENTITY`; enforce TLS policy on the server. |
| `REQUIRED` connects but does not verify server | This mode only requires encryption and skips CA chain and hostname checks. | Use `VERIFY_IDENTITY` and configure the truststore properly. |
| `REQUIRE X509` reports client certificate error | Client keystore missing private key/certificate, server does not trust CA, or account requires a different certificate. | Check client keystore, server CA, and account X.509 conditions. |
| Only some instances in a pool fail after cert rotation | Instances have different truststores, JDKs, DNS resolution, or physical connections. | Inventory per-instance configuration, recycle connections in a controlled way, and recheck TLS status. |

Never resolve certificate errors by disabling verification in production. Track down the root cause in the CA chain, SAN, certificate validity, truststore, DNS, or protocol settings.

## 11. Hands-On Exercise

Set up a test MySQL server with a certificate signed by a test CA. Create a Java application using Connector/J and perform the following steps:

1. Issue a server certificate with SAN `mysql-lab.example.test`; configure `ssl_cert`, `ssl_key`, and TLS protocol on MySQL.
2. Create a PKCS12 truststore containing the test CA; verify the fingerprint before importing.
3. Connect using a JDBC URL with `sslMode=VERIFY_IDENTITY` and the matching hostname.
4. Query `Ssl_version` and `Ssl_cipher` to confirm the active session uses TLS.
5. Test `sslMode=DISABLED` when the server has `require_secure_transport=ON`; confirm the connection is rejected.
6. Test `VERIFY_IDENTITY` with a hostname not present in the SAN; confirm hostname verification fails.
7. Test a truststore missing the CA or containing the wrong CA; confirm chain verification fails.
8. If possible, issue a separate client certificate, configure a client keystore, and set the account to `REQUIRE X509`; verify mTLS works.
9. Replace the server certificate in the test environment, rotate CAs in phases, and recreate physical connections in the pool.
10. Document the JDK/Connector/J configuration, `sslMode`, protocol, cipher, intentional errors triggered, and verification results.

After the exercise, learners should be able to explain why TLS encryption alone is insufficient without server verification, the difference between `VERIFY_CA` and `VERIFY_IDENTITY`, the roles of truststores and client keystores, and how to prove an actual JDBC session is using TLS. This provides a consistent, auditable foundation for securing MySQL connections from Java applications.
