# Choosing Compatible Java, Spring Boot, Spring Data, Driver, and MongoDB Versions

When starting a **Spring Data MongoDB** application, choosing versions goes beyond asking "What is the latest Spring Boot version?". A stable application requires **JDK**, **Spring Boot**, **Spring Framework**, **Spring Data MongoDB**, **MongoDB Java Driver**, and **MongoDB Server** to all be compatible with one another. Even if Java code compiles successfully, connections or features such as aggregation, indexes, transactions, or reactive streams can still fail when components are incompatible.

This lesson belongs to the **Setup** chapter of the `SPRING_DATA_MONGODB` module. The goal is to select a well-founded version combination, initialize a project with managed dependencies, connect to the server, verify the actual resolved versions, and know how to handle upgrades. After this step, you can continue practicing document mapping, `MongoRepository`, `MongoTemplate`, aggregation, indexes, transactions, reactive access, testing, and performance diagnostics.

> **Core principle:** Choose a supported **Spring Boot** line first; use its **BOM** (bill of materials) to manage Spring Data and driver versions, then cross-check **MongoDB Server** against both the Spring Data and MongoDB Java Driver compatibility matrices. Only override versions when there is a clear, verified need.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Describe the role of each layer in the stack: Java → Spring Boot → Spring Data MongoDB → Java Driver → MongoDB Server.
2. Read compatibility matrices and distinguish between **minimum requirements**, **tested versions**, and **support scope**.
3. Choose a version stack for starting a new project, maintaining an existing project, or using an existing MongoDB Server.
4. Create a basic Maven configuration, know how to choose between the synchronous and reactive starters, and inspect the dependency tree.
5. Configure the URI correctly for Spring Boot 3.5 and Spring Boot 4.x.
6. Run a `ping` check, detect Java runtime mismatches, misaligned dependency versions, and connectivity issues.
7. Outline a version upgrade workflow with integration tests and acceptance criteria.

## 2. Understanding Each Dependency Layer

```mermaid
flowchart TD
    A["JDK: compiles and runs Java"] --> B["Spring Boot: platform version and BOM"]
    B --> C["Spring Framework + Spring Data release train"]
    C --> D["Spring Data MongoDB: mapping, template, repository"]
    D --> E["MongoDB Java Driver: protocol, connections, BSON"]
    E --> F["MongoDB Server / Atlas: storage and command execution"]
    F -. "Server capabilities + actual features" .-> D
```

| Component | What to verify? | Example risks |
| --- | --- | --- |
| **Java/JDK** | Minimum and maximum versions verified by the Spring Boot line; JDK of IDE, Maven/Gradle, CI, and runtime host | Compiling with Java 21 while runtime only has Java 17 when using Java 21 features |
| **Spring Boot** | Supported release branch; JDK, Spring Framework, Maven/Gradle requirements; release notes | Major Boot upgrade while keeping old configuration keys that are no longer bound |
| **Spring Framework** | Version required by Spring Boot/Spring Data | Forcing Framework 6.x with Spring Data MongoDB 5.x which requires Framework 7.x |
| **Spring Data MongoDB** | Release train, module version, minimum Java Driver level, tested MongoDB versions | Calling APIs whose signatures changed or behave differently in a new release train |
| **MongoDB Java Driver** | Synchronous/reactive branch, version and server compatibility, protocol/codec changes | Mixing two versions of `mongodb-driver-core` and `mongodb-driver-sync`; runtime errors |
| **MongoDB Server** | Version, topology (standalone/replica set/sharded), required features, support policy | Application needs multi-document transactions while running MongoDB standalone |
| **Build tool** | Maven/Gradle and JDK versions supported by the Spring Boot plugin | New Boot plugin fails to run with a Gradle version that is too old |

**Two distinct types of compatibility:**

- **Technical compatibility:** components can start up and communicate.
- **Tested/supported compatibility:** combinations verified by the development team or documented as supported. You may be able to connect to a newer server, yet newer server features may not be fully tested by Spring Data or the driver.

