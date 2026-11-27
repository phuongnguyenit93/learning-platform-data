# Connection Protocol, Sessions, and URI Structure in PostgreSQL

## 1. A Connection URL Is More Than Just a "Database Address"

When a Java application connects to PostgreSQL, developers often see a short string:

~~~text
jdbc:postgresql://db.example.internal:5432/shopdb
~~~

Or when using a tool based on **libpq**:

~~~text
postgresql://app_reader@db.example.internal:5432/shopdb?sslmode=verify-full
~~~

Behind this string lies a multi-layered sequence of operations: host resolution, DNS or Unix-domain socket, creating a TCP connection, negotiating TLS if configured, exchanging PostgreSQL protocol messages, authenticating using the method requested by the server, opening a session, executing SQL statements, and managing transaction state. If the application uses a connection pool, the `Connection` object a developer receives may even be **a checkout (lease)** of an existing physical connection rather than a newly created database session.

Common errors stem from confusing these layers:

- "The machine is pingable" yet PostgreSQL is not listening on the TCP port.
- TCP connects, yet the server rejects it according to `pg_hba.conf`.
- Username/password are correct, yet the TLS certificate does not match the hostname.
- SQL executes successfully, yet the application leaves the transaction open, causing locks and VACUUM pressure.
- After returning a connection to the pool, the session still retains `search_path` or unwanted configuration variables.
- Using the same connection URI, yet the Java JDBC library and libpq **do not** interpret every option identically.
- Using transaction pooling while still relying on temporary tables, session-level `SET`, or prepared statements that persist across multiple checkouts.
- Putting a password directly in the URI and accidentally leaking it in logs, crash reports, or shell history.

**Goal:** thoroughly understand the protocol and state levels in order to choose connections that are correct, secure, observable, and operationally stable.

### 1.1. Learning Outcomes

After this lesson, you will be able to:

1. Distinguish between **client driver**, **TCP/Unix socket**, **TLS**, **PostgreSQL wire protocol**, **authentication**, **backend process**, and **SQL transaction**.
2. Describe startup, authentication, `ParameterStatus`, `BackendKeyData`, and `ReadyForQuery` messages.
3. Explain the **simple query protocol** and **extended query protocol** with `Parse`, `Bind`, `Execute`, and `Sync`.
4. Read and write connection strings accurately in URI format following libpq syntax, including escaping special characters.
5. Distinguish between **libpq URI**, **key=value connection string**, **JDBC URL**, and environment variables/tools.
6. Choose `sslmode`, manage CAs, verify hostnames, and understand how SCRAM and TLS differ.
7. Explain **session**, **transaction**, **statement**, **connection pool checkout**, and state retained across transactions.
8. Diagnose DNS/TCP, authentication, TLS, database/role, capacity, timeout, and pooling errors.
9. Use `pg_stat_activity`, `pg_stat_ssl`, `SHOW`, `pg_backend_pid()`, and several `psql` commands to inspect sessions.
10. Write safe Java JDBC examples using parameterized queries, transaction boundaries, and proper pooling.
11. Understand multi-host URIs, failover, read/write routing, and the limitations of connection strings.
12. Complete exercises with solutions for real-world deployment scenarios.

> **Scope:** this lesson presents common behavior of PostgreSQL protocol version 3 and modern libpq/JDBC. Some options depend on the specific PostgreSQL/client-driver version or platform. In production deployments, verify against your exact **client and server** versions; do not assume every PostgreSQL-compatible proxy supports the full protocol and all session features.

---

## 2. The Multi-Layer Picture of a Single Connection

~~~mermaid
flowchart TD
    A["Java application / psql / pgAdmin"] --> B["Client driver: JDBC or libpq"]
    B --> C["Read configuration: host, port, database, user, TLS"]
    C --> D["DNS, TCP, or Unix-domain socket"]
    D --> E["TLS / GSS encryption negotiation if used"]
    E --> F["PostgreSQL StartupMessage"]
    F --> G["Authentication: SCRAM, peer, or valid method"]
    G --> H["BackendKeyData, ParameterStatus, ReadyForQuery"]
    H --> I["Connection session ready to execute SQL"]
    I --> J["Transaction / statements / results"]
    J --> K["COMMIT/ROLLBACK, pool release, or close connection"]
~~~

### 2.1. Four Questions That Must Be Separated

| Question | Component Responsible | Example Error |
|---|---|---|
| Can the endpoint be found and connected to? | DNS, TCP/port, Unix socket, firewall | Connection refused / timeout |
| Is the connection encrypted and is the server verified? | TLS, CA, hostname validation | Certificate verify failed |
| Is the client allowed to log in to the database? | `pg_hba.conf`, role, auth method, credentials | No pg_hba.conf entry / password authentication failed |
| Within the session, does the SQL have the right permissions and data access? | `GRANT`, ownership, RLS, SQL transactions | Permission denied for table / row filtered by RLS |

An error at a lower layer must be resolved at that layer. If TCP does not even connect, changing the PostgreSQL password will not help.

### 2.2. A Driver Is Not the Database Server

- **PostgreSQL server** accepts connections and executes SQL.
- **JDBC driver** implements the protocol to interact with PostgreSQL from Java.
- **libpq** is the native PostgreSQL client library used by `psql` and many other tools.
- **PgBouncer/proxy** may sit between the client and PostgreSQL, changing how connections and sessions map.
- **Connection pool** inside the application may reuse physical connections.

Not every feature of `libpq` is automatically present in `pgJDBC`. Two clients may both speak the PostgreSQL wire protocol while exposing **different APIs and configuration parameters**.

---

## 3. TCP Connections and Unix-Domain Sockets

### 3.1. Host and Port

The default PostgreSQL port is **5432** unless configured otherwise. A TCP-style endpoint consists of a host/IP and a port:

~~~text
db.example.internal:5432
127.0.0.1:5432
[2001:db8::10]:5432
~~~

`localhost` may be resolved by the operating system/driver to IPv4 `127.0.0.1` or IPv6 `::1`. If the server only listens on one of them, results can differ; check both the address the server listens on and the one the client chooses.

### 3.2. Server `listen_addresses`

The `listen_addresses` parameter controls the network addresses PostgreSQL listens on; `port` controls the port. Check in SQL if you already have connection access:

~~~sql
SHOW listen_addresses;
SHOW port;
~~~

For example, `listen_addresses='localhost'` typically accepts only local TCP connections, not connections from an external application machine.

Do not change it to `'*'` just to "fix a connection failure" without controlling firewalls, private networking, `pg_hba.conf`, and TLS.

### 3.3. Local Socket Connections on the Server

On Unix-like systems, PostgreSQL can support **Unix-domain sockets**. With libpq, when no network host is specified (and depending on build/platform configuration), a local connection may go over a socket instead of TCP.

Example libpq key/value format:

~~~text
host=/var/run/postgresql dbname=shopdb user=app_reader
~~~

Here `host` is a **socket directory**, not a DNS hostname. `pg_hba.conf` distinguishes `local` (Unix socket) from `host`/`hostssl` (TCP).

### 3.4. A Unix Socket Is Not Equivalent to TLS

A Unix-domain socket is local IPC; it does not traverse TCP/TLS the way a remote TCP connection uses TLS. Access control may depend on file/socket permissions and authentication such as `peer`. You must evaluate local OS permissions rather than labeling it "absolutely secure".

### 3.5. What JDBC Needs to Watch Out For

pgJDBC normally uses TCP to a host/port and does not default to libpq's local Unix socket handling. Connecting via a Unix socket from Java may require a socket factory/extension or specific driver/version capabilities. Do not copy libpq's `host=/var/run/postgresql` URI into a JDBC URL assuming the driver will understand it automatically.

### 3.6. NAT, Proxies, and Cloud Endpoints

A DNS name may point to a load balancer/proxy while the real PostgreSQL backend lives on another host. If using TLS hostname verification, the name must match the certificate of the actual endpoint; if a proxy terminates and re-encrypts TLS, you need a threat model for **both hops**.

---

## 4. Overview of the PostgreSQL Wire Protocol

### 4.1. Protocol Version 3

Modern PostgreSQL primarily uses **frontend/backend protocol version 3.x**. The client sends structured binary messages as defined; the server responds with status, errors, row descriptions, data, and completion signals.

This is not like an HTTP REST API:

~~~text
HTTP: GET /api/orders -> JSON
PostgreSQL: Startup/Auth -> Query/Parse/Bind/Execute -> DataRow/CommandComplete/ReadyForQuery
~~~

The driver handles most messages; applications usually do not need to write a protocol parser.

### 4.2. Stateful Connections

A PostgreSQL connection has state: authenticated role, current database, configuration parameters, transaction status, prepared statements, temporary objects, and backend identity. Therefore, arbitrarily "switching the connection to another server" between two SQL statements can alter semantics.

### 4.3. Summary of Message Groups

| Group | Frontend or Backend | Purpose |
|---|---|---|
| SSLRequest / GSSENCRequest | Client | Propose setting up the corresponding transport security |
| StartupMessage | Client | Request opening a session with user, database, and startup parameters |
| Authentication* | Server/client | Execute the chosen authentication mechanism |
| ParameterStatus | Server | Report certain session parameters |
| BackendKeyData | Server | Data used to identify the backend for cancel requests |
| ReadyForQuery | Server | Finish a processing cycle and report transaction status |
| Query | Client | Simple Query protocol |
| Parse, Bind, Describe, Execute, Sync | Client | Extended Query protocol |
| RowDescription, DataRow | Server | Row descriptions and row data |
| CommandComplete | Server | Command finished and command tag |
| ErrorResponse, NoticeResponse | Server | Errors/notices |
| NotificationResponse | Server | LISTEN/NOTIFY notifications |

This list does not enumerate every message type. Drivers/proxies must conform to the protocol for the versions they support.

### 4.4. Do Not Parse SQL Data by Splitting Strings

The protocol has field encodings, message lengths, message types, and text/binary formats. Message ordering and error handling follow strict rules; you cannot implement a correct PostgreSQL client simply by opening a socket and sending raw SQL strings terminated by a newline.

---

## 5. Startup, TLS, and Authentication Handshake

### 5.1. High-Level Sequence

~~~text
Client                             PostgreSQL server
  |                                       |
  |--- TCP connect / local socket ------->|
  |                                       |
  |--- TLS request (if needed) ---------->|
  |<-- accept/reject ---------------------|
  |        TLS handshake if accepted      |
  |                                       |
  |--- StartupMessage: user, database --->|
  |<-- Authentication request -----------|
  |--- Credential/SASL exchange --------->|
  |<-- AuthenticationOk ------------------|
  |<-- ParameterStatus* ------------------|
  |<-- BackendKeyData --------------------|
  |<-- ReadyForQuery ---------------------|
  |                                       |
  |--- Query or Parse/Bind/Execute ------>|
  |<-- RowDescription, DataRow*, ... -----|
  |<-- ReadyForQuery ---------------------|
~~~

Depending on the authentication mechanism, proxy, encryption mode, and protocol extensions, the number of round trips varies. This is a **mental model**, not a full packet capture.

### 5.2. What Does StartupMessage Contain?

A protocol v3 StartupMessage carries the protocol version and parameter name/value pairs such as:

- `user`: database role requested.
- `database`: database to connect to.
- `application_name`: application name for server display/monitoring.
- Startup options supported by the server/client protocol.

The password is **not** sent in StartupMessage like a verbatim URL; authentication occurs through subsequent messages.

### 5.3. Authentication Is Not Always a Password

PostgreSQL can select a mechanism based on `pg_hba.conf` and supported methods: `scram-sha-256`, `peer` for local sockets, certificate-based auth, and other mechanisms. Do not assume every PostgreSQL connection must contain a username/password in the URI.

### 5.4. AuthenticationOk Does Not Guarantee SQL Permissions

After authentication and database-level access succeed, the role can enter the session, but SELECT/INSERT/UPDATE on individual objects still depends on `GRANT`, schema usage, ownership, Row-Level Security, and SQL privileges. "Connected successfully" does not equal "allowed to read every table".

### 5.5. ParameterStatus

The server may send `ParameterStatus` for certain session parameters. Client drivers use them to learn characteristics such as encoding, timezone-related settings, and values the driver needs for protocol/SQL handling.

Not every custom GUC is sent via `ParameterStatus`. To read a session setting in SQL, use `SHOW` or `current_setting`.

### 5.6. BackendKeyData and Cancel

The server sends identifying data so the client can request cancellation of a running query. **Do not treat** the process ID or cancel key as a session login token that allows executing SQL. A cancel request is a separate control path with its own limits and permissions; applications should use the driver's cancellation API rather than hand-crafting packets.

---

## 6. Ending a Query Cycle: ReadyForQuery

After completing a query cycle, the server sends `ReadyForQuery` to indicate it is ready for another cycle, along with the transaction status.

| Status | Protocol Indicator | Meaning |
|---|---|---|
| Idle | `I` | Not currently inside an explicit transaction block |
| In transaction | `T` | Inside a valid active transaction block |
| Failed transaction | `E` | Inside a failed transaction block; requires rollback or appropriate transaction control |

### 6.1. State E Causes Cascading Errors

Inside an explicit transaction:

~~~sql
BEGIN;

SELECT 1 / 0; -- division_by_zero

SELECT 42; -- fails again because the transaction is already aborted

ROLLBACK;
~~~

After the first error statement, PostgreSQL does not allow normal business SQL to run in the same transaction until the transaction is rolled back or handled with an appropriate savepoint.

A Java application must have `try/catch` and roll back when a transaction fails; returning a Connection to the pool in state `E` without cleanup is a serious bug.

### 6.2. "Auto-commit true" Does Not Mean No Transaction

Even a single SELECT statement in PostgreSQL runs under transaction semantics. With JDBC auto-commit typically defaulting to true, each statement completes/commits per driver semantics; with `setAutoCommit(false)`, the application explicitly manages transactions via `commit()` or `rollback()`.

### 6.3. One Query Request Differs From One Transaction

A Simple Query can carry multiple SQL statements, the extended protocol has its own cycle, and SQL transaction boundaries are still determined by `BEGIN`/`COMMIT`/`ROLLBACK` or the driver. Do not equate the number of network round trips with the number of transactions.

---

## 7. Simple Query Protocol

### 7.1. Model

The client sends a `Query` message containing SQL text:

~~~text
Frontend: Query("SELECT order_id FROM orders WHERE customer_id=101")
Backend:  RowDescription
          DataRow*
          CommandComplete
          ReadyForQuery
~~~

The driver decides whether to use the simple or extended protocol depending on the API/configuration. `psql` and different libraries may choose different paths.

### 7.2. Advantages and Limitations

Simple Query is easy to conceptualize, but does not provide the same `Bind` parameter mechanism as the extended protocol. Concatenating SQL strings from input remains vulnerable to SQL injection:

~~~text
SQL = "SELECT * FROM customers WHERE email='" + email + "'"
~~~

Do not use SQL text concatenation just because a protocol feels simpler.

### 7.3. Results the Server Can Return

