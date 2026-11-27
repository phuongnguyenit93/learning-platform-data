# Reading the Spring Boot, Spring Data, Client, and Server Compatibility Matrix

A Spring Data Elasticsearch application may compile successfully yet still fail to run against the Elasticsearch server in use. Conversely, the application may connect, yet an API, query type, authentication mechanism, or mapping feature may be incompatible. The reason is that an application's version does not consist of a single dependency: Spring Boot manages Spring Framework and Spring Data; Spring Data Elasticsearch selects the client/transport; the client communicates with the Elasticsearch server; and the Java runtime, plugins, and test environment also have their own version constraints.

Reading a compatibility matrix is how you identify a **supported version combination**, rather than picking each component independently. At least four layers need to be checked:

1. **Spring Boot ↔ Spring Data release train**: Spring Data modules must belong to the release train aligned with Boot.
2. **Spring Data Elasticsearch ↔ Elasticsearch Java client/transport**: the Spring Data module needs the exact client generation and dependencies it was built to use.
3. **Elasticsearch client ↔ Elasticsearch server**: REST API, protocol compatibility, and feature support must align.
4. **Java runtime and the test/plugin ecosystem**: JDK, Testcontainers, Elasticsearch plugins, and build tooling must also be compatible.

No single version number proves the entire stack is compatible. You must read the documentation for each layer, inspect the actual resolved dependencies, and run integration tests against the target server version.

## 1. Four version layers to read together

A stack can be visualized as follows:

~~~mermaid
flowchart TD
    A["Application code"] --> B["Spring Boot"]
    B --> C["Spring Data release train"]
    C --> D["Spring Data Elasticsearch"]
    D --> E["Elasticsearch Java API Client / transport"]
    E --> F["Elasticsearch HTTP server"]
    B --> G["Java runtime"]
    F --> H["Elasticsearch plugins"]
    D --> I["Testcontainers / integration test"]
    I --> F
~~~

Each relationship involves a different kind of compatibility:

| Component Pair | What to Check | Signs of Incompatibility |
|---|---|---|
| Spring Boot and Spring Data | Which release train the Boot BOM manages | Dependency convergence errors, `NoSuchMethodError` in Spring |
| Spring Data and Spring Data Elasticsearch | Which release train the module belongs to | Mismatched Spring Data module versions, out-of-sync APIs |
| Spring Data Elasticsearch and Java client | Client generation, version, and transport | Missing classes, different method signatures, mismatched client configuration |
| Java client and Elasticsearch server | Major version, REST compatibility, API/feature support | HTTP 400/406, missing API, unsupported request fields |
| Elasticsearch server and plugin | Plugin version compatible with server | Plugin fails to load or node fails to start |
| Spring Boot and JDK | Java baseline of Boot/framework/dependencies | `UnsupportedClassVersionError`, compiler/runtime mismatch |
| Testcontainers and server image | Image version, startup/security behavior | Tests differ from production, container fails to start, or tests use wrong protocol |

You should not simply compare the major numbers of Spring Boot and Elasticsearch and draw a conclusion. The two projects have independent release schedules; Spring Boot 3.x does not mean you must use Elasticsearch 3.x.

## 2. Starting from the Spring Boot BOM

In a Spring Boot application, the parent POM or dependency management BOM is usually the starting point for determining the managed versions of Spring Framework and Spring Data.

Maven example:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.x.y</version>
    <relativePath/>
</parent>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-elasticsearch</artifactId>
    </dependency>
</dependencies>
~~~

`3.x.y` is only a placeholder to illustrate the structure. A real project must use a Spring Boot version chosen from the official matrix and compatible with the project's JDK/build tool.

If not using `spring-boot-starter-parent`, you can import the BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.x.y</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

When a dependency is managed by the Boot BOM, you typically do not need to declare a separate version for the starter.

What to read:

- The Boot version in use.
- The Spring Framework version managed by Boot.
- The Spring Data release train selected by Boot.
- The version of `spring-data-elasticsearch`.
- The versions of transitive client/transport dependencies.
- The minimum Java version and build plugin versions.

The BOM is a set of version management rules. It does not prove that any arbitrary Elasticsearch server version is supported; that is a separate verification step.

## 3. What is a Spring Data release train?

Spring Data releases related modules together in a release train. Modules such as Commons, Elasticsearch, JPA, MongoDB, and Redis may need to align on the same release train to avoid internal API mismatches.

For example, a project might use:

- `spring-data-commons`
- `spring-data-elasticsearch`
- Other Spring Data modules if the application needs them.

You should not upgrade `spring-data-elasticsearch` alone to an arbitrary version while `spring-data-commons` remains managed by Boot on a different release train.

