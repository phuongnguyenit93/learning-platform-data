# Can't Connect, Connection Refused, and Address/Socket Resolution Errors

When an application fails to connect to MySQL, messages like `Can't connect to MySQL server`, `Connection refused`, `Unknown MySQL server host`, or `Can't connect through socket` are often lumped together as a generic database error. However, each message points to a different layer: the hostname cannot be resolved, the network path does not reach the destination, no process is listening on the port, the local socket path is wrong, or MySQL failed to start.

Diagnose along the connection path: **application → DNS/address → network and firewall → TCP port or Unix socket → MySQL listener → authentication and TLS**. Once you pinpoint the first failing layer, fixing the issue becomes much faster and avoids unnecessary changes.

## 1. Distinguishing Connection Error Categories

Common MySQL client error codes:

| Code / Message | Common Meaning | First Layer to Check |
|---|---|---|
| `2005: Unknown MySQL server host` | The client cannot resolve the hostname to an address. | DNS, service name, search domain, hostname configuration. |
| `2003: Can't connect to MySQL server` | Cannot establish a TCP connection to the host/port. | Address, route, firewall, listener, port, and bind address. |
| `2002: Can't connect through socket` | Local client cannot open the Unix socket, or the socket does not exist / is inaccessible. | Socket path, file permissions, server process, and client protocol selection. |
| `Connection refused` | The target or a network device explicitly refused the connection; usually no listener on that address/port. | MySQL service, port, bind address, container port mapping, and firewall reject rules. |
| `Connection timed out` | No connection response received within the timeout window. | Firewall drop, route, security group, network policy, or unresponsive target host. |
| `1045: Access denied` | Reached MySQL, and the server rejected authentication/login privileges. | User, host pattern, password, authentication plugin, and TLS policy. |
| `1040: Too many connections` | MySQL accepted the connection attempt, but all allowed connection slots are full. | `max_connections`, connection leaks, pool sizing, and workload. |
| `1129: Host ... is blocked` | MySQL blocked the host after repeated connection errors via the host cache mechanism. | Source of repeated errors, host cache, and network policy. |
| `2006: MySQL server has gone away` | The connection dropped or the server is no longer responding when the client performs an operation. | Server restart/crash, idle timeout, packet size, and network. |
| `2013: Lost connection to MySQL server during query` | The connection was lost while a query was executing. | Server error log, long query, network interruption, timeout, and packet size. |

Error codes may be wrapped by frameworks or drivers, so the outer message does not always preserve the raw MySQL code. Record the root exception, `SQLState`, vendor error code, hostname, port, and timestamp. Do not log passwords or full JDBC URLs containing secrets.

## 2. Start from the Application Connection Configuration

Before inspecting the server, verify where the application is actually trying to connect. Common configuration mistakes include:

- Stale hostname after switching environments or endpoints.
- Wrong port between MySQL Classic Protocol (`port`, usually `3306`) and X Protocol (`mysqlx_port`, usually `33060`).
- Application container using `localhost` instead of the MySQL container's hostname/service name.
- JDBC URL containing a different hostname, port, database, or TLS property than the configuration assumed to be active.
- Environment variables not loaded, wrong Spring Boot profile active, or outdated secret/ConfigMap.
- DNS cache or connection pool still holding an old address after an endpoint change.

With Connector/J, a typical Classic Protocol URL:

```properties
spring.datasource.url=jdbc:mysql://mysql-db.internal:3306/appdb
spring.datasource.username=app_runtime
spring.datasource.password=${DB_PASSWORD}
```

The address `mysql-db.internal` and port `3306` are only examples. Check the effective runtime values rather than just reading default config files. If using Spring profiles, environment variables, or a secret manager, confirm which profile and config source are active in the failing process.

If the error occurs in only one application instance, compare its configuration, DNS resolution, and network routes against a healthy instance. Do not change global database configuration when the issue is isolated to one pod, container, or application host.

## 3. Checking Hostname and DNS

If the error says `Unknown host`, check hostname resolution before checking passwords or grants. If a hostname cannot be resolved, the client cannot even open a connection to MySQL.

On Linux:

```bash
getent ahosts mysql-db.internal
nslookup mysql-db.internal
```

On Windows PowerShell:

```powershell
Resolve-DnsName mysql-db.internal
```

Verify:

1. Is the hostname spelled correctly and in the right environment domain?
2. Does the DNS record exist and return the expected address?
3. Does the application use a different DNS resolver/search domain than the admin workstation?
4. Are there multiple IPv4/IPv6 addresses, and are all returned addresses reachable?
5. Was the endpoint recently changed while a DNS cache or connection pool has not refreshed yet?

