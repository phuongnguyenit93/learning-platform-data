# Connection Strings, Database Names, `authSource`, and Application Accounts

> **Chapter:** Setup  
> **Scope:** MongoDB and Spring Data MongoDB (`MongoTemplate`, repositories, reactive).  
> **Objective:** Understand connection URIs, distinguish between the application database and authentication database, create least-privilege accounts, configure the application per Spring Boot version, and troubleshoot common connection errors.

## 1. What Information Does an Application Need to Connect to MongoDB?

A Spring Data MongoDB application connects to MongoDB through the **MongoDB Java Driver**. On the application side, `MongoClient`, `MongoDatabaseFactory`, `MongoTemplate`, or repositories use the same connection information to select servers, authenticate, and access data.

A minimal configuration typically requires:

1. **Server address**: MongoDB hostname/IP and port, or cluster address.
2. **Application database name**: where the application reads and writes collections.
3. **Authentication credentials**: username, password, or another authentication mechanism.
4. **Authentication database** (`authSource`): where MongoDB looks up the user identity when using a matching authentication mechanism.
5. **Connection options**: TLS, replica set, timeouts, write concern, etc., depending on the environment.

Example URI for a practice environment with authentication enabled:

~~~text
mongodb://inventory_app:<URL_ENCODED_PASSWORD>@127.0.0.1:27017/inventory_db?authSource=admin
~~~

In this URI, `inventory_db` is the database the **application operates on**, whereas `admin` is the **authentication database** for the `inventory_app` user. The two databases can be the same or different. Values inside `<...>` are placeholders, **not a ready-to-use password**.

## 2. Anatomy of a MongoDB Connection String

### 2.1. Standard URI Format: `mongodb://`

~~~text
mongodb://[username:password@]host1[:port1][,host2[:port2],...]/[database][?option1=value1&option2=value2]
~~~

| Component | Purpose | Example |
| --- | --- | --- |
| `mongodb://` | Uses an explicitly listed set of hosts/ports | `mongodb://` |
| `username:password@` | Account credentials; special characters in values must be percent-encoded | `inventory_app:abc%40123@` |
| `host:port` | MongoDB address reachable from the application | `127.0.0.1:27017` |
| `/database` | Default database for application operations | `/inventory_db` |
| `?authSource=...` | Database used to verify the user account | `?authSource=admin` |
| `&tls=true` | Requires a TLS-encrypted connection | `&tls=true` |
| `&replicaSet=...` | Name of the replica set to connect to | `&replicaSet=rs0` |

If the port is omitted in a standard URI, the default port is typically **27017**. Hosts in the URI must resolve meaningfully from the application's runtime environment: `localhost` inside a Docker container refers to **that container itself**, not automatically the Docker host or another MongoDB container.

Three examples for different purposes:

~~~text
# Local machine without authentication: suitable only for isolated test environments.
mongodb://127.0.0.1:27017/inventory_db

# Local machine with a user created in the admin database.
mongodb://inventory_app:<ENCODED_PASSWORD>@127.0.0.1:27017/inventory_db?authSource=admin

# Replica set: lists hosts and requires TLS over the network.
mongodb://inventory_app:<ENCODED_PASSWORD>@db1.example.net:27017,db2.example.net:27017,db3.example.net:27017/inventory_db?replicaSet=rs0&authSource=admin&tls=true
~~~

Hostnames ending in `example.net` are illustrative only. In production, configure real hostnames, dedicated accounts, TLS, and network rules matching your infrastructure.

### 2.2. DNS Seed List URI Format: `mongodb+srv://`

~~~text
mongodb+srv://inventory_app:<ENCODED_PASSWORD>@cluster.example.net/inventory_db?authSource=admin&retryWrites=true&w=majority
~~~

`mongodb+srv` looks up DNS SRV/TXT records to discover cluster nodes and connection options; the application usually needs only a single cluster hostname rather than a list of ports. The MongoDB driver enables **TLS** by default when using SRV unless overridden by configuration. This format is common in managed MongoDB services such as Atlas.

Notes when using `mongodb+srv`:

- The host in the URI is a DNS name with valid SRV records, not an arbitrary IP address; ports are generally not specified after an SRV hostname.
- Working DNS and network routes are required to resolve the hostname and reach the cluster nodes.
- TLS still requires trusted certificates and matching hostnames; do not disable certificate validation as a shortcut for configuration errors.
- Options supplied by the provider, including `authSource`, should be verified against where the user was created and your actual configuration.