A SELECT normally has a row description, data rows, and command completion. An UPDATE without RETURNING normally has command completion containing the affected row count; if a query errors, there is an `ErrorResponse`. Drivers translate these messages into rows/update counts/exceptions in the API.

### 7.4. Multiple Statements in One Query Message

The Simple Query protocol can contain multiple statements separated by semicolons. They have their own implicit transaction block and error-handling semantics; **do not** assume a multi-statement string is a safe replacement for explicit transactions and error management.

To guarantee atomicity across multiple business operations, manage transactions explicitly and understand how your client/driver executes batch statements.

---

## 8. Extended Query Protocol

### 8.1. Purpose

The extended protocol separates SQL preparation from parameter value binding. Key messages:

1. `Parse`: creates a prepared statement from SQL and type information.
2. `Bind`: supplies parameter values, creating a portal.
3. `Describe`: requests metadata describing the prepared statement/portal when needed.
4. `Execute`: executes the portal.
5. `Sync`: synchronizes the cycle; the server sends ReadyForQuery according to protocol rules.
6. `Close`: closes a statement/portal when the client needs to.

### 8.2. Illustrative Data Flow

~~~text
Client:
    Parse("SELECT name FROM customers WHERE id=$1")
    Bind(parameter 1 = 101)
    Describe(portal)
    Execute(portal)
    Sync

Server:
    ParseComplete
    BindComplete
    RowDescription
    DataRow*
    CommandComplete
    ReadyForQuery
~~~

This is an illustrative sequence; in practice there may be more or fewer messages such as Describe, NoData, PortalSuspended, Format codes, and others.

### 8.3. Parameters Are Data, Not SQL Identifiers

`$1` in PostgreSQL SQL represents a parameter value:

~~~sql
SELECT customer_id, customer_name
FROM app.customers
WHERE customer_id = $1;
~~~

You cannot use a parameter in place of a table or column name like this:

~~~sql
SELECT * FROM $1; -- invalid as a parameter identifier
~~~

Object names must be determined by the SQL text and properly allowlisted/quoted when dynamic. Values use bind parameters.

### 8.4. Text vs. Binary Formats

The extended protocol has format codes for values/results; many drivers use text format or binary format depending on data type and configuration. Do not assume all row values are UTF-8 text strings on the wire; the driver is responsible for decoding types properly.

### 8.5. Parse/Bind Differs From SQL-Level PREPARE

Protocol-level named prepared statements, unnamed statements, and SQL `PREPARE/EXECUTE` are related but not identical in API or lifetime. A driver may cache or switch to server-side preparation after a threshold, or always use unnamed statements. Exact pgJDBC details depend on version and settings such as prepare threshold.

### 8.6. Prepared Statements and Session Affinity

A named server-side prepared statement belongs to a single PostgreSQL session/backend. If a connection pool or proxy routes the next execution to a different backend, the prepared statement may **not exist on the new backend**, or the proxy needs its own tracking/preparation mechanism.

Do not conclude that "a JDBC PreparedStatement always remains on the server after the Java object is closed"—that is a driver/proxy implementation detail.

---

## 9. Protocol and SQL Injection Prevention

### 9.1. Using Prepared Statements

In JDBC:

~~~java
String sql =
    "SELECT customer_id, customer_name " +
    "FROM app.customers WHERE customer_id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, customerId);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong("customer_id"));
        }
    }
}
~~~

The question mark `?` in JDBC is a placeholder in the driver API; the driver compiles/translates it appropriately for the PostgreSQL protocol. Do not confuse the JDBC `?` symbol with PostgreSQL SQL's `$1` syntax.

### 9.2. What Does Parameterization Solve?

- Separates **command structure** from **data values**.
- Mitigates SQL injection caused by input being interpreted as SQL code.
- Helps the driver manage data types and bind parameters.
- Can support execution plan reuse under appropriate conditions.

### 9.3. Parameterization Does Not Replace Authorization

A safely parameterized query can still return data a user is not authorized to see if the application role has broad SELECT privileges and lacks RLS/tenant filters. Database authorization and API permission checks must still be designed separately.

### 9.4. Do Not Confuse URI Escaping With SQL Parameterization

Escaping `@` in a password to `%40` in a connection URI is **URI component encoding**, unrelated to binding values in a SQL statement. Both are required at **two different layers**.

---

## 10. libpq URI Format

### 10.1. General Structure

PostgreSQL libpq supports URIs of the form:

~~~text
postgresql://[user[:password]@][host][:port][/dbname][?param1=value1&param2=value2]
~~~

The scheme `postgres://` is also accepted by libpq in typical cases.

Example:

~~~text
postgresql://report_user@db.internal.example:5432/salesdb?sslmode=verify-full&application_name=reporter
~~~

### 10.2. Components

| Component | Example | Meaning |
|---|---|---|
| Scheme | `postgresql://` | Libpq connection URI |
| User | `report_user` | Requested PostgreSQL role |
| Password (optional) | `:secret@` | Credential; **avoid embedding** in URL |
| Host | `db.internal.example` | DNS name/IP/host value |
| Port | `5432` | TCP port |
| Database | `salesdb` | Database name |
| Query parameter | `sslmode=verify-full` | Client/TLS option |
| Query parameter | `application_name=reporter` | Application name |
| Query parameter | `connect_timeout=5` | Connection open timeout per libpq semantics |

### 10.3. Recommended Example: URI Without a Password

~~~text
postgresql://app_reader@db.internal.example:5432/shopdb?sslmode=verify-full&connect_timeout=5&application_name=orders-api
~~~

Retrieve passwords from a secret store, passfile, or separate parameter via driver/app configuration. **Do not log a URI after credentials have been added.**

### 10.4. Do Not Confuse Username With Database

~~~text
postgresql://alice@db.example.internal:5432/shopdb
~~~

`alice` is the role; `shopdb` is the database. The two strings do not have to be the same. If user/database are omitted, libpq applies defaults based on environment and specific configuration; do not assume every machine picks the same database.

### 10.5. Be Careful With IPv6

In the URI authority, an IPv6 literal needs square brackets so colons are not confused with the port:

~~~text
postgresql://app@[2001:db8::10]:5432/shopdb
~~~

This is an example documentation IPv6 address, not a real endpoint. With TLS verify-full, connecting by IP requires the certificate to match the IP per client rules; a DNS name is usually easier for certificate management.

---

## 11. Percent-Encoding: Special Characters in URIs

### 11.1. Why Is Encoding Needed?

When a username, database name, or password contains special characters, those characters can be confused with URI delimiters:

| Character | Escaped in URI | Meaning When Unescaped |
|---|---|---|
| Space | `%20` | Not valid literally in safe URI structure |
| `@` | `%40` | Separates userinfo and host |
| `:` | `%3A` | Separates user/password or host/port |
| `/` | `%2F` | Separates path |
| `?` | `%3F` | Starts query parameters |
| `&` | `%26` | Separates query parameters |
| `=` | `%3D` | Separates parameter name/value |
| `#` | `%23` | Fragment delimiter |
| `%` | `%25` | Prefix of percent-encoding |

A **hypothetical** example password `p@ss/word#1` is represented in a URI as `p%40ss%2Fword%231`:

~~~text
postgresql://demo:p%40ss%2Fword%231@db.example.internal:5432/shopdb
~~~

**Do not embed passwords directly in URLs in production.** Percent-encoding only ensures correct parsing; it is **not encryption or secret protection**. The full URI can still appear in logs, exceptions, shell history, and monitoring.

### 11.2. Encode Each Component, Not the Whole URL

Wrong: turning all structural characters `://?&=` into percent-encoded text, making the string unparseable as a URI.

Right: encode component values first, then place the proper delimiters.

### 11.3. Avoid Double-Encoding

If `@` becomes `%40` and is then encoded a second time into `%2540`, the client may decode it to the literal string `%40` instead of `@`. This is a subtle cause of password authentication failures.

### 11.4. Spaces and the `+` Sign

To avoid depending on differences between URI parsing and form-urlencoded conventions across tools, use `%20` for spaces in URI components rather than assuming `+` means the same thing in every parser.

---

## 12. Query Parameters in libpq URIs

### 12.1. Example With Multiple Options

~~~text
postgresql://app_reader@db.internal.example:5432/shopdb?sslmode=verify-full&connect_timeout=5&application_name=orders-api
~~~

Options serve distinct roles:

| Parameter | Meaning |
|---|---|
| `sslmode=verify-full` | Require TLS and verify certificate/hostname per libpq |
| `connect_timeout=5` | Time to wait when opening a connection, in seconds in libpq |
| `application_name=orders-api` | Tag session name for monitoring |
| `sslrootcert=...` | Client-side path to CA certificate |
| `options=...` | Startup options allowed by the server |
| `target_session_attrs=...` | Filter endpoints matching desired attributes when multiple hosts exist |

### 12.2. CA Path

~~~text
postgresql://app_reader@db.internal.example/shopdb?sslmode=verify-full&sslrootcert=%2Fetc%2Fpostgresql%2Fca.pem
~~~

`sslrootcert` here is a file on the **application/client machine**, not on the PostgreSQL server.

### 12.3. Startup Options

In appropriate environments, libpq allows `options` to pass startup parameters, for example:

~~~text
postgresql://app_reader@db.internal.example/shopdb?options=-c%20statement_timeout%3D5000
~~~

This illustrates percent-encoding of space and equals sign; you must check which settings the server allows and manage permissions accordingly.

### 12.4. The `&` Character in the Shell

When running commands in a shell, `&` can be a control character. Wrap the URI in quotes or use a config file instead of pasting unquoted. Do not put real passwords in command-line arguments because they can be recorded.

### 12.5. Do Not Mechanically Copy Options to JDBC

A libpq parameter may not exist, may have a different name, or may have different units in pgJDBC. Always consult the documentation of the exact client you are running, especially for SSL, timeouts, keepalives, and failover.

---

## 13. Unix-Domain Sockets in libpq URIs

### 13.1. Local Socket Directory

Libpq can specify a socket directory via `host`:

~~~text
host=/var/run/postgresql port=5432 dbname=shopdb user=app_reader
~~~

URI form:

~~~text
postgresql:///shopdb?host=%2Fvar%2Frun%2Fpostgresql&user=app_reader
~~~

`%2F` encodes the path separator in the parameter value. On different OSes/builds, the socket directory may differ; do not assume all servers have sockets at `/var/run/postgresql`.

### 13.2. Local Does Not Mean TCP Localhost

- `host=/var/run/postgresql`: Unix-domain socket.
- `host=localhost` or `host=127.0.0.1`: TCP loopback.
- Omitting host: libpq may choose a local socket on supported platforms, or another default.

The two paths can match **different** lines in `pg_hba.conf`: `local` versus `host`/`hostssl`.

### 13.3. `peer` Authentication

On a local Unix socket, the server can be configured with `peer` to map OS identity. Over TCP, the authentication method is chosen from HBA records for TCP connections; do not assume the same database role will use the same method.

### 13.4. JDBC Is a Different Case

pgJDBC normally uses TCP with standard URLs. Libpq's socket directory form does not automatically turn into a JDBC socket connection; some applications need a socket factory or driver/OS-specific configuration.

---

## 14. libpq key=value Strings

Besides URIs, libpq supports:

~~~text
host=db.internal.example port=5432 dbname=shopdb user=app_reader sslmode=verify-full connect_timeout=5 application_name=orders-api
~~~

### 14.1. Quoting Values

A value containing spaces can use quoting per libpq syntax:

~~~text
host=db.internal.example dbname=shopdb application_name='order processing worker'
~~~

**Do not** apply URI percent-encoding to the key/value form without understanding the connection string parser.

### 14.2. Why Explicit Configuration Is Better

If a client pulls host/user/database simultaneously from environment variables, a service file, and a URL, the effective choice can be hard to predict. Explicitly specify host, port, database, role, TLS mode, CA, timeout, and application name in managed configuration.

### 14.3. Do Not Put Credentials on the Command Line

Connection strings with passwords can be exposed via process listings, shell history, or error logs. Place secrets in mechanisms with restricted read permissions and ensure logging is redacted.

---

## 15. JDBC URLs Differ From libpq URIs

### 15.1. JDBC Form

~~~text
jdbc:postgresql://db.internal.example:5432/shopdb
~~~

Example with options:

~~~text
jdbc:postgresql://db.internal.example:5432/shopdb?sslmode=verify-full&ApplicationName=orders-api
~~~

`jdbc:postgresql://` is the syntax of the **PostgreSQL JDBC driver**, not a libpq URI. Even though both speak the PostgreSQL wire protocol, JDBC and libpq do not necessarily support the same set of properties.

### 15.2. Supplying Credentials via Properties

~~~java
String url = "jdbc:postgresql://db.internal.example:5432/shopdb";

Properties props = new Properties();
props.setProperty("user", System.getenv("DB_USER"));
props.setProperty("password", System.getenv("DB_PASSWORD"));
props.setProperty("sslmode", "verify-full");
props.setProperty("ApplicationName", "orders-api");

try (Connection connection = DriverManager.getConnection(url, props)) {
    System.out.println(connection.isValid(3));
}
~~~

This example requires importing `java.sql.*`, `java.util.Properties`, and having the PostgreSQL JDBC dependency in a real project. Environment variables are one deployment approach; production should use proper secret management and never print passwords.

### 15.3. Different Timeout Names and Units

- Libpq `connect_timeout`: time to wait while establishing a connection per libpq, in seconds.
- PgJDBC `connectTimeout`: corresponding driver parameter with its own rules.
- HikariCP `connectionTimeout`: time to wait to **borrow a connection from the pool**, typically in milliseconds.
- PostgreSQL `statement_timeout`: limit on SQL statement execution duration via server/session setting.

Do not see pool `connectionTimeout=30000` and assume the driver waits 30,000 seconds for TCP.

### 15.4. JDBC Question Mark in SQL Differs From URL

In a JDBC URL, `?sslmode=...` begins query parameters. In `PreparedStatement`:

~~~sql
SELECT order_id FROM app.orders WHERE customer_id = ?
~~~

`?` is a parameter placeholder in the JDBC API. It is not used to bind host, database, or table names in the URL.

### 15.5. Configuring via Spring Boot

Example `application.properties`:

~~~properties
spring.datasource.url=jdbc:postgresql://db.internal.example:5432/shopdb?sslmode=verify-full
spring.datasource.username=DB_USER_FROM_CONFIGURATION
spring.datasource.password=DB_PASSWORD_FROM_SECRET_STORE
~~~

The uppercase values here are only **illustrative placeholders**, not Spring interpolation syntax. In a real system, use your Spring deployment's environment/secret binding mechanism instead of committing passwords into files.

---

## 16. libpq Environment Variables

Some common variables:

| Variable | Purpose |
|---|---|
| `PGHOST` | Host or socket directory |
| `PGHOSTADDR` | Specific network address |
| `PGPORT` | Port |
| `PGDATABASE` | Database |
| `PGUSER` | Role |
| `PGPASSWORD` | Password — **not recommended** due to environment/process exposure risks |
| `PGSSLMODE` | TLS policy |
| `PGSSLROOTCERT` | CA root file |
| `PGAPPNAME` | Application name |
| `PGCONNECT_TIMEOUT` | Connection timeout |
| `PGSERVICE` | Service configuration name |
| `PGPASSFILE` | Password file path |

