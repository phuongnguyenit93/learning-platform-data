# Separating Local and CI Configurations with Profiles

## 1. Why do we need Maven profiles for contract testing?

In a microservices system, the **producer** defines HTTP APIs or messages using Groovy/YAML DSL, **Spring Cloud Contract Verifier** generates tests to verify the implementation, and then packages mappings into a stub artifact. The **consumer** runs tests via **Stub Runner** to detect changes that break client compatibility early. This workflow must operate reliably both on a developer's machine and in **CI**.

The challenge is that **local and CI environments have different conditions**:

- Locally, you might edit a contract in the producer, run `mvn install`, and let the consumer pick up stubs from `~/.m2/repository`.
- In CI, producer and consumer often run in separate pipelines/repositories, needing **exact-version** stubs from Nexus/Artifactory or a controlled artifact repository.
- Local machines might lack network access or credentials for shared repositories; CI must ensure it never silently pulls a stale stub cached on a build agent.
- CI must execute generated producer tests, never passing green due to `skipTests` or discovering zero contracts.
- Test configuration must be reproducible: the same commit and stub version must test against the same API agreement.

**Maven profiles** let you maintain one shared `pom.xml` while choosing environment-specific properties or settings via `-P` or activation conditions. This lesson belongs to the **Maven Integration** chapter of module `SPRING_CLOUD_CONTRACT` and focuses on **separating local and CI configurations with profiles**.

### Learning objectives

After this lesson, you can:

1. Distinguish **Maven build profiles**, **Spring Boot runtime profiles**, and **Stub Runner stubs modes**.
2. Design `contract-local` and `contract-ci` profiles without duplicating plugin configurations.
3. Bridge Maven properties to Spring properties actually read by consumer tests.
4. Choose `LOCAL` for stubs installed in the local Maven repository and `REMOTE` for CI artifact repositories.
5. Keep generated producer test configuration, base classes, test framework, and test mode consistent.
6. Distinguish dangerous test-skip commands from genuine verification steps.
7. Place repository URLs, artifact versions, credentials, and Maven `settings.xml` properly.
8. Diagnose why builds pass locally yet fail in CI, or appear false-green in CI.
9. Build a release gate: publish stubs to consumers only after producer verification passes.

> **Principle:** Profiles change **where artifacts come from and build execution policies**; they should never alter contract semantics just to turn a test green. Producer and consumer must still agree on the same request/response or message schema.

## 2. Three easily confused concepts: Maven profile, Spring profile, and stubs mode

| Concept | Controls | Example | Activation |
| --- | --- | --- | --- |
| **Maven build profile** | Build POM, dependencies, plugins, and Maven properties | `contract-local`, `contract-ci` | `mvn -Pcontract-ci verify` |
| **Spring profile** | Spring application beans/configuration at runtime | `test`, `ci`, `local` | `spring.profiles.active=test` or `@ActiveProfiles` |
| **Stub Runner stubs mode** | How Stub Runner locates stub artifacts | `CLASSPATH`, `LOCAL`, `REMOTE` | `spring.cloud.contract.stubrunner.stubsMode` |
| **Verifier contractsMode** | How the Maven plugin fetches **external contract sources** when using external contracts | `LOCAL`, `REMOTE` | `<contractsMode>...` in plugin |

All four can share the word "local," yet **they do not link to each other automatically**.

Example command:

~~~bash
./mvnw -Pcontract-ci -Dspring.profiles.active=test verify
~~~

In this command:

- `-Pcontract-ci` activates the **Maven profile**.
- `-Dspring.profiles.active=test` sets the **Spring profile** for test JVMs receiving that property.
- `Stub Runner` may read `REMOTE` via Maven/Surefire configuration in that profile; it **does not infer** the mode from the name `contract-ci`.
- `Verifier contractsMode` is not `Stub Runner stubsMode`: one chooses the source of *contract definitions*, while the other chooses the source of *stub artifacts*.

### 2.1. Choosing clear boundaries of responsibility

A maintainable separation:

- In the shared POM section: keep dependency versions, the Verifier plugin, `baseClassForTests`, `testFramework`, `testMode`, and stable verification rules.
- In `contract-local`: choose local stub sources, dynamic ports, or developer-friendly defaults.
- In `contract-ci`: choose remote stub sources, pin versions, fail on missing artifacts, and enforce quality gates.
- In `settings.xml`/CI secrets: manage mirrors, Maven repository credentials, and publish permissions.
- In `application-test.yml` or Spring test context: keep app settings such as HTTP client base URLs if not driven directly by Maven profiles.

**Never switch test mode from `MOCKMVC` to `WEBTESTCLIENT` per environment** just to paper over differences: test mode must follow the producer's stack (Spring MVC vs WebFlux), not the machine running the build.

## 3. Aligning local and CI Maven workflows

~~~mermaid
flowchart TD
    A["Groovy/YAML contracts"] --> B["Maven Contract Verifier: generateTests"]
    B --> C["Generated producer tests"]
    C --> D{"Producer verification passes?"}
    D -- "No" --> E["Build fails, do not publish"]
    D -- "Yes" --> F["Generate/attach stubs classifier"]
    F --> L["Local: mvn install into .m2"]
    F --> R["CI: mvn deploy to artifact repository"]
    L --> S["Consumer -Pcontract-local"]
    R --> T["Consumer -Pcontract-ci"]
    S --> U["Stub Runner WireMock"]
    T --> U
    U --> V["Consumer test invokes real client"]
    V --> W{"Assertions pass?"}
    W -- "No" --> X["Fix consumer/contract or version"]
    W -- "Yes" --> Y["Compatibility evidence within test scope"]
~~~

**Both sides must be verified independently**:

1. Producer tests confirm the real implementation satisfies the contract.
2. Consumer tests confirm the client and use cases handle stubs properly.
3. Stub artifacts should only be **published/promoted** once the producer passes required gates.
4. Local and CI may resolve stubs from different sources, yet you must know the exact `groupId:artifactId:version:classifier` coordinates tested.

