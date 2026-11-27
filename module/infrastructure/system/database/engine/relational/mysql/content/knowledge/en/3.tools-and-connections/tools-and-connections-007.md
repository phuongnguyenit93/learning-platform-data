# user@host Accounts and How MySQL Chooses the Matching Account

This lesson belongs to the **Tools and Connections** chapter of the `DATABASE_MYSQL` module. The module aims to build mastery of MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query tuning, privilege management, backups, and handling relational database operational issues. Among these topics, MySQL accounts are the first control layer: a client must authenticate with an account allowed to connect from its origin before privileges to read or modify data are evaluated.

After this lesson, you will be able to read and create accounts in `'user'@'host'` format, distinguish accounts that share the same username but differ in client host, explain how MySQL picks a row when multiple accounts match, and diagnose wrong-account login scenarios.

## 1. A MySQL Account Has Two Parts

MySQL does not identify an account by username alone. An account is identified by a **username** and the **host or source address from which the user connects**:

```sql
'user_name'@'host_name'
```

Examples:

- `'app'@'localhost'`: the `app` account for local connections.
- `'app'@'192.0.2.15'`: the `app` account for a machine with the specified IP address.
- `'app'@'db-client.example.com'`: the `app` account for the machine with the corresponding hostname.
- `'app'@'192.0.2.0/24'`: the `app` account for addresses in the IPv4 network with a `/24` CIDR prefix.

Thus, the following two accounts are completely independent and can have different passwords, authentication plugins, and privileges:

```sql
'app'@'localhost'
'app'@'192.0.2.15'
```

The account `'app'@'localhost'` might have read-only privileges on a local application host, whereas `'app'@'192.0.2.15'` is granted write privileges for a specific application server. Sharing the username `app` does not mean the two connections receive the same privileges.

The operating system username does not dictate the MySQL username either. Someone logged into Windows or Linux as `minh` can still connect to MySQL with `-u app`, provided the corresponding MySQL account exists and is permitted to connect.

When MySQL matches accounts, the `User` part is compared case-sensitively; the `Host` part is case-insensitive. The `User` part must match a literal name or be an empty string representing an anonymous user; `%` and `_` are not supported as wildcards in usernames.

### Writing and Quoting Account Names

The two parts are quoted separately, not combined into a single string:

```sql
-- Correct: user and host are two separate quoted parts
CREATE USER 'app'@'localhost' IDENTIFIED BY 'change_this_password';

-- Not equivalent:
-- 'app@localhost'
```

The host part can be omitted in certain statements. When omitted, an account name consisting only of the user is interpreted as having host `%`, meaning any host. Because this scope is broad and host wildcards are deprecated, always specify the host explicitly when creating new accounts.

### Anonymous Accounts

If the user part is an empty string, MySQL treats it as an anonymous account:

```sql
''@'localhost'
```

This account has no specific username, yet it still has a host part, an authentication mechanism, and its own privileges. When a connection authenticates as an anonymous account, `CURRENT_USER()` returns a string starting with `@`, such as `@localhost`.

In production systems, audit and remove anonymous accounts unless there is an explicit need for them. They easily mislead administrators into thinking a client logged in with the named account they supplied.

## 2. How Can the Host Part Be Specified?

The host part restricts where a client is allowed to connect from. MySQL supports hostnames, IP addresses, and several network notations.

| Host Form | Meaning | Example |
|---|---|---|
| Hostname | Connections from a host whose resolved name matches | `'client01.example.com'` |
| Specific IPv4 | Connections from a single IPv4 address | `'192.0.2.15'` |
| Specific IPv6 | Connections from a single IPv6 address | `'2001:db8::15'` |
| IPv4 CIDR | Connections from a network with a specified prefix length | `'192.0.2.0/24'` |
| IPv4 with subnet mask | Connections from a network defined by a subnet mask | `'192.0.2.0/255.255.255.0'` |
| Wildcard | Matches multiple hosts by pattern | `'%.example.com'`, `'%'` |

### Specific Addresses and CIDR Networks

If an application runs from a host with a stable IP, specifying the exact source address restricts access tightly:

```sql
CREATE USER 'billing_app'@'192.0.2.15'
    IDENTIFIED BY 'replace_with_a_strong_password';

GRANT SELECT, INSERT, UPDATE
    ON billing.*
    TO 'billing_app'@'192.0.2.15';
```

If multiple application servers sit on the same subnet, you can use CIDR instead of creating a separate account per host:

```sql
CREATE USER 'report_app'@'192.0.2.0/24'
    IDENTIFIED BY 'replace_with_a_strong_password';

GRANT SELECT
    ON reporting.*
    TO 'report_app'@'192.0.2.0/24';
```

