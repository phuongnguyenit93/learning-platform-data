# Authentication Plugins, `caching_sha2_password`, and Driver Compatibility

## Objectives

After this lesson, you will be able to:

- Explain the role of authentication plugins in MySQL and distinguish authentication from authorization.
- Describe the fast authentication and full authentication paths of `caching_sha2_password`.
- Check the plugin assigned to an account, migrate an account to an appropriate plugin, and verify connections securely.
- Diagnose compatibility errors across MySQL Server, drivers, applications, and proxies.
- Plan driver upgrades and plugin transitions without unexpected service disruption.

## 1. What Problem Do Authentication Plugins Solve?

When an application opens a connection to MySQL, the server must verify the account's identity before allowing a session to be established. MySQL delegates this verification to an **authentication plugin**. The plugin defines how the client proves that it knows the account's credentials, such as a password.

An authentication plugin does not decide which tables an account can read or modify. That is the job of the privilege system (`GRANT`, `REVOKE`, roles). A connection can authenticate successfully and still receive an `Access denied` error when accessing data due to missing privileges; conversely, an account with sufficient privileges cannot be used if authentication fails.

MySQL identifies accounts by a `user` and `host` pair, such as `'app_user'@'10.%'`. The plugin is attached to each individual account. Therefore, the same username at two different `host` values can have different authentication configurations.

Some common plugins:

| Plugin | Characteristics | Usage |
|---|---|---|
| `caching_sha2_password` | SHA-256–based plugin with a cached fast-authentication path and a full-authentication path when needed | Recommended default on modern MySQL versions |
| `mysql_native_password` | Legacy authentication mechanism based on MySQL's SHA-1 hashing | Keep only temporarily while legacy dependencies remain, with a plan to retire it |
| `sha256_password` | SHA-256 authentication without the fast-authentication cache of `caching_sha2_password` | Use only when specific compatibility requires it |
| `auth_socket` | Authenticates based on the OS user identity over a local socket | Suitable for certain local admin accounts on Linux; not a general choice for remote applications |

Since MySQL 8.0, `caching_sha2_password` is the default authentication plugin for new accounts when no other plugin is specified. `mysql_native_password` was deprecated in MySQL 8.0.34, disabled by default in MySQL 8.4, and removed in MySQL 9.0. Consequently, an older driver might still connect to an older server yet fail after a server upgrade or an account plugin change.

## 2. How `caching_sha2_password` Works

The plugin name describes two main ideas: SHA-256–based authentication and a cache that shortens subsequent authentication attempts. This cache is not the query cache and does not store plaintext passwords.

### 2.1. Handshake Exchange

When a client connects, MySQL sends the plugin information and random challenge data (challenge/nonce). The driver must understand the plugin's protocol to produce the right authentication response. If the driver does not support the plugin requested by the server, the handshake can stop before the application ever sends a SQL query.

`caching_sha2_password` has two paths:

1. **Fast authentication:** if the required credential state is already in the server's cache, the client sends a challenge-based response. The server verifies the response and completes authentication without performing a full password exchange.
2. **Full authentication:** if the cache does not yet hold matching state—such as the first time an account connects after the cache is cleared—both sides switch to the full authentication step. This step requires a secure transport channel or RSA encryption.

The cache lives in server memory. It can be cleared when the server restarts or when the account's credentials change. Thus, a driver that only worked when the cache was already populated can still fail on the first connection after a deployment or server restart.

### 2.2. Full Authentication over TLS or RSA

During full authentication, the client must transmit the password to the server in a protected manner:

- **Over TLS:** the password is sent inside a TLS connection. This is the recommended option for applications connecting over a network. Configure the client to verify the server certificate and hostname, such as `VERIFY_IDENTITY` mode in the MySQL client or Connector/J.
- **Over RSA without TLS:** the client uses the server's RSA public key to encrypt the password before sending it. The public key can be preconfigured on the client or retrieved from the server via a driver mechanism.

Automatically fetching the public key over an unauthenticated connection can expose the client to rogue servers or man-in-the-middle attacks. In production, prefer TLS with certificate verification. If RSA without TLS is unavoidable, distribute and pin a trusted public key according to the driver's documentation.

`caching_sha2_password` does not mean the server sends a hashed password for the application to compare itself. Both client and server must properly implement the challenge-response protocol, fast authentication path, and full authentication path. Therefore, changing a single connection string parameter cannot turn a driver lacking plugin support into a compatible one.

