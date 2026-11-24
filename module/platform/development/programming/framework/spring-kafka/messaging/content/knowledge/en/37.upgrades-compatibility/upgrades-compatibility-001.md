# Tracking the Spring Kafka Version Matrix

A Spring Kafka application does not have just one version to track. The actual runtime is a combination of the JDK, Spring Boot, Spring Framework, Spring Kafka, Kafka client, Kafka broker, and sometimes Kafka Streams, serializers, or Schema Registry. A single upgraded dependency can change APIs, retry behavior, transactions, serialization, or connection protocols even if the application source code does not change.

A compatibility matrix records the verified combination, the running environment, the verification source, and the test results. It helps the development team know which combinations are supported, which are only protocol-compatible, and which have actually been tested by the application. The matrix must be operational data with an owner and an update date, not just a version table copied from a README.

This lesson belongs to the **Upgrades and Compatibility** chapter of the **SPRING_KAFKA_MESSAGING** module. The module focuses on building applications that send and receive events using Spring Kafka, `KafkaTemplate`, and `@KafkaListener`, understanding topics, partitions, offsets, and consumer groups; while also learning serialization, retry, dead-letter, transactions, exactly-once, concurrent processing, and testing to operate reliable messaging flows.

## 1. Why track a version matrix?

A Kafka system has multiple software layers that are released independently. For example, an application may use Spring Boot to manage dependencies, Spring Kafka to provide listener containers and templates, Kafka client to implement the protocol, and the broker operated by a platform team.

If you only record "the application uses Spring Kafka 3.x", the operations team still does not know:

- Which versions of Spring Boot and Spring Framework are running.
- Which version of Kafka client is actually resolved from the dependency tree.
- Which version the Kafka broker cluster is running and whether it is undergoing a rolling upgrade.
- Whether the runtime JDK and build JDK meet the requirements of each component.
- Whether `spring-kafka-test`, Kafka Streams, serializers, and the Schema Registry client belong to the same compatible combination.
- Whether that combination has been tested in a production-like environment or has only built successfully.

The matrix answers these questions at a specific point in time. When a component changes, the team can identify which components need to be re-evaluated and tested.

## 2. Version layers in a Spring Kafka application

A minimal matrix should track the following layers:

| Component | Role | What to verify |
| --- | --- | --- |
| JDK | Runtime and compiler | Minimum/maximum Java version supported by the framework |
| Spring Boot | Application platform and dependency management | Spring Framework, Spring Kafka, and managed dependency versions |
| Spring Framework | Container, transactions, lifecycle, AOP | Version compatible with Boot and integration libraries |
| Spring Kafka | `KafkaTemplate`, listener container, error handling | APIs, behavior, and Kafka client range |
| `kafka-clients` | Producer, consumer, AdminClient, and protocol | Resolved version, broker compatibility, and feature support |
| Kafka broker | Storage, replication, group coordinator, transactions | Cluster version, rolling-upgrade state, and broker configuration |
| Kafka Streams | Stream processing API/runtime if used by the application | Same Kafka client line and state store compatibility |
| Serializer/Schema Registry | Event conversion and schema management | Wire format, serializer API, and server compatibility |
| `spring-kafka-test` | Embedded Kafka and test utilities | Same version line as the Spring Kafka runtime |
| Build tool/plugin | Compile, test, packaging | Maven/Gradle and plugin support for the current JDK |

Not every application uses Kafka Streams or Schema Registry. Mark non-applicable components explicitly instead of leaving them ambiguously blank.

## 3. Compatibility does not mean the same version

Components do not need to share the same version number. Spring Boot manages a set of integrated dependencies; Spring Kafka depends on the Kafka client; the Kafka client communicates with the broker over a protocol that has compatibility rules defined by Kafka.

For example, the Spring Kafka version number and the Kafka broker version number do not necessarily match. A newer Kafka client can connect to an older broker within the supported protocol range, though new features may require a newer broker. Similarly, an application compiling successfully does not prove that every runtime path works.

You need to distinguish:

- **Build compatibility:** dependencies resolve and the source code compiles.
- **API compatibility:** classes/methods called by the application still exist and preserve the required semantics.
- **Protocol compatibility:** the client and broker can exchange requests/responses.
- **Feature compatibility:** a specific feature is supported by the client, the broker, and the configuration.
- **Operational compatibility:** real workloads run stably and can be observed, upgraded, and rolled back.

