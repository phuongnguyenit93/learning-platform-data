# The package, install, and deploy Workflow

## Lesson objective

In **Spring Cloud Contract**, the producer defines HTTP or messaging behavior using **Groovy DSL** or **YAML DSL**. **Contract Verifier** uses these contracts to generate producer-side tests; HTTP contracts can also be converted into stub mappings and packaged into a **stub JAR** for consumers to use via **Stub Runner**. For this workflow to serve as reliable compatibility evidence in CI, writing valid contracts is not enough: you must understand **which phases Maven executes, which artifacts it produces, and where those artifacts are published**.

This lesson, **"The package, install, and deploy Workflow,"** belongs to the **Maven Integration** chapter and focuses on the build lifecycle from contracts in the producer repository to the stubs that consumers actually download. The most critical distinction is:

- `package`: **builds artifacts inside the build directory**, without yet sharing them with other projects.
- `install`: **installs artifacts into the local Maven repository**, serving builds on that same machine or environment.
- `deploy`: **pushes artifacts to a remote Maven repository** for other applications and CI jobs to fetch.
- `verify`: runs checks bound to the lifecycle to validate build quality; it is **not a form of repository publication**.

After this lesson, you will be able to trace `contract → generated producer test → mappings → -stubs.jar → repository → consumer Stub Runner`, choose the right Maven command for your goal, detect missing classifier artifacts or consumers running stale versions, and design reproducible release gates.

## 1. Which phases does a Maven command execute?

Maven has a **default lifecycle** made up of sequential phases. When you request a phase, Maven generally executes **all preceding phases in the same lifecycle**, along with their bound plugin goals.

~~~mermaid
flowchart LR
    A["validate"] --> B["compile"]
    B --> C["test"]
    C --> D["package"]
    D --> E["verify"]
    E --> F["install"]
    F --> G["deploy"]
~~~

The diagram highlights key phases; in practice there are also `generate-test-sources`, `process-test-resources`, `test-compile`, `integration-test`, and others.

| Command | Goal | What **not** to infer |
| --- | --- | --- |
| `./mvnw package` | Builds artifacts through the `package` phase | Not yet installed to local Maven or deployed remotely |
| `./mvnw verify` | Runs through `package` and checks bound to `verify` | Not yet installed/deployed |
| `./mvnw install` | Runs through `verify` then installs artifacts into local Maven | Not yet pushed to shared repository |
| `./mvnw deploy` | Runs through `install` then pushes artifacts to remote repository | Does not mean every consumer already tested the new version |
| `./mvnw clean verify` | Cleans prior build outputs, then runs lifecycle up to `verify` | `clean` belongs to a separate lifecycle, not a phase of `default` |
| `./mvnw clean deploy` | Cleans build, verifies, and publishes remotely | Run only in environments with publish rights and proper quality gates |

**You do not need to run `package`, `install`, and `deploy` sequentially** on the same build: invoking `deploy` traverses the earlier phases. You may run `clean verify` first to inspect, though note that a subsequent `deploy` runs the lifecycle again; if artifacts change between invocations, the published bytes might differ from what was previously tested.

### Difference between phase and goal

- A **phase** such as `package` or `deploy` is a stage in the lifecycle.
- A **goal** such as `spring-cloud-contract:generateTests` or `spring-cloud-contract:generateStubs` is an operation provided by a Maven plugin.
- **Binding** determines which goal executes in which phase of a build.

For instance, calling a goal manually:

~~~bash
./mvnw org.springframework.cloud:spring-cloud-contract-maven-plugin:generateTests
~~~

differs from running the full lifecycle up to `test` or `verify`. That command only **generates tests**; it does not ensure generated tests compiled, passed, or that the stub artifact was packaged.

## 2. Where does Spring Cloud Contract hook into the Maven lifecycle?

In documented versions of the Spring Cloud Contract Maven plugin, key goals include:

| Plugin goal | Purpose | Commonly documented binding phase |
| --- | --- | --- |
| `generateTests` | Reads Groovy/YAML contracts and generates producer acceptance tests | `generate-test-sources` |
| `convert` | Converts contracts into mappings for HTTP stubs | `process-test-resources` |
| `generateStubs` | Packages converted mappings into a stub JAR | `package` |
| `run` | Runs stubs for testing when appropriately configured | Standalone goal, not equivalent to publishing |

This list summarizes **capabilities and bindings described in plugin documentation**, and does not replace checking your project's exact version and effective POM. Depending on configuration, goals may bind automatically via plugin extensions or require explicit executions.

Understanding the sequence:

~~~mermaid
flowchart TD
    A["src/test/resources/contracts<br/>Groovy / YAML DSL"] --> B["generateTests<br/>generate-test-sources"]
    A --> C["convert<br/>process-test-resources"]
    B --> D["test-compile"]
    D --> E["test / generated producer tests"]
    C --> F["target/stubs<br/>mappings"]
    E --> G{"Tests PASS?"}
    F --> H["generateStubs<br/>package"]
    G -->|No| X["BUILD FAIL"]
    G -->|Yes| H
    H --> I["Producer JAR + attached stubs JAR"]
    I --> J["verify"]
    J --> K["install: local repository"]
    K --> L["deploy: remote repository"]
~~~

**Note:** the diagram shows intended logical flow; Maven executes goals according to **actual phase bindings and plugin execution ordering**. A plugin can be configured to behave differently. Inspect Maven logs and test reports to confirm what actually ran.

### Generated tests are not stubs

- Generated **producer tests** run against **producer code**, catching deviations from the agreement.
- Stub **mappings** return sample responses to consumer calls, letting consumer tests run without the real producer.
- The stub **JAR** is the packaged artifact distributed to repositories; a JSON mapping under `target/stubs` does not guarantee the JAR was built.
- Stub Runner fetches/starts stubs; it does **not** replace producer contract tests.

Passing producer tests and having an available stub JAR are **two separate conditions** to verify.

## 3. Illustrative Maven plugin configuration

A reference configuration in Order Service producer's `pom.xml`:

~~~xml
<properties>
    <!-- Replace with a version compatible with your project's Spring Boot/Spring Cloud -->
    <spring-cloud-contract.version>APPROPRIATE_VERSION</spring-cloud-contract.version>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-contract-maven-plugin</artifactId>
            <version>${spring-cloud-contract.version}</version>
            <extensions>true</extensions>
            <configuration>
                <contractsDirectory>
                    ${project.basedir}/src/test/resources/contracts
                </contractsDirectory>
                <baseClassForTests>
                    com.example.orders.contract.OrderContractBase
                </baseClassForTests>
                <failOnNoContracts>true</failOnNoContracts>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

`APPROPRIATE_VERSION` is a **placeholder**, not a real version to paste verbatim into a POM. The snippet intentionally omits dependency management, test dependencies, packaging, and other application settings.

Real projects also need test dependencies such as:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-contract-verifier</artifactId>
    <scope>test</scope>
</dependency>
~~~

Dependency versions should be managed via a compatible BOM. Projects using WebFlux, MockMvc, JUnit, or messaging tests may need different `testMode`, base test classes, and libraries. **Do not copy a sample POM and assume generated tests will run on every type of producer.**

### Why is the base test class important?

Generated tests need a way to invoke the producer or trigger messages. `OrderContractBase` sets up the Spring test context, HTTP client, fixtures, and event trigger methods.

If `baseClassForTests` points to the wrong package, tests fail to compile; if generated tests are skipped, the build may look green while leaving producer behavior unverified.

### If configuring goal executions explicitly

In some projects, teams declare an `executions` block for `convert`, `generateStubs`, and `generateTests`. Do not **combine both explicit executions and `<extensions>true</extensions>` without checking the effective build**, as goals could be duplicated or run in unintended phases. Pick one clear strategy and verify it in logs.

## 4. Sample source contract producing both tests and stubs

Suppose we have `src/test/resources/contracts/orders/get_paid_order.yml`:

~~~yaml
description: "Fetch a paid order"
name: get_paid_order
request:
  method: GET
  url: /api/orders/ORD-1001
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: ORD-1001
    status: PAID
~~~

From this contract:

1. `generateTests` can generate a producer test sending `GET /api/orders/ORD-1001` and verifying the response.
2. `convert` can generate a WireMock mapping simulating the request and response.
3. `generateStubs` can package the converted mapping into the stub artifact.
4. `install` or `deploy` can place the **attached** stub artifact into a Maven repository.
5. The consumer uses Stub Runner to fetch the artifact by coordinates and test the application.

The contract itself does not specify **`localhost`**, Stub Runner ports, or repository URLs. Those details belong to build/runtime configuration and consumer test settings.

## 5. `package`: where do the outputs live?

Run:

~~~bash
./mvnw clean package
~~~

In a properly configured JAR project, steps typically include:

- Cleaning old `target` outputs (via `clean`).
- Processing sources/resources and compiling code.
- Reading contracts, generating tests and mappings in bound phases.
- Compiling and executing matching unit/contract tests.
- Building the main application artifact.
- Building/attaching the stub JAR with classifier `stubs` when configured.

Illustrative outputs:

~~~text
order-service/
├── src/test/resources/contracts/orders/get_paid_order.yml
└── target/
    ├── generated-test-sources/contracts/    # generated producer tests
    ├── generated-test-resources/contracts/  # resources when needed
    ├── stubs/                               # converted mappings
    ├── surefire-reports/                    # test results
    ├── order-service-1.4.2.jar              # main artifact
    └── order-service-1.4.2-stubs.jar        # attached stubs artifact
~~~

This is an **illustrative layout**. Output names and directories can vary by Spring Cloud Contract version, plugin settings, `finalName`, Maven packaging, and other plugins.

### Two artifacts not to confuse

~~~text
Application / producer artifact:
com.example.orders:order-service:1.4.2

Stub artifact:
com.example.orders:order-service:1.4.2:stubs
~~~

| Component | Role |
| --- | --- |
| `groupId` | Namespace, e.g. `com.example.orders` |
| `artifactId` | Publication name, e.g. `order-service` |
| `version` | Build/artifact version, e.g. `1.4.2` |
| `classifier` | Stub variant, typically `stubs` |

An artifact named `order-service-stubs` as a **separate `artifactId`** is not equivalent to `artifactId` `order-service` with classifier `stubs`. If a team deliberately adopts another convention, it must declare and publish the actual coordinates.

### Inspecting output after `package`

In a shell supporting the `jar` command, inspect the generated artifact contents:

~~~bash
jar tf target/order-service-1.4.2-stubs.jar
~~~

Compare the output against the contracts. A JAR layout usable by Stub Runner includes paths under `META-INF` for contracts, mappings, and response files:

~~~text
META-INF/
  com.example.orders/
    order-service/
      1.4.2/
        contracts/
          orders/get_paid_order.yml
        mappings/
          orders/get_paid_order.json
~~~

This is an **example layout**, not a snapshot of every plugin version's output. What matters is that the artifact contains mappings with the right request/response matching what your version of Stub Runner looks for.

**Never treat the mere existence of `-stubs.jar` as enough**: confirm at least the mandatory mappings are packaged, not just an empty JAR.

## 6. `verify`: a quality gate before publication

The command:

~~~bash
./mvnw clean verify
~~~

executes the lifecycle through `verify`, meaning **it passes through `package` as well**. In a project integrating appropriate test plugins, it can also run post-package checks such as integration tests, coverage, or validation.

Avoid a common misconception: Maven **does not automatically run every integration test in the world** simply because `verify` exists. Relevant plugins such as Failsafe or custom checks must be configured and bound properly.

Release gate checks should include:

| Verification gate | Question to confirm |
| --- | --- |
| Contract discovery | Was the expected set of Groovy/YAML contracts discovered? |
| Generated test sources | Were new tests generated and included in test compilation? |
| Test execution | Did generated producer tests actually run and PASS without being skipped? |
| Stub conversion | Were proper mappings generated with no missing scenarios? |
| Stub packaging | Is `-stubs.jar` attached and filled with valid contents? |
| Extra quality checks | Did required integration tests and checks actually execute? |

