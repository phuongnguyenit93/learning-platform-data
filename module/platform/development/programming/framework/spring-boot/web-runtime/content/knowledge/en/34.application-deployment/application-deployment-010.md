# Keeping Session Data Compatible Across Coexisting Application Versions

## 1. The Real-World Problem: One Cookie, Two Application Versions

During a **rolling deployment**, **canary release**, or **blue–green deployment**, not every request from a user lands on the same software version. The following sequence can happen:

```text
User's browser
  Cookie: SESSION=abc123
         │
         ├── request 1 ──► App V1 (old pod) ──┐
         │                                    │
         ├── request 2 ──► App V2 (new pod) ──┤── Shared Redis / JDBC
         │                                    │    session store
         └── request 3 ──► App V1 (old pod) ──┘
```

If V1 stores a Java `CartSession` object in the session while V2 changed its package, fields, or data types, V2 may **fail to decode** V1's session. Conversely, when V2 writes a brand-new structure, a subsequent request routed back to V1 can break. Users experience unexpected logouts, empty carts, HTTP 500s, deserialization failures, or cart contents flipping back and forth between requests.

Moving from Tomcat in-memory sessions to **Spring Session Redis/JDBC** lets multiple pods read the same data; **it does not guarantee serialization, schema, or business-semantic compatibility**. Likewise, sticky sessions only lower the odds of switching pods; they do not protect against pod termination, autoscaling, health checks, or rollbacks.

This lesson belongs to **Application Deployment** in the **Spring Boot - web-runtime** module. Goals:
- Distinguish **session ID/cookie**, **session store**, and **session attributes**.
- Understand risks when JDK `Serializable`/JSON/DTOs/Spring Security contexts change between V1 and V2.
- Build a **read/write compatibility matrix** during coexistence and rollbacks.
- Implement **`schemaVersion`**, a dual-reader, a writer gate, and an expand–migrate–contract rollout.
- Experiment with **Java 17+, Spring Boot 3.3.13**, a standalone runnable MVC project, unit/integration tests, and a Redis-backed setup when multiple instances share sessions.
- Choose solutions that avoid silent data loss or unplanned forced logouts.

**Version scope:** API examples target Spring Boot **3.3.13**, Spring Framework 6.1, and Spring Session 3.3. This is an illustrative baseline; production should run a supported, security-patched version. Current **Spring Session 4.x** docs may use different starters/packages; do not copy 4.x config blindly into Boot 3.3 without cross-checking.

## 2. A Session Has Many Layers—Which Ones Must Stay Compatible?

```text
Browser                          Application V1 / V2
 ┌──────────────────────┐           ┌───────────────────────┐
 │ Cookie               │           │ HTTP session wrapper  │
 │ SESSION=opaque-id    ├──────────►│ HttpSession/WebSession│
 │ HttpOnly/Secure/...  │           │                       │
 └──────────────────────┘           └───────────┬───────────┘
                                              │ lookup ID
                                              ▼
                                     ┌──────────────────────┐
                                     │ Shared session store │
                                     │ Redis / JDBC         │
                                     │ session metadata     │
                                     │ + attribute bytes    │
                                     └───────────┬──────────┘
                                                 │ decode
                                   ┌─────────────┴─────────────┐
                                   ▼                           ▼
                             V1 Java classes             V2 Java classes
                             V1 JSON contract            V2 JSON contract
```

| Layer | Contents | Common failures |
|---|---|---|
| **Cookie/session ID** | Opaque browser identifier | Changing cookie name/path/domain; session ID not sent to new pod |
| **Session repository** | Redis/JDBC/in-memory and namespace | V1/V2 writing to different namespaces, or pods pointing to different Redis instances |
| **Serialization format** | Java JDK bytes, JSON, custom serializer | V1 writes JDK bytes, V2 expects JSON; missing class/package |
| **Attribute schema** | Keys like `cart.snapshot`, version, fields, types | V2 renames `skuIds` to `items`, V1 does not understand |
| **Business meaning** | What values represent | Changing currency units, locale, enums, permissions, coupon rules |
| **Security context** | Principal/roles, authentication object | V2 fails to deserialize V1 `SecurityContext` |
| **Lifecycle** | Timeout, cookie expiration, invalidation | Session lost due to TTL/namespace changes or unsynchronized ID rotation |

**Cookies carry only the ID** in standard server-side session setups, not the entire shopping cart. Still, if a system intentionally uses **stateless payload-bearing cookies/tokens** or a different Spring Session setup, verify the actual model. Never assume having a `SESSION` cookie means all session data is encrypted or signed; server-side session IDs still require protection against theft.

### 2.1. In-Memory Sessions vs Shared Sessions

With default Tomcat and no shared session repository, each pod holds local session state. A `JSESSIONID` cookie from pod A does not mean pod B has the data. Sticky load balancing can make a demo look fine, yet if pod A dies, data is still lost.

With **Spring Session**, Servlet `HttpSession` is replaced by a repository-backed abstraction (Redis/JDBC/etc.), typically via `springSessionRepositoryFilter`. Multiple instances truly share sessions only when they align on:
- Connecting to the same repository.
- Using the same namespace/table.
- Using the same cookie name/path/domain for browsers in scope.
- Sharing the serializer/attribute contract and security settings.
- Aligning timeout/clock/configuration behavior to avoid surprises.

**Sharing storage does not mean sharing Java code.** Two pods can read the exact same Redis key while one fails to decode the other's attribute bytes.

## 3. Deployment Patterns Prone to “Mixed-Version” Session Data

| Deployment pattern | Both versions serving? | Session risk |
|---|---|---|
| Rolling update across pods | Yes, while swapping replicas | Requests bounce V1↔V2 via load balancer |
| 5% V2 canary | Yes | A user can hit V2 then return to V1 |
| Blue–green traffic switch | Possible around cutover | V2 writes session then traffic rolls back to V1 |
| A/B experiment | Yes, over long periods | Sessions carry different feature payloads |
| Hotfix rollback | New V2 rolled back to V1 | Old reader cannot parse V2-written sessions |
| Autoscaling mixed images | Yes, if rollout/config drifts | Different session serializers or feature flags |
| Multi-region active–active | Yes, plus replication lag | Stale/lost updates, ordering, and TTL skew |
| Sticky sessions | Fewer pod switches | Does not solve pod crashes, rollbacks, or scaling |

Even a **1% canary** can break **100% of subsequent requests for sessions it wrote in a new format**, once those sessions route back to V1 and V1 cannot parse them. Never treat a small canary percentage as proof that a session schema change is safe.

### 3.1. A Real Failure Timeline

```text
12:00  V1 writes Java CartState(skus=[A, B])
12:01  V2 receives 5% traffic, reads or writes CartStateV2
12:02  Redis sessionAttr:cart is overwritten with new bytes
12:03  Browser routes back to V1
12:03  V1 deserializes:
       java.io.InvalidClassException
       or ClassNotFoundException
       or unsupported JSON schema
12:04  Users report disappearing carts / HTTP 500
12:05  Team rolls back completely to V1
12:06  V1 still cannot read sessions already rewritten by V2
```

**Rolling back the image does not roll back session bytes.** This is the core technical reason every session format change must be treated as a **data migration**, not just a code deployment.

## 4. JDK Serialization Risks: Serializable Is Not an Immutable Contract

Spring Session Redis/JDBC 3.3 uses **Java serialization** for session attributes by default unless you explicitly configure a different serializer/converter. Java `Serializable` persists an object graph tied to class names, `serialVersionUID`, field descriptors, and Java serialization compatibility rules.

V1 example:

```java
package com.example.v1;

import java.io.Serializable;
import java.util.List;

public class CartState implements Serializable {
    private static final long serialVersionUID = 1L;
    private List<String> skuIds;
}
```

V2 might change it to:

```java
package com.example.v2;

import java.io.Serializable;
import java.util.List;

public class CartState implements Serializable {
    private static final long serialVersionUID = 1L;
    private List<CartItem> items;
}
```

These are **two illustrative class fragments**, not files from the runnable project below. Even though both set `serialVersionUID=1L`, changing the **fully qualified class name** from `com.example.v1.CartState` to `com.example.v2.CartState` causes builds without the old class to throw `ClassNotFoundException`. Changing field types or object graphs can yield null/default fields, type mismatches, or corrupted semantics. Keeping the same UID **does not guarantee semantic compatibility**.

Common symptoms:
- `java.io.InvalidClassException`: incompatible stream/class descriptor, `serialVersionUID` mismatch.
- `ClassNotFoundException`: newer or older version lacks the class on its classpath.
- `NotSerializableException`: object graph contains a non-`Serializable` field.
- `ClassCastException`: deserializes yet code casts to a different class/type.
- Null/default values: some field edits do not throw yet silently produce invalid state.
- Java deserialization attack surface: deserializing untrusted data is dangerous; protect Redis/JDBC, dependency versions, and serialization filters per your threat model.

**Fixing `serialVersionUID=1L` does not solve everything.** JPA entities, Hibernate proxies, lazy collections, authentication principals, or complex DTO graphs remain fragile across V1/V2 deploys.

