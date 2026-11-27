# Troubleshooting PostgreSQL Connection Errors Caused by DNS, Network, TLS, Authentication, or pg_hba.conf

When an application cannot connect to PostgreSQL, the error message usually appears on the client side, but the root cause may lie in DNS, the network path, the server listener configuration, TLS, access rules, or authentication credentials. The effective way to troubleshoot is to identify which layer the connection stops at, gather evidence from the exact host running the application, and fix the relevant configuration.

A message like `connection refused` is completely different from `password authentication failed`: the first happens before PostgreSQL authenticates the user; the second shows that the client reached the server and the PostgreSQL process handled the login request. Distinguishing these prevents changing passwords or opening firewalls when the actual issue is in DNS or TLS.

## 1. Understanding the Path of a PostgreSQL Connection

For a standard TCP connection, the client goes through these main steps:

1. Resolve the hostname to an IP address.
2. Establish a TCP connection to the PostgreSQL IP and port.
3. Connect to the listening PostgreSQL process.
4. Negotiate TLS if the client requests it or the SSL mode allows it.
5. The server matches the connection against the rules in `pg_hba.conf`.
6. PostgreSQL authenticates the role using the specified method.
7. The server checks the target database and connect privilege, then creates a session.

Connections over a Unix domain socket bypass DNS and TCP, and typically match `local` lines in `pg_hba.conf`. Therefore, a successful local connection does not prove that an application from another host can connect over TCP.

Diagnostic diagram:

~~~mermaid
flowchart TD
    A["Application reads host, port, database, user"] --> B["DNS resolves host"]
    B -->|Failure| D["Check DNS, resolver, hostname"]
    B -->|Success| C["Establish TCP"]
    C -->|Timeout / refused| E["Check route, firewall, listener, port"]
    C -->|Success| F["Negotiate TLS"]
    F -->|TLS error| G["Check sslmode, CA, certificate, hostname"]
    F -->|Success| H["Match pg_hba.conf"]
    H -->|No matching rule| I["Fix rule, CIDR, order, SSL mode"]
    H -->|Rule matched| J["Authenticate role"]
    J -->|Failure| K["Check password, role, auth method"]
    J -->|Success| L["Check database and CONNECT privilege"]
    L --> M["Connection succeeded"]
~~~

Not every driver displays each step separately. Some libraries wrap TLS, socket, or authentication errors into a generic message. In those cases, correlate the client error message with server logs and layer-by-layer tests.

## 2. Gathering Information Before Changing Configuration

First, record:

- The timestamp of the error and the full error message, including inner/nested causes if provided by the driver.
- The host or container running the application, the network environment, and the source IP address seen by the server.
- The hostname, port, database, role, and TLS mode being used.
- The PostgreSQL version and the driver/client version.
- Whether the error affects all clients or only one application, one host, or one network.
- When the error started and any recent changes: DNS, firewall, certificates, passwords, configuration, application deployments, or failover.

Do not include passwords, connection strings containing passwords, private keys, or tokens in tickets, shared logs, or public diagnostic commands. You may mask sensitive values while keeping the hostname, port, database, username, and TLS mode for correlation.

Test the connection from the actual environment where the application runs. Testing from an administrator's laptop can yield different results because DNS, routes, NAT, firewalls, and source addresses differ.

## 3. Checking DNS and Hostname

### 3.1. Recognizing DNS Errors

Common error messages:

- `could not translate host name ... to address`
- `Name or service not known`
- `Temporary failure in name resolution`
- `No such host is known`

These errors occur before the client establishes a TCP connection to PostgreSQL. Check the hostname in the application configuration, environment variables, secrets, or connection string; pay close attention to staging/production environment names and dots or hyphens in the hostname.

### 3.2. Testing Name Resolution

On Linux:

~~~bash
getent ahosts db.example.internal
dig +short A db.example.internal
dig +short AAAA db.example.internal
~~~

On Windows PowerShell:

~~~powershell
Resolve-DnsName db.example.internal -Type A
Resolve-DnsName db.example.internal -Type AAAA
~~~

