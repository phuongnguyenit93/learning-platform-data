# Encryption, IAM Database Authentication, and Credential Management

A Java application running on Amazon ECS or AWS Lambda needs to query customer data from **Amazon RDS** or **Amazon Aurora**. Even when the database is already placed in a private subnet, three distinct questions still need answers: **how is data on disk encrypted?**, **is the connection between the application and the database protected?**, and **how does the application prove its identity to log in to the database?** These correspond respectively to **AWS KMS encryption at rest**, **TLS encryption in transit**, and **database authentication/authorization**.

Confusing these mechanisms easily leads to broken security postures: a system where “KMS is enabled” yet the app sends login credentials over a connection that skips certificate verification; or an IAM role granted `rds-db:connect` while assuming it can read every SQL table; or database passwords hardcoded in source code despite having **AWS Secrets Manager** and **IAM database authentication**.

This lesson belongs to the **RDS and Aurora Databases** chapter of the **CLOUD_PROVIDERS_AWS** module, connecting Region/AZ selection, IAM, VPC, compute, storage, databases, integration, and serverless with secure deployment, monitoring, recovery, and cost control requirements.

## 1. Learning objectives

After this lesson, you will be able to:

1. Distinguish **encryption at rest**, **TLS in transit**, **IAM database authentication**, **SQL privileges**, and **credential rotation**.
2. Explain KMS keys in RDS/Aurora, snapshots, backups, read replicas, key policies, and the risks of disabling keys.
3. Choose between an **AWS managed KMS key** and a **customer managed KMS key**, and design compatible backup/cross-Region restores.
4. Configure and verify TLS, server certificates, and mandatory encrypted-connection settings per database engine.
5. Set up **IAM database authentication** for MySQL/MariaDB/PostgreSQL across supported RDS/Aurora variants.
6. Write IAM **`rds-db:connect`** policies using the exact **database resource ID + database username**, distinguishing RDS instances, Aurora clusters, and RDS Proxy.
7. Generate and use **15-minute authentication tokens**, distinguishing them from AWS STS credentials and SQL permissions.
8. Manage passwords with **AWS Secrets Manager**, RDS-managed master credentials, rotation, and RDS Proxy.
9. Use CLI/SQL/Java to verify configurations, diagnose TLS/KMS/IAM/DB privilege errors, and estimate costs.

## 2. Three non-interchangeable protection layers

| Layer | What does it protect? | Common mechanism | What does it NOT solve? |
|---|---|---|---|
| **At rest** | Database storage, logs, automated backups, snapshots per service scope | RDS/Aurora storage encryption with AWS KMS | Does not encrypt TCP traffic; does not restrict SQL `SELECT` |
| **In transit** | Data and credentials over the client ↔ DB connection | **TLS**, CA/hostname verification, engine settings | Does not alter IAM/SQL permissions; does not encrypt disk |
| **Authentication** | Which identity may log into the database | DB password, **IAM database auth**, Kerberos where supported | Does not grant `SELECT`/`INSERT` |
| **SQL authorization** | Which schemas/tables/rows a DB account can touch | SQL `GRANT`, roles, RLS, and business checks | Does not open a VPC security group |
| **Credential lifecycle** | Storing, issuing, rotating, revoking secrets | Secrets Manager, temporary IAM credentials, rotation | Does not replace TLS and backups |
| **Network isolation** | Who can reach the DB endpoint on its TCP port | VPC security groups, private subnets, routes, NACLs | Does not protect data if a DB account is compromised |

~~~mermaid
flowchart LR
    APP["Java API / Lambda / ECS / EKS"] -->|"TLS / IAM token or password"| ENDPOINT["RDS / Aurora endpoint"]
    IAM["IAM role + rds-db:connect"] -. "Permits IAM DB login" .-> ENDPOINT
    SECRET["Secrets Manager"] -. "Provides DB password for password auth" .-> APP
    SG["VPC security groups"] -. "Restricts TCP 3306/5432" .-> ENDPOINT
    ENDPOINT --> STORAGE["RDS / Aurora storage<br/>Encryption at rest"]
    KMS["AWS KMS key"] -. "Protects storage encryption key" .-> STORAGE
    ENDPOINT --> SQL["Database users, roles,<br/>GRANTs, and data"]
~~~

**Example:** enabling encryption at rest does not give a **Lambda execution role** SQL privileges. To query a table, Lambda must pass through SGs/routes, establish TLS, log in via the configured auth mechanism, and the database account must hold the right **`GRANT`** on the corresponding schema/table.

## 3. RDS and Aurora: encryption-at-rest scope

### 3.1. RDS storage encryption

Amazon RDS supports encrypting stored data with **AWS KMS**, depending on engine and feature support. For an **encrypted DB instance**, coverage generally includes underlying database storage, transaction logs, automated backups, read replicas, and associated snapshots per RDS mechanics.

**At-rest encryption** is handled transparently by the service in the storage layer; applications read and write normally once authenticated and SQL-authorized. You do not rewrite SQL queries to AES-encrypt individual rows. **A KMS key protects storage data**, it is not a “database password.”

### 3.2. Aurora cluster encryption

Aurora uses a managed **cluster volume**, decoupling compute instances from multi-AZ distributed storage by design. **Aurora cluster encryption** is configured on the cluster and protects cluster storage plus backups/snapshots within AWS-supported scope. All **Aurora writer/reader instances** in that cluster share the same encrypted cluster storage model.

Do not confuse **Aurora cluster encryption** with **IAM database authentication**: an encrypted cluster can still use password auth, IAM auth, or other supported options depending on engine/version. Nor do the Aurora reader and writer endpoints alter the SQL permissions of the logged-in user.

### 3.3. Support by engine, Region, and version

AWS RDS/Aurora span many engines and engine versions. Attributes like **`StorageEncrypted`**, **`KmsKeyId`**, **`IAMDatabaseAuthenticationEnabled`**, and TLS options are not identical across all engine types. Before creating or migrating production, check the documentation specific to **RDS MySQL/MariaDB/PostgreSQL, Aurora MySQL/PostgreSQL**, or your exact engine.

### 3.4. Three statuses that are not equivalent

| Status | Accurate interpretation |
|---|---|
| **`StorageEncrypted = true`** | RDS/Aurora uses encryption at rest for that resource |
| **`KmsKeyId` has an ARN** | A KMS key protects storage; does not prove TLS or IAM auth |
| **`IAMDatabaseAuthenticationEnabled = true`** | IAM database authentication is enabled on the supported instance/cluster, yet you must still create/configure DB users and IAM permissions |

## 4. AWS KMS keys: AWS managed vs. customer managed

### 4.1. Comparing key choices

| Key | Who manages key policy and lifecycle? | When suitable | Watch out for |
|---|---|---|---|
| **AWS managed KMS key** for RDS | AWS manages the key policy; service-defined limits apply | Want encryption at rest with minimal key administration | Cannot customize key policy like a customer managed key |
| **Customer managed KMS key** | Organization controls IAM/key policy, rotation, state, and access | Compliance, auditing, lifecycle control, cross-account snapshot/copy | Misconfigured key policy or disabling/deleting the key can make DBs/snapshots inaccessible |

**Do not grant every Lambda/ECS app role `kms:Decrypt` on the RDS storage key just because the app runs `SELECT`.** RDS uses KMS inside its service-managed storage encryption layer. IAM/KMS permissions for **creation, snapshots, restores, copies**, and key grants are separate from **SQL connection privileges**. Grant KMS permissions directly to a client only when the client itself calls KMS or reads a separately encrypted secret/S3 object.

### 4.2. Envelope encryption and grants

~~~mermaid
flowchart TD
    CREATE["Create RDS instance / Aurora cluster<br/>StorageEncrypted = true"] --> SELECT["Select KMS key"]
    SELECT --> GRANT["RDS integrates with KMS / grants<br/>per authorized permissions"]
    GRANT --> DATA["Encrypted storage, logs,<br/>backups, and snapshots"]
    APP["Authenticated app"] --> DB["SQL endpoint"]
    DB --> DATA
    CLIENT["Backup/restore operator"] --> ACCESS["IAM/KMS + RDS permissions"]
    ACCESS --> GRANT
~~~

AWS KMS uses **envelope encryption**: the KMS-managed key protects the data keys used in the storage layer. RDS can use **KMS grants** when creating or starting resources. When encrypting with a customer managed key, the key policy and IAM must allow required operations; careless edits break provisioning, snapshots, or restores.

### 4.3. Rotation does not mean switching to a different KMS key ARN

- **Automatic KMS key rotation:** rotates the key material of the same logical KMS key where supported; previously encrypted data remains decryptable via the appropriate key material under KMS mechanics.
- **Changing a DB's actual KMS key:** you cannot simply edit **`KmsKeyId`** in place on an existing encrypted RDS instance. The standard path is **snapshot → copy snapshot with target key → restore to a new resource**; in supported **RDS Blue/Green Deployments**, you can also create a **green environment** using a new key via **`TargetKmsKeyId`** and switch over. Verify engine/version, constraints, quotas, and backup/rollback carefully before choosing this path; do not apply it mechanically to every Aurora cluster.
- **Keys for cross-Region replicas/backups:** the key must belong to the destination Region of the copy/restore; verify service support and KMS behavior in each Region.