### 16.1. `psql` Example on a Unix-Like Shell

~~~bash
export PGHOST=db.internal.example
export PGPORT=5432
export PGDATABASE=shopdb
export PGUSER=app_reader
export PGSSLMODE=verify-full
export PGSSLROOTCERT=/etc/postgresql/ca.pem

psql
~~~

Assumes a valid credential source is configured. Do not paste real passwords into shell history.

### 16.2. Precedence Rules

With libpq, explicitly supplied connection parameters generally take precedence over corresponding environment defaults. Service files and password files have their own combination rules. Do not assume pgJDBC automatically reads all `PG*` variables: Java frameworks/drivers use their own configuration.

### 16.3. `.pgpass`

The libpq password file has entries of the form:

~~~text
hostname:port:database:username:password
~~~

On Unix, permissions on a file containing passwords must be restricted, typically readable/writable only by the owner. `PGPASSFILE`/`passfile` can control its location per libpq. Do not print the contents of secret files in logs or support tickets.

### 16.4. A Password File Does Not Replace TLS

A passfile only supplies credentials when needed. It does not encrypt traffic, verify certificates, enforce RLS, or replace SQL privileges.

---

## 17. libpq Service Files

### 17.1. Grouping Configuration Under One Name

Example service configuration:

~~~ini
[shop_readonly]
host=db-read.internal.example
port=5432
dbname=shopdb
user=app_reader
sslmode=verify-full
sslrootcert=/etc/postgresql/ca.pem
application_name=reporting-cli
connect_timeout=5
~~~

A libpq client can use:

~~~bash
psql "service=shop_readonly"
~~~

Service file paths and variables such as `PGSERVICEFILE` depend on OS/libpq configuration; verify the location on the actual host.

### 17.2. Benefits

- Avoids duplicating endpoint/SSL config across many scripts.
- Easy to switch environments via centralized management.
- Different profiles can be defined for read-only/reporting/admin following least privilege.

### 17.3. Risks

If the `shop_readonly` config unexpectedly points to the primary or another database, unchanged scripts will silently hit the new target. Change management is required for service files; do not embed passwords in shared service profiles.

---

## 18. TLS: Encryption and Server Identity Verification

### 18.1. libpq SSL Modes

| `sslmode` | Description | When to Use |
|---|---|---|
| `disable` | Do not use TLS | Only where evaluated as safe with separate controls |
| `allow` | May try without TLS first | Does not guarantee encryption |
| `prefer` | Prefers TLS, may fall back | Does not guarantee hostname verification |
| `require` | Requires TLS | Not an explicit configuration guaranteeing server identity |
| `verify-ca` | TLS + CA chain verification | Does not automatically confirm endpoint hostname |
| `verify-full` | TLS + CA + hostname verification | Suitable for production with proper PKI/certificates |

In some libpq versions/configs, `require` has compatibility behavior when a CA file exists; **do not use `require` instead of `verify-full`** if endpoint verification is required.

### 18.2. Production-Like Example

~~~text
postgresql://app@db.prod.internal.example:5432/shopdb?sslmode=verify-full&sslrootcert=%2Fetc%2Fpostgresql%2Fca.pem
~~~

The CA file resides on the client machine. The server certificate must be valid and match the DNS hostname/IP per client policy.

### 18.3. Common Errors

- Server/proxy does not support TLS when the client requires it.
- Wrong CA bundle, missing intermediate certificate, or expired certificate.
- URL uses an IP while the certificate only has a DNS name.
- Client clock is wrong.
- Proxy terminates TLS and connects to the backend without an equivalent TLS policy.
- Misconfigured mTLS client cert/key.

### 18.4. TLS Differs From Authorization

TLS protects transport and authenticates the server per mode; it does not grant SELECT on tables and does not replace RLS. A `verify-full` connection can still be rejected due to PostgreSQL role, HBA, or SQL privileges.

---

## 19. SCRAM and `pg_hba.conf`

### 19.1. SCRAM Differs From TLS

`scram-sha-256` is a challenge–response password authentication method. TLS protects transport and can verify the server. Using SCRAM over TLS addresses two distinct requirements.

### 19.2. Types of HBA Rules

Example **not to be applied verbatim to production**:

~~~text
# TYPE   DATABASE USER         ADDRESS       METHOD
local    shopdb   app_reader                 peer
hostssl  shopdb   app_reader   10.20.0.0/16  scram-sha-256
~~~

`local` applies to Unix sockets. `hostssl` applies to TCP connections using TLS. The address range here is only a private network example, not a policy suitable for every deployment.

### 19.3. Matching Rules

PostgreSQL evaluates HBA records in order and selects the record matching the connection type/database/user/address. When a record matches but authentication fails, the server does not simply try the next record as a fallback password method.

### 19.4. Auth Methods

| Method | Meaning |
|---|---|
| `scram-sha-256` | Modern password authentication when supported by client/server |
| `peer` | OS-user-based authentication for local sockets |
| `cert` | Client-certificate-based authentication |
| `reject` | Blocks matching connections |
| `trust` | Requires no password proof; **should not be used on untrusted networks** |
| `md5` | Legacy; plan migration to support SCRAM properly |

If migrating from MD5 to SCRAM, check `password_encryption`, role password hashes, and client driver support. Do not simply edit one HBA line and assume every application will work.

### 19.5. HBA Does Not Replace GRANT

Passing HBA and password checks means the client can log in subject to remaining conditions. Permissions on databases, schemas, tables, functions, and RLS are still checked separately.

---

## 20. DNS `host`, `hostaddr`, and Certificate Name

### 20.1. Hostname

`host=db.internal.example` enables DNS resolution and supports hostname checking in TLS `verify-full`.

### 20.2. libpq `hostaddr`

`hostaddr=10.20.30.40` specifies the IP to connect to. In libpq configurations, both `host` (the name for operations needing a name, such as TLS certificate/credential matching) and `hostaddr` (the network address) can be provided to control resolution. Exact rules depend on libpq and the auth method.

### 20.3. Do Not Disable Certificate Verification Because of IP Connections

If a certificate is only valid for `db.internal.example`, switching the URL to a raw IP can cause `verify-full` to fail. Fix the endpoint/certificate configuration properly instead of lowering `sslmode` to `disable` to "fix" the error.

### 20.4. DNS Failover Does Not Migrate Existing Connections

When a DNS endpoint flips to a new primary, **already-open connections** remain bound to the old socket/backend until dropped or closed. Applications must handle reconnect and retry on failover; DNS does not automatically move a running PostgreSQL transaction to a new server.

---

## 21. Physical Connection, Session, Transaction, and Statement

### 21.1. Distinguishing Scopes

| Scope | Lifecycle | Example State |
|---|---|---|
| Physical connection | TCP/socket connection to server/proxy | Endpoint, socket, TLS |
| PostgreSQL session | One backend session after authentication | Backend PID, `SET`, temporary objects, prepared statements |
| SQL transaction | `BEGIN` → `COMMIT/ROLLBACK` or implicit transaction | Snapshots, locks, `SET LOCAL` |
| SQL statement | One `SELECT/UPDATE/...` | Command tag, `ROW_COUNT`, results |
| Pool checkout | One application lease of a `Connection` | Application resource lease; may reuse a physical connection |

### 21.2. One Session Has Many Transactions

~~~sql
BEGIN;
SELECT * FROM app.orders WHERE order_id=1001;
COMMIT;

BEGIN;
UPDATE app.orders SET status='paid' WHERE order_id=1002;
ROLLBACK;
~~~

There is no mandatory reason to open a new TCP connection between two transactions. However, with PgBouncer transaction pooling, the two transactions may **be assigned to two different backends** even though the client connection to the proxy does not change.

### 21.3. JDBC `close()` With a Pool

In many pools, Java's `connection.close()` **returns the logical connection to the pool**, rather than necessarily closing the physical socket. Forgetting to close can exhaust pool resources. Use try-with-resources.

### 21.4. Backend PID

`pg_backend_pid()` reports the PID of the backend **currently executing the SQL**. Do not use it as a user ID, HTTP request ID, or durable identifier; the PID can change across reconnects/pool routing and can be reused over the process lifecycle.

---

## 22. Lab: Observing Session Identity

### 22.1. Session Identification Query

~~~sql
SELECT
    current_database() AS database_name,
    current_user AS effective_role,
    session_user AS login_role,
    pg_backend_pid() AS backend_pid,
    inet_client_addr() AS client_ip,
    inet_client_port() AS client_port,
    inet_server_addr() AS server_ip,
    inet_server_port() AS server_port,
    current_setting('application_name') AS application_name,
    current_setting('TimeZone') AS timezone;
~~~

With Unix-domain sockets, `inet_client_addr()`/`inet_server_addr()` can be NULL; this is valid behavior.

### 22.2. Two `psql` Windows

Open two independent `psql` windows and run:

~~~sql
SELECT pg_backend_pid(), current_database(), current_user;
~~~

With direct connections, two active sessions normally have different PIDs. With transaction pooling, the backend PID for the same client can change between transactions.

### 22.3. Changing `application_name`

~~~sql
SET application_name='learning-order-worker';
SELECT current_setting('application_name');
~~~

Use `application_name` to identify workloads in logs/`pg_stat_activity`, not for tokens/passwords/PII. Clients can set it themselves, so it is **not proof of authentication**.

---

## 23. Session State vs. `SET LOCAL`

### 23.1. Session-Level `SET`

~~~sql
SET TIME ZONE 'UTC';

BEGIN;
SELECT current_setting('TimeZone');
COMMIT;

SELECT current_setting('TimeZone');
~~~

`SET TIME ZONE` can persist across multiple transactions in the same backend session. If a pool does not reset state, subsequent requests may inherit unwanted values.

### 23.2. `SET LOCAL`

~~~sql
BEGIN;

SET LOCAL statement_timeout='2s';
SELECT current_setting('statement_timeout');

COMMIT;

SHOW statement_timeout;
~~~

`SET LOCAL` only lasts for the running transaction. After COMMIT, the value reverts to the previous session-level setting (not necessarily the system default).

### 23.3. Session State and Tenant Isolation

Suppose request A runs:

~~~sql
SET search_path TO tenant_a, public;
~~~

And then returns the connection to the pool without resetting it. Request B may access `tenant_a`'s tables if it continues relying on the stale `search_path`. You need request/transaction-scoped context, schema-qualified SQL where appropriate, and explicit **cleanup/validation**.

### 23.4. Custom GUCs Are Not Identity Proof by Themselves

~~~sql
BEGIN;
SET LOCAL app.tenant_id='10';
-- Queries inside the transaction.
COMMIT;
~~~

This pattern only supports RLS/tenant logic when `app.tenant_id` is set by a trusted authenticated layer and the caller cannot spoof it. A configuration variable that a user can arbitrarily `SET` is not an authentication mechanism.

### 23.5. `RESET ALL` vs. `DISCARD ALL`

- `RESET ALL` resets session configuration parameters; it **does not clean up all other state**.
- `DISCARD ALL` cleans up many session resources/state, has limitations, and **cannot be executed inside a transaction block**.
- Aggressive state cleanup can drop prepared statement caches/temporary objects and incur cost.

Pools/drivers may automatically reset a subset of state on connection return; always check the contract instead of assuming all state is clean.

---

## 24. Java JDBC and Transaction Boundaries

### 24.1. Auto-Commit

A JDBC `Connection` normally starts with `autoCommit=true`. To group multiple statements into one transaction:

~~~java
connection.setAutoCommit(false);
try {
    // SQL 1
    // SQL 2
    connection.commit();
} catch (SQLException error) {
    connection.rollback();
    throw error;
}
~~~

In production code, handle rollback failures, finally/cleanup, and framework transaction managers properly. Do not manually commit/rollback a connection managed by Spring `@Transactional` if the contract forbids it.

### 24.2. Java Method Using `PreparedStatement`

~~~java
import java.sql.*;

public class OrderService {
    public static int markPaid(Connection connection, long orderId)
            throws SQLException {
        boolean oldAutoCommit = connection.getAutoCommit();

        try {
            connection.setAutoCommit(false);

            int rows;
            try (PreparedStatement ps = connection.prepareStatement(
                    "UPDATE app.orders SET status='paid' " +
                    "WHERE order_id=? AND status='new'")) {
                ps.setLong(1, orderId);
                rows = ps.executeUpdate();
            }

            connection.commit();
            return rows;

        } catch (SQLException error) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                error.addSuppressed(rollbackError);
            }
            throw error;
        } finally {
            connection.setAutoCommit(oldAutoCommit);
        }
    }
}
~~~

This pattern assumes the `app.orders` table exists and the method is called outside a framework-managed transaction. In a real environment, restoring `autoCommit` can also fail if the socket is broken; the pool must evict broken physical connections rather than reusing them.

### 24.3. `PreparedStatement` Does Not Replace Transactions

Parameter binding prevents SQL injection on data values; it does not automatically make two updates to orders and inventory atomic. Transactions, constraints, and concurrency design are still required.

### 24.4. SQLSTATE

In JDBC, `SQLException.getSQLState()` can be used for classification:

| Code | Meaning |
|---|---|
| `23505` | Unique violation |
| `23503` | Foreign key violation |
| `40001` | Serialization failure |
| `40P01` | Deadlock detected |
| `57014` | Query canceled |

Constraint errors differ from socket/TLS errors. Do not catch all `SQLException`s and return the same business code such as "not found".

---

## 25. Temp Objects, Prepared Statements, and Advisory Locks

### 25.1. Temporary Tables

~~~sql
CREATE TEMP TABLE tmp_request_ids (
    id bigint PRIMARY KEY
) ON COMMIT DROP;
~~~

`ON COMMIT DROP` drops the temp table when the transaction ends per appropriate semantics. A temp table without `ON COMMIT DROP` normally has session lifetime and can persist across pool checkouts if the backend does not change.

### 25.2. Named Prepared Statements

~~~sql
PREPARE get_customer(bigint) AS
SELECT customer_id,customer_name
FROM app.customers WHERE customer_id=$1;

EXECUTE get_customer(101);
DEALLOCATE get_customer;
~~~

SQL `PREPARE`/`EXECUTE` belong to the backend session. Protocol-level named prepared statements created by drivers have their own semantics but also depend on backend state; when routed to another server connection, that name does not necessarily exist.

### 25.3. Cursors

Some cursors are declared inside a transaction and do not exist after COMMIT; holdable cursors have special lifetimes. Do not assume a cursor can continue FETCHing on a new backend after PgBouncer transaction pooling.

### 25.4. Advisory Locks

Session-level:

~~~sql
SELECT pg_advisory_lock(12345);
SELECT pg_advisory_unlock(12345);
~~~

`pg_advisory_lock` can hold a lock **across COMMIT**, until unlocked or the session ends. That is risky when returning a backend to a pool.

Transaction-level:

~~~sql
BEGIN;
SELECT pg_advisory_xact_lock(12345);
COMMIT;
~~~

