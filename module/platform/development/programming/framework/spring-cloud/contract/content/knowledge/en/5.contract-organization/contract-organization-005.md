# How Path Conventions Affect Generated Tests

## Lesson Objectives

In **Spring Cloud Contract**, HTTP or messaging contracts are defined using **Groovy DSL** or **YAML DSL**, then used to generate **producer-side** tests and create stubs for the **consumer side**. However, where contract files are placed, how they are named, and which directories they are grouped into can determine:

- Whether the tooling **discovers** the contract for processing.
- Which **test group** the contract belongs to and which **base test class** it is bound to.
- The name, package, or structure of generated tests **in the Spring Cloud Contract version and configuration in use**.
- Which contracts are included in the stub bundle and later consumed via **Stub Runner**.
- Whether moving or renaming a file causes CI to silently omit tests.

The goal of this lesson in the **Contract Organization** chapter is to design paths that are clear, stable, and verifiable in CI. No folder naming convention automatically proves API compatibility; only generated tests that are actually **executed and passing** contribute to that evidence.

## 1. Distinguishing Three Commonly Confused Path Types

When inspecting a contract, distinguish among:

| Path Type | Role | Example |
| --- | --- | --- |
| **DSL file path** | Where Spring Cloud Contract locates and reads the contract definition | src/test/resources/contracts/orders/get_paid_order.yml |
| **HTTP path or message destination** | The interface the producer exposes to consumers | GET /api/orders/ORD-1001 |
| **Build output path** | Where the plugin generates tests/stubs; typically inside the build directory | target/… or build/… |

Important point: **moving a file** from the orders folder to the checkout folder **does not automatically change the URL** from /api/orders to /api/checkout. The HTTP URL is specified inside the contract body. Conversely, editing only the URL in YAML while keeping the file path unchanged can still break consumer behavior.

Path conventions primarily govern **discovery, grouping, mapping, and artifact generation**; contract content governs **integration behavior**.

## 2. Contract Root Directory: Tooling Must Find the File First

For a producer project using a typical Maven/Gradle layout, the local contracts directory is usually:

~~~text
order-service/
├── pom.xml                 # Or build.gradle
├── src/
│   ├── main/
│   │   └── java/
│   └── test/
│       ├── java/
│       └── resources/
│           └── contracts/
│               └── orders/
│                   ├── get_paid_order.yml
│                   └── get_missing_order.yml
└── ...
~~~

**src/test/resources/contracts** is the common default location when contracts live inside the producer project itself. If a team chooses another location or pulls contracts from a separate repository/artifact, the source and path must be configured for the plugin in use.

Examples of organizing contract sources:

| Contract Placement | What Must Be Ensured |
| --- | --- |
| Inside producer at src/test/resources/contracts | Plugin scans the default directory or configured directory properly |
| In a custom producer directory | Configure the corresponding DSL directory for Maven/Gradle |
| In a standalone contract artifact/repository | Configure the contract dependency/source along with the relative path inside the artifact |
| In a multi-producer monorepo | Each build selects only the contracts belonging to the producer being verified |

Across Spring Cloud Contract plugins, configuration property names vary by tool and version: for example, **contractsDirectory** in the Maven plugin context, or **contractsDslDir** in the Gradle plugin context. Options for contracts loaded from an artifact, such as the dependency source and **contractsPath**, serve a different purpose from the local DSL path. Always check the exact syntax for your **project's plugin version** before applying it.

A syntactically valid contract placed **outside the scanned directory** may be left out of the test suite. This is a dangerous failure mode because the build may still run other tests and report green.

### Lesson from a Folder Move

Suppose you change:

~~~text
src/test/resources/contracts/orders/get_paid_order.yml
~~~

to:

~~~text
src/contract-spec/orders/get_paid_order.yml
~~~

Without updating the contract source configuration, the tooling may fail to find the file at the new location. Always verify **the count of discovered contracts, the list of generated tests, and the results of actually executed tests** after a move.

## 3. Directory Grouping Conventions: By Business Domain and Integration Type

A scalable structure might look like:

~~~text
src/test/resources/contracts/
├── orders/
│   ├── http/
│   │   ├── get_paid_order.yml
│   │   ├── get_missing_order.yml
│   │   └── cancel_order.groovy
│   └── messaging/
│       └── order_paid_event.groovy
├── payments/
│   ├── http/
│   │   └── get_payment.yml
│   └── messaging/
│       └── payment_failed_event.groovy
└── shipping/
    └── http/
        └── get_shipment.yml
