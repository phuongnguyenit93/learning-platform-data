# Evaluating the Cost of Password Hashing, JWT Verification, and Introspection in Spring Security WebFlux

> **Learning path:** Spring Security - reactive → Observability and performance. The goal is to accurately measure the cost of three common authentication mechanisms, determine how they affect latency and throughput in a WebFlux application, and optimize in a controlled manner while preserving security properties.

## 1. Three Mechanisms, Three Cost Profiles

In a system using an OAuth2 Resource Server or password login, you cannot use a single “authentication time” figure to compare every request: execution mechanics, frequency, and where resources are consumed all differ.

| Mechanism | When Does It Run? | Dominant Cost | Potential I/O Component | Non-Negotiable Security Boundary |
| --- | --- | --- | --- | --- |
| Password hashing/verification with BCrypt, Argon2id, PBKDF2 | Typically on login, signup, password change; **no** need to re-run on every request using an access token | CPU; Argon2 also carries significant memory cost; worker/scheduler queue | Loading user record from DB | Never lower cost to weak levels just to hit RPS; never run hashing on the event loop |
| JWT access token (JWS) | Typically on every authenticated request, unless a result-reuse layer exists | Parsing/checking claims, verifying RSA/ECDSA/allowed-algorithm signatures; small CPU cost per call but significant at high RPS | Fetching JWKS on startup, cache miss, or key rotation | Never skip signature/issuer/audience/expiration checks; never trust token-chosen algorithms |
| Opaque token introspection (RFC 7662) | Resource Server asks Authorization Server whether token is still active and its authorities | HTTP/TLS, network, connection pool, IdP latency and capacity | **Normally every introspect is an HTTP call**, unless caching/other policy is configured | Never turn IdP errors into “allow”; bound caching to token revocation requirements |

**Never conclude unconditionally that “JWT is always faster than introspection”:** JWT typically avoids a network round-trip per request once JWKS is cached, but the comparison depends on implementation, token format, key type, algorithm, claim complexity, network, caching, and revocation policy. JWT does not inherently support immediate revocation; introspection usually reflects fresher token status at query time at the expense of network dependency.

A single request may involve multiple costs:

~~~text
Client → Netty/WebFlux
       → SecurityWebFilterChain
         ├─ Bearer JWT: parse → read cached key / fetch JWKS → verify signature
         │              → validate issuer, audience, exp, nbf → SecurityContext
         ├─ Opaque token: HTTP introspection → active + authorities → SecurityContext
         └─ Username/password login: lookup user → passwordEncoder.matches(...)
                                            → create session/token
       → Controller → Service → R2DBC/WebClient → Response
~~~

JWT and opaque token in the diagram are **alternative access-token authentication paths by configuration**, not both run by default on a single request. Password hashing usually belongs to a separate login flow. Distinguish measuring **component cost** from the **end-to-end latency** perceived by users.

## 2. Defining Metrics and Designing Measurements

### 2.1 Mandatory Metrics

1. **Latency:** p50, p95, p99 (ms) per request and per operation; separate success/failure, cold/warm, and timeouts.
2. **Throughput:** requests/s (RPS), logins/s, JWT verifications/s, introspections/s at steady load; record concurrency and virtual client count alongside.
3. **Resources:** CPU % and CPU-time, heap, off-heap/direct memory, GC pauses, allocations, thread count, and queue/rejections on the password-hashing scheduler.
4. **Network/IdP:** connection reuse, pending connections, DNS/TLS handshakes, server response time, timeouts, HTTP 429/5xx, key/JWKS cache hit/miss rates.
5. **Reactive health:** whether Netty event loops are blocked, worker wait time, pending requests, timeout/cancellation errors; check thread dumps/JFR/BlockHound in test environments.
6. **Correctness:** invalid signatures, wrong issuer/audience, expired tokens, wrong passwords, and `active=false` introspection results must be rejected per policy even under load.

**Latency definition:** includes queueing time when measured from HTTP request to response. Measuring only “hash function execution time” might show 80 ms while HTTP p99 climbs to several seconds due to queueing. Averages hide latency tails. Layer p95s **cannot be summed directly** to infer total request p95; you must measure end-to-end.

