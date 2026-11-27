# Choosing Compatible Cassandra, JDK, and Driver Versions

## 1. Objectives and Context

Apache Cassandra is a **distributed wide-column** database. To practice topics such as partition keys, query-driven table design, replication, consistency levels, compaction, repair, and Java application connectivity, you first need to choose a set of versions that can run together. A lab exercise that fails due to picking the wrong JDK or an incompatible driver will cause learners to mistake environment errors for CQL or Cassandra architecture errors.

After this lesson, you will be able to:

1. Distinguish between the **Cassandra server**, **server JDK**, **application build/runtime JDK**, and **Java driver** versions.
2. Select a pinned, suitable version stack for learning Cassandra 5.0 and Java.
3. Start a Cassandra node with Docker, verify the server version, node status, and datacenter name.
4. Connect from Java using the Apache Cassandra Java Driver 4.x, read data via CQL, and troubleshoot common compatibility errors.
5. Record version evidence to reproduce lab results.

> **Scope:** a local learning environment with a **single node**. A single-node example helps verify CQL and driver connectivity, but **cannot simulate** node failures, replica mechanisms, or the consistency guarantees of a multi-node cluster. Those topics require a multi-node environment in subsequent labs.

## 2. Four Versions to Distinguish

```
Development machine
  ├─ Application JDK (e.g., 17)
  └─ Java application
       └─ Apache Cassandra Java Driver 4.19.4
            │  CQL over native protocol / TCP 9042
            ▼
       Cassandra server 5.0.9 (container)
            └─ JVM running Cassandra (inside the container)
```

| Component | Role | What to verify |
|---|---|---|
| Apache Cassandra server | Stores data, executes CQL, manages nodes and replication | Version branch `5.0.x` or `4.1.x`, functional and data format changes across releases |
| Server JDK/JVM | Runs the Cassandra process | Must be one of the Java versions **supported by that Cassandra branch**; do not assume it equals the application JDK |
| Application JDK | Compiles and runs the Java program connecting to Cassandra | New enough for source code and driver libraries; consistent `JAVA_HOME`, compiler version, and runtime |
| Cassandra Java Driver | Manages connections, discovery, load balancing, prepared statements, retries, and CQL execution | Support for the Cassandra version, native protocol, CQL data types/features, and application JDK |

**Common pitfall:** driver 4.x **does not mean** it only runs with Cassandra 4.x. The major version of the server and the driver library are two separate release lines; you must check the compatibility documentation for both. Similarly, `java -version` on your local machine does not tell you which JVM Cassandra inside Docker is using.

When using Docker, the container has its own runtime for Cassandra. The development machine only needs Docker to run the server; **a local JDK is still required** if you compile and run the Java application on that machine.

## 3. Recommended Version Stack for the Practice Lab

### 3.1. Locking a Reproducible Stack

As of **2026-11-21**, the reference version stack for this lesson is:

| Component | Chosen Version | Rationale |
|---|---|---|
| Cassandra server | **5.0.9** | Stable release in the 5.0 branch, usable as a unified baseline for the course |
| Docker image | **`cassandra:5.0.9`** | Pins the server version instead of automatically drifting with the `latest` tag |
| Java for Cassandra | **Java 11 or 17** per Cassandra 5.0 documentation | When using the official image, the runtime is bundled in the image; observable via a command inside the container |
| Java for application | **JDK 17 (LTS)** | Unified choice for Java code examples and compatible with Java Driver 4.19.4 |
| Apache Cassandra Java Driver | **4.19.4**, module `java-driver-core` | 4.x driver from the Apache project, supports Cassandra 2.1+ and connects to Cassandra 5.0; uses the current Maven artifact |
| Maven | A Maven 3.9.x version compatible with JDK 17 | Used to resolve dependencies and run the sample program; not a Cassandra version |

Patch numbers may change after the authoring date. For labs, **pin exact version numbers** in the image and build files so everyone gets identical behavior; when upgrading, review the release notes and re-run all connection checks. Any newer version only becomes the standard stack after verification—never assume compatibility.

