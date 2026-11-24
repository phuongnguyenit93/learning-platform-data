# Session Data Serialization and Risks During Application Version Upgrades

## 1. Sessions and cookies: what data is actually stored where?

In a **Spring Boot web-runtime** application, the server can use sessions to retain state across multiple HTTP requests: temporary shopping carts, wizard steps, authentication info, and UI preferences. The browser normally holds only **a cookie containing the session ID** and sends that ID back to the server on subsequent requests.

Conceptual mechanism:

```text
Browser                                       Spring Boot
   │
   ├── POST /cart/items?sku=BOOK-1 ──────────►  @Controller
   │                                              │
   │                                              ▼
   │                                    HttpSession / WebSession
   │                                              │
   │                                   cart = CartSnapshot(...)
   │                                              │
   │                                   Session store / repository
   │
   ◄── Set-Cookie: <session-id> ────────────────┤
   │
   ├── GET /cart + Cookie: <session-id> ───────►  Lookup by session ID
   │                                              │
   │                                       Read session attributes
   │                                              │
   ◄── JSON/HTML response ───────────────────────┤
```

**A cookie normally does not hold the full Java session object.** It carries an ID/opaque token so the server can look up the data (the cookie may be named `JSESSIONID`, `SESSION`, or a custom name). Do not treat the cookie as a copy of the shopping cart or `SecurityContext` object. If an app intentionally implements client-side sessions differently, encryption, signing, key management, and size limits work completely differently.

**Serialization** converts an object/state into a storable format (byte stream, JSON, etc.); **deserialization** reconstructs the object/state from that stored representation. This becomes critical whenever sessions live in Redis, JDBC, or are replicated/persisted by a container.

The core question of this lesson: *If Version V1 stores object A, and then a request hits Version V2 reading the same session, what can break?* Beyond logouts, failures can occur in deserialization, data structures, security semantics, or cart handling—even while the cookie itself remains valid.

## 2. When is session data actually serialized?

Calling `session.setAttribute(...)` does not mean the JVM immediately serializes the object in every setup.

| Session storage type | Where it is stored | Serialization and version risks |
|---|---|---|
| **Servlet container in-memory** (single instance) | Map/objects in process RAM | Usually stores objects directly; may not serialize on each request. Restarts generally lose sessions unless special persistence is configured |
| **Container session replication/persistence** | Cluster or container-managed storage | Can serialize via Tomcat/Jetty/deployment-specific mechanisms; requires compatible attributes |
| **Spring Session Redis** | Redis, shared across multiple instances | Spring Session normally serializes **session attributes**; defaults to JDK serialization per Spring Session 3.x docs |
| **Spring Session JDBC** | `SPRING_SESSION` / `SPRING_SESSION_ATTRIBUTES` tables | Defaults to JDK-serializing attribute values into `byte[]`; supports custom converters/schemas |
| **Spring WebFlux in-memory WebSession** | Reactive in-memory store per instance | Does not inherently run Java serialization on every request; restarts/multi-instance are separate concerns |
| **Spring Session reactive + Redis** | Redis with `WebSession` | Carries similar format and compatibility risks when sharing attributes |

Suppose you run a Spring Boot MVC app with only `spring-boot-starter-web` and embedded Tomcat. `HttpSession.setAttribute("cart", object)` can succeed even if `object` does not implement `Serializable`, because the object stays in RAM. Once you switch to Redis/JDBC or container replication, `NotSerializableException` or cross-version read errors can surface. That is why you must **test against the real session store configuration**, not only locally in RAM.

**Valid cookie ≠ readable session:** Redis still holds the key and TTL, yet V2 cannot deserialize the bytes inside. Some apps respond with 5xx exceptions, login loops, lost attributes, or treat the session as invalid. Exact behavior depends on the framework, serializer, and error handler.

## 3. Lifecycle of a Redis/JDBC session and deployment failure points

```text
Build V1 (JDK/classes V1)
  │
  ├── new CartSnapshotV1(...)
  ├── session.setAttribute("cart", snapshot)
  └── serialize → bytes in Redis/JDBC
                            │
                       rolling deploy
                            │
Build V2 (JDK/classes V2)   │
  │                         ▼
  ├── request carries old ID cookie
  ├── load bytes belonging to old session
  ├── deserialize with V2 classpath
  │       ├── succeeds + semantics right
  │       ├── class/serialVersionUID error
  │       └── technically succeeds, yet logic breaks
  └── response / login / business result
```

During a **rolling deployment**, all of these can happen simultaneously:
- Node **V1 reads V1 sessions**.
- Node **V2 reads V1 sessions**.
- Node **V2 writes V2 sessions**, then a subsequent request lands back on Node V1.
- Node **V1 reads V2 sessions**.

Because a load balancer does not necessarily pin requests to a single pod (and sticky sessions do not guarantee failover safety), a safe migration requires **two-way compatibility** while V1 and V2 run side by side. If V2 can read old data yet V1 cannot read new data, the rollout is not yet safe.