**A KMS key that is disabled or scheduled for deletion** can render an encrypted database, backup, or snapshot inaccessible, causing downtime and loss of recovery paths. Never delete an old key just because “the DB moved to a new key” without inventorying every snapshot, replica, backup, and retention dependency still tied to the old key.

## 5. Snapshots, backups, read replicas, and restoring encrypted resources

### 5.1. Backups and snapshots inherit encryption state

A snapshot of an encrypted database **remains encrypted**. When copying a snapshot, you can choose a destination KMS key per service rules; to restore a database onto a different key, the common workflow is **copy encrypted snapshot → restore**. In many cases, you can also make an encrypted copy of an unencrypted snapshot and restore an encrypted resource; verify support per engine and snapshot type.

### 5.2. Cross-account snapshot sharing

When sharing an encrypted snapshot with another AWS account:

1. Grant **snapshot sharing/restore permissions** as supported by RDS/Aurora and the resource type.
2. An **AWS managed KMS key** does not work for cross-account encrypted snapshot sharing flows where the key policy cannot be edited.
3. With a **customer managed key**, grant the target account appropriate key access, and copy the snapshot using a key managed by the target account as needed.
4. Verify KMS key policies, IAM permissions, Region, snapshot type, database engine, and target resources.

Never treat a snapshot ARN as proof that another party can decrypt it. **RDS snapshot access** and **KMS key access** are two independent layers.

### 5.3. Read replicas, Multi-AZ, and Aurora Global Database

**Read replicas** serve reads and replication per engine capability; they do not replace backups/DR. **RDS Multi-AZ** and **Aurora** provide distinct HA topologies; enabling KMS does not guarantee RPO/RTO. With **Aurora Global Database** or cross-Region copy/restore, each Region has separate KMS requirements; rehearse failover/restores and update endpoints, DNS, and secrets when switching Regions.

### 5.4. Encryption and recovery strategies must go hand in hand

Minimum checklist: snapshot policies, AWS Backup if used, retention, cross-Region copies if DR requires it, key permissions in the destination Region, test restores with real data, and verifying that the app connects via TLS + IAM/password auth after restoration.

## 6. TLS encryption in transit: protecting every SQL connection

DB connections on port **3306 (MySQL/MariaDB)** or **5432 (PostgreSQL)** are separate from KMS encryption at rest. Always use **TLS** and verify the server certificate and hostname instead of relying solely on “the database is in a private subnet.”

### 6.1. What the application must verify

| Item | Goal |
|---|---|
| **TLS enabled** | Data and credentials are protected in transit |
| **Trusted CA bundle** | Client validates the certificate chain to the right RDS CA |
| **Hostname verification** | Prevents connecting to an impostor host; uses a valid RDS/Aurora endpoint |
| **TLS version/ciphers** | Compliant with security policy and engine version |
| **Certificate rotation** | App/driver trusts the new CA before the server certificate rotates |
| **DB server enforcement** | Rejects plaintext connections where supported by the engine |

AWS publishes the **RDS truststore bundle** on its CA management page. For example, the global bundle URL commonly cited in AWS docs:

~~~text
https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem
~~~

Download bundles only from trusted AWS sources and keep them updated. **Never deploy a trust-all SSL certificate verifier**, **`sslmode=disable`**, or disabled hostname verification “to make errors go away” in production.

### 6.2. PostgreSQL: enforcing TLS

For RDS/Aurora PostgreSQL, the **`rds.force_ssl`** parameter in a supported parameter group enforces TLS connections. Defaults and behavior vary by engine version and parameter group; check **`SHOW rds.force_ssl;`** and version docs instead of guessing.

PostgreSQL clients should use **`sslmode=verify-full`** with the proper CA and endpoint:

~~~text
host=db-demo.abcdefg.ap-southeast-1.rds.amazonaws.com
port=5432
sslmode=verify-full
sslrootcert=/secure/path/global-bundle.pem
~~~

**`sslmode=require`** encrypts the connection but does not always perform full server identity verification like **`verify-full`**. When MITM protection is required, enforce CA and hostname verification and test during certificate rotation.

### 6.3. MySQL/MariaDB: TLS and server enforcement

For RDS MySQL/Aurora MySQL and eligible engines, parameters such as **`require_secure_transport`** enforce TLS; availability and defaults depend on engine/version. On compatible MySQL clients, use **`ssl-mode=VERIFY_IDENTITY`** with the CA bundle. Never use an “accept any server certificate” TLS mode when transmitting credentials.

### 6.4. How do TLS and IAM auth relate?

An **IAM database authentication token** acts as the password during the database handshake. Connections must be protected per engine/AWS requirements; a short-lived token is no excuse to skip TLS. A leaked 15-minute token can still be abused within its validity window if auth and network rules permit.

## 7. Traditional passwords vs. IAM database authentication

| Characteristic | DB password authentication | IAM database authentication |
|---|---|---|
| Client secret | Password managed by DB/user | **Temporary auth token** signed with AWS credentials |
| Lifespan | Until rotated/expired per policy | Token used to **initiate a connection** is valid for **15 minutes** |
| Lifecycle management | Secrets Manager/rotation or secret store | IAM role + AWS SDK/CLI generates fresh tokens |
| Access control | DB user/password + SQL grants | **`rds-db:connect`** on `dbuser` ARN + IAM-configured DB user + SQL grants |
| Revocation | Rotate password, disable DB user, terminate sessions | Revoke/restrict IAM role/DB user; already authenticated sessions may persist |
| New connections at high rate | Bounded by pools/DB limits | Incurs IAM auth overhead; throttle new connection creation rate |
| Engine scope | Broad across DB engines | Only supported RDS/Aurora engines/versions |
| Best suited for | Apps/drivers needing passwords, secret-backed proxies, legacy | AWS workloads with IAM roles, automated token rotation, moderate connection churn |

**IAM auth eliminates long-lived database passwords inside the app** for IAM-enabled users; the app signs tokens using temporary AWS credentials from its execution/task/pod/instance role. However, **the user must still exist inside the database**, be configured with the right auth plugin/role, and hold least-privilege **SQL GRANTs**. IAM permits *logging in*; it does not grant permission to read tables.

### 7.1. Supported engines per AWS capabilities

IAM database authentication is supported for specific engines/versions of **RDS for MySQL, MariaDB, PostgreSQL**, and **Aurora MySQL-/PostgreSQL-compatible**. It is **not a universal feature across all RDS engines** such as SQL Server or Oracle. Specific limitations with replicas, engine versions, global databases, or add-on features can change; read the engine-specific docs before enabling.

### 7.2. What does the 15-minute token window mean?

**15 minutes** is the validity window for using a token to establish a **new connection** from the time the token was generated; **it is not a 15-minute limit on the duration of an already-established SQL session**. Once a connection is accepted by the DB, it can stay open per DB timeout/connection policies even after the token expires. For reconnects or when a pool opens a new physical connection, you must **generate a fresh token**.

**Never cache a token for the entire day** or generate one at app startup and reuse it indefinitely. Clock skew, mismatched username/hostname/port during signing, expired tokens, or expired SDK credentials will cause the DB handshake to fail.

## 8. End-to-end IAM database authentication flow

~~~mermaid
sequenceDiagram
    participant APP as Java app / Lambda
    participant IAM as IAM role credentials
    participant SDK as AWS SDK / CLI signer
    participant RDS as RDS / Aurora endpoint
    participant SQL as DB user + grants
    APP->>IAM: Obtain temporary AWS credentials via role
    APP->>SDK: Sign DB auth token (host, port, username)
    SDK-->>APP: 15-minute auth token
    APP->>RDS: TLS handshake + DB username + token
    RDS->>RDS: Verify IAM identity / rds-db:connect
    RDS->>SQL: Verify DB user has IAM auth and SQL privileges
    SQL-->>APP: Authenticated DB connection
    APP->>SQL: SQL SELECT/INSERT per GRANT
~~~

Calling the token generator via SDK/CLI produces **a client-side presigned authentication string**, not an AWS API call that retrieves a password from Secrets Manager. Do not assume CloudTrail logs every token creation: **`generate-db-auth-token`** is computed locally via signing mechanics, so inspect DB login/audit logs and IAM events separately.

### 8.1. Conditions that must all hold simultaneously

1. **IAM database authentication** is enabled on the target DB instance/cluster.
2. The **IAM principal** has exact **`rds-db:connect`** permission for **DB resource ID + username**.
3. The **SQL user** has been created and marked for IAM auth per engine rules.
4. **TLS connection**, server endpoint, port, and Region used to sign the token match accurately.
5. **Network** path from app to DB permits traffic: VPC, subnets, SGs, NACLs, routes, and DNS.
6. **SQL GRANTs** cover the exact database/schema/table/action needed.
7. **IAM role credentials** are valid and the token has not expired.

**Flipping the IAM auth toggle in the RDS Console satisfies only condition (1).** Missing any of the remaining conditions will still cause failures.

## 9. IAM `rds-db:connect` policy and database resource IDs

For IAM database authentication, the connection permission is **`rds-db:connect`**, not `rds:Connect` or `rds:DescribeDBInstances`. The IAM resource ARN uses the **`dbuser`** type and the **internal resource ID** of the instance, Aurora cluster, or proxy depending on which endpoint you connect to.

