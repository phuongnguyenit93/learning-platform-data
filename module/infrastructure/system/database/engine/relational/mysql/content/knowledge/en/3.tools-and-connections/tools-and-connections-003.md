# Classic Protocol, X Protocol, and Version Compatibility Scope

MySQL allows applications to communicate with the server over two main client/server protocols: **MySQL Classic Protocol** and **MySQL X Protocol**. Both can send requests to the same MySQL Server and operate on the same databases, accounts, access privileges, and storage engines. The difference lies in how messages are represented on the wire, the API model exposed by the client, support for relational or document data, and version requirements.

When building MySQL-based systems, you need to understand which protocol is in use so you can choose the right connector, configure the right port, diagnose connection errors, and apply appropriate security controls. Choosing X Protocol does not automatically make SQL queries run faster; query performance still depends on table design, indexes, transactions, execution plans, server resources, and how the application uses connections.

This article focuses on MySQL Server 5.7.12 and later, especially the 8.0 and 8.4 series. Older versions or custom-configured distributions may differ.

## 1. Two Protocols in the MySQL Architecture

Applications do not send InnoDB's internal data structures directly over the network. Instead, an application uses a client library (connector or driver) to package requests into a protocol that MySQL Server understands. The server receives the messages, authenticates the session, checks privileges, processes SQL or CRUD operations, and returns results.

At a high level, the two connection paths can be visualized as follows:

~~~text
Application
   |
   +-------------------------------+
   |                               |
   v                               v
Classic Connector           X DevAPI Connector
   |                               |
   v                               v
MySQL Classic Protocol       MySQL X Protocol
   |                               |
   v                               v
Classic Port (usually 3306)  X Plugin (usually 33060)
   |                               |
   +---------------+---------------+
                   |
                   v
              MySQL Server
                   |
           Parsing / Execution
                   |
                   v
             Storage Engine
             (e.g., InnoDB)
                   |
                   v
            Tables and Data
~~~

The diagram shows that X Plugin is the server-side component that accepts X Protocol connections. On the application side, X DevAPI is the programming interface provided by connectors to expose X Protocol capabilities. Classic Protocol has a long-standing ecosystem of connectors and is typically used directly through familiar SQL drivers.

The two protocols do not correspond to two separate databases. A table updated by an application using Classic Protocol can be read by an application using X Protocol, provided both connect to the same server, the same schema, and use accounts with appropriate privileges.

## 2. MySQL Classic Protocol

Classic Protocol is MySQL's traditional client/server protocol. It is widely used by SQL applications, administration tools, and connector libraries across many generations of MySQL.

### 2.1. Key Characteristics

- The standard protocol for traditional SQL operations such as SELECT, INSERT, UPDATE, DELETE, DDL, and transactions.
- Supports sending SQL statements and receiving result sets, success status, or errors.
- Supports prepared statements. Thus, Classic Protocol does not only transmit SQL as plain text; prepared statements use execution messages with parameters encoded in a binary format.
- Supported by long-established clients and connectors such as the `mysql` command-line program and many versions of Connector/J, Connector/C, Connector/Python, Connector/NET, and drivers for other platforms.
- Connects over TCP/IP; depending on the operating system and configuration, local mechanisms such as Unix sockets or named pipes are also supported.

For standard TCP/IP connections, the default port for Classic Protocol is **3306**. This port can be changed via server configuration or startup options, so applications must use the actual port configured for the environment.

### 2.2. Basic Processing Flow

A Classic Protocol connection typically goes through the following steps:

1. The client opens a connection to the address and port of MySQL Server.
2. The server sends a handshake packet containing protocol version info and connection capabilities.
3. The client sends authentication credentials and negotiated connection options.
4. After successful authentication, the client sends commands such as COM_QUERY or prepared-statement commands.
5. The server executes the request and returns a result set, affected row count, status, or error.
6. The client reuses the session for subsequent statements or closes the connection.

For regular SQL statements, the client can send the statement via COM_QUERY. For prepared statements, the client prepares the statement first and then sends parameter values at execution time. This approach separates data from SQL structure and reduces SQL injection risk when the application uses parameterized APIs properly.

Example using the `mysql` command-line program to connect over TCP:

~~~bash
mysql --protocol=TCP \
  --host=127.0.0.1 \
  --port=3306 \
  --user=app_user \
  --password
~~~

Passing `--password` without a value prompts the program to ask for the password interactively. Avoid placing real passwords directly in shell history, scripts, or command lines visible to other processes.

### 2.3. Text Protocol and Binary Protocol

These two concepts are often confused:

- **Text protocol** generally refers to sending regular SQL statements and receiving values in the result set using the protocol's text representation.
- **Binary protocol** is used during prepared statement execution steps to transmit parameter values or results in an appropriate binary format.

Both belong to Classic Protocol. Therefore, you should not equate Classic Protocol with transmitting all data as text strings.

Prepared statements are not merely writing SQL with question marks. The driver must use the proper prepare/bind/execute API so values are transmitted as parameters. Concatenating user input directly into an SQL string can still cause SQL injection, even if the application connects over Classic Protocol.

## 3. MySQL X Protocol

X Protocol is a client/server protocol designed to support both relational data access and MySQL's document store model. It is provided via **X Plugin** on MySQL Server and is typically consumed from applications through **X DevAPI** in compatible connectors.

### 3.1. Key Characteristics

- Uses Protocol Buffers to represent messages exchanged between client and server.
- Supports sending SQL statements as well as CRUD operations following the X DevAPI model.
- Supports working with both relational tables and document collections.
- Provides a more object-oriented API for schemas, tables, collections, queries, and transactions.
- Can be used by connectors and tools that support X Protocol, such as MySQL Shell and X DevAPI-enabled connectors.

For TCP/IP connections, the default port for X Protocol is **33060**. This port belongs to the listener provided by X Plugin. If X Plugin is not installed, is disabled, or its listener cannot bind to the configured address, X Protocol clients cannot connect even if the Classic port continues working.

### 3.2. Distinguishing X Protocol, X Plugin, and X DevAPI

These three terms are related, but they do not mean the same thing:

| Component | Role |
|---|---|
| X Protocol | Rules and format for client/server messages transmitted over the network |
| X Plugin | Component inside MySQL Server that accepts and processes X Protocol connections |
| X DevAPI | Client-side API implemented by connectors so applications can work with schemas, tables, collections, SQL, and transactions |

For example, a Python application can invoke an X DevAPI method. The connector translates that call into X Protocol messages; X Plugin receives the messages and asks MySQL Server to execute the operation. The application does not construct Protocol Buffers packets manually when using a connector.

### 3.3. SQL and CRUD via X DevAPI

X Protocol is not exclusively for JSON or documents. Applications can use X DevAPI to interact with relational tables and run SQL, while also using collections when the problem fits document-oriented data.

The following example demonstrates connecting with MySQL Connector/Python supporting X DevAPI and finding documents in a collection:

~~~python
import mysqlx

session = mysqlx.get_session({
    "host": "127.0.0.1",
    "port": 33060,
    "user": "app_user",
    "password": "your-password",
})

try:
    schema = session.get_schema("shop")
    customers = schema.get_collection("customers")

    result = customers.find("status = :status") \
        .bind("status", "ACTIVE") \
        .execute()

    for customer in result.fetch_all():
        print(customer)
finally:
    session.close()
~~~

This is an example of the collection API, not a direct SQL statement. A collection stores JSON documents and provides find, add, modify, and remove operations via X DevAPI.

X DevAPI also allows running SQL on a session. Here is a standalone example that creates and closes its own session:

~~~python
sql_session = mysqlx.get_session({
    "host": "127.0.0.1",
    "port": 33060,
    "user": "app_user",
    "password": "your-password",
})

try:
    result = sql_session.sql(
        "SELECT order_id, status FROM orders WHERE customer_id = ?"
    ).bind(42).execute()

    for row in result.fetch_all():
        print(row)
finally:
    sql_session.close()
~~~

Specific method names depend on the connector version. You must install a connector with X DevAPI support and consult documentation for the exact version in use. A traditional SQL driver that only supports Classic Protocol does not automatically become an X Protocol client simply by changing the port number.

## 4. Comparing Classic Protocol and X Protocol

| Criterion | Classic Protocol | X Protocol |
|---|---|---|
| Primary purpose | Traditional client/server SQL | SQL and CRUD via X DevAPI, including document store |
| Message representation | Traditional MySQL protocol; includes text protocol and binary protocol for prepared statements | Protocol Buffers-based messages |
| Server-side component | MySQL Server handles Classic connections | X Plugin inside MySQL Server accepts connections |
| Default TCP port | 3306 | 33060 |
| Typical APIs | JDBC, DB-API, ADO.NET, and connector SQL APIs | X DevAPI via supporting connectors |
| Data model | Primarily SQL operations on relational tables | Relational tables and document collections |
| Client compatibility | Very broad, including legacy applications and tools | Requires a connector or tool that supports X Protocol |
| Common use cases | Existing applications, SQL queries, administration tools | Applications wanting to use X DevAPI or document store |

You cannot conclude that one protocol is always faster than the other. When running the same SQL query on the same server, most query optimization and data access work still happens inside MySQL Server and the storage engine. Differences in network overhead, message framing, APIs, and how the application constructs queries can affect a specific workload; measure on the actual system before making performance decisions.

## 5. Usage Scope by MySQL Version

Classic Protocol is the traditional protocol and has been present across long-standing MySQL releases. X Protocol has specific version requirements because it requires X Plugin and a compatible connector.

| MySQL Server Version | Classic Protocol | X Protocol |
|---|---|---|
| MySQL 5.6 and older | Available | No built-in X Plugin/X Protocol as in newer 5.7 releases |
| MySQL 5.7.12 and later | Available | X Plugin is provided; for the 5.7 series, check and install/enable the plugin per version documentation |
| MySQL 8.0 | Available | X Plugin is installed and enabled by default in standard MySQL Server distributions |
| MySQL 8.4 LTS | Available | X Plugin included; check plugin status and listener configuration on the deployed server |

X Protocol was introduced in MySQL 5.7.12. That does not mean every 5.7 server is ready to accept X connections: verify the exact release, ensure the plugin is installed and active, ensure the port is open, and ensure the client supports X Protocol.

In MySQL 8.0 and 8.4, X Plugin is typically installed and enabled by default. However, administrators may alter the configuration, disable the plugin, or change the port. Therefore, do not infer listener status solely from the version string.

### 5.1. Server Version and Connector Version Must Be Compatible

Server support for X Protocol is not enough on its own. The application's connector must also understand the protocol and capabilities offered by the server. When selecting a connector, verify:

1. Does the connector version support X DevAPI/X Protocol, or only Classic Protocol?
2. Is the connector version compatible with the application's runtime and operating system?
3. Does the connector support the authentication method configured on the server?
4. Does the connector support TLS and required security options?
5. Are the X DevAPI features the application needs supported in that connector version?

A connector may support Classic Protocol without supporting X Protocol. Conversely, a connector with X DevAPI may offer both X DevAPI and traditional SQL APIs. Always check the connector documentation rather than relying only on the product name.

### 5.2. Client Tools May Support One or Both Protocols

The **mysql** command-line program is a traditional client using Classic Protocol. **MySQL Shell** supports both Classic Protocol and X Protocol; the operator can choose the protocol when connecting. For example:

~~~bash
# Classic Protocol connection
mysqlsh --mysql \
  --host=127.0.0.1 \
  --port=3306 \
  --user=app_user

# X Protocol connection
mysqlsh --mysqlx \
  --host=127.0.0.1 \
  --port=33060 \
  --user=app_user
~~~

These two commands illustrate explicit protocol selection. When using MySQL Shell, verify the connection mode and actual port in use; do not assume every tool with an SQL interface defaults to the same protocol.

## 6. Configuring Both Listeners on the Server

Classic Protocol and X Protocol have separate listeners. Common parameters include:

| Parameter | Meaning |
|---|---|
| port | TCP port for Classic Protocol; default is usually 3306 |
| bind_address | Network address that the Classic listener binds to |
| mysqlx_port | TCP port for X Protocol; default is usually 33060 |
| mysqlx_bind_address | Network address that X Plugin uses to bind its listener |

An example configuration in a MySQL option file:

~~~ini
[mysqld]
port=3306
bind_address=127.0.0.1

mysqlx_port=33060
mysqlx_bind_address=127.0.0.1
~~~

This example restricts both listeners to loopback, which is appropriate when clients run on the same host. If applications run on separate machines, administrators must select bind addresses aligned with the network architecture, configure firewalls, and restrict source access. Do not expose database ports to the public Internet without proper security controls.

After changing startup options, restart the service if the parameter requires a restart. In container or cloud environments, also check port mappings, security groups, and network policies; configuring listeners inside MySQL does not automatically open network paths at the infrastructure layer.

### 6.1. Checking Version and Plugin Status

You can run the following statements in an administrative SQL session:

~~~sql
SELECT VERSION();

SHOW PLUGINS;

SHOW VARIABLES LIKE 'port';
SHOW VARIABLES LIKE 'bind_address';
SHOW VARIABLES LIKE 'mysqlx_port';
SHOW VARIABLES LIKE 'mysqlx_bind_address';
~~~

In the `SHOW PLUGINS` output, look for the plugin named `mysqlx` and inspect its status. If the `mysqlx` variables do not exist or the plugin is not active, check the server distribution, installation method, and server startup logs. Variable names and configurability may vary by version or packaging.

OS-level connection checks should confirm that the listener is actually listening on the expected address and port. Seeing a setting in a config file does not prove the server loaded that configuration.

### 6.2. When X Protocol Is Not Used

A system that only uses Classic Protocol may not need the X Protocol listener enabled. Administrators should verify application requirements, active plugins, and deployment policies before changing X Plugin's state. If you decide to disable X Plugin, use the configuration option documented for your exact version, then restart and verify that the listener has stopped.

Do not remove or disable the plugin solely because the primary application connects on port 3306. Operational tools, administrative components, or other applications in the same environment may rely on X Protocol.

## 7. Accounts, Privileges, and Connection Security

Both protocols connect to MySQL Server and are governed by the server's authentication, account definitions, SQL privileges, and security policies. Using X Protocol does not bypass `GRANT` checks, and using Classic Protocol does not automatically make a connection more secure.

When deploying:

- Create role-specific application accounts and grant least-privilege permissions on relevant schemas or objects.
- Never use administrative accounts like `root` for application connections.
- Use TLS when traffic traverses untrusted networks; verify certificates and configure clients to validate server identity.
- Restrict allowed source IP addresses at the firewall or network layer.
- Protect passwords in a secret manager or the deployment environment's secrets mechanism.
- Select a connector version that supports the authentication plugin enabled on the server, especially when using default authentication mechanisms in newer MySQL releases.

If a legacy client does not support the current authentication mechanism, prioritize upgrading the connector or configuring the client properly. Do not arbitrarily downgrade server authentication security just to keep an outdated driver working.

## 8. Choosing a Protocol for Each Scenario

### 8.1. Prefer Classic Protocol When

- Existing applications already use stable JDBC, ODBC, ADO.NET, or SQL drivers.
- The system needs compatibility across multiple MySQL versions or older tooling.
- The workload is primarily relational SQL with no need for X DevAPI.
- Operations teams already have connection workflows, monitoring, firewalls, and account management built around the Classic listener.

Classic Protocol is a sensible choice for the vast majority of existing MySQL applications. There is no need to switch protocols if your current driver works reliably and meets security, performance, and maintainability requirements.

### 8.2. Consider X Protocol When

- The application wants to use X DevAPI to manipulate tables and collections.
- The problem involves document data and you want to use MySQL Document Store collections.
- The language connector supports X DevAPI and the development team wants to use this API.
- The system benefits from an X DevAPI CRUD programming model rather than manually building full SQL strings for every operation.

X Protocol fits when the benefits of X DevAPI and the document store solve a concrete requirement. It does not force every MySQL application to switch to a document model or replace relational SQL.

### 8.3. Running Both Protocols Together

A single MySQL Server can simultaneously serve Classic clients and X clients if both listeners are properly configured and enabled. For example, a system can keep a legacy Java application using JDBC over Classic Protocol while allowing a new service to use X DevAPI over X Protocol.

When operating both side by side, explicitly manage:

- Ports and bind addresses of each listener.
- Firewall rules, private networks, and port mappings.
- Accounts, privileges, TLS, and authentication methods for each client.
- Connector versions and upgrade procedures.
- Logs, metrics, and how to identify which protocol a connection uses during incident investigation.

Both protocols access the exact same data, so write operations must still use proper transactions and concurrency control. Using two protocols does not create two copies of the data or two independent transaction mechanisms.

## 9. Common Errors and Diagnostics

### 9.1. Classic Connects, but X Protocol Cannot Connect

Check in order:

1. Does the MySQL Server version support X Plugin?
2. Is X Plugin installed and in an active state?
3. Does `mysqlx_port` match the port the client is using?
4. Is the listener bound to an address reachable by the client?
5. Do firewalls, container port mappings, or security groups allow connections to the X port?
6. Does the connector actually support X Protocol/X DevAPI?

A successful connection to port 3306 only confirms that the Classic path works. It does not prove the X listener on port 33060 is also operational.

### 9.2. Connection Succeeds, but Authentication Fails

Check the username, the host part of the MySQL account, the password, the authentication methods supported by the connector, and the TLS configuration. An account may be allowed from one host but denied from another. Also distinguish authentication errors from authorization/privilege errors: succeeding at authentication does not mean the account has privileges to read or write the target table.

### 9.3. SQL Driver Cannot Connect to the X Port

Check the connector documentation. If the connector only implements Classic Protocol, changing the port from 3306 to 33060 will not enable it to speak X Protocol. You must use an X DevAPI-capable connector or continue connecting over Classic Protocol.

### 9.4. Application Uses X DevAPI but Cannot Find Schema or Collection

Check whether the schema exists, whether the collection has been created, exact object names, and account privileges. Also confirm whether the operation targets a table or a collection: the two models have different APIs and data rules even within the same MySQL Server.

### 9.5. Unsure Which Protocol a Tool Is Using

Check the tool's connection options, actual host/port, and the mode used by the connector. With MySQL Shell, explicitly specifying Classic or X Protocol in the connection command prevents confusion. When investigating at the server level, cross-reference listener settings and session info against deployment configuration.

## 10. Misconceptions to Avoid

**“X Protocol is a newer version that completely replaces Classic Protocol.”** Incorrect. Both protocols coexist; Classic Protocol remains the primary choice for a large share of existing SQL applications.

**“X Plugin, X Protocol, and X DevAPI are the same thing.”** Incorrect. The plugin is the server-side component, the protocol is the wire exchange format, and X DevAPI is the client-side API.

**“Classic Protocol only transmits SQL as plain text.”** Incorrect. Classic Protocol also supports prepared statements with binary encoding for parameters and data.

**“X Protocol is only for JSON.”** Incorrect. X DevAPI supports operations on relational tables, SQL execution, and document collections.

**“Switching to port 33060 means you are using X Protocol.”** Incorrect. The client must implement X Protocol; merely changing the port on a Classic driver will cause connection or protocol errors.

**“X Protocol is always faster than Classic Protocol.”** There is no such guarantee. You must benchmark with your actual workload, connector, network, and configuration.

**“MySQL 8.x always opens X Protocol on port 33060.”** That is a common default port, not a guarantee for every server. The plugin, port, bind address, and firewall may have been changed.

## 11. Selection and Deployment Workflow

When starting a project or preparing a MySQL upgrade, follow this sequence:

1. Record the actual MySQL Server version using `SELECT VERSION()`.
2. List the connectors, connector versions, and APIs used by the application.
3. Determine whether the workload only needs relational SQL or clearly benefits from X DevAPI and collections.
4. If choosing Classic, confirm the Classic listener, port, TLS, and connector.
5. If choosing X, confirm server version support, X Plugin status, `mysqlx_port`, `mysqlx_bind_address`, and an X DevAPI connector.
6. Verify accounts, least-privilege grants, authentication, and firewalls for the corresponding listener.
7. Test connectivity from the actual application runtime environment, then verify read queries, writes, and transactions.
8. Document the port, protocol, connector, version, and security configuration in deployment docs so operations teams can diagnose issues later.

Do not make decisions based solely on protocol names or default ports. Verify server version, plugin status, connector capabilities, and application data requirements together in a single assessment.

## Conclusion

Classic Protocol is MySQL's traditional protocol, broadly compatible and well suited for most existing SQL applications. X Protocol is provided via X Plugin, uses Protocol Buffers messages, and lets applications use X DevAPI for SQL, relational tables, and document collections. Default TCP ports are typically 3306 for Classic and 33060 for X.

X Protocol has been available since MySQL 5.7.12; 5.7 deployments require verifying plugin installation, while 8.0 and 8.4 typically install and enable the plugin by default. Whichever protocol you choose, the application must still use a compatible connector, an appropriately privileged account, encrypted/protected connections, and properly designed transactions. The best choice is the protocol that aligns with your MySQL version, client ecosystem, and actual system data requirements.
