# Microsoft Entra Authentication for Databases When Supported

A Spring Boot application running on Azure can use **Managed Identity** to acquire an access token from Microsoft Entra ID and connect to databases without storing static passwords. However, the integration mechanism differs across databases: PostgreSQL and MySQL Flexible Server use Spring Cloud Azure JDBC plugins; Azure SQL uses the Microsoft JDBC Driver with Entra authentication modes; Cosmos DB for NoSQL uses Azure Identity and native data-plane RBAC. Each service also requires a separate **database principal or role assignment** to grant data permissions.

The key is separating three steps: **the workload acquires an identity**, **the database authenticates the token**, and **database authorization checks data permissions**. Holding a valid token does not mean the application is authorized to read or write tables/containers. Nor is there a single `spring.cloud.azure.*` property that replaces every driver and permission system.

This lesson belongs to the **Azure Data Services** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module covers practical integration of Spring Boot with managed services across AWS, Azure, and Google Cloud via their respective Spring Cloud libraries, including identity/permission configuration, storage, messaging, data, secret protection, integration testing, and evaluating differences between cloud providers. This lesson focuses strictly on Azure database services that have clear documented support for Microsoft Entra authentication in Java/Spring.

## 1. Learning Outcomes

After this lesson, you will be able to:

- Explain the Microsoft Entra access token flow from workload to database.
- Distinguish system-assigned Managed Identity, user-assigned Managed Identity, service principals, and local development credentials.
- Identify which services/drivers support Entra authentication and choose the right integration.
- Configure passwordless JDBC for Azure Database for PostgreSQL and MySQL Flexible Server using Spring Cloud Azure.
- Configure Azure SQL using the Microsoft JDBC Driver with `ActiveDirectoryManagedIdentity` or `ActiveDirectoryDefault`.
- Connect to Azure Cosmos DB for NoSQL using the Java SDK and `DefaultAzureCredential`, then grant native data-plane roles.
- Distinguish authentication from database authorization and Azure control-plane RBAC.
- Manage tokens, connection pools, TLS, tenants, role scopes, and rotation safely.
- Test least privilege, token acquisition, token expiry, reconnection, and 401/403 scenarios.

## 2. How Does Microsoft Entra Authentication Work?

Microsoft Entra ID is the identity provider. The application obtains a token representing a user, service principal, or managed identity. The database only accepts tokens issued for the right resource/audience, unexpired, and belonging to the configured tenant. After authenticating the identity, the database maps that principal to a user/role or role assignment to determine which data operations are permitted.

~~~mermaid
sequenceDiagram
    participant App as Spring Boot workload
    participant Entra as Microsoft Entra ID
    participant DB as Azure database
    participant Data as Database objects
    App->>Entra: Request token using Managed Identity / credential
    Entra-->>App: Access token for target database audience
    App->>DB: JDBC / SDK request with token
    DB->>DB: Validate signature, tenant, audience and expiry
    DB->>DB: Map principal to database user / data-plane role
    DB->>Data: Check database authorization
    Data-->>DB: Result
    DB-->>App: Query result or authorization error
~~~

This flow has three independent checkpoints:

1. **Credential acquisition:** can the application acquire a token from Entra?
2. **Authentication:** does the database accept the token for that server/database?
3. **Authorization:** does the principal hold the required `SELECT`, `INSERT`, `UPDATE`, `DELETE`, or container query permissions?

A failure at step 1 usually points to Managed Identity endpoints, tenant configuration, credential chain, or token audience. A failure at step 2 usually points to Entra admin configuration, principal mapping, token audience/expiry, or server configuration. A failure at step 3 usually points to missing database grants, role assignments, or scopes.

## 3. Support Matrix by Service and Java Integration

Do not assume every service with "Azure Database" in its name authenticates identically. Start by choosing the right API/engine and driver:

| Service | Java/Spring Integration | Entra Authentication Mechanism | Data Authorization |
| --- | --- | --- | --- |
| **Azure Database for PostgreSQL Flexible Server** | PostgreSQL JDBC + Spring Cloud Azure PostgreSQL starter | `AzurePostgresqlAuthenticationPlugin` acquires token and passes it to the JDBC driver | Entra principal created as a PostgreSQL role; uses `GRANT` |
| **Azure Database for MySQL Flexible Server** | MySQL Connector/J + Spring Cloud Azure MySQL starter | `AzureMysqlAuthenticationPlugin` supplies token as MySQL authentication credential | Entra user/group/identity created as a MySQL user; uses `GRANT` |
| **Azure SQL Database** | Microsoft JDBC Driver for SQL Server; Spring Data JDBC/JdbcTemplate/JPA | `ActiveDirectoryManagedIdentity` or `ActiveDirectoryDefault` | Contained database user mapped to Entra principal; database roles/`GRANT` |
| **Azure SQL Managed Instance** | Microsoft JDBC Driver for SQL Server | Driver Entra authentication modes, depending on instance configuration | SQL logins/database users and roles per SQL Managed Instance model |
| **Azure Cosmos DB for NoSQL** | Azure Cosmos DB Java SDK; Spring Data Cosmos at repository layer | `DefaultAzureCredential`/`TokenCredential` via Cosmos client | Native Cosmos DB data-plane RBAC |

