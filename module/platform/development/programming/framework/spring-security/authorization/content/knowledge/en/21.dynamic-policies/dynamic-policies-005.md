# OPA or ReBAC Systems: Selection Criteria and Integration Scope with Spring Security

## 1. The architectural problem: where should dynamic policies live?

A Spring Boot application serving millions of documents has three simultaneous requirements:

1. Users may only access documents belonging to a **tenant** they are a member of, regardless of IDs or self-declared headers.
2. Alice can share Document#101 with Bob, a review group, or a project. Permissions can be inherited along folder → document, group → member, and organization → project relationships.
3. Rules vary by **context**: CONFIDENTIAL documents can only be read with clearance and ACTIVE state; large exports require MFA; financial data is restricted by time, region, risk score, or legal hold.

If all logic sits inside dozens of `@PreAuthorize` expressions scattered across controllers and services, changes become hard to audit and services risk applying inconsistent policies. Two approaches are commonly considered:

- **Open Policy Agent (OPA)**: a policy-as-code engine using **Rego** that takes JSON input and reference data and returns decisions. Strong at attribute/context-based rules (**ABAC**) and cross-cutting policies; able to evaluate many rule types beyond authorization alone.
- **Relationship-Based Access Control (ReBAC)**: derives permissions from a **user–group–resource** relationship graph, Zanzibar-style. A system like **OpenFGA** stores relationship tuples, defines an authorization model, and supports `Check`, `ListObjects`, and `ListUsers` queries. Strong at sharing, membership, inheritance, groups, and multi-level hierarchies.

**They are not mutually exclusive.** OPA can also read relationship data to decide, and OpenFGA supports conditions for runtime attributes within its model boundaries. The main differences lie in **abstractions, where permissions live, query APIs, data lifecycles, and operational capabilities**, rather than one side "knowing ABAC" and the other "unable to do ABAC".

### 1.1. A realistic authorization example

```text
Tenant t1
 ├── Group reviewers
 │    ├── user:bob
 │    └── user:claire
 ├── Folder project-7
 │    └── Document 101 (classification = INTERNAL)
 └── Document 102 (classification = CONFIDENTIAL)

Relations:
  user:alice --owner--> document:101
  group:reviewers --viewer--> document:101
  user:bob --member--> group:reviewers

Context:
  document:101.state = ACTIVE
  request.action = read
  caller.memberOf(t1) = true
  caller.risk = LOW
```

For Bob to read Document#101, a combined policy might require:

```text
ALLOW =
    authenticated(Bob)
    AND memberOf(Bob, t1)
    AND canonicalTenant(Document#101) == t1
    AND ReBAC.Check(user:bob, can_read, document:t1-101)
    AND OPA.Allow(
          action="read",
          classification="INTERNAL",
          state="ACTIVE",
          risk="LOW"
        )
```

Tenant and resource state conditions are read from **server-side sources**, not from `X-Tenant-Id`, request bodies, or client-claimed roles. Never write `OPA.allow OR ReBAC.allow` when the intent is for **both** to be mandatory: the OR branch turns into a bypass path.

## 2. PEP, PDP, PIP, and relationship stores

Separate four responsibilities:

| Component | Question | Example in application |
|---|---|---|
| **PEP — Policy Enforcement Point** | Block or allow the request/method? | `SecurityFilterChain`, `AuthorizationManager`, `@PreAuthorize` |
| **PDP — Policy Decision Point** | Given subject/action/resource/context, what is the decision? | OPA Rego engine, OpenFGA `Check`, or combined orchestrator |
| **PIP — Policy Information Point** | Which attributes come from trusted sources? | DB tenant membership, owner, resource state, clearance, verified IP |
| **Policy/relationship store** | Where are rules or relationships stored/updated? | Git + OPA bundles; OpenFGA model/tuples; business database |

The PEP always resides in the Spring application or gateway because OPA/OpenFGA **cannot modify HTTP responses or block database updates on their own** without integration. The PDP only returns decision information; your code must **enforce denials** on every access path.

A reference architecture:

```text
Browser / API client
       |
       v
[Spring Security authentication]
       |
       v
[PEP: AuthorizationManager / @PreAuthorize]
       |                         |
       |                 [PIP: canonical resource]
       |                 [PIP: server membership]
       |                         |
       +----------> Decision Orchestrator
                      /         \
                     v           v
               OPA/Rego        OpenFGA/ReBAC
               attributes      tuples/relations
                     \           /
                      v         v
                 explicit ALLOW/DENY
                           |
             ┌─────────────┴─────────────┐
             v                           v
          DENY 403                   ALLOW + guarded
                                    repository query
```

This is a **logical** diagram; it does not mean every request must call **both** services. Choose the right policy placement for each endpoint/data group and SLA.

### 2.1. Pieces always kept in the application

Even with an external PDP, Spring Security remains responsible for:
- **Authentication**: verifying JWT/session, issuer, audience, and identity.
- **Tenant boundary**: checking principal membership and the resource's canonical tenant; never relying on client-declared URL/header info.
- **Input validation**: object ID, action, resource type, parameter types; deny when unknown.
- **Enforcement and side effects**: rejecting **before** running mutations, and applying `WHERE tenant/ownership` at the data layer.
- **Failure policy**: timeouts, invalid responses, HTTP 5xx, circuit breakers; never allow by default.
- **Audit**: correlation ID, decision source, model/policy version, resource/action, latency.

OPA/ReBAC do not replace business transactions, row-level constraints, resource-existence checks, or authentication.

## 3. OPA: policy-as-code and contextual rules

**OPA** evaluates rules written in Rego against the decision's `input` and loaded `data` (policies/reference data). Applications can run OPA as a sidecar, shared service, or other supported runtime integration. For Java/Spring, calling the **OPA REST Data API** is a straightforward integration pattern:

```http
POST /v1/data/documents/allow HTTP/1.1
Content-Type: application/json

{
  "input": {
    "principal": "alice",
    "action": "read",
    "tenantId": "t1",
    "documentId": "101",
    "classification": "INTERNAL",
    "state": "ACTIVE",
    "boundAdmin": false,
    "owner": true
  }
}
```

This is an HTTP example using **backend-verified values**. If `data.documents.allow` returns a boolean, the OPA Data API responds:

```json
{"result":true}
```

However, **HTTP 200 does not mean allow**: if the query path is undefined, OPA may return `{}`, with no `result` key. The adapter must permit only when `result` is strictly boolean `true`; missing, null, non-boolean, or error all deny. Sending input as `{"input":...}` and reading `result` is the official `POST /v1/data/{path}` contract.

### 3.1. Example Rego policy compatible with OPA v1

**`policy/documents.rego`**