Compare the results against PostgreSQL's current IP address or the endpoint provided by your vendor. If both A and AAAA records exist, the client may try IPv6 while the IPv6 firewall or routing is not configured properly. If DNS returns multiple addresses, check each one because an old node or faulty endpoint can cause intermittent results.

If internal DNS uses split-horizon, test from the exact VPC, subnet, VPN, cluster, or container where the application runs. A hostname may resolve to a private IP on the internal network and a different IP on an external network.

### 3.3. Distinguishing DNS Errors from Network Errors

You can use an IP address temporarily to verify whether the issue is name resolution. With libpq, `hostaddr` specifies the network address while `host` keeps the logical hostname:

~~~bash
psql "host=db.example.internal hostaddr=10.20.30.40 port=5432 dbname=appdb user=app_user connect_timeout=5"
~~~

If connecting by IP works while using the hostname fails, check DNS, the resolver cache, and the hostname configuration. When `sslmode=verify-full` is enabled, you must still keep the proper hostname to verify the name in the server certificate; do not replace the hostname with an IP just to bypass a certificate error.

Only flush the DNS cache when you have confirmed the client host is holding stale results. On Windows, you can run `ipconfig /flushdns`; on Linux, how to clear the cache depends on the resolver in use, such as systemd-resolved, dnsmasq, or the network service. Flushing the cache will not fix an incorrect DNS record on the DNS server.

## 4. Checking the TCP Network and PostgreSQL Listener

### 4.1. Distinguishing Timeout and Connection Refused

| Message | Common Meaning | What to Check |
|---|---|---|
| `connection timed out` | Packets received no response within the wait period | Route, firewall, security group, ACL, VPN, NetworkPolicy |
| `connection refused` | Target rejected TCP, usually because no listener exists on that IP/port or a firewall actively rejected it | PostgreSQL not running, wrong port, wrong bind address, firewall rule |
| `No route to host` / `Network is unreachable` | Client host has no path to the target network or is blocked at the network layer | Route, subnet, gateway, VPN, IP address |
| `server closed the connection unexpectedly` | Connection was closed unexpectedly after starting | Server logs, restart/crash, proxy, network, TLS, or client-side error |

These are directional indicators, not absolute conclusions. A firewall can return a rejection or silently drop packets; proxies and load balancers can also produce messages different from a direct connection.

### 4.2. Checking the Port from the Client

On Linux, you can use netcat:

~~~bash
nc -vz db.example.internal 5432
~~~

On Windows PowerShell:

~~~powershell
Test-NetConnection -ComputerName db.example.internal -Port 5432
~~~

If TCP cannot be established, do not change passwords or role privileges yet. Check:

- The IP address and port the client is using.
- Routing between the application subnet and the database subnet.
- Host-level firewall and network firewalls.
- Cloud security groups, network ACLs, or firewall policies.
- VPN, peering, NAT gateway, proxy, or load balancer.
- Kubernetes Service, Endpoint/EndpointSlice, and NetworkPolicy if the application runs in a cluster.
- Whether the database port is properly published/forwarded if PostgreSQL runs in a container.

For source-IP-based firewalls, determine the actual source IP seen by the server. NAT, egress gateways, or proxies may make that IP different from the private address of the container or application host. Do not add a CIDR based on an IP guessed from a developer machine.

### 4.3. Verifying PostgreSQL Listens on the Right Address and Port

A server with PostgreSQL running can still reject remote connections if the process only binds to loopback.

Connect using a local socket or an active administrative session, then check:

~~~sql
SHOW listen_addresses;
SHOW port;
SHOW config_file;
SHOW hba_file;
~~~

- `listen_addresses` defines the IP addresses on which PostgreSQL accepts TCP connections.
- `port` is the TCP port of the instance.
- `config_file` and `hba_file` show the actual configuration files in use, preventing edits to an unused copy.

The default value is typically `localhost`, accepting only local connections. If network connections are needed, configure the appropriate private IP address or `*` when corresponding network controls are in place. Do not expose the listener on all public interfaces without a clear requirement and protection layers.

On Linux, you can inspect listening sockets:

~~~bash
ss -lntp | grep 5432
~~~

On Windows:

~~~powershell
Get-NetTCPConnection -LocalPort 5432 -State Listen
~~~

