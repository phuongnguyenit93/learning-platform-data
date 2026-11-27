# Client and Server Model in a PostgreSQL Session

When a Java application sends a `SELECT` statement, the data is not read directly from PostgreSQL files by that application. The application acts as a **client**: it opens a connection to PostgreSQL, sends requests over the PostgreSQL protocol, receives data, and closes or reuses the connection. On the PostgreSQL side is the **server**: it authenticates the request, manages the session, processes SQL, coordinates transactions, and accesses stored data.

This is the foundation of PostgreSQL's **client–server** architecture: each direct connection to PostgreSQL is served by a dedicated **backend process** in PostgreSQL's traditional process model. Multiple backends share the common resources of a single PostgreSQL instance, such as shared memory, the buffer pool, the locking system, WAL, and the databases within the same cluster.

This lesson walks from the moment an application initiates a connection until a session ends: specifying host/port/database, authenticating, spawning a backend, sending SQL, running transactions, inspecting connection state, and closing the connection. The examples use modern PostgreSQL (such as PostgreSQL 16) and the `psql` tool.

## 1. Components in the Client–Server Model

Consider a simple e-commerce system with a web application, an administration tool, and PostgreSQL:

~~~text
   Java Application          psql Tool                 Reporting Tool
   (PostgreSQL JDBC)         (libpq)                   (SQL driver)
          |                     |                            |
          | TCP/IP              | TCP or Unix socket         | TCP/IP
          +---------------------+----------------------------+
                                |
                                v
                      PostgreSQL server
                    (main supervisor process)
                                |
                 +--------------+---------------+
                 |              |               |
                 v              v               v
           Backend #1      Backend #2       Backend #3
           for Java        for psql         for reporting
                 |              |               |
                 +--------------+---------------+
                                |
                   Shared memory and resources
             shared_buffers, locks, WAL, catalog...
                                |
                                v
                      Data files in PGDATA
~~~

In the diagram:

- **Client** is the program that originates requests; it can be `psql`, pgAdmin, DBeaver, Java JDBC, Python, or another service.
- **Connection** is the communication channel between the client and PostgreSQL. A connection can use TCP/IP or a Unix-domain socket where supported by the environment.
- **PostgreSQL server** is the instance that manages a database cluster and accepts connections according to configuration.
- **Backend process** is the server-side PostgreSQL process dedicated to a direct connection that executes requests for that session.
- **Shared resources** enable backends to access data consistently together, without turning all connections into a single SQL process.

### How do cluster, database, and session differ?

| Term | Meaning in PostgreSQL | Example |
| --- | --- | --- |
| **Cluster** | A collection of databases managed by one PostgreSQL instance | PGDATA containing `postgres` and `shopdb` |
| **Database** | A container holding schemas, tables, views, and other objects | `shopdb` |
| **Role** | An identity that can be used to log in or receive privileges | `shop_app` |
| **Connection** | The client–server communication channel | TCP to `127.0.0.1:5432` |
| **Session** | The working session from connection establishment until termination | A `psql` session |
| **Transaction** | A group of SQL operations that is committed or rolled back | `BEGIN ... COMMIT` |
| **Backend process** | The server process executing requests for a connection | The PID shown via `pg_backend_pid()` |

A **session can contain multiple transactions**. Conversely, a normal transaction runs within the scope of a single session. Session settings, temporary tables, and prepared statements have a different lifecycle from data changes managed by transactions.

## 2. Server Process and Backend Process

When PostgreSQL starts, the main process (often called the **postmaster**, running the same `postgres` executable) initializes shared resources and listens for connections.

When a client connects successfully, PostgreSQL sets up a backend process to serve that connection. The backend is responsible for communicating with the client, processing SQL requests, and participating in transaction management.

~~~text
PostgreSQL instance
│
├── Postmaster / main server process
│   ├── Accept new connections
│   ├── Manage child processes and server lifecycle
│   └── Coordinate system resources
│
├── Client backend: PID 30101  ← Java session #1
├── Client backend: PID 30102  ← Java session #2
├── Client backend: PID 30103  ← psql session
│
├── Background processes
│   ├── Checkpointer
│   ├── Background writer
│   ├── WAL writer
│   ├── Autovacuum processes
│   └── Other auxiliary processes depending on configuration
│
└── Shared memory and files in PGDATA
~~~

**Key distinction:** client backends and background processes are not the same kind of process. A backend is tied to a connection session, whereas background processes perform shared work such as writing data pages, writing WAL, automatic maintenance, or supporting replication.

### Is one connection one thread?

In the traditional PostgreSQL model, each normal direct client connection uses **one operating system process on the server**, rather than a Java thread or a single thread shared across all connections. Therefore, opening a very large number of concurrent connections incurs memory, process-management, and resource overhead.

