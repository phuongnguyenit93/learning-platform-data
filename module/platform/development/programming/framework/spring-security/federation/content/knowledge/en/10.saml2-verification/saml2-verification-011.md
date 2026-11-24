# Assertion Replay Prevention and Evaluating Shared Tracking Across Nodes

In SAML 2.0 federation, the **Service Provider (SP)** receives a `SAMLResponse` from the Identity Provider (IdP), verifies the assertions, and creates a login session. An assertion with a valid signature, right issuer/audience, and still within its validity window **still must not be accepted a second time**: an attacker can copy the message from an earlier device or request and replay it while still valid. That is a **replay attack**.

This lesson focuses on two closely coupled technical questions:

1. **Preventing SAML assertion replay:** the SP accurately identifies a used assertion, rejects subsequent uses, and picks a TTL no shorter than the validity window.
2. **Evaluating shared tracking across nodes:** when multiple Spring Security instances receive callbacks, how can only one instance be permitted to consume the same assertion, even under concurrent requests, cache disruptions, or failovers?

**Principle:** signature/issuer/audience/time checks and **replay protection** are conditions that **must be combined**. An anti-replay cache does not replace SAML validators; conversely, SAML validators do not prove an assertion has never been used on other servers.

## 1. Attack Model: Valid Signature Yet Reused

Suppose the IdP issues assertion `_assertion-7` for the reporting application, with bearer `SubjectConfirmationData@NotOnOrAfter=10:05Z`.

~~~text
                   IdP
                    |
            SAMLResponse + assertion _assertion-7
                    |
        +-----------v-----------+
        | User's browser        |
        +-----------+-----------+
                    | POST /login/saml2/sso/corporate
                    v
              SP Node A
        - valid signature
        - right audience/recipient
        - assertion still valid
        - _assertion-7 not seen -> accept
                    |
              login session

Attack / replay same assertion before 10:05Z:
        Identical HTTP POST SAMLResponse
                    |
                    v
              SP Node B
        - signature still valid
        - assertion still valid
        - if B has only a local cache: "not seen"
                    |
             SECOND LOGIN (bug!)
~~~

An attacker does not need to alter the signature. A signature protects **integrity and origin**, not whether **a message has been used previously**. A **replay marker** (used-flag) shared across all nodes capable of handling the same SSO flow must be stored.

In Web Browser SSO, a SAML bearer assertion usually travels through the browser to the SP; hence short time windows and `InResponseTo`, session, and recipient constraints matter. Still, relying solely on `InResponseTo` is insufficient when the app supports IdP-initiated SSO, uses a weak repository, or has multiple nodes not sharing state.

### 1.1. Four Types of State Not to Conflate

| State | Typical key/source | Question resolved |
| --- | --- | --- |
| **Pending AuthnRequest** | `AuthnRequest@ID` bound to browser session, `Saml2AuthenticationRequestRepository`. | Does the callback belong to a **login transaction initiated in this session**? |
| **Response replay** | `Response@ID` + trusted issuer/context. | Was this exact **Response** processed previously? |
| **Assertion replay** | `Assertion@ID` + trusted issuer/context. | Was this exact **assertion** already used to prove identity before? |
| **Application session** | SP's session cookie/`SecurityContext`. | Does the user already have an app session and is it still valid? |

Key point: **Response ID differs from Assertion ID**, and one assertion can be wrapped in multiple `Response` messages or arrive via another profile/binding. Therefore marking **only Response ID** does not suffice to replace marking **assertion ID**. The `AuthnRequest` cache is also not a used-assertion cache.

## 2. Specification Obligations and Protection Boundaries

OASIS **Profiles for the OASIS Security Assertion Markup Language (SAML) V2.0**, Section **Web Browser SSO HTTP-POST-specific processing rules (§4.1.4.5)**, requires SPs to prevent replay of **bearer assertions** by maintaining the set of **used IDs** while the assertion remains considered valid based on `SubjectConfirmationData@NotOnOrAfter`.

This highlights two non-negotiable properties:

- **Identifier:** based on the issued **assertion ID**, after verifying the assertion comes from a trusted issuer.
- **Retention period:** at least covering the **entire window in which that assertion could still be accepted** (including validator-configured clock skew).

For other bindings/profiles, apply corresponding rules, yet keeping a unified anti-replay gate for assertions permitted to create login sessions remains a useful defensive design.

### 2.1. Does `<OneTimeUse>` Replace a Cache?

SAML Core defines `<saml:OneTimeUse/>` as a condition indicating an assertion should only be used once. However:

- `OneTimeUse` is **not a database**; it cannot remember prior usage on node A by itself.
- An IdP may **omit `OneTimeUse`** from assertions. That does not remove the obligation to prevent bearer replay under the Web SSO HTTP-POST profile.
- If an assertion contains `OneTimeUse`, the SP must enforce it via an appropriate validator/tracking mechanism rather than ignoring it because other conditions passed.
- Library/version condition validators might not be wired to your desired **shared replay store**; verify in practice rather than assuming presence of `OneTimeUse` makes multi-node setups safe by default.

