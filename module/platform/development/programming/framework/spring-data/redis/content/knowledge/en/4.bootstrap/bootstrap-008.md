# Verifying Connectivity with a Simple Write–Read Operation

After adding Spring Data Redis and configuring the Redis Server address, the first step is to **verify that the Spring Boot application can actually write a value to Redis and read back the exact same value**. A simple write–read smoke test surfaces connection, configuration, and permission errors early before you build more complex caching, session, token, or data storage logic.

The core idea is straightforward:

1. The application generates a **dedicated test key** that will not collide with real data.
2. It uses **StringRedisTemplate** to write a value with the equivalent of a **SET** command.
3. It reads the same key with the equivalent of a **GET** command.
4. It compares the read value against the written value; if they match, the write–read check succeeds.
5. It deletes the test key afterward and sets a **short TTL** in case the application terminates before cleanup runs.

This lesson uses Spring Boot 3.x, Spring Data Redis, and a locally running Redis Server as examples. The same reasoning applies to Redis in Docker Compose, dedicated servers, or managed Redis services.

## 1. What Does a Write–Read Check Confirm?

When a **SET** followed by **GET** succeeds from the application, it shows at the time of the check that:

- The application established a connection path through Spring Data Redis and the Redis driver to a Redis endpoint.
- Redis Server accepted and executed the write command for the test key.
- The application read that key back and received the expected value.
- The key/value encoding used during this write–read round-trip behaved consistently.

This is a **small end-to-end check**, stronger than merely seeing Spring Boot start up without errors.

However, one successful SET/GET **does not prove** the entire Redis setup is production-ready. It does not verify persistence across restarts, failover, replication, Redis Cluster, latency under load, permissions for every command type, or long-term stability. Those requirements must be tested and monitored separately.

### How `PING` and `SET`/`GET` Differ

| Check | Primarily Proves | Does Not Prove Yet |
|---|---|---|
| **PING** via `redis-cli` or driver | The Redis endpoint responds to a basic command | The app can SET/GET target keys or has write permissions |
| **SET** from Spring app | Connection path and write command work | The value can be read back accurately |
| **SET then GET and compare** | Closed-loop write–read with active client/serializer setup | Durability, high load, failover, or other Redis features |
| **SET with TTL, GET, then DEL** | Write–read works and test key cleanup is handled | Does not imply business data or entire Redis health is sound |

For instance, **redis-cli PING** can return **PONG** while the application still hits **NOAUTH**, **WRONGPASS**, connects to the wrong host, or uses a read-only Redis user. Therefore, run checks from **the Spring Boot application itself** when validating application configuration.

## 2. Preparing a Running Redis Server

A Spring Data Redis application is only a **client**; adding the starter does not spin up a Redis Server. Before writing verification code, you need a reachable Redis endpoint.

### 2.1. Example: Starting Redis with Docker

If Docker is available, you can run a Redis Server for learning:

~~~bash
docker run -d \
  --name redis-spring-demo \
  -p 127.0.0.1:6379:6379 \
  redis:7-alpine
~~~

This maps the container's Redis port to **6379 on the host loopback interface**, suitable when Spring Boot runs directly on the same machine. If another Redis Server already occupies that port, use the existing instance or pick a different host port; never run two servers competing for the same port.

Check Redis Server inside the container:

~~~bash
docker exec redis-spring-demo redis-cli PING
~~~

Expected output:

~~~text
PONG
~~~

**`PONG` here only verifies Redis inside the container**. The Spring Boot write–read step in subsequent sections tests the full connection path from the application.

If you have **redis-cli** on the host, you can also test through the published port:

~~~bash
redis-cli -h 127.0.0.1 -p 6379 PING
~~~

When done practicing, stop and remove the test container if no longer needed:

~~~bash
docker stop redis-spring-demo
docker rm redis-spring-demo
~~~

### 2.2. Note on `localhost`

**`localhost` refers to the environment running the client program**:

| Where Spring Boot Runs | Where Redis Server Lives | Host Configured in App |
|---|---|---|
| Spring Boot on host, Redis container publishes port 6379 to host | Same host via port mapping | **localhost** or **127.0.0.1** |
| Spring Boot and Redis in separate containers on the same Docker Compose network | Redis container named `redis` | **redis** (Compose service name) |
| Spring Boot on dev machine, Redis on another server | Dedicated server | DNS/IP of the Redis machine |
| Spring Boot in cloud, managed Redis | Managed Redis service | Endpoint provided by vendor |

When Spring Boot runs **inside a container**, `localhost` points to the Spring Boot container itself. If Redis is in another container, configuring `localhost` usually triggers connection failures. Containers should communicate via service names/hostnames over a shared network.

## 3. Adding Spring Data Redis to the Application

In Spring Boot using Gradle, declare the starter:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

The starter provides Spring Data Redis infrastructure and uses **Lettuce** as the default Redis driver. When Spring Boot auto-configuration conditions are met, the app can inject **StringRedisTemplate** and **RedisConnectionFactory**.

Path of an operation:

~~~text
Spring Boot Service / ApplicationRunner
                 |
                 v
         StringRedisTemplate
                 |
                 v
       RedisConnectionFactory
                 |
                 v
           RedisConnection
                 |
                 v
       Lettuce (Redis driver)
                 |
                 v
         Redis Server :6379
~~~

For a simple check, **StringRedisTemplate** is convenient: both keys and values are strings, reducing confusion from Java object serializers. **StringRedisTemplate does not store data itself**; it uses the connection factory and driver to send commands to Redis Server.

## 4. Configuring Connection Settings and Enabling the Check on Demand

Example settings in **src/main/resources/application.yml**:

~~~yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST:localhost}
      port: ${REDIS_PORT:6379}
      timeout: 2s

app:
  redis:
    smoke-test:
      enabled: ${REDIS_SMOKE_TEST_ENABLED:false}
~~~

Meaning:

- **spring.data.redis.host** and **port**: the Redis endpoint the app connects to.
- **timeout: 2s**: reasonable timeout for local demos; cloud networks or production systems should tune this per requirements.
- **REDIS_HOST** and **REDIS_PORT**: let you override the Redis address via environment variables without editing source code.
- **app.redis.smoke-test.enabled**: an example toggle defaulting to **false** so the test runs only when intentionally enabled.

In Spring Boot 3.x, the Redis prefix used here is **spring.data.redis**. If working with another Spring Boot version, verify properties against that specific version.

The **app.redis.smoke-test.enabled** flag is not a built-in Spring Boot Redis property; it is a custom key defined by this lesson to control the probe bean.

When Redis Server requires authentication or TLS, add matching settings such as username/password and SSL for your environment. Never hardcode passwords in Java code or commit real secrets to the repository.

## 5. Writing a `SET` → `GET` Check with `StringRedisTemplate`

We implement an **ApplicationRunner** bean. It runs once after Spring Boot builds the application context and receives startup arguments. Using **@ConditionalOnProperty**, it is created only when the smoke test flag is enabled.

Create a Java file inside an application package, e.g., **RedisSmokeTestConfiguration.java**:

~~~java
package com.example.redislearning;

