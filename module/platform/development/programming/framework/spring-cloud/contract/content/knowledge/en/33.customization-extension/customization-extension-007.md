# Customizing WireMock While Preserving Contract Source Traceability

## 1. Problem: More Flexible Stubs That Lose Connection to the Contract

**Spring Cloud Contract (SCC)** helps producer and consumer teams agree on HTTP or messaging behavior via a **Groovy/YAML DSL**. From a contract, Contract Verifier generates tests to verify the **real producer implementation**; the tool can also generate **WireMock stubs**, packaged as an artifact for consumers to run via **Stub Runner** in CI. This workflow detects incompatible API changes before release.

WireMock offers far more than static JSON responses: response templating, custom response transformers, extended request matching, mapping priority, scenario state, latency, and network faults. These customizations are valuable when consumers need to test dynamic data or failure cases. Yet editing stubs directly without tying them back to the contract source can create a dangerous situation:

- Inventory Service's contract promises `GET /api/inventory/SKU-123` returns `available:true`.
- Generated producer tests confirm the controller/service returns that exact body.
- A team manually edits the WireMock mapping to return `available:false` or renames the field to `inStock`.
- Checkout Service tests against the edited stub and passes against an interface **different from the contract verified by the producer**.
- The pipeline declares “compatibility verified” yet cannot trace which revision the response actually came from.

The risk grows even larger when a global extension alters statuses, bodies, or headers on **every** mapping, when a catch-all stub overrides contract-generated mappings, or when Stub Runner is still serving a stale artifact.

**Goal of this lesson:** customize WireMock to expand testing capability **without breaking the traceability chain**:

~~~text
Contract source + producer commit
    → generated producer tests
    → generated WireMock mappings
    → versioned, reviewed customization
    → stubs artifact with clear provenance
    → Stub Runner with exact candidate
    → real consumer client/handler
    → test report and compatibility decision
~~~

This lesson belongs to the **Customization and Extension** chapter, focusing specifically on **“Customizing WireMock While Preserving Contract Source Traceability”**.

### After This Lesson, You Will Be Able To

1. Distinguish **contract source**, **generated mapping**, **custom mapping**, **WireMock extension**, and **stub artifact**.
2. Clarify which customizations represent **promised API behavior** versus **test harness/resilience tests**.
3. Use request matching, mapping priority, response templating, metadata, and scenarios without masking vital contract constraints.
4. Organize customizations in source control rather than hand-editing generated outputs under `target`/`build`.
5. Record stubs artifact provenance by contract revision, producer commit, extension version, and checksum.
6. Distinguish a self-managed WireMock server from the WireMock created by **Stub Runner**, avoiding configuring the wrong instance.
7. Write control tests proving custom mappings do not turn invalid requests into passing responses.
8. Wire generation, verification, packaging, provenance, and consumer compatibility into reproducible CI.

## 2. Five Distinct Artifacts: Do Not Call Everything a “Stub”

| Artifact | Origin | Role | Risk if Conflated |
|---|---|---|---|
| **Contract DSL** | `src/test/resources/contracts` or agreed contract repo | Declares producer–consumer interface | Editing mappings without updating the contract |
| **Generated producer test** | SCC Contract Verifier | Verifies producer implementation satisfies DSL | Skipping tests or faking producer while staying green |
| **Generated WireMock mapping** | SCC stub generator | Gives consumer an HTTP model matching the DSL | Hand-editing and losing regenerability |
| **Custom WireMock config/extension** | Team-owned test harness code and config | Templating, matchers, state, faults, auxiliary headers... | Altering semantics without API-change review |
| **Stubs artifact + Stub Runner** | Packaged/published JAR loaded into WireMock runtime | Distributes and serves mappings to consumers | Running the wrong build, version, or mapping |

**The contract is the source of agreement**, generated output is the product of a specific generator version, and customization is an **intentional input** to stub creation/execution. Each piece needs its own location, ownership, and evidence.

Never say “contract passed” to describe a WireMock server running consumer-authored mappings. Such tests can help design interfaces, yet **they do not prove the real producer satisfies the contract**.

## 3. Three Customization Scopes to Separate by Policy

| Customization Category | Examples | Public Contract Change? | How to Verify |
|---|---|---|---|
| **Contract-owned behavior** | Status, JSON schema, error codes, required headers, request matching | **Yes**, if behavior changes | Edit/review in Groovy/YAML DSL; generated producer + consumer tests |
| **Semantics-preserving simulation** | Echoing correlation IDs, format-compliant response templating, dynamic data within allowed domains | **Maybe not**, yet still requires checks | Assert contract invariants and check mapping output against expected behavior |
| **Test harness / resilience** | 2-second delay, connection reset, injected 503, simulated scenario state | Usually **not** promised by the producer API | Label test-only, run in separate suite, never replace baseline contract stubs |

For instance, testing client retries when WireMock simulates a connection reset is useful, yet **you cannot infer that the producer promises to reset connections**. A fault-injection test must never masquerade as a “producer-verified contract” artifact.

Design rule: **if a customization changes which requests are accepted or what responses consumers observe on the public interface, treat and review it as a contract change**.

## 4. Provenance-Preserving Architecture

~~~mermaid
flowchart TD
    A["Producer commit P and contract revision C"] --> B["SCC Contract Verifier"]
    B --> D["Generated producer tests"]
    B --> M["Generated WireMock mappings"]
    D --> G{"Executed tests > 0, all pass?"}
    G -- "No" --> X["BLOCK"]
    G -- "Yes" --> H["Build candidate"]
    M --> H
    E["Reviewed WireMock customizations revision W"] --> H
    H --> I["Stubs JAR candidate, digest, and manifest"]
    I --> J["Maven-compatible repository"]
    J --> K["Stub Runner resolves exact candidate"]
    K --> L["WireMock loads mappings + extensions"]
    L --> N["Real consumer HTTP client"]
    N --> O{"Compatibility tests pass?"}
    O -- "No" --> X
    O -- "Yes" --> Q["Release policy + audit record"]
~~~

At each step, answer:

- **P:** which producer code commit was tested?
- **C:** which contract DSL revision/hash was the source?
- **W:** which customization source and binary version were used?
- **I:** what exact contents and digest does the candidate JAR hold?
- **K–L:** which artifact did Stub Runner resolve and what did WireMock load?
- **N–O:** which consumer version ran the real client, and with what assertions?

A label like `1.4.0-SNAPSHOT` alone cannot identify **I**; a mutable SNAPSHOT can point to different builds over time.

## 5. End-to-End Example: Inventory and Checkout

Checkout Service needs:

~~~http
GET /api/inventory/SKU-123 HTTP/1.1
Accept: application/json
X-Correlation-Id: req-1001
~~~

Inventory Service promises for fixture `SKU-123` with quantity 12:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
X-Correlation-Id: req-1001

{"sku":"SKU-123","available":true,"quantity":12}
~~~

Suppose the correlation ID is echoed from the request and other SKUs may carry different values. We have two goals:

1. **Preserve contract invariants:** method/path/status, types/semantics of `sku`, `available`, `quantity`, and critical headers.
2. **Increase stub flexibility:** accept varying correlation IDs or respond to error scenarios triggered by consumer tests.

Never “solve” goal 2 by deleting all request matchers or making response bodies return samples detached from producer behavior.

## 6. Groovy Contract as the Source of Public Behavior

