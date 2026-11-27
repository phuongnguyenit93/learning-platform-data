# Securing File Paths, URL Access, and Extension Configurations in Neo4j

## Learning objectives

After this lesson, you will be able to:

- Identify **trust boundaries** between a Java application, Neo4j Server, the filesystem, internal networks, and external data sources.
- Understand how `LOAD CSV` uses `file:///` addresses and remote URLs, as well as the role of the import directory, OS permissions, and security settings.
- Distinguish **core Cypher** from **APOC**, **Graph Data Science (GDS)** procedures, and third-party plugins; configure them following the principle of least privilege.
- Recognize risks of **path traversal**, symlinks, SSRF (*Server-Side Request Forgery*), HTTP redirects, credential leakage, and attack surface expansion via plugins.
- Propose safe ingestion patterns using vetted sources or the Java Driver without letting clients arbitrarily instruct the database to read files or URLs.
- Design testing, monitoring, and operational workflows to detect denied accesses, dangerous configuration changes, and ingestion incidents.

This lesson belongs to the **Security** chapter of the **DATABASE_ENGINE_GRAPH_NEO4J** module. Neo4j stores nodes, relationships, and properties using the **property graph** model, supports Cypher for graph reads/writes, and allows applications to use Java Driver, Spring Data Neo4j, plugins, or data-import tools. These extension mechanisms are useful, yet they also create a **path from a query to files on the server or services on the network**.

> **Scope:** Configuration examples are based on common setting names in Neo4j 5.x and modern releases. Setting names, defaults, procedure privilege models, and Aura support can vary by **version, edition, and deployment type**. Before applying, verify against the documentation and configuration reference for the **exact version in use**. Do not copy illustrative configurations to production without privilege assessment.

## 1. Threat model: who actually reads the file or calls the URL?

Consider an order management application:

~~~mermaid
flowchart LR
    U["HTTP client"] --> A["Spring Boot API"]
    A -->|Neo4j Java Driver| DB[("Neo4j Server")]
    DB -->|file:///| FS["Import directory / filesystem"]
    DB -->|https://| NET["Remote endpoint"]
    DB -->|CALL apoc.*| PL["APOC / plugin runtime"]
    PL --> FS
    PL --> NET
~~~

When the API sends a Cypher query containing `LOAD CSV FROM 'file:///customers.csv'`, the **Neo4j process** is the one reading the file: the path does not point to the Java Driver caller's laptop or a file in the Spring project directory. Similarly, when a procedure fetches JSON from a URL, the network request can originate from the **machine or container running Neo4j**. This is the core insight of the threat model.

| Asset to protect | Common attack path | Primary mitigation |
| --- | --- | --- |
| Config files, keys, backups, and files outside import | Read due to unrestricted paths or over-privileged plugins | Directory scoping, OS/container permissions, procedure allowlist |
| Internal endpoints and cloud metadata | Database abused to call user-controlled URLs (**SSRF**) | Disallow arbitrary URLs, egress firewall/proxy, authentication |
| Graph database | Malicious data import or out-of-scope Cypher writes | Narrow roles, validation, constraints, transactions |
| Credentials | URLs containing secrets, parameter logging, plugins reading configs | Secrets manager, redaction, minimal logging |
| Availability | Massive file imports, unbounded responses, or heap-exhausting plugins | Quotas, batching, timeouts, resource monitoring |
| Environment integrity | Untrusted plugin JARs, version drift | Official release sources, checksum checks, version-change process |

**Three questions before enabling an ingestion path:** is the source trusted, what data will pass through Neo4j, and do final read/write permissions belong to the **Neo4j Server account** or the **application account**?

## 2. Distinguishing local files, remote URLs, and user uploads

All look like "paths," yet the cases below are not equivalent:

~~~text
file:///customers.csv
https://data.example.org/exports/customers.csv
C:\Users\developer\Downloads\customers.csv
/home/app/uploads/customers.csv
~~~

- `file:///customers.csv` in `LOAD CSV` is a **file URL handled by Neo4j Server**; resolution is constrained by the import directory and configuration.
- `https://...` is a **network resource that the Neo4j server may have to fetch**.
- `C:\Users\...` is a path on a user's Windows machine; it normally **does not exist on Neo4j Server**, especially when the DB runs in a container or Aura.
- `/home/app/uploads/...` may exist on the API host without being mounted into the DB container, so it cannot be treated as readable by Neo4j.

For HTTP uploads, a sound pattern is typically:

1. **The API receives** the content and validates permissions, semantics, and size.
2. The API writes to a dedicated staging area with a server-generated filename, or parses and transforms data into structured records.
3. An authorized worker uses `UNWIND` via the Java Driver or a controlled import workflow.
4. Temporary files are deleted per policy after successful import and reconciliation.

**Never take a client-supplied filename** and interpolate it into a file URL executed by Neo4j. Parameterizing Cypher mitigates Cypher injection, yet **does not protect against path traversal or SSRF** if arbitrary URLs or paths are still accepted.

