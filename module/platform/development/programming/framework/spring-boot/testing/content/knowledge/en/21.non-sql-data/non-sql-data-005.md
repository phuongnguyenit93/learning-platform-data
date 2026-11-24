# @DataCassandraTest, @DataCouchbaseTest, or @DataLdapTest when the application has integrations

## 1. Problem statement and objectives

In a Spring Boot application, data does not reside exclusively in a relational database. A system might use Apache Cassandra to store partitioned events/telemetry, Couchbase to store JSON documents, and LDAP to query organizational directories. Each system has a distinct data model, connection setup, consistency, indexing, security, and lifecycle.

Using `@SpringBootTest` for every repository test typically loads unrelated beans: REST controllers, message consumers, scheduling, and cloud clients. Conversely, mocking the repository completely with Mockito leaves you blind to whether mappings are valid or queries actually execute on the real engine. Spring Boot provides three **test slices** for these integrations:

- `@DataCassandraTest`: focuses on Spring Data Cassandra, `@Table` mapping, Cassandra templates, and repositories.
- `@DataCouchbaseTest`: focuses on Spring Data Couchbase, `@Document` mapping, Couchbase templates, and repositories.
- `@DataLdapTest`: focuses on Spring LDAP / Spring Data LDAP, `@Entry` mapping, `LdapTemplate`, and repositories, with an optional embedded LDAP server when UnboundID is present.

In this lesson, you will:

1. Understand how a **test slice** differs from a full application context and a pure unit test.
2. Identify **dependencies**, **annotation imports**, and **auto-configuration** for Spring Boot 3.5 and Java 17.
3. Know why Cassandra/Couchbase require a real engine or container, whereas LDAP can use embedded UnboundID.
4. Write tests verifying mapping, repository CRUD, entity/document/entry, search/query, connectivity, and cleanup.
5. Use `Testcontainers`, `@ServiceConnection`, and `@Testcontainers` when testing Cassandra/Couchbase.
6. Use `spring.ldap.embedded.base-dn` and LDIF fixtures to test LDAP offline without real enterprise directory accounts.
7. Avoid assuming **rollback** for NoSQL slices like `@DataJpaTest`; design isolated test data.
8. Distinguish Cassandra partition/query semantics, Couchbase KV/index/query consistency, and LDAP DN/base/LDAP filters.
9. Know when to escalate to `@SpringBootTest` or contract/integration tests against real environments.
10. Troubleshoot common errors: `NoSuchBeanDefinitionException`, unreachable service, wrong keyspace/bucket/DN, permissions, schema/index issues, and version mismatches.

**Applicable versions:** Java 17+, Spring Boot **3.5.x** (Maven examples use **3.5.16**), JUnit Jupiter, Spring Data, and Testcontainers compatible with the Boot 3.5 BOM. In Spring Boot 4, many test annotations move to new modules/packages; always check documentation for the exact major version.

**Principle:** Choose a slice only when the application actually uses that technology and you want to verify **repository/mapping/connection against an appropriate engine**. Do not add Cassandra/Couchbase/LDAP starters just to try out three annotations in an app that does not use them.

## 2. What is a test slice, and what is it not?

### 2.1. Three testing boundaries

```text
Pure unit test:
  JUnit -> domain/service -> Mockito fake repository
  (no mapping, no database, no Spring context)

NoSQL/LDAP test slice:
  JUnit -> real Spring Data repository/template
                |
                v
          Cassandra/Couchbase/LDAP test instance
  (mapping/query/connection tested, without the whole app)

Full integration test:
  HTTP/controller -> service -> repository -> data store
  + security, properties, transactions, messaging, external adapters
```

`@DataCassandraTest`, `@DataCouchbaseTest`, and `@DataLdapTest` **are not annotations that automatically mock data**. They control which Spring context is loaded and configure the relevant clients/templates/repositories. The actual data and backend services are provided by Testcontainers, embedded LDAP, or a separate test environment.

### 2.2. Auto-configuration principles in Boot 3.5

Slices follow a strategy of enabling only necessary auto-configurations; Spring Boot commonly applies `@OverrideAutoConfiguration(enabled=false)`, type exclude filters, and `@ImportAutoConfiguration`. In Boot 3.5's test slice catalog:

| Slice | Key templates/repositories | Typical auto-configurations |
| --- | --- | --- |
| `@DataCassandraTest` | `CassandraTemplate`, plus reactive templates/repos when dependencies exist | `CassandraAutoConfiguration`, `CassandraDataAutoConfiguration`, Cassandra reactive & repository configs, SSL/cache |
| `@DataCouchbaseTest` | `CouchbaseTemplate` / `ReactiveCouchbaseTemplate`, repositories | `CouchbaseAutoConfiguration`, Couchbase data/reactive/repository configs, SSL/cache |
| `@DataLdapTest` | `LdapTemplate`, LDAP repositories/entities | `LdapAutoConfiguration`, `LdapRepositoriesAutoConfiguration`, `EmbeddedLdapAutoConfiguration` when conditions match |

When `spring-boot-testcontainers` is present, each slice also includes **optional `ServiceConnectionAutoConfiguration`** to pick up connection details from declared containers. Optional does not mean starting Docker or creating containers automatically if you haven't configured them.

### 2.3. Restricted component scanning

Boot 3.5 documentation makes clear these slices usually **do not scan regular `@Component` and `@ConfigurationProperties` beans** like a full app. Depending on the slice, they focus on domain mapping types and repositories.

```java
@DataCassandraTest
class TelemetryRepositoryTest {
    @Autowired TelemetryRepository repository;

    // @Autowired MyBusinessService service;
    // Usually NOT auto-scanned into the slice.
}
```

This snippet merely illustrates the dependency graph. If you want to test mapping/repositories, you do not need business services. If a small collaborator is genuinely required, use `@Import(MyService.class)` or `@MockitoBean` along the boundary; for `@ConfigurationProperties`, use `@EnableConfigurationProperties(MyStoreProperties.class)`.

**Do not** add `@ComponentScan("com.example")` to cure missing-bean errors: that defeats the slice and can drag production components into the test.

### 2.4. Do not combine the three slice annotations on the same class

Spring Boot does not support creating a single test by stacking `@DataCassandraTest`, `@DataCouchbaseTest`, and `@DataLdapTest` simultaneously. Each slice has its own bootstrap/auto-configuration overrides; if an app needs to test Cassandra + Couchbase + LDAP coordination in a single workflow, use `@SpringBootTest` with real test infrastructure, or pick one slice and intentionally import specific auto-configurations from the others per the docs.

Stick to **one test class/one boundary**, with isolated data and explicit cleanup.

## 3. Technology decision table

| Question | Cassandra | Couchbase | LDAP |
| --- | --- | --- | --- |
| Typical purpose | Wide-column, partitioned records, write-heavy | JSON documents, key-value, and N1QL/SQL++ queries | Directory entries, DNs, attributes, users/groups |
| Mapping annotation | `@Table` (Spring Data Cassandra) | `@Document` (Spring Data Couchbase) | `@Entry` (Spring Data LDAP) |
| Template | `CassandraTemplate` | `CouchbaseTemplate` / reactive variant | `LdapTemplate` |
| Repository | `CassandraRepository`/reactive | `CouchbaseRepository`/reactive | `LdapRepository` |
| Slice | `@DataCassandraTest` | `@DataCouchbaseTest` | `@DataLdapTest` |
| Test service | Real Cassandra container/cluster | Real Couchbase container/cluster | Embedded UnboundID or LDAP test server |
| Default embedded in-memory from slice? | **No** | **No** | **Possible**, if UnboundID and base DN are configured |
| Data cleanup | Delete partition-key rows / isolate keyspace | Delete document IDs / bucket, collection | LDAP unbind DN / clean LDIF fixture |
| Default SQL/JPA rollback? | No | No | No |
| Primary failure causes | Contact point/keyspace/schema/consistency | Bucket/index/query scope/KV consistency | Base DN/schema/filter/bind credentials/TLS |