```rego
package documents

default allow := false

# An INTERNAL ACTIVE document is accepted by OPA
# if the caller has already passed the tenant boundary in Spring.
allow if {
    input.action == "read"
    input.state == "ACTIVE"
    input.classification == "INTERNAL"
}

# CONFIDENTIAL accepts only the owner or a scoped admin.
allow if {
    input.action == "read"
    input.state == "ACTIVE"
    input.classification == "CONFIDENTIAL"
    input.owner == true
}

allow if {
    input.action == "read"
    input.state == "ACTIVE"
    input.classification == "CONFIDENTIAL"
    input.boundAdmin == true
}
```

This is an **illustrative policy**, intentionally omitting WRITE/DELETE rules. `default allow := false` closes any undefined action. OPA 1.x uses Rego v1 syntax with the `if` keyword; OPA versions before 1.0 may require `import rego.v1` depending on version.

Run with the OPA CLI installed:

```bash
opa fmt policy/documents.rego
opa test policy/
opa run --server policy/documents.rego
```

`opa fmt` checks/formats Rego; `opa test` executes Rego tests **if test files exist**; `opa run --server` starts an OPA server (typically at `localhost:8181`). Input data and Rego reside in separate layers: Rego **does not directly query** Spring's database for owner/tenant while evaluating rules; a PIP must pass the data in or OPA must receive data via a designed sync mechanism.

### 3.2. Rego unit tests (policy regression)

**`policy/documents_test.rego`**

```rego
package documents

test_internal_active_allowed if {
    allow with input as {
        "action": "read",
        "state": "ACTIVE",
        "classification": "INTERNAL",
        "owner": false,
        "boundAdmin": false
    }
}

test_confidential_nonowner_denied if {
    not allow with input as {
        "action": "read",
        "state": "ACTIVE",
        "classification": "CONFIDENTIAL",
        "owner": false,
        "boundAdmin": false
    }
}

test_inactive_denied if {
    not allow with input as {
        "action": "read",
        "state": "ARCHIVED",
        "classification": "INTERNAL",
        "owner": true,
        "boundAdmin": true
    }
}

test_unknown_action_denied if {
    not allow with input as {
        "action": "delete",
        "state": "ACTIVE",
        "classification": "INTERNAL",
        "owner": true,
        "boundAdmin": true
    }
}
```

With `policy/documents.rego` and `policy/documents_test.rego`, the command:

```bash
opa test policy/ -v
```

is expected to run the four defined tests. This is an **expected result**, not an execution log from this environment. In production, also test missing fields, wrong data types, missing classification, revoked clearance, old/new policy versions, and specific request risk attributes.

### 3.3. Practical strengths and limits of OPA

OPA fits well when rules involve many attributes: classification, action, risk, normalized IP, time, authentication assurance, approval state, limits, region, or service attributes. Rego provides policy-as-code, unit testing, code review, bundle distribution, decision logging, and near-app evaluation to cut network hops when deployed as a sidecar or embedded appropriately.

On the flip side:
- **Data synchronization**: OPA does not know the latest membership or resource graph unless you supply the data; you need a loading strategy, TTL, data ownership, and refresh plan.
- **Large relationship graphs**: can be encoded in Rego/data, yet OPA **does not natively provide** graph tuple storage, relationship write/revoke APIs, or listing authorized objects like a dedicated ReBAC service.
- **Policy governance**: managing branches, reviews, tests, bundle signing/versioning, canary rollouts, and rollbacks.
- **Input contract**: fields sent by callers must be verified; a valid policy over spoofed input still yields wrong decisions.
- **Decision semantics**: OPA can return any JSON document, not only booleans; adapters must enforce a fixed contract.

Choosing an OPA sidecar versus a central PDP requires benchmarking real-world latency, throughput, resource budgets, update propagation, and fail-closed behavior.

## 4. ReBAC: relationships, tuples, and Zanzibar-style models

In **ReBAC**, decisions rely on relationships between subjects and objects, potentially traversing groups or parent objects.

A tuple typically describes:

```text
user:alice     owner   document:t1-101
user:bob       viewer  document:t1-101
group:reviewers#member viewer document:t1-102
document:t1-101 parent folder:t1-project-7
```

These lines are **conceptual illustrations**; an authorization model defining types/relations must be created before writing tuples into OpenFGA. With `group:reviewers#member`, OpenFGA supports usersets, allowing group membership to imply user permissions.

### 4.1. Example OpenFGA authorization model

**`model.fga`**

```fga
model
  schema 1.1

type user

type group
  relations
    define member: [user]

type folder
  relations
    define viewer: [user, group#member]

type document
  relations
    define parent: [folder]
    define owner: [user]
    define viewer: [user, group#member] or viewer from parent or owner
    define editor: [user, group#member] or owner
    define can_read: viewer or editor
    define can_write: editor
```

In this model, `viewer from parent` means a user able to view a parent folder is treated as a viewer of any document linked via `parent` to that folder. That is a **business choice**, not automatic behavior in every ReBAC system. If PRIVATE documents must not inherit folder access, update the model accordingly and test it.

In practice, to use this model you must **create a store, write the authorization model**, obtain `store_id` and `authorization_model_id`, and then write corresponding tuples. Do not treat an `.fga` file as a Spring Boot configuration automatically loaded on startup.

### 4.2. OpenFGA Check API

```http
POST /stores/<store-id>/check HTTP/1.1
Content-Type: application/json

{
  "authorization_model_id": "<model-id>",
  "tuple_key": {
    "user": "user:bob",
    "relation": "can_read",
    "object": "document:t1-101"
  }
}
```

Response when authorized:

```json
{"allowed":true}
```

This contract follows OpenFGA's `POST /stores/{store_id}/check`. The `allowed` field must be strictly boolean `true`; `false` means deny. **Never treat HTTP 200 as allow.** If a relation does not exist in the model, the API may return HTTP 400 rather than false; the adapter must fail closed and emit metrics distinguishing configuration errors.

**Important:** OpenFGA is **one concrete ReBAC implementation**, not synonymous with all of ReBAC. Other implementations have different models, consistency contracts, APIs, and operational costs. Match the model, version, and SDK to your chosen provider.

### 4.3. Why ReBAC excels at sharing and hierarchies

ReBAC naturally answers questions like:
- Was Bob directly shared Document#101 or did he inherit it from Group reviewers?
- Can an Editor of Folder X edit child documents?
- Alice owns a project; who can view/edit issues inside it?
- Which team is a user in, and which organization owns that team?
- How do we list objects a user has `can_read` on?

A store like OpenFGA offers `Check`, `ListObjects`, `ListUsers`, and `BatchCheck` for such queries. However, it **does not automatically enforce** your application database's tenant boundaries: ID mapping, ownership, tenant changes, and tuple lifecycles must stay synchronized with authoritative sources.

### 4.4. Runtime conditions do not vanish from ReBAC

OpenFGA supports **conditional tuples** and forms of conditions when modeled, so it is inaccurate to claim "ReBAC cannot consider time/IP". Still, policies packed with risk rules, monetary limits, clearances, geography, negation rules, or rapidly changing business logic may be easier to manage with OPA/Rego in a rule-focused PDP. Evaluate **required expressiveness and data distribution**, rather than comparing ABAC and ReBAC labels dogmatically.