`pg_advisory_xact_lock` releases automatically when the transaction ends, usually making it easier to control for single-transaction business scopes.

### 25.5. LISTEN

~~~sql
LISTEN order_events;
~~~

A LISTEN registration is session state. The client must continue using the appropriate backend to receive notifications; transaction pooling does not guarantee session affinity across transactions.

---

## 26. Connection Pools and Resource Cost

### 26.1. Purpose of a Pool

Opening a new physical connection requires networking, TLS/auth handshakes, and PostgreSQL backend resources. A pool keeps connections ready; application requests borrow and return them:

~~~text
Request A ---> [Connection 1] ---> Backend 1
Request B ---> [Connection 2] ---> Backend 2
Request C ---> [busy pool; wait] 
Request D ---> [Connection 3] ---> Backend 3
~~~

### 26.2. Pool Saturation Differs From TCP Errors

When all slots are busy, the application may report "connection acquisition timeout". This does not mean the PostgreSQL hostname failed to resolve or the port is blocked.

Typical causes: slow queries, long transactions, lock contention, missing close/release, limited backend capacity, or mis-sized pools.

### 26.3. Total Connection Count

For example, 20 application instances × maximum pool size 30 = **600 potential connections**. You must also add background jobs, monitoring, admin sessions, reporting, and proxies. PostgreSQL `max_connections` is not a target that should always be fully consumed.

### 26.4. A Larger Pool Does Not Equal Higher Throughput

If the DB is constrained by CPU, I/O, or locks, a larger pool can worsen contention and increase latency. Choose sizing based on benchmarks, query durations, concurrency, and DB resource budgets.

### 26.5. Types of Timeouts

| Timeout | What Is Bounded |
|---|---|
| Pool checkout timeout | Time client waits to borrow a connection |
| TCP connect timeout | Time to establish the network connection |
| TLS/auth handshake timeout | Wait for the respective handshake |
| Socket/read timeout | Wait for I/O/response |
| `statement_timeout` | SQL statement execution time on the server |
| `lock_timeout` | Wait for a lock |
| `idle_in_transaction_session_timeout` | Open transaction left idle too long |

Names, units, and scopes vary by driver/pool/server. Do not copy a number without checking its units.

---

## 27. HikariCP Example

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import java.sql.*;

public class PgPool {
    public static HikariDataSource create() {
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(
            "jdbc:postgresql://db.internal.example:5432/shopdb" +
            "?sslmode=verify-full&ApplicationName=orders-api"
        );
        config.setUsername(System.getenv("DB_USER"));
        config.setPassword(System.getenv("DB_PASSWORD"));
        config.setMaximumPoolSize(12);
        config.setMinimumIdle(2);
        config.setConnectionTimeout(5000); // ms
        config.setValidationTimeout(2000); // ms
        return new HikariDataSource(config);
    }

    public static void query(HikariDataSource pool)
            throws SQLException {
        try (Connection c = pool.getConnection();
             PreparedStatement ps =
                c.prepareStatement("SELECT pg_backend_pid()");
             ResultSet rs = ps.executeQuery()) {
            if (rs.next()) {
                System.out.println(rs.getInt(1));
            }
        }
    }
}
~~~

This is a structural example; real projects need pgJDBC/HikariCP dependencies, proper CA trust, and secret configuration. Pool sizes and timeouts here are **illustrative**, not quantitative recommendations for every system.

### 27.1. Lifecycle

`maxLifetime`, `idleTimeout`, connection validation, and keepalives affect connection churn. Setting them inconsistently with backend/proxy/NAT idle limits can cause unexpected connection reset errors.

### 27.2. try-with-resources

Ensure `Connection.close()` is called in finally/try-with-resources. With a pool, close typically returns the logical connection rather than closing the backend immediately.

---

## 28. PgBouncer and Session/Transaction/Statement Pooling

### 28.1. Two Sides of the Proxy

~~~text
Application --client socket--> PgBouncer --server socket--> PostgreSQL
~~~

The number of client connections to PgBouncer can exceed the number of maintained PostgreSQL server connections.

### 28.2. Session Pooling

A backend is bound to a client session for the duration of that session; features relying on session affinity are more likely to behave like a direct connection, depending on proxy config.

### 28.3. Transaction Pooling

A backend connection is assigned for **one transaction** and returned to the server pool when the transaction finishes.

~~~text
Client X tx1 --> Backend A --> COMMIT
Client X tx2 --> Backend B --> COMMIT
~~~

Therefore, session-level state created on backend A is not guaranteed on B.

### 28.4. Statement Pooling

Backends can be assigned per statement, making applications that require explicit multi-statement transactions incompatible unless the proxy supports proper session retention. Use only when the workload fits.

### 28.5. Compatibility Table

| Feature | Session Pooling | Transaction Pooling |
|---|---|---|
| Simple SELECT/UPDATE SQL | Usually works | Usually works |
| Multi-statement BEGIN/COMMIT | Usually works | Works if transaction holds one backend |
| `SET LOCAL` inside transaction | Works | Works when all SQL is in the same transaction |
| Session-level `SET` across transactions | May persist | **Must not be assumed** |
| Temporary table across transactions | May persist | Unsafe |
| Session advisory lock | May persist | Unsafe |
| Long-lived LISTEN | May persist | Usually incompatible |
| SQL named `PREPARE` | Session-bound | Not portable by default |
| Protocol prepared statement | Session-bound | Some PgBouncer versions support tracking if configured |
| Unchanged `pg_backend_pid()` across transactions | Usually true | Not guaranteed |

### 28.6. Prepared Statements With Newer PgBouncer

Some modern PgBouncer versions support tracking protocol-level named prepared statements under transaction pooling via settings like `max_prepared_statements`. Do not assume equivalence with SQL `PREPARE`, and always test with your actual pgJDBC version and pool mode.

### 28.7. Double Pooling

HikariCP + PgBouncer can make sense, but you must measure both queues/timeouts and total concurrency. Double pooling does not cure DB overload on its own.

---

## 29. Idle in Transaction

### 29.1. The Problem

~~~sql
BEGIN;
SELECT * FROM app.orders WHERE order_id=1001;
-- Application stops sending SQL without COMMIT/ROLLBACK.
~~~

The session may show `idle in transaction` in `pg_stat_activity`.

### 29.2. Consequences

- Holds transactions/snapshots/locks depending on statements and isolation.
- Delays VACUUM cleanup or increases bloat.
- Occupies a pool slot.
- Causes lock waits and blocks other requests.

### 29.3. Timeouts

~~~sql
SHOW idle_in_transaction_session_timeout;
SHOW statement_timeout;
SHOW lock_timeout;
~~~

`idle_in_transaction_session_timeout` is a safety net, not a substitute for proper application commit/rollback. When the server terminates a backend due to timeout, the pool must discard the dead connection.

### 29.4. Do Not Equate Active With Healthy

A session may not be running a query at the instant you observe it while still holding an open transaction. Monitor transaction duration and wait events, not just CPU usage.

---

## 30. Savepoints and Failed Transactions

### 30.1. Failed Transaction

~~~sql
BEGIN;
SELECT 1/0; -- division_by_zero
SELECT 42;  -- rejected because transaction is aborted
ROLLBACK;
~~~

In the protocol, `ReadyForQuery` can return transaction status `E`.

### 30.2. Savepoints

~~~sql
BEGIN;
SAVEPOINT before_optional;
-- SQL that might fail.
-- If the SQL errored and the transaction still has the savepoint:
ROLLBACK TO SAVEPOINT before_optional;
SELECT 42;
COMMIT;
~~~

This snippet illustrates control flow, not a script with automatic error catching. The application must decide when to roll back to a savepoint and when to roll back the entire transaction.

### 30.3. JDBC Savepoints

~~~java
connection.setAutoCommit(false);
Savepoint checkpoint = connection.setSavepoint();
try {
    // Execute a statement.
} catch (SQLException error) {
    connection.rollback(checkpoint);
    // Continue only if the error can be handled safely.
}
connection.commit();
~~~

Do not try to continue every transaction after `serialization_failure`/deadlock or when the physical connection is lost. Those cases typically require retrying the entire transaction or acquiring a new connection per application policy.

### 30.4. Do Not Return Connections in State E to the Pool

The pool must roll back/clean up per contract, or discard broken connections. The next caller must never receive a backend stuck in a failed transaction and encounter `current transaction is aborted` errors unrelated to its own code.

---

## 31. Multi-Host URIs and Selecting the Right Server

### 31.1. Multi-Host in libpq

Libpq supports connection strings with host lists in supported configurations:

~~~text
postgresql://app_reader@pg-a.internal.example:5432,pg-b.internal.example:5432/shopdb?target_session_attrs=read-write&connect_timeout=5
~~~

Multiple hosts let libpq try endpoints according to its selection/connection attempt rules, but it does **not** mean PostgreSQL automatically performs load balancing, leader election, or replication.

### 31.2. `target_session_attrs`

`target_session_attrs` lets the client accept only a server with a desired attribute. For example, `read-write` avoids connecting to a server in read-only state in appropriate contexts.

~~~text
postgresql://app@pg-a,pg-b/shopdb?target_session_attrs=read-write
~~~

If neither can accept write transactions or no host is reachable, the connection fails. Behavior of other values such as `primary`, `read-only`, and `prefer-standby` depends on the libpq version; check your client's documentation.

### 31.3. Multi-Host Does Not Replace HA

For true high availability, a system still needs:

- Proper synchronization or replication between nodes.
- A primary/leader election mechanism.
- Endpoint/DNS/proxy configuration so clients reach the right node.
- Fencing/split-brain prevention in the HA system.
- Retry/transaction recovery rules in the application.

A connection URI alone does not solve replication correctness or failover.

### 31.4. Failover Does Not Transfer In-Flight Transactions

If the backend loses connection between `COMMIT` and the server's response, the application may **not know whether the transaction committed**. Blindly retrying an INSERT with side effects can create duplicates.

Use transaction idempotency keys, unique constraints, and reconciliation workflows to handle unknown commit outcomes. Do not treat every `connection reset` error as "the SQL never ran".

### 31.5. Read Replicas Are Not Always Suitable for Every SELECT

A SELECT on a replica can read stale data relative to the primary due to replication lag. If the application requires read-your-writes, route to the primary or use an appropriate consistency strategy rather than simply picking a `read-only` endpoint.

### 31.6. Reasonable Retries

You can retry opening connections when DNS/TCP/auth target failures occur per policy; however, retrying **business operations** must distinguish:

- Did the statement run before disconnect?
- Is the transaction outcome known?
- Is the operation idempotent?
- Are external calls or outbox events involved?
- Will retries add load while the DB is already overloaded?

Exponential backoff with jitter, retry limits, and circuit breakers help stabilize systems. Never allow millions of clients to retry endlessly at once.

---

## 32. Query Timeouts, Cancellation, and Shutdown

### 32.1. `statement_timeout`

~~~sql
SET statement_timeout='5s';

SELECT pg_sleep(10);
~~~

The 10-second sleep query is expected to be canceled after the timeout, depending on the environment. The SQLSTATE is typically `57014` (`query_canceled`).

This example **intentionally triggers an error**; run it only in a lab session, not directly in migrations or production applications.

### 32.2. `lock_timeout`

~~~sql
SET lock_timeout='2s';
~~~

`lock_timeout` limits waiting for locks. Unlike `statement_timeout`, a query can be slow due to CPU/I/O without waiting on locks, so `lock_timeout` does not affect it in the same way.

### 32.3. JDBC `Statement.setQueryTimeout`

A driver may provide `Statement.setQueryTimeout(seconds)`. How the driver implements it can involve cancellation and driver-specific mechanisms; do not assume it behaves identically to server `statement_timeout` in every scenario.

### 32.4. Cancel Requests

The PostgreSQL wire protocol has a separate cancel request mechanism based on backend key data from the connection. Drivers expose APIs to cancel queries; applications are discouraged from hand-crafting protocol cancel packets without a special reason and thorough safety testing.

### 32.5. `pg_cancel_backend` vs. `pg_terminate_backend`

~~~sql
SELECT pg_cancel_backend(<backend_pid>);
SELECT pg_terminate_backend(<backend_pid>);
~~~

**This is only a syntax illustration with placeholders**, not runnable SQL as-is. `pg_cancel_backend` requests canceling the running query, while `pg_terminate_backend` requests terminating the backend session subject to privileges. Both can impact transactions and application clients.

Do not run them against unfamiliar PIDs or in production just to "clean up idle connections". Check permissions, the query, transaction age, and session owner; prioritize fixing root causes like pool leaks or long transactions.

### 32.6. Cancel Does Not Automatically Roll Back Every Business Effect

Canceling a statement inside a transaction can put the transaction into a failed state, requiring rollback. If prior SQL or code already triggered external side effects, cancellation/rollback does not guarantee they are undone.

---

## 33. Monitoring Connections With `pg_stat_activity`

### 33.1. Basic Query

~~~sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    client_addr,
    backend_start,
    state,
    xact_start,
    query_start,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE backend_type = 'client backend'
ORDER BY backend_start;
~~~

Some fields/details depend on monitoring privileges. A role without monitor privileges may not see all data from other sessions. Do not grant `pg_monitor` or overly broad privileges just to run an unnecessary dashboard.

### 33.2. Common States

| State | General Meaning |
|---|---|
| `active` | Currently executing a query |
| `idle` | Waiting for a new command, not inside a transaction |
| `idle in transaction` | Transaction still open, not currently running a query |
| `idle in transaction (aborted)` | Transaction errored but not yet rolled back |
| `disabled` | State tracking may be disabled by configuration |

Do not treat `state='idle'` as proof of a leaked session. A healthy pool intentionally keeps idle server connections to serve requests quickly.

### 33.3. Query to Find Long Transactions

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start
LIMIT 30;
~~~

This is a snapshot at query time. Inside a long transaction, `now()` is the monitoring session's transaction timestamp; to measure current wall-clock time, use `clock_timestamp()`.

### 33.4. Query to Find `idle in transaction`

~~~sql
SELECT
    pid, usename, application_name, client_addr,
    now() - xact_start AS transaction_age,
    state
FROM pg_stat_activity
WHERE state LIKE 'idle in transaction%'
ORDER BY xact_start;
~~~

A long-idle transaction can hold locks/snapshots and hurt VACUUM. Review application traces and transaction ownership before terminating.

### 33.5. Connection Count by Application

~~~sql
SELECT
    application_name,
    state,
    COUNT(*) AS connections
FROM pg_stat_activity
WHERE backend_type='client backend'
GROUP BY application_name,state
ORDER BY connections DESC, application_name,state;
~~~

If multiple applications share an empty `application_name`, the output cannot distinguish them. Configure meaningful `application_name` values without secrets.

### 33.6. Connection Limits

~~~sql
SHOW max_connections;
SHOW superuser_reserved_connections;
~~~

Some PostgreSQL versions have additional reserved connection settings. Do not equate allowed application connection slots with `max_connections` without accounting for reserved slots, role limits, poolers, and other connections.

---

## 34. Observing Actual TLS From the Server Side

### 34.1. `pg_stat_ssl`