**Distinction:** an SP's **one-time consumption policy for bearer assertions** is an operational safeguard; `OneTimeUse` is a condition element inside the signed assertion. The two concepts are related yet not identical.

### 2.2. What Is Not Solved by a Replay Cache Alone?

An assertion **never before seen in the cache** can still be invalid due to a forged signature, unknown issuer, wrong recipient, audience for another SP, before `NotBefore`, past `NotOnOrAfter`, wrong `InResponseTo`, or invalid subject confirmation. Conversely, a response with a valid signature and content **must still be rejected** if the assertion ID was already consumed.

Thus, a replay cache is an **additional condition**; never an excuse to skip XML Signature, SAML Conditions, or browser session checks.

## 3. Identifying Which Assertion Was Used

A SAML assertion carries its own `ID`, for example:

~~~xml
<saml:Assertion
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_assertion-7"
    Version="2.0"
    IssueInstant="2026-11-07T03:00:00Z">
  <saml:Issuer>urn:example:idp:corporate</saml:Issuer>
  <saml:Conditions
      NotBefore="2026-11-07T03:00:00Z"
      NotOnOrAfter="2026-11-07T03:06:00Z">
    <saml:AudienceRestriction>
      <saml:Audience>urn:example:sp:reports</saml:Audience>
    </saml:AudienceRestriction>
  </saml:Conditions>
  <saml:Subject>
    <saml:SubjectConfirmation
        Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
      <saml:SubjectConfirmationData
          Recipient="https://sp.example.org/login/saml2/sso/corporate"
          InResponseTo="_request-123"
          NotOnOrAfter="2026-11-07T03:05:00Z"/>
    </saml:SubjectConfirmation>
  </saml:Subject>
</saml:Assertion>
~~~

This is **abbreviated XML illustrating ID and timestamp locations**, lacking signatures, status, and full authentication evidence, so it **must not be used as a real login assertion**.

### 3.1. What Should the Replay Key Contain?

A stable key can be built from:

~~~text
replay:v1:<spEntityId-or-application-namespace>:
          SHA-256(<trustedIssuer> || separator || <assertionId>)
~~~

Components:

- **`assertionId`**: taken from the assertion object **after proper origin/signature verification**, never synthesizing an ID from a new request.
- **`trustedIssuer`**: verified IdP identifier from `RelyingPartyRegistration`/validator. Ensures an attacker cannot arbitrarily pick namespaces.
- **SP/application namespace**: isolates distinct apps, environments, and trust boundaries. **Every node of the same SP** must use the **same key rule**, never embedding per-node hostname/pod ID.
- **Prefix/version**: allows upgrading key format, operational control, and separating marker types.

Hashing the key avoids storing raw IDs with strange characters or unexpected lengths directly in keys, and keeps key naming uniform. **SHA-256 here formats keys, not authentication proof.** Never use NameID/email as a replay key: the same user can legitimately log in multiple times with different assertion IDs; conversely, an attacker can replay an assertion without changing NameID.

Some architectures also record `Response@ID` in a separate namespace as defense in depth. **Assertion ID remains the primary key** for bearer assertion replay prevention. If a SAMLResponse contains multiple assertions used to build the same identity context, verify each assertion and ensure no already-used assertion is accepted; atomic all-or-nothing reservation across multiple markers is required rather than partial acceptance.

### 3.2. Identifiers Must Come from Verified Data

Prevent attackers from filling Redis with millions of self-declared IDs: before writing a marker, enforce request size limits, safe XML parsing, trusted registration selection, and verification of signature/issuer/recipient/audience/conditions and transaction policy. Only an **assertion that passed required verifications** is eligible for the mark-used step.

Pay attention to Response-signature vs Assertion-signature cases per binding/profile. When Response is signed yet the assertion is not independently signed in a supported profile, code must guarantee the consumed assertion **is the exact content protected by the Response signature**, preventing XML Signature Wrapping. Never pick `Assertion@ID` from an untrusted XPath while building the principal from a different assertion.

## 4. Safe Verification Pipeline with a Replay Gate

Processing diagram for a **SAMLResponse at the ACS** in a Spring Security application:

~~~text
Browser POST /login/saml2/sso/{registrationId}
        |
        v
Saml2WebSsoAuthenticationFilter
        |
Saml2AuthenticationTokenConverter
        |  resolve RelyingPartyRegistration, saved request
        v
AuthenticationManager / OpenSAML provider
        |
        +--> Parse / decrypt per profile
        +--> Valid signature and trust anchor
        +--> Issuer, status, destination/recipient
        +--> Audience, Conditions, bearer confirmation
        +--> InResponseTo / session, unsolicited SSO policy
        |
        v