### 3.1. Same coordinates do not guarantee identical bytes

If a developer reinstalls `inventory-producer:1.2.3:stubs` into the local repository with modified content while the release repository holds the older `1.2.3`, the two profiles run against **different stub contents under identical coordinates**.

Enforce an **immutable** artifact policy for releases, bumping versions or using explicit snapshots when content changes. Checking checksums, artifact metadata, and provenance is especially important when local passes while CI fails.

## 4. How do Maven profiles work?

Profiles are declared inside `<profiles>` in `pom.xml`, with an `<id>` and optional `<properties>`, `<dependencies>`, `<build>`, or repository configurations.

Minimal example:

~~~xml
<profiles>
    <profile>
        <id>contract-local</id>
        <properties>
            <contract.environment>local</contract.environment>
        </properties>
    </profile>
    <profile>
        <id>contract-ci</id>
        <properties>
            <contract.environment>ci</contract.environment>
        </properties>
    </profile>
</profiles>
~~~

Explicit activation:

~~~bash
./mvnw -Pcontract-local help:active-profiles
./mvnw -Pcontract-ci help:active-profiles
~~~

For contract testing, prefer **explicit `-P` flags** during development and in CI so build logs clearly state which profile was active.

### 4.1. The `activeByDefault` trap

Maven supports:

~~~xml
<activation>
    <activeByDefault>true</activeByDefault>
</activation>
~~~

However, in Maven, an `activeByDefault` profile in a POM is **deactivated whenever another profile in that same POM is activated**, even if the other profile has nothing to do with contract testing. Therefore:

- Never rely on `activeByDefault` as a guaranteed production CI policy.
- If defaults must be used, inspect `help:active-profiles` in every critical build command.
- For releases, pass `-Pcontract-ci` explicitly and fail if required properties are missing.
- Never assume CI activates a profile the same way your IDE did.

### 4.2. Is environment-based activation appropriate?

Maven also supports activation via system properties or environment variables, such as `env.CI`. However, a `CI` variable might be set to `true`, `1`, or exist as an empty string depending on the provider.

For clarity and debuggability, the running examples choose:

~~~bash
./mvnw -Pcontract-local clean verify
./mvnw -B -ntp -Pcontract-ci clean verify
~~~

Do not activate both `contract-local` and `contract-ci` in the same build unless precedence is explicitly designed. If both define the same property, merging can point stub resolution to the wrong source.

## 5. Choosing what belongs in shared configuration

Whether running locally or in CI, Inventory Service's contract remains `GET /api/inventory/SKU-100` with the agreed status and body. Elements that must not vary arbitrarily by profile:

- Scanned contract sources.
- `testFramework`: JUnit 5 if the project uses JUnit Jupiter.
- `testMode`: `MOCKMVC` for Spring MVC or `WEBTESTCLIENT` for WebFlux.
- `baseClassForTests` or base class mappings.
- Contract names and contents.
- DTO/schema definitions and protected matchers.
- Rules requiring generated producer tests to execute in quality gates.

Example Groovy contract:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_inventory_available')
    request {
        method GET()
        urlPath('/api/inventory/SKU-100')
        headers {
            accept(applicationJson())
        }
    }
    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-100',
            available: true,
            quantity: 8
        )
    }
}
~~~

If CI returns `quantity: 0` instead of `8` due to different test fixtures, fix **producer test data preparation** to satisfy the contract rather than weakening the contract to make CI green.

## 6. Producer POM example: keep the Verifier plugin in shared configuration

The producer is responsible for generating/verifying contracts and building the stub artifact. An abbreviated `pom.xml` snippet:

~~~xml
<properties>
    <!-- Replace with a version compatible with the project's Spring Boot/Spring Cloud -->
    <spring-cloud-contract.version>VERSION_APPROVED_BY_PROJECT</spring-cloud-contract.version>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-contract-maven-plugin</artifactId>
            <version>${spring-cloud-contract.version}</version>
            <extensions>true</extensions>
            <configuration>
                <testFramework>JUNIT5</testFramework>
                <testMode>MOCKMVC</testMode>
                <baseClassForTests>com.example.inventory.contract.ContractVerifierBase</baseClassForTests>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

**This is a POM snippet, not a complete POM file.** You need Spring Boot/test dependencies, compatible versions, and a real `ContractVerifierBase` configuring `RestAssuredMockMvc` or the matching test context. `VERSION_APPROVED_BY_PROJECT` is a placeholder to replace before building.

Per Spring Cloud Contract Maven Plugin documentation, `generateTests` binds to `generate-test-sources` in standard plugin setups; the plugin also provides `convert`, `generateStubs`, and `generateTests` goals. If lifecycle configuration differs or the plugin is inactive, verify that generated tests and stub artifacts are actually produced.

### 6.1. Why not place the entire plugin only inside a CI profile?

If only CI runs Contract Verifier, local developers miss breaking changes until pushing code. Furthermore, lacking generated tests in local builds misleads developers about test coverage. Keep **contract generation and verification logic shared**, and reserve profiles strictly for genuine environment differences.

If local iteration needs speed, use a targeted test command or goal, **never treating a quick local shortcut as equivalent to a full `clean verify`**.

### 6.2. What if the producer uses WebFlux?

In a WebFlux producer:

~~~xml
<configuration>
    <testFramework>JUNIT5</testFramework>
    <testMode>WEBTESTCLIENT</testMode>
    <baseClassForTests>com.example.inventory.contract.ReactiveContractBase</baseClassForTests>
</configuration>
~~~

Choose `MOCKMVC`/`WEBTESTCLIENT` based on the HTTP boundary technology, **not local vs CI**. Generated tests must run in both environments if both claim the same quality gate.

### 6.3. Inspect real test outcomes

After building the producer, verify:

- Generated test classes/methods appear matching contracts.
- Tests are actually executed by the test runner (Surefire/Failsafe per project).
- Contract Verifier is not skipped.
- Deliberately changing a response field/status incompatibly makes generated tests fail.
- `-stubs.jar` contains valid mappings, not just a main JAR.

`BUILD SUCCESS` without executed generated tests does not prove the producer satisfies its contracts.

## 7. From Maven profile to Stub Runner: a "bridge" is required

A common mistake:

~~~xml
<profile>
    <id>contract-ci</id>
    <properties>
        <stubrunner.mode>REMOTE</stubrunner.mode>
    </properties>
</profile>
~~~

Followed by writing a consumer test:

~~~java
@AutoConfigureStubRunner
class CheckoutContractTest {
    // ...
}
~~~

expecting Stub Runner to pick up `REMOTE` automatically. **No automatic link exists because `stubrunner.mode` is a custom project property**, not a built-in Spring Cloud Contract Stub Runner property. Maven knows it, yet the JVM running Spring tests does not necessarily see it.

There are two explicit bridges:

1. **Surefire/Failsafe `systemPropertyVariables`**: pass Maven profile values as Java system properties read by Spring/Stub Runner.
2. **Spring test configuration**: use `application-test.yml` paired with Spring profiles/env variables, ensuring the Maven profile activates or forwards the right environment.

This lesson illustrates option 1 to make the data flow explicit. Not every project has to pick option 1, but you must prove properties reach the test runtime.

### 7.1. Distinguishing Maven properties from Java system properties

| Location | Example | Who reads it? |
| --- | --- | --- |
| POM profile property | `stubrunner.mode=LOCAL` | Maven model/plugin interpolation |
| Surefire `systemPropertyVariables` | `spring.cloud.contract.stubrunner.stubsMode=LOCAL` | JVM running JUnit/Spring tests |
| Spring configuration property | `spring.cloud.contract.stubrunner.stubs-mode=LOCAL` | Spring binder inside the test application context |
| Environment variable | `SPRING_CLOUD_CONTRACT_STUBRUNNER_STUBS_MODE=LOCAL` | Spring Environment when property binding applies |

In Spring Cloud Contract documentation, standard camelCase system property names are `spring.cloud.contract.stubrunner.stubsMode`, `repositoryRoot`, and `ids`; in Spring YAML, kebab-case `stubs-mode` and `repository-root` work via relaxed binding. Do not mix them up when inspecting logs without knowing how binding resolves them.

## 8. Consumer POM: two profiles sharing one test configuration

Suppose Checkout needs stub:

~~~text
com.example:inventory-producer:1.2.3:stubs
~~~

Pin **an explicit version** so CI stays reproducible. The POM snippet below shows only relevant sections; integrate it into a real project and pin plugin versions via parent/`pluginManagement`:

~~~xml
<properties>
    <inventory.stub.version>1.2.3</inventory.stub.version>
    <inventory.stub.id>com.example:inventory-producer:${inventory.stub.version}:stubs</inventory.stub.id>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <configuration>
                <systemPropertyVariables>
                    <spring.cloud.contract.stubrunner.ids>${inventory.stub.id}</spring.cloud.contract.stubrunner.ids>
                    <spring.cloud.contract.stubrunner.stubsMode>${stubrunner.mode}</spring.cloud.contract.stubrunner.stubsMode>
                    <spring.cloud.contract.stubrunner.repositoryRoot>${stubrunner.repository.root}</spring.cloud.contract.stubrunner.repositoryRoot>
                </systemPropertyVariables>
            </configuration>
        </plugin>
    </plugins>
</build>

<profiles>
    <profile>
        <id>contract-local</id>
        <properties>
            <stubrunner.mode>LOCAL</stubrunner.mode>
            <stubrunner.repository.root></stubrunner.repository.root>
        </properties>
    </profile>

    <profile>
        <id>contract-ci</id>
        <properties>
            <stubrunner.mode>REMOTE</stubrunner.mode>
            <stubrunner.repository.root>https://repo.example.test/repository/maven-releases/</stubrunner.repository.root>
        </properties>
    </profile>
</profiles>
~~~

Understand each piece:

- `inventory.stub.version` is shared so contracts never diverge accidentally between local and CI.
- `inventory.stub.id` is passed to Stub Runner via system property `spring.cloud.contract.stubrunner.ids`.
- `stubrunner.mode` is a Maven property **assigned by the profile**, then forwarded by Surefire as `spring.cloud.contract.stubrunner.stubsMode`.
- `stubrunner.repository.root` is empty in `LOCAL` (resolver uses local Maven repo) and holds the artifact repository URL in `CI`.
- `repo.example.test` is only an example URL; replace it with your organization's real artifact repository.
- Never embed literal credentials in the POM. Handle auth via CI secrets/settings/properties as verified in your project.

**Important condition:** `-Pcontract-local` or `-Pcontract-ci` must be active before Maven interpolates `stubrunner.mode` and `stubrunner.repository.root`. Otherwise properties remain undefined and tests receive unresolved literal strings. You can set clear defaults and fail closed via Maven Enforcer or CI checks if builds must work without `-P`.

### 8.1. Which dependency does the consumer need?

The consumer needs the Spring Cloud Contract Stub Runner test dependency, for example:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-contract-stub-runner</artifactId>
    <scope>test</scope>
</dependency>
~~~

Its version can be managed by a compatible Spring Cloud Contract BOM. `@AutoConfigureStubRunner` requires matching Spring/JUnit test integration.

**It is not mandatory** to add the stub JAR as a `test` dependency in the consumer when using `LOCAL` or `REMOTE`, because Stub Runner resolves the artifact itself from `ids`. By contrast, `CLASSPATH` normally requires the stub JAR on the test runtime classpath. This is a difference in resolution mechanism, not three equivalent dependency-graph setups.

### 8.2. Consumer test reading system properties