~~~sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    s.ssl,
    s.version AS tls_version,
    s.cipher,
    s.client_dn
FROM pg_stat_activity AS a
JOIN pg_stat_ssl AS s
  ON s.pid=a.pid
WHERE a.pid=pg_backend_pid();
~~~

On a direct TCP TLS connection, `ssl=true` generally proves the hop **to that backend** is encrypted. Over a Unix socket it may be false or show appropriate fields.

### 34.2. `ssl=true` Does Not Prove `verify-full`

The server can see a TLS connection, yet does not know whether the client verified the hostname or CA according to client policy. `ssl=true` is insufficient to conclude "the client verified the server securely".

### 34.3. Proxies Change What Is Observed

If `app --TLS--> PgBouncer --TLS--> PostgreSQL`, `pg_stat_ssl` on PostgreSQL only observes the `PgBouncer -> PostgreSQL` leg; it does not tell you whether `app -> PgBouncer` used TLS.

### 34.4. Client-Side Inspection

`psql` has commands to show current connection info (such as `\conninfo`). Combine client inspection, proxy config, and server `pg_stat_ssl` to understand the full path.

### 34.5. TLS Version and Cipher

TLS protocol/cipher suite depends on the server, client, and OpenSSL or corresponding TLS library. Do not hardcode "all sessions are TLS 1.3" in heterogeneous environments; measure in practice and configure minimums per security policy.

---

## 35. `psql`: Basic Connection Diagnostic Toolkit

### 35.1. Connecting via TCP With Explicit Parameters

~~~bash
psql -h db.internal.example -p 5432 -U app_reader -d shopdb
~~~

If TLS/CA is required, configure service/environment/connection string rather than providing only the host and hoping the client verifies the hostname properly.

### 35.2. Connecting via URI

~~~bash
psql "postgresql://app_reader@db.internal.example:5432/shopdb?sslmode=verify-full&connect_timeout=5"
~~~

Do not include real passwords in commands that get saved in shell history.

### 35.3. Useful `psql` Commands

| Command | Effect |
|---|---|
| `\conninfo` | Displays current connection details (per psql/client capabilities) |
| `\c dbname` | Switches database / establishes a new connection |
| `\dt` | Lists visible table relations |
| `\dn` | Lists schemas |
| `\du` | Lists roles (per metadata visibility privileges) |
| `\timing on` | Shows client-side statement execution time |
| `\set ON_ERROR_STOP on` | Stops script on SQL error, useful in migrations when desired |
| `\q` | Quits psql |

### 35.4. `\c` Can Create a Different Session

When using `\c` to reconnect/switch databases, a new backend session may be created, losing prepared statements, temp tables, or `SET` values from the old session. Do not treat `\c` as equivalent to SQL `SET search_path`.

### 35.5. End-to-End Verification Query

~~~sql
SELECT
    current_database(),
    current_user,
    pg_backend_pid(),
    current_setting('application_name'),
    pg_is_in_recovery() AS is_standby;
~~~

`pg_is_in_recovery()=true` indicates the server is in recovery/hot standby mode at query time; it does not replace verifying primary/read-write status per HA/client routing config.

---

## 36. Diagnosing Errors by Layer

| Symptom | Possible Layer | How to Isolate |
|---|---|---|
| Cannot resolve hostname | DNS | Check name, resolver, network policy |
| Connection refused | TCP/listener | Check host/port, `listen_addresses`, firewall |
| Connection timed out | Network/firewall/load | Check route, security groups, proxy, connect timeout |
| Server does not support SSL/TLS as client requires | TLS negotiation | Check server/proxy TLS config |
| Certificate verify failed | PKI/TLS | Check CA, hostname, expiry, clock |
| No pg_hba.conf entry | Admission/auth rule | Check connection type, source IP, HBA order |
| Password authentication failed | Auth | Check role/credential/hash/auth method |
| Database does not exist | Startup/DB name | Check database/endpoint name |
| Role does not exist | Login identity | Check `user` and role configuration |
| Permission denied for table | SQL authorization | GRANT, ownership, schema USAGE, RLS |
| Too many connections | Server capacity | `max_connections`, reserved slots, pools/leaks |
| Failed transaction after SQL error | Transaction | Rollback/retry per contract |
| Pool acquisition timeout | Application pool | Active/idle/waiting, leaks, transactions |
| Connection reset by peer | Socket/proxy/server | Failover/restart, timeout, NAT, backend termination |
| Query canceled | Query timeout/cancellation | SQLSTATE, `statement_timeout`, client cancel |
| Unexpected session state | Pool reuse | RESET/DISCARD, SET LOCAL, backend affinity |

### 36.1. Inspect From the Outside In

1. Actual endpoint/URI (without exposing passwords).
2. DNS and network route.
3. TCP port/listener/proxy.
4. TLS mode, certificate, and trust roots.
5. Role/database/HBA authentication.
6. SQL privileges and RLS.
7. Pool checkout, query timeouts, and transaction state.
8. Session settings and proxy routing.

A `permission denied` error should not be "fixed" by changing `listen_addresses` or disabling TLS.

### 36.2. Do Not Log Passwords While Debugging

Redacted logs may include `host, port, database, application_name, sslmode` and sanitized error class/SQLSTATE. If a driver exception embeds a connection string, redact it before shipping logs to observability systems.

---

## 37. Decision Diagram When Unable to Connect

~~~mermaid
flowchart TD
    A["Application cannot connect to PostgreSQL"] --> B{"Is DNS/endpoint valid?"}
    B -- "No" --> C["Check domain name, DNS, proxy, network"]
    B -- "Yes" --> D{"Can TCP/socket open?"}
    D -- "No" --> E["Port, listen_addresses, firewall, timeout"]
    D -- "Yes" --> F{"Does TLS negotiation/verify succeed?"}
    F -- "No" --> G["CA, hostname, mode, proxy TLS"]
    F -- "Yes" --> H{"Do authentication and database CONNECT succeed?"}
    H -- "No" --> I["pg_hba, role, credential, database"]
    H -- "Yes" --> J{"Are SQL SELECT/UPDATE permitted?"}
    J -- "No" --> K["GRANT, schema USAGE, RLS"]
    J -- "Yes" --> L{"Are pool/transactions working properly?"}
    L -- "No" --> M["Checkout waits, idle in transaction, RESET, capacity"]
    L -- "Yes" --> N["Monitor and benchmark workload"]
~~~

### 37.1. One Rule

**Do not weaken security controls at a higher or unrelated layer to fix an error at another layer.** For example, do not set `sslmode=disable` to bypass a certificate error, or grant superuser to bypass an application missing SELECT on a table.

---

## 38. Multi-Tenant and Permissions: The Database Session Does Not Automatically Know the HTTP User

### 38.1. Database Role in an Application Pool

Many apps use one `app_runtime` role for all HTTP requests. Once a PostgreSQL session authenticates as `app_runtime`, the database **does not automatically know** which browser user is behind each request.

### 38.2. RLS With Trusted Context

If policies rely on tenant identity, ensure that identity is authenticated, set by a trusted layer, and **cannot be spoofed by clients via input or overly broad SQL permissions**.

### 38.3. Transaction-Local Context

`SET LOCAL` inside a transaction helps prevent state leakage across a pool, yet still requires:

- Authentication/authorization before selecting the tenant.
- Ensuring all queries execute in the right transaction.
- Not granting callers arbitrary SQL execution that can alter the context.
- Rollback/cleanup on error.
- Testing interleaved requests/tenants when the pool reuses the same physical connection.

### 38.4. Transaction Pooling and `SET LOCAL`

With PgBouncer transaction pooling, `SET LOCAL` executed in the same explicit transaction as subsequent SQL applies properly on the backend held for that transaction. Session-level `SET` across transactions **must not be relied upon**.

### 38.5. Do Not Infer Identity From `application_name`

`application_name` is just a client/worker label, not an authenticated user identity. Never build an RLS policy that blindly trusts a client-declared `application_name`.

---

## 39. Capacity Planning for Multiple Applications

### 39.1. An Estimation Example

Suppose there are:

- 12 application instances.
- Each instance has HikariCP `maximumPoolSize = 15`.
- 4 background workers, each with at most 5 DB connections.
- 10 reserved monitoring/admin connections.

Total potential = **12 × 15 + 4 × 5 + 10 = 210** client connections, before considering proxy/HA and other systems.

With PgBouncer transaction pooling, the number of backend server connections can be smaller than total client connections, but you must size the pooler's server pool and queueing for the workload.

### 39.2. Metrics to Monitor

- Active, idle, and pending connections in the pool.
- Checkout wait time (p50/p95/p99).
- PostgreSQL backend count by app/db/user.
- Transaction duration and `idle in transaction` sessions.
- Query latency, locks, deadlocks, and waits.
- Backend connection churn.
- TLS/auth handshake latency and failures.
- CPU, memory, WAL, I/O, autovacuum lag.
- PgBouncer client/server connections and queue waits if used.

### 39.3. Connection Budget Is Not Throughput Budget

Each connection consumes resources. A DB with 500 active connections running heavy queries can be slower than a DB with 80 well-bounded concurrent connections. Benchmark by requests/second, transaction durations, and resource bottlenecks.

### 39.4. Distinguishing Idle Connections From Leaks

A pool keeping 20 idle physical connections during low traffic can be normal behavior. A leak is when **the application fails to return a lease** or leaves transactions open, causing pool exhaustion. Use metrics and traces rather than merely counting idle backends.

---

## 40. Session Hygiene: Deployment Checklist

### 40.1. Define the Per-Request Contract

- [ ] Request acquires a connection from the pool and always returns it (try-with-resources).
- [ ] Transactions are committed or rolled back on every branch.
- [ ] Never return a connection in a failed transaction state.
- [ ] Session `SET`/role/`search_path` are reset per the pool/framework contract.
- [ ] Use `SET LOCAL` when transaction context is needed; never rely on state from a previous request.
- [ ] Do not leave unintended session advisory locks, temp objects, or LISTEN registrations behind.
- [ ] Do not rely on backend PID or SQL prepared statements persisting under transaction pooling.

### 40.2. Configuration Security

- [ ] Never hardcode passwords in URIs, source code, or logs.
- [ ] Each service has a least-privilege DB role.
- [ ] TLS `verify-full` and correct CA for the endpoint.
- [ ] Never use `trust` HBA on untrusted networks.
- [ ] SCRAM/auth policies aligned across client and server.
- [ ] Firewall/private network open only to required scope.
- [ ] `application_name` is helpful and contains no secrets.

### 40.3. Operations

- [ ] Connections/pools have appropriate timeouts at each layer.
- [ ] Total pool sizes fit within the connection budget.
- [ ] Alerts configured for pool pending, idle in transaction, and errors.
- [ ] Circuit breaker/backoff in place for DB outages.
- [ ] Failover/DNS refresh and idempotency strategies defined.
- [ ] `pg_stat_activity`/`pg_stat_ssl` observability configured with appropriate privileges.
- [ ] Credential and CA revocation/rotation playbook exists.
- [ ] Proxy pooling tested with any session-specific features.

---

## 41. Real-World Scenario: Connects on Laptop, Fails in Container

### 41.1. Description

A Java application running on a laptop uses:

~~~text
jdbc:postgresql://localhost:5432/shopdb
~~~

When packaged with Docker and run in a container, the connection reports `Connection refused` even though PostgreSQL is still running on the host.

### 41.2. Why?

`localhost` inside a container refers to the **loopback of the container's network namespace**, not necessarily the host OS where PostgreSQL is listening. If the app and database are in two separate containers, each container has its own `localhost`.

### 41.3. Solution

- In a Docker Compose network, use the database hostname/service name per network configuration.
- If the DB is on the host, use the environment-supported endpoint with proper network protection.
- Verify PostgreSQL `listen_addresses`, HBA, and firewall.
- Do not hardcode `localhost` across all deployments.

### 41.4. Adding TLS and Roles

When changing the endpoint to a host/service name, certificate verification must match the endpoint name. Do not turn off `verify-full` as a default workaround. Roles/passwords must be managed via secrets and match the container's HBA source IP/path.

---

## 42. Real-World Scenario: Pool Returns Data From Previous Tenant

### 42.1. Description

Request A belonging to tenant 10 runs:

~~~sql
SET search_path=tenant_10,public;
~~~

It then closes the logical connection, and the pool reuses the backend. Request B belonging to tenant 20 borrows the same physical connection and accidentally queries an unqualified table without resetting `search_path`.

### 42.2. Root Cause

Session-level `SET` persists across COMMIT and pool checkouts. If the pool/framework does not reset enough state, request B may read the wrong schema.

### 42.3. Remediation

1. Never use an unvalidated application-controlled `search_path` as the sole security boundary.
2. Use schema-qualified SQL or trusted tenant mapping.
3. If per-request context is needed, set `SET LOCAL` inside a proper explicit transaction.
4. Ensure both transaction success and rollback always clean up context.
5. Test two tenants interleaved on a pool size of 1 to surface state leakage easily.
6. Review RLS/GRANT so even if an app bug occurs, the database blocks unauthorized data access.

### 42.4. Conclusion

A normal connection pool reuses backend sessions. This helps performance, but demands **session hygiene** and database permissions that do not rely on leftover state.

---

## 43. Real-World Scenario: Prepared Statement Errors Through PgBouncer

### 43.1. Description

An application uses pgJDBC `PreparedStatement` through PgBouncer transaction pooling. After many requests, some queries fail stating that the prepared statement does not exist or statement names collide.

### 43.2. Possible Causes

- The client driver cached server-side prepared statements belonging to a previous backend.
- PgBouncer routed the transaction to a different backend.
- The PgBouncer version/config does not support protocol-level prepared statement tracking as required by the driver.
- SQL `PREPARE` lives in backend state while the app assumes it is attached to the client session.

### 43.3. How to Handle

1. Confirm PgBouncer mode: session, transaction, or statement.
2. Confirm pgJDBC version and server preparation settings.
3. Check PgBouncer `max_prepared_statements` capability/status if supported by the version.
4. Measure the actual Parse/Bind/Execute path and errors by backend PIDs.
5. If incompatible, use session pooling or adjust driver/server preparation per documentation; do not disable all parameter binding.
6. Continue using JDBC `PreparedStatement` to separate SQL and data for SQL injection safety, even if server-side prepare caching behavior changes.

### 43.4. Do Not Equate Parameterization With Server-Side Plan Caching

Disabling or tuning server-side prepared statement reuse **does not mean** switching to raw SQL string concatenation. Parameter binding remains a security requirement.

---

## 44. Real-World Scenario: Error After Failover With Unknown Commit Outcome

### 44.1. Description

An API records a payment and sends `COMMIT`. Immediately afterward, the network disconnects before the client receives the response. The application knows the connection dropped, but does not know whether the database committed.

### 44.2. Why Can't You Simply Retry the INSERT?

If the transaction already committed and the API retries with a new ID, it can create two payment rows or duplicate external side effects.

### 44.3. Safer Design