### 3.1. Differing from @DataJpaTest and H2

`@DataJpaTest` typically opens a test-managed transaction and rolls it back after the test; H2 can spin up an embedded database automatically. Do not project those expectations onto `@DataCassandraTest`, `@DataCouchbaseTest`, and `@DataLdapTest`:

- Cassandra does not use a JPA `EntityManager` or JPA-style local JDBC rollback.
- Couchbase KV writes have their own durability/consistency and transaction APIs; there is no free TestContext rollback per test.
- LDAP add/modify/delete entry operations do not auto-rollback like a JPA test transaction.
- `@Transactional` does not turn NoSQL operations into a JDBC transaction with automatic rollback.

Therefore, when a test `save`s and observes a record, you must **delete** the record or run on an ephemeral environment rather than expecting TestContext rollback.

### 3.2. Use only when the application actually has the integration

If an application only uses MySQL, do not add all three starters to the test classpath. They bloat the dependency graph, slow startup, and can trigger unwanted connection attempts. Add only the Spring Data module for the backend actually used, test at the repository level, and combine unit/integration tests according to risk.

## 4. Packages and versions: Spring Boot 3.5 vs. Boot 4

The three correct imports for **Spring Boot 3.5**:

```java
import org.springframework.boot.test.autoconfigure.data.cassandra.DataCassandraTest;
import org.springframework.boot.test.autoconfigure.data.couchbase.DataCouchbaseTest;
import org.springframework.boot.test.autoconfigure.data.ldap.DataLdapTest;
```

These packages live in the Spring Boot 3.x test auto-configuration module. In Boot 4, module splits and test annotation namespaces change, for example packages prefixed with `org.springframework.boot.data.cassandra.test.autoconfigure`. Do not copy code from Boot 4 docs into Boot 3.5 without updating imports/dependencies.

Commonly used Maven dependencies:

| Purpose | Maven groupId:artifactId |
| --- | --- |
| Cassandra data access | `org.springframework.boot:spring-boot-starter-data-cassandra` |
| Cassandra reactive | `org.springframework.boot:spring-boot-starter-data-cassandra-reactive` |
| Couchbase data access | `org.springframework.boot:spring-boot-starter-data-couchbase` |
| Couchbase reactive | `org.springframework.boot:spring-boot-starter-data-couchbase-reactive` |
| LDAP data access | `org.springframework.boot:spring-boot-starter-data-ldap` |
| JUnit + AssertJ + Spring Boot Test | `org.springframework.boot:spring-boot-starter-test` (test scope) |
| Testcontainers auto service connections | `org.springframework.boot:spring-boot-testcontainers` (test scope) |
| Testcontainers JUnit Jupiter | `org.testcontainers:junit-jupiter` (test scope) |
| Cassandra Testcontainers module (1.x) | `org.testcontainers:cassandra` (test scope) |
| Couchbase Testcontainers module (1.x) | `org.testcontainers:couchbase` (test scope) |
| Embedded LDAP UnboundID | `com.unboundid:unboundid-ldapsdk` (test scope) |

**Note:** The Testcontainers module coordinates listed target the Boot 3.5 BOM / Testcontainers 1.x. Testcontainers 2.x changes coordinates for several modules; always inspect `mvn dependency:tree` and align module coordinates with your active dependency management rather than mixing major versions accidentally.

## 5. @DataCassandraTest — model and scope

### 5.1. Cassandra differs from an RDBMS

Apache Cassandra relies on partition keys, clustering keys, and replicated distributed storage. To test a Cassandra repository, tests need to confirm:

- `@Table`, `@PrimaryKey`/`@PrimaryKeyColumn` mappings are accurate.
- The keyspace and table actually exist.
- Fields serialize into the right CQL types.
- Queries match partition/clustering keys or existing indexes.
- TTLs, timestamps, consistency/replication, and query patterns are properly designed.
- No SQL assumptions like `JOIN`, arbitrary `ORDER BY`, or full table scans via `ALLOW FILTERING` to "fix" query errors.

`@DataCassandraTest` loads `CassandraTemplate` and repositories, yet **does not create an H2-like embedded Cassandra engine**. Tests need a running Cassandra: Testcontainers, a CI container, or a dedicated test service.

### 5.2. @Table and primary key

```java
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("catalog_item")
public class CassandraItem {

    @PrimaryKey
    private String id;

    private String title;

    protected CassandraItem() {}

    public CassandraItem(String id, String title) {
        this.id = id;
        this.title = title;
    }

    public String getId() { return id; }
    public String getTitle() { return title; }
}
```

This fragment shows Spring Data Cassandra mapping, not Jakarta Persistence `@Entity`. For composite partition/clustering keys, use `@PrimaryKeyClass` and `@PrimaryKeyColumn` with explicitly designed key types and ordering; do not assume `@PrimaryKey String id` fits every production table.

### 5.3. CassandraRepository, CassandraTemplate

`CassandraRepository<CassandraItem, String>` supports CRUD by primary key; `CassandraTemplate` provides CQL operations/queries via Spring's abstraction. A `repository.save`/`findById` verifies mapping and key-value reads. However, a test reading only by primary key **does not prove** every `@Query`, paging, or consistency semantic is right.

When custom queries need verification, write dedicated tests on a production-like schema with real partition keys, clustering order, and indexes/denormalized tables.

## 6. Complete Cassandra project with Testcontainers

This is a **standalone project**, not merged with the LDAP/Couchbase projects in later sections. It requires a Testcontainers-compatible Docker/Podman environment, sufficient RAM for Cassandra, and network access to pull the image initially. The test initializes the keyspace/table via a CQL init script.

### 6.1. File tree

```text
cassandra-slice-lab/
├── pom.xml
├── src/main/java/com/example/casslab/
│   ├── CassandraLabApplication.java
│   ├── CassandraItem.java
│   └── CassandraItemRepository.java
└── src/test/
    ├── resources/cassandra/schema.cql
    └── java/com/example/casslab/CassandraItemRepositoryTest.java
```

### 6.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>cassandra-slice-lab</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
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
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-testcontainers</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.testcontainers</groupId>
      <artifactId>junit-jupiter</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.testcontainers</groupId>
      <artifactId>cassandra</artifactId>
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

The Boot parent manages driver and Testcontainers versions. Do not pin the DataStax driver independently to a version mismatched with Spring Data Cassandra. Testcontainers requires a container runtime; `@Testcontainers(disabledWithoutDocker = true)` is used in the example to **skip** when Docker is absent, though CI must clearly report skips; never treat "0 tests run" as proof Cassandra integration PASSED.

### 6.3. CassandraLabApplication.java

`src/main/java/com/example/casslab/CassandraLabApplication.java`:

```java
package com.example.casslab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CassandraLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(CassandraLabApplication.class, args);
    }
}
```

### 6.4. CassandraItem.java

`src/main/java/com/example/casslab/CassandraItem.java`:

```java
package com.example.casslab;

import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("catalog_item")
public class CassandraItem {
    @PrimaryKey
    private String id;
    private String title;

    protected CassandraItem() {
    }

    public CassandraItem(String id, String title) {
        this.id = id;
        this.title = title;
    }

    public String getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }
}
```

The entity uses a test-provided id; do not use JPA `GenerationType.IDENTITY`. Cassandra does not auto-assign identity values like relational auto-increment. In production, define id/partition keys around access patterns.

