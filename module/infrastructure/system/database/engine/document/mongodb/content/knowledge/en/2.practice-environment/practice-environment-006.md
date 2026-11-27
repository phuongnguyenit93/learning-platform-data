# Reading MongoDB Connection Strings: `mongodb://`, `mongodb+srv://`, and URI Options

A connection string is an address paired with configuration parameters so an application or tool like `mongosh` can locate MongoDB, authenticate, select appropriate servers, and establish communication behavior. Reading a URI accurately lets you distinguish network failures, certificate issues, credential errors, and cluster configuration problems without resorting to blind trial-and-error.

In this lesson, we use two URI formats: `mongodb://` (listing hosts directly) and `mongodb+srv://` (discovering hosts via DNS). Hostnames such as `example.net` in examples are purely illustrative; replace them with the actual addresses of your practice environment.

## 1. General Structure of a Connection String

### Standard Format: `mongodb://`

```text
mongodb://[username:password@]host1[:port1][,host2[:port2],...]/[database][?option1=value1&option2=value2]
└─scheme─┘ └────user info────┘ └──────────hosts───────────────┘ └─path──┘ └──────────query───────────────┘
```

| Component | Meaning | Example |
| --- | --- | --- |
| `mongodb://` | Standard connection scheme; declares hosts directly | `mongodb://` |
| `username:password@` | Authentication credentials, optional if the server permits unauthenticated access | `reader:secret@` |
| `host:port` | MongoDB host address and TCP port; MongoDB's default port is `27017` | `localhost:27017` |
| `host1,host2,...` list | Multiple seed host addresses, commonly used to discover a replica set | `db1:27017,db2:27017` |
| `/database` | Default database name in the URI; may also act as default authentication source if `authSource` is unset | `/inventory` |
| `?key=value&...` | Connection options as key–value pairs separated by `&` | `?tls=true&appName=demo` |

Reading an illustrative URI:

```text
mongodb://reporter:p%40ss%3A2026@db1.example.net:27017/sales?authSource=admin&tls=true&appName=report-lab
```

- **Scheme:** `mongodb://`.
- **Account:** `reporter`; password in the URI is `p%40ss%3A2026`, which decodes to `p@ss:2026`.
- **Target:** host `db1.example.net`, port `27017`.
- **Database path:** `sales`.
- **Options:** authenticate against `admin`, enable TLS, set application name `report-lab`.

Pay attention to the difference between **database path** and **authentication database**. For example, `/sales?authSource=admin` targets `sales` for data operations while looking up user credentials in `admin`. Without `authSource`, for standard username/password authentication, MongoDB uses the path database as the authentication source; if the path specifies no database, it defaults to `admin`. Specialized mechanisms such as `MONGODB-X509` follow their own rules.

### DNS Seed List Format: `mongodb+srv://`

```text
mongodb+srv://[username:password@]hostname/[database][?option1=value1&option2=value2]
```

Example:

```text
mongodb+srv://appuser:<password>@cluster.example.net/catalog?retryWrites=true&w=majority
```

Here `<password>` is a placeholder to replace, **not** an actual password, and you must not keep the `<`/`>` angle brackets when using the URI. If the password contains special characters, encode them as shown in the next section.

With `mongodb+srv://`, the URI declares **only one hostname**, **no port**, and **no comma-separated host list**. The driver queries DNS SRV records (typically at `_mongodb._tcp.cluster.example.net`) to obtain server hosts and ports, and may also read certain settings from DNS TXT records. DNS must be properly configured for this, so you cannot arbitrarily turn `mongodb://localhost` into `mongodb+srv://localhost`.

## 2. Distinguishing `mongodb://` and `mongodb+srv://`

| Criterion | `mongodb://` | `mongodb+srv://` |
| --- | --- | --- |
| Target declaration | One or more `host[:port]` entries | A single hostname used for DNS SRV lookup |
| Host list source | Read directly from URI; driver may then discover topology | Read from SRV records; driver then discovers topology |
| Port in URI | Allowed; defaults to `27017` if omitted | Not allowed in URI |
| DNS TXT | Not used to fetch URI options | May supply certain supported options |
| Default TLS | Typically off unless requested by URI/config | Enabled by default unless explicitly overridden |
| Common use | Local MongoDB, self-managed hosts, replica sets with seed list | Clusters with DNS SRV configured, common on managed MongoDB services |

**Which format to choose?** For MongoDB running locally, start with `mongodb://localhost:27017`. For a cluster whose administrator or provider supplies a `mongodb+srv://` URI, use it as provided: the driver queries DNS and selects appropriate servers. Both formats can connect securely when configured with proper TLS and authentication.

The resolution flow can be simplified as:

```text
Parse URI
   |
   +-- mongodb:// ------> read hosts/ports from URI -----+
   |                                                      |
   +-- mongodb+srv:// --> query DNS SRV/TXT --------------+
                                                          |
                                          resolve TLS, auth, topology
                                                          |
                                          select server and open connection
                                                          |
                                          send command (ping, find, insert, ...)
```

## 3. How to Read Common URIs

### 3.1. Local MongoDB Without Authentication

```text
mongodb://localhost:27017
```

A URI for MongoDB running on the same machine as the client program. Absence of `username:password@` means **the URI supplies no login credentials**, not that every MongoDB instance accepts anonymous access.

### 3.2. Specifying Database and Authentication Source

```text
mongodb://student:demoPass@localhost:27017/lab?authSource=admin
```

The application operates on `lab`, while user `student` authenticates against `admin`. If the user was actually created in `lab`, you must use `authSource=lab` (or matching configuration); changing the database path randomly will not fix authentication failures.

### 3.3. Multi-Server Replica Set

```text
mongodb://db1.example.net:27017,db2.example.net:27017,db3.example.net:27017/orders?replicaSet=rs0&tls=true
```

The three hosts are **discovery seeds**, not three independent connections the application rotates manually. The driver fetches topology from the servers, identifies primary/secondaries, and routes operations based on read/write settings. `replicaSet=rs0` enforces the expected replica set name; hostnames advertised by the cluster must also be resolvable and reachable from the client.

### 3.4. Cluster Using DNS SRV

```text
mongodb+srv://reader:encodedPassword@cluster.example.net/analytics?authSource=admin&readPreference=secondaryPreferred
```

The driver queries DNS to locate cluster members. `readPreference=secondaryPreferred` prefers reading from a secondary when available while falling back to the primary; data read from secondaries may lag behind recent writes due to replication lag. Do not enable this option merely to "speed things up" if your logic needs to read immediately after writes.

## 4. Encoding Special Characters in Username/Password

URI delimiter characters (`@`, `:`, `/`, `?`, `#`, `%`, ...) must be **percent-encoded** when they appear as literal characters in a username or password. Otherwise, the parser may misinterpret part of the password as the host, path, or query string.

| Literal Character | Value Written in URI |
| --- | --- |
| `@` | `%40` |
| `:` | `%3A` |
| `/` | `%2F` |
| `?` | `%3F` |
| `#` | `%23` |
| `%` | `%25` |
| `&` | `%26` |
| `+` | `%2B` |

For example, if the raw password is `a@b:c/42`, the password segment in the URI must be `a%40b%3Ac%2F42`:

```text
mongodb://student:a%40b%3Ac%2F42@localhost:27017/lab?authSource=admin
```

Only encode the **credential values** being passed—never encode `://`, the `@` separating userinfo from host, or `&` separating options. A character already encoded as `%40` must not be double-encoded into `%2540` if you want it decoded back to `@`.

If the hostname is an IPv6 literal, wrap it in square brackets to distinguish colons inside the address from the colon before the port, for example:

```text
mongodb://[::1]:27017/lab
```

**Security:** Never put URIs containing real passwords into Git, public READMEs, terminal screenshots, or logs. Load them from environment variables, a secret store, or runtime secret configuration; redact usernames, passwords, and any sensitive details before sharing error reports.

## 5. Key URI Option Groups

Options follow `?`; multiple options are separated by `&`. Example:

```text
mongodb://localhost:27017/lab?appName=mongo-lab&serverSelectionTimeoutMS=5000&maxPoolSize=30
```

### 5.1. Authentication and Transport Encryption

| Option | Effect | Example |
| --- | --- | --- |
| `authSource` | Database holding authentication records for standard username/password auth | `authSource=admin` |
| `authMechanism` | Explicitly selects an authentication mechanism; e.g., SCRAM | `authMechanism=SCRAM-SHA-256` |
| `tls` | Enables/disables TLS for connections; `ssl` is a legacy alias | `tls=true` |
| `tlsCAFile` | Path to trusted CA file, supported depending on driver/tool | `tlsCAFile=/path/to/ca.pem` |
| `appName` | Sends an application name in connection metadata for observability | `appName=order-service` |

With `mongodb+srv://`, TLS is enabled by default unless overridden. With `mongodb://`, set `tls=true` when connecting to servers configured with TLS, especially across untrusted networks. Some drivers support client certificates, handshake timeouts, and TLS settings via dedicated configuration objects rather than putting everything in the URI; consult the documentation for your driver version.

Never use `tlsAllowInvalidCertificates=true`, `tlsAllowInvalidHostnames=true`, or `tlsInsecure=true` as a "quick fix" for certificate errors. Those flags weaken server identity verification; fix the certificate, CA trust, or hostname alignment instead.