If no listener appears, check the service status, startup logs, configured port, and PostgreSQL processes. If the listener only appears on `127.0.0.1:5432` or `[::1]:5432`, it is not accepting connections from other network interfaces.

Changing `listen_addresses` or `port` requires restarting PostgreSQL because these are startup parameters. Reloading the configuration does not apply changes that require a restart. Before restarting, evaluate the impact on applications, replicas, connection pools, and maintenance windows.

### 4.4. Checking Server Status with pg_isready

~~~bash
pg_isready -h db.example.internal -p 5432 -d appdb -U app_user
~~~

`pg_isready` checks whether PostgreSQL is accepting connections. Common exit codes are:

- `0`: server is accepting connections normally.
- `1`: server is rejecting connections, for example during startup or shutdown.
- `2`: no response from the server.
- `3`: invalid invocation parameters.

This command does not prove that the password is correct, the role has privileges, or the application can complete login. Use `psql` to test the full authentication flow.

## 5. Checking TLS and Certificates

PostgreSQL can encrypt TCP connections using TLS. TLS errors typically occur after TCP connects but before authentication completes.

### 5.1. libpq sslmode Options

For clients using libpq, the `sslmode` parameter controls TLS handling:

| sslmode | Behavior |
|---|---|
| `disable` | Do not use TLS |
| `allow` | Try unencrypted first, only try TLS if the unencrypted connection fails |
| `prefer` | Try TLS first, may fall back to unencrypted |
| `require` | Require TLS-encrypted connection, without full server identity verification as in `verify-full` |
| `verify-ca` | Require TLS and verify the certificate chain against a trusted CA |
| `verify-full` | Require TLS, verify the CA chain, and verify the server hostname |

In production environments, prefer `verify-full` with a trusted CA and a hostname matching the certificate. `prefer` can allow a client to fall back to an unencrypted connection; `require` ensures encryption but does not replace verifying the server identity.

Do not use `sslmode=disable` as a long-term fix. If this mode makes the connection succeed, it only shows that the non-TLS path works; you still need to resolve the TLS configuration and security requirements of the system.

### 5.2. Common Certificate Errors

| Error | Possible Causes | Resolution |
|---|---|---|
| Certificate verify failed | CA is not trusted, missing intermediate certificate, or invalid certificate chain | Install the correct CA and configure `sslrootcert` |
| Hostname mismatch | Hostname used by the client does not match a valid SAN/CN in the certificate | Use the correct endpoint or reissue the certificate with the appropriate SAN |
| Certificate has expired | Certificate has expired | Renew, deploy the new certificate, and reload according to procedure |
| Server does not support SSL | Server-side SSL is not enabled, client connects to the wrong endpoint, or a proxy does not support PostgreSQL TLS | Check `ssl`, the endpoint, and the proxy configuration |
| No certificate provided / certificate required | Server requires a client certificate, but client did not send one or sent the wrong one | Configure the appropriate client certificate and private key |
| Private key permission denied | Client process cannot read the private key or file permissions are too permissive | Fix ownership and file permissions on the key |

With `verify-full`, the hostname must match a name in the server certificate. If the client connects using a DNS alias, that alias must also appear in the certificate's Subject Alternative Name (SAN).

### 5.3. Client-Side TLS Configuration

Example connecting with libpq using an organization CA:

~~~bash
psql "host=db.example.internal port=5432 dbname=appdb user=app_user sslmode=verify-full sslrootcert=/etc/postgresql/certs/root-ca.crt connect_timeout=5"
~~~

If the server requires a client certificate:

~~~bash
psql "host=db.example.internal port=5432 dbname=appdb user=app_user sslmode=verify-full sslrootcert=/etc/postgresql/certs/root-ca.crt sslcert=/etc/postgresql/certs/client.crt sslkey=/etc/postgresql/private/client.key"
~~~

Paths are examples only; use the certificates issued by your system. The private key must be protected and readable only by the user running the application. On Unix, libpq typically requires the private key not to be readable by group or other users; `0600` permissions are a common choice.

Some Java, .NET, Node.js libraries, and PostgreSQL drivers have their own parameter names or trust store mechanisms. Check the documentation for the exact driver version. Do not assume libpq's `sslmode`, `sslrootcert`, or certificate paths work verbatim in every driver.