### 6.5. CassandraItemRepository.java

`src/main/java/com/example/casslab/CassandraItemRepository.java`:

```java
package com.example.casslab;

import org.springframework.data.cassandra.repository.CassandraRepository;

public interface CassandraItemRepository
        extends CassandraRepository<CassandraItem, String> {
}
```

You do not need `@Repository` on the interface for Spring Data to create a bean when Cassandra repositories are auto-configured. If the repository sits outside the auto-scanned package, use appropriate package configuration instead of pulling in the whole application.

### 6.6. schema.cql

`src/test/resources/cassandra/schema.cql`:

```sql
CREATE KEYSPACE IF NOT EXISTS training
WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

CREATE TABLE IF NOT EXISTS training.catalog_item (
    id text PRIMARY KEY,
    title text
);
```

The CQL script creates the keyspace and table **before** Spring Data runs queries. In a single-node container, `SimpleStrategy` with replication factor 1 fits demos; never copy that into a multi-datacenter production config.

### 6.7. CassandraItemRepositoryTest.java

`src/test/java/com/example/casslab/CassandraItemRepositoryTest.java`:

```java
package com.example.casslab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.cassandra.DataCassandraTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.data.cassandra.core.CassandraTemplate;
import org.testcontainers.containers.CassandraContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@DataCassandraTest(properties = {
        "spring.cassandra.keyspace-name=training",
        "spring.cassandra.local-datacenter=datacenter1"
})
@Testcontainers(disabledWithoutDocker = true)
class CassandraItemRepositoryTest {

    @Container
    @ServiceConnection
    static final CassandraContainer<?> cassandra =
            new CassandraContainer<>("cassandra:4.1")
                    .withInitScript("cassandra/schema.cql");

    @Autowired
    CassandraItemRepository repository;

    @Autowired
    CassandraTemplate template;

    @Test
    void savesAndLoadsByPartitionKey() {
        String id = "lesson-259-cassandra-1";

        try {
            repository.save(new CassandraItem(id, "Cassandra slice"));
            assertThat(repository.findById(id))
                    .isPresent()
                    .get()
                    .extracting(CassandraItem::getTitle)
                    .isEqualTo("Cassandra slice");

            assertThat(template).isNotNull();
        }
        finally {
            repository.deleteById(id);
        }
    }

    @Test
    void missingPrimaryKeyReturnsEmpty() {
        assertThat(repository.findById("missing-259-cassandra"))
                .isEmpty();
    }
}
```

**Technical breakdown:**
- `@DataCassandraTest` selects only the Cassandra slice, mappings, and repositories.
- `@Container` declares the container managed by JUnit/Testcontainers.
- `@ServiceConnection` supplies `CassandraConnectionDetails` to Spring Boot instead of hardcoding Docker-mapped ports.
- `CassandraContainer.withInitScript(...)` loads CQL from the classpath before tests; schema creation may take time while the cluster starts.
- `spring.cassandra.keyspace-name=training` tells the template/repository which keyspace to use; container initialization creates that keyspace.
- `repository.save(...)` and `findById(...)` verify entity mapping against real Cassandra.
- `finally` deletes the row so database state does not leak across methods. Cassandra does not auto-rollback via TestContext.
- The second test verifies a read miss, avoiding assumptions about leftover data from an earlier test.

If container implementations/versions changed packages in Testcontainers 2.x, adjust imports and module coordinates to match the BOM rather than copying v1 `org.testcontainers.containers.CassandraContainer` onto a v2 classpath unchecked.

### 6.8. Running the Cassandra lab

```bash
mvn -q clean test
mvn -q -Dtest=CassandraItemRepositoryTest test
```

If Docker is available and tests pass, Maven returns exit code 0. **If Docker is absent**, the annotation can skip tests; check the Surefire summary (`tests` / `skipped`) before drawing conclusions. Pulling the Cassandra image and bootstrapping the cluster for the first time takes longer than unit tests; timeouts must reflect real startup time.

The project intentionally omits fixed stdout because Testcontainers/Docker logs/driver versions vary. Reports go to `target/surefire-reports`. This is analyzed sample documentation; Maven execution must be verified in a Docker-enabled environment.

## 7. Advanced considerations when testing Cassandra

### 7.1. Primary keys and valid queries

Cassandra organizes data by **partition key** and clustering columns; a primary-key test reading by id proves only one access path. For methods like `findByStatus(...)` or searching by a non-partition/non-indexed field, queries may be rejected or perform inefficient scans. Never add `ALLOW FILTERING` just to make a test pass when production could not handle the load.

### 7.2. Cassandra does not "commit" like JDBC

A Cassandra write has its own consistency/durability semantics and replication/acknowledgment, without a local JDBC transaction wrapping the whole test. A test `save` is not rolled back by Spring TestContext by default.

If the application uses lightweight transactions (`IF NOT EXISTS`/compare-and-set) or logged batches, write dedicated tests verifying those semantics on a real cluster. A single Testcontainers node cannot prove cross-datacenter consistency or network partition behavior.

### 7.3. TTLs/tombstones

Cassandra has `TTL` and tombstones; tests should check TTL over an appropriate window when it is a business contract. Never write `Thread.sleep(1000)` expecting millisecond-exact deletion; TTL granularity and background compaction differ. Use sufficiently large TTLs, bounded polling/reasonable clocks, and classify those as slower integration tests.

### 7.4. Consistency levels

A single-node test cannot verify quorum/all/write-failure scenarios of a multi-node cluster. When consistency level is a requirement, use a suitable test cluster/environment. `@DataCassandraTest` only shapes the Spring context; it does not create a production-like multi-node replicated cluster.

### 7.5. Schema migrations

The test `schema.cql` should reflect a specific version of the schema contract. Production Cassandra schema changes may require `ALTER TABLE`, migration coordination, and rollout, none of which `@DataCassandraTest` runs automatically. Keep schema initialization/tooling consistent between test and production.

## 8. @DataCouchbaseTest — document/KV/query

### 8.1. Couchbase is a JSON document store + KV + query

Couchbase stores JSON documents by key inside a bucket/scope/collection. Spring Data Couchbase provides `@Document`, `@Id`, `@Field`, `CouchbaseTemplate`, and repositories.

`@DataCouchbaseTest` loads Couchbase template/repository infrastructure, yet **does not supply an embedded Couchbase server automatically**. Tests need a container or test cluster. You can use Testcontainers `CouchbaseContainer` with `@ServiceConnection` and create a dedicated bucket.

### 8.2. KV lookup differs from N1QL query

A `repository.findById(id)` test typically uses the **key-value lookup** path and does not necessarily need a secondary index. However, derived queries such as `findByTitle`/`findByCategory` may invoke the query service and require indexes, scope/collection mapping, and proper consistency. A passing KV test does not prove all SQL++/N1QL queries pass.

Couchbase has **query consistency** and index update lag: newly written documents may not appear immediately in secondary indexes under default `NOT_BOUNDED` queries. If a test saves and immediately queries, understand `REQUEST_PLUS`/`AT_PLUS`/scan consistency or use bounded eventual assertions when semantics call for it. Never sprinkle arbitrary `Thread.sleep(200)` to paper over races.

### 8.3. Bucket/scope/collection must match

Couchbase connection properties (host/credentials) do not mean Spring Data Couchbase knows the right bucket. In Spring Boot 3.5, `spring.data.couchbase.bucket-name` is the standard property for Spring Data Couchbase.

If using non-default scopes/collections, repositories/templates and bucket provisioning must align on the exact scope/collection. Testing against `_default` while production uses another scope can hide mapping bugs; add integration tests matching the production layout when needed.