### 2.2 Three Scenario Groups to Separate

- **Baseline:** same machine/JDK version, same key size/hash cost, zero concurrent requests, proper warm-up; used to understand single-operation duration.
- **Steady load:** step up load incrementally, holding long enough for CPU, pools, and queues to stabilize, observing where p95/p99 inflect sharply or timeouts begin.
- **Stress/failure:** slow/429/5xx IdP, JWKS cache miss, key rotation, saturated hash scheduler, exhausted connection pool, high rate of invalid tokens, login spikes; verify fail-closed behavior and recovery.

Record the JDK, Spring Security version, CPU/cores and container limits, memory, algorithm/hash cost, RSA/ECDSA key length, network path to IdP, pool settings, timeouts, valid/invalid token ratio, token size, caching, and request distribution. Comparisons must use identical test data. Never use real tokens or real passwords in benchmarks.

### 2.3 A Formula for Explaining Queueing

In steady state, Little’s law gives the approximation **L = λ × W** (work in the system ≈ throughput × time spent in the system). For example, if introspection averages 0.08 seconds and there are 250 requests/s, an average of about **20 concurrent calls** are in flight awaiting completion, assuming each request requires one introspection and ignoring other stages. If the system's concurrency limit is lower than demand or the network/IdP slows down further, requests will queue up. This number is for forming measurement hypotheses, not a default pool size to apply blindly.

## 3. Password Hashing: Intentionally Resource-Intensive, But Must Not Stall the Event Loop

BCrypt, Argon2id, and PBKDF2 are password hashing/KDF algorithms with **cost parameters**; their purpose is to make brute-force password guessing expensive. BCrypt has a work factor; Argon2id has memory/time/parallelism; PBKDF2 has an iteration count. Their parameters do not share units and cannot be compared by a raw number like “cost 12” or “100000 iterations”. Choose the algorithm and parameters according to current security policy, measure on production-like hardware, and plan cost increases as hardware evolves.

Measure both **encode** (registration/password change) and **matches** (login). Most login traffic exercises `matches`; DB user lookup must be measured separately to distinguish hashing CPU from I/O. For non-existent users, a dummy hash at the same cost can reduce timing discrepancies to resist account enumeration, alongside rate limiting against abuse. Never log plaintext passwords, and never put passwords/hashes into metric tags.

### 3.1 Correct Handling Pattern in WebFlux

~~~java
package example.security;

import jakarta.annotation.PreDestroy;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

@Configuration
class PasswordConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        // Value 12 is only a reference setting; must be benchmarked and reviewed against policy.
        return new BCryptPasswordEncoder(12);
    }
}

@Service
public class ReactivePasswordVerifier {
    private final PasswordEncoder encoder;
    private final Scheduler worker =
            Schedulers.newBoundedElastic(8, 200, "password-hash");

    public ReactivePasswordVerifier(PasswordEncoder encoder) {
        this.encoder = encoder;
    }

    public Mono<Boolean> matches(String rawPassword, String storedHash) {
        return Mono.fromCallable(() -> encoder.matches(rawPassword, storedHash))
                .subscribeOn(worker);
    }

    @PreDestroy
    public void close() {
        worker.dispose();
    }
}
~~~

Here **Mono.fromCallable** defers hash computation until subscription; **subscribeOn(worker)** moves synchronous CPU-bound work off the event loop. A bounded scheduler caps workers and queued tasks, yet **does not replace ingress rate limits/concurrency limits**. When the queue fills or rejects tasks, the system must return controlled errors/throttling; never move hashing back onto Netty threads. A dedicated scheduler helps separate hash backlogs from other blocking work; the 8/200 settings are illustrative only and must be sized from CPU/memory budgets and benchmarks.

**Wrong:**

~~~java
// Anti-pattern: matches() executes synchronously directly in the reactive processing path.
// Do not copy into production handlers.
public Mono<Boolean> unsafe(String raw, String hash, PasswordEncoder encoder) {
    return Mono.just(encoder.matches(raw, hash));
}
~~~

**Also wrong:** manually calling **subscribe()** in a handler and returning a response before hashing completes; calling **block()** on the event loop; running enough concurrent Argon2 instances to exhaust memory; or lowering the work factor when more throughput is needed without weighing the security consequences.

