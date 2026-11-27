# Reading the release train and Boot–Spring Data–driver–server matrix

## 1. Why read the entire version chain?

Applications using **Spring Data MongoDB** typically write code with **MongoTemplate**, **MongoRepository**, **ReactiveMongoTemplate**, or reactive repositories. At runtime, however, those APIs also rely on Spring Framework, the MongoDB Java Driver, and MongoDB Server. An application can compile cleanly and still fail when connecting or reading BSON because the components are incompatible.

In the **Versions and Upgrades** chapter of the **SPRING_DATA_MONGODB** module, the goal is to know how to choose and verify **a version combination**, rather than just changing the version number of a single dependency.

~~~mermaid
flowchart TB
    JDK["Java / JDK"]
    Boot["Spring Boot<br/>plugin + dependency management"]
    Train["Spring Data release train<br/>BOM synchronizing modules"]
    SD["Spring Data MongoDB<br/>MongoTemplate / Repository"]
    Driver["MongoDB Java Driver<br/>sync / reactive / BSON"]
    Server[("MongoDB Server<br/>standalone / replica set / sharded")]
    Framework["Spring Framework<br/>container / transaction / conversion"]
    JDK --> Boot
    Boot --> Framework
    Boot --> Train
    Train --> SD
    Boot --> Driver
    SD --> Driver
    Driver <-->|"Wire protocol, commands, features"| Server
~~~

At minimum, answer **six questions** before upgrading:

1. Which **Spring Boot** version is the application using, and which **JDK** does it run on?
2. Which **Spring Data release train** does that Boot version manage?
3. Which **spring-data-mongodb** version does that release train contain?
4. What **minimum MongoDB Java Driver** does that Spring Data MongoDB version require? Which driver version is actually on the runtime classpath?
5. To what extent is that driver compatible with the **MongoDB Server** in use?
6. Will the features the application uses (transactions, change streams, aggregations, indexes, codecs, queries, TLS, etc.) still work properly on the new combination?

**Key takeaway:** "runs together" does not necessarily mean "tested in this combination," "long-term supported," or "every new feature is usable."

## 2. Distinguishing five commonly confused version systems

| Component | Example | Meaning |
| --- | --- | --- |
| **Spring Boot** | 3.5.x, 4.0.x, 4.1.x | Application platform, auto-configuration, starters, BOM, Java/Spring Framework requirements |
| **Spring Data release train** | 2025.0.x, 2025.1.x, 2026.0.x | Synchronized release group of Spring Data modules |
| **Spring Data MongoDB** | 4.5.x, 5.0.x, 5.1.x | Specific version of the mapping/repository library for MongoDB |
| **MongoDB Java Driver** | 5.5.x, 5.6.x, 5.8.x | Driver handling BSON, sessions, cluster topology, and wire protocol |
| **MongoDB Server** | 6.0, 7.0, 8.0 | Database version executing commands, aggregations, and transactions |

**A Spring Data release train is not a Spring Data MongoDB version.** For example, train **2026.0** contains Spring Data MongoDB **5.1.x** and Spring Data Commons **4.1.x**. You cannot put **2026.0** as the version of the Maven artifact **spring-data-mongodb**.

**Spring Data MongoDB is also not the MongoDB Java Driver.** The **org.springframework.data:spring-data-mongodb** artifact implements mapping/repositories; the **org.mongodb:mongodb-driver-sync**, **mongodb-driver-reactivestreams**, **mongodb-driver-core**, and **bson** artifacts handle driver communication and BSON processing.

### What is a release train?

**Spring Data** consists of multiple modules developed and released on a shared schedule, while each module has its own version history. A **release train** bundles a curated set of versions to be used together via a **BOM** (Bill of Materials).

In newer Spring Data generations, release train names use calendar versioning:

~~~text
2026.0.2
│    │ └─ Service release / iteration
│    └─── Release line within the year
└──────── Release year
~~~

Example version formats:

| Pattern | Interpretation |
| --- | --- |
| **2026.0.0** | First GA release of train 2026.0 |
| **2026.0.2** | Maintenance release of the same train |
| **2026.1.0-M2** | Milestone of a new train, not necessarily suitable for production |
| **2026.1.0-RC1** | Release candidate; review deployment policy before using |
| **2026.1.0-SNAPSHOT** | Development snapshot, subject to change |

When you see a library like **Spring Data MongoDB 5.1.2**, do not infer that it is a release train version or Spring Boot **5.1**. You must check the BOM to see the exact relationship.

## 3. Reading the matrices in the right order

No single table replaces all compatibility tables. You need to combine information from multiple official sources:

| Table / document | Question answered | What does it NOT prove? |
| --- | --- | --- |
| **Spring Boot Managed Dependency Coordinates** | Which exact Spring Data MongoDB, driver, and BSON versions will this Boot version select if not overridden? | Does not confirm the actual MongoDB Server supports every feature |
| **Spring Data Dependencies / Release Train BOM** | Which Spring Data modules belong to which train? | Does not describe all Spring Boot dependencies |
| **Spring Data MongoDB Requirements / Compatibility Matrix** | How trains and Spring Data MongoDB relate; minimum driver and tested servers? | Not a list of every driver patch managed by Boot |
| **MongoDB Java Driver Compatibility Tables** | Is the driver compatible with the server and Java runtime per MongoDB's policy? | Does not verify your Spring Data code, queries, or business logic |
| **Migration Guide and Release Notes** | Which APIs, behaviors, configurations, or storage types changed? | Does not automatically fix code or data |
| **Actual resolved build dependencies** | Which versions did the artifacts ultimately resolve to? | Does not guarantee those resolved versions form a supported combination |

Reading order:

~~~mermaid
flowchart TD
    A["Record current Boot and Java versions"]
    B["Check the BOM of that exact Boot patch"]
    C["Identify Spring Data release train and MongoDB module"]
    D["Check Requirements: minimum driver, tested servers"]
    E["Check driver ↔ server and Java compatibility"]
    F["Read migration guide + changelog"]
    G["Inspect resolved dependencies in the build"]
    H["Run integration tests against actual server and topology"]
    A --> B --> C --> D --> E --> F --> G --> H
~~~

**Read top-down:** Boot determines the default dependency set; Spring Data defines library support boundaries; the driver determines server interaction; and application tests prove specific functionality.

## 4. Spring Data MongoDB and MongoDB Java Driver matrix

The following table is drawn from the **Compatibility Matrix** section in the Spring Data MongoDB documentation, verified on **November 20, 2026**. Documentation may be updated when new releases arrive, so during an actual upgrade you must reopen the page for the exact **release train** you choose.

| Spring Data release train | Spring Data MongoDB | Stated minimum driver | MongoDB Server tested by Spring Data |
| --- | --- | --- | --- |
| **2026.0** | **5.1.x** | **5.6.x** | **6.x – 8.x** |
| **2025.1** | **5.0.x** | **5.6.x** | **6.x – 8.x** |
| **2025.0** | **4.5.x** | **5.5.x** | **6.x – 8.x** |
| **2024.1** | **4.4.x** | **5.2.x** | **4.4.x – 8.x** |
| **2024.0** | **4.3.x** | **4.11.x or 5.x** | **4.4.x – 7.x** |

Source: [Spring Data MongoDB — Requirements and Compatibility Matrix](https://docs.spring.io/spring-data/mongodb/reference/preface.html).

### How to read a row?

For example, the **2026.0** row indicates:

1. If you choose release train **2026.0**, the MongoDB module belongs to the **5.1.x** line.
2. Spring Data MongoDB on that line requires **MongoDB Java Driver 5.6.x or higher** as its published minimum.
3. The Spring Data test suite ran against the listed **server generations 6.x through 8.x**.
4. It does **not** mean Boot always resolves exactly driver **5.6.x**; Boot's BOM may select a newer version.
5. It does **not** mean every server combination outside the listed range fails; those need additional checks against the driver–server matrix and testing.

### "Minimum driver" vs. "managed driver"

Suppose a train states **Minimum Driver Version = 5.6.x** and Spring Boot manages **5.8.1**:

- **5.6.x** is the minimum threshold for Spring Data MongoDB in that documentation.
- **5.8.1** is the version your build may actually use if you keep Boot's dependency management.
- You do not need to downgrade the driver to **5.6.x** just to match the "minimum" column literally.
- You should not arbitrarily upgrade to another driver just because it is the latest: you must evaluate Spring Data, Boot, and Java runtime support.

**"Tested database versions"** describes the range of server versions exercised in Spring Data's test suite, not a guarantee that every server configuration, command, and feature is tested for your application.

## 5. Mapping a release train to Spring Boot

The Boot–Spring Data pairing depends on the **specific Boot version** and its accompanying BOM. To visualize the release lines, see the following examples:

| Spring Boot line | Corresponding Spring Data release train | Corresponding Spring Data MongoDB |
| --- | --- | --- |
| **3.4.x** | **2024.1.x** | **4.4.x** |
| **3.5.x** | **2025.0.x** | **4.5.x** |
| **4.0.x** | **2025.1.x** | **5.0.x** |
| **4.1.x** | **2026.0.x** | **5.1.x** |

This shows **relationships between lines**, not a patch-by-patch matrix. If an application uses **Boot 3.5.3**, you must check the exact documentation/BOM for that patch; you cannot assume every dependency matches **Boot 3.5.13**.

To see concrete patch differences at the time the Boot dependency docs were consulted:

| Example Boot version | Spring Data MongoDB managed by Boot | MongoDB Java Sync Driver managed by Boot |
| --- | --- | --- |
| **3.5.13** | **4.5.13** | **5.5.2** |
| **4.0.10** | **5.0.9** | **5.6.5** |
| **4.1.3** | **5.1.3** | **5.8.1** |

Sources are the [Boot 3.5 Managed Dependencies](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html), [Boot 4.0 Managed Dependencies](https://docs.spring.io/spring-boot/4.0/appendix/dependency-versions/coordinates.html), and [Boot 4.1 Managed Dependencies](https://docs.spring.io/spring-boot/4.1/appendix/dependency-versions/coordinates.html) pages.

**How to read accurately:** take the **org.springframework.data:spring-data-mongodb** and **org.mongodb:mongodb-driver-sync** entries from the same Boot document. For reactive, also look up **mongodb-driver-reactivestreams**. For BSON, track both **mongodb-driver-core** and **bson**, because mixing mismatched patches manually can create hard-to-diagnose classpath issues.

**Boot 4.2.x** and newer Spring Data lines may be released on their own schedules; check [Spring Project Generations](https://spring.io/projects/generations/) and the BOM of the exact Boot version chosen rather than guessing by incrementing numbers.

## 6. Checking the MongoDB Java Driver ↔ Server matrix

Once you know the runtime driver, proceed to check the [MongoDB Client Library Compatibility Tables](https://www.mongodb.com/docs/drivers/compatibility/?driver-language=java&java-driver-framework=java-sync).

In MongoDB's table, you may encounter:

| Symbol | Practical meaning |
| --- | --- |
| **✓** | The driver fully supports features within the published compatibility scope for that server |
| **⊛** | Can connect, but does not yet support all new features of the server |
| **✗** | Combination marked as incompatible |
| **Blank** | Not yet published as tested/compatible in that table |

You must read both the **driver row** and the **MongoDB Server column**. For example, a driver may connect to a newer server without supporting a new server feature; an application doing basic CRUD might keep running, while an application relying on the new command must upgrade the driver.

**Three independent verification levels:**

1. **Spring Data supports the driver**: check the minimum version and migration guide of Spring Data MongoDB.
2. **MongoDB supports the driver/server combination**: check the official driver compatibility table.
3. **The application supports the actual combination**: run integration tests and verify data, performance, and errors in an appropriate environment.

Beyond server version, topology also affects features:

- **Transactions** require a replica set or sharded cluster as required by MongoDB; a standalone instance does not become a transaction test environment just by changing the driver.
- **Change streams** require a supporting replica set or sharded cluster; account for oplog/resume tokens and retention windows.
- **Sharding**, data partitioning, and routing through **mongos** require the corresponding topology and privileges.
- Certain **aggregation operators**, **index types**, and specialized search features only exist on specific servers, editions, or topologies.

Do not treat a qualifying version number as proof of those topology or configuration requirements.

## 7. Java and Spring Framework are also in the matrix

An application does not only have to run with MongoDB Server; it must also satisfy the **Java/JDK** and **Spring Framework** requirements of Boot and Spring Data.

For instance, Spring Data MongoDB **4.5.x** belongs to the generation using **Spring Framework 6.2** and requires at least Java **17**; Spring Data MongoDB **5.x** belongs to the **Spring Framework 7** generation and also publishes a minimum requirement of Java **17**. However, for a specific Boot version, you must separately verify Java compatibility, toolchain settings, and the entire ecosystem. Upgrading from Boot 3 to Boot 4 can affect APIs, auto-configuration, third-party libraries, and non-MongoDB namespaces/dependencies.

### Why is the JDK an independent constraint?

- The bytecode of Spring Framework and the driver must be understood by the current JVM.
- Libraries using reflection, native access, virtual threads, or TLS may have different requirements.
- The Java driver has its own Java runtime support table; do not assume "a new driver always runs on every older JDK."
- Gradle/Maven plugins may require a JVM to launch the build that differs from the **Java toolchain** used to compile the application.

A complete upgrade plan must record the **actual Java runtime in production**, not just the **sourceCompatibility** setting in the project.

## 8. BOM and dependency management: let Boot choose the versions

### 8.1. Maven with Spring Boot parent

Example of a synchronous application using **spring-boot-starter-data-mongodb**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.3</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>mongo-version-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
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
</project>
~~~

Boot version **4.1.3** here is only an example whose BOM can be cross-referenced, not a requirement for every project to upgrade to this release. Key point: do not specify a separate version for **spring-data-mongodb** or **mongodb-driver-sync** when Boot's BOM already selects the dependency set.

If the project does not use **spring-boot-starter-parent** and instead imports **spring-boot-dependencies** in Maven dependency management, you still need to check BOM import order and rules to know which version is ultimately chosen.

### 8.2. Gradle with the Spring Boot plugin and dependency management

An example **build.gradle** using the Gradle Groovy DSL:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.3'
    id 'io.spring.dependency-management' version '1.1.7'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-mongodb'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

This example uses the **io.spring.dependency-management** plugin to import the dependency management provided by Boot. If a project uses Gradle native platform/BOM support or custom convention plugins, the syntax will differ; inspect the **resolved dependencies** after configuring the build.

**Avoid declaring at the same time** a custom driver version and a BOM version from a different Spring Data line. When multiple places dictate versions, the build may pick an unintended version or introduce conflicts.

### 8.3. When should you import spring-data-bom separately?

For a Spring project that does not use Spring Boot, you can import **org.springframework.data:spring-data-bom** to synchronize Spring Data modules. Maven example:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.data</groupId>
            <artifactId>spring-data-bom</artifactId>
            <version>2026.0.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

In that case, you still have to manage **Spring Framework**, the driver, and external libraries appropriately. **Spring Data BOM does not replace the entire Spring Boot BOM**. In a Boot project, only override the release train if you have a clear reason and have cross-checked the compatibility tables.

If using the Spring Boot Maven parent and wanting to override the train, the Spring Data docs mention the **spring-data-bom.version** property. Changing this property **does not guarantee** that all transitive dependencies, Boot APIs, and Spring Framework remain compatible; be especially careful when crossing a major version boundary.

## 9. Inspect the actually resolved versions, don't just read build.gradle

The build file only states **requests** and version management rules. The dependency graph reflects the actual artifacts resolved for a specific configuration.

### 9.1. Gradle

In a shell with the Gradle wrapper:

~~~bash
# View all libraries on the runtime classpath:
./gradlew dependencies --configuration runtimeClasspath

# Determine why Spring Data MongoDB has its current version:
./gradlew dependencyInsight --dependency spring-data-mongodb --configuration runtimeClasspath

# Check the sync or reactive driver:
./gradlew dependencyInsight --dependency mongodb-driver-sync --configuration runtimeClasspath
./gradlew dependencyInsight --dependency mongodb-driver-reactivestreams --configuration runtimeClasspath

# Find versions of core driver dependencies and BSON:
./gradlew dependencyInsight --dependency mongodb-driver-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency bson --configuration runtimeClasspath
~~~

On Windows use **gradlew.bat** or the wrapper command appropriate for your terminal. In multi-module projects, check the right module (for example **:app:dependencyInsight**) and the right configuration containing runtime artifacts rather than only checking the root project's dependencies.

**Lines to watch:**

- Do **requested** and **selected/resolved version** differ?
- Is there any conflict resolution, version constraint, or **force** in effect?
- Does another module pull in an extra MongoDB driver/codec transitively?
- Are the sync and reactive drivers selected from the same compatible version group?

### 9.2. Maven

~~~bash
# View the dependency tree related to Spring Data and MongoDB:
./mvnw dependency:tree

# View the effective POM, including actual dependencyManagement:
./mvnw help:effective-pom
~~~

On Windows use **mvnw.cmd**. You can filter the tree by group/artifact using Maven Dependency Plugin options, but before trusting a filtered view, make sure no transitive dependencies are hidden.

### 9.3. Verify the server

In **mongosh** connected to the deployment the application actually uses:

~~~javascript
db.version()
db.hello()
db.runCommand({ buildInfo: 1 }).version
~~~

**db.version()** shows the server version; **db.hello()** reveals topology information and communication details. Never infer the server version solely from the MongoDB CLI/mongosh version installed on a developer workstation.

If the application connects through **mongos** or a managed cloud service, confirm the server version provided by the service and the provider's upgrade policy. In a sharded cluster, do not assume inspecting a single endpoint is enough to evaluate whether all components are at the same upgrade stage.

### 9.4. Create a small inventory table before upgrading

Example:

| Item | Current (illustrative) | Target | Verification source |
| --- | --- | --- | --- |
| JDK runtime | 17 | 21 | Deployment image / runtime |
| Spring Boot | 3.5.x | 4.1.x | Maven/Gradle |
| Spring Data train | 2025.0.x | 2026.0.x | BOM |
| Spring Data MongoDB | 4.5.x | 5.1.x | dependencyInsight / dependency:tree |
| Mongo Java Driver | 5.5.x | Version managed by Boot 4.1.x | resolved runtimeClasspath |
| MongoDB Server | 7.0 | 7.0 or separate server plan | db.version / provider |
| Topology | Replica set | Replica set | rs.status / operations system |

This is a **recording template**, not a mandatory recommended configuration. Any plan to upgrade the JDK or server must be verified separately against your system's requirements and support schedule.

## 10. Changes that can affect code and BSON during an upgrade

The version matrix only indicates **platform compatibility**. When changing a **Spring Data MongoDB major version**, specific behaviors can also change.

### 10.1. Driver API and dependencies

Spring Data MongoDB **5.x** requires **MongoDB Java Driver 5.6+** and no longer supports the **4.x** driver generation. If an older library pins **mongodb-driver-core 4.x** or removed driver APIs, upgrading Spring Data can cause **NoSuchMethodError**, **ClassNotFoundException**, or runtime failures.

Check:

- All **org.mongodb** artifacts in the dependency graph.
- Code directly using the Java Driver outside **MongoTemplate** or repositories.
- Plugins or libraries using the driver: migration tools, schema validators, telemetry, test fixtures, GridFS helpers.
- The reactive driver if the application uses **ReactiveMongoTemplate**.

Do not try to work around binary incompatibility by forcing a 4.x driver underneath Spring Data 5.x.

### 10.2. UUID representation

When storing UUIDs in MongoDB, there are Binary representations with different subtypes/byte orders. Spring Data MongoDB 5.x no longer provides a default setup for **UuidRepresentation** through configuration classes as before; the migration guide requires specifying it explicitly when storing UUIDs.

Example with the Java Driver:

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import org.bson.UuidRepresentation;

MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(
        new ConnectionString("mongodb://localhost:27017/demo")
    )
    .uuidRepresentation(UuidRepresentation.STANDARD)
    .build();
~~~

This is a standalone driver settings example. In Spring Boot, ensure that the **MongoClient used by MongoTemplate/repositories** actually receives that configuration rather than configuring a different client.

Do not blindly switch all UUIDs to STANDARD if existing data was written using a legacy representation. Inspect the raw Binary data, identify the legacy mapping, prepare a migration, and test cross-version reads/writes.

### 10.3. BigDecimal, BigInteger, and Decimal128

When upgrading to Spring Data MongoDB 5.x, the **default representation of BigDecimal/BigInteger via custom configuration** is highlighted in the migration guide. When you want to store decimals as BSON **Decimal128**, you can declare it explicitly on the property:

~~~java
import java.math.BigDecimal;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

class InvoiceAmount {
    @Field(targetType = FieldType.DECIMAL128)
    BigDecimal total;
}
~~~

**@Field(targetType = FieldType.DECIMAL128)** explicitly states the representation for the property. If existing data was stored as **String**, changing the annotation or converter default can cause new documents to have a different BSON type; you must check aggregations, sorting, range queries, and other services reading the same collection.

Do not apply a global converter across an entire collection when only one property needs to change without checking compatibility first.

### 10.4. Mapping and custom converters

Inspect entities that use:

- **@PersistenceCreator**, immutable constructors, Java **record**s.
- **_class**, **@TypeAlias**, and polymorphic fields.
- **@Field** renaming, ID mapping, enums, date/time types.
- **MongoCustomConversions**, reading/writing converters, and custom codecs.
- Data written by older application versions.

A test that only calls **repository.save(entity)** followed by **findById()** with the new code alone may miss cases where the new application misreads old BSON. Add **raw BSON fixtures** built from anonymized real data shapes.

### 10.5. Queries, aggregations, transactions, and change streams

Review the migration guide and release notes for the **actual upgrade step**, for example **4.x -> 5.x**. Potentially affected areas include:

| Group | What to check |
| --- | --- |
| **Derived queries** | Property names, conversion, regex, pagination, and sorting |
| **MongoTemplate Query/Criteria** | BSON filter syntax and field mapping mechanism |
| **Aggregation** | Operators on the target server, aliases, output BSON types |
| **Indexes** | Unique, partial, TTL, compound, and auto-created indexes |
| **Transactions** | MongoTransactionManager, sessions, retries, rollback, and replica set |
| **Change streams** | Consumer lifecycle, resume tokens, filters, and restart handling |
| **Reactive access** | ReactiveMongoTemplate, Reactor/reactive driver, cancellation, and timeouts |
| **GridFS** | Upload/download, metadata, codecs, and stream access |

For example: the Spring Data MongoDB 5.x migration guide also notes a change in **DefaultMessageListenerContainer**: lifecycle auto-start is enabled by default. Applications that relied on manually starting listeners must review startup order and server permissions before deploying.

## 11. Practical case: evaluating a Boot 3.5 to 4.1 upgrade

Suppose an application currently runs:

- **Spring Boot 3.5.x**, Spring Data train **2025.0.x**, Spring Data MongoDB **4.5.x**.
- **MongoDB Server 7.0** running as a replica set.
- **MongoTemplate**, repositories, aggregations, transactions, and change streams.
- Data containing UUID and BigDecimal fields written across multiple application versions.

The target is **Spring Boot 4.1.x** and train **2026.0.x**, with Spring Data MongoDB **5.1.x**. Do not treat this as merely changing one line in the plugin block.

### Step 1 — Establish the baseline and comparison record

Record the JDK, Boot, release train, **actual** MongoDB Driver, MongoDB Server, topology, and transitive dependencies. Run unit and integration tests on the current state so you can distinguish new upgrade-induced failures.

### Step 2 — Check compatibility

For **MongoDB Server 7.0**, the Spring Data table shows that both **4.5.x** and **5.1.x** are within the tested server range. Next, look up the driver version managed by **Boot 4.1.x** and the corresponding cell for MongoDB Server **7.0** in the MongoDB Java Driver table.

This is only the baseline prerequisite. If you use specialized server features, check the driver release notes and test those features directly.

### Step 3 — Read major version changes

Cross-check:

- **Boot 3 -> 4**: changes in Spring Framework, auto-configuration, starters, third-party libraries, and the application.
- **Spring Data MongoDB 4 -> 5**: driver **5.6+** requirement, UUID configuration, BigDecimal, listener lifecycle, and API changes.
- **MongoDB Java Driver 5.5 -> version managed by Boot 4.1**: API classes, connection options, TLS, codecs, and reactive support if used.

You can perform intermediate upgrade steps in an experimental branch—for instance, validating on **Boot 4.0** before moving to **4.1**—to isolate generation-specific issues. The final path depends on your system's support schedule and code change scope.

### Step 4 — Run data and functional tests

- Read **raw BSON fixtures** of legacy UUID/BigDecimal data; verify mapping preserves values without loss.
- Save/find/update via **MongoTemplate** and **MongoRepository**.
- Execute real aggregations and compare results against the baseline.
- Test transaction **commit** and **rollback** on a replica set.
- Open a change stream, write events, verify consumer reception and resume handling.
- For reactive code, use **StepVerifier** and a real MongoDB instance on critical access paths.

### Step 5 — Pre-release checks

Once tests pass, inspect driver error logs, deprecated API warnings, connection pooling, timeouts, retries, p95/p99 latency, aggregation durations, and key queries. Keep a way to roll back to the pre-upgrade application artifact; if you already migrated data or changed BSON representations, **code rollback** alone may not be enough to recover the system.

## 12. How should an upgrade test matrix be structured?

A small test matrix helps separate application bugs from server issues:

| Application | MongoDB Server | Goal | Results to record |
| --- | --- | --- | --- |
| **Old version** | **Current server** | Pre-upgrade baseline | Functionality, performance metrics, BSON shapes |
| **New version** | **Current server** | Upgrade Boot/Spring Data/driver while keeping server | Backward compatibility with legacy data |
| **New version** | **Target server** | Validate target combination | Queries, indexes, aggregations, transactions, change streams |
| **Old version** | **Target server** | Assess rolling upgrade if two app versions coexist | Whether cross-version reads/writes work; only test if supported by the tables |

For multi-instance deployments, test **mixed-version scenarios** during the transition window. If the new application writes a BSON format the old application cannot read, a rolling deploy can fail even when each version passes tests in isolation.

### Is Testcontainers enough?

**Testcontainers** is very useful for selecting MongoDB Server images for integration tests:

~~~java
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.utility.DockerImageName;

// Example with the Testcontainers MongoDB module API in the 1.x line.
MongoDBContainer mongo =
    new MongoDBContainer(DockerImageName.parse("mongo:7.0"));
~~~

Pin the major/minor image matching your real environment, and use a replica set when testing transactions or change streams. When testing security, sharding, managed clusters, or edition-specific features, a simple container environment may not fully simulate production.

Running tests across multiple server versions only catches bugs if critical code paths are actually exercised. Never treat a container starting successfully as proof of business compatibility.

## 13. Common mistakes when reading the matrices

| Mistake | Consequence | Correct check |
| --- | --- | --- |
| Treating **2026.0** as the MongoDB artifact version | Declaring a nonexistent or wrong dependency | Use the train for the BOM; use **5.1.x** for the module per the matrix |
| Treating "minimum driver 5.6" as a version that must be pinned | Downgrading the driver away from Boot's managed version | Check the **managed version** and compare against the minimum |
| Treating "tested servers 6.x–8.x" as prohibiting all newer servers | Overlooking potentially compatible options | Check the driver–server matrix and release notes |
| Treating a successful connection as full feature compatibility | Failures appear later in transactions/aggregations/change streams | Run integration tests per use case |
| Upgrading **mongodb-driver-core** alone while leaving **bson** old | Classpath/binary linkage errors | Use the BOM and dependencyInsight across all org.mongodb artifacts |
| Upgrading **spring-data-mongodb** across a major boundary on an old Spring Framework | Class/method errors or broken auto-configuration | Upgrade along the compatible release train and Boot version |
| Reading only **build.gradle** | Missing versions overridden or selected by dependency conflict resolution | Inspect the actual **runtimeClasspath** |
| Testing only new data and skipping legacy data | Legacy UUID/Decimal128/aliases may fail to read | Test raw BSON fixtures from older schemas |
| Comparing mongosh version with MongoDB Server | Misjudging server runtime version | Connect to the real deployment and run **db.version()** |
| Running transactions on standalone and blaming the driver | Confusing topology limits with version bugs | Use an appropriate replica set or sharded cluster |
| Treating **M/RC/SNAPSHOT** previews as stable without assessing risk | API changes, lack of support, or extra repositories needed | Verify release status and usage policy |
| Equating "compatible" with "still receiving support/security fixes" | Running end-of-life versions | Check Spring support policy and MongoDB Server lifecycle |

## 14. Reusable upgrade workflow

1. **Inventory**: record the exact JDK runtime, Boot, Spring Data train, Spring Data MongoDB, sync/reactive drivers, BSON, and current MongoDB Server/topology.
2. **Target**: select a supported Boot line and train; decouple application upgrades from server upgrades when isolating changes.
3. **Cross-check tables**: Boot BOM → Spring Data compatibility → MongoDB driver/server matrix → Java requirements.
4. **Read migration guides**: removed APIs, UUIDs, BigDecimal, mappings, converters, transactions, and change streams.
5. **Avoid manual dependency mixing**: prefer the BOM; inspect runtimeClasspath/effective POM to catch overrides.
6. **Test legacy data**: read legacy BSON and verify new writes do not break older clients.
7. **Test against a real server**: CRUD, aggregations, indexes, transactions, reactive, change streams, TLS, and retries per application.
8. **Measure performance**: compare baseline and target combination, watching pool usage, timeouts, latency, and documents scanned.
9. **Staged rollout and rollback**: keep checkpoints, monitoring, and a data recovery plan if schema/BSON changed.
10. **Record evidence**: save resolved versions, test results, links to tables used, and verification date.

### Self-check questions

**1. Does Spring Data release train 2026.0 mean Spring Data MongoDB 2026.0?** No. Per the matrix above, train **2026.0** contains Spring Data MongoDB **5.1.x**.

**2. If Spring Data MongoDB requires a minimum driver of 5.6.x, should you always pin 5.6.0?** No. Prefer the driver managed by the Spring Boot BOM, then verify the resolved version meets the requirement and is tested in the actual combination.

**3. If MongoDB Server 8.0 is in Spring Data's tested range, will every older driver generation work?** No. You still must check the Java Driver ↔ MongoDB Server matrix; older drivers may lack full support or be incompatible.

**4. Can you use standalone MongoDB to verify transactions after an upgrade?** No. Testing transactions requires a MongoDB topology that supports transactions, typically a replica set.

**5. Does a passing save/find test prove legacy UUIDs and BigDecimals are safe?** No. You must test reading BSON written by older versions and inspect the representation produced by new writes.

**6. Why can upgrading Boot without touching MongoDB dependencies still change the driver?** Because Spring Boot manages many dependencies via its BOM; changing Boot can update all managed dependency versions accordingly.

**7. How do a compatibility matrix and a support policy differ?** A matrix tells you which combinations work or were tested technically; a support policy tells you which versions are still maintained, patched, and supported on a release schedule.

**8. Do you need to check Java if your only goal is upgrading Spring Data MongoDB?** Yes. Spring Data/driver generations and Spring Framework have their own Java runtime requirements, and the Boot BOM can upgrade related components together.

## Conclusion

Reading the **Boot–Spring Data–driver–server** matrix is a process of tracing the dependency chain: **Spring Boot selects the BOM; the release train synchronizes Spring Data; Spring Data MongoDB requires the driver; the driver communicates with MongoDB Server at a specific compatibility level**. You must also check the **JDK**, topology, and changes to BSON, APIs, transactions, and change streams. A reliable upgrade decision rests on **resolved versions**, documentation matching the release line, and integration tests with appropriate data and servers—not on a single version number.

## Official references

- [Spring Data MongoDB — Requirements and Compatibility Matrix](https://docs.spring.io/spring-data/mongodb/reference/preface.html)
- [Spring Data — Dependencies, Release Train BOM and Dependency Management](https://docs.spring.io/spring-data/mongodb/reference/data-commons/dependencies.html)
- [Spring Boot — Managed Dependency Coordinates (4.1)](https://docs.spring.io/spring-boot/4.1/appendix/dependency-versions/coordinates.html)
- [Spring Boot — Managed Dependency Coordinates (4.0)](https://docs.spring.io/spring-boot/4.0/appendix/dependency-versions/coordinates.html)
- [Spring Boot — Managed Dependency Coordinates (3.5)](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html)
- [Spring — Project Generations](https://spring.io/projects/generations/)
- [MongoDB — Client Library Compatibility Tables](https://www.mongodb.com/docs/drivers/compatibility/?driver-language=java&java-driver-framework=java-sync)
- [Spring Data MongoDB — Migration Guide 4.x to 5.x](https://docs.spring.io/spring-data/mongodb/reference/migration-guide/migration-guide-4.x-to-5.x.html)
- [MongoDB — Release Notes](https://www.mongodb.com/docs/manual/release-notes/)

*The illustrative numbers and matrix rows in this article were verified on **November 20, 2026**. When using this guide to upgrade a project, always re-check the documentation for the exact versions before locking in your BOM, driver, and MongoDB Server.*
