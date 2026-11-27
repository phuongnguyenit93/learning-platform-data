# Access Denied and Checking user@host, Plugin, TLS, and Password

The `Access denied for user ...` error when connecting to MySQL usually occurs before the application can execute any SQL statement. The cause may be an incorrect password, an account that does not match the client host, MySQL selecting a different account than expected, an incompatible authentication plugin, unmet TLS requirements, or a locked/expired account. Because many different causes produce nearly identical messages, the effective approach is to inspect connection identity, the `user@host` account, plugin, security channel, and credentials in order.

This lesson belongs to the `DATABASE_MYSQL` module and focuses on troubleshooting login errors in MySQL and remote client applications. The content connects user/privilege administration, Connector/J, TLS, and relational database operations.

After this lesson, you will be able to:

- Distinguish authentication errors from database/table authorization errors.
- Identify the actual username and host seen by MySQL.
- Find the matched `user@host` account and detect shadowed accounts.
- Check authentication plugins, lock state, and password expiration.
- Verify TLS, RSA public keys, and driver compatibility.
- Verify SQL privileges and host resolution configuration.
- Rotate passwords safely and handle blocked hosts.
- Build a repeatable investigation checklist without exposing secrets.

## 1. Distinguishing Common Connection Errors

Not every connection error is `Access denied`. Read the error code, full message, and failure stage before modifying accounts.

| Common Error | General Meaning | First Investigation Path |
|---|---|---|
| `1045` / `ER_ACCESS_DENIED_ERROR` | Server rejected account authentication or credentials | Username, host, account match, plugin, password, TLS, and account state |
| `1130` / `ER_HOST_NOT_PRIVILEGED` | Client host is not permitted to connect per account/host policy | Actual host, account Host pattern, and network configuration |
| `1129` / `ER_HOST_IS_BLOCKED` | Host blocked due to too many connection errors | Network errors, `max_connect_errors`, and host cache |
| `1251` or similar plugin error | Client does not support the required authentication protocol/plugin | MySQL client/Connector/J version and account plugin |
| `2059` / unable to load authentication plugin | Client cannot find or load the required plugin | Driver, plugin libraries, and client version |
| TLS/SSL handshake or certificate error | TLS channel cannot be established or certificate is untrusted | CA, certificate chain, hostname, TLS version, and truststore |
| Login succeeds but `SELECT` is denied | Authentication succeeded; SQL privileges are insufficient | `SHOW GRANTS`, roles, and target objects |

Exact error codes and wording vary by server, connector, and client version. Save the full error message, `SQLState`, and vendor error code for investigation; do not save only a truncated `Access denied` line.

## 2. Reading the Access Denied Message Properly

A common message looks like:

```text
ERROR 1045 (28000): Access denied for user 'shop_app'@'client.example'
(using password: YES)
```

The message typically tells you:

- The username sent by the client.
- The client host or address observed by the server during connection.
- Whether the client sent a password (`YES`/`NO`).

`using password: YES` only means the client sent password data; it does not prove the password is correct. `NO` usually indicates the application did not send a password or credential configuration was not passed to the driver.

The host in the message is an important clue, but do not automatically assume it represents the exact matched account row. MySQL performs account matching against both `Host` and `User` columns; you must inspect candidate accounts and confirm via an equivalent successful connection if possible.

## 3. Identifying Where MySQL Sees the Client Connecting From

An application may connect across multiple network layers: containers, Kubernetes pods, NAT gateways, proxies, bastions, or load balancers. The host seen by MySQL may differ from the hostname of the machine running the application.

Record:

- Hostname/IP in the JDBC URL or client command.
- Actual source IP after NAT or proxy.
- The MySQL endpoint receiving the connection: primary, replica, proxy, or another node.
- Forward/reverse DNS and `skip_name_resolve` configuration.
- Network policy, firewall, security group, and TCP port.

If you can log in with an administrative account over the same network path, run:

```sql
SELECT
    USER() AS presented_identity,
    CURRENT_USER() AS matched_account,
    @@hostname AS server_hostname,
    @@port AS server_port,
    @@skip_name_resolve AS skip_name_resolve;
```

