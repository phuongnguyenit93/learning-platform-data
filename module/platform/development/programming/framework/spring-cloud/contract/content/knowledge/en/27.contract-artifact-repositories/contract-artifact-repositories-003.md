# Fetching Contracts from External Locations or Artifacts

## Learning Objectives

In **Spring Cloud Contract**, the producer exposes an API or emits messages, while the consumer uses that interface. **Groovy/YAML DSL** contracts describe HTTP or messaging behavior; from the DSL, the tooling generates **producer contract tests**, **stubs** for the consumer to run via **Stub Runner**, and helps CI detect incompatible changes.

This lesson belongs to the **Contract and Artifact Repositories** chapter, focusing on scenarios where contracts **do not reside directly inside the producer module**. They may live in another folder, be packaged into a **contract JAR** on Nexus/Artifactory, or reside in a **Git SCM repository**.

After this lesson, you can:

- Distinguish **contract source**, **contract definition JAR**, **producer binary**, and **producer stubs JAR**.
- Specify an external contract directory using `contractsDirectory` (Maven) or `contractsDslDir` (Gradle).
- Configure the producer to fetch a contract artifact using `contractDependency`, `contractsPath`, `contractsMode`, and repository URLs.
- Fetch contracts via Git SCM using the `git://` prefix and understand the `META-INF/group/artifact/version/contracts` layout.
- Select the right contracts per producer/consumer and keep versions traceable.
- Connect DSL fetching to generated producer tests, stub publication, consumer Stub Runner, and CI.
- Avoid false green builds caused by 0 generated tests, stale artifacts, wrong paths, skipped tests, or caching.

> **Principle:** a contract repository only supplies expected definitions. The producer must still run **generated tests against the real implementation and pass** before publishing stubs as a verified interface.

## 1. Why Do We Need an Independent Contract Repository?

Suppose **Inventory Service** exposes an API for **Checkout Service**:

~~~http
GET /api/inventory/SKU-101 HTTP/1.1
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"sku":"SKU-101","available":true,"quantity":8}
~~~

When two teams manage separate repositories, Checkout might not have permission to clone Inventory's source code. Yet Checkout needs to propose contracts, review bodies/statuses/headers, and know whether the producer already supports the API. A shared repository can:

1. Allow consumers to open pull requests describing the behavior they need.
2. Allow producers to review expectations before changing code.
3. Give multiple consumers visibility into their requirements.
4. Publish contract definitions as an independent version.
5. Let producer CI fetch the **exact reviewed version**.
6. Let consumers test against stubs that the producer has already verified.

**Trade-off:** when DSL sources sit outside the module, the build additionally depends on repository URLs, credentials, JAR/Git layouts, versions, and caches. If any of those are wrong, the producer may fail to verify new changes even though the build reports SUCCESS.

### Overall flow

~~~mermaid
flowchart TD
    A["Consumer proposes Groovy/YAML DSL"] --> B["Contract repository"]
    B --> C{"Fetch source"}
    C -->|Folder| D["Local directory"]
    C -->|Artifact| E["Maven contract JAR"]
    C -->|Git| F["Git SCM tree"]
    D --> G["Producer contract generator"]
    E --> G
    F --> G
    G --> H["Generated producer tests"]
    H --> I{"Producer implementation PASS?"}
    I -->|No| X["Block verified stub"]
    I -->|Yes| J["Producer :stubs artifact"]
    J --> K["Consumer Stub Runner"]
    K --> L["Consumer test real client/handler"]
~~~

## 2. Four Resources You Must Not Confuse

| Resource | Sample coordinates or name | Role |
|---|---|---|
| **DSL source** | `stockAvailable.groovy`, `stockAvailable.yml` | Describes communication behavior |
| **Contract definition JAR** | `com.example.contracts:shared-contracts:1.4.0` | Packages DSL/fixtures for the producer to fetch |
| **Producer binary** | `com.example:inventory-producer:2.3.0` | The real Inventory application |
| **Producer stub JAR** | `com.example:inventory-producer:2.3.0:stubs` | Mappings/definitions the consumer uses with Stub Runner |

**A contract JAR is not a stub JAR.** A contract JAR can be published from the contract repository before the producer finishes implementing the behavior; a verified stub must be tied to executed and PASSING producer tests. The two artifacts can have **different versions**:

~~~text
Contract definitions: com.example.contracts:shared-contracts:1.4.0
Producer artifact:    com.example:inventory-producer:2.3.0
Consumer stubs:       com.example:inventory-producer:2.3.0:stubs
~~~

CI must store the link: **producer 2.3.0 verified against shared-contracts 1.4.0 from which source SHA**, producing `:stubs` with which digest.

Adding the contract JAR to Gradle's `implementation` or Maven's runtime `dependencies` **does not automatically tell the generator** to read the DSL. The Spring Cloud Contract plugin has dedicated configuration for contract sources.

## 3. One Sample DSL Used Across All Sources

### Groovy

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Inventory SKU-101 has 8 items left'

    request {
        method 'GET'
        url '/api/inventory/SKU-101'
        headers {
            accept(applicationJson())
        }
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-101',
            available: true,
            quantity: 8
        )
    }
}
~~~

### Equivalent YAML

~~~yaml
description: 'Inventory SKU-101 has 8 items left'
request:
  method: GET
  url: '/api/inventory/SKU-101'
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-101
    available: true
    quantity: 8
~~~

Choose **one** format for this scenario in a real build. Values `quantity: 8` (number) and `available: true` (boolean) are typed; do not turn them into strings just to make a producer test pass if the consumer expects the right types.

## 4. Contract Sources and When to Choose Each

| Source | Example | Producer uses | Best for |
|---|---|---|---|
| Local folder outside module | `../api-contracts/inventory` | `contractsDirectory` / `contractsDslDir` | Monorepo, CI checking out two repos |
| Maven artifact repository | `shared-contracts:1.4.0` | `contractDependency` + repository + `contractsPath` | Versioned artifacts, multi-pipeline setups |
| Git SCM repository | `git://https://git.example.invalid/team/contracts.git` | SCM downloader + producer coordinates | Git reviews and SCM stubs |

**Note:** a Maven repository and a Git repository are not two equivalent URL styles. Maven resolves JARs by `group:artifact:version`; the Git SCM downloader traverses a file tree with its own layout. Do not apply one source's layout to the other.

## 5. Option A — Contract Directory Outside the Producer Module

A sample workspace:

~~~text
commerce-workspace/
├── api-contracts/
│   └── inventory/
│       └── stockAvailable.groovy
└── inventory-producer/
    ├── pom.xml
    ├── build.gradle
    └── src/main/java/...
~~~

`api-contracts` can live in a monorepo or be checked out by CI from another repository into the same workspace.

### Maven: contractsDirectory

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.springframework.cloud</groupId>
      <artifactId>spring-cloud-contract-maven-plugin</artifactId>
      <version>REPLACE_WITH_COMPATIBLE_SCC_VERSION</version>
      <extensions>true</extensions>
      <configuration>
        <testFramework>JUNIT5</testFramework>
        <baseClassForTests>
          com.example.inventory.contract.InventoryContractBase
        </baseClassForTests>
        <contractsDirectory>
          ${project.basedir}/../api-contracts/inventory
        </contractsDirectory>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

`contractsDirectory` is a **filesystem path**, not Maven coordinates. Maven will not automatically clone Git just because you declare a path outside the project. The pipeline must check out the repository and ensure the folder exists before running the verifier.

`REPLACE_WITH_COMPATIBLE_SCC_VERSION` is a placeholder to replace. The producer module still needs Spring Boot, verifier dependencies, and a real base class.

### Gradle: contractsDslDir

~~~groovy
contracts {
    testFramework = 'JUNIT5'
    testMode = 'MockMvc'
    baseClassForTests =
        'com.example.inventory.contract.InventoryContractBase'

    contractsDslDir = file('../api-contracts/inventory')
}
~~~

With modern Gradle plugins, local contracts typically live in `src/contractTest/resources/contracts`. `contractsDslDir` overrides where the plugin looks for DSL; relative paths resolve against the Gradle module being configured.

### Pros and limitations

- **Pros:** easy to test unpublished contract PRs, no registry required, diffs are directly visible.
- **Limitations:** CI requires a stable workspace layout; does not automatically pin commits, risking empty folders or wrong revisions.
- **Safeguards:** check out an explicit commit/tag of the contract repo, log the revision, and verify both DSL count and executed generated producer tests.

Do not merely verify “folder exists.” An empty folder or one holding another producer's contracts can still yield **0 meaningful tests**.

## 6. Option B — Packaging a Shared Contract JAR

An independent repository:

~~~text
shared-contracts/
├── pom.xml or build.gradle
└── src/main/resources/
    └── com/example/
        ├── inventory-producer/
        │   ├── checkout-consumer/
        │   │   └── stockAvailable.groovy
        │   └── reporting-consumer/
        │       └── stockLow.yml
        └── pricing-producer/
            └── checkout-consumer/
                └── priceAvailable.groovy
~~~

The JAR produces these entries:

~~~text
com/example/inventory-producer/checkout-consumer/stockAvailable.groovy
com/example/inventory-producer/reporting-consumer/stockLow.yml
com/example/pricing-producer/checkout-consumer/priceAvailable.groovy
~~~

Artifact coordinates:

~~~text
com.example.contracts:shared-contracts:1.4.0
~~~

Structuring by consumer name tells reviewers which consumer depends on each contract; it also supports `stubs-per-consumer` organization when fully configured.

### Maven contract definitions module

With `src/main/resources`, Maven JAR packaging can be very concise:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example.contracts</groupId>
  <artifactId>shared-contracts</artifactId>
  <version>1.4.0</version>
  <packaging>jar</packaging>
</project>
~~~

~~~bash
# Build the contract JAR in the contracts repository.
./mvnw -B -ntp package
jar tf target/shared-contracts-1.4.0.jar
~~~

Inspection must show the DSL under `com/example/inventory-producer`. Succeeding at **JAR packaging** does not prove the producer implements the interface correctly.

### Gradle contract JAR module

~~~groovy
plugins {
    id 'java'
    id 'maven-publish'
}

group = 'com.example.contracts'
version = '1.4.0'

publishing {
    publications {
        definitions(MavenPublication) {
            from components.java
            artifactId = 'shared-contracts'
        }
    }
}
~~~

The `java` plugin includes `src/main/resources` in the JAR. This is a **contract definitions** publication, distinct from the producer's `verifierStubsJar`. Repositories and credentials must be configured securely for real publishing.

### Three verification boundaries

| Step | Responsibility |
|---|---|
| Contract repo CI | Review DSL, syntax, fixtures, and package JAR with proper structure |
| Producer CI | Fetch contract JAR, generate/run tests against real Inventory code |
| Consumer CI | Fetch **producer stubs**, test real client/handler via Stub Runner |

**The existence of a contract artifact does not mean producer contract tests passed.**

## 7. Producer Maven Fetching Contract JAR via REMOTE

Suppose JAR `com.example.contracts:shared-contracts:1.4.0` is published in a Maven-compatible repository.

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.springframework.cloud</groupId>
      <artifactId>spring-cloud-contract-maven-plugin</artifactId>
      <version>REPLACE_WITH_COMPATIBLE_SCC_VERSION</version>
      <extensions>true</extensions>

      <configuration>
        <testFramework>JUNIT5</testFramework>
        <baseClassForTests>
          com.example.inventory.contract.InventoryContractBase
        </baseClassForTests>

        <contractsMode>REMOTE</contractsMode>
        <contractsRepositoryUrl>
          https://repo.example.invalid/repository/contract-definitions
        </contractsRepositoryUrl>

        <contractDependency>
          <groupId>com.example.contracts</groupId>
          <artifactId>shared-contracts</artifactId>
          <version>1.4.0</version>
        </contractDependency>

        <contractsPath>com/example/inventory-producer</contractsPath>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

The `example.invalid` repository is a **non-functional illustrative URL**; replace it with your project's Nexus/Artifactory/Maven repository. Verifier dependencies, Spring Boot BOM, and test setup are not condensed into a complete POM here.

| Option | Meaning |
|---|---|
| `contractsMode=REMOTE` | Resolver fetches contracts from a remote source |
| `contractsRepositoryUrl` | Maven repository URL hosting the contract JAR |
| `contractDependency` | Specifies the artifact containing the DSL |
| `contractsPath` | Directory **inside the JAR** dedicated to Inventory |
| `baseClassForTests` | Class preparing the real producer controller/application |
| `testFramework` | Selects JUnit 5 in this example |

### Why is contractsPath important?

By default, `contractsPath` is documented as being inferred from `groupId/artifactId` of the **contract dependency**:

~~~text
Contract artifact:
  com.example.contracts:shared-contracts:1.4.0

Default path inferred:
  com/example/contracts/shared-contracts

Actual contracts path in our JAR:
  com/example/inventory-producer
~~~

If `contractsPath` is omitted, the plugin may **download the artifact successfully yet find no contracts**. The gap between resolving the JAR and discovering the DSL is a very common cause of false green builds.

Maven may fall back to configured repositories if `contractsRepositoryUrl` is omitted, depending on plugin version. When CI needs traceability, explicitly record **which repository and artifact digest** were used.

## 8. Producer Gradle Fetching the Same Contract JAR

In `inventory-producer/build.gradle` with the `org.springframework.cloud.contract` plugin applied:

~~~groovy
contracts {
    testFramework = 'JUNIT5'
    testMode = 'MockMvc'
    baseClassForTests =
        'com.example.inventory.contract.InventoryContractBase'

    contractsMode = 'REMOTE'

    contractDependency {
        stringNotation = 'com.example.contracts:shared-contracts:1.4.0'
    }

    contractRepository {
        repositoryUrl =
            'https://repo.example.invalid/repository/contract-definitions'
    }

    contractsPath = 'com/example/inventory-producer'
}
~~~

This is the **`contracts` configuration block**, not a full build file. You still need the plugin version, BOM, verifier dependencies, and base test matching your Spring Boot/Cloud version.

You can declare the dependency with fields instead of `stringNotation`:

~~~groovy
contractDependency {
    groupId = 'com.example.contracts'
    artifactId = 'shared-contracts'
    version = '1.4.0'
}
~~~

Pick **one declaration style**; never specify differing versions in two places.

### Inspecting Gradle tasks

~~~bash
./gradlew :inventory-producer:tasks --all
./gradlew :inventory-producer:contractTest
~~~

With modern Gradle plugins, generated producer tests typically run in the `contractTest` source set/task. Tests must call real Inventory code, not a mock simulating Inventory's endpoint.

Do not use:

~~~groovy
// Does not replace contractDependency configuration:
implementation 'com.example.contracts:shared-contracts:1.4.0'
~~~

because `implementation` manages the application classpath rather than telling the generator where to find DSLs.


## 9. LOCAL and REMOTE: Same Contract, Different Source

When developing an unpublished contract candidate, the contract team can build the JAR and install it into the local Maven repository:

~~~bash
# Run in the shared-contracts repository.
./mvnw -B -ntp clean install
~~~

The producer can use `contractsMode=LOCAL` with the same coordinates:

~~~xml
<configuration>
    <contractsMode>LOCAL</contractsMode>
    <contractDependency>
        <groupId>com.example.contracts</groupId>
        <artifactId>shared-contracts</artifactId>
        <version>1.4.0</version>
    </contractDependency>
    <contractsPath>com/example/inventory-producer</contractsPath>
</configuration>
~~~

Gradle equivalent:

~~~groovy
contracts {
    contractsMode = 'LOCAL'

    contractDependency {
        stringNotation = 'com.example.contracts:shared-contracts:1.4.0'
    }

    contractsPath = 'com/example/inventory-producer'
}
~~~

**LOCAL does not mean the plugin reads directly from `target/shared-contracts-1.4.0.jar`**; the artifact must be installed into the Maven local repository used by the build process, with valid metadata.

| Attribute | LOCAL | REMOTE |
|---|---|---|
| Artifact source | Maven local repo | Nexus/Artifactory/Maven-compatible repo |
| Best for | Offline dev, PR trials, CI candidates installed locally | CI, releases, multi-team consumption |
| Risks | Stale cache under same version, missing artifact on dev machine | Network, credentials, proxy, repository cache |
| Controls | Log local path + version/digest | Log repository URL + version/digest |
| Self-verifies producer? | **No** | **No** |

**Distinguish configuration names:**

- `contractsMode`: **producer** fetches *contract definitions* via LOCAL/REMOTE.
- `stubsMode`: **consumer Stub Runner** fetches *producer stubs* via LOCAL/REMOTE.

They share the same mode values but fetch **two different kinds of artifacts**.

## 10. Option C — Using Git SCM as a Contract Repository

Spring Cloud Contract documents using Git as an SCM store for contracts and stubs. For the plugin to pick the SCM downloader, the URL must carry the **`git://` prefix**:

~~~text
git://https://git.example.invalid/team/service-contracts.git
~~~

Compared to a standard HTTPS URL:

~~~text
https://git.example.invalid/team/service-contracts.git
~~~

the `git://` prefix is **Spring Cloud Contract's resolver-selection convention** placed ahead of the HTTPS transport URL. Do not mistake it for requiring an unencrypted Git daemon connection.

### SCM layout expected by the downloader

~~~text
service-contracts.git/
└── META-INF/
    └── com.example/
        └── inventory-producer/
            └── 2.3.0/
                ├── contracts/
                │   └── checkout-consumer/
                │       ├── stockAvailable.groovy
                │       └── stockNotFound.yml
                └── mappings/
                    └── checkout-consumer/
                        └── stockAvailable.json
~~~

Per the Git SCM documentation, the root for each producer/version is:

~~~text
META-INF/<groupId>/<artifactId>/<version>/
~~~

containing `contracts/` for DSL and `mappings/` for HTTP stub mappings. In the example, group ID `com.example` is used verbatim as a folder beneath `META-INF`. This is the **SCM downloader layout**, distinct from `com/example/inventory-producer` inside the contract JAR shown earlier.

In a CDC cycle, consumers can propose DSL first, while `mappings` are added **after the producer generates and verifies stubs**. Do not require every new contract PR to already include JSON mappings.

### Maven Git remote configuration

In the producer Maven plugin:

~~~xml
<configuration>
    <contractsMode>REMOTE</contractsMode>

    <contractsRepositoryUrl>
        git://https://git.example.invalid/team/service-contracts.git
    </contractsRepositoryUrl>

    <contractDependency>
        <groupId>com.example</groupId>
        <artifactId>inventory-producer</artifactId>
        <version>2.3.0</version>
    </contractDependency>

    <baseClassForTests>
        com.example.inventory.contract.InventoryContractBase
    </baseClassForTests>
</configuration>
~~~

`contractDependency` in the SCM case is used to locate `META-INF/com.example/inventory-producer/2.3.0/contracts`. It **does not mean the Git repository contains a Maven contract JAR**.

### Gradle Git remote configuration

~~~groovy
contracts {
    contractsMode = 'REMOTE'

    contractDependency {
        stringNotation = 'com.example:inventory-producer:2.3.0'
    }

    contractRepository {
        repositoryUrl =
            'git://https://git.example.invalid/team/service-contracts.git'
    }

    baseClassForTests =
        'com.example.inventory.contract.InventoryContractBase'
}
~~~

These snippets show the core plugin configuration. The producer still needs dependencies/test setup and proper Git authentication, never placing passwords/tokens directly in source or URLs.

### Does it automatically push stubs back to Git?

**No.** Spring Cloud Contract provides the `pushStubsToScm` goal/task, which must be invoked **intentionally**, for example:

~~~bash
./gradlew :inventory-producer:pushStubsToScm
~~~

This is a **write operation to an external repository**, not needed to read contracts. Only invoke it after generated producer tests **actually execute and PASS**, and within a CI job holding protected push permissions.

Maven has the corresponding `pushStubsToScm` goal; do not attach it automatically to every unreviewed PR and treat a successful push as producer verification.

## 11. A Git Version Folder Does Not Replace a Git Commit

The SCM example uses `META-INF/com.example/inventory-producer/2.3.0/contracts`. “`2.3.0`” is only a **logical version folder**; if the default Git branch continues changing, that folder's contents could be modified after the producer ran verification.

Two layers of identity must be managed:

1. **Logical version:** version folder / contract artifact version looked up by the plugin.
2. **Source revision:** commit SHA/tag or JAR digest actually verified.

For strict reproducibility:

- Build an **immutable versioned contract JAR** from a reviewed Git commit.
- Or check out the Git repo at a **pinned commit SHA/tag** in CI, then use the local `contractsDirectory`/`contractsDslDir` of that snapshot.
- If you want the SCM downloader to pin a revision directly, verify the capabilities and exact option names of **your plugin version**; do not invent properties like `gitCommit` or `branch`.
- Store the contract SHA alongside the producer SHA, stub version, and generated test results.

Never silently edit DSL under an already-published version while keeping the same version string across pipelines with different caches.

## 12. Selecting Contracts per Producer and Consumer

A contract JAR may contain:

~~~text
com/example/inventory-producer/checkout-consumer/stockAvailable.groovy
com/example/inventory-producer/reporting-consumer/stockLow.groovy
com/example/pricing-producer/checkout-consumer/priceAvailable.groovy
~~~

If the Inventory producer configures:

~~~groovy
contracts {
    contractsPath = 'com/example/inventory-producer'
}
~~~

it selects Inventory's contract group. To filter further by consumer, Spring Cloud Contract offers mechanisms like `includedFiles` and `ignoredFiles` depending on the plugin; filters must match **the actual paths inside the unpacked artifact**.

### Maven includedFiles example

~~~xml
<configuration>
    <contractsPath>com/example/inventory-producer</contractsPath>
    <includedFiles>
        <includedFile>**/checkout-consumer/**</includedFile>
        <includedFile>**/reporting-consumer/**</includedFile>
    </includedFiles>
</configuration>
~~~

This illustrates additions alongside `contractDependency`/`contractsMode` in the producer module, not a complete configuration. If the path or pattern is wrong, the artifact may download fine yet **0 contracts are selected**.

### When HTTP and messaging share one JAR

- HTTP: generated tests need a base class initializing the right controller/MockMvc or live HTTP app.
- Messaging: generated tests need a messaging verifier/binder, `triggeredBy` or `messageFrom`, and destination.
- Security/error cases: may require test setups with exception handlers/filters or special fixtures.

Spring Cloud Contract provides `baseClassMappings` for contract path/package patterns. Each group must extend the right base class; never assume every test can share one setup and skip tricky branches.

### Overlapping mapping pitfalls

If two contracts both match `GET /api/inventory/SKU-101` yet return two different responses, sitting in two consumer folders **does not make WireMock distinguish the requests automatically**. Fix matchers, versioning, URLs, or stub-per-consumer policies rather than hoping folders control runtime precedence.

## 13. Consumer Proposes Contracts via a Shared Repository

The CDC workflow typically involves these steps:

~~~mermaid
sequenceDiagram
    participant C as Checkout team
    participant R as Contract repository
    participant P as Inventory producer CI
    participant A as Artifact registry
    participant T as Checkout consumer CI
    C->>R: PR adding/updating Groovy or YAML DSL
    R->>R: Review interface, fixture, and ownership
    P->>R: Fetch exact contract candidate revision
    P->>P: Generate tests, implement, verify producer
    alt Producer tests pass
        R->>A: Publish contract artifact per policy
        P->>A: Publish candidate producer :stubs
        T->>A: Stub Runner fetches exact version
        T->>T: Test real consumer client/handler
    else Producer test fails
        P-->>C: Coordinate fixing contract/implementation
    end
~~~

The contract repository is where **consumers propose requirements**; the producer must accept and prove its implementation complies.

### Producer PASS does not mean all older consumers remain compatible

Old contract:

~~~json
{"sku":"SKU-101","available":true,"quantity":8}
~~~

New contract:

~~~json
{"sku":"SKU-101","availability":"IN_STOCK","units":8}
~~~

If producer implementation and DSL are changed simultaneously, new generated tests can PASS. Yet old Checkout still reads `available` and `quantity`.

Run consumer tests against the **new candidate stub** and review breaking changes against currently deployed versions. This is why a contract repository should track owner/consumer context, not just a list of DSL files.

## 14. Producer Verification Does Not Change Because DSL Lives Further Away

Once the contract source is resolved:

~~~text
Contract folder / contract JAR / Git SCM
    |
    v
Discover Groovy/YAML contract files
    |
    v
Generate producer test sources
    |
    v
Compile and run generated tests with real producer code
    |
    v
Assert HTTP status/headers/body or message payload
    |
    v
PASS => producer stub eligible for publication
~~~

### Maven

~~~bash
./mvnw -B -ntp clean verify
~~~

Generated tests typically appear under `target/generated-test-sources/contracts`, though customizable.

### Gradle

~~~bash
./gradlew :inventory-producer:contractTest
~~~

Generated tests typically sit under `build/generated-test-sources/contractTest`, depending on plugin version.

### What evidence should you inspect?

1. Resolver fetched the intended artifact version/revision and repository.
2. `contractsPath`/SCM folder matched and discovered the expected number of DSLs.
3. Generated tests compiled, **actually executed**, and produced a test report.
4. Base class invoked producer code, not merely a mock returning sample responses.
5. Assertions checked the fields/statuses/headers/payloads consumers depend on.
6. Tests PASSED before packaging/publishing verified producer `:stubs`.

`failOnNoContracts` and `failOnInProgress` are useful fail-closed options. Gradle example:

~~~groovy
contracts {
    failOnNoContracts = true
    failOnInProgress = true
}
~~~

Verify options/defaults for your plugin version and still confirm **executed test count**: failing when contracts are missing does not replace verifying test execution reports.

## 15. Contract Sources Are Build-Time Input Only

A common misconfiguration:

~~~groovy
dependencies {
    // Does not cause Contract Verifier to read the DSL path automatically.
    implementation 'com.example.contracts:shared-contracts:1.4.0'
}
~~~

If the goal is to fetch a contract JAR to generate tests, use:

~~~groovy
contracts {
    contractsMode = 'REMOTE'

    contractDependency {
        stringNotation = 'com.example.contracts:shared-contracts:1.4.0'
    }

    contractsPath = 'com/example/inventory-producer'
}
~~~

Add the appropriate repository URL as well. Never place contracts on the runtime classpath simply because the plugin wasn't configured properly.

Keep boundaries clear:

- Contract DSL: **build/test input**.
- Generated producer test: **verifies producer implementation**.
- Stub artifact: **consumer test input**.
- Producer runtime: **real application**, does not need the contract JAR just to serve HTTP.

## 16. Consumer Stub Runner Consumes Producer :stubs, Not the Contract JAR

Once the producer has verified:

~~~text
Contract source:
  com.example.contracts:shared-contracts:1.4.0

Verified producer:
  com.example:inventory-producer:2.3.0

Verified producer stub:
  com.example:inventory-producer:2.3.0:stubs
~~~

The consumer uses Stub Runner to fetch the **producer stub**, for example:

~~~java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:2.3.0:stubs:0",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot =
        "https://repo.example.invalid/repository/verified-stubs"
)
class CheckoutInventoryContractTest {
    // Use Checkout's real HTTP client pointed at the runtime stub port.
    // Assert JSON/status and business decisions.
}
~~~

This is a skeleton; Spring tests need the client, port injection via `@StubRunnerPort`/`StubFinder`, and corresponding assertions. `example.invalid` is a placeholder.

**Never** point Stub Runner at `com.example.contracts:shared-contracts:1.4.0` and treat it as a producer-verified stub.

### Three repository URLs with distinct roles

| Configuration location | Meaning |
|---|---|
| Producer Maven `contractsRepositoryUrl` | Fetch **contract definitions** |
| Producer Gradle `contractRepository.repositoryUrl` | Fetch **contract definitions** |
| Consumer Stub Runner `repositoryRoot` | Fetch **producer stub artifacts** |

An organization may share a single Nexus/Artifactory instance, yet must track the exact path, permissions, and artifact fetched at each step.

For HTTP, the client must call the exact Stub Runner URL/port, not `localhost:0` or production producer. For messaging, the consumer uses `StubTrigger` and awaits handling results; a contract JAR does not create a broker or listener on its own.


## 17. Versions and Caches: Ways False Green Builds Happen

### Scenario A — New contract published, producer still uses old version

~~~text
Contract repository:
  shared-contracts 1.4.1

Producer build:
  contractDependency = shared-contracts:1.4.0

Build result:
  PASS
~~~

PASS only proves the implementation satisfies **1.4.0**; it says nothing about new requirements in 1.4.1.

### Scenario B — Same version, artifact bytes changed

~~~text
Yesterday: shared-contracts:1.4.0 = bytes A
Today:     shared-contracts:1.4.0 = bytes B
~~~

Two runners can cache differently while reporting the same version, destroying reproducibility. For releases, enforce **immutable versions**. For PR candidates, assign unique build/commit versions or verify digests.

### Scenario C — New producer, consumer still uses old stub

~~~text
Producer verifies:
  shared-contracts:1.4.1

Consumer Stub Runner loads:
  inventory-producer:2.2.0:stubs

Expected candidate producer:
  inventory-producer:2.3.0:stubs
~~~

Consumer tests can still pass because they hit a version that does not reflect the changes. Log the **actual artifact Stub Runner resolved**, not just the desired version.

### Scenario D — Gradle build cache hides skipped test execution

A Gradle test task can report `UP-TO-DATE` or restore from build cache when inputs/outputs do not reflect external contract artifact changes. When CI checks sensitive candidates, you can re-run:

~~~bash
./gradlew :inventory-producer:contractTest --rerun-tasks --no-build-cache
~~~

This is a diagnostic/short-term measure. Long-term, declare task inputs properly, enforce immutable artifact versions, and run pipelines that actively check **test count + pass/fail**.

### Scenario E — Wildcard/latest changes meaning across builds

Older docs sometimes illustrate `+`/`latest` to fetch the newest build. In CI acting as a quality gate, that makes outcomes depend on resolution timing and caches.

Replace:

~~~xml
<version>+</version>
~~~

with an explicit version:

~~~xml
<version>1.4.1</version>
~~~

and record the digest/source SHA used. For mutable `SNAPSHOT`s, isolate caches or generate unique candidate IDs to avoid cross-build contamination.

## 18. Credentials, Permissions, and Contract Repository Safety

A contract repository is typically shared across teams. Separate permissions:

| Actor | Reasonable permissions | Permissions to avoid |
|---|---|---|
| Producer CI | **Read** approved contract JARs/Git revisions | Write access to entire contract repository |
| Contract repository CI | Publish contract JAR after review | Overwriting release artifacts |
| Consumer CI | Read published/authorized candidate **producer stubs** | Release credentials |
| Producer release job | Publish verified stub after quality gate | Pushing untested builds |
| Reviewer | Review DSL/fixtures and impacted consumers list | Allowing merges just because packaging is green |

### Credentials and proxies

The Maven plugin provides options for repository username/password and proxy; Gradle has `contractRepository` with `username`, `password`, `proxyHost`, and `proxyPort` fields per the documentation.

When using them:

- Inject values from a **CI secret manager** or credential provider, never hardcode in `pom.xml`/`build.gradle`.
- Grant only read permissions needed for normal builds; release jobs hold separate write rights.
- Never embed tokens inside URLs committed to Git.
- Never print URLs containing credentials or sensitive content into logs.
- Verify TLS/CA/proxy settings in the CI environment; a developer laptop downloading an artifact does not prove a CI container can.
- Never place real user data in contract fixtures.

### Git SCM governance

- Protect the main branch; configure code owners/reviewers per producer.
- Each PR must document which consumers need changes.
- Review status codes, headers, URLs, MIME types, body field types, and messaging destinations.
- Never trigger `pushStubsToScm` automatically on untrusted PRs.
- Only allow producer CI to push mappings when generated tests PASS.
- Pin commits/tags or package versioned contract JARs so CI stays reproducible.

A separate repository does not create ownership on its own; the review process does.

## 19. Troubleshooting: Is the Bug in Source, Discovery, or Verification?

| Symptom | Possible cause | How to resolve |
|---|---|---|
| `Cannot resolve contractDependency` | Wrong group/artifact/version, URL, credentials | Check repository, coordinates, read permissions, and resolver logs |
| Contract JAR downloads yet 0 tests run | Wrong `contractsPath`, include filter dropped everything | Run `jar tf`, check nested DSL path and contract count |
| Maven still scans default folder | Plugin config in wrong module/phase | Inspect effective POM/plugin logs |
| Gradle lacks `contractTest` | Plugin not applied or task name differs by version | `./gradlew :inventory-producer:tasks --all` |
| Tests generate yet fail to compile | Base class wrong package/JUnit, missing verifier dependency | Read generated tests/imports, fix base class |
| Generated test gets 404 | Controller/fixture/path mismatch | Check test mode, MockMvc/context, and request |
| Messaging receive timeout | Trigger fails to publish or wrong binder/destination | Check `triggeredBy`, `messageFrom`, `sentTo`, and adapter |
| Git fails to fetch contracts | Missing `git://`, wrong URL/credentials | Check SCM resolver and Git logs |
| Git clones yet 0 DSL found | Wrong `META-INF/group/artifact/version/contracts` layout | Compare tree against `contractDependency` |
| Stub Runner finds contract JAR yet no stubs | Confused definitions JAR with producer `:stubs` | Publish producer stub with right classifier/version |
| Consumer gets WireMock 404 | Request did not match mapping | Check URL/headers/body and unmatched request log |
| CI green against old contract | Mutable version cache, pinned version not bumped | Log source SHA/digest, verify resolved artifact |
| Push mappings never runs | `pushStubsToScm` not invoked | Invoke only in release job after verification |
| Published stub differs from tested source | Rebuilt from different commit or stale artifact | Pin SHA/digest and promote exact candidate artifact |

### Effective debugging sequence

1. **Source:** do contracts live in a local folder, Maven JAR, or Git? Was the right version/SHA fetched?
2. **Discovery:** after fetching, which DSL files did the plugin discover? Is `contractsPath` right?
3. **Verification:** did generated tests actually run against producer code and PASS?
4. **Packaging:** does the stub artifact carry the right mappings/contracts/fixtures and `stubs` classifier?
5. **Consumption:** which artifact did consumer Stub Runner load, and what URL did the real client call?

Never loosen matchers or raise timeouts when the real cause is **failing to load the DSL**. And never switch to `latest` to mask versioning bugs.

## 20. Two-Repository, Two-Artifact CI Pipeline

A reference pipeline:

~~~mermaid
flowchart TD
    A["PR edits DSL in contract repo"] --> B["Review + validate DSL/fixtures"]
    B --> C["Package candidate contract JAR"]
    C --> D["Record artifact version + contract SHA"]
    D --> E["Producer CI fetches exact candidate"]
    E --> F["Generate/run generated producer tests"]
    F --> G{"Producer PASS?"}
    G -->|No| H["Do not publish verified stub"]
    G -->|Yes| I["Package candidate producer :stubs"]
    I --> J["Consumer Stub Runner uses exact stub"]
    J --> K{"Consumer compatibility PASS?"}
    K -->|No| L["Review breaking change/migration"]
    K -->|Yes| M["Release per policy"]
~~~

### A traceable report

~~~text
Contract source SHA:        <contract-sha>
Contract artifact:          com.example.contracts:shared-contracts:1.4.1
Contract JAR SHA-256:       <digest-A>

Producer source SHA:        <producer-sha>
Generated producer tests:   8 executed / 8 passed
Producer stub artifact:     com.example:inventory-producer:2.3.0:stubs
Stub JAR SHA-256:           <digest-B>

Consumer source SHA:        <consumer-sha>
Stub Runner resolved:       inventory-producer:2.3.0:stubs
Consumer tests:             5 executed / 5 passed

Release decision:           eligible after required approvals/gates
~~~

Values in `<...>` are placeholders for CI to populate. Spring Cloud Contract does not automatically generate full metadata matching this template.

### Two release workflows

**Contract JAR released first:** the contract repo reviews and publishes an immutable version; the producer fetches that version, implements until tests PASS, and then publishes verified stubs.

**Pre-release candidates:** CI builds a temporary contract artifact with a unique ID from the PR so producer/consumer can test early; once passing and reviewed, the release version is published.

Both must obey the rule: **never publish a verified stub before producer tests pass**. A candidate can be kept in CI/staging for debugging, but never disguised as a verified interface.

### Minimum quality gates

- Resolver fetched the exact contract artifact/SHA.
- Discovered contract count is non-zero if the module must have contracts.
- Generated producer tests actually executed and PASSED, without being skipped.
- Base test uses the right test mode, prepares fixtures, and calls real producer code.
- Stub packaging and version/digest match the tested contracts.
- Consumer Stub Runner loads the exact candidate producer stub.
- Consumer tests exercise real request/response or message handler logic.
- Breaking changes are reviewed with deployed consumers.
- Only authorized release jobs can publish verified artifacts.

## 21. Practice Exercise: JAR Resolves Yet Contract Tests Equal Zero

### Problem statement

The contract repository published:

~~~text
com.example.contracts:shared-contracts:1.4.0

JAR entries:
  com/example/inventory-producer/checkout-consumer/stockAvailable.groovy
~~~

Yet the Inventory producer module uses:

~~~groovy
contracts {
    contractsMode = 'REMOTE'

    contractDependency {
        stringNotation = 'com.example.contracts:shared-contracts:1.4.0'
    }

    contractRepository {
        repositoryUrl =
            'https://repo.example.invalid/repository/contract-definitions'
    }

    // contractsPath not declared.
}
~~~

The build downloads the JAR successfully yet yields `0 generated contract tests`. Other unit tests PASS.

**Question 1. What is the root cause?**

By default, the plugin looks for a path inferred from the group/artifact of the **contract dependency**, whereas Inventory's DSL sits under `com/example/inventory-producer`.

**Question 2. How do you fix it?**

~~~groovy
contracts {
    contractsMode = 'REMOTE'

    contractDependency {
        stringNotation = 'com.example.contracts:shared-contracts:1.4.0'
    }

    contractRepository {
        repositoryUrl =
            'https://repo.example.invalid/repository/contract-definitions'
    }

    contractsPath = 'com/example/inventory-producer'
    failOnNoContracts = true
}
~~~

You also need the plugin, base class, dependencies, and `contractTest` task properly wired for the project. `failOnNoContracts` is a safeguard, not a substitute for reading test reports.

**Question 3. Would switching to `contractsMode=LOCAL` fix it?**

No. Mode only changes the artifact source, not the nested DSL path. LOCAL also requires the JAR to actually be in the environment's Maven local repository.

**Question 4. What if producer tests FAIL after reading the right contract?**

Block stub release, investigate contract/implementation/fixture; do not silently edit the DSL to hide the mismatch without consulting the consumer.

**Question 5. What if the consumer still uses an old stub version?**

Consumer test results only prove compatibility with the old stub. Use the **candidate producer `:stubs`** from the exact verified revision.

### Extension exercise: Git SCM

The Git repository contains:

~~~text
META-INF/com.example/inventory-producer/2.3.0/contracts/
└── checkout-consumer/stockAvailable.groovy
~~~

Explain:

1. Why is the `git://` prefix needed before the Git URL?
2. Does `contractDependency` identify a JAR or locate `group/artifact/version` in the SCM tree?
3. Is `pushStubsToScm` needed to **read** contracts?
4. How does CI prove which contract commit the producer tested against?
5. Why is having DSL without a `mappings` folder valid prior to producer verification?

**Hint:** `pushStubsToScm` handles **writing** mappings after verification; it is not needed to read DSL.

### Self-check questions

- How does `contractsDirectory` differ from `contractsPath`?
- When is `contractsDslDir` used in Gradle?
- How does a contract JAR differ in responsibility from a producer `:stubs` JAR?
- Does `contractsMode=REMOTE` by itself prove the producer complies with the contract?
- Why does a shared JAR need producer and consumer folders?
- How do you detect a PASSING build that generated zero tests?
- Why doesn't a Git version folder automatically pin a commit?
- When should you use `LOCAL` vs. `REMOTE`?
- Why does a consumer test with an old stub not validate a new PR?
- When is a pipeline allowed to invoke `pushStubsToScm`?

## 22. Checklist Before Accepting a Change

- [ ] Clearly identify contract source: folder, Maven JAR, or Git SCM.
- [ ] Producer and consumer owners/reviewers exist.
- [ ] DSL and fixtures are reviewed, with no overly loose matchers eroding compatibility.
- [ ] For local folders, CI checks out the exact commit and the path exists.
- [ ] For JARs, `contractDependency` has right group/artifact/version and JAR contains real DSL entries.
- [ ] `contractsPath` points to the right nested folder, not confused with a dev machine path.
- [ ] For Git, URL has `git://` and follows `META-INF/group/artifact/version/contracts` layout.
- [ ] `contractsMode` fits LOCAL/REMOTE, credentials are provisioned securely.
- [ ] Contract version is immutable or candidate carries a unique ID/digest.
- [ ] Build logs record resolved artifact/commit/digest.
- [ ] `includedFiles`/`ignoredFiles` do not accidentally drop all contracts.
- [ ] Generated tests are generated, compiled, executed, and **PASS**.
- [ ] Tests are not skipped, and `0 tests` is not treated as success.
- [ ] Base class executes real producer code across the scope under verification.
- [ ] Producer `:stubs` are built from the exact tested contract revision.
- [ ] Verified stubs are never published while producer verification fails or hasn't run.
- [ ] `pushStubsToScm`, if used, is gated and restricted to authorized jobs.
- [ ] Consumer Stub Runner fetches **producer stubs**, not the contract definitions JAR.
- [ ] Consumer HTTP client/message handler runs against the right stub candidate.
- [ ] Breaking changes are reviewed for deployed consumers.
- [ ] CI records contract SHA, producer SHA, artifact versions, digests, and test reports.

## 23. Key Takeaways and References

**Fetching contracts from external locations or artifacts** only changes where the producer receives **DSL sources**. For folders, use `contractsDirectory` (Maven) or `contractsDslDir` (Gradle). For JARs, use `contractDependency`, `contractsMode`, repository URL, and `contractsPath`. For Git SCM, use the `git://` prefix and corresponding `META-INF/.../contracts` layout.

A contract repository helps consumers propose/review requirements, yet **the producer must still generate and run generated contract tests against the real implementation**. Only after PASS does the producer publish `:stubs`; consumers use Stub Runner with the **exact artifact version** to verify their own clients/handlers.

### Official documentation

- [Spring Cloud Contract — Common Repository with Contracts](https://docs.spring.io/spring-cloud-contract/reference/howto/how-to-common-repo-with-contracts.html): shared JAR, producer/consumer layout, and `contractsPath`.
- [Spring Cloud Contract — CDC with External Repository](https://docs.spring.io/spring-cloud-contract/reference/using/cdc-external-repo.html): how consumers propose and producers verify contracts.
- [Spring Cloud Contract — Git as Storage](https://docs.spring.io/spring-cloud-contract/reference/howto/how-to-use-git-as-storage.html): `git://` prefix, SCM layout, and `pushStubsToScm`.
- [Spring Cloud Contract — Maven Project](https://docs.spring.io/spring-cloud-contract/reference/maven-project.html): `contractsDirectory`, `contractDependency`, `contractsMode`.
- [Spring Cloud Contract — Gradle Project](https://docs.spring.io/spring-cloud-contract/reference/gradle-project.html): `contractsDslDir`, `contractRepository`, `contractsPath`, `contractTest`.
- [Spring Cloud Contract — Stub Runner Boot](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-boot.html): consumer usage of producer stubs.
- [Maven — Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html): Maven local/remote repositories.

**Practical conclusion:** whenever CI reports PASS, confirm **the DSL came from the right source/version**, **producer tests actually ran and passed**, and **the consumer uses verified stubs from that exact producer revision**. These three pieces of evidence matter far more than whether the DSL sits beside the producer or in a completely independent repository.
