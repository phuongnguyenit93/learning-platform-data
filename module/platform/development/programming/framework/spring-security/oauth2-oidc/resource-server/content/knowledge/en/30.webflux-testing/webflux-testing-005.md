# StepVerifier for Reactive Validators, Converters, and Introspectors

## 1. Why Does Reactive Testing Require a Different Approach?

In Spring Security WebFlux, OAuth 2.0 Resource Server authentication typically returns a Publisher rather than an immediately available result when a method is called. A JWT decoder returns **Mono<Jwt>**, a JWT authentication converter returns **Mono<AbstractAuthenticationToken>**, and an opaque-token introspector returns **Mono<OAuth2AuthenticatedPrincipal>**.

This means calling a method does not necessarily execute the work. With Reactor, Publishers are typically lazy: work begins upon subscription. If a test merely calls the method and inspects the returned object, the test may not have actually run the authentication logic.

Reactor Test's **StepVerifier** lets you describe the expected sequence of signals: emitted items, errors, completion, backpressure, and cancellation. The test subscribes to the Publisher and verifies the actual signals in order.

In this lesson, we use StepVerifier to test the reactive boundaries of a Spring Security Resource Server:

- JWT decoders and validation results.
- Converters mapping a JWT into an Authentication.
- Opaque token introspectors calling an Authorization Server or token-state store.
- Additional asynchronous checks such as tenant membership or entitlements.
- Timeouts, upstream failures, empty publishers, and cancellation.
- Integrating the full security chain with WebTestClient.

There is an important distinction to keep clear: **Spring Security's OAuth2TokenValidator<Jwt> is a synchronous API**. The **validate(Jwt)** method returns **OAuth2TokenValidatorResult**, not a Mono. In a reactive Resource Server, validators are invoked by `ReactiveJwtDecoder` while producing **Mono<Jwt>**. Therefore, test validators directly for synchronous logic and use StepVerifier to test the reactive decoder/pipeline containing that validator. If you need to call an asynchronous service to check tenant or entitlement, place that step in the reactive authentication/authorization pipeline rather than putting blocking calls inside a synchronous validator.

### Learning Objectives

After this lesson, you will be able to:

1. Understand how StepVerifier subscribes to and verifies `Mono`/`Flux` signals.
2. Distinguish synchronous validators from `ReactiveJwtDecoder`.
3. Test valid JWTs, wrong audience, issuer, timestamps, and signatures.
4. Test synchronous converters wrapped by `ReactiveJwtAuthenticationConverterAdapter`.
5. Test genuinely asynchronous converters when looking up authorities.
6. Test `ReactiveOpaqueTokenIntrospector` for success, inactive tokens, and upstream errors.
7. Use virtual time to test timeouts, delays, and TTLs without real waiting.
8. Verify context, cancellation, and subscriptions.
9. Combine StepVerifier with WebTestClient to test the WebFlux security chain.
10. Avoid common mistakes such as calling `block()`, over-mocking, or writing tests that only inspect unsubscribed objects.

## 2. Preparing Dependencies and Test Fixtures

### 2.1. Dependencies

The application needs Spring Security Resource Server, Spring WebFlux, and Reactor Test. With Gradle, use Spring Boot's dependency management/BOM so Spring Security and Reactor versions stay compatible:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Even if the project already has the test starter, declare `reactor-test` explicitly when tests use StepVerifier, TestPublisher, or PublisherProbe. Do not pin a Reactor Test version different from the Reactor Core managed by the BOM.

### 2.2. Common Imports

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.time.Instant;
import java.util.List;
~~~

Spring Security tests also commonly import:

~~~java
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;

import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtAuthenticationConverterAdapter;

import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
~~~

Package names and some extension points may vary across Spring Security lines. Consult the Javadoc of the exact version resolved in your build.

### 2.3. Creating a JWT Object for Unit Tests

When only testing a validator predicate or converter, you do not need to sign a real token. You can build a `Jwt` object directly:

~~~java
static final String ISSUER = "https://id.example.test";
static final String AUDIENCE = "orders-api";

static Jwt validJwt() {
    Instant now = Instant.now();

    return Jwt.withTokenValue("test-access-token")
        .header("alg", "RS256")
        .issuer(ISSUER)
        .subject("user-417")
        .audience(List.of(AUDIENCE))
        .issuedAt(now.minusSeconds(10))
        .expiresAt(now.plusSeconds(300))
        .claim("scope", "orders.read")
        .build();
}
~~~

This is a fixture for claim-mapping and converter unit tests. It does not prove JWT signatures are verified. When testing signatures or the real decoder, generate a compact JWT using a test private key and configure the decoder with the matching public key.

---

## 3. How Does StepVerifier Verify Signals?

### 3.1. A Successful Mono

Simple example:

~~~java
@Test
void emitsOneValueAndCompletes() {
    Mono<String> result = Mono.just("orders-api");

    StepVerifier.create(result)
        .expectNext("orders-api")
        .verifyComplete();
}
~~~

**verifyComplete()** both declares the expected completion signal and subscribes to run the test. If the Publisher emits an error, emits the wrong value, or never completes, the test fails.

### 3.2. Checking Values with a Predicate

When you do not want to compare the entire object:

~~~java
StepVerifier.create(Mono.just(validJwt()))
    .assertNext(jwt -> {
        assertEquals("user-417", jwt.getSubject());
        assertTrue(jwt.getAudience().contains("orders-api"));
    })
    .verifyComplete();
~~~

**assertNext** fits when multiple assertions are needed. **expectNextMatches** fits short predicates:

~~~java
StepVerifier.create(Mono.just("orders.read"))
    .expectNextMatches(scope -> scope.startsWith("orders."))
    .verifyComplete();
~~~

### 3.3. Verifying Errors

A Publisher may terminate with an error:

~~~java
StepVerifier.create(Mono.error(
        new IllegalStateException("introspection unavailable")))
    .expectError(IllegalStateException.class)
    .verify();