This conclusion applies to **clients connecting directly to PostgreSQL**. If there is a proxy/pooler such as PgBouncer, the number of client connections pointing into the pooler can **differ** from the number of connections actually open to PostgreSQL.

### What do backends share and what is private?

| Resource | Typical scope |
| --- | --- |
| `shared_buffers` and shared memory structures | Shared across backends within the same instance |
| Table data, indexes, and WAL | Shared resources of the database/cluster |
| Transaction IDs, locking, MVCC | Coordinated across backends |
| A backend PID | Belongs to the process serving one direct connection |
| `SET` parameters in a session | Usually effective only within that session |
| Temporary tables and session-level prepared statements | Tied to the corresponding session |
| Results of an executing query | Handled by the backend and sent back to the client |

This explains two seemingly contradictory behaviors: **multiple sessions view the same table data**, yet **changing `search_path` or creating a temporary table in session A does not give session B that same state**.

## 3. From Client to PostgreSQL: host, port, database, user

To establish a connection, a client typically provides at least these attributes:

~~~text
Host      = db.example.internal
Port      = 5432
Database  = shopdb
User      = shop_app
Password  = authentication secret if required
TLS       = depending on configuration and environment policy
~~~

Example `psql` command:

~~~bash
psql \
  -h 127.0.0.1 \
  -p 5432 \
  -U shop_app \
  -d shopdb \
  -W
~~~

`-W` tells `psql` to prompt for a password proactively. It does not replace server-side authentication configuration. `shop_app` and `shopdb` are **placeholder** names: replace them with an existing, authorized role/database.

### 3.1. TCP/IP and Unix-domain sockets

In Unix/Linux environments, two common connection types are:

~~~bash
# TCP/IP over loopback:
psql -h 127.0.0.1 -p 5432 -U shop_app -d shopdb

# Unix socket: omit -h when the tool can find the default socket;
# or specify the socket directory explicitly, for example:
psql -h /var/run/postgresql -p 5432 -U shop_app -d shopdb
~~~

Differences:

- `127.0.0.1` is the TCP loopback address of the machine running the client.
- A path like `/var/run/postgresql` in `-h` specifies the **directory containing the Unix socket**, not an IP address.
- Unix socket connections can be configured to authenticate using the `peer` method; TCP connections are governed by matching `host` rules in `pg_hba.conf`.
- `localhost` may resolve to IPv4 or IPv6; do not assume it always equals `127.0.0.1` in every environment.

On Windows, local connection mechanisms differ from traditional Linux Unix sockets; use the appropriate TCP host/port.

If the application runs in another container, `127.0.0.1` inside that container points to **the application container itself**. With Docker Compose on the same network, you typically use the **PostgreSQL service name** as the host and internal port `5432`.

### 3.2. One session connects to one database

A PostgreSQL connection is established to **one specific database**. In `psql`, switching databases with the `\connect` meta-command creates a **new connection**:

~~~text
\connect shopdb shop_app
~~~

PostgreSQL does not use `USE other_database;` syntax like some other database systems. A normal SQL session cannot directly query an arbitrary table in another database simply by prefixing the database name. When cross-database access is needed, it requires an explicit design such as `postgres_fdw` or `dblink`, with appropriate permissions and configuration.

## 4. Connection Lifecycle: From Handshake to Ready Session

A simplified sequence:

~~~text
Client                             PostgreSQL
  |                                     |
  |-- Open TCP / Unix socket ---------->|
  |                                     |
  |-- TLS negotiation (if used) ------->|
  |<------- Negotiation response -------|
  |                                     |
  |-- Send startup parameters --------->|
  |   user, database, application_name  |
  |                                     |
  |<-- Authentication request (if needed)|
  |-- Authentication response --------->|
  |                                     |
  |<-- Accept connection / parameters --|
  |<-- Ready for Query -----------------|
  |                                     |
  |-- SQL query / bind / execute ------>|
  |<-- Row data / command status -------|
  |<-- Ready for Query -----------------|
  |                                     |
  |-- Subsequent requests ------------->|
  |<-- Subsequent results --------------|
  |                                     |
  |-- Close connection ---------------->|
  |                                     |
~~~

This is a conceptual model, not a complete transcript of every message in the PostgreSQL wire protocol. Negotiation may include additional steps such as GSS encryption, authentication mechanism selection, and driver-specific messages.

### Step 1: is the server listening?

PostgreSQL must be running and listening on the appropriate address and port. Relevant settings usually include:

- `listen_addresses`: the TCP addresses the server listens on.
- `port`: the PostgreSQL port, commonly `5432`.
- `unix_socket_directories`: where Unix sockets are created on supported operating systems.
- Firewalls, routing, container networking, or cloud provider network policies.

For example, a server listening only on `localhost` will not automatically accept TCP connections from another machine, even with a valid user/password.

### Step 2: authentication and connection privileges