A combination should only be marked as verified when the levels required for the workload have been checked.

## 4. Authoritative sources for version verification

Do not take a matrix from a blog post or an undated table. Verify against the official documentation of each component:

| Question | Source to check |
| --- | --- |
| Which JDKs does Spring Boot support? | Spring Boot System Requirements and release notes |
| Which Spring Framework and Spring Kafka versions does Boot manage? | Dependency Versions appendix/BOM of the exact Spring Boot release |
| Which APIs and Kafka clients does Spring Kafka support? | Spring for Apache Kafka reference, release notes, and dependency metadata |
| Which brokers/protocols does the Kafka client support? | Apache Kafka documentation and release/upgrade notes |
| In what order should Kafka brokers be upgraded? | Apache Kafka upgrade guide for the source and target releases |
| Are the serializer/Schema Registry compatible? | Official documentation of the serializer and Schema Registry vendor |
| Is the runtime JDK supported? | JDK vendor support matrix and framework requirements |

When recording a decision in the matrix, save the URL or document name, document version, check date, and verifier. Release notes often contain changes that cannot be inferred from version numbers alone, such as deprecations, default behavior changes, and compatibility limits.

## 5. Spring Boot BOM as the starting point for dependency versions

In a Spring Boot project, you should let Spring Boot dependency management manage the corresponding Spring and Kafka dependencies, unless there is a verified decision to upgrade independently.

Maven example using the Spring Boot parent:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>BOOT_VERSION</version>
    <relativePath/>
</parent>

<dependencies>
    <dependency>
        <groupId>org.springframework.kafka</groupId>
        <artifactId>spring-kafka</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.kafka</groupId>
        <artifactId>spring-kafka-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

The placeholder `BOOT_VERSION` is provided in project properties or the organization's version catalog. Do not copy an illustrative version number into production without checking against the selected release.

If the project imports the `spring-boot-dependencies` BOM instead of using the parent, ensure the BOM is imported with the right scope and precedence order. Dependencies without an explicit version will take the version provided by dependency management.

## 6. Managing dependencies with Gradle

With Gradle, you can use the Spring Boot plugin together with dependency management or import the platform BOM:

~~~kotlin
val bootVersion = providers.gradleProperty("springBootVersion").get()

dependencies {
    implementation(platform("org.springframework.boot:spring-boot-dependencies:$bootVersion"))
    implementation("org.springframework.kafka:spring-kafka")
    testImplementation("org.springframework.kafka:spring-kafka-test")
}
~~~

If the project already uses the Spring Boot Gradle plugin and dependency management, avoid duplicate unnecessary BOM declarations. Choose one consistent version management mechanism.

Do not set independent versions for `spring-kafka`, `kafka-clients`, and `spring-kafka-test` arbitrarily. If you must override a component, record the reason, verification source, and required tests in the compatibility record.

## 7. Verifying the actual resolved dependencies

Build files only reflect direct declarations. Transitive dependencies, BOMs, plugins, or constraints can cause the runtime version to differ from what you expect.

Maven:

~~~bash
mvn help:effective-pom
mvn dependency:tree -Dincludes=org.springframework.kafka:*,org.apache.kafka:*
~~~

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency kafka-clients \
  --configuration runtimeClasspath
~~~

You should check `compileClasspath`, `runtimeClasspath`, and the test classpath when they differ. Save the dependency tree output of the release candidate to compare against the deployed artifact.

If the dependency tree has multiple versions or a forced version, find which dependency pulls that version in. Do not resolve conflicts by excluding dependencies randomly, because that can remove classes or APIs needed by another library.

## 8. Spring Boot, Spring Framework, and Spring Kafka

A Spring Boot release is built around a Spring Framework line and a set of dependencies tested together. When upgrading Boot, read the release notes for changes in the Framework, auto-configuration, property binding, logging, Jackson, and transactions.

Spring Kafka integrates deeply with the Spring container, bean lifecycle, transaction manager, and observation. Therefore, the Spring Kafka version is not just an isolated producer/consumer library. APIs for listener containers, error handlers, message conversion, and transaction integration can change across lines.

Version selection process:

1. Choose the target Spring Boot release based on JDK support and application policy.
2. Read the dependency versions of the target Boot release to find the managed Spring Framework and Spring Kafka versions.
3. Check the Spring Kafka release notes and migration guide.
4. Verify the resolved Kafka client version.
5. Check broker and feature requirements.
6. Run compile, unit/component tests, and integration tests before rollout.

