# Cannot Connect: URI, DNS, TLS, `authSource`, or Permissions

## Learning Objectives

In **Spring Data MongoDB**, the same symptom—"cannot connect"—can originate from several different layers: malformed URI syntax, DNS failing to resolve the host, network blocking a port, TLS handshake failure, authenticating against the wrong database, or an account lacking permissions to run commands on a collection.

For example, a failing `mongoTemplate.findOne(...)` call might happen because the driver cannot locate a primary, because the password is valid but `authSource` is wrong, or because authentication succeeded yet the user was never granted `find` permission. The remedy for each case is completely different.

This lesson belongs to the **Errors and Diagnostics** chapter. After completing it, you will be able to:

- Read and verify `mongodb://` and `mongodb+srv://` MongoDB connection strings.
- Distinguish the **application database** from the **authentication database (`authSource`)**.
- Check DNS (A/AAAA, SRV/TXT), TCP, replica set topology, and TLS in a repeatable order.
- Distinguish **authentication** errors from **authorization** errors using messages, error codes, and actual operations.
- Test `MongoClient`, `MongoTemplate`, repositories, and reactive clients directly.
- Diagnose safely without leaking credentials or disabling TLS verification.

> Code snippets focus on the Java Driver and Spring Data MongoDB APIs. Spring Boot configuration property names, exception names, and driver options must be cross-checked against your project's actual version.

## 1. Identify the Failing Layer Before Changing Configuration

A MongoDB read request passes through multiple steps. Each step has distinct symptoms and checks:

```mermaid
flowchart TD
    A[Spring Data MongoDB calls MongoClient] --> B[Parse URI and build settings]
    B --> C[DNS: resolve host or SRV/TXT]
    C --> D[TCP: host, port, firewall]
    D --> E[TLS handshake and certificate verification]
    E --> F[Hello, topology discovery, and server selection]
    F --> G[Authentication: user, password, authSource]
    G --> H[Authorization: database, collection, command]
    H --> I[MongoTemplate / repository processes query]
```

This is a diagnostic layer diagram, not a strict per-socket protocol order: the driver can discover nodes, open additional connections, and perform authentication during ongoing operation.

| Symptom | First Possibility to Check | Distinguishing Signal |
| --- | --- | --- |
| Failure immediately during URI parsing | Wrong scheme, special characters, invalid option | Configuration exception before any traffic |
| `UnknownHostException` | DNS or wrong hostname | Hostname cannot be resolved from the app environment |
| `Connection refused`, `ConnectException` | Wrong port, service not listening, firewall | Socket cannot be established |
| `SSLHandshakeException`, `PKIX path building failed` | TLS, CA, hostname verification | TCP may succeed, but handshake fails |
| `MongoTimeoutException` during server selection | DNS/TCP/TLS/topology/read preference | Inspect `ClusterDescription` and underlying cause |
| `AuthenticationFailed`, usually code `18` | User/password, `authSource`, auth mechanism | Reached server, but authentication failed |
| `not authorized`, usually code `13` | Insufficient role or privilege | Authenticated successfully, but command was rejected |
| `ping` works, but `find`/`save` fails | Wrong target database or missing permissions | Must test the exact operation and namespace |

A server selection timeout **does not prove MongoDB is overloaded**. Its root cause can be DNS, certificates, or networking.

## 2. MongoDB URI: Hosts, Database, and `authSource`

Two common URI forms:

```text
mongodb://<username>:<password>@host1:27017,host2:27017/orders?authSource=admin&tls=true

mongodb+srv://<username>:<password>@cluster.example.net/orders?authSource=admin
```

Each part serves a different purpose:

- `mongodb://`: specifies one or more seed hosts and ports; the driver continues topology discovery.
- `mongodb+srv://`: retrieves host/port lists from DNS SRV records and applicable options from TXT records; ports are not specified directly on the host portion.
- `/orders`: default database for application operations when no other database is specified.
- `authSource=admin`: database used to authenticate the account; it does **not** determine which database the service reads from or writes to.
- `tls=true`: requires TLS for connections. SRV URIs normally enable TLS by default unless overridden; verify final effective settings.
- Options `replicaSet` and `readPreference`: affect which servers can be selected.