Replay gate (same trust decision)
        |  key = namespace + issuer + assertion ID
        |  INSERT-IF-ABSENT (atomic, shared)
        |
        +-- Already exists --------> REJECT (do not create Authentication)
        +-- Store unavailable -----> FAIL CLOSED
        +-- Insert succeeded ------> continue
                                   |
                                   v
                         Saml2Authentication
                                   |
                             SecurityContext / SP session
~~~

The diagram expresses **security requirements**, not the exact order of every internal OpenSAML step. When customizing the provider, choose an extension point where **before issuing a successful `Authentication`** all trusted data is available for atomic marking. Never run an ad-hoc servlet filter pulling IDs from unverified XML and assume the cache is safe.

### 4.1. Where to Write the Marker and Handle Errors

- **Never just `GET key` then `SET key`**: two nodes could both read "unused" and both accept.
- **Never mark with non-atomic operations**: replay protection requires an **insert-if-absent** operation where only one node wins.
- **Do not delete the marker merely because login fails in a later step**: a processed assertion should not return to unused state. If business checks fail after the marker is written, require the user to start a fresh SSO flow.
- **If the store returns an error/timeout**, do not assume the assertion is fresh; the safe default is **temporary rejection**, letting the user initiate a new login.
- **If the marker already exists**, reject before issuing a new session, even if signature/audience/validity remain intact.
- **If authentication aborts before reaching the replay gate**, do not emit markers to "mark" unverified XML.

In large systems, define consumption timing relative to custom mapping/provisioning steps. A straightforward safe option is **verify SAML → atomically consume assertion → application processing**, never rolling back the marker solely because provisioning or session persistence errored.

## 5. Calculating TTL: How Long Must the Marker Be Kept?

An assertion's usable window is bounded by multiple timestamps:

1. `Conditions@NotBefore`: earliest accepted time.
2. `Conditions@NotOnOrAfter`: assertion expiration bound (exclusive right bound).
3. `SubjectConfirmationData@NotOnOrAfter`: bearer confirmation expiration, directly governing Web SSO.
4. Validator-permitted **clock skew** tolerance.
5. SP-specific limits on freshness and SSO execution duration; if stricter security bounds are needed, declare them by policy.
6. If multiple valid subject confirmations exist or profiles permit alternate confirmation paths, determine **the latest instant at which that exact assertion could still be accepted by any permitted verification path**.

**Safety rule:** the marker **must not expire before the final instant the SP could still accept that exact assertion**, after applying proper skew and all configured verification branches. Add a small safety margin to cover clock drift across nodes, cache cleanup schedules, and processing latency.

Example timestamps (UTC):

| Condition | Value |
| --- | --- |
| `IssueInstant` | `10:00:00Z` |
| `Conditions@NotOnOrAfter` | `10:06:00Z` |
| Bearer `SubjectConfirmationData@NotOnOrAfter` | `10:05:00Z` |
| Configured compatible skew | 30 seconds |
| SP accepts assertion via this exact bearer confirmation until | Before roughly `10:05:30Z`, barring tighter bounds |

If the assertion is accepted at `10:02:00Z`, **do not set replay TTL = 30 seconds**; the assertion can remain valid for several minutes. In this example, retain the marker at least past **`10:05:30Z`** plus an operational safety margin. The TTL at write time must be the remaining duration until that deadline, rather than always using `NotOnOrAfter - IssueInstant`.

Suppose the protection policy and verified time source compute `retentionUntil=10:05:45Z`; at `10:02:00Z`, TTL is **225 seconds**. Note this is a **numerical example for one case**; there is no single "min of two bounds" formula valid across all multi-confirmation assertions and profiles. TTL calculation must match the validator's **exact acceptance policy**; when a profile lacks safely determinable bounds, the SP should reject or enforce a mandatory freshness cap before accepting.

### 5.1. Why Is Too-Short a TTL Dangerous?

If the ID marker expires in Redis at `10:03Z` while the SP can still accept the assertion until `10:05Z`, a replay at `10:04Z` appears "never seen". Conversely, a slightly longer TTL only costs extra memory; too short a TTL **directly breaks the protection**.

Never use the **HTTP session cookie** lifetime or **SAML `SessionNotOnOrAfter`** as the assertion's replay TTL: those describe application/IdP session lifecycles, not the window in which a bearer assertion may be presented at the ACS.

### 5.2. An Upper Bound Is Needed

If an IdP sends assertions lacking profile-compliant time limits, or the SP sets excessive skew, the cache could have to hold IDs indefinitely. The right design is **enforcing a policy rejecting assertions lacking valid bounds or exceeding maximum lifetime**, not arbitrarily capping cache TTL and inadvertently permitting replay once markers vanish.