### 3.2 Measuring and Interpreting

Run tests with at least two costs configured for the test environment, such as BCrypt cost 10 and cost 12, on target hardware; use random fixture passwords and salts, ensuring both hashes correspond to the stored hashes generated. Illustrative results may show higher cost sharply increases CPU time; **do not hardcode fixed millisecond expectations** as CPU, JVM warm-up, container limits, and background load vary. Beyond `matches` p95, measure **logins/s, CPU%, queue wait, rejections, and heap/RSS**. For Argon2id, measure RSS/direct/native memory under concurrent load; heap usage alone does not reflect total memory pressure.

## 4. JWT Verification: Local CPU, Cold-Path JWKS Dependency

For signed JWT/JWS, the Resource Server must decode structures within reasonable bounds, select a key from a trusted key set, verify the signature with an allowed algorithm, and validate issuer, audience, `exp`, `nbf`, and application claims/policies. Merely Base64-decoding the payload or reading claims is **insufficient to validate a token**. A token with a valid signature can still be invalid for this API due to wrong issuer/audience, expiration, or missing scope.

Separate measurements into:

1. **Warm verification:** JWK/key already cached, same algorithm, signature verification + claim validation.
2. **Cold start/cache miss:** discovery/JWKS retrieval, DNS/TLS/network, JWK parsing, and verification; can trigger latency spikes.
3. **Key rotation:** tokens with a new **kid** in the updated JWK set while old tokens remain valid during transition; ensure attackers sending random `kid` values cannot trigger unbounded fetches.
4. **Rejected tokens:** bad signature, disallowed `alg`, wrong issuer/audience, expired; note early-exit paths have different latencies so do not blindly mix failure rates.
5. **Token size and claim count:** also measure parse time, header size, and network overhead; more claims do not necessarily scale cryptographic work linearly.

Example **JWT Resource Server** configuration for Spring Boot WebFlux:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.test/realms/demo
~~~

In JWT mode, Spring Security validates tokens through an appropriate **ReactiveJwtDecoder**; `issuer-uri` may require metadata/discovery to locate JWKS. For **audience** requirements, configure your API's corresponding validator/policy; never assume a valid signature alone suffices. Example when explicitly constructing a decoder:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;

@Configuration
public class JwtDecoderConfig {
    private static final String ISSUER = "https://issuer.example.test/realms/demo";
    private static final String JWKS_URI = ISSUER + "/protocol/openid-connect/certs";
    private static final String EXPECTED_AUDIENCE = "notes-api";

    @Bean
    ReactiveJwtDecoder jwtDecoder() {
        NimbusReactiveJwtDecoder decoder =
                NimbusReactiveJwtDecoder.withJwkSetUri(JWKS_URI).build();

        OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience().contains(EXPECTED_AUDIENCE)
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                                new OAuth2Error("invalid_token",
                                        "Token has the wrong audience", null));

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER), audience));
        return decoder;
    }
}
~~~

This snippet illustrates an IdP-managed JWK endpoint and a fixed audience. URIs and allowed algorithms must match your real IdP; never fetch JWKs from a URL supplied inside the token itself. If **issuer-uri** auto-configuration is already in use, do not copy an extra custom decoder bean unnecessarily; a custom bean can replace auto-configuration. Enable HTTP security/`oauth2ResourceServer` as required by your application's security setup.

**Measurement note:** only reuse the same valid token in local-verification throughput tests; when testing JWKS caching or key rotation, control the key set and token key IDs explicitly. Never cache “verified JWT = allowed forever” indefinitely because `exp`, permission changes, blocklists, and revocation may require stricter lifetimes/policies.

## 5. Opaque-Token Introspection: Latency, Pools, and IdP Availability

The Resource Server sends the opaque token to the Authorization Server's introspection endpoint using server-to-server credentials per RFC 7662; results typically include **active**, `sub`, `scope`, `exp`, and permitted attributes. Introspection incurs network + TLS costs, IdP queueing, IdP database/cache work, and response parsing. Real measurements depend on regional proximity, connection reuse, DNS, pool sizing, and IdP policies.