- Each payment operation has an **idempotency key** stored and enforced as UNIQUE in the database.
- On reconnect, query transaction status by business key.
- Use a transactionally written outbox for external effects and idempotent consumers.
- Handle unique conflicts as a normal part of the idempotency protocol; do not treat every `23505` as "success" if the payload differs.
- Enforce retry limits and backoff.

### 44.4. Connection Strings Do Not Solve This

Even though a multi-host URI can try a new endpoint, it cannot determine the transaction outcome of the old connection. This is an atomicity + idempotency problem at the business layer.

---

## 45. Common Misconceptions

| Misconception | Why It Is Wrong | Correct Understanding |
|---|---|---|
| "A PostgreSQL connection is just a TCP socket" | Also involves TLS, startup, auth, protocol state | Layer the connection model |
| "Pingable host means DB is accessible" | Ping differs from TCP/TLS/auth | Check endpoint and each layer separately |
| "Port 5432 is always right" | PostgreSQL can change port | Check actual config |
| "`localhost` is always the host OS" | Inside a container it is a different namespace | Use the deployment's endpoint |
| "Unix socket is identical to TCP localhost" | IPC, HBA, and auth differ | Distinguish local/host rules |
| "TLS `require` means hostname is verified" | Encryption differs from server identity | `verify-full` with proper CA |
| "Percent-encoding a password keeps it secret" | Only URI escaping | Secret store/redaction |
| "Just use `sslmode=disable` to fix cert errors" | Loses transport protection | Fix PKI/hostname |
| "SCRAM replaces TLS" | SCRAM authenticates credentials; TLS protects the channel | Use both layers appropriately |
| "`pg_hba.conf` grants SELECT on tables" | HBA controls admission/auth | Separate GRANT/RLS |
| "HBA tries later rules if the password is wrong" | First-matching-record rule | Fix matching/auth |
| "JDBC URL matches libpq URI for all options" | Client properties differ | Check pgJDBC docs |
| "`connect_timeout` is a query timeout" | Opening connection vs. executing SQL | Per-layer timeouts |
| "Pool timeout means TCP is unreachable" | Slots may simply be busy | Measure checkout waits |
| "`Connection.close()` always closes the physical socket" | Pools return logical connections | Understand pool lifecycle |
| "One HTTP request equals one PostgreSQL session" | Pool reuse | Track transactions/checkouts |
| "`COMMIT` always clears session-level `SET`" | Session `SET` persists across transactions | `SET LOCAL`/reset |
| "`RESET ALL` clears all prepared/temp/locks" | Does not clear all session state | `DISCARD ALL`/proper cleanup |
| "`DISCARD ALL` works inside `BEGIN`" | Forbidden inside transaction blocks | Clean up at the right time |
| "`pg_backend_pid` is a user ID" | It is the backend process ID | Use proper identity |
| "Backend PID never changes through a pool proxy" | Transaction pooling can switch backends | Do not rely on session affinity |
| "`PreparedStatement` is always SQL `PREPARE`" | Driver/protocol caching differs | Understand Parse/Bind and driver |
| "`?` in URL and `?` in SQL are the same" | Completely different layers | URL options vs. bind param |
| "Parameter binding works for table names" | Parameters are values | Allowlist/quote identifiers |
| "Bind params provide authorization" | SQL injection differs from data permissions | GRANT/RLS |
| "`ReadyForQuery` `I` means session closed" | `I` is idle transaction status | Session is still alive |
| "A failed transaction can still run SELECT" | State `E` requires rollback | Error handling |
| "Timeout cancellation undoes all external side effects" | External systems sit outside the transaction | Outbox/idempotency |
| "A larger pool is always faster" | Increases contention and resource use | Benchmark/sizing |
| "All idle connections are leaks" | Pools intentionally keep idle connections | Measure active/checkout |
| "`idle in transaction` is harmless since no query runs" | Can hold locks/snapshots | Commit/rollback promptly |
| "PgBouncer transaction pool preserves all `SET` state" | Backends switch | `SET LOCAL`/avoid session state |
| "PgBouncer can never use prepared statements" | Versions/configs support tracking | Verify compatibility |
| "Multi-host automatically provides load balancing and replication" | Only connection selection | Separate HA infrastructure |
| "A read replica always sees writes immediately" | Replication lag | Consistency strategy |
| "Connection reset means the transaction rolled back" | Outcome may be unknown | Idempotency/reconcile |
| "`pg_stat_ssl.ssl=true` proves client `verify-full`" | Server doesn't know client hostname validation | Client-side PKI config |
| "`pg_notify` is a durable message queue" | Notifications are not durably stored for offline clients | Outbox/broker |
| "`application_name` is an authenticated identity" | Client-declared label | Separate auth/RLS |
| "Every `SQLException` is a network failure" | Constraint/auth/query errors differ | SQLSTATE and layered diagnosis |
| "Never set timeouts because they cause errors" | Unbounded waits exhaust resources | Choose timeouts per SLO |
| "Include passwords in exceptions so DBAs can debug" | Can leak secrets | Log redacted metadata |

---

## 46. Production PostgreSQL Configuration Checklist

### 46.1. URI/Driver

- [ ] Choose the right libpq URI, key=value, or pgJDBC URL syntax.
- [ ] Explicit hostname/port/database/user for the environment.
- [ ] Encode URI components properly, without double-encoding.
- [ ] Retrieve credentials from a secret store/passfile, not in source code.
- [ ] Verify JDBC properties against your pgJDBC version.
- [ ] `application_name` is useful for monitoring and contains no secrets.
- [ ] Distinguish connection, query, and pool timeouts and their units.

### 46.2. Network and TLS

- [ ] Endpoint reachable only from authorized networks.
- [ ] Appropriate PostgreSQL `listen_addresses`/port and HBA rules.
- [ ] TLS mode `verify-full` when server verification is required.
- [ ] Correct root CA on clients, with a rotation plan.
- [ ] Hostname matches certificate; no validation bypass.
- [ ] If using a proxy, control TLS on both client–proxy and proxy–server hops.
- [ ] SCRAM/auth method compatible across client, role, and server.

### 46.3. Permissions and Data

- [ ] Least-privilege database roles per service.
- [ ] GRANT/RLS/schema USAGE reviewed.
- [ ] Clients cannot spoof tenant identity.
- [ ] API uses parameterized SQL and validates dynamic identifiers.
- [ ] Do not use backend PID or `application_name` as an authenticated user ID.

### 46.4. Pool/Session

- [ ] Total maximum pool size fits `max_connections` and CPU/I/O.
- [ ] Connections always released in `finally`/try-with-resources.
- [ ] Transactions have COMMIT/ROLLBACK on every branch.
- [ ] Session `SET`/`ROLE`/`search_path` do not leak across checkouts.
- [ ] Do not leave sessions `idle in transaction`.
- [ ] Transaction pooling does not depend on session-level TEMP/LISTEN/advisory locks.
- [ ] Prepared statements verified compatible with PgBouncer/driver version.
- [ ] Pool evicts broken connections after failover/socket errors.

### 46.5. Operations/Failover

- [ ] `pg_stat_activity`/`pg_stat_ssl` observability in place.
- [ ] Alerts configured for pool pending, auth/TLS errors, and idle transactions.
- [ ] Retry/backoff and idempotency in place for unknown commit outcomes.
- [ ] Replica lag monitored if using read replicas.
- [ ] Credential/certificate rotation plan in place.
- [ ] Staging tests for DNS failover, proxy restarts, and application rolling deployments.

---

## 47. Application Connection Lifecycle Diagram

~~~mermaid
flowchart LR
    A["Application request"] --> B["Get Connection from pool"]
    B --> C{"Does pool have a valid connection?"}
    C -- "Yes" --> D["Borrow physical session"]
    C -- "No" --> E["DNS/TCP/TLS/Startup/Auth"]
    E --> D
    D --> F["Begin transaction if needed"]
    F --> G["SET LOCAL context / Prepared SQL"]
    G --> H{"Did SQL succeed?"}
    H -- "Yes" --> I["COMMIT"]
    H -- "No" --> J["ROLLBACK / retry policy"]
    I --> K["Reset session state per contract"]
    J --> K
    K --> L["Return logical connection to pool"]
    L --> M["Physical connection reused or closed"]
~~~

### 47.1. Three Principles to Preserve

**First**, credentials and TLS only determine how a session is established and secured; they do not replace row-level or object-level permissions.

**Second**, pool reuse optimizes resources, but turns resetting session state into a correctness and security requirement.

**Third**, retrying after a disconnect does not guarantee idempotency; unknown transaction outcomes must be resolved at the business layer.

---

## 48. Practice Exercises

These exercises use examples from the lesson. Questions containing SQL that modifies configuration or induces failing transactions should only be run in an authorized **test database**; do not disable TLS, create overly broad roles, or terminate backends in production to experiment.

### Exercise 1 — Connection Layers

A Java application reports `Connection refused` when calling the DB. List the layers to inspect in order from DNS to SQL permissions and explain why changing the password is not the first step.

### Exercise 2 — Hostname, Port, and Database

Explain the roles of `db.internal.example`, `5432`, and `shopdb` in `postgresql://app@db.internal.example:5432/shopdb`. Can the host and database have the same name?

### Exercise 3 — TCP vs. Unix Socket

On the same machine, `psql` without `-h` connects successfully, while `psql -h 127.0.0.1` fails. State two possible reasons.

### Exercise 4 — StartupMessage

Name at least three pieces of information a client can send when starting a PostgreSQL session. Is the password necessarily sent in plaintext inside StartupMessage?

### Exercise 5 — Authentication vs. Authorization

A role logs into PostgreSQL successfully, yet SELECT on a table reports `permission denied`. Why is passing HBA authentication not enough?

### Exercise 6 — ReadyForQuery

Explain the three transaction statuses `I`, `T`, and `E`. In which situation is `ROLLBACK` needed?

### Exercise 7 — Simple Query

Describe a simple query SELECT flow from frontend to backend. List the message types the server can return.

### Exercise 8 — Extended Query

Order the operations `Parse`, `Bind`, `Execute`, and `Sync`, and explain the purpose of parameter binding.

### Exercise 9 — Binding a Table Name?

Can you use `SELECT * FROM $1` and bind `$1='customers'` to substitute a table name? Propose a safe way to build dynamic identifiers.

### Exercise 10 — libpq URI Format

Write a URI for user `reporter`, host `db.example.internal`, port 5433, database `analytics`, requiring `sslmode=verify-full` and `application_name=nightly-report`. Do not embed a password.

### Exercise 11 — Percent-Encoding

How must the test value `p@ss/word#1` be written if forced into the password component of a URI? Why does encoding not secure a password?

### Exercise 12 — Double Encoding

What does `%40` become if encoded a second time? What character might the client interpret it as after decoding once?

### Exercise 13 — Query String

Add `connect_timeout=5` and `sslrootcert=/etc/postgresql/ca.pem` to the libpq URI with `sslmode=verify-full`. Point out which part of the URL needs percent-encoding.

### Exercise 14 — IPv6 Literal

Write the valid URI form for IPv6 host `2001:db8::5`, port 5432, and database `shopdb`.

### Exercise 15 — key=value

Rewrite the URI from Exercise 10 as a libpq key=value connection string. If `application_name` contains a space, how should it be handled?

### Exercise 16 — Service File

Create a `shop_readonly` profile containing host/port/db/user/TLS. Write a `psql` command using that profile. Why is a service file not necessarily the right place to store passwords?

### Exercise 17 — JDBC URL

Write the JDBC URL equivalent to the endpoint in Exercise 10. Is the JDBC format identical to a libpq URI in scheme and all query properties?

### Exercise 18 — JDBC PreparedStatement

Write a Java JDBC snippet querying by `customer_id` using a bind parameter and try-with-resources. Distinguish `?` in JDBC SQL from `?` starting URL query parameters.

### Exercise 19 — Comparing Timeouts

Distinguish libpq `connect_timeout`, HikariCP `connectionTimeout`, PostgreSQL `statement_timeout`, and pgJDBC `socketTimeout`.

### Exercise 20 — TLS Modes

Compare `require`, `verify-ca`, and `verify-full`. In production, when exact server hostname verification is needed, which one should be chosen?

### Exercise 21 — IP and Certificate

A certificate only lists DNS `db.example.internal`, yet the application changes the URL to IP `10.0.0.8`. Why might `sslmode=verify-full` fail? Should verification be turned off?

### Exercise 22 — SCRAM

Which two distinct tasks do SCRAM-SHA-256 and TLS address? Should you choose SCRAM alone without TLS on an untrusted network?

### Exercise 23 — HBA

Write an illustrative HBA line for role `app_reader` connecting to database `shopdb` from CIDR `10.20.0.0/16` over TLS using `scram-sha-256`.

### Exercise 24 — First-Match Rule

If a matching HBA rule is found but the password is wrong, does PostgreSQL automatically try the next rule to find another method?

### Exercise 25 — `pg_backend_pid`

Write a query returning the current backend PID, database, user, and `application_name`. Why should PID not be used as a business identity?

### Exercise 26 — Two Sessions

Open two independent `psql` connections and compare `pg_backend_pid()`. When using PgBouncer transaction pooling, how can the PID change between two transactions?

### Exercise 27 — `SET` and `SET LOCAL`

State the difference between `SET TIME ZONE 'UTC'` and `SET LOCAL TIME ZONE 'UTC'`. Write a transaction example to verify.

### Exercise 28 — Session State Leak

Pool size = 1. Request A runs `SET search_path=tenant_a` and returns the connection; request B queries an unqualified table. What risk arises and how do you mitigate it?

### Exercise 29 — Temp Table

A request creates a TEMP TABLE without `ON COMMIT DROP`. Can a subsequent request receiving the same backend see that table? Write the syntax to create a temp table that lasts only until COMMIT.

### Exercise 30 — Advisory Lock

Compare `pg_advisory_lock` and `pg_advisory_xact_lock` in terms of lifetime. Why is a session-level lock risky with a connection pool?

### Exercise 31 — LISTEN

Why is `LISTEN channel` incompatible with assuming a transaction pool keeps the same backend across multiple transactions?

### Exercise 32 — Pool Checkout

An application has 10 instances, each with a HikariCP pool max of 20 connections; plus 10 background connections. What is the total potential connection count? Why is this not a throughput guarantee?

### Exercise 33 — Pool Leak

An endpoint forgets to call `Connection.close()` on an error path. What symptoms can appear? Write a Java construct that guarantees returning the connection.

### Exercise 34 — Idle in Transaction

Explain why an `idle in transaction` backend can cause VACUUM/lock problems even when CPU is not high. Write a query to find the 10 transactions with the oldest `xact_start`.

### Exercise 35 — Transaction State E

After `BEGIN; SELECT 1/0; SELECT 42;`, what typically happens to the second SELECT? What must be done before continuing?

### Exercise 36 — Savepoint

Write SQL illustrating rolling back a failing statement to a savepoint and continuing the transaction. When should savepoints not be treated as a cure-all for connection errors?

### Exercise 37 — PgBouncer Pooling Modes

Compare session, transaction, and statement pooling. Which mode is most favorable for session-level prepared statements, temp tables, and LISTEN?

### Exercise 38 — Prepared Statements Through a Proxy