## 3. Inspecting Plugins and Accounts on the Server

Before changing configuration, determine the server version and the plugin currently attached to application accounts. Run these checks using an administrative account with privileges to view system metadata.

```sql
SELECT VERSION() AS mysql_version;

SELECT user, host, plugin, account_locked
FROM mysql.user
ORDER BY user, host;
```

On MySQL 8.x, `mysql.user` is a view of account information in the privilege system. If you prefer not to query that view directly or only need to check one account, you can use:

```sql
SHOW CREATE USER 'app_user'@'10.%';
```

The `SHOW CREATE USER` statement can display hashed authentication credentials and account attributes. Do not paste the raw output into public tickets, application logs, or shared documents; mask the credential portion before sharing it with others.

Do not inspect only interactive login accounts. Inventory all accounts used by APIs, background workers, scheduled jobs, migration tools, backup tools, monitoring, BI, and middleware services. A single system may have multiple connection paths using different drivers or libraries.

## 4. Creating and Migrating Accounts to `caching_sha2_password`

### 4.1. Creating a New Account

Example of creating an application account with privileges limited to the `sales_app` schema:

```sql
CREATE USER 'sales_app'@'10.%'
  IDENTIFIED WITH caching_sha2_password BY 'REPLACE_WITH_A_UNIQUE_SECRET'
  REQUIRE SSL;

GRANT SELECT, INSERT, UPDATE, DELETE
  ON sales_app.*
  TO 'sales_app'@'10.%';
```

Replace the placeholder string with a strong password issued from your secret management system. Do not use the placeholder string verbatim in real environments. The host scope `10.%` is only an example; restrict the host or network range according to your actual architecture. `REQUIRE SSL` requires the account to connect over TLS, while server certificate verification must still be configured on the client side.

### 4.2. Migrating an Existing Account

Once you have confirmed every application using the account has a compatible driver, you can switch the plugin with `ALTER USER`:

```sql
ALTER USER 'legacy_app'@'10.%'
  IDENTIFIED WITH caching_sha2_password BY 'REPLACE_WITH_A_NEW_SECRET'
  REQUIRE SSL;
```

This statement changes the authentication method and resets the password to the new value. Update the corresponding secret in your secret manager or application configuration store according to your deployment workflow. If the account is shared across multiple services, identify all consumers before making the change.

The `CREATE USER` and `ALTER USER` statements update privilege tables directly; you do not need to run `FLUSH PRIVILEGES` afterward. The plugin change takes effect for new connection authentications. Previously established sessions generally persist until closed, so actively open a new connection to verify the configuration.

### 4.3. Checking Privileges Separately from Authentication

After creating or migrating an account, inspect the granted privileges:

```sql
SHOW GRANTS FOR 'sales_app'@'10.%';
```

If a connection succeeds but queries are denied, inspect privileges and roles before changing the plugin. Do not resolve authorization errors by granting `GRANT ALL` or switching the application to an administrative account.

## 5. Compatibility of Drivers and Connection Components

Compatibility must be verified along the entire connection path, not just on the MySQL Server. Components involved can include client libraries, language drivers, ORMs, connection pools, proxies, and operational tools.

| Component | What to Check |
|---|---|
| MySQL command-line client | Use a client version recent enough to support the server's plugin; verify TLS options and full authentication |
| MySQL Connector/J | Use a version supporting `caching_sha2_password`; configure the trust store/CA and hostname verification when using TLS |
| MySQL Connector/Python | Update to a connector compatible with the server version; enable certificate and server identity verification |
| PHP `mysqli` / PDO MySQL | Determine whether PHP uses `mysqlnd` or `libmysqlclient`, the library version built with PHP, and its plugin support |
| Node.js driver | Check the package version and authentication protocol support; verify pool TLS settings as well |
| Go driver, ORMs, and frameworks | Check the underlying MySQL driver the framework actually uses; an ORM does not add plugin support if the driver lacks it |
| Proxy or connection management service | Confirm the proxy supports forwarding the full authentication flow and does not alter the authentication method between client and server |

Do not infer compatibility solely from the programming language or ORM name. Two Java applications can use two different Connector/J versions; a PHP application can be built against different client libraries. Record the actual versions running in your environment.