~~~java
@SpringBootTest
@AutoConfigureStubRunner
class CheckoutContractTest {

    @StubRunnerPort("com.example:inventory-producer")
    int inventoryPort;

    @Test
    void checkoutShouldUseInventoryStub() {
        InventoryClient inventory = new InventoryClient(
            "http://localhost:" + inventoryPort
        );
        CheckoutService checkout = new CheckoutService(inventory);

        assertThat(checkout.canPlaceOrder("SKU-100", 3))
            .isTrue();
    }
}
~~~

This is an **illustrative test skeleton**; you need proper imports, test dependencies, and application classes. Most importantly, tests must exercise the real `InventoryClient`/`CheckoutService`, not just ping WireMock to prove the stub started.

Avoid hardcoding `stubsMode = StubsMode.LOCAL` or `ids = "..."` directly on the annotation when external profiles are meant to control them. When multiple configuration sources exist, check precedence and actual property binding for your Spring Cloud Contract version.

### 8.3. When using Failsafe instead of Surefire

Maven Surefire usually runs unit tests in `test`; Failsafe usually runs `*IT` integration tests in `integration-test`/`verify`. If `CheckoutContractIT` runs via Failsafe while you **only configured `systemPropertyVariables` on Surefire**, properties may **never reach the Failsafe JVM**.

Pass the same properties to Failsafe if integration tests run there:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <executions>
        <execution>
            <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <systemPropertyVariables>
            <spring.cloud.contract.stubrunner.ids>${inventory.stub.id}</spring.cloud.contract.stubrunner.ids>
            <spring.cloud.contract.stubrunner.stubsMode>${stubrunner.mode}</spring.cloud.contract.stubrunner.stubsMode>
            <spring.cloud.contract.stubrunner.repositoryRoot>${stubrunner.repository.root}</spring.cloud.contract.stubrunner.repositoryRoot>
        </systemPropertyVariables>
    </configuration>
</plugin>
~~~

Use a compatible Failsafe version and ensure integration tests match naming conventions. Running `mvn test` **does not invoke Failsafe `verify`**; run `mvn verify` for Failsafe workflows.

### 8.4. Verifying property propagation with an assertion

In consumer test setup, you can print **non-sensitive values** and fail if the mode mismatches:

~~~java
String mode = System.getProperty(
    "spring.cloud.contract.stubrunner.stubsMode"
);

assertThat(mode).isEqualTo("REMOTE"); // In contract-ci job
~~~

This is an assertion intended strictly for a **CI job**; hardcoding it in a test shared by both local and CI breaks local runs unnecessarily. Prefer profile-aware logging/assertions or a configuration test expecting the mode passed via a dedicated property.

**Never print `repositoryRoot` if its URL embeds credentials**, and never log usernames, passwords, or tokens; log only sanitized hosts, modes, or artifact versions when debugging.


## 9. Local and CI commands: one contract, two stub sources

Once the POM and profiles are in place, developers can run:

~~~bash
# In producer: generate tests, verify contracts, and install stubs locally
./mvnw -B clean install

# In consumer: fetch stubs from local Maven repository
./mvnw -Pcontract-local clean verify
~~~

Running `install` on the producer only produces `-stubs.jar` if the Spring Cloud Contract Maven plugin is configured and required goals/phases actually run. If Maven succeeds yet `inventory-producer-1.2.3-stubs.jar` is missing, inspect producer generation and packaging configuration.

CI normally follows this sequence:

~~~bash
# Producer CI: deploy only if verify passes and pipeline permits publishing
./mvnw -B -ntp clean deploy

# Consumer CI: use artifact published to shared repository
./mvnw -B -ntp -Pcontract-ci clean verify
~~~

`mvn deploy` executes preceding Maven lifecycle phases, including `verify`, unless disabled by skip flags or other settings. **Never use the same profile ID to implicitly trigger artifact publishing across all job types**: `deploy` should be an explicitly authorized pipeline step after quality gates, backed by credentials and repository policy.
For example, the producer uses the shared Verifier config from Section 6 and does not need `-Pcontract-ci`; if the producer has its own CI profile, declare and activate it in the **producer POM**, independent of `contract-ci` in the consumer POM. `mvn deploy` executes preceding Maven lifecycle phases, including `verify`, unless disabled by skip flags or other settings. **Never use the same profile ID to implicitly trigger artifact publishing across all job types**: `deploy` should be an explicitly authorized pipeline step after quality gates, backed by credentials and repository policy.

### 9.1. What if a developer wants faster feedback?

You can run a single test or specific module while iterating on code:

~~~bash
./mvnw -Pcontract-local -Dtest=CheckoutConsumerContractTest test
~~~

Make clear this is **quick feedback**, not equivalent to a full `clean verify` pipeline. When tests live in Failsafe per `*IT` naming, invoke Failsafe's goal/phase rather than forcing Surefire.

### 9.2. Never use profiles to alter contracts

An anti-pattern:

~~~text
contract-local  → response.quantity = 8
contract-ci     → response.quantity = 0
~~~

If this is the same use case and same consumer contract, diverging here destroys verification value. Instead, use **reproducible fixtures** in the producer base class, isolate test data, or define two clearly named scenarios (in-stock and out-of-stock) if the consumer needs both.

## 10. Installing/publishing artifacts: where do `LOCAL` and `REMOTE` differ?

| Step | Local development | CI/release |
| --- | --- | --- |
| Contract source | Agreed Groovy/YAML | Same source, exact commit/revision |
| Producer tests | Generated tests on developer machine | Generated tests on clean runner |
| Stub artifact | `...-stubs.jar` installed into `~/.m2/repository` | `...-stubs.jar` published to shared repository |
| Consumer mode | `LOCAL` | `REMOTE` |
| Stub version used | Explicit coordinates installed locally | Explicit coordinates published remotely |
| WireMock port | Dynamic or test-isolated | Dynamic; avoids port collisions across runners |
| Evidence to retain | Test reports and artifact version | Test reports, artifact provenance, CI run ID |