### 2.3. Encoding Usernames and Passwords in a URI

Reserved URI characters can cause the driver to misparse boundaries between username, password, host, and query parameters. When embedding credentials in a URI, **percent-encode the username and password values individually**, not the entire URI.

| Original character in password | Percent-encoded representation |
| --- | --- |
| `@` | `%40` |
| `:` | `%3A` |
| `/` | `%2F` |
| `?` | `%3F` |
| `#` | `%23` |
| `$` | `%24` |
| `%` | `%25` |

For example, a real password `Abc@123` must appear as `Abc%40123` in the URI:

~~~text
mongodb://inventory_app:Abc%40123@127.0.0.1:27017/inventory_db?authSource=admin
~~~

This is a **fictional password for syntax illustration**, never use it in real deployments. Percent-encoding only ensures the URI parses accurately; it is **not security encryption**. Protect passwords via a secret manager, config access controls, and TLS in transit.

## 3. Distinguishing Application Database from `authSource`

Two independent questions must be answered:

- **Where does the data live?** → The application database, typically `inventory_db` in the URI path.
- **Where was the account created?** → The authentication database, specified by `authSource` or defaulted according to URI rules.

For SCRAM username/password authentication, if `authSource` is omitted, MongoDB authenticates against the database in the URI path (`defaultauthdb`); if no database is specified in the path, it defaults to `admin`. Specifying `authSource` explicitly reduces confusion when the two databases differ.

| URI (abbreviated) | Database used for data | Database used for authentication |
| --- | --- | --- |
| `.../inventory_db?authSource=admin` | `inventory_db` | `admin` |
| `.../inventory_db?authSource=inventory_db` | `inventory_db` | `inventory_db` |
| `.../inventory_db` | `inventory_db` | `inventory_db` (unless overridden by another config value) |
| `.../?authSource=admin` | Not specified in path; app must choose explicitly | `admin` |

**Scenario A:** An administrator creates user `inventory_app` in the `admin` database and grants the `readWrite` role on `inventory_db`. When connecting, the application must specify `authSource=admin`; read and write operations still target `inventory_db`.

**Scenario B:** An administrator creates user `inventory_app` directly in `inventory_db` with read/write privileges on `inventory_db`. In this case, you can use `authSource=inventory_db` or omit `authSource` when `/inventory_db` is in the URI path.

**Do not conflate authentication and authorization:** being able to log in does not guarantee permissions for `find`, `insert`, or `createIndex` on the application database. A valid user identity can still receive `not authorized` if required roles are missing.

## 4. Creating an Application Account Following Least Privilege

With self-managed MongoDB and authentication configured, an administrator can provision a dedicated user for the application. The examples below are for someone **who already has administrative privileges** on MongoDB; the application does not run `createUser()` on every startup.

### 4.1. User Created in `admin`, Permitted to Write Only to `inventory_db`

Log in as an admin via `mongosh`, then run:

~~~javascript
// Use admin privileges to create an application account.
use admin

db.createUser({
  user: "inventory_app",
  pwd: passwordPrompt(),
  roles: [
    { role: "readWrite", db: "inventory_db" }
  ]
});
~~~

Explanation:

- `use admin` selects the database **where the user is created**.
- `passwordPrompt()` prompts interactively for the password, avoiding writing the password directly into commands or shell history.
- `readWrite` grants only appropriate read/write permissions on `inventory_db`. The application does not need `root`, `userAdminAnyDatabase`, or `readWriteAnyDatabase`.
- For a read-only reporting account, consider the `read` role scoped to the exact required database.

To connect with this newly created user, the application URI takes the form:

~~~text
mongodb://inventory_app:<ENCODED_PASSWORD>@db.example.net:27017/inventory_db?authSource=admin&tls=true
~~~

This `db.createUser()` example applies to **self-managed MongoDB**. On **MongoDB Atlas**, database users are managed through the Atlas UI or management API; `db.createUser()` is not supported directly on Atlas clusters. Create the database user and assign roles in your provider's control plane, then use the URI they provide.

### 4.2. Creating a User Directly in `inventory_db`

If your organization prefers placing the application identity directly inside the application database:

~~~javascript
use inventory_db