### 4.1. Never Put Mutable Entities or Proxies in the Session

Discouraged:

```java
session.setAttribute("currentCustomer", customerJpaEntity);
session.setAttribute("cart", mutableCartWithHibernateCollection);
```

These objects can:
- Hold lazy proxies that fail serialization.
- Carry stale state relative to the database.
- Retain huge object graphs bloating Redis/BLOB storage.
- Depend on ORM/module/package versions across releases.
- Be mutated in place where Spring Session fails to detect dirty state.

Instead store only an **ID or a small, versioned snapshot**:

```text
sessionAttr:cart.snapshot =
  {"schemaVersion":1,"skuIds":["SKU-1","SKU-2"]}
```

The source of truth for payments, orders, inventory, and authorization remains the database/service with proper validation. A session cart is temporary UI state, not a transaction ledger.

## 5. JSON Does Not Automatically Solve All Versioning Issues

JSON removes direct dependence on Java class names in the **application payload** when designed as a stable schema. Yet it still requires:
- Contracted field names and types.
- Versions and conversion rules.
- Sensible defaults for new fields.
- Explicit readers for old data.
- Policies for unknown future versions.
- Distinguishing backward compatibility, forward compatibility, and rollbacks.
- Avoiding permissive polymorphic type metadata that introduces deserialization gadget risks.

**Important:** switching **the entire Spring Session serializer** from JDK to JSON via a new `RedisSerializer` bean **does not mean existing JDK sessions automatically become readable under the new serializer**. You need a dual-format serializer, a migration tool, a legacy decoder, or an intentional forced re-login. In our demo project, we keep the default Spring Session serializer while storing a **JSON-encoded `String`** in attribute `cart.snapshot`; Java `String` serializes stably across Java 17 apps, leaving JSON schema evolution under application control.

Two distinct version levels exist:
1. **Container serializer**: Redis/JDBC bytes → `String` attribute (JDK serialization or configured serializer).
2. **Application schema**: `String` → JSON `schemaVersion=1/2` → domain object.

If layer (1) switches formats incompatibly, layer (2)'s reader **never even gets invoked**. Test both separately.

## 6. Designing a Versioned Envelope to Prevent Silent Data Loss

Define a stable session key `cart.snapshot`. Two example formats:

**Schema V1** — stores a list of SKUs:

```json
{
  "schemaVersion": 1,
  "skuIds": ["SKU-1", "SKU-2"]
}
```

**Schema V2** — renames the list and adds a coupon:

```json
{
  "schemaVersion": 2,
  "items": ["SKU-1", "SKU-2"],
  "coupon": "WELCOME"
}
```

Read rules:
- A **V1+V2 compatible reader** reads both `skuIds` and `items`.
- For V1, `coupon` defaults to an empty string.
- For V2, validate types/counts/schema; `coupon` is a new field carrying business meaning.
- Unknown `schemaVersion` must be handled safely: **fail closed** or show a controlled maintenance error; never silently reset to an empty cart.
- Never silently drop unknown fields in a **downgrading writer** if those fields must be preserved.

Write rules:
- **Writer V1** writes only `schemaVersion=1` + `skuIds` and **forbids** using the coupon feature, since V1 cannot represent coupons.
- **Writer V2** writes `schemaVersion=2` + `items` + `coupon`.
- Enable Writer V2 only when **no V1-only reader** still receives traffic and the rollback target supports V2.
- If a Writer V1 pod coexists with a Writer V2 pod, Writer V1 could **read V2 then rewrite V1 and drop the coupon**. That is a **lost field on downgrade** bug; rollouts require writer fencing or a consistent write policy.

**Do not treat “V2 can read V1” as safe to write V2 everywhere.** In mixed deployments, the invariant is that **every active writer must produce a format every active reader can read**, not just new reading old.

## 7. Read–Write Compatibility Matrix and Rollbacks

Assume three binaries/behaviors:
- **A**: reader understands V1 only, writer V1.
- **B**: reader understands V1+V2, writer V1 (reader expansion phase).
- **C**: reader understands V1+V2, writer V2.

| Data in store | A: R1/W1 | B: R1+2/W1 | C: R1+2/W2 |
|---|---|---|---|
| JSON V1 | Readable, writes V1 | Readable, writes V1 | Readable; on mutate writes V2 |
| JSON V2 | **Error** | Readable, yet mutating may downgrade/lose new fields | Reads/writes V2 |
| Unknown V3 | **Error** | **Error per policy** | **Error per policy** |

**Safe phase-by-phase conclusions:**

| Phase | Coexisting pods | Permitted write format | Rollback target |
|---|---|---|---|
| 0. Pre-upgrade | A | V1 | A |
| 1. Expand readers | A + B | **V1** | A (safe for cart format) |
| 2. All readers upgraded | B | **V1** | B, or A if no V2 data exists |
| 3. Switch writers | B/C if **fenced** so W1 cannot drop fields | V2 | **B-compatible reader preserving/migrating V2**, not A |
| 4. Post-rollout | C | V2 | B/C under controlled writer policy |
| 5. Contract old schema | C, after rollback/session retention ends | V2 | Only binaries with V2 reader |

**Phase 3 subtlety:** if B still handles requests and runs V1 write code, it can downgrade a V2 session. Safe cutover needs a **consistent writer gate**, a brief write pause, backend CAS/enforcement, or writer B preserving V2 fields when encountered. A feature flag propagating unevenly across pods creates mixed writers; **never assume flag toggles are atomic across all pods**.

### 7.1. Keeping Rollbacks Compatible

Once binary C has written V2 data, rolling all traffic back to binary A will fail because A cannot read V2. Options:
1. **Keep rollback binary B+**, able to read both V1/V2, never reverting to A.
2. **Tested dual-write/format compatibility** avoiding last-write-wins, only if business semantics allow.
3. **Hold off enabling Writer V2** until past the window where rolling back to A might be required.
4. **Migrate data backward** with schema/rollback tooling, accounting for V2-only fields (`coupon`) if backward conversion loses information.
5. **Intentionally force users to start fresh sessions** only when state loss/re-auth is accepted; never silently flush Redis.

A rollback strategy must cover **code, schemas, already-written data, feature flags, cookies, security contexts, and backend session stores**. A single `kubectl rollout undo` does not undo persisted bytes.

## 8. Runnable Project: Spring Boot MVC with JSON Schema V1/V2 in HttpSession

We build a project **requiring no Redis for unit/API tests**. The goal is to prove the JSON contract and Writer V1/V2 modes first. For multi-pod setups, section 12 adds Redis Session to a **build/deploy variant**; `MockMvc` tests must not be mistaken for real Redis proof.

The project includes:
- `GET /api/cart`: reads the session cart.
- `POST /api/cart/items?sku=SKU-1`: adds an SKU and writes back the session attribute.
- `POST /api/cart/coupon?code=WELCOME`: allowed only when Writer V2 is enabled.
- `POST /api/session/logout`: invalidates the session (for lab demonstration; does not replace authentication logout).
- `CartCodec`: dual-reader V1/V2 with writer chosen via `demo.cart.write-version`.
- `@RestControllerAdvice`: rejects unknown session formats instead of silently clearing the cart.
- JUnit codec contract tests + `MockMvc` session continuity tests.

### 8.1. Directory Structure

```text
session-compat-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/sessioncompat/
    │   │   └── SessionCompatibilityApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/sessioncompat/
            └── SessionCompatibilityTest.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'session-compat-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/resources/application.properties`:**

```properties
server.port=8080
spring.application.name=session-compat-demo

# Expand phase: V1/V2-capable instances still write V1.
demo.cart.write-version=1

# In-memory Tomcat session in the base build.
server.servlet.session.timeout=30m
server.servlet.session.cookie.http-only=true
```

**There is no Redis in the base build**, so each app instance holds sessions locally; do not use the base build to claim a session from port 8081 is readable on port 8082. Section 12 covers testing the shared store.

### 8.2. Java Application: Immutable Record, Versioned Codec, and Controller

**`src/main/java/com/example/sessioncompat/SessionCompatibilityApplication.java`:**