The `/24` prefix indicates that the first 24 bits of the IPv4 address define the network. In the example above, the network spans `192.0.2.0` through `192.0.2.255`. Use the actual network range of the application; do not widen the range just as a quick workaround for a connection error.

### Host Wildcards and Why to Avoid Them in New Accounts

MySQL allows `%` and `_` characters in the host part to match multiple hostnames or IP addresses. For example:

- `'%.example.com'`: hosts ending in `.example.com`.
- `'198.51.100.%'`: address pattern within `198.51.100.*`.
- `'%'`: any host.

However, the `%` and `_` wildcards in host specifications have been deprecated and may be removed in a future release. Therefore, prefer specific hostnames, IP addresses, CIDR notation, or subnet masks. Legacy `'app'@'%'` accounts in older systems still need to be recognized when evaluating matching rules, but should not be copied as the default pattern for new systems.

An empty host value `''` also means any host and has lower precedence than `%`. Avoid creating accounts with an empty host.

## 3. Which Account Does MySQL Choose When Multiple Rows Match?

This is the most important section of the lesson.

When a client connects, MySQL must locate an account row in the `mysql.user` system table whose `User` and `Host` match. If multiple rows match, MySQL does not pick randomly or by the order in which an administrator created the accounts. The server sorts the rows by specificity precedence rules, then uses **the first matching row**.

General process:

1. The client sends a connection request with a username and credentials from a source host/IP.
2. MySQL determines the client's host information using the configured hostname-resolution mechanism.
3. The server evaluates account rows in sorted precedence order.
4. The first row where both user and host match is selected.
5. The server checks the authentication credentials and account-lock status. If authentication succeeds, the connection is accepted and the privileges of that selected account row apply.

### Host Precedence

MySQL sorts more specific hosts before more general ones. Key cases:

| Precedence | Example Host Part | Interpretation |
|---|---|---|
| Highest | `localhost`, `192.0.2.15`, literal hostname | Exact host or IP match |
| Next | IP with CIDR prefix | Network match by prefix length |
| Next | IP with subnet mask | Network match by subnet mask |
| Low | `%` | Any host |
| Lowest | `''` | Any host; sorts after `%` |

Among multiple CIDR networks, a narrower network range is generally more specific than a broader range. Avoid creating multiple rows of equal specificity with differing privileges so you do not depend on indeterminate ordering.

### User Precedence

Only when rows share the same `Host` value does MySQL evaluate `User` specificity:

- A literal username takes precedence over an empty user.
- An empty user is anonymous and can match any supplied username.
- If both Host and User have equal specificity, ordering between rows is not guaranteed. Avoid configurations that rely on this edge case.

**Key takeaway:** Host specificity is evaluated before User specificity. As a result, an anonymous account with a specific host can be selected ahead of a named account with a broad wildcard host.

## 4. Example: Anonymous Account Shadowing a Named Account

Suppose a MySQL Server has two accounts:

```sql
-- App account allowed to connect from any host
CREATE USER 'app'@'%'
    IDENTIFIED BY 'app_password';

-- Anonymous account restricted to local connections
CREATE USER ''@'localhost'
    IDENTIFIED BY 'anonymous_password';
```

When a client connects locally matching `localhost` and supplies username `app`, both rows are candidates:

| Account | Does User Match? | Does Host Match Local Connection? | Specificity |
|---|---|---|---|
| `'app'@'%'` | Yes, username is app | Yes, wildcard matches | Less specific host |
| `''@'localhost'` | Yes, empty user matches any name | Yes, specific host localhost | More specific host |

MySQL prioritizes `''@'localhost'` because its Host is more specific than `%`. The connection may be authenticated against the anonymous account even though the user entered `app`. Consequently, the granted privileges are not those of `'app'@'%'`.

The client must still supply the credentials of the selected row. In this example, if MySQL selects `''@'localhost'`, the password must match `anonymous_password`. If the client sends `app_password` while the anonymous row is selected, authentication fails; MySQL does not fall back to trying the password for `'app'@'%'` after choosing the first matching row.

You can detect this scenario by running inside the session:

```sql
SELECT
    USER() AS client_identity,
    CURRENT_USER() AS matched_account;
```

Example output:

```text
+-----------------+-----------------+
| client_identity | matched_account |
+-----------------+-----------------+
| app@localhost   | @localhost      |
+-----------------+-----------------+
```

Here:

- `USER()` shows the username submitted by the client and the connection's source host.
- `CURRENT_USER()` shows the MySQL account actually used for authentication and privilege determination.