Some signs of misaligned Spring Data dependencies:

- `NoSuchMethodError` in the `org.springframework.data` package.
- A class compiled against one version but loaded at runtime from another version.
- Repository configuration behaving differently between the IDE and CI.
- The dependency tree containing two versions of Spring Data Commons.
- Test context failing when creating repository proxies.

If you need a newer version than what the Boot BOM manages, identify the corresponding Spring Data release train and check the Spring Boot matrix before overriding. Upgrade related modules together and verify dependency convergence; do not just change a single version line.

## 4. Client generations of Spring Data Elasticsearch

An important boundary in the history of Spring Data Elasticsearch is the transition from the Elasticsearch High Level REST Client to the Elasticsearch Java API Client.

At a major-family level of orientation:

| Spring Data Elasticsearch Line | Client Typically Associated with That Line | Implications When Upgrading |
|---|---|---|
| 4.x | Elasticsearch High Level REST Client (HLRC) | Code typically uses old client APIs and old query types |
| 5.x | Elasticsearch Java API Client | Switches to the new client; query model and transport configuration change |

This is a major-family architectural orientation, not a guaranteed patch-level table for every combination. Check the documentation for the exact minor/patch of Spring Data Elasticsearch and your project's dependency tree.

Moving from HLRC to the Java API Client is not just swapping an artifact:

- Request/response classes are different.
- Query builders and query data types are different.
- Client/transport configuration is different.
- Authentication, SSL, and HTTP header configuration may differ.
- Custom repositories, converters, or callbacks may need edits.
- Deprecated/removed APIs may no longer exist.

If the project still uses HLRC, do not add the new Java API Client just to use a code example without verifying whether the Spring Data version supports that combination.

## 5. Spring Boot and Spring Data Elasticsearch: reading the relationship by release train

The Spring Boot matrix typically shows which Spring Data release train a Boot version manages. That release train in turn determines the version of `spring-data-elasticsearch`.

You can read it down the chain:

~~~text
Spring Boot version
       |
       v
Spring Boot dependency management
       |
       v
Spring Data release train
       |
       v
spring-data-elasticsearch version
       |
       v
Supported client generation and dependency versions
~~~

A common historical orientation:

| Application Group | Spring Data Elasticsearch | Client Generation | Major Notes |
|---|---|---|---|
| Spring Boot 2.x applications | Usually Spring Data Elasticsearch 4.x | HLRC | Spring Framework 5 ecosystem and `javax` APIs |
| Spring Boot 3.x applications | Usually Spring Data Elasticsearch 5.x | Elasticsearch Java API Client | Spring Framework 6, Java 17 baseline, and Jakarta namespace |

This table only helps identify generations. It does not replace the specific release matrix. Not every patch of Boot 2/3 uses the exact same patch of Spring Data Elasticsearch; take the version managed by the Boot BOM for the exact release.

When upgrading from Boot 2 to Boot 3, beyond Elasticsearch there are changes from `javax.*` to `jakarta.*`, Java baseline, Spring Security, and other libraries. If you only check the Elasticsearch client, the application may still fail to build or start.

## 6. Reading the Elasticsearch Java client and server relationship

The Elasticsearch Java API Client is an HTTP client generated from the Elasticsearch API. The client version is closely tied to the server API line, though it does not necessarily have to match the server patch version.

When reading client/server documentation, distinguish:

- **Same-major compatibility**: client and server share the same major version; this is the normal compatibility zone to prioritize.
- **Forward compatibility**: an older client can communicate with a newer minor server within the same major version according to the published compatibility policy.
- **Backward compatibility**: a newer client communicating with an older server; do not assume this is supported by default.
- **Cross-major compatibility**: only rely on this if official documentation explicitly states how it is supported, such as REST API compatibility mode for a specific version pair.
- **Feature compatibility**: a request may be transmitted successfully, yet an older server does not support a new feature.

Do not infer compatibility merely from a request returning HTTP 200. Certain new fields, query options, or response properties may differ between versions.

### Example of how to read it

Suppose an application uses Java API Client line 8 and the server is also in line 8:

- This is the same-major zone, so it is a reasonable starting point.
- You need to verify whether the client minor supports the target server minor according to Elastic documentation.
- If the application uses an API newly added in a newer server minor, the client model must also have the corresponding API.
- If the server is upgraded by a minor version while the client stays the same, check forward compatibility and the behavior of the features in use.

If the application uses a client major newer than the server major, do not assume it works just because HTTP is a REST protocol. Check REST compatibility mode, media type/version headers, and API limitations in the documentation for that specific version pair.

## 7. Distinguishing protocol compatibility and feature compatibility