A green `mvn verify` pipeline running **0 contract tests** is not compatibility proof. Configure CI to fail when required scenarios are missing.

## 7. `install`: placing both main artifact and stubs into local Maven

Run:

~~~bash
./mvnw clean install
~~~

When the build succeeds, Maven passes `verify` and then installs attached artifacts into the **local Maven repository**, typically `~/.m2/repository` (customizable in settings).

Example:

~~~text
~/.m2/repository/com/example/orders/order-service/1.4.2/
├── order-service-1.4.2.pom
├── order-service-1.4.2.jar
└── order-service-1.4.2-stubs.jar
~~~

**Only artifacts that are actually attached/installed** appear. If the Maven plugin neither creates nor attaches the stub JAR, `install` cannot invent the `stubs` classifier on its own.

### When is local install useful?

- Developing producer and consumer on the same machine.
- Testing Stub Runner in `LOCAL` mode.
- Checking that the consumer resolves stub coordinates before publishing remotely.
- A local/CI pipeline sharing one workspace where the producer build runs before consumer tests against the **same local Maven repository**.

However, an artifact installed in a developer's `~/.m2` **does not magically exist** on CI agents or teammates' machines.

### Consumer Stub Runner `LOCAL` example

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example.orders:order-service:1.4.2:stubs:8090",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class CheckoutContractTest {

    @Test
    void checkoutHandlesPaidOrder() {
        // Point Checkout's HTTP client to the stub on port 8090.
        // Invoke Checkout business logic and assert consumer behavior.
    }
}
~~~

This is an illustrative skeleton. A real test also needs dependencies, client configuration, and assertions. The Stub Runner ID includes **port 8090**, though the port **is not part of the Maven artifact coordinates**.

### Local cache pitfalls

If the producer edits a contract without re-running `install`, a consumer using `LOCAL` will still pick up the old JAR. Thus, passing consumer tests prove nothing about the new contract unless the version/bytes were actually updated.

In CI, prefer **build-isolated local repositories** or strict cache isolation to avoid sharing artifacts from stale revisions.

## 8. `deploy`: publishing artifacts to a shared repository

Running:

~~~bash
./mvnw clean deploy
~~~

executes all prior phases (including `package`, `verify`, and `install`) and pushes deployable artifacts to the configured **remote Maven repository**.

An example `distributionManagement` block in a POM:

~~~xml
<distributionManagement>
    <repository>
        <id>company-releases</id>
        <url>https://repo.example.test/maven/releases</url>
    </repository>
    <snapshotRepository>
        <id>company-snapshots</id>
        <url>https://repo.example.test/maven/snapshots</url>
    </snapshotRepository>
</distributionManagement>
~~~

These are **illustrative URLs**, not real repositories. Maven selects the repository matching release or SNAPSHOT versions per deploy configuration.

Credentials are normally managed via **Maven settings** or CI secret storage, matching `server.id` to `distributionManagement.repository.id` / `snapshotRepository.id`. **Never put usernames, passwords, or tokens in POMs or contract sources.**

A skeleton `settings.xml` showing only the ID linkage:

~~~xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <servers>
        <server>
            <id>company-releases</id>
            <username>CI_USER_PLACEHOLDER</username>
            <password>CI_SECRET_PLACEHOLDER</password>
        </server>
        <server>
            <id>company-snapshots</id>
            <username>CI_USER_PLACEHOLDER</username>
            <password>CI_SECRET_PLACEHOLDER</password>
        </server>
    </servers>
</settings>
~~~

Placeholders must never be committed as real credentials. CI should supply temporary settings via secret injection, restrict publish permissions, and avoid logging sensitive values.

### What should be verified after `deploy`?

1. The remote repository actually holds both `order-service-1.4.2.jar` **and** `order-service-1.4.2-stubs.jar`.
2. POM/metadata were published under the right group/artifact/version.
3. The JAR contains the contracts/mappings of the intended revision.
4. The artifact has checksums or provenance proving published bytes were not altered later.
5. Consumers have read permissions and do not accidentally pull JARs from another source.