Once the client reaches the server, PostgreSQL checks the request against **`pg_hba.conf`** to determine how to authenticate it. Matching rules typically evaluate:

- Connection type: `local` (Unix socket), `host`, `hostssl`, or appropriate variants.
- Target database.
- Login role.
- Client source address for TCP connections.
- Authentication method, such as `scram-sha-256`, `peer`, or another administrator-chosen method.

PostgreSQL evaluates `pg_hba.conf` records **in order**; the first matching record determines the authentication method. Once a record matches and authentication fails, PostgreSQL does not automatically fall through to later records to try another method.

Beyond authentication, the role needs the `LOGIN` attribute and `CONNECT` privilege on the target database. Logging in successfully does not grant `SELECT` on every table.

### Step 3: backend and session state

After the connection is established, the backend handles session requests. The client receives session parameters from the server and can begin sending queries. Application name, database, role, timezone settings, and protocol details become part of the session context.

A client can connect successfully yet fail when executing a query due to missing permissions on a schema/table. **Connection errors, authentication errors, and SQL permission errors are three distinct categories**.

## 5. Server-Side Execution Flow of an SQL Statement

After connecting, the client sends an SQL statement, for example:

~~~sql
SELECT order_id, total_amount
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 10;
~~~

The backend processes the request through logical stages:

~~~text
SQL from client
       |
       v
  Parse (syntax parsing)
       |
       v
  Analyze / Rewrite
  - resolve columns, tables, data types
  - check permissions, related objects
  - apply rewrite rules
       |
       v
  Planner / Optimizer
  - choose scan / index / join / sort
  - estimate cost based on statistics
       |
       v
  Executor
  - run the plan
  - read data pages via buffer manager
  - follow MVCC, locks, and transaction rules
       |
       v
  Results returned via protocol to client
~~~

In practice, PostgreSQL can prepare and reuse SQL statements, cache appropriate components, or perform other protocol steps; do not treat the diagram above as meaning every invocation repeats all work identically from scratch.

### Backends and shared buffers

A backend does not simply read PostgreSQL files directly and send data back. It normally goes through buffer and I/O management components:

~~~text
Backend
   |
   v
Shared buffers  <---->  Data files on storage
   |
   +----> Lock / MVCC / WAL depending on operation
~~~

An accessed data page may already reside in `shared_buffers` or need to be loaded from storage. For write statements, in-memory page modifications and the WAL mechanism coordinate to ensure crash recovery according to PostgreSQL's durability guarantees.

Multiple backends share the buffer pool while maintaining **independent session and transaction states**; PostgreSQL coordinates concurrent access using MVCC and locking rather than allowing uncoordinated writes to data files.

### Does a large SQL query always run on a single process?

The client's backend is the coordinator for the session, but PostgreSQL can use **parallel query workers** for eligible queries. Therefore, "one backend per connection" does not mean a single query can never use additional worker processes.

## 6. How Does a Session Differ from a Transaction?

This is especially important in operations.

A **session** starts once the connection is established and ends when the connection closes. Within a session, the client can run sequentially:

~~~text
Session A
|
|-- SELECT 1;                     implicit transaction 1
|
|-- BEGIN;
|     UPDATE ...;
|     SELECT ...;
|   COMMIT;                        transaction 2
|
|-- SELECT now();                  implicit transaction 3
|
|-- BEGIN;
|     UPDATE ...;
|   ROLLBACK;                      transaction 4
|
|-- Close connection
~~~

The "implicit transaction" label above matches how `psql` or drivers operate in normal **autocommit** mode: each standalone SQL statement outside `BEGIN` runs in its own transaction. PostgreSQL does not have a server setting meaning "every session is always autocommit" in the exact way some JDBC libraries describe it; how the client groups SQL statements and sends `BEGIN` determines transaction boundaries.

### 6.1. Explicit transaction example

~~~sql
BEGIN;

UPDATE lab_accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE lab_accounts
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
~~~

This is a syntax example for a hypothetical `lab_accounts` table. Both `UPDATE` statements belong to the same transaction; if an error occurs or cancellation is needed, `ROLLBACK` discards uncommitted changes.

The session **remains open after `COMMIT`**. The client can send further SQL statements over the same connection.

### 6.2. When a transaction encounters an error

In PostgreSQL, when an SQL statement puts the current transaction into an error state, subsequent statements in that same transaction are normally rejected until `ROLLBACK` is executed or control returns to an appropriate savepoint.

Example:

~~~sql
BEGIN;
SELECT 1 / 0;   -- Intentionally cause an error.
SELECT 2;       -- Fails because the transaction is marked aborted.
ROLLBACK;
SELECT 3;       -- Runs in a new/implicit transaction.
~~~

This is a key operational distinction: **a single statement error can prevent the entire uncommitted transaction from continuing**, without necessarily closing the whole session.

### 6.3. Session SET and transaction SET LOCAL