```java
package com.example.sessioncompat;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

import jakarta.servlet.http.HttpSession;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class SessionCompatibilityApplication {

    public static void main(String[] args) {
        SpringApplication.run(SessionCompatibilityApplication.class, args);
    }
}

// Small snapshot; do not store JPA entities or object graphs with proxies.
record CartSnapshot(List<String> items, String coupon) {
    CartSnapshot {
        items = List.copyOf(items);
        coupon = coupon == null ? "" : coupon;
    }

    static CartSnapshot empty() {
        return new CartSnapshot(List.of(), "");
    }
}

record CartView(List<String> items, String coupon) {
    static CartView from(CartSnapshot state) {
        return new CartView(state.items(), state.coupon());
    }
}

class IncompatibleSessionException extends RuntimeException {
    IncompatibleSessionException(String message) {
        super(message);
    }

    IncompatibleSessionException(String message, Throwable cause) {
        super(message, cause);
    }
}

@Component
class CartCodec {

    private static final int MAX_ITEMS = 50;
    private final ObjectMapper mapper;

    CartCodec(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    String encode(CartSnapshot state, int version) {
        if (version != 1 && version != 2) {
            throw new IllegalArgumentException(
                    "Supported writer versions are 1 and 2");
        }

        ObjectNode root = mapper.createObjectNode();
        root.put("schemaVersion", version);

        ArrayNode array = mapper.createArrayNode();
        state.items().forEach(array::add);

        if (version == 1) {
            if (!state.coupon().isEmpty()) {
                throw new IllegalArgumentException(
                        "V1 cannot represent coupon");
            }
            root.set("skuIds", array);
        } else {
            root.set("items", array);
            root.put("coupon", state.coupon());
        }

        try {
            return mapper.writeValueAsString(root);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException(
                    "Cannot encode cart snapshot", e);
        }
    }

    CartSnapshot decode(String encoded) {
        if (encoded == null || encoded.length() > 16_384) {
            throw new IncompatibleSessionException(
                    "Session cart payload is absent or too large");
        }

        final JsonNode root;
        try {
            root = mapper.readTree(encoded);
        } catch (JsonProcessingException e) {
            throw new IncompatibleSessionException(
                    "Invalid JSON in session cart", e);
        }

        if (root == null || !root.isObject()) {
            throw new IncompatibleSessionException(
                    "Session cart must be a JSON object");
        }

        JsonNode versionNode = root.get("schemaVersion");
        if (versionNode == null || !versionNode.isInt()) {
            throw new IncompatibleSessionException(
                    "Missing or invalid session schemaVersion");
        }

        int version = versionNode.intValue();
        if (version == 1) {
            return new CartSnapshot(readItems(root.get("skuIds")), "");
        }

        if (version == 2) {
            String coupon = "";
            JsonNode couponNode = root.get("coupon");
            if (couponNode != null && !couponNode.isNull()) {
                if (!couponNode.isTextual()
                        || couponNode.asText().length() > 20) {
                    throw new IncompatibleSessionException(
                            "Invalid session cart coupon");
                }
                coupon = couponNode.asText();
            }

            return new CartSnapshot(
                    readItems(root.get("items")), coupon);
        }

        // Do not infer data from an unknown version.
        throw new IncompatibleSessionException(
                "Unsupported session schemaVersion");
    }

    private List<String> readItems(JsonNode array) {
        if (array == null || !array.isArray()
                || array.size() > MAX_ITEMS) {
            throw new IncompatibleSessionException(
                    "Invalid session cart items");
        }

        List<String> items = new ArrayList<>();
        for (JsonNode element : array) {
            if (!element.isTextual()
                    || !element.asText().matches(
                            "[A-Z0-9_-]{1,32}")) {
                throw new IncompatibleSessionException(
                        "Invalid session cart SKU");
            }
            items.add(element.asText());
        }
        return List.copyOf(items);
    }
}

@RestController
@RequestMapping("/api/cart")
class CartController {

    private static final String CART_KEY = "cart.snapshot";

    private final CartCodec codec;
    private final int writerVersion;

    CartController(CartCodec codec,
            @Value("${demo.cart.write-version:1}")
            int writerVersion) {
        if (writerVersion != 1 && writerVersion != 2) {
            throw new IllegalArgumentException(
                    "demo.cart.write-version must be 1 or 2");
        }
        this.codec = codec;
        this.writerVersion = writerVersion;
    }

    @GetMapping
    CartView get(HttpSession session) {
        return CartView.from(read(session));
    }

    @PostMapping("/items")
    CartView addItem(
            @RequestParam String sku, HttpSession session) {

        if (!sku.matches("[A-Z0-9_-]{1,32}")) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid SKU");
        }

        CartSnapshot before = read(session);
        List<String> items = new ArrayList<>(before.items());
        if (!items.contains(sku)) {
            items.add(sku);
        }
        if (items.size() > 50) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Too many items");
        }

        CartSnapshot after =
                new CartSnapshot(items, before.coupon());

        // Explicit setAttribute so Spring Session can
        // detect the modified attribute per save-mode.
        session.setAttribute(
                CART_KEY, codec.encode(after, writerVersion));

        return CartView.from(after);
    }

    @PostMapping("/coupon")
    CartView applyCoupon(
            @RequestParam String code, HttpSession session) {

        if (writerVersion != 2) {
            // Block new feature before writer switchover.
            throw new ResponseStatusException(
                    HttpStatus.CONFLICT,
                    "Coupon feature is not active");
        }
        if (!code.matches("[A-Z0-9]{1,20}")) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid coupon");
        }

        CartSnapshot before = read(session);
        CartSnapshot after =
                new CartSnapshot(before.items(), code);

        session.setAttribute(
                CART_KEY, codec.encode(after, writerVersion));

        return CartView.from(after);
    }

    private CartSnapshot read(HttpSession session) {
        Object stored = session.getAttribute(CART_KEY);

        if (stored == null) {
            return CartSnapshot.empty();
        }
        if (!(stored instanceof String json)) {
            throw new IncompatibleSessionException(
                    "Session cart attribute is not a String");
        }

        return codec.decode(json);
    }
}

@RestController
@RequestMapping("/api/session")
class SessionLifecycleController {

    @PostMapping("/logout")
    ResponseEntity<Void> logout(HttpSession session) {
        session.invalidate();
        return ResponseEntity.noContent().build();
    }
}

@RestControllerAdvice
class SessionErrorAdvice {

    @ExceptionHandler(IncompatibleSessionException.class)
    ResponseEntity<ProblemDetail> incompatible(
            IncompatibleSessionException error) {

        // Do not delete data and do not expose raw session contents.
        // Production requires correlation ID/metrics and an incident policy.
        ProblemDetail problem = ProblemDetail.forStatus(
                HttpStatus.SERVICE_UNAVAILABLE);
        problem.setTitle("Session temporarily unavailable");
        problem.setDetail(
                "Session data cannot be read by this application version");

        return ResponseEntity
                .status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(problem);
    }
}
```

**Detailed explanation:**

- The file has a single top-level `public class` matching `SessionCompatibilityApplication.java`. The records, controllers, codec, and advice are package-private, valid in Java 17 and discovered by Spring component scan.
- `CartSnapshot` copies the `List` via `List.copyOf` so mutable session objects cannot be altered without Spring Session detecting a change.
- `CartCodec.decode` supports both V1 and V2 and **never assumes an unknown version is V1**. Invalid JSON/schema throws a dedicated exception; operationally you should emit metrics and return a safe response.
- `CartCodec.encode` forbids writing V1 if a coupon is already present. This prevents **silent data loss** at the codec layer, though it does not prevent last-write-wins races between concurrent requests.
- `writerVersion` is configured at startup. **Never run two writer versions concurrently when V2-only fields exist**; toggling the flag requires a release barrier and draining/controlling old writers and in-flight writes.
- `session.setAttribute` is called after every mutation, which matters for Spring Session `save-mode=on-set-attribute`. Mutating a list inside an existing attribute without calling `setAttribute` may not persist under that save mode.
- `@RestControllerAdvice` returns 503 when the app cannot understand the session without auto-invalidating the session or logging JSON/session IDs. This is an illustrative policy; production may use an appropriate error page/support flow.
- `/api/session/logout` is only for studying session invalidation and **does not replace Spring Security logout handlers or CSRF/session-fixation protections**. Real POST endpoints require authentication/authorization and client-appropriate CSRF protection.
- The demo lacks atomic compare-and-set/revision counters for concurrent updates; critical cart/financial state belongs outside `HttpSession` in a durable store with transactions or optimistic locking.

### 8.3. Run a Single Instance of the Demo

Requires JDK 17+ and a Spring Boot 3.3-compatible Gradle installation:

```bash
gradle bootRun
```

If the project includes a Gradle Wrapper, run `./gradlew bootRun` on Linux/macOS or `.\gradlew.bat bootRun` on Windows PowerShell. It runs on port **8080** by default; the base project uses local Tomcat sessions.

Use `curl` with a cookie jar to **preserve the same session ID** across requests:

```bash
# Create / refresh cookie jar for local example:
curl -i -c cookies.txt -b cookies.txt \
  -X POST \
  "http://localhost:8080/api/cart/items?sku=SKU-1"

curl -i -c cookies.txt -b cookies.txt \
  "http://localhost:8080/api/cart"

curl -i -c cookies.txt -b cookies.txt \
  -X POST \
  "http://localhost:8080/api/cart/coupon?code=WELCOME"
```

The first two requests return bodies like:

```json
{"items":["SKU-1"],"coupon":""}
```

The final request receives HTTP **409 Conflict** because `demo.cart.write-version=1`. That is **not** a Redis or serialization failure: it is an intentional **feature gate** preventing V2-only schema writes prematurely.

Override config at launch:

```bash
gradle bootRun --args='--demo.cart.write-version=2'
```

Now the controller allows coupons, though a new process's local Tomcat session cannot read in-memory sessions from the stopped process. To demonstrate **true cross-instance** sharing, switch to Redis as in section 12 using the same cookie jar across both ports.

## 9. Standalone Tests: JSON V1, V2, Unknown Versions, and HttpSession