~~~

When you need to inspect error details:

~~~java
StepVerifier.create(Mono.error(
        new IllegalArgumentException("invalid audience")))
    .expectErrorSatisfies(error -> {
        assertInstanceOf(IllegalArgumentException.class, error);
        assertEquals("invalid audience", error.getMessage());
    })
    .verify();
~~~

Do not just check that "an error occurred." Confirm the error type matches the contract of the layer under test. For example, a token with invalid claims is a token validation error; an Authorization Server timeout is an infrastructure error; missing scope after authentication is an authorization error.

### 3.4. Mono.empty Is Not the Same as Mono.error

Three distinct states:

| Publisher | Meaning | Test |
|---|---|---|
| **Mono.just(value)** | Has one result | `expectNext(value).verifyComplete()` |
| **Mono.empty()** | Completes without emitting an item | `verifyComplete()` and confirms no items |
| **Mono.error(error)** | Terminates with an error | `expectError(...)` |

For an authentication converter or introspector, emitting **Mono.empty()** is generally not the way to represent "invalid token." Emit an appropriate error per contract so the framework does not confuse "no result" with "authentication failed."

### 3.5. Bounding Test Execution Time

A Publisher that never completes can hang tests. You can pass a timeout to `verify`:

~~~java
StepVerifier.create(Mono.never())
    .expectSubscription()
    .thenCancel()
    .verify(Duration.ofSeconds(2));
~~~

In real tests, pick a timeout generous enough for CI yet short enough to catch deadlocks or unresponsive upstreams.

### 3.6. StepVerifier Triggers Subscription

This snippet has not run any reactive work yet:

~~~java
Mono<Jwt> decoded = decoder.decode(compactJwt);
~~~

The Publisher only describes the work. When the test runs:

~~~java
StepVerifier.create(decoded)
    .expectNextMatches(jwt -> jwt.getSubject().equals("user-417"))
    .verifyComplete();
~~~

StepVerifier subscribes and observes the outcome. Do not call **block()** just to force a Publisher to run in a test.

---

## 4. Testing OAuth2TokenValidator and ReactiveJwtDecoder

### 4.1. JWT Validators Are Synchronous

Spring Security defines:

~~~java
OAuth2TokenValidatorResult validate(Jwt token);
~~~

The validator inspects token properties and returns success or failure synchronously within the call. This is not a reactive contract. Example audience validator:

~~~java
static OAuth2TokenValidator<Jwt> audienceValidator(
        String requiredAudience) {

    return jwt -> {
        if (jwt.getAudience().contains(requiredAudience)) {
            return OAuth2TokenValidatorResult.success();
        }

        OAuth2Error error = new OAuth2Error(
            "invalid_token",
            "Required audience is missing",
            null
        );

        return OAuth2TokenValidatorResult.failure(error);
    };
}
~~~

You can combine the default validator with a custom validator:

~~~java
OAuth2TokenValidator<Jwt> validator =
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(ISSUER),
        audienceValidator(AUDIENCE)
    );
~~~

The default validator checks issuer and timestamps as configured. The audience validator adds the check required by the API.

### 4.2. Unit Testing the Validator Directly

~~~java
@Test
void acceptsJwtForExpectedAudience() {
    OAuth2TokenValidator<Jwt> validator =
        audienceValidator("orders-api");

    OAuth2TokenValidatorResult result =
        validator.validate(validJwt());

    assertTrue(result.getErrors().isEmpty());
}

@Test
void rejectsJwtForDifferentAudience() {
    Jwt jwt = Jwt.withTokenValue("test-token")
        .header("alg", "RS256")
        .issuer(ISSUER)
        .subject("user-417")
        .audience(List.of("billing-api"))
        .issuedAt(Instant.now().minusSeconds(5))
        .expiresAt(Instant.now().plusSeconds(120))
        .build();

    OAuth2TokenValidatorResult result =
        audienceValidator("orders-api").validate(jwt);

    assertFalse(result.getErrors().isEmpty());
    assertEquals(
        "invalid_token",
        result.getErrors().iterator().next().getErrorCode()
    );
}
~~~

This test verifies validator logic. StepVerifier is not needed because there is no Publisher here.

### 4.3. ReactiveJwtDecoder Produces Mono<Jwt>

The reactive decoder contract is:

~~~java
Mono<Jwt> decode(String token);
~~~

With Spring Security, **NimbusReactiveJwtDecoder** verifies signatures, decodes claims, and runs configured validators. This is the right boundary to use StepVerifier.

Example decoder configuration:

~~~java
@Bean
ReactiveJwtDecoder jwtDecoder() {
    NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder.withJwkSetUri(
            "https://id.example.com/.well-known/jwks.json"
        ).build();

    OAuth2TokenValidator<Jwt> withIssuer =
        JwtValidators.createDefaultWithIssuer(ISSUER);

    OAuth2TokenValidator<Jwt> withAudience =
        new DelegatingOAuth2TokenValidator<>(
            withIssuer,
            audienceValidator(AUDIENCE)
        );

    decoder.setJwtValidator(withAudience);
    return decoder;
}
~~~

### 4.4. Testing the Decoder with a Genuinely Signed JWT

An integration-style unit test should use:

- A test private key to sign the JWT.
- The matching public key to configure the decoder.
- Explicit issuer, audience, and timestamps.
- A compact JWT generated before calling `decode`.
- StepVerifier to assert `Mono<Jwt>`.

Assertion snippet:

~~~java
@Test
void decodesAndValidatesSignedJwt() {
    String compactJwt = signedJwtFixture();

    StepVerifier.create(decoder.decode(compactJwt))
        .assertNext(jwt -> {
            assertEquals(ISSUER, jwt.getIssuer().toString());
            assertEquals("user-417", jwt.getSubject());
            assertTrue(jwt.getAudience().contains(AUDIENCE));
        })
        .verifyComplete();
}
~~~