### 5.2. Cluster Identity and Connection Routing

| Option | Effect | Notes |
| --- | --- | --- |
| `replicaSet` | Specifies the expected replica set name | Must match the actual replica set name |
| `directConnection` | Forces the driver to talk directly to a single server without cluster discovery | Use only intentionally, typically with a single host |
| `loadBalanced` | Enables load-balanced topology mode when supported by the server/endpoint | Not a replacement for standard replica set setups |
| `srvServiceName` | Overrides the DNS service name used in SRV lookups if supported by the driver | Mainly for specialized SRV setups |

For instance, `directConnection=true` can be helpful when inspecting an isolated MongoDB node in a lab. If mistakenly enabled against a multi-node replica set, the application may fail to locate a new primary after topology changes.

### 5.3. Read and Write Behavior

| Option | Effect | Example |
| --- | --- | --- |
| `readPreference` | Selects server preference for reads: `primary`, `primaryPreferred`, `secondary`, `secondaryPreferred`, `nearest` | `readPreference=primary` |
| `readConcernLevel` | Consistency/visibility guarantee for read data, e.g., `local`, `majority` | `readConcernLevel=majority` |
| `w` | Write concern: acknowledgment level for writes, e.g., `1`, `majority` | `w=majority` |
| `wTimeoutMS` | Time limit for satisfying write concern | `wTimeoutMS=5000` |
| `retryWrites` | Lets the driver automatically retry eligible write operations on retryable errors | `retryWrites=true` |
| `retryReads` | Enables retrying eligible read operations | `retryReads=true` |

`w=majority` only governs write acknowledgment across the replica set; it does not by itself guarantee every read immediately sees the latest write. `readPreference`, `readConcern`, and `writeConcern` control distinct dimensions of distributed behavior. Moreover, automatic retries are bounded by operation type, server support, and driver version.

### 5.4. Connection Pool and Timeouts

| Option | Effect | Unit |
| --- | --- | --- |
| `maxPoolSize` | Maximum number of connections in a pool per server | Connection count |
| `minPoolSize` | Minimum number of connections the pool tries to maintain | Connection count |
| `maxConnecting` | Limits simultaneous connection establishments in a pool (if supported by driver) | Connection count |
| `waitQueueTimeoutMS` | Maximum time waiting to check out a connection from the pool (if supported by driver) | Milliseconds |
| `serverSelectionTimeoutMS` | Time window to find a suitable server for an operation | Milliseconds |
| `connectTimeoutMS` | Time limit to establish a network connection | Milliseconds |
| `socketTimeoutMS` | Wait limit for socket network read/write activity (exact behavior depends on driver) | Milliseconds |

Three frequently confused timeouts:

- **Server selection timeout:** the driver could not find a node eligible to serve the request.
- **Connect timeout:** failed to finish opening the TCP connection to the chosen node within the allowed window.
- **Socket timeout:** the connection was open, but a network operation failed to finish in time.

Setting timeouts too low triggers spurious failures on brief network jitter; setting them too high prolongs request stalls. Tune values to your environment and application SLAs. Connection pools are normally held by a shared `MongoClient` rather than creating a new client per query.

## 6. Understanding DNS SRV and TXT in Practice

Suppose the URI is:

```text
mongodb+srv://user:password@cluster.example.net/shop?retryWrites=true
```

The driver looks up records corresponding to the MongoDB service name, such as:

```text
_mongodb._tcp.cluster.example.net.  SRV  0 0 27017 db-a.example.net.
_mongodb._tcp.cluster.example.net.  SRV  0 0 27017 db-b.example.net.
_mongodb._tcp.cluster.example.net.  SRV  0 0 27017 db-c.example.net.
```

This is purely illustrative DNS data. The driver uses hostnames/ports from the SRV records to seed cluster discovery; a TXT record on the root hostname can supply a supported subset of options such as `authSource` or `replicaSet`. Drivers enforce SRV DNS validation constraints; arbitrary TXT records do not automatically become valid options.

Practical consequences:

1. The client machine must be able to resolve DNS SRV/TXT records, not just standard A/AAAA records.
2. Hostnames returned by SRV records must be reachable from the application's network.
3. Domain names, CAs, and certificates must match the TLS configuration.
4. Options written directly in the URI are merged with DNS options according to driver rules; inspect for conflicts if unexpected behavior occurs.

If `mongodb://host:27017` works while `mongodb+srv://host` fails, check SRV/TXT resolution and syntax restrictions before changing user credentials.

## 7. Practicing Connections with `mongosh` and Java

### 7.1. Testing Connection from `mongosh`

Local connection:

```bash
mongosh "mongodb://localhost:27017"
```

Inside the shell:

```javascript
db.adminCommand({ ping: 1 })
```