Do not assume that because "Spring Boot supports Java 21", every plugin, library, or server version in your project automatically supports it. You must evaluate the entire ecosystem.

## 3. Version Map for Initial Orientation

The table below describes common **lines**, not a permanently locked patch table. The Spring Boot → Spring Data relationship is determined by a specific Boot version's BOM; Spring Data lines and minimum driver levels are cross-referenced with the official matrix.

| Spring Boot | Minimum Java | Related Spring Data train | Spring Data MongoDB | Minimum driver per Spring Data | MongoDB Server tested by Spring Data |
| --- | --- | --- | --- | --- | --- |
| **3.5.x** | Java 17 | **2025.0** | **4.5.x** | **5.5.x** | **6.x–8.x** |
| **4.0.x** | Java 17 | **2025.1** | **5.0.x** | **5.6.x** | **6.x–8.x** |
| **4.1.x** | Java 17 | **2026.0** | **5.1.x** | **5.6.x** | **6.x–8.x** |

A few notes when reading the table:

- The Boot 3.5 line uses Spring Framework 6.2.x; Boot 4.x lines use the corresponding Spring Framework 7.x. Do not intentionally pair Spring Data MongoDB 5.x with a Spring Framework 6.x baseline.
- The "Minimum driver" column does **not** guarantee the application is using that exact version. The Spring Boot BOM often selects a newer compatible version. Check the dependency tree to see the **actual resolved version**.
- The "MongoDB Server tested" column does not mean all other server versions will definitely fail. For newer servers, also check the driver–server matrix, release notes, and run integration tests; for very old servers, pay close attention to dropped support.
- The table may change when new patches or release trains are published. Always refer back to the **Requirements** page for your exact Spring Data line and **System Requirements** for your exact Spring Boot line before locking versions for a real project.
- The minimum JDK is a lower bound; choosing a Java LTS supported by your operations team (for example, Java 21) can be appropriate for new projects. However, using a Java version newer than what documentation has verified must also be tested.

### Decision Example: Java 21, Boot 4.1, MongoDB 8.0

A reasonable learning combination:

```text
JDK / runtime         : Java 21 (LTS)
Spring Boot           : 4.1.2 (example of a specific patch in the 4.1 line)
Spring Data MongoDB   : 5.1.x managed by BOM
MongoDB Java Driver   : version managed by BOM, compatible with minimum 5.6.x
MongoDB Server        : 8.0 (a branch within the tested 6.x–8.x range)
Build tool            : Maven 3.9.x, or a Gradle version compatible with Boot 4.1
Data API              : MongoRepository / MongoTemplate (imperative)
```

You do not need to specify separate versions for `spring-data-mongodb` and `mongodb-driver-sync` when using the Spring Boot starter and BOM. This is an **illustrative combination**, not a claim that the patch above is always the latest release.

### When a Project Already Uses Java 17 or Spring Boot 3.5

If your operations platform is already standardized on Java 17 and Boot 3.5, you do not have to upgrade Boot just to learn `MongoTemplate` or repositories. The Boot 3.5 line and Spring Data MongoDB 4.5 still provide the core capabilities; what you need to track are support timelines, security updates, your project's APIs, and compatibility with your current MongoDB Server.

### When the System Uses MongoDB Server 9.x or a Very Old Server

Do not blindly apply the "6.x–8.x tested" column to MongoDB 9.x. Check the latest driver–server compatibility matrix; cells marked **partially compatible** do not guarantee support for all new features. If you must keep an old server, also check driver support removals. For example, Java Driver 5.5 dropped support for MongoDB Server 4.0; using a newer Spring Data version against an old server may be unfeasible even if application code compiles.

## 4. A Repeatable Version Selection Process

To avoid "guessing versions", verify in the following order:

1. **List operational constraints:** permitted JDK versions, Maven/Gradle/CI, existing MongoDB Server, deployment model (local/Atlas/replica set).
2. **List required features:** mapping, repository, aggregation, indexes, multi-document transactions, change streams, reactive access, time-series/vector search (if applicable).
3. **Choose a supported Spring Boot line** matching the JDK and project maintenance lifecycle; verify against the System Requirements page for that exact line.
4. **Inspect the Spring Boot BOM** to identify the managed Spring Data release train and Java Driver. Avoid declaring individual library versions manually when unnecessary.
5. **Check the Spring Data MongoDB matrix:** Spring Framework/JDK requirements, minimum driver, and tested servers.
6. **Check the MongoDB Java Driver matrix:** specific server version, authentication, encryption/TLS, new driver features, and Java support.
7. **Prototype and run a smoke test** against a MongoDB instance on the same branch as the target environment; run integration tests before approving the combination.

Example decision record you can keep directly in the project's technical documentation:

| Field | Sample Value |
| --- | --- |
| Java build/runtime | 21 |
| Spring Boot | 4.1.2 |
| Spring Data MongoDB | 5.1.x (BOM) |
| Java Driver | BOM-resolved version; verified via dependency tree |
| MongoDB Server | 8.0 on replica set for transaction testing |
| Access style | Imperative; `MongoTemplate` and `MongoRepository` |
| Build/CI | Maven Wrapper; verify `mvnw -version` on CI |
| Acceptance criteria | Connection, CRUD, indexes, aggregation, transactions, and retries as required |

## 5. Creating a Maven Project with Managed Dependencies

Let's use the example combination **Java 21 + Spring Boot 4.1.2 + MongoDB 8.0**, with Spring Data and the driver managed by Spring Boot.

In **Spring Initializr** or in your Maven project, choose the required dependencies. Here is a minimal `pom.xml` for an application using synchronous `MongoTemplate`/repositories:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>dev.learning</groupId>
    <artifactId>mongo-compat-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-mongodb</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**Why omit versions for starters, Spring Data, or the driver?** `spring-boot-starter-parent` inherits Spring Boot's dependency management mechanism. As a result, the entire Spring Data group and driver modules are selected as a consistent set by the BOM. If your application uses a different parent, you can import the `spring-boot-dependencies` BOM with the matching Boot version under `dependencyManagement` instead of scattering explicit versions.

If using Gradle, the same principle applies: apply the Spring Boot plugin for the chosen line, use the corresponding dependency management mechanism (BOM via the dependency-management plugin or Gradle `platform`), and declare starters without explicit versions. Use the Gradle Wrapper to pin the build tool version per project.

### 5.1. Choosing the Starter Matching Your Access Style

| Requirement | Starter Dependency | Common APIs |
| --- | --- | --- |
| Imperative / blocking | `spring-boot-starter-data-mongodb` | `MongoTemplate`, `MongoRepository` |
| Reactive / non-blocking | `spring-boot-starter-data-mongodb-reactive` | `ReactiveMongoTemplate`, `ReactiveMongoRepository` |
| Using MongoDB Java Driver directly, without Spring Data | `mongodb-driver-sync` or matching reactive driver | `MongoClient`, `MongoCollection`, BSON API |

The reactive driver uses Reactive Streams. You do **not** turn blocking calls into non-blocking ones simply by putting `Mono`/`Flux` in a service signature. Choose the access style upfront based on your application architecture; if both stacks coexist, you must clearly understand and configure their respective clients and repositories.

Do not manually add `mongodb-driver-core` or `bson` if the starter already pulls them in; avoid having driver modules resolve to different versions due to direct declarations.

### 5.2. Verifying the Versions Maven/Gradle Actually Uses

Run in your project directory (these are **example commands**, no need to run while reading theory):

```bash
java -version
./mvnw -version
./mvnw dependency:tree
```

On Windows, use `.\mvnw.cmd -version` and `.\mvnw.cmd dependency:tree`. In the output, verify:

- `org.springframework.data:spring-data-mongodb`.
- `org.mongodb:mongodb-driver-sync` for imperative, or `org.mongodb:mongodb-driver-reactivestreams` for reactive.
- `org.mongodb:mongodb-driver-core` and `org.mongodb:bson` on the same matching branch/version.
- Spring Framework and Spring Data Commons modules have versions managed by the same BOM set.

For Gradle:

```bash
./gradlew -version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-data-mongodb --configuration runtimeClasspath
./gradlew dependencyInsight --dependency mongodb-driver-core --configuration runtimeClasspath
```

**Distinguish declared versions from resolved versions:** a POM/Gradle build can declare versions at multiple levels; the dependency conflict resolver picks the final version. When diagnosing runtime errors, use `dependency:tree` or `dependencyInsight` rather than only reading the `dependencies` block.

## 6. Configuring the MongoDB URI for Your Spring Boot Line

An important difference between **Spring Boot 3.5** and **Spring Boot 4.x** is the MongoDB connection property prefix.

| Spring Boot Line | Connection URI Property |
| --- | --- |
| **3.5.x** | `spring.data.mongodb.uri` |
| **4.0.x / 4.1.x** | `spring.mongodb.uri` |

Starting with Spring Boot 4, many connection properties moved from `spring.data.mongodb.*` to `spring.mongodb.*`. Some properties that belong directly to Spring Data (for example, `spring.data.mongodb.auto-index-creation`) keep the old prefix. Do not migrate all properties via a blind find-and-replace.

### 6.1. With Spring Boot 4.x

Example `src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: mongo-compat-demo
  mongodb:
    uri: "mongodb://localhost:27017/learning_mongo"
```

With Spring Boot 3.5, the equivalent URI configuration is:

```yaml
spring:
  data:
    mongodb:
      uri: "mongodb://localhost:27017/learning_mongo"
```

Both examples use a local MongoDB **without authentication enabled**, suitable for an isolated learning environment. In real deployments, load the URI from an environment variable or secret manager, and enable authentication and TLS as required:

```yaml
spring:
  mongodb:
    uri: "${MONGODB_URI}"
```

The `MONGODB_URI` variable must be supplied by the deployment environment; for example, the application will not start properly if the variable is unset. Do not commit passwords or connection strings containing real credentials into source code. If a password appears in the URI, special characters must be percent-encoded according to URI standards.

### 6.2. Understanding Connection String Formats

```text
# Single local server:
mongodb://localhost:27017/learning_mongo

# Replica set (illustrative addresses, adapt for real deployment):
mongodb://node1:27017,node2:27017,node3:27017/learning_mongo?replicaSet=rs0

# MongoDB Atlas (illustrative hostname):
mongodb+srv://USER:PASSWORD@cluster.example.mongodb.net/learning_mongo
```

- `mongodb://` specifies explicit hosts, ports, and connection parameters; multiple hosts can be listed for a replica set.
- `mongodb+srv://` uses DNS SRV/TXT records to discover cluster hosts and options; it requires working DNS, network access, and proper TLS configuration.
- `authSource` specifies the authentication database when needed; the application database name and the authentication database do not have to be the same.
- The driver may initialize the client lazily and only hit the network when an operation runs. Therefore, successful application startup **does not prove** the connection actually works.

## 7. Smoke Test: Confirming Version, Connection, and Mapping

A minimal test is executing an actual `ping` against MongoDB from the application.

```java
package dev.learning;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.data.mongodb.core.MongoTemplate;

@SpringBootApplication
public class MongoCompatDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MongoCompatDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner verifyMongo(MongoTemplate template) {
        return args -> {
            var response = template.executeCommand("{ ping: 1 }");
            System.out.println("MongoDB ping: " + response.toJson());
        };
    }
}
```

If configured properly and MongoDB Server is reachable, the command returns a result containing `"ok": 1`. When it fails, check the **root cause** in the stack trace: timeout, authentication, TLS, DNS/SRV, wrong host/port, or classpath conflict. Never print a URI containing a password to the console.