**signedJwtFixture()** is a test helper that builds a token signed with the test private key. Never use a fake JWT with an **alg=none** header to prove signature validity.

### 4.5. Testing Wrong-Audience Tokens Through the Decoder

When the decoder has an audience validator:

~~~java
@Test
void decoderRejectsWrongAudience() {
    String compactJwt = signedJwtFixtureWithAudience("billing-api");

    StepVerifier.create(decoder.decode(compactJwt))
        .expectError(JwtException.class)
        .verify();
}
~~~

Depending on the decoder/version, the concrete error may be `JwtValidationException` or another `JwtException`. If the test contract only requires the decoder to reject the token, checking the parent `JwtException` type is more resilient than depending on internal error messages.

### 4.6. Distinguishing Validator Failures from Decoder Failures

| Scenario | Detecting layer | Typical outcome |
|---|---|---|
| Wrong audience | `OAuth2TokenValidator` | Decode fails |
| Wrong issuer | `JwtIssuerValidator`/default validator | Decode fails |
| Expired token | `JwtTimestampValidator` | Decode fails |
| Malformed compact JWT | Decoder/parser | Decode fails |
| Invalid signature | Decoder/signature verifier | Decode fails |
| JWKS endpoint error | Key retrieval/upstream | Decode fails due to infrastructure |

When testing failures, do not lump everything into a single "invalid token" case. Split tests by layer so you know whether a failure stems from policy, token data, or a dependency.

### 4.7. Checking Custom Asynchronous Policies at the Right Layer

If policy requires calling an asynchronous service—for instance, checking whether a user still belongs to a tenant—do not make blocking HTTP/Redis calls inside `OAuth2TokenValidator`. A synchronous validator will block the calling thread and cannot return a `Mono`.

You can perform that check in the reactive authorization layer:

~~~java
public interface TenantMembership {
    Mono<Boolean> isMember(String subject, String tenantId);
}
~~~

For example, a `ReactiveAuthorizationManager` can return an `AuthorizationDecision` after querying membership:

~~~java
public final class TenantAuthorizationManager
        implements ReactiveAuthorizationManager<AuthorizationContext> {

    private final TenantMembership membership;

    public TenantAuthorizationManager(TenantMembership membership) {
        this.membership = membership;
    }

    @Override
    public Mono<AuthorizationDecision> check(
            Mono<Authentication> authentication,
            AuthorizationContext context) {

        String tenantId = context.getExchange()
            .getRequest()
            .getHeaders()
            .getFirst("X-Tenant-Id");

        return authentication
            .filter(JwtAuthenticationToken.class::isInstance)
            .cast(JwtAuthenticationToken.class)
            .flatMap(auth -> membership.isMember(
                    auth.getToken().getSubject(), tenantId)
                .map(AuthorizationDecision::new))
            .defaultIfEmpty(new AuthorizationDecision(false));
    }
}
~~~

In a real application, the tenant ID must be verified against a tenant registry/route policy. Never trust a client-supplied header as sole proof of tenant membership. The snippet only illustrates where to place the async check.

Testing with StepVerifier:

~~~java
@Test
void grantsAccessWhenMembershipExists() {
    when(membership.isMember("user-417", "alpha"))
        .thenReturn(Mono.just(true));

    Mono<AuthorizationDecision> decision =
        authorizationManager.check(
            Mono.just(jwtAuthentication(validJwt())),
            authorizationContext("alpha")
        );

    StepVerifier.create(decision)
        .expectNextMatches(AuthorizationDecision::isGranted)
        .verifyComplete();
}

@Test
void deniesAccessWhenMembershipDoesNotExist() {
    when(membership.isMember("user-417", "alpha"))
        .thenReturn(Mono.just(false));

    StepVerifier.create(checkTenantAccess("alpha"))
        .expectNextMatches(result -> !result.isGranted())
        .verifyComplete();
}
~~~

The **jwtAuthentication** and **authorizationContext** helpers create Authentication/AuthorizationContext fixtures. Testing the manager in isolation verifies the reactive decision; testing the security chain in section 10 verifies it is wired into real routes.

---

## 5. Testing the JWT Authentication Converter

### 5.1. Converters Can Be Synchronous or Reactive

In WebFlux, the JWT DSL expects a converter of type:

~~~java
Converter<Jwt, Mono<AbstractAuthenticationToken>>
~~~

An existing converter from the Servlet/imperative stack typically has type:

~~~java
Converter<Jwt, AbstractAuthenticationToken>
~~~

Spring Security provides **ReactiveJwtAuthenticationConverterAdapter** to wrap a synchronous converter into a reactive converter.

### 5.2. Using ReactiveJwtAuthenticationConverterAdapter

Example configuring authority mapping from the `scope` claim:

~~~java
@Bean
Converter<Jwt, Mono<AbstractAuthenticationToken>>
jwtAuthenticationConverter() {

    JwtGrantedAuthoritiesConverter authoritiesConverter =
        new JwtGrantedAuthoritiesConverter();

    authoritiesConverter.setAuthoritiesClaimName("scope");
    authoritiesConverter.setAuthorityPrefix("SCOPE_");

    JwtAuthenticationConverter delegate =
        new JwtAuthenticationConverter();

    delegate.setJwtGrantedAuthoritiesConverter(authoritiesConverter);

    return new ReactiveJwtAuthenticationConverterAdapter(delegate);
}
~~~

Wiring it into WebFlux Resource Server:

~~~java
@Bean
SecurityWebFilterChain securityWebFilterChain(
        ServerHttpSecurity http,
        Converter<Jwt, Mono<AbstractAuthenticationToken>> converter) {

    return http
        .authorizeExchange(exchange -> exchange
            .pathMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyExchange().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt.jwtAuthenticationConverter(converter))
        )
        .build();
}
~~~

The adapter merely wraps the synchronous converter's result in a `Mono`. It does not make database/HTTP lookups inside the delegate non-blocking. If asynchronous lookups are needed, write a converter returning `Mono` directly and use reactive clients.