### 10.1. Why avoid `+` in CI?

Stub Runner supports Ivy notation:

~~~text
groupId:artifactId:version:classifier:port
~~~

Example:

~~~text
com.example:inventory-producer:1.2.3:stubs
~~~

If you omit the version, the resolver typically uses `+` to pick the latest. When CI fetches "latest," a newly published producer build can break an unchanged Checkout commit **without any consumer code change**. Pinning versions in profiles/dependency management and upgrading deliberately preserves reproducibility and diagnosability.

### 10.2. Snapshots can change contents

A `1.2.4-SNAPSHOT` artifact can be replaced by another build under the exact same version. In `LOCAL`, a developer can also reinstall new bytes into `.m2`. When investigating compatibility, record snapshot build metadata or checksums, not only short coordinates.

For releases, treat `1.2.3` as immutable. Never publish two stub JARs with different contents under the same release version and expect reproducible CI.

### 10.3. `REMOTE` can still use caching

`REMOTE` mode does not mean "re-download fresh bytes over the network every single time." Maven Resolver/Stub Runner can leverage local caches and metadata update policies. If an artifact is overwritten or uses dynamic versions, caches can make one agent see old mappings while another sees new ones. The durable fix is **version pinning + immutable artifacts**, not wiping caches blindly.

## 11. Repositories and credentials: put them in the right place

A frequent question: should we embed username/password inside `pom.xml` for the CI profile?

**No.** POMs live in Git; even in private repositories, literal credentials can leak through clones, published artifacts, or build logs.

### 11.1. Maven `settings.xml` for artifact resolution/deployment

Maven supports `settings.xml` with `<servers>`, `<mirrors>`, `<profiles>`, and `<activeProfiles>`. An **abbreviated example containing no real credentials**:

~~~xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <servers>
        <server>
            <id>artifact-releases</id>
            <username>${env.CI_MAVEN_USER}</username>
            <password>${env.CI_MAVEN_PASSWORD}</password>
        </server>
    </servers>
</settings>
~~~

In the producer `pom.xml`, when using `distributionManagement`:

~~~xml
<distributionManagement>
    <repository>
        <id>artifact-releases</id>
        <url>https://repo.example.test/repository/maven-releases/</url>
    </repository>
</distributionManagement>
~~~

**The `<id>` must match** so the Maven deploy plugin finds the right server entry. In CI, supply a generated settings file or secret injection without committing real values. Never pass credentials on the command line via `-Dpassword=...`, which exposes them in process lists and logs.

### 11.2. Watch out: Maven Resolver credentials vs Stub Runner credentials

Inside the consumer test JVM, Stub Runner can use its own resolver/configuration and supports `spring.cloud.contract.stubrunner.username`, `password`, and `repositoryRoot`. Never assume Maven deploy credentials are **automatically** read by every Stub Runner configuration path.

If the repository requires authentication, verify which mechanism your Spring Cloud Contract version supports. You may inject:

~~~text
SPRING_CLOUD_CONTRACT_STUBRUNNER_USERNAME
SPRING_CLOUD_CONTRACT_STUBRUNNER_PASSWORD
~~~

into the environment of the **process running consumer tests** if your project's Spring property binding picks up these variables. Alternatively, configure resolver/server IDs per your version's docs. Never log secret values.

Distinguish:

- Maven `settings.xml`: configures Maven artifact resolution/publishing.
- Stub Runner `repositoryRoot`: URL for fetching stub JARs at test runtime.
- `ids`: coordinates of the **stub artifact**.
- `@StubRunnerPort`: port of the **WireMock server** once the artifact has loaded.

### 11.3. Never make the local profile require CI secrets

The `contract-local` profile should work with locally installed artifacts without needing CI repository tokens. If the local profile still tries to hit a remote URL or CI secret variables, check for overrides from parent POMs, Maven settings, environment variables, or Spring annotations.

## 12. External contracts on the producer: `contractsMode` is not `stubsMode`

Some projects store contracts in a **shared repository** instead of the producer's `src/test/resources/contracts`. In that case, the Spring Cloud Contract Maven plugin can use:

- `contractDependency`: artifact containing contract definitions.
- `contractsMode`: how to resolve the contract artifact (e.g., `LOCAL` or `REMOTE`).
- `contractsRepositoryUrl`: URL hosting the contract artifact if needed.
- `contractsPath`: sub-path inside the JAR holding contracts.

Configuration skeleton:

~~~xml
<configuration>
    <contractsMode>${producer.contracts.mode}</contractsMode>
    <contractsRepositoryUrl>${producer.contracts.repository}</contractsRepositoryUrl>
    <contractDependency>
        <groupId>com.example</groupId>
        <artifactId>shared-inventory-contracts</artifactId>
        <version>1.2.3</version>
    </contractDependency>
    <contractsPath>/</contractsPath>
    <testFramework>JUNIT5</testFramework>
    <testMode>MOCKMVC</testMode>
    <baseClassForTests>com.example.inventory.contract.ContractVerifierBase</baseClassForTests>
</configuration>
~~~

The local profile can set `producer.contracts.mode=LOCAL`; CI can set `REMOTE` plus the repository URL. **Apply this pattern only when the producer truly fetches contracts from an external artifact.** If contracts live in producer sources, do not add an external dependency just to use Maven profiles.

Crucially, never confuse:

| Property | Owner | Artifact fetched |
| --- | --- | --- |
| Verifier `contractsMode` | **Producer** Maven plugin | JAR containing Groovy/YAML contracts |
| Stub Runner `stubsMode` | **Consumer** test runtime | JAR containing WireMock/message stubs |

A producer can use local contracts while consumers use remote stubs, or vice versa. Those two choices are independent.

### 12.1. Consistent contract source in CI