db.createUser({
  user: "inventory_app_local",
  pwd: passwordPrompt(),
  roles: [
    { role: "readWrite", db: "inventory_db" }
  ]
});
~~~

Corresponding URI:

~~~text
mongodb://inventory_app_local:<ENCODED_PASSWORD>@127.0.0.1:27017/inventory_db?authSource=inventory_db
~~~

Do not create two duplicate users for the same purpose in both `admin` and `inventory_db` without a clear reason. In MongoDB, the same username in two different authentication databases represents **two distinct identities**.

### 4.3. Rules for Using Credentials in Applications

- Each service/environment should have its own user so credentials can be revoked, rotated, and audited without affecting other systems.
- Never embed real passwords in code, committed `application.yml` files, docs, or logs. Use environment variables supplied by the deployment platform, container/orchestrator secrets, or a secret manager.
- Never paste connection URIs containing passwords into issues, shared screens, or bug reports. When logging, output only **credential-redacted** details.
- Enable TLS for network connections; percent-encoding does not protect data in transit.
- Establish credential rotation and revocation policies; after granting roles, verify access using the actual **application** account rather than an admin account.

## 5. Configuration in Spring Boot

Spring Data MongoDB provides `MongoTemplate` and repositories backed by a `MongoDatabaseFactory`. With Spring Boot and the appropriate MongoDB starter, usually passing the URI is all that is needed; Boot configures `MongoClient` and supporting components.

**Spring Boot version note:**

| Version | URI Property | Equivalent Environment Variable for Direct Binding |
| --- | --- | --- |
| Spring Boot **3.x** | `spring.data.mongodb.uri` | `SPRING_DATA_MONGODB_URI` |
| Spring Boot **4.x** | `spring.mongodb.uri` | `SPRING_MONGODB_URI` |

Spring Boot 4 moved the prefix of many MongoDB connection properties from `spring.data.mongodb.*` to `spring.mongodb.*`; some **Spring Data-specific** properties such as `spring.data.mongodb.auto-index-creation` retain the older prefix. When upgrading, always verify which configuration properties are actually loaded, especially deployment environment variables.

### 5.1. Spring Boot 4.x: `application.yml`

~~~yaml
spring:
  mongodb:
    # MONGODB_URI is provided by the runtime environment or secret manager.
    uri: ${MONGODB_URI}
~~~

Illustrative environment variable value:

~~~text
MONGODB_URI=mongodb://inventory_app:<ENCODED_PASSWORD>@db.example.net:27017/inventory_db?authSource=admin&tls=true
~~~

Do not store strings containing real passwords in version-controlled configuration files. The application runtime must provide `MONGODB_URI` per environment.

### 5.2. Spring Boot 3.x: `application.yml`

~~~yaml
spring:
  data:
    mongodb:
      uri: ${MONGODB_URI}
~~~

Only the **Spring Boot property path** differs; the MongoDB URI syntax is unchanged between both examples. Avoid declaring both a URI and separate host/database/username/password properties at the same time unless intentional, as doing so can cause confusion about which configuration source takes effect.

If you want to use an environment variable to bind directly to Boot's property, use the exact name from the table above. If your app uses `uri: ${MONGODB_URI}` as in both examples, the `MONGODB_URI` variable works identically across both versions.

### 5.3. Selecting a Database When Not Embedded in the URI

The clearest approach is putting the application database directly after `/` in the URI:

~~~text
mongodb://inventory_app:<ENCODED_PASSWORD>@db.example.net:27017/inventory_db?authSource=admin&tls=true
~~~

If the URI has no database path, you can configure the application database **separately** via `spring.mongodb.database` (Boot 4.x) or `spring.data.mongodb.database` (Boot 3.x), depending on version:

~~~yaml
# Boot 4.x example - illustrates separate database configuration only.
spring:
  mongodb:
    uri: ${MONGODB_SERVER_URI}
    database: inventory_db
~~~

`MONGODB_SERVER_URI` must include an appropriate authentication database, for example `mongodb://inventory_app:<ENCODED_PASSWORD>@db.example.net:27017/?authSource=admin&tls=true`. When the database is already in the URI, stick to **one consistent configuration source** so operators are never confused about which database is active.

### 5.4. Verifying Connectivity with `MongoTemplate`

Example service using the synchronous API; imports are from Spring Data MongoDB and MongoDB BSON:

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;

@Service
public class MongoConnectionCheck {
    private final MongoTemplate mongoTemplate;