### 5.3. Testing a Synchronous Converter Wrapped by the Adapter

~~~java
@Test
void convertsJwtToAuthentication() {
    JwtAuthenticationConverter delegate =
        new JwtAuthenticationConverter();

    Converter<Jwt, Mono<AbstractAuthenticationToken>> converter =
        new ReactiveJwtAuthenticationConverterAdapter(delegate);

    StepVerifier.create(converter.convert(validJwt()))
        .assertNext(authentication -> {
            assertInstanceOf(JwtAuthenticationToken.class, authentication);
            assertEquals("user-417", authentication.getName());
            assertTrue(authentication.getAuthorities().stream()
                .anyMatch(authority ->
                    authority.getAuthority().equals("SCOPE_orders.read")));
        })
        .verifyComplete();
}
~~~

This test verifies the adapter emits an Authentication and maps authorities properly. It does not prove the delegate performs asynchronous I/O.

### 5.4. Asynchronous Converter to Load Authorities

When roles/permissions live in a reactive service, the converter can call the service and return a `Mono`:

~~~java
public interface RoleDirectory {
    Mono<Collection<GrantedAuthority>> findAuthorities(String subject);
}
~~~

~~~java
public final class DirectoryJwtAuthenticationConverter
        implements Converter<Jwt, Mono<AbstractAuthenticationToken>> {

    private final RoleDirectory directory;

    public DirectoryJwtAuthenticationConverter(RoleDirectory directory) {
        this.directory = directory;
    }

    @Override
    public Mono<AbstractAuthenticationToken> convert(Jwt jwt) {
        return directory.findAuthorities(jwt.getSubject())
            .map(authorities ->
                new JwtAuthenticationToken(jwt, authorities));
    }
}
~~~

This converter does not call `block()` and does not fabricate authorities when the directory fails. If the directory can return empty, its contract must be clearly defined; typically it should return an empty collection rather than `Mono.empty` so the converter always emits an Authentication with an empty authority set.

### 5.5. Testing a Successful Converter

~~~java
@Test
void loadsAuthoritiesAsynchronously() {
    GrantedAuthority read =
        new SimpleGrantedAuthority("SCOPE_orders.read");

    when(roleDirectory.findAuthorities("user-417"))
        .thenReturn(Mono.just(List.of(read)));

    Converter<Jwt, Mono<AbstractAuthenticationToken>> converter =
        new DirectoryJwtAuthenticationConverter(roleDirectory);

    StepVerifier.create(converter.convert(validJwt()))
        .assertNext(authentication -> {
            assertEquals("user-417", authentication.getName());
            assertTrue(authentication.getAuthorities().contains(read));
        })
        .verifyComplete();

    verify(roleDirectory).findAuthorities("user-417");
}
~~~

Because StepVerifier subscribes, the call to the role directory is triggered. Calling Mockito `verify` after `verifyComplete()` confirms the dependency was actually invoked.

### 5.6. Testing a Converter When a Dependency Fails

~~~java
@Test
void propagatesRoleDirectoryFailure() {
    when(roleDirectory.findAuthorities("user-417"))
        .thenReturn(Mono.error(
            new IllegalStateException("role directory unavailable")));

    Converter<Jwt, Mono<AbstractAuthenticationToken>> converter =
        new DirectoryJwtAuthenticationConverter(roleDirectory);

    StepVerifier.create(converter.convert(validJwt()))
        .expectErrorMatches(error ->
            error instanceof IllegalStateException
                && error.getMessage().contains("unavailable"))
        .verify();
}
~~~

Do not use `onErrorResume(error -> Mono.just(authentication))` to let tokens pass when the authority service fails. That can turn a dependency outage into unintended authorization.

### 5.7. Testing That a Converter Does Not Perform I/O Before Subscription

Because Publishers are lazy, tests can verify the dependency is not invoked before subscribing:

~~~java
@Test
void roleLookupStartsOnSubscription() {
    when(roleDirectory.findAuthorities("user-417"))
        .thenReturn(Mono.just(List.of()));

    Mono<AbstractAuthenticationToken> result =
        converter.convert(validJwt());

    verifyNoInteractions(roleDirectory);

    StepVerifier.create(result)
        .expectNextCount(1)
        .verifyComplete();

    verify(roleDirectory).findAuthorities("user-417");
}
~~~

If the converter calls the service immediately on method invocation instead of inside the pipeline, this test catches the eager side effect.

---

## 6. Testing ReactiveOpaqueTokenIntrospector

### 6.1. Introspector Contract

For opaque access tokens, the Resource Server does not decode a JWT locally. It calls an introspection endpoint or token-state store to verify the token. WebFlux uses:

~~~java
Mono<OAuth2AuthenticatedPrincipal> introspect(String token);
~~~

Spring Security provides **SpringReactiveOpaqueTokenIntrospector**. You can replace it with a custom implementation or wrap the default implementation to map authorities, enforce extra policies, or record metrics.

A valid introspector emits a principal when the token is verified. If the token is inactive or cannot be introspected, it must emit an appropriate error. Never emit an empty principal to represent an invalid token.

### 6.2. Custom Introspector Wrapping a Delegate

Example adding authority mapping from introspection attributes:

~~~java
public final class CustomOpaqueTokenIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private final ReactiveOpaqueTokenIntrospector delegate;

    public CustomOpaqueTokenIntrospector(
            ReactiveOpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        return delegate.introspect(token)
            .map(principal -> {
                Collection<GrantedAuthority> authorities =
                    extractAuthorities(principal);

                return new DefaultOAuth2AuthenticatedPrincipal(
                    principal.getName(),
                    principal.getAttributes(),
                    authorities
                );
            });
    }

    private Collection<GrantedAuthority> extractAuthorities(
            OAuth2AuthenticatedPrincipal principal) {

        Object scopeValue = principal.getAttribute("scope");

        if (!(scopeValue instanceof String scopes)) {
            return List.of();
        }

        return Arrays.stream(scopes.split(" "))
            .filter(scope -> !scope.isBlank())
            .map(scope -> new SimpleGrantedAuthority("SCOPE_" + scope))
            .toList();
    }
}
~~~