Next, test mapping and repository access:

```java
package dev.learning;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("books")
public class Book {
    @Id
    private String id;

    private String title;

    public Book() {}

    public Book(String title) {
        this.title = title;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }
}
```

```java
package dev.learning;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface BookRepository extends MongoRepository<Book, String> {
}
```

```java
@Bean
CommandLineRunner smokeTest(BookRepository books) {
    return args -> {
        Book saved = books.save(new Book("Spring Data MongoDB"));
        Book found = books.findById(saved.getId()).orElseThrow();
        System.out.println(found.getTitle());
    };
}
```

The `smokeTest` snippet can be added to the corresponding Spring configuration class; when combined with `verifyMongo`, both beans can be placed in the `@SpringBootApplication` class. This example **writes real data** into the `books` collection, so use a dedicated learning database.

A proper setup test only answers "can it connect and perform basic CRUD". To verify features that have specific server requirements, dedicated tests are needed.

## 8. Choosing MongoDB Server by Features and Topology

**Working basic CRUD** does not mean all prerequisites for every Spring Data MongoDB feature are satisfied.

| Requirement | What to consider |
| --- | --- |
| CRUD, mapping, `MongoRepository`, `MongoTemplate` | Driver–server compatibility, collection permissions, BSON data types |
| Aggregation pipeline | Whether the stages/operators actually exist on the server version in use |
| Indexes (compound, TTL, text, wildcard, etc.) | Supported index features and server limits; index creation strategy |
| Multi-document transactions | Deployment and configuration supporting transactions (replica set or appropriate sharded cluster); sessions and transaction manager |
| Change streams | Deployment supporting change streams, permissions, and resume logic on disconnect |
| Reactive access | Reactive driver and appropriate reactive API/runtime; the server still must support the issued commands |
| Performance/diagnostics | Indexes, `explain`, profiler/metrics, representative test data and realistic configuration |

### Standalone vs. Replica Set

A standalone MongoDB instance can suffice for CRUD and introductory lessons. However, multi-document transactions require a suitable topology; to practice transactions locally you can create a **single-node replica set**, while production typically uses a multi-node replica set or sharded cluster depending on availability needs.

New server features do not automatically appear in older Spring Data versions. When planning to use a new aggregation operator or index type, verify **server supports → driver supports → Spring Data exposes**, and if Spring Data does not yet expose a convenience API, you may need lower-level APIs (within supported limits) or a version upgrade.

### MongoDB Atlas and Self-Managed Systems

Atlas manages many deployment aspects, yet the application still must choose the right URI, permissions, IP/network policies, TLS, and driver version. With self-managed servers, the operations team also needs to track topology, server version, support lifecycle, backups, and upgrade procedures.

## 9. Common Conflicts and How to Verify Them

| Symptom | Hypothesis to check | How to confirm |
| --- | --- | --- |
| `UnsupportedClassVersionError` | Java runtime is older than the compiled bytecode level | `java -version`, `mvnw -version`, Java compiler and JDK config on CI |
| `NoSuchMethodError` / `NoClassDefFoundError` | Spring Data, Spring Framework, and MongoDB driver versions are mismatched | Dependency tree, BOM, any `exclusions` / dependency overrides |
| `ClassNotFoundException` on reactive APIs | Missing appropriate reactive starter/driver | Dependency tree, repository/template type |
| `MongoTimeoutException` / server selection timeout | Server unreachable, wrong host/port/DNS/TLS/replica set | Server `ping`, DNS, firewall, URI, topology, driver logs |
| `MongoSecurityException` / authentication failed | Wrong username/password/authSource or insufficient privileges | Check account and auth database; avoid logging secrets |
| App starts up, but queries hit the wrong database | URI/default database or property name changed after Boot upgrade | Check `spring.mongodb.uri` on Boot 4 and `spring.data.mongodb.uri` on Boot 3.5 |
| Transaction reports unsupported | Running standalone, missing manager, or wrong transaction context | Topology, `MongoTransactionManager` or `ReactiveMongoTransactionManager`, service invocation path |
| Error when invoking a new aggregation stage | Server version is older than the feature requires | Check documentation and release notes for that stage/operator |
| Slow queries despite all versions being compatible | Missing indexes, unsuitable data shape, or unoptimized query | `explain`, profiler, metrics, workload comparison |