## 3. `LOAD CSV` with file:/// and the import directory

### 3.1. Import directory principles

Neo4j can load CSV from file URLs when configuration permits. In self-managed 5.x configurations, two common settings are:

~~~properties
# neo4j.conf - illustration for self-managed Neo4j
server.directories.import=import
dbms.security.allow_csv_import_from_file_urls=true
~~~

Meaning:

- `server.directories.import` specifies the **permitted import directory** for file URLs read by the corresponding mechanism. Relative values resolve against the server directory structure; exact physical location depends on installation method.
- `dbms.security.allow_csv_import_from_file_urls` controls whether `LOAD CSV` is allowed to read via **`file:///`**. Set to `false` when local file import is not needed.
- If importing from HTTPS URLs is required, disabling **file URLs** does not block all network URLs. Both paths must be evaluated independently.

**Never remove the import directory restriction just to "make a file somewhere else work."** Certain settings or plugins can erode path boundaries when the import directory is unrestricted. The right design **stages data into the vetted import area**, rather than exposing the entire filesystem.

### 3.2. Example CSV import within the permitted scope

Suppose an administrator placed `customers.csv` into Neo4j's actual import directory and the reading account holds valid privileges:

~~~csv
customerId,displayName
C-101,Lan
C-102,Minh
~~~

Verify schema first:

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;
~~~

Read/write statement:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
WITH row
WHERE row.customerId IS NOT NULL
  AND trim(row.customerId) <> ''
MERGE (c:Customer {customerId: trim(row.customerId)})
SET c.displayName = row.displayName;
~~~

Key points:

1. Neo4j Server opens the file, **not the Java client**.
2. `WITH HEADERS` reads the first row as column names; CSV values still require type and business validation.
3. `MERGE` on a stable key makes simple cases repeatable; a **constraint** prevents duplicate nodes under concurrent writes.
4. The Cypher caller also needs appropriate **graph read/write and data-loading privileges** per edition/version, not just OS permissions.
5. A syntactically valid file URL does not guarantee the file exists or that the user/process can read it.

For large files, split transactions using `CALL { ... } IN TRANSACTIONS` or batching supported by your Cypher version. **Each batch commits independently**, so design retries, checkpoints, and cleanup rather than assuming the entire import is one atomic transaction.

### 3.3. Difference between a file URL and an OS path

Self-managed Neo4j example:

~~~text
NEO4J_HOME/
  conf/neo4j.conf
  import/
    customers.csv
    products.csv
~~~

With the import directory configured above, standard usage is `file:///customers.csv`, **not** `file:///NEO4J_HOME/import/customers.csv`. Inside a Linux container, the in-container path may be `/var/lib/neo4j/import`; on Windows, physical paths differ. **Never use host-machine paths inside Cypher** when the database runs in Docker or Kubernetes.

Filenames containing spaces, Unicode, or special characters must be properly encoded for file URLs, yet **encoding does not replace path validation**. Disallow `..`, double-encoded URL forms, or symlinks pointing outside the permitted area. Enforce controls at both Neo4j configuration **and** filesystem/mount permissions.

### 3.4. When to disable local file import completely

If all data ingestion flows through the backend and the API uses `UNWIND`, configure:

~~~properties
dbms.security.allow_csv_import_from_file_urls=false
~~~

This is an **extra guardrail**, not a substitute for OS permissions or procedure controls: another plugin capable of reading files still requires its own configuration. Changing Neo4j configuration usually requires a restart/redeploy workflow and version-specific verification.

## 4. Path traversal, symlinks, and OS permissions

**Path traversal** occurs when a caller-controlled path resolves to a location **outside the authorized directory**. For example, an endpoint:

~~~text
POST /import?filename=customers.csv
POST /import?filename=../../conf/neo4j.conf
~~~

Dangerous application code:

~~~java
// Do not do this: filename is controlled by the client.
String cypher =
        "LOAD CSV FROM 'file:///" + requestFilename + "' AS row ...";
~~~

This both accepts arbitrary paths and risks **Cypher injection** by concatenating input into query syntax. Even if moved into a URL parameter, untrusted input can still point to an unauthorized resource.

### Multi-layer defense boundaries

| Layer | How to apply | Reason |
| --- | --- | --- |
| **API** | Client picks an approved `datasetId` from a list, never sends filesystem paths | Eliminates "read arbitrary file" functionality |
| **Staging** | Server generates filenames; validates format, size, schema, checksum | Prevents malicious content and forged filenames |
| **Canonical path** | When handling files in the app, resolve/normalize and compare against a fixed root | Blocks `../` and variants |
| **Filesystem** | Neo4j OS user has read-only access to import dir; no access to secrets/backups | Limits blast radius if a bug occurs |
| **Container** | Mount only the specific directory, prefer read-only, never mount host root/`conf` | Shrinks filesystem attack surface |
| **Plugin config** | Keep import-directory enforcement active; deny arbitrary path access in plugins | Prevents boundary bypass via extension procedures |