This snippet illustrates the case where the AS returns scopes as a space-delimited string. If the AS returns a list or a custom claim, map according to the real contract. Never promote a scope into an administrative role automatically.

### 6.3. Testing an Introspector Returning a Principal

~~~java
@Test
void introspectsActiveToken() {
    OAuth2AuthenticatedPrincipal principal =
        new DefaultOAuth2AuthenticatedPrincipal(
            "user-417",
            Map.of(
                "active", true,
                "scope", "orders.read"
            ),
            List.of(new SimpleGrantedAuthority("SCOPE_orders.read"))
        );

    when(delegate.introspect("opaque-token"))
        .thenReturn(Mono.just(principal));

    StepVerifier.create(introspector.introspect("opaque-token"))
        .assertNext(result -> {
            assertEquals("user-417", result.getName());
            assertEquals(
                "orders.read",
                result.getAttribute("scope")
            );
            assertTrue(result.getAuthorities().stream()
                .anyMatch(authority ->
                    authority.getAuthority().equals("SCOPE_orders.read")));
        })
        .verifyComplete();

    verify(delegate).introspect("opaque-token");
}
~~~

This test verifies both delegate invocation and preservation of attributes/authorities.

### 6.4. Testing Inactive Tokens

An introspection response with **active=false** must not produce a successful principal. **SpringReactiveOpaqueTokenIntrospector** raises an error if a token is inactive. In a custom introspector, preserve errors from the delegate:

~~~java
@Test
void propagatesInactiveTokenFailure() {
    when(delegate.introspect("revoked-token"))
        .thenReturn(Mono.error(
            new IllegalStateException("token is inactive")));

    StepVerifier.create(introspector.introspect("revoked-token"))
        .expectErrorMatches(error ->
            error.getMessage().contains("inactive"))
        .verify();
}
~~~

In real tests, use the exception thrown by the introspector implementation—such as `OAuth2IntrospectionException` or `OAuth2AuthenticationException` depending on the class. The key is never turning an inactive token into a privileged principal.

### 6.5. Testing Introspection Timeouts

You can configure a timeout around the introspector call or at the HTTP client according to application policy:

~~~java
@Test
void failsWhenIntrospectionDoesNotRespond() {
    Mono<OAuth2AuthenticatedPrincipal> result =
        Mono.<OAuth2AuthenticatedPrincipal>never()
            .timeout(Duration.ofMillis(100));

    StepVerifier.create(result)
        .expectError(TimeoutException.class)
        .verify(Duration.ofSeconds(2));
}
~~~

This test checks pipeline timeout semantics. For real HTTP introspection, configure connect/read/response timeouts on `WebClient` and test against a mock web server or stub endpoint to verify network-layer timeouts.

### 6.6. Do Not Cache Errors as Inactive Tokens

Two outcomes must be distinguished:

- AS returns token inactive: the token is not authenticated.
- AS times out or returns 5xx: token status is unknown because the dependency is unavailable.

Do not cache an upstream timeout as `active=false` for a long period if it masks outages. Nor should you turn a timeout into `active=true`. The Resource Server should fail closed for granting Authentication and return an error per the designed error handling.

---

## 7. Testing Errors, Retries, and Timeouts in the Reactive Pipeline

### 7.1. Classifying Errors

| Error | Typical detecting layer | Test behavior |
|---|---|---|
| Invalid JWT signature | `ReactiveJwtDecoder` | `Mono` error |
| Wrong JWT audience | JWT validator in decoder | `Mono` error |
| Inactive opaque token | `ReactiveOpaqueTokenIntrospector` | `Mono` error |
| Introspection endpoint timeout | `WebClient`/dependency | Timeout/error |
| Role directory failure | Custom converter | `Mono` error |
| User not in tenant | `ReactiveAuthorizationManager` | `AuthorizationDecision` false |
| Missing scope | Authorization rule | 403 |
| Request without token | Security entry point | 401 |

Tests should assert errors at the right boundary. For instance, a user not belonging to a tenant does not mean the JWT signature is invalid; that is an authorization decision.

### 7.2. Testing Intentional Retries

If a dependency allows retrying transient failures, test both the attempt count and the final outcome:

~~~java
@Test
void retriesTransientIntrospectionFailure() {
    AtomicInteger attempts = new AtomicInteger();

    Mono<String> result = Mono.defer(() -> {
        if (attempts.incrementAndGet() < 3) {
            return Mono.error(new IOException("temporary failure"));
        }
        return Mono.just("active");
    }).retry(2);

    StepVerifier.create(result)
        .expectNext("active")
        .verifyComplete();

    assertEquals(3, attempts.get());
}
~~~

Do not retry all errors. Invalid tokens, audience mismatches, or inactive tokens are authentication failures; retrying cannot fix them. HTTP introspection retries need bounded attempts, backoff, timeouts, and bulkheads to prevent retry storms.

### 7.3. Virtual Time for Delays and Timeouts

When testing a Publisher with a delay, there is no need for `Thread.sleep`:

~~~java
@Test
void verifiesDelayedResultWithoutWaiting() {
    StepVerifier.withVirtualTime(
            () -> Mono.delay(Duration.ofMinutes(5)))
        .thenAwait(Duration.ofMinutes(5))
        .expectNext(0L)
        .verifyComplete();
}
~~~

The Publisher must be constructed inside the `Supplier` passed to `withVirtualTime` so StepVerifier installs the virtual scheduler before the pipeline is assembled.

Virtual time only works with schedulers supporting virtual scheduling. A real HTTP request or a library using its own scheduler is not automatically fast-forwarded.

### 7.4. Testing Timeouts with Virtual Time