**`src/test/java/com/example/sessioncompat/SessionCompatibilityTest.java`:**

```java
package com.example.sessioncompat;

import java.util.List;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import jakarta.servlet.http.HttpSession;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest(properties = "demo.cart.write-version=1")
@AutoConfigureMockMvc
class SessionCompatibilityTest {

    @Autowired
    CartCodec codec;

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @Test
    void v1PayloadCanBeReadByExpandedReader() {
        CartSnapshot cart =
                new CartSnapshot(List.of("SKU-1"), "");

        String encoded = codec.encode(cart, 1);
        CartSnapshot decoded = codec.decode(encoded);

        assertThat(decoded).isEqualTo(cart);
        assertThat(encoded).contains("\"schemaVersion\":1");
        assertThat(encoded).contains("\"skuIds\"");
    }

    @Test
    void v2PayloadCanBeReadByExpandedReader() {
        CartSnapshot cart =
                new CartSnapshot(List.of("SKU-2"), "WELCOME");

        String encoded = codec.encode(cart, 2);
        CartSnapshot decoded = codec.decode(encoded);

        assertThat(decoded).isEqualTo(cart);
        assertThat(encoded).contains("\"schemaVersion\":2");
        assertThat(encoded).contains("\"items\"");
        assertThat(encoded).contains("\"coupon\"");
    }

    @Test
    void unknownVersionIsRejectedWithoutDeletingData() {
        assertThatThrownBy(() -> codec.decode(
                "{\"schemaVersion\":3,\"items\":[]}"))
                .isInstanceOf(IncompatibleSessionException.class);
    }

    @Test
    void writerV1CannotSilentlyDropCoupon() {
        CartSnapshot cart =
                new CartSnapshot(List.of("SKU-1"), "WELCOME");

        assertThatThrownBy(() -> codec.encode(cart, 1))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("V1 cannot represent coupon");
    }

    @Test
    void oldReaderWouldFailOnV2Schema() throws Exception {
        String v2 = codec.encode(
                new CartSnapshot(List.of("SKU-1"), "WELCOME"), 2);

        JsonNode node = mapper.readTree(v2);

        // Simulate an old reader supporting only schemaVersion=1.
        assertThat(node.get("schemaVersion").asInt()).isEqualTo(2);
        assertThat(node.has("skuIds")).isFalse();
        assertThatThrownBy(() -> legacyReadV1Only(v2))
                .isInstanceOf(IllegalArgumentException.class);
    }

    private String legacyReadV1Only(String json) throws Exception {
        JsonNode root = mapper.readTree(json);
        if (root.path("schemaVersion").asInt(-1) != 1) {
            throw new IllegalArgumentException(
                    "Old reader only knows V1");
        }
        return root.path("skuIds").toString();
    }

    @Test
    void mockHttpSessionReusesCartAcrossRequests()
            throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(post("/api/cart/items")
                        .param("sku", "SKU-1")
                        .session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items[0]").value("SKU-1"));

        mvc.perform(get("/api/cart").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items[0]").value("SKU-1"))
                .andExpect(jsonPath("$.coupon").value(""));

        Object saved = session.getAttribute("cart.snapshot");
        assertThat(saved).isInstanceOf(String.class);
        assertThat((String) saved).contains(
                "\"schemaVersion\":1");
    }

    @Test
    void couponIsNotEnabledBeforeWriterSwitch()
            throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(post("/api/cart/coupon")
                        .param("code", "WELCOME")
                        .session(session))
                .andExpect(status().isConflict());

        assertThat(session.getAttribute(
                "cart.snapshot")).isNull();
    }
}
```

Run:

```bash
gradle test
```

**Expected outcome:** seven tests pass on Java 17/Boot 3.3.13 with the specified dependencies. This is an **expectation from code analysis, not an observed Gradle run**.

**Scope of these tests:**
- `v1PayloadCanBeReadByExpandedReader`: proves **the new reader reads old payloads**.
- `v2PayloadCanBeReadByExpandedReader`: proves the V1+V2 reader reads new payloads.
- `unknownVersionIsRejectedWithoutDeletingData`: does not default to an empty cart.
- `writerV1CannotSilentlyDropCoupon`: prevents dropping V2-only fields on downgrade.
- `oldReaderWouldFailOnV2Schema`: explicitly models a V1-only reader via a small helper without pretending an old binary ran.
- `mockHttpSessionReusesCartAcrossRequests`: proves the session key stores a string and calls `setAttribute` per the Servlet API.
- `couponIsNotEnabledBeforeWriterSwitch`: feature is rejected during Phase 1.

**Does not prove** Redis migration, cross-process serialization, Spring Security auth context, or sticky LBs, because `MockHttpSession` runs inside one test JVM. Those scenarios require the tests in sections 13/16.

## 10. Why Those Tests Are Only a Starting Point: Real Cross-Version Contracts

In a real system, at least **two code/artifact versions** exist. If V1 was built on a classpath lacking new DTOs, tests inside V2's JVM (which has the new classes) cannot catch a `ClassNotFoundException` on V1. Therefore keep:
- Golden session payload bytes/JSON fixtures **generated by the actual V1 binary**.
- Tests verifying V2 reads V1's bytes—not just V2 encoding and V2 decoding.
- Golden V2 payloads tested against rollback binary B.
- Integration tests with real Redis/JDBC rather than mocking the serialization layer.
- Cross-instance cookie requests across two base URLs.
- Rolling-upgrade tests where one pod runs the old writer and one runs the new writer.
- Security login continuity and logout/invalidation tests from both sides.
- Read/write race and TTL expiration tests.

**Golden fixtures can contain sensitive data** if captured from production. Use synthetic test sessions; never commit production cookies/tokens, session IDs, customer data, or principal objects into repositories.

### 10.1. Automated Integration Matrix to Run

| Producer | Consumer | Data | Expectation |
|---|---|---|---|
| A V1 writer | A V1 reader | V1 | PASS |
| A V1 writer | B dual-reader | V1 | PASS |
| B V1 writer | A V1 reader | V1 | PASS |
| C V2 writer | B dual-reader | V2 | PASS read; prevent B writing V1 and dropping coupon |
| C V2 writer | A V1-only reader | V2 | **Expected incompatible**; never allow this traffic |
| C V2 writer | C V2 reader | V2 | PASS |
| B reader + C reader | Concurrent mutate same cart | V1/V2 | No silent lost updates or dropped fields |
| Unknown future schema V3 | B/C | V3 | Fail closed, do not delete session |
| Expired session | B/C | No data | Start fresh session per policy |
| Wrong cookie name/domain | B/C | No ID | Enforce consistent cookie contract |
| Redis unavailable | B/C | Existing ID | Explicit error/fail policy, never forge login |
| SecurityContext V1 bytes | Security V2 | Authentication | Readable, or planned migration/re-auth |
| Rollback after V2 write | B/C rollback | V2 | Readable, preserves new fields |
| Rollback to A | A old | V2 | **Do not deploy** without backward migration |

Do not assert only HTTP 200; verify **data remains intact** across a V1→V2→V1 sequence and no updates vanish under concurrent writers.

## 11. Does Every New Field Require Changing schemaVersion?

Not every new field needs a new schema version, yet **changing meaning or representability** requires an explicit contract.

| Change type | Risk | Recommendation |
|---|---|---|
| Adding optional JSON field with sensible default | Low if old reader ignores unknown fields and writer preserves them | Compatibility tests; can share schema if contract permits |
| Renaming `skuIds` → `items` | High if old reader expects old key | Dual reader/dual write or new `schemaVersion` |
| Changing `priceCents` to `priceDollars` | High even though JSON remains a number | Version bump, migration + unit conversion |
| Renaming enum `PENDING` → `QUEUED` | High for old switches/mappers | Expand enums or stable wire-value mapping |
| Changing timezone semantics | High without parser errors | UTC/ISO-8601 contract and migration |
| Changing UUID string to an object | High | V2 schema and dual-form decoder |
| Adding coupon/discount unrepresentable in V1 | High on rollback | Feature gate + writer barrier |
| Moving package of a `Serializable` Java class | High for JDK bytes | Keep legacy class/serializer or migrate |
| Switching Redis serializer JDK→JSON | Very high | Planned dual decoder/namespace migration |
| Switching cookie `SESSION` ↔ `JSESSIONID` | High for auth/session lookup | Cookie transition strategy |
| Rotating signing/encryption key for signed cookies/tokens | High | Overlapping key rotation and dual-key verification |

**Do not assume “Jackson ignores unknown properties”** if a deserializer enables `FAIL_ON_UNKNOWN_PROPERTIES` or custom type binders. The demo uses `JsonNode` and selects fields explicitly for tight control; if using Jackson DTOs, configure carefully and test against both V1 and V2 fixtures.

### 11.1. What If You Store Only an ID in the Session?

For more stateless APIs, you can store `userId`/`cartId` and fetch live state from DB/cache per request, avoiding large DTO graphs in the session. Changing application-layer Java DTOs then barely impacts session serialization. However:
- Never trust a client-supplied `userId`; authenticate it.
- Never treat a session ID as authorization for DB objects without permission checks.
- DB/cache schemas still need multi-version compatibility.
- Extra DB reads add latency/cost to measure.
- TTL, concurrency, and invalidation still require management.