`USER()` returns the client-presented identity and the client host recognized by the server. `CURRENT_USER()` returns the actual MySQL account used for privilege checking. The two values can differ due to account matching.

If login fails completely, you cannot run this query from the failing session itself. Instead, use error details, server logs, account metadata, and an independent admin connection from the same network to investigate.

### 3.1. NAT, Containers, and Proxies

For example, an application runs inside a container with internal address `172.18.0.5`, but MySQL only sees the gateway address `10.20.1.15` after NAT. An account restricted to host `172.18.0.5` will not match. Similarly, when traffic passes through a TCP proxy, the server may see the proxy address instead of the pod IP.

Do not fix an account by widening `Host` to `%` as soon as an error appears. First determine the actual source IP the server sees, then choose the narrowest host pattern appropriate for the topology.

### 3.2. `skip_name_resolve`

Check:

```sql
SHOW VARIABLES LIKE 'skip_name_resolve';
```

When `skip_name_resolve=ON`, MySQL does not perform DNS lookups to resolve client hostnames during account matching; account `Host` values must use IP addresses or supported forms that do not rely on DNS. The `localhost` account still retains its special meaning for local connections.

If an account is defined with a hostname while the server runs with `skip_name_resolve=ON`, the account may not match as expected. Before changing accounts, verify the variable value on the target instance and existing host patterns.

## 4. How MySQL Selects a `user@host` Account

A MySQL account has two parts: `User` and `Host`. Examples:

```sql
'shop_app'@'localhost'
'shop_app'@'10.20.1.15'
'shop_app'@'10.20.%'
'shop_app'@'%'
```

These are distinct accounts. Passwords, authentication plugins, lock states, and privileges can differ across them even though the username is identical.

MySQL sorts grant rows by `Host` specificity. More specific `Host` values are evaluated first; if an anonymous account (empty `User`) exists with a more specific `Host` than a named user account with a broader `Host`, that anonymous account can be matched first. Therefore, having `'shop_app'@'%'` does not guarantee every client passing username `shop_app` will use that account.

### 4.1. Listing Candidate Accounts

An administrator can inspect accounts matching the username as well as anonymous accounts:

```sql
SELECT
    User,
    Host,
    plugin,
    account_locked,
    password_expired
FROM mysql.user
WHERE User IN ('shop_app', '')
ORDER BY Host, User;
```

Querying `mysql.user` requires appropriate administrative privileges, and metadata columns may vary by version. Do not query or export `authentication_string` into logs/tickets; that field contains sensitive authentication data.

Check for duplicate usernames with different `Host` values, anonymous accounts, or stale legacy accounts. Compare each account against the source IP and host-matching rules.

### 4.2. Shadowed Account Example

Suppose the following exist:

```sql
CREATE USER 'shop_app'@'%' IDENTIFIED BY '<secret-a>';
CREATE USER ''@'10.20.1.15' IDENTIFIED BY '<secret-b>';
```

A client at `10.20.1.15` logs in with username `shop_app`. The anonymous account has a more specific `Host` than the named account with `%`, so MySQL may select the anonymous account for authentication. If the anonymous account's password or plugin differs, the client fails even though `'shop_app'@'%'`'s password is correct.

This example is solely to explain matching rules. Do not create anonymous accounts in production to test. If unnecessary accounts are discovered, evaluate impact and lock or drop them per governance procedures.

### 4.3. Confirming the Account After Successful Login

Once connected, run:

```sql
SELECT USER(), CURRENT_USER();
SHOW GRANTS;
```

`CURRENT_USER()` is direct proof of which account row was matched. `SHOW GRANTS` shows the privileges applied to the current account. Save non-secret output in the investigation report.

## 5. Checking the Authentication Plugin

A correct username/password can still fail if the client does not support the account's plugin or if security prerequisites for the plugin are unmet.

Common plugins:

| Plugin | Characteristics | Operational Recommendation |
|---|---|---|
| `caching_sha2_password` | Default plugin for new accounts in MySQL 8.0; supports fast/full authentication | Preferred for modern clients/drivers |
| `sha256_password` | SHA-256 based; can use TLS or RSA | Use only when explicit compatibility is required |
| `mysql_native_password` | Legacy plugin used for backward compatibility | Plan migration away; do not choose for new applications |
| Third-party plugins | Depends on matching server/client plugins | Confirm the plugin is installed, supported, and configured on both sides |

Check the account's plugin:

```sql
SELECT User, Host, plugin, account_locked
FROM mysql.user
WHERE User = 'shop_app';
```

### 5.1. `caching_sha2_password` and Client Compatibility

MySQL 8.0 uses `caching_sha2_password` as the default plugin for new accounts. Connector/J 8.0.9 and later support this plugin. If an application uses an older Connector/J, the driver may fail to complete the handshake or load the plugin.

Verify the driver actually loaded by the application at runtime, not just the dependency declared in `pom.xml` or Gradle. Multiple connector versions may exist on the classpath, or a container image may still bundle an old JAR.

For full authentication, `caching_sha2_password` requires a secure channel such as TLS or RSA public key exchange. If TLS is not enabled, the client must have a trusted way to obtain the public key.

### 5.2. Lifecycle of `mysql_native_password`

`mysql_native_password` was deprecated in MySQL 8.0.34, disabled by default in MySQL 8.4, and removed in MySQL 9.0. An application that only connects when an account uses the legacy plugin is likely relying on an outdated driver or library.

The preferred solution is upgrading Connector/J or the client library, then migrating the account to a modern plugin in a tested change window. Do not re-enable the legacy plugin on newer servers merely to mask compatibility errors without assessing risks and a migration timeline.

## 6. Checking TLS and RSA Public Keys

### 6.1. Does the Account Require SSL/TLS?

Check the account definition with:

```sql
SHOW CREATE USER 'shop_app'@'10.20.1.15';
```

This statement can expose authentication metadata, so only authorized users should run it and full output should not be pasted into tickets/logs. Look for requirements such as `REQUIRE SSL`, `REQUIRE X509`, issuer, or subject.

If the account has `REQUIRE SSL`, the client must establish TLS. If the server enables `require_secure_transport=ON`, insecure connections can be rejected at the server level even if the account does not explicitly declare `REQUIRE SSL`.

Check:

```sql
SHOW VARIABLES LIKE 'require_secure_transport';
SHOW VARIABLES LIKE 'have_ssl';
```

### 6.2. Preferring TLS with Hostname Verification

With the MySQL command-line client, for example:

```bash
mysql \
  --host=mysql.example.internal \
  --port=3306 \
  --user=shop_app \
  --password \
  --ssl-mode=VERIFY_IDENTITY \
  --ssl-ca=/etc/mysql/certs/ca.pem \
  shop
```

Depending on client/version, CA flags and TLS options may vary. `--password` with no value prompts interactively, avoiding putting passwords directly on the command line.

With modern Connector/J:

```text
jdbc:mysql://mysql.example.internal:3306/shop?sslMode=VERIFY_IDENTITY
```

The client must trust the CA that issued the server certificate, and the hostname in the URL must match the certificate's SAN. `sslMode=REQUIRED` only enforces TLS encryption; `VERIFY_IDENTITY` verifies both the CA and the hostname identity.

### 6.3. Confirming TLS on a Connected Session

```sql
SHOW SESSION STATUS LIKE 'Ssl_cipher';
SHOW SESSION STATUS LIKE 'Ssl_version';
```

A non-empty `Ssl_cipher` indicates the session is using a TLS cipher. However, this query does not prove the client enabled hostname verification; you must verify client configuration and certificate validation results.

### 6.4. RSA When Not Using TLS

If using `caching_sha2_password` or `sha256_password` during full authentication without TLS, the client needs the RSA public key to encrypt the password. With Connector/J, you can specify the public key file:

```text
jdbc:mysql://mysql.example.internal:3306/shop?sslMode=DISABLED&serverRSAPublicKeyFile=/etc/shop-app/mysql/server-rsa-public.pem
```

