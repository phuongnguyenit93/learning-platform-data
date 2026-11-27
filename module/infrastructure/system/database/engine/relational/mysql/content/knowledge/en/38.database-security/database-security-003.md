# user@host, Wildcards, and Account Selection Rules

This lesson belongs to the **DATABASE_MYSQL** module. On the path to mastering MySQL—from table design, data types, keys, and SQL queries to indexes, transactions, and concurrency control; as well as practicing reading execution plans, optimizing queries, managing privileges, backing up, and handling operational issues in relational databases—understanding how MySQL identifies accounts is foundational to configuring access privileges with the right scope.

MySQL does not identify an account by username alone. An account is identified by a **username and source host pair** (`user` and `host`). When a client connects, MySQL matches the login credentials along with the connection origin against declared accounts, selects one matching account, and only then authenticates and applies that account's privileges. Understanding the matching order helps prevent mistakes such as logging in as an anonymous account, applying the wrong privilege set, or opening access wider than intended.

## 1. A MySQL Account Is a `user` and `host` Pair

An account name is typically written in the form:

```sql
'user_name'@'host_name'
```

Examples:

```sql
'app'@'localhost'
'app'@'192.0.2.17'
'app'@'192.0.2.0/24'
'app'@'%'
```

The two parts have distinct meanings:

- `user_name` is the account name sent by the client at login.
- `host_name` specifies the host, IP address, or address pattern allowed to connect with that account.

Therefore, `'app'@'localhost'` and `'app'@'192.0.2.17'` are **two separate accounts**, even though both have the username `app`. Each account can have a different password, authentication plugin, lock state, and privilege set. An `app` account created only for `localhost` does not inherently allow connections from another machine.

Example of creating two accounts with the same name but different connection source restrictions:

```sql
CREATE USER 'app'@'localhost'
  IDENTIFIED BY 'replace-with-a-secret';

CREATE USER 'app'@'192.0.2.17'
  IDENTIFIED BY 'replace-with-another-secret';

GRANT SELECT, INSERT, UPDATE
  ON shop.* TO 'app'@'localhost';

GRANT SELECT
  ON shop.* TO 'app'@'192.0.2.17';
```

Connections from the local machine will use `app@localhost`; connections from `192.0.2.17` will use the account corresponding to that address. Privileges of the two accounts are not combined.

MySQL also supports **anonymous accounts**: the `user_name` portion is an empty string, such as `''@'localhost'`. Such an account can match connections that have no matching named user in the account table, so they must be audited and managed carefully. The `user_name` part does not support `%` and `_` as wildcards to match multiple usernames; those characters only act as wildcards in the `host_name` part.

## 2. Wildcards in the `host` Part

MySQL allows certain wildcard characters in the host portion of an account:

| Character | Meaning | Example |
|---|---|---|
| `%` | Matches a string of zero, one, or more characters | `'app'@'10.20.%'` |
| `_` | Matches a single character | `'app'@'db_.example.net'` |

For example, `'app'@'10.20.%'` can match clients whose host address starts with `10.20.`. This pattern is string matching, not a CIDR subnet check. You should not treat `10.20.%` as an exact network representation in every situation, especially when you need to restrict a specific IP range.

Starting in MySQL **8.0.35**, using `%` and `_` in host values is deprecated. For new systems, prefer declaring specific hosts/IPs or using network syntax supported by your MySQL version. If you need to restrict by IPv4 subnet, you can use a netmask; MySQL 8.0.23 and later also support CIDR notation:

```sql
-- CIDR, supported since MySQL 8.0.23
CREATE USER 'app'@'192.0.2.0/24'
  IDENTIFIED BY 'replace-with-a-secret';

-- IPv4 netmask notation
CREATE USER 'app'@'192.0.2.0/255.255.255.0'
  IDENTIFIED BY 'replace-with-a-secret';
```

Choose the syntax appropriate for your server version and verify by connecting from an address inside—as well as outside—the intended network range.

### `localhost` and `127.0.0.1` Are Not Always Equivalent

On Unix/Linux systems, clients usually use a Unix socket when `localhost` is specified, whereas `127.0.0.1` typically opens a TCP/IP connection. Consequently, these two connections can match two different accounts:

```sql
CREATE USER 'app'@'localhost' IDENTIFIED BY 'replace-with-a-secret';
CREATE USER 'app'@'127.0.0.1' IDENTIFIED BY 'replace-with-another-secret';
```

When testing the difference, specify the protocol explicitly on the client:

```bash
# Connect via Unix socket (if supported by client and server)
mysql --protocol=SOCKET -u app -p

# Connect via TCP to loopback
mysql --protocol=TCP -h 127.0.0.1 -u app -p
```

Do not infer which account was selected solely from the fact that the client and MySQL Server reside on the same machine; verify the actual identity after logging in.

## 3. How Does MySQL Select the Matching Account?

During the connection verification phase, MySQL compares the username supplied by the client and the source host detected by the server against declared account rows. You can think of the process in the following steps:

1. The client sends a username and opens a connection from a source address.
2. MySQL determines the client's host/IP. Hostname resolution depends on the `skip_name_resolve` setting.
3. MySQL searches for account rows where both `User` and `Host` match.
4. The server evaluates rows with more specific hosts before broader hosts. Exact host/IP matches take precedence; wildcard patterns are ordered by specificity, and broad patterns like `%` typically come last.
5. For the same `Host` value, an account with a specific username takes precedence over an anonymous account with an empty `User`.
6. The first matching row is chosen for authentication. If authentication fails, MySQL does not fall back to trying a less specific row.

The key point is that **Host is evaluated before User**. As a result, an anonymous account bound to a very specific host can be selected ahead of a named account declared only with a broad host.

For example, suppose two accounts exist:

```sql
CREATE USER 'report'@'%'
  IDENTIFIED BY 'replace-with-a-secret';

CREATE USER ''@'localhost'
  IDENTIFIED BY 'replace-with-another-secret';
```

When a client connects as `report` from `localhost`, the row `''@'localhost'` has a more specific host than `report@%`, so it may be selected. As a result, the connection is authenticated against the anonymous account. If `report@localhost` also exists, the named account `report` will take precedence over the anonymous account because both rows have the same `Host`.

Important consequences to remember:

- `app@localhost` can be selected ahead of `app@%` when connecting from the local machine.
- `app@192.0.2.17` can be selected ahead of `app@192.0.2.0/24` or `app@%` if all of them match.
- The selected account determines both the authentication method and the access privileges; MySQL does not merge privileges from other account rows with the same username.
- If the password or authentication method of the selected row fails, the server does not automatically switch to a broader account and retry.

## 4. Impact of Hostname Resolution

If `skip_name_resolve` is off, MySQL can resolve the client's IP address to a hostname to match hostname-based account values. This depends on DNS and network configuration; DNS changes can alter connection matching behavior.

When `skip_name_resolve` is enabled, the server does not perform hostname resolution for client connections. In that case, use IP addresses or appropriate subnets in the `Host` field; `localhost` remains a supported special case. You can check the setting with:

```sql
SHOW VARIABLES LIKE 'skip_name_resolve';
```

Additionally, the server only sees the address of the peer connecting directly to it. If the application passes through NAT, a proxy, a load balancer, or a container gateway, the source address MySQL sees may be that of the intermediate component. When configuring `user@host`, base it on the actual address MySQL receives, not merely the end host's IP.

## 5. Verifying Which Account Is Being Used

The `USER()` and `CURRENT_USER()` functions distinguish the connection information from the MySQL account actually selected:

```sql
SELECT
  USER() AS client_identity,
  CURRENT_USER() AS matched_account;
```

- `USER()` reports the client username and host for the current connection.
- `CURRENT_USER()` reports the MySQL account used for privilege checking. If an anonymous account was selected, the result may look like `@localhost` even if the client sent the name `report`.

After identifying the account, check the privileges currently in effect:

```sql
SHOW GRANTS;

-- Check the definition and privileges of a specific account
SHOW CREATE USER 'app'@'192.0.2.17';
SHOW GRANTS FOR 'app'@'192.0.2.17';
```

To review accounts sharing the same name or anonymous accounts, an administrator with sufficient privileges can inspect the `mysql.user` system table:

```sql
SELECT User, Host, plugin, account_locked
FROM mysql.user
WHERE User IN ('app', '');
```

Use this table for inspection only. Manage accounts and privileges using statements such as `CREATE USER`, `ALTER USER`, `DROP USER`, `GRANT`, and `REVOKE`; do not update system tables directly.

## 6. Designing Accounts Under Least Privilege

When designing application access, apply the following principles:

1. **Restrict hosts to actual need.** Prefer the application server IP or a well-defined subnet. Use `%` only when connections from many sources are genuinely required and compensating network controls are in place.
2. **Separate accounts by application and environment.** Application runtime, reporting, migration, and administrative accounts should have separate identities and privileges. Avoid sharing a single administrative account across all services.
3. **Grant the right privileges on the right schema.** For instance, an order-processing service may need `SELECT`, `INSERT`, `UPDATE` on `orders_db.*`, while a reporting service only needs `SELECT`.
4. **Align DNS and `skip_name_resolve` configuration.** If the server does not perform name resolution, do not rely on hostnames in account rows.
5. **Test from the application's actual network path.** Connecting from an admin workstation or localhost does not prove the same account will match when the application goes through a proxy or NAT.
6. **Review anonymous and legacy accounts.** Verify usage before locking or dropping; do not keep an overly broad account solely because a legacy connection relies on it.

Example configuring two roles with different host scopes and privileges:

```sql
-- Order-writing service: accepted only from one application host
CREATE USER 'orders_api'@'192.0.2.17'
  IDENTIFIED BY 'replace-with-a-secret';

GRANT SELECT, INSERT, UPDATE
  ON orders_db.* TO 'orders_api'@'192.0.2.17';

-- Reporting service: accepted from a defined IPv4 subnet
-- CIDR syntax requires MySQL 8.0.23 or later
CREATE USER 'orders_report'@'192.0.2.0/24'
  IDENTIFIED BY 'replace-with-another-secret';

GRANT SELECT
  ON orders_db.* TO 'orders_report'@'192.0.2.0/24';
```

The password strings in the examples are placeholders only. In deployment, use distinct, strong secrets stored in your environment's secret management system.

## 7. Troubleshooting Account Matching Errors

When encountering an `Access denied` error, check in the following order to pinpoint the root cause:

1. Confirm which username the client is sending and whether it is connecting over a socket or TCP.
2. Identify the source address MySQL sees; check for NAT, proxies, or gateways if applicable.
3. Inspect account rows with the same `User`, including empty `User` rows, and compare `Host` specificity.
4. Check `skip_name_resolve` if the account uses a hostname.
5. Once logged in, run `SELECT USER(), CURRENT_USER();` to see which account was actually selected.
6. Use `SHOW GRANTS;` to inspect that account's privileges, then adjust the exact matching account row with appropriate administrative statements.

Do not work around the issue by immediately creating an additional `user@'%'` account. That can mask a host-matching bug and widen the access surface. Identify the actual host, the selected account row, and the required privileges before modifying the configuration.

## 8. Self-Check

Suppose the server has the following accounts:

```sql
'api'@'localhost'
'api'@'192.0.2.17'
'api'@'192.0.2.0/24'
'api'@'%'
''@'localhost'
```

Answer these questions for yourself:

1. Which account will a client logging in as `api` from `192.0.2.17` match?
2. Which account will a client logging in as `api` from another IP in the `192.0.2.0/24` subnet match?
3. If connecting from `localhost` without an `api@localhost` row, how can the anonymous account affect matching?
4. Why are the privileges of `api@%` not automatically added to the privileges of `api@localhost`?
5. When `skip_name_resolve` is enabled, what must be changed if existing accounts rely on hostnames?

Your answers should rely on host specificity taking precedence first, followed by username when `Host` is equal. For connections from `192.0.2.17`, the exact IP account takes precedence; for other IPs in the subnet, the subnet account is evaluated before `%`. For `localhost`, a host-specific account can cause the anonymous account to be selected if no `api@localhost` account exists. Privileges always belong strictly to the single selected account row and are never merged from other rows.