Ensure node clocks are synchronized. Use `Instant` rather than local time strings, computing deadlines from verified data; TTL must be positive and policy-bounded. Redis expiration ticks independently of application clocks, yet computing `PX` from timestamps still depends on node clocks: measure skew and use a unified time source.

## 6. Shared Store: Mandatory Properties

When the SP runs two or more replicas/pods/VMs:

~~~text
                Load Balancer
                      |
           +----------+----------+
           |                     |
        SP Node A             SP Node B
       Validator A           Validator B
           |                     |
           +----------+----------+
                      |
             SHARED REPLAY STORE
        atomic insert-if-absent + TTL
                      |
                 one outcome
            winner: accept marker
            loser: replay detected
~~~

**Minimum requirements** for a shared replay store:

| Property | Why mandatory |
| --- | --- |
| **Single keyspace** for same SP/issuer | Every node must query the same place; never shard cache by hostname/pod ID. |
| **Atomic check-and-set** | For two concurrent callbacks, only one is treated as first use. |
| **TTL matching acceptance window** | Never erase markers while the assertion remains usable. |
| **Strong enough read/write consistency** | Node B must see the marker Node A wrote before B decides to accept. |
| **Fail closed** | Store errors must not become "cache miss" or "first use". |
| **Adequate capacity and eviction policy** | Markers must not be evicted due to RAM pressure before TTL expires. |
| **Supports node churn/failover** | Scale-outs, rolling deploys, and pod restarts must not wipe replay history. |
| **Connection security and access control** | TLS, ACLs, secret rotation; disallow other actors from deleting markers. |
| **Observability/auditing** | Distinguish real replays, reload double-submits, clock skew, and cache outages. |

**Sticky sessions are insufficient**: they reduce correlation errors yet cannot guarantee an assertion always returns to the same node. During load balancer failovers, rolling deployments, or deliberate parallel requests, an assertion can still hit another node.

### 6.1. Comparing Options

| Option | Pros | Risks/limits | Recommendation |
| --- | --- | --- | --- |
| Per-node `ConcurrentHashMap`/Caffeine | Fast, simple, configurable TTL. | **Local only**, nodes A/B do not share markers. Restarts lose state. | Only for demos/single-node under limited assumptions; insufficient for clusters. |
| Sticky sessions | Helps keep `AuthnRequest` per node. | Does not block replays hitting another node and non-durable across node swaps. | Routing aid only, does not replace a replay store. |
| Shared Redis, `SET key value NX PX ttl` | Atomic per key, automatic TTL, low latency. | Replication/failover/eviction/durability require explicit design. | Practical when all HA and failure-policy requirements are met. |
| SQL with **unique constraint** and expiry column | Duplicate writes blocked by DB; transactional/durable and auditable. | Higher DB load; needs cleanup and index tuning. | Worth considering when strict consistency/durability is required. |
| Distributed map/cache with linearizable `putIfAbsent` | Can offer fitting APIs and TTL. | Must verify product semantics under partitions/failovers. | Acceptable only with genuine atomic guarantees, not eventual consistency. |
| Bloom filter | Low RAM per ID. | Has false positives and may lack exact removal/TTL; complex sync. | Should not act as sole login gate without an exact store. |

Redis is frequently cited for `SET ... NX EX/PX`, which **does not mean every Redis HA setup is automatically linearizable or durable across failovers**. If security policy cannot tolerate losing an acknowledged marker, evaluate corresponding durability/consensus/transactional mechanisms; if unmet, document residual risk and explicit fail-safe controls.

## 7. Redis: Right and Wrong Atomic Operations

### 7.1. Right Command

~~~redis
SET saml:replay:v1:reports:80b4a7f... used NX PX 240000
~~~

Model:

- `NX`: create key **only if it does not exist**.
- `PX 240000`: TTL **240,000 ms = 4 minutes**, illustrative only; real TTL must derive from the assertion's remaining acceptance window.
- Value `used` is just a marker; minimal timestamp/metadata may be stored if needed for audit, avoiding PII.
- If Redis returns **`OK`**, this node wrote the marker first and may let login proceed (pending remaining validation checks).
- If Redis returns **nil/null** because the key already exists, it is a replay/duplicate: **reject**.
- If connection times out/Redis errors, treat as **UNKNOWN**: **do not allow through**.

Note: the exact same key must always be derived for the same tuple issuer + assertion ID + SP namespace. Redis guarantees atomicity for **one command on one key**; never split into separate `GET` and `SET`.

### 7.2. Race Condition of the Wrong Approach

~~~text
Node A: GET key  -> nil
Node B: GET key  -> nil
Node A: SET key  -> OK
Node B: SET key  -> OK
Node A: ACCEPT
Node B: ACCEPT

Both issued sessions for the same assertion.
~~~