PostgreSQL supports session-scoped configuration parameters:

~~~sql
SHOW search_path;

SET search_path = public;
SHOW search_path;
~~~

If `SET` succeeds and is committed when executed inside a transaction, the value normally remains active in the session until changed/reset or the session closes.

Inside a transaction, you can set a value for that transaction only:

~~~sql
BEGIN;
SET LOCAL statement_timeout = '2s';

SELECT current_setting('statement_timeout');

COMMIT;

SELECT current_setting('statement_timeout');
~~~

After `COMMIT`, the `SET LOCAL` setting no longer applies; the previous session value or baseline configuration is restored. This is useful for bounding execution time for one group of statements without affecting all later queries in the session.

## 7. Information and Objects Scoped to a Session

Not all state created inside a session is shared with other sessions.

### 7.1. Session parameters

~~~sql
SET application_name = 'psql-lab-A';
SET TIME ZONE 'Asia/Ho_Chi_Minh';

SHOW application_name;
SHOW TimeZone;
~~~

These settings affect how the session processes/displays certain values and how it appears in monitoring tools. They **do not change the timezone or application_name of other connections**.

### 7.2. Temporary tables

~~~sql
CREATE TEMP TABLE session_notes (
    id integer,
    note text
);

INSERT INTO session_notes (id, note)
VALUES (1, 'Only this session sees the temporary table');

SELECT * FROM session_notes;
~~~

Temporary tables are tied to the session that creates them; other sessions cannot directly access that temporary table by its regular name. By default, unless `ON COMMIT DROP` or `ON COMMIT DELETE ROWS` is specified, a temporary table persists across `COMMIT` within the same session and is dropped when the session ends.

**Distinction:** being session-scoped does not mean rows in a temporary table bypass transaction rules. An `INSERT` into a temporary table inside a rolled-back transaction is still subject to rollback.

### 7.3. Prepared statements

~~~sql
PREPARE find_order(bigint) AS
SELECT order_id, total_amount
FROM orders
WHERE order_id = $1;

EXECUTE find_order(1001);
~~~

This example assumes the `orders` table exists. `PREPARE` creates a session-level prepared statement; other sessions do not automatically get `find_order`. When the session ends, session-level prepared statements are no longer usable on that connection.

Drivers such as JDBC may use the PostgreSQL extended query protocol and manage prepared statements according to their own policies. Do not assume JDBC prepared statement names or lifetimes match writing `PREPARE ... EXECUTE` in SQL.

### 7.4. Session role and permissions

Commonly used functions:

~~~sql
SELECT
    session_user,
    current_user,
    current_database();
~~~

`session_user` is normally the role used to initiate the session, while `current_user` is the identity used when checking permissions in the current execution context. Mechanisms such as `SET ROLE` or `SECURITY DEFINER` functions can make them differ.

Do not treat `application_name` or the client's connection address as proof that an SQL statement has access rights; evaluate role privileges and active security policies instead.

## 8. Inspecting a Session Yourself with psql

Log in to a lab PostgreSQL instance you are authorized to access:

~~~bash
psql -h 127.0.0.1 -p 5432 -U lab_user -d lab_db
~~~

This command assumes the `lab_user` role and `lab_db` database already exist. Once connected, you can run:

~~~sql
SELECT
    current_database() AS database_name,
    session_user AS login_role,
    current_user AS effective_role,
    pg_backend_pid() AS backend_pid,
    inet_client_addr() AS client_address,
    inet_client_port() AS client_port,
    inet_server_addr() AS server_address,
    inet_server_port() AS server_port;
~~~

| Function / info | Helps confirm |
| --- | --- |
| `current_database()` | Database of the current connection |
| `session_user` | Role that started the session |
| `current_user` | Effective role in the current context |
| `pg_backend_pid()` | PID of the backend process serving the connection |
| `inet_client_addr()` | Client IP address if connected over TCP |
| `inet_client_port()` | Client source port for TCP |
| `inet_server_addr()` | Server IP address used by the connection |
| `inet_server_port()` | Server port for TCP connections |

**Note:** the `inet_*` functions can return `NULL` for Unix-domain socket connections. That does not mean the session has failed or lacks a backend.

In `psql`, run:

~~~text
\conninfo
~~~

This displays current connection details, including user, database, and address/port or socket depending on the connection method.

### How to verify two independent connections

Open two `psql` windows connected to `lab_db`. In each window:

~~~sql
SELECT pg_backend_pid(), current_database(), current_user;
~~~

Two concurrent direct connections normally have **two different backend PIDs**. If you close and reopen a connection, the PID can change; a PID is not a permanent identifier for a user or business history.

## 9. Experiment: Two Sessions Accessing Data Concurrently

This experiment demonstrates that sessions have independent state, yet both read/write **the same committed data** governed by MVCC and isolation rules.