## 5. Selection matrix: when to use OPA, ReBAC, or hybrid?

| Criterion | OPA / Rego | ReBAC / OpenFGA | Selection guidance |
|---|---|---|---|
| Policies driven by many attributes & risk | Very strong | Supports conditions but model-centric | OPA when context dominates |
| User–group–folder–resource relationships | Expressible via `data` | Core abstraction | ReBAC when graphs/sharing are central |
| User-driven grant/revoke sharing | Requires custom data/CRUD design | Explicit tuple write/delete | ReBAC if sharing UI is frequent |
| Group membership, inheritance | Self-organized data/policy | Graph relations, usersets | ReBAC |
| Complex conditional rules | Easy to package/test in Rego | Conditions fit select cases | OPA or hybrid |
| Listing permitted objects | Compile/partial evaluation, integrated data filtering | `ListObjects`/batch checks | Assess paging correctness & performance |
| Policy-as-code review | Rego in Git/bundles | Versioned models + tests, runtime tuple data | Depends on governance |
| Small, app-local policy changes | Sidecar/local runtime may fit | Remote service usually needs its own topology | Benchmark deployment |
| Checking by model & tuple version | Versioned policy/bundles; separate data sync | Model ID + tuple state/consistency | Evaluate revocation consistency |
| Latency and per-request cost | Depends on placement/data size | Depends on graph query/cache/storage | P95/P99 + real load testing |
| Multi-tenant data boundaries | Needs local PIP/guards | Needs tenant-aware models/object IDs/guards | Neither **replaces** tenant authorization |
| Operational complexity | OPA rollout, bundles, logs, data sync | Model/tuple writes, graph DB, query service | Choose based on team capability |
| Security review | Rego policy diffs, tests | Model diffs + tuple audit/write policies | Both require threat modeling |

**Quick selection rules:**

1. If the problem is mainly **classification, risk, time, environment, compliance** with simple relationships: favor **OPA** or an equivalent policy engine.
2. If the problem is mainly **document sharing, groups, projects, inheritance, owner/editor/viewer, ListObjects**: favor **ReBAC** such as OpenFGA.
3. If you need **dynamic relationships + mandatory contextual security rules**: choose **hybrid**, typically with **AND** for mandatory conditions, or define a provable combined policy.
4. If you only have a few fixed roles without independent policy changes, **in-app Spring Security** may suffice; do not introduce a distributed PDP merely for trendiness.

There is no "default X ms latency" or "best price" true across all setups. Measure on real infrastructure, data, graphs, and traffic.

### 5.1. Estimating total cost

Calculate:
- `N_checks/sec` across reads, writes, list APIs, and background jobs.
- P50/P95/P99 for decisions, queueing, retries, and TLS overhead.
- Request context size, average relations per object, and group depth.
- Memory/CPU of OPA sidecars and storage/CPU of ReBAC.
- Cost of model/tuple migrations, event ingestion, cache invalidation, and on-call support.
- Acceptable revocation lag: seconds, minutes, or near real-time.
- Log throughput, retention, and sensitive data redaction.

Include the **cost of correctness** in the decision: a cheap system whose permission model is hard to audit or prone to fail-open can cost far more during an incident.

## 6. Spring Security integration scope: choosing the PEP

Two common PEP placements exist.

### 6.1. HTTP-level AuthorizationManager

Spring Security 6.5 allows a custom `AuthorizationManager<RequestAuthorizationContext>` via `authorizeHttpRequests(...).anyRequest().access(manager)`.

```java
@Component
final class RemoteAuthorizationManager
        implements AuthorizationManager<RequestAuthorizationContext> {

    @Override
    public AuthorizationDecision check(
            Supplier<Authentication> authentication,
            RequestAuthorizationContext context) {
        // Pass authenticated principal + canonical resource/context
        // to the PDP; missing result or error => deny.
        return new AuthorizationDecision(false);
    }
}
```

This is an **illustrative API skeleton**, omitting imports/constructor/lookup. Placing the PEP at the HTTP layer makes sense for gateways, route-level scopes, or APIs lacking dedicated service logic. Yet URLs alone do not prove `documentId` belongs to the tenant or that the user is allowed on that object; safety requires canonical lookups and protected DB queries. Calls from jobs/batches/event consumers can also bypass HTTP PEPs.

### 6.2. Method-level @PreAuthorize (recommended default for domain)

```java
@PreAuthorize("@documentPolicy.canRead(authentication, #documentId)")
public DocumentView read(@P("documentId") Long documentId) {
    // Runs only if policy permits.
}
```

This is an illustrative structure; `@EnableMethodSecurity` must be enabled and the method must be called through a **Spring-managed proxy**. Placing policies at the service boundary allows reuse across HTTP, schedulers, and other services; repositories must still enforce `tenant_id` and guarded predicates.

Never use `@PostAuthorize` to evaluate permissions after a method has already written to the DB, sent an email, or fired a webhook; side effects may have occurred before denial. For mutations, evaluate permissions **before** acting, paired with transactions/conditional updates to reduce TOCTOU.

### 6.3. Never let clients define trusted PDP input

In the example below, the controller receives only `documentId`; the Java policy pulls:
- `principal` from Spring Security `Authentication`.
- `tenantId` and `classification` from the canonical document repository.
- membership and admin bindings from server-side sources.
- `action="read"` from the invoked method, never from arbitrary JSON.

If OPA/ReBAC inputs contain `isAdmin=true` copied from the request body, the policy can be "true to its input" yet insecure. **PIP** trustworthiness matters just as much as Rego expressions or FGA models.

## 7. Java 17 demo: one PEP, two PDP adapters, selected via config

This example uses Spring Boot **3.5.6** (Spring Security **6.5.x** managed by Boot). A GET endpoint reads documents via `@PreAuthorize`. `DocumentPolicy` always checks Authentication + tenant membership + canonical document state; then:

- `app.authz.mode=opa`: requires OPA to allow.
- `app.authz.mode=rebac`: requires OpenFGA to allow.
- `app.authz.mode=hybrid`: **both** must allow.

In tests, both adapters are mocked so no live OPA/OpenFGA server is required. In operations, configure URLs, store/model IDs, and deploy the corresponding PDPs. Test HTTP contracts and real policies/models separately before going to production.

### 7.1. Project tree

```text
policy-pdp-demo/
  pom.xml
  src/main/java/com/example/pdp/
    PdpApplication.java
    SecurityConfig.java
    Document.java
    DocumentCatalog.java
    TenantDirectory.java
    DecisionInput.java
    OpaDecisionPort.java
    RebacDecisionPort.java
    OpaHttpDecisionPort.java
    OpenFgaHttpDecisionPort.java
    DocumentPolicy.java
    DocumentService.java
    DocumentController.java
  src/main/resources/
    application.properties
  src/test/java/com/example/pdp/
    DocumentPolicyIntegrationTest.java

# Optional, run OPA/OpenFGA standalone:
  policy/documents.rego
  policy/documents_test.rego
  model.fga
```