### 2.1. Example of Wrong `authSource`

Suppose an administrator creates user `orders_app` in `admin`, then grants read/write privileges on `orders`. A URI missing `authSource`:

```text
mongodb://orders_app:<encoded-password>@mongo1.internal:27017/orders?tls=true
```

With username/password SCRAM and a URI containing the `orders` database, the default authentication database may be `orders`. Because the user lives in `admin`, login can fail with `AuthenticationFailed`. The URI should explicitly specify:

```text
mongodb://orders_app:<encoded-password>@mongo1.internal:27017/orders?authSource=admin&tls=true
```

If the user was **created in `orders`**, then `authSource=orders` is appropriate. Verify where the user was created instead of guessing values at random.

For standard SCRAM, if the URI specifies no database at all, the default auth database is typically `admin`. With X.509, OIDC, LDAP, or other mechanisms, rules and requirements differ; supply parameters matching the actual mechanism.

### 2.2. Percent-Encode Special Characters in Passwords

If a password contains `@`, `:`, `/`, `?`, `#`, `%`, or other URI-reserved characters, you must **percent-encode the username/password individually** before embedding them in the URI string.

For example, with a hypothetical password `p@ss:word`:

```text
mongodb://demo:p%40ss%3Aword@mongo1.example.net:27017/orders?authSource=admin
```

If you omit encoding, `@` can be parsed as the delimiter between credentials and hostname. Never encode the entire URI as a single string, because that breaks the scheme, delimiters, and query parameters.

**Protect secrets:** never print URIs containing passwords into logs, tickets, terminal screenshots, or CI reports. CLI arguments can appear in process lists or shell history; prefer secret managers, interactive password prompts, and controlled configuration.

### 2.3. URI Mistakes to Check

| Configuration Mistake | Common Consequence |
| --- | --- |
| `mongodb+srv://cluster:27017` | Syntax error: SRV URIs must not include a port on the hostname |
| Extra or missing `/orders` | Unexpected default database |
| Wrong `authSource` | Account authentication fails |
| Unencoded `@`/`:` in password | Driver misparses URI credentials |
| `replicaSet` doesn't match topology | Driver cannot select an eligible server |
| URI set in properties while code creates a custom `MongoClient` | Spring Data beans may use different settings |
| Wrong host or pasted URI from another environment | DNS, connection, auth, or permissions may fail |

## 3. DNS: Test from Where the Application Runs

DNS on a development laptop is **not necessarily the same as DNS inside a container, pod, or VM**. Diagnostics must run from the environment whose network path and DNS match the application as closely as possible.

### 3.1. `mongodb://` URIs: A/AAAA Records

A URI like `mongodb://mongo1.internal:27017/orders` must resolve `mongo1.internal`.

Linux or containers with appropriate tools:

```bash
getent hosts mongo1.internal
nslookup mongo1.internal
```

Windows PowerShell:

```powershell
Resolve-DnsName -Name mongo1.internal -Type A
Resolve-DnsName -Name mongo1.internal -Type AAAA
```

Not every minimal container includes `dig`, `getent`, or `nslookup`; if missing, use an authorized diagnostic container in the same network environment rather than installing ad-hoc tools onto a production workload.

### 3.2. `mongodb+srv://` URIs: SRV and TXT

For `mongodb+srv://cluster.example.net/orders`, the driver looks up SRV records at:

```text
_mongodb._tcp.cluster.example.net
```

Linux:

```bash
dig SRV _mongodb._tcp.cluster.example.net
dig TXT cluster.example.net
```

PowerShell:

```powershell
Resolve-DnsName -Name _mongodb._tcp.cluster.example.net -Type SRV
Resolve-DnsName -Name cluster.example.net -Type TXT
```

Next, check **every target hostname and port returned in the SRV records**. A successful SRV lookup does not guarantee every target accepts TCP; DNS can also return different records due to private zones or caching.

