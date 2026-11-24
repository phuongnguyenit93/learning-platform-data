# Minimal Attributes, Data Verification, and Protecting the Call Channel

> **Spring Security – authorization · Dynamic Policies.** This Knowledge lesson designs the authorization query flow from a Spring application (**Policy Enforcement Point – PEP**) to a **Policy Decision Point – PDP** such as Open Policy Agent (OPA): send only genuinely necessary attributes, verify their sources before sending, and protect both the communication channel and the returned result. Spring samples use Java 17+, Spring Boot 3.x, and Spring Security 6.x. Snippet blocks are distinct from standalone plain-Java programs runnable with `javac`.

## 1. Objectives and example

After this lesson, you can select the data needed for ABAC (subject/resource/action/environment), identify which attributes come from authentication/DB/directories rather than the client, use mTLS or service-to-service tokens properly, handle missing decisions fail-closed, and test a Spring Security PEP, OPA REST calls, and timeout/revocation/privacy scenarios.

Suppose tenant alpha has Alice (role EDITOR), Document 7 classification CONFIDENTIAL owner Alice; tenant beta has Bob (role READER), Document 7 classification INTERNAL owner Bob. Policy:
- The caller is authenticated and holds membership in the selected tenant.
- The record genuinely belongs to that tenant.
- INTERNAL: role READER or EDITOR can READ.
- CONFIDENTIAL: only an EDITOR who is also the owner can READ.
- All other actions/roles/classifications are DENY.

**Wrong: sending full context and sensitive content to the PDP**:

~~~json
{
  "requestHeaders": {"Authorization": "Bearer [raw JWT]"},
  "authentication": {"credentials": "[secret]", "principal": "[whole object]"},
  "document": {
    "id": 7, "title": "ALPHA:Secret",
    "body": "[confidential business content]",
    "ownerEmail": "alice@example.invalid",
    "classification": "CONFIDENTIAL"
  }
}
~~~

Even over TLS, those fields can end up in APM, debug logs, reverse proxies, or OPA decision logs.

**Right for the sample policy:**

~~~json
{
  "input": {
    "verifiedTenant": "alpha",
    "resourceTenant": "alpha",
    "role": "EDITOR",
    "action": "READ",
    "resourceType": "Document",
    "classification": "CONFIDENTIAL",
    "ownerMatches": true
  }
}
~~~

There is no need to send user tokens, owner emails, content, titles, all roles, or `documentId` when the rule does not need them. `ownerMatches` is computed by the PEP comparing the authenticated stable principal ID and trusted owner metadata—never copied from a client-declared boolean.

## 2. PEP/PDP/PIP/PAP and the trust path

| Component | Responsibility | Example |
| --- | --- | --- |
| PEP | Build verified requests, block/allow real actions | Spring application service |
| PDP | Evaluate policy from input | OPA or remote authorization service |
| PIP | Supply authoritative attribute data | User/tenant directory, document metadata DB |
| PAP | Manage, test, version, and roll out policies | Rego Git repository and bundles |
| Audit | Correlate requests, policy revisions, and decision IDs with execution outcomes | Controlled PEP/PDP logs |

~~~text
HTTP -> validated Authentication
     -> membership verified for requested tenant
     -> resource metadata WHERE tenant = verifiedTenant AND id = requestedId
     -> derived trusted role/classification/ownerMatches
     -> minimal typed PDP request
     -> HTTPS, server identity + service authentication
     -> PDP evaluates current policy
     -> only explicit ALLOW continues to protected read/write
     -> DENY/undefined/error/timeout never returns protected data
~~~

**The PEP must enforce**, not merely log. The PDP does not replace tenant predicates, transactions, object classification, or response redaction. Conversely, policies updated via bundles do not immediately refresh PIP values if membership/ACLs still sit in stale caches.

## 3. Minimal attribute contract

| Field | Send? | Source and rationale |
| --- | --- | --- |
| `verifiedTenant` | Yes | Membership of authenticated user in the selected tenant |
| `resourceTenant` | Yes | DB metadata, checks cross-tenant equality |
| `role` | Yes | Role for **that tenant** from trusted membership store |
| `action` | Yes | Server enum/constant, READ/WRITE with clear semantics |
| `resourceType` | Yes | Backend-determined canonical type |
| `classification` | Yes | Resource metadata; never from JSON request |
| `ownerMatches` | Yes | Derived boolean from trusted principal + DB owner |
| `subjectId`/`resourceId` | No in this policy | Add opaque IDs when object/user-specific rules require them |
| `title`/`document.body`/owner email | No | Unnecessary, causes disclosure |
| JWT/password/cookies/raw headers | No | Credentials belong to authentication, not policy attributes |
| IP/device/MFA/time/region | Rule-dependent | Only from trusted proxies/attestation/clocks with proper expiry |
| Policy/ACL/membership revision | Consistency-dependent | Must be real versions, never hardcoded latest |