These two concepts are easily confused.

**Protocol compatibility** answers whether the client can send requests and understand responses over HTTP/API.

**Feature compatibility** answers whether the server supports the behavior the application requests.

For example:

- The client can connect and call `_search`.
- However, an older server does not recognize a new query option.
- Connection and authentication succeed.
- That specific request still fails with HTTP 400 or a query execution error.

Another example is a newer Java client having models for new response fields. When calling an older server, that field may be absent; code must not assume it is always present.

Therefore, the matrix must be read per feature used by the application, not only by client/server major version.

## 8. Elasticsearch REST API compatibility mode

Elasticsearch provides a REST API compatibility mechanism for certain major-version transitions. Its purpose is to allow clients from the previous major version to continue working during a documented transition period.

However:

- Not every API can use compatibility mode.
- Not every new feature can be used with an older client.
- Media type/compatibility headers must be configured properly for the version.
- Only rely on modes supported by Elastic for the specific major pair.
- This is not a guarantee that every client library and Spring Data version is fully compatible.

If Spring Data Elasticsearch does not expose the required compatibility configuration or the client does not support the corresponding request headers, manually adding a header in one place is not enough to guarantee the entire stack is compatible.

Prioritize upgrading the client/Spring Data along the supported path. Use compatibility mode as a time-boxed bridge with tests and a removal plan.

## 9. Do not confuse Elasticsearch server version with Java client version

Dependency example:

~~~xml
<dependency>
    <groupId>co.elastic.clients</groupId>
    <artifactId>elasticsearch-java</artifactId>
</dependency>
~~~

This artifact is the Java API Client. The Elasticsearch server is an independently running service whose version is determined in the cluster/container/managed service.

In addition, there may be HTTP transport dependencies, JSON mappers, and supporting libraries. Looking only at the version of `elasticsearch-java` does not tell you which version the server is running.

Record both:

| Component | Version Source |
|---|---|
| Spring Boot | Parent/BOM/build file |
| Spring Data Elasticsearch | Dependency management/Resolved dependency |
| Elasticsearch Java API Client | Dependency tree |
| HTTP transport | Dependency tree |
| Elasticsearch server | Cluster info/API or managed service control plane |
| Elasticsearch plugins | Plugin metadata and server deployment |
| Test Elasticsearch | Testcontainers image/tag |

Do not try to upgrade the server by changing a Maven dependency. Changing the client dependency does not upgrade the cluster; upgrading the cluster does not automatically update the client in the application.

## 10. Checking the running server version

Cluster information can be read via the root endpoint:

~~~http
GET /
~~~

The response typically contains the server version, build, and cluster details:

~~~json
{
  "name": "es-node-1",
  "cluster_name": "catalog",
  "version": {
    "number": "8.x.y",
    "build_flavor": "default",
    "build_type": "docker"
  },
  "tagline": "You Know, for Search"
}
~~~

The version in the example is a placeholder. Managed service environments may display different information or restrict APIs.

Verify the endpoint the application actually connects to. A cluster setup may have multiple environments or endpoints; checking local Elasticsearch does not prove production is on the same version.

You can also check:

~~~http
GET /_cluster/health
~~~

~~~http
GET /_cat/nodes?v
~~~

These APIs help confirm cluster and nodes, but require appropriate permissions. Do not grant cluster-admin to the runtime application just to read operational info; use a separate monitoring/admin identity.

## 11. Checking actual dependencies with Maven

Declarations in `pom.xml` are only inputs. Maven can resolve versions from parent, BOM, dependency management, profiles, or transitive dependencies.

View the dependency tree:

~~~bash
./mvnw dependency:tree
~~~

Filter relevant dependencies:

~~~bash
./mvnw dependency:tree \
  -Dincludes=org.springframework.boot:*,org.springframework.data:*,co.elastic.clients:*,org.elasticsearch.client:*
~~~

View the effective POM:

~~~bash
./mvnw help:effective-pom
~~~

You can save the effective POM to a file to inspect the managed versions after parent/BOM are applied.

When reading the output, look for:

- How many versions of `spring-data-commons` are present.
- Which version of `spring-data-elasticsearch` is actually selected.
- Whether `elasticsearch-java` matches the right client generation.
- Whether any `elasticsearch-rest-high-level-client` remains.
- Whether Maven selected a different dependency version due to a conflict.
- Which dependencies were omitted for conflict and which version won.

If a library pulls another client version into runtime, handle dependency management/exclusions intentionally. Do not add random exclusions before knowing which dependency needs it.

## 12. Checking actual dependencies with Gradle

Gradle can use version catalogs, platforms/BOMs, constraints, and resolution rules. Therefore, reading `build.gradle` alone is not enough.