### 7.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.6</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>policy-pdp-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build><plugins><plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
  </plugin></plugins></build>
</project>
```

Do not pin a separate Spring Security version. `RestClient` comes with Boot-managed Spring Framework; `@MockitoBean` comes with Spring Framework 6.2. No OpenFGA SDK dependency is needed when calling the REST API via `RestClient`; the official SDK is an option if you want convenient auth/retry/model ID management and tracing.

### 7.3. Boot application and SecurityConfig

**`src/main/java/com/example/pdp/PdpApplication.java`**

```java
package com.example.pdp;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PdpApplication {
    public static void main(String[] args) {
        SpringApplication.run(PdpApplication.class, args);
    }
}
```

**`src/main/java/com/example/pdp/SecurityConfig.java`**

```java
package com.example.pdp;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/documents/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

`@EnableMethodSecurity` activates `@PreAuthorize`. The HTTP layer requires Authentication only, while object-level decisions live in the service. Running without configured credentials still requires login on the GET endpoint; integration tests use `@WithMockUser`. In production with a JWT resource server, verify issuer/audience/signature and tenant mappings.

### 7.4. Document and canonical data

**`src/main/java/com/example/pdp/Document.java`**

```java
package com.example.pdp;

public record Document(
        Long id,
        String tenantId,
        String owner,
        String classification,
        String state,
        String title) {}
```

**`src/main/java/com/example/pdp/DocumentCatalog.java`**

```java
package com.example.pdp;

import java.util.Map;
import org.springframework.stereotype.Repository;

@Repository
public class DocumentCatalog {
    private final Map<Long, Document> docs = Map.of(
        101L, new Document(
            101L, "t1", "alice",
            "INTERNAL", "ACTIVE", "Quarterly report"),
        102L, new Document(
            102L, "t1", "alice",
            "CONFIDENTIAL", "ACTIVE", "Strategy"),
        103L, new Document(
            103L, "t1", "manager",
            "INTERNAL", "ARCHIVED", "Old notes"),
        201L, new Document(
            201L, "t2", "carol",
            "INTERNAL", "ACTIVE", "South report")
    );

    public Document find(Long id) {
        return id == null ? null : docs.get(id);
    }
}
```

**`src/main/java/com/example/pdp/TenantDirectory.java`**

```java
package com.example.pdp;

import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Component;

@Component
public class TenantDirectory {
    private final Map<String, Set<String>> members = Map.of(
        "t1", Set.of("alice", "bob", "manager"),
        "t2", Set.of("carol", "dave")
    );

    private final Set<String> admins = Set.of("t1:manager");

    public boolean isMember(String tenant, String user) {
        Set<String> users = members.get(tenant);
        return users != null && user != null
            && users.contains(user);
    }

    public boolean isBoundAdmin(String tenant, String user) {
        return tenant != null && user != null
            && admins.contains(tenant + ":" + user);
    }
}
```

The catalog and directory hold trusted data **for the demo**. Production replaces them with repositories or synced IAM; never let callers pass `owner`, `tenantId`, or `isBoundAdmin` to bypass policy.

### 7.5. DecisionInput and two ports

**`src/main/java/com/example/pdp/DecisionInput.java`**

```java
package com.example.pdp;

public record DecisionInput(
        String principal,
        String tenantId,
        String documentId,
        String action,
        String classification,
        String state,
        boolean owner,
        boolean boundAdmin) {}
```

**`src/main/java/com/example/pdp/OpaDecisionPort.java`**

```java
package com.example.pdp;

public interface OpaDecisionPort {
    boolean allowed(DecisionInput input);
}
```

**`src/main/java/com/example/pdp/RebacDecisionPort.java`**

```java
package com.example.pdp;

public interface RebacDecisionPort {
    boolean allowed(DecisionInput input);
}
```

Ports create a clear boundary between the Spring PEP/PIP and remote PDPs. Tests can mock ports; swapping OpenFGA for another ReBAC engine does not force changes to the business service. Production typically enriches booleans into structured decisions with policy/model versions, reason codes, correlation IDs, and latency metrics.

### 7.6. OPA HTTP adapter

**`src/main/java/com/example/pdp/OpaHttpDecisionPort.java`**

```java
package com.example.pdp;

import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class OpaHttpDecisionPort implements OpaDecisionPort {
    private final RestClient rest;

    public OpaHttpDecisionPort(
            RestClient.Builder builder,
            @Value("`${app.authz.opa.url:http://localhost:8181}`")
            String opaUrl) {
        this.rest = builder.baseUrl(opaUrl).build();
    }

    @Override
    public boolean allowed(DecisionInput input) {
        Map<?, ?> reply = rest.post()
            .uri("/v1/data/documents/allow")
            .body(Map.of("input", input))
            .retrieve()
            .body(Map.class);

        // OPA 200 with {} or non-true result = DENY.
        return reply != null
            && Boolean.TRUE.equals(reply.get("result"));
    }
}
```

**Explanation:** OPA expects JSON body `{"input":{...}}`; the adapter accepts only `result === true`. On HTTP 4xx/5xx, timeouts, or bad JSON, `RestClient` throws or returns invalid data, and the orchestrator must **fail closed**. Never swallow errors and allow.

### 7.7. OpenFGA HTTP adapter

**`src/main/java/com/example/pdp/OpenFgaHttpDecisionPort.java`**

```java
package com.example.pdp;

import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class OpenFgaHttpDecisionPort implements RebacDecisionPort {
    private final RestClient rest;
    private final String storeId;
    private final String modelId;

    public OpenFgaHttpDecisionPort(
            RestClient.Builder builder,
            @Value("`${app.authz.fga.url:http://localhost:8080}`")
            String url,
            @Value("`${app.authz.fga.store-id:demo-store}`")
            String storeId,
            @Value("`${app.authz.fga.model-id:demo-model}`")
            String modelId) {
        this.rest = builder.baseUrl(url).build();
        this.storeId = storeId;
        this.modelId = modelId;
    }

    @Override
    public boolean allowed(DecisionInput input) {
        // Map business action to a relation present in the FGA model.
        String relation = switch (input.action()) {
            case "read" -> "can_read";
            default -> throw new IllegalArgumentException(
                "Action not modeled");
        };

        // Object name must match the written tuple;
        // tenant-qualified ID prevents key collisions across tenants.
        String objectId = "document:"
            + input.tenantId() + "-" + input.documentId();

        Map<String, Object> tuple = Map.of(
            "user", "user:" + input.principal(),
            "relation", relation,
            "object", objectId
        );
        Map<String, Object> body = Map.of(
            "authorization_model_id", modelId,
            "tuple_key", tuple
        );

        Map<?, ?> reply = rest.post()
            .uri("/stores/{storeId}/check", storeId)
            .body(body)
            .retrieve()
            .body(Map.class);

        return reply != null
            && Boolean.TRUE.equals(reply.get("allowed"));
    }
}
```

**Configuration warning:** `demo-store` and `demo-model` are merely local defaults; to call a **real OpenFGA server**, create a store, publish the model, write tuples, and populate real IDs. If OpenFGA requires authentication, configure `RestClient` with bearer tokens/mTLS from a secret store; never hardcode secrets or accept PDP tokens from clients. In production, bound connect/read timeouts, add appropriate retry budgets/circuit breakers, and emit metrics on PDP errors.

Do not use bare local usernames like `user:alice` if they are not globally unique across IdPs/tenants. With multiple issuers, choose a canonical subject identifier like `issuer+subject` or an internal user ID, and ensure that exact ID is written into tuples.

### 7.8. Orchestrator: tenant boundary AND external decisions

**`src/main/java/com/example/pdp/DocumentPolicy.java`**

```java
package com.example.pdp;