If both accounts have the same specific host—such as `'app'@'localhost'` and `''@'localhost'`—the named account `app` takes precedence over the anonymous account because Host specificity is tied while User is more specific.

Example:

```sql
CREATE USER 'app'@'localhost'
    IDENTIFIED BY 'app_local_password';
```

After creating this account, a local connection with user `app` matches `'app'@'localhost'` ahead of the anonymous row with the same Host.

## 5. Distinguishing localhost, 127.0.0.1, and TCP Connections

The three forms below are related, but should not be assumed identical:

- `localhost`: hostname referring to the local machine. On Unix, the MySQL client typically uses a Unix socket when connecting to `localhost`, unless connection flags force TCP/IP. On Windows, local connections may also use a named pipe or shared memory depending on configuration.
- `127.0.0.1`: IPv4 loopback address.
- `::1`: IPv6 loopback address.

Connections via socket or named pipe are treated as local connections and match host `localhost` if a matching account exists. Over TCP, MySQL may resolve the client IP to a hostname via DNS or the host cache. Under default settings, connections to `127.0.0.1` often resolve to `localhost`; behavior differs when `skip_name_resolve` is enabled.

To test a TCP connection to loopback, specify the protocol explicitly:

```bash
mysql --protocol=TCP --host=127.0.0.1 --port=3306 --user=app --password
```

To connect locally using the client's default behavior:

```bash
mysql --host=localhost --user=app --password
```

The two commands can match different account rows depending on OS, protocol, DNS, and server configuration. When diagnosing issues, do not look only at the host string in the client command; run `USER()` and `CURRENT_USER()` inside the session itself.

### Effect of skip_name_resolve

The `skip_name_resolve` system variable controls whether the server resolves hostnames when checking incoming connections.

Check status:

```sql
SHOW VARIABLES LIKE 'skip_name_resolve';
```

- When `OFF`, MySQL performs hostname resolution to match against the Host part of accounts.
- When `ON`, MySQL uses only IP addresses to match clients; account rows specified with hostnames may no longer match. Prepare IP-based Host accounts before enabling this setting.
- Local connections must be tested separately by protocol and platform; do not infer that every `localhost` scenario behaves identically.

If you enable `skip_name_resolve` while having only hostname-based accounts, applications may lose the ability to log in. This is a configuration change that should be tested in staging and paired with a rollback plan before deployment.

## 6. Creating Accounts and Granting Properly Scoped Privileges

Creating an account and granting privileges are two distinct operations. `CREATE USER` creates the identity and authentication credentials; `GRANT` assigns privileges at the database, table, or object scope. Create the user first, then grant only the exact privileges the application needs.

Example creating an application account that connects only from a specific application host:

```sql
CREATE USER 'orders_app'@'192.0.2.25'
    IDENTIFIED BY 'replace_with_a_strong_password';

GRANT SELECT, INSERT, UPDATE
    ON orders.*
    TO 'orders_app'@'192.0.2.25';

SHOW GRANTS FOR 'orders_app'@'192.0.2.25';
```

This account is permitted to read, insert, and update data in the `orders` database from host `192.0.2.25`. It does not inherently gain permission to delete data, create users, alter table structures, or access other databases.

If needed for a group of servers in an application subnet:

The CIDR example below is an alternative to the single-IP account above. Choose the scope that fits your actual architecture; create both simultaneously only when intentionally assigning different privileges to one dedicated host versus the rest of the subnet.

```sql
CREATE USER 'orders_app'@'192.0.2.0/24'
    IDENTIFIED BY 'replace_with_a_strong_password';

GRANT SELECT, INSERT, UPDATE
    ON orders.*
    TO 'orders_app'@'192.0.2.0/24';
```

Do not arbitrarily create both accounts with the same name. If a specific-host account and a CIDR account both match, the more specific host is chosen. This can be intentional so a special host receives different privileges, but it should be documented and verified.

### Inspecting Accounts Sharing the Same Username

Accounts are stored in the `mysql.user` system table. An administrator can inspect existing user-host pairs:

```sql
SELECT
    User,
    Host,
    plugin,
    account_locked
FROM mysql.user
WHERE User = 'orders_app'
ORDER BY Host;
```

This query requires read access to the corresponding system table. Inspect only the columns needed to verify configuration; do not query or share password hash values.

View grants for a specific account:

```sql
SHOW GRANTS FOR 'orders_app'@'192.0.2.25';
```

To modify privileges, use `GRANT` or `REVOKE`; to change passwords, use `ALTER USER`. Do not edit the grant tables in the `mysql` database directly.