~~~

Here:

- **orders, payments, shipping** represent business domains well understood by the development team.
- **http** and **messaging** separate contracts needing different test setups and verification mechanisms.
- Filenames clearly reflect the **behavior** or scenario to verify, not implementation class names.

This is a **recommended project convention**, not a mandatory nested folder structure enforced by Spring Cloud Contract. A small project may need only one level; a large project may also group by consumer, interface version, or use-case category if that improves traceability.

Do not create deep folder hierarchies merely to mimic Java packages. Choose only as many levels as needed for **ownership, discoverability, test setup grouping, and change management**.

### Intentional Naming

Names should express behavior:

| Unclear Name | Purpose-Driven Name | Reason |
| --- | --- | --- |
| test1.yml | get_paid_order.yml | Easy to recognize the scenario |
| ok.yml | create_order_success.yml | Distinguishes creation from lookup |
| error.yml | get_missing_order.yml | States the error condition |
| controller_contract.groovy | cancel_order.groovy | Not coupled to an internal class name |

Use consistent naming with lowercase letters, digits, and underscores when possible. For **directory names** that may participate in generating Java packages or package mappings, prefer segments valid as Java identifiers (e.g., orders, http, messaging), avoiding spaces, hyphens, and special characters. This also avoids case-sensitivity discrepancies between Windows machines and Linux CI environments.

## 4. Relative Paths Can Affect Generated Test Structure

Depending on the Spring Cloud Contract version, DSL, and Verifier configuration, filenames, contract names, and relative directory structures can affect the **class name, method name, package, or grouping of generated tests**.

Example:

~~~text
contracts/
└── orders/
    └── http/
        ├── get_paid_order.yml
        └── get_missing_order.yml
~~~

Both contracts belong to orders/http. Whether the generator places them in one or multiple test classes, which class/method names it chooses, and how packages are structured are **details that must be confirmed from actual build output**, rather than assuming all tool versions behave identically.

What can be stated at the organizational level is: **relative paths must be controlled as an input to test generation**. If a mapping rule relies on directory structure, renaming a folder can cause tests to select the wrong base class or fail to generate as expected.

### Contract Name and Filename Do Not Substitute for Each Other

A YAML contract can include an identifying **name** field. For example:

~~~yaml
description: "Checkout views a paid order"
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

The contract above may be stored at:

~~~text
src/test/resources/contracts/orders/http/get_paid_order.yml
~~~

**name** identifies the scenario; **filename and location** organize and select source inputs; **url** is the HTTP path called by the consumer. Do not treat these three concepts as interchangeable.

If you change the filename or `name` value, re-check the generated test output. If you change `url`, check consumer impact as well because that is an HTTP interface change.

## 5. Base Test Classes and Directory-Based Mapping Rules

In producer-side contract testing, generated tests need an execution environment: initialized controllers or application context, sample data, HTTP test client setup, and sometimes a broker or message verifier. A project can define **base test classes** to prepare these conditions.

Example:

~~~text
src/test/resources/contracts/
├── orders/
│   ├── http/get_paid_order.yml
│   └── messaging/order_paid_event.groovy
└── payments/
    └── http/get_payment.yml

src/test/java/com/example/contract/
├── OrderHttpBase.java
├── OrderMessagingBase.java
└── PaymentHttpBase.java
~~~

A single shared base class can serve all tests when setup is uniform. With multiple contract groups, however, teams often need to map **each group to its own base class**, for example:

| Contract Group | Expected Base Class | Setup Responsibility |
| --- | --- | --- |
| orders/http | com.example.contract.OrderHttpBase | HTTP client/test context, order fixtures |
| orders/messaging | com.example.contract.OrderMessagingBase | Event trigger conditions and message verification |
| payments/http | com.example.contract.PaymentHttpBase | HTTP context and payment fixtures |

In Spring Cloud Contract, a project may use a global **baseClassForTests** setting or base-class selection rules such as **baseClassMappings**; some setups also support package-based base-class naming via **packageWithBaseClasses**. Exact declaration syntax and matching semantics must be verified against the active Maven/Gradle plugin.

To illustrate the idea behind **baseClassMappings**, look at the following *illustrative rule table*; it is not raw configuration syntax to paste directly into a build file:

~~~text
Contract scope             -> Selected test base class
orders/http/**             -> com.example.contract.OrderHttpBase
orders/messaging/**        -> com.example.contract.OrderMessagingBase
payments/http/**           -> com.example.contract.PaymentHttpBase
~~~

If the real configuration matches **package names** derived from paths rather than raw file paths, match expressions must follow the format accepted by the plugin, typically dots and regex. **Do not copy `/**` verbatim into a regex expression** unless the plugin defines it as a glob.

When moving a contract from orders/http to payments/http:

1. The contract may fall under a different mapping scope.
2. The generated test may extend the payment base class instead of the order base class.
3. Initialized fixtures or application beans may be wrong, causing tests to fail or verify the wrong target.
4. Fixing it by altering the URL just to make the test pass hides the root cause.

Therefore, after any directory change, inspect the **actual base class of the generated test**, rather than relying solely on a green build.

## 6. Concrete Example: Same Contract, Different Storage Location

Suppose a producer exposes:

~~~http
GET /api/orders/ORD-1001
Accept: application/json
~~~

Agreed response:

~~~json
{
  "id": "ORD-1001",
  "status": "PAID"
}
~~~

The team stores the DSL at:

~~~text
contracts/orders/http/get_paid_order.yml
~~~

Then reorganizes it to:

~~~text
contracts/checkout/http/get_paid_order.yml
~~~

Regarding the **HTTP contract**, request and response may remain unchanged. For test generation, however:

| Item | Before Moving | What to Check After Moving |
| --- | --- | --- |
| DSL discovery | Scanned under orders/http | Still scanned under checkout/http? |
| Base class | Mapped to OrderHttpBase | Still mapped accurately? |
| Package/test name | Follows current generator rule | Any unintended changes? |
| Test data | Has ORD-1001 in PAID state | Does the new fixture preserve this scenario? |
| Stub | Has mapping from the contract | Does the new stub build still include it? |
| Consumer CI | Uses stubs from verified build | Does it pull the right version of the new artifact? |

If the checkout folder means "consumer Checkout owns the contract," agree on how to handle cases where multiple consumers share the endpoint. If the orders folder means "producer/domain owns the contract," that naming usually stays more stable as the consumer list evolves. There is no single right choice for every project; clearly document the chosen **grouping axis**.

## 7. HTTP and Messaging Contracts May Need Different Base Classes

In Spring Cloud Contract, both HTTP and messaging contracts can be written in Groovy/YAML DSL, but verification differs:

- **HTTP:** generated tests send requests and compare HTTP status, headers, and body.
- **Messaging:** generated tests trigger or verify message interactions per contract; they may require message verifier/broker setup and event-emission conditions.

Example Groovy contract describing an emitted message:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description "Emit event when an order is paid"

    label "order_paid_event"

    input {
        triggeredBy("triggerOrderPaid()")
    }

    outputMessage {
        sentTo("order-events")
        body(
            eventType: "ORDER_PAID",
            orderId: "ORD-1001"
        )
        headers {
            contentType(applicationJson())
        }
    }
}
~~~

This is an **illustrative sample**. The method **triggerOrderPaid()** must be defined in the producer-side test context, and sending to **order-events** must match actual messaging configuration. Placing a Groovy contract in the right folder does not guarantee tests will run if the base class lacks the trigger method or verification infrastructure.

Grouping contracts under a messaging folder helps reviewers immediately see setup differences. Still, naming a directory messaging **does not make the tooling spin up a broker or generate the right fixtures automatically**. Base classes and tests still have to be properly configured.

## 8. Contract Paths and Stub Artifacts Are Different Concepts

Spring Cloud Contract can generate stubs/mappings from the processed contract set. Stubs are packaged and published, and **Stub Runner** lets consumers download/run stubs for integration testing.

Typical flow:

~~~mermaid
flowchart TD
    A["Contracts in scanned directory"] --> B["Spring Cloud Contract"]
    B --> C["Generated producer tests"]
    B --> D["Stubs/mappings"]
    C --> E["Run producer tests in CI"]
    D --> F["Package versioned stub artifact"]
    E --> G{"Producer evidence PASS?"}
    G -->|Yes| H["Publish verified artifact"]
    G -->|No| X["Stop, fix failure"]
    F --> H
    H --> I["Consumer uses Stub Runner"]
    I --> J["Consumer testing"]
~~~

A DSL file in the source tree has a path such as:

~~~text
src/test/resources/contracts/orders/http/get_paid_order.yml
~~~

However, Stub Runner **does not route HTTP requests by YAML file path**. It runs the generated stubs; requests are matched by HTTP specification (e.g., GET /api/orders/ORD-1001) and stub matching rules. Physical paths inside the stub artifact, mapping folder names, and filenames inside the JAR are **tool-generated outputs** that may differ from the original DSL layout.

Therefore, after changing contract file paths:

- Confirm the producer still discovers and verifies the contract.
- Confirm the new stub artifact actually contains the expected mappings/definitions.
- Run consumer tests against the **new, explicitly pinned stub version**.
- Do not conclude safety from a consumer test run still reusing an old stub.

## 9. Dedicated Contract Folders and Monorepos: Identifying Each Producer's Source

In an organization with multiple producers, a shared contract repository might look like:

~~~text
contracts-repository/
├── order-service/
│   ├── orders/http/get_paid_order.yml
│   └── orders/messaging/order_paid_event.groovy
└── payment-service/
    ├── payments/http/get_payment.yml
    └── payments/messaging/payment_failed_event.groovy
~~~

This is an **illustrative internal organization**, not a mandatory Spring Cloud Contract artifact layout.

When producer order-service pulls contracts from an external source, configuration must select only the order-service branch. Selecting the entire repository and running it on order-service could process payment-service contracts by mistake or generate unrunnable tests.

For each producer, document clearly:

| Setting to Manage | Purpose |
| --- | --- |
| Contract source (local or external) | Specifies where to locate DSL files |
| Contract source version | Ensures reproducible testing |
| Relative path within source | Selects only contracts belonging to that producer |
| Base class rules | Selects the right setup for each contract group |
| Stub artifact name, version, and coordinates | Lets consumers pull the right verified stubs |

When contracts are loaded from an artifact, the path inside the artifact and the local source path **do not necessarily match**. Check the active plugin configuration rather than assuming every repository is scanned from src/test/resources/contracts.

## 10. CI Must Catch Contracts That "Fall Out" of Test Generation

A wrong path is sometimes more dangerous than a failing test: a test that is never generated cannot report a failure.

A verification workflow after path changes can be structured as follows:

~~~mermaid
flowchart TD
    A["Change/move contract directory"] --> B["Check contracts root configuration"]
    B --> C["Regenerate tests from current contracts"]
    C --> D{"Expected contracts/tests present?"}
    D -->|No| X["BLOCK: find why tests are missing"]
    D -->|Yes| E["Check test package/base class"]
    E --> F{"Setup accurate?"}
    F -->|No| X
    F -->|Yes| G["Run producer contract tests"]
    G --> H{"PASS?"}
    H -->|No| X
    H -->|Yes| I["Inspect generated stubs"]
    I --> J["Consumer tests right stub version"]
~~~

What to monitor is not just a static test count. One file can declare multiple scenarios, and generated test structure varies across configurations/versions. Better yet, compare the **expected list of contracts** against **the scenarios actually processed**.

A helpful CI record might look like:

~~~yaml
# Team-designed verification log template,
# not a default Spring Cloud Contract configuration.
contract_source_revision: contracts-commit-abc123
producer_revision: producer-commit-def456
expected_contracts:
  - orders/http/get_paid_order.yml
  - orders/http/get_missing_order.yml
  - orders/messaging/order_paid_event.groovy
generated_tests_reviewed: true
base_class_mapping_reviewed: true
producer_contract_tests: PASS
stub_artifact_version: 2.4.0
consumer_stub_tests: PASS
~~~

If a path moves from orders/http to checkout/http, both the expected contracts list and base class mappings need review. **Never automatically remove a contract from the expected list just to make CI green.**

### Essential Practical Checks

1. **Verify root:** the generator scans the right contracts directory after configuration changes.
2. **Verify discovery:** every new, renamed, or moved contract appears in generation output.
3. **Verify tests:** inspect actual generated tests, package names, and selected base classes.
4. **Verify execution:** generated tests actually run on the producer rather than being skipped or filtered out.
5. **Verify stubs:** the new artifact contains the exact scenarios consumers need.
6. **Verify CI:** consumers use the exact stub artifact version rather than drifting to an older or uncontrolled latest version.

With Maven/Gradle, generated outputs typically reside in the respective build directory (`target` or `build`), though **specific task/goal names and subdirectories depend on the plugin version**. When verifying, check test-generation logs and output files of the actual build you are running.

## 11. Common Errors and How to Fix Them

| Symptom | Possible Path-Related Cause | How to Verify/Fix |
| --- | --- | --- |
| Added a contract, no new test appears | File is outside the contracts root | Check effective root, source config, and list of read DSL files |
| Test generated but fails to compile | Wrong package or incompatible base class | Inspect generated test, baseClassForTests/baseClassMappings |
| Test uses wrong fixture after folder move | Directory-based mapping rule changed | Adjust mapping; verify actual base class |
| HTTP tests pass while message test fails | Message contract picked up HTTP setup | Group and map base class suited for messaging |
| Linux CI fails while Windows passes | Case sensitivity or path separator differences | Normalize names and check paths for CI environment |
| Generated tests exist, CI does not run them | Filters, tasks, or source-set/test engine exclude generated tests | Check test runner and executed test count reports |
| Consumer test passes only with old stub | Artifact/version not updated after contract change | Regenerate stub, pin version, and rerun consumer tests |
| Stub fails to match despite file in right folder | DSL method/path/header/body matchers do not fit real request | Inspect contract content and generated mapping |
| Two contracts share the same name | Unclear naming or naming rule causes collision in scope | Assign distinct scenario names; inspect test/artifact generation errors |

Never fix a path error by altering business behavior in the contract, disabling tests, or manually editing generated tests. Generated tests are **build outputs**; the source to fix is normally the DSL, discovery/mapping configuration, or base test class setup.

## 12. Hands-On Exercises

### Exercise A — Diagnosing an Undiscovered Contract

A project has its contracts root configured as src/test/resources/contracts. A teammate adds:

~~~text
src/test/resources/contract/orders/create_order.yml
~~~

The build stays green and no new test appears for create_order.

**Task:** Identify the mistake, explain how to confirm the new test was actually generated, and explain why a green build status must not be treated as proof of compatibility.

**Hint:** The folder name contract differs from contracts. Move it to the right location or reconfigure the root intentionally, then inspect both the presence and execution of the generated test.

### Exercise B — Moving a Contract Causes Wrong Base Class Selection

A team has two groups: orders/http and orders/messaging. A contract order_paid_event.groovy is moved from messaging to http, while its content still describes an event.

**Task:** Outline what must be inspected in generated tests, fixtures, message verification, and stub artifacts before approving the change.

**Hint:** Review base class mapping rules: message tests may require a dedicated trigger method and verifier. Do not convert the contract to HTTP merely because the new folder is named http.

### Exercise C — Changing Folder While Keeping the API

The contract get_paid_order.yml moves from orders/http to checkout/http with no change to request or response. CI generates tests in a different package, and old filter configurations omit those tests from running.

**Task:** Distinguish a test-structure change from an API-behavior change; propose verification steps before declaring the producer compatible.

**Hint:** The API did not change, yet verification evidence is missing because tests did not execute. Fix test discovery configuration, rerun producer tests, verify stub generation, and run consumer tests against the proper artifact.

## 13. Checklist When Organizing or Changing Contract Paths

- [ ] Every Groovy/YAML contract sits in the configured source and contracts root.
- [ ] Directory structure reflects business domain or integration type per an agreed convention.
- [ ] Folder names are valid when used for package generation or base-class mapping.
- [ ] Filenames and contract name fields clearly describe scenarios without ambiguity or collisions.
- [ ] File paths, HTTP URLs, and message destinations are clearly distinguished.
- [ ] baseClassForTests or baseClassMappings still resolves the right base class for each group.
- [ ] Generated tests are both generated **and executed**, not merely sitting in the build directory.
- [ ] After moving folders, processed scenarios are compared to catch tests dropped from generation.
- [ ] Stubs are generated/packaged from the exact contract revision and verified producer build.
- [ ] Consumers retest against an explicit stub version via Stub Runner.
- [ ] CI runs cleanly on the target environment, accounting for OS path differences.
- [ ] All organizational changes have been reviewed for impact on tests, fixtures, and contract ownership rules.

**Key takeaway:** In Spring Cloud Contract, path conventions are part of the **test generation and organization system**. Putting DSL files in the right spot is only the first step; verify that they are discovered, bound to the right base class, produce the expected tests/stubs, and execute in CI. Only with that evidence can restructuring or scaling directories avoid silently losing the ability to detect incompatible API changes.