Beyond object types, changes that can affect sessions include:
- Renaming or moving a Java package or class.
- Changing `serialVersionUID`, changing field types, or deleting a class.
- Adding a field without business code handling default values.
- Changing enum values, field semantics, or authorization state representations.
- Changing Jackson property names, polymorphic subtypes, serializer options, or modules.
- Upgrading Spring Security / Spring Session / Redis serializer versions.
- Changing the Redis namespace, attribute keys, TTL, cookie settings, or session ID resolver.
- Sharing a single session store across multiple apps with different classes/formats.

## 4. Java Serializable: what it does and does not do

JDK serialization converts an object graph implementing `java.io.Serializable` into a binary stream. To store a Java object using the default serializer, **every field actually serialized must also support serialization** (or be marked `transient`/handled via custom logic). Marking only the outer class `implements Serializable` is not enough if a nested field holds a non-serializable class.

Example:

```java
import java.io.Serial;
import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;

final class CartSnapshot implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private final int schemaVersion;
    private final ArrayList<String> items;

    CartSnapshot(int schemaVersion, List<String> items) {
        this.schemaVersion = schemaVersion;
        this.items = new ArrayList<>(items);
    }

    int schemaVersion() {
        return schemaVersion;
    }

    List<String> items() {
        return List.copyOf(items);
    }
}
```

This is the Java class used in the complete project in Section 7. `ArrayList<String>` is a standard serializable type; `String` is serializable too. Never store `EntityManager`, sockets, streams, connections, threads, executors, requests, or Spring beans/services inside a session.

### 4.1. `serialVersionUID` is not schema migration

`serialVersionUID` is a class-level Java serialization compatibility identifier. When a stream's UID differs from the loaded class, reading usually throws `java.io.InvalidClassException`. Declaring it explicitly:

```java
@Serial
private static final long serialVersionUID = 1L;
```

prevents the default computed UID from changing due to unintentional source edits. However, **keeping the same UID does not guarantee logical compatibility**:
- Newly added fields can arrive as `null`, `0`, or `false` when reading an old stream.
- Renaming a field causes the old field's data to be dropped and the new field to receive its default value.
- Changing field types, inheritance hierarchies, or custom `readObject`/`writeObject` methods can break the contract.
- Renaming packages or classes can still cause `ClassNotFoundException`, regardless of keeping the same UID.
- Nested classes in the object graph also have their own UIDs and compatibility rules.

**Never tweak a UID to “force” reading data** whose structure or semantics are incompatible. Plan payload versioning and tested migrations instead.

### 4.2. Related exceptions

| Error | Common situation |
|---|---|
| `java.io.NotSerializableException` | An attribute or nested object does not implement `Serializable` when Java serializer writes |
| `java.io.InvalidClassException` | Mismatched UID or incompatible class structure change |
| `java.lang.ClassNotFoundException` | Stream references a class absent in the new deployment |
| `java.io.StreamCorruptedException` | Binary input does not match expected serialization format or data is corrupted |
| Jackson mapping/type-id errors | JSON properties or class metadata incompatible with V2's mapper |
| ClassCastException / NullPointerException | Deserialization succeeds technically, yet values violate V2's model/logic |

Stack traces often appear at the **moment the session is read from the store**, which can happen before the controller even executes. Do not just wrap `getAttribute("cart")` in a `try/catch` assuming every deserialization failure will be caught there.

## 5. Why version upgrades lose sessions or trigger errors

### 5.1. V1 and V2 see the same class name with different meanings

Suppose V1 has:

```java
// V1:
private final String shippingAddress;
```

And V2 replaces it with:

```java
// V2:
private final DeliveryAddress shippingAddress;
```

The serialized value from V1 is a `String`, whereas V2 expects a `DeliveryAddress` object. With JDK serialization, changing a field's type is an incompatible change; with a JSON deserializer, a mapper/migration is needed to convert the old representation to the new one. Even if part of the pipeline deserializes without crashing, if business code assumes a new field is non-null, shipping calculations can fail later.

### 5.2. V1 and V2 share Redis while writing two different formats

Suppose V1 used the Java binary serializer and V2 switched to a JSON serializer. The Redis key `spring:session:...` still exists, yet the JSON serializer cannot understand the previous Java binary bytes. Simply swapping the serializer bean does not migrate existing data in the store. You need one of:
- A transitional reader that understands both old and new formats, or a controlled migration tool.
- Keeping the old serializer until TTLs expire and notifying users if session loss is acceptable.
- A new namespace with an intentional logout plan.
- A coordinated deployment with a verified rollback plan.

**Never try to parse random binary bytes as JSON** and silently fall back to an empty default object; detect formats explicitly, validate, and log appropriately.

### 5.3. Security classes can also live inside the session