View the runtime dependency graph:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Check the selected version for the Java API Client:

~~~bash
./gradlew dependencyInsight \
  --dependency elasticsearch-java \
  --configuration runtimeClasspath
~~~

Check Spring Data Elasticsearch:

~~~bash
./gradlew dependencyInsight \
  --dependency spring-data-elasticsearch \
  --configuration runtimeClasspath
~~~

Check Spring Data Commons:

~~~bash
./gradlew dependencyInsight \
  --dependency spring-data-commons \
  --configuration runtimeClasspath
~~~

`dependencyInsight` explains which dependency requested a version, which constraint won, and why other versions were dropped.

If using a Gradle platform:

~~~kotlin
dependencies {
    implementation(platform(
        "org.springframework.boot:spring-boot-dependencies:3.x.y"
    ))
    implementation("org.springframework.boot:spring-boot-starter-data-elasticsearch")
}
~~~

Use the version placeholder appropriate for the real project. If the project already uses the Spring Boot plugin/BOM, avoid importing another Boot BOM of a different version into the same configuration without a clear reason.

## 13. Identifying dependency conflicts

A healthy runtime classpath usually has a consistent version across modules that must move together in a release train.

Risk example:

~~~text
spring-data-commons: version A
spring-data-elasticsearch: version B
elasticsearch-java: version C
elasticsearch-rest-client: version D
~~~

Not all differing versions are wrong; artifacts have their own release schedules. What you need to verify is whether they belong to the dependency set supported by that release.

Signs of runtime conflict:

| Exception | Possible Meaning |
|---|---|
| `NoSuchMethodError` | Runtime class lacks a method called by compiled code |
| `NoClassDefFoundError` | Required class is missing from runtime classpath or initialization failed |
| `ClassNotFoundException` | Class loader cannot find the requested class |
| `AbstractMethodError` | Runtime implementation does not satisfy the method contract expected by caller |
| `NoSuchFieldError` | Field does not exist in the loaded class version |
| `UnsupportedClassVersionError` | Bytecode was compiled with a newer Java version than the current runtime |

Do not conclude every `NoClassDefFoundError` is a version conflict; static initializers or classpath configuration can also cause it. Read the full cause chain and dependency tree.

## 14. The Java runtime is part of the matrix

Spring Boot and foundational libraries have their own Java baselines. The project must use a JDK that satisfies all of:

- Spring Boot version.
- Spring Framework version.
- Spring Data release train.
- Elasticsearch Java API Client.
- Plugins/build tools/compilers.
- Application bytecode target.

Example Maven compiler configuration:

~~~xml
<properties>
    <java.version>17</java.version>
</properties>
~~~

Example Gradle toolchain:

~~~kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

The numbers in the examples are illustrative only. Use the baseline required by the specific Boot version and dependency set.

Distinguish between the JDK used to compile and the JDK used to run the application. CI might compile with a newer JDK while the production image still runs an older Java version, leading to `UnsupportedClassVersionError`.

When upgrading Boot, check the Docker base image, CI toolchain, local IDE, and production runtime together.

## 15. Jakarta namespace and major Spring changes

When upgrading from the Spring Framework 5/Spring Boot 2 generation to Spring Framework 6/Spring Boot 3, many APIs moved from `javax.*` to `jakarta.*`.

For example:

- `javax.servlet.*` moved to `jakarta.servlet.*`.
- `javax.validation.*` moved to `jakarta.validation.*`.
- Related Jakarta EE APIs may require corresponding versions.

This is not an Elasticsearch wire protocol issue, but it can prevent the application from compiling or prevent the Spring context from starting after upgrading Boot.

An old dependency pulling in `javax` APIs while the application needs `jakarta` can produce hard-to-diagnose failures. When reading the matrix, check web, validation, persistence, and security libraries at the same time.

Do not try to fix it by adding both namespaces to the classpath and ignoring the old dependency. Upgrade the library to a version supporting the new platform or replace the incompatible dependency.

## 16. Elasticsearch plugins must match the server

Elasticsearch plugins run inside the server process, so they have their own version rules. Analysis plugins, ingest plugins, or custom plugins typically require an exact version compatible with the Elasticsearch server node.

For example:

- Elasticsearch server version A.
- Analysis plugin built for version B.
- The node starts up and refuses to load the plugin due to a version mismatch.

Do not confuse plugin versions with the Java client version. Plugins are not runtime dependencies of the Spring application.

Check plugins on the server:

~~~http
GET /_cat/plugins?v
~~~

For Docker images, install plugins in the image build or deployment step according to the instructions for that exact Elasticsearch server version. When upgrading the server, check plugin availability/compatibility before rolling out nodes.

