# Testing Token Expiration, Timeouts, Cancellation, and Committed Responses in Spring Security WebFlux

## 1. Goal and boundaries

This lesson focuses on four categories of edge cases often overlooked in **reactive** security testing: expired tokens, operations exceeding allowed time, subscriber cancellation, and errors occurring after an HTTP response has been committed. The goal is to prove **the system emits the right signals, returns the proper response while still possible, cleans up resources, and never masks security errors**.

Examples assume Java 17+, Spring Boot 3.3.x, Spring Security 6.x, Spring WebFlux, Reactor, and JUnit 5. Distinguish the test layers:

- **Token/validator:** verify signatures, `exp`, `nbf`, issuer, audience, clock skew, and error codes on the real decoder.
- **HTTP security chain:** test the outcome of `SecurityWebFilterChain` when `ReactiveJwtDecoder` returns a valid `Jwt` or emits an authentication error.
- **Reactive signals:** test `onNext`, `onError`, `onComplete`, `cancel`, and the effect of `timeout`.
- **HTTP response:** test commit timing and the inability to modify status/headers after commit.

Do not equate `WebTestClient` with `StepVerifier`: the former observes HTTP protocol behavior, while the latter observes Publisher signals. In WebFlux, `cancel` is a downstream-to-upstream signal; it is not an HTTP response with a fixed status code.

## 2. Processing flow model and expectations

Conceptually, a request is processed as follows:

~~~text
HTTP request
  -> WebFilter / SecurityWebFilterChain
  -> authenticate Bearer token (ReactiveJwtDecoder)
  -> authorize
  -> handler creates Mono/Flux
  -> write status, headers, and body
  -> response committed -> complete / error / client disconnect
~~~

At each point, ask: **has the token been verified yet, has the publisher been subscribed to yet, which stage is the timer measuring, has the response been committed yet, and who emitted the cancel signal?**

| Scenario | Decisive observation | What must be proven |
| --- | --- | --- |
| Token expired at authentication | Decoder/validator rejects token | Typically HTTP 401 and `WWW-Authenticate: Bearer` challenge; protected endpoint body does not run |
| Token valid but lacks permission | Authenticated, authorization rejects | HTTP 403, clearly distinguished from 401 |
| Stage unfinished when wait expires | Publisher emits `TimeoutException`, or fallback branch | HTTP status per error policy if **not yet** committed; verify upstream timeout and cleanup |
| Subscriber cancels | `doOnCancel` or `doFinally(CANCEL)` | Downstream stops, subscription/resources released; do not expect an HTTP status from this signal |
| Error after first byte/flush written | `ServerHttpResponse.isCommitted() == true` | Cannot change status to 401/403/5xx; verify logging, cleanup, and safe connection termination |

**401, 403, 408, 503, and 504 are not interchangeable.** 401 means unauthenticated; 403 means insufficient permission after authentication. An application timeout may map to 503 or another code per API contract; 504 is typically returned by a gateway/proxy on upstream timeout, while 408 relates to request-receiving timeouts. Never assume every `TimeoutException` becomes 504.

## 3. Testing JWT expiration with controlled time

JWTs use `exp` (expiration time), usually represented as a NumericDate in Unix seconds. `nbf` is not-before time; `iat` is issued-at time and **does not by itself replace `exp` checks**. At the exact `exp` boundary, a token is considered expired by timestamp comparison, though many validators configure **clock skew** tolerance. Determine actual clock skew before writing boundary expectations.

Key matrix: valid token, `exp` past clock skew, `exp` near boundary, `nbf` in future, bad signature, wrong issuer/audience, missing bearer token, and valid user missing authority. Ensure signed JWTs with real claims actually pass through the decoder in crypto/claim test cases.

Two test levels must not be confused:

1. **Testing the real decoder:** create JWTs signed with a test-only key; configure the same issuer/audience, algorithm, and validators as production; use a fixed clock when supported by the validator/infrastructure; prove `exp` and `nbf` are genuinely rejected. Avoid `Thread.sleep` to wait for expiration. When testing near time boundaries, use injectable `Clock`/validator time or timestamps safely outside skew tolerance.
2. **Testing the HTTP chain:** stub `ReactiveJwtDecoder` to return an error to prove Spring Security translates authentication errors into 401 without running the handler. Stubbing here **does not prove** the real validator checks expiration properly.