Do not upgrade Spring Framework independently from the Boot-managed line without a clear reason and support matrix.

## 9. Spring Kafka and kafka-clients

Spring Kafka provides abstractions such as `KafkaTemplate`, `@KafkaListener`, listener containers, message conversion, error handlers, and transaction integration. Protocol execution lives in the Apache Kafka Java client, typically the `kafka-clients` artifact.

Some Spring Kafka APIs call Kafka client APIs directly. Therefore, overriding the Kafka client to one that is too old or too new can cause compile/runtime errors such as `NoSuchMethodError`, `ClassNotFoundException`, or behavior different from the version Spring Kafka was tested against.

Track at least:

- Spring Kafka version.
- Resolved `kafka-clients` version.
- Kafka broker version per cluster.
- Whether Kafka client config uses any new features.
- Whether release notes change defaults or introduce deprecations.

Do not assume the Kafka client version must match the broker version. Read the compatibility guidance and test against the actual target broker.

## 10. Kafka client and broker compatibility

The Kafka client and broker have an API version negotiation mechanism within the supported range, but not every feature is available across every combination.

When checking compatibility, distinguish:

- Can the client connect and perform basic requests?
- Does the broker support the API versions required for the feature?
- Does the feature require new broker configuration or cluster metadata?
- Is the cluster undergoing a rolling upgrade with brokers on multiple versions; does the client work with all brokers during the transition?
- Have transaction, idempotent producer, group protocol, topic administration, or quota behaviors changed?

For example, an application using transactions must verify the producer transaction API, broker support, transaction coordinator, and transactional ID configuration. Testing only non-transactional record sends is not enough to prove transactions work.

When a cluster has multiple broker versions during a rolling upgrade, test both the mixed-version phase and the post-upgrade state. Follow the upgrade order and inter-broker protocol guidance of the respective Kafka release.

## 11. Tracking the JDK and bytecode target

The build JDK, test JDK, and runtime JDK can differ. The matrix should clearly state:

- JDK used on developer workstations/CI.
- Java toolchain/compiler release.
- Bytecode target.
- JDK running the production container.
- JDKs supported by Spring Boot and related libraries.
- JDK vendor/distribution if the organization has a specific standard.

Gradle toolchain example:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}
~~~

Maven compiler release example:

~~~xml
<properties>
    <maven.compiler.release>JAVA_RELEASE</maven.compiler.release>
</properties>
~~~

These values only illustrate how to declare the setting. Choose the JDK based on the target Boot requirements and runtime policy. Compiling with a newer JDK does not automatically prove the application runs on a lower JDK; bytecode target, called APIs, and runtime dependencies must all align.

## 12. Kafka Streams, serializers, and Schema Registry

If a module uses Kafka Streams, track the `kafka-streams` artifact, Kafka client, state stores, and Kafka Streams migration requirements. Upgrading Kafka Streams can involve state directories, changelog topics, repartition topics, and how state is restored.

For serializers outside Apache Kafka—such as JSON, Avro, Protobuf, or vendor serializers—record their versions separately. Check:

- Whether the serializer/deserializer API is compatible with the Kafka client.
- Whether the wire format and schema ID are compatible with old data.
- Schema Registry server version and client version.
- Subject/schema compatibility mode.
- Reader/writer schema evolution.
- Topics containing data produced by previous application versions.

A new application starting successfully does not prove it can read all existing events. Test with fixture data generated by both old and new versions.

## 13. Building a compatibility matrix table

The matrix should have a row for each environment and workload combination, rather than listing only the latest version:

| Component | Development | Staging | Production | Source/notes |
| --- | --- | --- | --- | --- |
| JDK | `<version>` | `<version>` | `<version>` | Vendor + support policy |
| Spring Boot | `<version>` | `<version>` | `<version>` | BOM/release notes |
| Spring Framework | `<resolved>` | `<resolved>` | `<resolved>` | Boot dependency management |
| Spring Kafka | `<resolved>` | `<resolved>` | `<resolved>` | Spring Kafka release notes |
| kafka-clients | `<resolved>` | `<resolved>` | `<resolved>` | Dependency tree + broker compatibility |
| Kafka broker | `<cluster version>` | `<cluster version>` | `<cluster version>` | Platform owner/upgrade plan |
| Kafka Streams | `<version or N/A>` | `<version or N/A>` | `<version or N/A>` | If used by the workload |
| Serializer/Registry | `<version>` | `<version>` | `<version>` | Wire format/schema policy |
| Test libraries | `<version>` | `<version>` | `<version>` | Same runtime line when required |