### 5.4. Checking Server-Side TLS and Session Encryption

When you have administrative connection access:

~~~sql
SHOW ssl;
SHOW ssl_cert_file;
SHOW ssl_key_file;
SHOW ssl_ca_file;
~~~

`ssl` must be enabled if the server is expected to serve TLS connections. Check the certificate, private key, CA chain, and file read permissions for the user running PostgreSQL. Whether a parameter requires a restart or only a reload depends on the parameter's context and PostgreSQL version; check `pg_settings` rather than assuming all TLS changes apply the same way.

To confirm the current session is encrypted:

~~~sql
SELECT
    ssl,
    version,
    cipher,
    bits
FROM pg_stat_ssl
WHERE pid = pg_backend_pid();
~~~

If `ssl` is `true`, the current session uses TLS. This view only shows the state of an already established connection; it cannot diagnose a client failing before login.

## 6. Checking pg_hba.conf

`pg_hba.conf` (Host-Based Authentication) is where PostgreSQL specifies which clients may connect to which databases, as which roles, from which addresses, and using which authentication methods.

This is server-side configuration. Editing a file on the client machine does not change PostgreSQL's access policy.

### 6.1. Structure of an HBA Entry

Common formats:

~~~text
# TYPE     DATABASE   USER       ADDRESS          METHOD
local      appdb      app_user                    scram-sha-256
host       appdb      app_user   10.20.30.0/24    scram-sha-256
hostssl    appdb      app_user   10.20.30.0/24    scram-sha-256
hostnossl  appdb      app_user   10.20.30.0/24    reject
~~~

Key connection types:

- `local`: Unix domain socket, no IP address column.
- `host`: TCP, either with TLS or without TLS.
- `hostssl`: TCP over TLS.
- `hostnossl`: TCP without TLS.

A TCP connection will not match a `local` line. If an application switches from a local socket to a hostname or IP, it needs an appropriate `host`, `hostssl`, or `hostnossl` rule.

### 6.2. Matching Rules and Line Order

PostgreSQL reads HBA lines from top to bottom. **The first rule that completely matches the connection type, database, user, and address is applied.** If authentication fails under that rule, PostgreSQL does not continue trying subsequent lines.

Example:

~~~text
host    all     all         10.20.30.0/24    reject
hostssl appdb   app_user    10.20.30.0/24    scram-sha-256
~~~

For a client in the subnet above, the first `reject` line already matches, so the `hostssl` line below is never evaluated. Specific rules and general rules must be ordered appropriately.

The database and user fields must also match. A rule for `appdb` does not automatically allow connecting to the `reporting` database; a rule for `app_user` does not apply to other roles.

### 6.3. Determining Source Address and CIDR

The `ADDRESS` field is the source address seen by PostgreSQL. If the client traverses NAT, an egress gateway, a proxy, or a load balancer, that address may differ from the application host's original IP.

Example:

~~~text
hostssl appdb app_user 10.20.30.0/24 scram-sha-256
~~~

This rule allows IPv4 addresses in the `10.20.30.0/24` subnet to access the `appdb` database as `app_user` over TLS with SCRAM authentication.

For IPv6, use the corresponding IPv6 CIDR. Verify the real source address and grant only the smallest range required. Do not use `0.0.0.0/0` or `::/0` as a quick fix for connection errors; doing so can open access to the entire Internet if the firewall also permits it.

### 6.4. Inspecting the Active HBA File and Syntax Errors

From an active administrative session:

~~~sql
SHOW hba_file;
~~~

Read the exact file returned, inspect the relevant rules, and verify that the file parses cleanly:

~~~sql
SELECT
    line_number,
    type,
    database,
    user_name,
    address,
    auth_method,
    error
FROM pg_hba_file_rules
WHERE error IS NOT NULL
ORDER BY line_number;
~~~

If the query returns error rows, fix the syntax or values on the indicated lines. The `pg_hba_file_rules` view helps inspect the file's contents and parse errors; having no syntax errors does not prove a specific client matches the intended rule. You must still verify database, user, connection type, SSL, and source address.

### 6.5. Reloading Configuration After Edits