The complete HTTP test example below belongs in a Spring Boot WebFlux app with WebFlux, Security, OAuth2 Resource Server, and test starters. With Spring Boot 3.3, `@MockBean` fits well; in newer versions use the supported mock annotation.

~~~java
package demo.security;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidationException;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import static org.mockito.Mockito.when;

@WebFluxTest(controllers = JwtExpiryHttpTest.SecretController.class)
@Import(JwtExpiryHttpTest.TestSecurity.class)
class JwtExpiryHttpTest {

    @Autowired
    WebTestClient client;

    @MockBean
    ReactiveJwtDecoder decoder;

    @Test
    void expiredJwtReturns401WithBearerChallenge() {
        when(decoder.decode("expired")).thenReturn(
            Mono.error(new JwtValidationException(
                "JWT expired",
                List.of(new OAuth2Error(
                    "invalid_token", "JWT expired", null))
            ))
        );

        client.get()
            .uri("/private")
            .headers(h -> h.setBearerAuth("expired"))
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().valueMatches(
                HttpHeaders.WWW_AUTHENTICATE, "Bearer.*");
    }

    @Test
    void acceptedJwtReachesProtectedHandler() {
        Jwt accepted = Jwt.withTokenValue("accepted")
            .header("alg", "HS256")
            .claim("sub", "alice")
            .issuedAt(Instant.parse("2026-01-01T00:00:00Z"))
            .expiresAt(Instant.parse("2099-01-01T00:00:00Z"))
            .build();
        when(decoder.decode("accepted")).thenReturn(Mono.just(accepted));

        client.get()
            .uri("/private")
            .headers(h -> h.setBearerAuth("accepted"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("protected");
    }

    @RestController
    static class SecretController {
        @GetMapping("/private")
        Mono<String> secret() {
            return Mono.just("protected");
        }
    }

    @Configuration
    @EnableWebFluxSecurity
    static class TestSecurity {
        @Bean
        SecurityWebFilterChain webFluxSecurity(ServerHttpSecurity http) {
            return http
                .authorizeExchange(ex -> ex
                    .pathMatchers("/private").authenticated()
                    .anyExchange().permitAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                    .jwt(Customizer.withDefaults()))
                .build();
        }
    }
}
~~~

In the first test, the decoder error signal causes the authentication middleware to return 401; the handler never gets a chance to produce protected data. The second test proves a **stub-allowed** JWT passes through the HTTP chain. It does not verify signatures or `exp` in a real decoder. You can add an `AtomicInteger` in the controller test to assert the handler is never called on bad tokens, without sharing mutable state across tests that causes order dependencies.

For authority-protected routes, add a case where the decoder accepts the JWT but scope/role is missing: `authenticated()` alone will not produce 403; configure `hasAuthority(...)` or real authorization rules before asserting 403. `SecurityMockServerConfigurers.mockJwt()` works well for testing authorization, though it also does not test JWT expiration or signatures.

## 4. Testing timeouts: start time, failing layer, and fallbacks

Three independent timeouts to distinguish:

- **Token verification:** fetching JWKS keys, opaque-token introspection, or calling a remote auth backend can be slow. Test timeouts and error mapping directly at the authentication adapter; never label every timeout as an expired token.
- **Reactive business processing:** `Mono.timeout`/`Flux.timeout` bounds stream duration; on timeout it cancels the upstream subscription and emits `TimeoutException`. Fallbacks via `onErrorResume` should be used only when business policy permits.
- **Client/gateway:** `WebTestClient.responseTimeout(...)` or a reverse proxy timing out is an observer/gateway limit; it does not prove the server handled a `TimeoutException` or cleaned up properly.

With `StepVerifier.withVirtualTime`, you must **build the Publisher inside the supplier** so Reactor's time schedulers are replaced by the virtual scheduler at assembly time. Tests run in milliseconds while simulating seconds or hours. Remember `timeout` governs the wait between signals per overload: `Mono.timeout(Duration)` bounds arrival of the first/terminal signal; `Flux.timeout(Duration)` also bounds gaps between `onNext` signals.

Runnable example for timeout and cancellation:

~~~java
package demo.security;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ReactiveSignalsTest {

    @Test
    void timeoutProducesExplicitFallback() {
        StepVerifier.withVirtualTime(() ->
                Mono.delay(Duration.ofSeconds(10))
                    .timeout(Duration.ofSeconds(3))
                    .onErrorResume(TimeoutException.class,
                        error -> Mono.just(-1L)))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(3))
            .expectNext(-1L)
            .verifyComplete();
    }

    @Test
    void cancellingSubscriberCancelsUpstream() {
        AtomicReference<SignalType> terminalSignal =
            new AtomicReference<>();

        StepVerifier.withVirtualTime(() ->
                Flux.interval(Duration.ofSeconds(1))
                    .doFinally(terminalSignal::set))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(2))
            .expectNext(0L, 1L)
            .thenCancel()
            .verify();

        assertEquals(SignalType.CANCEL, terminalSignal.get());
    }
}
~~~

