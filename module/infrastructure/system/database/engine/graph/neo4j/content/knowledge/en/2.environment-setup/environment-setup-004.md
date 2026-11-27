# Connection Ports, URIs, Bolt Protocol, and Browser Access

## 1. Objectives and Context

Neo4j is a database management system based on the **property graph** model: **nodes** represent entities, **relationships** represent directed links, and **properties** store their attributes. You interact with the graph using **Cypher**. Before studying indexes, constraints, paths, query tuning, data import, or integrating **Java Driver** and **Spring Data Neo4j**, you must first connect reliably to the **Neo4j DBMS**.

A very common mistake is opening the web interface on port `7474` while a Java application still reports it cannot connect. The reason is that the **UI address**, the **Driver query address**, the **transport protocol**, and **where the application is running** are separate factors.

By the end of this lesson, you will be able to:

1. Explain the roles of ports `7474`, `7473`, and `7687` and how to change them.
2. Read and choose the right URI among `bolt://`, `neo4j://`, `bolt+s://`, `neo4j+s://`, and TLS variants.
3. Open Neo4j Browser, connect, and verify the database with Cypher.
4. Distinguish `localhost` on the host machine, inside a Docker container, and on a remote client.
5. Configure URIs for Java/Spring Boot and troubleshoot port, DNS, routing, TLS, and authentication errors.

**Lesson scope:** Examples focus on a single local or containerized Neo4j DBMS, contrasted with Neo4j AuraDB. Ports shown are **common default configuration values**; real environments may change ports, listen interfaces, security protocols, or DNS.

## 2. What Does a Neo4j Connection Actually Consist Of?

To connect, you need to know:

- **Host or IP**: the machine/endpoint running Neo4j, such as `localhost`, `127.0.0.1`, `neo4j` inside a Docker network, or a hostname provided by AuraDB.
- **Port**: the TCP port of the corresponding service.
- **Protocol and security**: opening the HTTP/HTTPS UI or using Bolt/Neo4j with or without TLS.
- **Credentials**: usually username and password; other authentication methods depend on deployment.
- **Target database**: typically `neo4j` on a fresh practice instance, though it can have another name.

When using the Java Driver, all of these parts must align **at the same time**. Connecting to the right port with the wrong TLS scheme still fails; connecting to the right hostname and port with the wrong password also prevents querying.

### 2.1. Port diagram in a local environment

~~~mermaid
flowchart LR
    B["Web browser"] -->|"HTTP :7474 loads UI"| H["HTTP connector"]
    B -->|"Bolt/WebSocket :7687 for queries"| P["Bolt connector"]
    J["Java Driver / cypher-shell"] -->|"Bolt/TCP :7687"| P
    H --> D["Neo4j DBMS"]
    P --> D
    D --> G[("Graph database<br/>node - relationship - property")]
~~~

**Distinguish two steps:**

1. The browser loads **Neo4j Browser** from the HTTP endpoint.
2. The Neo4j Browser app then opens a database connection over **Bolt**, usually via WebSocket in the browser. Therefore, **loading the Browser page does not prove the Bolt port is working**.

Java Driver and `cypher-shell` speak Bolt; **do not** put `http://localhost:7474` into the Java Driver URI configuration.

## 3. Default Ports and Use Cases

| Common port | Protocol | Role | How to access |
| --- | --- | --- | --- |
| **7474/TCP** | **HTTP** | Serves Neo4j Browser and the HTTP endpoint if enabled | `http://localhost:7474/browser/` or `http://localhost:7474` |
| **7473/TCP** | **HTTPS** | HTTP over TLS, used only when the **HTTPS connector is enabled and certificates are configured** | `https://hostname:7473/browser/` |
| **7687/TCP** | **Bolt** | Query connections from Java Driver, Spring Data Neo4j, `cypher-shell`, and compatible tools | `bolt://localhost:7687` or appropriate `neo4j://`, `+s` URIs |

Notes:

- **7473 is not enabled by default** in every installation. HTTPS requires configuring TLS/SSL per version and environment.
- **7687** is the default Bolt port locally, **not HTTP**. Entering `http://localhost:7687` in the browser address bar will not open Neo4j Browser.
- **443/TCP** is typically web/proxy HTTPS and **does not automatically replace 7687** for Bolt. For AuraDB, use the **exact URI provided by Aura Console**, which typically connects via TLS to the Bolt service on the URI's default port.
- These are **listener ports** inside the Neo4j process; Docker may map a different **host port** to the container port.
- Do not expose administrative or internal ports externally just to run Cypher queries. Additional port lists depend on edition, topology, and deployment version.

## 4. Neo4j and Bolt URIs: Which Scheme Should You Choose?

A **URI** consists of at least a scheme and hostname, and optionally a port:

~~~text
scheme://hostname:port
~~~

Examples:

~~~text
bolt://localhost:7687
neo4j://localhost:7687
neo4j+s://example123.databases.neo4j.io
~~~

`example123` is only an **illustrative instance ID**. URIs must be replaced with your actual environment's endpoint.

### 4.1. Common schemes

| Scheme | Connection type | TLS / certificate | When to use |
| --- | --- | --- | --- |
| `bolt://` | Direct Bolt to specified host/port | Does not require TLS by scheme | Local dev with a single DBMS, connections in controlled networks |
| `neo4j://` | Bolt with **routing**: Driver receives appropriate server info for the session | Does not require TLS by scheme | Connecting to DBMS/topologies requiring routing, when TLS is configured appropriately |
| `bolt+s://` | Direct Bolt | **TLS**, verifies certificate against system trust store | Direct Bolt endpoint with a trusted CA certificate |
| `neo4j+s://` | Routing over Bolt | **TLS**, verifies certificate | **AuraDB** and deployments with routing + standard TLS |
| `bolt+ssc://` | Direct Bolt | TLS, but **accepts self-signed certificates / skips standard CA chain verification** | Tightly controlled testing; not recommended for public/production connections |
| `neo4j+ssc://` | Routing over Bolt | TLS with matching self-signed trust policy | Labs with routing and self-signed certs when risks are understood |

**Quick selection rules:**

- Local Neo4j, single instance, TLS not configured: **`bolt://localhost:7687`**.
- Managed Neo4j via **AuraDB**: **`neo4j+s://...` URI copied from Aura Console**.
- Cluster, routing, or multi-server endpoint: use **`neo4j://` / `neo4j+s://`** matching infrastructure and security setup.
- Do not change `neo4j+s://` to `bolt://` or `bolt+ssc://` just to bypass certificate errors. Check DNS, TLS, certificates, and endpoint configuration instead.

### 4.2. How do direct Bolt and routing differ?

**`bolt://`** instructs the Driver to open a connection directly to the specified address. For standalone Neo4j on a laptop, this is simple and easy to debug.

**`neo4j://`** enables the Driver to perform **routing discovery**: asking the server for appropriate read/write addresses and opening connections to those advertised addresses. In multi-server systems, this mechanism is essential for routing to each server's proper role.

~~~mermaid
flowchart TD
    A["App uses neo4j:// or neo4j+s://"] --> B["Connect to seed address"]
    B --> C["Receive routing table"]
    C --> D["Driver connects to appropriate advertised address"]
    D --> E["Send Cypher in session / transaction"]
~~~

**Practical consequence:** a TCP connection to the seed host may succeed, yet if the server advertises an address **unreachable from the application**, a Driver using a routing scheme will still fail. This commonly happens when the DBMS sits behind NAT, Docker, a reverse proxy, or across multiple networks.

Not every Neo4j Community/standalone setup needs routing. Local practice labs can use `bolt://` to avoid unnecessary complexity.

### 4.3. Understanding `+s` and `+ssc`

TLS encrypts traffic and helps the client verify the server when using trusted certificates.

- `+s`: requires **TLS** and verifies the server's certificate. If the certificate is invalid, the hostname mismatches, or the CA is untrusted, the connection should be rejected.
- `+ssc`: still encrypts with TLS but relaxes CA trust-chain verification; this makes the client more vulnerable to connecting to a spoofed server on untrusted networks.
- No security suffix: encryption depends on Driver/server configuration, typically **unencrypted** in local examples.