When Spring Security uses HTTP sessions, the `SPRING_SECURITY_CONTEXT` attribute can contain `SecurityContext`, `Authentication`, principals, and authorities. Not only `cart`, but Spring Security classes or custom `UserDetails` implementations must also remain compatible. Spring Security 6.3 introduced improvements to JDK serialization compatibility testing to reduce risks across minor releases, yet **this is not a guarantee that every custom application principal will remain compatible**.

Do not slap the same `serialVersionUID` onto every custom security class arbitrarily; test with real serialized fixtures and both old/new classpaths.

## 6. Principles for modeling durable session data

**Recommendation:** keep session attributes minimal, explicitly schema-versioned, and decoupled from database entity models.

Prefer storing:
- A `cartId` or `draftId` pointing to primary data in a DB/cache.
- Small flags/filters like `locale`, `theme`, or a non-sensitive list of SKUs.
- Dedicated session DTOs with stable fields, simple collection types, and `schemaVersion`.
- Data with an appropriate TTL/retention window that does not require infinite recovery.
- If using JSON, a **version discriminator** (e.g., `schemaVersion: 1`), with readers supporting older versions during the migration window.

Avoid storing:
- JPA entities with lazy proxies (pulling in huge class graphs, ORM connections/sessions, and extra data).
- `HttpServletRequest`, `WebClient`, `EntityManager`, `DataSource`, `InputStream`, futures, threads, schedulers, or locks.
- Plaintext passwords, OTPs, long-lived refresh tokens, or secrets without explicit requirements and protections.
- Massive object graphs that make every request read/write expensive.
- Session attributes as an unbounded global cache without TTLs.

**Watch out for mutable objects:** some session repositories only detect changes when `setAttribute` is called (depending on `SaveMode`), missing deep in-place mutations. For instance, calling `cart.getItems().add(sku)` without calling `setAttribute` again may fail to persist in Redis/JDBC. Create immutable DTOs or defensive copies and **re-invoke `setAttribute` with the new object** to avoid change-tracking bugs, races, and dirty-checking surprises.

## 7. Runnable example: Spring Boot MVC + HttpSession + Serializable DTO

This example demonstrates a serializable session object, cookie creation, and reuse across multiple HTTP requests. **The baseline example uses in-memory sessions** and needs no Redis to run. The test in Section 8 verifies real JDK serialization so you do not mistake a passing local run for cross-version compatibility.

**Prerequisites:** JDK 17+ and Gradle compatible with Spring Boot 3.3.x. Version 3.3.13 is pinned for reproducible learning; for production workloads, pick an actively supported Spring Boot line with current patches.

Project structure:

```text
session-version-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/sessions/SessionVersionApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/sessions/CartSnapshotSerializationTest.java
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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
server.servlet.session.timeout=20m
server.servlet.session.cookie.http-only=true
# In production HTTPS, enable cookie.secure=true
# and configure SameSite appropriately for login/redirect flows.
```

**`src/main/java/com/example/sessions/SessionVersionApplication.java`:**

```java
package com.example.sessions;

import java.io.Serial;
import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class SessionVersionApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionVersionApplication.class, args);
    }
}

@RestController
@RequestMapping("/cart")
class CartController {
    private static final String KEY = "cart.snapshot.v1";

    @PostMapping("/items")
    CartView add(HttpServletRequest request, @RequestParam String sku) {
        if (!sku.matches("[A-Za-z0-9_-]{1,24}")) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    "Invalid SKU");
        }

        HttpSession session = request.getSession(true);
        Object stored = session.getAttribute(KEY);
        CartSnapshot old = stored instanceof CartSnapshot snapshot
                ? snapshot : new CartSnapshot(1, List.of());

        List<String> items = new ArrayList<>(old.items());
        items.add(sku);

        CartSnapshot updated = new CartSnapshot(1, items);
        session.setAttribute(KEY, updated); // Helps the repository detect the change.
        return new CartView(updated.schemaVersion(), updated.items());
    }

    @GetMapping
    CartView view(HttpServletRequest request) {
        // Do not create a session just to view an empty cart.
        HttpSession session = request.getSession(false);
        Object stored = session == null ? null : session.getAttribute(KEY);
        CartSnapshot current = stored instanceof CartSnapshot snapshot
                ? snapshot : new CartSnapshot(1, List.of());
        return new CartView(current.schemaVersion(), current.items());
    }

    @DeleteMapping
    ResponseEntity<Void> clear(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session != null) {
            session.invalidate();
        }
        return ResponseEntity.noContent().build();
    }
}

record CartView(int schemaVersion, List<String> items) {}

// This object is dedicated to session storage, NOT a JPA entity.
final class CartSnapshot implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private final int schemaVersion;
    private final ArrayList<String> items;

    CartSnapshot(int schemaVersion, List<String> items) {
        this.schemaVersion = schemaVersion;
        this.items = new ArrayList<>(items);
    }

    int schemaVersion() {
        return schemaVersion;
    }

    List<String> items() {
        return List.copyOf(items);
    }
}
```