Add columns for `status`, `last verified`, `owner`, `evidence link`, `known limitation`, and `next review date`. Values can be `candidate`, `tested`, `approved`, `deprecated`, or `blocked`.

Do not mark `tested` solely because dependencies resolved successfully. The status must reflect test evidence for that specific combination.

## 14. Distinguishing the compatibility matrix from the upgrade target matrix

The two tables serve different purposes:

- **Compatibility matrix** records combinations currently running or already verified.
- **Upgrade target matrix** records planned upgrade combinations, transition steps, and acceptance criteria.

Example:

| Item | Current | Target | Required evidence |
| --- | --- | --- | --- |
| Spring Boot | `<current>` | `<target>` | Release notes, dependency BOM |
| Spring Kafka | `<current>` | `<target>` | API migration and integration tests |
| Kafka client | `<current>` | `<resolved target>` | Dependency tree and broker protocol |
| Broker | `<current>` | `<target>` | Kafka upgrade guide and mixed-version test |
| JDK | `<current>` | `<target>` | Framework support and runtime test |

Do not write the target into the current column before production rollout is complete. If staging has been upgraded while production has not, keep the two states separate.

## 15. Tracking deprecations and API migrations

Spring Kafka and Spring Boot release notes must be read before upgrading. An API may still compile yet be deprecated, or the behavior of a handler/container may have changed.

API areas to review in a messaging application:

- Error handling: legacy `ErrorHandler` and `CommonErrorHandler`/`DefaultErrorHandler` APIs.
- Retry: blocking retry, retry topics, and recovery configuration.
- Listener container: transaction manager, acknowledgment, pause/resume, and concurrency.
- Producer: transactions, idempotence, callbacks, and observation.
- Message conversion: JSON serializer/deserializer, trusted packages, and type headers.
- Consumer: group protocol, isolation level, and offset management.
- Test: `@EmbeddedKafka`, `KafkaTestUtils`, and test lifecycle.

This list identifies areas to check, not a claim that all APIs are removed in the same release. Verify deprecations/removals in the release notes and compiler warnings of the exact version.

## 16. Properties and default behavior can change

Upgrading versions can change default values or how properties are bound. An application whose YAML is unchanged can still exhibit different behavior.

Review these configuration groups:

- `spring.kafka.bootstrap-servers`, producer, and consumer properties.
- `max.poll.records`, `max.poll.interval.ms`, auto commit, and isolation level.
- Retry/backoff, error handler, and DLT destination.
- Transaction ID prefix and transaction timeout.
- Serializer/deserializer and message conversion.
- SSL/SASL properties, truststore, and credentials.
- Listener concurrency, AckMode, and container lifecycle.
- Observation, metrics, and tracing.

Compare configuration metadata and release notes between source and target. For deprecated properties, plan the migration before they are removed. Do not copy all old defaults into explicit configuration without understanding why; doing so can prevent the application from receiving default improvements in the new version.

## 17. Process for evaluating an upgrade

A controlled upgrade should go through these steps:

1. Record the current matrix and dependency tree.
2. Select a target release that is still supported under organizational policy.
3. Read the release notes for Boot, Spring Kafka, Kafka client, and broker.
4. Identify the Java baseline and build tool/plugin requirements.
5. Find deprecated/removed APIs and property behavior changes.
6. Verify broker/client protocol and feature requirements.
7. Update the BOM or dependency constraints from one clear source of management.
8. Compile and run unit/component tests.
9. Run integration tests against a broker version close to production.
10. Run contract tests with old and new events/schemas.
11. Run performance/regression tests for throughput, latency, and memory.
12. Deploy to staging/canary and observe metrics.
13. Roll out to production according to plan and update the matrix after completion.

If you change Boot, Spring Kafka, broker, and JDK at the same time, it will be hard to isolate the root cause when failures occur. When possible, break the upgrade into smaller independently verifiable changes.

## 18. Which layers does compatibility testing require?

A proper test suite should include:

| Test | What to confirm |
| --- | --- |
| Compile/API | Source code and APIs used by the application remain valid |
| Unit | Business logic, retry classifier, and serializer wrapper |
| Spring context | Auto-configuration, bean wiring, and listener startup |
| Embedded Kafka | Basic listener, producer, DLT, and offset flow |
| Testcontainers/real broker | Broker/client protocol, transactions, group behavior |
| Schema compatibility | Reading old events and writing new events |
| Security integration | TLS/SASL, principal, and ACLs |
| Performance regression | Throughput, latency, heap, GC, and consumer lag |
| Rolling upgrade test | Mixed broker/client versions and rebalance |
| Recovery test | Restart, retry, DLT, transaction rollback, and replay |

A passing `@SpringBootTest` only proves the context can initialize. It does not replace testing against a real broker, old schemas, or network errors.

## 19. Testing the matrix across multiple environments

Development, staging, and production may use different broker versions or security configurations. Do not infer production compatibility solely from local Embedded Kafka.

Document the differences:

- Broker version and topology.
- Replication factor, min ISR, and topic configuration.
- TLS/SASL mechanisms and ACL authorizer.
- Transaction coordinator configuration.
- Schema Registry version and compatibility mode.
- Network latency, DNS, and quotas.
- JDK/container image.
- Partition count, record size, and traffic profile.

Staging should match production as closely as possible in protocol, security, and topology. If staging cannot match completely, record the limitations and add dedicated tests for the differences.

## 20. Tracking feature gates and broker limits

Some features require support from both the client and the broker, and sometimes broker or topic configuration as well. The matrix should have a dedicated feature table:

| Feature | Client/API | Broker requirement | Config/test |
| --- | --- | --- | --- |
| Idempotent producer | Supported by Kafka client | Broker supports required protocol | Retry/restart and duplicate test |
| Kafka transactions | Spring Kafka + Kafka client | Transaction coordinator available | Commit/abort/read_committed test |
| New consumer group protocol | Supported by Kafka client | Broker supports corresponding protocol | Rebalance/assignment test |
| Topic administration | AdminClient API | Broker supports operation | ACL and timeout test |
| Kafka Streams feature | Kafka Streams/client | Compatible broker and internal topics | State restore/upgrade test |

Do not mark a feature as supported just because a class or property exists. Check the broker minimum version, cluster settings, license/modules if any, and run runtime tests.

## 21. Upgrading the broker and application in order

Upgrading the broker and upgrading the application are two changes that can be coordinated, though they do not always have to happen at the same time. The order depends on the Kafka release, client compatibility, and features used.

Principles:

- Read the upgrade guide for the source and target Kafka releases.
- Check rolling upgrade and mixed-version compatibility.
- Do not raise the inter-broker protocol/version marker before every broker meets the requirements in the guide.
- Verify that old clients still work while brokers are in a mixed-version phase.
- Enable new features only after the cluster and all required clients are ready.
- Upgrade application clients via canary to check protocol and behavior.
- Monitor leader movement, ISR, request errors, consumer lag, and transaction state.

Do not deduce the broker upgrade order from major/minor version numbers alone. Kafka has specific migration steps for certain releases; follow the official upgrade guide for the exact version.

## 22. Managing dependency overrides and exceptions

Sometimes you need to override `kafka-clients` or another dependency for a security patch or bug fix. This is an exception that must be documented, not the default way to manage versions.

An exception record should include:

- Dependency and the version managed by the BOM.
- Override version.
- Reason (CVE, bug, feature, or vendor requirement).
- Verification source confirming compatibility with Spring Kafka.
- Tests executed and results.
- Approving owner.
- Review deadline and plan to remove the override.

After overriding, inspect the dependency tree and runtime packages. The test classpath must also be compatible; avoid having runtime use a different Kafka client version than tests due to differing dependency management scopes.

## 23. Tracking security support and end of life

Technical compatibility does not mean security support is still active. A combination may run, yet Spring Boot, Spring Kafka, Kafka broker, or the JDK may have reached end of support according to vendor/community policy.

The matrix should record:

- Whether the release in use is still within its support window.
- End-of-support date if published.
- Relevant security advisories/CVEs.
- Minimum patched version.
- Owner responsible for the upgrade.
- Remediation deadline and exception status.

Do not track only major versions. Patch releases can contain important security fixes or regressions. Follow security advisories for the projects and vendors the application actually uses.

## 24. Automating matrix checks

You can automatically extract versions from the build and include them in CI reports:

- Export Maven effective POM/dependency tree.
- Export Gradle runtime dependency report.
- Capture the JDK version from the build agent and container image.
- Retrieve the broker version from platform inventory or cluster admin.
- Compare against the approved matrix.
- Fail the build if a dependency is overridden outside policy.
- Attach test results and commit SHA to the compatibility record.