**A deeper point:** `Path.normalize()` or string-prefix checks **are not enough** against symlinks and TOCTOU (*time-of-check to time-of-use*) races. For uploads that users might swap after validation, use a staging directory writable by no other user, server-generated filenames, safe file-opening APIs, and *real path* checks where appropriate. In production, never mount a directory containing unvetted symlinks into import.

A Java-layer example illustrating only the **path-verification step** on an existing file:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class SafeStagingFile {
    public static Path resolveExisting(
            Path trustedRoot, String serverGeneratedName)
            throws IOException {
        Path root = trustedRoot.toRealPath();
        Path candidate = root.resolve(serverGeneratedName).normalize();
        Path actual = candidate.toRealPath();

        if (!actual.startsWith(root) || !Files.isRegularFile(actual)) {
            throw new SecurityException("File outside import staging");
        }
        return actual;
    }
}
~~~

**Limitation of this snippet:** It does not lock the file against replacement **after verification**, and must never be called directly with a client-supplied filename. A stronger workflow reads files inside a strictly permissioned staging area or ships structured data to containers/workers over a trusted channel.

## 5. HTTP(S) URLs: the SSRF threat

Neo4j can fetch data from external URLs when a Cypher statement or procedure permits, for example:

~~~cypher
LOAD CSV WITH HEADERS
FROM 'https://data.example.org/exports/products.csv' AS row
RETURN row.sku AS sku, row.name AS name
LIMIT 10;
~~~

**SSRF** occurs when an attacker causes **the server** to send requests to targets the attacker normally cannot reach. A Neo4j host inside a VPC can reach internal endpoints, localhost, or cloud metadata services invisible to an Internet user.

Risky input patterns:

~~~text
http://127.0.0.1:port/admin
http://10.0.0.5/internal
http://169.254.169.254/...
https://attacker-controlled.example/redirect-to-private
~~~

These URLs only **illustrate dangerous target classes**. Calling internal or metadata endpoints is never a legitimate function of a product-import API.

### 5.1. Why is "HTTPS only" not enough?

HTTPS protects the **transport channel** when certificates are verified; it does not determine whether a URL is **business-authorized**. An attacker-controlled HTTPS URL can:

- Redirect to HTTP or to an internal network IP.
- Serve oversized payloads, malformed schemas, redirect loops, or slow-loris responses.
- Capture the Neo4j host IP and any forwarded request headers.
- Abuse DNS that changes IP addresses after validation (*DNS rebinding*).

Thus, host/domain checks **in the application layer** are necessary yet insufficient if clients supply arbitrary URLs; you must account for redirects, DNS resolution, resolved destination IPs, timeouts, and network **egress policy**.

### 5.2. A safer URL-ingestion architecture

~~~mermaid
flowchart LR
    C["Client: datasetId"] --> A["Import API"]
    A --> M["Approved source catalog"]
    M --> F["Fetcher/staging service<br/>egress + validation"]
    F --> Q["Parse + schema validate"]
    Q --> J["Java Driver / UNWIND"]
    J --> N[("Neo4j")]
~~~

Instead of letting clients pass arbitrary URLs to `LOAD CSV` or `apoc.load.json`:

1. The API accepts a **`datasetId`** or administrator-configured source key.
2. A dedicated fetcher reaches only approved endpoints, inspects redirects, and limits hop counts.
3. Connections enforce HTTPS/TLS with certificate verification; credentials come from a secret manager, never URL query strings.
4. The fetcher enforces size limits, connect/read timeouts, rate limits, format checks, and row caps.
5. Data is validated, logged by request ID, and sent as `UNWIND` batches via the Driver.

Key benefit: **Neo4j needs no broad Internet access** to import data. The dedicated fetcher can run in an isolated network segment with explicit download policies.

### 5.3. Network egress is a critical guardrail

Depending on deployment, apply firewalls, Kubernetes NetworkPolicy, service mesh/proxies, or VPC egress controls:

- Allow Neo4j outbound network access only for specific business requirements.
- Block Neo4j from reaching cloud metadata, management networks, other services' loopback interfaces, or unapproved internal IP ranges.
- Enforce DNS and redirect restrictions via an egress proxy; keep sensitive URL parts out of logs.
- Use a **separate administrative process** for plugin updates or approved file downloads rather than opening unrestricted Internet access to query accounts.

Certain Neo4j features support restricting `LOAD` privileges by URL or CIDR range depending on version/edition. Database-level privileges are an additional barrier, **not a replacement** for network firewalls and policies.

## 6. Cypher parameters are not a URL access-control tool

Neo4j supports parameters instead of string concatenation in Cypher, for example:

~~~cypher
LOAD CSV WITH HEADERS FROM $sourceUrl AS row
RETURN row.customerId
LIMIT 100;
~~~