If the hostname resolves to both IPv4 and IPv6, test connectivity to each address. DNS might return IPv6 while MySQL only listens on IPv4, or a firewall might allow only one address family. Testing by IP address helps isolate DNS, but that is only a diagnostic step; production configuration should keep using a stable service name when required by the architecture.

In Docker Compose, services on the same network usually reach each other by service name. For example, from an application container connect to `db:3306`; `localhost` inside the application container refers to the application container itself, not the MySQL container. From the host machine, use the published port, such as `127.0.0.1:3307` if Compose maps `3307:3306`.

## 4. Checking the TCP Port from the Client Side

Once the hostname resolves, verify that a TCP connection can be opened to the right port.

On Linux/macOS you can use:

```bash
nc -vz mysql-db.internal 3306
```

Or:

```bash
telnet mysql-db.internal 3306
```

On Windows PowerShell:

```powershell
Test-NetConnection -ComputerName mysql-db.internal -Port 3306 -InformationLevel Detailed
```

Interpret the output as follows:

- `TcpTestSucceeded: True` or `succeeded`: TCP handshake succeeded; proceed to check MySQL protocol, TLS, and authentication.
- `Connection refused`: the target address responded, but nothing is listening on that port or a network device is actively rejecting it.
- `Timed out`: packets may be dropped or the route cannot reach the target; check firewalls, security groups, network ACLs, and routing.
- `No route to host`/`Network is unreachable`: check routing, subnet, gateway, and network interfaces.

A successful TCP test does not prove the username/password is valid or that MySQL queries work. It only confirms the TCP path to the endpoint is open.

If failures occur on only one network, compare tests from a host in the same subnet as MySQL and from the application host. If connecting from an admin machine works while the application subnet fails, inspect firewall/security group rules for that specific source-destination pair.

## 5. Verifying the MySQL Service Is Running

On the MySQL server host, check the service first:

```bash
sudo systemctl status mysqld
```

On some distributions, the service name is `mysql`:

```bash
sudo systemctl status mysql
```

If the service is not running, inspect status and logs before repeatedly restarting:

```bash
sudo journalctl -u mysqld -n 100 --no-pager
```

If the service is named `mysql`, substitute the corresponding unit name. You can locate the MySQL error log via `log_error`:

```sql
SHOW VARIABLES LIKE 'log_error';
```

Common reasons the service fails to start include bad configuration, port already in use, wrong data directory permissions, full disk, invalid InnoDB/redo files, failed plugin loading, or post-upgrade errors. The error log usually gives a far more specific cause than the application error message.

Do not arbitrarily delete files in the data directory, socket files, or PID files just to force the service to start. Before modifying any file, verify that the MySQL process is stopped and understand how the service manages that file.

## 6. Checking That MySQL Listens on the Right Address and Port

When the service is running, verify the listener at the OS level.

Linux:

```bash
sudo ss -lntp | grep 3306
```

Or:

```bash
sudo netstat -lntp | grep 3306
```

Windows PowerShell:

```powershell
Get-NetTCPConnection -LocalPort 3306 -State Listen
```

If there is no listener, inspect MySQL configuration:

```sql
SHOW VARIABLES LIKE 'port';
SHOW VARIABLES LIKE 'bind_address';
SHOW VARIABLES LIKE 'skip_networking';
SHOW VARIABLES LIKE 'socket';
```

The SQL queries above require an existing local connection or another admin session. If you cannot connect at all, read the server configuration files and error log to determine effective values.

Key meanings:

- `port`: Classic Protocol port the server uses to accept TCP connections.
- `bind_address`: interface address to which MySQL binds its listener. If bound only to loopback, clients on other hosts cannot connect over private/public interfaces.
- `skip_networking`: when enabled, MySQL does not accept TCP/IP connections; local connections via Unix socket may still work.
- `socket`: Unix socket path on Unix-like operating systems.

Do not set `bind_address=0.0.0.0` or expose the port on all interfaces just to test without controlling firewalls and source access. Choose the required private interface or address, then restrict firewall rules to the application subnet.

If port `3306` is already in use by another process, MySQL may fail to bind and log `Address already in use` in the error log. Identify the process holding the port before deciding to change ports or stop another service.

## 7. Distinguishing TCP from Unix Socket