A Java application uses prepared statements, yet through PgBouncer transaction pooling encounters statement-does-not-exist errors. Name three parameters/components to inspect before abandoning parameterization.

### Exercise 39 — `pg_stat_activity`

Write a query grouping connection counts by `application_name` and `state`, and explain why `idle` does not equate to a leak.

### Exercise 40 — `pg_stat_ssl`

Write a query checking whether the current backend connection uses SSL and its TLS version. If `ssl=true`, does it prove the client used `verify-full`?

### Exercise 41 — Container `localhost`

An application running inside a Docker container uses JDBC host `localhost` to connect to PostgreSQL in another container. Why does it fail, and what hostname should be used?

### Exercise 42 — Multi-Host / Failover

Write a libpq URI containing two hosts `pg-a.internal.example`, `pg-b.internal.example`, database `shopdb`, and `target_session_attrs=read-write`. Does this URI automatically create replication or prevent split-brain?

### Exercise 43 — Read Replica Consistency

An application inserts into the primary and immediately selects from a replica, but does not see the row. Explain why and state two approaches when read-your-writes is required.

### Exercise 44 — Unknown Commit

Network connectivity drops right after the client sends `COMMIT` but before receiving the response. May we assume the transaction rolled back and retry INSERT with a new ID? Outline an idempotency design.

### Exercise 45 — Cancel Query

Distinguish query cancel, backend termination, `statement_timeout`, and `lock_timeout`. Why should you not call `pg_terminate_backend` on arbitrary PIDs to reduce connection count?

### Exercise 46 — Classifying Errors

Classify these five errors: DNS lookup failed, certificate verify failed, password authentication failed, permission denied for table, pool acquisition timeout. For each, give a diagnostic direction.

### Exercise 47 — Multi-Tenant Context

An RLS policy relies on `current_setting('app.tenant_id')`, yet the HTTP client can choose `tenant_id` arbitrarily. Why is this unsafe? Does `SET LOCAL` solve identity spoofing by itself?

### Exercise 48 — Comprehensive Diagnosis

A service uses HikariCP through PgBouncer transaction pooling with TLS across ~20 instances. After a failover, the app reports both `connection reset` and `prepared statement does not exist`, pool waiting rises, and in-flight transactions are retried. Propose an investigation/remediation runbook of at least eight steps covering transaction outcomes, credentials, TLS, pool/proxy, prepared statements, session state, retries, and observability.

---

## 49. Solutions and Explanations — Exercises 1 to 24

### Exercise 1 — Checking Layer by Layer

A logical order: DNS/hostname → TCP port/socket and routing/firewall → TLS negotiation/certificate → StartupMessage/role/database → HBA/password authentication → database privileges/SQL permissions → pool/session state.

`Connection refused` usually occurs at the transport layer when no service is listening on the endpoint or the connection is rejected. Passwords are only used once the authentication phase is reached; changing the password right away does not address the root cause.

### Exercise 2 — Host, Port, Database

- `db.internal.example`: network endpoint host.
- `5432`: server/proxy TCP port.
- `shopdb`: database name in the PostgreSQL cluster.
- `app`: database role requested for login.

The host and database names can syntactically match as strings, yet they are two different namespaces/concepts. Never infer the database name from the hostname.

### Exercise 3 — Socket Differs From TCP

There are at least two reasons:

1. `psql` without `-h` can use a Unix socket, whereas `-h 127.0.0.1` forces TCP. PostgreSQL might not be listening on TCP or may use a different port.
2. `pg_hba.conf` has a `local ... peer` rule for sockets, while the `host ...` rule for TCP requires a password or rejects the source.

Check `SHOW listen_addresses; SHOW port;` after connecting via socket and inspect the applicable HBA records. Do not change a rule to `trust` on untrusted networks to "fix" connections.

### Exercise 4 — StartupMessage

The client can send `user`, `database`, `application_name`, and valid startup parameters. Password authentication occurs in separate messages after the server selects an auth method; StartupMessage does not simply carry a plaintext password like a query string.

### Exercise 5 — Authentication Differs From Authorization

HBA/role authentication determines whether the user may enter a session. After that:

- `CONNECT` on the database may need checking.
- Schema `USAGE`, table/column `SELECT`, function privileges, and RLS govern SQL access.
- A role that connects successfully can still lack table read privileges.

Fix the error by granting the right scope/role or policies, not by granting superuser just to run SELECT.

### Exercise 6 — I, T, E

- `I`: idle, not inside an explicit transaction block.
- `T`: inside a valid transaction.
- `E`: inside a failed transaction block; requires `ROLLBACK` or appropriate savepoint recovery.

If a statement fails inside a `BEGIN` block, subsequent normal SQL can report "current transaction is aborted"; handle the transaction state first.

### Exercise 7 — Simple Query Messages

The client sends `Query("SELECT ...")`; the server can respond with `RowDescription`, zero or more `DataRow`, `CommandComplete`, and `ReadyForQuery`. On error, `ErrorResponse` enters the result stream as appropriate.

The protocol still uses binary-framed messages, not simply sending a SQL text line over TCP and waiting for a JSON line.

### Exercise 8 — Extended Query

A simplified sequence: **Parse → Bind → [Describe] → Execute → Sync**. Parse defines the prepared statement and SQL structure, Bind supplies parameter values and creates a portal, Execute runs it, and Sync ends the cycle per protocol rules.

Parameter binding separates data from SQL syntax; it reduces injection risks caused by input being concatenated as code.

### Exercise 9 — Parameters Do Not Replace Identifiers

Do not use `FROM $1` to bind a table name. Parameters represent **values**, not table/column/schema names.

If you must choose a table dynamically:

- Validate the identifier against an allowlist.
- In PL/pgSQL dynamic SQL, use `format('%I', identifier)` to quote object names.
- Use `EXECUTE ... USING` for values.
- In Java, select among fixed SQL statements from an allowed list instead of concatenating raw input.

### Exercise 10 — Correct URI

~~~text
postgresql://reporter@db.example.internal:5433/analytics?sslmode=verify-full&application_name=nightly-report
~~~

No password in the URL. The client still needs appropriate authentication via passfile/secret provider or another method. TLS `verify-full` requires the matching CA and endpoint certificate.

### Exercise 11 — Escaping a Dummy Password

`p@ss/word#1` → `p%40ss%2Fword%231`.

Structural form:

~~~text
postgresql://demo:p%40ss%2Fword%231@db.internal.example:5432/shopdb
~~~

This example only illustrates parsing, **not a recommendation to put secrets in URIs**. URI percent-encoding is trivially reversible and does not encrypt secrets.

### Exercise 12 — Double-Encoding

`%40` → `%2540`. The client decodes once into the literal `%40` rather than the `@` character. If the real password contains `@`, authentication can fail due to mismatched input.

### Exercise 13 — `connect_timeout` and CA

~~~text
postgresql://reporter@db.example.internal:5433/analytics?sslmode=verify-full&application_name=nightly-report&connect_timeout=5&sslrootcert=%2Fetc%2Fpostgresql%2Fca.pem
~~~

`%2F` encodes slashes in the file path. The CA file must exist **on the client side**. Do not place passwords in the URI for operational convenience.

### Exercise 14 — IPv6

~~~text
postgresql://app@[2001:db8::5]:5432/shopdb
~~~

Brackets `[ ]` enclose the IPv6 literal so `:` inside the IP is not confused with the host/port separator. This address is only an example.

### Exercise 15 — key=value

~~~text
host=db.example.internal port=5433 dbname=analytics user=reporter sslmode=verify-full application_name=nightly-report
~~~

If the application name contains a space:

~~~text
application_name='nightly report'
~~~

Libpq key=value has its own quoting/escaping rules; do not apply URI percent-encoding mechanically.

### Exercise 16 — Service Profile

Example:

~~~ini
[shop_readonly]
host=db-read.internal.example
port=5432
dbname=shopdb
user=app_reader
sslmode=verify-full
sslrootcert=/etc/postgresql/ca.pem
~~~

Connect:

~~~bash
psql "service=shop_readonly"
~~~

Do not embed passwords in shared profiles when a safer passfile/secret store is available. A service file is configuration, not a replacement for credential storage and TLS identity validation.

### Exercise 17 — JDBC URL

~~~text
jdbc:postgresql://db.example.internal:5433/analytics?sslmode=verify-full&ApplicationName=nightly-report
~~~

It is **not** identical to a libpq URI in scheme; JDBC uses the `jdbc:postgresql://` prefix. Property names/units and extension features must be checked against your pgJDBC version.

### Exercise 18 — PreparedStatement

~~~java
String sql =
    "SELECT customer_id, customer_name " +
    "FROM app.customers WHERE customer_id=?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, customerId);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getString("customer_name"));
        }
    }
}
~~~

`?` in `PreparedStatement` is a SQL bind placeholder; `?` in the URL starts the list of connection query parameters. Do not use raw string concatenation for `customerId` when the bind API is available.

### Exercise 19 — Timeouts

| Setting | Scope |
|---|---|
| libpq `connect_timeout` | Wait to open connection, per libpq semantics |
| HikariCP `connectionTimeout` | Wait to check out connection from pool, usually milliseconds |
| PostgreSQL `statement_timeout` | Server cancels statement exceeding time limit |
| pgJDBC `socketTimeout` | I/O/socket read waiting per driver semantics |

If the DB already has 12 busy connections, a HikariCP checkout timeout can occur even though the TCP endpoint is reachable. If a query runs too long, `statement_timeout` is one mechanism that cancels the statement.

### Exercise 20 — TLS `require`/`verify-ca`/`verify-full`

- `require`: requires TLS but does not explicitly guarantee verifying the exact hostname.
- `verify-ca`: verifies the CA chain.
- `verify-full`: verifies the CA and endpoint hostname.

When guarding against connecting to the wrong server on an untrusted network with proper PKI, use `verify-full` with the right root CA.

### Exercise 21 — Certificate Host Mismatch

The certificate only vouches for `db.example.internal`, while connecting to IP `10.0.0.8` checks against the endpoint name/IP. If the certificate lacks a matching IP identity, `verify-full` can reject it. Do not drop to `sslmode=disable`; use a valid DNS name or issue a proper certificate.

### Exercise 22 — SCRAM and TLS

SCRAM proves the client knows the credential per the auth method; TLS protects traffic and authenticates the server certificate when verification is configured properly. Using SCRAM alone on an unprotected path may fail to protect SQL/response data and server identity. Designs typically use both when remote connections traverse networks needing protection.

### Exercise 23 — HBA `hostssl`

~~~text
hostssl  shopdb  app_reader  10.20.0.0/16  scram-sha-256
~~~

This example only allows PostgreSQL TCP SSL/TLS connections from the listed IP range to the corresponding role/db per HBA; server TLS configuration and other related rules are also needed. Never copy sample ranges into production firewalls without verifying your actual network.

### Exercise 24 — First-Match

No. Once a matching HBA record is selected and authentication fails, PostgreSQL does not simply try subsequent rules. You must fix credentials, auth method, role, or HBA rule order accurately; never append a broad `trust` rule hoping for fallback.

---

## 50. Solutions and Explanations — Exercises 25 to 48

### Exercise 25 — Session Identity Query

~~~sql
SELECT
    pg_backend_pid() AS backend_pid,
    current_database() AS database_name,
    current_user AS db_role,
    current_setting('application_name') AS app_name;
~~~

Backend PID is the process identity serving the session at query time, not an authenticated principal, not durable across restarts/reconnects/pool routing, and can be reused. Never use it as a business data key.

### Exercise 26 — Two Sessions and PgBouncer

Open two direct `psql` sessions:

~~~sql
SELECT pg_backend_pid();
~~~

Normally you get two different PIDs. With PgBouncer transaction pooling, the same client session can use backend A in transaction 1 and backend B in transaction 2. When diagnosing, measure the PID **inside each transaction**, rather than inferring from one checkout.

### Exercise 27 — `SET` vs. `SET LOCAL`

~~~sql
SET TIME ZONE 'UTC';

BEGIN;
SELECT current_setting('TimeZone');
COMMIT;

SELECT current_setting('TimeZone');
~~~

`UTC` can remain because `SET` is session-level.

~~~sql
BEGIN;
SET LOCAL TIME ZONE 'Asia/Ho_Chi_Minh';
SELECT current_setting('TimeZone');
ROLLBACK;
SHOW TIME ZONE;
~~~

After ROLLBACK, `SET LOCAL` ceases to apply, and the session returns to its pre-transaction value (UTC in this example). Never run `SET LOCAL` without understanding transaction scope.

### Exercise 28 — Session State Leaking Through a Pool

Request B may use the wrong `search_path` and mistakenly read/update tenant A's schema if DB permissions allow it. Required steps:

- Use validated explicit schema/tenant mapping or proper RLS.
- Set transaction-scoped context using `SET LOCAL` where appropriate.
- Ensure rollback/cleanup on error.
- Configure the pool to reset session state per contract.
- Test alternating tenant A/B on pool size=1.
- Never rely solely on app-level filters to prevent cross-tenant data access.

### Exercise 29 — Temp Table

If using the same backend session and the temp table is still alive, the next checkout **can see the temp table**. Transaction-scoped pattern:

~~~sql
BEGIN;

CREATE TEMP TABLE tmp_ids(
    id bigint PRIMARY KEY
) ON COMMIT DROP;

INSERT INTO tmp_ids(id) VALUES (1),(2);
SELECT * FROM tmp_ids;

COMMIT;
~~~

After COMMIT, the temp table is dropped per `ON COMMIT DROP`. Do not rely on temp table names to share data across two backends in a transaction pool.

### Exercise 30 — Advisory Lock Lifetime

- `pg_advisory_lock(key)`: session-level lock; can persist after COMMIT and is released on unlock/session end.
- `pg_advisory_xact_lock(key)`: transaction-level lock; released when the transaction ends.

A session lock leaking through a pool can cause subsequent requests to hold unwanted locks or wait indefinitely. When a lock only serves a single transaction, prefer transaction-level locks if suitable.

### Exercise 31 — LISTEN and Backend Affinity

`LISTEN order_events` is a registration belonging to one backend session. A transaction pool can assign a different backend after COMMIT; the listener is not guaranteed to retain its registration on the backend in use to receive notifications. Use a dedicated session connection or a messaging/outbox pattern depending on your goal.

### Exercise 32 — Connection Budget

10 × 20 + 10 = **210 potential connections**. This is the number of connection slots that could be requested, not a throughput guarantee. The DB is still bounded by CPU/I/O/locks; many slow queries can reduce throughput even when the pool has available slots.

### Exercise 33 — Leak From Missing Close

When a code path fails to return a `Connection`, `active/in-use` in the pool climbs steadily, and new requests wait on checkout and can time out even while the server is alive.

Correct pattern:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(
         "SELECT current_database()");
     ResultSet rs = ps.executeQuery()) {

    if (rs.next()) {
        System.out.println(rs.getString(1));
    }
}
~~~

Try-with-resources closes `ResultSet`, `PreparedStatement`, and the logical `Connection` upon exiting the block, even if an exception is thrown.

### Exercise 34 — Idle in Transaction