**The HTTPS connector certificate and the Bolt certificate are related configurations, not identical.** A server can serve Browser over HTTPS while Bolt does not yet have TLS configured. When accessing Browser remotely over HTTPS, browser security policies may block insecure WebSocket connections.

## 5. Distinguishing Addresses and Connection Scopes

### 5.1. `localhost` always refers to where the calling program runs

| Where the calling program runs | `localhost` points to | Typical Bolt URI |
| --- | --- | --- |
| Java app running directly on laptop, Neo4j ports published to host | **Laptop** | `bolt://localhost:7687` |
| Java app in **another container** on the same Compose network as service `neo4j` | **Java container**, not Neo4j | `bolt://neo4j:7687` |
| Java running on another VM/host | **Host running Java** | URI using reachable DNS/IP of the Neo4j host, per network/TLS policy |
| App connecting to AuraDB | Does not use localhost | `neo4j+s://<id>.databases.neo4j.io` provided by Aura |

`127.0.0.1` is the **IPv4** loopback address; `localhost` may resolve to IPv4 or IPv6 depending on the OS. When diagnosing a listener bound only to IPv4, testing `127.0.0.1` explicitly helps identify DNS/IPv6 differences.

### 5.2. Host port differs from container port

Example in Docker Compose:

~~~yaml
services:
  neo4j:
    image: neo4j:2026.10.2
    ports:
      - "127.0.0.1:7475:7474"
      - "127.0.0.1:7688:7687"
~~~

How to read `"127.0.0.1:7688:7687"`:

- **127.0.0.1**: published only on host loopback.
- **7688**: port called by **Java running on the host**.
- **7687**: Bolt port **inside the container**, used by apps on the same Docker network.

With this configuration:

~~~text
Browser on host:              http://localhost:7475/browser/
Java Driver on host:          bolt://localhost:7688
Java in same Compose network: bolt://neo4j:7687
~~~

Do not use `bolt://neo4j:7688` from a Java container in the same Compose network, because `7688` is the port published on the **host**, not the service's internal port.

### 5.3. Listen address and advertised address

Neo4j distinguishes:

- **Listen address**: the interface/port the DBMS opens to accept connections, e.g., `0.0.0.0:7687` inside a container.
- **Advertised address**: the address the DBMS announces to Drivers or other members for connections, especially critical for routing.

Some related Neo4j 5.x/2026.x configuration keys:

~~~properties
# Illustrative neo4j.conf example, DO NOT blindly copy to every machine
server.bolt.enabled=true
server.bolt.listen_address=:7687
server.http.enabled=true
server.http.listen_address=:7474
~~~

Settings like `server.default_listen_address` and `server.bolt.advertised_address` may need adjustment when running behind NAT/proxies or across multiple hosts; **do not** set the advertised address to `localhost` if applications run on other machines.

**Note:** `0.0.0.0` is for **binding/listening** on all IPv4 interfaces, not a valid hostname for remote clients to connect to. For remote networking, use a real DNS name/IP and design proper firewall, TLS, and authentication controls.

## 6. Hands-on Practice: Local Neo4j with Docker Compose

The following example merely creates a **test database** to observe ports and URIs. If you already have Neo4j running on the host, you can keep your existing DBMS and jump to Section 7.

Create `compose.yaml` in a dedicated lab directory:

~~~yaml
services:
  neo4j:
    image: neo4j:2026.10.2
    ports:
      - "127.0.0.1:7474:7474"
      - "127.0.0.1:7687:7687"
    environment:
      NEO4J_AUTH: "neo4j/${NEO4J_PASSWORD:?Set NEO4J_PASSWORD in .env}"
    volumes:
      - neo4j_data:/data

volumes:
  neo4j_data:
~~~

Create `.env` **in the same directory**:

~~~dotenv
NEO4J_PASSWORD=REPLACE_WITH_A_UNIQUE_STRONG_PASSWORD
~~~