Example revoking update privilege:

```sql
REVOKE UPDATE
    ON orders.*
    FROM 'orders_app'@'192.0.2.25';
```

Remove an account when an application no longer uses it:

```sql
DROP USER IF EXISTS 'orders_app'@'192.0.2.25';
```

The `DROP USER` statement affects only the exact user-host pair specified. Dropping `'orders_app'@'192.0.2.25'` does not drop `'orders_app'@'192.0.2.0/24'`.

## 7. Diagnostic Workflow When Login Fails or Is Rejected

When an application cannot connect, investigate from concrete details rather than immediately changing the host to `%`.

### Step 1: Record Connection Details

Collect the following values:

- The username the application passes to MySQL.
- The actual source host or IP of the machine running the application.
- The target host, port, and connection protocol.
- The database name the application intends to access.
- The full error message, excluding passwords or secrets.

### Step 2: Distinguish Missing-Row Errors from Authentication Errors

Common errors:

| Message or Symptom | Common Meaning | Diagnostic Direction |
|---|---|---|
| `Host ... is not allowed to connect` | No account row has a Host matching the client | Check Host, DNS, source IP, CIDR, and `skip_name_resolve` |
| `Access denied for user ...` | Wrong password, wrong auth plugin, locked account, or a different row matched than expected | Check exact user-host, lock status, plugin, and credentials |
| Connection succeeds but lacks privileges | Authentication succeeded, but the selected account lacks required privileges | Run `CURRENT_USER()` and `SHOW GRANTS` for the matched account |
| `USER()` and `CURRENT_USER()` differ | Server authenticated against a different account than the client-submitted name | Check anonymous users and Host specificity |

### Step 3: Check Which Account Was Actually Selected

If login succeeds, run:

```sql
SELECT USER(), CURRENT_USER();
SHOW VARIABLES LIKE 'skip_name_resolve';
```

Then use the `CURRENT_USER()` result as the basis for checking privileges:

```sql
SHOW GRANTS FOR 'actual_user'@'actual_host';
```

Replace both parts with the exact account value returned by `CURRENT_USER()`. If the account is anonymous, the user part will be empty, for example:

```sql
SHOW GRANTS FOR ''@'localhost';
```

### Step 4: Check DNS and the Host Cache When Resolution Looks Wrong

MySQL can use DNS to resolve a client IP address into a hostname. If DNS returns a name different from what is declared in the account, the expected row may fail to match.

Administrators can inspect `performance_schema.host_cache` if they have privileges:

```sql
SELECT
    IP,
    HOST,
    HOST_VALIDATED,
    SUM_CONNECT_ERRORS
FROM performance_schema.host_cache
ORDER BY IP;
```

This table helps correlate client IPs with the hostnames resolved by the server. Do not flush the host cache or enable `skip_name_resolve` arbitrarily before checking existing accounts.

### Step 5: Fix the Exact Account and Retest

If an account is missing, create the exact user-host pair. If the host is overly broad, plan a migration to a specific IP or subnet, create the new account, verify connectivity and privileges, and then drop the old account once the application is confirmed working.

Do not resolve errors by granting `ALL PRIVILEGES` or widening Host to `%` when the application only needs access from a specific host or subnet.

## 8. Hands-On Lab: Observing How MySQL Selects an Account

This lab lets you observe the difference between the username sent by a client and the account selected by the server. Perform it on a learning MySQL Server using an admin account authorized to create and drop users.

### Preparation

Create two test accounts:

```sql
CREATE USER 'lab_app'@'%'
    IDENTIFIED BY 'lab_app_password';

CREATE USER ''@'localhost'
    IDENTIFIED BY 'lab_anonymous_password';
```

Perform this in an isolated lab server that can be reset. If the environment already has these accounts, check `mysql.user` first; do not overwrite or delete accounts used by other applications. An anonymous account has an empty username, so it cannot be given a custom lab username.

### Experiment 1: Connecting from localhost

Open a local connection whose host the server recognizes as `localhost` using username `lab_app`:

~~~bash
mysql --host=localhost --user=lab_app --password
~~~

When prompted for the password, enter `lab_anonymous_password`, because the anonymous row has a more specific Host and is selected ahead of `'lab_app'@'%'`. If you enter `lab_app_password`, authentication fails since that password belongs to a different account row. If your environment or connection protocol causes the two rows not to both match, results will differ; check `USER()` and `CURRENT_USER()` rather than assuming.

After connecting successfully, run:

```sql
SELECT USER(), CURRENT_USER();
```