On Linux/macOS, the MySQL client can connect locally via a Unix domain socket or TCP. When given `localhost`, some command-line clients default to the Unix socket; when given `127.0.0.1`, the client uses TCP. This explains why `mysql -h localhost` succeeds while `mysql -h 127.0.0.1` fails, or vice versa.

Force the client to use TCP:

```bash
mysql --protocol=TCP -h 127.0.0.1 -P 3306 -u app_runtime -p
```

Force the client to use the Unix socket:

```bash
mysql --protocol=SOCKET \
  --socket=/var/run/mysqld/mysqld.sock \
  -u app_runtime -p
```

Replace the socket path in the example with the actual server/client value. Check the server `socket` variable and the client socket option; both sides must point to the exact same socket file. Additionally, the OS user running the application must have permissions on the parent directory and socket file.

Common causes of socket errors:

- MySQL has not started yet, so the socket has not been created.
- Server created the socket at `/var/lib/mysql/mysql.sock` while the client looks at `/var/run/mysqld/mysqld.sock`.
- Stale socket file left behind after a crash with no server listening.
- Directory/socket permissions deny access to the application OS user.
- Client is forcing `SOCKET` while the server is only reachable over TCP or a different socket path.

On Windows, local protocols may include TCP, named pipes, or shared memory depending on configuration. Do not apply Unix socket paths on Windows; use the protocol and pipe name configured on both client and server.

Note: Connector/J connects to MySQL over TCP/IP and does not use Unix sockets the way the `mysql` CLI can. Therefore, testing `localhost` via socket with the CLI does not prove a TCP JDBC URL will work.

## 8. Checking Firewalls, Security Groups, and Network Policies

If MySQL is listening on the expected interface/port but the client still cannot connect, inspect the network layer on both ends:

- Host firewall: `firewalld`, `ufw`, Windows Defender Firewall, or `iptables`/`nftables`.
- Cloud security group / network security group: inbound rule for the MySQL port from the application's exact subnet or security identity.
- Network ACLs, route tables, VPNs, peering, and gateways between subnets.
- Kubernetes `NetworkPolicy`, Service selector, endpoints, and service ports if running in a cluster.
- Client-side firewall or intermediate proxy blocking outbound traffic.

Open only the required port for the required source. For example, if the application resides in subnet `10.20.0.0/16`, the inbound rule should restrict the source to that subnet or security group rather than `0.0.0.0/0`. Port `3306` should not be exposed directly to the public Internet.

If possible, inspect packets on both client and server using approved network tools. If `SYN` reaches the server without a `SYN-ACK`, check the listener and host firewall. If `SYN` never reaches the server, investigate routing or intermediate firewalls. If the server sends `RST`, typically nothing is listening on that destination address/port or an intermediate device is actively rejecting it.

## 9. Checking Docker and Kubernetes

### Docker Compose

A common configuration:

```yaml
services:
  app:
    build: .
    environment:
      DB_HOST: db
      DB_PORT: 3306
    depends_on:
      db:
        condition: service_healthy

  db:
    image: mysql:8.4.4
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}
      MYSQL_DATABASE: appdb
    ports:
      - "3307:3306"
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "127.0.0.1", "-uroot", "-p${MYSQL_ROOT_PASSWORD}"]
      interval: 5s
      timeout: 3s
      retries: 20
```

Inside the Compose network, `app` connects to `db:3306`. From the developer host machine, connect to `127.0.0.1:3307`. Host port `3307` is mapped to container port `3306`; using `localhost:3306` from the `app` container points back to the `app` container itself.

`depends_on` with `condition: service_healthy` waits for the healthcheck when Compose supports it, but it does not replace application-level retries. The database may restart after the app starts, or the healthcheck may only confirm the server responds locally without proving the application user/schema is ready.

Checks:

```bash
docker compose ps
docker compose logs db
docker compose exec db mysqladmin ping -h 127.0.0.1 -uroot -p
```

Do not put real passwords directly in commands or shell history; the last example uses an interactive password prompt. Confirm the container is healthy and port mappings are correct with `docker compose ps`.

### Kubernetes

If the application runs in Kubernetes, connect via the Service DNS name, such as `mysql.database.svc.cluster.local`, rather than a Pod IP. Check:

1. Does the Service selector match the MySQL Pod labels?
2. Do the Service `port` and `targetPort` point to the correct listener port?
3. Does the `EndpointSlice` contain a Ready Pod endpoint?
4. Does any `NetworkPolicy` allow traffic from the application namespace/pod to the database?
5. Does the readiness probe accurately reflect MySQL's readiness to accept connections?