Example **opaque-token Resource Server** configuration, independent of the JWT option above:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaque-token:
          introspection-uri: https://issuer.example.test/oauth2/introspect
          client-id: resource-server
          client-secret: YOUR_SECRET_FROM_SECRET_MANAGER
~~~

This structure is illustrative; inject secrets via a secret manager/environment variables and never commit secret strings in files. In WebFlux, use a properly configured **ReactiveOpaqueTokenIntrospector**/reactive HTTP client that reuses connection pools and sets appropriate connect/response/read timeouts; never call **RestTemplate**, blocking **HttpClient.send()**, or **block()** on Netty event loops.

### 5.1 Mandatory Scenarios to Test

| Scenario | Expected Observation |
| --- | --- |
| Token active=true and healthy IdP endpoint | API grants permissions per returned scopes/claims; record latency, RPS, and pool usage |
| Token active=false/expired | API denies access even though endpoint returned HTTP 200; never treat active=false as success |
| IdP slower than timeout | Resource Server **fails closed**, never lets request pass; record timeouts and appropriate HTTP error rates |
| IdP HTTP 429/5xx or network outage | Denies access; record dependency failures separately from invalid tokens where possible |
| No connection reuse | Latency spikes from TCP/TLS handshakes; measure pool hits and connect time |
| Introspection with cache TTL | Verify token expiration, stale permissions, and revocation; test revoking a token right after caching |
| Burst of many distinct tokens | Pending connections, IdP request rate, 429/rate-limit statuses, queueing/timeouts |

**Caching introspection is a security decision:** caching reduces round-trips but delays the effect of revocation/permission changes. TTL must be bounded, never exceed `exp`, and align with revocation SLAs; some policies forbid caching altogether. If cache keys derive from tokens, never log raw tokens; treat tokens as credentials. Use HTTPS and client authentication; never introspect by sending tokens to a client-supplied URL.

**Behavior on IdP errors:** returning 503 for dependency unavailability may fit some architectures, but never fall back to anonymous/allow-all or read permissions from an expired cache. If upstream errors are mapped to 401 by the framework, distinguish them via internal metrics/tracing so operations knows this is an IdP outage rather than bad user credentials.

## 6. Standalone Java 17 Exercise: Separating the Three Cost Profiles

This section is a **small benchmark runnable with JDK 17+**, requiring no real IdP or production services. It separates:

- **PBKDF2WithHmacSHA256**, which consumes CPU and represents the password-KDF family; this is **not** a numerical substitute for production BCrypt/Argon2.
- **SHA256withRSA (RS256) Signature.verify** with an in-memory key; measures only the cryptographic signature part of a JWS fixture, **without** validating JWT claims, `alg` allowlists, JWK trust, or expiration.
- **Mock HTTP introspection** on `127.0.0.1` with intentional server delay; illustrates network + remote response. The mock always returns `active=true` and does not implement OAuth2 introspection, TLS, or client authentication.

Save the file as **SecurityCostExercise.java** (matching the public class name):

~~~java
import com.sun.net.httpserver.HttpServer;