If the producer loads contracts from an external artifact, pin an **explicit contract artifact version** or commit/revision. Never let `contractsMode=REMOTE` with a dynamic version generate different tests across two runs. When the contract repo updates, let CI fail cleanly if the producer has not met the change.

## 13. Preventing false-green CI caused by skipped tests

Maven has multiple ways to skip tests; they are **not equivalent**:

| Setting/command | Primary impact | Risk to contracts |
| --- | --- | --- |
| `-DskipTests` | Usually skips running Surefire tests while still compiling tests | Generated producer tests may not execute |
| `-Dmaven.test.skip=true` | Skips test compilation/execution; some plugins check this flag too | Contract Verifier generation/execution may be skipped |
| `-Dspring.cloud.contract.verifier.skip=true` | Requests skipping Spring Cloud Contract Verifier plugin work | Tests/stubs may not be generated |
| `-DskipITs` | Skips integration tests managed by Failsafe | Consumer `*IT` tests may be skipped |
| Surefire `failOnNoTests=false` | Allows builds with zero tests in certain cases | CI may stay green despite missing expected tests |
| Stub Runner `failOnNoStubs=false` | May not fail when zero stubs are found | Consumer tests may run without needed dependencies |

Subtlety: different Maven plugin versions handle skip flags at different phases. Per Spring Cloud Contract plugin source behavior, `generateTests` inspects `spring.cloud.contract.verifier.skip` and `maven.test.skip`. So **never guess** that `-DskipTests` always behaves identically to `-Dmaven.test.skip`.

### 13.1. Why checking `BUILD SUCCESS` alone is not enough

A pipeline might output:

~~~text
[INFO] BUILD SUCCESS
Tests run: 0
~~~

or run a few unrelated unit tests while **skipping generated contract tests**. Concluding "producer is compatible with consumer" in that state has zero basis.

Verify explicitly:

1. Contracts exist at the expected source.
2. Plugin `generateTests` and `generateStubs` executed.
3. Generated test sources were actually generated.
4. Test runners discovered and **executed** generated test classes/methods.
5. CI collected test report evidence.
6. The stubs JAR with right classifier/mappings was attached.
7. Artifact publishing runs only after all required checks pass.

### 13.2. `failIfNoTests` does not replace contract count checks

You can enable `failIfNoTests` on Surefire/Failsafe, yet if a handful of normal unit tests still run, the build can pass with **zero generated contract tests**.

Therefore, verify the **specific group of generated tests** or check contract/test-class counts per project setup. Generated class names depend on package/folder layout, so do not hardcode one universal pattern across all projects without inspecting build outputs.

### 13.3. Prefer fail-closed behavior in CI

A CI job responsible for producer verification must fail if:

- Mandatory contracts are not found.
- Generated tests did not execute.
- Contract assertions fail.
- Expected `-stubs.jar` is not created.
- Repository deployment fails.
- Published artifact version cannot be verified.

A consumer contract test job must fail if:

- Required stub artifact cannot be resolved.
- WireMock fails to load expected mappings.
- Consumer client fails to reach the stub.
- Consumer behavior/assertions fail.
- Wrong profile is active or required properties are missing.

## 14. Inspecting effective configuration with the Maven Help Plugin

When suspecting a Maven profile was not activated, never guess from folder names or environment variables.

### 14.1. Which profiles are active?

~~~bash
./mvnw -Pcontract-local help:active-profiles
./mvnw -Pcontract-ci help:active-profiles
~~~

These commands display active profiles for the Maven session. If the project uses a parent POM and `settings.xml`, output may list other profiles alongside the two contract profiles.

### 14.2. What does the merged POM look like?

~~~bash
./mvnw -Pcontract-ci help:effective-pom
~~~

Output can be very long; search for `maven-surefire-plugin`, `maven-failsafe-plugin`, `spring-cloud-contract-maven-plugin`, and `stubrunner` properties. In sensitive environments, **do not publish the entire effective POM to public logs**, because merged configs may expose internal endpoints or sensitive data from other sources.

### 14.3. What value does a specific property have?

~~~bash
./mvnw -q -Pcontract-ci help:evaluate \
  -Dexpression=stubrunner.mode \
  -DforceStdout
~~~

Expected output: `REMOTE`. Likewise, locally:

~~~bash
./mvnw -q -Pcontract-local help:evaluate \
  -Dexpression=stubrunner.mode \
  -DforceStdout
~~~

Expected output: `LOCAL`.

Maven `help:evaluate` checks the **Maven property**. It does not prove Surefire forwarded the value into the Spring test process; to verify that next step, inspect system properties in JUnit test setup or Spring `Environment` for **non-sensitive** values.

### 14.4. Checking the right Spring profile

Passing `-Pcontract-ci` **does not automatically enable** `spring.profiles.active=ci` in Spring Boot. If the application depends on `application-ci.yml`, activate the Spring profile via its own mechanism, such as:

~~~bash
./mvnw -Pcontract-ci -Dspring.profiles.active=ci verify
~~~

Never assume `application-ci.yml` loads simply because a Maven profile named `contract-ci` was activated.

## 15. Automatic profile activation: when should you use it?

Maven allows:

~~~xml
<profile>
    <id>contract-ci</id>
    <activation>
        <property>
            <name>env.CI</name>
            <value>true</value>
        </property>
    </activation>
    <properties>
        <stubrunner.mode>REMOTE</stubrunner.mode>
    </properties>
</profile>
~~~

Benefit: many CI providers set `CI=true`, letting the profile activate automatically.

Remember, however:

- The `CI` variable may be set to something other than `true`, depending on environment.
- Developers might run inside an IDE/container with `CI=true` unexpectedly set.
- `activeByDefault` profiles in the POM can be deactivated when another profile triggers.
- Parent POM or settings profiles can complicate configuration merge ordering.
- If both local and CI profiles become active simultaneously, final property values may surprise you.