In the timeout test, the source publisher would emit `0` after 10 virtual seconds, but timeout triggers after 3 virtual seconds so the fallback emits `-1` and `onComplete`. In the cancellation test, two values `0, 1` arrive after 1 and 2 virtual seconds; `thenCancel()` cancels the subscription and `doFinally` receives `CANCEL`. Also add a **no-fallback** test using `expectError(TimeoutException.class)` when the contract requires propagating the error.

When turning an error into an HTTP response, put `onErrorResume` or `onErrorMap` at a layer with an explicit handling policy, and assert the actual body/status via `WebTestClient`. Never use `onErrorReturn` to convert an authentication error into "success" data; doing so can expose endpoints meant to be denied.

## 5. Cancellation and resource cleanup

In Reactive Streams, `Subscription.cancel()` signals that downstream no longer wants data. Examples: client closes the connection mid-stream, `take(n)` receives enough elements, or `timeout` cancels a slow upstream. After cancellation, do not assume the client can receive a new error body. Subscription cancellation is also **not** an instant kill switch guaranteed to abort all non-Reactor I/O, especially blocking code or external service calls that ignore cancellation.

Checkpoints that matter in business logic:

1. Upstream publisher receives cancel: use `doOnCancel`, `doFinally(SignalType.CANCEL)`, or publishers with lifecycle hooks.
2. Resources are reclaimed: connections, files, locks, streams, background tasks. For reactive resources, implement cleanup via `usingWhen` or corresponding lifecycle APIs; distinguish cleanup on complete, error, and cancel.
3. No avoidable side effects are emitted after cancellation. For operations already dispatched to external systems, cancellation **does not mean rollback**; design idempotency/compensation if business rules require it.
4. Avoid `block()` and `Thread.sleep()` on the event loop: these block threads and prevent timeouts/cancellation from taking effect promptly.

For HTTP streaming/SSE, `WebTestClient` can obtain a `FluxExchangeResult`, subscribe partially, and dispose/cancel; however, when the network delivers connection close to the server depends on transport. Stable cleanup tests should assert at an instrumented Publisher or service, supplemented by HTTP integration tests verifying lifecycle on a real runtime. Never claim a code like "499" is a standard contract: it is a non-standard code used by certain proxies/logging layers.

## 6. Committed responses: why you cannot switch to 401/500?

In HTTP, once status/headers are sent (or the response is committed by writing), the server cannot go back and change the status mid-response. WebFlux exposes `ServerHttpResponse.isCommitted()`. With `writeWith` or `writeAndFlushWith`, commit can occur before the entire body finishes. `beforeCommit(...)` is a hook to configure headers/metadata **before** commit; it does not let you rewrite an already-sent response.

The small test below uses Spring WebFlux's mock response. It verifies that writing the body commits the response and `setStatusCode` is rejected afterwards.

~~~java
package demo.security;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.HttpStatus;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CommittedResponseTest {

    @Test
    void committedResponseCannotChangeStatus() {
        MockServerWebExchange exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/stream").build());
        ServerHttpResponse response = exchange.getResponse();

        response.setStatusCode(HttpStatus.OK);
        DataBuffer body = response.bufferFactory().wrap(
            "part-1".getBytes(StandardCharsets.UTF_8));

        StepVerifier.create(response.writeWith(Mono.just(body)))
            .verifyComplete();

        assertTrue(response.isCommitted());
        assertFalse(response.setStatusCode(HttpStatus.UNAUTHORIZED));
    }
}
~~~