Typical causes:

1. Corporate DNS, firewall, or cluster resolver does not support or blocks SRV/TXT lookups.
2. Wrong SRV domain name or records failing driver validation rules.
3. Targets from SRV fail A/AAAA resolution, or resolve only to addresses unreachable by the pod.
4. VPN, VPC peering, private endpoint, or DNS zone has not been provisioned for the app environment.
5. TXT records contain options disallowed by the driver or conflicting with the URI.

**Verification:** record the queried record name, target, and error type, without placing usernames/passwords into log output.

## 4. TCP, Firewalls, Allowlists, and Replica Set Topology

After DNS, the app must open TCP connections to the hosts and ports the driver needs. Examples:

Linux (if `nc` is available):

```bash
nc -vz mongo1.internal 27017
```

Windows:

```powershell
Test-NetConnection -ComputerName mongo1.internal -Port 27017
```

If this fails, verify from the application runtime environment:

- Is the server listening on the right interface and port?
- Is traffic blocked by a firewall, security group, IP allowlist, Kubernetes `NetworkPolicy`, or proxy?
- Does DNS return a public IP or private IP? Does the network route match that endpoint?
- Which **replica set nodes** must the app reach after the driver discovers topology?
- Does `replicaSet` in the URI match the actual replica set name? Is there a primary for writes?
- Does the read preference require a node that does not exist or is unavailable?

Reachability to a seed host does not guarantee the driver can reach **the hostnames advertised in the replica set configuration**. This is a common failure mode when connecting to MongoDB from containers, Kubernetes, or across NAT.

**Distinguish:** `Connection refused` usually means the connection was actively rejected at the host/port or by an inline device; `connection timed out` can mean packets were dropped or the host did not respond. `MongoTimeoutException` during server selection can surface at a higher layer above these errors.

A working TCP connection **does not prove** TLS, authentication, or collection permissions work.

## 5. TLS: Distinguishing Certificate Errors from Credential Errors

TLS protects data in transit and verifies server identity via certificates. After TCP succeeds, the TLS handshake can still fail.

| Message | What to Check |
| --- | --- |
| `SSLHandshakeException: PKIX path building failed` | JVM does not trust the server's CA or is missing an intermediate certificate |
| `No subject alternative DNS name matching ...` | Host in URI does not match the certificate's SAN |
| `bad_certificate` | Client or server certificate was rejected; check mTLS requirements |
| Handshake fails after changing endpoint/proxy | Certificate chain, SNI, TLS termination, and target host |
| Error occurs only after upgrading JDK | TLS version/cipher suites and truststore in the new runtime |

Example URI:

```text
mongodb://mongo1.example.net:27017/orders?tls=true&authSource=admin
```

The MongoDB Java Driver on the JVM normally uses TLS/SSL settings from the Java runtime. When the server uses an internal CA, **the application's truststore must trust the appropriate CA**. If mTLS is deployed, you must also supply the client certificate and private key via the corresponding SSL context/keystore configuration.

With replica sets or SRV, certificates must match **each actual hostname used by the driver**, not only the first seed hostname. Switching to an IP address to "work around" an error can still fail hostname verification if the certificate lacks an IP SAN.

Never fix this by disabling TLS, skipping hostname verification, or trusting all certificates. Those changes strip away guarantees that the application is talking to the intended trusted server.

## 6. Authentication: `authSource`, Secrets, and Mechanisms

Authentication checks whether an account is permitted to log in. For SCRAM:

- In which database was the account created?
- Is the username exact?
- Is the password pulled from the secret manager the right version?
- Is the password properly percent-encoded in the URI?
- Does `authSource` point to the database containing the user?
- Are the MongoDB server and client using compatible mechanisms?
- Is another `MongoClient` bean still using an old URI or stale secret?

If using X.509 or another mechanism, verify the principal, certificate, and mechanism-specific options instead of mechanically applying SCRAM fixes.

### 6.1. Testing with `mongosh` and a Password Prompt

Example for an environment with shell access and network permission:

```bash
mongosh "mongodb://mongo1.internal:27017/orders?tls=true" \
  --username orders_app \
  --authenticationDatabase admin \
  --password
```

Depending on the shell version, `--password` without a value prompts interactively. Never pass passwords directly on the command line. After logging in, test **a command in the exact same namespace as the application**; opening a shell successfully does not prove the app has write permission.

A `mongosh` test must also use the same network path, CA, and DNS as the application JVM. If the tool works on a laptop but fails inside a pod, you cannot conclude the password works for that deployment.

### 6.2. When to Look at Error Code 18

MongoDB typically reports `AuthenticationFailed` with code `18` for login failures. Troubleshoot in the order **user → authSource → secret → mechanism**, rather than changing the business database or granting admin roles. If authentication succeeds yet a command fails with `Unauthorized` (code `13`), move on to investigating **authorization**.

## 7. Authorization: Right User, Missing Permissions

Authentication and authorization are separate layers. An `orders_reader` account might be created in `admin`, authenticate cleanly, and hold the `read` role on `orders`, yet still be denied inserts, updates, or deletes.

Example read check in `mongosh`:

```javascript
use orders
db.orders.find({ _id: "healthcheck-nonexistent" }).limit(1)
```

Never write a test document into a production collection just to check permissions. If you must verify writes, use a **dedicated test collection** and an authorized account/environment.

| Spring Data MongoDB Operation | Required MongoDB Privilege |
| --- | --- |
| `MongoTemplate.findOne`, repository `findById` | `find` privilege on the collection |
| `insert`, `save` on a new object | `insert` privilege |
| `updateFirst`, `findAndModify` | `update` privilege |
| `remove` / repository delete | `remove` privilege |
| Index creation, collection creation | Specific privileges for creating indexes/collections |
| Aggregation accessing multiple collections | Privileges on all collections referenced by the pipeline |
| Transactions spanning multiple commands | Privileges for each command plus a transaction-capable deployment |

If error code `13` appears on `orders`, inspect the **target database/collection** and granted roles instead of blindly changing `authSource`. The `readWrite` role on the application database may suit write workloads, whereas many services only need `read` or a narrower custom role.

Never grant `root` or cluster-wide admin rights just to bypass a privilege error. Better practice separates the runtime application account from migration/index-management accounts and grants only required privileges.

### 7.1. Wrong Namespace Also Surfaces as "Unauthorized"

Suppose `MongoTemplate` is configured with database `admin` instead of `orders`. Querying `admin.orders` can be rejected even if the user holds `readWrite` on `orders`. **Fixing the target database** is the proper correction.

In multi-tenant systems, verify the tenant → database mapping after authentication. `authSource` may be shared across tenants, while business databases and access roles must remain isolated according to policy.

## 8. Spring Data MongoDB: Identifying Which Client Is Actually Used

### 8.1. Checking Application Configuration

For Spring Boot versions using the `spring.data.mongodb.uri` property:

```properties
spring.data.mongodb.uri=${MONGODB_URI}
```

In some newer Spring Boot versions, MongoDB property names have changed. Always check the **configuration reference for your exact version** instead of guessing property names. If the project defines a custom `MongoClient` or `MongoDatabaseFactory` bean, programmatic configuration can override property-driven auto-configuration.

URIs containing credentials should come from environment variables or a secret manager and must never be exposed via configuration endpoints or logs.

### 8.2. Creating a `MongoClient` Is Not a Connection Test

The MongoDB Java Driver manages its connection pool and server discovery asynchronously. Constructing `MongoClient` or `MongoTemplate` does not necessarily validate connectivity, TLS, or permissions immediately. An application can start up cleanly and only time out on the first request.

Illustrative Java Driver smoke test:

```java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.bson.Document;

String uri = System.getenv("MONGODB_URI");
if (uri == null || uri.isBlank()) {
    throw new IllegalStateException("MONGODB_URI is required");
}

MongoClientSettings settings = MongoClientSettings.builder()
        .applyConnectionString(new ConnectionString(uri))
        .build();

try (MongoClient client = MongoClients.create(settings)) {
    var db = client.getDatabase("orders");

    // Verify basic server responsiveness.
    db.runCommand(new Document("ping", 1));

    // Also verify read permission on the business collection.
    // Do not print document contents to logs.
    db.getCollection("orders")
      .find(new Document("_id", "healthcheck-nonexistent"))
      .limit(1)
      .first();
}
```

This is a standalone diagnostic snippet, not something to execute on every HTTP request.

**`ping` does not prove the account can read or write a collection.** An account can successfully run `ping` and still receive `Unauthorized` on `find` or `update`. Verify operations matching the application's actual privileges.

### 8.3. Checking the Actual `MongoTemplate`

After testing the driver directly, check the `MongoTemplate` bean used by your services or repositories:

```java
@Service
public class MongoConnectionProbe {
    private final MongoTemplate mongoTemplate;

    public MongoConnectionProbe(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public void verifyRead() {
        Query q = Query.query(
                Criteria.where("_id").is("healthcheck-nonexistent"));

        mongoTemplate.findOne(q, Document.class, "orders");
    }
}
```

This example uses the `MongoTemplate` configured in the application context; `Document` here is `org.bson.Document`. The command does not require a matching document to exist: succeeding shows that queries can execute against that namespace, distinguishing it from permission or connectivity errors.

Check:

1. Which database `MongoDatabaseFactory` selects.
2. Whether repositories reference the right template if the app has **multiple datasources/`MongoClient`s**.
3. Where the connection string is configured: properties, environment, code, or container secrets.
4. Whether MongoDB requires distinct TLS/auth settings across environments.
5. If running reactive, whether the reactive client uses the same intended URI and settings.

You may log the **target database name** via metadata APIs if logging policy allows, but never print a full connection string when it contains a password.

### 8.4. The `ReactiveMongoTemplate` Case

`ReactiveMongoTemplate` also uses the MongoDB Java Driver, so URI, DNS, TLS, `authSource`, and permission issues still apply. The difference is that a reactive publisher executes only when subscribed.

```java
Mono<Document> check =
        reactiveMongoTemplate.executeCommand("{ ping: 1 }");

// Inside a reactive service/controller method:
return check.then();
```

Creating a `Mono` without subscribing or returning it to the framework **has not tested connectivity**. Do not call `block()` on the WebFlux event loop. In integration tests, use `StepVerifier` or an appropriate subscription mechanism.

### 8.5. Why Transactions and Indexes Can Fail Even When CRUD Works

- The runtime account has read/write privileges but **lacks index/collection creation privileges**; startup index creation can fail.
- Transactions require an appropriate deployment and transaction setup; `Transaction numbers are only allowed ...` is a topology/deployment capability issue, unlike a bad password.
- An aggregation using `$lookup` into another collection may require permissions on that collection.
- Lacking a primary in a replica set can block writes even while some reads continue depending on read preference.

Record **which command** failed rather than concluding that all of MongoDB "cannot connect."

## 9. Reading Exceptions and Logs Properly

Illustrative log output:

```text
MongoTimeoutException:
Timed out while waiting for a server that matches WritableServerSelector.
ClusterDescription:
  ServerDescription{address=mongo1.internal:27017, type=UNKNOWN,
    exception=MongoSocketException:
    Exception opening socket,
    caused by java.net.ConnectException: Connection refused}
```

The outermost error is `MongoTimeoutException`, yet the root cause can be **unable to open a socket**. Increasing `serverSelectionTimeoutMS` will not fix a wrong host or port.

Exception groups to distinguish:

- `MongoConfigurationException` or URI parsing errors: invalid settings.
- `UnknownHostException`: hostname cannot be resolved.
- `MongoSocketException` / `MongoSocketOpenException`: socket or connection error.
- `SSLHandshakeException`: TLS, certificate, or hostname mismatch.
- `MongoSecurityException` or `MongoCommandException` code `18`: authentication failure.
- `MongoCommandException` code `13`: missing authorization.
- `MongoTimeoutException`: server selection wait or related timeout expired.