**Recommendation for quality gates:** even with automatic activation, CI should explicitly specify the intended profile in the command and verify `help:active-profiles`/effective configuration in a prep step.

## 16. Comparing two configuration separation strategies

### 16.1. Profiles driving system properties

~~~text
Maven -Pcontract-local / -Pcontract-ci
    → Maven properties
    → Surefire / Failsafe systemPropertyVariables
    → Java system properties
    → Spring Environment
    → Stub Runner
~~~

Pros:

- Configuration propagation path is clear and traceable.
- All local/CI switches live centrally in the POM.
- Identical JUnit test runs in both environments.

Cons:

- If another test runner replaces Surefire/Failsafe, a matching bridge is needed.
- Property precedence can get tricky if annotations override properties.
- POM XML grows verbose if many properties are added.

### 16.2. Separate Spring profiles and environment configurations

An alternative: keep Maven profiles strictly for build/repository policies, while Spring test configuration defines:

~~~yaml
# application-local.yml, illustrative
spring:
  cloud:
    contract:
      stubrunner:
        stubs-mode: LOCAL
        ids:
          - "com.example:inventory-producer:1.2.3:stubs"
~~~

~~~yaml
# application-ci.yml, illustrative
spring:
  cloud:
    contract:
      stubrunner:
        stubs-mode: REMOTE
        repository-root: https://repo.example.test/repository/maven-releases/
        ids:
          - "com.example:inventory-producer:1.2.3:stubs"
~~~

Pros: fits the Spring configuration ecosystem cleanly and feels natural in Boot apps/tests. Cons: requires ensuring `spring.profiles.active` or `@ActiveProfiles` is set properly; matching Maven and Spring profile names **creates no automatic link**.

Both strategies are valid when verified. **Avoid setting conflicting values in multiple places simultaneously.** If combining both, document the source of truth and precedence clearly.

### 16.3. Is Maven resource filtering needed?

Maven can filter `application-*.yml` using POM placeholders, yet this easily breaks because Spring also uses `${...}` placeholders and Maven can unintentionally substitute the wrong strings. When build-time substitution is not strictly required, prefer **runtime environment properties** or the Surefire bridge. If you must filter resources, define clear delimiters/escaping and inspect generated resources in build output.

## 17. When local passes but CI fails: diagnostic table

| Symptom | Likely cause | Resolution path |
| --- | --- | --- |
| Local Stub Runner works, CI cannot find stub | Local `.m2` has stub, CI `REMOTE` lacks artifact | Check published artifact, coordinates, and `repositoryRoot` |
| CI gets `401/403` fetching artifact | Missing repository credentials or permissions | Check CI secrets, server/repository config |
| CI uses `CLASSPATH` despite `contract-ci` | Maven property didn't reach JVM; annotation override | Inspect Surefire/Failsafe bridge and Spring `Environment` |
| CI receives stale response body | Used `+`, snapshot/cache, or overwritten artifact | Pin version and compare checksums/mappings |
| Local `mvn test` passes, CI `mvn verify` fails | Failsafe integration tests only run at `verify` | Run proper lifecycle, check test naming |
| CI build green yet contracts unverified | Skip flags, generated tests didn't run | Inspect test reports and plugin goals |
| Generated tests fail in CI but pass locally | Different fixtures/timezone/database/concurrency | Isolate test data and deterministic setup |
| WireMock returns 404 while producer has route | Consumer request fails stub mapping match | Compare method/path/headers and resolved artifact |
| Right Maven profile, wrong Spring profile | `-P` does not activate `spring.profiles.active` | Activate Spring profile separately |
| WireMock port conflicts in CI | Fixed port shared across concurrent jobs | Let Stub Runner assign dynamic ports and inject via annotation/API |
| Resolution error after version bump | Producer has not published artifact yet | Run publish gate, check repository metadata |
| CI misses tests despite contract sources | Wrong test runner pattern/source directory | Check generated test path and Surefire/Failsafe patterns |

### 17.1. Ordered investigation sequence

1. Confirm `-Pcontract-ci` is actually present in the CI command.
2. Run `help:active-profiles` or inspect Maven logs.
3. Verify `stubrunner.mode` and `inventory.stub.version` interpolated properly.
4. Check the Java system properties received by JUnit tests.
5. Confirm Stub Runner uses `REMOTE` and the right `repositoryRoot`.
6. Confirm the artifact exists with the right classifier and expected mappings.
7. Confirm the consumer calls the right WireMock URL/port.
8. Compare responses against the contract and client behavior assertions.
9. If producer verification fails, inspect fixtures/test mode/generated assertions instead of blaming the repository by default.
10. If artifact resolution fails, do not hastily alter business contracts.

## 18. Hands-on exercise: migrating Checkout from local `.m2` to a CI repository

### 18.1. Context

Inventory Service (producer) exposes:

~~~http
GET /api/inventory/SKU-100 HTTP/1.1
Accept: application/json
~~~

Response:

~~~json
{
  "sku": "SKU-100",
  "available": true,
  "quantity": 8
}
~~~

Checkout Service (consumer) must ensure an order requesting `3` items is accepted when quantity is `8`, and an order requesting `9` items is rejected.

Producer stub coordinates:

~~~text
com.example:inventory-producer:1.2.3:stubs
~~~

### 18.2. Task A — Create two profiles

In the consumer POM, define:

- `contract-local`: `stubrunner.mode=LOCAL`.
- `contract-ci`: `stubrunner.mode=REMOTE`, with `stubrunner.repository.root`.
- Shared `inventory.stub.version=1.2.3`.

Use the Surefire/Failsafe bridge so the test JVM receives `spring.cloud.contract.stubrunner.ids`, `stubsMode`, and `repositoryRoot`.

**Question:** Why does merely defining the Maven property `stubrunner.mode` not guarantee Stub Runner uses that mode?

### 18.3. Task B — Run locally