### 9.1. The ARN must use the resource ID, not the display DB identifier

| Case | Resource ID to use | Sample ARN |
|---|---|---|
| Direct connection to RDS DB instance | **`DbiResourceId`**, usually prefixed **`db-`** | **`arn:aws:rds-db:ap-southeast-1:111122223333:dbuser:db-ABCDEFGHIJKLMNOPQRSTU/app_iam`** |
| Direct connection to Aurora cluster | **`DbClusterResourceId`**, usually prefixed **`cluster-`** | **`arn:aws:rds-db:ap-southeast-1:111122223333:dbuser:cluster-ABCDEFGHIJKLMNOPQRSTU/app_iam`** |
| Connection via RDS Proxy | **Proxy resource ID**, usually prefixed **`prx-`** | **`arn:aws:rds-db:ap-southeast-1:111122223333:dbuser:prx-ABCDEFGHIJKLMNOPQRSTU/app_iam`** |

The resource ID strings in the table are **placeholders only**. **`DbiResourceId`** is not the DB instance identifier like `orders-prod-db`; **`DbClusterResourceId`** is not the cluster name like `orders-aurora`. For a proxy, client → proxy requires the **proxy resource ID** ARN—never confuse it with the cluster ARN used for client → DB.

### 9.2. Identity policy for a Java application role

Example IAM policy allowing an app to log in only as **`app_iam`** on a single RDS instance:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ConnectOnlyAsApplicationUser",
      "Effect": "Allow",
      "Action": "rds-db:connect",
      "Resource": "arn:aws:rds-db:ap-southeast-1:111122223333:dbuser:db-ABCDEFGHIJKLMNOPQRSTU/app_iam"
    }
  ]
}
~~~

If connecting to an **Aurora cluster**, replace **`db-...`** with **`cluster-...`** from the real cluster. If connecting only through a **proxy**, use **`prx-...`**. When multiple database users are needed, list each authorized ARN explicitly; never use **`dbuser:*/*`** just to save typing.

### 9.3. Distinguish API permissions from SQL connection privileges

~~~text
rds:DescribeDBInstances       → read DB metadata from RDS control plane
rds:ModifyDBInstance          → modify DB instance configuration
rds-db:connect                → permitted to attempt login via IAM DB auth
secretsmanager:GetSecretValue → retrieve an authorized secret
kms:Decrypt                   → use a KMS key for the matching secret/resource
SQL SELECT/INSERT/UPDATE      → governed by database roles / GRANTs
~~~

A role holding **`rds-db:connect`** cannot automatically call `rds:ModifyDBInstance`, and SQL user **`app_iam`** does not become a database administrator. IAM Database Authentication does not act as a per-SQL-query IAM policy.

### 9.4. Retrieve resource IDs via AWS CLI (read-only)

~~~bash
# Instance resource ID.
aws rds describe-db-instances \
  --region ap-southeast-1 \
  --db-instance-identifier orders-prod-db \
  --query 'DBInstances[].{DB:DBInstanceIdentifier,ResourceId:DbiResourceId,Endpoint:Endpoint.Address,IAM:IAMDatabaseAuthenticationEnabled}' \
  --output json

# Aurora cluster resource ID.
aws rds describe-db-clusters \
  --region ap-southeast-1 \
  --db-cluster-identifier orders-aurora \
  --query 'DBClusters[].{Cluster:DBClusterIdentifier,ResourceId:DbClusterResourceId,Endpoint:Endpoint,IAM:IAMDatabaseAuthenticationEnabled}' \
  --output json

# RDS Proxy resource ID lives inside DBProxyArn, e.g., the prx-... segment.
aws rds describe-db-proxies \
  --region ap-southeast-1 \
  --db-proxy-name orders-db-proxy \
  --query 'DBProxies[].{Name:DBProxyName,Arn:DBProxyArn,Endpoint:Endpoint,Status:Status,DefaultAuthScheme:DefaultAuthScheme}' \
  --output json
~~~

These commands only inventory resources you are authorized to view. Never guess a database resource ID by concatenating DB name, account, and Region; always read the value returned by the API.

## 10. Configuring SQL users for IAM authentication

**Prerequisites:** IAM database auth enabled on a compatible instance/cluster; database administrator privileges per organizational process; IAM role and TLS/network ready. The SQL commands below **modify database users and permissions**—run only in authorized environments and verify exact syntax for your engine/version.

### 10.1. RDS/Aurora MySQL: `AWSAuthenticationPlugin`

MySQL-compatible engines use the **`AWSAuthenticationPlugin`** for IAM-enabled database users. Illustrative example:

~~~sql
-- Run by a database administrator in a test environment.
CREATE USER 'app_iam'@'%'
  IDENTIFIED WITH AWSAuthenticationPlugin AS 'RDS';

-- Never grant server-wide privileges; grant only what is needed.
GRANT SELECT, INSERT
  ON orders_db.orders
  TO 'app_iam'@'%';
~~~

**Host pattern `'%'`** is purely database user-matching syntax in this example; **it does not mean opening the SG to `0.0.0.0/0`**. The VPC security group must still block unneeded network paths. For MariaDB or other engines/versions, user creation syntax can differ; consult **Creating a database account using IAM authentication** for your exact engine.

An IAM user should not simultaneously rely on a long-lived password with an incompatible plugin configuration. Even a properly granted **IAM role policy** is useless if the **`app_iam`** database user has not been created or configured with the plugin.

### 10.2. RDS/Aurora PostgreSQL: the `rds_iam` role

For PostgreSQL-compatible engines, grant the **`rds_iam`** role to the database user:

~~~sql
-- Example run with an appropriately privileged DB admin account.
CREATE ROLE app_iam LOGIN;
GRANT rds_iam TO app_iam;

GRANT CONNECT ON DATABASE orders_db TO app_iam;

-- Run inside database orders_db as the appropriate schema/table owner.
GRANT USAGE ON SCHEMA public TO app_iam;
GRANT SELECT, INSERT ON TABLE public.orders TO app_iam;
~~~

**`rds_iam`** governs the authentication method; **it does not grant SQL `SELECT`/`INSERT`**. A PostgreSQL user holding **`rds_iam`** prioritizes IAM auth over password authentication; never attach `rds_iam` carelessly to the **master user**, replication accounts, or users needed for password auth elsewhere. Verify engine, replication, and RDS Proxy behavior before altering active users.

### 10.3. Verify SQL privileges before production traffic

In PostgreSQL, inspect role memberships and schema/table grants via system catalogs/views. In MySQL, **`SHOW GRANTS FOR 'app_iam'@'%';`** lists granted privileges. Do not test only “login succeeded”: verify that ungranted statements, such as **`DROP TABLE`**, fail as expected.

## 11. Generating IAM database authentication tokens properly

**An authentication token is a SigV4-signed string used in place of a password when connecting over SQL**—not an access key or IAM role session token. The token must be generated with the **exact real DNS endpoint, port, database username, and Region** used by the connection.

### 11.1. AWS CLI: `GenerateDBAuthToken`

~~~bash
# Run in a Bash shell with valid AWS credentials.
# Replace placeholder values with your real database endpoint.
DB_HOST="orders-prod-db.abcdefg.ap-southeast-1.rds.amazonaws.com"
DB_PORT="5432"
DB_USER="app_iam"

TOKEN="$(aws rds generate-db-auth-token \
  --region ap-southeast-1 \
  --hostname "$DB_HOST" \
  --port "$DB_PORT" \
  --username "$DB_USER")"

# Never echo TOKEN into logs or tickets.
~~~

**`generate-db-auth-token` generates a token locally without checking `rds-db:connect` beforehand**; actual authorization is checked during the database authentication handshake. Therefore, successfully generating a token **does not prove** the app can log in.

**Never substitute an arbitrary CNAME for the RDS endpoint** when signing a token. AWS requires the official endpoint for signing; token and connection must agree on host, port, and user. With **RDS Proxy**, the token must target the **proxy endpoint**, not the underlying DB endpoint.

### 11.2. Connecting to PostgreSQL via `psql`

Bash example with **`psql`**:

~~~bash
# Uses the token from the previous step; enforces TLS verify-full.
PGPASSWORD="$TOKEN" psql \
  "host=$DB_HOST port=$DB_PORT dbname=orders_db user=$DB_USER sslmode=verify-full sslrootcert=/secure/path/global-bundle.pem" \
  -c 'SELECT current_user, now();'

# Clear the token variable after use in the lab shell.
unset TOKEN
~~~

**`PGPASSWORD`** here is a temporary environment variable, not a place for long-term credential storage. In production apps, use an SDK/driver/credential provider per connection open and protect secrets in memory. Never leak tokens into shell history, CLI arguments, CI/CD logs, or public reports.

### 11.3. Connecting with a MySQL-compatible client

Using a MySQL client supporting the authentication plugin and TLS:

~~~bash
# MySQL host/port must match the generated token (port 3306).
mysql \
  --enable-cleartext-plugin \
  --ssl-mode=VERIFY_IDENTITY \
  --ssl-ca=/secure/path/global-bundle.pem \
  --host=orders-mysql.abcdefg.ap-southeast-1.rds.amazonaws.com \
  --port=3306 \
  --user=app_iam \
  --password