For carts and critical transactional workflows, storing `cartId` and managing cart state in a store with optimistic locking/idempotency is usually more reliable than keeping a fully mutable cart inside `HttpSession`.

## 12. Real Deployment Variant: Shared Spring Session Redis Across Pods

**Version warning:** in Spring Boot **3.3**, use BOM-managed modules such as:

```groovy
// Add the following lines to dependencies in Boot 3.3 build.gradle:
implementation 'org.springframework.boot:spring-boot-starter-data-redis'
implementation 'org.springframework.session:spring-session-data-redis'
```

Do not use `org.springframework.boot:spring-boot-starter-session-data-redis` from **Boot 4.x** docs assuming the same GAV exists in Boot 3.3. Spring Boot 3.3 auto-configures Spring Session Redis once Spring Session and Redis connection dependencies are present. Use only one session store implementation unless intentionally multi-storing.

Shared configuration across **all instances**:

**`src/main/resources/application.properties`** or environment overrides:

```properties
spring.data.redis.host=127.0.0.1
spring.data.redis.port=6379

# Use the same namespace across all releases of the same app.
spring.session.redis.namespace=demo:sessioncompat

# Timeout for session repository; do not confuse with cookie max-age.
spring.session.timeout=30m

# Write changes only on save; sync attribute on setAttribute.
spring.session.redis.flush-mode=on-save
spring.session.redis.save-mode=on-set-attribute

# Still use writer V1 in the expand phase.
demo.cart.write-version=1
```

These properties exist in Spring Boot 3.3, yet **putting them into an app without Redis dependencies does not enable Redis-backed sessions**. If you add the dependencies and forget to start Redis, endpoints touching the session will fail due to unavailable Redis connections.

Spring Session Redis:
- Stores session metadata + attributes in Redis keys under the namespace with expiration/TTL.
- Uses JDK serialization for attribute values by default in Spring Session 3.3.
- Replaces the container `HttpSession` via `springSessionRepositoryFilter` in the Servlet stack.
- Defaults the cookie name to `SESSION` when Spring Session's cookie resolver is active—**not necessarily Tomcat's `JSESSIONID`**.
- Manages session timeout; note that browser cookie `Max-Age`, Redis TTL, and auth token expiry need not be identical.
- Supports configuring flush/save mode, indexed repositories, and expiration events as needed, without enabling all events/features automatically.
- End-of-request flush/write timing can make updates appear slightly later to concurrent requests; verify with cross-node concurrency tests.

### 12.1. Running Two Processes Against the Same Redis (Lab)

Requires local Redis (never point at a production store):

```bash
docker run --rm --name sessioncompat-redis \
  -p 127.0.0.1:6379:6379 redis:7
```

Build the project **after adding both Redis dependencies**:

```bash
gradle clean bootJar
```

With the configured `settings.gradle`, the expected JAR is:

```text
build/libs/session-compat-demo-1.0.0.jar
```

Terminal 1 — instance B (reader V1+V2, writer V1):

```bash
java -jar build/libs/session-compat-demo-1.0.0.jar \
  --server.port=8081 \
  --demo.cart.write-version=1
```

Terminal 2 — instance C (reader V1+V2, writer V2):

```bash
java -jar build/libs/session-compat-demo-1.0.0.jar \
  --server.port=8082 \
  --demo.cart.write-version=2
```

These are **two processes of the same source code with two write policies**, not two distinct compiled Java binaries; they illustrate the schema/persistence side of rollouts, **not a substitute for golden cross-version tests**.

During the **expand phase**, keep **both 8081 and 8082 writing V1**. Switch to `writer=2` only when:
1. No V1-only readers remain in the fleet.
2. No old W1 writers remain that could drop V2-only fields, or write fencing is in place.
3. Rollback artifacts can read V2.
4. The new business feature is gated and tests pass.

### 12.2. Testing Cookies Across Two Base URLs

Once in the right phase:

```bash
# Start with instance 8081:
curl -i -c cookies.txt -b cookies.txt \
  -X POST \
  "http://localhost:8081/api/cart/items?sku=SKU-1"

# Keep cookie and read from instance 8082:
curl -i -c cookies.txt -b cookies.txt \
  "http://localhost:8082/api/cart"

# At 8082 with writer2, add coupon:
curl -i -c cookies.txt -b cookies.txt \
  -X POST \
  "http://localhost:8082/api/cart/coupon?code=WELCOME"

# Read again at 8081 only when its reader understands V2:
curl -i -c cookies.txt -b cookies.txt \
  "http://localhost:8081/api/cart"
```

Cookies do not distinguish TCP ports under the HTTP cookie model (domain/path/scheme matter), so `localhost:8081` and `localhost:8082` share one cookie jar when attributes align. **Use the same host `localhost`**—do not mix `localhost` and `127.0.0.1` in cookie tests.

After `writer2` writes V2, `reader1+2` on 8081 can read it. However, if 8081 (`writer1`) **mutates** the cart while a coupon is present, the demo's `codec.encode(..., 1)` throws intentionally rather than silently dropping the coupon. That is a codec safety guardrail, not a desirable user experience. Production must **stop routing writes to W1 or synchronize the writer policy**.

**Do not conclude “two ports work = all production browser sessions are safe”.** Still test cookie `Domain`/`SameSite`/`Secure`, TLS/WSS, sticky LBs, Redis availability, auth contexts, login/logout, concurrency, and rollbacks.

## 13. Redis Namespace, Cookies, and TTL: Same Store Can Still “Lose Sessions”

Releases must share consistent configuration:

| Property | V1 | V2 | If mismatched |
|---|---|---|---|
| Redis endpoint/cluster/DB | Same environment | Same environment | Session ID lookup finds no data |
| `spring.session.redis.namespace` | `shop:session` | `shop:session` | Separate keyspaces, looks like logout |
| Cookie name | `SESSION` | `SESSION` | Browser sends wrong/different cookie |
| Cookie path/domain | `/` / standard domain | Compatible | Cookie not sent to new app |
| Cookie Secure/SameSite | Current TLS & policy | Compatible | Browser rejects or omits cookie |
| Session timeout | 30m | 30m | Pods have mismatched expiry expectations |
| JDK/JSON serializer | Same contract | Same contract | Cannot read attribute bytes |
| Security context serialization | Compatible classes & modules | Compatible | Authentication disappears or errors |
| Clock/TTL behavior | Time synced | Time synced | Sessions expire unexpectedly |
| Field-schema reader | V1 | V1+V2 | Must verify before enabling V2 writer |

**A Redis namespace is not schema migration.** Changing the namespace from `shop:session:v1` to `shop:session:v2` without bridging/migrating simply makes old sessions invisible. If isolating new data in a new namespace, design dual-store session lookups carefully (avoiding security bypasses), logout/rehydration plans, and stopping writes to the old namespace.

**TTL is usually a sliding inactivity timeout** (`maxInactiveInterval`), depending on the repository and how sessions are accessed. Do not assume `spring.session.timeout=30m` means every session expires 30 minutes after login; active users keep extending it. Waiting for “V1 sessions to expire” may require a separate absolute max-age deadline, offline migration, or lazy read-repair.

**Never run `redis-cli FLUSHALL`** to “fix” migration issues. It wipes sessions across all systems sharing Redis and triggers mass logouts. Any targeted cleanup requires clear key/namespace ownership, backups/snapshots, and an approved rollout plan.

### 13.1. Inspecting Session Keys Safely

Example inspecting metadata in local Redis:

```bash
redis-cli --scan --pattern 'demo:sessioncompat:sessions:*'
```

Never dump raw session values into logs or tickets because they hold authentication state, user preferences, and potentially sensitive data. When inspecting structures in test environments, use synthetic cookies/session IDs and an isolated Redis instance.

Redis TTLs, session cleanup, and expiration events may carry implementation-specific delays. Never use “session expired” events as an exact-timing distributed lock or financial trigger.

## 14. Redis/JDBC Session Serializer: Do Not Swap Formats in a Single Rollout

If V1 uses **JDK-serialized attribute bytes** and V2 swaps the Spring Session serializer to JSON:
- Existing JDK data does not magically turn into JSON.
- Switching serializers can break V2 immediately when loading `SPRING_SECURITY_CONTEXT`/`cart` even if the app's cart JSON schema is intact.
- If V2 writes JSON bytes, V1's JDK serializer cannot read them → rollback breaks.
- Switching Redis namespaces to “avoid mismatches” makes existing sessions disappear.
- A dual-format serializer must safely detect formats, parse against an allowlist, encode with versions, and pass read/write/rollback tests.

In Spring Session Redis 3.3 you can override the serializer via a bean named **`springSessionDefaultRedisSerializer`**. The snippet below **only illustrates the API extension point** and **must not be turned on directly when existing JDK sessions exist**:

```java
// Fragment inside @Configuration, not a standalone class:
@Bean("springSessionDefaultRedisSerializer")
RedisSerializer<Object> sessionSerializer() {
    return new GenericJackson2JsonRedisSerializer();
}
```