### Risk of "Quickly Overriding Just the Driver Version"

Suppose the Spring Boot BOM manages `mongodb-driver-sync`, `mongodb-driver-core`, and `bson`. If you override only `mongodb-driver-sync` to a different version, your code may compile, while at runtime it still uses the older `mongodb-driver-core`.

The proper process is to determine **why an override is needed**, check Spring Boot/Spring Data guidance, upgrade the entire dependency group through a supported mechanism, and then test connectivity and business logic. For security fixes, prefer upgrading to a maintained Boot/driver patch before manually mixing versions outside the BOM set.

## 10. Upgrading from Spring Boot 3.5 to 4.x

This is a **major** change, so treat it as a verified migration, not just changing `<version>` in `pom.xml`.

1. Ensure the JDK and build tool meet the target Spring Boot requirements; for Boot 4.1, Gradle 8.14+ (if on Gradle 8) or a supported Gradle 9 line is required.
2. Upgrade the Spring Boot parent/plugin and let the BOM re-select Spring Framework, Spring Data, and the driver.
3. Consult the Spring Boot 4 migration guide, especially for starter, package, and configuration changes.
4. Move the URI property from `spring.data.mongodb.uri` to `spring.mongodb.uri`; check other properties against the documentation and avoid blind bulk replacements.
5. Recompile everything, inspect the dependency tree, and fix changed APIs and configurations.
6. Run smoke tests, CRUD, BSON mapping, aggregation, indexes, transactions, and reactive flows if used by the app.
7. Run integration tests against the **exact MongoDB Server branch** in use and verify a rollback path in case the upgrade fails.

Example configuration change:

```diff
 spring:
-  data:
-    mongodb:
-      uri: "mongodb://localhost:27017/learning_mongo"
+  mongodb:
+    uri: "mongodb://localhost:27017/learning_mongo"
```

Note that there is no guarantee all Boot 3.5 code will run unmodified after upgrading to Boot 4. For custom APIs, consult the corresponding Spring Data MongoDB migration documentation.

## 11. Compatibility Testing by Risk Level

A new application only practicing CRUD can use a simple checklist. Applications using transactions and reactive flows should also verify rarer edge cases.

| Level | Check | Pass Criteria |
| --- | --- | --- |
| **Build** | Build with the chosen JDK and the right Maven/Gradle Wrapper | No compiler, plugin, or dependency version errors |
| **Connection** | `ping` from the application to the target MongoDB | Successful response; no credential leakage |
| **Mapping** | Save/read documents with `@Id`, nested fields, collection name, date/number/UUID types as needed | Read-back data matches expected format |
| **Query** | Repository queries and `MongoTemplate` | Queries and updates succeed; no codec or API errors |
| **Index/aggregation** | Create indexes in a test environment, run representative pipelines | No commands/operators unsupported by the server |
| **Transaction** | Modify two documents in one transaction, then trigger an intentional failure | Changes roll back on a supported topology |
| **Reactive** | CRUD with `ReactiveMongoTemplate` or reactive repository; backpressure/cancellation if relevant | No blocking calls stalling non-blocking threads |
| **Performance** | Measure `explain`, p95/p99 latency, and pool metrics under sample load | Meets agreed application thresholds |

If using Testcontainers, run the MongoDB image version matching your target environment rather than just `latest`. A replica set topology is required for transaction tests. Test data must be isolated from production databases.

### Practice Exercises