## 9. Complete Couchbase project with Testcontainers

This project is **independent** from Cassandra and LDAP. It needs Docker, the Couchbase image, adequate RAM/CPU, and sufficient startup timeout. Tests focus on KV mapping without claiming N1QL/secondary-index correctness.

### 9.1. File tree

```text
couchbase-slice-lab/
├── pom.xml
├── src/main/java/com/example/cbslab/
│   ├── CouchbaseLabApplication.java
│   ├── CatalogDocument.java
│   └── CatalogRepository.java
└── src/test/java/com/example/cbslab/
    └── CatalogRepositoryTest.java
```

### 9.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>couchbase-slice-lab</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-data-couchbase</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-testcontainers</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.testcontainers</groupId>
      <artifactId>junit-jupiter</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.testcontainers</groupId>
      <artifactId>couchbase</artifactId>
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

### 9.3. CouchbaseLabApplication.java

`src/main/java/com/example/cbslab/CouchbaseLabApplication.java`:

```java
package com.example.cbslab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CouchbaseLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(CouchbaseLabApplication.class, args);
    }
}
```

### 9.4. CatalogDocument.java

`src/main/java/com/example/cbslab/CatalogDocument.java`:

```java
package com.example.cbslab;

import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;

@Document
public class CatalogDocument {

    @Id
    private String id;

    @Field
    private String title;

    protected CatalogDocument() {
    }

    public CatalogDocument(String id, String title) {
        this.id = id;
        this.title = title;
    }

    public String getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }
}
```

Couchbase/Spring Data `@Id` is `org.springframework.data.annotation.Id`, not `jakarta.persistence.Id`. Spring Data Couchbase `@Field` describes a persisted field. Never use JPA `@Entity`/`@Table` for Couchbase document mapping.

### 9.5. CatalogRepository.java

`src/main/java/com/example/cbslab/CatalogRepository.java`:

```java
package com.example.cbslab;

import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface CatalogRepository
        extends CouchbaseRepository<CatalogDocument, String> {
}
```

The test reads by ID; Couchbase does not need a secondary index for KV gets. If you add `findByTitle`, ensure the query service and index exist and account for index consistency; do not infer from this test that derived queries automatically work.

### 9.6. CatalogRepositoryTest.java

`src/test/java/com/example/cbslab/CatalogRepositoryTest.java`:

```java
package com.example.cbslab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.couchbase.DataCouchbaseTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.data.couchbase.core.CouchbaseTemplate;
import org.testcontainers.couchbase.BucketDefinition;
import org.testcontainers.couchbase.CouchbaseContainer;
import org.testcontainers.couchbase.CouchbaseService;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.assertj.core.api.Assertions.assertThat;

@DataCouchbaseTest(properties = {
        "spring.data.couchbase.bucket-name=lesson_bucket",
        "spring.couchbase.env.timeouts.connect=2m",
        "spring.couchbase.env.timeouts.key-value=1m"
})
@Testcontainers(disabledWithoutDocker = true)
class CatalogRepositoryTest {

    @Container
    @ServiceConnection
    static final CouchbaseContainer couchbase =
            new CouchbaseContainer(
                    DockerImageName.parse("couchbase/server:7.6.2"))
                    .withEnabledServices(
                            CouchbaseService.KV,
                            CouchbaseService.INDEX,
                            CouchbaseService.QUERY)
                    .withBucket(new BucketDefinition("lesson_bucket"));

    @Autowired
    CatalogRepository repository;

    @Autowired
    CouchbaseTemplate template;

    @Test
    void storesAndFetchesDocumentById() {
        String id = "lesson-259-couchbase-1";
        try {
            repository.save(new CatalogDocument(id, "Couchbase slice"));

            assertThat(repository.findById(id))
                    .isPresent()
                    .get()
                    .extracting(CatalogDocument::getTitle)
                    .isEqualTo("Couchbase slice");

            assertThat(template.getBucketName())
                    .isEqualTo("lesson_bucket");
        }
        finally {
            repository.deleteById(id);
        }
    }

    @Test
    void missingDocumentIsAbsent() {
        assertThat(repository.findById("missing-259-couchbase"))
                .isEmpty();
    }
}
```

**Explanation:**
- `@DataCouchbaseTest` configures templates and repositories, without app-wide controllers or services.
- `CouchbaseContainer` provisions a Couchbase test server and `lesson_bucket`.
- `@ServiceConnection` injects connection details into Spring Boot; the bucket name must still match `spring.data.couchbase.bucket-name`.
- `withEnabledServices` declares KV, index, and query services as needed for testing. Testcontainers 2.x packages may differ from this version.
- `findById` uses the KV path, avoiding index creation or index-update wait requirements in the initial demo.
- `finally` deletes the specific document ID; NoSQL test slices do not auto-rollback.
- If testing secondary-index queries, add index provisioning and corresponding assertions.

**Operational note:** The Couchbase container is much heavier than embedded LDAP. On slower CI runners or without pre-cached images, allocate adequate resources and timeouts instead of letting timeouts turn test runs into a gamble.

### 9.7. Running the Couchbase lab

```bash
mvn -q clean test
mvn -q -Dtest=CatalogRepositoryTest test
```

Only conclude integration PASSED when Surefire records that tests **actually ran**, not skipped due to missing Docker. `@ServiceConnection` passes connection details, yet does not create arbitrary buckets/scopes beyond what the container setup provisions. Inspect `target/surefire-reports` to verify results.

## 10. Expanding Couchbase testing within proper boundaries

### 10.1. Derived queries and indexes

A method:

```java
List<CatalogDocument> findByTitle(String title);
```

declared in `CatalogRepository` causes Spring Data to invoke the query service. To test it:
- Ensure the right bucket/scope/collection/index exists.
- Create the index before the test or via container schema provisioning.
- Account for consistency behavior after KV writes.
- Verify exact property names and field annotations.
- Clean up data by key/collection rather than wiping a bucket shared with other tests.

The method above is an **extension pattern**, absent from the runnable `CatalogRepository.java` in Section 9; to run it, add it to the interface and create an index.

### 10.2. Query consistency differs from KV consistency

If after saving, `findById` finds the document while `findByTitle` misses it, the query index may simply not have updated yet. Do not immediately assume mapping is broken. When query consistency is required, configure scan consistency on the appropriate API/template/query options, or use bounded await/retry strictly for eventual consistency contracts; avoid blind sleeps.

### 10.3. CAS and concurrent modifications

Couchbase provides CAS (compare-and-swap) and optimistic concurrency modes. If business rules require preventing lost updates, explicitly test CAS/`@Version` mapping against a real container. `@DataCouchbaseTest` does not automatically simulate races or guarantee multi-document atomicity.

### 10.4. Durability and cross-node guarantees

A single Couchbase container works well for mapping/KV integration, yet does not prove quorum durability or replica failover of a production cluster. Depending on risk, use a multi-node environment with controlled tests. Never infer from one passing `save` test that all production durability policies are sound.

### 10.5. Bucket, scope, and collection in multi-tenant apps

If production isolates tenants by collection/bucket, testing in `_default` will miss routing bugs. Provision data containers matching production structure and verify repository mapping and security isolation. Never hardcode production credentials in `application-test.properties`.

## 11. @DataLdapTest — embedded LDAP and DNs

### 11.1. LDAP is not a SQL table or JSON document store

LDAP stores directory entries identified by a **Distinguished Name (DN)**, for example:

```text
uid=alice,ou=people,dc=example,dc=org
```

Entries have attributes and object classes:

```ldif
dn: uid=alice,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: alice
cn: Alice Nguyen
sn: Nguyen
```