Passing `$sourceUrl` reduces **Cypher code injection** compared to string assembly:

~~~java
// Parameterized properly, YET not safe enough regarding the URL:
tx.run("""
    LOAD CSV WITH HEADERS FROM $sourceUrl AS row
    RETURN row.customerId AS customerId
    LIMIT 100
    """, java.util.Map.of("sourceUrl", externalUrl));
~~~

If `externalUrl` is freely chosen by a user, the database can still be directed to an unauthorized target. You must validate **source authorization** independently of query syntax safety.

A practical rule: **parameterization prevents injection; source allowlists + egress controls prevent SSRF; directory scoping + OS permissions prevent out-of-scope file reads.** No single layer replaces the other two.

## 7. APOC: separate file read/write settings from LOAD CSV

**APOC** is an extension library of procedures and functions for Neo4j. Several procedures support importing/exporting CSV, JSON, XML, GraphML, or loading from URLs. Installing APOC **does not mean** all file read/write capabilities are enabled.

In modern APOC Core/Extended releases, file-related settings are typically placed in `apoc.conf`:

~~~properties
# apoc.conf - hardening example when file read/write plugins are NOT needed
apoc.import.file.enabled=false
apoc.export.file.enabled=false
apoc.import.file.use_neo4j_config=true
~~~

Explanation:

- `apoc.import.file.enabled`: enables/disables **APOC file import** functionality.
- `apoc.export.file.enabled`: enables/disables **APOC file export** functionality.
- `apoc.import.file.use_neo4j_config=true`: instructs APOC import mechanisms to respect Neo4j's import directory restrictions for procedures that support this rule.

**Never set `apoc.import.file.use_neo4j_config=false` merely to read files outside the import folder.** In configurations that permit it, doing so can substantially widen APOC's filesystem reach. That is not a performance tweak—it is a **security boundary change**.

### 7.1. When APOC file import is genuinely required

On a **self-managed server** with a secure staging workflow, consider:

~~~properties
# Use only after approving business requirements and OS/container permissions:
apoc.import.file.enabled=true
apoc.import.file.use_neo4j_config=true
apoc.export.file.enabled=false
~~~

Then grant procedure execution only to the designated importer role. Enabling file import should not automatically enable file export unless needed; **export** introduces risks of writing to the filesystem or exfiltrating sensitive data.

### 7.2. APOC and remote URLs are a separate surface

A procedure like `apoc.load.json` can fetch JSON from URLs as supported. **Setting `apoc.import.file.enabled=false` must not be assumed to disable all HTTP(S) requests** from other procedures. Every network-capable procedure/plugin must be evaluated separately:

- Does it accept user-controlled URLs?
- Does it enforce redirect, timeout, and TLS policies?
- Can it send headers containing secrets?
- Can it reach localhost, private IPs, or metadata services?
- Which roles can invoke that procedure?

If trusted URLs cannot be guaranteed, **do not grant execution** of URL-loading procedures to that role, or route fetching through a controlled application fetcher.

## 8. Distinguishing APOC Core, APOC Extended, GDS, and other plugins

Neo4j extensions differ in purpose and privilege profile:

| Component | Role | Operational/security considerations |
| --- | --- | --- |
| **Core Cypher** | `MATCH`, `CREATE`, `LOAD CSV`, and supported clauses | Roles, `LOAD` privileges, file URL settings |
| **APOC Core** | Common utilities/procedures, depending on Neo4j release | Version-matched plugin, `apoc.conf`, procedure privileges |
| **APOC Extended** | Additional procedures, potentially including external integrations | Separate release/versioning; install only what is truly needed |
| **Graph Data Science (GDS)** | In-memory graph projections and algorithms | Compatible plugin, license/edition, RAM/CPU, procedure privileges |
| **Third-party plugins** | Vendor or custom-written extensions | Code/source audit, dependencies, filesystem/network rights, upgrade lifecycle |

**Never treat a plugin JAR as "harmless" just because its call looks like Cypher.** Plugins execute inside the server process or runtime with the privileges granted to plugin/procedure mechanisms. A flaw in a plugin or its dependencies can compromise data, networks, or availability.

### 8.1. Process for deploying plugins to production

1. Obtain plugins only from **approved release sources**, preferring official distributions matching your edition and version.
2. Pin Neo4j and plugin versions; verify the **compatibility matrix** instead of pulling `latest` arbitrarily.
3. Verify checksums/signatures when published; scan dependencies and monitor security advisories.
4. Evaluate `procedures.unrestricted` needs: grant unrestricted access only to namespaces/procedures that **strictly require it**.
5. Place plugins in a directory writable only by admin/deployment tooling, never modifiable by application accounts.
6. Restart/redeploy per change workflow; verify plugin load logs and active procedure list after startup.
7. Measure resource usage, plan version rollbacks, and assess impact on active transactions.