~~~

The client prompts for a password; supply the **newly generated IAM token for that host/port/user** safely without passing **`--password=TOKEN`** on the command line, which leaks into process lists and shell history. Some MySQL drivers/versions require enabling **`mysql_clear_password`** or equivalent settings; check client/runtime docs. Because the plugin transmits the token during authentication, it is **safe only when TLS is properly configured and verified**.

### 11.4. Generating tokens in Java with AWS SDK for Java 2.x

AWS SDK for Java v2 provides **`RdsUtilities.generateAuthenticationToken`**. This example focuses on token generation without opening a JDBC connection:

~~~java
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.rds.RdsClient;
import software.amazon.awssdk.services.rds.RdsUtilities;

public final class RdsTokenFactory {
    private static final Region REGION = Region.AP_SOUTHEAST_1;
    private static final String HOST =
            "orders-prod-db.abcdefg.ap-southeast-1.rds.amazonaws.com";

    public static String createToken(String username, int port) {
        try (RdsClient rds = RdsClient.builder()
                .region(REGION)
                .credentialsProvider(DefaultCredentialsProvider.create())
                .build()) {

            RdsUtilities utilities = rds.utilities();
            return utilities.generateAuthenticationToken(b -> b
                    .hostname(HOST)
                    .port(port)
                    .username(username));
        }
    }

    private RdsTokenFactory() {}
}
~~~

This example requires the **`software.amazon.awssdk:rds`** dependency and compatible SDK versions. The token serves as the password when opening a JDBC connection; **TLS/CA verification**, timeouts, validation queries, and database grants must still be configured in the JDBC driver/pool.

**Do not create a new `RdsClient` for every SQL statement in production.** Reuse `RdsClient`/`RdsUtilities` or use lightweight SDK/driver integrations, and **generate a fresh token each time a physical database connection is opened** when the previous token nears expiry. Ensure the SDK credentials provider chain refreshes IAM role credentials properly.

### 11.5. SQL connection pools and token refresh

A connection pool like **HikariCP** opens far fewer **physical connections** than total SQL statements. You do not need a fresh token per query on an already authenticated connection. However, if the pool opens a new connection after 15 minutes or after a failover, any token saved at startup is expired.

Use a **dynamic credential supplier/token provider** invoked when opening each physical connection as supported by your JDBC driver/pool. If a pool only accepts a static password, design a safe refresh/reconfiguration strategy or evaluate **RDS Proxy**. Test scenarios such as **idle longer than 15 minutes followed by a new connection**, network flaps, and reader/writer endpoint failover.

## 12. IAM DB auth limits and connection strategies

AWS recommends considering **IAM database authentication** when new connection creation rates are moderate; docs cite a reference threshold **under roughly 200 new IAM-authenticated connections per second**, recommending connection pooling or **RDS Proxy** for higher new-connection rates. This figure is **not an exact hard quota for every DB**, but a design guideline to benchmark by engine, memory, and workload.

### 12.1. Protecting the database from connection storms

- **Long-running Java services:** size pools with moderate `maximumPoolSize`, idle timeouts, connection lifetimes, readiness checks, and reconnect backoff.
- **AWS Lambda:** concurrency spikes can open many DB connections; curb fan-out, set Reserved Concurrency, and consider RDS Proxy.
- **ECS/EKS:** HPA scale-outs multiply pool instances; 100 Pods each with a pool of 20 can open up to **2,000 DB connections**.
- **Aurora clusters:** writer/reader endpoints serve distinct roles; split read/write traffic and monitor `DBConnections` and failover.

### 12.2. IAM DB auth has overhead

IAM database authentication consumes extra memory/CPU during authentication; AWS recommends monitoring resource utilization and keeping headroom, especially on smaller instances or under high connection churn. Never roll out IAM auth broadly without watching **Enhanced Monitoring/Performance Insights/Database Insights**, DB connections, and app load.

### 12.3. A token is not proof of query authorization

An IAM role with **`rds-db:connect`** only opens the door for a declared DB username. SQL privileges are evaluated by **`CREATE USER/ROLE`, `GRANT`, RLS, and database policies**. If the user holds only `SELECT`, a valid token will never permit `DROP` or `ALTER`.

## 13. AWS Secrets Manager: storing and rotating passwords

In many systems, **password authentication** remains the right fit due to legacy drivers, proxy backends, engine support, or integration constraints. **AWS Secrets Manager** avoids hardcoding usernames/passwords in source code, AMIs, Docker images, or shared config files.

### 13.1. What does Secrets Manager manage?

| Capability | Meaning |
|---|---|
| **Secret value** | JSON payload such as username/password/host/port/dbname |
| **Encryption** | Secret encrypted with AWS KMS per service/key policy |
| **IAM/resource policy** | Defines which principals may call `GetSecretValue`/`PutSecretValue`/`RotateSecret` |
| **Version stages** | **`AWSCURRENT`, `AWSPENDING`, `AWSPREVIOUS`** in rotation workflows |
| **Rotation** | Automated password rotation on schedule/supported mechanisms |
| **Audit/monitoring** | CloudTrail API auditing, CloudWatch/event metrics, change alerts |

An application secret might hold JSON following a standard schema:

~~~json
{
  "engine": "postgres",
  "host": "orders-prod-db.abcdefg.ap-southeast-1.rds.amazonaws.com",
  "port": 5432,
  "dbname": "orders_db",
  "username": "app_password",
  "password": "PLACEHOLDER_NOT_REAL"
}
~~~

This is **sample data, not real credentials**. A secret may store only username/password if endpoint metadata is managed elsewhere. Never put real passwords in Git, CI/CD logs, CloudWatch Logs, exception stack traces, or documentation.

### 13.2. RDS-managed master password

RDS/Aurora supports **`ManageMasterUserPassword`** on eligible DB engines/resources: AWS RDS manages the master password automatically in **AWS Secrets Manager**, with integrated rotation support. Inspect **`MasterUserSecret`** status and settings via the RDS API.

**Master credentials should not be application credentials.** Create a dedicated **least-privilege application DB user** with only needed permissions, paired with IAM DB auth or a dedicated rotated secret. An AWS-managed master secret does not automatically create or rotate passwords for application users.

### 13.3. Rotation: single-user vs. alternating-users

| Strategy | How it works | Trade-off |
|---|---|---|
| **Single-user rotation** | Changes the password of the single active database user | Simpler, though new connections during transition can fail if app caches are stale |
| **Alternating-users rotation** | Two equivalent users alternate: rotates the inactive user's password, then flips current secret | Shrinks password-mismatch window; requires managing grants and a privileged rotation user |
| **RDS-managed master rotation** | AWS manages the master secret via built-in integration | Less operational work, though apps should not use the master account |

Secrets Manager rotation typically uses a **rotation Lambda function** with steps like **`createSecret`, `setSecret`, `testSecret`, `finishSecret`**. Never write a custom rotation function that updates the secret while **forgetting to update the password inside the database**—that causes immediate state drift. The rotation Lambda also needs **VPC connectivity** to the DB, IAM permissions to read/write the secret, and required DB privileges.

### 13.4. Cache secrets, but refresh them

Apps can use the **AWS Secrets Manager caching client/extension** or a TTL-bounded cache to reduce API calls and latency. However, caching too long leaves the app using an old password after rotation, causing login failures when pools open new connections. Implement bounded **refresh-on-auth-failure** alongside TTL refreshes; test connection pools across password rotations and RDS failovers.

Never call Secrets Manager on **every SQL query**. Fetch the secret when opening physical DB connections or through a cache; avoid unnecessary API bills and latency dependencies.

## 14. RDS Proxy: centralized pooling and two IAM authentication modes

**Amazon RDS Proxy** provides a **proxy endpoint** to pool and manage database connections, dampening short-lived connection bursts and smoothing certain failover scenarios on supported engines/features. It does not grant SQL privileges or fix slow queries. Session state, long transactions, and certain SQL statements cause **pinning**, reducing multiplexing gains.

### 14.1. Standard IAM vs. end-to-end IAM

| Mode | Client → Proxy | Proxy → Database | Database secret in Secrets Manager |
|---|---|---|---|
| **Standard IAM auth** | IAM token signed for proxy endpoint | Password authentication | **Required** for proxy to reach DB |
| **End-to-end IAM auth** | IAM token signed for proxy endpoint | IAM database authentication | **No DB password secret needed** for this flow |

AWS supports **end-to-end IAM authentication** on RDS Proxy for the **MySQL, MariaDB, and PostgreSQL** engine families when configuration/Region/version criteria are met. Inspect the proxy's **`DefaultAuthScheme`**; an existing proxy does not automatically switch to end-to-end just because clients use IAM auth.

~~~mermaid
flowchart TD
    APP["Java Lambda / ECS / EKS"] -->|"TLS + IAM token"| PROXY["RDS Proxy endpoint"]
    PROXY --> MODE{"Authentication scheme"}
    MODE -->|"Standard IAM"| SM["Secrets Manager<br/>DB password"]
    SM --> DB["RDS / Aurora"]
    MODE -->|"End-to-end IAM"| ROLE["Proxy IAM role<br/>rds-db:connect DB user"]
    ROLE --> DB
    DB --> SQL["SQL roles / GRANT<br/>business authorization"]