A producer `BUILD SUCCESS` log **does not prove consumers can resolve from the remote repository**. Follow deployment with an independent consumer smoke test if needed.

## 9. Remote Stub Runner: consumer downloads the exact deployed version

One way to configure the consumer test:

~~~java
@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example.orders:order-service:1.4.2:stubs:8090",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.test/maven/releases"
)
class CheckoutRemoteStubTest {
    // Consumer test using the stub fetched from the repository.
}
~~~

This is an **annotation example**, requiring compatible classpath and versions. The repository URL is a placeholder. Repository URL options, credentials, and proxies must match your Stub Runner version; CI jobs may configure repositories in Maven settings or environment variables.

| Mode | Where artifact comes from | When to use |
| --- | --- | --- |
| **LOCAL** | Local Maven repository of the test environment | Local development and single-agent pipelines |
| **REMOTE** | Configured artifact repository | Cross-team testing and distributed CI |
| **CLASSPATH** | Stub resources/JAR already on the classpath | Tests bundling stubs directly as consumer dependencies |

**Do not switch versions to `+` or "latest" just to avoid updating configs.** Dynamic versions allow the same consumer commit to run against different stubs across runs. Release gates should pin versions or at least record exact resolved versions and bytes.

## 10. `package`, `install`, and `deploy` with multi-module Maven

A project may look like:

~~~text
commerce/
├── pom.xml               # Parent / aggregator
├── order-api/
├── order-domain/
├── order-service/
│   ├── pom.xml
│   └── src/test/resources/contracts/orders/...
└── checkout-service/
~~~

Not every module needs to run the Spring Cloud Contract plugin. If contracts belong to `order-service`, then:

- `order-service` needs the plugin configured with the right base test class.
- The parent POM can manage the plugin version inside `pluginManagement`.
- Yet **`pluginManagement` only declares managed defaults**; it does not automatically run the plugin in child modules.
- `order-api` or `order-domain` should not be forced to generate stubs from an inherited inapplicable plugin.
- An aggregator POM with `packaging=pom` does not automatically create `order-service-...-stubs.jar`.

To build one module along with its internal reactor dependencies, use:

~~~bash
./mvnw -pl order-service -am clean verify
~~~

`-pl` picks the module, and `-am` builds modules Maven identifies as reactor dependencies. Do not expect it to run **all consumer modules** outside its dependency graph. Separate consumer contract suites typically need their own pipeline or command.

### Coordinating multi-module deployments

Running `mvn deploy` from the parent may push many modules to the remote repository, not only producer stubs. That may exceed publish permissions on a PR branch.

Distinguish:

- **Build/verify**: can run broadly across the reactor for validation.
- **Publish**: runs only in authorized release pipelines targeting defined repositories and modules.
- **Consumer tests**: target supported consumer versions against the verified stub artifact.

## 11. SNAPSHOTs, release versions, and reproducibility

Example:

~~~text
1.4.3-SNAPSHOT : used in development; contents can be updated.
1.4.2          : release version; should be an immutable artifact.
+ / version range: can resolve different artifacts over time.
~~~

| Scenario | Risk |
| --- | --- |
| Re-deploying the same release version `1.4.2` with different bytes | Past consumer test results become non-reproducible |
| Consumer uses SNAPSHOT while CI caches an older build | Consumer skips testing the new commit's stub |
| Consumer uses `+` / dynamic version | The same commit can run against two different producer stubs |
| Producer publishes new release while consumer never updates ID | CI stays green on old stub, missing breaking changes |
| Same version while external contract source changes revision | Stubs and producer tests may reflect different commitments |

For official releases:

1. Lock producer commit, contract revision, and version.
2. Build and run generated producer tests.
3. Produce the stub JAR from **that exact build/contracts**.
4. Verify stub artifact contents and checksums.
5. Publish to a repository enforcing immutability.
6. Test consumers against the **exact new version** and archive results.