Do not scrape arbitrary web pages to automatically decide which versions are supported. It is better to store approved constraints in a repository or owned catalog, and have CI validate resolved dependencies against that catalog.

The matrix needs review when changing the Boot BOM, Spring Kafka, Kafka client, broker, JDK, serializer, Schema Registry, or security mechanism. Set up a periodic review schedule and trigger an immediate review whenever a security advisory or release support status changes.

## 25. Runbook when an incompatible combination is detected

When an application fails after an upgrade:

1. Record the exact resolved versions from runtime and the dependency tree.
2. Compare against the matrix approved before the change.
3. Identify whether the error occurs at compile time, startup, TLS/authentication, protocol, listener, or data format.
4. Read the release notes for each changed component.
5. Check for `NoSuchMethodError`, `ClassNotFoundException`, `UnsupportedVersionException`, authentication/authorization errors, and serialization exceptions.
6. Reproduce with the corresponding broker/version and JDK.
7. Narrow the change down to a single component if possible.
8. Choose to fix or roll back according to a verified plan.
9. Re-run integration, schema, and performance tests.
10. Update the matrix, evidence, and known limitations.

Do not fix issues by upgrading every dependency to `latest` at the same time. That increases the number of variables and makes the root cause harder to identify.

## 26. Rollback and keeping the matrix accurate

Application rollback may not be straightforward if the broker or schema has already been upgraded. Before rollout, confirm that the target remains compatible with the current broker and that the older application version can run against the cluster after the change.

Prepare:

- Application artifact/container image from before the upgrade.
- Dependency lock or old BOM version.
- Old configuration and secret references.
- Compatibility of the old client with the current broker.
- Schema backward/forward compatibility.
- Transactional ID and consumer group behavior during rollback.
- Replay or duplicate-handling procedure if offsets or logic changed.

Do not roll back the broker or schema automatically if new data/metadata incompatible with the older version already exists. Update the matrix to reflect the actual state after rollback; do not leave the target version showing as current.

## 27. Template for a combination verification record

A verification record should contain:

| Field | Content |
| --- | --- |
| Workload | Service and consumer/producer group |
| Environment | Dev, staging, or production |
| JDK | Runtime/build version |
| Spring Boot | Version and BOM source |
| Spring Framework | Resolved version |
| Spring Kafka | Resolved version |
| kafka-clients | Runtime resolved version |
| Broker | Cluster version and topology |
| Serializer/Registry | Library and server version |
| Features | Transactions, retry, Streams, security... |
| Test evidence | Build, integration, schema, performance |
| Status | Candidate, tested, approved, deprecated, or blocked |
| Owner | Responsible person/team |
| Verified at | Verification date |
| Limitations | Known limitations and applicability conditions |

Store evidence such as dependency reports, test reports, release-note links, and deployment revisions. Do not store secrets, passwords, tokens, or private keys in the compatibility matrix.

## 28. Checklist for tracking the Spring Kafka version matrix

Before approving a combination, confirm:

1. Build and runtime JDKs meet the target Spring Boot requirements.
2. Spring Boot BOM properly manages Spring Framework and Spring Kafka.
3. Actual resolved Spring Kafka and `kafka-clients` versions have been checked.
4. `spring-kafka-test` is compatible with runtime dependencies.
5. Kafka broker version and rolling-upgrade state are recorded.
6. Client/broker protocol and feature requirements are verified.
7. Kafka Streams/serializers/Schema Registry are checked if used by the workload.
8. Deprecated/removed APIs and property default changes have been reviewed.
9. Security support and end-of-life status remain appropriate.
10. Unit, context, integration, schema, and performance tests pass.
11. Staging/canary verified with production-like configuration.
12. Rollback path is compatible with the post-change broker and schema.
13. Dependency overrides have a reason, owner, evidence, and review date.
14. The matrix has source links, last verified date, owner, and known limitations.
15. The current version is updated only after the actual rollout completes.

Tracking the Spring Kafka version matrix means tracking a verified runtime combination, not comparing isolated version numbers. Start from the Spring Boot BOM and dependency tree, then verify the JDK, Spring Kafka, Kafka client, broker, serializers, and active features. Record test evidence, limitations, and owners for each environment; only promote a combination from candidate to approved once build, integration, schema, security, and operations are confirmed.