~~~

### 14.2. Distinct permissions for app vs. proxy

In both modes when using IAM client authentication, the **application IAM role** needs **`rds-db:connect`** on the ARN containing the **proxy resource ID `prx-.../db_user`**, and the token must be signed for the **proxy hostname**, not the DB instance hostname.

In **standard mode**, the **proxy IAM role** needs **`secretsmanager:GetSecretValue`** and matching KMS permissions to read the DB password; the app does not need access to that secret. In **end-to-end mode**, the proxy IAM role needs **`rds-db:connect` to the database resource ID**, the DB user must have IAM auth enabled, and DB password secrets are no longer required on that path. These are **two separate principals** and two separate authorization hops.

### 14.3. TLS and pinned connections

RDS Proxy uses AWS-managed TLS/certificates that may differ from trusting the RDS DB endpoint CA directly. Always enforce **TLS** and verify endpoints, CAs, and **`RequireTLS`** per proxy documentation. Pooling reuses connections, yet does not eliminate **long transactions, session variables, temp tables, or slow queries**; monitor **`DatabaseConnections`**, **`ClientConnections`**, **`SessionPinnedConnections`**, **`DatabaseConnectionsBorrowLatency`**, and backend query latency.

### 14.4. When should you use a proxy?

Strongly consider RDS Proxy for **Lambda concurrency bursts**, microservices with many small pools, short-lived compute instances, or failover reconnect storms. For a long-running Java service with a well-sized pool and low connection counts, proxy costs may outweigh benefits; benchmark latency, connection counts, memory, and proxy charges.

## 15. IAM, SQL, KMS, and Secrets Manager: principal matrix

| Principal / layer | Direct IAM DB auth | DB password from Secrets Manager | IAM via RDS Proxy |
|---|---|---|---|
| **App IAM role** | **`rds-db:connect`** on DB user ARN | **`secretsmanager:GetSecretValue`** + secret KMS permissions if needed | **`rds-db:connect`** on proxy `dbuser` ARN |
| **Database user** | IAM plugin / `rds_iam` + **SQL GRANT** | Password + **SQL GRANT** | Auth method matching proxy mode + SQL GRANT |
| **RDS Proxy IAM role** | N/A for direct connection | N/A if app reads secret directly | Secret read/KMS for standard; **`rds-db:connect` DB** for end-to-end |
| **RDS/KMS storage integration** | Storage encryption managed by RDS | Not a database password | Unchanged by adding a proxy |
| **DB administration role** | Manages DB parameters/users/privileges | Manages rotation and DB users | Manages proxy/targets and IAM config |
| **Backup operator** | Snapshot/RDS + KMS restore permissions | Needs no DB password just to copy encrypted snapshots | Independent of proxy |

### 15.1. IAM policy to read a single authorized secret

Example for an application role using **password auth only** with a secret encrypted by a customer managed KMS key:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadOneDbSecret",
      "Effect": "Allow",
      "Action": "secretsmanager:GetSecretValue",
      "Resource": "arn:aws:secretsmanager:ap-southeast-1:111122223333:secret:orders/app-db-REPLACE_SUFFIX"
    },
    {
      "Sid": "DecryptOnlySecretKey",
      "Effect": "Allow",
      "Action": "kms:Decrypt",
      "Resource": "arn:aws:kms:ap-southeast-1:111122223333:key/REPLACE_SECRET_KEY_ID",
      "Condition": {
        "StringEquals": {
          "kms:ViaService": "secretsmanager.ap-southeast-1.amazonaws.com"
        }
      }
    }
  ]
}
~~~

In this example, **`REPLACE_SUFFIX`** and **`REPLACE_SECRET_KEY_ID`** must be replaced with real values returned by AWS. The KMS key policy must allow the corresponding access; if the secret uses the AWS managed key, required permissions can differ. **The Secrets Manager KMS key is not necessarily the same KMS key used to encrypt RDS storage.**

### 15.2. Runtime role must match the compute platform

- **Lambda:** execution role; never store IAM user access keys in environment variables.
- **ECS/Fargate:** **task role** for the Java SDK; do not confuse with the task execution role used for ECR/logs.
- **EKS:** EKS Pod Identity or IRSA per service account where supported; avoid sharing a broad node role.
- **EC2:** instance profile, IMDSv2, and least-privilege policies.

IAM policies are still constrained by SCPs, permissions boundaries, and explicit Denies. An IAM **`Allow rds-db:connect`** cannot overcome a **missing SQL user, failed TLS verification, or an SG blocking port 5432**. Troubleshoot the exact failing layer rather than opening IAM wildcards.

## 16. Layered secure Java application architectures

### 16.1. Java API on ECS with IAM DB auth

~~~mermaid
flowchart TB
    USER["Client"] --> ALB["ALB HTTPS"]
    ALB --> ECS["ECS Java API<br/>Multi-AZ private subnets"]
    ROLE["ECS task role<br/>rds-db:connect for app_iam"] -. "SigV4 auth token" .-> ECS
    ECS -->|"TLS verify-full + IAM auth"| DB["RDS / Aurora endpoint<br/>Private DB subnets"]
    SG["DB Security Group:<br/>3306/5432 only from ECS SG"] -. "TCP authorization" .-> DB
    DB --> STORAGE["Encrypted storage / backups<br/>AWS KMS key"]
    ECS --> LOG["CloudWatch Logs / traces"]
    DB --> MON["RDS metrics / DB logs"]
~~~

**Pros:** the application stores no long-lived database password; IAM role credentials are managed automatically via ECS. **Trade-offs:** the Java pool must generate fresh tokens when opening physical connections, and SQL user **`app_iam`** needs least-privilege GRANTs.

### 16.2. Java Lambda through RDS Proxy with secret-backed proxy

~~~mermaid
flowchart LR
    API["API Gateway"] --> FN["Lambda Java"]
    FN -->|"TLS + IAM auth token"| PROXY["RDS Proxy"]
    ROLE["Lambda execution role<br/>rds-db:connect proxy ARN"] -. "IAM" .-> FN
    PR["Proxy IAM role"] -->|"GetSecretValue"| SM["Secrets Manager<br/>DB password rotation"]
    PROXY -->|"Password to DB"| DB["RDS / Aurora"]
    DB --> KMS["KMS encrypted storage"]
~~~

This illustrates **standard IAM authentication** via RDS Proxy. With **end-to-end IAM** where supported, the proxy uses IAM DB auth to reach the database, eliminating the DB password secret on that path. Not every environment should enable end-to-end: verify driver, proxy config, SQL user setup, IAM roles, and operational requirements.

### 16.3. Networking and availability still matter

Even with encryption enabled and IAM auth turned on, the app must still traverse **VPC networking**: right endpoint, private DNS, security group source, port, NACLs, and routing. On RDS Multi-AZ/Aurora, failovers drop TCP sessions; clients must **reconnect, refresh DNS, perform bounded retries, and maintain idempotency**.

**Multi-AZ is not Multi-Region DR.** If Regional resilience is required, you need backups/cross-Region copies/Global Database per engine, KMS keys in the DR Region, DNS/app endpoint updates, and recovery drills.

### 16.4. Endpoint selection

| Endpoint | When to use | Key watchout |
|---|---|---|
| **DB instance endpoint** | Direct RDS DB | IAM token signed for DB instance host/port |
| **Aurora writer cluster endpoint** | Reads/writes | Writer changes on failover; pool must reconnect |
| **Aurora reader endpoint** | Read-only workloads | Account for replica lag per architecture |
| **RDS Proxy endpoint** | Pooling/reconnect where supported | IAM token signed for proxy endpoint; IAM `dbuser` ARN uses proxy resource ID |

**Never use an arbitrary CNAME to sign an IAM database token** when AWS requires the official endpoint. With IAM auth and TLS hostname verification, the connected host, signed token host, and certificate must all align per official docs.

## 17. AWS CLI inventory for encryption, IAM auth, and secrets (read-only)

The following commands are **read-only** and do not modify AWS resources. Replace hypothetical Regions, identifiers, and ARNs with your authorized resources. Use an IAM principal with restricted **Describe** permissions rather than administrator credentials.

### 17.1. Inspect an RDS DB instance

~~~bash
aws sts get-caller-identity --output json

aws rds describe-db-instances \
  --region ap-southeast-1 \
  --db-instance-identifier orders-prod-db \
  --query 'DBInstances[].{Name:DBInstanceIdentifier,Engine:Engine,Version:EngineVersion,Encrypted:StorageEncrypted,KmsKey:KmsKeyId,IAMAuth:IAMDatabaseAuthenticationEnabled,ResourceId:DbiResourceId,Endpoint:Endpoint.Address,CA:CACertificateIdentifier}' \
  --output json
~~~

### 17.2. Inspect an Aurora DB cluster

~~~bash
aws rds describe-db-clusters \
  --region ap-southeast-1 \
  --db-cluster-identifier orders-aurora \
  --query 'DBClusters[].{Name:DBClusterIdentifier,Engine:Engine,Encrypted:StorageEncrypted,KmsKey:KmsKeyId,IAMAuth:IAMDatabaseAuthenticationEnabled,ResourceId:DbClusterResourceId,Writer:Endpoint,Reader:ReaderEndpoint,MasterSecret:MasterUserSecret}' \
  --output json