A Service with no Ready endpoints can cause timeouts or connection failures even when the MySQL Pod exists. Test DNS from inside the application Pod itself, because resolvers and search domains inside a Pod can differ from a local machine.

## 10. After TCP Connects: Distinguishing Network Errors from Auth Errors

Once the TCP handshake succeeds, the client exchanges the MySQL protocol handshake, negotiates TLS (if enabled), and authenticates. If you receive `1045 Access denied`, the connection already reached MySQL; focus on user, host, password, plugin, and grants instead of continuing to tweak firewalls.

MySQL distinguishes accounts by the `(user, host)` pair. Example:

```sql
CREATE USER 'app_runtime'@'10.20.%' IDENTIFIED BY 'managed-secret';
GRANT SELECT, INSERT, UPDATE, DELETE ON appdb.*
TO 'app_runtime'@'10.20.%';

SHOW GRANTS FOR 'app_runtime'@'10.20.%';
```

This example only illustrates how account host patterns work; create the account matching the actual source address and grant least-privilege permissions. If the application traverses NAT, a proxy, or a Kubernetes egress gateway, MySQL may see a different source IP than the Pod IP.

Check authentication plugins and TLS if errors appear after a driver or server upgrade. Connector/J and MySQL must support a compatible authentication method. With TLS, verify the CA, certificate hostname, trust store, and verification policy; never disable certificate verification in production just to bypass a handshake error.

If the error is `1040 Too many connections`, check:

```sql
SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Max_used_connections';
SHOW VARIABLES LIKE 'max_connections';
SHOW FULL PROCESSLIST;
```

Look for connection leaks, pools creating too many connections across many instances, transactions holding connections for too long, or sudden workload spikes. Raising `max_connections` without checking RAM and OS limits can overload the server further.

## 11. Checking the MySQL Host Cache and Blocked Hosts

MySQL tracks connection errors per host. If errors exceed `max_connect_errors`, the server can block that host and return error `1129`. Investigate the source of repeated failures before clearing the block state:

```sql
SHOW VARIABLES LIKE 'max_connect_errors';

SELECT
    IP,
    HOST,
    HOST_VALIDATED,
    SUM_CONNECT_ERRORS,
    COUNT_HOST_BLOCKED_ERRORS
FROM performance_schema.host_cache;
```

Column names in `performance_schema.host_cache` depend on the version. Inspect the table structure on the current server if the query fails. Fix the root cause—such as network flakiness, reverse DNS issues, or misbehaving client retries—before unblocking.

Once confirmed safe, on versions that still support it, an administrative account can run:

```sql
FLUSH HOSTS;
```

`FLUSH HOSTS` was deprecated in MySQL 8.0.23. On versions supporting direct operations on the Performance Schema host cache, the alternative is:

```sql
TRUNCATE TABLE performance_schema.host_cache;
```

Check the documentation and required privileges for your exact version before running it. Clearing the host cache only removes the current block state; it does not fix network, DNS, or broken client retry issues. Do not use these commands as a routine workaround if the host continues generating connection errors.

## 12. Connection Pools and Application Startup Timing

An application may start before MySQL or while MySQL is restarting. If the pool tries connecting only once, the application may stay in a broken state even after the database becomes ready.

Connection design should include:

- A finite connection timeout so requests do not hang indefinitely.
- Retries with backoff and jitter during startup or transient outages.
- Validation query / connection test appropriate for the pool and driver.
- Eviction of broken connections after failover or server restart.
- Pool sizing capped according to total instance count and MySQL's `max_connections`.
- Application readiness checks that reflect serving capability without triggering a continuous crash-restart loop during database maintenance.

With HikariCP, an illustrative configuration:

```yaml
spring:
  datasource:
    hikari:
      connection-timeout: 30000
      validation-timeout: 5000
      maximum-pool-size: 10
      minimum-idle: 2
```

Values must be based on workload and the system-wide connection budget. If 20 application instances each have a max pool size of 10, the database may need to handle up to 200 application connections, excluding jobs, admin sessions, and replication. A larger pool does not mean faster queries; too many concurrent connections can increase CPU, memory usage, and lock contention.

## 13. Ordered Diagnostic Procedure

Follow these steps in order and record results to pinpoint the failing layer:

1. **Verify endpoint**: read effective application configuration, hostname, port, protocol, and database.
2. **Resolve DNS**: confirm the hostname resolves to the right address from the application environment itself.
3. **Test TCP**: use `nc` or `Test-NetConnection` to the exact IP/port.
4. **Check server process**: confirm the MySQL service is running and read the error log.
5. **Check listener**: verify `port`, `bind_address`, `skip_networking`, and socket path.
6. **Check network policies**: host firewall, security groups, routes, container port mapping, or Kubernetes Service/NetworkPolicy.
7. **Test with MySQL client**: use the same host/port/protocol from the application environment with an authorized account.
8. **Classify protocol/auth errors**: `1045`, TLS handshake, authentication plugin, `1040`, or blocked host.
9. **Check pool and retries**: inspect connection lifetime, stale connections, startup ordering, and connection counts.
10. **Verify with logs and timestamps**: correlate application logs, MySQL error logs, firewall logs, and deploy/restart events.

A simple tracking table:

| Step | Result | Interpretation |
|---|---|---|
| DNS | Hostname returns expected IP | Proceed to network checks. |
| TCP | Port open from app host | TCP path to listener is working. |
| Service | MySQL active | Process is running; still verify listener. |
| Listener | Expected IP/port | MySQL is bound to the expected endpoint. |
| MySQL protocol | Server returns handshake | Client reached the MySQL protocol layer. |
| Authentication | Login succeeds | User/host/password/plugin/TLS are valid. |
| Query | Test query succeeds | Connection can execute SQL within granted privileges. |

## 14. Three Typical Troubleshooting Scenarios

### Scenario A: Application Reports Connection Refused

The application connects to `mysql-db.internal:3306` and receives `Connection refused`.

1. `Resolve-DnsName`/`getent ahosts` shows the hostname resolves properly.
2. `Test-NetConnection`/`nc` reports connection refused on port `3306`.
3. On the MySQL host, `systemctl status mysqld` shows the service failed.
4. The error log states the port is already used by another process.
5. Identify the process holding the port, verify whether it is an old MySQL instance or another service, resolve the conflict, and start MySQL per runbook.
6. Verify the listener and retry from the app host.

Do not "solve" this by opening firewall rules wider, because the cause is that the server failed to bind the port.

### Scenario B: localhost Works, but App Container Cannot Connect

MySQL runs on the host machine; `mysql -h localhost` succeeds, but the app container times out.

1. Confirm the CLI may be using the Unix socket because the hostname is `localhost`.
2. Run `mysql --protocol=TCP -h 127.0.0.1 -P 3306` on the host to test TCP.
3. Inside the app container, `localhost` refers to the app container itself.
4. Use service name `db` and internal port `3306` if both containers share a Compose network.
5. Inspect `docker compose ps`, healthcheck, logs, and network membership.

Outcome: change the app endpoint to `db:3306` instead of `localhost:3306` or the host's published port.

### Scenario C: TCP Opens, but Application Receives Access Denied

`nc -vz mysql-db.internal 3306` succeeds, but JDBC reports `1045`.

1. The DNS/TCP/listener path is already working.
2. Verify the actual username and secret the app is using.
3. Check whether a MySQL account exists with a host pattern matching the source IP the server sees.
4. Check authentication plugin, TLS requirements, and grants.
5. Grant proper permissions to the application account and verify directly from the app host.

No need to change port or bind address once the server already returned a handshake and rejected authentication.

## 15. Checklist Before Concluding Connection Errors Are Resolved

- [ ] Application uses the correct hostname, port, protocol, and configuration profile.
- [ ] Hostname resolves from the actual application machine/container/pod.
- [ ] TCP connection opens to the exact IP and port.
- [ ] MySQL service is running and the error log shows no startup/listener errors.
- [ ] `bind_address`, `port`, `skip_networking`, and socket path are appropriate.
- [ ] Firewalls, security groups, routes, and network policies allow only required sources.
- [ ] Docker/Kubernetes service name, port mapping, and endpoints are verified.
- [ ] Client protocol matches: TCP, Unix socket, or named pipe.
- [ ] If `1045` occurred, user/host/password/plugin/TLS were verified.
- [ ] If `1040` occurred, connection pool and total connection budget were reviewed.
- [ ] Pool has appropriate timeouts, validation, and retries; stale connections are evicted.
- [ ] Connectivity confirmed via an actual query using the application account.

MySQL connection failures must be addressed at the exact failing layer. `Unknown host` points to DNS; `Connection refused` points to listener/port or network rejection; socket errors point to protocol and socket path; timeouts point to routing/firewalls; `1045` is an authentication failure after reaching the server. By documenting the endpoint, step-by-step test results, and corresponding logs, operations teams can isolate the root cause quickly, fix the right component, and avoid overly broad network or security changes.