~~~java
@Test
void verifiesReactiveTimeout() {
    StepVerifier.withVirtualTime(
            () -> Mono.<String>never()
                .timeout(Duration.ofSeconds(30)))
        .thenAwait(Duration.ofSeconds(30))
        .expectError(TimeoutException.class)
        .verify();
}
~~~

This tests the timeout operator, not Netty/`WebClient` timeout configuration. To test the HTTP client, use a mock server with reasonably bounded real time.

### 7.5. Testing Cancellation

When a client cancels a request or times out, the pipeline should propagate cancellation upstream to release resources:

~~~java
@Test
void cancelsUpstreamWhenSubscriberCancels() {
    AtomicBoolean cancelled = new AtomicBoolean();

    Mono<String> source = Mono.<String>never()
        .doOnCancel(() -> cancelled.set(true));

    StepVerifier.create(source)
        .expectSubscription()
        .thenCancel()
        .verify();

    assertTrue(cancelled.get());
}
~~~

For introspection or directory lookups, cancellation can stop unneeded work. However, cancellation cannot always abort a request already dispatched to an external system; verify cancellation behavior in your HTTP client and downstream services.

---

## 8. Backpressure, Context, and Subscription Count

### 8.1. Testing Backpressure

`Mono` emits at most one item, but a `Flux` or internal publisher may need demand testing:

~~~java
@Test
void emitsOnlyAfterDemand() {
    StepVerifier.create(Flux.just("one", "two"), 0)
        .expectSubscription()
        .thenRequest(1)
        .expectNext("one")
        .thenRequest(1)
        .expectNext("two")
        .verifyComplete();
}
~~~

For a Resource Server, most decoders/introspectors return `Mono`. However, a converter may combine multiple reactive sources; test demand if your pipeline processes a `Flux` or stream of authorities.

### 8.2. Verifying Reactor Context

If a custom pipeline reads a correlation ID or tenant context from Reactor Context, you can supply initial context to StepVerifier:

~~~java
StepVerifier.create(
        service.loadAuthorities("user-417"),
        StepVerifierOptions.create()
            .withInitialContext(Context.of("correlationId", "test-123"))
    )
    .expectAccessibleContext()
    .contains("correlationId", "test-123")
    .then()
    .expectNextCount(1)
    .verifyComplete();
~~~

Do not confuse Reactor Context with Servlet `ThreadLocal`. In a reactive flow, never assume callbacks execute on the same thread. Spring Security stores `SecurityContext` in the reactive context; custom code must stay within the pipeline and avoid arbitrary jumps to blocking executors.

### 8.3. Checking Introspection Call Count

If the pipeline includes retries, caching, or multiple subscribers, verify how many times the dependency is called:

~~~java
@Test
void introspectsOnceForOneSubscription() {
    AtomicInteger calls = new AtomicInteger();

    ReactiveOpaqueTokenIntrospector introspector =
        token -> Mono.defer(() -> {
            calls.incrementAndGet();
            return Mono.just(activePrincipal());
        });

    StepVerifier.create(introspector.introspect("opaque-token"))
        .expectNextCount(1)
        .verifyComplete();

    assertEquals(1, calls.get());
}
~~~

If the same `Mono` is subscribed to twice, the work may run twice. Do not add `cache()` or `share()` just to make a test pass; decide explicitly whether introspection results should be cached and whether caching aligns with revocation freshness.

### 8.4. Using PublisherProbe or TestPublisher for Flow Control

**PublisherProbe** helps confirm whether a Publisher branch was subscribed to. **TestPublisher** lets tests control when values/errors are emitted.

They are useful when a custom converter/introspector has branches:

- Token cached: do not call AS.
- Token cache miss: call introspection.
- User lacks tenant membership: do not call data repository.
- Upstream cancelled: do not continue calling downstream dependencies.

Use them to verify orchestration. For JWT signatures, claim validation, and HTTP behavior, you still need real fixtures or integration tests.

---

## 9. Testing the WebFlux Security Chain with WebTestClient

### 9.1. Unit Tests Do Not Replace Integration Tests

StepVerifier tests a Publisher in isolation. It does not prove that `SecurityWebFilterChain` wires the right decoder, converter, introspector, and authorization rules.

`WebTestClient` tests HTTP requests/responses through the WebFlux application context. It can be combined with Spring Security test support to send tokens or mock authentication.

### 9.2. Configuring the JWT Chain

Example chain:

~~~java
@Bean
SecurityWebFilterChain apiSecurity(
        ServerHttpSecurity http,
        ReactiveJwtDecoder decoder,
        Converter<Jwt, Mono<AbstractAuthenticationToken>> converter) {

    return http
        .authorizeExchange(exchange -> exchange
            .pathMatchers("/api/public/**").permitAll()
            .pathMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyExchange().denyAll()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt
                .decoder(decoder)
                .jwtAuthenticationConverter(converter)
            )
        )
        .build();
}
~~~

### 9.3. Testing Endpoints with a Mock JWT

Spring Security test can supply a mock JWT to verify authorization mapping:

~~~java
webTestClient
    .mutateWith(mockJwt()
        .jwt(jwt -> jwt
            .subject("user-417")
            .claim("scope", "orders.read")
        )
        .authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )
    )
    .get()
    .uri("/api/orders")
    .exchange()
    .expectStatus().isOk();
~~~

This tests authorization/route rules. Mock JWT does not run signature verification, `ReactiveJwtDecoder`, or custom `OAuth2TokenValidator` instances. Do not use this test as proof that the decoder rejects invalid-signature JWTs.

### 9.4. Testing the Real Decoder Over HTTP

To test end-to-end:

1. Start the WebFlux application context.
2. Configure the decoder with a test public key or test JWKS endpoint.
3. Generate a compact JWT signed with the test private key.
4. Send the token in the Authorization header.
5. Check the HTTP status and response body.
6. Send a token with the wrong audience or signature to confirm 401.
7. Send a valid token missing the scope to confirm 403.