~~~

**`StorageEncrypted = true`** does not prove TLS is enforced. **`IAMAuth = true`** does not prove SQL users have proper privileges. Inspect DB parameter groups and test authentication with authorized users and SQL GRANTs.

### 17.3. Inspect KMS key state

~~~bash
aws kms describe-key \
  --region ap-southeast-1 \
  --key-id arn:aws:kms:ap-southeast-1:111122223333:key/REPLACE_STORAGE_KEY_ID \
  --query 'KeyMetadata.{Arn:Arn,State:KeyState,Enabled:Enabled,KeyManager:KeyManager,DeletionDate:DeletionDate}' \
  --output json
~~~

If the key is **`Disabled`/`PendingDeletion`**, follow data-protection procedures immediately. Never create a new key ARN and assume existing DB storage switched to it. **`KMS DescribeKey`** reads metadata only; it does not prove all RDS restore/snapshot permissions are intact.

### 17.4. Inspect secret metadata without reading the password

~~~bash
aws secretsmanager describe-secret \
  --region ap-southeast-1 \
  --secret-id orders/app-db \
  --query '{Name:Name,Arn:ARN,KmsKey:KmsKeyId,RotationEnabled:RotationEnabled,RotationRules:RotationRules,LastChanged:LastChangedDate,LastRotated:LastRotatedDate}' \
  --output json

aws secretsmanager list-secret-version-ids \
  --region ap-southeast-1 \
  --secret-id orders/app-db \
  --query 'Versions[].{VersionId:VersionId,Stages:VersionStages,Created:CreatedDate}' \
  --output json
~~~

**Never run `get-secret-value` during routine audit examples** to avoid printing secrets into CLI logs, tickets, or shared screens. When password verification is genuinely required, use authorized secret-access procedures and protect output.

### 17.5. Inspect RDS Proxy auth mode and health

~~~bash
aws rds describe-db-proxies \
  --region ap-southeast-1 \
  --db-proxy-name orders-db-proxy \
  --query 'DBProxies[].{Name:DBProxyName,Arn:DBProxyArn,Status:Status,Endpoint:Endpoint,RequireTLS:RequireTLS,DefaultAuthScheme:DefaultAuthScheme,Auth:Auth}' \
  --output json

aws rds describe-db-proxy-targets \
  --region ap-southeast-1 \
  --db-proxy-name orders-db-proxy \
  --target-group-name default \
  --output json
~~~

**`Auth`** output can reveal secret ARN and user mapping details; restrict to authorized operators. Check **`DefaultAuthScheme`** to distinguish standard IAM from end-to-end IAM rather than guessing from the proxy name.

### 17.6. Inspect TLS parameters for the exact engine

In PostgreSQL, inspect **`rds.force_ssl`**; in MySQL/Aurora MySQL, inspect **`require_secure_transport`**. Read the right **DB parameter group or Aurora DB cluster parameter group**, as parameter placement differs by engine/version.

~~~bash
# Read parameter metadata from a known DB parameter group.
aws rds describe-db-parameters \
  --region ap-southeast-1 \
  --db-parameter-group-name orders-db-params \
  --query 'Parameters[].{Name:ParameterName,Value:ParameterValue,ApplyMethod:ApplyMethod,Source:Source}' \
  --output json

# For Aurora cluster-level parameters:
aws rds describe-db-cluster-parameters \
  --region ap-southeast-1 \
  --db-cluster-parameter-group-name orders-aurora-cluster-params \
  --query 'Parameters[].{Name:ParameterName,Value:ParameterValue,ApplyMethod:ApplyMethod,Source:Source}' \
  --output json
~~~

Do not edit a production parameter group until you verify its **parameter family, dynamic/static type, `pending-reboot` status, and maintenance window**. Enforcing TLS can break legacy clients lacking an updated CA bundle/truststore.

## 18. Diagnostic runbook: do not lump every error under AccessDenied

A SQL request can fail at **network, TLS, IAM, database auth, SQL permissions, secret rotation, KMS storage key, or query/runtime**. Each layer has its own verification path.

~~~mermaid
flowchart TD
    A["App cannot query RDS / Aurora"] --> B{"At which stage does it fail?"}
    B -->|"Timeout / DNS"| NET["VPC/SG/route/endpoint<br/>DB instance, cluster, or proxy?"]
    B -->|"TLS / x509"| TLS["CA chain, hostname,<br/>certificate, sslmode"]
    B -->|"Authentication failed"| AUTH["DB user/plugin/rds_iam<br/>IAM role rds-db:connect<br/>token expiry and signed host"]
    B -->|"SQL permission denied"| SQL["SQL GRANT, schema/table,<br/>RLS, owner, tenant"]
    B -->|"Secrets/KMS error"| KEY["Secret rotation/stages<br/>KMS key policy/state"]
    NET --> FIX["Fix only the exact fault layer<br/>test in staging"]
    TLS --> FIX
    AUTH --> FIX
    SQL --> FIX
    KEY --> FIX
    FIX --> VERIFY["Verify TLS, login, SQL grants,<br/>p95 latency, and zero leaked secrets"]
~~~

### 18.1. Common symptoms and root causes

| Symptom | Possible cause | First investigation step |
|---|---|---|
| **Connection timeout** before login | Wrong DB endpoint/port, SG/NACL/route/DNS, database unavailable | Verify real endpoint, DB status, TCP path from workload subnet |
| **Connection refused** | Wrong port, DB process/target down, unhealthy proxy target | DB/proxy status, engine port, target health |
| **SSL certificate verify failed** | Truststore missing CA, hostname mismatch, cert rotation | CA bundle, JDBC/psql `sslmode`, signed endpoint |
| **IAM token generated, yet login rejected** | Wrong `dbuser` ARN in IAM policy, token signed with wrong host/port/Region, DB IAM auth disabled | `DbiResourceId`/`DbClusterResourceId`, token age, DB user config |
| **IAM token expired after 15 minutes** | Pool reusing startup token for new connections | Dynamic token generation on physical pool connection creation |
| **MySQL Access denied for user** | Wrong user/plugin, missing IAM role/permissions, host mismatch, or invalid token | `AWSAuthenticationPlugin`, `rds-db:connect`, username/host/TLS |
| **PostgreSQL PAM authentication failed** | Missing `rds_iam` role or incompatible IAM authorization | SQL role membership, IAM policy, TLS, endpoint |
| **Login succeeds, yet SELECT denied** | Missing SQL GRANT/schema permission/RLS | SQL user, table/schema grants, app tenant context |
| **Password login fails after rotation** | Stale app cache; `AWSCURRENT` secret differs from DB user password | Secret stages, rotation logs, connection pool refresh |
| **SecretsManager AccessDenied** | Role lacks `GetSecretValue`, resource policy, or SCP Deny | App task/execution role and exact secret ARN |
| **KMS AccessDenied when reading secret** | Secret CMK denies `kms:Decrypt` or key policy/boundary blocks it | Distinguish secret's KMS key from storage key |
| **RDS inaccessible-encryption-credentials** | Storage KMS key disabled/unavailable | KMS key state, RDS events, key recovery runbook |
| **RDS Proxy authentication error** | Token signed with DB hostname instead of proxy, wrong `dbuser` ARN, wrong standard/end-to-end config | Proxy endpoint, `DefaultAuthScheme`, role/secret/DB user |
| **RDS Proxy connection borrow timeout** | Proxy pool/DB overloaded or session pinning | Proxy metrics, `DBConnections`, long transactions |
| **Spike in errors after Multi-AZ failover** | Stale connections, DNS caching, TLS/reconnect, app retry storm | DB events, pool lifetime, DNS, retry/backoff |
| **Slow queries despite valid IAM/KMS** | Locks/contention, missing indexes, CPU/IO, DB capacity | Database Insights/Performance Insights, SQL `EXPLAIN`, CloudWatch |
| **Cross-account snapshot restore fails** | Snapshot share permissions, KMS key policy/Region, encrypted key type | Snapshot ARN/owner, KMS key permissions, destination Region |

### 18.2. Workflow when IAM DB login fails

1. Confirm whether the app uses **direct DB** or **RDS Proxy**, and note the exact hostname/port.
2. Run **`aws sts get-caller-identity`** inside the authorized runtime to verify the real IAM role ARN.
3. Inspect **`IAMDatabaseAuthenticationEnabled`** and the resource ID of the instance/cluster/proxy.
4. Match the **`rds-db:connect`** policy against **`dbuser:RESOURCE_ID/username`**—never substitute the display DB identifier.
5. Inspect the DB user: **`AWSAuthenticationPlugin`** for MySQL-compatible, **`rds_iam`** for PostgreSQL.
6. Re-generate the token using the exact host/port/user/Region; verify clock sync and valid AWS credentials.
7. Connect over TLS with CA and hostname verification; if failing, log errors/traces with the **token redacted**.
8. Once login succeeds, run a minimal permitted `SELECT`, then verify real queries and SQL GRANTs.

**Never log full tokens** for debugging. IAM tokens are long, carry identity/signature details, and are valid for a window; logs can become a credential leak vector. Log only safe metadata such as token generation timestamp, internal endpoint alias, controlled username, error code, and trace ID.