An application may connect successfully, yet the required analyzer is missing from the index/node; query behavior or index creation can then fail. Integration tests need a server image with the same plugin set as the target environment.

## 17. Testcontainers must also be in the matrix

Testcontainers is not just a test dependency. The Elasticsearch image launched by tests determines the server APIs and behavior the tests are verifying.

Example:

~~~java
@Container
static final ElasticsearchContainer elasticsearch =
        new ElasticsearchContainer(
                "docker.elastic.co/elasticsearch/elasticsearch:8.x.y"
        );
~~~

Do not use `latest` in a test suite that needs reproducible results. Pin the server image version and choose the version according to the goal:

- Current compatibility tests: use the production server version.
- Upgrade tests: also run against the target server version.
- Migration tests: verify data/mappings from the source version to the target version.
- Security/TLS tests: the image and fixtures must enable security according to the configuration being verified.

If production uses Elasticsearch 8.x while Testcontainers uses 7.x, integration tests can miss API differences. If tests use a newer version than production, tests may pass using a feature production does not yet support.

## 18. Reading the matrix by feature, not only by version

List the features the application uses:

| Feature | Spring Data/Client Must Support | Server Must Support |
|---|---|---|
| Repository CRUD | Repository mapping and client transport | Index/get/index/update/delete APIs |
| NativeQuery | Client query model | Specific Query DSL |
| Nested query | Query builder supporting nested | Nested mapping and nested query |
| Aggregation | Aggregation response model | Aggregation type/option |
| Highlight | Search hit/highlight mapping | Highlight API and field mapping |
| Bulk | Bulk request/response model | Bulk action and operation semantics |
| Search after/PIT | Client API and Spring Data integration | PIT/search_after APIs |
| API key | Authentication config in transport | Security feature/license/configuration |
| TLS/mTLS | SSL context/keystore/truststore | HTTP TLS and realm/configuration |
| Index lifecycle/alias | Admin client API if the app performs it | Index/alias APIs and privileges |

If the application does not use a feature, you do not need to treat it as a blocker. If it does use it, confirm the feature on both the client API and the server version.

## 19. Not every server API is in the Spring Data abstraction

Spring Data provides convenient abstractions, but it does not cover the entire Elasticsearch REST API. When you need a new API, you may have to:

- Upgrade Spring Data Elasticsearch so the API is exposed.
- Use the Elasticsearch Java API Client directly if dependencies/versions allow.
- Use a custom repository fragment or adapter.
- Use another REST client per official guidance if an unexposed endpoint is needed.

Do not add an arbitrary client version alongside the client managed by Spring Data. That can lead to two transport stacks, two connection pools, two sets of TLS/authentication configurations, and dependency conflicts.

If you must call an API directly, place it in an adapter with clear boundaries and document the version/feature dependency. Test both requests and responses against the target server version.

## 20. What structure should a project's compatibility matrix have?

An internal table should record the chosen versions and supporting evidence:

| Field | Value to Record |
|---|---|
| Spring Boot | Full version |
| Spring Framework | Version managed by Boot |
| Spring Data release train | Train name/version |
| Spring Data Elasticsearch | Resolved version |
| Spring Data Commons | Resolved version |
| Elasticsearch Java API Client | Resolved version |
| HTTP transport | Artifact/version |
| Elasticsearch server | Version of each environment |
| Java runtime | JDK vendor and version |
| Build tool | Maven/Gradle wrapper version |
| Testcontainers | Library version and Elasticsearch image tag |
| Elasticsearch plugins | Plugin name/version/server compatibility |
| Features | Query/API/security features used by the application |
| Evidence | Links to release notes/compatibility docs and integration test results |

The table should distinguish:

- **Declared version**: version written in the build file.
- **Resolved version**: version actually selected by Maven/Gradle.
- **Deployed version**: version running in the environment.
- **Tested version**: version verified by integration tests.

These four values can differ. When there is a discrepancy, explain it clearly rather than recording only a single number.

## 21. Example of reading a hypothetical matrix

Suppose the team has the following table (version numbers are placeholders to illustrate how to read it):

| Component | Project Version | Verification Source |
|---|---|---|
| Spring Boot | 3.A.B | Parent/BOM |
| Spring Data train | 2023.X | Boot dependency management |
| Spring Data Elasticsearch | 5.C.D | Resolved dependency |
| Elasticsearch Java API Client | 8.E.F | Dependency tree |
| Elasticsearch server production | 8.G.H | Cluster info |
| Elasticsearch server test | 8.G.H | Testcontainers image |
| Java runtime | 17 | Toolchain and production image |