In the producer, ensure generated tests pass and the stub JAR installs locally:

~~~bash
./mvnw -B clean install
~~~

In the consumer:

~~~bash
./mvnw -Pcontract-local clean verify
~~~

Verify mode, artifact version, WireMock port, and Checkout assertions.

### 18.4. Task C — Simulate CI run

Assume the shared repository holds published version `1.2.3`. Run:

~~~bash
./mvnw -B -ntp -Pcontract-ci clean verify
~~~

Never put usernames/passwords on the command line. If the repository requires auth, use CI secrets and Maven/Stub Runner credentials per project mechanism.

Record:

- `help:active-profiles` showing `contract-ci`.
- Expected `stubrunner.mode` value `REMOTE`.
- Actual resolved stub coordinates/version.
- Results of success and out-of-stock consumer tests.
- Test reports, not just `BUILD SUCCESS`.

### 18.5. Task D — Deliberately introduce two failures

**Failure 1:** Change `inventory.stub.version` to `9.9.9` (unpublished). Expect consumer CI to **fail at artifact resolution**, not because Checkout parses JSON incorrectly.

**Failure 2:** Restore the right version, then edit `InventoryClient` to call `/api/inventories/SKU-100` (wrong path). Expect Stub Runner to start while the request misses the WireMock mapping; the consumer test must fail.

These two failures train distinguishing **repository configuration errors** from **contract mismatches**.

### 18.6. Task E — Prove generated tests actually run

In the producer, confirm the build produces generated tests and matching test reports. Try a contract-breaking change, such as returning `quantity` as String `"8"` instead of number `8`. Generated tests must catch the mismatch when the contract enforces the type.

Revert the code before finishing the exercise. Never publish stubs from a build whose producer verification failed.

### 18.7. Task F — Explain profile choices

Write a short answer covering:

1. Why is `LOCAL` convenient for development yet prone to drift across machines?
2. Why does `REMOTE` fit multi-repository CI?
3. Why shouldn't `activeByDefault` be relied upon to guarantee CI enables a profile?
4. Why is `-DskipTests` disallowed in contract verification jobs?
5. When consumer `*IT` runs via Failsafe, where must the property bridge be configured?
6. Why does pinning stub versions help reproduce failures?
7. Where should all credentials be managed?
8. In what situations should a dedicated Spring profile be preferred over driving everything through Maven?

## 19. Pre-merge/pre-release checklist

- [ ] `contract-local` and `contract-ci` have clear purposes without pointless duplication.
- [ ] CI commands explicitly enable `-Pcontract-ci`.
- [ ] Maven profiles and Spring profiles are not confused.
- [ ] The test runner JVM receives the exact Stub Runner mode, IDs, and `repositoryRoot`.
- [ ] Surefire or Failsafe is configured for the exact test classes executed.
- [ ] Producer Verifier plugin, test mode, and base class sit in shared, consistent configuration.
- [ ] Generated producer tests are actually generated and executed.
- [ ] Neither `spring.cloud.contract.verifier.skip` nor skip-test flags are set in mandatory verify jobs.
- [ ] Zero green builds with 0 generated contract tests are marked verified.
- [ ] Stub JAR has the exact group/artifact/version/classifier/mappings.
- [ ] `LOCAL`: artifacts are completely installed in the local Maven repository.
- [ ] `REMOTE`: published artifact and version exist in the repository.
- [ ] Stub version is pinned or follows an explicit version strategy.
- [ ] Repository credentials stay out of Git and are supplied via proper secrets/settings.
- [ ] Tests never log tokens, passwords, or URLs with embedded credentials.
- [ ] Real consumer code calls WireMock and asserts business behavior.
- [ ] Critical error paths (404/400/5xx) have matching tests.
- [ ] Ports and test data are isolated when CI runs in parallel.
- [ ] Both local and CI have reproducible commands and expected outcomes documented.
- [ ] Producer publishes stubs only after quality gates pass.
- [ ] Transaction, resilience, and broker delivery tests outside contract scope have clear owners.

## 20. References

- [Maven — Introduction to Build Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html): `-P`, profile activation, `activeByDefault`, and environment properties.
- [Maven — Settings Reference](https://maven.apache.org/settings.html): `settings.xml`, servers, profiles, repository credentials, and mirrors.
- [Maven Surefire — Using System Properties](https://maven.apache.org/surefire/maven-surefire-plugin/examples/system-properties.html): `systemPropertyVariables` and passing Maven properties to the test JVM.
- [Maven Failsafe — Introduction](https://maven.apache.org/surefire/maven-failsafe-plugin/): `integration-test`/`verify` lifecycle for `*IT`.
- [Spring Cloud Contract — Maven Project](https://docs.spring.io/spring-cloud-contract/reference/maven-project.html): Verifier plugin config, `generateTests`, test mode/base class, and external contracts.
- [Spring Cloud Contract — Maven Plugin Goals](https://docs.spring.io/spring-cloud-contract/docs/current/spring-cloud-contract-maven-plugin/plugin-info.html): `generateTests`, `generateStubs`, `convert`, and other goals.
- [Spring Cloud Contract — Stub Runner Common Properties](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-common.html): `ids`, `stubsMode`, `repositoryRoot`, classifier, and port.
- [Spring Cloud Contract — Step-by-step CDC](https://docs.spring.io/spring-cloud-contract/reference/getting-started/cdc.html): producer verification, stub publishing, and consumer testing.

**Key takeaway:** Maven profiles separate **how builds run and where stubs are fetched** between local and CI, yet profile names alone do not configure Spring Cloud Contract. Keep Verifier and core contract rules shared, use `contract-local`/`contract-ci` to choose artifact sources, bridge values to the test JVM via Surefire/Failsafe or Spring configuration, pin versions, and keep secrets out of POMs. CI may declare contract testing successful only when **generated producer tests and consumer behavior tests actually execute**, stubs carry the exact version, and release gates pass.