When testing introspection, use a stub HTTP endpoint returning active/inactive responses and verify the Resource Server responds accordingly. Tests must never call a production Authorization Server.

### 9.5. Verifying the Converter Is Invoked in the Request Flow

You can spy/mock a dependency called by the converter, send a request with a JWT validated by the decoder, and assert the dependency was called once. This proves the converter is part of the live pipeline.

### 9.6. Verifying HTTP Status Codes at the Right Layer

| Scenario | Typically expected HTTP status |
|---|---|
| No token on an authenticated endpoint | 401 |
| JWT with invalid signature/issuer/audience/expiry | 401 |
| Inactive opaque token | 401 |
| Introspection dependency failure | Per error mapping; do not grant Authentication |
| Valid JWT missing scope | 403 |
| Valid JWT denied by tenant policy | 403 or 404 per policy |
| Valid JWT with sufficient permissions | 2xx |

If introspection times out, the system may respond with 503 per the designed error handling. Never turn a timeout into 2xx or a default principal.

---

## 10. Example Composite Test Suite

A test suite can be organized by boundary:

~~~text
security/
  AudienceValidatorTests
  ReactiveJwtDecoderTests
  JwtAuthenticationConverterTests
  ReactiveOpaqueTokenIntrospectorTests
  TenantAuthorizationManagerTests
  ResourceServerWebFluxIntegrationTests
~~~

### 10.1. AudienceValidatorTests

- Correct audience returns success.
- Wrong audience returns validation error.
- Missing audience returns validation error.
- Token with multiple audiences excluding the required API is rejected.

### 10.2. ReactiveJwtDecoderTests

- JWT signed with a trusted key emits `Jwt`.
- Invalid signature emits error.
- Wrong issuer emits error.
- Wrong audience emits error.
- Expired token emits error.
- JWKS/upstream failures are never turned into a valid `Jwt`.

### 10.3. JwtAuthenticationConverterTests

- Subject maps to the Authentication name.
- Scopes map to authorities with the appropriate prefix.
- Custom claims map accurately.
- Role directory is called upon subscription.
- Role directory failures propagate.
- No permissions returns an Authentication with empty authorities or rejects per contract, never adding default permissions.

### 10.4. ReactiveOpaqueTokenIntrospectorTests

- Active token returns a principal.
- Attributes are preserved.
- Scopes are mapped properly.
- Inactive token emits an error.
- HTTP timeout emits an error.
- HTTP 5xx does not create a principal.
- Delegate is invoked the expected number of times.
- Neither tokens nor client secrets are logged.

### 10.5. TenantAuthorizationManagerTests

- Membership true grants access.
- Membership false denies access.
- Membership service timeout does not grant permission.
- Missing Authentication is denied.
- Invalid tenant ID is denied.
- Context/correlation data is preserved across the reactive chain.

### 10.6. ResourceServerWebFluxIntegrationTests

- Public endpoints are accessible.
- Protected endpoints without a token return 401.
- Valid JWT with sufficient scope returns 2xx.
- Valid JWT missing scope returns 403.
- Invalid-signature JWT returns 401.
- Active opaque token is accepted.
- Inactive opaque token is rejected.
- Dependency outages never unintentionally authenticate requests.

---

## 11. Common Pitfalls When Using StepVerifier

| Mistake | Consequence | How to fix |
|---|---|---|
| Calling a method without subscribing | Test never runs the pipeline | Use StepVerifier or WebTestClient |
| Calling `block()` in a reactive test | Masks subscription/execution-model bugs | Verify with StepVerifier |
| Using StepVerifier directly on `OAuth2TokenValidator` | Validator does not return a Publisher | Test `validate()` directly |
| Assuming `ReactiveJwtDecoder` makes validators async | Misunderstands reactive boundary | Validators stay sync; decoder emits `Mono` |
| Mocking the decoder in every test | Signatures/claim validation never tested | Include decoder integration tests with test keys |
| Using `mockJwt` to test signatures | Bypasses the decoder | Send a genuinely signed compact JWT |
| Converter calls blocking database | Blocks event loop | Use reactive repository/client |
| Treating adapter as automatically making I/O non-blocking | Blocking delegate stays blocking | Use the adapter only for pure CPU sync converters |
| Introspector returns `Mono.empty` on inactive token | Fails to express authentication failure | Emit error per introspector contract |
| Turning timeouts into a default principal | Fail-open | Never grant Authentication when unverified |
| Retrying invalid-token errors | Wastes load, cannot fix token | Retry only classified transient failures |
| Tests using `Thread.sleep` | Slow and flaky | Use virtual time when scheduler supports it |
| Omitting verify timeout | Tests can hang | Use `verify(Duration)` |
| Not testing cancellation | Upstream resources may keep running | Use `thenCancel` and check `doOnCancel` |
| Testing only one node for distributed caches | Misses cross-node races/replays | Integration test with a shared store |
| Mocking the entire security chain | Fails to verify wiring | Add `WebTestClient` integration tests |

---

## 12. Workflow for Writing a Readable StepVerifier Test

When writing tests for a reactive security component, follow these steps:

1. Identify the contract: does the `Mono` emit a principal, an authentication, or an error?
2. Create the minimal fixture: `Jwt`, principal, key pair, or stub response.
3. Prepare mock/fake dependencies before constructing the Publisher.
4. Create the Publisher without subscribing manually.
5. Use StepVerifier to describe value/error/completion/cancellation.
6. After `verify`, assert interaction counts and side effects.
7. Set a timeout to prevent hanging tests.
8. Add integration tests if the logic depends on wiring or HTTP boundaries.

A good test clearly shows both the result and the terminal signal:

~~~java
StepVerifier.create(introspector.introspect("opaque-token"))
    .assertNext(principal -> {
        assertEquals("user-417", principal.getName());
        assertTrue(principal.getAuthorities().stream()
            .anyMatch(authority ->
                authority.getAuthority().equals("SCOPE_orders.read")));
    })
    .verifyComplete();