**For Aura:** managed environments typically **do not allow tenants to drop arbitrary JARs onto the server**. Check the list of supported procedures/plugins for your tier and use application API/Java integrations or external analytics services when unsupported capabilities are needed.

## 9. Procedure allowlist and unrestricted: two distinct controls

In self-managed Neo4j 5.x, common settings are:

~~~properties
# neo4j.conf - ILLUSTRATIVE, must be tuned to actual plugins and requirements
dbms.security.procedures.allowlist=apoc.coll.*,apoc.text.*

# Do not grant unrestricted to every plugin automatically.
# Declare only patterns explicitly required by plugin documentation.
# dbms.security.procedures.unrestricted=...
~~~

`allowlist` controls **which procedures/functions are allowed to be loaded or exposed** per version support. `unrestricted` governs whether procedures may use **privileged internal APIs** that Neo4j normally blocks; it is **not a read-only setting**.

Neither setting **replaces user authorization**:

1. Is the procedure **installed/loaded** on the server?
2. Is the procedure **permitted** by the corresponding allowlist/unrestricted config?
3. Does the caller's **role** hold `EXECUTE PROCEDURE` (and `EXECUTE BOOSTED PROCEDURE` if required)?
4. Is the procedure permitted to access files/URLs by APOC config and network/OS policy?

**Dangerous anti-pattern:**

~~~properties
# DO NOT use as a default security configuration.
dbms.security.procedures.unrestricted=*
dbms.security.procedures.allowlist=*
~~~

An "allow everything" configuration sharply increases exposure to unintended procedure exploitation. Never fix a "procedure not found" error by opening `*` without knowing why it was blocked.

### 9.1. Role-based access control (RBAC)

Neo4j Enterprise offers finer-grained roles and privileges than Community. In deployments supporting the corresponding syntax, administrators can run:

~~~cypher
// Run in the proper admin context on RBAC-supporting editions.
CREATE ROLE import_operator IF NOT EXISTS;

// Example granting one specific procedure if installed and permitted:
GRANT EXECUTE PROCEDURE apoc.load.json ON DBMS
TO import_operator;
~~~

Also grant **data read/write privileges** per use case and Neo4j `LOAD` requirements for your version. Never assign an import role to an API account serving public Internet users. Conversely, if a role only queries the graph, it needs no file-loading or URL-fetching privileges.

When a procedure requires boosted execution, evaluate **specific risks and privilege scope** rather than granting `EXECUTE BOOSTED PROCEDURE *` to an entire group. Verify every `GRANT` example against your version and edition: Community does not provide Enterprise RBAC features.

## 10. Docker, Kubernetes, and filesystem hardening

Containers do not automatically make file paths safe. Mounting a host directory containing secrets or backups into the Neo4j container can expose those files if configuration, permissions, or plugins are misconfigured.

### 10.1. Safe mount layout

~~~text
Host:
  /srv/neo4j/data/          (database files, private)
  /srv/neo4j/import-safe/   (vetted CSVs only)
  /srv/neo4j/secrets/       (never mounted into import)

Neo4j Container:
  /data                     (database volume)
  /import                   (read-only staging mount)
  /conf                     (deployment-managed config)
~~~

Set in `neo4j.conf` (if applicable to your image/version):

~~~properties
server.directories.import=/import
dbms.security.allow_csv_import_from_file_urls=true
~~~

Example **illustrating mounts in Docker Compose**, not a complete deployment spec:

~~~yaml
services:
  neo4j:
    image: neo4j:5.26
    volumes:
      - /srv/neo4j/data:/data
      - /srv/neo4j/import-safe:/import:ro
    # Add auth, secrets, resource limits, TLS, networking, and configs
    # for real systems. Never hard-code passwords in public compose files.
~~~

**Note:** Select a Neo4j image compatible with your hardware and plugins; the tag above is illustrative, not a latest-version recommendation. The container needs read access to the import mount, not write access to vetted CSV files. Database storage and import staging are separate scopes.

### 10.2. Container deployment checklist

- Run processes as a **non-root user** where supported.
- Never use privileged containers or mount the Docker socket into Neo4j.
- Mount **only the dedicated import directory**, preferring `readOnly`; never mount `/`, `/etc`, home directories, or secrets.
- Keep `plugins`, `conf`, `certificates`, and import directories on separate volumes/permissions.
- Restrict network egress to approved endpoints; apply a NetworkPolicy matching your actual CNI/Kubernetes setup.
- Enforce CPU/RAM limits; large imports can stress page cache, heap, disk, and GC.
- Test on staging with synthetic files sized to maximum business expectations.

## 11. Java/Spring API: ingesting data without the database reading URLs

When Neo4j only needs to ingest records already vetted by the application, the Java Driver can pass **structured lists** via parameters. This is often more flexible and lower-privilege than `LOAD CSV FROM $clientUrl`.