How to read it:

1. Does Boot `3.A.B` manage Spring Data train `2023.X`?
2. Does Spring Data Elasticsearch `5.C.D` belong to the train supported by Boot?
3. Is Java API Client `8.E.F` the dependency expected by SDE `5.C.D`?
4. Does client `8.E.F` support server `8.G.H` according to Elastic documentation?
5. Does the test server have the same version and required plugin/security behavior as production?
6. Does JDK 17 satisfy Boot and all dependencies?
7. Do integration tests cover the features the application actually uses?

If a cell has no evidence, mark it as unverified. Do not fill in "compatible" just because the application runs on a developer's machine.

## 22. Distinguishing the official matrix from the dependency tree

These two sources answer different questions:

- **Compatibility matrix/release documentation**: which combinations are supported by the vendor.
- **Dependency tree/effective POM**: which versions the current application actually loads.

You need both.

For example, the dependency tree shows client version 8.x. That does not prove production server 8.y is supported. Conversely, the official matrix may list a supported combination, yet if the build file overrides a different client version, the project is no longer using the combination in the matrix.

Verification process:

1. Read the official matrix.
2. Read the release notes of Boot/Spring Data/Spring Data Elasticsearch.
3. Inspect the dependency tree.
4. Check the actual server version.
5. Run integration tests on the target server version.
6. Record the results and tested features.

## 23. Documentation pages to read

When verifying compatibility, prioritize official documentation for each component:

| Component | Documentation to Look For |
|---|---|
| Spring Boot | System requirements, dependency versions, release notes |
| Spring Data | Release train documentation and supported versions |
| Spring Data Elasticsearch | Reference documentation, compatibility note, migration guide |
| Elasticsearch Java API Client | Client compatibility and release notes |
| Elasticsearch server | Upgrade guide, REST API compatibility, breaking changes |
| Testcontainers | Elasticsearch module docs and version-specific notes |
| Java | JDK release notes and class-file compatibility |
| Plugins | Plugin compatibility with server version |

Do not rely on an old blog post as the sole source for a version table. A tutorial may have been accurate when written, but dependency management and supported server versions change across releases.

When reading documentation, check versioned URLs or select the documentation version matching the dependencies in use. The `current` page may describe a newer release than the production stack.

## 24. Reading release notes and migration guides

The compatibility matrix usually shows supported combinations, while release notes explain changes that can affect code.

Look for sections on:

- Minimum Java version.
- Changed dependency versions.
- Removed/deprecated client APIs.
- Query builder API changes.
- Mapping/converter changes.
- Changed default settings.
- Security/authentication changes.
- HTTP transport/TLS changes.
- Changed behavior in server APIs.
- Upgrade paths and breaking changes.

When doing a major upgrade, read migration guides from the current version to the target version. If there are multiple major versions in between, do not assume you can jump straight across without going through required upgrade steps.

For the Elasticsearch server, the upgrade path may impose rules on snapshots, intermediate versions, and rolling upgrades. Follow the server upgrade guide independently of upgrading the Java client.

## 25. Upgrade the client first or the server first?

There is no universal order for every case. The decision depends on the matrix and the supported upgrade path.

A possible workflow:

~~~text
Current application + current server
          |
          v
Inspect compatibility and breaking changes
          |
          v
Choose supported intermediate client/server combination
          |
          v
Upgrade application dependencies and test
          |
          v
Deploy compatible client to current server (if supported)
          |
          v
Upgrade server using official upgrade path
          |
          v
Run smoke/integration tests
          |
          v
Enable new features after both sides support them
~~~

In some cases, the server must be upgraded first to satisfy upgrade path requirements; in others, the client must be upgraded first so the application understands new APIs. Do not choose the order based purely on deployment convenience.

You must also check mixed-version clusters during a rolling upgrade. A client may connect to either an old or new node depending on the load balancer; compatibility must cover that transition window.

## 26. Planning Spring Boot and Spring Data upgrades

When upgrading Boot:

1. Identify the target Boot version and JDK baseline.
2. Check the dependency management of the target Boot version.
3. Identify the Spring Data release train managed by Boot.
4. Confirm the Spring Data Elasticsearch version and client generation.
5. Read Spring Framework/Spring Security migration notes.
6. Check the `javax`/`jakarta` namespace.
7. Run compilation, unit tests, and integration tests.
8. Inspect the resolved dependency tree.
9. Verify Elasticsearch client, SSL, and authentication configuration.
10. Run against the target server version.

If you need to override a Spring Data module, have a clear reason and compatibility evidence. Prefer letting the Boot BOM manage modules within the same release train.

## 27. Planning Elasticsearch server upgrades