### 18.3. Workflow when Secrets Manager rotation causes errors

1. Check secret **`RotationEnabled`**, **`LastRotatedDate`**, and **`VersionStages` `AWSCURRENT`/`AWSPENDING`**; never print `SecretString` to public channels.
2. Check rotation Lambda/managed rotation status, VPC/SG, DB user permissions, and the secret's KMS key.
3. Verify app cache TTL, DB connection creation timing, and whether the driver/connection pool refreshes credentials.
4. Test opening a **new connection** in staging using the current secret version to avoid adding load to production.
5. If rotation is stuck, follow the Secrets Manager/RDS runbook; never manually move `AWSCURRENT` or change passwords without reconciling against the DB.
6. After fixing, verify new logins, drain old connections, check error rates, and watch the next scheduled rotation.

### 18.4. When a storage KMS key is disabled

This is a **critical availability incident**, not a password error. An encrypted RDS DB may enter **`inaccessible-encryption-credentials-recoverable`** or another terminal state depending on DB, backup, and engine conditions. AWS notes some instances have a bounded recovery window; workflows differ for Aurora, read replicas, and instances that cannot be stopped.

**Do not delete snapshots, keys, or grants** before verifying. Prioritize inspecting **`KeyState`, RDS events, key owner/account/Region**; if authorized, restore key state per the official runbook and verify database health. If the instance cannot be recovered, fall back to decryptable backups/snapshots per your DR plan. Never promise “re-enabling the key guarantees the DB immediately comes back” for every engine or state.

## 19. Monitoring, auditing, and incident response

### 19.1. Telemetry sources to maintain

| Source | What to monitor | Why it matters |
|---|---|---|
| **CloudWatch RDS metrics** | `DatabaseConnections`, `CPUUtilization`, `FreeableMemory`, `FreeStorageSpace`, IOPS, `Read/WriteLatency` | Detects sudden connection spikes and resource exhaustion |
| **Database Insights / Performance Insights** | DB load, waits, SQL bottlenecks where available | Separates auth overhead from slow queries |
| **Enhanced Monitoring** | OS-level CPU/memory/process metrics | Investigates memory overhead and saturation |
| **RDS/Aurora events** | Failover, maintenance, snapshots, key access issues | Recovery and RCA |
| **Database engine logs** | Login failures, TLS/auth issues, slow queries per config | IAM auth/SQL errors do not always appear in AWS control-plane logs |
| **Secrets Manager rotation status** | Rotation success/failure, version stages, last rotated | Prevents credential mismatches |
| **KMS/CloudTrail** | Key state changes, grant changes, KMS APIs, IAM/RDS control-plane activity | Audits encryption and key permissions |
| **RDS Proxy metrics** | `ClientConnections`, `DatabaseConnections`, `BorrowLatency`, pinned sessions | Detects connection storms |
| **Application traces** | JDBC connection waits, auth retries, query latency, pool errors | Correlates user symptoms with backend behavior |

**CloudTrail audits AWS APIs**, not every SQL statement or IAM DB auth login by default. **`generate-db-auth-token`** computes SigV4 tokens client-side, so you cannot rely on CloudTrail to count how many tokens users generated. To audit SQL logins and queries, enable database-specific auditing/logging per engine and security policy.

### 19.2. Recommended alerts

- Sudden spikes in **`DBConnections`**, **`DatabaseConnectionsBorrowLatency`**, app connection timeouts, or login failures.
- **Secret rotation failed/impaired** or overdue past its approved schedule.
- **KMS key disabled/pending deletion**, key policy/grant edits, or snapshot restore `AccessDenied`.
- **Parameter group** updates that alter TLS enforcement.
- Rising **RDS/Aurora failover events**, replication lag, or storage saturation.
- IAM policy modifications involving **`rds-db:connect`**, **`secretsmanager:GetSecretValue`**, **`kms:Decrypt`**, or **`rds:ModifyDBInstance/Cluster`**.

Do not apply a single alert threshold across all workloads. A batch job opening 500 short-lived connections differs from a low-p99 transactional API. Calibrate thresholds against SLOs, business hours, and measured baselines.

### 19.3. Keep secrets out of telemetry

Never log **database passwords, IAM auth tokens, Secrets Manager `SecretString`, JDBC URLs with passwords, `Authorization` headers, private keys, or sensitive data payloads**. When errors occur, exception messages can embed connection details; enforce redaction, log access controls, and retention policies.

## 20. Cost and choosing the right approach

**Encryption and credential management** involve more than KMS fees. Systems also pay for compute/storage, Multi-AZ, replicas, snapshots, secrets, proxies, CloudWatch, and networking. Evaluate total cost via **TCO + SLO**, not just individual API unit prices.

| Component | Cost/impact to consider |
|---|---|
| **RDS/Aurora compute/storage/I/O** | Instance or ACU charges, storage mode, provisioned IOPS, I/O requests by engine |
| **Multi-AZ, replicas, Global Database** | HA/DR capacity, replication, data transfer, and extra storage |
| **AWS KMS customer managed key** | Monthly key fee, API request volume, key rotation/storage by key type |
| **RDS encryption at rest** | KMS and associated resource costs; do not confuse with client-side encryption |
| **Secrets Manager** | Per-secret monthly fees and API/rotation call charges per current pricing |
| **Rotation Lambda** | Invocations/duration, private networking, logging |
| **RDS Proxy** | Proxy capacity fees per current pricing model |
| **CloudWatch/Database Insights** | Logs, metrics, retention, paid analysis features |
| **VPC network endpoints** | Interface endpoint hours, private networking, data processing |
| **Backup/restore** | Retained snapshot storage, cross-Region copies, data transfer |

### 20.1. Three reference optimization models

| Model | When suitable | Notes |
|---|---|---|
| **Direct IAM DB auth** | Java service with steady connection pools and clean IAM roles | Refresh token on physical connection open; benchmark new-connection rates |
| **Secrets Manager + DB password** | Legacy clients, engines/drivers lacking IAM auth support | Handle rotation/caching, `GetSecretValue`, and secret KMS policy |
| **RDS Proxy + IAM client** | Scaling Lambda/containers with many short-lived connections | Proxy fees apply; pick standard vs. end-to-end IAM mode carefully |

**IAM auth is not automatically cheaper than Secrets Manager** if it forces adding a proxy, custom dynamic JDBC token providers, and operational complexity. Conversely, sprawling self-managed passwords increase incident risk and recovery cost. Benchmark **latency, connection counts, throughput, cost, and operational overhead**.

### 20.2. Key policy and snapshot planning

If compliance mandates customer-managed keys and cross-account/Region backups, plan KMS keys from day one. Switching keys after production data accumulates requires snapshot/copy/restore or supported Blue/Green workflows, incurring extra storage, transitional resources, and testing effort.

## 21. Case exercises

### Case A — KMS enabled, yet the client still sends credentials insecurely

RDS PostgreSQL has **`StorageEncrypted = true`** and a customer-managed KMS key. A Java app uses a database password, yet its JDBC connection string disables SSL validation and relies solely on TCP 5432 restricted to private subnets.

**Task:** explain the two gaps and propose fixes.

**Hint:** KMS protects **at rest**, not data in transit. Enable TLS with **`verify-full`**, a valid CA truststore/hostname, consider **`rds.force_ssl`**, and test the app. Next, adopt **Secrets Manager/rotation** instead of hardcoded passwords; private SGs do not replace TLS.

### Case B — Lambda has `rds-db:connect` yet cannot log in

A Java Lambda uses IAM auth to Aurora PostgreSQL. Its role has:

~~~text
arn:aws:rds-db:ap-southeast-1:111122223333:dbuser:db-EXAMPLE/app_iam
~~~

Whereas the cluster reports **`DbClusterResourceId = cluster-REAL_ID`**.

**Task:** find the bug and propose the corrected policy.

**Hint:** it is using an instance **`db-...`** ID instead of **`cluster-...`** for an Aurora cluster connection. Check the real cluster resource ID, grant **`rds-db:connect`** on **`dbuser:cluster-REAL_ID/app_iam`**, verify PostgreSQL **`GRANT rds_iam`**, TLS, token/endpoint, and SQL GRANTs.

### Case C — HikariCP works initially, then fails after 15 minutes

An ECS service generates an IAM token once at startup and sets it as a static password in HikariCP. Initial connections succeed; later during autoscaling/reconnects, the app sees authentication failures.

**Task:** why do old SQL sessions keep running while new connections fail?

**Hint:** the token is valid for **15 minutes to establish a new connection**, without immediately terminating already-authenticated sessions. Use a dynamic token provider on physical connection creation, verify AWS credentials refresh and TLS, and consider **RDS Proxy** for large burst scale.

### Case D — Secrets Manager rotation finishes, yet the API returns 500

A Java service reads the password from its secret at startup, caches it forever, and opens new DB connections on every autoscaling event. Secrets Manager rotation changes the DB password.

**Task:** fix the application without disabling rotation.

**Hint:** use a TTL cache and refresh-on-auth-failure, verify **`AWSCURRENT`/`AWSPENDING`** stages, actual DB password, pool refresh, and rotation Lambda logs. Never call **`GetSecretValue` on every SQL query**, and never manually flip secret stages without verifying DB state.