### 11.1. Java Driver + UNWIND

~~~cypher
UNWIND $customers AS item
WITH item
WHERE item.customerId IS NOT NULL
  AND trim(item.customerId) <> ''
MERGE (c:Customer {customerId: item.customerId})
SET c.displayName = item.displayName;
~~~

Java service example:

~~~java
import java.util.List;
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class CustomerImporter {
    private final Driver driver;

    public CustomerImporter(Driver driver) {
        this.driver = driver;
    }

    public void importBatch(List<Map<String, Object>> sanitizedCustomers) {
        // Caller must validate schema/size and cap element count.
        if (sanitizedCustomers.isEmpty() || sanitizedCustomers.size() > 500) {
            throw new IllegalArgumentException("Invalid batch size");
        }

        try (Session session =
                driver.session(SessionConfig.forDatabase("neo4j"))) {
            session.executeWrite(tx -> {
                tx.run("""
                    UNWIND $customers AS item
                    MERGE (c:Customer {customerId: item.customerId})
                    SET c.displayName = item.displayName
                    """, Map.of("customers", sanitizedCustomers))
                  .consume();
                return null;
            });
        }
    }
}
~~~

Strengths of this pattern:

- Neo4j needs no **filesystem** reads or **Internet** egress; the server receives only Bolt parameters.
- Java handles source authentication, parsing, and validation; Neo4j transactions commit atomically per batch.
- Queries are parameterized; user data is never concatenated into Cypher.
- Reuses a shared `Driver`, opens `Session` per request/batch, and uses `executeWrite` for mutations.

**Limitations:** Managed transaction callbacks may retry on transient errors. Batch inputs and IDs must be idempotent; never trigger email/HTTP side effects inside callbacks. Each batch commits independently, so do not assume all batches roll back together if a later batch fails. Very large datasets require streaming/batch pipelines with checkpoints, retries, and backpressure.

### 11.2. Do not trust data merely because it passed through the API

Before feeding rows into `UNWIND`:

- Cap row counts, column counts, string lengths, total bytes, and nesting depth.
- Validate data types, date formats, enums/statuses, and business keys.
- Verify the user is authorized to **import into that specific dataset/tenant**; never mix another customer's data.
- Use constraints to protect node IDs, and conditions/transactions to protect relationships.
- Sanitize content dangerous to downstream systems (HTML/reports/logs), not just Cypher.
- Log job ID and received/accepted/rejected row counts; never dump entire sensitive payloads.

A small record count can still hold huge strings or fan-out relationship structures. Bound **record count** and **total bytes/complexity** together.

## 12. Neo4j privileges and separation of duties

To minimize damage if an API credential leaks, never reuse one administrative account across all workloads.

| Account type | Privileges to grant | Privileges to avoid |
| --- | --- | --- |
| **Graph read API** | Read only required labels/relationships/properties | File import, URL calls, privileged procedures, graph writes |
| **Business write API** | Write only owned portions of the graph | Plugin installs, config changes, filesystem access |
| **Import worker** | Required `LOAD`/procedures and writes to permitted datasets | Full admin rights, arbitrary file export |
| **Graph analyst** | Read appropriate data, approved algorithms/analytics | Unnecessary network URL loads, sensitive writes |
| **DB administrator** | Manage config, roles, backups, and operations | Never use this account for public endpoints |

Organizations must verify both **Neo4j RBAC** and **OS/network permissions**. For instance, a DB role might allow calling a procedure while the container blocks outbound Internet access; that is **defense in depth**, not a bug to fix by "opening everything."

### 12.1. Multi-tenancy and import paths

In multi-tenant systems, a CSV from tenant A could contain business IDs belonging to tenant B. If `MERGE (c:Customer {customerId: item.id})` omits tenant scope when IDs are only unique per tenant, data can be overwritten or cross-linked.

Use a **logical key combining tenantId + localId** or globally unique IDs, paired with matching constraints and predicates:

~~~cypher
CREATE CONSTRAINT customer_tenant_key IF NOT EXISTS
FOR (c:Customer)
REQUIRE (c.tenantId, c.customerId) IS UNIQUE;
~~~

In this model, the application must derive `tenantId` from a **trusted authentication context**, never trusting an arbitrary CSV column to decide which tenant gets written. If your edition/version lacks the desired constraint type, use a supported key/constraint pattern without dropping tenant verification.

## 13. Monitoring, auditing, and incident management

Imports and plugins cannot be secured by a static set of settings alone. You need visibility into **who** invokes risky features, **which sources** are loaded, **what outcomes** occur, and whether access matches expectations.