Observe whether the server picked `lab_app` or the anonymous account. The outcome depends on the connection protocol and the host the server uses for matching. If authenticated as the anonymous account, session privileges are those of `''@'localhost'`.

### Experiment 2: Creating a Row with a Specific Host for the User

Create the account:

```sql
CREATE USER 'lab_app'@'localhost'
    IDENTIFIED BY 'lab_local_password';
```

Reconnect from localhost using user `lab_app` and run:

~~~bash
mysql --host=localhost --user=lab_app --password
~~~

This time enter `lab_local_password`, because `'lab_app'@'localhost'` is more specific than the anonymous account sharing the same Host.

Once connected, run:

```sql
SELECT USER(), CURRENT_USER();
```

Compare with the previous experiment. When Host specificity is tied at `localhost`, a named User takes precedence over an empty User.

### Experiment 3: Checking Privileges

Grant distinct privileges to see how the selected account directly affects SQL execution:

```sql
CREATE DATABASE IF NOT EXISTS mysql_account_lab;

CREATE TABLE IF NOT EXISTS mysql_account_lab.sample (
    id INT PRIMARY KEY,
    note VARCHAR(100)
);

GRANT SELECT
    ON mysql_account_lab.*
    TO 'lab_app'@'localhost';
```

Reconnect as `lab_app` and check:

```sql
SHOW GRANTS FOR 'lab_app'@'localhost';

SELECT *
FROM mysql_account_lab.sample;
```

An account with `SELECT` can read data. Try a write operation to confirm the server rejects it while `INSERT` has not been granted. Then grant the needed privilege and observe the result.

### Cleanup

Once finished, exit sessions using the lab accounts and drop the test objects:

```sql
DROP USER IF EXISTS 'lab_app'@'localhost';
DROP USER IF EXISTS 'lab_app'@'%';
DROP USER IF EXISTS ''@'localhost';

DROP DATABASE IF EXISTS mysql_account_lab;
```

Run the statement dropping the anonymous user only if it is the exact test account you just created in the lab environment. Never delete an existing anonymous account on a shared server or one serving another application.

## 9. Principles to Remember

1. A MySQL account is a `'user'@'host'` pair; two different hosts form two distinct accounts even with the same username.
2. Host denotes where the client connects from, not the destination host the client uses to locate MySQL Server.
3. When multiple rows match, MySQL picks the first row after sorting: more specific Host is evaluated first, followed by more specific User.
4. An anonymous user can be selected if its Host is more specific than a named account with a broad Host.
5. `USER()` shows the identity sent by the client; `CURRENT_USER()` shows the account used by the server for authentication and privilege calculation.
6. `localhost`, `127.0.0.1`, and TCP connections can lead to different matching outcomes depending on protocol, DNS, and configuration.
7. Prefer specific hostnames, IPs, or CIDR ranges; avoid creating new accounts with wildcard hosts `%` or `_` since they are deprecated.
8. Create users with `CREATE USER`, grant least privileges with `GRANT`, verify with `SHOW GRANTS`, and manage changes via dedicated account statements.

## Official References

The rules in this lesson were verified against the MySQL 9.7 Reference Manual as of **19-11-2026**:

1. [Specifying Account Names](https://dev.mysql.com/doc/refman/9.7/en/account-names.html): `user@host` syntax, anonymous accounts, hostnames, IPs, CIDR, subnet masks, and wildcards.
2. [Access Control, Stage 1: Connection Verification](https://dev.mysql.com/doc/refman/9.7/en/connection-access.html): account row sorting order and first-match selection rules.
3. [Access Control, Stage 2: Request Verification](https://dev.mysql.com/doc/refman/9.7/en/request-access.html): how MySQL checks privileges after a connection is authenticated.
4. [Adding Accounts, Assigning Privileges, and Dropping Accounts](https://dev.mysql.com/doc/refman/9.7/en/creating-accounts.html): creating, granting privileges to, and dropping accounts.
5. [Information Functions](https://dev.mysql.com/doc/refman/9.7/en/information-functions.html): meaning of `USER()` and `CURRENT_USER()`.
6. [Server System Variables](https://dev.mysql.com/doc/refman/9.7/en/server-system-variables.html): `skip_name_resolve` configuration.
7. [DNS Lookups and the Host Cache](https://dev.mysql.com/doc/refman/9.7/en/host-cache.html): hostname resolution, host cache, and connection diagnostics.
8. [Troubleshooting Problems Connecting to MySQL](https://dev.mysql.com/doc/refman/9.7/en/problems-connecting.html): connection errors and troubleshooting steps.