- `uid=alice` is a Relative Distinguished Name (RDN).
- `ou=people` is the organizational unit holding the entry.
- `dc=example,dc=org` is the base DN.
- `cn` is common name; `sn` is surname.
- `objectClass` dictates required and allowed attributes under the LDAP schema.

An LDAP filter `(uid=alice)` **is not a SQL WHERE clause**. Characters `*`, `(`, `)`, `\`, and NUL follow specific escaping rules; never concatenate user input into an unescaped filter string.

### 11.2. Boot 3.5 supports embedded LDAP with UnboundID

`@DataLdapTest` auto-configures `LdapTemplate`/LDAP repositories and an **in-memory embedded LDAP server when the right library and properties are supplied**.

Requirements:
- `spring-boot-starter-data-ldap`.
- `com.unboundid:unboundid-ldapsdk` on the test classpath.
- `spring.ldap.embedded.base-dn=dc=example,dc=org`.
- An LDIF fixture defining base/organizational units/entries when initial data is desired.
- Optionally `spring.ldap.base=dc=example,dc=org` so the template works with relative DNs.

Embedded LDAP typically binds to a random local port. **Do not** point `spring.ldap.urls` to a corporate LDAP server in this slice test. If intentionally testing against an external server, exclude embedded auto-configuration and provide sandbox test URL/bind credentials (never production).

## 12. Complete LDAP project, no Docker required

The LDAP project below includes an LDIF fixture and three tests: looking up/searching a seeded entry, checking a missing entry, and adding/deleting an entry with cleanup. This is the lightest lab among the three examples.

### 12.1. Directory tree

```text
ldap-slice-lab/
├── pom.xml
├── src/main/java/com/example/ldaplab/
│   └── LdapLabApplication.java
└── src/test/
    ├── resources/ldap-test.ldif
    └── java/com/example/ldaplab/LdapDirectoryTest.java
```

### 12.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>ldap-slice-lab</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-data-ldap</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>com.unboundid</groupId>
      <artifactId>unboundid-ldapsdk</artifactId>
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

There is no Spring Security starter here. `@DataLdapTest` verifies LDAP data access, **not** the application's authentication manager, role mapping, or security filter chain. For Spring Security LDAP, write separate tests at the security boundary.

### 12.3. LdapLabApplication.java

`src/main/java/com/example/ldaplab/LdapLabApplication.java`:

```java
package com.example.ldaplab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LdapLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(LdapLabApplication.class, args);
    }
}
```

### 12.4. ldap-test.ldif

`src/test/resources/ldap-test.ldif`:

```ldif
dn: dc=example,dc=org
objectClass: top
objectClass: domain
dc: example

dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: uid=alice,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: alice
cn: Alice Nguyen
sn: Nguyen
```

No real passwords or employee accounts are included; the data is a pure fixture. Ensure proper newlines and a blank line separating entries. LDIF has specific rules for non-ASCII encoding and continuation lines; the fixture uses plain ASCII to avoid encoding quirks. If adding Vietnamese names, use valid UTF-8 LDIF.

### 12.5. LdapDirectoryTest.java

`src/test/java/com/example/ldaplab/LdapDirectoryTest.java`:

```java
package com.example.ldaplab;

import java.util.List;
import javax.naming.Name;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.ldap.DataLdapTest;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

import static org.assertj.core.api.Assertions.assertThat;

@DataLdapTest(properties = {
        "spring.ldap.base=dc=example,dc=org",
        "spring.ldap.embedded.base-dn=dc=example,dc=org",
        "spring.ldap.embedded.ldif=classpath:ldap-test.ldif"
})
class LdapDirectoryTest {

    @Autowired
    LdapTemplate ldapTemplate;

    @Test
    void findsSeededDirectoryEntry() {
        List<String> names = ldapTemplate.search(
                "ou=people",
                "(uid=alice)",
                (AttributesMapper<String>) attrs ->
                        attrs.get("cn").get().toString());

        assertThat(names).containsExactly("Alice Nguyen");
    }

    @Test
    void unknownUidReturnsEmptySearch() {
        List<String> names = ldapTemplate.search(
                "ou=people",
                "(uid=not-present)",
                (AttributesMapper<String>) attrs ->
                        attrs.get("cn").get().toString());

        assertThat(names).isEmpty();
    }

    @Test
    void createsAndDeletesOnlyItsOwnEntry() {
        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", "bob")
                .build();

        DirContextAdapter entry = new DirContextAdapter(dn);
        entry.setAttributeValues("objectClass", new String[] {
                "top", "person", "organizationalPerson", "inetOrgPerson"
        });
        entry.setAttributeValue("uid", "bob");
        entry.setAttributeValue("cn", "Bob Tran");
        entry.setAttributeValue("sn", "Tran");

        boolean bound = false;
        try {
            ldapTemplate.bind(entry);
            bound = true;

            String commonName = ldapTemplate.lookup(
                    dn,
                    (AttributesMapper<String>) attrs ->
                            attrs.get("cn").get().toString());

            assertThat(commonName).isEqualTo("Bob Tran");
        }
        finally {
            if (bound) {
                ldapTemplate.unbind(dn);
            }
        }
    }
}
```

**Detailed explanation:**
- `@DataLdapTest` sets up the LDAP slice, template, and embedded UnboundID when conditions match.
- `spring.ldap.base` lets the template work with relative DNs: `ou=people`, `uid=bob,ou=people`. The LDAP server still stores full DNs under `dc=example,dc=org`.
- `LdapTemplate.search` runs LDAP filter `(uid=alice)` under the organizational unit; the mapper extracts the `cn` attribute.
- The unknown-user test proves searches return an empty list rather than assuming other default users exist.
- `DirContextAdapter` constructs an LDAP entry with valid object classes and attributes.
- `LdapTemplate.bind` adds the entry; `lookup` reads back the DN and attribute.
- `finally` unbinds that specific DN; the LDAP slice does not auto-rollback inserted records.
- All static fixture data stays repeatable as long as cleanup completes and contexts/fixtures are not mutated concurrently by other tests.

**Note on repository mapping:** The lab uses `LdapTemplate` to keep the example short and DNs explicit. Spring Data LDAP also offers `@Entry`, `@DnAttribute`, `@Attribute`, and `LdapRepository`, which are helpful when the application uses a full repository model. `@DataLdapTest` supports both. Never assume an LDAP entry maps like a JPA entity.

### 12.6. Running the LDAP lab

```bash
mvn -q clean test
mvn -q -Dtest=LdapDirectoryTest test
```

This lab requires neither Docker nor an external LDAP server. When Maven/tests PASS, exit code is 0; if the context fails due to LDIF/schema/base DN issues, inspect `target/surefire-reports` and Spring Boot startup logs. Never use `spring.ldap.urls=ldap://ldap.company...` in this lab.

### 12.7. When a real LDAP server is needed

Spring Boot reference supports excluding embedded LDAP from the slice:

```java
import org.springframework.boot.autoconfigure.ldap.embedded.EmbeddedLdapAutoConfiguration;
import org.springframework.boot.test.autoconfigure.data.ldap.DataLdapTest;

@DataLdapTest(
    excludeAutoConfiguration = EmbeddedLdapAutoConfiguration.class,
    properties = {
        "spring.ldap.urls=ldap://127.0.0.1:1389",
        "spring.ldap.base=dc=example,dc=org"
    })
class ExternalDirectoryTest {
    // Requires a real test-only LDAP server at that URI.
}
```

This is an **illustrative pattern**, not part of the runnable lab; `127.0.0.1:1389` is merely the address of a separately started LDAP test server. Real LDAP servers may require bind principal/password, StartTLS/LDAPS, truststores, network access, and permissions. Never connect to a production Directory from unit tests.

