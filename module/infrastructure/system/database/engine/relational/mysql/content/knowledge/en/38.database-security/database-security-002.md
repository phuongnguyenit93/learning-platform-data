# CREATE USER, ALTER USER, DROP USER and Account Lifecycle

In the `DATABASE_MYSQL` module, learners master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query optimization, privilege management, backups, and handling operational issues. This lesson focuses on a core part of security and access control: creating, modifying, locking, and revoking MySQL accounts across the lifecycle of an application or user.

The examples use MySQL 8.0 syntax. Some password policy options depend on the server version; check the actual version with `SELECT VERSION()` before applying them.

## 1. MySQL Accounts Are Identified by User and Host

In MySQL, an account is not just a login name. An account identity is a pair:

```sql
'user_name'@'host'
```

For example, the two accounts below are two distinct identities:

```sql
'orders_app'@'localhost'
'orders_app'@'10.20.5.12'
```

The first account is for connections from the local host; the second account is for connections originating from the specified IP address. Therefore, creating `orders_app`@`localhost` does not mean an application connecting from another machine will be able to log in with that account. MySQL selects an account based on the username and the connection's host information, so you must declare the actual connection source accurately.

Some guidelines when choosing a host:

- Prefer the specific hostname or IP address that the application actually uses to connect.
- Avoid creating accounts with host `%` out of habit. `%` matches many connection sources and widens the login scope beyond what is expected.
- Do not share one account across multiple applications or multiple people if you need independent tracing and privilege revocation.
- Do not create anonymous accounts or accounts with overly broad hosts to work around connection errors.

You can check the identity MySQL applied for the current session with:

```sql
SELECT
    USER() AS client_identity,
    CURRENT_USER() AS authenticated_account;
```

`USER()` shows the username and host submitted by the client; `CURRENT_USER()` shows the account MySQL actually used to authenticate the session. When troubleshooting privilege errors or connecting with the wrong account, these two values help determine whether the issue lies in the connection credentials or in the `user`/`host` configuration.

## 2. CREATE USER: Creating a New Account

`CREATE USER` creates a login identity in MySQL. This statement does not automatically grant privileges to read or write data in schemas, tables, or views. After creation, the new account cannot perform application work until an administrator grants appropriate privileges using `GRANT`.

Common syntax:

```sql
CREATE USER [IF NOT EXISTS] 'user_name'@'host'
    IDENTIFIED BY 'password'
    [REQUIRE SSL]
    [WITH MAX_USER_CONNECTIONS connection_limit];
```

Example of creating an account for an order-processing service, allowing connections only from the application server at IP `10.20.5.12`, requiring TLS, and limiting concurrent connections:

```sql
CREATE USER 'orders_app'@'10.20.5.12'
    IDENTIFIED BY 'REPLACE_WITH_SECRET_FROM_VAULT'
    REQUIRE SSL
    WITH MAX_USER_CONNECTIONS 20;
```

The password string in the example is a placeholder, not a real password. In deployment environments, retrieve secrets from a secret manager or controlled vault, restrict who can read them, and avoid writing real passwords into source code, logs, tickets, or shared command history. `REQUIRE SSL` forces the account's connections to use TLS; client configuration and server certificates must also be compatible for connections to succeed.

After creating the account, grant only the privileges required for its job. For example, if the service only needs to operate on the `shop.orders` table:

```sql
GRANT SELECT, INSERT, UPDATE, DELETE
ON shop.orders
TO 'orders_app'@'10.20.5.12';
```

Do not grant `ALL PRIVILEGES` or administrative privileges just to get an application working. Start with least privilege, then add privileges when there is a reviewed business requirement. You can inspect granted privileges with:

```sql
SHOW GRANTS FOR 'orders_app'@'10.20.5.12';
```

### What Does `IF NOT EXISTS` Mean?

```sql
CREATE USER IF NOT EXISTS 'orders_app'@'10.20.5.12'
    IDENTIFIED BY 'REPLACE_WITH_SECRET_FROM_VAULT';
```

If the account already exists, `IF NOT EXISTS` prevents the statement from failing with a duplicate-account error; MySQL issues a warning and preserves the existing configuration. This option does not synchronize the password, authentication plugin, lock state, or policies of the existing account. Therefore, it should not be used in place of verifying the configuration or running `ALTER USER`.

### Authentication Plugins and Passwords

MySQL supports multiple authentication plugins. In modern MySQL 8.0 releases, `caching_sha2_password` is the common default plugin. When specifying the plugin explicitly, the syntax looks like:

```sql
CREATE USER 'report_reader'@'10.20.5.25'
    IDENTIFIED WITH caching_sha2_password
    BY 'REPLACE_WITH_SECRET_FROM_VAULT';
```

Only choose a plugin supported by both the server and the client. `mysql_native_password` was deprecated in MySQL 8.0.34 and disabled by default in MySQL 8.4; do not downgrade authentication just to avoid upgrading a client. Check the documentation for your exact MySQL version and driver compatibility before changing plugins.

## 3. ALTER USER: Modifying an Existing Account

`ALTER USER` modifies properties of an existing account. Common use cases include changing passwords, setting password expiration, requiring TLS, setting resource limits, and locking or unlocking an account.

### Changing a Password

```sql
ALTER USER 'orders_app'@'10.20.5.12'
    IDENTIFIED BY 'NEW_PASSWORD_FROM_VAULT';
```

When rotating secrets, update both the secret store and the application configuration in sync according to your deployment workflow. If the password is changed on the server while the application still uses the old password, new connections will fail. In multi-instance systems, determine the update order to avoid downtime.

### Setting a Password Expiration Policy

```sql
ALTER USER 'orders_app'@'10.20.5.12'
    PASSWORD EXPIRE INTERVAL 90 DAY;
```

Common options:

| Option | Meaning |
|---|---|
| `PASSWORD EXPIRE` | Marks the password as expired immediately. |
| `PASSWORD EXPIRE INTERVAL 90 DAY` | Sets the password to expire after the specified number of days. |
| `PASSWORD EXPIRE DEFAULT` | Applies the server's default password expiration policy. |
| `PASSWORD EXPIRE NEVER` | Never automatically expires the password for this account. |

Expiration policies should align with how the application manages secrets. A service account without an automated password rotation mechanism can cause an outage if its password expires unexpectedly. Coordinate expiration periods, secret rotation workflows, and deployment schedules; do not set `NEVER` by default without compensating controls.

### Locking and Unlocking an Account

When login access needs to be temporarily suspended, you can lock the account:

```sql
ALTER USER 'orders_app'@'10.20.5.12' ACCOUNT LOCK;
```

Once the root cause is resolved and operations are cleared to resume:

```sql
ALTER USER 'orders_app'@'10.20.5.12' ACCOUNT UNLOCK;
```

Locking an account blocks new logins. It does not automatically terminate already-connected sessions, so during incident response or emergency privilege revocation, administrators must inspect and handle active sessions separately according to operational procedures. Unlocking only restores the ability to log in; previously granted privileges remain in effect.

### Connection Limits and Applying Password Policies

Connection limits can be adjusted after the account is created:

```sql
ALTER USER 'orders_app'@'10.20.5.12'
    WITH MAX_USER_CONNECTIONS 20;
```

On MySQL 8.0.19 and later, you can also configure password history and account locking after failed login attempts:

```sql
ALTER USER 'orders_app'@'10.20.5.12'
    PASSWORD HISTORY 5
    PASSWORD REUSE INTERVAL 365 DAY
    FAILED_LOGIN_ATTEMPTS 5
    PASSWORD_LOCK_TIME 1;
```

In this example, MySQL stores a policy preventing reuse of the last five passwords, preventing password reuse for 365 days, locking the account after five consecutive failed login attempts, and keeping it locked for one day. Actual values should be based on information security policy, application support, and server version. On versions older than 8.0.19, failed-login tracking options may not be supported.

## 4. DROP USER: Removing an Account

When a user leaves, a service is decommissioned, or an account no longer has a valid purpose, an administrator can remove the account:

```sql
DROP USER 'orders_app'@'10.20.5.12';
```

To run safely in automation scripts where the account may have already been removed earlier, use `IF EXISTS`:

```sql
DROP USER IF EXISTS 'orders_app'@'10.20.5.12';
```

`DROP USER` removes the MySQL account along with the privileges attached to it. The statement does not delete schemas, tables, or data rows that the account created or modified. Removing an account should also not be treated as a way to terminate open connections; inspect and handle existing sessions separately. Before dropping a shared or service account, confirm that no applications, scheduled jobs, or operational processes still depend on it.

If you need a temporary pause for investigation or pending approval, `ACCOUNT LOCK` is usually preferable to immediate deletion because it can be unlocked again. Once you confirm the account is no longer needed, revoke its privileges and drop the account following change management procedures.

## 5. Account Lifecycle Management Workflow