import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.security.Signature;
import java.time.Duration;
import java.util.Arrays;
import java.util.Base64;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class SecurityCostExercise {
    @FunctionalInterface
    interface CheckedOperation {
        void run() throws Exception;
    }

    static byte[] derive(char[] password, byte[] salt)
            throws GeneralSecurityException {
        PBEKeySpec spec = new PBEKeySpec(password, salt, 120_000, 256);
        try {
            return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
                    .generateSecret(spec).getEncoded();
        } finally {
            spec.clearPassword();
        }
    }

    static void sample(String label, int warmup, int count, CheckedOperation op)
            throws Exception {
        for (int i = 0; i < warmup; i++) {
            op.run();
        }
        long[] durationNs = new long[count];
        for (int i = 0; i < count; i++) {
            long start = System.nanoTime();
            op.run();
            durationNs[i] = System.nanoTime() - start;
        }
        Arrays.sort(durationNs);
        int p50 = (int) Math.ceil(count * 0.50) - 1;
        int p95 = (int) Math.ceil(count * 0.95) - 1;
        System.out.printf(Locale.ROOT,
                "%s: n=%d, p50=%.3f ms, p95=%.3f ms%n",
                label, count, durationNs[p50] / 1_000_000.0,
                durationNs[p95] / 1_000_000.0);
    }

    static String urlPart(String input) {
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(input.getBytes(StandardCharsets.UTF_8));
    }

    public static void main(String[] args) throws Exception {
        char[] password = "training-password-only".toCharArray();
        byte[] salt = new byte[16];
        new SecureRandom().nextBytes(salt);
        byte[] expected = derive(password, salt);

        sample("PBKDF2 verify", 3, 16, () -> {
            byte[] actual = derive(password, salt);
            if (!MessageDigest.isEqual(expected, actual)) {
                throw new IllegalStateException("Wrong password fixture");
            }
        });

        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair keys = generator.generateKeyPair();

        String jwsInput = urlPart("{\"alg\":\"RS256\",\"typ\":\"JWT\"}")
                + "."
                + urlPart("{\"iss\":\"https://issuer.test\",\"sub\":\"alice\","
                          + "\"aud\":\"notes-api\",\"exp\":1893456000}");
        byte[] message = jwsInput.getBytes(StandardCharsets.US_ASCII);
        Signature signer = Signature.getInstance("SHA256withRSA");
        signer.initSign(keys.getPrivate());
        signer.update(message);
        byte[] signed = signer.sign();

        sample("RS256 signature only", 100, 1000, () -> {
            Signature verifier = Signature.getInstance("SHA256withRSA");
            verifier.initVerify(keys.getPublic());
            verifier.update(message);
            if (!verifier.verify(signed)) {
                throw new IllegalStateException("Bad JWT signature fixture");
            }
        });

        ExecutorService pool = Executors.newFixedThreadPool(2);
        HttpServer mock = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        mock.setExecutor(pool);
        mock.createContext("/introspect", exchange -> {
            try {
                if (!"POST".equals(exchange.getRequestMethod())) {
                    exchange.sendResponseHeaders(405, -1);
                    return;
                }
                try {
                    Thread.sleep(25); // Only inside the mock server of the CLI demo.
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
                byte[] data = "{\"active\":true,\"sub\":\"alice\"}"
                        .getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set(
                        "Content-Type", "application/json");
                exchange.sendResponseHeaders(200, data.length);
                try (var output = exchange.getResponseBody()) {
                    output.write(data);
                }
            } finally {
                exchange.close();
            }
        });
        mock.start();

        try {
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(1))
                    .build();
            URI uri = URI.create(
                    "http://127.0.0.1:" + mock.getAddress().getPort()
                    + "/introspect");
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(2))
                    .header("Content-Type",
                            "application/x-www-form-urlencoded")
                    .POST(HttpRequest.BodyPublishers.ofString(
                            "token=demo-opaque-token"))
                    .build();

            sample("Mock introspection HTTP", 5, 25, () -> {
                // Blocking send() is only used in the CLI to create a baseline;
                // production WebFlux must use a reactive client.
                HttpResponse<String> response = client.send(
                        request, HttpResponse.BodyHandlers.ofString());
                if (response.statusCode() != 200
                        || !response.body().contains("\"active\":true")) {
                    throw new IllegalStateException(
                            "Mock introspection response invalid");
                }
            });
        } finally {
            mock.stop(0);
            pool.shutdownNow();
        }
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac --add-modules jdk.httpserver SecurityCostExercise.java
java --add-modules jdk.httpserver SecurityCostExercise
~~~

Output format (millisecond values **vary by machine and run**, so fake numbers are not given as measurements):

~~~text
PBKDF2 verify: n=16, p50=<measured ms>, p95=<measured ms>
RS256 signature only: n=1000, p50=<measured ms>, p95=<measured ms>
Mock introspection HTTP: n=25, p50=<measured ms>, p95=<measured ms>
~~~

With this fixture, warm JWT signature verification typically takes less time than the password KDF, while mock introspection is dominated by the 25ms sleep plus local networking. This is a **qualitative observation that must be verified on your machine**, not a guarantee of ranking across all algorithms and environments. Small `System.nanoTime` loops suit only lab/initial observations; 16 or 25 samples are insufficient to estimate reliable production p99, and sequential runs do not reveal saturation under high concurrency.

### 6.1 From lab to trustworthy benchmarks

To benchmark primitives, use **JMH** with warm-up/forks, `Blackhole` or result consumption, and controlled inputs; avoid JIT dead-code elimination and separate key/hash setup from the measured operation. To benchmark WebFlux end-to-end, use load generators like k6/Gatling/wrk in an isolated environment with token fixtures. Never use JMH as a substitute for network and connection-pool testing; never make password-policy decisions from a single `System.nanoTime` run.

## 7. Placing Metrics at the Right Points Without Distorting Data

Micrometer can measure each operation separately via **Timer.Sample** from subscription to terminal signal; in WebFlux you must measure the reactive operation and avoid wrapping a `Mono` already subscribed elsewhere.

Example helper (for use in a project with Micrometer and Spring Boot Actuator/Reactor):

~~~java
package example.security;

import java.util.function.Supplier;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import reactor.core.publisher.Mono;

public final class AuthenticationTimers {
    private final MeterRegistry registry;

    public AuthenticationTimers(MeterRegistry registry) {
        this.registry = registry;
    }

    public <T> Mono<T> measure(
            String operation, Supplier<Mono<T>> work) {
        return Mono.defer(() -> {
            Timer.Sample sample = Timer.start(registry);
            return Mono.defer(work).doFinally(signal ->
                    sample.stop(Timer.builder("security.auth.operation")
                            .tag("operation", operation)
                            .tag("signal", signal.name())
                            .register(registry)));
        });
    }
}
~~~

How to call at an existing business/security point (illustrative, not assembled into a standalone controller):

~~~java
// Each operation is executed only once in the real pipeline.
Mono<Boolean> matching = timers.measure(
        "password_matches",
        () -> passwordVerifier.matches(rawPassword, storedHash));

Mono<org.springframework.security.oauth2.jwt.Jwt> validatedJwt =
        timers.measure("jwt_decode", () -> jwtDecoder.decode(bearerToken));

Mono<org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal> principal =
        timers.measure("introspection",
                () -> introspector.introspect(opaqueToken));
~~~

The variables **timers, passwordVerifier, jwtDecoder, introspector, rawPassword, storedHash, bearerToken, opaqueToken** are dependencies/inputs already present in the application; the second snippet only illustrates wrapping pipelines, not a standalone runnable program. Never decode/introspect **an extra time** just to record metrics, as that increases cost and can alter security semantics. Operation names come from a **small constant set**, and signals have finite values. Avoid attaching JWTs/raw tokens, usernames, `userId`, `tenantId`, URLs with IDs, or free-form exception messages as labels: that creates high cardinality and credential exposure risk. Trace spans may record normalized issuer/provider names, never tokens.

Add metrics at the **HTTP layer** and at **outbound IdP calls** to distinguish pool wait time, network latency, and post-authentication work. For password hashing, a `Timer` purely around `matches` misses queue wait if it starts after a worker picks up the task; wrapping the publisher as above starts at subscription, making it useful for observing queue delays. JFR/thread dumps/profilers can supplement this to confirm CPU hotspots or blocked event loops.

## 8. Fair Comparative Load-Testing Plan

Use the same machine/JVM mode, fixture data, and load profile; run separately:

**Test A – Password login.** Seed demo accounts with pre-generated hashes at each cost. Test 1, 2, 4, 8, 16 concurrent logins (adjust to available resources), measuring logins/s, p95/p99, CPU/RSS, and active/queued/rejected workers. Never run password `encode` on every request when the real flow only runs `matches`; never conflate DB lookup with hashing without measuring them separately. Test wrong logins and non-existent accounts to evaluate password enumeration, cost, and rate limiting.

**Test B – JWT resource server.** Send the lightest auth-protected API request with signed JWTs matching valid issuer/audience. Measure warm RS256 verification across RPS levels, then cold start/JWKS miss/key rotation and invalid-signature/expired/wrong-audience JWTs. To isolate security overhead, compare the same test route without heavy backend DB work, but **never deploy a security bypass to production**. Keep payloads/responses identical and inspect CPU/Netty metrics.

**Test C – Opaque introspection.** Use a test IdP or HTTP mock configured with 10/50/100ms latency, timeouts, and 429/5xx responses; measure RPS, timeouts, connection pool stats, end-to-end p95/p99, IdP requests/s, and resource server CPU. Toggle cache off/on only when policy allows, then revoke a cached token and measure revocation propagation lag. Outage simulations must verify **no unauthorized access is granted**.

**Test D – Mixed workload.** Combine realistic ratios (e.g., 95% JWT, 5% login; ratios are fixtures only, not a universal rule) plus login bursts. Because hashing is CPU-heavy and JWT/IdP paths contend for resources, observe how login spikes affect normal request p99. In multi-node setups, measure both per-instance behavior and shared IdP limits.

Collect results into a table with consistent units:

| Test/Run | Mode/Params | RPS | Concurrent | HTTP p50/p95/p99 ms | Op p95 ms | CPU / RSS | Failure / Timeout | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A1 | Chosen BCrypt cost | measure | measure | measure | hash matches | measure | measure | Scheduler queue |
| B1 | JWT RS256, warm JWKS | measure | measure | measure | jwt decode | measure | measure | Key cache |
| B2 | JWT RS256, cold/rotation | measure | measure | measure | jwt decode | measure | measure | JWKS fetch |
| C1 | Introspection cache off | measure | measure | measure | introspection | measure | measure | IdP latency/pool |
| C2 | Introspection controlled TTL cache | measure | measure | measure | introspection | measure | measure | Revoke freshness |

The “measure” cells are a **result-recording template**, not measured numbers. Conclude a bottleneck only with evidence from CPU profiles, latency breakdowns, or queue/pool correlation; a high p95 alone does not immediately prove hashing or JWT is the culprit.

## 9. Common Measurement and Operational Mistakes

- **Comparing mismatched workloads:** comparing “one `matches` call” against “one end-to-end HTTP request”, or against a mock introspection without TLS, and concluding one mechanism is universally superior.
- **Skipping warm-up:** mixing JIT/JWK fetch/pool initialization into steady-state numbers; conversely, testing only warm cases misses key-rotation and startup risks.
- **Measuring blocking on the event loop:** Reactor wrappers do not make blocking computations non-blocking; you must use proper boundaries and monitoring.
- **Ignoring queues:** low CPU operation p95 alongside high HTTP latency caused by `boundedElastic`/connection-pool waiting.
- **Putting all costs on one Scheduler:** login spikes starving workers needed by other blocking I/O; apply capacity planning, rate limiting, and resource isolation when evidenced.
- **Optimizing by dropping validation:** skipping `aud`/`exp`/`issuer`/`alg` checks or accepting access on introspection timeout is a security vulnerability, even if benchmarks look faster.
- **Uncontrolled caching:** caching JWT JWKS keys is completely different from caching access permissions or `active` introspection results; permission TTL directly impacts revocation.
- **Reporting only averages:** hides p99 and tail latency during slow I/O, GC pauses, or queue spikes.
- **Ignoring error mixes and test inputs:** invalid-token ratios, short-circuiting, and bad credentials change measurements; you cannot compare two configs under skewed workloads.
- **Testing against a production IdP:** load tests can trigger rate limits or impact real users; use sandboxes and approved limits.

## 10. Knowledge Lesson Completion Checklist

This lesson is complete when learners can explain: (1) CPU/memory cost differences between password KDFs, JWT crypto/CPU, and introspection network/IdP calls; (2) why password `matches` must run off the Netty event loop; (3) how cold/warm JWKS and key rotation affect JWT measurements; (4) how to test introspection timeouts/fail-closed behavior and cache impact on revocation; (5) why p50/p95/p99, throughput, concurrency, and queue/pool/CPU metrics matter more than a single average; (6) how to run the JDK 17 lab and state the limits of synthetic benchmarks; (7) how to wrap operations with Micrometer without putting credentials into metrics; (8) a load-testing methodology with scenarios, parameters, security correctness, and evidence before optimizing.

**Application principle:** preserve authentication policies and password safety, isolate measurements, confirm the true bottleneck source, and only then optimize queues, threading, connection reuse, permitted caching, or infrastructure capacity. Every performance change must be re-tested for security behavior, token lifetimes, and permission revocation.