An idle transaction can still hold locks and a snapshot, limiting MVCC/VACUUM cleanup. Inspect with:

~~~sql
SELECT
    pid,usename,application_name,state,
    xact_start,
    clock_timestamp()-xact_start AS age
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start
LIMIT 10;
~~~

When investigating, do not terminate a backend solely because it is at the top of the list; check valid business transactions, wait events, and operational authority.

### Exercise 35 — Failed Transaction

After `SELECT 1/0` inside `BEGIN`, the transaction can enter a failed state. `SELECT 42` is typically rejected with an error such as "current transaction is aborted". You must `ROLLBACK` or roll back to an appropriate savepoint if one exists before continuing business SQL.

### Exercise 36 — Savepoint

An operation pattern consisting of statements run **selectively based on error responses**:

~~~sql
BEGIN;
SAVEPOINT before_optional;
-- Run SQL that might fail.
-- When an error occurs, do not run arbitrary SELECTs:
ROLLBACK TO SAVEPOINT before_optional;
SELECT 42;
COMMIT;
~~~

This is a pseudo-sequence guiding the caller. If the connection has died, there is no reliable backend session to `ROLLBACK TO SAVEPOINT`. Serialization/deadlock failures typically require application-level transaction retry logic rather than treating savepoints as a universal fix.

### Exercise 37 — Three Pooling Modes

- **Session pooling:** backend stays bound to client session; better suited to state like temp tables, LISTEN, session advisory locks, and server-side prepared statements.
- **Transaction pooling:** backend is held for one transaction and returned to the pool; suited to stateless SQL or transaction-local state.
- **Statement pooling:** backend is assigned per statement, restricting multi-statement transaction patterns.

No single mode is best for every workload; choose based on the app's reliance on session state, DB connection capacity, and proxy/driver support.

### Exercise 38 — Prepared Statements Through PgBouncer

Check:

1. PgBouncer pooling mode and version.
2. PgBouncer `max_prepared_statements`/tracking capability if supported by the version.
3. pgJDBC version and server-side prepare threshold/caching.
4. SQL-level `PREPARE` versus protocol-level named statements.
5. Which backend PID change or pool checkout triggers the error.
6. Feasibility of switching to session pooling for workloads that require it.

**Do not switch to SQL concatenation**; keep using JDBC `PreparedStatement` parameter binding to prevent injection even when changing server-side prepare reuse.

### Exercise 39 — Grouping Connection Counts

~~~sql
SELECT
    application_name,
    state,
    COUNT(*) AS connection_count
FROM pg_stat_activity
WHERE backend_type='client backend'
GROUP BY application_name,state
ORDER BY connection_count DESC,application_name,state;
~~~

A pool intentionally maintaining idle backends can be normal. A leak typically shows up as **unreleased checkouts**, excessive pool active/in-use counts, and growing pending queues; compare pool metrics with DB metadata.

### Exercise 40 — Checking `pg_stat_ssl`

~~~sql
SELECT
    s.ssl,
    s.version AS tls_version,
    s.cipher
FROM pg_stat_ssl AS s
WHERE s.pid=pg_backend_pid();
~~~

`ssl=true` indicates the PostgreSQL backend sees TLS on that connection hop. It **does not prove** the client used `verify-full` on the certificate/hostname, nor does it describe the full `client -> proxy -> backend` path.

### Exercise 41 — `localhost` in a Container

Inside the app container, `localhost` refers to the app container's own network namespace. Because PostgreSQL is in another container, the hostname should be the **service name**/DNS name within the managed network (for example `postgres-db` if Docker Compose names the service that way).

You also need proper PostgreSQL listener/HBA/firewall settings and a matching certificate hostname. Do not expose the DB to the entire Internet to fix Docker networking.

### Exercise 42 — Multi-Host URI

~~~text
postgresql://app@pg-a.internal.example:5432,pg-b.internal.example:5432/shopdb?target_session_attrs=read-write&connect_timeout=5
~~~

This is an illustrative **libpq URI** configuration, not necessarily identical to pgJDBC failover syntax. It helps probe for an endpoint matching `read-write` per libpq rules, but **does not create replication, election, fencing, or split-brain protection**.

### Exercise 43 — Replica Lag

Asynchronous replication can cause a replica not to see a row just committed on the primary. Two approaches:

1. Read data requiring read-your-writes from the primary or via a session/routing strategy that guarantees consistency.
2. If you must read from a replica, wait for replay up to an appropriate WAL position/consistency token in a controlled manner, or accept eventual consistency in the API contract.

Do not simply raise client timeouts assuming the replica will instantly catch up.

### Exercise 44 — Unknown COMMIT

Do not automatically assume a rollback. Losing the response on the client can happen **after the server already committed** or before commit. Pattern:

- Every payment has an API-issued idempotency key.
- The database enforces UNIQUE on the idempotency key and checks payload consistency.
- On reconnect, query by business/idempotency key to reconcile.
- Use a transactional outbox tied to the DB commit for side effects.
- Retry with limits/backoff; never create duplicate payments while outcome is unconfirmed.

### Exercise 45 — Cancel and Terminate

- **Cancel query:** requests canceling the executing statement; the connection may remain alive.
- **Terminate backend:** terminates the session/backend, dropping the connection and any incomplete transaction.
- **`statement_timeout`:** server limit on statement execution duration.
- **`lock_timeout`:** limit on waiting for locks.

Arbitrarily terminating backends can roll back critical business work or trigger a reconnect storm. Inspect owner/application/query/waits and follow a runbook with proper authorization before intervening.

### Exercise 46 — Classifying Five Errors

| Error | Layer | Investigation |
|---|---|---|
| DNS lookup failed | Name resolution | DNS hostname/resolver/private zone |
| Certificate verify failed | TLS/PKI | CA file, hostname, expiry, proxy |
| Password authentication failed | Authentication | Role/password/SCRAM/HBA rule |
| Permission denied for table | SQL authorization | GRANT, schema, RLS, ownership |
| Pool acquisition timeout | Application pooling | Pool active/pending, checkout leaks, long transactions |

Do not fix an HBA error by increasing the pool; do not fix a certificate mismatch by granting table permissions.

### Exercise 47 — Untrusted Tenant Context

If an HTTP client can choose `app.tenant_id` arbitrarily, a policy relying on `current_setting` can trust a spoofed value. `SET LOCAL` only changes the **scope/lifetime of the setting**, not who is authorized to pick the tenant.

You need a trusted authenticated layer/role mapping, proper database permissions/RLS, and session/transaction context that clients cannot tamper with.

### Exercise 48 — Post-Failover Runbook

A runbook:

1. Record the failover timestamp, affected services, endpoints, and proxy/driver versions.
2. Separate errors by SQLSTATE/network errors instead of lumping all failures together.
3. Verify DNS, TCP, firewall, and hostname/TLS certificate/CA against the new endpoint.
4. Inspect PgBouncer client/server pool status and primary/replica health.
5. Compare HikariCP active/pending/idle, checkout timeouts, connection churn, and DB `max_connections`.
6. Check pgJDBC prepared statement behavior and PgBouncer pooling mode/version/tracking.
7. Evict broken connections and ensure transaction rollback/session cleanup before reuse.
8. Reconcile operations with **unknown commit outcomes** via idempotency keys; never unconditionally retry INSERTs.
9. Verify read/write routing, `pg_is_in_recovery()`, and replication lag.
10. Bound retries/backoff to prevent a reconnect storm.
11. Inspect `pg_stat_activity`, `pg_stat_ssl`, wait events, logs, and sanitized SQLSTATEs.
12. Reconcile business data/outbox, fix configuration, and test failure injection in staging.
13. Roll out changes via canary with an approved rollback path.
14. Separate root causes: network failover, prepared statement session affinity, pool exhaustion, and retry/idempotency may be **multiple independent bugs**.

Never disable TLS or grant superuser just to make connections "succeed" before completing root-cause analysis.

---

## 51. Extra Practice: A Two-Connection Session Inspection Scenario

This is a small lab requiring no table-creation privileges. Open two `psql` windows to the same database, using direct connections if possible to observe backend state clearly.

### 51.1. Session A

~~~sql
SELECT pg_backend_pid() AS pid_a;
SET application_name='lesson-session-A';
SET TIME ZONE 'UTC';

BEGIN;
SET LOCAL statement_timeout='3s';
SELECT current_setting('TimeZone') AS timezone_a,
       current_setting('statement_timeout') AS timeout_a;
COMMIT;

SELECT current_setting('TimeZone') AS timezone_after,
       current_setting('statement_timeout') AS timeout_after;
~~~

The session-level timezone can remain UTC, whereas the local `statement_timeout` reverts to its pre-transaction value.

### 51.2. Session B

~~~sql
SELECT pg_backend_pid() AS pid_b,
       current_setting('application_name') AS app_b,
       current_setting('TimeZone') AS timezone_b;
~~~

Session B does not inherit A's `SET` commands when the two connections genuinely point to separate backend sessions. If using PgBouncer transaction pooling, explain the difference in session mapping.

### 51.3. Observing `pg_stat_activity`

~~~sql
SELECT
    pid,
    application_name,
    state,
    backend_start,
    xact_start
FROM pg_stat_activity
WHERE datname=current_database()
ORDER BY backend_start DESC
LIMIT 20;
~~~

You can see sessions A/B if your role has privileges to view the corresponding metadata. Do not use this query to conclude all clients are visible when monitoring privileges are restricted.

### 51.4. Cleaning Up Lab State

~~~sql
RESET application_name;
RESET TIME ZONE;
RESET statement_timeout;
~~~

If you want a completely clean session, close the connection and open a new session; do not treat `RESET ALL` as clearing all temp objects/locks/prepared statements.

---

## 52. Official Documentation and Version-Specific Lookup

When configuring production, prioritize documentation for the **exact major version of your client and server**, especially for TLS/proxy pooling:

- [PostgreSQL — Frontend/Backend Protocol](https://www.postgresql.org/docs/current/protocol.html): overall wire protocol structure.
- [PostgreSQL — Protocol Flow](https://www.postgresql.org/docs/current/protocol-flow.html): startup, authentication, simple and extended queries.
- [PostgreSQL — Message Formats](https://www.postgresql.org/docs/current/protocol-message-formats.html): message types, fields, and ReadyForQuery.
- [PostgreSQL — libpq Connection Strings](https://www.postgresql.org/docs/current/libpq-connect.html): URI/key=value, host lists, `target_session_attrs`.
- [PostgreSQL — libpq Environment Variables](https://www.postgresql.org/docs/current/libpq-envars.html): `PGHOST`, `PGUSER`, `PGSERVICE`, and other variables.
- [PostgreSQL — libpq Password File](https://www.postgresql.org/docs/current/libpq-pgpass.html): structure and permissions of passfiles.
- [PostgreSQL — libpq Service Files](https://www.postgresql.org/docs/current/libpq-pgservice.html): named connection profiles.
- [PostgreSQL — SSL/TLS Support](https://www.postgresql.org/docs/current/ssl-tcp.html): server/client TLS configuration.
- [PostgreSQL — Client Authentication](https://www.postgresql.org/docs/current/client-authentication.html): `pg_hba.conf` and auth methods.
- [PostgreSQL — pg_stat_activity](https://www.postgresql.org/docs/current/monitoring-stats.html): session state, wait events, statistics.
- [PostgreSQL — Run-time Configuration](https://www.postgresql.org/docs/current/runtime-config.html): timeouts, connection limits, logging, and session settings.
- [PostgreSQL — SET](https://www.postgresql.org/docs/current/sql-set.html): session and transaction-local configuration.
- [PostgreSQL — DISCARD](https://www.postgresql.org/docs/current/sql-discard.html): cleaning up session state.
- [PostgreSQL — LISTEN](https://www.postgresql.org/docs/current/sql-listen.html): session notification behavior.
- [PostgreSQL — Advisory Locks](https://www.postgresql.org/docs/current/explicit-locking.html): session-level and transaction-level advisory locks.
- [PostgreSQL JDBC Driver — Documentation](https://jdbc.postgresql.org/documentation/): pgJDBC URL, connection properties, prepared statements, and TLS.
- [HikariCP — Project Documentation](https://github.com/brettwooldridge/HikariCP): pool lifecycle and configuration.
- [PgBouncer — Documentation](https://www.pgbouncer.org/config.html): `pool_mode`, prepared statements, authentication, TLS/proxy config.

`/current/` URLs point to the latest PostgreSQL docs and do not guarantee matching your running server. When discussing protocol extensions, libpq attributes, TLS negotiation, `pgJDBC`, and `PgBouncer`, check **versions of each component**, not only the server.

---

## 53. Summary

**The PostgreSQL connection protocol is stateful, and a URI is only one way to describe how a client locates and establishes a session.** For an application to operate safely, you must distinguish all layers:

1. **Network endpoint**: DNS, TCP port, Unix socket, firewall, proxy routing.
2. **Transport security**: TLS, root CA, and hostname verification (typically `sslmode=verify-full` with libpq and proper PKI).
3. **PostgreSQL startup/auth**: StartupMessage, HBA, SCRAM/peer/cert, ParameterStatus, and ReadyForQuery.
4. **Wire protocol**: Simple Query or Extended Query with Parse/Bind/Execute/Sync; applications should use parameterized queries to separate data from SQL.
5. **Connection strings**: libpq URI, libpq key=value, and pgJDBC URL are **not fully equivalent**; special characters in URIs must be properly percent-encoded, and credentials should be stored outside URLs.
6. **Session**: carries backend state across multiple transactions, including session `SET`, temporary objects, LISTEN, advisory locks, and prepared statements.
7. **Transaction**: unit of atomicity/isolation; COMMIT/ROLLBACK releases transaction resources, but does not necessarily close the session or reset all state.
8. **Connection pool**: logical `close()` may only return a connection to the pool. Pools must reset session state, avoid returning backends in a failed transaction, and bound total connections appropriately.
9. **PgBouncer**: session pooling preserves affinity better for session features; transaction pooling can switch backends between transactions, requiring version-specific checks for prepared statement support.
10. **TLS and auth do not replace privileges**: connecting successfully does not prove a role has SELECT/UPDATE access to objects or proper tenant isolation.
11. **Per-layer timeouts**: connect, pool checkout, SQL statement, lock, and socket/read timeouts are not interchangeable.
12. **Observability**: `pg_stat_activity`, `pg_stat_ssl`, `pg_backend_pid()`, `application_name`, and SQLSTATE help pinpoint errors at the right layer.
13. **Failover and retries**: multi-host URIs aid endpoint selection but do not create HA; losing a connection during COMMIT can leave the transaction outcome unknown, requiring idempotency/reconciliation.
14. **Long-term security**: secret management, certificate rotation, least-privilege roles, session hygiene, proper RLS, and staging tests are ongoing operational requirements, not just initial setup.

Workflow to remember: **read URI and driver config → verify DNS/TCP/socket → handshake TLS and authentication → identify session/backend identity → execute SQL with bind parameters and transaction boundaries → return connection per pool contract → observe timeouts/locks/state → handle failover/retries using idempotency and business data**.