Every field must define type, allow-listed enum, length, canonicalization, trusted source, freshness, privacy classification, schema version, and which policy consumes it. Unknown/missing values must never default to PUBLIC, EDITOR, or a grant. `verifiedTenant` is merely a field name—it **does not prove on its own** that verification occurred.

### 3.1. Subject

In Servlet apps, Spring Security places `Authentication` into `SecurityContextHolder` after authentication filters/providers verify it. With JWTs, validate signature, issuer, expiry/nbf, and audience per resource server policy. `Authentication#getName()` may be a username or stable user ID depending on configuration; maintain a consistent convention.

A user may be EDITOR in alpha and READER in beta. Passing alpha's role into beta's decision is an authorization bug. If roles change, membership caches/token claims can go stale; define freshness/revocation SLAs.

### 3.2. Resource

Query scoped by tenant:

~~~java
Optional<DocumentMetadata> meta =
        repository.findByTenantIdAndId(verifiedTenant, documentId);
~~~

Instead of a global query:

~~~java
Optional<DocumentMetadata> meta = repository.findById(documentId);
~~~

A valid ID belonging to another tenant must never appear in the current tenant's lookup. For sensitive resources, use a metadata projection to check permissions before loading full content, and transaction/version checks to prevent a resource from changing tenant/owner/classification between PDP decision and DB operation.

### 3.3. Environment

Never trust `X-Forwarded-For` or `deviceTrusted=true` declared by the client. Real client IPs require trusted ingress; device posture requires signed attestation/MDM; MFA age requires authentication events; time-based policies require a trusted clock and skew policy. Do not add fields if the policy does not use them.

### 3.4. Who may assert high-trust booleans?

mTLS authenticates the calling service, yet does not prove `ownerMatches=true` was computed accurately. If the PDP does not fully trust the PEP, it can fetch owner/tenant/classification from an independent PIP, verify signed claims/attestation, or enforce its own policy on which workloads may assert which attributes. The design must document **the source of every fact**.

## 4. Protecting the PDP call channel

Three independent layers must coexist:
1. **TLS/HTTPS:** PEP verifies CA/certificate chain, hostname/SAN, and encrypts traffic. Never use trust-all or disable hostname verification.
2. **Workload authentication:** PDP knows which PEP service is calling via client mTLS certificates or machine-to-machine tokens with checked issuer/audience/scope/expiry. Never forward Alice's raw JWT as a shared credential.
3. **PDP authorization:** the service may query only its target policy endpoint—never `PUT /v1/policies` or read raw sensitive `data` unless authorized.

Add host/port allowlists to prevent SSRF (never take the PDP URL from requests), block cross-host redirects, manage secret/cert rotation, bound connect/read timeouts, limit pools/concurrency, apply rate limiting, emit metrics, and never log credentials.

The OPA service must **have authentication/authorization configured**; never assume APIs are locked down by default. With mTLS, configure server TLS, trusted client CAs, `--authentication=tls`, `--authorization=basic`, and `system.authz` policies restricting APIs. Localhost/sidecar reduces network hops yet is not a security boundary on its own if other processes can call it.

**Never** work around certificate errors using `curl -k`, `trustAll`, downgrading to HTTP, or disabling hostname validation. Fix the CA/SAN/truststore/DNS/cert rotation instead.

## 5. OPA REST Data API: only Boolean true means ALLOW

Request:

~~~http
POST /v1/data/app/documents/allow HTTP/1.1
Host: pdp.internal.example
Content-Type: application/json

{"input":{"verifiedTenant":"alpha","resourceTenant":"alpha","role":"EDITOR","action":"READ","resourceType":"Document","classification":"CONFIDENTIAL","ownerMatches":true}}
~~~

A named policy decision may return:

~~~json
{"result":true}
~~~

or:

~~~json
{"result":false}
~~~

If the rule/path is undefined, the OPA Data API can return HTTP 200 with body:

~~~json
{}
~~~

**That is NOT ALLOW.** `status==200`, `body!=null`, or `body.contains("true")` are all insufficient. Parse a typed result; only strictly `Boolean.TRUE` opens access. If the PDP returns obligations (`maskFields`, `filterRows`, `requireMFA`), the PEP must validate and enforce them—never ignore them.

| PDP state | PEP |
| --- | --- |
| 2xx + result Boolean true | May allow if all local invariants hold |
| result false | Deny |
| result missing/null/wrong type | Error closed / deny |
| HTTP 401/403 | Error closed, check workload credentials/authorization |
| HTTP 404/500, timeout, DNS/TLS failure | Error closed, never fall back to permitAll |
| ALLOW yet resource tenant differs | Deny |
| ALLOW yet resource/role changes before write | Revalidate in transaction |
| Cached ALLOW after revocation | Do not use unless freshness is guaranteed |

Fail closed does not always mean 403. A PDP outage can return API 503 so clients can retry, while never executing the protected operation. Internal metrics should distinguish `POLICY_DENIED`, `UNDEFINED`, `UNAVAILABLE`, `MALFORMED`, and `INVALID_CONTEXT` without leaking cross-tenant data in responses.

## 6. Spring Boot demo: PEP and simulated PDP to verify the flow

The demo runs without OPA using `LocalDecisionClient`. The remote OPA adapter is in the next section. Examples require Spring Boot 3.x, Java 17+, and Spring Web/Security.

Save `src/main/java/demo/dynamic/DynamicPolicyApplication.java`:

~~~java
package demo.dynamic;

import java.util.Map;
import java.util.Optional;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
@EnableMethodSecurity
public class DynamicPolicyApplication {
    public static void main(String[] args) {
        SpringApplication.run(DynamicPolicyApplication.class, args);
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http.authorizeHttpRequests(a -> a
                    .requestMatchers("/api/tenants/**").authenticated()
                    .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice").password("{noop}demo")
                    .authorities("document:read").build(),
                User.withUsername("bob").password("{noop}demo")
                    .authorities("document:read").build(),
                User.withUsername("carol").password("{noop}demo")
                    .authorities("document:read").build(),
                User.withUsername("viewer").password("{noop}demo")
                    .authorities("profile:read").build());
    }
}

record Document(long id, String tenant, String classification,
                String owner, String title) {}
record DocKey(String tenant, long id) {}
record DocumentView(long id, String tenant, String title) {}

record PdpInput(String verifiedTenant, String resourceTenant,
                String role, String action, String resourceType,
                String classification, boolean ownerMatches) {}

interface DecisionClient {
    boolean allow(PdpInput input);
}

@Component
class TenantMemberships {
    private final Map<String, Map<String,String>> roles = Map.of(
            "alice", Map.of("alpha","EDITOR"),
            "bob", Map.of("beta","READER"),
            "carol", Map.of("alpha","READER"));

    String requireRole(Authentication actor, String tenant) {
        if (actor == null || !actor.isAuthenticated()
                || actor instanceof AnonymousAuthenticationToken
                || tenant == null
                || !tenant.matches("[a-z][a-z0-9-]{0,31}")) {
            throw new AccessDeniedException("Tenant access denied");
        }
        String role = roles.getOrDefault(
                actor.getName(),Map.of()).get(tenant);
        if (role == null) {
            throw new AccessDeniedException("Tenant access denied");
        }
        return role;
    }
}

@Component
class DocumentStore {
    private final Map<DocKey,Document> data = Map.of(
            new DocKey("alpha",7L),
                new Document(7L,"alpha","CONFIDENTIAL",
                             "alice","ALPHA:Secret"),
            new DocKey("beta",7L),
                new Document(7L,"beta","INTERNAL",
                             "bob","BETA:Public"),
            new DocKey("alpha",8L),
                new Document(8L,"alpha","INTERNAL",
                             "carol","ALPHA:Public"));

    Optional<Document> findWithinTenant(String tenant, long id) {
        return Optional.ofNullable(data.get(new DocKey(tenant,id)));
    }
}

@Component
@Profile("!remote-pdp")
class LocalDecisionClient implements DecisionClient {
    private volatile PdpInput lastInput;