This requires importing `org.springframework.data.redis.serializer.RedisSerializer`, `GenericJackson2JsonRedisSerializer`, and `org.springframework.context.annotation.Bean`. **Do not copy and deploy straight into an environment with existing JDK sessions**: it can drop/break active user sessions and carries polymorphic deserialization risks. With Spring Security, configure the required Jackson modules/mix-ins and lock down allowed polymorphic types and versions.

For **Spring Session JDBC**, attributes are typically stored in `SPRING_SESSION_ATTRIBUTES` as serialized bytes (`ATTRIBUTE_BYTES`); changing converters or DB column encodings is likewise a migration requiring testing. Do not assume switching Redis→JDBC preserves sessions automatically; store migrations require dedicated dual-read, data sync, or controlled re-login design.

**Recommendation:** if your goal is only evolving a business attribute, keep the session repository serializer intact and version **the attribute's value** itself. Only replace the global session serializer with strong justification, a dual decoder, and a broad migration plan since it impacts authentication state too.

## 15. Migrating from Legacy Java Session Objects to JSON Strings

Suppose a legacy `"cart"` attribute holds `LegacyCart implements Serializable`, and the new version wants `"cart.snapshot"` as a JSON `String`. Migration **cannot only read the new key**, because existing sessions do not have it yet.

A controlled strategy:

**Phase A – Compatibility bridge:**
- Keep `LegacyCart` with compatible package/`serialVersionUID` to decode legacy bytes.
- On read, inspect both old and new keys according to a defined precedence rule.
- Convert the legacy object into the small DTO and encode JSON schema V1.
- While old pods remain, do not delete the legacy attribute if old readers still depend on it.
- Avoid writing two unsynchronized independent keys: they will drift when pods update only one.

**Phase B – Cut over source of truth:**
- Roll out the bridge reader to all instances first.
- Fence/retire old writers so legacy keys are no longer rewritten after migration.
- Define which key is the source of truth, track a version/revision marker, and handle concurrent writes.
- If performing read-repair on read, write back only after ensuring you won't overwrite newer data (consider optimistic locking/CAS).
- Emit metrics for legacy sessions read/migrated and errors.

**Phase C – Retire legacy:**
- Wait through the rollback window and session TTL/absolute retention period.
- Only then drop the legacy DTO/decoder.
- Clean up unused legacy Redis/JDBC attributes selectively without wiping active sessions or authentication.

**Conceptual snippet (not a runnable class):**

```java
Object rawNew = session.getAttribute("cart.snapshot");
Object rawLegacy = session.getAttribute("cart");

if (rawNew instanceof String json) {
    return codec.decode(json);
}
if (rawLegacy instanceof LegacyCart old) {
    CartSnapshot state = migrateLegacyCart(old);

    // Only write if source-of-truth/concurrent writer rules
    // are resolved. Do not perform blind read-repair.
    session.setAttribute(
            "cart.snapshot", codec.encode(state, 1));
    return state;
}
return CartSnapshot.empty();
```

`LegacyCart` and `migrateLegacyCart` must retain the exact V1 implementation, classpath, and type contract. If legacy bytes **cannot deserialize** because the old class was deleted, the code above **never reaches `instanceof`**: keep a legacy module or run an offline migration with a compatible classpath/serializer.

## 16. Spring Security: Session Data Is Not Just the Cart

Apps using Spring Security login often persist authentication state in a session attribute named **`SPRING_SECURITY_CONTEXT`**. Its object graph typically includes:
- `SecurityContext`/`Authentication` implementations.
- Principal/user-details types.
- Granted authorities/roles and custom claims.
- Objects from security libraries or SSO integrations.
- Serialization metadata from JDK/JSON serializers.

When upgrading Spring Boot/Spring Security or modifying a custom principal, two pods can become **incompatible on serialized authentication state** even if `cart.snapshot` decodes fine. V2 failing to decode V1's `SecurityContext` triggers logouts/401s/500s. V1 receiving V2's authentication state can fail similarly.

Protection checklist:
1. Test login on V1 → authenticated request on V2 → back to V1.
2. Test remember-me, logout/invalidation, and session ID rotation if used.
3. Keep custom principals small/stable; avoid JPA entities or lazy proxies.
4. If switching Java serializer→JSON, include Spring Security Jackson modules/mix-ins and never enable unrestricted Jackson default typing on untrusted data.
5. Verify authority/role semantics on both V1/V2, not just error-free deserialization.
6. Never fabricate an authenticated principal when a session attribute fails to decode; **fail securely**.
7. Never log session IDs, serialized `SecurityContext`, or tokens in logs/metrics.
8. Plan **controlled re-authentication** when an unavoidable format change breaks backward compatibility.

**Session fixation:** after successful login, Spring Security rotates session IDs for protection. V1/V2 and proxies must handle cookie/ID rotation consistently. Do not mistake valid session ID rotation at login for a store migration failure.

**CSRF/SameSite:** when a frontend uses cookie-based sessions, `POST`/`PUT`/`DELETE` requests still need proper CSRF defenses (Spring Security defaults or client-appropriate token strategies). `SameSite` helps mitigate certain attacks, not replace authorization or complete CSRF protection.

## 17. Concurrent Writes: Compatible Schemas Can Still Lose Data

When two concurrent requests hit the same session:
1. Request A reads cart `[SKU-1]`.
2. Request B reads the same cart `[SKU-1]`.
3. A adds `SKU-2` and saves.
4. B adds `SKU-3` onto its stale snapshot and saves.
5. The store keeps B's final write → **`SKU-2` is lost**.

```text
Time ──────────────────────────────────────────►

Request A: read [1] ── add [2] ── save [1,2]
Request B:   read [1] ── add [3] ──────── save [1,3]
Session:   [1]         → [1,2]          → [1,3]
                                               ▲ lost update
```

This is a **concurrency/last-write-wins** bug, independent of `schemaVersion`. `session.setAttribute(...)` marks an attribute dirty for saving; **it is not a whole-session compare-and-swap**. `synchronized(session)` inside one JVM does not synchronize across multiple pods.

If cart state matters:
- Store state in a DB/Redis key with a **revision** using optimistic locking or atomic scripts/transactions.
- Use idempotency keys for browser/retry mutations.
- Design merge semantics for independent edits instead of overwriting from stale snapshots.
- For pricing discounts/coupons, always re-validate against current rules at checkout.
- Separate user session ID from business cart/order state.
- Measure conflicts and auto-retry **only when transformations are idempotent/mergeable**.

Coexisting V1↔V2 versions compound this because an old writer can overwrite and drop a new field. If the rollout cannot guarantee a writer barrier, keep the session cart **read-only during schema transition** or route mutations through a shared version-aware backend.

## 18. Planning Rollouts with Expand–Migrate–Contract

### 18.1. Before Deployment

- Inventory all stored session attribute keys, types, serializers, sizes, TTLs, and owners/services.
- Identify attributes affecting login, checkout, payment, or roles—not just cart UI.
- Capture fixtures from the currently running version and test reading them with the new build.
- Define `schemaVersion`, fallback defaults, and rules for unknown versions and invalid JSON.
- Check whether old writers ignore/drop unknown fields.
- Determine maximum/active session lifetimes, not just inactivity TTL.
- Document canary/rollback policies and who owns session format changes.
- Enable metrics for session decode failures and migrations before changing writers.

### 18.2. Phase 1: Deploy Dual-Reader While Keeping Old Writer

Build **B**:
- Reads V1 and V2.
- Writes **V1 only**.
- Keeps V2-only features (coupon) disabled.
- Keeps the same cookie/store/namespace/timeout.
- Canaries are safe because sessions they write remain V1, which A understands.

Test:
- A writes → B reads.
- B writes → A reads.
- B reading corrupt/unknown data → fails safely.
- Login A → B → A.

### 18.3. Phase 2: Retire V1-Only Readers

- Roll out B to **100%** and confirm A receives zero traffic—including queues, old ingress routes, idle keep-alive connections, and background workers.
- Monitor session decode successes/errors, auth failures, and session store latency.
- Ensure the **rollback target** is no longer an old A binary unable to read V2.
- Across multiple regions/tenants, verify all are reader-compatible.

### 18.4. Phase 3: Switch Writers Behind a Barrier

- Ensure all binaries already include the dual-reader.
- Switch writers to V2 **as a coordinated change**, preventing leftover W1 instances from downgrading V2 after users apply coupons.
- Consider edge/service feature gating, or briefly pausing mutations during the switch if necessary.
- Backends can enforce compare-and-set/version guards rejecting session downgrades.
- Enable coupons only after Writer V2 is stable and the rollback baseline reads/writes V2.
- Alert if `schemaVersion=2` is ever overwritten back to `1`.

### 18.5. Phase 4: Contract After Expiry and Rollback Windows Close

- Wait for V1 sessions to migrate or expire per policy.
- **Do not assume after 30 minutes that zero V1 sessions remain** when timeouts are sliding inactivity-based and users stay active.
- Only when V1-read metrics drop to zero for a meaningful window and rollback is closed should you remove the V1 reader.
- Do not remove legacy decoders early if raw JDK sessions from before migration still exist.
- Clean up legacy attributes/keys narrowly with backups; never run `FLUSHALL`.