Even calling `SETNX` followed by `EXPIRE` in **two separate commands** is suboptimal: if the node crashes between commands, the marker may lack a TTL, bloating the store. `SET key value NX PX ttl` combines conditional creation and lifetime in a single operation.

### 7.3. Do Not Treat Replay Markers as Locks to "Unlock"

The `used` marker represents a **consumed** event, not a distributed lock guarding a temporary critical section. Therefore after successful login **do not `DEL key`**. After an error at session creation, normally **also do not DEL** to let the assertion be reused: that opens replay windows during uncertain failure states.

If a flow spans multiple steps needing `PENDING`/`CONSUMED` states, define explicit atomic state-transition, recovery, and timeout protocols. **Do not mechanically apply distributed-lock "unlock via DEL" recipes to replay markers**.

### 7.4. Redis Operational Conditions to Check

- **Eviction policy:** `allkeys-lru`, `allkeys-lfu`, or `volatile-ttl` can evict markers before TTL under memory pressure. That lets replays pass. Use policies/capacity ensuring markers are never evicted early; on OOM **raise errors and fail closed**, never silently continue.
- **Failover:** Redis replicas normally replicate asynchronously; a `SET NX` acknowledged `OK` by primary might not reach the replica before primary failure. Post-failover, the lost marker can let the same assertion pass again. `WAIT`/AOF reduce risk depending on config yet **do not automatically make every failover durable/linearizable**.
- **Replication reads:** never query "does key exist?" from a lagging replica to decide. Use conditional writes against the consistent key owner.
- **Partition:** when disconnected from the shared store, reject callbacks instead of spinning up a local cache to merge later.
- **ACL/TLS:** only the SAML service may read/write markers in its namespace; disallow other apps from deleting or resetting replay data.
- **Deployment:** preserve the same environment, SP, and namespace across rolling updates; never wipe markers simply because a new app version deployed.

## 8. Java 17: Simulating Two Nodes Sharing a Replay Store

The following snippet uses **pure Java 17** to simulate two nodes accessing a shared atomic marker store. It illustrates races and key naming, **without implementing real SAML, Redis, TTL eviction, or signature verification**. In production, replace `ConcurrentHashMap` with a real shared store and run full SAML validation before calling `markFirstUse`.

File **`ReplayGuardDemo.java`**:

~~~java
import java.time.Instant;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class ReplayGuardDemo {
    static class SharedStore {
        // Shared across simulated nodes within the same JVM.
        private final Set<String> used = ConcurrentHashMap.newKeySet();

        boolean markFirstUse(String trustedIssuer, String assertionId) {
            return used.add(trustedIssuer + "|" + assertionId);
        }
    }

    static class Node {
        private final SharedStore store;

        Node(SharedStore store) {
            this.store = store;
        }

        boolean accept(String issuer, String id,
                       Instant now, Instant validUntil) {
            // Illustrates a single time condition, not a SAML validator.
            if (!now.isBefore(validUntil)) {
                return false;
            }
            return store.markFirstUse(issuer, id);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        SharedStore shared = new SharedStore();
        Node nodeA = new Node(shared);
        Node nodeB = new Node(shared);

        Instant now = Instant.parse("2026-11-07T03:00:00Z");
        Instant expires = now.plusSeconds(300);

        System.out.println(nodeA.accept(
                "trusted-idp", "_assertion-1", now, expires));
        System.out.println(nodeB.accept(
                "trusted-idp", "_assertion-1", now, expires));
        System.out.println(nodeB.accept(
                "another-idp", "_assertion-1", now, expires));
        System.out.println(nodeA.accept(
                "trusted-idp", "_expired",
                now.plusSeconds(301), expires));

        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(2);
        AtomicInteger successes = new AtomicInteger();

        Runnable attempt = () -> {
            try {
                start.await();
                if (nodeA.accept(
                        "trusted-idp", "_racing", now, expires)) {
                    successes.incrementAndGet();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                done.countDown();
            }
        };

        new Thread(attempt).start();
        new Thread(() -> {
            try {
                start.await();
                if (nodeB.accept(
                        "trusted-idp", "_racing", now, expires)) {
                    successes.incrementAndGet();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                done.countDown();
            }
        }).start();

        start.countDown();
        done.await();
        System.out.println(successes.get());
    }
}
~~~

Compile and run:

~~~bash
javac ReplayGuardDemo.java
java ReplayGuardDemo
~~~

**Exact output:**

~~~text
true
false
true
false
1
~~~

Meaning:

1. Node A is first to mark `_assertion-1`, returning `true`.
2. Node B uses the same issuer + assertion ID and receives `false`.
3. Same assertion ID yet **a different verified issuer** creates a distinct namespace, so it can pass replay checks (other trust checks remain mandatory).
4. Expired assertion is rejected, never marked as a fresh login.
5. Two threads race on `_racing`; thanks to the atomic operation on the **same SharedStore**, exactly **one** thread wins; winning order is non-deterministic, yet `successes.get()` is always 1.

The demo intentionally omits marker cleanup and applies only to **one JVM**; never use `ConcurrentHashMap.newKeySet()` as a cluster replay cache or treat the demo's time check as full SAML validation. A real app must compute `validUntil` from library-verified conditions/subject confirmations.

## 9. Safe Spring Security SAML 2.0 Integration

In the Servlet stack, SAML callbacks pass through `Saml2WebSsoAuthenticationFilter`, the converter, and `AuthenticationManager` to the OpenSAML provider. Typical path:

~~~text
POST /login/saml2/sso/{registrationId}
    -> Saml2WebSsoAuthenticationFilter
    -> Saml2AuthenticationTokenConverter
    -> Saml2AuthenticationToken
    -> OpenSAML authentication provider
    -> Saml2Authentication (if successful)
~~~

Spring Security may use **`OpenSaml4AuthenticationProvider`** or **`OpenSaml5AuthenticationProvider`** depending on version. Newer documentation shows `OpenSaml5AuthenticationProvider.AssertionValidator` can add condition validators such as OpenSAML's **`OneTimeUseConditionValidator`**. Yet **you cannot assume every SAML login setup automatically includes a distributed used-assertion cache**. Inspect validator configuration, where the replay store is wired, and behavior under concurrent load.

### 9.1. Basic Configuration Does Not Replace a Replay Gate

Example `SecurityFilterChain` in a Spring Boot project with the SAML service provider dependency:

~~~java
package example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

This is a **Spring Boot configuration snippet**, not a class compilable/runnable with plain JDK. Besides `spring-security-saml2-service-provider`, it needs IdP metadata/trust credentials, SP entityID, and an accurate public ACS. Enabling SAML login **does not prove** a Redis-backed replay gate is configured; a dedicated deployment verification step is required.

### 9.2. Picking the Right Extension Point

Customization options in real systems:

| Need | Extension point | Mandatory requirement |
| --- | --- | --- |
| Enforce `OneTimeUse` or extended assertion conditions | OpenSAML provider's assertion validator / condition validator per version. | **Retain default validators** and append condition handlers; never disable audience, subject confirmation, or time checks. |
| Reject replay of all Web SSO bearer assertions | Replay-check component invoked **after SAML data verification** and **before recognizing Authentication**. | Key from trusted issuer + assertion ID, atomic operation against shared store. |
| Coordinate multiple nodes | Redis/SQL shared replay repository. | TTL, retry policy, fail-closed, consistency, capacity. |
| Retain original login request | `Saml2AuthenticationRequestRepository`, typically backed by `HttpSession`. | Correlates `InResponseTo` and browser session; do not treat as a shared replay cache. |
| Map attributes and permissions | Response authentication converter or business service after verification. | Never grant permissions from an assertion that bypassed the replay gate and validators. |

**Do not write markers in an arbitrary filter before signature verification**: an attacker can spam arbitrary IDs, exhausting storage or "preempting" legitimate IDs. **Do not place replay logic inside a success handler and assume safety** if Authentication/session was already published or concurrent callbacks bypass the validator; ensure the gate is an atomic precondition for issuing a session.

### 9.3. Redis Integration Pseudocode

This is **architectural pseudocode**, not copy-pasteable Spring Security/OpenSAML API code:

~~~text
verifySaml(response, trustedRegistration, pendingRequest)
    -> verifiedAssertions, verifiedIssuer, acceptanceWindows

for every bearer assertion used for login:
    derive key from SP namespace, verifiedIssuer, verifiedAssertionId
    derive retentionUntil from last possible acceptance time + safety margin
    require redis SET key "used" NX PX remainingMillis == OK

if all security checks and all needed replay reservations succeeded:
    create Saml2Authentication
else:
    throw AuthenticationException
~~~

If **multiple assertions in the same Response** must be marked, an independent `SET NX` loop can leave partial state if one marker already exists. For security, never grant a session in that partial state; operationally, use an atomic all-or-nothing reservation protocol (e.g. transaction/compare-and-set on supporting stores) or only accept SAML structures where every consumed assertion can be guarded consistently. With Redis Cluster, atomic multi-key Lua/transactions require keys in the same hash slot; never assume multiple distributed keys share single-`SET NX` atomicity.

## 10. HA Analysis: Replay Can Still Happen Even with a Shared Store

Many teams deploy Redis thinking "it's shared" while overlooking these risks:

### 10.1. Two Nodes Write Concurrently

If both target the same Redis primary/key with **`SET NX PX`**, one node wins. If each node checks a local cache and writes Redis asynchronously, both can issue sessions before noticing the duplicate. **Allow/deny decisions must rely on the atomic marker write outcome**, not a background-dispatched event.

### 10.2. Redis Primary Fails Immediately After Confirming Write

Suppose primary returns `OK` for assertion A and then crashes **before the replica receives the marker**. The promoted replica lacks A; a replayed callback hits the new primary, and `NX` returns `OK` again. Technically this is **loss of a consumed marker**, not non-concurrent requests.

Assess security/durability requirements and options: replication behavior, AOF, replica acknowledgments, failover strategy, or moving to a datastore with stronger transactional/consistency guarantees. **Never claim Redis is "exactly-once across every failover" by default.** If absolute guarantees cannot be met, document residual risk, keep short TTL/timeout bounds, and pause SSO when store consistency is degraded.

### 10.3. Connection Errors, Timeouts, and Uncertain Outcomes

A `SET NX` might have executed on Redis while the response back to the node was lost. The node then **does not know** whether the marker was created. Safe behavior: **do not issue a session on an uncertain result**; report a retryable error **via a new login transaction**. If retrying the same assertion—even though it might already be recorded—reject per single-use policy; never "allow through because the previous attempt timed out".

### 10.4. Cache Eviction and Deployments

A marker with a 5-minute TTL is not guaranteed to survive 5 minutes if eviction policies allow early deletion or a deployment wipes the key namespace. Verify memory policies, availability, restarts, persistence, and rollouts. Clearing the entire cache mid-shift opens a replay window for unexpired assertions.

### 10.5. Multiple Geographic Regions

If SPs in Region A and Region B use two independent Redis clusters synced **eventually consistently**, an assertion can be accepted in both during replication lag. System-wide single-use requires **one atomic decision point per key** or an equivalently strongly consistent architecture. If global latency SLAs prevent that, document the boundary and design safe routing instead of calling it "global replay prevention".

## 11. Verification Matrix and Test Scenarios

| Test case | Expected outcome |
| --- | --- |
| Valid bearer assertion, first receipt. | Accepted after full verification and successful marker write. |
| Re-send same assertion to same node while still valid. | Rejected because marker already exists. |
| Re-send same assertion to a different node immediately afterward. | Rejected **via shared store**. |
| Concurrent POST of same assertion to two nodes. | **Only one** callback passes the replay gate; never issue two sessions. |
| Same `Response@ID` yet altered assertion/invalid signature. | Rejected by validator; response ID does not replace XML verification. |
| Identical assertion ID yet different verified issuer. | No collision against the other issuer's key; trust checks must still pass. |
| Replay after marker TTL ends when assertion's validity window has also ended. | Time validator rejects; no login created. |
| Marker removed **before** assertion usability window ends. | Security bug to detect/alert; unacceptable design. |
| Redis returns error or timeout. | **Fail closed**, never fall back to local cache. |
| Redis `NX` returns nil because key exists. | Treat as replay/duplicate; never retry and overwrite marker. |
| Restart both Spring Security nodes. | Marker persists in shared store; old assertion is rejected. |
| Redis failover before replica syncs marker. | Test marker loss risk / enforce durability requirements; do not claim safety if lost. |
| One node has clock drift within configured tolerance. | TTL still covers maximum acceptance window, never expiring early. |
| Response carries multiple assertions used for login. | Each assertion has its own ID/validation; no partial pass if any marker duplicates. |
| `OneTimeUse` present while default validator omits it. | Enforce appropriate validator; never skip unrecognized conditions. |
| IdP-initiated SSO without `InResponseTo`. | Enforce separate unsolicited policy; replay gate remains mandatory. |
| Valid assertion yet user is disabled in the application. | Deny app access; consumed marker is not deleted for reuse. |

**Concurrency tests** require a real load balancer, two independent instances, two parallel HTTP requests carrying the same validly signed SAMLResponse, and the same shared store. Do not unit-test a local `ConcurrentHashMap` and claim cluster safety is proven.

## 12. Observability and Operations

Logs/metrics are needed to separate **real attacks**, **users pressing F5**, **browser POST retries**, **session errors**, and **store incidents**:

| Metric / trace | Meaning |
| --- | --- |
| `saml_replay_first_use_total` | Count of markers created successfully. |
| `saml_replay_duplicate_total` | Count of rejections due to existing key. |
| `saml_replay_store_error_total` | Connection, timeout, capacity, or failover errors. |
| `saml_replay_gate_latency` | Latency of allow/deny decision. |
| `saml_replay_ttl_below_policy_total` | Computed TTL too short or unable to determine safely. |
| `saml_clock_skew_rejection_total` | Assertions rejected due to timing/clock. |
| `saml_in_response_to_rejection_total` | Mismatched AuthnRequest/session correlation. |

Metric names are **design suggestions**, not default Spring Security metrics. If duplicates spike suddenly, inspect whether requests come from one user (double submit) or multiple IPs/sessions; never label an attack from a single counter alone.

Record **verified issuer registration, short hashed ID for correlation, UTC timestamp, node, rejection reason, and store response time**. Never log raw `SAMLResponse`, assertion XML, NameID, cookies, secret keys, or personal data. Use per-node/region dashboards and alert when Redis memory climbs, evictions > 0, or failovers drop markers.

Rough capacity planning: active markers depend on **SSO rate × average retention duration** plus key/value and replication overhead. Load-test at peak login rates, verify audit output, and have a store-full plan: **temporarily deny new SSO**, never flip to an allow-all fallback.

## 13. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Verify only signature/audience/expiry. | Validly signed assertion can be replayed within validity window. | Add assertion-ID-based replay gate. |
| Cache only `Response@ID`. | Assertion can be repackaged inside another Response. | Cache `Assertion@ID`, optionally adding response ID separately. |
| Use NameID/email as key. | Blocks legitimate subsequent logins or collides across users. | Use verified issuer + assertion ID + SP namespace. |
| Use only per-node `HttpSession`. | Replays hitting another node can succeed. | Shared store across all instances. |
| Redis `GET` then `SET`. | Race condition; two nodes both allow through. | Atomic `SET key value NX PX ttl`. |
| Separate `SETNX` and `EXPIRE` commands. | Can leave markers without TTL on crash between steps. | Combine creation condition and TTL. |
| Pick a short fixed TTL. | Marker expires while assertion is still acceptable. | Derive TTL from acceptance window and clock skew. |
| Delete marker on logout or SP session expiry. | Allows old assertion reuse before expiry. | Marker lives independently per assertion lifetime. |
| Delete marker when success handler/provisioning fails. | Consumed assertion becomes reusable. | Retain marker and require a fresh login. |
| Fail-open when Redis disconnects. | Replay protection vanishes right when system degrades. | Fail closed with a friendly error. |
| Assume Redis with replication is automatically exactly-once. | Failover can lose primary-acknowledged markers. | Assess durability/consistency and residual risk. |
| Parse XML yourself for `Assertion@ID` before signature check. | Allows fake ID spam, DoS, checking the wrong assertion. | Only take ID from validator-accepted assertions. |
| Believe `OneTimeUse` persists markers by itself. | Condition may be read without the needed state store. | Wire validator to a proper replay store. |
| Replace Spring default validators with a cache-only validator. | Drops issuer, audience, recipient, expiry, and signature checks. | Extend/retain default validation and add the gate. |

## 14. Self-Check Comprehension

1. **Why is a valid signature insufficient to stop replay?** — Because the identical signature can be re-submitted intact before the assertion expires.
2. **Does a SAML bearer assertion have an ID or only the SAML Response?** — Each assertion has **its own ID**, and the used ID must be tracked.
3. **Which state must be shared across nodes?** — Assertion replay markers; AuthnRequest/session also need suitable correlation sharing.
4. **Can per-pod `ConcurrentHashMap` replace Redis?** — No, when multiple pods handle SSO.
5. **Why is `GET` then `SET` unsafe?** — Two nodes can both observe a missing key and both grant login.
6. **What does `SET ... NX PX` returning null mean?** — The key already exists; must not be accepted again.
7. **Is it okay to allow logins when the cache errors to boost availability?** — No, if replay protection is a mandatory security control; **fail closed**.
8. **Can TTL be shorter than `SubjectConfirmationData@NotOnOrAfter`?** — No, if the SP could still accept the assertion after the marker disappears; factor in skew and all acceptance branches.
9. **If Redis primary failover loses recent writes, do two nodes still guarantee exactly-once?** — No; evaluate or strengthen durability/consistency.
10. **If login fails after the marker was written, should you `DEL` so the user can retry the same Response?** — No; use a new SSO transaction.
11. **Does having `OneTimeUse` in XML make a cluster safe?** — No; an actual validator and shared used-ID state are required.
12. **An assertion has expired and its marker was already purged: will a replay pass?** — No, if the time validator works properly; that is why the replay gate and time validation must always operate together.

## 15. References

- [OASIS SAML V2.0 Profiles — §4.1.4.5, HTTP-POST replay prevention](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf)
- [OASIS SAML V2.0 Core — Assertion ID, Conditions, OneTimeUse](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf)
- [OASIS SAML V2.0 Errata 05 — bearer SubjectConfirmationData, InResponseTo](https://docs.oasis-open.org/security/saml/v2.0/errata05/os/saml-v2.0-errata05-os.html)
- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html)
- [Spring Security — Authenticating SAML Responses, OpenSaml5 AssertionValidator, and OneTimeUseConditionValidator](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html)
- [Spring Security — AuthnRequest and Saml2AuthenticationRequestRepository](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html)
- [Redis SET — NX, EX, PX options and return values](https://redis.io/docs/latest/commands/set/)
- [Redis Persistence and replication mechanisms (HA operations reference)](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/)