When upgrading a cluster:

- Identify the current and target server versions.
- Check the official upgrade path.
- Review breaking changes in APIs/queries/mappings.
- Check plugins and modules.
- Check index formats and migration requirements.
- Create snapshots/backups according to instructions.
- Check shard allocation and cluster health.
- Check Java client/Spring Data support with the target server.
- Test on a data copy or staging environment.
- Monitor logs, tasks, cluster health, and search/write behavior after upgrading.

Do not merely verify that the root endpoint returns the new version. Run real operations the application uses: repository CRUD, search, aggregation, bulk, alias, security, and TLS.

## 28. Using Testcontainers to test multiple server versions

You can create different profiles/test suites to run the same integration test suite against multiple Elasticsearch images.

Example configuring the image via a property:

~~~java
static String elasticsearchImage() {
    return System.getProperty(
            "test.elasticsearch.image",
            "docker.elastic.co/elasticsearch/elasticsearch:8.x.y"
    );
}
~~~

Starting the container:

~~~java
@Container
static final ElasticsearchContainer elasticsearch =
        new ElasticsearchContainer(elasticsearchImage());
~~~

You can run tests with the current image and the target image via two CI jobs. Keep the same application dependency set when testing client/server compatibility. If you change both the client and server in the same test run, it will be hard to tell which change caused a failure.

The test matrix should include:

| Job | Spring/Client | Server Image | Goal |
|---|---|---|---|
| Baseline | Current | Current | Confirm current state |
| Target server | Current | Target | Test current client against target server |
| Target application | Target | Current | Test new client against current server |
| Full target | Target | Target | Confirm final combination |
| Upgrade path | Intermediate steps | Intermediate versions | Verify transition if needed |

Only run combinations supported by documentation or required to verify the upgrade plan. Do not treat every cell in the Cartesian product as a valid combination.

## 29. Analyzing common errors when stack versions drift

| Symptom | Where to Check First |
|---|---|
| `NoSuchMethodError` in Spring Data | Spring Data release train and dependency convergence |
| `ClassNotFoundException` for HLRC class | Code/client generation after migration |
| `NoClassDefFoundError` for Java API Client | Runtime dependency or excluded client artifact |
| `UnsupportedClassVersionError` | JDK runtime vs. dependency bytecode |
| HTTP 406 / media type error | REST compatibility headers/content type |
| HTTP 400 with unfamiliar query option | Whether the server supports the API/DSL option |
| Client compiles but server returns unsupported operation | Client/server feature compatibility |
| Plugin fails to load | Plugin version vs. Elasticsearch server |
| Tests pass but production fails | Test server image differs from production or lacks plugins/security |
| Spring context fails to start after Boot upgrade | Spring Framework/Jakarta/dependency versions |

Do not swap dependencies wholesale as soon as you see an error. First gather:

- Full stack trace.
- Resolved dependency tree.
- Boot/Spring Data/client/server/JDK versions.
- HTTP request/response error type if the request reached the server.
- Differences between test and production configurations.

## 30. A compatibility checklist for each upgrade

You can include a checklist in the pull request or release plan:

| Check | Evidence |
|---|---|
| Target Boot version supports current JDK | Boot system requirements |
| Spring Data train matches Boot | Boot dependency management |
| SDE version belongs to that train | Effective POM/dependency tree |
| Client generation is supported by SDE | SDE reference/release notes |
| Client version supports target server | Elastic compatibility docs |
| APIs/queries in use exist on target server | Feature docs/integration tests |
| Plugins are compatible with server | Plugin documentation |
| Testcontainers image matches target | CI config |
| Runtime JDK matches compile target | Docker/CI/runtime config |
| Security/TLS/auth work | Secured integration tests |
| Server upgrade path is valid | Elasticsearch upgrade guide |
| Rollback/snapshots are prepared | Deployment plan |

This checklist is for recording evidence, not replacing reading the documentation. An item should only be marked complete when backed by a source or test.

## 31. Example storing a version matrix in the project

You can keep a table in engineering documentation:

~~~yaml
platform:
  springBoot: "3.x.y"
  springFramework: "6.x.y"
  springDataTrain: "2023.x"
  springDataElasticsearch: "5.x.y"

elasticsearch:
  javaApiClient: "8.x.y"
  httpTransport: "resolved-version"
  productionServer: "8.x.y"
  testServerImage: "docker.elastic.co/elasticsearch/elasticsearch:8.x.y"
  plugins:
    - name: "analysis-plugin"
      version: "8.x.y"

runtime:
  java: "17"
  buildTool: "Gradle wrapper version"