This is a general strategy. With multiple session stores, multi-region setups, or lossy migrations, add runbooks and dry-runs on synthetic/anonymized snapshots.

## 19. Kubernetes, Blue–Green, and Sticky Load Balancers

A Deployment can spin up replacement pods before old pods finish draining from the Service. Even under the same image tag, changed dependencies can alter serialization. Treat **image digests** and **serializer configuration** as part of your deployment compatibility contract.

Kubernetes does not guarantee “the user's next request always hits the same old pod”, even with `sessionAffinity` enabled:
- Pods are deleted during rolling updates.
- Client IPs change or multiple users share NAT.
- Service/Ingress affinity policies differ.
- Pre-rollout HTTP/2 keep-alive connections persist.
- Browsers reconnect after timeouts or pod drains.
- Blue–green rollbacks shift traffic back to the prior version.

**Sticky sessions do not replace a shared/durable store** when sessions must survive pod recreation. Conversely, a shared store **does not guarantee schema compatibility**; they address separate problems.

### 19.1. Readiness and Graceful Shutdown

In Spring Boot 3.3:
- `management.endpoint.health.probes.enabled=true` enables liveness/readiness endpoints with Actuator.
- `server.shutdown=graceful` and `spring.lifecycle.timeout-per-shutdown-phase=...` let in-flight HTTP requests complete within budget on shutdown.
- Readiness/Ingress routing reduces new requests reaching terminating pods.
- `terminationGracePeriodSeconds` must cover `preStop` + graceful drain + margin.

**Do not rely on graceful shutdown to hide a reader unable to parse a new writer.** A request completing on V2 writes a V2 session; the very next request can land on V1 and fail to decode it. Establish session compatibility before worrying about network draining.

### 19.2. Blue–Green Traffic Switches and Rollbacks

In blue–green, only green may take traffic at a given instant, yet:
- Sessions live in the shared Redis.
- Green may already have migrated/written the new format.
- Rolling back to blue **still reads that newly written data**.
- If green changed cookie names/namespaces, browsers carrying old cookies can lose sessions.
- If green changed security principal serialization, users can lose authentication.

Simulate **switching to green, creating/mutating sessions, and switching back to blue** in staging. Only mark “rollback tested” once **cross-version session bytes and behavior have been verified**, not just seeing Pods Running.

## 20. Pitfalls That Break Production Sessions

### 20.1. Do Not Wipe the Entire Session When One Attribute Fails to Decode

If the cart schema is unrecognized, invalidating the whole session logs the user out and destroys valid attributes. Per business requirements:
- Return a controlled 503/409.
- Record a metric/correlation ID while preserving state to support migration.
- If data is clearly unsafe, invalidate under an approved security policy.
- If only the cart is disposable, reset **only the cart attribute** with explicit messaging/warnings rather than deleting `SecurityContext`.

The demo returns 503 without deleting the session, preserving state for safe rollback and investigation. That status code is not mandated by Spring.

### 20.2. Never Automatically Deserialize Arbitrary Client-Supplied Payloads

Protect Redis/JDBC session backends with network ACLs, auth/TLS, and least privilege. Never let clients supply raw Redis keys, Java serialized bytes, or arbitrary class types to deserialize. With Jackson polymorphism, avoid wide default typing or accepting arbitrary `@class` from untrusted JSON; enforce strict allowlists and tested modules.

### 20.3. Never Put Secrets or PII in Tags or Logs

Never log:
- `SESSION`/`JSESSIONID` cookie values.
- Raw `SecurityContext`/`Authentication`.
- Redis session payloads or serialized Java bytes.
- Refresh/access tokens, passwords, PII, or sensitive cart data.
- Unknown raw JSON from clients.

Metrics should use bounded dimensions like **`schemaVersion`, deployment version, `result=success/failure`, finite reason codes, and store type**—never session IDs or user IDs as tags.

## 21. Observing Session Health During Rollouts

Recommended signals to collect:

| Metric/log | Suggested tags | Meaning |
|---|---|---|
| `session.decode.total` | `format=1/2/unknown`, `appVersion` | Which format versions readers encounter |
| `session.decode.errors` | `reason=bad_json/class_missing/uid_mismatch` | Incompatibilities needing rollback/fix |
| `session.write.total` | `writerSchema=1/2` | Whether V1 writers are still active |
| `session.schema.downgrade.blocked` | `from=2,to=1` | Catches old writers trying to drop fields |
| `session.migration.total` | `from=1,to=2,result` | Read-repair/migration progress |
| `session.redis.errors` | `operation=read/write/timeout` | Store outages, distinct from schema mismatch |
| `session.auth.failures` | `reason=principal_decode/expired/invalid` | Separates auth breaks from cart breaks |
| `session.size.bytes` | histogram/percentiles | Prevents bloated session graphs |
| `session.ttl.remaining` | bucketed/aggregated | Tracks retention/expiry |
| `http.server.requests` | URI template/status/outcome | Impact on HTTP clients |
| `session.concurrent.conflicts` | `operation=cart_mutate` | Detects lost updates when using revision/CAS |

**Most importantly:** separate **Redis unavailable** from **unrecognized schema**. If all V2 requests report missing sessions, V2 may be pointing at a different namespace rather than failing JSON decode. If only pre-deploy sessions fail, suspect class/serializer incompatibility.

These metric names are **suggested custom instrumentation**, not all built into Spring Boot out of the box. Actuator/Micrometer tracing requires proper dependencies/exporters; never automatically attach attribute values or session IDs to spans.

### 21.1. Set User-Centric Rollback Thresholds

Do not watch only `HTTP 5xx rate`. An app might catch a deserialization error, silently instantiate an empty cart, and return HTTP 200—making dashboards look green while customers lose their carts.

Set SLIs/SLOs for:
- Rate of users forced to re-login immediately after rollout.
- Unexpected cart reset/empty-cart rate.
- Session decode error rate broken down by binary version.
- Missing/invalid `SecurityContext` rate.
- Concurrency conflicts/lost updates.
- Redis p95/p99 latency, availability, and connection pool saturation.
- Support complaints/checkout regressions (without PII labels).

## 22. Troubleshooting Multi-Version Session Failures

| Symptom | Possible cause | Diagnostic path |
|---|---|---|
| Switching pods forces re-login | In-memory sessions, unreliable stickiness | Check actual Spring Session repository and cookies |
| Redis configured yet sessions still lost | Namespace/Redis DB/cluster/cookie mismatch | Compare app configs, Redis key prefixes, and cookie attributes |
| `InvalidClassException` | Incompatible JDK UID/field graph | Keep legacy class, add fixture contract tests, migrate |
| `ClassNotFoundException` reading session | Class moved package or deleted | Backward-compatible class adapter or migrate before removal |
| `NotSerializableException` on save | Attribute graph holds non-`Serializable` type | Store `String`/small DTO, never entities/proxies |
| V2 reads V1 fine, V1 fails on V2 | Forward compatibility missing | Do not enable writer2 while old readers remain |
| Image rollback still returns 500 | Redis holds V2-written bytes | Roll back to reader-compatible B or run data migration |
| Cart loses coupon when hitting old pod | Writer1 read V2 then wrote V1 | Writer gate/fencing, block downgrade, CAS |
| Added cart items vanish randomly | Concurrent request lost updates | Durable store revisions/optimistic locking |
| V1 JSON parses into an empty cart | Wrong default or unvalidated missing key | Explicit versioned reads + validation/fail closed |
| `SESSION` cookie flips to `JSESSIONID` | Mixed Spring Session/container cookie resolvers | Standardize cookie name/migration |
| Logged out on one pod, still logged in on another | Separate session stores/invalidation/stale cache | Unify repository and auth invalidation semantics |
| Auth fails while cart remains | `SecurityContext`/principal serializer mismatch | Check custom principals, Security modules, and fixtures |
| V2 fails startup due to Redis | Redis config/ACL/TLS/availability | Connection health/logs, network policy, fail-safe rollout |
| Read-only request mutates session version | Read-repair without write barrier | Do not migrate while old writers are live |
| New JSON serializer cannot read old bytes | Swapped global `RedisSerializer` in one step | Dual serializer/migration; never swap directly |
| JDBC sessions missing after switch | Switched Redis→JDBC without migrating | Keep stable store or plan migration |
| Sessions expire “immediately” after deploy | Mismatched TTL/clock/timeout/cookie `Max-Age` | Inspect `session.timeout` and cookie config |
| Sticky sessions hide bugs in testing | Client stayed on one backend | Test two ports/pods with one cookie, forcing switches |
| Lots of 200s while users lose carts | Handler silently wipes incompatible data | Add preservation metrics, fail closed, QA at business layer |
| V2-only feature visible before writer2 | Ungated feature flag | Disable UI/API until writer mode is stable |
| Cannot drop V1 reader after 30m | Sliding TTL with active users | Measure legacy reads, use absolute expiry/migration plan |
| Running `FLUSHALL` logs everyone out | Confused namespace with whole Redis | Never mass-delete; enforce ownership/backups |