import java.time.Duration;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration(proxyBeanMethods = false)
public class RedisSmokeTestConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(RedisSmokeTestConfiguration.class);

    @Bean
    @ConditionalOnProperty(
            name = "app.redis.smoke-test.enabled",
            havingValue = "true"
    )
    ApplicationRunner redisWriteReadSmokeTest(StringRedisTemplate redis) {
        return args -> {
            String key = "smoke:redis:" + UUID.randomUUID();
            String expected = "spring-data-redis-ok";
            boolean writeCompleted = false;

            try {
                // SET key value EX 60: write data with a 60-second TTL.
                redis.opsForValue().set(
                        key,
                        expected,
                        Duration.ofSeconds(60)
                );
                writeCompleted = true;

                // GET key: read the data back through the Spring application.
                String actual = redis.opsForValue().get(key);

                if (!expected.equals(actual)) {
                    throw new IllegalStateException(
                            "Redis write/read mismatch for key: " + key
                                    + ", actual=" + actual
                    );
                }

                log.info("REDIS_SMOKE_OK: SET/GET succeeded, key={}", key);
            } finally {
                if (writeCompleted) {
                    try {
                        // Clean up test key; TTL still protects if cleanup fails.
                        redis.delete(key);
                    } catch (RuntimeException cleanupFailure) {
                        log.warn(
                                "Could not delete temporary Redis key: {}",
                                key,
                                cleanupFailure
                        );
                    }
                }
            }
        };
    }
}
~~~

### 5.1. Why Use a Key with a UUID?

~~~java
String key = "smoke:redis:" + UUID.randomUUID();
~~~

Each run gets its own unique key, such as:

~~~text
smoke:redis:9be4fe07-88bb-4773-8a68-31dd78b0ef3d
~~~

The **smoke:redis:** prefix identifies the test purpose. The UUID reduces the risk of:

- Overwriting existing business keys.
- Two Spring Boot instances colliding on the same key and yielding flaky results.
- Reading stale values left over from an earlier test run.

In shared Redis environments, use a namespace dedicated to the application/environment. If Redis ACLs restrict key patterns, ensure the smoke test namespace falls within the client's permitted key patterns.

### 5.2. Why Must `SET` Include a TTL?

~~~java
redis.opsForValue().set(
        key,
        expected,
        Duration.ofSeconds(60)
);
~~~

Spring Data Redis asks Redis Server to perform the equivalent of:

~~~text
SET smoke:redis:<id> spring-data-redis-ok EX 60
~~~

**EX 60** attaches a 60-second expiration atomically with the write. If the program crashes, drops the connection, or skips cleanup, the test key still expires.

This is safer than writing a test key without a TTL and hoping cleanup always runs. In this example, **60 seconds** is plenty for local checks; real systems should pick a TTL suited to their network and latency characteristics.

### 5.3. Why Compare the Value Instead of Just Calling `GET`?

~~~java
String actual = redis.opsForValue().get(key);

if (!expected.equals(actual)) {
    throw new IllegalStateException(
            "Redis write/read mismatch for key: " + key
                    + ", actual=" + actual
    );
}
~~~

**GET** returns **null** if the key is missing or already expired. The check passes only when **actual** equals **expected**. Writing **expected.equals(actual)** also prevents a **NullPointerException** when `actual` is null.

In real applications, you do not always need to log full values. For sensitive payloads like OTPs, tokens, or session data, log only check status and non-sensitive identifiers.

### 5.4. Why Always Clean Up the Key?

The **finally** block runs after either the success path or an exception. If the write returned successfully, the program attempts to delete the key with **DEL**. Cleanup is wrapped in its own try/catch so a cleanup error never masks the primary write–read failure.

If Redis Server executed `SET` but the connection dropped before the client received the reply, **writeCompleted** may remain false. Because the key was written with a TTL, the test data still expires instead of lingering forever.

Deletion can be denied by Redis ACLs. That does not invalidate the SET/GET check, though cleanup warnings should be aligned with permission policies; the TTL acts as a safety net.

## 6. Running the Check and Reading Results

Prerequisites before running:

1. Redis Server is running and reachable from Spring Boot's environment.
2. The application includes the **spring-boot-starter-data-redis** dependency.
3. **application.yml** holds valid connection settings and the smoke test flag.
4. **RedisSmokeTestConfiguration** sits in a package scanned by Spring Boot.

You can enable the flag in your IDE run configuration in either of two ways:

- Add program argument: **--app.redis.smoke-test.enabled=true**.
- Or set environment variable **REDIS_SMOKE_TEST_ENABLED=true**.

If packaged as an executable JAR, for example:

~~~bash
java -jar app.jar --app.redis.smoke-test.enabled=true
~~~

The name **app.jar** is illustrative; substitute your actual JAR path. On success, the logs show a message like:

~~~text
INFO  ... RedisSmokeTestConfiguration :
REDIS_SMOKE_OK: SET/GET succeeded, key=smoke:redis:9be4fe07-...
~~~

The UUID changes each run. The success message is logged **only after SET, GET, and the equality check all pass**. If Redis is unreachable or the read value mismatches, the runner throws an exception and Spring Boot fails startup.

### What Does Defaulting the Flag to `false` Achieve?

When the flag is off, **@ConditionalOnProperty** skips creating the probe `ApplicationRunner` bean. This prevents unwanted test writes on every production application startup.

A smoke test that **intentionally fails startup** on Redis write–read failure can be useful in learning, testing, or when Redis is a hard dependency. In production systems, deciding whether temporary Redis unavailability should block startup must reflect actual dependency criticality and health/readiness strategy; do not accidentally use a demo probe as an availability policy.

## 7. Tracing `SET` and `GET` Flow in Spring Data Redis

When the runner executes:

~~~java
redis.opsForValue().set(key, expected, Duration.ofSeconds(60));
String actual = redis.opsForValue().get(key);
~~~

The processing flow looks like:

~~~text
  ApplicationRunner
         |
         | set(key, value, 60s)
         v
  StringRedisTemplate
         |
         | convert String to bytes
         | obtain RedisConnection from RedisConnectionFactory
         v
  Lettuce / Jedis
         |
         | SET key value EX 60
         v
     Redis Server
         |
         | store key and TTL; return response
         v
  Spring Data Redis
         |
         | get(key)
         v
     Redis Server
         |
         | return value (or nil if key is absent)
         v
  StringRedisTemplate
         |
         | convert bytes to String
         v
  ApplicationRunner
         |
         | expected.equals(actual)?
         +---- Yes --> log REDIS_SMOKE_OK
         |
         '---- No ---> throw error, investigate cause
~~~

In this model:

- **StringRedisTemplate** provides the Java API and handles string serialization.
- **RedisConnectionFactory** supplies a `RedisConnection` per application settings.
- **RedisConnection and the driver** transmit commands and receive responses over the connection.
- **Redis Server** executes SET/GET/DEL and manages TTLs.

Seeing `RedisTemplate` work does not mean `RedisConnectionFactory` stores data itself: data storage remains inside Redis Server.

## 8. A Minimal Version to Try Inside a Service

If you already have a service or lab exercise that invokes a probe explicitly, you can simplify the logic:

~~~java
import java.time.Duration;
import java.util.UUID;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class SimpleRedisProbe {

    private final StringRedisTemplate redis;

    public SimpleRedisProbe(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public boolean checkWriteRead() {
        String key = "smoke:redis:" + UUID.randomUUID();
        String expected = "hello-redis";

        try {
            redis.opsForValue().set(
                    key, expected, Duration.ofSeconds(30));
            String actual = redis.opsForValue().get(key);

            return expected.equals(actual);
        } finally {
            // If delete fails, Redis will auto-expire the key via TTL.
            redis.delete(key);
        }
    }
}
~~~

Calling **checkWriteRead()** from a controlled lab or test harness returns `true` if the round-trip passes, `false` if the value mismatches or is missing, and can throw **DataAccessException** or related exceptions if connecting or running commands fails. **Never expose this method as an unprotected public endpoint**, because each request triggers writes to Redis.

This short version highlights the core idea. Its **finally** block is minimal, so if cleanup throws an exception it could alter the outcome or mask an earlier failure; the `ApplicationRunner` version in Section 5 isolates cleanup errors to avoid that.

## 9. Verifying with `redis-cli`: Cross-Checking from the Redis Server Side

To observe server behavior independently from Spring, run manual commands on a test key:

~~~bash
docker exec redis-spring-demo redis-cli SET smoke:manual hello EX 60
docker exec redis-spring-demo redis-cli GET smoke:manual
docker exec redis-spring-demo redis-cli TTL smoke:manual
docker exec redis-spring-demo redis-cli DEL smoke:manual
~~~

Typical output:

~~~text
OK
"hello"
(integer) 58
(integer) 1
~~~

The TTL value is illustrative since it counts down over time; you may see a different number. **DEL** returns `1` if it deleted an existing key, or `0` if the key did not exist at deletion time.

This tests Redis through **redis-cli**. If it succeeds while Spring Boot fails, focus on the Redis address as seen from the application, environment variables, authentication/TLS, Redis user permissions, networking between the two environments, and Spring's connection factory settings.

Conversely, if both `redis-cli` and the application fail to connect from the same network location, check Redis Server and networking first.

Note that the `ApplicationRunner` code uses a random key and deletes it immediately after a successful read; therefore you normally **cannot catch that key in `redis-cli` after the success log appears**. That is expected smoke-test behavior, not evidence that `SET` failed.

## 10. Automating as an Integration Test

Beyond startup checks, you can write an **integration test** to detect connectivity issues in test environments. The code below assumes a test Redis Server is running, the test profile points to it, and the project includes **spring-boot-starter-test**:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

JUnit 5 example:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;

@SpringBootTest
class RedisWriteReadIntegrationTest {

    @Autowired
    private StringRedisTemplate redis;

    @Test
    void shouldWriteAndReadTheSameValue() {
        String key = "test:redis:" + UUID.randomUUID();
        String expected = "round-trip-ok";

        try {
            redis.opsForValue().set(
                    key, expected, Duration.ofSeconds(60));

            String actual = redis.opsForValue().get(key);

            assertEquals(expected, actual);
        } finally {
            redis.delete(key);
        }
    }
}
~~~

This test talks to a **real Redis instance** and is not a mocked unit test. It fails if no suitable Redis endpoint is available. To run reliably in CI, provide a dedicated test Redis (such as a test container), configure test host/port settings, and never rely on production Redis or shared user data.

Comparison of the approaches:

| Check Method | When It Runs | Outcome |
|---|---|---|
| **Flagged ApplicationRunner** | At app startup in selected environments | Success log or exception failing startup |
| **JUnit integration test** | During test suite execution | Assertion pass/fail in test results |
| **`redis-cli SET/GET`** | When run manually in CLI | Proves CLI reaches endpoint; may not reflect Spring client config |

Choose one or combine them per your development workflow. You do not need to run all three on every application request.

## 11. Diagnosing Errors by Symptom

### 11.1. Connection Refused or Unable to Connect

Typical log entries include **RedisConnectionFailureException**, **Connection refused**, **Unable to connect**, or similar exceptions.

Check in order:

1. Is Redis Server running? Does **docker ps** show the container?
2. Is Redis listening on the expected host/port and port mapping?
3. Does the app run on the host or inside a container? Where does `localhost` resolve?
4. Are DNS, firewalls, Docker networks, or security groups blocking the path?
5. Is the timeout value reasonable for the environment?

In Docker Compose, if Spring Boot and Redis are services on the same network, set **REDIS_HOST=redis** (assuming the Redis service is named `redis`), not `localhost` inside the Spring Boot container.

### 11.2. Redis Requires Authentication or TLS

If logs show **NOAUTH**, **WRONGPASS**, or TLS handshake errors, check connection settings and permissions:

- Does Redis ACL require both username and password?
- Did Spring Boot receive the right environment variables or secrets?
- Does the server require TLS while the client connects over plaintext TCP, or vice versa?
- Are you using the provider's exact endpoint and port for that connection mode?

For restricted Redis users, ensure required commands like **SET** and **GET** are allowed in the smoke test namespace. **DEL** is only for cleanup and can be handled accordingly if ACLs forbid it; the TTL still limits key lifetime.

### 11.3. `PONG` Works but `SET` Fails

`PING` and write commands have different requirements. Possible causes include:

- The Redis user is allowed to `PING` but denied `SET` or denied access to the key pattern.
- The app is connected to a read-only Redis replica or non-writable endpoint.
- Redis Server is in an operational state rejecting writes.
- `PING` was sent via **`redis-cli` with different settings**, while the app uses another host, account, or TLS configuration.

Therefore, `PONG` must never substitute for a write–read verification.

### 11.4. `SET` Throws No Error, Yet `GET` Returns `null`

Things to investigate:

- The key expired before `GET` ran or was deleted by another process.
- The key was evicted due to memory policy and resource pressure.
- The two commands did not hit the same endpoint, database, or namespace as assumed.
- Different key serializers/encodings were used across calls.
- The app reads from a replica before replication caught up as expected by the architecture.

In the **StringRedisTemplate** example using the same bean, key, and an immediate `GET` after `SET`, this symptom warrants investigation. A short TTL cleans up test keys, though very slow environments may require a longer TTL.

### 11.5. `GET` Returns Unexpected Data

**StringRedisTemplate** uses string serializers for keys and values. If another service writes to the same key using a `RedisTemplate` with a different serializer, read data can look garbled or fail string decoding.

For a write–read smoke test, use **one `StringRedisTemplate` for both SET and GET** to minimize variables. For real application data, services must standardize key/value formats and serialization policies.

### 11.6. `StringRedisTemplate` Bean Not Found

If Spring fails to inject `StringRedisTemplate`, check:

- Is **spring-boot-starter-data-redis** on the classpath of the runnable module?
- Was Spring Boot auto-configuration excluded or customized?
- Does a valid connection factory bean exist?
- Is the injecting class inside the application context and managed by Spring?

This is a Spring bean/configuration startup error, distinct from having a template that fails to connect to Redis Server.

### 11.7. Test Passes While Connected to the Wrong Redis

A **different** Redis endpoint can also answer SET/GET. A passing check only confirms access to the configured endpoint; it does not verify the identity of the target environment.

Before running in shared environments, verify host values, active profiles, secrets, Redis database/namespace, and network mappings so you never accidentally write to production Redis.

## 12. Technical Distinctions to Keep Clear

### 12.1. Real Connections Often Happen When a Command Runs

In many Spring Boot configurations, the app creates `RedisTemplate` and `RedisConnectionFactory` beans successfully even if Redis Server is not ready yet. Drivers may open connections lazily on demand, or connections may drop after startup.

Thus, **application context startup succeeding does not equate to verified SET/GET**. The smoke test intentionally executes commands to confirm a working path.

### 12.2. Redis Connection and Redis Data Are Separate Issues

Factories and drivers handle communication; Redis Server stores data. When reading incorrect data, check:

- Did the client hit the intended Redis endpoint?
- Was the key encoded properly and written to the expected database/namespace?
- Did TTL, eviction, deletion, or another writer affect the key?

Changing Redis drivers or raising connection timeouts will not fix key/value logic bugs.

### 12.3. Never Use Real Production Keys for Testing

Avoid keys like **user:1**, **session:current**, or **cart:123** in smoke tests. Those may be live business keys where overwrites cause unintended impact.

A dedicated prefix plus UUID and TTL keeps checks isolated even when multiple people run tests concurrently. Still, in production, always review ACLs, prefixes, and traffic before enabling test writes.

### 12.4. One-Time Startup Check vs. Continuous Monitoring

A startup smoke test answers: **"Can the application write and read Redis right now?"**

It does not continuously track failures that emerge later while the app runs. For ongoing visibility, use health/readiness checks, metrics, logs, and alerts. `PING`-style health checks are usually lighter than periodic SET/GET writes; continuous synthetic writes must be designed carefully to avoid unnecessary load and key churn.

### 12.5. Throwing an Exception vs. Returning `false`

Consider the check logic:

~~~java
String actual = redis.opsForValue().get(key);
return expected.equals(actual);
~~~

- **true**: `GET` returned the exact expected value.
- **false**: `GET` returned `null` or a different string without throwing an error.
- **exception**: connecting, writing, or reading failed abnormally.

In a required gating smoke test, both `false` and exceptions should count as **failures**; never swallow exceptions to return `true` or log "Redis connected" without verifying the read result.

## 13. Extended Practice Exercises

Once SET/GET succeeds, try a few controlled variations:

### Exercise A — Inspecting Remaining Expiration Time

Right after `SET` with a 60-second TTL, query Redis for the remaining time:

~~~java
Long remainingSeconds = redis.getExpire(key);
System.out.println("Remaining TTL (seconds): " + remainingSeconds);
~~~

The result is typically a positive integer close to 60. TTL counts down over time; depending on the command and key state, special negative values indicate a missing key or no expiration. **Do not assert that TTL equals exactly 60** because time elapses between `SET` and the query.

### Exercise B — Testing Intentional Connection Failure

In an isolated test environment, change host/port to an address with no Redis Server and enable the smoke test. Observe the Spring Data Redis exception and distinguish it from data-type errors. Then restore the valid configuration.

The goal is recognizing connection exceptions from the app; never shut down a shared Redis instance just to test this.

### Exercise C — Testing Namespaces

Replace **smoke:redis:** with an environment-specific prefix such as **dev:inventory:smoke:** and repeat the test. When multiple applications share a Redis Server, consistent key conventions simplify diagnosis and prevent collisions.

### Exercise D — Comparing `PING` and `SET`/`GET`

Send `PING` via `redis-cli` before starting the app. Then enable Spring's smoke test and observe both outcomes. Ask yourself: if `PONG` succeeds yet the app cannot `SET`, where might the problem lie?

## 14. Review Questions

**1. Why is seeing Spring Boot start up insufficient to conclude Redis connectivity is healthy?**

Because Redis beans can be created without executing any network commands yet. SET/GET from the app proves the access path for those operations at test time.

**2. Why use `StringRedisTemplate` for the first test?**

Because it works with string keys/values via a simple API, consistent serializers, and Spring-managed connections. Results are easy to reason about and inspect with `redis-cli`.

**3. If `GET` returns `null`, should you log success?**

No. If `expected` is a specific string and `actual` is `null`, the check failed, even though `GET` threw no exception.

**4. Why use both a UUID and a TTL?**

The UUID prevents key collisions across runs. The TTL bounds the test key's lifetime if cleanup code fails to run.

**5. If `PING` inside the Redis container succeeds but `SET`/`GET` in Spring fails, where should you look?**

Check host/port from the app's vantage point, Docker networks, ACLs, authentication, TLS, drivers, and Spring configuration. `PING` inside the container only shows the local server responds there.

**6. Does a successful write–read check guarantee Redis will not lose data after a restart?**

No. Persistence and recovery depend on RDB/AOF settings, replication, topology, and operational procedures—well beyond a basic SET/GET check.

**7. Should the `ApplicationRunner` check run on every production startup?**

Only if explicitly decided as a system requirement. The example defaults the flag to off to avoid unintended write commands and startup failures.

## Key Takeaways

~~~text
1. Redis Server is ready and the app is properly configured
                       |
                       v
2. StringRedisTemplate SET random key + TTL
                       |
                       v
3. StringRedisTemplate GET same key
                       |
                       v
4. Compare actual with expected
       |                         |
       | equal                   | different / null / exception
       v                         v
    SUCCESS                    FAILED
       |                         |
       '-----------+-------------'
                   |
                   v
5. Clean up key when possible; TTL ensures the test key does not persist forever
~~~

**Write–read verification confirms Redis connectivity at the application level**, not just the network level. An example using **StringRedisTemplate**, a dedicated key, **SET with TTL**, **GET value comparison**, and **safe cleanup** provides a solid baseline before building more complex Spring Data Redis features.