**Exercise 1 — Build a compatibility matrix for a new project:** Your team uses Java 21 and MongoDB 8.0 and wants repositories + aggregation + transactions. Choose a supported Spring Boot line, identify the corresponding Spring Data MongoDB version, minimum driver requirement, and required topology. Cite documentation sources so others can verify.

**Exercise 2 — Inspecting the dependency tree:** A teammate reports a `NoSuchMethodError` at runtime. Describe how to check the resolved versions of `spring-data-mongodb`, `mongodb-driver-sync`, `mongodb-driver-core`, and `bson`, and propose how to restore version consistency.

**Exercise 3 — Migrating configuration:** An application running on Boot 3.5 with `spring.data.mongodb.uri` is upgraded to Boot 4.1. Update the property, verify the effective connection URI, and describe a sufficient test to prove the app connects to the intended database.

**Exercise 4 — Testing a newer server:** A team wants to upgrade MongoDB Server to a version not yet listed in the "tested by Spring Data" range. Which matrices will you check, what tests will you run, and what evidence do you require before approving deployment?

### Suggested Answers

1. For example, Boot 4.1.x + Java 21 + Spring Data MongoDB 5.1.x managed by the BOM, driver meeting the minimum requirement, MongoDB 8.0, and a replica set for transactions; verify exact patch and build tool versions in the docs.
2. Inspect the dependency tree, locate overrides and misaligned modules, return version selection control to the BOM, and retest.
3. Change to `spring.mongodb.uri` and run a `ping` plus a write/read against the test database; do not treat startup success as sole proof.
4. Check the **Spring Data → Java Driver → MongoDB Server** matrices, release notes/feature changes, run integration tests, and run load tests against the target server version to be deployed.

## 12. End-of-Lesson Checklist

- [ ] Document the **Java build/runtime** version and CI configuration.
- [ ] Select **Spring Boot** based on support lifecycle and system requirements, and record the pinned patch version.
- [ ] Verify the **Spring Data release train** and driver via BOM/`dependency:tree`.
- [ ] Cross-check **MongoDB Server** against both Spring Data and Java Driver matrices.
- [ ] Pick **imperative** or **reactive** matching your architecture.
- [ ] Use the right URI key: `spring.data.mongodb.uri` on Boot 3.5; `spring.mongodb.uri` on Boot 4.x.
- [ ] Run `ping` and CRUD against a test database.
- [ ] Test aggregation, indexes, transactions, and reactive flows individually as used.
- [ ] Keep passwords out of source code; verify TLS, network, and access permissions.
- [ ] Have an upgrade and rollback plan for major version changes.

## 13. Official Documentation for Version Verification

The following pages may be updated per patch or release train; for a real project, open the **exact version branch** and record the date checked:

1. [Spring Boot 3.5 — System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html).
2. [Spring Boot 4.1 — System Requirements](https://docs.spring.io/spring-boot/4.1/system-requirements.html).
3. [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/4.1/appendix/application-properties/index.html), see `spring.mongodb.*`.
4. [Spring Boot — Working with NoSQL Technologies](https://docs.spring.io/spring-boot/4.1/reference/data/nosql.html).
5. [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide).
6. [Spring Data MongoDB — Requirements & Compatibility Matrix](https://docs.spring.io/spring-data/mongodb/reference/preface.html).
7. [Spring Data — Dependency Management / BOM](https://docs.spring.io/spring-data/mongodb/reference/data-commons/dependencies.html).
8. [MongoDB — Client Library Compatibility Tables](https://www.mongodb.com/docs/drivers/compatibility/?driver-language=java&java-driver-framework=java-sync).
9. [MongoDB Java Driver — Upgrade Driver Versions](https://www.mongodb.com/docs/drivers/java/sync/current/reference/upgrade/).

**Remember:** Compatibility is proven by **official matrices, actual resolved dependencies, and tests against the target server**. A combination that merely "starts up" is only the first step toward running Spring Data MongoDB reliably.