After editing `pg_hba.conf`, you can reload the configuration:

~~~sql
SELECT pg_reload_conf();
~~~

A result of `true` indicates the reload request was sent successfully; check the server logs to confirm there were no errors reading the configuration. You can also use `pg_ctl reload` or your service reload command depending on how PostgreSQL is installed.

HBA changes typically do not require a full PostgreSQL restart. However, read the logs after reloading and retry from the exact client. If you also changed `listen_addresses` or other restart-required parameters at the same time, reloading HBA alone will not apply those changes.

### 6.6. Choosing the Right Authentication Method

Common methods:

| Method | How It Works and Scope |
|---|---|
| `scram-sha-256` | Password authentication using SCRAM; the modern recommended choice for password authentication |
| `md5` | Legacy password method; plan to migrate to SCRAM when clients support it |
| `password` | Sends password in the PostgreSQL protocol; should only be used over TLS |
| `peer` | Uses the OS user identity for local Unix connections |
| `cert` | Authenticates via client certificate according to certificate and mapping configuration |
| `trust` | Allows connection without password verification; suitable only in tightly controlled, isolated local scopes |

For remote applications, `hostssl` combined with `scram-sha-256` is generally recommended. Do not switch to `trust` to bypass password errors, because any client matching that rule can log in without proving identity with a password.

When migrating from MD5 to SCRAM, ensure drivers and client libraries support SCRAM, set `password_encryption` appropriately, and then reset passwords for the roles being migrated. Changing `password_encryption` does not automatically convert previously stored password hashes.

## 7. Checking Role, Password, and Database Privileges

When logs report `password authentication failed for user ...`, the client reached PostgreSQL and the server proceeded to authentication. Possible causes include a wrong password, wrong role, stale secret, incompatible authentication method, or the application pointing to the wrong endpoint.

### 7.1. Checking That the Role Exists and Has LOGIN

From an administrative session:

~~~sql
SELECT
    rolname,
    rolcanlogin,
    rolvaliduntil
FROM pg_roles
WHERE rolname = 'app_user';
~~~

- No rows returned: the role does not exist in the connected cluster.
- `rolcanlogin = false`: the role is not allowed to log in directly.
- `rolvaliduntil` is in the past: the role's password has expired per that setting.

You can inspect role attributes with `\du` in psql. If the role needs to log in and policy allows:

~~~sql
ALTER ROLE app_user LOGIN;
~~~

Only grant `LOGIN` to application roles designed for login. Group roles or privilege-only roles can remain without login.

### 7.2. Resetting a Password Safely

Once you have verified the right cluster, role, and change approval process, an administrator can use the `\password` command in psql:

~~~text
\password app_user
~~~

This command prompts interactively for the password and avoids putting the password directly in SQL statements that may be saved in history or logs. Do not send passwords over chat or write passwords into shell scripts, committed configuration files, or command lines visible to process monitors.

After rotating the secret, update the secret store and restart or refresh the connection pool according to how the application uses it. Some pools keep old connections alive or continue using the old password when opening new connections.

### 7.3. Checking Database Existence and CONNECT Privilege

The database must exist on the right cluster:

~~~sql
SELECT datname
FROM pg_database
WHERE datname = 'appdb';
~~~

If the role authenticates successfully but cannot connect to the database, check privileges:

~~~sql
SELECT
    has_database_privilege('app_user', 'appdb', 'CONNECT') AS can_connect;
~~~

If policy permits granting the privilege:

~~~sql
GRANT CONNECT ON DATABASE appdb TO app_user;
~~~

The message `database "appdb" does not exist` usually indicates a wrong database name or connecting to the wrong cluster. The message `permission denied for database` requires checking the CONNECT privilege. Both cases differ from a password error.

### 7.4. Checking Application Connection String and Secrets

Verify these fields:

- Do host and port point to the right environment?
- Are database and username mixed up between staging and production?
- Has the password been updated in the secret manager, environment variables, and connection pool?
- Are special characters in the password properly encoded if using a URI?
- Does the driver read the intended environment variable or configuration file?

In a URI, reserved characters such as `@`, `:`, `/`, `?`, `#`, and `%` must be percent-encoded when they appear in the username/password component. When possible, prefer passing secrets separately or via a secret manager rather than embedding passwords in URLs.

Avoid using the `PGPASSWORD` environment variable in multi-user environments because process environments can be exposed through system tools. With libpq, you can use a `.pgpass` password file or `PGPASSFILE` with restricted file permissions. On Unix, the file typically requires `0600` permissions; on Windows, libpq uses `%APPDATA%\postgresql\pgpass.conf`.

## 8. Reading PostgreSQL Logs for Server-Side Root Causes

Server-side logs often provide details the client does not show, especially when a proxy or driver collapses multiple errors into one message.

Depending on deployment, view logs via:

- `journalctl` or service logs on Linux.
- Event Viewer and PostgreSQL logs on Windows.
- `docker logs` if PostgreSQL runs in a container.
- Cloud provider database, audit, or connection logs.
- Kubernetes pod logs and centralized logging systems.

If permitted, you can temporarily enable `log_connections` during diagnostics to record connection attempts and authentication outcomes. Consider log volume, load, and security policy; disable or revert the setting afterward if it was only a temporary change.

Correlate logs by timestamp, client address, database, and role. Messages like the following help classify the issue:

- `no pg_hba.conf entry for host ...`: check HBA rules, source IP, database, role, and SSL state.
- `password authentication failed for user ...`: check password, role, secret, and auth method.
- `role ... does not exist`: check username and target cluster.
- `database ... does not exist`: check database name and endpoint.
- `too many connections`: check session counts, connection pool, and connection limits.
- Errors reading certificate or private key: check path, owner, file permissions, and certificate chain.
- Server restart or crash at the exact time of the error: check OS logs, container logs, and failover events.

Do not enable password logging. PostgreSQL does not need to log plaintext passwords to diagnose login failures.

## 9. Running an End-to-End Check from Client to Server

Use the same hostname, port, database, and user as the application. Follow the steps in order to pinpoint which exact layer fails.

### Step 1: Confirm Application Configuration

Check host, port, database, user, sslmode, and secret source. Do not print passwords to the terminal or logs. Confirm the application is pointing to the right endpoint and environment.

### Step 2: Check DNS

Use `getent`, `dig`, or `Resolve-DnsName`. Record all returned IPs and test the hostname from the exact container or application host.

### Step 3: Check TCP

Use `nc -vz` or `Test-NetConnection`. If TCP fails, focus on routing, firewall, security group, port, and listener.

### Step 4: Check Whether PostgreSQL Accepts Connections

~~~bash
pg_isready -h db.example.internal -p 5432 -d appdb -U app_user
~~~

If the server is rejecting or not responding, check service status and logs. If the server accepts connections, proceed to check TLS and authentication.

### Step 5: Test Login with psql

~~~bash
psql "host=db.example.internal port=5432 dbname=appdb user=app_user connect_timeout=5 sslmode=verify-full sslrootcert=/etc/postgresql/certs/root-ca.crt"
~~~

The command will prompt for a password if the authentication method requires one. If the client does not use libpq or does not have the CA at that path, adjust for your actual driver and trust store.

### Step 6: Check HBA and Server Logs

If you see `no pg_hba.conf entry`, check the source address seen by the server, database, role, host/hostssl, and rule order. Verify the file using `pg_hba_file_rules`, reload, and retry.

### Step 7: Check Role and Privileges

If you see a password error, verify the role, secret, auth method, and password expiration. If authentication succeeds but you cannot enter the database, verify the database exists and check the CONNECT privilege.

### Step 8: Re-check the Application and Pool

Once `psql` succeeds from the exact environment, check the driver, TLS configuration, environment variables, secret cache, connection pool, and when the application creates connections. An application may continue failing if the process or pool has not picked up the new configuration.

## 10. Common Scenarios

### Scenario A: Local Connections Work, but Remote Application Connections Time Out

Local connections use a Unix socket or loopback and do not traverse network firewalls. Check `listen_addresses`, listeners on private IPs, routing, security groups, and firewalls. Then verify the actual source IP and HBA rules.

### Scenario B: TCP Works, but Server Reports no pg_hba.conf entry

The TCP path has reached PostgreSQL. Verify the source IP seen by the server, database, user, SSL mode, and line order. Add a narrow, appropriate rule to the active HBA file, check syntax, reload, and read the logs.

### Scenario C: Only Production Applications Fail After Password Rotation

The secret store may have changed while an application instance or connection pool still holds the old password. Check secret version, username, host, and deployment time; update configuration and refresh the pool per procedure. Do not broaden HBA if the error is password authentication failed.

### Scenario D: Connecting by IP Works, but Hostname Fails with a Certificate Error

Check the hostname in the connection string and the certificate's SAN. Use the DNS endpoint issued for the database or reissue the certificate with the matching SAN. If you need to test DNS independently, use `hostaddr` while keeping `host` set to a valid hostname for TLS verification.

### Scenario E: Connection Works When SSL Is Disabled

This suggests an issue with TLS negotiation, CA, certificates, or SSL configuration. Check server-side `ssl`, client-side CA, certificate expiration, hostname, and `hostssl` requirements in HBA. Do not leave `sslmode=disable` as a production solution.

### Scenario F: Errors Appear Only Intermittently

If DNS returns multiple IPs, test each node individually. If using a load balancer or proxy, check health checks and backend endpoints. Correlate errors with failovers, restarts, certificate updates, connection limits, backups, or firewall changes. One address in a DNS pool or one backend may be configured differently from the other nodes.

### Scenario G: Server Reports too many connections

This is a resource-limit issue, distinct from DNS or password problems. Inspect sessions:

~~~sql
SELECT
    usename,
    datname,
    state,
    count(*) AS connections
FROM pg_stat_activity
GROUP BY usename, datname, state
ORDER BY connections DESC;
~~~

Check the number of application connections, number of pool instances, and max pool size configuration. You can use PgBouncer or pool limits to control backend counts. Do not increase `max_connections` immediately without evaluating RAM and per-backend overhead.

## 11. Risky Approaches to Avoid

- Do not set HBA to `trust` to bypass authentication.
- Do not open `0.0.0.0/0` or `::/0` just to test connectivity.
- Do not permanently disable TLS when encountering a certificate error.
- Do not delete WAL files, data files, or replication slots to fix connection errors.
- Do not restart the database repeatedly without reading logs and identifying which parameters require a restart.
- Do not repeatedly change passwords when the actual error is a timeout or DNS issue.
- Do not edit a guessed `pg_hba.conf` file without checking `SHOW hba_file`.
- Do not treat `pg_isready` returning ready as proof that authentication and database privileges are correct.
- Do not log passwords, private keys, or full connection URIs containing secrets.

Every change should have a narrow scope, a clear reason, and a post-change verification step. For production systems, record before/after configuration and follow your operations team's change process.

## 12. Connection Troubleshooting Checklist

- [ ] Recorded the full error message, timestamp, and originating environment.
- [ ] Confirmed the application's host, port, database, user, and sslmode.
- [ ] Checked DNS from the exact host or container running the application.
- [ ] Checked TCP connectivity to the exact IP and port.
- [ ] Confirmed PostgreSQL is listening on the required interface and port.
- [ ] Checked routing, firewall, security groups, NAT, and NetworkPolicy.
- [ ] Checked TLS, CA, SAN, certificate expiration, and private key if used.
- [ ] Verified the active HBA file, source address, database, role, and rule order.
- [ ] Checked for syntax errors with `pg_hba_file_rules` and reloaded configuration when needed.
- [ ] Checked role LOGIN attribute, password, auth method, and password expiration.
- [ ] Checked database existence and CONNECT privilege.
- [ ] Correlated PostgreSQL logs with application logs.
- [ ] Checked connection pools and secret caches after changes.
- [ ] Confirmed connectivity again using the application's actual environment and driver.

## Conclusion

PostgreSQL connection errors should be classified by layer. DNS determines which IP the client looks up; the TCP network and listener determine whether the client reaches the PostgreSQL process; TLS protects and verifies the connection; `pg_hba.conf` determines which connections are allowed to attempt authentication; and role, password, and database privileges determine whether the user can open a session.

Check sequentially from client to server, using logs and tests from the application's actual environment. Once you know which layer failed, small, verified changes will restore connectivity faster while preserving the database's security policy.