~~~

Avoid `expectNextCount(1)` when the principal's contents matter for security. Assert the actual claims, subject, scopes, and authorities returned.

---

## 13. Self-Check Questions

**Question 1.** Why is calling the decoder and inspecting the Publisher variable insufficient?

**Answer:** Reactive Publishers are typically lazy. Work starts only upon subscription; StepVerifier subscribes and observes the actual signals.

**Question 2.** Is `OAuth2TokenValidator` a reactive API?

**Answer:** No. `validate(Jwt)` returns `OAuth2TokenValidatorResult` synchronously. `ReactiveJwtDecoder` calls validators while producing `Mono<Jwt>`.

**Question 3.** Where should StepVerifier be used when testing JWT validation?

**Answer:** Test validator predicates directly with JUnit; use StepVerifier for `ReactiveJwtDecoder.decode()` to verify the decoder emits a `Jwt` or an error.

**Question 4.** What does `ReactiveJwtAuthenticationConverterAdapter` do?

**Answer:** It wraps a synchronous `Converter<Jwt, AbstractAuthenticationToken>` into `Converter<Jwt, Mono<AbstractAuthenticationToken>>`. It does not make blocking I/O inside the delegate non-blocking.

**Question 5.** When should you write a converter that returns `Mono` directly?

**Answer:** When mapping an Authentication requires calling a reactive service to load authorities, entitlements, or other data.

**Question 6.** What does `ReactiveOpaqueTokenIntrospector` return when a token is active?

**Answer:** A `Mono` emitting an `OAuth2AuthenticatedPrincipal` with appropriate attributes and authorities.

**Question 7.** Should an inactive token return `Mono.empty` or `Mono.error`?

**Answer:** Emit an error per the introspector contract. `Mono.empty` is not the standard representation for an inactive token.

**Question 8.** How can you test upstream timeouts without waiting long?

**Answer:** Use virtual time with publishers/schedulers supporting virtual scheduling, or test the timeout operator directly. Real HTTP clients need separate tests with a mock server.

**Question 9.** Why not use `mockJwt` to test signatures?

**Answer:** `mockJwt` creates an Authentication fixture and skips signature decoding/verification. A genuinely test-key-signed compact JWT is needed.

**Question 10.** If the role directory fails, should the converter return a default Authentication?

**Answer:** No. Dependency failures must propagate per failure policy; never grant permissions when authorities could not be loaded.

**Question 11.** How does StepVerifier test cancellation?

**Answer:** Use `expectSubscription()`, `thenCancel()`, `verify()`, and check `doOnCancel` or upstream cleanup.

**Question 12.** Why not retry an audience mismatch?

**Answer:** That is a token data/policy error, not a transient dependency failure. Retrying cannot make a wrong-audience token valid.

**Question 13.** Is testing a converter in isolation enough to prove `SecurityWebFilterChain` uses it?

**Answer:** No. A `WebTestClient` integration test is needed to confirm wiring of the decoder, converter, filter chain, and authorization rules.

**Question 14.** Can a blocking Redis call be placed inside `OAuth2TokenValidator` when using WebFlux?

**Answer:** No. The validator is synchronous and can block the processing thread. Use the reactive authorization/authentication pipeline and reactive clients instead.

**Question 15.** When introspection times out, may the Resource Server accept the token?

**Answer:** No. When token status cannot be verified, Authentication must never be granted fail-open.

---

## 14. Official References

- [Spring Security — OAuth 2.0 Resource Server JWT for WebFlux](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): `ReactiveJwtDecoder`, validation, and JWT authentication converters.
- [Spring Security — OAuth 2.0 Resource Server Opaque Token for WebFlux](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html): `ReactiveOpaqueTokenIntrospector`, `SpringReactiveOpaqueTokenIntrospector`, and custom introspectors.
- [Spring Security API — OAuth2TokenValidator](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/OAuth2TokenValidator.html): synchronous `validate()` contract.
- [Spring Security API — ReactiveJwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/ReactiveJwtDecoder.html): `decode()` returning `Mono<Jwt>`.
- [Spring Security API — ReactiveJwtAuthenticationConverterAdapter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/ReactiveJwtAuthenticationConverterAdapter.html): adapter for synchronous converters.
- [Spring Security API — ReactiveOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenIntrospector.html): introspection contract returning a `Mono` principal.
- [Reactor Test — StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): `expectNext`, `expectError`, `thenCancel`, `verify`, and virtual time.
- [Reactor Reference — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): StepVerifier, TestPublisher, and PublisherProbe.

APIs may change across versions. Check the documentation for the exact Spring Security/Reactor version resolved by your project build.

## 15. Key Takeaways

StepVerifier is the tool for verifying Publisher behavior: subscription, emitted values, errors, completion, backpressure, and cancellation. Use it at the reactive boundaries your application actually exercises.

- **JWT validators:** `OAuth2TokenValidator.validate()` is synchronous; test its logic directly.
- **JWT decoders:** `ReactiveJwtDecoder.decode()` returns `Mono<Jwt>`; use StepVerifier to test decoding and validation errors.
- **Authentication converters:** use `ReactiveJwtAuthenticationConverterAdapter` for synchronous converters; write a `Converter` returning `Mono` when genuine reactive lookups are needed.
- **Opaque introspectors:** `ReactiveOpaqueTokenIntrospector.introspect()` returns a `Mono` principal; test active, inactive, timeout, and upstream error cases.
- **Async policies:** place tenant/entitlement lookups in the reactive authorization/authentication pipeline, never block inside validators.
- **Integration:** `WebTestClient` tests `SecurityWebFilterChain`; `mockJwt` is only for authorization tests and does not verify JWT signatures.

A good reactive test proves both the output and how the pipeline terminates. Never let upstream errors turn into a default Authentication, never let blocking converters run on the event loop, and never substitute mocks for signature or wiring tests that need verification.