A practical workflow can be implemented with the following steps:

1. **Identify owner and purpose.** Record the application or individual using the account, environment, connection source, responsible owner, and next review date.
2. **Choose the exact identity.** Define the `user`/`host` pair based on the actual connection source; avoid sharing accounts across development, testing, and production environments.
3. **Create the account with secure settings.** Use `CREATE USER`, choose an appropriate authentication plugin, require TLS where needed, and cap connections according to expected load.
4. **Grant least privilege.** Use `GRANT` on the exact schemas, tables, or operations the account requires. Account creation and privilege granting are two separate steps.
5. **Verify after changes.** Use `SHOW GRANTS` to inspect privileges; inspect the account definition with `SHOW CREATE USER` if you have the required privilege. `SHOW CREATE USER` output can contain sensitive authentication data, so do not paste it verbatim into logs or public communication channels.
6. **Maintain during active use.** Rotate passwords, review privileges, and update limits and expiration policies when business requirements change.
7. **Lock or remove.** Use `ACCOUNT LOCK` when logins must be paused temporarily; use `DROP USER` when the account has reached end-of-life and dependencies have been verified.

Example of inspecting privileges after creating an account:

```sql
SHOW GRANTS FOR 'orders_app'@'10.20.5.12';
```

Example of viewing the account definition to review the authentication plugin, TLS requirement, and lock status:

```sql
SHOW CREATE USER 'orders_app'@'10.20.5.12';
```

Restrict access to viewing this output because hashed credentials remain sensitive data in an administrative context.

## 6. Common Errors and Troubleshooting

| Symptom | Common Cause | How to Check or Resolve |
|---|---|---|
| `CREATE USER` reports the account already exists | The `user`/`host` pair was already created earlier. | Verify the exact host and use `ALTER USER` if the goal is to update settings. `IF NOT EXISTS` only suppresses the duplicate error; it does not update the account. |
| Application reports `Access denied` even though the user was created | The account's host does not match the connection source; password or plugin mismatch; account is locked; or privileges have not been granted. | Check `USER()` and `CURRENT_USER()` from the connection session, verify password/plugin, lock status, and `SHOW GRANTS`. |
| `ALTER USER` or `DROP USER` does not affect the intended account | Wrong `host` or username specified. | Specify the full `user`/`host` pair; do not rely on the username alone. |
| Account is locked, yet queries from the application are still running | Locking an account blocks new logins, not already-authenticated sessions. | Inspect existing sessions and terminate them separately per operational procedures. |
| Account can log in, yet cannot query tables | `CREATE USER` does not automatically grant privileges on data. | Grant least privilege using `GRANT` on the exact required objects. |

Do not modify the `mysql.user` system table directly to create, alter, or delete accounts. Use `CREATE USER`, `ALTER USER`, `DROP USER`, and official privilege management statements so MySQL validates syntax, updates metadata, and applies policies consistently.

These account management statements cause an implicit commit in MySQL. Therefore, do not design workflows assuming you can wrap `CREATE USER`, `ALTER USER`, or `DROP USER` inside a transaction and use `ROLLBACK` to undo them. Treat each account change as an individual administrative operation that is logged, reviewed, and executed under change control.

## 7. Hands-on Exercise

An inventory management application runs on host `10.20.5.18` and only needs to read the products table and update stock quantities in the stock table within the `warehouse` schema. Complete the following tasks in a test environment:

1. Create an `inventory_app` account bound to host `10.20.5.18`, using a password retrieved from a secret vault, requiring TLS, and limiting concurrent connections to at most 15.
2. Grant `SELECT` on `warehouse.products` and `SELECT`, `UPDATE` on `warehouse.stock`.
3. Use `SHOW GRANTS` to verify privileges; check `USER()` and `CURRENT_USER()` from an application connection.
4. Set a password expiration policy matching your environment's rules; if the server runs MySQL 8.0.19 or later, consider configuring failed-login limits.
5. Simulate a service suspension with `ACCOUNT LOCK`, verify new connections are rejected, then unlock with `ACCOUNT UNLOCK`.
6. At the end of the exercise, confirm no dependencies remain and remove the account using `DROP USER IF EXISTS`.

After completing the exercise, you should be able to explain why `inventory_app`@`localhost` does not substitute for `inventory_app`@`10.20.5.18`, why creating an account is not enough to query tables, and why locking an account differs from dropping an account. These are three decisive points for safely managing the account lifecycle in a running MySQL system.