Class names and exception wrapping can vary across driver versions; Spring Data also translates several errors into `DataAccessException`. **Read the cause chain**, error code, namespace, server address, and command name.

### 9.1. Distinguishing Timeouts

| Option / Concept | Meaning |
| --- | --- |
| `serverSelectionTimeoutMS` | Waiting to select a server matching the topology and operation |
| `connectTimeoutMS` | Time limit to establish a TCP connection |
| `socketTimeoutMS` | Socket I/O wait limit per driver settings |
| Connection pool checkout timeout | Waiting for an idle connection from the pool |
| HTTP/gateway request timeout | Whole-request deadline, which may expire before MongoDB times out |

If the network is healthy and the server is genuinely slow, adjusting timeouts can make sense. With bad DNS, untrusted TLS, or missing permissions, raising timeouts only makes failures wait longer.

### 9.2. Enabling Controlled Logging

You can temporarily enable driver topology/connection logging:

```properties
logging.level.org.mongodb.driver.cluster=DEBUG
logging.level.org.mongodb.driver.connection=DEBUG
```

Enable only within authorized scope, time-box it, and filter sensitive data. Command/query debug logs can capture emails, tokens, or PII payloads. Never print URIs, secrets, request bodies, or entire documents as proof of connectivity.

## 10. Step-by-Step Troubleshooting Workflow

1. **Confirm the failing operation:** startup, `ping`, `find`, `save`, transaction, aggregation, or index creation? Record timestamp and exception/cause code.
2. **Verify active runtime configuration:** URI scheme, host/port, business database, `authSource`, TLS, topology options, and active client bean.
3. **Verify URI syntax:** special characters in password encoded; SRV has no port; `replicaSet` matches.
4. **Verify DNS from the app container/pod/VM:** A/AAAA or SRV/TXT, then resolve target hostnames.
5. **Verify TCP and topology:** are all required nodes reachable; check firewalls/network policies, private endpoints/allowlists, and primary stability.
6. **Verify TLS:** truststore, CA chain, SAN/hostname, TLS settings, and mTLS requirements if applicable.
7. **Verify authentication:** user location, `authSource`, auth mechanism, and secret version; code `18` usually belongs here.
8. **Verify authorization:** role on the right collection/command, database chosen by `MongoDatabaseFactory`; code `13` usually belongs here.
9. **Verify Spring Data:** confirm `MongoTemplate`, repositories, and reactive clients use the intended settings.
10. **Repeat a minimal test after fixing:** `ping`, `find`, and the minimal authorized business operation. Confirm privileges were not widened unnecessarily.

### Scenario A: `AuthenticationFailed` Message

```text
URI: mongodb://orders_app:<encoded-password>@mongo.internal:27017/orders?tls=true
User created in: admin
Result: AuthenticationFailed (code 18)
```

Fix the URI to explicitly set `authSource=admin`:

```text
mongodb://orders_app:<encoded-password>@mongo.internal:27017/orders?authSource=admin&tls=true
```

After fixing, test a `find` operation in `orders`. If `ping` succeeds yet `find` returns code `13`, stop changing `authSource`; inspect roles on the namespace instead.

### Scenario B: Handshake Failure

```text
javax.net.ssl.SSLHandshakeException:
PKIX path building failed
```

Verify the CA and intermediate certificates in the JVM truststore, hostname vs. SAN, and TLS deployment. Do not disable certificate validation as a "quick fix" in production.

### Scenario C: SRV Fails Only in Kubernetes

`dig SRV _mongodb._tcp.cluster.example.net` works on a laptop, but fails inside a pod. Check CoreDNS, pod DNS policy, private zones, network policies, and reachability to the target hosts/ports. Changing the MongoDB password will not fix DNS here.

### Scenario D: Reads Work, Writes Fail

```text
db.orders.find(...): success
db.orders.insertOne(...): not authorized (code 13)
```