Prepare once using a role permitted to create tables in the lab schema:

~~~sql
CREATE TABLE IF NOT EXISTS session_lab_accounts (
    account_id integer PRIMARY KEY,
    balance integer NOT NULL
);

INSERT INTO session_lab_accounts (account_id, balance)
VALUES (1, 1000)
ON CONFLICT (account_id)
DO UPDATE SET balance = EXCLUDED.balance;
~~~

**Run this only in a lab database**; the `ON CONFLICT ... DO UPDATE` clause intentionally resets `balance = 1000` if the row already exists, so it is unsuitable for real business data.

Assume both `psql` windows run at the default `READ COMMITTED` isolation level and have `SELECT` privileges on the table. Even if session B lacks write privileges, you can still observe the read behavior.

### Step 1: Session A makes an uncommitted change

In window A:

~~~sql
SET application_name = 'session-lab-A';

BEGIN;
UPDATE session_lab_accounts
SET balance = 900
WHERE account_id = 1;

SELECT balance
FROM session_lab_accounts
WHERE account_id = 1;
-- A sees 900 because A's own transaction just updated it.
~~~

**Do not commit yet.** Keep transaction A open for step 2.

### Step 2: Session B reads the same row

In window B:

~~~sql
SET application_name = 'session-lab-B';

SELECT pg_backend_pid() AS pid_b;

SELECT balance
FROM session_lab_accounts
WHERE account_id = 1;
-- B normally still sees 1000 under READ COMMITTED.
~~~

Because A has not committed, session B does not see A's change through a normal `SELECT` under `READ COMMITTED`. This illustrates transaction isolation, not two sessions storing separate copies of the table.

### Step 3: Session A commits

In window A:

~~~sql
COMMIT;
~~~

### Step 4: Session B reads again

~~~sql
SELECT balance
FROM session_lab_accounts
WHERE account_id = 1;
-- B sees 900 in a new read transaction under READ COMMITTED.
~~~

From this experiment:

- A and B have **separate backends**, yet access the same table.
- Before `COMMIT`, A's modification does not appear in a normal consistent read by B.
- After `COMMIT`, a new `SELECT` by B under `READ COMMITTED` can see the committed data.
- Sessions do not close automatically when a transaction completes.

**Important exception:** under `REPEATABLE READ`, if B already started a transaction and took its snapshot before A committed, subsequent consistent reads in B can continue seeing the old snapshot within that same transaction. Do not conclude "after commit, every active session immediately sees the new result" while ignoring isolation levels and read semantics.

After the experiment, in a session with no open transaction:

~~~sql
DROP TABLE IF EXISTS session_lab_accounts;
~~~

Only perform cleanup after confirming this is the lab test table and no application depends on that data.

## 10. Observing Sessions with pg_stat_activity

PostgreSQL provides the `pg_stat_activity` view to monitor server and backend activity. Common columns for client sessions include:

| Column | Content |
| --- | --- |
| `pid` | Backend PID |
| `usename` | Recorded login role name |
| `datname` | Connected database |
| `application_name` | Application name set by the client |
| `client_addr` | Client IP address when applicable |
| `client_port` | Source port or special indicator depending on connection type |
| `backend_start` | Timestamp when the backend was started |
| `xact_start` | Timestamp when the current transaction started, if any |
| `query_start` | Timestamp when the recorded query started |
| `state` | Current state, such as `active` or `idle` |
| `wait_event_type`, `wait_event` | Wait event category and name, if the backend is waiting |
| `query` | Recent/currently running query depending on state and visibility privileges |

Example monitoring query:

~~~sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    client_addr,
    backend_start,
    xact_start,
    state,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE backend_type = 'client backend'
  AND datname = current_database()
ORDER BY backend_start, pid;
~~~

In modern PostgreSQL, `pg_stat_activity` also includes background processes; filtering by `backend_type = 'client backend'` focuses on client connections.

### Privileges to view other sessions' state

Users can usually see full details of **sessions owned by their own role**, whereas some fields from other sessions may be hidden or restricted without sufficient privileges. A monitoring role granted `pg_read_all_stats` or equivalent privileges can inspect more details. Do not grant superuser solely to read a dashboard when dedicated monitoring roles suffice.

### What states can a session be in?

| `state` | Interpretation | Investigation direction |
| --- | --- | --- |
| `active` | Backend is executing a query | Long-running query, CPU/I/O, lock waits |
| `idle` | Session is waiting for the next command from client | Pool holding connections or app forgot to close? |
| `idle in transaction` | Client has not sent a new command, but transaction remains open | Holding locks or snapshots too long? |
| `idle in transaction (aborted)` | Transaction failed and is waiting for client rollback | Did the app forget error handling/rollback? |

`state = 'active'` does not automatically mean the backend **is using CPU**: it may be waiting on I/O or waiting for a lock. To understand further, inspect `wait_event_type` and `wait_event` alongside the query and logs.