For MySQL Connector/J, an example connection URL enabling TLS and server identity verification:

```text
jdbc:mysql://db.example.internal:3306/sales_app?sslMode=VERIFY_IDENTITY
```

The application host must trust the CA that signed the server certificate (via an appropriate trust store), and the certificate's subject/SAN must match the hostname `db.example.internal`. If using an internal certificate, install the internal CA into the trust store rather than disabling certificate verification.

With the MySQL command-line client, you can test the connection using:

```bash
mysql --host=db.example.internal \
      --user=sales_app \
      --password \
      --ssl-mode=VERIFY_IDENTITY \
      --ssl-ca=/path/to/company-ca.pem \
      sales_app
```

Passing `--password` without a value prompts the client interactively, avoiding putting the password directly into shell history or process lists. Replace the CA path and hostname in the example with your real configuration.

After connecting, verify whether the current session uses TLS:

```sql
SHOW SESSION STATUS LIKE 'Ssl_cipher';
```

A non-empty `Ssl_cipher` value indicates the session is using TLS encryption. This confirms transport encryption; verifying the server's identity still depends on client-side configuration.

## 6. Pre-Deployment Testing Procedure

A test that only runs `SELECT 1` is not enough to confirm compatibility. Test all connection paths and full-authentication scenarios.

1. **Inventory:** record the MySQL Server version, each account's plugin, and the actual driver version of every application, job, tool, and proxy.
2. **Upgrade drivers in a test environment:** update libraries before switching account plugins. Test with the exact runtime version, TLS configuration, connection pool, and proxy used in production.
3. **Test cold connections:** use a brand-new test account or a test account whose password was just changed to test the first authentication when the cache does not yet hold matching state. Do not test only connections reused from a pool.
4. **Test connection lifecycle:** close and reopen the pool, restart the test application, and confirm new connections still succeed. If operational procedures involve restarting MySQL, test the cache-cleared scenario in staging.
5. **Functional testing:** run migrations, representative read/write queries, transactions, background jobs, test backups/restores, and health checks. Confirm no component silently falls back to an old driver.
6. **Security checks:** confirm TLS is used, the client validates certificates, and the account has only the required least privilege.
7. **Phased rollout:** migrate one group of accounts or services at a time, monitoring authentication failures and new-connection establishment before moving to the next group.

Maintain separate test accounts for each driver or application type. Sharing a single test account can mask differences in host matching, TLS configuration, or access privileges.

## 7. Diagnosing Common Errors

| Message or Symptom | Possible Cause | How to Handle |
|---|---|---|
| `Authentication plugin 'caching_sha2_password' cannot be loaded` | Client is too old, missing the client-side plugin, or loading an incompatible library | Identify the exact client library loaded by the application; upgrade the driver/client to a version supporting the plugin |
| `Client does not support authentication protocol requested by server` | Driver or proxy does not understand the plugin requested by the server | Check driver and proxy versions; test a direct connection to MySQL with a recent client to isolate the issue |
| `Public Key Retrieval is not allowed` | Driver lacks a configured RSA key and disallows automatic public key retrieval | Prefer enabling TLS with certificate verification; if TLS cannot be used, configure a trusted public key per driver docs |
| `Authentication requires secure connection` or similar error | Full authentication is required, but the connection lacks TLS and the client has not configured RSA properly | Enable TLS, or configure secure RSA key exchange for both client and server |
| Existing connections work, but new connections fail | Application is still holding old sessions; full-authentication path was untested; pool hides errors | Open a new connection with a test account, test after the cache is cleared, and inspect driver logs |
| `Access denied for user` | Wrong password, mismatched `user`/`host` pair, locked account, or incomplete authentication flow | Verify exact matched user and host, account status, plugin, and client settings; only then check SQL privileges |
| Connects successfully, yet queries receive `command denied` or `SELECT command denied` | Authentication succeeded, but privileges are missing | Use `SHOW GRANTS` and grant the right privileges on the right schema/tables; do not change the plugin to fix privilege errors |
| Only some application instances fail | Instances run different runtimes, drivers, secrets, or TLS configurations | Compare deployed versions and settings across instances; inspect connection pool config and environment variables |

A helpful diagnostic clue is when failures only appear when opening new connections after a restart or password change. That pattern typically points to the full-authentication path, TLS, or RSA. Use both client and server logs to confirm rather than concluding from timing alone.