**Regarding JDK 17 and Cassandra 5.0:** official documentation states that Cassandra 5.0 binaries are built with Java 11 and can run on either Java 11 or Java 17. If you **build the server from source using Java 17**, that artifact will not run backwards on Java 11 due to a different bytecode level. This is a constraint on the **server runtime**, not proof that the Java application must use the same Java version as the server.

**Regarding the driver:** the current Apache driver Maven coordinate is `org.apache.cassandra:java-driver-core`. Many older tutorials still use `com.datastax.oss:java-driver-core`. Do not mix versions from both artifact groups on the same classpath. Even though the groupId moved to Apache, common 4.x driver API imports remain `com.datastax.oss.driver.api...`.

### 3.2. When Should You Choose Different Versions?

| Scenario | Decision | Rationale |
|---|---|---|
| Starting to learn CQL and writing a new Java app | Cassandra 5.0.9 + application JDK 17 + driver 4.19.4 | Matches the lesson examples and allows exploring 5.0 branch features |
| Need to mirror a system running Cassandra 4.1 | Pick a specific 4.1 patch (e.g., 4.1.12), check server JDK per **4.1** docs, keep driver 4.19.4 if used features are supported | A newer driver does not add new features to an older server; you must test the CQL queries in use |
| Existing Java 11 application | Driver 4.x can be used on Java 11, but verify the exact artifact version; lesson examples still use JDK 17 | Application JDK is an independent compatibility axis from the server JDK |
| Want to use a new feature, such as `vector` type in Cassandra 5.0 | Check both the server version **and** corresponding driver feature support | A successful connection does not prove all data types and APIs are supported |
| Upgrading server or driver to a new major version | Read release notes, upgrade guide, verify runtime requirements, then run smoke tests | Network compatibility, API compatibility, and feature compatibility are distinct concepts |

**Examples of invalid combinations to reject immediately:** Cassandra 5.0 + Java 8 server JVM; building the server with JDK 17 and running that bytecode on JVM 11; compiling the application with `--release 17` and running on Java 11; declaring driver 3.x by mistake while copying 4.x APIs. Moreover, a successful TCP handshake between server and driver is **insufficient** to conclude full workload compatibility.

## 4. Pre-Installation Version Selection Workflow

Follow this order when setting up a project or planning an upgrade:

1. **Define the lab goal:** basic CQL or Cassandra 5.0 features, single or multi-node, and whether you need to match an existing system's version.
2. **Pin the server branch and patch:** pick an exact published release; check the [Cassandra download/releases page](https://cassandra.apache.org/_/download.html), rather than just using the `5.0` branch name.
3. **Verify the server JDK:** cross-check the Java support documentation for the **same Cassandra branch**; for tarball/RPM/DEB installs, check the process `JAVA_HOME`; for Docker, inspect the Java version inside the image.
4. **Select the application JDK and driver:** check driver documentation, minimum JDK, and specific CQL features; pin exact versions in `pom.xml` or `build.gradle`.
5. **Validate before writing business logic:** confirm the server is `UN` (Up/Normal), run `SELECT release_version` via `cqlsh` and the Java driver, and record the actual datacenter, host/port, dependencies, and JDK.

For multi-node environments, beyond version numbers you must also verify rolling upgrade rules, inter-node compatibility, replication, native protocol, and rollback paths according to the documentation for that specific version pair. Do not use this lab selection table as a production upgrade plan.

## 5. Standing Up Cassandra 5.0.9 with Docker

### 5.1. Prerequisites

- Docker Engine or Docker Desktop capable of running Linux containers; sufficient CPU/RAM for Cassandra to start and execute queries.
- JDK 17 installed for the Java application; Maven ready if running the Java connectivity section.
- Port **9042** free on the host. This is the Cassandra native transport port for CQL; **7199** is for JMX and **7000/7001** are for inter-node communication depending on configuration, not for client CQL traffic.

The following Docker commands can be run in any terminal supporting the Docker CLI. You do not need Java installed on the host just to start the container.

### 5.2. Pulling the Image and Starting the Node

```bash
docker pull cassandra:5.0.9

docker run -d --name cassandra-lab \
  -p 127.0.0.1:9042:9042 \
  -e CASSANDRA_CLUSTER_NAME=cassandra-lab \
  -e CASSANDRA_ENDPOINT_SNITCH=GossipingPropertyFileSnitch \
  -e CASSANDRA_DC=datacenter1 \
  -e CASSANDRA_RACK=rack1 \
  cassandra:5.0.9
```

Configuration explanation:

- `--name cassandra-lab` assigns a fixed container name for use with `docker exec`.
- `127.0.0.1:9042:9042` binds the CQL port only to the local loopback interface. This is a **learning** example, not a configuration for external network access.
- `CASSANDRA_CLUSTER_NAME` sets the cluster name; `CASSANDRA_DC` and `CASSANDRA_RACK` define node topology.
- `GossipingPropertyFileSnitch` instructs Cassandra to read datacenter/rack settings from the corresponding configuration. Setting `CASSANDRA_DC` alone without an appropriate snitch may fail to produce the expected datacenter.
- `--rm` is omitted so you can inspect logs if startup fails; explicit cleanup commands are provided at the end of the lesson.

Cassandra takes longer to start than typical HTTP services. `docker run -d` returning a container ID **does not mean** CQL is ready. Verify with:

```bash
docker ps --filter name=cassandra-lab
docker logs cassandra-lab
docker exec cassandra-lab nodetool status
```

When the node is healthy, `nodetool status` displays a row with state **`UN`** (Up/Normal), typically under `Datacenter: datacenter1`. If it shows `UJ` (Up/Joining), startup is still in progress; if the command fails to connect to JMX or CQL, inspect the logs and re-check.

### 5.3. Verifying Server Version, JVM, and Datacenter

```bash
# Actual Cassandra version running:
docker exec cassandra-lab nodetool version

# JVM of the process inside the container:
docker exec cassandra-lab java -version

# Connect using cqlsh bundled with the server:
docker exec cassandra-lab cqlsh -e \
  "SELECT release_version, data_center, cluster_name FROM system.local;"
```

Expected output: `release_version` is `5.0.9`, `data_center` equals `datacenter1`, and `cluster_name` is `cassandra-lab`. Actual server/JDK versions must be taken from **command output**, not inferred from image tags or the host's JDK. If `cqlsh` initially reports *Connection refused*, check `nodetool status` and logs because the container may not be ready yet.

Test a minimal CQL workflow on a single node:

```bash
docker exec -it cassandra-lab cqlsh
```

```sql
CREATE KEYSPACE IF NOT EXISTS lab
WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

CREATE TABLE IF NOT EXISTS lab.events_by_user (
    user_id text,
    event_time timestamp,
    event_type text,
    PRIMARY KEY ((user_id), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);

INSERT INTO lab.events_by_user (user_id, event_time, event_type)
VALUES ('u-001', '2026-11-21T08:00:00Z', 'login');

SELECT user_id, event_time, event_type
FROM lab.events_by_user WHERE user_id = 'u-001';
```

Here `user_id` is the **partition key** and `event_time` is the **clustering column**: filtering by partition key aligns with Cassandra's access model. `SimpleStrategy` with replication factor 1 is strictly for single-node labs; when studying multi-datacenter replication, consider `NetworkTopologyStrategy` and the actual node count.

## 6. Connecting with Java Driver 4.19.4

### 6.1. Checking Application Java and Maven

Run **on the machine that will execute the Java application**, not inside the container:

```bash
java -version
javac -version
mvn -version
```

Both `java` and `javac` should show **17.x**; `mvn -version` must indicate that Maven is running on Java 17. On machines with multiple JDKs, `JAVA_HOME` and `PATH` must point to the exact version the project uses. If Maven reports Java 11 while the code compiles for release 17, fix the JDK used by Maven first.

### 6.2. Creating a Minimal Maven Project

Example layout:

```text
cassandra-java-lab/
├── pom.xml
└── src/main/java/LabCassandra.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example.cassandra</groupId>
    <artifactId>cassandra-java-lab</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.cassandra</groupId>
            <artifactId>java-driver-core</artifactId>
            <version>4.19.4</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Only `java-driver-core` is needed for basic connectivity; Query Builder and Mapper are **separate optional** modules. Keep the exact same version across all driver modules if you add them later.

### 6.3. Connection Verification Program

`src/main/java/LabCassandra.java`:

```java
import java.net.InetSocketAddress;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.Row;

public class LabCassandra {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("datacenter1")
                .build()) {

            Row row = session.execute(
                    "SELECT release_version, data_center FROM system.local").one();
            if (row == null) {
                throw new IllegalStateException("system.local not found");
            }

            System.out.println("Cassandra: " + row.getString("release_version"));
            System.out.println("Datacenter: " + row.getString("data_center"));
        }
    }
}
```

In the directory containing `pom.xml`, run:

```bash
mvn compile exec:java -Dexec.mainClass=LabCassandra
```

Expect to see Cassandra version `5.0.9` and `Datacenter: datacenter1` (along with Maven/driver log lines). Because the application runs **on the host**, the contact point is `127.0.0.1:9042` published in the Docker step. If the application also runs inside a container, `127.0.0.1` refers to the application container itself: you must use the service name/address within the **same Docker network**, and verify the address Cassandra advertises to the driver.

Important details:

- `CqlSession` manages connections and resources; real applications typically use **one shared session per cluster** rather than creating a new one per query. `try-with-resources` is appropriate for a short verification script.
- `withLocalDatacenter("datacenter1")` must match the actual datacenter name returned by Cassandra; names are **case-sensitive**. Whenever explicit contact points are configured, the driver requires a local datacenter.
- The driver communicates via the **CQL native protocol**, not JDBC as with relational databases. CQL has SQL-like syntax, but table design and queries depend on partition/clustering keys.
- A successful connection only proves the basic CQL path works. TLS, authentication, consistency levels, retry policies, and advanced data types must be tested separately when used by a project.

## 7. Troubleshooting Version or Configuration Mismatches

| Symptom | Possible Cause | Verification and Resolution |
|---|---|---|
| `UnsupportedClassVersionError` | Bytecode compiled with a newer JDK than the running JVM | Compare `java -version`, `javac -version`, `mvn -version`, and `maven.compiler.release`; for self-built servers, check build and runtime JDKs |
| `NoNodeAvailableException` or driver fails to build session | Node is not `UN`, port 9042 is not published, wrong address, or container/network unreachable | Run `docker ps`, `docker logs`, `nodetool status`, `cqlsh`; verify `127.0.0.1:9042` from where the program executes |
| Driver local datacenter error | `withLocalDatacenter` does not match server DC name | Run `SELECT data_center FROM system.local;`, fix the value paying attention to case sensitivity |
| `ClassNotFoundException` / `NoClassDefFoundError` | Missing dependency, 3.x/4.x driver mix-up, mixed artifacts or classpath issues | Inspect `pom.xml`, use a consistent `org.apache.cassandra` 4.19.4 set, run `mvn dependency:tree` |
| New CQL/data type fails despite successful connection | Feature absent in the running Cassandra branch or unsupported by the driver API | Check server version, feature docs, and driver release notes; test directly with a sample query/codec |
| `AuthenticationException`, SSL/handshake error | Server has auth or TLS enabled while the application is unconfigured | Check cluster security settings, supply environment credentials/truststore; never disable security on a real system to pass a test |
| Node exits unexpectedly or `nodetool` fails | Insufficient memory, incompatible JVM flags, low disk space, or port conflict | Check `docker logs`, RAM limits/availability, and the JVM version inside the container |

**Distinguishing three levels of verification:**

1. **Server running:** `nodetool status` shows `UN`.
2. **Connectivity working:** `cqlsh` and Java can read `system.local`.
3. **Required features working:** partition-key queries succeed, data types are validated, and consistency/replication configurations are verified when moving to a multi-node cluster.

Do not infer level 3 solely from level 2 passing. In production environments, a healthy cluster also requires monitoring metrics, latency, compaction, repair, topology, and failure behavior.

## 8. Recording Configuration, Cleanup, and Self-Check Exercises

### 8.1. Environment Record Template

Record your **actual** results in your own README or lab log:

| Item | Example Value |
|---|---|
| Check date | `2026-11-21` |
| Docker image | `cassandra:5.0.9` (optionally include the image digest for full pinning) |
| `nodetool version` / `system.local.release_version` | `5.0.9` |
| JVM inside Cassandra container | Output of `docker exec cassandra-lab java -version` |
| JDK/Javac/Maven on application machine | Output of `java -version`, `javac -version`, `mvn -version` |
| Maven dependency | `org.apache.cassandra:java-driver-core:4.19.4` |
| Contact point / local DC | `127.0.0.1:9042` / `datacenter1` |
| Connection test result | `cqlsh` and Java print expected version and datacenter |

When two machines both run Cassandra `5.0.9` yet exhibit different errors, this log helps isolate differences in JDK, image digest, ports, driver, datacenter, and network setup.

### 8.2. Stopping and Removing the Lab Container

```bash
docker stop cassandra-lab
docker rm cassandra-lab
```

In this example **no data volume was created**, so removing the container deletes all lab data. If you need to persist state across sessions, attach a volume for `/var/lib/cassandra` and record the exact image/volume in use; only remove the volume once you decide to discard the lab data.

### 8.3. Self-Check Scenarios

1. A team installs Cassandra 5.0 via Docker, and their Java application runs on JDK 17. Do they need to manually install JDK 17 inside the container? State the command to inspect the server's JVM before answering.
2. Maven reports `release version 17 not supported`, while `java -version` in the terminal shows Java 17. Which command shows the JDK **that Maven actually uses**, and where should it be fixed?
3. `cqlsh` inside the container queries successfully, but the Java driver on the development machine reports it cannot connect. Walk through checks in the order **container `UN` → published port → contact point address → local datacenter**.
4. Driver 4.19.4 connects to a Cassandra 4.1 cluster. Can you conclude the application can use every feature exclusive to Cassandra 5.0? Explain the difference between protocol compatibility and feature support.
5. A teammate changes the Docker tag from `cassandra:5.0.9` to `cassandra:latest`. What might change upon recreating the container, and how can you trace the difference?

**Completion criteria:** learners obtain `nodetool status = UN`, record `release_version` and `data_center` via `cqlsh`, compile/run the Java 17 program with driver 4.19.4, and document the exact server/JDK/driver versions. This establishes the verification baseline before moving on to replication, consistency, compaction, repair, and node failure testing.

## 9. Official References

- [Apache Cassandra — Download and Releases](https://cassandra.apache.org/_/download.html): look up released Cassandra and Java Driver versions.
- [Apache Cassandra 5.0 — Support for Java](https://cassandra.apache.org/doc/latest/cassandra/reference/java17.html): build/runtime JDK matrix for Cassandra 5.0.
- [Apache Cassandra — Installing Cassandra](https://cassandra.apache.org/doc/latest/cassandra/installing/installing.html): installation prerequisites and Java checks.
- [Apache Cassandra — Quickstart](https://cassandra.apache.org/doc/latest/cassandra/getting-started/cassandra-quickstart.html): Docker and `cqlsh` usage.
- [Docker Official Image — cassandra](https://hub.docker.com/_/cassandra): tags and environment variables such as `CASSANDRA_DC`, `CASSANDRA_ENDPOINT_SNITCH`.
- [Apache Cassandra Java Driver — README](https://github.com/apache/cassandra-java-driver): compatibility, dependency coordinates, and Java versions.
- [Apache Cassandra Java Driver — Core quick start](https://apache.github.io/cassandra-java-driver/4.19.0/core/): `CqlSession` API, contact points, and local datacenter; the 4.19.0 docs still apply to the sample API flow in the 4.19.x branch.
