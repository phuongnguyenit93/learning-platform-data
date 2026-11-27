# Post-Upgrade JDK, Driver, Spring Data, and Protocol Matrix

> **Chapter:** Upgrades and Compatibility  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — Apache Cassandra with distributed architecture, wide-column model, partition keys, query-driven table design, read/write consistency, CQL, replication, compaction, repair, error handling, and Java application connectivity.

A Cassandra upgrade can succeed at the node level yet fail at the application layer: the new node runs on a different JDK, an older Java Driver cannot decode a new data type, Spring Data clashes with Spring Boot, or the client connects while negotiating only an older **native protocol**. A passing `SELECT 1` test **does not prove** vectors, SAI, codecs, TLS, paging, prepared statements, and schema mappings work.

This lesson focuses on building and verifying a **multi-layer compatibility matrix**:

1. **Cassandra server ↔ JDK running the Cassandra node.**
2. **Java application ↔ application JDK ↔ Java Driver version.**
3. **Spring Boot ↔ Spring Framework/Spring Data Cassandra ↔ BOM-managed Java Driver.**
4. **Java Driver ↔ actual negotiated native protocol ↔ required CQL features.**
5. **Rolling upgrade ↔ mixed-version cluster state ↔ read/write and new-feature stability.**

> **Core rule:** "Can connect" differs from "officially supported," which differs from "**fully** supporting all features of the new release." Matrices in this lesson are **scoped reference milestones**, not substitutes for exact release notes/BOMs of the deployed versions. Before rollout, lock down **server patch, JDK distribution/build, driver patch, Spring Boot/Data patch, native protocol, and feature set** in a test manifest.

## 1. Learning Objectives

Upon completing this lesson, you can:

1. Distinguish the JDK running **Cassandra nodes** from the JDK running **Java services**, avoiding forcing identical major versions unnecessarily.
2. Read the Cassandra 4.x/5.0, Java Driver 3.x/4.x, Spring Data Cassandra 4.5/5.0, and Spring Boot 3.5/4.0 matrices as **separate compatibility axes**.
3. Measure the negotiated native protocol via the Java Driver, explaining v4/v5 and mixed-version cluster effects.
4. Identify risks from groupId/artifact shifts, classpath conflicts, and API changes when upgrading the Java Driver or Spring Data.
5. Design pre/post-upgrade tests for connectivity, prepared statements, UDTs/collections, TLS, paging, CLs, vectors/SAI, and performance.
6. Author a rolling upgrade plan with canaries, rollback/roll-forward options, and approval gates so new features are never enabled too early.

## 2. Five Compatibility Layers: Following One Request's Path

~~~mermaid
flowchart LR
    A["Java service<br/>Application JDK"] --> B["Spring Boot / Spring Data Cassandra"]
    B --> C["Java Driver + Netty/codecs"]
    C --> D["Native protocol v3/v4/v5<br/>TLS, auth, prepared CQL"]
    D --> E["Cassandra node<br/>Server JDK"]
    E --> F["Replicas, schema, SSTables, RF/CL"]
    G["BOM + dependency tree"] -. "Pin versions" .-> B
    H["Upgrade runbook"] -. "Rolling server" .-> E
~~~

| Layer | Question to answer | Typical failures |
|---|---|---|
| **Server runtime** | Which JDK does this Cassandra release run on, and which JVM flags/GC are supported? | `UnsupportedClassVersionError`, startup failure, GC/heap regressions |
| **Java Driver runtime** | What minimum JDK does the driver JAR require? 3.x or 4.x API? | `ClassNotFoundException`, `NoSuchMethodError`, missing mapping classes |
| **Spring stack** | Which Spring Data Cassandra and driver versions does the Spring Boot BOM pull? | Dependency conflicts, `BeanCreationException`, repository/template mapping bugs |
| **Wire/native protocol** | Which protocol version do the driver and each server negotiate? | Protocol negotiation failure, unsupported codecs/features |
| **Data behavior** | Did CQL types, schemas, consistency, paging, or token metadata change? | Connects cleanly yet reads/writes diverge, timeouts, wrong retries |

### 2.1. Node JDK and Application JDK **Are Not the Same JDK**

A Cassandra 5.0 cluster can run **JDK 11 or 17** per its official matrix, while a Spring Boot 3.5 service runs **JDK 17**. That is no contradiction: they are **two independent JVM processes** communicating over the native protocol. Conversely, upgrading the application's JDK does not upgrade the native protocol if the driver/protocol remains old.

Example:

~~~text
Cassandra 5.0.x cluster:
  Runtime: Java 11 or 17 depending on release/build

Service orders-api:
  Runtime: Java 17
  Spring Boot: 3.5.x
  Spring Data Cassandra: 4.5.x (BOM-managed)
  Java Driver: depends on actual resolved version
  Native protocol: outcome of session handshake
~~~

**Mistake:** writing "JDK 17" in docs without stating whether it belongs to the nodes or the service. A good deployment matrix has **two separate JDK columns**.

### 2.2. Three Compatibility Verdict Levels

| Level | Minimum evidence | Example |
|---|---|---|
| **Wire-connectivity** | TCP/TLS handshake, native protocol negotiation, auth, and simple CQL succeed | Driver 4.17 connects to Cassandra 5.0 to read legacy scalar tables |
| **API/schema compatibility** | Java code compiles, Spring repositories, schemas/UDTs, mappers, paging, and CL tests pass | Legacy repository reads/writes accurately on a 5.0 cluster |
| **Feature completeness** | Specific new Cassandra features are supported by driver/Spring Data and integration tests pass | Vector types, vector search, SAI, new CQL types |