verification:
  dependencyTreeReviewed: true
  officialCompatibilityDocsReviewed: true
  integrationTestsAgainstTargetServer: true
~~~

This is an illustrative structure, not a recommended version set. Update the table in the same pull request as the upgrade and keep links to the release notes/compatibility docs used.

Do not store passwords, API keys, or certificate private keys in the matrix. Record only versions, artifacts, image tags, and documentation references.

## 32. Common mistakes

### Looking only at the Spring Boot version

The Boot BOM manages many dependencies, but the Elasticsearch server is an independent system. Both client and server must be checked.

### Upgrading spring-data-elasticsearch independently

This can misalign Spring Data Commons or the release train. Check the Boot BOM and compatibility of the entire train.

### Assuming the Java API Client version must match the server patch

Not necessarily. Read the client/server compatibility policy and test the features in use.

### Assuming same major is enough

Same major is a starting point; it does not prove every API/feature is supported. Minor versions and feature availability still matter.

### Using a new client with an old server without checking

Backward/cross-major compatibility is not automatically guaranteed. Check REST compatibility mode if available and test thoroughly.

### Running only unit tests after upgrading

Unit tests do not prove HTTP protocol, mapping, and query behavior against a real server. Integration tests on the target server version are required.

### Using Testcontainers `latest`

Test results change over time and may differ from production. Pin the image version.

### Ignoring plugin versions

Nodes may fail to start or analyzers/processors may fail after a server upgrade. Check plugins alongside the server.

### Compiling with a new JDK but running with an old JDK

This can trigger `UnsupportedClassVersionError`. Align the CI toolchain and production runtime.

### Upgrading Boot and forgetting Jakarta migration

`javax.*` code or dependencies may be incompatible with the new Spring Framework. Read the full-stack migration guide.

### Using compatibility mode as a permanent solution

REST compatibility is a limited bridge. Plan to upgrade the client and remove the mode once the transition finishes.

### Not recording actual versions

Build files may declare a version different from resolved dependencies or the deployed server. Record declared, resolved, deployed, and tested versions.

## 33. Process for reading the matrix and verifying a stack

When preparing to select or upgrade versions:

1. Record the current Spring Boot, JDK, and build tool.
2. Inspect the Boot BOM to see the managed Spring Data release train.
3. Identify the actual `spring-data-elasticsearch` version.
4. Identify the resolved client generation and version.
5. Identify the HTTP transport and related dependencies.
6. Read compatibility guidance for the Java API Client with the server version.
7. Record the Elasticsearch server version for each environment.
8. Check the features/queries/security APIs the application actually uses.
9. Check plugins, Testcontainers image, and JDK runtime.
10. Read release notes/migration guides from current to target.
11. Run the dependency tree and resolve conflicts.
12. Run unit tests, then integration tests on the target server version.
13. If upgrading the server, follow the upgrade path and verify mixed-version transitions.
14. Save the compatibility matrix alongside documentation sources and test results.
15. Only enable new features once client, server, and mapping all support them.

## References

- [Spring Boot — Dependency Versions](https://docs.spring.io/spring-boot/appendix/dependency-versions/)
- [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
- [Spring Data — Release Trains](https://spring.io/projects/spring-data)
- [Spring Data Elasticsearch — Reference Documentation](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch.html)
- [Spring Data Elasticsearch — Migration Guides](https://docs.spring.io/spring-data/elasticsearch/reference/migration-guides.html)
- [Elasticsearch Java API Client — Compatibility](https://www.elastic.co/guide/en/elasticsearch/client/java-api-client/current/introduction.html)
- [Elasticsearch — REST API Compatibility](https://www.elastic.co/guide/en/elasticsearch/reference/current/rest-api-compatibility.html)
- [Elasticsearch — Upgrade Guide](https://www.elastic.co/guide/en/elasticsearch/reference/current/setup-upgrade.html)
- [Elasticsearch — Plugins](https://www.elastic.co/guide/en/elasticsearch/plugins/current/index.html)
- [Testcontainers — Elasticsearch Module](https://java.testcontainers.org/modules/elasticsearch/)
- [Maven — Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Gradle — Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html)

## Conclusion

Read the compatibility matrix along the chain Spring Boot → Spring Data release train → Spring Data Elasticsearch → Java client/transport → Elasticsearch server, while also checking JDK, plugins, and Testcontainers. The Boot BOM tells you which Spring dependencies are managed; the dependency tree shows which versions are actually resolved; Elastic documentation tells you which client/server pairs and features are supported. Same major does not replace minor/feature checks, and REST compatibility mode is only a scoped bridge. Record declared, resolved, deployed, and tested versions, read migration guides, and run integration tests against the target server before upgrading.