### Case E — Changed KMS key, then could not restore an older snapshot

An RDS instance used **K1**; the team copied a snapshot with **K2** to restore a new DB, then scheduled **K1** for deletion. Weeks later they needed to restore an older snapshot not copied to K2.

**Task:** where was the mistake?

**Hint:** older snapshots still depend on K1. Inventory all snapshots, backups, replicas, and cross-account copies, verifying decryption and retention before disabling/deleting K1. Practice restore drills and check `KeyState` and IAM/KMS policies; never assume re-keying a DB re-encrypts all old backups.

### Case F — Lambda connection storm hitting RDS

API Gateway triggers hundreds of concurrent Java Lambda instances, each opening multiple DB connections. DB CPU and `DatabaseConnections` spike, user p99 latency degrades, and IAM authentication adds overhead.

**Task:** evaluate direct IAM auth, Secrets Manager, and RDS Proxy.

**Hint:** tune pools and Lambda concurrency, bound new connection rates, measure DB bottlenecks, and evaluate **RDS Proxy**. Choose **standard IAM with a secret backend** or **end-to-end IAM** if supported, watching session pinning and proxy costs. IAM auth is authentication, **not connection pooling**.

### Case G — IAM role has Connect, yet SQL `SELECT` is denied

PostgreSQL database user **`report_iam`** has **`GRANT rds_iam`** and connects successfully with a token. Running **`SELECT * FROM finance.transactions`** returns **`permission denied`**.

**Task:** where is the missing permission, and should you grant `AmazonRDSFullAccess` to Lambda?

**Hint:** no. The missing privilege is **SQL `GRANT USAGE ON SCHEMA` / `SELECT ON TABLE`** or RLS/ownership—not the IAM RDS control plane. Grant access only to the exact required tables and verify tenant isolation.

### Case H — Proxy accepts the token, yet backend reports auth failure

A Java app connects to the RDS Proxy endpoint; its IAM role has `rds-db:connect` on the proxy ARN and a valid token. The proxy is in **standard IAM mode**, yet the proxy's Secrets Manager secret holds an old password.

**Task:** identify the failing layer and fix it.

**Hint:** client IAM auth succeeds while **proxy → DB password authentication** fails. Inspect the proxy **`DefaultAuthScheme`**, Auth config, Secret ARN/rotation, and DB user password. If moving to end-to-end IAM, configure DB user IAM auth, proxy role `rds-db:connect`, and engine/version prerequisites.

### Case I — Lost access to customer managed KMS key

A security team disables an RDS customer-managed KMS key to meet an internal policy without checking dependencies. The DB enters an inaccessible state.

**Task:** design the incident response.

**Hint:** this is an **at-rest encryption key access** issue, not a JWT/password bug. Verify key ARN, `KeyState`, RDS status/events, and engine/backup recovery options; coordinate with the KMS key owner to restore access via formal procedures without deleting snapshots, then add SCPs/guardrails and key disable/deletion alerts.

### Case J — Cross-Region DR has a snapshot, yet fails to open

A system copies an encrypted RDS snapshot to another Region without preparing a customer-managed KMS key/permissions in the destination Region, and the DR app lacks the proper TLS CA/truststore and endpoint config.

**Task:** list what DR components must be verified.

**Hint:** the destination Region needs a KMS key and permissions, snapshot copy/restore, DB subnet group/SGs, parameter groups, new IAM DB resource ID and updated `rds-db:connect` ARN, SQL users, Secrets Manager, and TLS. Restoring the database while the app cannot connect **does not meet RTO**.

## 22. Production deployment checklist

- [ ] Verified engine/version, RDS instance vs. Aurora cluster type, Region, and HA/DR requirements.
- [ ] Selected storage encryption with **AWS managed KMS key** or **customer managed key** per compliance/operations.
- [ ] Verified `StorageEncrypted`/`KmsKeyId`, KMS key state/policy/grants, and snapshot encryption.
- [ ] Conducted backup/restore drills, inventoried snapshots/replicas, and planned safe key changes/copies.
- [ ] Configured **TLS**, CA bundle, hostname verification, and engine-supported DB parameter group TLS enforcement.
- [ ] Tested **certificate rotation**; prohibited insecure trust-all or SSL-disable settings in production.
- [ ] Placed DB in segmented private networks with SGs allowing the DB port only from authorized app SGs.
- [ ] Selected **IAM database auth** or **password auth** suited to drivers, workload, and connection creation rate.
- [ ] For IAM, enabled **`IAMDatabaseAuthenticationEnabled`** on supported instances/clusters.
- [ ] Granted **`rds-db:connect`** scoped to exact **`dbuser` resource ID/DB username**, avoiding broad wildcards.
- [ ] Created SQL users with **`AWSAuthenticationPlugin`** or **`rds_iam`** per engine; applied least-privilege SQL GRANTs.
- [ ] Generated fresh IAM tokens per **physical connection** with matching endpoint/port/Region/username and never logged them.
- [ ] Used **Lambda execution role / ECS task role / EKS Pod Identity / EC2 profile**, never hardcoded AWS keys.
- [ ] For password auth, stored credentials in **Secrets Manager** with KMS policies, rotation, and cache refresh.
- [ ] Managed master user/secret separately; prevented apps from using the master DB account for routine traffic.
- [ ] If using RDS Proxy, verified **standard IAM** vs. **end-to-end IAM**, roles, secrets, and TLS.
- [ ] Measured pool sizes, new connection rates, `DatabaseConnections`, proxy borrow latency, and DB p95/p99.
- [ ] Tested failover, reconnect, DNS refresh, DB credential rotation, and IAM token expiration.
- [ ] Enabled logs/alerts for auth failures, key state, rotation, DB performance, and IAM policy edits.
- [ ] Restricted who can read secrets, change KMS keys, edit DB parameter groups, and manage database users.
- [ ] Budgeted RDS/Aurora compute/storage, Multi-AZ, snapshots, KMS, Secrets Manager, proxy, and observability.
- [ ] Prepared a runbook distinguishing network, TLS, IAM DB auth, SQL privileges, Secrets rotation, and KMS key outages.

## 23. Key takeaways

**AWS KMS encryption at rest** protects RDS/Aurora storage, backups, and snapshots per service scope; **TLS** protects SQL traffic in transit; **IAM database authentication** authenticates a DB user via a SigV4 token valid for **15 minutes to open a new connection**; and **SQL GRANTs** determine which `SELECT`/`INSERT`/`UPDATE` statements the database user may run. These are **four separate layers** and never substitute for one another.

With **IAM DB auth**, the app uses an IAM role with **`rds-db:connect`** on the exact **`dbuser` ARN containing the database resource ID**, a DB user configured with the right IAM plugin/role, TLS verification, and proper SQL permissions. With **password auth**, use **Secrets Manager** to store, rotate, and refresh credentials rather than putting passwords in source code. **RDS Proxy** manages connection pools and supports **standard IAM** (proxy reads secret) or **end-to-end IAM** where eligible. Finally, a secure system still requires **private networking, backup/restore, key/secret lifecycle monitoring, HA/DR, and an incident runbook**.

### Official AWS documentation for reference

- [Amazon RDS: Encrypting RDS resources](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Overview.Encryption.html) — KMS at rest, snapshots, read replicas, key lifecycle, and Blue/Green.
- [Amazon Aurora: Encryption at rest](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Overview.Encryption.html) — cluster encryption, backups, and KMS.
- [RDS: SSL/TLS for connections](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.SSL.html) — CA trust, certificate bundles, and engine specifics.
- [RDS: IAM database authentication for MariaDB, MySQL and PostgreSQL](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.IAMDBAuth.html) — scope, limits, 15-minute tokens.
- [IAM DB authentication: Supported Regions and DB engines](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Concepts.RDS_Fea_Regions_DB-eng.Feature.IamDatabaseAuthentication.html) — check version/Region support.
- [IAM DB authentication: Creating a database account](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.IAMDBAuth.DBAccounts.html) — `AWSAuthenticationPlugin`, `rds_iam`.
- [IAM DB authentication: Creating IAM policies](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.IAMDBAuth.IAMPolicy.html) — `dbuser`/resource ID ARNs.
- [IAM DB authentication: Connecting](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.IAMDBAuth.Connecting.html) — `generate-db-auth-token` and SQL clients.
- [RDS: Password management with Secrets Manager](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-secrets-manager.html) — RDS-managed master password/rotation.
- [Secrets Manager: Managed rotation](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotate-secrets_managed.html) — managed service rotation.
- [RDS Proxy: Concepts and authentication](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy.howitworks.html) — connection pooling, standard/end-to-end IAM.
- [RDS Proxy: IAM authentication setup](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy-iam-setup.html) — proxy role and backend IAM access.
- [RDS Blue/Green: Encryption considerations](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/blue-green-deployments-considerations.html) — key changes on green environments.
- [Amazon RDS pricing](https://aws.amazon.com/rds/pricing/), [Amazon Aurora pricing](https://aws.amazon.com/rds/aurora/pricing/), [AWS KMS pricing](https://aws.amazon.com/kms/pricing/), [AWS Secrets Manager pricing](https://aws.amazon.com/secrets-manager/pricing/), and [AWS Pricing Calculator](https://calculator.aws/) — pricing by Region and service.