Example file `src/test/resources/contracts/inventory/get-stock.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Checkout checks inventory for SKU-123'

    request {
        method GET()
        url '/api/inventory/SKU-123'
        headers {
            header('Accept', 'application/json')
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-123',
            available: true,
            quantity: 12
        )
    }
}
~~~

An equivalent YAML form:

~~~yaml
description: Checkout checks inventory for SKU-123
name: get_stock_sku123

request:
  method: GET
  url: /api/inventory/SKU-123
  headers:
    Accept: application/json

response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    available: true
    quantity: 12
~~~

These two examples are **alternatives** for the same scenario; do not commit both and generate duplicate mappings.

**Important note:** the correlation header from the HTTP snippet in Section 5 is not yet in this contract. If the consumer truly relies on the **producer echoing `X-Correlation-Id`**, that is **public behavior that must be added to the contract/review and producer verification**, not merely a stub-side response transformer.

## 7. Generated Mappings: Inspect Output, Never Edit as Source

From the contract, SCC may produce a WireMock mapping like:

~~~json
{
  "request": {
    "method": "GET",
    "url": "/api/inventory/SKU-123"
  },
  "response": {
    "status": 200,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "sku": "SKU-123",
      "available": true,
      "quantity": 12
    }
  }
}
~~~

**This is an illustrative structure.** Actual mappings may use `body` instead of `jsonBody`, add request headers/regex/JSONPath/metadata, or sit in different folder layouts depending on SCC/WireMock versions. Always **open the actual generated file** to confirm.

A mapping like this is a generation output. If you edit it directly in `target`/`build`:

- The next `clean` wipes your edits.
- Producer tests still validate the old contract while the consumer stub serves different behavior.
- You cannot reproduce the JAR from committed source code/versions.
- Reviewers cannot see the real delta if outputs stay out of Git.
- Build caches may restore a mapping from the wrong revision.

**Principle:** generated mappings are **derived artifacts**, not manual edit targets. If behavior belongs to the contract, edit the DSL; if it belongs to the test harness, commit customizations in a dedicated place with clear ownership and tests.

## 8. Minimum Traceability for a Mapping

For every important stub, you should be able to trace:

| Detail | Example | Source |
|---|---|---|
| Producer service | `inventory-service` | Artifact identity / CI |
| Contract source path | `contracts/inventory/get-stock.groovy` | Contract repository |
| Contract revision | Commit/hash `a1b2c3d4` | Git / contract artifact |
| Generated mapping identifier | `get-stock-sku123` or file path | SCC generation |
| Generator/plugin version | SCC build plugin version | Build metadata |
| Customization version | `wiremock-fixtures@c2d3e4` | Git module / build |
| Stub coordinates | `com.example:inventory-service:1.4.0-rc.pr173:stubs` | Repository |
| Stub digest | SHA-256 of packaged JAR | Producer CI |
| Consumer resolution | Exact version/digest downloaded by Stub Runner | Consumer CI |
| Consumer test | Checkout build/commit, scenario report | Test runner |

Never rely solely on a `generated by SCC` comment inside a mapping: comments may be incomplete, mappings can be overwritten, and they never identify which JAR actually ran.

Depending on your registry/pipeline capabilities, provenance can live **inside the artifact, in mapping metadata, or in a sidecar attestation/report**. What matters is verifying **digest and revision** after packaging.

## 9. Source Ownership Rules for Customizations

A *suggested* layout inside the producer repository:

~~~text
inventory-service/
├── pom.xml  (or build.gradle)
├── src/test/resources/contracts/inventory/
│   ├── get-stock.groovy
│   └── sku-not-found.yml
├── src/test/java/com/example/inventory/
│   └── ContractTestBase.java
├── src/test/java/com/example/inventory/wiremock/
│   └── InventoryWireMockCustomizerTest.java
└── src/test/resources/wiremock-custom/
    ├── README-as-policy-example.txt
    ├── resilience/
    │   └── connection-reset.json
    └── scenarios/
        └── reservation-state.json
~~~

This layout only illustrates **source classification**; SCC does not automatically package these custom folders by default. To include custom mappings inside the stubs JAR, configure **deliberate resource copying/merging** per your actual plugin/build and inspect the final artifact. Never create a custom folder and assume Stub Runner magically finds it.

You can house customizations in a separate test-support module/repository, provided versions are pinned alongside the producer candidate and resilience-only fixtures are clearly labeled.

## 10. Option 1: If Expressible in Contract DSL, Prefer the DSL

If the requirement is for the producer to return 404 when a SKU does not exist, declare it in the contract, for example:

~~~yaml
description: SKU does not exist

request:
  method: GET
  url: /api/inventory/SKU-404

response:
  status: 404
  headers:
    Content-Type: application/json
  body:
    code: SKU_NOT_FOUND
    message: SKU does not exist
~~~

**Do not hand-write a replacement WireMock mapping** just to describe this 404. Putting the behavior in the DSL provides dual evidence from a single source:

- Generated producer tests check that the **Inventory implementation** returns 404 and the error body.
- Generated stubs expose that exact behavior to Checkout consumer tests.

If someone edits the mapping alone to `ITEM_NOT_FOUND`, producer tests no longer verify what the consumer sees—one of the easiest ways to create “two truths”.

Prefer the DSL for methods, URLs, query/header/body matchers, statuses, headers, expected bodies, enum/error codes, and all HTTP/message behaviors supported by your SCC version.

## 11. Option 2: Response Templating When Data Is Genuinely Dynamic

WireMock supports **response templating** (commonly Handlebars-based) to compute responses from request data. Example test harness mapping echoing a correlation header:

~~~json
{
  "name": "inventory-correlation-example",
  "request": {
    "method": "GET",
    "url": "/api/inventory/SKU-123",
    "headers": {
      "X-Correlation-Id": {
        "matches": "req-[0-9]{4,}"
      }
    }
  },
  "response": {
    "status": 200,
    "headers": {
      "Content-Type": "application/json",
      "X-Correlation-Id": "{{request.headers.X-Correlation-Id}}"
    },
    "jsonBody": {
      "sku": "SKU-123",
      "available": true,
      "quantity": 12
    },
    "transformers": ["response-template"]
  }
}
~~~

**This is an illustrative WireMock mapping**, not a default SCC-generated mapping. Template expression syntax, header lookups, transformer names, and per-property templating must be verified for your chosen WireMock version. Use `body` as a template string if `jsonBody` is not processed as expected in your version/harness.

Response templating fits well when:

- Echoing a contract-promised correlation ID;
- Generating dynamic responses within allowed format/semantics;
- Reducing mapping duplication without loosening request matchers;
- Producing rule-based test fixture data.

**Never use templating to “invent” a business response unverified by producer verification.**

## 12. Escaping, Injection, and Template Determinism

Reusing request data inside responses is convenient, yet carries risks:

- A value containing quotes can break JSON if interpolated straight into `body` without escaping.
- Context-inappropriate template helpers can produce invalid HTML/JSON.
- Echoing raw authorization tokens, passwords, or PII from requests into responses/logs leaks sensitive data.
- Random/time helpers create nondeterministic output, making tests flaky when fixtures require exact values.
- Custom helpers might access unauthorized data sources in the test environment.

When using templates:

1. Constrain request inputs with matchers/validation per the contract.
2. Escape/serialize data for **JSON context**, never via naive string concatenation.
3. Echo only contract-permitted fields; never echo secrets.
4. Use deterministic seeds/clocks when reproducibility is needed.
5. Write negative tests with quotes, newlines, Unicode, long strings, and special characters.
6. Record template engine/extension versions in build metadata.

A template echoing `X-Correlation-Id` only simulates behavior; if that is a public promise, prove the **real producer** echoes it too via generated tests or integration assertions.

## 13. Mapping Priority: Custom Fallbacks Must Never Swallow Contract Mappings

WireMock supports **mapping priority**; normally, **lower priority numbers take higher precedence**. Specific mapping example:

~~~json
{
  "name": "inventory-contract-specific",
  "priority": 1,
  "request": {
    "method": "GET",
    "url": "/api/inventory/SKU-123"
  },
  "response": {
    "status": 200,
    "jsonBody": {
      "sku": "SKU-123",
      "available": true,
      "quantity": 12
    }
  }
}
~~~

A separate fallback for the test harness:

~~~json
{
  "name": "inventory-unmatched-fallback",
  "priority": 10,
  "request": {
    "method": "ANY",
    "urlPathPattern": "/api/inventory/.*"
  },
  "response": {
    "status": 501,
    "jsonBody": {
      "code": "STUB_NOT_CONFIGURED"
    }
  }
}
~~~

**Warning:** `method: "ANY"` or regex in fallbacks must be checked against your WireMock version's syntax and behavior. When uncertain, use explicit methods or verify the mapping loads properly.

Goals of a fallback:

- Explicitly signal “request outside the contract” when tests make wrong calls;
- Never fabricate a fake 200 business success;
- Hold lower priority than specific mappings;
- Never replace contracted business 404s or 422 validations;
- Serve as a **diagnostic fixture**, never assumed to represent producer behavior.

If a fallback returns `200 {"available":true}` for every path, consumer tests pass even when the client sends wrong URLs—an anti-pattern to eliminate.

## 14. Test Fallbacks with Invalid Requests to Catch “False Greens”

To validate fallbacks and mapping priorities, do not send only valid requests. Intentionally send:

~~~text
GET /api/inventory/SKU-123      -> 200 + contract body
GET /api/inventory/NOT-A-SKU     -> must not falsely match SKU-123 success
POST /api/inventory/SKU-123     -> must not falsely match GET mapping
GET /api/inventory/SKU-123?x=1  -> check query parameter policy
GET /wrong/inventory/SKU-123    -> must not return 200 inventory
~~~

If a fallback is active in the test environment, ensure **unmatched errors** are reported clearly (ideally with a diagnostic status distinct from business responses) so consumer tests never mistake them for a valid `SKU_NOT_FOUND` from the producer.

**Never rely on HTTP status code alone:** a WireMock unmatched 404 is not a business 404. Error-handling tests must assert **error codes/bodies** and inspect the request journal when needed.

A strong control test also verifies which mapping matched by **ID/name/metadata** or via the request journal, depending on your WireMock version's API. That proves not only that 200 returned, but **which exact mapping** served it.

## 15. Mapping Metadata: Tagging Provenance Without Treating Labels as Sole Proof

WireMock allows storing **metadata** on mappings, useful for citing sources:

~~~json
{
  "name": "inventory-stock-sku123",
  "metadata": {
    "purpose": "contract-generated-or-reviewed",
    "contractSource": "contracts/inventory/get-stock.groovy",
    "producerService": "inventory-service",
    "scenarioId": "INV-STOCK-001",
    "owner": "inventory-api-team"
  },
  "request": {
    "method": "GET",
    "url": "/api/inventory/SKU-123"
  },
  "response": {
    "status": 200,
    "jsonBody": {
      "sku": "SKU-123",
      "available": true,
      "quantity": 12
    }
  }
}
~~~

Metadata is **descriptive**, not self-proving that the cited source actually generated the mapping. Someone could copy the wrong `contractSource` into another file. Therefore:

- Use metadata to **cross-reference/index** mappings.
- Record **contract revisions/hashes** and candidate artifact provenance at the CI level.
- Compare mappings present in the JAR against the expected contract list.
- Emit metadata during a controlled build step rather than trusting hand-typed tags.
- Compute artifact digests **after** packaging all metadata and customizations.

If the generator does not add metadata to mappings by default, maintain an **external manifest**: map `mapping file → contract source → customization source`. This avoids manually editing generated files.

## 16. Never Use Metadata as a Backdoor to Alter Contracts

Suppose a mapping has:

~~~json
{
  "metadata": {
    "contractSource": "contracts/inventory/get-stock.groovy"
  },
  "response": {
    "status": 200,
    "jsonBody": {
      "available": false
    }
  }
}
~~~

while the source contract promises `available=true`.

Having `contractSource` **does not make the response valid**. To adopt new behavior:

1. Update the corresponding contract DSL.
2. Have producer/consumer owners review the breaking/semantic change.
3. Run generated producer tests against the real implementation.
4. Regenerate stubs from the same revision.
5. Run consumer compatibility tests against the new candidate.

If `available=false` is only for testing Checkout out-of-stock handling, create a **dedicated contract scenario with appropriate producer state** or a clearly labeled **test-only fault/fixture**—never pass it off as the valid response for the 12-unit `SKU-123` scenario.

## 17. Custom Response Transformers: When Templating Is Insufficient

An extension can modify responses before WireMock serves them—for instance, adding a **test-harness-only diagnostic header** or transforming formats within published bounds.

WireMock exposes extension APIs for response transformers; **WireMock 2** and **WireMock 3** differ in interfaces, packages, lifecycles, and registration. The snippet below is a **conceptual illustration** following WireMock 3's `ResponseDefinitionTransformerV2` style; adapt and compile against your exact selected dependency:

~~~java
import com.github.tomakehurst.wiremock.extension.ResponseDefinitionTransformerV2;
import com.github.tomakehurst.wiremock.http.ResponseDefinition;
import com.github.tomakehurst.wiremock.http.ResponseDefinitionBuilder;
import com.github.tomakehurst.wiremock.stubbing.ServeEvent;

public final class DiagnosticTraceTransformer
        extends ResponseDefinitionTransformerV2 {

    @Override
    public String getName() {
        return "diagnostic-trace";
    }

    @Override
    public ResponseDefinition transform(ServeEvent event) {
        ResponseDefinition original = event.getResponseDefinition();

        return ResponseDefinitionBuilder.like(original)
            .withHeader("X-Test-Harness", "inventory-stub")
            .build();
    }
}
~~~

A mapping can request the transformer by name:

~~~json
{
  "name": "inventory-with-diagnostic-header",
  "request": {
    "method": "GET",
    "url": "/api/inventory/SKU-123"
  },
  "response": {
    "status": 200,
    "jsonBody": {
      "sku": "SKU-123",
      "available": true,
      "quantity": 12
    },
    "transformers": ["diagnostic-trace"]
  }
}
~~~

Key considerations:

- The extension class must be on the **classpath of the actually running WireMock instance**.
- The extension must be **registered in server configuration** per WireMock version; a name in JSON alone does not install a JAR.
- `X-Test-Harness` is an **internal test indicator**, not a producer-promised header. Never write consumer contract assertions against it unless testing the harness itself.
- A **global** transformer alters every mapping, including business error responses. Prefer **per-stub opt-in** when you do not want suite-wide impact.
- `like(original)` aims to preserve the existing response definition, yet verify behavior on your exact version—especially with body files, delays, or headers.
- When upgrading WireMock major versions, check extension APIs and generated mappings before reusing binaries.

If a transformer **changes `status`, `available`, `quantity`, or error codes**, that is a semantic change; review and verify it just like editing a contract.

## 18. A Standalone `WireMockServer` Is Not the Stub Runner Server

To see how extensions are registered on a **test-created** WireMock server, consider this conceptual snippet:

~~~java
import com.github.tomakehurst.wiremock.WireMockServer;
import com.github.tomakehurst.wiremock.core.WireMockConfiguration;

WireMockServer server = new WireMockServer(
    WireMockConfiguration.wireMockConfig()
        .dynamicPort()
        .extensions(new DiagnosticTraceTransformer())
);

server.start();

try {
    // Load mappings and run tests against this server.
    // In a real project, pick the right mapping source artifact.
} finally {
    server.stop();
}
~~~

This illustrates managing a standalone server. When consumer tests use `@AutoConfigureStubRunner`, **Stub Runner starts its own `WireMockServer`**. Registering an extension on `server` above **does not register it** on Stub Runner's managed server.

Therefore verify:

- Which WireMock server actually serves the URL called by the consumer's HTTP client?
- Does that server have the extension binary/classpath and registration config?
- Which WireMock customization hooks does your Stub Runner version support?
- If the framework exposes a customization hook, is it invoked **before mappings load**?
- Are multiple stub JARs/servers active in the same test, and which server receives the extension?

Never paste standalone `WireMockServer` startup code into a Stub Runner test thinking you customized Stub Runner. You may accidentally start **two servers** and point the client at the wrong one.

## 19. Distinguish Test-Harness Source Code from the Binary Run by Consumers

An extension involves more than a Java source file:

~~~text
customization source revision W
    ↓ compile/package
extension binary E + dependency versions
    ↓ wiremock runtime classpath
WireMock instance + registered extension
    ↓
effective mapping behavior
~~~

When recording provenance, capture at minimum:

- Source revision of the custom transformer/matcher;
- WireMock dependency version compatible with the binary;
- Hash/version of the extension JAR or test-support module;
- Configuration registering the extension with Stub Runner/WireMock;
- Which mappings activate that transformer;
- Test reports proving behavior with the extension enabled and disabled.

A stubs JAR containing **JSON mappings with `"transformers":["diagnostic-trace"]`** is insufficient if the runtime lacks the extension. Consumer CI must fail loudly rather than silently ignoring the transformer and serving default or fallback responses while marking the suite green.

## 20. Custom Request Matchers: Extend Without Making Every Request Valid

WireMock supports custom request matchers when default method/path/header/JSONPath matchers fall short—such as validating experimental request signatures or cross-checking fields.

A proper matcher returns **match/no-match** strictly per contract rules. However, custom matchers can also become overly permissive:

~~~text
Wrong:
  isMatch(request) = true

Intended:
  isMatch(request) =
    method = POST
    AND path = /api/reservations
    AND Content-Type is application/json
    AND sku matches promised format
    AND quantity is an integer within valid range
~~~

If using a custom matcher for HMAC signatures:

- Manage test secrets securely; never hardcode production credentials.
- Define strict body/header canonicalization; never compare raw body strings if JSON permits key reordering.
- Write negative tests for bad signatures, missing timestamps, altered bodies, and out-of-window replays.
- Keep matching fast and side-effect-free.
- Record extension version/owner and where it is applied.

`RequestMatcherExtension`/`MatchResult` APIs vary across WireMock versions; this lesson presents **extension contracts at the functional level** to avoid prescribing an incompatible signature for an unspecified version.

Never use a custom matcher to **bypass** constraints that the original DSL expresses clearly and verifiably.

## 21. Stateful Scenarios: Simulating Sequences, Always Resetting

WireMock supports **scenario states** to vary responses across sequential calls. Example test journey:

~~~text
Started
  GET /api/inventory/SKU-123 -> 200 available=true
  -> transitions to Depleted

Depleted
  GET /api/inventory/SKU-123 -> 200 available=false
~~~

Illustrative mapping for the initial call:

~~~json
{
  "name": "inventory-started",
  "scenarioName": "inventory-depletes",
  "requiredScenarioState": "Started",
  "newScenarioState": "Depleted",
  "request": {
    "method": "GET",
    "url": "/api/inventory/SKU-123"
  },
  "response": {
    "status": 200,
    "jsonBody": {
      "sku": "SKU-123",
      "available": true,
      "quantity": 1
    }
  }
}
~~~

Mapping for the subsequent state:

~~~json
{
  "name": "inventory-depleted",
  "scenarioName": "inventory-depletes",
  "requiredScenarioState": "Depleted",
  "request": {
    "method": "GET",
    "url": "/api/inventory/SKU-123"
  },
  "response": {
    "status": 200,
    "jsonBody": {
      "sku": "SKU-123",
      "available": false,
      "quantity": 0
    }
  }
}
~~~

This is a **WireMock test scenario**; it does not prove Inventory actually decrements quantity on GET. If the business contract states GET is read-only, simulating a GET depleting stock **misrepresents producer semantics** and should only be used for clearly labeled client-resilience tests.

To avoid false failures or false PASSes:

- Reset scenario state between tests;
- Never let test A leave `Depleted` behind for test B;
- Never run parallel tests against the same stateful WireMock instance without isolation;
- Never use scenario states to fake producer state transitions that haven't been verified on the producer.

**Stateful stubs test consumer behavior**; producer state transitions must be verified in dedicated producer tests/integration tests.

## 22. Latency, Fault Injection, and HTTP 503: Distinguish Testing from Contracts

WireMock can delay responses or simulate network faults:

~~~json
{
  "name": "inventory-delayed-test-only",
  "request": {
    "method": "GET",
    "url": "/api/inventory/SKU-123"
  },
  "response": {
    "status": 200,
    "fixedDelayMilliseconds": 1500,
    "jsonBody": {
      "sku": "SKU-123",
      "available": true,
      "quantity": 12
    }
  }
}
~~~

Illustrative fault injection:

~~~json
{
  "name": "inventory-reset-test-only",
  "request": {
    "method": "GET",
    "url": "/api/inventory/SKU-123"
  },
  "response": {
    "fault": "CONNECTION_RESET_BY_PEER"
  }
}
~~~

Verify these settings against your running WireMock version. Specifically, **connection reset is not HTTP status 503**: clients typically receive a transport exception, whereas 503 is an HTTP response returned by the server.

Keep goals and conclusions accurate:

| Fixture | What It Tests | What It Does Not Prove |
|---|---|---|
| 1,500 ms delay | Consumer timeout/latency handling | Real producer has 1,500 ms latency |
| Connection reset | Retries/circuit breakers on dropped connections | Producer promises to reset connections |
| Contract 503 + `INVENTORY_UNAVAILABLE` | Consumer handling of contracted business/service errors | All network failures return 503 |
| 200 with contract body | Happy-path compatibility | Production timeouts, brokers, or databases |

If fault/resilience mappings coexist with baseline mappings, **isolate them by test suite, scenario, port, or test-only header**. Never let a high-priority global fault hijack baseline contract stubs.

## 23. Mapping Collisions: When Two Stubs Match One Request

When merging generated and custom mappings, it is easy for two entries to match the same request:

~~~text
Generated:
  GET /api/inventory/SKU-123 -> 200 available=true

Custom:
  GET /api/inventory/SKU-123 -> 200 available=false
~~~

If priorities and match conditions fail to disambiguate, **serving order becomes unpredictable**. A custom mapping with accidentally higher priority can shadow a generated mapping. Consumer tests see a different response while reports still cite “the right stub artifact version”.

To control collisions:

1. Inventory generated and custom mapping IDs/names along with method/path/header/body predicates.
2. Check any mapping pairs with **overlapping request sets**.
3. Set priorities deliberately; remember lower numbers normally win.
4. Enable custom behavior only behind an explicit discriminator (test-only header, separate port, scenario state, or isolated suite).
5. Avoid catch-all 200 successes, especially in fallbacks.
6. Write tests sending requests **capable of matching both** to prove the right mapping wins.
7. Run negative tests with missing headers or wrong paths.
8. Inspect the request journal and which mapping actually served the response.

For the same contracted business behavior, **never maintain two conflicting mapping sources**. Put the agreed behavior into the contract DSL and regenerate.

## 24. Dynamic Mappings via Admin API: Convenient Yet Hard to Reproduce

WireMock exposes a runtime mapping API allowing tests to add or alter stubs while running. Useful for specialized setups, yet when used carelessly:

- Test A adds a mapping, and Test B accidentally reuses it;
- CI archives the JAR without archiving mappings added imperatively in code;
- Exact per-request responses become irreproducible;
- Runtime admin state mutates while the artifact digest stays identical;
- Tests pass locally yet fail when run in parallel.

Safe usage:

- Keep dynamic mapping definitions under version control.
- Test setup **loads deterministic fixtures** from versioned sources/manifests.
- Reset mappings/scenarios cleanly in test lifecycle hooks before and after each test.
- Log IDs/versions of programmatically added mappings.
- Never accept ad-hoc runtime mappings as **official contract sources**.
- For compatibility verification, inspect effective mappings after setup, not just the static stubs JAR.

If a response was loaded via the Admin API rather than coming from the candidate artifact, label it explicitly in reports as a **custom test fixture**, never as an SCC-generated mapping.

## 25. Customizations Belong in a Reproducible Build Graph

A sound principle:

~~~text
StubsCandidate =
    Generate(ContractSources@C, SCCPlugin@V)
    + ReviewedOverrides@W
    + StaticFixtures@F
    + BuildConfiguration@B
~~~

This is a **dependency model**, not built-in plugin syntax. Every input must be identified so artifacts can be reproduced when needed.

A build record might capture:

~~~yaml
producer:
  service: inventory-service
  commit: a1b2c3d4
contract:
  revision: a1b2c3d4
  root: src/test/resources/contracts
toolchain:
  springCloudContractPlugin: VERSION_FROM_BUILD
  wireMockRuntime: VERSION_FROM_BUILD
customization:
  revision: c2d3e4f5
  manifest: wiremock-custom-manifest
artifact:
  groupId: com.example
  artifactId: inventory-service
  version: 1.4.0-rc.pr173.a1b2c3d4
  classifier: stubs
  sha256: SHA256_FROM_PACKAGED_ARTIFACT
~~~

This is an **illustrative CI-managed manifest**, not a mandatory SCC schema. Replace `VERSION_FROM_BUILD` values from actual resolved dependencies and build config.

**Checksum rule:** compute the JAR digest **only after all customizations and internal metadata have been packaged**. Adding a provenance JSON into the JAR **after** hashing invalidates the recorded digest.

## 26. Where Should Provenance Live: Mapping Metadata, In-JAR Manifest, or Sidecar?

Three options have distinct trade-offs:

| Option | Pros | Limitations |
|---|---|---|
| `metadata` inside each mapping | Easy to tag source/scenario/owner | Can be mis-copied; generated mappings lack it by default |
| `META-INF/contract-provenance.json` inside stubs JAR | Artifact is self-describing with source/toolchain info | Must configure packaging; never assume SCC generates it |
| Sidecar provenance/attestation bound to artifact digest | Can be signed, audited, and avoids mutating the packaged JAR | Registry/CI must link sidecar unambiguously |

A pragmatic pattern uses **mapping names/metadata for per-scenario lookup** and **artifact-level sidecar/provenance records** for commits, dependency versions, digests, and build runs.

If storing a manifest **inside** the JAR, generate and package it before computing the checksum. Avoid embedding the JAR's own `artifactSha256` inside the JAR itself (which creates a circular hash problem); store the **digest in a post-packaging sidecar**.

All provenance data must originate from **trusted build inputs**, not merely user-supplied strings in a manifest.

## 27. What Gets Published: A Complete JAR, Not Loose Mappings

An example stubs artifact:

~~~text
groupId:    com.example
artifactId: inventory-service
version:    1.4.0-rc.pr173.a1b2c3d4
classifier: stubs
type:       jar
~~~

Logical filename:

~~~text
inventory-service-1.4.0-rc.pr173.a1b2c3d4-stubs.jar
~~~

Depending on SCC/plugin versions, mappings, contracts, and resources may reside under a structure resembling:

~~~text
META-INF/com.example/inventory-service/1.4.0-rc.pr173.a1b2c3d4/
  contracts/
    inventory/get-stock.groovy
  mappings/
    inventory-get-stock.json
  __files/
    inventory-response.json
~~~

**This layout is illustrative only.** Inspect the real JAR because SCC layouts, body files, and resource paths vary across versions.

When packaging customizations:

- Never reference a response body file in a mapping that is missing from the JAR.
- Never use absolute paths tied to a developer's machine.
- Never overwrite original generated mappings unintentionally.
- Never introduce duplicate mappings without deliberate priority rules.
- Never put production secrets or PII into fixtures.
- Ensure any runtime extension binary is supplied per the test runner's mechanism; **JSON inside a JAR does not bring along Java classpath dependencies**.

## 28. Inspect the Stubs JAR Before Publishing

Before consumers run Stub Runner, inspect **the exact artifact about to be published**, not merely producer sources:

~~~bash
# Replace with your actual output JAR name.
jar tf target/inventory-service-1.4.0-rc.pr173.a1b2c3d4-stubs.jar
~~~

Verify it includes all contract sources, generated mappings, `__files` referenced by `bodyFileName`, the `stubs` classifier, zero resilience fixtures leaking into baseline, zero mapping collisions, and no missing extension binaries/registrations.

Cross-check mapping counts against the **expected scenario list**. Counting JSON files alone is insufficient: one missing mapping and one stray mapping still sum to the same total. When plugins vary generated filenames/paths, use a **manifest mapping file → contract source**.

Never assume SCC automatically packages custom `wiremock-custom` folders; inspect the final JAR to verify **the exact paths Stub Runner reads**.

## 29. Digests and Candidate Versions Prove Exact Bytes

To reconcile what the producer published against what the consumer downloaded:

~~~bash
sha256sum target/inventory-service-1.4.0-rc.pr173.a1b2c3d4-stubs.jar
~~~

On Windows:

~~~powershell
Get-FileHash -Algorithm SHA256 -Path .\target\inventory-service-1.4.0-rc.pr173.a1b2c3d4-stubs.jar
~~~

A verification report should record:

~~~yaml
producerCommit: a1b2c3d4
contractRevision: a1b2c3d4
customizationRevision: c2d3e4f5
sccPluginVersion: FROM_BUILD
wireMockVersion: FROM_RUNTIME
stubArtifact: com.example:inventory-service:1.4.0-rc.pr173.a1b2c3d4:stubs
producerSha256: FROM_PACKAGED_JAR
consumerResolvedSha256: FROM_DOWNLOADED_JAR
generatedMappingCount: FROM_BUILD
loadedMappingCount: FROM_STUB_RUNTIME
~~~

`FROM_*` values are placeholders, not measured outputs. **Requirement:** the consumer's digest must match the digest published by producer CI for **that exact candidate**.

If you inject a manifest into the JAR after computing SHA-256, recompute it. Never embed the JAR's own digest **inside the JAR** in a self-referential loop; store the digest in a post-packaging sidecar attestation.

## 30. Consumer Tests Must Run the Real Client Against Stub Runner

Example in Checkout Service:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties =
    "inventory.base-url=http://localhost:18081")
@AutoConfigureStubRunner(
    ids = "com.example:inventory-service:1.4.0-rc.pr173.a1b2c3d4:stubs:18081",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.invalid/repository/candidates"
)
class InventoryConsumerCompatibilityTest {

    @Autowired
    InventoryClient inventoryClient;

    @Test
    void checkoutCanReadInventoryCandidate() {
        StockResponse stock =
            inventoryClient.getStock("SKU-123");

        assertThat(stock.sku()).isEqualTo("SKU-123");
        assertThat(stock.available()).isTrue();
        assertThat(stock.quantity()).isEqualTo(12);
    }
}
~~~

`InventoryClient` and `StockResponse` are example Checkout classes, not SCC APIs. `example.invalid` is a dummy URL; configure repository/credentials/port per project. `REMOTE` resolves from the configured repository; `LOCAL` requires the artifact installed in the runner's local store and **does not automatically share the producer's local cache**.

If a test uses `when(inventoryClient.getStock(...)).thenReturn(...)`, it **never calls WireMock**; every custom matcher/transformer in the JAR is bypassed. Compatibility suites must invoke the **real production HTTP client**.

## 31. Verify the Right WireMock Instance—Do Not Confuse Servers

A test suite may run multiple servers:

~~~text
Checkout InventoryClient -> Stub Runner Inventory:18081
Checkout PricingClient   -> Stub Runner Pricing:18082
Custom test setup        -> Standalone WireMockServer:dynamicPort
~~~

An extension takes effect only on the server **where it is registered**. To verify, log:

1. The base URL used by the real consumer client;
2. The artifact/version/digest resolved by Stub Runner;
3. The actual port and mapping count of WireMock;
4. Names/versions of extensions registered on that server;
5. Which mapping name/ID matched the request via the journal;
6. Test context lifecycle, scenario state, and startup timing.

Calling `.extensions(new MyTransformer())` on a standalone server on a different port **does not customize Stub Runner's instance**. If your SCC version exposes a customization hook, verify its API/signature for that exact version and confirm it applies to the **managed instance**.

## 32. Separate Baseline Compatibility and Resilience Tests

| Suite | Response Source | Valid Conclusion |
|---|---|---|
| Producer Contract Verifier | Real producer implementation | Producer satisfies contract scenarios |
| Consumer baseline | Candidate stubs artifact with provenance, semantics-preserving mappings | Consumer understands producer-verified contract behavior |
| Consumer resilience | Custom delay/reset/overload fixtures | Client handles simulated failures properly |
| Design preview | Consumer-authored mappings | Client handles a proposed API during development |
| End-to-end | Real producer/broker/network | Integration within environment scope |

**Passing resilience tests never replaces passing baseline compatibility.** If fault fixtures share the baseline artifact or server, enforce header/port/scenario suite isolation so faults never override generated contract mappings.

A sound report distinguishes contract-generated mappings from fault-testing mappings, and records which instance and version the consumer ran against.

## 33. Negative Tests for Request Matchers and Priority

An error-catching matrix:

| Request | Expectation | If It Falsely Returns Success |
|---|---|---|
| `GET /api/inventory/SKU-123` | Matches baseline 200 | — |
| `GET /api/inventory/WRONG` with no contract | Must not match SKU-123 baseline | URL matcher too broad |
| `POST /api/inventory/SKU-123` | Must not match GET baseline | Method matcher too loose |
| `GET /api/inventory/SKU-123` missing required header | Rejected or matched to error scenario per contract | Header matcher too loose |
| Request without test-only discriminator | Must not match fault mapping | Fault mapping enabled globally |
| Request matching both generated and custom | Test verifies which mapping won | Uncontrolled collision/priority |
| Client calls Pricing port | Fails loudly | Wrong base URL or service routing |

Not every invalid request must return 404: there may be **contracted 400/422 business validations**. What matters is **never falsely matching happy-path 200/201**.

Inspect the WireMock request journal and near-misses whenever needed to confirm **which mapping actually served** the request; HTTP status alone does not prove the intended mapping matched.

## 34. Mutation Tests: Customizations Must Never Mask Producer Bugs

On a test branch, mutate Inventory code from:

~~~java
// Correct code for fixture quantity=12:
return new StockResponse("SKU-123", true, 12);
~~~

to:

~~~java
// Intentionally broken mutation:
return new StockResponse("SKU-123", false, 12);
~~~

Generated producer tests must **FAIL** when the contract requires `available:true`. If a base test uses a fake controller always returning `true`, you get a false green. If a custom transformer rewrites `false` back to `true` along the producer test path, it masks broken behavior.

Also test mutations on the consumer/stub side:

- Change request URL to `/api/stock/SKU-123`; baseline matchers must not return success.
- Alter a required header; the stub must not accidentally match another mapping.
- Raise fault mapping priority over baseline; negative tests must catch it.
- Disable a required extension; tests must report ERROR/FAIL.
- Reference a missing response body file; artifact checks must block it.
- Point to an older candidate JAR; digest/provenance gates must block it.

Revert all mutations before merging. Keep records of **tests turning red then green again** as proof the suite detects regressions.

## 35. CI Pipeline Connecting Code, Contracts, Customizations, and Consumers

~~~mermaid
flowchart TD
    A["Producer code + contract revision"] --> B["SCC generate tests + mappings"]
    B --> C{"Producer tests executed > 0 and PASS?"}
    C -- "No" --> X["BLOCK"]
    C -- "Yes" --> D["Merge reviewed customizations"]
    E["Customization revision + extension binary"] --> D
    D --> F["Validate mappings, collisions, __files, test cases"]
    F --> G{"No unauthorized overrides?"}
    G -- "No" --> X
    G -- "Yes" --> H["Package stubs JAR candidate"]
    H --> I["Compute digest + provenance attestation"]
    I --> J["Publish immutable candidate artifact"]
    J --> K["Stub Runner resolves exact artifact"]
    K --> L["Real consumer client + negative tests"]
    L --> M{"Compatible?"}
    M -- "No" --> X
    M -- "Yes" --> N["Release quality gates"]
~~~

Minimum gates must ensure contract discovery and executed producer tests are **greater than 0**, customizations are reviewed, the JAR holds all resources, consumer-resolved artifact digests match, extensions load properly at runtime, and tests invoke the real HTTP client.

`BUILD SUCCESSFUL` matters only for checks that **actually executed**; never accept zero generated tests or mocked consumer tests as proof of contract verification.

## 36. Maven and Gradle: Merging Customizations Is a Controlled Build Step

In a Maven producer, visualize:

~~~text
Groovy/YAML contracts
 -> spring-cloud-contract-maven-plugin
 -> generated producer tests + WireMock mappings
 -> test runner checks real producer code
 -> merge reviewed custom resources
 -> package stubs JAR classifier
 -> install/deploy candidate
~~~

In Gradle:

~~~text
contracts source
 -> Spring Cloud Contract Gradle plugin
 -> generated tests/mappings
 -> test task/producer verification
 -> merge custom resources before stubs Jar task
 -> publish candidate artifact
~~~

**This is a conceptual lifecycle**, not a guarantee every SCC version executes phases in the exact same order. Check your exact plugin version's reference and verify actual build outputs.

A controlled merge step must:

1. Run **after generation, before packaging**.
2. Read committed source files, never stray files from temporary workspaces.
3. Never overwrite generated mappings without an explicit, reviewed decision.
4. Validate JSON schemas, body file paths, mapping collisions, and priorities.
5. Pin extension binary/dependency versions on the classpath.
6. Emit a manifest tracing contract–mapping–customization.
7. Tag the candidate artifact with producer commit and customization revision.
8. Compute the digest **only after complete packaging**.
9. Publish only when executed producer contract tests > 0 and all pass.
10. Prevent reruns from fetching `latest` or mutable dependencies differing from the first run.

Never use generated outputs under `target`/`build` to store manual edits, because clean/regenerate/build caches can wipe or overwrite them.

## 37. SNAPSHOTs, Caching, and Stale Runtimes

A common timeline:

~~~text
T1: Stub Runner loads JAR A + extension A
T2: Developer updates mapping and extension to B
T3: Producer republishes 1.4.0-SNAPSHOT
T4: Consumer test hits WireMock server started at T1
T5: Response is still A; test may PASS falsely
~~~

Separate two questions:

- **Did the resolver download the new JAR and new extension binary?**
- **Did the running WireMock instance load the new contents?**

Maven `-U` and Gradle `--refresh-dependencies` affect dependency resolution, yet **do not automatically hot-reload a running WireMock process**.

Release gates should use **unique candidate versions** tied to producer commits with repository overwrite protection. If SNAPSHOTs are unavoidable, log resolved timestamped builds, digests, and startup times. When runtime extensions ship as separate dependencies, also record/pin **extension versions and digests**, since the right stubs JAR with a stale extension still behaves differently.

## 38. Security of WireMock Customizations

Response templates, request matchers, and extensions can inspect request data and runtime config, so enforce:

- Never echo or log `Authorization`, session cookies, passwords, tokens, or PII.
- Use synthetic/anonymized data across `contracts`, mappings, and `__files`.
- Restrict the WireMock Admin API to test networks; never expose it publicly.
- Prohibit extensions from uncontrolled file or network access.
- Pin dependency versions and review extension source code.
- Test JSON escaping, Unicode, quotes, newlines, and long strings.
- Avoid regexes vulnerable to excessive CPU backtracking.
- Prevent global transformers/priorities from leaking beyond test scope.
- Reset scenario state between tests and isolate parallel runs.
- Sanitize request journals before archiving in CI.
- Restrict stubs artifact publish permissions per owner/registry policy.

**Provenance aids both security and debugging**: knowing which binary loaded, which source revision supplied it, and who approved the behavior.

## 39. Case Study: A Transformer Giving Checkout a False-Green Test

### Scenario

Inventory contract v1 returns:

~~~json
{"sku":"SKU-123","available":true,"quantity":12}
~~~

Producer v2 changes it to:

~~~json
{"sku":"SKU-123","inStock":true,"quantity":12}
~~~

The consumer team adds a WireMock transformer:

~~~text
If response contains inStock:
    set available = inStock
    remove inStock
~~~

Checkout v3 still reads `available` and PASSes against the customized WireMock. Upon deployment, however, **the real producer has no such transformer** and returns only `inStock`, breaking Checkout v3.

### Root Cause

The consumer was testing a **rewritten simulated API**, not the behavior guaranteed by producer verification. The pipeline logged “using the right stubs version”, yet **runtime customization diverged from producer code**.

### Remediation

1. Evaluate whether Checkout v3 is still within the supported consumer window.
2. If compatibility is required, the real producer must emit a **dual-field response** during migration.
3. Update the Groovy/YAML contract to include both `available` and `inStock`; both teams review.
4. Run generated producer tests against the real implementation.
5. Build a new JAR with **no semantic rewrites** in baseline compatibility.
6. Run Checkout v3's real client against the new candidate stub.
7. Migrate consumers to `inStock` before deprecating the old field per policy.
8. If keeping transformers for design/resilience tests, label them **test-only** and never cite them for production compatibility.

**Conclusion:** WireMock customizations must never mask differences between the producer-verified contract and the API real consumers will receive.

## 40. Symptom-Based Troubleshooting

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Contract matches yet Stub Runner returns differently | Custom mapping override, stale JAR | Resolved digest, priority, journal |
| Body contains literal `{{...}}` | Response templating disabled | Mapping transformers, WireMock version |
| Transformer does not run | Not registered on right instance | Classpath, startup logs |
| Compiles locally, fails in CI | Different WireMock major version/dependency | Runtime version and extension API |
| JSON template breaks | Unescaped input | Negative request inputs, JSON parser |
| Wrong URL still gets 200 | Catch-all mapping | Matchers and fallback priority |
| Tests intermittently FAIL | Stateful scenario not reset | Scenario states, parallelism |
| Producer tests PASS despite broken code | Fake controller or skipped tests | Base test, executed count, mutation |
| Missing body file | `bodyFileName`/`__files` mispackaged | `jar tf` and mapping resources |
| New JAR yet stale response | Server started prior to publish | Restart and inspect effective mappings |
| Right JAR, different behavior | Different runtime extension | Extension binary/version |
| Consumer test sends no HTTP | Mocked client or wrong port | Client URL and request journal |
| WireMock 404 mistaken for business 404 | Status-only assertion | Error code/body and near-misses |
| CI intermittently passes with SNAPSHOT | Cache/publish race | Exact candidate version/digest |

Investigation order:

~~~text
Contract source/commit
 -> Generated producer tests/report
 -> Generated + custom mapping sources
 -> Extension version/registration
 -> Packaged JAR + body files
 -> Repository/consumer resolved digest
 -> Stub Runner effective mappings/scenario state
 -> Consumer real request/client URL
 -> Business assertions and CI decision
~~~

Never alter a contract to “match” a broken client request or wipe caches blindly when the real cause is an unregistered extension.

## 41. Hands-On Exercise A — Adding Provenance Without Changing Semantics

**Goal:** attach source traceability to mappings.

1. Create an Inventory producer and Groovy contract GET SKU-123 returning 200, `available:true`, `quantity:12`.
2. Generate tests and WireMock mappings with SCC.
3. Read the actual mapping; create a source-controlled manifest holding contract path, mapping name, commit, and customization revision.
4. If embedding metadata in mappings, inject it via a **deterministic build step**, never editing temporary output by hand.
5. Package the JAR; inspect the JAR for mappings, metadata/manifest, and body files.
6. Compute SHA-256 post-packaging; store a sidecar digest.
7. Compare contract responses before/after: status, headers, and business fields must remain unchanged.
8. Mutate the producer to `available:false`; generated tests must FAIL.
9. Restore code and re-run tests.
10. Document clearly that metadata is a **lookup tag**, not sole proof.

**Evidence to submit:** contract, mapping/manifest, JAR listing, digest, and producer test/mutation report.

## 42. Hands-On Exercise B — Bounded Templating/Extension

**Goal:** add dynamic behavior without altering public behavior outside the contract.

1. Discuss whether echoing `X-Correlation-Id` is part of the producer's public contract.
2. If yes, update producer/DSL so verification enforces that behavior.
3. Build a test-only template or transformer that adds only a diagnostic header.
4. Pin WireMock version, compile the extension, and register it on the right instance.
5. Test valid request IDs, missing headers, quotes/newlines/Unicode, and long strings.
6. Verify JSON escaping and ensure secrets are never echoed.
7. Compare `sku`, `available`, and `quantity` before/after the transformer.
8. Run negative request tests: wrong path, wrong header, unexpected body.
9. If the consumer uses Stub Runner, verify both the candidate JAR **and extension version** active at runtime.
10. Report baseline compatibility separately from test-harness diagnostics.

**Evidence to submit:** extension/template source, runtime logs, matcher test matrix, provenance, and documented test limits.

## 43. Hands-On Exercise C — Isolating Fault Injection and Priority

**Goal:** ensure resilience mappings never shadow baseline mappings.

1. Generate baseline mapping GET SKU-123 → 200.
2. Create test-only connection-reset/delay mappings.
3. Activate them only via dedicated port/header/scenario, never a global catch-all.
4. Ensure baseline requests still get 200 from the contract mapping.
5. Send requests triggering faults; verify consumer retries/timeouts/circuit-breakers.
6. Intentionally give a fault mapping higher priority to shadow baseline; negative tests must catch it.
7. Restore priority and re-run both suites.
8. Reset scenario states; run parallel tests to surface shared-state flakiness.
9. Package candidate and verify zero out-of-scope custom mappings leaked in.
10. Record **baseline compatibility results** separately from **resilience test results**.

**Evidence to submit:** mapping priority table, request journal, reports, and suite isolation policy.

## 44. Pre-Merge Customization Review Checklist

- [ ] Groovy/YAML contracts remain the **primary source** of producer-promised HTTP/message behavior.
- [ ] All semantic changes are reviewed via contracts/producer implementation, never stub-only edits.
- [ ] Generated producer tests run against real code, count > 0, and pass.
- [ ] Generated mappings under `target`/`build` are never hand-edited as source.
- [ ] Custom mappings/transformers/matchers are committed, owned, and reviewed.
- [ ] Extension binary and WireMock runtime versions are pinned and compatibility-tested.
- [ ] Mapping priorities/overlaps/catch-alls are checked so baseline is never shadowed.
- [ ] Non-contract requests never falsely return success.
- [ ] Response templates use safe escaping and never echo PII/tokens.
- [ ] Test-only faults/scenarios are never mistaken for public producer behavior.
- [ ] Stateful WireMock scenarios are reset and isolated.
- [ ] Global transformers are enabled only intentionally; prefer per-stub opt-in.
- [ ] Extensions are registered on the **exact instance** called by the consumer client.
- [ ] Stubs JAR includes proper mappings, `__files`, and classifier.
- [ ] Provenance maps contract path/revision, producer commit, and customization revision.
- [ ] JAR digest is computed **after packaging**, and consumer CI verifies the real digest.
- [ ] Candidate versions are immutable; SNAPSHOTs record timestamps/checksums if unavoidable.
- [ ] Consumer tests use real clients/handlers, never mocked communication.
- [ ] Negative/mutation tests turn red on invalid requests or broken behaviors.
- [ ] Unmatched 404s are never confused with contracted business 404s.
- [ ] Baseline and resilience suites have separate results and ownership.
- [ ] CI never marks PASS when executed tests are missing or artifact provenance is absent.
- [ ] Zero secrets, tokens, or production PII exist in JARs, logs, or test fixtures.

## 45. Self-Check Questions

**1. Why should you never edit generated mappings directly?**

Because regeneration overwrites them and breaks synchronization with DSL and producer tests. Edit the DSL or use version-controlled, reviewed customizations.

**2. Does `contractSource` metadata prove a mapping came from that contract?**

No. You must reconcile source revisions, build inputs, JAR digests, and test reports.

**3. When must response templating be reflected in the contract?**

Whenever dynamic behavior (such as echoing a correlation ID) is a **public producer promise**. Stub-only templates do not prove the real producer implements that behavior.

**4. How can a transformer cause false compatibility verdicts?**

It alters stub responses in ways absent from producer runtime, causing consumers to test a simulated interface that differs from production.

**5. Does registering an extension on a standalone `WireMockServer` automatically apply to Stub Runner?**

No. The two servers can be separate instances; configure the Stub Runner-managed runtime directly.

**6. What does a lower mapping priority number mean?**

WireMock normally gives precedence to **lower priority numbers**. Verify which mapping wins and check for unintended overlaps.

**7. Is connection reset the same as HTTP status 503?**

No. Connection reset is a transport fault; HTTP 503 is a status-bearing response typically carrying headers and a body.

**8. Why does a resilience PASS not replace a baseline compatibility PASS?**

Resilience tests use fault/delay fixtures to check client failure handling; they do not prove contract-verified producer behavior.

**9. Why might a JAR with the right version still serve the wrong response?**

Mutable SNAPSHOTs, a server still holding an older JAR, or a mismatched runtime extension version. Verify digests, mappings, and extensions.

**10. What is the minimum evidence for a safe customization?**

Reviewed source revisions, passing generated producer tests, mapping/extension version/collision checks, JAR digest, Stub Runner loading the right candidate, real consumer client tests, and negative controls.

## 46. References

- [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/): producer verification, Groovy/YAML DSL, and stub artifacts.
- [Spring Cloud Contract — Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): HTTP/message behavior and matchers.
- [Spring Cloud Contract — Stub Runner](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner.html): artifact resolution and consumer compatibility.
- [Spring Cloud Contract — Maven](https://docs.spring.io/spring-cloud-contract/reference/project-features-maven.html): generated tests and stubs packaging.
- [Spring Cloud Contract — Gradle](https://docs.spring.io/spring-cloud-contract/reference/project-features-gradle.html): Gradle integration and publishing.
- [WireMock — Stubbing](https://wiremock.org/docs/stubbing/): mappings, priorities, and response definitions.
- [WireMock — Response Templating](https://wiremock.org/docs/response-templating/): Handlebars helpers and transformer config.
- [WireMock — Extending WireMock](https://wiremock.org/docs/extending-wiremock/): extension interfaces and registration.
- [WireMock — Stateful Behaviour](https://wiremock.org/docs/stateful-behaviour/): scenario state lifecycle.
- [WireMock — Simulating Faults](https://wiremock.org/docs/simulating-faults/): delays and transport errors.
- [WireMock — Request Matching](https://wiremock.org/docs/request-matching/): matcher predicates, request journal, near-misses.
- [Apache Maven — Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html): local/remote artifact resolution.
- [Gradle — Dependency Caching](https://docs.gradle.org/current/userguide/dependency_caching.html): changing/dynamic dependencies.

**Version note:** WireMock 2 and 3 differ in extension APIs, templating, helpers/registration, and lifecycle. SCC Stub Runner also varies hooks/customizations across Spring Boot–Cloud Contract versions. Code snippets are **technical illustrations to verify against real dependencies**, not guarantees that every snippet compiles verbatim. Paths, `example.invalid` URLs, commits, and SHAs are illustrative only. Authoring did not execute Maven/Gradle or specialized Content QA.

---

**Key takeaway:** WireMock customizations are valuable for dynamic responses, advanced matchers, fault injection, and scenario state, yet **contract DSL remains the source of producer-promised behavior**. Custom mappings and extensions must be **versioned, reviewed inputs**, never rewriting public stub responses in ways the producer does not implement. Traceability must run end-to-end from **contract revision → generated mapping → customization revision → stubs JAR/digest → Stub Runner runtime → real consumer client → test report**. Only then can extensibility grow without eroding compatibility assurance.