    @Override
    public boolean allow(PdpInput p) {
        lastInput = p;
        if (p == null || !"READ".equals(p.action())
                || !"Document".equals(p.resourceType())
                || !p.verifiedTenant().equals(p.resourceTenant())) {
            return false;
        }
        boolean allowedRole = "READER".equals(p.role())
                || "EDITOR".equals(p.role());
        if ("INTERNAL".equals(p.classification())) {
            return allowedRole;
        }
        if ("CONFIDENTIAL".equals(p.classification())) {
            return "EDITOR".equals(p.role()) && p.ownerMatches();
        }
        return false;
    }

    PdpInput lastInput() {
        return lastInput;
    }
}

@Service
class DocumentService {
    private final TenantMemberships memberships;
    private final DocumentStore store;
    private final DecisionClient client;

    DocumentService(TenantMemberships memberships,
                    DocumentStore store, DecisionClient client) {
        this.memberships = memberships;
        this.store = store;
        this.client = client;
    }

    @PreAuthorize("hasAuthority('document:read')")
    public DocumentView read(String requestedTenant, long id) {
        Authentication auth = SecurityContextHolder
                .getContext().getAuthentication();
        String role = memberships.requireRole(auth, requestedTenant);
        Document doc = store.findWithinTenant(requestedTenant,id)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Document not found"));

        // ownerMatches is built by the PEP from trusted auth and resource metadata.
        PdpInput input = new PdpInput(
                requestedTenant, doc.tenant(), role, "READ",
                "Document", doc.classification(),
                doc.owner().equals(auth.getName()));
        boolean grant;
        try {
            grant = client.allow(input);
        } catch (RuntimeException unavailable) {
            throw new AccessDeniedException(
                    "Authorization service unavailable", unavailable);
        }
        if (!grant) {
            throw new AccessDeniedException("Policy denied");
        }
        return new DocumentView(doc.id(),doc.tenant(),doc.title());
    }
}

@RestController
@RequestMapping("/api/tenants/{tenant}/documents")
class DocumentController {
    private final DocumentService service;

    DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    DocumentView read(@PathVariable("tenant") String tenant,
                      @PathVariable("id") long id) {
        return service.read(tenant,id);
    }
}
~~~

Data flow is protected by route authentication, method `@PreAuthorize`, tenant membership, scoped document lookup, typed PDP input, and explicit allow. `PdpInput` has seven fields and sends no content, title, ownerId, or user JWT to the PDP. In production code, use a DB metadata projection and fetch full content only after ALLOW; enforce transaction/version constraints so resources cannot change between check and use.

Gradle dependencies (plugins/configuration already present in the project):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

`{noop}` passwords and in-memory users are strictly for the demo; production uses trusted password encoders, proper JWT/session setup, and persistent directories.

## 7. MockMvc: verifying the PEP truly enforces

Save `src/test/java/demo/dynamic/DynamicPolicyApplicationTest.java`:

~~~java
package demo.dynamic;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
        .jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
        .status;

@SpringBootTest
@AutoConfigureMockMvc
class DynamicPolicyApplicationTest {
    @Autowired MockMvc mvc;
    @Autowired LocalDecisionClient pdp;