Never turn "the driver connected to the server" into "all new features are supported." Only **approve new features** after server, driver, Spring Data/mapping layers, and protocol version all align.

## 3. Cassandra Server ↔ JDK Matrix

### 3.1. Lines to Consider

| Apache Cassandra | Node JDK — reference scope | Upgrade notes |
|---|---|---|
| **3.11.x** | Java 8 is the historical baseline | If on 3.11, verify target requirements and server upgrade path before swapping runtimes |
| **4.0.x** | Java 8 and Java 11; Java 11 fully supported from **4.0.2** | JVM options changed between 8/11; avoid carrying old JVM flags verbatim |
| **4.1.x** | 4.x branch uses the 8/11 matrix per exact release docs | Confirm exact build/distribution, patches, and support policy in production |
| **5.0.x** | **Java 11 or Java 17** for official binary releases built with JDK 11 | Java 8 is no longer supported; builds compiled on JDK 17 will not run on JVM 11 |
| **Experimental/newer majors** | **Do not infer from this table** | Check dedicated release notes; never ship alpha/beta into production as GA |

Sources for key milestones: [Cassandra Java 11 support (4.x)](https://cassandra.apache.org/doc/4.1/cassandra/getting_started/java11.html), [Cassandra 5.0 Java 17 support matrix](https://cassandra.apache.org/doc/stable/cassandra/reference/java17.html), and [Cassandra 5.0 new features](https://cassandra.apache.org/doc/stable/cassandra/new/).

**Distinguish build vs. run:** Cassandra 5.0 docs separate source builds using Java 11 (official binary releases) from building with Java 17. Java 17-compiled bytecode needs a compatible runtime; JARs compiled with 17 cannot run on JVM 11. Checking `java -version` on the build laptop alone is insufficient; record both **build JDK and node runtime JDK** when building from source.

### 3.2. Preparing the JDK Before Swapping Cassandra Binaries

On an authorized node environment:

~~~bash
java -version
echo "$JAVA_HOME"
nodetool version
nodetool status
~~~

With a new JVM, audit:

- Release-specific JVM config files such as `jvm.options` and JDK-specific option files; remove obsolete or altered flags.
- Heap, GC, pause times, direct/off-heap memory, container memory limits, and OOM behavior.
- Exact JDK package/update/security patch; never treat the string "17" as sufficient proof of performance.
- Native libraries, TLS ciphers/JCA providers, PKCS#12/truststores, Netty/JNR, and JVM monitoring tools.

If the node boots yet p99 rises due to GC or TLS handshakes, the issue is **not native protocol**; isolate the JDK/GC axis from client compatibility when comparing.

## 4. Java Driver ↔ Cassandra Server and Native Protocol Matrix

### 4.1. Java Driver 3.x, 4.x, and the 4.19 Milestone

| Driver family | Runtime & primary API | Assessment when connecting to Cassandra 4.x/5.0 |
|---|---|---|
| **DataStax/Apache Java Driver 3.x** | `com.datastax.driver.core.Session`-style API; legacy line | Can serve legacy CQL workloads per version, yet never assume full Cassandra 5.0 feature support |
| **Java Driver 4.0–4.10** | New `com.datastax.oss.driver.api.core.CqlSession` API, Java 8+ | Limited compatibility with Cassandra 4.0 features due to incomplete protocol v5 support in early releases |
| **Java Driver 4.11+** | Production-ready native protocol v5 | Key milestone when upgrading from Cassandra 3.x to 4.x |
| **Java Driver 4.16–4.18** | Partial support for certain Cassandra 5.0 features | Do not assume support for all new vector/type variants |
| **Apache Java Driver 4.19.x** | Apache-maintained 4.x branch; verify exact modules/groupId | Milestone recommended by compatibility docs for **full Cassandra 5.0 driver features**; still verify the Spring layer |
| **Future Java Driver 5.x** | Requirements depend on actual release | A 2026 roadmap note mentions Java 17+ for 5.0; **never cite a roadmap as proof an artifact is GA** |

The 4.11 milestone for protocol v5 is noted in the [Java Driver upgrade guide](https://apache.github.io/cassandra-java-driver/4.19.0/upgrade-README/). Patch-level Cassandra 5.0 feature support must be verified against [Apache Java Driver](https://apache.github.io/cassandra-java-driver/4.19.0/) release notes and the features your application actually uses.

Driver 4.x's **Java 8+** minimum is a library floor—**not** a reason to run Spring Boot 3.5 on Java 8: Spring Boot 3.x imposes its own Java runtime minimum. The final runtime requirement is **the intersection of all constraints**.

### 4.2. Two Maven `groupId`s That Are Easily Confused

Common artifact generations:

~~~xml
<!-- Java Driver 4.x from the DataStax era, e.g., 4.17.x: -->
<dependency>
  <groupId>com.datastax.oss</groupId>
  <artifactId>java-driver-core</artifactId>
  <version>4.17.0</version>
</dependency>
~~~

~~~xml
<!-- Apache Java Driver 4.18+; declare directly only if not managed by another BOM: -->
<dependency>
  <groupId>org.apache.cassandra</groupId>
  <artifactId>java-driver-core</artifactId>
  <version>4.19.0</version>
</dependency>
~~~

**Do not put both artifacts on the classpath** to "guarantee compatibility." Nearly identical Java modules under different coordinates introduce **two driver copies** and unpredictable dependency trees. When using a Spring Boot starter, let the BOM manage versions or override **deliberately with full testing**—never add a second duplicate dependency.

The `groupId` shift at 4.18+ and the `java-driver-core` module are documented in the [Apache Java Driver repository](https://github.com/apache/cassandra-java-driver) and [upgrade guide](https://apache.github.io/cassandra-java-driver/4.19.0/upgrade-README/).

### 4.3. Driver 3 → 4 Is an API Change, Not Just a Dependency Bump

| Java Driver 3.x | Java Driver 4.x |
|---|---|
| `com.datastax.driver.core.Cluster` and `Session` | `com.datastax.oss.driver.api.core.CqlSession` |
| Legacy Config Builder/Pooling APIs | HOCON config, execution profiles, new async/reactive APIs |
| 3.x Metadata/Token/Codec APIs | 4.x Driver context, metadata, codec registry, and mapper |
| 3.x prepared/bound classes | `com.datastax.oss.driver.api.core.cql.PreparedStatement` / `BoundStatement` |
| Legacy driver metrics/routing structure | Different metrics and load-balancing config; consult migration guide |

A project calling driver 3.x directly must rewrite imports, `Session` lifecycles, auth/TLS, local datacenter config, paging, retry policies, and mappers. **Compiling cleanly is not enough**: run against Cassandra with the new driver.

## 5. Native Protocol: Wire Version, Not CQL or SSTable Version

### 5.1. Distinguish Three Version Numbers

One request touches:

- **Server version** — e.g., Cassandra `5.0.x`.
- **Native protocol version** — e.g., `V4` or `V5` (on-the-wire message framing).
- **CQL language version** — version of the CQL dialect implemented by the server.

These three numbers **do not advance in lockstep**. Cassandra 5.0 does not mean every client uses native protocol "v5.0," and "CQL 3" does not mean native protocol v3.

### 5.2. Sample Negotiation Table with Java Driver 4.x

Per [Apache Java Driver 4.19 — Native Protocol](https://apache.github.io/cassandra-java-driver/4.19.0/core/native_protocol/), driver 4 supports native protocols **V3–V5**:

| Server version | Typical protocol with matching Driver 4.x | Notes |
|---|---|---|
| Cassandra 2.1.x | V3 | Legacy only; not recommended for new environments |
| Cassandra 2.2.x/3.x | V4 | Scalar/collection CQL and features available in that generation |
| Cassandra 4.x | V5 with full-support driver (4.11+ milestone) | Verify driver version; early 4.x had V5 caveats |
| Cassandra 5.0.x | V5 is within Driver 4.x supported range | **Cassandra 5.0 features do not appear automatically just from V5**; matching driver patches/type codecs are required |

While a cluster mixes Cassandra 3.x and 4.x during a rolling upgrade, driver 4 includes compatibility negotiation for mixed clusters, yet **never assume every connection uses V5**. Check the session's actual protocol; do not enable features requiring all newer nodes until every node qualifies.

### 5.3. Inspecting Protocol After Connecting from Java

Java Driver 4.x example:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.Row;

// session already built with contact points, local DC, TLS, and auth.
void logCompatibility(CqlSession session) {
    System.out.println("Negotiated protocol = "
            + session.getContext().getProtocolVersion());

    Row local = session.execute(
            "SELECT release_version, cql_version FROM system.local").one();
    if (local != null) {
        System.out.println("Coordinator/local node release = "
                + local.getString("release_version"));
        System.out.println("CQL version = "
                + local.getString("cql_version"));
    }
}
~~~

**Understand what is measured:** `session.getContext().getProtocolVersion()` reports the protocol selected/recorded by the driver session under the current API; `system.local` returns metadata for the node executing that query, **not a list of all replica versions**. In mixed-version clusters, combine `nodetool status`, node inventories, and metadata/metrics across multiple endpoints.

### 5.4. Should You Pin `advanced.protocol.version`?

By default, **let the driver negotiate automatically**. Some 4.x drivers allow pinning:

~~~hocon
# TEST ONLY in lab when driver docs and server version confirm support.
datastax-java-driver {
  advanced.protocol {
    version = V4
  }
}
~~~

Pinning V4 can help isolate negotiation bugs during testing, yet disables newer-protocol features and can mask unresolved mixed-version states. Never pin `V5` against a Cassandra 3.x cluster expecting the driver to auto-fix it: leave it **auto** and log outcomes, forcing only for concrete technical reasons.

### 5.5. TLS Is Separate from the Native Protocol

TLS starts at the network handshake (CA/cert/SAN, ciphers); native protocol negotiation happens **inside** an established transport connection. When a TLS handshake fails, the driver never even sends the native protocol startup message. Conversely, if a native protocol version is unsupported, fixing the TLS keystore will not solve it. Split tests into layers:

~~~text
TCP endpoint reachable?
  -> TLS handshake and hostname verification (if enabled)?
     -> CQL authentication (if enabled)?
        -> Native protocol startup/negotiation?
           -> Prepared CQL / serialization / paging?
~~~

Exact auth/startup frame ordering depends on protocol/driver, yet the core principle is **isolating the failing layer via logs/exceptions** rather than lumping everything into "Cassandra won't connect."

## 6. Spring Data Cassandra and Spring Boot: The BOM Is the Source of Truth

### 6.1. Spring Boot Versions Do Not Track Cassandra Versions

| Spring Boot | Spring Data release train | Spring Data Cassandra | Application JDK (guidance) |
|---|---|---|---|
| **3.5.x** | **2025.0.x** | **4.5.x** | Java **17+** per Spring Boot 3.x baseline |
| **4.0.x** | **2025.1.x** | **5.0.x** | Java **17+** and Spring Framework 7.x per Boot 4 generation |
| **Newer branches** | Check BOM of **exact Boot release** | Never infer from server branch | Check release notes/BOM and minimum JDK |

Example mappings documented in [Spring Data 2025.0 GA](https://spring.io/blog/2025/05/16/spring-data-2025-0-goes-ga/) and [Spring Data 2025.1.1](https://spring.io/blog/2025/12/12/spring-data-2025-1-1-2025-0-7-and-2024-1-13-released/). Patch versions change over time; this table shows **generational relationships**, not an exhaustive perpetual support list.

**Common trap:** hearing "Cassandra 5.0" and manually bumping `spring-data-cassandra` from 4.5 to 5.0 inside a **Spring Boot 3.5** project. Spring Data 5.0 belongs to a newer Spring generation; isolated overrides clash with Spring Framework, Spring Data Commons, and driver dependencies.

### 6.2. Maven Sample with Spring Boot BOM

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>cassandra-compat-lab</artifactId>
  <version>1.0.0</version>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
  </parent>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-data-cassandra</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
</project>
~~~

**Purpose:** let Boot manage Spring Data and transitive dependencies without injecting another `java-driver-core` coordinate before inspecting the dependency tree. This is an **educational sample**, not a recommendation to pin Boot 3.5.0 without security/patch updates. In real testing, use your team's approved patch release.

### 6.3. Inspect the Dependency Tree; Never Guess from `pom.xml`

~~~bash
# Maven commands inside the application project, not on a Cassandra node.
./mvnw -q help:effective-pom
./mvnw dependency:tree

# To locate Cassandra driver artifacts pulled transitively:
./mvnw dependency:tree -Dincludes=org.apache.cassandra:*,com.datastax.oss:*
~~~

Filter flags are only suggestions; Maven plugins handle wildcards/quotes differently across shells, so if filtering shows nothing, **read the full dependency tree**. Inspect driver core, query-builder/mapper, Netty, Jackson, Guava/shaded dependencies, and Spring Data Commons.

**A BOM does not automatically guarantee Cassandra 5.0 feature compatibility.** It guarantees a mutually consistent dependency set for the Spring release train. If the app needs vector/Cassandra 5 features, verify Spring Data mapping support and that the managed driver provides required codecs/features, then run integration tests. Override the driver only when Spring/Boot docs permit it and with full regression testing.

### 6.4. Spring Data Areas Requiring Verification

- **Repository/query methods**: derived queries, `@Query`, parameter binding, paging/limits, counts.
- **`CassandraTemplate`/`ReactiveCassandraTemplate`**: APIs, threading model, reactive backpressure, and exception translation.
- **Mapping**: `@Table`, `@PrimaryKey`, `@PrimaryKeyColumn`, UDTs/collections, `@Version`, and custom converters.
- **Session configuration**: Boot properties, auto-configuration, local datacenter, contact points, TLS/auth, retry policies.
- **Schema actions**: schema generation/validation flags; avoid auto `CREATE`/`DROP` in production during Spring major upgrades.
- **Observation/tracing**: Micrometer/metric IDs and OpenTelemetry/logging; observability changes can silence alerts or drop metrics.

When upgrading Spring Data across a major version, **read the dedicated Spring Data Cassandra migration guide**. Never just bump versions, compile, and skip repository integration tests.

## 7. Consolidated Matrix: Illustrating Practical Scenarios

**"Needs testing" cells do not mean unconditional support.** This table helps select lab scenarios, not certify arbitrary patches or features.

| Scenario | Cassandra server / node JDK | Java service / runtime | Driver / Spring stack | Expected native protocol | Preliminary assessment |
|---|---|---|---|---|---|
| **A — stay legacy** | 3.11 / JDK 8 | App JDK 8 | Driver 3.x, legacy Spring | Usually V4 | Fits migration baseline, not a long-term target |
| **B — move to Cassandra 4.0** | 4.0.2+ / JDK 11 | App JDK 17 | Driver 4.11+, Boot 3.5/Data 4.5 where supported | V5 when cluster/driver align | Can thoroughly test legacy apps; watch mapping/API shifts |
| **C — Cassandra 5.0 with Boot 3.5 app** | 5.0 / JDK 11 or 17 | App JDK 17 | Driver 4.19.x via planned deps, Boot 3.5/Data 4.5 | V5 | **Core features:** test; vector/SAI features: test per layer and BOM override |
| **D — upgrade Spring stack too** | 5.0 / JDK 17 | App JDK 17+ | Boot 4.0/Data 5.0 and matching BOM driver | V5 | Gains new Spring generation, widens change blast radius |
| **E — pin older protocol** | 5.0 / JDK 11/17 | App JDK 17 | Driver 4.x pinned to V4 | V4 | For investigation only where supported; never production default |

**What must not be inferred from this table:** running Boot 4.0/new driver against Cassandra 5.0 **does not guarantee** SAI is enabled, index schemas are right, feature flags are supported, or the cluster is ready to upgrade SSTable formats.

### 7.1. An Audit-Ready Compatibility Manifest Entry

~~~yaml
service: orders-api
environment: staging
server:
  cassandra_release: "5.0.x (fill actual patch)"
  node_jdk: "17.0.x (fill vendor/build)"
  topology: "dc1, RF=3 (example; measure actual)"
application:
  runtime_jdk: "17.0.x (fill vendor/build)"
  spring_boot: "3.5.x (actual BOM)"
  spring_data_cassandra: "4.5.x (resolved)"
  java_driver: "org.apache.cassandra:java-driver-core:4.19.x (if actually used)"
wire:
  negotiated_protocol: "V5 (read from session, never guessed)"
  tls: "CA/SAN valid; native port allowed"
features_under_test:
  - prepared_statements
  - pagination
  - ttl_and_writetime
  - udt_or_collection_mapping
  - LOCAL_QUORUM
  - vector_or_sai_if_used
approval:
  evidence: "test artifacts + SLO"
  rollback_owner: "runbook owner"
~~~

This manifest is strictly a **template**, not measured output. Record `V5` in the manifest **only after** observing it at runtime; use non-sensitive string keys and never store passwords or TLS private keys in YAML.

## 8. Pre- and Post-Upgrade Testing Matrix

### 8.1. Test Correctness Before Performance

| Group | Minimum integration tests | Easily missed bugs |
|---|---|---|
| Connectivity | TLS CA/SAN, CQL auth, local DC, CL, reconnects | Some nodes have bad certs or driver picks remote DC |
| CQL scalars | `int`, `bigint`, `uuid`, `timestamp`, `decimal`, `blob` | Serialization/timezone/large-number shifts |
| Collections/UDTs | `list/set/map`, frozen/non-frozen UDTs matching schema | Incompatible codecs/mappers |
| Prepared statements | Prepare, execute, schema changes, reconnect, and re-prepare | Stale prepare cache bugs after rolling upgrade |
| Paging | Multi-page reads with small page sizes and large row sets | Reading only first page; reusing paging state on wrong query |
| Consistency | `LOCAL_QUORUM`/`LOCAL_ONE` under real RF/DC, temp node Down | Misconfigured CL/local DC causing timeouts |
| TTL/tombstones | `TTL()`, `WRITETIME()`, `DELETE`, expiration, repair policy | Expired records resurrecting due to weak tests |
| LWT/conditional writes | `IF NOT EXISTS`, `IF column = ...` where used | Changed CAS semantics, exceptions, or retries |
| Schema migrations | ALTER/UDT/indexes, schema agreement across mixed nodes | Older nodes unable to parse new schema |
| Cassandra 5 features | Vector types/functions, SAI, advanced codecs per workload | Driver connects yet fails to bind/deserialize feature |
| Performance | p50/p95/p99, throughput, error/retry rates, GC/CPU | Pretty p50 masking spiking p99 and timeouts |

**Never enable Cassandra 5 features during mixed-version windows** if older nodes can participate in reads/writes without understanding new schemas/types/queries. Wait until all nodes reach the target version, metadata stabilizes, and driver/Spring tests pass completely.

### 8.2. Two Separate Server vs. App Test Suites

**Server upgrade tests**

~~~text
[ ] All nodes Up/Normal, RF and DC/rack accurate
[ ] No major GC/OOM, abnormal compaction/streaming backlogs
[ ] Schema agreement, reads/writes at declared CLs
[ ] SSTables/tombstones/repairs cause zero data errors
[ ] SSTable format changes or new features deferred
~~~

**Application upgrade tests**

~~~text
[ ] App JDK and dependency tree match BOM
[ ] Actual protocol and driver version captured
[ ] Prepared CQL, paging, UDTs/collections, and TTLs execute cleanly
[ ] TLS/auth/authorization/connection pools/retries operational
[ ] Spring repositories/templates + mappings yield unchanged results
[ ] End-to-end p99 and timeouts <= approved SLOs
~~~

When upgrading only the Cassandra server, ideally run **an application canary keeping the current driver** alongside a canary with the new driver to isolate variables. If you bump app JDK, Spring Boot, and driver **simultaneously** and tests fail, root-causing becomes far harder.

## 9. Java Driver Lab: Measuring Protocol, CL, Prepared Statements, and Paging

### 9.1. Lab Environment

Example using Cassandra 4.1 or 5.0 in a **lab cluster** with actual DC `dc1` and RF=3 when three nodes exist; otherwise adjust RF/CL to match real topology. Check:

~~~bash
java -version
nodetool status
nodetool version
nodetool describecluster
~~~

In `cqlsh`:

~~~sql
SELECT release_version, cql_version FROM system.local;

CREATE KEYSPACE IF NOT EXISTS compat_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS compat_lab.events_by_device_day (
  device_id uuid,
  event_day date,
  event_time timestamp,
  event_id uuid,
  payload text,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

INSERT INTO compat_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, payload)
VALUES (
  d654b0fe-7357-497f-8db4-59b165d58a0f,
  '2026-11-21',
  '2026-11-21T08:15:00Z',
  80aaeac3-1f11-4f66-877f-d9ccfca2216d,
  'compat-sample'
);
~~~

**Do not benchmark performance with one row:** this lab tests syntax/feature paths. Assessing latency requires multiple token ranges, varied partition sizes, realistic read/write mixes, load, and representative data distributions. `IF NOT EXISTS` does not update an existing schema; use `DESCRIBE TABLE` to verify against intended DDL.

### 9.2. Java Driver 4.x: Session Probe

This snippet assumes `CqlSession session` was created using the app's security config and proper local DC. The goal is **verifying protocol + prepared/paging**, without hard-coding passwords:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

void verifyCompatibility(CqlSession session) {
    System.out.println("Protocol = " +
            session.getContext().getProtocolVersion());

    Row info = session.execute(
            "SELECT release_version FROM system.local").one();
    if (info != null) {
        System.out.println("Contacted server release = " +
                info.getString("release_version"));
    }

    PreparedStatement ps = session.prepare(
        "SELECT event_time, event_id, payload " +
        "FROM compat_lab.events_by_device_day " +
        "WHERE device_id = ? AND event_day = ? " +
        "AND event_time >= ? AND event_time < ? LIMIT ?");

    BoundStatement stmt = ps.bind(
            UUID.fromString("d654b0fe-7357-497f-8db4-59b165d58a0f"),
            LocalDate.of(2026, 11, 21),
            Instant.parse("2026-11-21T00:00:00Z"),
            Instant.parse("2026-11-22T00:00:00Z"),
            100)
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setPageSize(20);

    long startedNs = System.nanoTime();
    ResultSet rs = session.execute(stmt);
    int rows = 0;
    for (Row row : rs) {
        UUID eventId = row.getUuid("event_id");
        Instant eventTime = row.getInstant("event_time");
        if (eventId == null || eventTime == null) {
            throw new IllegalStateException("Unexpected null key fields");
        }
        rows++;
    }
    double elapsedMs = (System.nanoTime() - startedNs) / 1_000_000.0;
    System.out.println("Rows=" + rows + ", full-consumption-ms=" + elapsedMs);
}
~~~

Key points here:

- `LOCAL_QUORUM` requires valid RF/DC; if a 1-node lab sets RF=3, results are meaningless/unavailable.
- `setPageSize(20)` is only a target page size, not a guarantee every page holds exactly 20 rows.
- The loop iterates **all pages** if present; latency differs from first-page-only timing.
- `SELECT system.local` returning one node release does not guarantee a uniform cluster.
- Run across **different driver/Spring BOM versions** on identical data/CLs to catch API and behavioral changes.

### 9.3. Testing Protocol v4 vs. v5

Create two identical lab configs differing only in:

~~~hocon
# A: default — DO NOT set advanced.protocol.version.
datastax-java-driver {
  basic.load-balancing-policy.local-datacenter = "dc1"
}
~~~

~~~hocon
# B: pinned lower, ONLY when driver/server docs allow.
datastax-java-driver {
  basic.load-balancing-policy.local-datacenter = "dc1"
  advanced.protocol.version = V4
}
~~~

Run the same simple query suite to check if option B works **with required features**. If a new feature requires V5 or new codecs, case B may fail; that is a vital matrix finding, not an excuse to "disable the feature" in production.

Never pin protocols to mask an incomplete Cassandra upgrade or an overly old driver. After testing, return production to **automatic negotiation** unless there is an approved reason otherwise.

## 10. Rolling Upgrade: Change Order and Approval Gates

### 10.1. Characteristics of Node-by-Node Upgrades

Cassandra is a multi-replica distributed system. Briefly, old and new nodes can coexist. A rolling upgrade aims to keep RF/CL satisfied while pulling nodes one at a time, yet **no promise exists that arbitrary major versions can mix freely**.

Follow **release-documented upgrade paths**, never skipping majors/minors just because a package starts. For paths like 3.x → 4.x → 5.x, read release-specific upgrade notes and mandatory intermediate steps; never attempt multiple major jumps together without official guidance.

### 10.2. Verifiable Sequence

~~~mermaid
flowchart TD
    A["Inventory release/JDK/driver/Boot/BOM/protocol"] --> B["Lock upgrade path and backup/restore drill"]
    B --> C["Upgrade driver/app canary compatible with both server generations"]
    C --> D["Staging mixed-version cluster + feature regression"]
    D --> E["Upgrade canary node; monitor RF/CL/latency/repair"]
    E --> F{"Canary meets SLOs with zero data errors?"}
    F -->|No| G["Halt / evaluate rollback or roll-forward"]
    F -->|Yes| H["Roll remaining nodes/safe batches"]
    H --> I["Uniform cluster, schema agreement, repair/compaction stable"]
    I --> J["Further upgrade Spring/driver if needed, re-test"]
    J --> K["Only last: enable new CQL / SAI / vector features"]
~~~

**Focus on invariants:** never break schemas older nodes cannot parse, never tweak protocol settings arbitrarily, never drop a DC below replica counts required by app CLs, and never delete snapshots before a rollback plan is locked.

### 10.3. What Must Wait Until the Whole Cluster Reaches Target

- Creating data types/vectors/functions/indexes understood only by the new version.
- Converting SSTables to formats/features unreadable by old nodes; check compatibility before running `upgradesstables` or enabling rewrite options.
- Unnecessary schema/replication/compaction strategy changes in the same maintenance window.
- Removing untested legacy app libraries/drivers while rollback still depends on them.
- Enabling protocols or cipher suites incompatible between clients and older endpoints.

**Downgrades require extreme caution:** once a new server writes new metadata/SSTable formats or schemas, never assume "reinstalling the old binary" reverts cleanly. Sometimes **rolling forward** to a patched release or restoring from release-compatible backups is safer. Establish the strategy before deploying.

### 10.4. Clear Stop Conditions

| Signal | Operational decision |
|---|---|
| Nodes stuck Down/Joining abnormally, DC lacks replicas | **Halt rollout**, inspect topology/streaming |
| Read/write timeouts rise, p99 breaches SLO | Halt, check CL/retries/client pools, CPU/disk/GC |
| Driver hits protocol/codec/prepare errors | Stop app canary or affected server step; never enable new features |
| Prolonged schema disagreement | Defer DDL and next upgrade step; resolve agreement |
| Compaction/repair/streaming backlog grows unchecked | Throttle rollout, wait for headroom |
| Auth/TLS failures appear on specific nodes | Check truststores/certs/SANs and cluster-wide driver routing |
| Missing data or wrong TTL/tombstone/LWT behavior appears | Halt, investigate correctness and recovery strategy |

Never press on just because "most requests still succeed": with RF=3 and `CL=QUORUM`, one replica can be broken while apps still get responses even as availability margin collapses.

## 11. Spring Data Cassandra Practice: Post-Upgrade Repository Testing

### 11.1. Simple Repository Model

With Spring Boot/Spring Data properly configured for Cassandra, an example mapping:

~~~java
import java.util.UUID;
import org.springframework.data.annotation.Id;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("customers_by_id")
public class CustomerRow {
    @Id
    private UUID id;
    private String displayName;

    public UUID getId() { return id; }
    public void setId(UUID id) { this.id = id; }
    public String getDisplayName() { return displayName; }
    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
~~~

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface CustomerRepository
        extends CassandraRepository<CustomerRow, UUID> {
}
~~~

Corresponding CQL schema in **lab**:

~~~sql
CREATE TABLE IF NOT EXISTS compat_lab.customers_by_id (
    id uuid PRIMARY KEY,
    display_name text
);
~~~

**Note on naming strategy:** Spring Data maps Java field names to column names by convention. To ensure `displayName ↔ display_name` across versions/conventions, specify `@Column("display_name")` or verify real mappings. In production projects, never allow blind auto-DDL schema generation during Spring Data major upgrades.

### 11.2. Tests to Keep Stable

- `save()`/`findById()`/`deleteById()` preserve baseline semantics; avoid repository ID generators causing key collisions.
- `@Column`/`@PrimaryKeyColumn` for composite partition/clustering keys map accurately.
- Converters for `Instant`, `LocalDate`, `BigDecimal`, UDTs, and collections preserve meaning.
- Repository queries with `ALLOW FILTERING`, `LIMIT`, or ordering are not treated as passing merely because they compile.
- Transaction annotations do not make Cassandra ACID across partitions; LWT/conditional semantics still require dedicated tests.
- Reactive streams preserve backpressure and error propagation matching the driver/Spring generation.

If upgrading Spring Boot 4 and Spring Data 5 together, re-test auto-configuration, dependency injection, logging/metrics, test slices, actuator health, and TLS/auth chains explicitly; **this is a Java platform upgrade**, not just Cassandra.

## 12. Experiment Matrix, Conclusions, and Checklist

### 12.1. Result Matrix to Fill with Measured Data

| Case | Server/node JDK | App JDK/Boot/Data | Driver/groupId | Measured protocol | Query/feature | p99/timeouts | Pass/Fail |
|---|---|---|---|---|---|---|---|
| Baseline | _fill_ | _fill_ | _fill_ | _fill_ | CQL + prepared | _fill_ | _fill_ |
| New server canary | _fill_ | _keep baseline_ | _keep baseline_ | _fill_ | CL/TLS + paging | _fill_ | _fill_ |
| New driver canary | _keep server_ | _fill_ | _fill_ | _fill_ | UDT/codecs + prepare | _fill_ | _fill_ |
| Full server upgraded | _fill_ | _keep app_ | _fill_ | _fill_ | Repair/stream/read-write | _fill_ | _fill_ |
| New feature canary | _fill_ | _fill_ | _fill_ | _fill_ | SAI/vector if used | _fill_ | _fill_ |

Never fill in hypothetical numbers. A test running `SELECT release_version` only checks that one node replies—it **cannot** prove p99, repair, schema agreement, or feature completeness.

### 12.2. Approval Checklist

- [ ] Inventoried **node JDK** and **application JDK** separately (vendor/build/patch).
- [ ] Locked supported Cassandra upgrade path without arbitrary major jumps.
- [ ] Recorded Spring Boot and Spring Data release trains/BOMs plus the **resolved** dependency tree.
- [ ] Confirmed zero duplicate `java-driver-core` jars from different groupIds on the classpath.
- [ ] Distinguished Java Driver 3.x vs. 4.x APIs if migrating clients.
- [ ] Recorded actual native protocol via `session.getContext().getProtocolVersion()`.
- [ ] Tested prepared CQL, paging, UDTs/collections, TTLs, CLs, and TLS.
- [ ] Enabled new Cassandra features only after full cluster, driver, and mappers support them.
- [ ] Prepared canaries, stop conditions, snapshots/backups, restore drills, and roll-forward/rollback plans.
- [ ] Monitored per-DC/node metrics, p50/p95/p99, timeouts/retries, and stream/repair backlogs.
- [ ] Completed repository/template tests and Java runtime tests before shifting full traffic.
- [ ] Archived actual manifests, release notes, QA results, and approval decisions.

## 13. Applied Exercises

### Exercise 1 — Two Different JDKs

A Cassandra 5.0 cluster runs JDK 11; a Spring Boot 3.5 service runs JDK 17 with Java Driver 4.x. Must the node JDK change to 17 for the service to connect?

**Answer:** No. Node and app JDKs are independent; the native protocol bridges both processes. Verify Cassandra/driver patches, negotiated protocol, TLS/auth, and API/feature compatibility—never force identical JVM majors unnecessarily.

### Exercise 2 — Connects Fine, Yet Vectors Fail

A service using driver 4.11 connects to Cassandra 5.0 and reads scalar CQL cleanly, yet fails to bind vector values. The deployment team says "Cassandra 5 is running, so the driver definitely supports it." True or false?

**Answer:** False. Driver 4.11 supports protocol V5, yet **that does not equal full Cassandra 5.0 feature support**. You need a driver patch supporting vector types, codecs, Spring Data mapping, and feature tests against real schemas; driver 4.19 is a key reference milestone.

### Exercise 3 — Upgrading Spring Data Off the Wrong Release Train

A Boot 3.5 app uses Spring Data Cassandra 4.5 via the BOM. A developer manually sets `spring-data-cassandra:5.0.x` without upgrading Boot. What is the risk?

**Answer:** Spring Data 5.0 targets a newer Spring Framework/Boot generation, causing binary incompatibilities, broken auto-configuration, and classpath conflicts. Stick to the Boot BOM or intentionally upgrade the whole platform and test.

### Exercise 4 — Mixing Driver Artifacts

The classpath contains both `com.datastax.oss:java-driver-core:4.17.0` and `org.apache.cassandra:java-driver-core:4.19.0`. Is this a valid way to support all servers?

**Answer:** No. Two closely related artifacts cause duplicate classes and transitive dependency conflicts. Clean up the dependency tree and keep a single supported driver family/version.

### Exercise 5 — Mixed-Version Rolling Window

A cluster mixes Cassandra 3.11 and 4.x along a supported upgrade path. A developer immediately creates schemas using a 4.x-only feature and routes new services to it. Why is this dangerous?

**Answer:** Older nodes do not understand the new metadata/features, and routing/protocols may negotiate lower. Keep schemas and feature sets mutually compatible during mixed operation; wait until every node stabilizes before enabling features and testing.

### Exercise 6 — Reading Protocol from the Right Source

Java Driver 4.x prints `V4` even though one Cassandra 4.x node is Up/Normal. Can you conclude the driver "does not support Cassandra 4"?

**Answer:** Not yet. The cluster may still contain 3.x nodes, the driver patch may be old, the protocol may be pinned, or the session chose a compatible level for mixed-version operation. Check node versions, driver patch, config overrides, logs, and test auto-negotiation.

## 14. References

1. Apache Cassandra Documentation — [Support for Java (Cassandra 5.0: JDK 11/17)](https://cassandra.apache.org/doc/stable/cassandra/reference/java17.html).
2. Apache Cassandra Documentation — [Support for Java 11 (Cassandra 4.x)](https://cassandra.apache.org/doc/4.1/cassandra/getting_started/java11.html).
3. Apache Cassandra Documentation — [What's new in Cassandra 5.0](https://cassandra.apache.org/doc/stable/cassandra/new/): vectors, SAI, trie SSTables, JDK 17.
4. Apache Java Driver 4.19 — [Native Protocol](https://apache.github.io/cassandra-java-driver/4.19.0/core/native_protocol/): V3–V5, negotiation, and protocol overrides.
5. Apache Java Driver 4.19 — [Upgrade Guide](https://apache.github.io/cassandra-java-driver/4.19.0/upgrade-README/): Driver 3 → 4, production-ready V5 milestone, and API changes.
6. Apache Java Driver — [Repository and Maven coordinates](https://github.com/apache/cassandra-java-driver): `org.apache.cassandra` groupId for Apache-maintained drivers.
7. Spring Data — [2025.0 release: Spring Data Cassandra 4.5 and Spring Boot 3.5](https://spring.io/blog/2025/05/16/spring-data-2025-0-goes-ga/).
8. Spring Data — [2025.1 release: Spring Data Cassandra 5.0](https://spring.io/blog/2025/12/12/spring-data-2025-1-1-2025-0-7-and-2024-1-13-released/).
9. Spring Data Cassandra — [Reference Documentation](https://docs.spring.io/spring-data/cassandra/reference/): repositories, mapping, configuration, migration.
10. Spring Boot — [3.5 Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html) and [4.0 Managed Dependency Coordinates](https://docs.spring.io/spring-boot/4.0/appendix/dependency-versions/coordinates.html): verifying BOM-resolved library versions.
11. Apache Cassandra Documentation — [Operations and Upgrade Guidance](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/): procedures, version transitions, and rollout limits.