Replace the placeholder with a real password dedicated to the **local lab** before starting. Do not commit `.env` to Git; add it to `.gitignore`. This setup illustrates protocols/ports, but `.env` is not a secret manager; for team/production projects use secret mechanisms like **Compose secrets** and the `NEO4J_AUTH_FILE` option supported by Neo4j Docker.

> **Important:** `NEO4J_AUTH` sets the **initial first-time password** for a database in an empty volume. If the `neo4j_data` volume already has data, editing the password in `.env` and restarting Compose **does not reset the old password**.

Validate and start:

~~~bash
docker compose config --quiet
docker compose up -d
docker compose ps
docker compose logs --tail=100 neo4j
~~~

Wait until the logs report the DBMS is ready. If `7474` or `7687` is already in use, change the **host ports** in `ports`, and update the URIs in the steps below accordingly. There is no need to change Neo4j's internal container ports just because of a host port conflict.

**Data is stored in the named volume `neo4j_data`**. Running `docker compose down` preserves the volume by default; `docker compose down -v` removes the project's volumes and can wipe all lab data.

## 7. Accessing via Neo4j Browser

**Neo4j Browser** is a web tool for writing Cypher, viewing results as tables or graphs, and running queries against the database. It is not a separate database itself.

### 7.1. Opening the UI and establishing a connection

1. For the local example in Section 6, open **`http://localhost:7474/browser/`** (or `http://localhost:7474` and follow any redirect).
2. On the Browser connection screen, use **URI** `bolt://localhost:7687` when TLS is not enabled locally.
3. Enter **username `neo4j`** and the password configured for that exact instance.
4. Click **Connect**. If Browser prompts to change the initial password, complete it and update the credentials used by your applications.
5. Run a verification query in the Cypher editor:

~~~cypher
RETURN 1 AS ok, datetime() AS serverTime;
~~~

Expected result includes `ok = 1` and the timestamp returned by the database. If the Browser page loads but connecting reports an error, check **Bolt URI, port, TLS, and credentials** before reinstalling Neo4j.

### 7.2. Identifying which DBMS you are connected to

When a machine has multiple instances or containers, never infer the server version from the Neo4j Browser version. Run:

~~~cypher
CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions, edition;
~~~

The output shows the **version and edition** of the DBMS handling the query. If multiple databases exist and you have appropriate privileges, check:

~~~cypher
SHOW DATABASES;
~~~

Permissions and multi-database capabilities depend on edition/account. Typically a fresh lab has a database named `neo4j`, but verify the actual name rather than assuming in every environment.

### 7.3. Testing reading a path in a property graph

~~~cypher
MERGE (a:Person {personId: 'neo4j-port-001'})
  ON CREATE SET a.name = 'An'
MERGE (b:Person {personId: 'neo4j-port-002'})
  ON CREATE SET b.name = 'Binh'
MERGE (a)-[:KNOWS]->(b)
RETURN a.name AS sourcePerson, b.name AS targetPerson;
~~~

~~~cypher
MATCH path =
  (:Person {personId: 'neo4j-port-001'})
  -[:KNOWS]->
  (:Person {personId: 'neo4j-port-002'})
RETURN path;
~~~

Neo4j Browser can render `path` as a graph with two `Person` nodes and the `KNOWS` relationship. `MERGE` helps avoid duplicates when re-running the lab; under concurrent write loads in real projects, you still need a **uniqueness constraint** on business keys and proper transaction design.

### 7.4. When Browser runs from another machine

Suppose Neo4j runs on host `db.example.internal`, and your laptop only opens the web UI remotely. For this to work:

1. The Browser HTTP/HTTPS endpoint must be **reachable** from your laptop over an authorized internal network/VPN/proxy.
2. The **Bolt endpoint** used by Browser must also be reachable from your laptop; serving HTML/JS over the HTTP port alone is not enough.
3. If the UI runs over **HTTPS**, the Bolt/WebSocket connection must comply with browser TLS policies; avoid **mixed content**.
4. When using `neo4j+s://`, the hostname, certificate, and **advertised address** (if routing) must be valid and reachable.