Authentication has likely succeeded; check `insert` permission on `orders`. Do not grant cluster-wide admin roles to test. If the account is meant strictly for reporting, rejecting writes may be completely by design.

## 11. Testing to Catch Configuration Errors Early

| Test Scenario | Expected Behavior |
| --- | --- |
| Invalid URI scheme/option | Fails with invalid configuration details |
| Password containing `@`/`:` | Works when properly percent-encoded |
| Broken DNS SRV | Clear resolver/SRV error; not misattributed to wrong password |
| TCP blocked by firewall | Traceable timeout/socket error |
| JVM does not trust CA | TLS rejected; certificate validation is not bypassed |
| User in `admin`, URI authenticates against `orders` | Authentication fails if user does not exist in `orders` |
| User has `read` but not `insert` | `find` succeeds, write is rejected |
| `MongoTemplate` points to wrong database | Query test on target collection catches mismatch |
| Reactive pipeline not subscribed | No actual MongoDB request occurs |
| Brief primary loss in replica set | Proper handling/retry policy, not misreported as password error |

For transient errors such as failovers or brief network interruptions, consider **bounded retries with backoff and idempotency**. Do not infinitely retry URI errors, TLS trust failures, code `18`, or code `13`, as those are usually configuration or authorization issues.

For writes, also evaluate retryable writes, transaction semantics, and the risk that the server executed the operation before the client lost the response. Never automatically re-run entire business workflows just because a timeout occurred.

## 12. Security During Diagnostics and Operations

A successful investigation must still protect data:

- Never put passwords, full connection strings, tokens, or private keys into logs, tickets, or command history.
- Never disable TLS verification, skip hostname validation, or open wide firewall rules just to get past an error.
- Never grant `root` to test a query; use an account with only the needed privileges.
- When driver logs are needed, limit log levels, collection window, and viewer access.
- Never log documents/PII in health checks; log only pass/fail outcomes and appropriate error codes.
- Never run ad-hoc writes or real user data into production collections to test.
- After fixing, verify the exact database/tenant, access permissions, and actual response times.

In multi-database/multi-tenant systems, `authSource` may be shared while per-tenant databases and roles differ. Start investigating from the authenticated tenant and queried namespace rather than extrapolating from a test on a different tenant.

## 13. Self-Check Exercises

1. An app uses `mongodb://user:pass@host/orders`, while the user was created in `admin`. State what must be added to the URI and why.
2. `Resolve-DnsName` returns valid SRV records, yet connections still fail. What must you verify for the target hostnames and ports?
3. Distinguish `Connection refused`, `SSLHandshakeException`, and `AuthenticationFailed` by failure layer.
4. Why can `ping` succeed while `MongoTemplate.save(...)` still fails with `Unauthorized`?
5. Why will increasing `serverSelectionTimeoutMS` not fix a wrong hostname or untrusted CA?
6. For `ReactiveMongoTemplate`, does creating a `Mono` without subscribing verify connectivity?
7. If a `read` role fits the business design yet an update is blocked, should you switch the role to `root`?
8. Why must you inspect the actual `MongoClient`/`MongoDatabaseFactory` beans instead of reading application properties alone?

## Takeaways

- **URI** specifies seed hosts, database, and options; **`authSource`** specifies where MongoDB verifies user identity.
- **DNS → TCP → TLS → topology → authentication → authorization** are separate diagnostic layers.
- **Code 18** usually indicates an authentication error; **code 13** usually indicates missing command/namespace authorization.
- Creating a `MongoClient` does not prove connectivity works; **`ping`** alone does not prove read/write permissions.
- `MongoTemplate` and repositories must use the **right client, database, and privileges**; reactive clients have their own configuration and execution paths.
- Inspect the **cause chain**, error code, and cluster description before changing timeouts, roles, or URIs.
- Make only minimal configuration changes, keep connection secrets confidential, and always re-test actual business operations.

In Spring Data MongoDB, systematic diagnostics resolve connectivity incidents faster, prevent misconfigured permissions or disabled security controls, and establish a foundation for reliable operational logging, monitoring, and testing.