    @Test
    void aliceReadsOwnConfidentialDoc() throws Exception {
        mvc.perform(get("/api/tenants/alpha/documents/7")
                    .with(httpBasic("alice","demo")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("ALPHA:Secret"));
        PdpInput p = pdp.lastInput();
        assertNotNull(p);
        assertEquals("alpha",p.verifiedTenant());
        assertEquals("EDITOR",p.role());
        assertTrue(p.ownerMatches());
    }

    @Test
    void bobReadsBetaWithSameDocumentId() throws Exception {
        mvc.perform(get("/api/tenants/beta/documents/7")
                    .with(httpBasic("bob","demo")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("BETA:Public"));
    }

    @Test
    void bobCannotSelectAlpha() throws Exception {
        mvc.perform(get("/api/tenants/alpha/documents/7")
                    .with(httpBasic("bob","demo")))
                .andExpect(status().isForbidden());
    }

    @Test
    void carolCannotReadAliceConfidentialDoc() throws Exception {
        mvc.perform(get("/api/tenants/alpha/documents/7")
                    .with(httpBasic("carol","demo")))
                .andExpect(status().isForbidden());
    }

    @Test
    void anonymousAndViewerAreRejected() throws Exception {
        mvc.perform(get("/api/tenants/alpha/documents/7"))
                .andExpect(status().isUnauthorized());
        mvc.perform(get("/api/tenants/alpha/documents/7")
                    .with(httpBasic("viewer","demo")))
                .andExpect(status().isForbidden());
    }

    @Test
    void pdpInputHasOnlyWhitelistedFields() throws Exception {
        mvc.perform(get("/api/tenants/alpha/documents/7")
                    .with(httpBasic("alice","demo")))
                .andExpect(status().isOk());
        PdpInput p = pdp.lastInput();
        assertNotNull(p);
        assertEquals(7,PdpInput.class.getRecordComponents().length);
        assertFalse(p.toString().contains("ALPHA:Secret"));
        assertFalse(p.toString().contains("ownerId"));
        assertFalse(p.toString().contains("Bearer "));
    }
}
~~~

This test passes through the Spring HTTP filter and method-security proxy with a simulated PDP; it **cannot prove TLS/mTLS**. If parallel JUnit execution is enabled, `lastInput` on a singleton is simple instrumentation that risks cross-test interference—replace with spies/context isolation. Never store `PdpInput` in a singleton field in production.

## 8. Real OPA adapter with RestClient and mTLS

Spring Boot 3.2+ provides `RestClientSsl` to apply SSL bundles. Create `src/main/java/demo/dynamic/RemotePdpConfiguration.java`:

~~~java
package demo.dynamic;

import java.net.URI;

import com.fasterxml.jackson.annotation.JsonProperty;
import org.springframework.boot.autoconfigure.web.client.RestClientSsl;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.core.env.Environment;
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

@Configuration
@Profile("remote-pdp")
class RemotePdpConfiguration {
    @Bean
    RestClient opaHttp(RestClient.Builder builder,
                       RestClientSsl ssl, Environment env) {
        URI endpoint = URI.create(
                env.getRequiredProperty("app.pdp.base-url"));
        if (!"https".equalsIgnoreCase(endpoint.getScheme())
                || !"pdp.internal.example".equalsIgnoreCase(
                        endpoint.getHost())
                || endpoint.getUserInfo() != null
                || endpoint.getRawQuery() != null
                || endpoint.getRawFragment() != null) {
            throw new IllegalArgumentException("Untrusted PDP endpoint");
        }

        return builder.baseUrl(endpoint.toString())
                .apply(ssl.fromBundle("pdp-client"))
                .build();
    }

    @Bean
    DecisionClient remoteDecisionClient(RestClient opaHttp) {
        return new OpaDecisionClient(opaHttp);
    }
}

record OpaRequest(PdpInput input) {}
record OpaResponse(Boolean result,
        @JsonProperty("decision_id") String decisionId) {}

final class OpaDecisionClient implements DecisionClient {
    private final RestClient http;

    OpaDecisionClient(RestClient http) {
        this.http = http;
    }

    @Override
    public boolean allow(PdpInput input) {
        if (input == null) return false;
        try {
            OpaResponse reply = http.post()
                    .uri("/v1/data/app/documents/allow")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(new OpaRequest(input))
                    .retrieve().body(OpaResponse.class);
            return reply != null
                    && Boolean.TRUE.equals(reply.result());
        } catch (RestClientException error) {
            return false;
        }
    }
}
~~~

Responses missing `result`, null result, or false do not ALLOW. Type-mismatched JSON/HTTP errors usually throw client exceptions and get blocked; the service also has a final `RuntimeException` catch. In production, classify network/schema errors for alerting and consider returning API 503 while still failing closed.

**Note:** `ssl.fromBundle(...)` may replace the request factory. Configure timeouts, retries, pooling, and redirect policies inside the same SSL-compatible request factory and test against your Spring Boot version rather than assuming timeouts configured before `apply` remain intact. Verify CA, client cert, hostname verification, rotation, and authorized PDP endpoints.

Sample configuration:

~~~yaml
app:
  pdp:
    base-url: https://pdp.internal.example:8181

spring:
  ssl:
    bundle:
      pem:
        pdp-client:
          keystore:
            certificate: file:/run/secrets/pdp-client.crt
            private-key: file:/run/secrets/pdp-client.key
          truststore:
            certificate: file:/run/secrets/pdp-ca.crt
~~~

Never commit private keys/tokens into source control; file paths represent mounted secrets. Enable the `remote-pdp` profile only when the PDP server has mTLS/authz configured. A client SSL bundle does not automatically enable authentication on the OPA server.

Corresponding Rego:

~~~rego
package app.documents

import rego.v1

default allow := false

tenant_match if {
    input.verifiedTenant == input.resourceTenant
}

known_role if {
    input.role == "READER"
}
known_role if {
    input.role == "EDITOR"
}

allow if {
    tenant_match
    input.action == "READ"
    input.resourceType == "Document"
    input.classification == "INTERNAL"
    known_role
}

allow if {
    tenant_match
    input.action == "READ"
    input.resourceType == "Document"
    input.classification == "CONFIDENTIAL"
    input.role == "EDITOR"
    input.ownerMatches == true
}
~~~

When fields are missing or unknown, defaults to false. This is illustrative Rego logic, lacking production policy rollout, bundle signatures, and external PIP trust rules. A mocked REST client test proves only parsing/shape. Open real connections in an mTLS test environment to test missing/expired certs, wrong hostnames, 401/403, and restricted management APIs.

## 9. Standalone Java 17: minimal attributes and fail closed

This program **runs on plain JDK**, without Spring/OPA/TLS. It demonstrates tenant-scoped lookup, trusted role mapping, and sending only six attributes for a fixed Document resource type policy.

Save `MinimalAttributeDemo.java`:

~~~java
import java.util.Map;

public class MinimalAttributeDemo {
    record Key(String tenant, long id) {}
    record Doc(String tenant, String classification,
               String owner, String title) {}
    record User(String name, Map<String,String> roles) {}
    record MinimalInput(String verifiedTenant,
                        String resourceTenant, String role,
                        String action, String classification,
                        boolean ownerMatches) {}

    static final Map<Key,Doc> DATA = Map.of(
            new Key("alpha",7L),
                new Doc("alpha","CONFIDENTIAL","alice","ALPHA:Secret"),
            new Key("beta",7L),
                new Doc("beta","INTERNAL","bob","BETA:Public"),
            new Key("beta",9L),
                new Doc("beta","INTERNAL","bob","BETA:Another"));

    static boolean policy(MinimalInput in) {
        if (!in.verifiedTenant().equals(in.resourceTenant())
                || !"READ".equals(in.action())) return false;
        boolean known = "EDITOR".equals(in.role())
                || "READER".equals(in.role());
        if ("INTERNAL".equals(in.classification())) return known;
        if ("CONFIDENTIAL".equals(in.classification())) {
            return "EDITOR".equals(in.role()) && in.ownerMatches();
        }
        return false;
    }

    static String read(User user, String tenant, long id,
                       boolean pdpAvailable) {
        if (user == null || tenant == null) return "DENY_TENANT";
        String role = user.roles().get(tenant);
        if (role == null) return "DENY_TENANT";
        Doc doc = DATA.get(new Key(tenant,id));
        if (doc == null) return "NOT_FOUND";
        MinimalInput input = new MinimalInput(
                tenant,doc.tenant(),role,"READ",
                doc.classification(),user.name().equals(doc.owner()));
        if (!pdpAvailable) return "DENY_UNAVAILABLE";
        if (!policy(input)) return "DENY_POLICY";
        return "ALLOW:" + doc.title();
    }

    public static void main(String[] args) {
        User alice = new User("alice",Map.of("alpha","EDITOR"));
        User bob = new User("bob",Map.of("beta","READER"));
        User carol = new User("carol",Map.of("alpha","READER"));

        System.out.println("alice-alpha=" +
                read(alice,"alpha",7L,true));
        System.out.println("bob-beta=" +
                read(bob,"beta",7L,true));
        System.out.println("bob-alpha=" +
                read(bob,"alpha",7L,true));
        System.out.println("carol-confidential=" +
                read(carol,"alpha",7L,true));
        System.out.println("beta-resource-via-alpha=" +
                read(alice,"alpha",9L,true));
        System.out.println("pdp-unavailable=" +
                read(alice,"alpha",7L,false));

        MinimalInput input = new MinimalInput(
                "alpha","alpha","EDITOR","READ","CONFIDENTIAL",true);
        System.out.println("payload-fields=" +
                MinimalInput.class.getRecordComponents().length);
        System.out.println("payload-contains-title=" +
                input.toString().contains("ALPHA:Secret"));
    }
}
~~~

Commands:

~~~bash
javac --release 17 MinimalAttributeDemo.java
java MinimalAttributeDemo
~~~

Exact stdout:

~~~text
alice-alpha=ALLOW:ALPHA:Secret
bob-beta=ALLOW:BETA:Public
bob-alpha=DENY_TENANT
carol-confidential=DENY_POLICY
beta-resource-via-alpha=NOT_FOUND
pdp-unavailable=DENY_UNAVAILABLE
payload-fields=6
payload-contains-title=false
~~~

The program proves minimal payload logic without verifying HTTPS or user credentials. For production Java, assembling HTTP requests must happen in an authenticated, host-bound service.

## 10. Dynamic permissions, caching, and TOCTOU

Between t1 when the PDP decides and t2 when SQL updates, owner/classification/tenant or membership can change. For sensitive write operations, protect with transactions, optimistic versioning/locks, and conditional predicates:

~~~sql
UPDATE document
SET title = :newTitle, version = version + 1
WHERE tenant_id = :verifiedTenant
  AND id = :id
  AND version = :expectedVersion;
~~~

Check the row count; never fall back to a tenant-less UPDATE. If rules depend on classification/owner, verify inside the same transaction or add predicates/versions per data model.

**Cached ALLOWs** must include tenant, principal, resource type/id, action, real membership/ACL/policy/resource revisions in the key, plus proper invalidation. For sensitive data, skipping ALLOW caching is often simpler and safer. A 5-minute TTL does not meet immediate revocation needs. Old token roles and sidecar bundle eventual consistency can also go stale even without decision caching.

`{"result":true}` is not a bearer token reusable across resources. If using signed decision tokens, include audience/action/subject/tenant/resource bindings, expiry, nonce/replay protections, and a reviewed signature—never invent a custom crypto scheme.

PDP unavailable: bounded timeouts, circuit breakers, budgeted retries, rate limiting, and local PDP/sidecars where availability requires them; never write `catch(Exception) { return true; }`.

With `@Async`/queues, thread-local security context/tenant can be lost or leak across tasks. Use context capture/cleanup in `finally`, explicit trusted tenant parameters, and worker-side revalidation at use time. Never serialize a raw `SecurityContext`/JWT onto a queue as a permanent decision.

## 11. Decision logs and personal data

The PEP can record stable actor ID, resource type/ID, verified tenant, action, decision outcome, request correlation ID, and PDP decision ID; the PDP only needs minimal `PdpInput`. When enabled, OPA decision logs can store input/result/bundle revision, with `data.system.log.mask` to scrub/mask sensitive fields. Audit the application, HTTP clients, APM, ingress, and exporters; never log authorization headers, document bodies, emails, access tokens, or client private keys.

mTLS reduces eavesdropping risk yet **does not erase** privacy obligations for tenant/role/opaque IDs. When the PDP sits in another region, assess data residency, retention, log viewers, and re-identification risks. PDP ALLOW does not prove a file finished downloading; investigations require correlating response/business/storage access logs.

## 12. Pre-production test matrix

| Case | Expected outcome |
| --- | --- |
| Alice owner confidential, role EDITOR alpha | ALLOW |
| Bob role READER beta, same ID 7 | ALLOW beta, no leak of alpha |
| Bob selects alpha | DENY before PDP |
| Carol READER alpha on Alice's confidential doc | DENY |
| Spoofed tenant selector/path, spoofed role header | Trusted attributes unchanged |
| Client spoofs classification/ownerMatches | PEP uses DB/auth, never body |
| Resource does not exist in tenant | 404/no metadata leak |
| Anonymous user or missing feature authority | DENY |
| Null/unknown enum/malformed JSON | DENY/error closed |
| PDP `{"result":true}` | ALLOW if local invariants pass |
| PDP `{"result":false}` or `{}` | DENY |
| HTTP 200 with wrong result type | ERROR CLOSED |
| PDP 401/403/500 or timeout | No grant |
| Untrusted CA, wrong hostname, expired client cert | No connection/no grant |
| Runtime service tries to update policy | Rejected by PDP authorization |
| Cross-host redirect/SSRF | Blocked |
| Membership/ACL revoked after cache warm | Never use stale ALLOW |
| Resource state changes between check/write | Transaction/version guard |
| `@Async` worker reuses thread | Never retains previous tenant |
| Decision logs enabled | No raw JWT/content/excess PII |
| `MockRestServiceServer` test passes | Do not claim mTLS was tested |
| Multi-PDP policy revision mismatch | Monitored per consistency contract |

Mutation testing: intentionally remove the membership check, drop the tenant predicate, force `ownerMatches` to true, or treat HTTP 200 as ALLOW—negative tests must fail. If they stay green, the suite is not guarding the boundary.

## 13. Common pitfalls and mitigations

- Sending raw tokens/Authentication/JPA entities: replace with an allowlist of typed attributes.
- Trusting role/tenant from headers or JSON: verify via authentication/membership/DB.
- TLS without workload identity: add mTLS/tokens and PDP authorization.
- Disabling certificate validation: fix CA/SAN/truststore, never trust-all.
- Letting PEP services query/update all OPA APIs: restrict to policy endpoints.
- Treating HTTP 200 as ALLOW: require strict Boolean true per contract.
- Permitting all on PDP timeout: fail-open; instead deny/503 with zero side effects.
- Caching decisions by document ID alone: missing tenant/principal/action/revisions.
- Skipping resource state checks between PDP decision and DB write: use transaction/version checks.
- Client-declared owner boolean: compute from principal + DB, or let the PDP fetch from a PIP.
- Trusting arbitrary IP/region/device headers: environment sources require attestation/trusted proxies.
- Logging full inputs: OPA decision logs can turn into a PII store.
- Treating local mocked PDP tests as TLS proof: run dedicated TLS/certificate integration tests.
- Treating ALLOW results as permanent tokens: decisions are context-bound, never freely replayable.
- Client-controlled PDP URLs: SSRF/exfiltration risk; use allowlists.
- Uncleaned async context: leaks tenant/role into subsequent tasks.

## 14. Self-check exercises

**Question 1:** A policy needs only `ownerMatches`. Should you send owner email and document body?

**Answer:** No, if the PEP computes the boolean from trusted sources; if the PDP does not trust the PEP, use an independent PIP rather than sending the whole entity.

**Question 2:** Alice is EDITOR in alpha and VIEWER in beta, and requests beta. Which role goes to the PDP?

**Answer:** The verified role for beta, never alpha's EDITOR.

**Question 3:** OPA returns 200 with body `{}`. Should READ be allowed?

**Answer:** No; result is undefined, fail closed.

**Question 4:** Does valid mTLS prove `ownerMatches` is accurate?

**Answer:** No; it authenticates the workload and secures the channel, not the semantic correctness of input data.

**Question 5:** Does a passing MockMvc local PDP test prove SSL client cert configuration is right?

**Answer:** No; dedicated handshake/hostname/mTLS/API-authorization integration tests are required.

**Question 6:** Can a PDP outage be ignored when attempting DELETE?

**Answer:** No. Deny or return 503 without executing the protected operation.

## 15. Summary

~~~text
Authenticated user
  + verified tenant membership and role
  + tenant-scoped resource metadata
  + trusted action/environment
     -> minimal typed PDP input
     -> HTTPS verified PDP + authenticated PEP workload
     -> PDP evaluates policy
     -> ONLY Boolean TRUE permits enforcement
     -> protected operation within current data/transaction scope
     -> minimal audit with decision/correlation ID
~~~

**Three tightly coupled requirements:** (1) **send only necessary attributes**; (2) **verify provenance and freshness**, never trusting client-declared fields; (3) **protect the channel and fail closed** via TLS/mTLS or service tokens, PDP authz, PEP enforcement, and transaction/data scoping. Missing any single piece can cause dynamic policies to grant wrong permissions or leak data.

## Official references

- [NIST SP 800-162 – ABAC Definition and Considerations](https://csrc.nist.gov/pubs/sp/800/162/upd2/final): ABAC/PEP/PDP/PIP.
- [OPA – Integration](https://www.openpolicyagent.org/docs/integration): named Data API decisions, sidecars.
- [OPA – REST API](https://www.openpolicyagent.org/docs/rest-api): input, result, undefined responses.
- [OPA – Security](https://www.openpolicyagent.org/docs/security): TLS, mTLS, API authentication/authorization.
- [OPA – Decision Logs](https://www.openpolicyagent.org/docs/management-decision-logs): input, decision_id, masking.
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): @EnableMethodSecurity/@PreAuthorize.
- [Spring Security – JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT validation.
- [Spring Boot 3.5 RestClientSsl API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/client/RestClientSsl.html): SSL bundles for RestClient.
- [Spring Boot – SSL Bundles](https://docs.spring.io/spring-boot/reference/features/ssl.html): TLS trust/key material.