**Semantic version numbering does not replace compatibility testing.** A minor or patch bump on the producer can still alter a field an older consumer relies on.

## 12. Recommended CI workflow

A pipeline can enforce explicit gates:

~~~mermaid
flowchart TD
    A["Checkout producer + contract revision"] --> B["Clean + generate tests + convert"]
    B --> C{"Did generated producer tests run?"}
    C -->|No| X["BLOCK"]
    C -->|Yes| D{"Producer contract tests PASS?"}
    D -->|No| X
    D -->|Yes| E["package: main JAR + stubs JAR"]
    E --> F{"Stub JAR has mappings & right classifier?"}
    F -->|No| X
    F -->|Yes| G["verify: integration/quality gates"]
    G --> H{"PASS?"}
    H -->|No| X
    H -->|Yes| I["Controlled install/deploy"]
    I --> J["Consumer downloads exact G:A:V:stubs"]
    J --> K{"Coordinates + checksum valid?"}
    K -->|No| X
    K -->|Yes| L["Stub Runner + consumer tests"]
    L --> M{"Consumer assertions PASS?"}
    M -->|No| X
    M -->|Yes| N["Archive evidence and decide rollout"]
~~~

### Mandatory gates to consider

| Gate | What happens if skipped |
| --- | --- |
| Contracts root and discovered contract count | Green build because Verifier found no DSL |
| Generated test compilation and execution | Code generated yet never run by test runner |
| Inspect `-stubs.jar` | Only main JAR published; consumers fail to fetch stubs |
| Contract revision traceability | Stubs generated from a different source than producer tests |
| Repository target and deploy permissions | Accidental push to release repository |
| Stub artifact checksum/version | Consumer tests stale or overwritten artifact |
| Consumer integration assertions | Stub starts while consumer logic remains buggy |
| Guard against accidental test skipping | CI PASS gives zero compatibility assurance |

### Do not use skip flags as a "fix" for failing contract tests

Several flags can bypass checks:

~~~bash
./mvnw package -DskipTests
./mvnw package -Dmaven.test.skip=true
./mvnw package -Dspring.cloud.contract.verifier.skip=true
~~~

Their exact effects differ: `-DskipTests` typically skips test **execution** while still compiling; `-Dmaven.test.skip=true` can skip both **compilation and execution**; the Verifier property skips plugin goals. They are **not equivalent**, and none should be used in release gates meant to certify contract compliance.

A `package` or `deploy` that succeeds with skipped tests may still produce a JAR, yet gives zero proof that the producer honors its contracts.

## 13. External contract sources separated from the producer

In some organizations, contracts live in an **independent repository or artifact** rather than `src/test/resources/contracts`. The Maven plugin supports external contract configuration such as contract dependency, contracts path, mode, and repository URL per version.

In that setup, track at least three identities:

~~~text
Producer build revision:       order-service@abc123
Contract source revision:      order-contracts@def456
Published stub artifact:       com.example.orders:order-service:1.4.2:stubs
~~~

If the plugin tests the producer against contract `def456` while another job packages stubs from `xyz789`, a passing consumer proves nothing about that producer build.

**The `package` step does not guarantee provenance by itself.** The pipeline must pin contract sources, log resolved artifacts/revisions, and ensure generated tests and mappings consume identical inputs.

## 14. Do not confuse running stubs with publishing stubs

The Spring Cloud Contract Maven plugin may offer the `run` goal to launch HTTP stubs in appropriate setups. However:

| Action | Purpose |
| --- | --- |
| `spring-cloud-contract:run` | Starts stubs locally to try requests |
| `package` | Builds artifacts inside `target` |
| `install` | Places artifacts into local Maven |
| `deploy` | Publishes artifacts to a remote Maven repository |
| Stub Runner consumer test | Loads/starts selected stub and asserts consumer logic |

A WireMock server running at `localhost:8090` **does not mean the artifact was published**. Conversely, a deployed `-stubs.jar` does not automatically open an HTTP port; consumer tests must launch Stub Runner or a corresponding stub runtime.