import java.util.Locale;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {
    public enum Mode { OPA, REBAC, HYBRID }

    private final DocumentCatalog docs;
    private final TenantDirectory tenants;
    private final OpaDecisionPort opa;
    private final RebacDecisionPort rebac;
    private final Mode mode;
    private final AuthenticationTrustResolver trust =
        new AuthenticationTrustResolverImpl();

    public DocumentPolicy(
            DocumentCatalog docs,
            TenantDirectory tenants,
            OpaDecisionPort opa,
            RebacDecisionPort rebac,
            @Value("`${app.authz.mode:hybrid}`")
            String mode) {
        this.docs = docs;
        this.tenants = tenants;
        this.opa = opa;
        this.rebac = rebac;
        this.mode = Mode.valueOf(mode.toUpperCase(Locale.ROOT));
    }

    private static boolean hasAuthority(
            Authentication auth, String name) {
        for (GrantedAuthority authority : auth.getAuthorities()) {
            if (name.equals(authority.getAuthority())) {
                return true;
            }
        }
        return false;
    }

    public boolean canRead(Authentication auth, Long documentId) {
        if (auth == null || !auth.isAuthenticated()
                || trust.isAnonymous(auth)) {
            return false;
        }

        Document doc = docs.find(documentId);
        if (doc == null
                || !tenants.isMember(doc.tenantId(), auth.getName())) {
            return false;
        }

        // Immutable baseline for ALL modes: deny archived.
        if (!"ACTIVE".equals(doc.state())) {
            return false;
        }

        boolean admin = hasAuthority(
            auth, "ROLE_TENANT_ADMIN")
            && tenants.isBoundAdmin(doc.tenantId(), auth.getName());

        DecisionInput input = new DecisionInput(
            auth.getName(), doc.tenantId(),
            String.valueOf(doc.id()), "read",
            doc.classification(), doc.state(),
            auth.getName().equals(doc.owner()),
            admin
        );

        // Error, timeout, missing result, wrong model => DENY.
        try {
            return switch (mode) {
                case OPA -> opa.allowed(input);
                case REBAC -> rebac.allowed(input);
                case HYBRID ->
                    opa.allowed(input) && rebac.allowed(input);
            };
        }
        catch (RuntimeException ex) {
            // Production: log/metric by error code, never leak secrets.
            return false;
        }
    }
}
```

**Semantic warning:** Different modes enforce different policies. In the demo, `REBAC` retains the "ACTIVE + tenant membership" baseline, yet **does not automatically enforce OPA's classification rules**. Do not switch to REBAC-only for data where classification rules are mandatory unless those rules have been moved to a trusted guard or FGA condition. Never treat mode switching as a harmless performance tweak; it is a security policy change requiring review, migration, and testing.

When `mode=HYBRID`, `&&` short-circuits: if OPA denies, ReBAC is not called. If OPA allows yet ReBAC denies, the result is still deny. If either adapter throws an exception, the result is deny. This demonstrates an **intersection policy**; another system might intentionally use OR rules, but must prove that the OR cannot bypass tenants, data classification, or mandatory security conditions.

### 7.9. Domain service and controller

**`src/main/java/com/example/pdp/DocumentService.java`**

```java
package com.example.pdp;