## 13. LdapRepository/@Entry: an alternative to LdapTemplate

### 13.1. LDAP entity using @Entry

Example describing an LDAP directory object (advanced snippet, not part of the lab created above):

```java
@Entry(base = "ou=people",
       objectClasses = {"top", "person", "organizationalPerson", "inetOrgPerson"})
public class DirectoryPerson {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    // No-arg constructor, getters/setters
}
```

The corresponding imports are Spring Data LDAP annotations `org.springframework.ldap.odm.annotations.Entry`, `Id`, and `Attribute`. This snippet is **not a standalone compilable file** because constructors/accessors are omitted; in a real project, provide complete mapping and a DN generation/update strategy.

A repository:

```java
public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {
}
```

requires `org.springframework.data.ldap.repository.LdapRepository` and entity scanning. When the ID is a full/relative DN and base DN is configured, keep mappings consistent; do not treat a UID string like a SQL primary key when the repository expects a `Name`/DN.

### 13.2. Filter injection

A filter built from input:

```java
String filter = "(uid=" + externalUserInput + ")";
```

can have `*`, `)`, `(`, or escape sequences injected. This is an **anti-pattern**. Use Spring LDAP filter builders or RFC 4515 escaping (e.g., `EqualsFilter`), and assert that input containing special characters does not widen the search condition.

### 13.3. Embedded LDAP does not simulate every enterprise schema

UnboundID works well for basic DNs/searches/mappings. However, Active Directory, OpenLDAP, and other Directory services may involve:
- Schema extensions/custom attributes.
- Group membership/`memberOf` semantics.
- ACLs and bind rules.
- Password policies, lockouts, and password hashing.
- StartTLS/LDAPS, certificates/truststores.
- Referral chasing, paging/sorting controls.
- Different case/normalization behavior.

For specialized requirements, add sandbox integration tests against the real directory engine rather than treating embedded LDAP PASS as proof of all security/policy behavior.

## 14. @ServiceConnection and @DynamicPropertySource

### 14.1. How does service connection work?

With Boot 3.5 and `spring-boot-testcontainers`, `@ServiceConnection` on a typed container lets Boot supply connection details automatically. Boot ships built-in factories for `CassandraConnectionDetails` from `CassandraContainer` and `CouchbaseConnectionDetails` from `CouchbaseContainer`. These details can take precedence over regular connection properties.

```java
@Testcontainers
@DataCassandraTest(properties = "spring.cassandra.keyspace-name=training")
class ContainerSliceTest {
    @Container
    @ServiceConnection
    static CassandraContainer<?> cassandra =
            new CassandraContainer<>("cassandra:4.1");
}
```

This snippet is **not standalone runnable** without the schema/keyspace from Section 6, and imports are omitted. It illustrates how connection details are registered, not automatic keyspace creation.

### 14.2. Do not assume @ServiceConnection creates schemas or buckets

- Cassandra: `@ServiceConnection` provides endpoint/datacenter/credentials from the container factory; **it does not replace `CREATE KEYSPACE`/`CREATE TABLE`**.
- Couchbase: connection details provide cluster endpoint/credentials; **the bucket and scope/collection** must still be provisioned/configured properly on the container.
- LDAP: embedded auto-configuration has its own mechanism; `@ServiceConnection` is not needed for the UnboundID lab in Section 12.

This is a common cause of context startup failures: the client reaches the server, yet the keyspace/bucket does not exist yet.

### 14.3. @DynamicPropertySource when custom connection settings are needed

If a typed service connection cannot be used, register properties dynamically:

```java
@DynamicPropertySource
static void cassandraProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.cassandra.contact-points",
            () -> cassandra.getHost() + ":" + cassandra.getMappedPort(9042));
    registry.add("spring.cassandra.local-datacenter",
            cassandra::getLocalDatacenter);
    registry.add("spring.cassandra.keyspace-name", () -> "training");
}
```

This is a snippet inside a class that already declares `static CassandraContainer<?> cassandra`. It requires `DynamicPropertySource`/`DynamicPropertyRegistry` imports and schema initialization before startup. If your Boot 3.5 config requires a specific contact-points/port format, follow the Boot reference/Javadoc; `@ServiceConnection` is generally less error-prone.

Never add both `@ServiceConnection` and manual contact-point overrides expecting the manual properties to win: connection details can take precedence over properties.

### 14.4. Container lifecycle in Spring TestContext

A static `@Container` under the JUnit Testcontainers extension starts/stops with the class lifecycle. Spring TestContext **caches application contexts** across multiple test classes with identical configuration; this creates a risk of a cached context holding a connection to a stopped container. For large suites, consider declaring the container as a Spring bean in `@TestConfiguration` with `@ServiceConnection`, or use the context isolation/caching strategy recommended in Spring Boot 3.5 documentation.

Pin Docker image digests/tags intentionally for repeatable CI runs; never use `latest` for Cassandra/Couchbase without checking migration compatibility.

## 15. Test data isolation and cleanup

### 15.1. Why is there no automatic rollback?

A Cassandra or Couchbase `save` and `ldapTemplate.bind` mutate external state outside the test method. These `@Data...Test` annotations do not open a JDBC/JPA transaction and roll back by default. Therefore:

- Tests must generate **distinct IDs/DNs**.
- Delete/clean up in `finally`/`@AfterEach`.
- Use dedicated test containers/buckets/keyspaces/base DNs.
- Accept that cleanup may not run if the JVM is killed; **ephemeral infrastructure** is the safety net.
- Never point at production, even to "run just one integration test".
- Avoid running parallel tests on shared keys/entries without namespaces or isolation.

### 15.2. Cassandra cleanup

Usually delete rows by primary key:

```java
try {
    repository.save(new CassandraItem("test-id", "data"));
    // assertions
}
finally {
    repository.deleteById("test-id");
}
```

If a test performs multiple writes/partitions, clean up all of them. Cassandra deletes create tombstones; with large datasets, do not generate millions of tombstones just for testing. Ephemeral keyspaces/containers are better suited for heavy test workloads.

### 15.3. Couchbase cleanup

```java
try {
    repository.save(new CatalogDocument("test-id", "data"));
    // assertions
}
finally {
    repository.deleteById("test-id");
}
```

If tests query via a secondary index, cleanup may not appear immediately in query results due to index consistency; tests should not assert zero counts immediately without accounting for consistency semantics. For parallel suites, use test ID prefixes or bucket/collection isolation.

### 15.4. LDAP cleanup

```java
Name dn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "temporary")
        .build();

try {
    ldapTemplate.bind(context);
    // assertions
}
finally {
    ldapTemplate.unbind(dn);
}
```

This snippet assumes `context` was built with a valid DN/schema, and should only unbind if binding succeeded; the runnable lab uses a `bound` flag to avoid masking the original exception. Never unbind an entire organizational unit or base DN because it can wipe shared test fixtures.

### 15.5. @DirtiesContext does not clean the data store

`@DirtiesContext` only resets the lifecycle of the cached Spring context; it does not delete rows/documents/entries from Cassandra/Couchbase/LDAP. It also slows tests down by forcing context restarts. Cleanup must happen on the real data store or via discarding ephemeral containers when the suite ends.

## 16. Mapping and query correctness: testing by contract

### 16.1. Field types differ across backends