## 23. Alternative Strategies When Compatibility Cannot Be Maintained

Not every system can maintain dual old/new formats simultaneously. Acceptable alternatives depending on product tolerance:

**A. Controlled re-login:** if a security context change cannot safely deserialize, force re-authentication during a maintenance window with user notice, selective session invalidation, and clear SLOs—better than unpredictable auth failures.

**B. Side-by-side session stores:** V1 uses namespace A and V2 uses namespace B; requires sticky/canary routing, cookie transition handling, and no expectation of state continuity. Fits when session isolation and re-auth/transfer are acceptable.

**C. Central session gateway/service:** apps hold a stable token or session ID while a central service manages versioned state. Adds latency/dependencies, but centralizes schema contracts.

**D. Stateless authentication + external business state:** use standard tokens (verifying signing/expiry/rotation) and store carts/workflows in a DB. Does not eliminate all session-like state; refresh tokens/revocation, CSRF, and token compatibility still apply.

**E. Longer backward compatibility window:** retain dual-readers/legacy decoders across several releases; costs extra code but usually carries lower risk than mass session loss.

The choice depends on the business cost of logouts/cart loss, migration complexity, sensitivity, session volume, and rollout/rollback timelines.

## 24. Incident and Rollback Procedure When Post-Rollout Errors Appear

Suppose after enabling `writer2`, 2% of users hit `session.decode.errors`:

1. **Halt rollout expansion** and identify which instances are writing V2.
2. **Do not rush to roll back to V1-only A** if C already wrote V2 data; that can make things worse.
3. Keep/route traffic on a binary B/C **capable of reading V2**, disabling offending features/writes if needed.
4. Capture synthetic/anonymized metadata of format version, exception type, deployment version, namespace, and connector; **never log raw user sessions**.
5. Determine whether the failure stems from Redis connectivity, serializer, classpath, cookies, or app JSON schema.
6. Block writer downgrades/mixed writes if unprotected.
7. Assess critical auth/carts, session data loss, and retry paths.
8. If data migration is unavoidable, test on backups/staging first with forward/backward conversion, logging/metrics, and data rollback.
9. Resume canary only after verifying all reader/writer compatibility.
10. Afterward, add golden binary fixtures, cross-node tests, and CI/CD deployment gates.

**Never delete sessions just to make error graphs drop if the data is recoverable.** Often the bug lies in the V2 app binary, and rolling back to reader-compatible B restores service immediately without touching Redis data.

## 25. Pre-Deployment QA Checklist

- [ ] Inventoried session attribute keys, types, serializers, and owners.
- [ ] Explicitly selected store (in-memory/Redis/JDBC), namespace, and cookie contract.
- [ ] V1 and V2 share the exact same Redis/JDBC connection and schema when sharing sessions.
- [ ] Did not assume sticky LB or matching cookie names imply data compatibility.
- [ ] Defined `schemaVersion`, validation rules, and unknown-version handling.
- [ ] New reader successfully parses golden payloads produced by the real old binary.
- [ ] Old/rollback reader successfully parses every format possible after writer switchover.
- [ ] Writer V1 cannot drop V2-only fields, or is strictly fenced.
- [ ] V2-only features are gated until Writer V2 is safe.
- [ ] No JPA entities, proxies, or large mutable object graphs stored in sessions.
- [ ] Spring Session save mode configured properly; `setAttribute` called after snapshot updates.
- [ ] If migrating serializer JDK→JSON, dual-decoding/migration or controlled re-login is planned.
- [ ] Spring Security context/principal compatibility tested.
- [ ] Login/logout/session ID rotation and CSRF/cookie attributes are consistent.
- [ ] Concurrent requests protect against last-write-wins where state is critical.
- [ ] TTL/absolute retention plan exists rather than relying solely on idle timeouts.
- [ ] Cross-instance V1→V2→V1 test executed with the same cookie and real Redis.
- [ ] Rollback tested **after V2 already wrote** session data.
- [ ] Metrics track decode/write versions, auth failures, cart loss, and Redis availability.
- [ ] Never log raw cookies/session payloads/tokens or wipe Redis as a workaround.
- [ ] Deployment barriers/feature flags synchronized, with an incident runbook ready.

## 26. Self-Check Questions

**1. Do two pods connected to the same Redis guarantee session compatibility?**  
No. They must also align on cookies, namespaces, serializers, and reader schemas. Redis does not convert V1 objects into V2 DTOs.

**2. Do sticky sessions prevent all rolling-deployment errors?**  
No. Old pods can crash, traffic can reroute, cookies/namespaces can mismatch, or rollbacks can occur.

**3. Is `serialVersionUID=1L` on both classes sufficient?**  
No. Fully qualified class names, object graphs, field types, and semantic state can still break.

**4. Why isn't “V2 can read V1” enough to enable the V2 writer?**  
Because V1-only pods and rollback artifacts may not read V2. If V1 writers remain live, they can also downgrade sessions and drop V2-only fields.

**5. Does rolling back V2→V1 automatically roll back Redis session bytes?**  
No. Redis retains the data format written by V2.

**6. Why is storing JSON inside a `String` easier to migrate than storing Java DTOs directly?**  
Because the app controls `schemaVersion`, field mappings, and fallbacks inside JSON without tying the session attribute class name to business DTOs. Still, the underlying session serializer must stay compatible.

**7. Is changing `springSessionDefaultRedisSerializer` from JDK to JSON immediately safe?**  
No. Existing JDK bytes will fail under the JSON decoder; `SecurityContext` can break too.

**8. Does a 30m session timeout mean zero V1 sessions remain 30m after deployment?**  
No. Timeouts are often inactivity-based and extend as users stay active. Explicit retention/migration/metrics are needed.

**9. Why does `session.setAttribute` matter under `on-set-attribute` save mode?**  
It signals that the attribute changed; mutating an existing object in place may not be persisted by the repository.

**10. Can you drop the V1 reader as soon as V2 rollout reaches 100%?**  
Not necessarily. V1 sessions may persist in the store alongside rollback windows, background/multi-region writers, and active users. Use metrics and retention policy to decide.

**11. While V1 and V2 both write to a cart, does a compatible schema prevent lost updates?**  
No. Concurrent writes still suffer last-write-wins; critical state needs revisions/optimistic locking or a durable cart store.

**12. If only authentication state fails to decode, should you reset the cart or delete every session?**  
Do not guess. Handle auth via a fail-safe security policy, consider controlled re-login, and avoid wiping unrelated state unnecessarily.

**13. Do `MockMvc` tests prove cross-node Redis sessions work?**  
No. They test code and Servlet sessions in a single test JVM. Use real Redis and two separate processes/binaries sharing cookies.

**14. What is the safe rollback path after C's V2 writer has been active?**  
Roll back to a reader-compatible binary (B+ reading V2 and preserving state), or perform a real migration—never blindly revert to V1-only A.

## 27. Official References

1. **Spring Boot 3.3.13 — Spring Session**: auto-configuration, Servlet/Reactive stores, and session timeouts. https://docs.spring.io/spring-boot/3.3/reference/web/spring-session.html
2. **Spring Boot 3.3 — Common Application Properties**: `spring.session.redis.*`, `spring.session.timeout`, `server.servlet.session.*`. https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
3. **Spring Session 3.3 — Redis Configuration**: default JDK serialization, `springSessionDefaultRedisSerializer`, namespaces, indexed/default repositories. https://docs.spring.io/spring-session/reference/3.3/configuration/redis.html
4. **Spring Session 3.3 — Spring Boot + Redis Guide**: `springSessionRepositoryFilter` and cookie/Redis lifecycles. https://docs.spring.io/spring-session/reference/3.3/guides/boot-redis.html
5. **Spring Session 3.3 — JDBC Configuration**: `SPRING_SESSION_ATTRIBUTES`, binary attribute serialization, and conversion. https://docs.spring.io/spring-session/reference/3.3/configuration/jdbc.html
6. **Spring Session 3.3 — WebSession Integration**: reactive `WebSession`, `SessionRepository`-backed stores. https://docs.spring.io/spring-session/reference/3.3/web-session.html
7. **Spring Framework — Web MVC Sessions**: Servlet `HttpSession` and session attributes. https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/httpsession.html
8. **Spring Security — Session Management**: session fixation, authentication contexts, and session lifecycle. https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
9. **Oracle Java Object Serialization Specification**: stream class descriptors, compatibility, and `serialVersionUID`. https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/
10. **Kubernetes — Deployments / Rolling Update**: rollout and rollback lifecycles. https://kubernetes.io/docs/concepts/workloads/controllers/deployment/

**Conclusion:** When V1 and V2 serve traffic concurrently, sessions must be treated as **versioned data with a deployment lifecycle independent of the container image**. Shared Redis/JDBC lets both read the same keys, yet does not make code understand old/new bytes automatically. Use multi-version readers, barrier-enforced writer policies, feature gating, golden cross-binary fixtures, cross-pod cookie tests, and rollback tests after V2 writes. When compatibility cannot be preserved, plan an explicit migration or controlled re-login—rather than letting users silently lose their sessions.