`setStatusCode(...)` returning `false` proves **the status code cannot be changed once committed**; it does not mean the client's status turns into 401. In practice, errors after the first byte of an SSE/stream usually require telemetry recording, subscription cancellation, and closing or ending the stream per application protocol. Never assume `@ControllerAdvice` or `ServerAuthenticationEntryPoint` can always write a new error JSON after commit.

By design, all authentication/authorization required to grant data must finish **before sending the first byte**. If a long-lived stream requires continuous session/token validity checks, specify an explicit re-validation mechanism or connection duration limit; a JWT validated at connection start is not automatically re-checked by the decoder on every element.

## 7. Layered testing and regression matrix

| Case | Trigger setup | Required assertions |
| --- | --- | --- |
| Valid JWT accepted | Real decoder accepts signature and claims, or stub in HTTP test | HTTP 200 and expected body; clearly note which layer is tested |
| Expired JWT | `exp` beyond clock skew; real decoder or intentional `JwtValidationException` | HTTP 401, Bearer challenge, handler never runs |
| Not-yet-valid JWT | `nbf` past current time plus skew | Decoder rejects; not treated as missing authority |
| Authenticated but missing permission | Valid JWT, `hasAuthority` policy | HTTP 403 |
| Slow decoder/introspection | Slow upstream or Publisher with configured timeout | Policy timeout error; not confused with `exp`; upstream cancelled appropriately |
| Slow handler | `Mono.delay`/test Publisher with virtual time | `TimeoutException` or defined fallback; HTTP status per pre-commit mapper |
| Mid-stream cancel | Subscriber triggers `thenCancel` or disposes | `doFinally(CANCEL)`, cleanup, no extra side effects |
| Error after first chunk | Explicitly commit/flush then emit `onError` | `isCommitted()` true, no status/header change, no double body |
| Normal completion | Publisher `onComplete` | Cleanup not misrecorded as `CANCEL` |
| Race between timeout/cancel/complete | Deterministic scheduler control | Single terminal outcome per contract; cleanup runs once; no wall-clock millisecond assertions |

Depending on complexity, name tests to reflect scope accurately: `expiredJwtReturns401`, `timeoutCancelsUpstream`, `clientCancelClosesResource`, `committedResponseRejectsStatusChange`. For gateway/client timeouts, add dedicated tests in the real deployment layer rather than forcing mocked Reactor tests to verify proxy behavior.

## 8. Dependencies, running tests, and QA notes

In a Gradle Groovy project using Spring Boot, sample dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

`spring-boot-starter-test` includes JUnit Jupiter, Spring Test, Reactor Test, and Mockito in standard Boot setups. Examples live in package `demo.security` inside a configured Spring Boot application. Run `./gradlew test --tests 'demo.security.*'` if project task/module names and test configs permit; in multi-project builds, use the matching task path. The code blocks are **three separate test files** — do not merge three `package` declarations into one file.

During QA, verify:

- Never include real tokens/keys in logs, fixtures, or assertion messages; test keys are strictly for tests.
- `exp`, `nbf`, clock skew, and seconds/milliseconds units are clearly specified; avoid flaky wall-clock tests.
- HTTP tests with a stubbed decoder are clearly labeled as mapping tests, not reported as real signature/validator tests.
- `@WithMockUser`, `mockJwt()`, and mock authentication contexts are for authorization testing, not substitutes for decoder validation.
- Identify which layer emits `TimeoutException`, whether fallback is intentional, and whether the pipeline cancels upstream.
- Cancel, error, and complete paths all close resources appropriately; cleanup never runs twice causing duplicate side effects.
- Only assert error status/headers when the response is **uncommitted**; post-commit, assert commit state, telemetry, and lifecycle.
- Ensure every Publisher is subscribed in tests; never use `Thread.sleep` for behavior that virtual time can simulate.
- In real HTTP environments, add integration tests for streaming, proxy timeouts, and connection closure when those behaviors are product requirements.

**Core takeaway:** token expiration is an **authentication** decision; timeouts are **wait-duration** decisions; cancellation is a **subscription lifecycle** signal; committed responses are an **HTTP protocol boundary**. Separating these four mechanisms into independent tests and testing their intersections is what reveals reactive security bugs that happy-path tests miss.