### Tracking long-running transactions

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
  AND datname = current_database()
ORDER BY xact_start;
~~~

Long-lived transactions can hold locks, interfere with vacuum, and increase row versions that must be retained. However, transaction duration **alone** is not enough to conclude a bug; ETL jobs or migrations may be designed to run for a long time. Correlate with application context and impact.

## 11. How Long Does a Session Last? When Does a Connection End?

A session typically ends when:

- The client explicitly closes the connection, such as `\q` in `psql` or the application calling `Connection.close()`.
- The application or operating system drops the connection.
- PostgreSQL shuts down or the backend is terminated.
- An applicable timeout fires.

When a session ends, session resources such as temporary tables and session-level prepared statements are cleaned up by PostgreSQL. Changes already **committed** to tables normally persist; uncommitted transactions are never treated as committed merely because the connection dropped.

### Does closing a connection in Java always close the PostgreSQL connection?

Not necessarily in the physical sense. With a connection pool like HikariCP, calling `Connection.close()` in the application usually **returns the connection to the pool** for reuse instead of closing the socket and backend immediately. The PostgreSQL session can stay alive after the HTTP request finishes.

This difference explains why a dashboard may show dozens of `idle` connections even when the application is not currently processing many queries.

### Timeouts to be aware of

~~~sql
SHOW statement_timeout;
SHOW lock_timeout;
SHOW idle_in_transaction_session_timeout;
SHOW idle_session_timeout;
~~~

| Parameter | Purpose |
| --- | --- |
| `statement_timeout` | Bounds execution time of eligible statements |
| `lock_timeout` | Bounds time spent waiting to acquire a lock where applicable |
| `idle_in_transaction_session_timeout` | Can terminate an idle session that keeps a transaction open beyond the configured time |
| `idle_session_timeout` | Can terminate an idle session outside a transaction beyond the configured time |

These parameters can be set per database, role, session, or server configuration depending on the case. Do not set overly aggressive timeouts in production blindly: legitimate work can be canceled, and poolers may misbehave if the server closes connections that the client assumes are still usable.

## 12. Connection Pools and Backend Process Count

Opening a PostgreSQL connection has overhead: socket setup, handshake, authentication, state initialization, and a corresponding backend process. If every web request opens a new connection and closes it immediately, the application can place significant load on the server.

A **connection pool** keeps a set of ready connections for reuse across requests:

~~~text
100 concurrent HTTP requests
             |
             v
         Java service
             |
             v
       Connection pool
       max 20 connections
             |
             v
       PostgreSQL server
       about 20 backends for that pool
~~~

This pattern is illustrative: the actual backend count also depends on connections from other tools, multiple application instances, and pool state.

### Client-side pools

In Java, HikariCP typically holds `java.sql.Connection` objects and manages their lifecycle:

- A request borrows a connection.
- Executes the required SQL/transaction.
- Commits or rolls back per business logic.
- Returns the connection to the pool.

When returning a connection, the pool must ensure transaction state and session attributes are handled properly. If one request alters `search_path`, role, or session state and returns the connection without resetting it, the next request can experience unexpected behavior.

### PgBouncer and server-side pooling

PgBouncer is a proxy/pooler sitting between clients and PostgreSQL. It offers different pooling modes:

| Mode | Relationship between client and PostgreSQL backend |
| --- | --- |
| **Session pooling** | One server connection is assigned to the client for the entire client session |
| **Transaction pooling** | Server connections can be returned to the pool after each transaction |
| **Statement pooling** | Shared per statement, with stricter limitations |

**Important consequence:** with **transaction pooling**, features that require preserving **the exact same PostgreSQL session across multiple transactions** may not work as they do over a direct connection. For example, consider session-level `SET`, temporary tables, session-level prepared statements, or operations relying on a stable backend PID.

Some PgBouncer versions/configurations include mechanisms supporting certain prepared statements under transaction pooling, but you should never assume all session state is preserved.

### max_connections is not a throughput metric

~~~sql
SHOW max_connections;

SELECT COUNT(*) AS client_backends
FROM pg_stat_activity
WHERE backend_type = 'client backend';
~~~

`max_connections` sets the server connection limit in PostgreSQL, but **raising this limit does not automatically make queries faster**. More concurrent backends consume more RAM and increase CPU, I/O, and lock contention. You also need to account for connection slots reserved for administration and system roles depending on version/configuration.

If a service runs 10 instances and each instance configures a pool of up to 30 connections, that service alone can request **300 connections**. When sizing, sum across all pools, administrative tools, background jobs, and other services.

## 13. JDBC Connections from a Java Application