Artifact coordinates and runtime ports are separate pieces of information:

~~~text
Artifact: com.example.orders:order-service:1.4.2:stubs
Runtime:  http://localhost:8090
Request:  GET /api/orders/ORD-1001
~~~

## 15. Common errors by phase

| Symptom | Usual phase/stage | What to inspect |
| --- | --- | --- |
| No generated tests visible | `generate-test-sources` | Plugin didn't run, wrong contracts root, DSL files filtered |
| Generated tests fail to compile | `test-compile` | Base class, dependencies, test mode, generated source |
| Producer test fails | `test`/`verify` per config | Implementation breaks contract or fixture is wrong |
| `target/stubs` has no mappings | `convert` | Input contracts, plugin executions, conversion logs |
| `package` builds main JAR without `-stubs.jar` | `generateStubs`/attachment | Plugin goals, classifier, skip flags, mapping contents |
| `install` succeeds yet `LOCAL` consumer misses stub | Local repository | Different coordinates, not attached, built on another machine, or stale cache |
| `deploy` returns 401/403 | Remote repository | Credentials, settings server ID, publish permissions |
| `deploy` reports missing repository | `distributionManagement` | Repository URL, release/SNAPSHOT target, plugin config |
| `deploy` pushes main JAR without stubs | Artifact attachment/publication | Inspect artifact list, classifier, metadata post-publish |
| `REMOTE` consumer fails to download | Stub Runner repository resolution | group/artifact/version/classifier, URL, permissions, proxy/cache |
| Stub Runner starts yet returns 404 | HTTP matching | Method/URL/headers/body and mappings inside JAR |
| Consumer CI PASSES despite breaking API | Version/provenance | Testing stale stub or missing assertions |
| CI passes with 0 contract tests | Test execution/filters | Fail when contracts are missing or tests skipped |

**Diagnose by layer:** contract source → test generation → test execution → mapping conversion → packaging → attachment → install/deploy → artifact resolution → HTTP matching → consumer logic.

Never edit `response.body` in the DSL because Maven returned 401 on `deploy`, and never tweak `repositoryRoot` when the HTTP stub already started yet failed request matching.

## 16. Practice exercises

### Exercise A — `package`, `install`, or `deploy`?

A developer runs `./mvnw clean package` successfully, then a teammate on another machine configures Stub Runner `LOCAL` and cannot find `order-service:1.4.2:stubs`.

**Task:** explain why, and propose two workflows: testing locally on one machine and sharing artifacts across a team.

**Hint:** `package` only builds artifacts; `install` writes to the local repository of the machine running the build; `deploy` publishes to a remote repository for teammates to fetch (typically with `REMOTE`).

### Exercise B — Main JAR only

After `./mvnw clean install`, local Maven holds `order-service-1.4.2.jar` and its POM, but no `order-service-1.4.2-stubs.jar`.

**Task:** identify the failure layer and list what to check before re-running `install`.

**Hint:** check contract discovery, `convert`, `generateStubs`, and attachment/classifier; `install` cannot create a stub JAR if the build did not attach it.

### Exercise C — How does `verify` differ from `deploy`?

One CI job runs `./mvnw clean verify` with contract tests PASSING. Another job needs consumers to download stubs from a remote repository.

**Task:** name the missing step and the conditions required to permit it.

**Hint:** the artifact must be published; verify the stubs JAR and provenance, obtain deploy credentials/permissions, then verify the artifact can be fetched from the repository.

### Exercise D — Skipping tests to release

A producer has a FAILING generated contract test; a developer passes `-DskipTests` so `mvn deploy` succeeds.

**Task:** evaluate the validity of the release evidence and recommend how to fix it.

**Hint:** a successful deploy only proves an artifact was uploaded, not that the producer honors contracts; fix the implementation, fixture, or agreed contract, then re-run producer tests.

### Exercise E — Multi-module

A parent POM configures the plugin under `pluginManagement`, yet module `order-service` does not declare the plugin and has zero generated tests.

**Task:** explain the role of `pluginManagement` and how to ensure the plugin runs in the right module.