This is an illustrative configuration for controlled environments; disabling TLS on untrusted networks is not recommended. The public key must be distributed over an authenticated channel and verified for integrity. Never share the server's private key.

`allowPublicKeyRetrieval=true` allows the driver to request the public key from the server. If the connection is unprotected and unauthenticated, the key could be replaced by a man-in-the-middle attacker. Do not enable this property as a quick fix for `Public Key Retrieval is not allowed`; prefer TLS `VERIFY_IDENTITY` or a verified public key file.

## 7. Checking Passwords, Account Status, and Authentication Policy

After confirming the right account row and plugin, check the password and account status.

Common causes:

- Application uses an old secret after password rotation.
- Secret contains special characters that were truncated, escaped, or decoded improperly across YAML, environment variables, or the JDBC URL.
- Secret manager returned credentials for a different environment.
- Account is locked or password has expired.
- Account was recreated with a different `Host` than the one the application matches.
- Some pods/instances still hold stale configuration or old connection pools.

Check account status:

```sql
SELECT
    User,
    Host,
    plugin,
    account_locked,
    password_expired
FROM mysql.user
WHERE User = 'shop_app';
```

Do not read or print password hashes. If a reset is needed, use `ALTER USER` on the exact account row after confirming the host:

```sql
ALTER USER 'shop_app'@'10.20.1.15'
    IDENTIFIED WITH caching_sha2_password BY '<new-secret-from-secret-manager>';
```

`<new-secret-from-secret-manager>` is a placeholder, not a real password. Do not commit commands containing secrets to repositories or shell history. After resetting, update the secret manager and recycle pools so new connections use the new credentials.

### 7.1. Locked Accounts or Expired Passwords

If an account is locked, investigate why before unlocking it. Only after confirming the account should be active and credentials are properly managed should you run:

```sql
ALTER USER 'shop_app'@'10.20.1.15' ACCOUNT UNLOCK;
```

If the password has expired, rotate the password per organizational policy. Do not disable server-wide expiration policies just to let a legacy application connect.

### 7.2. Special Characters in Passwords

Passwords containing `&`, `?`, `#`, `%`, `@`, quotes, or slashes can be misinterpreted if concatenated directly into a JDBC URL. Pass username/password via `Properties`, `DataSource`, or a secret provider instead of embedding the password in the URL.

Example:

```java
Properties properties = new Properties();
properties.setProperty("user", secretProvider.get("shop-db-user"));
properties.setProperty("password", secretProvider.get("shop-db-password"));

Connection connection = DriverManager.getConnection(
    "jdbc:mysql://mysql.example.internal:3306/shop?sslMode=VERIFY_IDENTITY",
    properties
);
```

`secretProvider` is an illustrative component representing a secret manager. Do not log `Properties`, the JDBC URL, or exception context containing secrets.

## 8. Checking Privileges After Successful Authentication

If login succeeds but statements return `SELECT command denied`, `INSERT command denied`, or other privilege errors, the problem lies in authorization rather than authentication.

Check:

```sql
SELECT USER(), CURRENT_USER();
SHOW GRANTS;
```

Or for a specific account:

```sql
SHOW GRANTS FOR 'shop_app'@'10.20.1.15';
```

Inspect assigned roles and which roles are active in the session if the system uses MySQL roles. Do not grant `ALL PRIVILEGES` or `GRANT OPTION` as a default workaround.

Example least-privilege grant for a service needing read and write access to one schema:

```sql
GRANT SELECT, INSERT, UPDATE, DELETE
ON shop.* TO 'shop_app'@'10.20.1.15';
```

Required privileges depend on business needs. A reporting service may only need `SELECT`; a migration service needs dedicated DDL privileges and should not share the application's runtime account.

## 9. Blocked Hosts and the Host Cache

If too many connection errors originate from an address, MySQL may block the host and return error `1129` (`Host ... is blocked because of many connection errors`). This differs from `1045` caused by passwords or account matching.

Check the variable:

```sql
SHOW VARIABLES LIKE 'max_connect_errors';
```

If authorized, inspect the host cache:

```sql
SELECT *
FROM performance_schema.host_cache
WHERE IP = '10.20.1.15'\G
```

The host cache can hold counts for name resolution, handshake, authentication, TLS, and connection errors. Columns may vary by MySQL version. Do not export sensitive client information beyond what is necessary.

Before clearing or resetting the host cache, fix the root cause—such as wrong passwords retried continuously, TLS handshake failures, or clients sending invalid handshakes. If you only flush the cache without fixing the application, the host may be blocked again immediately. Clearing the host cache requires administrative privileges and must follow the documentation for the running version.

## 10. Ordered Access Denied Investigation Procedure

Follow this flow to avoid prematurely resetting passwords or over-granting privileges:

1. **Collect the error:** record the full error code, `SQLState`, message, timestamp, endpoint, and client/driver version.
2. **Verify endpoint:** ensure the application is connecting to the intended MySQL instance, proxy, or replica.
3. **Identify client host:** check source IP after NAT/proxy and the `skip_name_resolve` setting.
4. **Check account matching:** list `User`/`Host` rows, anonymous accounts, and more specific host patterns.
5. **Check plugin:** identify the exact account row's plugin and client/Connector/J support.
6. **Check TLS/RSA:** check whether the account requires `SSL/X509`, whether the server enforces secure transport, and whether the client has matching CA/hostname or a trusted RSA key.
7. **Check credentials:** verify secret version, password expiration, account lock, and password passing configuration.
8. **Check privileges:** after successful login, verify `CURRENT_USER()` and `SHOW GRANTS`.
9. **Check host cache:** only when the error is host blocked or shows repeated handshake failures.
10. **Retest over the exact network path:** use a compatible client and the same endpoint/host to confirm.
11. **Update runbook:** record the matched account row, plugin, TLS mode, changes, and verification results without storing secrets.

Do not change multiple variables at once. Changing plugin, password, host pattern, and TLS simultaneously makes it hard to determine which change fixed the issue and can leave unintended accounts behind.

## 11. Symptom and Remediation Matrix

| Symptom | Possible Cause | Evidence to Check | Appropriate Action |
|---|---|---|---|
| Password is correct but still `1045` | MySQL matched a different `Host` account | `mysql.user` rows, host in error, anonymous accounts | Fix account matching and revoke redundant accounts after review |
| Only containers/pods fail | Source IP after NAT differs from expected | Client IP seen by server, network path | Update to an appropriate narrow host pattern or fix network path |
| Local machine connects, remote fails | `localhost` account differs from remote account; firewall or TLS | `User`/`Host`, IP, port, and server log | Create/configure proper remote account and check network |
| `using password: NO` | Password not transmitted | Secret injection, `DataSource` properties | Fix credential config and avoid concatenating password into URL |
| `caching_sha2_password` unsupported | Connector/J or client too old | Actual driver loaded at runtime | Upgrade driver and test |
| `Public Key Retrieval is not allowed` | Full auth without TLS and missing RSA key | TLS mode, plugin, public key config | Use verified TLS or a trusted public key file |
| SSL handshake failed | Wrong CA, certificate chain, or hostname | Truststore, SAN, certificate validity period | Update CA/certificates and use matching hostname |
| Account locked | Policy or admin action | `account_locked`, audit/change log | Verify cause, then unlock in a controlled manner |
| Password expired | Password policy | `password_expired`, client message | Rotate password per policy and update secret |
| Login succeeds, queries denied | Missing privileges or inactive role | `CURRENT_USER()`, `SHOW GRANTS` | Grant least-privilege permissions to the right account |
| `1129` host blocked | Repeated handshake/connection errors | `host_cache`, `max_connect_errors`, logs | Fix root cause, then handle host cache per version |

## 12. Rotating Passwords Without Downtime

Changing a password directly on an active account can break new pool connections if the application still holds the old secret. On MySQL versions supporting dual passwords, you can retain the old password during transition:

```sql
ALTER USER 'shop_app'@'10.20.1.15'
    IDENTIFIED BY '<new-secret>' RETAIN CURRENT PASSWORD;
```

Once the application has picked up the new secret and pools have been recycled:

```sql
ALTER USER 'shop_app'@'10.20.1.15'
    DISCARD OLD PASSWORD;
```

Dual-password support depends on version and plugin. If unsupported, create a new account with equivalent privileges, switch the application to the new account, and lock/revoke the old account after confirming no connections still use it.

Safe procedure:

1. Identify the exact `user@host` account and the services using it.
2. Create the new credential in the secret manager.
3. Update the account or create a new account per the supported strategy.
4. Update application secrets and perform a rolling restart / recycle connection pools.
5. Verify new connections, `CURRENT_USER()`, and query privileges.
6. Confirm no instances remain on the old password.
7. Discard the old password or revoke the old account.
8. Record timestamp, operator, and result without storing secret values.

## 13. Security During Incident Handling

- Never ask users to send passwords via chat, tickets, or logs.
- Never include `authentication_string`, passwords, tokens, private keys, or truststore passwords in reports.
- Never grant `ALL PRIVILEGES`, `CONNECTION_ADMIN`, or broad admin privileges just to resolve a login error.
- Never widen `Host` to `%` or disable TLS as a quick fix.
- Never re-enable legacy authentication plugins without risk assessment and a replacement deadline.
- Never use the `root` account in applications.
- Restrict access to inspect `mysql.user`, `SHOW CREATE USER`, server logs, and the host cache.
- Reset passwords or unlock accounts only after confirming the exact account row and service owner.

A good investigation report records username, matched `Host` row, plugin, TLS mode, client version, error code, and changes made—never passwords or hashes.

## 14. Practice Scenario

A Spring Boot application running in Kubernetes cannot connect to MySQL after migrating to a new cluster. Logs show `Access denied for user 'shop_app'@'10.20.1.15' (using password: YES)`. Operations confirms the password in the secret manager is still correct.

Practice in a lab environment:

1. Confirm the hostname/port the pod connects to and the source IP the server sees.
2. Check `skip_name_resolve` and list `shop_app` accounts plus any anonymous accounts that could match.
3. Compare `plugin`, `account_locked`, and `password_expired` across each account row.
4. Check the actual Connector/J version inside the container image and confirm `caching_sha2_password` support.
5. Check whether the account has `REQUIRE SSL` and whether the server sets `require_secure_transport`.
6. Configure TLS `VERIFY_IDENTITY`, trust the CA, and match the SAN hostname; verify connection succeeds.
7. Use `USER()` and `CURRENT_USER()` to prove the actual matched account row after login.
8. Use `SHOW GRANTS` to verify privileges and test both an allowed operation and a denied operation.
9. Practice rotating the password in the lab, updating the secret, and recycling the pool.
10. Write a report covering root cause, evidence, changes, and recurrence prevention without storing secrets.

**Self-assessment questions:**

- Why does `using password: YES` not prove the password is correct?
- How do `USER()` and `CURRENT_USER()` differ?
- Why can an anonymous account with a specific `Host` affect account selection?
- How does `skip_name_resolve=ON` affect using hostnames in account `Host` values?
- Why might `caching_sha2_password` require TLS or an RSA public key during full authentication?
- How does `sslMode=REQUIRED` differ from `VERIFY_IDENTITY`?
- When should you investigate the host cache and `max_connect_errors` instead of resetting a password?
- Why is a `SELECT` permission error after successful login not an authentication error?
- How do you rotate a password without breaking the entire connection pool?

## Conclusion

`Access denied` errors must be investigated starting from client identity and the `user@host` account before changing passwords or privileges. Identify the exact account row, verify plugin and driver compatibility, confirm TLS/RSA and account status, and only then check SQL privileges. For modern applications, prefer `caching_sha2_password`, TLS `VERIFY_IDENTITY`, restricted account `Host` patterns, and a secret manager. Document evidence and changes, and never put passwords or private keys into logs.