**Key points:**
- Both `CartView` (JSON response DTO) and `CartSnapshot` (session-stored object) are separated from database entities.
- `CartSnapshot` implements `Serializable` and declares an explicit UID. `ArrayList<String>` keeps the object graph simple.
- `session.setAttribute(KEY, updated)` creates a new object rather than mutating a nested list and hoping the framework detects it.
- `request.getSession(false)` avoids creating a new session when only reading; `getSession(true)` creates one if missing.
- `session.invalidate()` invalidates the session on the server. It differs from merely clearing the browser cookie; with a shared store, verify TTL/invalidation/replication semantics.
- Session IDs are not returned in JSON. Cookies are sent by the container and retained by curl/browsers without the app manually echoing the ID.
- The demo code has no authentication/authorization/CSRF; production must apply appropriate protections, especially on mutating POST/DELETE endpoints.

**Run:**

```bash
gradle bootRun
```

If the project uses Gradle Wrapper: `./gradlew bootRun` (macOS/Linux) or `.\gradlew.bat bootRun` (Windows PowerShell).

Use curl while preserving cookies:

```bash
# Save cookie from the session-creating response:
curl -i -c cookies.txt -X POST \
  "http://localhost:8080/cart/items?sku=BOOK-1"

# Send the same cookie back:
curl -i -b cookies.txt "http://localhost:8080/cart"

# Invalidate the session:
curl -i -b cookies.txt -X DELETE "http://localhost:8080/cart"

# Viewing again with the old cookie returns an empty cart:
curl -i -b cookies.txt "http://localhost:8080/cart"
```

The first two responses (with no prior data) should return HTTP 200 and JSON:

```json
{"schemaVersion":1,"items":["BOOK-1"]}
```

After `DELETE`, the server returns HTTP 204 No Content. The subsequent GET with the invalidated ID receives an empty cart:

```json
{"schemaVersion":1,"items":[]}
```

Do not predict the cookie/session ID value: it is random and per-session. The local in-memory demo **does not verify** session survival across restarts or across multiple nodes.

## 8. Testing real JDK serialization with Java 17 + JUnit

This test intentionally serializes a `CartSnapshot` to `byte[]` and deserializes it with the same class version. It proves the current class can round-trip, yet **does not yet prove V2 can read V1**.

**`src/test/java/com/example/sessions/CartSnapshotSerializationTest.java`:**

```java
package com.example.sessions;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.util.List;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;

class CartSnapshotSerializationTest {

    @Test
    void cartSnapshotRoundTripsThroughJdkSerialization() throws Exception {
        CartSnapshot before = new CartSnapshot(
                1, List.of("BOOK-1", "BOOK-2"));

        byte[] bytes;
        try (ByteArrayOutputStream buffer = new ByteArrayOutputStream();
             ObjectOutputStream output = new ObjectOutputStream(buffer)) {
            output.writeObject(before);
            output.flush();
            bytes = buffer.toByteArray();
        }

        Object restored;
        try (ByteArrayInputStream buffer = new ByteArrayInputStream(bytes);
             ObjectInputStream input = new ObjectInputStream(buffer)) {
            restored = input.readObject();
        }

        CartSnapshot after = assertInstanceOf(CartSnapshot.class, restored);
        assertEquals(1, after.schemaVersion());
        assertEquals(List.of("BOOK-1", "BOOK-2"), after.items());
    }
}
```

Run:

```bash
gradle test
```

Expected result: the test **passes** with the exact code and dependencies. This tests a byte stream **just produced by and trusted within the test itself**. **Never** use `ObjectInputStream` to read bytes directly from untrusted requests or sources without a strict safety model: Java deserialization of untrusted object graphs carries gadget execution and resource exhaustion risks.