import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    private final DocumentCatalog docs;

    public DocumentService(DocumentCatalog docs) {
        this.docs = docs;
    }

    @PreAuthorize(
        "@documentPolicy.canRead(authentication, #documentId)"
    )
    public Document read(@P("documentId") Long documentId) {
        return docs.find(documentId);
    }
}
```

**`src/main/java/com/example/pdp/DocumentController.java`**

```java
package com.example.pdp;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/documents")
public class DocumentController {
    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/{documentId}")
    public Document read(
            @PathVariable("documentId") Long documentId) {
        return service.read(documentId);
    }
}
```

**`src/main/resources/application.properties`**

```properties
app.authz.mode=hybrid
app.authz.opa.url=http://localhost:8181
app.authz.fga.url=http://localhost:8080
app.authz.fga.store-id=demo-store
app.authz.fga.model-id=demo-model
```

`app.authz.mode` must be a protected server config, **never read from query params/headers** letting callers pick a weaker mode. Even without a tenant ID in the URL, the policy reads the canonical tenant from the document and checks corresponding membership. If an endpoint includes a tenant ID in the path, **verify `pathTenant == doc.tenantId`** before calling the PDP.

`DocumentService.read` performs no mutations, keeping the focus on authorization. Writes/deletes require `@PreAuthorize` on the corresponding action, transactions, and guarded SQL updates with tenant/owner/version predicates.

### 7.10. Integration tests: PEP and fail-closed with mock ports

**`src/test/java/com/example/pdp/DocumentPolicyIntegrationTest.java`**

```java
package com.example.pdp;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentPolicyIntegrationTest {
    @Autowired MockMvc mvc;
    @Autowired DocumentService service;

    @MockitoBean OpaDecisionPort opa;
    @MockitoBean RebacDecisionPort rebac;

    @BeforeEach
    void allowBothByDefault() {
        when(opa.allowed(any())).thenReturn(true);
        when(rebac.allowed(any())).thenReturn(true);
    }

    @Test
    @WithMockUser(username = "alice")
    void ownerWithBothGrantsCanRead() throws Exception {
        mvc.perform(get("/api/documents/101"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("Quarterly report"));
    }

    @Test
    @WithMockUser(username = "bob")
    void tenantMemberCanReadWhenBothPdpAllow() throws Exception {
        mvc.perform(get("/api/documents/101"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "carol")
    void otherTenantOwnerCanReadOwnResource() throws Exception {
        mvc.perform(get("/api/documents/201"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "alice")
    void membershipDoesNotCrossTenant() throws Exception {
        mvc.perform(get("/api/documents/201"))
            .andExpect(status().isForbidden());
        verifyNoInteractions(opa, rebac);
    }

    @Test
    @WithMockUser(username = "mallory")
    void unknownMemberCannotReachPdp() throws Exception {
        mvc.perform(get("/api/documents/101"))
            .andExpect(status().isForbidden());
        verifyNoInteractions(opa, rebac);
    }

    @Test
    @WithMockUser(username = "alice")
    void unknownResourceFailsClosed() throws Exception {
        mvc.perform(get("/api/documents/999"))
            .andExpect(status().isForbidden());
        verifyNoInteractions(opa, rebac);
    }

    @Test
    @WithMockUser(username = "manager", roles = "TENANT_ADMIN")
    void archivedResourceDeniedBeforeAnyPdpCall()
            throws Exception {
        mvc.perform(get("/api/documents/103"))
            .andExpect(status().isForbidden());
        verifyNoInteractions(opa, rebac);
    }

    @Test
    @WithMockUser(username = "alice")
    void opaDenyOverridesRebacAllow() throws Exception {
        when(opa.allowed(any())).thenReturn(false);
        mvc.perform(get("/api/documents/101"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice")
    void rebacDenyOverridesOpaAllow() throws Exception {
        when(rebac.allowed(any())).thenReturn(false);
        mvc.perform(get("/api/documents/101"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice")
    void opaTimeoutOrExceptionFailsClosed() throws Exception {
        when(opa.allowed(any())).thenThrow(
            new IllegalStateException("OPA unavailable"));
        mvc.perform(get("/api/documents/101"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice")
    void rebacExceptionFailsClosed() throws Exception {
        when(rebac.allowed(any())).thenThrow(
            new IllegalStateException("ReBAC unavailable"));
        mvc.perform(get("/api/documents/101"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "manager", roles = "TENANT_ADMIN")
    void boundAdminCanReadIfBothPdpApprove() throws Exception {
        mvc.perform(get("/api/documents/102"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "bob", roles = "TENANT_ADMIN")
    void roleStringAloneDoesNotGrantCrossTenant()
            throws Exception {
        mvc.perform(get("/api/documents/201"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob")
    void spoofedRoleAndTenantHeadersDoNotGrantAccess()
            throws Exception {
        mvc.perform(get("/api/documents/201")
                .header("X-Tenant-Id", "t2")
                .header("X-User", "carol")
                .header("X-Role", "ROLE_TENANT_ADMIN"))
            .andExpect(status().isForbidden());
    }

    @Test
    void anonymousRequestIsChallenged() throws Exception {
        mvc.perform(get("/api/documents/101"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "alice")
    void directSpringManagedServiceAlsoEnforcesPolicy() {
        when(rebac.allowed(any())).thenReturn(false);
        assertThrows(AccessDeniedException.class,
            () -> service.read(101L));
    }

    @Test
    @WithMockUser(username = "alice")
    void successfulServiceCallReturnsCanonicalTenant() {
        Document doc = service.read(101L);
        assertEquals("t1", doc.tenantId());
        assertEquals("alice", doc.owner());
    }
}
```

From `policy-pdp-demo`:

```bash
mvn test
```

**Expected code behavior:** These JUnit/MockMvc tests pass, demonstrating local baseline checks before calling PDPs, hybrid AND, fail-closed on PDP errors, spoofed headers granting nothing, and Method Security blocking direct service calls. However, these tests **mock OPA/ReBAC ports**; they do **not** prove:
- REST bodies/responses match a real OPA/OpenFGA server.
- Real Rego policies/FGA models are loaded and tuples are written.
- Correct consistency, latency, TLS, bearer tokens, or caching.
- PIP data synchronization when a grant is revoked.

Therefore, write **contract tests** and **end-to-end tests** against managed OPA/OpenFGA instances using real policies/models, including timeouts and model migrations. Never treat `@MockitoBean` as proof of production-ready authorization infrastructure.

## 8. Hybrid: one decision, two permission sources

In many document products, ReBAC handles **discretionary grants** (who is shared/owner/group), while OPA enforces **mandatory guards** (classification, risk, compliance). A policy:

```text
permitRead(user, document, requestContext) =
    isAuthenticated(user)
    AND isTenantMember(user, document.tenantId)
    AND document.state == ACTIVE
    AND OpenFGA.Check(user, "can_read", document)
    AND OPA.Check(classification, clearance, deviceTrust, risk)
```

For a CONFIDENTIAL document, if Bob holds a viewer tuple via a group yet OPA denies for insufficient clearance → **DENY**. If OPA allows yet the relationship tuple was revoked → **DENY**. The two engines do not know about each other; the orchestrator is responsible for combining them via reviewed policy.

### 8.1. Precedence and deny rules

| Baseline tenant | ReBAC | OPA | Hybrid AND outcome |
|---|---|---|---|
| Deny | Allow | Allow | Deny |
| Allow | Deny | Allow | Deny |
| Allow | Allow | Deny | Deny |
| Allow | Allow | Allow | Allow |
| Allow | Timeout/error | Allow | Deny |
| Allow | Allow | Undefined/missing result | Deny |

Some use cases allow OR or admin overrides; in those cases, explicitly ensure "global mandatory denies" **never** sit inside a bypassable branch. `ROLE_SUPER_ADMIN` does not automatically waive legal holds or cross-tenant boundaries.

### 8.2. Why not send the entire document to the PDP?

Send only minimal required attributes: canonical ID/tenant, classification, status, and normalized risk conditions. Never push document contents, access tokens, raw cookies, or excess PII into decision logs. OPA decision logging and tracing are valuable yet can record `input`; configure redaction/masking and retention properly.

### 8.3. Revocation and consistency

A user revoked from OpenFGA while a cache still returns allow during its TTL creates an access window. OpenFGA provides **`MINIMIZE_LATENCY`** and **`HIGHER_CONSISTENCY`** query preferences: the latter bypasses cache to read the data store, trading off latency. That alone **does not guarantee** atomic transactions across your business DB and OpenFGA, nor does it clear stale data in other layers.

In OPA, policy bundle/data updates also incur propagation delay; sidecars on different nodes may pick up new versions at different times. You can:
- Track versions of policies/models and relationship writes.
- Emit invalidation events on revocation.
- Use higher-consistency checks after recent changes or for sensitive actions.
- Define a revocation SLA and test it on your production topology.
- Never allow "fall back to stale cache allow" when the PDP is unavailable without a security proof.

## 9. Synchronizing relationships and business data: source of truth

In a ReBAC service, a tuple `document:t1-101#viewer@user:bob` can linger after Document#101 is deleted in the domain DB if lifecycles are unlinked. If a document moves to another tenant, an old parent tuple might still derive access from the original tenant. Design a mutation workflow:

```text
User shares Document#101 with Bob
    |
    v
Validate actor canShare + recipient tenant
    |
    v
Persist business share intent / version
    |
    v
Write relationship tuple
    |
    v
Audit + publish/reconcile + test effective Check
```

**There is no default JDBC transaction** spanning your Spring database and OPA/OpenFGA HTTP. Options:
- Business DB as source of truth: a transaction writes share metadata + outbox, and a worker syncs tuples with retries/idempotency; while pending, policy must define clear behavior (e.g., deny until confirmed).
- ReBAC store as the relationship source of truth: domain DB holds resource/tenant metadata, and mutations ensure idempotency and reconciliation.
- Event-sourced projections/versions for relationships; monitor lag and alert on "stale grants".

With OPA, if membership data is bundled inside policy bundles, DB permission changes do not take immediate effect across all sidecars. If Spring queries a runtime PIP, latency and consistency depend on where checks occur. Never update a business record and assume every PDP already sees it.

### 9.1. Risk of "permissions on a new object ID"

If IDs are reused, a tuple granting access to `document:t1-101` could apply to a brand-new object. Use canonical immutable object IDs, delete/reconcile tuples on deletion, and never treat a client-chosen raw ID as tenant proof.

### 9.2. Child objects and list/search

Document listing is a special flow:
- ReBAC `ListObjects` can find object IDs where the user holds the required relation.
- OPA can support partial evaluation to generate data-filtering predicates when properly integrated.
- DB queries still need tenant/visibility predicates and must apply **permission filters before pagination/counting**.
- Never simply fetch 100 rows and call a remote PDP 100 times to filter them—that causes N+1 latency, empty pages, and metadata leakage.
- Use batch checks, query pushdown, cursor semantics, cardinality limits, and caching where appropriate; test empirically on large lists.

A `ListObjects` result **does not replace** verifying at serve time that the resource still exists, is not soft-deleted, belongs to the verified tenant, and allows the requested action.

## 10. Operations, availability, and security of the PDP

### 10.1. Fail-closed by action

When OPA/OpenFGA is unavailable, responses lack `result/allowed`, JSON is malformed, requests time out, or the model ID is wrong, sensitive permissions must generally **DENY**. Never write `catch(Exception){return true;}`.

For critical endpoints, consider:
- Short, bounded timeouts; never let requests hang indefinitely.
- Circuit breakers and **budgeted** retries; retry storms can collapse a struggling PDP further.
- Bulkheads/rate limiting, queueing, and capacity planning.
- Separate health/readiness probes: a service should not accept traffic if it cannot enforce mandatory policies.
- Fallbacks only for **public/read-only** paths when offline entitlement is proven and does not bypass revocations; never apply blanket fallbacks.
- Metrics distinguishing `DENY_POLICY`, `DENY_UNAVAILABLE`, `DENY_INVALID_RESPONSE`, and `DENY_STALE_DATA` for operations.

### 10.2. Securing the PDP endpoint

The OPA HTTP server or OpenFGA API must sit in a trusted network with restricted access; use mTLS/service identity/bearer authentication and least privilege. Specifically, permissions to **write policies/tuples** are far more dangerous than **querying Check**. Never issue relationship-write tokens to every service that only needs read checks.

OpenFGA store/model IDs must live in versioned server configuration, never allowing clients to specify another model ID for an easier policy. Rego bundles need signing/verification, reviews, and rollbacks. Secrets must never be hardcoded in code/READMEs or decision audit logs.

### 10.3. Logging decisions without leaking data

Each decision should capture:
- `correlationId/requestId`, canonicalized principal ID.
- canonical tenant and resource IDs, action, policy/model version.
- decision (allow/deny), engine, reason category, latency.
- freshness or consistency preference if applicable.
- Never log raw JWTs, file contents, sensitive PII, or raw request bodies.

OPA has decision logs; ReBAC services also offer telemetry/tracing depending on deployment. Combine them with application audits to prove **the PEP actually blocked** the target method, not only that "the PDP returned deny".

### 10.4. Rollouts without unexpected permission shifts

Use:
1. Shadow evaluation: new PDP evaluates without enforcing, comparing outcomes against the legacy policy.
2. Categorize diffs: old allow/new deny, old deny/new allow, data errors, timeouts.
3. Security review **especially for old deny → new allow**.
4. Canary a few routes/tenants using server-side feature flags and pinned model versions.
5. Clear rollback plan; verify caches and tuple/model state.
6. Switch primary enforcement only after stabilization, monitoring deny/error rates and revocation lag.

**Shadow mode does not grant permissions**: actual decisions must still follow the trusted legacy policy until cutover.

## 11. POC evaluation criteria before selecting

A POC can test the following scenarios:

| ID | Scenario | Expected outcome |
|---|---|---|
| P01 | Owner reads ACTIVE doc in right tenant, valid relation, OPA allow | Allow |
| P02 | Cross-tenant user tries with spoofed header | Deny |
| P03 | Same-tenant member without share | Deny |
| P04 | Group membership grants indirect access | Allow if policy permits |
| P05 | Folder permission inherited by child document | Allow per inheritance model |
| P06 | CONFIDENTIAL document, relationship allows yet OPA denies | Deny |
| P07 | Archived/deleted document, both PDPs allow | Deny at baseline |
| P08 | Tuple revoked, re-checked immediately and after TTL | Within revocation SLA |
| P09 | OPA bundle update across multiple sidecars | Policy version within rollout SLA |
| P10 | Wrong model ID or nonexistent relation | Deny + error metric |
| P11 | HTTP timeout/500 from PDP | Deny, bounded latency |
| P12 | OPA 200 but missing `result` | Deny |
| P13 | OpenFGA 200 but missing or false `allowed` | Deny |
| P14 | Batch/list 10,000 objects with pagination/count | No data leak, meets P95 |
| P15 | Object moved to another tenant | Does not retain unauthorized grant |
| P16 | Two services share the same policy version | Consistent decisions |
| P17 | PDP disconnected for 5 minutes | Never fails open |
| P18 | Unauthorized attempt to write tuples/OPA bundles | Only authorized actors change policy |

Set measurable thresholds for every POC: P95/P99 latency, error rate, queries per call, propagation delay, cache hit/miss, cost, and team ownership. Do not decide from a "Hello World" demo with one user and one tuple.

### 11.1. Scoring rubric for selection

A practical approach is scoring 1–5 across:
- Ability to model current and projected 12–24 month use cases.
- Ability to prove tenant isolation/revocation.
- Reliability, latency, and resilience during PDP outages.
- List/search integration and large dataset scaling.
- Implementation/migration, operational, and on-call costs.
- Governance: reviews, CI tests, policy/model versioning, audits.
- SDK/API/tooling understood and maintainable by the team.

You might assign weights such as 25% correctness, 20% model fit, 20% operations, 15% performance, 10% integration, and 10% cost **as an example**, but weights must reflect your organization's risks. Do not claim any single "standard" scorecard fits every product.

## 12. Common integration mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| HTTP 200 from OPA/FGA means allow | Missing `result` or `allowed` causes privilege escalation | Allow only on strict boolean true |
| Taking `tenantId`/`isAdmin` from body as PDP input | Right policy on spoofed input | Server-side PIP, canonical tenant |
| `OPA.allow OR FGA.allow` for mandatory rules | Bypasses rules on one side | Baseline AND, clear policy precedence |
| Using ReBAC-only for data with mandatory classification | Skips compliance guard | Hybrid or equivalent condition/guard |
| Putting all groups/relations into OPA JSON per request | Large context, staleness, and slow performance | Evaluate graph store or structured data sync |
| Using FGA yet forgetting to delete tuples on resource deletion | Orphan grants/reused IDs | Lifecycle/outbox/reconciliation |
| Everything in `@PostAuthorize` | Side effects run before denial | `@PreAuthorize`, transactions, guarded DML |
| Falling back to allow on remote PDP exception | Fail-open during outages | Explicit fail-closed |
| Letting clients choose policy mode/model ID | Picks weaker policy | Server config pinning versions |
| Skipping tenant scope because FGA tracks relationships | Cross-tenant leak if a tuple is wrong | Canonical DB tenant + membership baseline |
| Untested OPA bundle or FGA model updates | Unexpected permission shifts | CI policy/model tests, canaries |
| Cache lacks tenant/action/version | Cross-user/tenant stale allow | Canonical cache keys and revocation invalidation |
| `ListObjects` returns IDs then skips DB scope | Exposes deleted/foreign-tenant objects | Re-check canonical visibility |
| List API calls PDP per row after paging | N+1 latency, wrong page/total | Batching/query pushdown/filter before paging |
| No tests for conflicting PDPs | Hybrid bypass goes undetected | Allow/deny/error matrix |
| Bean self-invocation | `@PreAuthorize` is bypassed | Proper Spring proxy/AspectJ |
| Sharing tuple-write privileges with check privileges | Easy self-escalation if service is compromised | Least-privilege tokens |

## 13. Design and implementation checklist

- [ ] Subject–action–resource–context defined; canonical ownership and tenant.
- [ ] Mandatory deny conditions identified that cannot be bypassed by admin/OR.
- [ ] Real count of relationships/groups/inheritance compared against attribute/context rules.
- [ ] OPA, ReBAC, or hybrid chosen from use cases, POCs, and SLAs—not buzzwords.
- [ ] PEP at `SecurityFilterChain` or Spring-managed services; all entrypoints covered.
- [ ] Trusted authentication and PIP; never grant permissions from client headers/bodies.
- [ ] Tenant membership and resource tenant verified before or with PDP decisions, never solely from client.
- [ ] PDP input/response have schemas/versions; missing/unknown => deny.
- [ ] OPA uses `{"input":...}` and checks `result === true`; undefined cases tested.
- [ ] ReBAC uses user/relation/object with pinned model ID, tuple lifecycle, and canonical identity.
- [ ] Hybrid composition has proven precedence, fail-closed, and negative tests.
- [ ] Policy/model/tuple updates have audits, reviews, CI, version pinning, and rollbacks.
- [ ] Bounded timeouts/retries/circuit breakers, TLS, and least-privilege inter-service secrets.
- [ ] Consistency/cache/revocation SLA plan exists when immediate effect is needed.
- [ ] Business DB ↔ relationship store sync (outbox/reconciliation) without assuming distributed transactions.
- [ ] `ListObjects`, search, count, and export enforce tenant/permission predicates before paging.
- [ ] Decisions logged with correlation ID and policy/model version; sensitive data redacted.
- [ ] Benchmarked P50/P95/P99, error rate, memory, graph depth, and cost.
- [ ] Full allow/deny/mismatch/error test matrix executed, not only mocked ports.

## 14. Self-check questions

**Question 1.** An application allows sharing folders with groups and inheriting permissions across thousands of documents. Is OPA or ReBAC the natural initial choice?

**Answer:** ReBAC (such as OpenFGA) is usually the natural fit because relationships/groups/inheritance are its core abstraction. You must still benchmark performance, tenant isolation, and real list queries.

**Question 2.** A system has many clearance, transaction-time, risk-score, and compliance rules, with minimal object sharing. Where should you start?

**Answer:** OPA/Rego or a similar policy-as-code engine usually fits better; pay attention to PIP data freshness, bundle distribution, and tests.

**Question 3.** FGA Check returns `allowed=true` yet OPA returns `result=false` for a CONFIDENTIAL document. What does hybrid AND decide?

**Answer:** Deny. A relationship is necessary but does not override mandatory classification rules.

**Question 4.** The OPA Data API returns HTTP 200 with body `{}`. Should access be allowed?

**Answer:** No. Missing `result` can occur when a document/rule is undefined. Only strict boolean true grants access.

**Question 5.** You revoke a tuple and immediately call Check with `MINIMIZE_LATENCY`. Why might the old permission still appear?

**Answer:** If caching is active within its TTL, the API may serve a cached response. Consider `HIGHER_CONSISTENCY` for paths needing freshness, while still accounting for consistency between your business DB and FGA.

**Question 6.** Both PDP ports return allow for a document in t2, yet the user only belongs to t1. May the service return data?

**Answer:** No. Baseline tenant membership and the canonical tenant boundary must deny before PDPs ever become a basis for access.

## 15. Official references and further reading

- [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): custom `AuthorizationManager<RequestAuthorizationContext>`, Open Policy Agent integration example, and matcher ordering.
- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, policy beans, and proxy limitations.
- [OPA — Overview and Integration](https://www.openpolicyagent.org/docs): separation of policy decision vs enforcement, Rego, and calling OPA.
- [OPA — REST Data API](https://www.openpolicyagent.org/docs/rest-api): `POST /v1/data/{path}`, `{"input":...}`, `result`, and undefined results.
- [OPA — Rego v1](https://www.openpolicyagent.org/docs/policy-reference/keywords/import): `if` syntax and `import rego.v1` in older versions.
- [OpenFGA — Concepts](https://openfga.dev/docs/concepts): model, type, relation, tuple, and Check.
- [OpenFGA — Perform a Check](https://openfga.dev/docs/getting-started/perform-check): `POST /stores/{store_id}/check`, `authorization_model_id`, and `allowed`.
- [OpenFGA — Parent-Child Objects](https://openfga.dev/docs/modeling/parent-child): how folder/project permissions can affect child objects depending on model.
- [OpenFGA — Query Consistency Modes](https://openfga.dev/docs/interacting/consistency): `MINIMIZE_LATENCY`, `HIGHER_CONSISTENCY`, caching, and latency trade-offs.
- [OpenFGA — Conditional Tuples](https://openfga.dev/blog/conditional-tuples-announcement): support for conditions on relationships.
- [OWASP API Security Top 10 — BOLA](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): object-level authorization and client-chosen IDs.

**Conclusion:** Choose **OPA** when the focus is attribute/context rules managed as code; choose **ReBAC** when the focus is user–group–resource relationships, sharing, and inheritance; choose **hybrid** when you need both discretionary graph grants and mandatory contextual guards. Whichever PDP you pick, **Spring Security must enforce**, inputs must be trustworthy, tenants/resources must be verified, errors must fail closed, and you must test policies, models, data sync, and real HTTP integration.