**Hint:** managing version/defaults differs from activating a plugin; check the module's effective POM and Maven logs.

### Exercise F — Mutated SNAPSHOT

Checkout CI uses `order-service:1.5.0-SNAPSHOT:stubs`. The same Checkout commit runs twice and receives two different sets of mappings.

**Task:** analyze the risk and explain how to make the release gate reproducible.

**Hint:** pin exact revisions/versions, record checksums, use immutable artifacts or isolated environments; avoid implicit latest snapshots.

### Exercise G — Older consumer must test new producer

Producer 1.5.0 renames JSON field `status` to `paymentStatus`. Checkout 2.8.0 PASSES against stub 1.4.2.

**Task:** can you conclude 1.5.0 is compatible with Checkout 2.8.0? What must be tested?

**Hint:** you must test Checkout 2.8.0 against stub 1.5.0 generated from the exact contract revision verified by producer 1.5.0, then plan backward compatibility for the old field.

## 17. Pre-release checklist via Maven

- [ ] Groovy/YAML contracts sit at the right path and are discovered by the plugin.
- [ ] `generateTests` actually generates producer tests into test sources.
- [ ] Generated tests compile, execute, and PASS without being skipped.
- [ ] Base test class, fixtures, and test mode fit the producer's HTTP/messaging stack.
- [ ] `convert` produces mappings for all expected contracts.
- [ ] `generateStubs` produces a JAR attached with classifier `stubs` (or the agreed classifier).
- [ ] `package` creates both the main artifact and the stub artifact to publish.
- [ ] `verify` actually executes required quality/integration checks.
- [ ] `install` places the stub JAR into local Maven under the right group/artifact/version.
- [ ] `deploy` runs only in authorized pipelines with secure repository URLs and credentials.
- [ ] Verified the remote repository actually contains `-stubs.jar` and matching metadata.
- [ ] Rejected releases built with `-DskipTests` or `spring.cloud.contract.verifier.skip` when compatibility proof is required.
- [ ] Release artifacts are immutable or at minimum tracked by checksum and revision.
- [ ] Release gates never depend on `+`/latest when reproducibility is required.
- [ ] Consumer Stub Runner references the exact published artifact, classifier, and version.
- [ ] Consumer integration tests include business assertions rather than only checking stub startup.
- [ ] In multi-module builds, the plugin runs in the right module and publish jobs do not push unintended artifacts.
- [ ] With external contracts, producer tests and stub JAR use the exact same revision.
- [ ] No tokens, passwords, or sensitive production data appear in POMs, contracts, or stubs.
- [ ] CI reports record producer commit, contract revision, artifact coordinates, and tested consumer versions.

## 18. References

- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): definitions of `package`, `verify`, `install`, and `deploy`.
- [Spring Cloud Contract — Maven Project](https://docs.spring.io/spring-cloud-contract/reference/maven-project.html): plugin configuration, contracts, test generation, and base class.
- [Spring Cloud Contract Maven Plugin — Goals](https://docs.spring.io/spring-cloud-contract/docs/current/spring-cloud-contract-maven-plugin/plugin-info.html): `generateTests`, `convert`, and `generateStubs` goals.
- [Spring Cloud Contract Maven Plugin — generateStubs](https://docs.spring.io/spring-cloud-contract/docs/current/spring-cloud-contract-maven-plugin/generateStubs-mojo.html): packaging mappings into a stub JAR and classifier.
- [Spring Cloud Contract — Stub Runner Common Properties](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-common.html): stub coordinates and artifact resolution.

**Key takeaway:** `package` **creates** main/stub artifacts, `install` places them into the **local Maven repository**, and `deploy` **publishes** them to a remote repository. Yet succeeding in any Maven phase does not by itself prove producer–consumer compatibility: CI must confirm generated producer tests actually executed and PASSED, the stub JAR carries the right classifier/contents/version, and consumers test against **that exact artifact**. That turns stub publishing into an auditable, traceable workflow rather than merely seeing `BUILD SUCCESS`.