A response with `ok: 1` confirms the server processed `ping`. It does not prove the account can read/write every collection; test operations specifically according to your application's permissions.

For URIs containing sensitive credentials, prefer passing them via environment variables or your machine's secret mechanism to avoid saving passwords in shell command history.

### 7.2. Using the MongoDB Java Sync Driver

The example below reads the URI and database name from environment variables, creates a client, runs `ping`, and closes resources:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public class MongoConnectionExample {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Missing MONGODB_URI");
        }

        String databaseName = System.getenv().getOrDefault("MONGODB_DATABASE", "lab");

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database = client.getDatabase(databaseName);
            Document result = database.runCommand(new Document("ping", 1));
            System.out.println("MongoDB ping: " + result.get("ok"));
        }
    }
}
```

Add a compatible version of `mongodb-driver-sync` to your application build. Calling `MongoClients.create(uri)` constructs the client configuration, while network I/O may only occur when executing an operation like `ping`; thus, constructing the client object alone does not prove the URI can connect.

In long-running services, reuse a single `MongoClient` across the application's lifetime because it manages connection pooling and is thread-safe; close it on shutdown. The `try-with-resources` pattern above suits short diagnostic programs.

## 8. Failure Scenarios and How to Isolate Them

| Symptom | Possibilities to Check | Sensible Diagnostic Step |
| --- | --- | --- |
| `Invalid connection string` or URI parse error | Missing `/`, misplaced `?`/`&`, unencoded password characters, `mongodb+srv` with port/multiple hosts | Break URI into scheme, userinfo, host, path, and query; check encoding of each value |
| DNS SRV not found | Domain lacks `_mongodb._tcp` records or DNS blocks the query | Query DNS SRV/TXT records and inspect the resolver from the actual runtime environment |
| `ServerSelectionTimeout` | No eligible node found; wrong host/port, firewall, IP allowlist, replica set mismatch, or TLS | Read full driver exception details; verify network reachability to cluster-advertised hosts |
| `Authentication failed` | Wrong username/password, wrong `authSource`, mismatched auth mechanism | Verify where the user was created and how special characters in password are encoded |
| TLS handshake/certificate error | TLS disabled/mismatched, untrusted CA, hostname mismatch on cert | Verify TLS mode and certificate chain against the target hostname |
| Write error `not primary` or no writable server | Topology change, connected to secondary, inappropriate `directConnection` | Inspect node list, `replicaSet`, and primary discovery behavior |
| Connected, but missing data or permission denied | Wrong database/collection selected or insufficient roles | Check active database and user roles; do not confuse target DB with `authSource` |

In containerized environments, `localhost` always refers to **the container or machine running the client itself**, never another MongoDB container. Use the Docker/network service name or an address actually reachable by the client. Similarly, if a replica set advertises internal hostnames, an external client might reach a seed host yet fail to reach discovered members.

## 9. URI Reading and Analysis Exercises

**Exercise 1.** Analyze:

```text
mongodb://user:pa%23ss@mongo.example.net:27018/training?authSource=admin&tls=true
```

Questions: what are the host and port, what is the decoded password, and are the database path and authentication database the same?

**Answer:** host `mongo.example.net`, port `27018`; decoded password is `pa#ss`; database path is `training` while authentication database is `admin`, so they are not the same.

**Exercise 2.** Spot the error in this URI:

```text
mongodb+srv://db1.example.net:27017,db2.example.net:27017/catalog
```

**Answer:** `mongodb+srv://` accepts only a single hostname and no ports. To list `db1` and `db2` directly, use `mongodb://`. To use SRV, provide one hostname with properly configured DNS SRV/TXT records.

**Exercise 3.** Where might these two URIs differ?

```text
mongodb://student:secret@localhost:27017/lab
mongodb://student:secret@localhost:27017/lab?authSource=admin
```

**Answer:** both share the `lab` database path, but the first normally authenticates `student` against `lab` while the second authenticates against `admin`. Which URI works depends on which database holds the user record.

## 10. Key Takeaways for Configuring Practice Environments

- Parse URIs in order: **scheme → credentials → hosts → database path → options**; never infer access permissions solely from the database name.
- `mongodb://` takes a host/port list; `mongodb+srv://` uses DNS SRV/TXT, a single hostname, and TLS by default.
- Percent-encode special characters in username/password without accidentally encoding URI delimiters.
- Verify `authSource`, TLS, `replicaSet`, and reachability of cluster-advertised hostnames before tuning timeouts.
- Keep URIs containing secrets out of source code, reuse a properly pooled `MongoClient`, and verify connectivity with a real operation such as `ping`.

Reading each component systematically turns a connection string into a verifiable specification of **addressing**, **identity**, **security**, **routing**, and **driver behavior**.