A Java application typically uses the PostgreSQL JDBC driver to create connections:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public class PgSessionExample {
    public static void main(String[] args) throws SQLException {
        String url =
            "jdbc:postgresql://127.0.0.1:5432/lab_db"
            + "?ApplicationName=java-lab";

        // Set environment variables before running; do not hard-code secrets.
        String user = System.getenv("PG_LAB_USER");
        String password = System.getenv("PG_LAB_PASSWORD");

        try (Connection connection =
                 DriverManager.getConnection(url, user, password);
             PreparedStatement statement = connection.prepareStatement(
                 "SELECT pg_backend_pid() AS pid, "
                 + "current_database() AS dbname")) {

            try (ResultSet rs = statement.executeQuery()) {
                if (rs.next()) {
                    System.out.println(
                        "PID = " + rs.getInt("pid")
                        + ", DB = " + rs.getString("dbname")
                    );
                }
            }
        }
    }
}
~~~

This example requires the PostgreSQL JDBC driver on the classpath, a running server, and environment variables containing valid user/password credentials. The connection inside `try-with-resources` is closed when exiting the block; when using a pool, logical vs. physical closing depends on the pool implementation.

Safe practices:

- Use `PreparedStatement` with bound parameters instead of concatenating user input into SQL.
- Use TLS according to environment policy when communicating over untrusted networks; configure connections to verify certificates properly.
- Never put passwords in logs, source code, or public error messages.
- Manage transactions with explicit commit/rollback when changing JDBC's `autoCommit` setting.

### Autocommit in JDBC and PostgreSQL sessions

A JDBC `Connection` typically defaults to `autoCommit = true`; calling `setAutoCommit(false)` lets the driver manage explicit transactions suitable for grouping multiple statements until commit/rollback.

~~~java
connection.setAutoCommit(false);
try {
    // Execute SQL statements belonging to one transaction.
    connection.commit();
} catch (SQLException error) {
    connection.rollback();
    throw error;
}
~~~

This illustrates a **transaction management pattern**, not a complete standalone program. Production code must also handle exceptions during rollback and restore connection state before returning to a pool.

## 14. Distinguishing Connection and Query Error Categories

### 14.1. Connection refused or server unreachable

Possible causes:

- PostgreSQL is not running or is listening on a different port.
- `listen_addresses` does not accept the address the client is connecting to.
- Firewall/network rules or Docker port mappings are incorrect.
- The client uses `localhost` inside a container, mistakenly pointing to the container itself.

Check:

~~~bash
pg_isready -h 127.0.0.1 -p 5432
~~~

`pg_isready` tells you whether the server accepts connections at the given address/port; **it does not prove that the application's user/password or table permissions are valid**.

### 14.2. FATAL: password authentication failed

The client reached the server, but credentials or the authentication method failed. Check the role, secret, `pg_hba.conf` configuration, and driver/authentication mechanism compatibility. Do not fix this by opening `trust` network-wide.

### 14.3. no pg_hba.conf entry

No HBA rule matched the combination of user/database/address/connection type (or SSL requirement), so the server rejected it. Adjust the exact rule, rule ordering, and encryption requirements per operational policy. `pg_hba.conf` controls **authentication and connection access**, not `SELECT` privileges on tables.

### 14.4. FATAL: database does not exist

The host/port is valid, but the target database name does not exist. Verify `-d`, that the database was created, and that the connection points to the intended instance.

### 14.5. permission denied for table

The session authenticated and connected successfully, but the role lacks privileges on the table/schema. This is an **SQL authorization error**, not a socket or password issue.

### 14.6. too many clients already

The server is at or near the available connection limit for the role. Inspect total connection pool configurations, idle sessions, active backends, and reserved slots rather than immediately raising `max_connections`.

### 14.7. relation does not exist even though the table was created earlier

Possible reasons:

- The client connected to the wrong database.
- The table resides in a schema outside `search_path`.
- It is a temporary table that only exists in the session that created it, while the client is using another session.
- The migration creating the table was not committed or failed.

Check:

~~~sql
SELECT current_database(), current_schema();
SHOW search_path;
~~~

Compare this output against the target table's schema and permissions.

## 15. Tools for Monitoring and Managing Sessions

### Viewing your own backend

~~~sql
SELECT pg_backend_pid();
~~~

### Viewing client connections and states

~~~sql
SELECT
    datname,
    application_name,
    state,
    COUNT(*) AS connection_count
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY datname, application_name, state
ORDER BY datname, application_name, state;
~~~

Seeing many `idle` sessions does not automatically indicate an error. Connection pools keep `idle` connections to avoid recreation overhead. Compare against pool sizing and actual workload.

### Canceling queries and terminating backends

PostgreSQL provides:

~~~sql
-- Syntax example only after identifying the target PID:
SELECT pg_cancel_backend(12345);

-- Stronger: terminate the backend and its corresponding session:
SELECT pg_terminate_backend(12345);
~~~

Both PIDs above are **placeholder numbers**. Do not run these before confirming which application owns the backend and what impact termination will have.