    public MongoConnectionCheck(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public boolean canReachServer() {
        Document result = mongoTemplate.executeCommand(new Document("ping", 1));
        return result.getDouble("ok") == 1.0;
    }
}
~~~

The `ping` command verifies network reachability to the server; it **does not prove** the user has read/write permissions on business collections. To verify authorization, test `find`/`insert`/`delete` on a test collection in `inventory_db` using the application account, then clean up the test data.

`MongoRepository` also uses the Boot-configured `MongoClient`/database; repositories target collections according to `@Document(collection = "...")`. When multiple MongoDB databases or clusters are required within a single application, you must explicitly declare separate `MongoDatabaseFactory`, `MongoTemplate`, and repository configurations; that is an advanced setup beyond a single default connection.

### 5.5. Reactive Access

With the Spring Data MongoDB Reactive dependency, `ReactiveMongoTemplate` and `ReactiveMongoRepository` use the reactive driver and return `Mono` / `Flux`. The URI format, `authSource`, and security rules **remain identical**; the difference lies in asynchronous execution.

~~~java
import org.bson.Document;
import reactor.core.publisher.Mono;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;

// Inside a component that has reactiveMongoTemplate injected:
Mono<Boolean> reachable = reactiveMongoTemplate
    .executeCommand(new Document("ping", 1))
    .map(result -> result.getDouble("ok") == 1.0);
~~~

Never call `block()` on a reactive event-loop thread. Whether the application actually connects is only verified when the publisher is **subscribed to** within a reactive pipeline.

## 6. Verifying Configuration with `mongosh`

When isolating issues, test directly with `mongosh` from a **host/container sharing the same network path** as the application. To avoid exposing passwords in command-line arguments, pass a URI without credentials and use the password prompt flag:

~~~bash
mongosh "mongodb://db.example.net:27017/inventory_db?authSource=admin&tls=true" --username inventory_app --password
~~~

This command assumes the target server has valid TLS and the user was created in `admin`. `mongosh` will ask for the password via an interactive prompt.

After logging in, run checks on the application database:

~~~javascript
// Currently selected database.
db.getName(); // "inventory_db"

// Verify server responds.
db.runCommand({ ping: 1 });

// Verify which identity the server authenticated.
db.runCommand({ connectionStatus: 1 }).authInfo.authenticatedUsers;

// Use a dedicated test collection only to avoid touching real data.
db.setup004_connection_probe.insertOne({ _id: "setup004-smoke", ok: true });
db.setup004_connection_probe.findOne({ _id: "setup004-smoke" });
db.setup004_connection_probe.deleteOne({ _id: "setup004-smoke" });
~~~

These operations require proper roles in `inventory_db`; `ping` succeeding while `insertOne` fails with `not authorized` signals missing privileges, not a network failure. After deleting the test document, the empty test collection may still remain; only drop it if permitted and certain it is the dedicated test collection.

In practice, a sensible troubleshooting order is **verify URI and network → authenticate user → confirm application database → check collection permissions → verify Spring Boot loads the right property**.

## 7. Common Errors

| Symptom | Likely Cause | Resolution |
| --- | --- | --- |
| `Authentication failed`, error code 18 / `MongoSecurityException` | Wrong user/password, wrong `authSource`, unencoded special characters in password | Confirm which database holds the user, test login with `mongosh`, properly encode password |
| `not authorized on inventory_db` | Login succeeded, but role is missing on application database | Check assigned roles; have admin grant least-privilege access |
| Reads return empty despite successful connection | URI points to wrong database or collection, or environment defaults to `test` database | Check `/database` in URI; compare `MongoTemplate`, `@Document`, and active profile config |
| `MongoTimeoutException` / server selection timeout | Host/port unreachable, firewall, replica set advertising unreachable hostnames | Check DNS, network/containers, port, IP allowlist, and member addresses |
| Error resolving `mongodb+srv` | Invalid DNS SRV/TXT records or blocked DNS | Verify hostname and DNS resolution from the app's runtime environment |
| SSL handshake / certificate error | TLS not enabled, untrusted CA, or hostname mismatch in certificate | Check `tls=true`, truststore/SSL bundle, and server certificate |
| Works in `mongosh`, but Boot connects to wrong server | Wrong property name across Boot 3 ↔ Boot 4, profile/env not loaded, custom `MongoClient` overriding config | Check `spring.data.mongodb.uri` vs `spring.mongodb.uri`; inspect effective config with secrets masked |
| URI misparsed around `@`, `#`, `?` | Unencoded credentials | Percent-encode username/password individually before building URI |
| Connection to `localhost` fails inside container | `localhost` refers to the app container itself | Use the MongoDB service hostname on the container network or infrastructure hostname |

Never expose raw URIs containing credentials in stack traces, tickets, or screenshots. If your application manually defines `MongoClient` or `MongoClientSettings`, check whether it overrides Spring Boot auto-configuration.

## 8. Practical Setup Workflow

Suppose you need to deploy an inventory service using Spring Data MongoDB:

1. **Choose the MongoDB endpoint** per environment (local/staging/production); enable TLS and verify network reachability.
2. **Choose the application database** `inventory_db` and standardize collection naming.
3. **Create a dedicated user** `inventory_app` in `admin` (or designated auth location) and grant `readWrite` strictly on `inventory_db`.
4. **Construct the URI** with `/inventory_db`, `authSource=admin`, percent-encoded password, and required TLS options.
5. **Provide the URI as a secret**, configuring `application.yml` for Spring Boot 3.x or 4.x accordingly.
6. **Verify with the application account** via `mongosh` and a controlled CRUD test; then verify connectivity from the app via `MongoTemplate`/repositories.
7. **Monitor errors** without logging passwords. In production, establish credential rotation plans and strict secret access controls.

Relationship diagram:

~~~mermaid
flowchart LR
  A["Spring Data MongoDB<br/>MongoTemplate / Repository"] --> B["MongoClient<br/>reads URI and TLS"]
  B --> C["MongoDB server / cluster"]
  C --> D["Authenticate user<br/>authSource = admin"]
  D --> E["Authorize roles<br/>readWrite on inventory_db"]
  E --> F["Collection CRUD<br/>in inventory_db"]
~~~

## 9. Self-Check Exercises

**Exercise 1 — Dissect a URI.** Given the URI:

~~~text
mongodb://catalog_app:Example%402026@mongo.internal:27017/catalog_db?authSource=admin&tls=true
~~~

Identify the host, port, application database, authentication database, username, pre-encoded password, and transport security option.

**Answer:** host `mongo.internal`, port `27017`, database `catalog_db`, `authSource=admin`, username `catalog_app`, example password `Example@2026`, `tls=true`. This is an illustrative URI only; never use these details as real credentials.

**Exercise 2 — Diagnose an error.** User `billing_app` was created in `admin` and granted `readWrite` on `billing_db`. The app uses:

~~~text
mongodb://billing_app:<ENCODED_PASSWORD>@mongo.internal:27017/billing_db
~~~

Why might it throw `Authentication failed`? **Answer:** The URI defaults authentication to `billing_db`, while the user was created in `admin`. Fix the URI to `.../billing_db?authSource=admin`, keeping `billing_db` as the CRUD database.

**Exercise 3 — Upgrade check.** An application migrates from Boot 3 to Boot 4; the existing deployment sets `SPRING_DATA_MONGODB_URI` and has no `uri: ${MONGODB_URI}` in YAML. Identify the required change. **Answer:** Switch to the new property `spring.mongodb.uri` or direct binding variable `SPRING_MONGODB_URI`; review other MongoDB properties whose names changed during the upgrade.

## References

- [MongoDB Manual — Connection String Formats](https://www.mongodb.com/docs/manual/reference/connection-string-formats/): `mongodb://`, `mongodb+srv://`, URI components, default authentication database.
- [MongoDB Manual — Connection String Options](https://www.mongodb.com/docs/manual/reference/connection-string-options/): `authSource`, TLS, replica set, and other parameters.
- [MongoDB Manual — `db.createUser()`](https://www.mongodb.com/docs/manual/reference/method/db.createUser/): creating users and assigning roles on self-managed MongoDB.
- [Spring Boot 3.4 — Working with NoSQL Technologies](https://docs.spring.io/spring-boot/3.4/reference/data/nosql.html): `spring.data.mongodb.uri` and MongoDB configuration in Spring Boot 3.
- [Spring Boot 4 — Working with NoSQL Technologies](https://docs.spring.io/spring-boot/4.0/reference/data/nosql.html): `spring.mongodb.uri` and auto-configuration mechanism.
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): renamed MongoDB properties when upgrading to Boot 4.