| Metric/event group | What to record | Warning signs |
| --- | --- | --- |
| **Import jobs** | Job ID, dataset ID, user/role, timestamp, row counts, status | Unusually large files, spikes in rejected rows |
| **URL access** | Approved domain, error codes, latency, payload size; avoid secrets in URLs | Unfamiliar hosts, abnormal redirects, private IPs |
| **Privileges/procedures** | Denied calls, role changes, boosted procedure grants | Sudden privilege escalation, unexpected procedure calls |
| **Plugin lifecycle** | Added/removed JARs, checksums, versions, startup errors | Unknown JAR provenance, post-deploy changes |
| **Neo4j** | CPU, heap, GC, page cache, disk, transaction latency, Cypher errors | Imports starving transactional workloads |
| **Filesystem** | Import storage usage, leftover temp files, permission changes | Unexpected files or symlinks inside import dir |
| **Network** | Egress to hosts/IP ranges, DNS lookups, TLS failures | Connections to non-allowlisted addresses |

In Neo4j Enterprise/self-managed, specific audit capabilities and logs depend on configuration and version. Never enable logging at a verbosity that captures full sensitive Cypher parameters without evaluating **data security** and overhead. On Aura, rely on provider-exposed logs and metrics rather than assuming host log-file access.

### Response workflow when exploitation is suspected

1. Immediately restrict the abused import endpoint, role, or procedure while preserving evidence.
2. Inspect egress/network logs, job history, query audit trails, and plugin/config changes.
3. Rotate potentially exposed credentials and tokens; secure related secret stores.
4. Reconcile nodes/relationships and anomalous mutations; use backup/restore per playbook if necessary.
5. Patch application/plugin/Neo4j, tighten allowlists, run regression tests, and monitor post-remediation.

This is a general outline; follow your organization's incident-response policy and evidence-retention rules.

## 14. Common errors and layered diagnosis

| Symptom | Possible causes | Safe troubleshooting path |
| --- | --- | --- |
| `LOAD CSV` fails on `file:///customers.csv` | File URLs disabled, file missing from import dir, wrong OS permissions | Check config and path on **Neo4j Server**; never open the whole filesystem |
| Works on host, fails in Docker | Import dir not mounted or mounted at wrong container path | Inspect volumes and `server.directories.import` |
| HTTP error fetching URL | DNS, TLS, proxy, firewall, timeout, or disallowed URL | Check allowlist and egress logs; never disable TLS verification |
| `apoc.load.json` does not exist | APOC not installed, version mismatch, excluded by allowlist, missing privilege | Check plugin, version, procedure catalog, and role |
| APOC file import denied | `apoc.import.file.enabled=false` or invalid directory/permissions | Enable only for approved use cases; keep `use_neo4j_config=true` |
| Procedure returns `permission denied` | Role lacks `EXECUTE`/`BOOSTED` or graph privileges | Grant targeted privilege, never global admin |
| Plugin fails to start | Wrong JAR version, missing dependency, invalid configuration | Check startup logs and compatibility matrix |
| Slow import / OOM | Huge file, oversized transaction, resource contention | Batch, cap size/timeout, measure heap/GC/disk |
| URL succeeds but violates policy | Server egress too broad or wrong role granted | Narrow sources, proxy, firewall, and procedure grants |

**Crucial rule:** Never fix "cannot read file" by "disabling all checks," setting `unrestricted=*`, "mounting host root," or "skipping TLS verification." Those actions expand the attack surface far beyond importing a file.

## 15. Hands-on lab: importing a CSV safely

### Objective

In a **self-managed test Neo4j** environment, import customer data without letting the API account read arbitrary files or call arbitrary URLs. Execute on a dedicated demo database with proper change authorization for configuration edits.

### Step 1 — Map the boundaries

Document:

- Is Neo4j running locally, in Docker, Kubernetes, or Aura?
- What is the **actual import path inside the server/container**?
- Which OS user runs Neo4j, and what read/write permissions exist on the import directory?
- Who can call `LOAD CSV`, and which roles can run APOC?
- Does Neo4j genuinely need Internet connectivity for imports?

### Step 2 — Configure import staging

Place **only** a schema- and size-checked `customers.csv` in the import directory. If using containers, mount only that directory, preferably read-only. Never place secrets, config files, certificate private keys, or database backups in the import directory.

### Step 3 — Read the file within scope

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
RETURN row.customerId AS customerId,
       row.displayName AS displayName
LIMIT 10;
~~~

Verify:

1. Permitted files can be read when file URLs are enabled for the lab.
2. Files outside the import directory cannot be accessed by altering path strings.
3. When file URLs are disabled in config, the command above fails as expected.

Never test against real files containing sensitive data: use **non-sensitive dummy files** to validate blocking controls.

### Step 4 — Write to the graph using business keys

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;

LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
WITH row
WHERE row.customerId IS NOT NULL
  AND trim(row.customerId) <> ''
MERGE (c:Customer {customerId: trim(row.customerId)})
SET c.displayName = row.displayName;
~~~

Re-run with the same file to confirm no duplicate nodes are created for `customerId`; if source data violates schema, flag errors rather than forcing the import.

### Step 5 — Test URL policies