| Concept | Cassandra | Couchbase | LDAP |
| --- | --- | --- | --- |
| Identity | Partition/clustering primary key | Document key/ID | Distinguished Name (DN) |
| Schema | CQL schema/keyspace/table | Flexible JSON document schema, indexes | LDAP object classes/attribute schema |
| Query | CQL with key/index rules | KV + SQL++/N1QL | LDAP filters/search scope |
| Ordering | Clustering order within partition | Only if query specifies ORDER BY | LDAP search does not guarantee sort |
| Missing value | CQL null/unset semantics | JSON null/missing semantics | Absent attribute vs. empty string |
| Consistency | Tunable consistency + replication | KV durability/query scan consistency | Directory server/replica/referral/replication |
| TTL | Native TTL | Expiry (document) | Not a universal LDAP property |
| Transactions | Batches/LWT, not JPA test rollback | Separate Couchbase transactional APIs if used | LDAP ops have no JDBC test rollback |

Do not write a single test helper that imposes the same "save, query count, rollback after test" assumption across all three backends.

### 16.2. Verify critical data fields

When domain logic depends on mapping:
- Cassandra: ID, column names/CQL types, partition keys, custom converters, TTL/consistency.
- Couchbase: document ID, field names, JSON types, `@Version`/CAS, expiry, scope/collection, query indexes.
- LDAP: DN/base, RDN, objectClass, attributes, group membership/filters and escaping.

Include negative tests: missing key/unknown DN, invalid schema/type, unmatched queries, access denied, expired documents, or invalid credentials when required. However, never pull security/TLS assertions into embedded-only tests and conclude production is secure.

## 17. Common errors and resolutions

### 17.1. No qualifying bean for repository/template

**Cause:** missing starter module, repository outside auto-scanned package, wrong backend mapping annotation, or slice filter excluding the bean. Check `mvn dependency:tree`, packages, and imports. Never fix blindly with `@SpringBootTest`.

### 17.2. Missing @Service or @ConfigurationProperties in slice

**Cause:** slices exclude regular components. **Fix:** `@Import(MyService.class)` or `@EnableConfigurationProperties(MyProperties.class)` only when truly part of the test boundary. If testing full workflows and multiple adapters, use a full integration test.

### 17.3. Cassandra connection refused / no host available

**Cause:** no Cassandra server running, Docker down, startup incomplete, wrong host/port/datacenter. **Fix:** verify Testcontainers runtime, `@ServiceConnection`, Cassandra logs, keyspace, and local datacenter. Never point to production Cassandra for convenience.

### 17.4. Cassandra InvalidQueryException: unconfigured table

**Cause:** `schema.cql` did not run, wrong test keyspace, or table name mismatches `@Table`. **Fix:** verify resource path, CQL init script, keyspace `training`, and table `catalog_item`. Do not rely on JPA `ddl-auto=create-drop`; that property means nothing to Cassandra.

### 17.5. Cassandra query rejected due to missing key/index

**Cause:** query does not match primary key. **Fix:** design access patterns, tables/materialized views/indexes properly; using `ALLOW FILTERING` requires performance evaluation and justification, never use it as a quick patch.

### 17.6. Couchbase authentication or bucket not found

**Cause:** connection details exist, yet `spring.data.couchbase.bucket-name` is wrong, the bucket was not provisioned, or credentials/network failed. **Fix:** ensure the bucket name in `BucketDefinition` matches the Boot property and inspect container logs.

### 17.7. Couchbase findById PASSES, derived query FAILS

**Cause:** KV get needs no index, while queries need the query service/index/scope or consistency settings. **Fix:** create appropriate indexes/schema; test consistency per contract rather than adding sleeps to hope data shows up.

### 17.8. Couchbase timeout on CI

**Cause:** Couchbase container starts slowly / low RAM, bucket warm-up, Query service not ready yet. **Fix:** allocate sufficient resources/timeouts, pin image tags, and track startup readiness; never silently skip tests and report PASS.

### 17.9. LDAP NoSuchObjectException

**Cause:** wrong base DN, `ou=people` missing from LDIF, relative/full DNs mixed up, or wrong object hierarchy. **Fix:** check `spring.ldap.base`, `spring.ldap.embedded.base-dn`, and the LDIF tree; search with the right relative DN.

### 17.10. LDAP invalid attribute/objectClass

**Cause:** entry missing `cn`/`sn`, objectClass does not support the attribute, or LDIF breaks schema. **Fix:** supply valid object classes and required attributes; never disable `spring.ldap.embedded.validation.enabled` just to turn tests green if schema validation is a core risk.

### 17.11. LDAP filter injection

**Cause:** concatenating unescaped user input into filter strings. **Fix:** use Spring LDAP filter builders/escaping, test malicious inputs, and restrict search scope. Never treat a broad search result as "user authenticated".

### 17.12. Embedded LDAP PASSES, enterprise LDAP FAILS

**Cause:** differences in schema, ACLs, binds, groups, TLS/LDAPS/StartTLS, pagination, or referrals. **Fix:** add integration tests against a matching test directory engine with fake users/groups, test TLS certificates, and realistic permissions.

### 17.13. Passes locally, fails in parallel runs

**Cause:** reusing the same Cassandra key, Couchbase document ID, or LDAP DN; shared container/bucket/context mutable state. **Fix:** unique IDs, test namespaces, cleanup, and backend isolation; never rely on JUnit execution order.

### 17.14. @DirtiesContext used to clear NoSQL test data

**Wrong:** it only clears the Spring context cache. **Fix:** delete/flush collections, use ephemeral containers, or explicitly tear down data store state.

### 17.15. @Transactional does not auto-rollback NoSQL tests

**Cause:** NoSQL/LDAP repository operations do not live inside a JDBC/JPA test transaction by default. **Fix:** understand native transaction support, test the actual boundary, and clean up explicitly. Do not use JPA's `TestTransaction` expecting Cassandra/Couchbase/LDAP rollback.

### 17.16. Testcontainers skipped due to missing Docker

**Cause:** `@Testcontainers(disabledWithoutDocker = true)` skips integration tests. **Fix:** CI integration jobs must run on Docker-enabled runners and require tests to actually execute (`skipped=0`) before qualifying a build; unit/LDAP tests can run in a separate Docker-less job.

### 17.17. Mixing Spring Boot 3.5 with Boot 4 imports

**Cause:** Boot 4 moves data slice annotations into dedicated modules with new packages. **Fix:** follow the BOM and docs for your major version; inspect actual compiler errors rather than forcing `spring-boot-test-autoconfigure:3.x` into Boot 4.

### 17.18. Tests using production credentials

**Cause:** test profile reads app secrets or environment variables matching production. **Fix:** test containers, embedded LDAP, fake users, and isolated credentials. CI must never log tokens, passwords, or real LDAP user data.

## 18. Multi-layered test architecture

| Goal | Test type | Technology |
| --- | --- | --- |
| Domain validation or calculations unrelated to data stores | JUnit/Mockito | No Spring context |
| Cassandra `@Table`/primary key/repository CRUD mapping | `@DataCassandraTest` | Cassandra container |
| Couchbase `@Document`/KV repository mapping | `@DataCouchbaseTest` | Couchbase container |
| LDAP DN/search/attributes | `@DataLdapTest` | Embedded UnboundID |
| Cassandra CQL, TTL, LWT, multi-node consistency | Slice + suitable integration environment | Matching Cassandra cluster/version |
| Couchbase SQL++/indexes/consistency/CAS | Slice + provisioned indexes/cluster | Couchbase test server |
| LDAP auth/groups/schema/ACLs/TLS | Slice or full-context integration | Real LDAP sandbox engine |
| Service coordinating Cassandra + Couchbase + LDAP | `@SpringBootTest` | Test stores + fake external boundaries |
| REST controller returning JSON backed by store | `@WebMvcTest` or `@WebFluxTest` | Mock service or real storage depending on goal |
| Observability/retry/circuit breaker integration | Full-context/integration | Instrumentation and controlled fault injection |