- `pg_cancel_backend(pid)` requests cancellation of the currently running query without necessarily closing the session.
- `pg_terminate_backend(pid)` terminates the backend, interrupting the session; any uncommitted transaction is rolled back when the backend exits.
- These functions require appropriate privileges and may be restricted for special backends or superuser roles.

Do not use them as a "query tuning technique". If sessions wait on locks or leave transactions open, investigate the application root cause and implement appropriate timeouts and handling.

## 16. Practice Exercises

All exercises use a lab PostgreSQL instance. Do not read or modify production databases.

**Exercise 1.** A Java program and a `psql` window both connect directly to the `shopdb` database. How many client backends exist under the traditional PostgreSQL model while both connections are active? Do they share all session state?

**Exercise 2.** Explain the differences between **cluster**, **database**, **session**, and **transaction**. Can one session contain multiple transactions?

**Exercise 3.** Write a `SELECT` statement that displays the current database, the user that initiated the session, and the backend PID. Distinguish what `pg_backend_pid()` and `current_database()` return.

**Exercise 4.** Session A starts a transaction and updates a row without committing. Session B runs a normal `SELECT` under `READ COMMITTED`. Does B see A's uncommitted value? What happens on a new read by B after A commits?

**Exercise 5.** Session A creates `TEMP TABLE temp_demo`. Session B runs `SELECT * FROM temp_demo;` and gets a relation-not-found error. Why?

**Exercise 6.** An application uses a connection pool of 15 connections and runs 8 concurrent instances. If every pool opens its maximum, how many connections might this application alone require from PostgreSQL? Why shouldn't you size `max_connections` from that number alone?

**Exercise 7.** Explain the difference between `active`, `idle`, and `idle in transaction` in `pg_stat_activity`. Which state is concerning if it persists for a long time?

**Exercise 8.** Two containers share the same Compose network: the PostgreSQL service is named `db` with internal port `5432`, mapped to `5433` on the host machine. Which host and port should the application container use?

**Exercise 9.** An application uses PgBouncer transaction pooling, yet requires a temporary table to persist across multiple client transactions. What must be considered before adopting that design?

**Exercise 10.** `pg_isready` reports the server is accepting connections, yet `psql` fails with `permission denied for table`. Why are these two results not contradictory?

### Suggested Answers

| Exercise | Key points |
| --- | --- |
| 1 | Normally two separate backends. They share server data and coordination, but not all session state |
| 2 | A cluster holds databases; a session is the connection lifecycle; a transaction is the commit/rollback unit. One session can contain multiple transactions |
| 3 | `SELECT current_database(), session_user, pg_backend_pid();`; PID identifies the backend process, while database is the connection target |
| 4 | Uncommitted data from A is hidden; after commit, a new consistent read by B under `READ COMMITTED` can see the change |
| 5 | Temporary tables are bound to session A, so session B does not have that same temporary table |
| 6 | `15 × 8 = 120` max connections from that app alone; you must also account for other services, RAM, CPU/I/O load, and reserved slots |
| 7 | `active` is running a query, `idle` is waiting for a new query, `idle in transaction` is an idle session with an open transaction. The last state persisting for long requires investigation |
| 8 | Use `db:5432` inside the Compose network, not `localhost:5433` from the application container |
| 9 | Transaction pooling can switch server backends between transactions; session-scoped temporary table state cannot be assumed to persist across transactions |
| 10 | `pg_isready` checks connectivity acceptance; `SELECT` privilege is a separate authorization check during SQL execution |

## 17. Key Takeaways for a PostgreSQL Session Architecture

| Question | Short answer |
| --- | --- |
| Who does the client send SQL to? | The PostgreSQL server over a connection and protocol |
| Who processes SQL for a direct connection? | The corresponding backend process |
| Can two backends read the same table? | Yes, subject to permissions, transaction isolation, and MVCC |
| Does a session end on COMMIT? | No. COMMIT ends the transaction; the session can continue |
| Where can you see the backend PID? | `pg_backend_pid()` or `pg_stat_activity.pid` |
| What state is private to a session? | Role context, `SET` parameters, temporary tables, prepared statements... |
| Is opening very many connections free? | No. Each backend carries resource overhead |
| Can a pooler change the client–backend relationship? | Yes, depending on session/transaction/statement pooling |
| What if a client disconnects mid-transaction? | Uncommitted changes are not treated as committed |

**Mental model to remember:** an application or `psql` **opens a connection → authenticates → gets a PostgreSQL session and backend → sends queries/transactions → the backend operates on shared resources → returns results → continues or closes the session**. Understanding the boundaries between **session**, **transaction**, and **backend process** helps you size connection pools properly, interpret `pg_stat_activity` states, troubleshoot connection errors, and avoid concurrency pitfalls in PostgreSQL.