Set up a **team-controlled test HTTPS source**—never connect to real cloud metadata or production admin endpoints:

- Allowlisted endpoints succeed when permitted by the use case.
- Non-allowlisted domains are **rejected by the app/fetcher** before reaching Neo4j.
- Redirects to disallowed domains are rejected.
- Files exceeding byte/row caps or slow responses time out cleanly.
- A graph read-only API role lacks file/URL import rights and sensitive import procedures.

### Step 6 — Test plugins

If APOC import/export is unused, keep:

~~~properties
apoc.import.file.enabled=false
apoc.export.file.enabled=false
apoc.import.file.use_neo4j_config=true
~~~

Only when the lab requires it and the environment runs the proper APOC version should file import be enabled in the vetted area. Inspect procedure lists and roles; **never turn on unrestricted wildcards "just to test easily."**

### Step 7 — Compare against Driver-based ingestion

Use the Java API from Section 11 to send the same `Customer` batch via `UNWIND`. Compare:

| Criterion | `LOAD CSV file:///` | Java Driver + `UNWIND` |
| --- | --- | --- |
| Neo4j must read server filesystem | **Yes** | **No** |
| Database needs HTTP egress | No, for local file URLs | No, if the app pre-parses |
| Pre-import validation/authorization | Must live in staging/app workflow | Cleanly placed in the service |
| Batching/retries | Managed via Cypher/transactions | Managed per Java request/batch |
| Best fit | Files placed in staging by admins | APIs/workers ingesting varied sources |

**Lab conclusion:** The goal is not making every file/URL feature work at once, but **opening only the required ingestion path** and proving all other paths are blocked.

## 16. Pre-production hardening checklist

- [ ] Identify **who reads files/URLs**: Neo4j Server, APOC procedures, or the Java application.
- [ ] If using `LOAD CSV file:///`, allow only a **vetted import directory** with minimal OS permissions.
- [ ] Disable `dbms.security.allow_csv_import_from_file_urls` when file URLs are unnecessary.
- [ ] Never build endpoints that interpolate client-supplied paths or URLs into Cypher or procedures.
- [ ] Validate canonical paths, symlinks, staging write permissions, and path-traversal/TOCTOU scenarios.
- [ ] Permit only vetted source URLs; enforce HTTPS, redirect checks, DNS validation, private-IP blocking, timeouts, and size caps.
- [ ] Enforce firewalls/egress proxies or NetworkPolicies; never rely solely on URL regexes.
- [ ] Keep `apoc.import.file.use_neo4j_config=true` when using APOC file imports.
- [ ] Do not enable `apoc.export.file.enabled` unless export is an explicit business requirement.
- [ ] Install only strictly needed APOC/GDS/plugins from trusted sources with matching versions.
- [ ] Never use `dbms.security.procedures.unrestricted=*` or grant boosted procedure wildcards to application roles.
- [ ] Distinguish procedures that are **loaded**, **allowlisted**, and **EXECUTE**-granted to roles.
- [ ] Pin image/JAR versions, protect `plugins`/`conf`/`secrets` volumes, and minimize container privileges.
- [ ] Use business IDs, uniqueness constraints, validation, and batching for imported data.
- [ ] Where possible, isolate a fetcher/ingest service and send structured batches via Java Driver/`UNWIND`.
- [ ] Monitor audits, denied accesses, import jobs, plugin changes, network egress, and system resources.
- [ ] Test **blocked cases** on staging; maintain incident-response playbooks and configuration rollback steps.

## References

- [Neo4j Cypher Manual — LOAD CSV](https://neo4j.com/docs/cypher-manual/current/clauses/load-csv/)
- [Neo4j Operations Manual — Configuration settings](https://neo4j.com/docs/operations-manual/current/configuration/configuration-settings/)
- [Neo4j Operations Manual — File locations](https://neo4j.com/docs/operations-manual/current/configuration/file-locations/)
- [Neo4j Operations Manual — Security and authorization](https://neo4j.com/docs/operations-manual/current/security/authorization/)
- [Neo4j Operations Manual — Docker and configuration](https://neo4j.com/docs/operations-manual/current/docker/configuration/)
- [APOC Documentation — Configuration](https://neo4j.com/docs/apoc/current/config/)
- [APOC Documentation — Import](https://neo4j.com/docs/apoc/current/import/)
- [Neo4j Graph Data Science — Installation](https://neo4j.com/docs/graph-data-science/current/installation/)
- [Neo4j Java Driver Manual — Transactions](https://neo4j.com/docs/java-manual/current/transactions/)

**Conclusion:** Securing file paths, URL access, and extension configurations in Neo4j means controlling **what the database process is permitted to read, call externally, and execute via procedures**. Import directory limits, disabling unused features, SSRF protections across API and network layers, least-privilege plugin policies, and vetted ingestion pipelines work together as complementary layers. When data import is needed, open **only the right source, role, and scope**, and verify with both positive and negative access tests.