You do not need end-to-end tests for every field: keep plenty of **fast unit tests**, focused **data slice tests** per technology, and targeted **cross-component integration tests** for coupling risks.

### 18.1. Cost and speed

- Embedded LDAP starts quickly and needs no Docker.
- Cassandra containers spin up a cluster and take noticeable time and resources.
- Couchbase containers are heavy, running multiple services and bucket initialization.
- Full application contexts can cost more than slices when pulling unrelated infrastructure.

You can separate Maven test targets for unit vs. integration tests, yet never equate skipped tests with PASSING tests. In real CI pipelines, teams may gate Cassandra/Couchbase integration jobs on runners with Docker and enough RAM; always report coverage transparently.

## 19. Security and stability checklist

### 19.1. Secrets and personal data

- Never use production Cassandra/Couchbase/LDAP credentials in tests.
- Never store real passwords, employee emails/IDs, or access tokens in LDIF fixtures.
- Use test-only service accounts with least privilege.
- Never print plain-text LDAP bind credentials or Couchbase admin passwords to CI logs.
- When testing TLS, use properly managed self-signed/test certificates; never disable certificate verification in production configs.

### 19.2. Resource isolation

- Each test uses distinct keys/IDs/DNs to avoid collisions.
- Clean up in `finally`/test teardown and rely on ephemeral infrastructure.
- Do not rely on `@DirtiesContext` or implicit rollback to wipe NoSQL rows.
- Align container lifecycle with Spring TestContext caching for static containers.
- Configure reasonable memory/CPU/readiness timeouts for Cassandra/Couchbase.
- Align backend/test image versions with production compatibility targets.

### 19.3. Meaningful business assertions

A test asserting `repository.count() > 0` is weak when fixtures are pre-seeded or stores are shared. Assert exact identity, fields, query results, and negative paths. For LDAP DNs, assert paths/base and attributes; for Cassandra/Couchbase, assert mapping/queries matching access patterns.

## 20. Practice exercises

1. Create a project with only Spring Data Cassandra and `@DataCassandraTest`; explain why tests do not get an embedded Cassandra automatically.
2. Use `CassandraContainer` and `@ServiceConnection`; deliberately omit `schema.cql` to observe the keyspace/table error, then restore the schema.
3. For a Cassandra composite key, add `@PrimaryKeyColumn` for partition and clustering columns; test querying by the exact partition key.
4. Add a TTL to a Cassandra write and design a test with bounded polling instead of arbitrary sleeps.
5. Create a Couchbase `@Document` and `findById` repository, verifying round-trip persistence on a test bucket.
6. Add a derived query `findByTitle` to Couchbase; provision an index and compare KV lookup against query consistency.
7. Intentionally set `spring.data.couchbase.bucket-name` to an invalid name and explain the resulting error.
8. Create an LDIF entry with `uid=alice` and `@DataLdapTest`; search by OU and attributes.
9. Add a temporary LDAP entry using `DirContextAdapter`, look it up, and unbind it in `finally`.
10. Build a filter using external input containing `*`/`)`; prove the filter builder escapes input so searches do not unexpectedly broaden.
11. Use `@EnableConfigurationProperties` to bring a custom properties bean into a slice; contrast with scanning all `@Component` beans.
12. Why don't `@Transactional` and `@DirtiesContext` automatically clean up NoSQL writes? Propose solutions.
13. Run all three labs separately, noting which need Docker and which do not; distinguish PASS from SKIPPED.
14. Outline how to add a full integration test for a service that uses both Cassandra and LDAP.
15. When upgrading Boot from 3.5 to 4.x, where would you check annotation packages, Maven starter names, Testcontainers versions, and service connection changes?

Pass criteria: learners identify the **right backend**, **right slice**, **right test infrastructure**, **right schema/identity/indexes**, **exact verified scope**, and **proper cleanup**.

## 21. Pre-merge checklist

- [ ] Application actually uses Cassandra/Couchbase/LDAP; no unnecessary starters added?
- [ ] Spring Boot/Java versions and annotation imports match Boot 3.5 major?
- [ ] Exactly one test slice selected per class, without stacking multiple slices?
- [ ] Unnecessary `@Component`/`@ConfigurationProperties` beans excluded from context?
- [ ] When custom properties are needed, `@EnableConfigurationProperties` used selectively?
- [ ] Cassandra tests have the right engine, keyspace, table schema, and local datacenter?
- [ ] Cassandra `@Table`/primary key mapping and CQL access patterns tested?
- [ ] Cassandra cleanup scoped by primary key/ephemeral keyspace rather than relying on rollback?
- [ ] Couchbase tests have container, bucket, credentials, and required services?
- [ ] Couchbase `@Document`/`@Id`/`@Field` accurate and repository mapping asserted?
- [ ] Couchbase KV lookup vs. query/index/consistency clearly separated?
- [ ] LDAP tests have UnboundID and accurate base DN/LDIF?
- [ ] LDAP filter escaping, DN, objectClass/attribute schema tested?
- [ ] LDAP bind/unbind never touches real users or directories?
- [ ] `@ServiceConnection`/`spring-boot-testcontainers`/Testcontainers module versions aligned?
- [ ] If Docker is missing, CI does not treat skipped tests as integration PASS?
- [ ] All generated data has explicit cleanup or ephemeral service lifecycle?
- [ ] Parallel tests have unique IDs/DNs and isolation?
- [ ] Backend images/schemas/test setups match production-critical behaviors?
- [ ] Security/TLS/ACLs are not inferred from simple mapping tests?
- [ ] Negative paths tested, not just happy paths?
- [ ] Maven tests executed in the right CI job and Surefire reports reviewed?

**Conclusion:** `@DataCassandraTest`, `@DataCouchbaseTest`, and `@DataLdapTest` isolate the **non-SQL data access layer** rather than providing magical fake databases. Cassandra and Couchbase generally need Testcontainers or a real test cluster, while LDAP can run with embedded UnboundID. Each slice keeps real mappings/repositories/templates while excluding most unrelated application components. Because there is no default JPA-style rollback, design isolated fixtures, identities, cleanup, and infrastructure boundaries. When tests need query semantics, authentication, or multi-store workflows, widen the boundary with an appropriate integration test instead of asking a slice to prove what it does not cover.

## 22. Official references

- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 — Test Slices auto-configuration appendix: https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html
- Spring Boot 3.5 — Working with NoSQL Technologies: https://docs.spring.io/spring-boot/3.5/reference/data/nosql.html
- Spring Boot 3.5 — Testcontainers / Service Connections: https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html
- Spring Boot 3.5 — `@DataCassandraTest` Javadoc: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/data/cassandra/DataCassandraTest.html
- Spring Boot 3.5 — `@DataCouchbaseTest` Javadoc: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/data/couchbase/DataCouchbaseTest.html
- Spring Boot 3.5 — `@DataLdapTest` Javadoc: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/data/ldap/DataLdapTest.html
- Spring Data Apache Cassandra — Reference: https://docs.spring.io/spring-data/cassandra/reference/
- Spring Data Couchbase — Reference: https://docs.spring.io/spring-data/couchbase/reference/
- Spring Data LDAP — Reference: https://docs.spring.io/spring-data/ldap/reference/
- Spring LDAP — Directory Context Adapter: https://docs.spring.io/spring-ldap/reference/dirobjectfactory.html
- Spring LDAP — Testing: https://docs.spring.io/spring-ldap/reference/testing.html
- Testcontainers Java — Cassandra Module: https://java.testcontainers.org/modules/databases/cassandra/
- Testcontainers Java — Couchbase Module: https://java.testcontainers.org/modules/databases/couchbase/
- Spring Boot 4 Migration Guide: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide
