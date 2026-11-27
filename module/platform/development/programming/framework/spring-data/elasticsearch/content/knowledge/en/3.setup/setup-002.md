# Choosing Compatible Spring Boot, Spring Data, Client, and Elasticsearch Versions

When initializing a Spring Data Elasticsearch project, you need to select a set of versions that can work together. This set includes the Java runtime, Spring Boot and Spring Framework, Spring Data Elasticsearch, the client library used to send requests, and the Elasticsearch server receiving and processing those requests. Simply picking the latest version of each component and combining them can lead to dependency errors, API errors, or communication failures at runtime.

The practical rule is to choose Spring Boot first, let Spring Boot's dependency management handle the versions of Spring Data and related libraries, and then choose an Elasticsearch server according to the compatibility matrix of that specific Spring Data Elasticsearch release line. The client should use the version managed by that dependency set. Verify the entire combination via the dependency tree and an integration test against a real Elasticsearch server.

## 1. Components That Must Be Compatible

A Spring Data Elasticsearch application typically includes the following component layers:

| Component | Role | What to Check |
|---|---|---|
| Java runtime | Runs the application and libraries | Minimum Java version required by Spring Boot and libraries |
| Spring Boot | Provides auto-configuration, starters, and dependency management | Version suitable for the application platform and JDK |
| Spring Framework | Container foundation, DI, transactions, and Spring APIs | Version managed by Spring Boot |
| Spring Data Elasticsearch | Repositories, mapping, `ElasticsearchOperations`, and Spring Data integration | Release train matching Spring Boot and Elasticsearch |
| Elasticsearch Java client | Translates Java calls into requests sent to the server | Artifact and version compatible with Spring Data Elasticsearch |
| Elasticsearch server | Stores indices, indexes data, and executes queries | Server version within the range supported by Spring Data Elasticsearch |

These components are interrelated, but they are not the same product and do not share a single version number. For example, Spring Boot has its own version, Spring Data has its own release train, the `elasticsearch-java` library has its own version, and the Elasticsearch server also has its own version.

### How Does Spring Boot Manage Dependencies?

Spring Boot provides dependency management through the `spring-boot-dependencies` BOM. This BOM defines versions selected and tested together by the Spring team. When using a Spring Boot starter, Gradle or Maven pulls the corresponding versions from the BOM instead of each project manually choosing versions for every library.

For Spring Data Elasticsearch, the standard starter is:

```text
org.springframework.boot:spring-boot-starter-data-elasticsearch
```

The starter brings in Spring Data Elasticsearch and the dependencies required for Spring Boot's configuration. In a standard Spring Boot project, let Boot manage these versions. Manually declaring a different version for `spring-data-elasticsearch` or `elasticsearch-java` can create an untested combination.

### What Are the Roles of Spring Data Elasticsearch and the Client?

Spring Data Elasticsearch provides integration with the Spring ecosystem: `ElasticsearchRepository`, `ElasticsearchOperations`, entity/document mapping, and client configuration. The client is a lower-level communication library responsible for sending requests to the Elasticsearch server.

An application can operate via repositories or `ElasticsearchOperations`, but underneath it still requires a compatible client. The fact that a repository class compiles does not prove that the client and server can communicate properly in a real runtime environment.

## 2. Understanding Client API Generations

Different versions of Spring Data Elasticsearch can use different client APIs. This is important to keep in mind when upgrading from an older project.

### The `RestHighLevelClient` Generation

Older Spring Data Elasticsearch lines, notably the 4.x line, integrated with Elasticsearch 7.x and commonly used the Elasticsearch REST High Level Client (`RestHighLevelClient`).

Common legacy artifact:

```text
org.elasticsearch.client:elasticsearch-rest-high-level-client
```

This API belongs to the older client generation. When moving to newer Spring Data Elasticsearch lines, do not retain the old configuration and add the new client to the classpath hoping both will work together automatically.

### The Elasticsearch Java API Client Generation

Spring Data Elasticsearch 5.x switched to the Elasticsearch Java API Client, with the artifact:

```text
co.elastic.clients:elasticsearch-java
```

The new client API has the primary class `co.elastic.clients.elasticsearch.ElasticsearchClient`. It uses a lower-level REST client transport and provides a Java API generated from the Elasticsearch API.

In new Spring Boot projects, you usually do not need to create the transport and client manually if auto-configuration meets your needs. If custom configuration is needed, follow the guide for the exact Spring Data Elasticsearch version in use.

### Do Not Arbitrarily Mix Two Client Generations

`RestHighLevelClient` and `ElasticsearchClient` belong to two different API generations. Adding both dependencies to one application does not make them compatible. It can pull in multiple versions of HTTP, JSON, or core Elasticsearch libraries, causing dependency conflicts and making configuration hard to control.

When upgrading, migrate configuration code and client calls to the API supported by the new Spring Data version. Do not retain beans or imports from the old client if the new Spring Data line no longer uses them.

## 3. Version Matrix by Generation

The table below helps identify common technology generations. This is high-level guidance at the major version level, not a guarantee that every patch version in a row is mutually compatible.

| Application Generation | Typical Spring Data Elasticsearch Line | Typical Elasticsearch Server Line | Typical Client |
|---|---|---|---|
| Spring Boot 2.x | Spring Data Elasticsearch 4.x | Elasticsearch 7.x | `RestHighLevelClient` |
| Spring Boot 3.x | Spring Data Elasticsearch 5.x | Elasticsearch 8.x | Elasticsearch Java API Client (`elasticsearch-java`) |
| Spring Boot 4.x | Spring Data Elasticsearch 6.x | Elasticsearch 9.x | Elasticsearch Java API Client (`elasticsearch-java`) |

Use this table to identify the generation, then look up the official compatibility matrix for the exact Spring Data Elasticsearch version. Do not assume that every Spring Boot 3.x supports every Elasticsearch 8.x, or that every Spring Data 5.x supports every 8.x server release.

### Why Must You Check Down to Minor and Patch Versions?

A major line can have many minor releases. Each minor release may update the client version, fix integration bugs, or add support for a specific Elasticsearch server version. For example, Spring Data Elasticsearch 5.2.x and 5.5.x both belong to major version 5, yet they do not necessarily use the same client version or have the same supported server matrix.

Therefore, verify all of the following together:

1. The Spring Boot version in use.
2. The exact Spring Data Elasticsearch version selected by Boot's BOM.
3. The client version selected by Spring Data/BOM.
4. An Elasticsearch server version within the support matrix of that exact Spring Data Elasticsearch version.

If the project uses Spring Data standalone without the Spring Boot BOM, check the corresponding Spring Data release train BOM and compatibility guide. Do not treat the major table above as a substitute for the minor/patch matrix.

## 4. Process for Choosing Versions for a New Project

### Step 1: Identify the Java and Spring Boot Baseline

First, determine which JDK the development environment, CI, and deployment environment can use. Then choose a Spring Boot version that supports that JDK and fits the project's maintenance lifecycle.

Spring Boot 3.x requires Java 17 or higher. Other Spring Boot lines may have different Java baselines, so check the Java requirement in the documentation for that exact Boot version instead of guessing from whatever is installed locally.

For example, if a project is constrained to an older JDK, picking a newer Spring Boot just for new features can prevent the application from starting. The JDK must be consistent across the IDE, Gradle/Maven, CI, and deployment runtime.

### Step 2: Choose Spring Boot and Use the Starter

For a Spring Boot application, add the official starter and let Boot manage the Spring Data Elasticsearch version.

Gradle Groovy DSL example:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<spring-boot-version>'
    id 'io.spring.dependency-management' version '<dependency-management-plugin-version>'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-elasticsearch'
}
```

Maven example:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>${spring-boot.version}</version>
    <relativePath/>
</parent>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-elasticsearch</artifactId>
    </dependency>
</dependencies>
```

Placeholder strings in the examples must be replaced with the project's selected versions. Do not copy placeholders verbatim into build files.

There is normally no need to declare separate versions for `spring-data-elasticsearch` or `elasticsearch-java`. If overriding is strictly required, inspect the dependency tree and compatibility matrix before proceeding.

### Step 3: Determine the Actual Resolved Spring Data Elasticsearch Version

Do not rely on assumptions that a given Boot version always pulls a specific Spring Data version. Inspect the dependencies resolved by the build tool.

With Gradle:

```bash
./gradlew dependencyInsight \
  --dependency spring-data-elasticsearch \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency elasticsearch-java \
  --configuration runtimeClasspath
```

You can view the full runtime dependency tree with:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

With Maven:

```bash
mvn dependency:tree \
  -Dincludes=org.springframework.data:spring-data-elasticsearch

mvn dependency:tree \
  -Dincludes=co.elastic.clients:elasticsearch-java
```

If the dependency tree contains multiple versions of the same library or shows both old and new generation clients simultaneously, locate the direct or transitive dependency introducing them.

### Step 4: Select the Elasticsearch Server from the Spring Data Matrix

Once you know the exact Spring Data Elasticsearch version, open its compatibility documentation and select an Elasticsearch server within the supported range. Check both minor and patch versions if the documentation specifies corresponding server versions.

Do not choose the server solely by major number. An application may compile with the client yet encounter runtime errors if the server lacks an API, has mapping changes, or behaves differently from the version supported by Spring Data.

### Step 5: Align Versions Across Environments

Once versions are chosen, align the Elasticsearch image across developer machines, CI, integration tests, and deployment environments. Do not use the `latest` tag for a system requiring reproducible results, as that tag can point to a different version on a subsequent pull.

At minimum, record the following in project documentation or build configuration:

- JDK used to build and run the application.
- Spring Boot version.
- Resolved Spring Data Elasticsearch version.
- Resolved Elasticsearch client version.
- Elasticsearch server/image version.

## 5. Basic Connection Configuration in Spring Boot

Once the starter and compatible versions are selected, Spring Boot can automatically configure the client based on properties.

Example `application.yml` for a local development Elasticsearch server:

```yaml
spring:
  elasticsearch:
    uris: http://localhost:9200
```

If the server requires authentication, configure credentials via environment variables or a secret manager. Do not commit real passwords, API keys, or credentials to the repository.

Property names and security options may vary across Spring Boot lines. Refer to the Elasticsearch properties section in the documentation for your specific Boot version. For HTTPS clusters, configure TLS and certificates properly; do not disable certificate verification to bypass connection errors in real environments.

### Verifying the Running Elasticsearch Server

You can call the root endpoint to confirm the server responds and check its version info:

```bash
curl http://localhost:9200
```

If the cluster has security enabled, the request requires appropriate credentials and the HTTPS protocol. The response typically includes the cluster name, node name, version number, and build info. Cross-check the version number against the version selected in the matrix.

### Manually Configuring the Client Only When Truly Needed

Spring Boot auto-configuration is usually sufficient for basic connections. Only create manual client configuration when you need to customize transport, TLS, authentication, timeouts, or connection pool behavior beyond what default properties support.

When configuring manually:

- Use the exact client type required by your Spring Data version.
- Create and manage the transport/client lifecycle according to that version's guide.
- Avoid declaring duplicate beans alongside auto-configured beans unless intentionally replacing them.
- Ensure HTTP resources are closed properly on application shutdown.
- Check how credentials and trust material are passed, and do not log secrets.

Do not copy a `RestHighLevelClient` configuration from a Spring Data 4.x guide into a Spring Data 5.x or newer project without converting to the corresponding API.

## 6. Do Client and Server Need the Exact Same Version?

Client and server are two independent artifacts, so their version numbers do not have to match identically. However, that does not mean every combination is supported.

With the Elasticsearch Java API Client, the client's compatibility policy indicates the server range with which the client can communicate. A client may support some newer server minor versions, but you should not assume a newer client can call every API on an older server. An API added to the client might not yet exist on an older server.

Beyond client-server compatibility, Spring Data Elasticsearch must also be considered. Spring Data may restrict supported Elasticsearch server versions even if the standalone client can communicate with a wider range of servers.

Therefore, both conditions must be satisfied simultaneously:

1. The client version matches the server according to the Elasticsearch Java client's compatibility policy.
2. The server version lies within the compatibility matrix of the Spring Data Elasticsearch version in use.

In a Spring Boot project, the safe approach is to keep the client at the version managed by the BOM/starter and pick the server according to Spring Data documentation. Only override the client when there is a specific requirement, compatibility has been verified, and integration tests prove the required behavior.

## 7. Upgrading Across Generations

A major upgrade can affect multiple layers simultaneously. For example, migrating from Spring Boot 2.x / Spring Data Elasticsearch 4.x to Spring Boot 3.x / Spring Data Elasticsearch 5.x commonly involves the Java baseline, Spring Framework, the Jakarta namespace, and the Elasticsearch client API.

Items to review:

| Item | What to Check When Upgrading |
|---|---|
| Java | Minimum JDK, Gradle/Maven toolchain, and deployment runtime |
| Spring Framework | APIs changed or removed between major versions |
| Jakarta | Related `javax.*` packages may need migration to `jakarta.*` when upgrading to Spring Boot 3 |
| Spring Data Elasticsearch | Repositories, mapping annotations, templates, and client configuration |
| Elasticsearch client | Migrating from `RestHighLevelClient` to Elasticsearch Java API Client when required by the Spring Data line |
| Elasticsearch server | APIs, mappings, security defaults, and features changed across major versions |
| Existing indices | Mappings, analyzers, templates, and potential need for reindexing |

Do not upgrade every component simultaneously without intermediate verification steps. Read the upgrade guides of Spring Boot, Spring Data Elasticsearch, and Elasticsearch for your exact source/target versions.

A practical upgrade sequence:

1. Record the current JDK, Boot, Spring Data, client, and server versions.
2. Determine the target versions and check mandatory upgrade steps.
3. Upgrade the JDK and Spring Boot as required by the target version.
4. Let the Boot BOM resolve the corresponding Spring Data and client versions.
5. Migrate legacy configuration/client code to the new API if needed.
6. Verify mappings, repository queries, custom queries, and serialization.
7. Run integration tests against an Elasticsearch server at the exact target version.
8. Plan reindexing or index migration if mappings/APIs changed.
9. Deploy environment by environment and monitor for connection, indexing, and query errors.

## 8. Verifying Compatibility During Development

Successful compilation only confirms that code and dependencies can work together at compile time. It does not confirm that the running server is the right version or that actual API requests are supported.

Include at least the following verification layers:

### Dependency Verification

- Inspect the actual Spring Data Elasticsearch and client versions on the runtime classpath.
- Look for dependencies overridden outside the BOM.
- Prevent two client generations from appearing unintentionally.
- Check dependency convergence if the project has multiple modules.

### Connection Verification

- Confirm the URI, DNS, port, and HTTP/HTTPS protocol.
- Verify authentication and index permissions.
- Verify the TLS trust chain when using HTTPS.
- Read the server version from the endpoint or cluster info.

### Integration Verification

Run the application and perform real operations against the corresponding server:

- Create or verify the index and mapping.
- Save a document.
- Read a document by ID.
- Execute a repository or `ElasticsearchOperations` query.
- Update and delete a document.
- Verify handling of authentication failures, timeouts, and unavailable servers.

In CI pipelines, use an Elasticsearch container with a pinned version tag matching the server version planned for deployment. Integration tests should verify both index/mapping initialization and query operations, because mapping errors may only surface when requests are actually sent.

## 9. Common Errors from Mismatched Versions

### `NoSuchMethodError` or `ClassNotFoundException`

These errors usually occur when code is compiled against one API version but loads a different library version at runtime, or when dependencies conflict. Inspect the runtime dependency tree, BOM, and manually declared versions.

### Legacy Client Classes Not Found

An older tutorial may import `RestHighLevelClient`, whereas the current project uses a Spring Data line that has moved to the Elasticsearch Java API Client. Match examples to the exact Spring Data version and update the configuration to the new API.

### Client Connects but Server Rejects Requests

A successful TCP/HTTP connection does not guarantee the server supports the API sent by the client. Check the server version, endpoint, request format, and compatibility matrices of both the client and Spring Data.

### Mapping or Index Errors on Startup

The mapping may be incompatible with an old index or server version. Inspect existing mappings, index templates, and index creation settings. If changes cannot be applied in place, create a new index and reindex according to plan.

### Works Locally but Fails in CI or Production

The cause is often differing JDKs, Elasticsearch images, security configurations, or environment variables across environments. Pin versions and include integration tests in CI to catch discrepancies early.

### Using the `latest` Tag

The `latest` tag causes the same configuration to pull different server versions over time. When the server updates unexpectedly, the application can encounter API or behavioral changes. Use specific version tags and update intentionally.

## 10. Example Version-Controlled Dependency and Server Setup

The following example illustrates placing versions in one place and avoiding overriding the client version in a Spring Boot project. Placeholders must be replaced with a version set verified via the BOM and compatibility matrix.

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<spring-boot-version>'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-elasticsearch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    // Add the Testcontainers Elasticsearch library compatible with
    // the Testcontainers version managed by your project.
}
```

Example local environment configuration:

```yaml
spring:
  elasticsearch:
    uris: ${ELASTICSEARCH_URIS:http://localhost:9200}
```

Example running a local server with Docker:

```bash
docker run --name elasticsearch-dev \
  -p 9200:9200 \
  -e discovery.type=single-node \
  -e xpack.security.enabled=false \
  docker.elastic.co/elasticsearch/elasticsearch:<elasticsearch-version>
```

The command above is only an example for an isolated development environment. Replace the placeholder with a verified compatible version. Disabling security is not suitable for shared or production environments; those environments require proper authentication, TLS, and secret management.

## 11. Checklist Before Locking in a Version Set

Before writing code or upgrading, confirm the following:

- [ ] The JDK meets the requirements of the chosen Spring Boot version.
- [ ] The Spring Boot version is pinned in the build file.
- [ ] The project uses `spring-boot-starter-data-elasticsearch` if following Spring Boot.
- [ ] Spring Data Elasticsearch is resolved from the BOM and its exact version is identified.
- [ ] The Elasticsearch client is managed consistently with the Spring Data dependency set.
- [ ] The client API in use matches the right generation; no incompatible legacy configuration remains.
- [ ] The Elasticsearch server falls within the support matrix of that exact Spring Data Elasticsearch version.
- [ ] The Elasticsearch image tag is pinned, without using `latest`.
- [ ] Local, CI, and deployment environments use the aligned version set.
- [ ] Integration tests verify connection, mapping, write, read, update, delete, and queries.
- [ ] A plan exists to handle mapping changes or reindexing if upgrading the server or Spring Data alters indices.

## 12. Conclusion

Choosing compatible versions is about selecting a controlled combination of Java, Spring Boot, Spring Data Elasticsearch, the Elasticsearch client, and the Elasticsearch server. For Spring Boot projects, let the Boot BOM manage Spring Data and the client, then choose the server according to the compatibility matrix of that exact Spring Data version. The major version table only helps identify generations; final decisions should rely on minor/patch versions in official documentation.

Once the combination is locked in, pin versions in build files and container images, inspect the dependency tree, configure security appropriately for each environment, and run integration tests against a real server. This approach helps catch client API mismatches, mapping issues, or version discrepancies early before deploying the application to production.