The Azure SQL JDBC driver also has Entra modes for Azure Synapse Analytics; verify specific capabilities per workspace type, driver version, and SQL features used. This lesson does not assume Cosmos DB APIs for MongoDB/Cassandra/Gremlin/Table share the same native NoSQL data-plane roles. For other APIs or services without documented Java/Spring support, verify separately before implementing.

## 4. Choosing Credentials by Environment

Azure Identity and Spring Cloud Azure support several credential types:

| Credential | When to Use | Notes |
| --- | --- | --- |
| **System-assigned Managed Identity** | Workloads running on an Azure resource with identity enabled | Lifecycle tied to the resource; deleting the resource deletes the identity |
| **User-assigned Managed Identity** | Multiple workloads sharing one identity or identity needing independent lifecycle | Must specify the right client ID; manage role assignments separately |
| **Service principal + certificate** | Workloads without Managed Identity support or running outside Azure | Prefer certificates/federated credentials over static secrets when appropriate |
| **Service principal + client secret** | Legacy integrations or environments lacking alternatives | Secret must live in a secret manager with rotation |
| **`DefaultAzureCredential`** | Local development and Java apps needing a credential chain | Can pick up Azure CLI/IDE locally and Managed Identity on Azure; explicitly control credential sources in production |
| **Interactive/user credential** | Developer tools or interactive user flows | Never use interactive flows in headless backends |

### 4.1. Local Development

Developers can sign in via the Azure CLI:

~~~bash
az login
az account set --subscription "<subscription-id>"
~~~

With Java SDKs using `DefaultAzureCredential`, the credential chain can discover credentials from supported developer environments such as Azure CLI or IDEs. The database must still have a principal representing the user/developer with appropriate permissions. Never use personal admin privileges to run services routinely.

### 4.2. Production

When running on Azure App Service, Azure Spring Apps, VMs, AKS, or another Azure resource supporting Managed Identity, prefer assigning an identity to the workload. Use a user-assigned identity when identity lifecycle must be independent of the resource or shared intentionally. Grant database permissions to that identity at the smallest scope.

On AKS, Workload Identity Federation can map a Kubernetes service account to an Entra identity instead of issuing static secrets. Issuer, subject, and audience configuration must match the federated credential; never confuse a Kubernetes service account token with a database access token.

### 4.3. Token Audience Must Match the Target Service

Access tokens carry specific audiences/resources. Never fetch a token for Azure Resource Manager and try to use it for SQL, PostgreSQL, MySQL, or Cosmos DB. Common scopes include:

| Service | Common Token Audience/Scope |
| --- | --- |
| Azure SQL | `https://database.windows.net/.default` |
| PostgreSQL/MySQL Flexible Server | Resource type `oss-rdbms`; typical scope `https://ossrdbms-aad.database.windows.net/.default` |
| Cosmos DB for NoSQL | `https://cosmos.azure.com/.default` |

With Spring Cloud Azure passwordless plugins, the library acquires the proper token for that integration; do not override the scope with a different resource. When managing tokens directly via a Java SDK, use the exact scope specified in the service's documentation.

## 5. Azure Database for PostgreSQL Flexible Server

### 5.1. Enabling Entra Authentication and Creating the Database Principal

PostgreSQL Flexible Server allows enabling Microsoft Entra authentication during provisioning or afterward. An Entra administrator must be configured. Because the administrator has elevated privileges, use it only to create/manage principals; runtime applications need a separate principal with least privilege.

A principal can be an Entra user, group, service principal, or managed identity. Once the Entra admin is set, create the corresponding PostgreSQL role using the `pgaadauth` extension. Example per Microsoft guidance:

~~~sql
SELECT *
FROM pgaadauth_create_principal('orders_api', false, false);
~~~

The principal name must match the identity configured on the server. Next, grant database/schema/table privileges:

~~~sql
GRANT CONNECT ON DATABASE orders TO orders_api;
GRANT USAGE ON SCHEMA public TO orders_api;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON ALL TABLES IN SCHEMA public TO orders_api;
GRANT USAGE, SELECT
    ON ALL SEQUENCES IN SCHEMA public TO orders_api;
~~~

The example uses an illustrative role name; verify the exact role name returned by the principal creation command. Manage default privileges for future tables/sequences via migrations or a schema-admin role. Never grant `superuser`/`CREATEDB` to a runtime service.

### 5.2. Spring Cloud Azure Starter

Add the PostgreSQL starter and the Spring Cloud Azure BOM compatible with Spring Boot:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>${spring-cloud-azure.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-jdbc-postgresql</artifactId>
    </dependency>
</dependencies>
~~~

Spring Cloud Azure PostgreSQL support integrates `AzurePostgresqlAuthenticationPlugin` and exposes `spring.datasource.azure.passwordless-enabled`. Example:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://${PG_SERVER}.postgres.database.azure.com:5432/${PG_DATABASE}?sslmode=require
    username: ${PG_ENTRA_DATABASE_USER}
    azure:
      passwordless-enabled: true
  cloud:
    azure:
      credential:
        managed-identity-enabled: true
        # Declare only for user-assigned identity:
        client-id: ${AZURE_CLIENT_ID}
~~~

Set `PG_ENTRA_DATABASE_USER` to the database principal created for the Entra identity. Locally, supported credential sources such as Azure CLI/IDE can be used; when deployed on Azure, Managed Identity supplies the token. Global credential properties must match your Spring Cloud Azure version.

Passwordless PostgreSQL support has been available since Spring Cloud Azure 4.5.0. Choose a BOM compatible with Spring Boot and check the version mapping before upgrading; do not upgrade the starter in isolation while skipping related Azure Identity dependencies.

### 5.3. Verification Flow

1. Verify FQDN, firewall/private network, port 5432, and TLS.
2. Verify an Entra admin is configured.
3. Verify the database principal representing the workload identity exists.
4. Check that the principal holds `CONNECT`, `USAGE`, and required table/sequence privileges.
5. Verify Spring Cloud Azure acquires tokens for the `oss-rdbms` resource.
6. Test an authorized `SELECT`/`INSERT` and an unauthorized operation.

TLS must remain enabled. `sslmode=require` encrypts connections; production should evaluate `verify-full` and CA/hostname verification per driver configuration.

## 6. Azure Database for MySQL Flexible Server

### 6.1. Enabling Authentication and Server-Side Identity Setup

MySQL Flexible Server supports MySQL authentication, Microsoft Entra authentication, or both depending on server settings. When enabling Entra authentication, configure an Entra administrator and create a database user mapped to the Entra identity:

~~~sql
CREATE AADUSER 'orders-api-mi';
GRANT SELECT, INSERT, UPDATE, DELETE
    ON orders.* TO 'orders-api-mi'@'%';
FLUSH PRIVILEGES;
~~~

Entra user/group/identity naming follows MySQL rules; use exact spelling and verify mapping per service docs. Successful authentication **does not automatically grant read/write privileges**. The database user must still be `GRANT`ed required permissions.

**Special note on MySQL server user-assigned identity:** MySQL Flexible Server uses a user-assigned managed identity attached to the server itself to read user/group/service principal metadata from Microsoft Graph. This server-side identity needs the Graph permissions required by Microsoft (`User.Read.All`, `GroupMember.Read.All`, `Application.Read.All`, or `Directory Readers` per docs). This identity is for server-side principal lookups; it is **distinct from the application's Managed Identity** used to acquire database connection tokens. Never grant broad Graph permissions to a workload just because the database server needs lookup permissions.

### 6.2. Spring Cloud Azure MySQL Starter

Dependency:

~~~xml
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-jdbc-mysql</artifactId>
</dependency>
~~~

Include the compatible `spring-cloud-azure-dependencies` BOM. The starter uses `AzureMysqlAuthenticationPlugin` to convert Entra tokens into MySQL credentials. Example:

~~~yaml
spring:
  datasource:
    url: jdbc:mysql://${MYSQL_SERVER}.mysql.database.azure.com:3306/${MYSQL_DATABASE}?sslMode=VERIFY_IDENTITY&serverTimezone=UTC
    username: ${MYSQL_ENTRA_DATABASE_USER}
    azure:
      passwordless-enabled: true
      credential:
        managed-identity-enabled: true
        # Declare only if workload uses user-assigned identity:
        client-id: ${AZURE_CLIENT_ID}
~~~

`spring.datasource.azure.passwordless-enabled` enables token-based authentication. For simple setups, credentials can come from `DefaultAzureCredential`; production can explicitly specify Managed Identity. Ensure Connector/J supports the cleartext authentication plugin per MySQL instructions while keeping TLS active. Never downgrade `sslMode` to `DISABLED` to fix token errors.

### 6.3. Token Audience and Principal Naming

MySQL Flexible Server uses the `oss-rdbms` resource type to acquire access tokens. Tokens must target the right service and tenant. Entra principal names can be case-sensitive; the username in the JDBC URL must match the created database user.

Microsoft has announced stricter token audience validation starting January 2027; applications must use the supported `ossrdbms` audience. When acquiring tokens manually, use the resource type/scope specified in the latest MySQL Flexible Server guidance rather than reusing Azure SQL or PostgreSQL tokens by guessing audiences.

MySQL server identity and app identity have distinct roles:

| Identity | Used For | Configuration / Permissions |
| --- | --- | --- |
| Server user-assigned identity | MySQL server looking up Entra users/groups/service principals | Attached to Flexible Server with documented Graph permissions |
| Workload system/user-assigned identity | Spring Boot acquiring tokens to log in to the database | Attached to App Service/VM/AKS/host; create MySQL `AADUSER` and `GRANT` data rights |
| Entra administrator | Managing Entra database users | High administrative privileges; do not use as runtime identity |

## 7. Azure SQL Database and SQL Managed Instance

Azure SQL uses the Microsoft JDBC Driver for SQL Server. Do not use PostgreSQL/MySQL authentication plugins. The driver supports Entra modes such as:

- `ActiveDirectoryManagedIdentity`: workloads running on Azure resources with Managed Identity.
- `ActiveDirectoryDefault`: uses Azure Identity `DefaultAzureCredential`; fits supported credential chains across local development and Azure hosting.
- `ActiveDirectoryInteractive`: interactive flow for developers/users; unsuitable for headless backends.
- `ActiveDirectoryServicePrincipal` or certificate modes: workloads using service principals.

### 7.1. Adding the Driver and Configuring Managed Identity

Maven dependency example:

~~~xml
<dependency>
    <groupId>com.microsoft.sqlserver</groupId>
    <artifactId>mssql-jdbc</artifactId>
</dependency>
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
</dependency>
~~~

Driver 12.2 and later support the mode names `ActiveDirectoryManagedIdentity` and `ActiveDirectoryDefault`. Older releases used aliases such as `ActiveDirectoryMSI`; pin versions per compatibility matrix and use mode names matching your driver.

Spring Cloud Azure can also supply credentials to other Spring integrations, whereas `ActiveDirectoryDefault` is a Microsoft JDBC Driver mode that invokes Azure Identity via the driver's dependencies/version. Check which credential settings the driver actually reads; do not assume every Spring Cloud Azure property propagates into the SQL driver automatically.

System-assigned Managed Identity:

~~~yaml
spring:
  datasource:
    url: jdbc:sqlserver://${SQL_SERVER}.database.windows.net:1433;databaseName=${SQL_DATABASE};encrypt=true;trustServerCertificate=false;hostNameInCertificate=*.database.windows.net;loginTimeout=30;authentication=ActiveDirectoryManagedIdentity
~~~

User-assigned Managed Identity can specify the client ID via `msiClientId` depending on driver version:

~~~text
jdbc:sqlserver://<server>.database.windows.net:1433;databaseName=<database>;encrypt=true;trustServerCertificate=false;authentication=ActiveDirectoryManagedIdentity;msiClientId=<managed-identity-client-id>
~~~

Or use `authentication=ActiveDirectoryDefault` so the driver invokes `DefaultAzureCredential`:

~~~yaml
spring:
  datasource:
    url: jdbc:sqlserver://${SQL_SERVER}.database.windows.net:1433;databaseName=${SQL_DATABASE};encrypt=true;trustServerCertificate=false;hostNameInCertificate=*.database.windows.net;authentication=ActiveDirectoryDefault
~~~

In driver 12.1, Microsoft Learn described the name `DefaultAzureCredential`; from driver 12.2 onward, the standard name is `ActiveDirectoryDefault`. Do not mix PostgreSQL/MySQL starter properties into the SQL Server JDBC driver if the driver does not read them.

### 7.2. Creating a Database User for Managed Identity

First configure a Microsoft Entra administrator on the logical SQL server/Managed Instance. Then, the Entra admin or an admin principal creates a contained database user representing the workload:

~~~sql
CREATE USER [orders-api-mi] FROM EXTERNAL PROVIDER;
GO
ALTER ROLE db_datareader ADD MEMBER [orders-api-mi];
ALTER ROLE db_datawriter ADD MEMBER [orders-api-mi];
GO
~~~

This example uses built-in roles for illustration. Production should consider custom roles or exact schema/table `GRANT`s rather than broadly granting `db_datawriter` or `CONTROL` privileges. A migration identity may require DDL; a runtime identity typically needs DML only.

Azure SQL authentication can succeed while queries are still rejected if the contained database user has not been created or roles/`GRANT`s are missing. Azure Resource Manager Contributor/SQL Server Contributor does not automatically grant `SELECT`/`INSERT` on the database.

### 7.3. Spring Data JDBC/`JdbcTemplate`

Once `DataSource` is configured properly, Spring Data JDBC/`JdbcTemplate` works just like with standard SQL Server:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderJdbcRepository {
    private final JdbcTemplate jdbc;

    public OrderJdbcRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int countOrders() {
        return jdbc.queryForObject(
            "SELECT COUNT(*) FROM dbo.orders",
            Integer.class);
    }
}
~~~

Never acquire access tokens manually inside each repository method. Let the JDBC driver/credential integration manage connection tokens. HikariCP manages the pool; new connections need valid authentication, so test credential refresh when the pool opens fresh connections after long uptimes.

## 8. Azure Cosmos DB for NoSQL

Cosmos DB for NoSQL uses an SDK/HTTP API rather than JDBC. The Java client accepts a `TokenCredential` from Azure Identity. Example:

~~~xml
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-cosmos</artifactId>
</dependency>
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
</dependency>
~~~

Build the client with `DefaultAzureCredential`:

~~~java
import com.azure.cosmos.CosmosAsyncClient;
import com.azure.cosmos.CosmosClientBuilder;
import com.azure.identity.DefaultAzureCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;

DefaultAzureCredential credential =
    new DefaultAzureCredentialBuilder().build();

CosmosAsyncClient client = new CosmosClientBuilder()
    .endpoint(System.getenv("AZURE_COSMOS_ENDPOINT"))
    .credential(credential)
    .buildAsyncClient();
~~~

In Spring Data Cosmos, apply this credential when configuring the `CosmosClientBuilder`/client bean used by `CosmosTemplate` or repositories. Bean names and extension points depend on your Spring Data Cosmos version; avoid letting another auto-configuration create a key-based client that accidentally remains active.

### 8.1. Native Data-Plane RBAC

Cosmos DB for NoSQL has its own native data-plane role system. Two common built-in roles:

- **Cosmos DB Built-in Data Reader:** reads items, queries, and reads change feed within the role's scope.
- **Cosmos DB Built-in Data Contributor:** reads/writes items and performs data operations within the role's scope.

Assign the role to the principal ID of the Managed Identity/service principal/user and limit the scope to account, database, or container. Example container scope:

~~~text
/dbs/orders-db/colls/orders
~~~

The Java SDK acquires tokens for Cosmos DB for NoSQL with scope `https://cosmos.azure.com/.default`; the SDK supports `TokenCredential` and attaches credentials to requests automatically.

Permissions to manage accounts/databases/containers belong to control-plane RBAC. Permissions to read/write items belong to native data-plane RBAC. Creating role definitions/assignments may require separate control-plane permissions; runtime workloads should never be granted permission to assign roles to themselves.

After verifying that applications use Entra data-plane roles, consider disabling key-based authentication (`disableLocalAuth`) on new accounts or during a controlled security migration. Do this only after auditing all workloads, operational tools, and backup/restore paths; any clients still using account keys will break.

### 8.2. Scope by API

The `Cosmos DB Built-in Data Reader/Contributor` roles above apply to **Cosmos DB for NoSQL**. Do not blindly apply them to Cosmos DB API for MongoDB, Cassandra, Gremlin, or Table. Each API has its own authentication/authorization model and requires consulting its specific documentation.

## 9. Authentication vs. Authorization

| Layer | Question | Example |
| --- | --- | --- |
| Azure resource identity | Which principal is the workload? | App Service Managed Identity |
| Token authentication | Is the token valid for the database? | Right SQL/`oss-rdbms`/Cosmos audience, unexpired |
| Database principal mapping | Which user does the database recognize? | PostgreSQL role, MySQL `AADUSER`, SQL contained user |
| Database/data authorization | What can the user do? | `GRANT SELECT`, `db_datareader`, Cosmos Data Reader |
| Azure control-plane authorization | Who can manage resources/role assignments? | Azure RBAC on server/account |

A Managed Identity can hold an Azure resource-management role yet lack a database user. Conversely, a database principal can have `GRANT`s inside the database while the workload fails to acquire a token and still cannot connect. Check each layer independently.

## 10. Token Lifetime, Connection Pools, and Refresh

Access tokens expire. Applications should never fetch a token once at startup and store it in a long-lived `spring.datasource.password`. Let the plugin/driver/credential integration acquire tokens when opening connections and manage caching/refresh through supported mechanisms.

Operational points:

- An already-authenticated JDBC connection can generally continue operating after the login-time token expires; tokens are checked when establishing connections. New connections require an unexpired token.
- When HikariCP opens a new connection after long uptime, the credential provider must fetch a fresh token. Test pool connection creation after the initial token expires.
- Never log tokens or store raw tokens in configuration or databases.
- Tune `maxLifetime`, `idleTimeout`, and `keepaliveTime` to network/server limits; do not set artificially short pool lifetimes that cause excessive Entra token requests.
- When an identity is deleted or a role assignment is revoked, already-open connections may not drop immediately. Revoking access requires draining/recycling connections and re-verifying permissions.
- Avoid instantiating a new `DefaultAzureCredential` or SDK client per request; reuse thread-safe credentials/clients per SDK guidance.

## 11. Protecting Managed Identities and Entra Permissions

Apply least privilege:

1. Give each workload or workload group clear trust boundaries.
2. Prefer system-assigned identity when lifecycle matches one Azure resource; use user-assigned when independent lifecycle management is needed.
3. Create dedicated runtime database principals; separate admin and migration identities.
4. Grant database permissions only on required schemas/tables/containers.
5. Never grant Azure subscription Owner/Contributor as a substitute for database `GRANT`s.
6. For service principals, prefer certificates or workload federation; avoid static client secrets whenever alternatives exist.
7. Audit role assignments and database grants; revoke access when workloads decommission.

**MySQL note:** Graph permissions attached to the MySQL server's user-assigned identity exist for principal resolution; that is no reason to grant those Graph permissions to the application's Managed Identity. Scope the server identity separately.

## 12. Troubleshooting by Service

| Symptom | Likely Causes | Checks |
| --- | --- | --- |
| Token acquisition failure | Managed Identity disabled, wrong client ID, workload lacks endpoint/credential, or wrong tenant | Azure resource identity, credential chain, tenant, Azure Identity logs |
| 401 / login failed | Expired token, wrong audience, missing principal, or Entra admin not configured | Resource/scope, database principal, server Entra settings |
| PostgreSQL `password authentication failed` | Plugin not loaded, mismatched username, wrong token resource | Starter/plugin version, username, `oss-rdbms` token |
| MySQL access denied | Wrong `AADUSER` mapping, missing cleartext plugin/TLS, or missing `GRANT` | Entra user spelling, Connector/J options, database grants |
| SQL Server login failed | Outdated JDBC driver, wrong auth mode, or unmapped identity | Driver version, `ActiveDirectoryManagedIdentity`/`Default`, contained user |
| Cosmos 403 | Token acquired but missing data-plane role or wrong scope | Principal ID, native role assignment, and database/container scope |
| Works locally, fails on Azure | Local uses Azure CLI credential; production Managed Identity lacks role | Actual host identity, token claims, principal mapping |
| Pool works initially then fails on reconnect | Token refresh/credential chain or identity assignment issue | Hikari connection creation, Azure Identity diagnostics |
| One service has access while another fails | Database principals/roles are per-database | Do not assume Azure roles transfer across SQL/PostgreSQL/MySQL/Cosmos |

Never log access tokens or connection strings containing secrets while diagnosing. You may log credential type, sanitized principal ID, database host, operation, error code, and correlation/activity ID.

## 13. Testing Entra Authentication

### 13.1. Unit Tests

Mock repositories/DAOs to test business rules and error handling. Unit tests do not prove tokens can authenticate to the database or that role assignments are right.

### 13.2. Local Integration Tests

For local development, use Azure CLI/IDE credentials or a least-privilege test principal. Verify:

- The credential chain acquires a token for the expected tenant/resource.
- The database principal has been created.
- Authorized `SELECT`/`INSERT` operations succeed.
- Unauthorized operations are rejected.
- TLS hostname/certificate validation stays enabled.

Never use a personal Entra admin account as the runtime test user.

### 13.3. Azure Integration Tests

Deploy the application onto an Azure resource with Managed Identity or Workload Identity. Verify:

1. The host supplies the expected system/user-assigned identity.
2. The principal ID/client ID matches the database user/role assignment.
3. Database authentication accepts tokens with the right audience.
4. Least-privilege check: required reads/writes succeed, while DDL or accessing other schemas is rejected.
5. The connection pool opens fresh connections with valid tokens after extended runtime.
6. Removing/revoking the role assignment in the test environment yields the expected authorization error.
7. Logs/metrics contain no raw tokens or secrets.

### 13.4. Minimum Test Matrix

| Test | PostgreSQL | MySQL | Azure SQL | Cosmos NoSQL |
| --- | --- | --- | --- | --- |
| Local developer credential | Entra plugin | Entra plugin | `ActiveDirectoryDefault` | `DefaultAzureCredential` |
| Managed Identity | Starter credential | Starter credential + server identity setup | `ActiveDirectoryManagedIdentity` | `TokenCredential` |
| Principal mapping | PostgreSQL role | `AADUSER` | Contained database user | Native data-plane role |
| Least privilege | `GRANT` | `GRANT` | SQL role/`GRANT` | Reader/Contributor/custom role |
| Token audience | `oss-rdbms` | `oss-rdbms` | `database.windows.net` | `cosmos.azure.com` |
| Expiry/reconnect | JDBC pool new connection | JDBC pool new connection | JDBC pool new connection | SDK credential refresh |

## 14. Migration Process from Passwords to Entra

Do not disable password authentication until verifying every workload has migrated:

1. **Inventory:** list all apps, jobs, migrations, reporting tools, and operators using database passwords/keys.
2. **Enable Entra:** configure the Entra administrator and required server/account settings.
3. **Create principal:** create the database user or native role for the workload identity.
4. **Grant least privilege:** apply minimal privileges and separate migration/runtime identities.
5. **Update app:** configure the right driver/starter/SDK for the service, endpoint, credential, and TLS.
6. **Test:** run unit, integration, and Azure smoke tests; verify both allowed and denied actions.
7. **Deploy canary:** switch one workload/instance first; watch token acquisition, login errors, 403s, and pool health.
8. **Rotate/revoke old secrets:** after all workloads migrate cleanly, revoke old credentials per change plan.
9. **Disable local auth if supported and required by policy:** audit backup/restore, admin tools, and remaining integrations first.
10. **Audit:** record principals, role scopes, owners, purpose, and revocation procedures.

~~~mermaid
flowchart TD
    A[Inventory password/key users] --> B[Enable Entra on database]
    B --> C[Assign workload identity]
    C --> D[Create database principal / data role]
    D --> E[Grant least privilege]
    E --> F[Configure Spring driver / SDK]
    F --> G[Integration test + canary]
    G --> H{All workloads pass?}
    H -->|No| I[Fix identity, audience, role or network]
    I --> G
    H -->|Yes| J[Revoke old password/key]
    J --> K[Disable local auth where supported]
    K --> L[Audit and monitor]
~~~

## 15. Common Design Pitfalls

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| Treating Managed Identity as database permissions | Valid token but `SELECT` is denied | Create database principal/role assignment and `GRANT` |
| Using Azure Contributor instead of database roles | Resource management rights without data access | Grant database authorization separately |
| Passing ARM tokens to databases | Invalid audience | Acquire tokens with the service's exact scope |
| Using PostgreSQL/MySQL plugins for Azure SQL | Driver ignores authentication mode | Use Microsoft JDBC Driver |
| Using key-based Cosmos SDK while assuming Entra migration is complete | App still depends on keys | Configure `TokenCredential` and inspect active client beans |
| Granting admin rights to runtime services | Larger blast radius on credential compromise | Create dedicated principals with minimal `GRANT`s |
| Confusing MySQL server UAMI with app UAMI | Graph permissions granted to the wrong identity | Separate server lookup identity from app connection identity |
| Storing access tokens in `application.yml` | Tokens expire and credentials leak | Let plugins/drivers/SDKs manage tokens |
| Testing locally with Azure CLI only | Production Managed Identity may lack grants | Run Azure integration tests with the workload identity |
| Disabling password/key auth too early | Legacy tools/jobs lose access | Inventory, canary, and revoke incrementally |

## 16. Practice Exercises

**Exercise 1 — PostgreSQL passwordless.** Create a PostgreSQL Flexible Server, enable an Entra admin, attach a Managed Identity to a Spring Boot workload, create a principal with `pgaadauth_create_principal`, grant schema/table privileges, and connect via `spring-cloud-azure-starter-jdbc-postgresql`.

**Exercise 2 — MySQL passwordless.** Enable Entra authentication for MySQL Flexible Server. Distinguish the server-side UAMI reading Microsoft Graph from the application's Managed Identity. Create an `AADUSER`, `GRANT SELECT/INSERT`, and verify Connector/J uses TLS.

**Exercise 3 — Azure SQL.** Configure Microsoft JDBC Driver 12.2 with `ActiveDirectoryManagedIdentity` or `ActiveDirectoryDefault`. Create a contained database user from an external provider, grant `db_datareader`, and verify a DDL statement is rejected.

**Exercise 4 — Cosmos DB.** Create a `CosmosAsyncClient` with `DefaultAzureCredential`. Assign Cosmos DB Built-in Data Reader to a specific container, verify queries succeed and writes fail; then switch to Contributor and re-test.

**Exercise 5 — Authentication or authorization?** Construct four failure scenarios: token acquisition failure, wrong token audience, missing principal, and existing principal lacking `GRANT`. Classify logs/errors and pinpoint what to fix in each.

**Exercise 6 — Credential chain.** Run the same app on a developer machine with `az login` and on Azure App Service with Managed Identity. Record which credential gets selected, its tenant, principal, and how to guarantee production never accidentally uses developer credentials.

**Exercise 7 — Token refresh.** With HikariCP, run the app long enough for the initial token to expire, then open new connections. Verify the plugin/driver acquires a fresh token; monitor login errors and pool metrics without logging tokens.

**Exercise 8 — Migration.** Plan migrating an app from database passwords to Entra. Cover inventory, principals/roles, canary rollout, secret revocation, disabling local auth if supported, and a rollback plan.

## 17. Key Takeaways

- **Microsoft Entra supplies identity and access tokens; the database must still map the principal and grant data rights.** Successful authentication does not imply successful authorization.
- PostgreSQL/MySQL Flexible Server use Spring Cloud Azure JDBC starters and plugins; Azure SQL uses the Microsoft JDBC Driver; Cosmos DB for NoSQL uses the Java SDK/`TokenCredential` and native data-plane RBAC.
- Use the exact **token audience/scope** for SQL, OSS RDBMS, or Cosmos. ARM tokens cannot substitute for database tokens.
- **Managed Identity is not a database user.** Create the corresponding PostgreSQL role, MySQL `AADUSER`, SQL contained database user, or Cosmos data-plane role.
- MySQL Flexible Server uses a **server-side user-assigned identity** to query Microsoft Graph; this is separate from the workload's Managed Identity.
- Choose system/user-assigned identities or appropriate credential chains; local developers can use Azure CLI/IDE while production prefers Managed Identity/workload identity.
- Drivers/starters/SDKs manage tokens and reconnections; never store raw access tokens in configs or logs. Test connection pools opening new connections after token expiry.
- Roll out passwordless incrementally: inventory, enable Entra, principals, least privilege, canary, revoke secrets, and only then disable local auth where supported.

## 18. References

- [Passwordless authentication with Spring Cloud Azure](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/passwordless-authentication)
- [Spring Cloud Azure PostgreSQL support](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/postgresql-support)
- [Spring Cloud Azure MySQL support](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/mysql-support)
- [Use Spring Data JDBC with Azure SQL Database](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/configure-spring-data-jdbc-with-azure-sql-server)
- [Microsoft JDBC Driver — Entra authentication](https://learn.microsoft.com/en-us/sql/connect/jdbc/connecting-using-azure-active-directory-authentication)
- [Microsoft JDBC Driver — connection properties](https://learn.microsoft.com/en-us/sql/connect/jdbc/setting-the-connection-properties)
- [Configure and manage Microsoft Entra authentication with Azure SQL](https://learn.microsoft.com/en-us/azure/azure-sql/database/authentication-aad-configure)
- [Microsoft Entra authentication for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/security/security-entra-configure)
- [Managed Identity connection for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/security/security-connect-with-managed-identity)
- [Microsoft Entra authentication for MySQL Flexible Server](https://learn.microsoft.com/en-us/azure/mysql/security/security-entra-authentication)
- [Set up Microsoft Entra authentication for MySQL Flexible Server](https://learn.microsoft.com/en-us/azure/mysql/flexible-server/security-how-to-entra)
- [Connect to Cosmos DB for NoSQL with Microsoft Entra ID and RBAC](https://learn.microsoft.com/en-us/azure/cosmos-db/how-to-connect-role-based-access-control)
- [Azure Identity client library for Java](https://learn.microsoft.com/en-us/java/api/overview/azure/identity-readme?view=azure-java-stable)
- [Azure Cosmos DB Java client library](https://learn.microsoft.com/en-us/java/api/overview/azure/cosmos-readme?view=azure-java-stable)