Do not expose Browser HTTP and Bolt directly to the Internet just for convenient remote access. For multi-user systems, evaluate VPN/reverse proxy, TLS, firewall, and access control first.

### 7.5. Neo4j AuraDB

AuraDB is managed Neo4j in the cloud. From **[Aura Console](https://console.neo4j.io/)**, select your instance, use **Query** or the provided query tool, and copy the **Connection URI**, username, and password. The URI typically looks like:

~~~text
neo4j+s://example123.databases.neo4j.io
~~~

Do not open `http://localhost:7474` if you only have AuraDB and have not installed Neo4j locally. With AuraDB, **copy the exact URI from the console** and use TLS as instructed; do not invent an HTTP address or DNS name from examples. If AuraDB Free pauses due to inactivity, check its status in Aura Console before diagnosing DNS/TLS.

## 8. Verifying with Cypher Shell and Java Driver

### 8.1. Cypher Shell: separating Browser UI from the Bolt connection

If `cypher-shell` is available in your environment, test connecting directly over Bolt:

~~~bash
# Run on host if cypher-shell is installed and Neo4j publishes port 7687
cypher-shell -a bolt://localhost:7687 -u neo4j -d neo4j
~~~

If using the Docker container from Section 6, you can run:

~~~bash
docker compose exec neo4j cypher-shell -a bolt://localhost:7687 -u neo4j -d neo4j
~~~

When prompted, enter the database password. **Do not pass the password directly to the `-p` flag** on shared machines when avoidable, as it can appear in shell history or process listings.

Once connected, run:

~~~cypher
RETURN 'Bolt OK' AS status;
~~~

If Cypher Shell connects while Browser still fails, focus on checking **Browser address, WebSocket, browser settings, TLS, and client-side config**. If both fail, inspect the DBMS, Bolt port, and authentication.

### 8.2. Configuring Spring Data Neo4j

In a Spring Boot application with compatible Neo4j/Spring Data Neo4j dependencies, use `application.properties`:

~~~properties
spring.neo4j.uri=${NEO4J_URI}
spring.neo4j.authentication.username=${NEO4J_USERNAME}
spring.neo4j.authentication.password=${NEO4J_PASSWORD}
~~~

Set environment variables according to where the application runs:

| Where does the Spring Boot app run? | Example `NEO4J_URI` |
| --- | --- |
| On host, Neo4j Docker publishes `7687` | `bolt://localhost:7687` |
| In another service on the same Compose network | `bolt://neo4j:7687` |
| On host, Neo4j Docker publishes host port `7688` | `bolt://localhost:7688` |
| Connecting to AuraDB | `neo4j+s://...` URI provided by Aura Console |

Credentials must belong to the **exact target DBMS/instance**; do not assume a Docker secret on the Neo4j service is shared with the Spring Boot application container.

### 8.3. Testing with Neo4j Java Driver

The Java snippet below illustrates connection logic (requires a **Neo4j Java Driver** dependency compatible with your application JDK and Neo4j Server version):

~~~java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;

public class Neo4jConnectionCheck {
    public static void main(String[] args) {
        String uri = System.getenv("NEO4J_URI");
        String username = System.getenv("NEO4J_USERNAME");
        String password = System.getenv("NEO4J_PASSWORD");

        try (Driver driver = GraphDatabase.driver(
                uri, AuthTokens.basic(username, password))) {
            driver.verifyConnectivity();
            try (Session session = driver.session()) {
                int value = session.run("RETURN 1 AS ok")
                                   .single().get("ok").asInt();
                System.out.println("Neo4j connected: " + value);
            }
        }
    }
}
~~~

Expected output: `Neo4j connected: 1`. In real applications, specify the target **database** explicitly when needed, manage the Driver across the application lifecycle, and add appropriate timeouts/retries. Never log passwords or hardcode them in source files.

**Version note:** The Java application's JVM and Neo4j Server's JVM can differ because they are two independent processes; what you must verify is the **Java Driver ↔ application JDK ↔ Neo4j Server** compatibility matrix.

## 9. Checking Ports and Troubleshooting by Layer

### 9.1. Step 1 — Is the DBMS running?

With Docker:

~~~bash
docker compose ps
docker compose logs --tail=100 neo4j
~~~

With Neo4j Desktop, check the DBMS status and logs in the UI. With a native Linux server, check service status and logs per your system, such as `systemctl status neo4j`.

**Container running does not guarantee the DBMS is ready for Cypher**: wait for startup, read logs, or run a test query.

### 9.2. Step 2 — Can the client reach the right port?

Check HTTP (Linux/macOS host):

~~~bash
curl -I http://127.0.0.1:7474
~~~

Receiving an HTTP response shows the HTTP connector is reachable, **not proof that Bolt works**.

Check Bolt TCP on Linux/macOS (if `nc` is installed):

~~~bash
nc -vz 127.0.0.1 7687
~~~

Check on Windows PowerShell:

~~~powershell
Test-NetConnection -ComputerName 127.0.0.1 -Port 7687
~~~

`TcpTestSucceeded = True` or `nc` reporting connected only proves **TCP reaches the port**; you still must verify protocol, TLS, user, and database.

If the host reports a port conflict, on Linux you can check:

~~~bash
ss -lnt
~~~

On Windows PowerShell:

~~~powershell
Get-NetTCPConnection -State Listen -LocalPort 7474,7687 -ErrorAction SilentlyContinue
~~~

If running inside an application container, the check must run **from that exact container/network**. A successful connection on the host does not prove another container can resolve the `neo4j` hostname.

### 9.3. Step 3 — Checking URI, routing, TLS, and authentication

| Symptom | Possible cause | Troubleshooting action |
| --- | --- | --- |
| `Connection refused` immediately when opening Driver | Wrong port, DBMS not listening, port not published, wrong hostname | Check process/logs and port from **where the program runs** |
| Browser loads page but fails to connect to database | HTTP OK but Bolt/WebSocket blocked, wrong URI or credentials | Try `cypher-shell`, verify `7687`, URI, and logs |
| Driver in container using `localhost` is refused | `localhost` points to the app container | On the same Compose network, use `bolt://neo4j:7687` |
| `Unable to retrieve routing information` or routing table error | Server advertises an unreachable address or misconfigured routing/network | Check DNS, **advertised address**, and use a routing URI matching topology |
| TLS handshake/certificate error | Wrong scheme, hostname mismatch, missing CA, endpoint lacks TLS | Use the official URI; verify certificate/CA and TLS config |
| `Authentication failed` | Wrong user/password, different instance, or password in old volume | Verify instance/port and credentials; change password with admin tools |
| `Database not found` / insufficient privileges | Wrong database name or access rights | Verify database name and account roles/privileges |
| `curl` to `http://localhost:7687` fails | Using HTTP against the Bolt port | Test TCP or use a **Bolt** tool such as `cypher-shell` |
| Java connects locally, fails from another machine | Host binds only `127.0.0.1`, firewall, or DNS | Design remote endpoint with proper networking and TLS; do not expose publicly |
| AuraDB stops connecting after inactivity | Instance paused, wrong URI, network blocks Bolt/TLS | Check Aura Console, official URI, and firewall/DNS |

**Effective troubleshooting order:** identify **where the client runs** → hostname/DNS → TCP port → HTTP vs. Bolt → routing/TLS → credentials → database/privileges → Cypher query.

## 10. Security When Exposing Ports and Connecting Remotely

A setup that works on a laptop is not secure enough when exposed to the Internet:

- Keep `7474`/`7687` **bound to loopback only** for local labs, e.g., `127.0.0.1:7687:7687` in Docker Compose.
- For remote connections, prefer a **private network/VPN or protected endpoint**, firewall rules restricting source access, and **TLS** with verified certificates.
- **Do not use `bolt+ssc://` to bypass certificate verification** over public networks. For AuraDB, always use the `neo4j+s://` URI provided by the service.
- Use strong passwords and least-privilege roles; administrative accounts should not be reused indiscriminately across all applications.
- Protect credentials in a secret manager or proper secret store; keep them out of Git, logs, lab docs, and command history.
- Only change `listen_address`/`advertised_address` after understanding **all client network paths**; advertising an internal address to external clients breaks routing.

## 11. Hands-on Exercises and Self-Check Questions

### Exercise 1 — Distinguishing the Two Ports

Local Neo4j is running; you can open `http://localhost:7474/browser/`, but the Java Driver uses `http://localhost:7474` and errors out. Identify the protocol mistake, choose the correct URI, and explain why the Browser UI still loads.

**Target answer:** Java Driver uses Bolt, e.g., `bolt://localhost:7687`; `7474` is the HTTP connector.

### Exercise 2 — Changing the Host Port in Compose

Replace `127.0.0.1:7687:7687` with `127.0.0.1:7688:7687`. Determine the URI when Java runs on the host and when Java runs in another container on the same Compose network. Test `cypher-shell` from host/container if available and compare results.

**Target answer:** host uses `bolt://localhost:7688`; container on the same network uses `bolt://neo4j:7687`.

### Exercise 3 — Analyzing TLS on AuraDB

An application was given `neo4j+s://example123.databases.neo4j.io`, but a developer changed it to `bolt://example123.databases.neo4j.io` to "reduce configuration errors." Point out the risks and list the proper diagnostic steps when TLS/certificate checks fail.

**Target answer:** keep the exact URI from Aura Console; check DNS, network/port, CA/certificate, and instance status—never disable TLS.

### Exercise 4 — Routing and Advertised Address

The client can reach the seed hostname over TCP, yet a Driver with `neo4j://` reports it cannot retrieve routing information or cannot connect to advertised servers. Explain why reaching the seed alone is insufficient and which address settings must be verified.

**Target answer:** inspect the routing table, advertised addresses, and reachability of those endpoints **from the client's network**.

### Completion Checklist

- [ ] Can distinguish HTTP `7474`, configurable HTTPS `7473`, and Bolt `7687`.
- [ ] Can distinguish Browser UI loading from the Bolt database connection.
- [ ] Choose `bolt://` for single local labs and `neo4j+s://` for AuraDB when appropriate.
- [ ] Know the difference between `+s` and `+ssc`, and never casually skip certificate verification.
- [ ] Know `localhost` inside a Java container does not point to the Neo4j container.
- [ ] Verified `CALL dbms.components()` and ran Cypher to read a path.
- [ ] Distinguish TCP port reachability from successful DBMS authentication.
- [ ] Know how to diagnose routing/advertised addresses and never expose ports publicly by convenience.

## 12. Official References

- [Neo4j Operations Manual — Configuration: Ports](https://neo4j.com/docs/operations-manual/current/configuration/ports/) — port roles and connections.
- [Neo4j Operations Manual — Connectors](https://neo4j.com/docs/operations-manual/current/configuration/connectors/) — HTTP, HTTPS, Bolt; listen/advertised addresses.
- [Neo4j Operations Manual — SSL framework](https://neo4j.com/docs/operations-manual/current/security/ssl-framework/) — certificates and TLS setup.
- [Neo4j Browser Manual](https://neo4j.com/docs/browser-manual/current/) — using Browser and connecting to databases.
- [Neo4j Java Driver — Connect to the database](https://neo4j.com/docs/java-manual/current/connect/) — Driver URIs, authentication, connectivity verification.
- [Neo4j Operations Manual — Docker](https://neo4j.com/docs/operations-manual/current/docker/introduction/) — publishing ports and running the DBMS.
- [Neo4j Aura — Connect to an instance](https://neo4j.com/docs/aura/getting-started/connect-instance/) — URIs and credentials for AuraDB.

**Key takeaway:** Read URIs from the perspective of **the connecting program**. Querying Neo4j requires getting **address, port, Bolt/routing scheme, TLS, credentials, and database** right simultaneously. Checking layer by layer finds issues much faster than guessing URIs at random.