To test real cross-version compatibility, save **V1 fixture bytes** (generated by V1's artifact/classpath) and run a dedicated test in the V2 build that reads those bytes. A test where V2 serializes and V2 deserializes cannot prove compatibility with V1 data sitting in Redis.

## 9. Using Redis to share sessions across instances

Spring Session replaces session storage with a repository, usually through a servlet filter. **Controller `HttpSession` calls do not have to change**, while serialization/persistence moves to Redis. With Spring Boot 3.3 and Example A, add to `dependencies` in `build.gradle`:

```groovy
implementation 'org.springframework.session:spring-session-data-redis'
implementation 'org.springframework.boot:spring-boot-starter-data-redis'
```

The snippet above consists of **two extra dependency lines**, not the full build file. With a running Redis server, add configuration:

```properties
spring.data.redis.host=localhost
spring.data.redis.port=6379
spring.session.redis.namespace=demo:session:v1
server.servlet.session.timeout=20m
```

These lines illustrate local/dev configuration. In production, configure TLS/ACL/auth/secrets, network policies, app-isolated namespaces, and TTL policies. Never commit Redis passwords to Git. Spring Session Redis paired with Spring Boot auto-configuration is normally enough to manage `HttpSession`; do not also add `@EnableRedisHttpSession` just to duplicate auto-configuration.

With a Redis session store, requests hitting multiple nodes can read the same ID if they share the repository, key namespace, and serializer/class format. However, it only **provides a shared storage location**, and does not guarantee every build version can understand every other version's objects.

Spring Session Redis 3.x uses **JDK serialization by default for session attributes** per documentation. Therefore:
- `CartSnapshot` in the example genuinely needs to be serializable.
- Non-serializable attributes can fail on save; compatibility errors can appear on load.
- Matching packages/names/`serialVersionUID` are only the baseline, not a guarantee of business logic correctness.
- Session TTL/invalidation governs how long old data survives and the migration window.
- Changing namespace from `demo:session:v1` to `demo:session:v2` hides old sessions from the app. That is **isolation or forced re-login**, not automatic migration.

**Do not confuse session persistence with class upgradability:** a Redis session surviving a restart only proves the byte stream stayed in Redis, not that every Java/app upgrade can read it back.

## 10. How do JDBC Sessions and Spring WebFlux differ?

### 10.1. Spring Session JDBC

With JDBC, Spring Session typically stores session metadata in `SPRING_SESSION` and attributes in `SPRING_SESSION_ATTRIBUTES`. Per the Spring Session JDBC 3.x guide, attribute values are JDK-serialized into **bytes** by default, so class compatibility risks remain even though storage is SQL.

Configuration and dependencies vary by database/datasource. Example **configuration snippet** for an app with an existing datasource:

```groovy
implementation 'org.springframework.session:spring-session-jdbc'
implementation 'org.springframework.boot:spring-boot-starter-jdbc'
```

These are supplemental dependencies only; running requires configuring the datasource, JDBC driver, session schema, permissions, and connection pool. Spring Session ships database-specific SQL scripts. When customizing the JDBC serializer, configure the proper converter (commonly a `springSessionConversionService` bean) along with schema/SQL matching your column types. Customization differs from Redis; **never copy a Redis serializer bean expecting JDBC to automatically switch formats**.

### 10.2. Spring WebFlux uses `WebSession`

In WebFlux, the abstraction is `org.springframework.web.server.WebSession`, not Servlet `HttpSession`. Illustrative code model inside **a separate `spring-boot-starter-webflux` project**:

```java
import org.springframework.web.server.WebSession;
import reactor.core.publisher.Mono;

// Inside a WebFlux @RestController, not a Servlet controller:
@GetMapping("/reactive/cart")
Mono<CartStatus> view(WebSession session) {
    String json = session.getAttribute("cart.json");
    return Mono.just(new CartStatus(json != null));
}

@PostMapping("/reactive/cart")
Mono<Void> mark(WebSession session) {
    session.getAttributes().put("cart.json",
            "{\"schemaVersion\":1,\"items\":[\"BOOK-1\"]}");
    return Mono.empty();
}

record CartStatus(boolean hasCart) {}
```

This is an **illustrative controller snippet**, not a standalone file: place the methods inside a controller, import `GetMapping`/`PostMapping`, and implement proper input validation. The WebFlux framework persists `WebSession` when the response completes per contract; when writing custom cleanup/invalidation flows, note that APIs such as `WebSession.invalidate()` return `Mono<Void>` and must be composed/returned rather than calling `subscribe()` manually inside a controller.

When using Spring Session Redis for WebFlux, also check serialization/payload compatibility for reactive session attributes. Running on Netty instead of Tomcat **does not eliminate** the risk of stale objects in Redis.

## 11. Application-controlled versioned JSON payloads

One way to reduce coupling to Java class internals is storing a **JSON string with an explicit schema version** in the session instead of full Java entities or complex object graphs.

Example of two formats:
- V1: `{"schemaVersion":1,"items":["BOOK-1"]}`
- V2: `{"schemaVersion":2,"skuCodes":["BOOK-1"]}`

V2 can **read both V1 and V2**, while writing V2 only after no V1 nodes remain if V1 cannot read V2.

Example helper using Jackson, available whenever a Spring Boot web project includes Jackson:

**`src/main/java/com/example/sessions/CartJsonCodec.java`:**

```java
package com.example.sessions;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

final class CartJsonCodec {
    private final ObjectMapper mapper = new ObjectMapper();

    String encodeV2(List<String> skuCodes) throws JsonProcessingException {
        return mapper.writeValueAsString(Map.of(
                "schemaVersion", 2,
                "skuCodes", skuCodes));
    }

    List<String> decodeV1OrV2(String text) throws IOException {
        JsonNode root = mapper.readTree(text);
        if (root == null || !root.isObject()) {
            throw new IllegalArgumentException("Invalid cart payload");
        }

        int version = root.path("schemaVersion").asInt(-1);
        JsonNode array;

        if (version == 1) {
            array = root.path("items");
        } else if (version == 2) {
            array = root.path("skuCodes");
        } else {
            throw new IllegalArgumentException(
                    "Unsupported cart schema version: " + version);
        }

        if (!array.isArray() || array.size() > 100) {
            throw new IllegalArgumentException("Invalid cart items");
        }

        ArrayList<String> result = new ArrayList<>();
        for (JsonNode item : array) {
            if (!item.isTextual()
                    || !item.asText().matches("[A-Za-z0-9_-]{1,24}")) {
                throw new IllegalArgumentException("Invalid SKU");
            }
            result.add(item.asText());
        }
        return List.copyOf(result);
    }
}
```

**Usage in a session (illustrative snippet inside a service/controller):**

```java
CartJsonCodec codec = new CartJsonCodec();

String json = codec.encodeV2(List.of("BOOK-1"));
session.setAttribute("cart.json", json);

// On read: verify the exact type before decoding.
Object stored = session.getAttribute("cart.json");
if (stored instanceof String text) {
    List<String> items = codec.decodeV1OrV2(text);
    // Process items according to business logic.
}
```

This snippet assumes an `HttpSession session` and a method allowed to throw/handle `IOException`. It is **not a complete controller**. In real applications, inject/reuse `ObjectMapper`/codec, distinguish legacy-data errors from business errors, add safe logging/metrics, and define an intentional invalidation or migration policy.

**Why does this help migrations?**
- Java `String` has a far more stable serialization contract than application-specific object graphs. If Spring Session still uses the JDK serializer, the **`String`** value may still be JDK-serialized to a byte stream; this does not automatically turn all of Redis into raw JSON.
- The schema version and application parser explicitly govern renaming `items` → `skuCodes` and validate bounds and values.
- You can test with JSON fixtures from multiple app versions without loading V1 classes.
- However, if Redis still holds other attributes via JDK serialization (especially security contexts), risks on those attributes remain.
- Never turn on broad Jackson default polymorphic typing to deserialize arbitrary classes from untrusted data; configure explicit allowed types and security modules properly.

### 11.1. Changing the serializer for all of Spring Session Redis is a bigger step

Spring Session lets you customize the Redis serializer via a bean named **`springSessionDefaultRedisSerializer`**. Example **illustrative configuration** (verify compatibility across *all* session attributes before deploying):

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializer;

@Configuration
class SessionSerializerConfig {

    @Bean("springSessionDefaultRedisSerializer")
    RedisSerializer<Object> springSessionDefaultRedisSerializer() {
        return new GenericJackson2JsonRedisSerializer();
    }
}
```

This uses Spring Data Redis's `GenericJackson2JsonRedisSerializer`; it is not a change to apply blindly to every system. **If JDK-serialized sessions already exist, switching the serializer to JSON will not automatically read old data.** You need a migration, dual reader, fresh namespace, or planned session expiration policy.

With Spring Security, custom `ObjectMapper` setups typically require dedicated Jackson modules/mix-ins to serialize/deserialize `SecurityContext` and principals. A generic JSON config might work for a cart yet break when restoring authentication. Test **every** attribute, not just `cart`. Avoid permissive type polymorphism over untrusted bytes; restrict Redis access, enforce network/TLS security, and keep schemas/types tight.

## 12. Rolling deployments: designing two-way compatibility

A simple verification matrix:

| Serving reader | V1 bytes/payload | V2 bytes/payload |
|---|---|---|
| **V1 node** | Must be readable | May not be readable |
| **V2 node** | Must be readable during rolling upgrade | Must be readable |

While V1 and V2 serve traffic simultaneously, if V2 **writes** a new format that V1 **cannot read**, the top-right cell fails. A safe rollout can follow three phases:

**Phase A — Expand reader:** release V1.5 capable of reading both V1 and V2 schemas while **still writing V1**. Wait until every node runs the new reader, checking deserialization failure metrics, session load/save latency, and 5xx rates. Never deploy a new global serializer while unreadable bytes remain.

**Phase B — Switch writer:** once all nodes read both formats, switch to writing V2 while still accepting V1. If a rollback to V1.5 is needed, V1.5 can still read V2. Rolling back to the original V1 would still be unsafe; plan rollbacks to a dual-reader release.

**Phase C — Contract:** after TTLs and retention windows guarantee all V1 payloads have expired or been migrated, you can remove V1 reader code. Do so only when observability proves old sessions are gone and product owners accept any remaining user impact.

When compatibility cannot be preserved (e.g., breaking JDK binary class graph changes), explicit options include:
- **Force new sessions** on deploy, notify users to re-sign in, and do not promise preserving unsaved carts.
- **Isolate namespaces** between V1 and V2 with a controlled migration strategy; changing namespace **does not migrate automatically**.
- **Stop-the-world deployment** with acceptable downtime and planned session wiping/migration.
- **Keep short TTLs** for non-critical sessions and wait for all old keys to expire before changing serializers.

Sticky sessions can reduce node-hopping frequency yet do not solve failover, autoscaling, pod eviction, or multi-revision rollouts. Never cite sticky sessions as proof of compatibility.

## 13. Business, security, and operational risks

### 13.1. Semantic bugs are more dangerous than exceptions

Succeeding at deserialization while a field takes on a new meaning causes subtle corruption:
- `roles` changing from CSV string to list isn't parsed properly, causing wrong authorization.
- Newly added `currency` arrives null → totals calculated with the wrong default currency.
- Old carts hold discontinued SKUs or stale prices/taxes.
- V1 wizard state lacks a new consent or terms step.
- Tenant/customer context shifts while an old session retains the previous identifier.

Never treat the session as the sole source of truth for prices, inventory, or privileges. Recompute sensitive values from authoritative sources and enforce authorization on every request. For critical records, persist in a DB under a stable key and hold only the reference in the session.

### 13.2. Cookie and session security

- Session IDs are **bearer secrets**; never log raw values to stdout, access logs, or analytics.
- Enforce HTTPS, `Secure`, `HttpOnly`, and `SameSite` suited to login/redirect flows and CORS/CSRF policies.
- Regenerate/rotate session IDs after authentication or privilege elevation to mitigate session fixation.
- Invalidate sessions properly on logout/revocation, synchronized with Spring Security and the session repository.
- Secure Redis/JDBC: restrict networks, auth, ACLs, encryption, backups, and access controls; stored sessions can contain PII and security metadata.
- **Never deserialize untrusted Java bytes** via unrestricted `ObjectInputStream`. Java serialization has gadget attack surfaces; enforce input types, object filters, and minimize classpath exposure if used.
- Do not assume JSON is inherently safe: avoid broad polymorphic deserialization, validate schemas/field lengths, and cap attribute byte sizes and element counts.

### 13.3. Races between two requests sharing one session

Two concurrent requests from the same browser can load the same V1 snapshot and overwrite each other when saving, causing **lost updates**. `Serializable`/JSON does not make session updates transactional. When cart consistency matters, write updates to a DB/Redis data structure with appropriate locking or atomic operations rather than treating a session attribute object as the single source of truth.

With Spring Session's `SaveMode` and `FlushMode`, verify when attributes are marked dirty and when persistence runs. Deeply mutating a mutable session object may go undetected. Safe practice: copy into an immutable DTO, re-call `setAttribute`, and use dedicated concurrency control for concurrent writes.

### 13.4. TTL, eviction, and deployments

Session TTL is typically an **inactivity timeout**, not necessarily an absolute age since creation. Actively used sessions can survive across multiple deployments. Do not assume “waiting 30 minutes” suffices if active users keep refreshing V1 data. Inspect max lifetimes/retention, attribute re-save behavior, and real metrics.

Redis eviction under memory pressure can also drop sessions before TTL; replication/failover does not guarantee strong transactions across an entire workflow. Plan UX for affected users: re-login prompts, cart recovery from DB if appropriate, and graceful handling of session load failures.

## 14. How to actually test migrations

A multi-layered test strategy:

1. **Unit tests on current code:** serialize/deserialize V1/V1 or V2/V2. Catch `NotSerializableException`, inspect the object graph, and validate.
2. **Cross-version golden fixtures:** run the V1 build to produce real binary fixtures (`CartSnapshot` and, if applicable, `SecurityContext`), commit them to test resources, and have the V2 build read those fixtures and assert semantics.
3. **Compatibility matrix:** test V1 reading V2 if both run concurrently; or prove V1 is fully drained before enabling the new writer.
4. **Redis integration tests:** run two artifact versions sequentially/concurrently against the same Redis and namespace; obtain a cookie from V1, send requests to V2, then send back to V1. Confirm zero 500s, no unexpected logouts, and no lost carts.
5. **Security fixtures:** test `SPRING_SECURITY_CONTEXT`, custom principal classes, authorities, and session fixation/invalidation across upgrades.
6. **Rollback rehearsal:** let V2 write a session, then roll back to the allowed target release and confirm data remains readable.
7. **Failure injection:** remove a class from the classpath, alter a demo class UID, swap JSON codecs, expire keys, bring Redis down; verify responses, logs, and metrics behave cleanly.
8. **Load/concurrency tests:** fire two concurrent requests updating the cart in the same session, verifying lost-update protections where business rules require them.

Meaningful test flow (pseudocode, **not standalone runnable**):

```text
1) Boot V1 + Redis test container + cookie jar
2) POST /cart/items?sku=BOOK-1 -> persists V1 session
3) Stop V1, boot V2 with same Redis namespace/serializer
4) GET /cart with same cookie -> receives BOOK-1 intact
5) POST /cart/items?sku=BOOK-2 on V2 -> persists update
6) If rolling: route request back to V1.5 (dual reader)
7) GET /cart -> still shows BOOK-1, BOOK-2
8) Repeat with Spring Security authentication/sessions separately
```

If step 4 fails, inspect serializer errors, class names, UIDs, and security context. If step 7 fails, the older reader cannot parse the new payload; do not enable the V2 writer while V1 nodes remain live.

**Never cite local in-memory restarts as proof of compatibility**: restarts wipe in-memory session objects, leaving no old-version data to deserialize. Tests must use a persistent/shared store or saved fixture bytes.

## 15. Symptom-based troubleshooting

| Symptom | Suspected cause | Resolution |
|---|---|---|
| Local MVC works; Redis deploy throws `NotSerializableException` | Attribute or nested class is not serializable | Audit object graph; switch to simple DTOs or JSON Strings |
| HTTP 500 after deploy on requests carrying old cookies | `InvalidClassException`, missing class, or JSON mapping failure | Inspect stack trace at session load time; run cross-version fixtures |
| Users randomly logged out across pods | Security context fails to deserialize, mismatched namespace, missing keys, or TTL/Redis error | Test Spring Security attributes and verify identical cookie/session store configs |
| No serialization error, yet shopping cart becomes empty | Attribute key/schema changed, or default values applied when reading old class | Readers must accept both schemas and migrate rather than silently dropping data |
| 5xx errors after switching to JSON serializer | Redis still contains prior JDK binary byte streams | Use migration/dual reader or an intentional invalidation policy |
| Added new field, yet code receives `null` | Java deserialization populates defaults for fields absent from old stream | Validate/normalize after deserialization; update schema and test old fixtures |
| Updating a list in the session fails to persist | Deep mutation was not marked dirty | Create a new object and call `setAttribute`; check `SaveMode` |
| Errors appear only during rollback | V1 cannot read payloads written by V2 | Follow expand–contract; roll back only to a dual-reader version |
| Sessions expire early or never expire | TTL/inactivity, access refreshes, eviction, or mismatched configs | Monitor Redis/JDBC expiry and session metadata; unify configurations |
| Renaming a DTO package causes `ClassNotFoundException` | Binary Java stream embeds the old class name | Use controlled migration/bridge classes or class-independent schemas |
| Two items added in parallel, yet only one shows up | Lost update from concurrent requests | Enforce atomic updates in business storage |

**Observe without leaking secrets:** log attribute/class/serializer names, build/version IDs, error codes, an anonymous correlation ID, and failed key counts; never log cookie values, raw serialized bytes, full principals, or PII. Metrics such as `session_deserialization_failures_total`, `session_read_latency`, `session_migration_fallback_total`, and `session_invalidations_total` show whether a migration is healthy.

## 16. Pre-upgrade checklist

- [ ] Inventoried where sessions live: in-memory, container replication, Spring Session Redis/JDBC, or reactive `WebSession`.
- [ ] Inventoried all attributes and object graphs; identified security contexts/principals and custom serializers.
- [ ] Identified which build/version wrote existing data and which readers will read it during/after rollout.
- [ ] Put stable schema versions/DTOs or real cross-version Java fixtures in place.
- [ ] Tested **V2 reading V1** and, for rolling upgrades, **V1/V1.5 reading V2**.
- [ ] Did not switch JDK↔JSON serializers while legacy bytes remain without a migration or invalidation plan.
- [ ] Applied expand–contract, aligning rollout/rollback to reader capabilities rather than relying solely on sticky sessions.
- [ ] Verified real TTL/age, plus re-login/state-recovery UX if forcing session resets.
- [ ] Verified cookies, auth sessions, Spring Security compatibility, and Redis/JDBC security.
- [ ] Checked mutable state/lost updates, deserialization error metrics, and rehearsed rollback.
- [ ] Never treated single-classpath unit test passes as proof of deployment compatibility.

## 17. Further official reading

- Spring Session 3.1 — Boot + Redis: dependencies, filter, session timeout, and namespace: https://docs.spring.io/spring-session/reference/3.1/guides/boot-redis.html
- Spring Session 3.2 — Redis custom serializer and `springSessionDefaultRedisSerializer`: https://docs.spring.io/spring-session/reference/3.2/configuration/redis.html
- Spring Session 3.3 — JDBC binary JDK serialization and custom converter/JSON: https://docs.spring.io/spring-session/reference/3.3/configuration/jdbc.html
- Spring Boot 3.3 — Spring Session integration: https://docs.spring.io/spring-boot/3.3/reference/web/spring-session.html
- Oracle Java SE 17 — `Serializable`, `serialVersionUID`, and `InvalidClassException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html
- Java Object Serialization Specification — Compatible and incompatible class changes: https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/version.html
- Spring Security — Blog post on JDK serialization compatibility starting in Spring Security 6.3: https://spring.io/blog/2024/01/19/spring-security-6-3-adds-passive-jdk-serialization-deserialization-for/

**Summary:** cookies usually serve only as session lookup keys; deployment risks lie in **serialized attributes** and their business semantics. `Serializable`/`serialVersionUID` solves only part of compatibility. In multi-node environments with rolling upgrades, design versioned payloads, two-way compatible readers during the transition window, tests using real V1 data, and explicit invalidation/migration/rollback policies.