## 8. Migration Path from Legacy Plugins

When a system still uses `mysql_native_password`, treat the transition as a multi-component compatibility change:

**Phase 1 — Dependency inventory.** List accounts, hosts, consuming services, driver versions, proxies, and secret distribution methods. Pay special attention to infrequently run applications such as monthly jobs, backup tasks, and administrative tools.

**Phase 2 — Client upgrades.** Update drivers and runtimes in test environments. Configure TLS, CAs, and hostname verification. Emit compatibility errors into logs or metrics so they are visible during rollout.

**Phase 3 — Testing with new accounts.** Create accounts using `caching_sha2_password`, least privilege, and TLS requirements. Run full application flows with these accounts, including fresh connections after pool recreation.

**Phase 4 — Service-by-service cutover.** Update secrets and accounts in small batches. Monitor failed connection counts, authentication errors, connection establishment latency, and proxy errors. Have a controlled rollback plan ready if a component proves incompatible.

**Phase 5 — Removing legacy dependencies.** Once all clients are verified, migrate any remaining accounts, remove any server settings allowing the legacy plugin, and update operational runbooks. Do not retain a shared over-privileged account just to preserve compatibility for one un-upgraded client.

Do not re-enable `mysql_native_password` server-wide just to keep one legacy application running. First identify the exact offending client and upgrade it. If a transition period is unavoidable, restrict the account scope, network scope, and lifetime, and record an owner along with an upgrade deadline. In MySQL 8.4, this plugin is disabled by default; in MySQL 9.0, the plugin is removed so re-enabling it is no longer an option.

## 9. Operational Security Principles

- **Require TLS for network connections:** prefer client-side CA and hostname verification. Encryption without verifying server identity may still leave the application vulnerable to rogue servers.
- **Do not treat `allowPublicKeyRetrieval=true` as a default production fix:** this option helps some drivers retrieve an RSA key without TLS, but key-trust risks must be assessed. Prefer TLS or reliably distributed public keys.
- **Manage passwords outside source code:** use a secret manager, restrict who can read secrets, and enforce rotation procedures. Do not place passwords in connection URLs, logs, shell history, or code repositories.
- **Restrict privileges and connection sources:** use separate accounts per application or role, restrict hosts, grant least privilege, and lock unused accounts.
- **Monitor new-connection establishment:** connection pools can mask authentication failures for long periods. Health checks should exercise creating new connections and alert on authentication errors.
- **Protect diagnostic output:** `SHOW CREATE USER` output, handshake logs, and connection configs can contain sensitive details. Redact sensitive data before sharing.

## 10. Hands-on Scenario

A sales service runs on MySQL 8.0. The main application is working, but after spinning up a new instance, that instance reports `Public Key Retrieval is not allowed`. The `sales_app` account has already been migrated to `caching_sha2_password`. A backup job running on another host still uses an older client.

Handle the situation in order:

1. On MySQL, verify the server version and the plugins for the exact `sales_app` account and the backup account. Check the `user`/`host` pairs, because the two services may match different accounts.
2. On the new instance, record the actual driver version and TLS configuration. Do not rush to set `allowPublicKeyRetrieval=true` to bypass the error.
3. Configure the trusted CA and hostname verification, then open a new connection. If the architecture cannot yet use TLS, evaluate distributing a trusted RSA public key per the driver's documentation.
4. Upgrade the backup job's client in a test environment; run test backups and restores to validate the entire flow.
5. Complete the cutover only after all clients pass cold-connection, functional, and security testing.

**Self-check questions:**

1. Why might an application connect successfully before a MySQL restart yet fail when opening new connections after the restart?
2. Under what circumstances does `caching_sha2_password` use TLS and RSA? Why is certificate verification important?
3. When a connection succeeds but queries are denied, should you check the plugin or `SHOW GRANTS` first? Explain.
4. Besides the main application, what other clients should be tested before migrating an account to the new plugin?
5. Why should you avoid enabling `mysql_native_password` server-wide just to support one legacy driver?

## Conclusion

`caching_sha2_password` is the right authentication choice for modern MySQL versions. For reliable operation, the server, drivers, and intermediate components must all support the protocol; the full-authentication path requires TLS or trusted RSA configuration. Inventory every client, test new connections in staging, migrate accounts in batches, and re-verify both SQL privileges and transport security after deployment.
