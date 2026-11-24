# Testing expired, tampered, stolen, or replayed cookies

## 1. Objectives and security scope

Remember-me allows a browser to re-prove identity via a long-lived cookie after the previous HTTP session is gone. In Spring Security Servlet, this cookie is processed by `RememberMeAuthenticationFilter` and `RememberMeServices`, typically producing a `RememberMeAuthenticationToken`. The remember-me cookie **differs** from `JSESSIONID`: extending a session does not test remember-me token replay, and resending `JSESSIONID` fails to prove auto-login ran.

This article explains how to design and test **four remember-me cookie scenarios**:

1. **Expired:** the browser still tries to send an old cookie or the server-side token has aged out; the system must reject authentication.
2. **Tampered:** bytes, structure, signature, or series/token pair are no longer valid; the system must not grant access.
3. **Stolen:** another actor obtains a valid *copy* of the cookie; we must understand detection limits, blast radius, and revocation.
4. **Replayed:** the exact same cookie value is sent again after prior use; outcomes differ between hash-based and persistent-token remember-me.

Applies to **Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring MVC/Servlet**. Never use real cookies belonging to others; examples use synthetic users, tokens, and repositories inside test environments. Never access external systems without authorization.

### 1.1. Distinguishing the four states

| State | Does the server accept the cookie? | Result to test | Primary risk |
| --- | --- | --- | --- |
| **Expired** | No | Must not auto-login; force user to log in again | Accepting credentials beyond policy lifetime |
| **Tampered** | No, if signature/format or DB token mismatches | Reject, cancel client cookie when appropriate, leak no secrets | Bypassing integrity checks or granting access on parse errors |
| **Stolen** | **Possibly**, since it is a valid credential copy | Distinguish hash-based vs. persistent token; test revocation policy | Cookie thief accesses account without password |
| **Replay** | Depends on implementation and request order | Hash-based is reusable; persistent-token rotates and detects stale mismatches | Used credential accepted indefinitely or false positives from races |

**Never conclude “the cookie was not stolen” simply because its signature is valid.** Signatures detect modified data; they **do not** prove who holds the cookie. A byte-for-byte copy is cryptographically valid. Persistent-token rotation can surface signs of stale reuse, yet cannot definitively identify which actor is the attacker from the token pair alone.

## 2. Understanding the verification flow before writing tests

A normal flow after a user checks “Remember me”:

~~~text
Successful interactive login
  POST /login + username/password + remember-me=true
        |
        ├── AuthenticationManager verifies password
        ├── SecurityContext saved per session policy
        └── RememberMeServices.loginSuccess(...)
                ├── hash-based: signs cookie data
                └── persistent: creates series + token, stores in DB
                       |
                       v
           Set-Cookie: remember-me=<secret>

Later visit, NO authenticated HttpSession remaining
  GET /account/me
  Cookie: remember-me=<secret>
                       |
                       v
           RememberMeAuthenticationFilter
                       |
           SecurityContext lacks Authentication?
                       |
                      YES
                       |
           RememberMeServices.autoLogin(...)
                       |
          ┌────────────┴────────────┐
          |                         |
        Valid            Invalid/expired/revoked
          |                         |
 RememberMeAuthenticationToken    null/exception
          |                         |
 AuthenticationManager            No access
          |                         |
 Authorization                  Login again
~~~

If the request **already has a valid session carrying an `Authentication`**, the remember-me filter usually **does not** run auto-login. Tests must clear/omit the old session cookie and `MockHttpSession` to force the app to inspect remember-me. Never just mint a cookie and call an API inside a still-fully-authenticated session: such a test can pass completely without ever exercising the remember-me token.

### 2.1. Two standard implementations

| Feature | `TokenBasedRememberMeServices` (hash-based) | `PersistentTokenBasedRememberMeServices` |
| --- | --- | --- |
| Cookie contents | Base64 of username, expiry timestamp, algorithm, signature | Base64 of `series` and `token` |
| Verification | Recomputes/compares signature from user/password/key and checks expiry | Queries `PersistentTokenRepository`, compares series/token and record age |
| Separate DB token row | No | Yes |
| Valid cookie used first time | Auto-login | Auto-login **and rotates token** in DB/cookie |
| Reusing the exact old cookie | **May keep being accepted** until expiry or password/key change | If series exists yet DB token changed → mismatch, may throw `CookieTheftException` |
| Detecting reuse of a copy | No built-in per-token replay detection | Signs via series/token mismatch after rotation |
| Revocation | Expiry, password/key change, or extra measures | Delete record/token per policy; standard logout may revoke user tokens |
| Testing focus | Expiry, signature, replay still succeeding, password/key change | Record age, series, token rotation, replay mismatch, revocation, concurrency |

Both implementations require `UserDetailsService`. Both must use HTTPS, appropriate `HttpOnly`/`Secure` cookies, and CSRF protection whenever browsers send cookies automatically to authenticate state-changing requests.

## 3. Expiration: test at BOTH browser and server

There are **two expiration layers** to separate:

- **Browser expiration:** `Max-Age` or `Expires` decides whether the browser keeps sending the cookie automatically.
- **Server token validity:** even if a client deliberately sends a cookie value past expiration, the server **must still reject it**. Browsers are not trusted components for enforcing expiration policies.

To avoid tests sleeping 14 days, **never use `Thread.sleep(...)` to wait for token expiry**. Construct controlled expired data or inject a clock where your app owns the time logic. For Spring Security library services lacking public Clock injection at the relevant points, calling protected test hooks or creating an already-expired token is faster and more focused.

### 3.1. Hash-based: expiry lives inside the signed cookie

Conceptual structure in Spring Security 6:

~~~text
Base64(
  username : expiryTimeMillis : algorithmName : signature
)

signature = hash(username : expiryTimeMillis : storedPassword : serverKey)
~~~

Compatibility exists for legacy cookies omitting `algorithmName`. Hence:

- Changing `expiryTimeMillis` to a future timestamp **without** recomputing the signature with the key → **signature mismatch**, cookie rejected.
- Creating a **validly signed** payload whose `expiryTimeMillis` is in the past → must be rejected as **expired**, not due to a bad signature.
- Setting `Max-Age=0` on responses makes browsers delete cookies; however, an HTTP client can deliberately resend raw cookies regardless. Always test server-side enforcement.
- `tokenValiditySeconds` affects both server-side validity checks and cookie lifetime. Negative values in hash-based remember-me produce a browser-session cookie while server token lifetime may still default higher; do not use `Max-Age` alone as an oracle.

Never call `Base64.decode(...)` in production app code to identify users from the cookie before Spring Security verifies the signature. Base64 is encoding, **not encryption**, and unverified payloads can be forged.

### 3.2. Persistent-token: expiry lives in record age

A typical row:

~~~sql
CREATE TABLE persistent_logins (
    username VARCHAR(64) NOT NULL,
    series VARCHAR(64) PRIMARY KEY,
    token VARCHAR(64) NOT NULL,
    last_used TIMESTAMP NOT NULL
);
~~~

When the `series:token` cookie matches the DB yet `last_used` (updated on token creation/rotation) is older than `tokenValiditySeconds`, `PersistentTokenBasedRememberMeServices` rejects auto-login. **Rejecting an expired token does not automatically delete the row from the table**, so production needs a cleanup policy.

Tests should distinguish:

1. Matching series and matching token yet expired record → rejected due to expiration.
2. Matching series yet wrong token → `CookieTheftException` branch before/distinct from expiry; may revoke user's tokens.
3. Unknown series → persistent token not found; **do not** infer cookie theft.
4. Browser drops cookie due to Max-Age → request arrives without cookie; does not exercise the server-expired branch.

When running multi-node Redis/SQL, test server time/clock skew and token-update atomicity. Never mutate OS system clocks on production machines to test expiration.

## 4. Tampered cookies: classify before asserting errors

“Tampering” covers several distinct test actions:

| Test manipulation | Hash-based | Persistent-token | Expectation |
| --- | --- | --- | --- |
| Invalid Base64 string | Decode fails | Decode fails | No login; cookie cancelled when appropriate. |
| Valid Base64 with wrong field count | `InvalidCookieException` / invalid cookie handling | `InvalidCookieException` | No login. |
| Change username in payload | Signature no longer matches or user not found | Persistent cookie has no explicit username field | Must not grant another identity. |
| Change expiry while keeping signature | Signature invalid | Expiry lives on server record, not in cookie field | Cannot extend access via client edits. |
| Change signature | Signature mismatch | No equivalent signature field; altering token causes mismatch | No login. |
| Change token while keeping existing series | Series/token pair does not apply | **Can trigger `CookieTheftException` and revoke user tokens** | Fail closed; avoid running tamper tests against real users' tokens. |
| Change series to a nonexistent series | Does not apply | Record not found | No login; no cookie identity restored. |

**Never test tampering on a real production user's cookie.** With persistent tokens, tampering with a token inside a valid series can cause the server to **delete all persistent-login tokens for that username** under the standard implementation. Isolate this side effect inside fixture/test environments.

### 4.1. Do not assume HTTP 401 in every scenario

`AuthenticationProvider`/`RememberMeServices` do not dictate a single HTTP status code. When `autoLogin` yields no identity, a protected endpoint may:

- Return `401 Unauthorized` in APIs configured with an appropriate `AuthenticationEntryPoint`.
- Redirect `302` to `/login` in form-login websites.
- Return `403` if authorization or CSRF blocks the request at another layer.

Therefore, **service-layer** tests should assert `Authentication == null` or the specific exception type. **HTTP integration** tests should assert responses matching your configured filter chain/entry point rather than assuming a universal 401 or 302 for every app.

## 5. Stolen cookies: what can actually be detected?

A cookie is a **bearer credential**: if a valid copy is stolen, sending requests from another user agent/IP **does not automatically invalidate its signature or token**. Distinguish testing a **tampered credential** from testing a **copied valid credential**.

Safe test setup:

~~~text
Browser A (account owner)
  └── holds valid cookie R1
                 |
        In test fixture only:
        copy R1 to client B
                 |
                 v
Browser B (simulated attacker)
  └── sends exact R1 (unchanged byte-for-byte)
                 |
                 v
Server: verifies R1 per implementation
~~~

**Hash-based:** B can auto-login as A until the cookie expires or password/key changes. Using R1 does not invalidate R1, so replay tests across two clients **can both succeed**. This is a **critical security limitation to mitigate via lifetimes, re-auth, anomaly detection, and remember-me policies**.

**Persistent-token:** the first client presenting `series=S, token=T1` updates the DB to `S,T2` and receives a new cookie. A client still presenting `S,T1` hits a matching series with a mismatched token; by default `PersistentTokenBasedRememberMeServices` treats this as suspected theft, throws `CookieTheftException`, and calls `removeUserTokens(username)`.

### 5.1. Unknown who used it first

Suppose the token thief uses R1 **before** the victim:

~~~text
DB: S/T1

Attacker B sends S/T1 → VALID
  DB rotates to S/T2
  B receives cookie S/T2

Victim A sends S/T1 → MISMATCH
  Server suspects cookie theft
  User's tokens are revoked
~~~

B's first use **succeeded**; detection only arrives on the subsequent request. Token rotation cannot prevent the very first use of a stolen credential. Moreover, a mismatch **does not prove which party was the attacker**; it is a signal requiring investigation.

### 5.2. Concurrency and false positives

Two parallel requests from two legitimate tabs can both send `S/T1` before the browser applies the new cookie. The first request rotates the DB to `T2`, while the second presents the stale token and triggers a mismatch. With the default implementation, revocation can fire even with no attacker present.

Hence you must test races, retries, multiple tabs, and transport latency in staging. Never simply delete token comparison to avoid false positives: doing so destroys replay detection. Instead, review request/session transition design, application-layer synchronization, or an evaluated custom token scheme; altering persistent remember-me logic requires a security review.

### 5.3. From detection to response

Upon replay or cookie-theft signals, typical procedures include:

1. Reject auto-login and revoke tokens per policy.
2. Log the **event category** (mismatch/expired/unknown series) with a correlation ID, without logging raw cookies/series/tokens.
3. Notify the account owner via a trusted channel when appropriate; avoid including tokens in notifications.
4. Require fresh interactive login and potentially MFA/step-up for sensitive actions.
5. Review active authenticated HTTP sessions and other tokens; revoking remember-me **does not automatically destroy all existing JSESSIONIDs**.
6. Analyze concurrent requests before concluding cookie theft from a single signal alone.

## 6. Replayed cookies: distinguish “first use” and “subsequent use”

Replay typically means **resending a credential that was previously accepted**. Outcomes differ:

~~~text
HASH-BASED
Cookie R1 → autoLogin succeeds
Cookie R1 → autoLogin again may still succeed
Cookie R1 → ... until expiry/password/key changes

PERSISTENT
DB: S/T1
Cookie S/T1 → autoLogin succeeds
              DB: S/T2, response cookie S/T2

Cookie S/T2 → autoLogin succeeds
              DB: S/T3, response cookie S/T3

Cookie S/T1 → valid series, stale token
              CookieTheftException, may revoke user's tokens
~~~

This is why replay test suites must retain an **immutable copy of the old cookie** rather than accidentally overwriting it with the new response cookie from the first auto-login. If an HTTP test client auto-updates its cookie jar, sending the “second cookie” may actually send the **rotated** token, returning 200 every time and failing to test stale replay.

Test independently:

- **Replaying the same raw hash-based cookie:** two turns without sessions; both may succeed while valid.
- **Persistent normal rotation:** use the new cookie from the response; must succeed with a new token value distinct from the old one while keeping the same series.
- **Persistent stale replay:** resend the **old** cookie after rotation; must be rejected with a mismatch signal.
- **Persistent unknown series:** no record found; do not conflate with token mismatch.
- **Persistent expired record:** even a matching token must not authenticate.
- **Replay after revocation/logout:** must not auto-login once the persistent token was removed from the store.

## 7. Preconditions for trustworthy tests

A high-quality test suite controls these factors:

| Factor | How to control |
| --- | --- |
| **Real cookie sent** | In HTTP integration tests, send the `remember-me` cookie **without JSESSIONID** and without injecting users via `@WithMockUser`. |
| **Isolated identities** | Use dedicated fake test usernames so mismatches do not wipe real users' tokens. |
| **Signing key** | Fixed test-only key inside test environments; production keys live in a secret manager. |
| **Password hash** | For hash-based, use a stable `UserDetailsService` and matching key/password; do not mutate the user mid-test unless testing password change. |
| **Persistent store** | `InMemoryTokenRepositoryImpl` is for unit tests only; production uses a durable DB. |
| **Time** | Use tokens constructed with past `Date`s or validly signed past expiries; never sleep for days. |
| **Cookie jar** | Snapshot the old token before auto-login; keep new `Set-Cookie` values separate. |
| **Session** | Never let an interactive login session mask the remember-me path. |
| **Status/entry point** | Align assertions with the real filter chain; do not mix up 401/302/403. |
| **Side effects** | Assert repository state after rotation/mismatch/revocation, not HTTP status alone. |
| **Data safety** | Never print tokens, cookies, series, passwords, or hashes to logs or CI artifacts. |
| **Concurrency** | Include parallel-request tests; do not treat every mismatch as proof of attack. |

One crucial reminder: **browser cookie expiration** and **server token expiration** must be tested separately. Custom clients or attackers can still submit raw cookies after a normal browser would have deleted them.

## 8. Spring Boot 3.x / Java 17+ / JUnit 5 test project

The example below invokes **RememberMeServices directly along with protected hooks exposed in a test subclass**, rather than going through a browser. This precisely verifies token signatures, expiration, series rotation, mismatches, and repository side effects without needing a real HTTP session. All tokens are synthetic; tests need no external database.

In a Spring Boot 3.x Gradle project with plugin and dependency management configured:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

This is a **snippet for an existing `build.gradle`**, not a standalone build file. `spring-boot-starter-test` supplies JUnit 5 and Spring Mock request/response objects; `spring-boot-starter-security` supplies the remember-me services.

File to create in the project:

~~~text
src/test/java/com/example/remembertest/RememberCookieSecurityTest.java
~~~

### 8.1. Test fixture and complete tests

~~~java
package com.example.remembertest;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.Date;

import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.authentication.rememberme.CookieTheftException;
import org.springframework.security.web.authentication.rememberme.InMemoryTokenRepositoryImpl;
import org.springframework.security.web.authentication.rememberme.PersistentRememberMeToken;
import org.springframework.security.web.authentication.rememberme.PersistentTokenBasedRememberMeServices;
import org.springframework.security.web.authentication.rememberme.RememberMeAuthenticationException;
import org.springframework.security.web.authentication.rememberme.TokenBasedRememberMeServices;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RememberCookieSecurityTest {

    private static final String KEY = "only-a-test-secret-not-for-production";
    private static final String USERNAME = "student";
    private static final String STORED_PASSWORD = "{noop}demo-password";
    private static final String COOKIE_NAME = "remember-me";
    private static final int TWO_WEEKS = 14 * 24 * 60 * 60;

    private static UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername(USERNAME)
                .password(STORED_PASSWORD)
                .roles("USER")
                .build()
        );
    }

    private static Authentication authenticatedUser() {
        UserDetails user = users().loadUserByUsername(USERNAME);
        return UsernamePasswordAuthenticationToken.authenticated(
            user, null, user.getAuthorities());
    }

    private static MockHttpServletRequest withCookie(Cookie cookie) {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.setCookies(cookie);
        return request;
    }

    private static MockHttpServletRequest optInLoginRequest() {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addParameter("remember-me", "true");
        return request;
    }

    private static Cookie issuedCookie(TokenBasedRememberMeServices service) {
        MockHttpServletResponse response = new MockHttpServletResponse();
        service.loginSuccess(
            optInLoginRequest(), response, authenticatedUser());
        Cookie cookie = response.getCookie(COOKIE_NAME);
        assertNotNull(cookie);
        return cookie;
    }

    private static class InspectableHash extends TokenBasedRememberMeServices {
        InspectableHash() {
            super(KEY, users());
            setTokenValiditySeconds(TWO_WEEKS);
            afterPropertiesSet();
        }

        // Expose protected hook solely to mint a VALID signature for expiry tests.
        String sign(long expiresAt, String username, String storedPassword) {
            return makeTokenSignature(expiresAt, username, storedPassword);
        }
    }

    private static class InspectablePersistent
            extends PersistentTokenBasedRememberMeServices {
        InspectablePersistent(InMemoryTokenRepositoryImpl repository) {
            super(KEY, users(), repository);
            setTokenValiditySeconds(TWO_WEEKS);
            afterPropertiesSet();
        }

        // Unit test only: bypass autoLogin() wrapper to assert
        // exact exception types and repository side effects.
        UserDetails inspect(String series, String token) {
            return processAutoLoginCookie(
                new String[] {series, token},
                new MockHttpServletRequest(),
                new MockHttpServletResponse()
            );
        }
    }

    private static class StoreFixture {
        final InMemoryTokenRepositoryImpl repository =
            new InMemoryTokenRepositoryImpl();
        final InspectablePersistent service =
            new InspectablePersistent(repository);

        void put(String series, String token, Date lastUsed) {
            repository.createNewToken(
                new PersistentRememberMeToken(
                    USERNAME, series, token, lastUsed));
        }
    }

    private static String base64(String text) {
        return Base64.getEncoder().encodeToString(
            text.getBytes(StandardCharsets.UTF_8));
    }

    @Test
    void hashCookieCanAuthenticateWithoutAnHttpSession() {
        InspectableHash service = new InspectableHash();
        Cookie cookie = issuedCookie(service);

        Authentication result = service.autoLogin(
            withCookie(cookie), new MockHttpServletResponse());

        assertNotNull(result);
        assertEquals(USERNAME, result.getName());
        assertTrue(result.isAuthenticated());
    }

    @Test
    void hashCookieTamperingIsRejected() {
        InspectableHash service = new InspectableHash();
        Cookie original = issuedCookie(service);

        String raw = new String(
            Base64.getDecoder().decode(original.getValue()),
            StandardCharsets.UTF_8);
        String[] fields = raw.split(":", -1);
        assertTrue(fields.length == 4 || fields.length == 3);

        // Keep valid Base64 format, but replace the signature part.
        fields[fields.length - 1] = "bad-signature";
        Cookie tampered = new Cookie(
            COOKIE_NAME, base64(String.join(":", fields)));

        MockHttpServletResponse response = new MockHttpServletResponse();
        Authentication result = service.autoLogin(
            withCookie(tampered), response);

        assertNull(result);
        Cookie cancelled = response.getCookie(COOKIE_NAME);
        assertNotNull(cancelled);
        assertEquals(0, cancelled.getMaxAge());
    }

    @Test
    void expiredHashCookieIsRejectedEvenWithValidSignature() {
        InspectableHash service = new InspectableHash();

        long past = System.currentTimeMillis()
            - Duration.ofDays(2).toMillis();
        String signature =
            service.sign(past, USERNAME, STORED_PASSWORD);

        // Three-field format remains supported by Spring Security to read
        // legacy cookies lacking algorithmName.
        String oldButSigned = base64(
            USERNAME + ":" + past + ":" + signature);
        Cookie expired = new Cookie(COOKIE_NAME, oldButSigned);

        assertNull(service.autoLogin(
            withCookie(expired), new MockHttpServletResponse()));
    }

    @Test
    void hashCookieCanBeReplayedWhileStillValid() {
        InspectableHash service = new InspectableHash();
        Cookie original = issuedCookie(service);

        // Two requests WITHOUT attaching the old HttpSession;
        // both present the exact same remember-me cookie.
        Authentication first = service.autoLogin(
            withCookie(original), new MockHttpServletResponse());
        Authentication second = service.autoLogin(
            withCookie(original), new MockHttpServletResponse());

        assertNotNull(first);
        assertNotNull(second);
        assertEquals(USERNAME, first.getName());
        assertEquals(USERNAME, second.getName());
    }

    @Test
    void persistentValidUseRotatesTokenButKeepsSeries() {
        StoreFixture f = new StoreFixture();
        f.put("series-1", "token-old", new Date());

        UserDetails user = f.service.inspect(
            "series-1", "token-old");

        PersistentRememberMeToken rotated =
            f.repository.getTokenForSeries("series-1");
        assertEquals(USERNAME, user.getUsername());
        assertNotNull(rotated);
        assertEquals("series-1", rotated.getSeries());
        assertNotEquals("token-old", rotated.getTokenValue());
    }

    @Test
    void replayOfOldPersistentTokenDetectsMismatchAndRevokes() {
        StoreFixture f = new StoreFixture();
        f.put("series-2", "token-before-rotation", new Date());

        // Client A uses valid cookie and makes the server rotate the token.
        f.service.inspect("series-2", "token-before-rotation");
        PersistentRememberMeToken changed =
            f.repository.getTokenForSeries("series-2");
        assertNotNull(changed);
        assertNotEquals(
            "token-before-rotation", changed.getTokenValue());

        // Client B holds old copy: same series but wrong token.
        assertThrows(CookieTheftException.class, () ->
            f.service.inspect(
                "series-2", "token-before-rotation"));

        // Standard implementation deletes the username's tokens on mismatch.
        assertNull(f.repository.getTokenForSeries("series-2"));
    }

    @Test
    void persistentUnknownSeriesIsRejected() {
        StoreFixture f = new StoreFixture();

        assertThrows(RememberMeAuthenticationException.class, () ->
            f.service.inspect("series-not-stored", "any-token"));

        // No record exists to attribute the failure to a specific user.
        assertNull(f.repository.getTokenForSeries("series-not-stored"));
    }

    @Test
    void expiredPersistentRecordIsRejectedAndNotAutoDeleted() {
        StoreFixture f = new StoreFixture();
        Date old = Date.from(Instant.now().minus(Duration.ofDays(30)));
        f.put("series-expired", "correct-old-token", old);

        assertThrows(RememberMeAuthenticationException.class, () ->
            f.service.inspect(
                "series-expired", "correct-old-token"));

        // Spring Security rejects because it expired, yet does not
        // automatically purge expired records from the repository.
        assertNotNull(f.repository.getTokenForSeries("series-expired"));
    }

    @Test
    void persistentTamperWithKnownSeriesTriggersTheftSignal() {
        StoreFixture f = new StoreFixture();
        f.put("series-known", "real-token", new Date());

        assertThrows(CookieTheftException.class, () ->
            f.service.inspect("series-known", "modified-token"));

        assertNull(f.repository.getTokenForSeries("series-known"));
    }

    @Test
    void persistentExplicitRevocationPreventsFurtherLogin() {
        StoreFixture f = new StoreFixture();
        f.put("series-revoked", "token-before-revoke", new Date());

        f.repository.removeUserTokens(USERNAME);

        assertNull(f.repository.getTokenForSeries("series-revoked"));
        assertThrows(RememberMeAuthenticationException.class, () ->
            f.service.inspect(
                "series-revoked", "token-before-revoke"));
    }
}
~~~

### 8.2. Why separate service unit tests from HTTP tests?

The `InspectablePersistent.inspect(...)` tests **call the `processAutoLoginCookie` hook directly** to assert exact `CookieTheftException` types and `PersistentTokenRepository` side effects. Going through public `RememberMeServices.autoLogin(...)` and `RememberMeAuthenticationFilter`, certain errors may be caught and converted into “no auto-login”, the cookie gets cleared, and the request proceeds to the authentication entry point. Never assume an HTTP client receives a response body naming the exception.

Keep two assertion layers in mind:

- **Service/repository unit tests:** exception types, token rotation, record presence/absence, signature/expiry.
- **MockMvc/integration tests:** whether the cookie actually reaches the filter, whether `SecurityContext` stays empty or recovers, whether endpoints permit remembered authentication, and valid HTTP statuses/redirects.

In `hashCookieTamperingIsRejected`, the test swaps the signature for an invalid string while preserving valid Base64 and delimiter structure. That is an **integrity test**, not a malformed-Base64 decoding test. Write a separate test for non-Base64 cookies if your application adds a custom cookie decoder.

In `expiredHashCookieIsRejectedEvenWithValidSignature`, the legacy 3-field cookie supported by Spring Security 6.x constructs a **past expiry with a valid signature**. This isolates expiry enforcement from signature mismatch without real-time waiting.

In `hashCookieCanBeReplayedWhileStillValid`, both auto-login attempts succeeding **is not a test failure**: it demonstrates the hash-based implementation's limitation and why persistent tokens/step-up should be considered.

Persistent tests use `InMemoryTokenRepositoryImpl` only inside the test suite. It is unsuitable for production and does not simulate database locking, transactions, or replication.

### 8.3. Running the tests

~~~bash
./gradlew test --tests com.example.remembertest.RememberCookieSecurityTest
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests com.example.remembertest.RememberCookieSecurityTest
~~~

If the project uses the right Spring Boot 3.x, Java 17+, Spring Security 6.x, and section 8 dependencies, the assertions express expected behavior; Gradle normally reports `BUILD SUCCESSFUL` when all pass. **Do not treat this as an observed execution log**: actual results depend on your exact versions and environment.

This test code is JUnit code, not a `public static void main(...)` application compiled with plain `javac`; it requires Spring Security, Spring Test, and JUnit on the classpath. Never use dummy keys/usernames/passwords from examples in production configurations.

## 9. Adding HTTP-layer tests with MockMvc

Unit testing `RememberMeServices` still does not prove the real application's filter chain and authorization rules. At the HTTP layer, tests should:

1. Perform interactive login with `remember-me=true` and a valid CSRF token when form login enables CSRF.
2. Capture the `remember-me` cookie from the response and store it **in an isolated fixture**.
3. On the next request, **omit `JSESSIONID` or `MockHttpSession` from the login**.
4. Call an endpoint requiring `authenticated()` only.
5. Assert the principal is restored by remember-me.
6. Call a sensitive endpoint using `fullyAuthenticated()`; the remembered user must be required to re-authenticate interactively.
7. Invalidate the token (expiry/revocation/tampering) and assert the endpoint no longer accepts remember-me.

Example of building the request in a Spring Boot test using `MockMvc` (this is a fragment requiring a test fixture and matching filter chain configuration):

~~~java
MvcResult login = mvc.perform(
        post("/login")
            .with(csrf())
            .param("username", "student")
            .param("password", "demo-password")
            .param("remember-me", "true"))
    .andExpect(status().is3xxRedirection())
    .andReturn();

Cookie remember = login.getResponse().getCookie("remember-me");
assertNotNull(remember);

// DO NOT call .session(...) on the request below.
// Send only the remember-me cookie, with no authenticated session.
mvc.perform(get("/account/me").cookie(remember))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.remembered").value(true));
~~~

This snippet is **not a standalone test file**: it needs `@SpringBootTest`, `@AutoConfigureMockMvc`, a `SecurityFilterChain` bean enabling `formLogin()`/`rememberMe()`, a demo `UserDetailsService`, a controller returning `remembered`, and MockMvc static imports. With proper web session configuration, the test proves browsers do not need to send the old session to auto-login via remember-me.

**Note:** `@WithMockUser` or `SecurityMockMvcRequestPostProcessors.user(...)` injects authentication directly onto the request, causing `RememberMeAuthenticationFilter` to skip running. Avoid them in primary remember-me tests.

### 9.1. Integration tests should use two independent browser clients

For stolen and replayed tokens, use two separate HTTP clients/cookie jars:

~~~text
Client A — legitimate
  Login + remember-me -> token R1
  Session cookie excluded from auto-login tests

Client B — simulated stolen-cookie actor
  Receives copy of R1 in test environment only

Verify in sequence:
  1) B sends R1
  2) A sends R1
  3) Did A or B receive new cookie R2?
  4) Did the store revoke?
  5) Was a new session created before/after auto-login?
  6) Could fullyAuthenticated endpoint permissions be bypassed?
~~~

With persistent tokens, **the A/B order can be reversed**, yet only the first client to use R1 succeeds before rotation. The second client sending R1 triggers a mismatch. Never print raw tokens in CI reports; emit booleans, opaque fixture IDs, and correlation IDs.

### 9.2. Cookie jars must be controlled explicitly

HTTP client libraries can automatically overwrite old cookies with incoming `Set-Cookie` headers. That helps normal usage but invalidates replay tests.

Two **separate** scenarios are needed:

- **Normal flow:** update the cookie jar after each response; use R2 then R3, verifying auto-login continues working.
- **Attack simulation:** snapshot R1 up front and keep it frozen in another client; after the server rotates to R2, resend R1 and assert rejection/mismatch.

Never decode tokens in the browser and edit fields in production frontend code. Constructing synthetic token inputs belongs solely in test harnesses/unit tests, never in business code.

## 10. E2E procedure for expired cookies

To test browser behavior, configure a staging environment with an intentionally short remember-me validity, e.g., 2 minutes. Avoid slowing every CI run by sleeping 2 minutes; use clock-assisted integration tests or a dedicated test profile.

**Case A — Browser drops the cookie automatically:**

~~~text
Login with Remember me
  ↓
Set-Cookie: remember-me=...; Max-Age=120
  ↓
Wait in test profile / simulate browser expiration
  ↓
Cookie is no longer sent by the browser
  ↓
Protected endpoint requires logging in again
~~~

**Case B — Client still sends an expired token:**

~~~text
Create an expired server-side token in test fixture
  ↓
Send Cookie: remember-me=<expired-token>
  ↓
Spring Security does not issue RememberMeAuthenticationToken
  ↓
Protected endpoint requires logging in again
~~~

Case B is the **more critical security guarantee**: browser compliance does not substitute for server-side expiration checks. For persistent records, Case B builds a row with an old `last_used` date in the repository. For hash-based cookies, build a payload with a past timestamp **and a valid signature**, like `InspectableHash.sign(...)`.

Never alter production clocks or real user cookies/tokens just to prove expiration.

## 11. Logout, password reset, and token revocation

Some “stolen/replayed cookie” tests produce misleading results if you only inspect the logout response:

- Logout invalidates `HttpSession`, yet if the remember-me cookie stays valid and un-cleared, the next request can auto-login again.
- Hash-based remember-me logout typically clears the cookie on the current browser, **without a DB token list to automatically invalidate all stolen copies**.
- With the standard persistent-token implementation, when the logout handler receives an appropriate `Authentication`, it can call `removeUserTokens(username)`, revoking multiple tokens for the user. This differs from “forget current device only”.
- Password resets can invalidate old hash-based cookies because signatures depend on the password hash. Persistent-token rows **are not automatically deleted just by changing the password**: the app needs an explicit revocation policy.
- Rotating the signing key in hash-based remember-me also invalidates old cookies, yet requires a key rotation plan and consistent secrets across nodes.

Tests should prove at least:

| Event | Hash-based | Persistent-token |
| --- | --- | --- |
| Current logout | Browser cookie cleared; stolen copy may still remain valid | Browser cookie cleared; DB tokens revoked per handler/policy |
| Password changed | Tokens signed with old password become invalid | Explicitly delete persistent tokens per policy |
| User locked/disabled | `UserDetailsService`/checker must block auto-login | Same; verify user status checks |
| Remember-me token revoked | No built-in per-token revocation | DB lookup finds no series, rejects |
| HTTP session cleared | Remember-me cookie can auto-login anew | Same if persistent token remains valid |
| Endpoint demands full login | `fullyAuthenticated()` rejects remembered-only | Same |

**Revoking remember-me does not necessarily destroy already authenticated HTTP sessions.** If the product requires “Log out all devices”, coordinate session stores/registries, remember-me tokens, API tokens, and other mechanisms.

## 12. Testing cookie attributes and browser security

A strong token sent with the wrong cookie scope is still dangerous. Inspect `Set-Cookie` in tests or DevTools:

| Attribute | Security expectation |
| --- | --- |
| `Secure` | Production sends only over HTTPS. |
| `HttpOnly` | JavaScript normally needs no read access to the remember-me token; enable to curb XSS theft. |
| `SameSite` | Match same-site/cross-site topology; do not enable `None` lightly; maintain separate CSRF protection. |
| `Domain` | Do not broaden to unnecessary subdomains. |
| `Path` | Restrict to suitable route/host; logout must clear cookies with matching Path/Domain. |
| `Max-Age` / `Expires` | Browser lifetime aligned with server token validity, no longer than necessary. |
| Cookie name | Name must match filter/service configuration without colliding with other cookies. |

**Do not confuse** the `JSESSIONID` session cookie with the `remember-me` cookie. `server.servlet.session.cookie.*` settings normally control the session cookie; remember-me is managed by `RememberMeServices`. Inspect each cookie individually rather than assuming identical flags.

CORS is also not a defense against cookie theft or CSRF. Whenever a backend relies on cookies automatically attached by browsers, keep CSRF protection on state-changing requests. When browsers call cross-origin APIs, evaluate `credentials: "include"`, CORS allowlists, and cookie `SameSite` separately.

Regarding XSS, `HttpOnly` impedes JS from reading cookies, yet does not stop scripts running on a trusted origin from issuing requests under the user's identity. Enforce CSP, output encoding, and DOM-injection defenses.

## 13. Testing HTTP status: expectations by authentication level

A sensitive endpoint might have the policy:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/account/sensitive").fullyAuthenticated()
    .requestMatchers("/account/**").authenticated()
    .anyRequest().permitAll()
);
~~~

From this:

| State | `GET /account/me` | `GET /account/sensitive` |
| --- | --- | --- |
| Fully authenticated session | Allowed | Allowed, provided matching authorities exist |
| Valid remember-me only | Allowed | Requires fresh interactive login / step-up |
| Tampered cookie | Not auto-logged-in | Access denied |
| Expired cookie | Not auto-logged-in | Access denied |
| Replayed and revoked persistent token | Not auto-logged-in after revocation | Access denied |
| No cookie | Unauthenticated | Unauthenticated |

In form-login web apps, unauthenticated or remembered-only access to a protected endpoint may trigger a **302 redirect** to login; at an API entry point, it may return **401**. If a request violates CSRF, it may receive **403** before reaching the remember-me handler. Thus **never treat 403/401/302 status codes as sole proof of whether a token was valid**; test the service/repository and principal/trust level to verify root cause.

A remembered user can have `Authentication.isAuthenticated()==true`, yet `AuthenticationTrustResolver.isRememberMe(authentication)` is true and `isFullyAuthenticated(authentication)` is false. Never rely solely on the `isAuthenticated` flag to allow password changes, payments, MFA toggles, or account deletion.

## 14. Debugging when tests fail

| Symptom | Possibility | How to check |
| --- | --- | --- |
| Tampered cookie still returns 200 | Old session or `@WithMockUser` already authenticating | Drop JSESSIONID/mock session; verify filter ran. |
| Expired cookie still “accepted” | Only tested browser Max-Age, not server check | Send raw expired token directly to service. |
| Stale persistent replay still 200 | HTTP client auto-updated new token | Keep **copy of old token** in an independent cookie jar. |
| Persistent mismatch wipes multiple devices | `removeUserTokens(username)` was invoked | Verify revocation scope and logout/incident policy. |
| Unknown series reported as theft | Test mistakenly attached token to an existing series | Generate a series genuinely absent from repository. |
| Token expired yet row remains | Cleanup has not run | That can be standard behavior; test cleanup job separately. |
| Yesterday's hash cookie suddenly breaks | Password hash or signing key changed | Check keys across deployments and user updates. |
| Remember-me cookie missing from response | Not opted in, wrong param, login failed | Check loginSuccess, form params, cookie flags. |
| Remember-me works yet sensitive endpoint redirects | `fullyAuthenticated()` is working | This may be expected behavior. |
| Parallel persistent test flakes | Rotation races against concurrent old-token requests | Test with barrier/2 clients; evaluate race handling. |
| Logged out yet auto-logs back in | Cookie or DB token not cleared | Check logout handlers, Path/Domain, and policy. |
| Local test passes, production drops cookie | HTTPS, Secure, SameSite, proxy, third-party browser limits | Test on real origin and DevTools Network. |

### 14.1. Safe logging principles

Never log the following:

- Raw `Cookie`, `Set-Cookie`, or `Authorization` headers.
- Full `remember-me`, `JSESSIONID`, or series/token values.
- Plaintext passwords, BCrypt hashes, or signing keys.
- URLs containing tokens/cookies or debug response bodies echoing tokens.

Logs should include correlation ID, mechanism type (hash-based/persistent), error category (expired/tampered/unknown-series/mismatch), masked/minimized username or user ID per privacy policy, and revocation status. For `CookieTheftException`, log “suspected replay” rather than asserting confirmed theft.

## 15. Testing system failures and data consistency

The four main groups do not cover every risk. For persistent-token implementations backed by SQL/Redis, also test:

1. **Repository timeout during auto-login:** requests must never receive access if tokens cannot be verified. Never treat DB errors as valid cookies.
2. **Token update failure after validation:** never report rotation success if the DB failed to persist the new token.
3. **Two nodes updating the same series concurrently:** ensure consistency/transaction semantics and test races; default repositories do not substitute for distributed locking designs.
4. **Row deleted between read and update:** requests must fail closed or have clear error handling.
5. **Clock skew:** nodes must synchronize time; `tokenValiditySeconds` is enforced server-side.
6. **User disabled/locked after token issuance:** must check current user status, not just token validity.
7. **Secret rotation in hash-based:** new keys intentionally invalidate old cookies; prevent keys from changing accidentally.
8. **Token cleanup job:** expired rows are purged on schedule without deleting still-valid tokens.
9. **Cookie domain/path mismatch during logout:** tokens not cleared by the browser can auto-login again.
10. **SecurityContext/session persistence after remembered auto-login:** ensure session fixation/creation and step-up rules remain intact rather than promoting remembered auth to full authentication simply because a new session was created.

In particular, restoring a remembered user into a new session **does not automatically turn that authentication into fully authenticated**. Authorization must still rely on trust levels and policy.

## 16. Summary QA matrix for the lab

| Case ID | Cookie type | Setup | Expectation |
| --- | --- | --- | --- |
| RM-EXP-01 | Hash | Expired cookie timestamp, valid signature | Auto-login rejected. |
| RM-EXP-02 | Persistent | Record older than `tokenValiditySeconds`, valid token | Rejected; row may remain in store. |
| RM-EXP-03 | Both | Browser omits cookie past Max-Age | Endpoint demands login; no auto-auth. |
| RM-TAMP-01 | Hash | Altered signature, valid format | No auto-login; cookie cancelled when appropriate. |
| RM-TAMP-02 | Hash | Invalid Base64/field format | No auto-login; no leaked stack trace. |
| RM-TAMP-03 | Persistent | Existing series, wrong token | Mismatch signal; revoked per standard implementation. |
| RM-TAMP-04 | Persistent | Nonexistent series | Rejected; no theft conclusion. |
| RM-REPLAY-01 | Hash | Resend valid cookie across two clients | Both **may** auto-login; document risk. |
| RM-REPLAY-02 | Persistent | Valid S/T1 → updated to S/T2 | Auto-login succeeds; series preserved. |
| RM-REPLAY-03 | Persistent | Resend S/T1 after rotation | `CookieTheftException` in service; user tokens revoked. |
| RM-REPLAY-04 | Persistent | Use S/T2 after rotation | Auto-login continues and rotates to T3. |
| RM-THEFT-01 | Hash | Cookie copy used from client B | Usable until expiry or key/password change. |
| RM-THEFT-02 | Persistent | Client B uses cookie before client A | B may succeed first; A hits mismatch later. |
| RM-RACE-01 | Persistent | Two concurrent requests using S/T1 | Evaluate false positives and handling policy. |
| RM-REVOKE-01 | Persistent | Server deletes token record | Old cookie can no longer authenticate. |
| RM-REVOKE-02 | Hash | Password/key changed | Cookie signed under old inputs becomes invalid. |
| RM-LOGOUT-01 | Both | Logout via proper handler, client sends new request | No auto-login via cleared/revoked cookie. |
| RM-TRUST-01 | Both | Remember cookie only; `fullyAuthenticated()` endpoint | Prompts interactive re-login. |
| RM-SESSION-01 | Both | Drop JSESSIONID while keeping remember-me | Exercises remember-me path rather than session. |
| RM-OPS-01 | Persistent | Store error or unavailable | Fail closed; audit and return status per policy. |

## 17. Summary and design decisions

The real lesson is not merely “assert the cookie returns 401”, but **proving the system handles credential states properly**:

- **Expired:** server rejects even when a client keeps sending the raw cookie.
- **Tampered:** signature or DB token mismatches; no Authentication granted.
- **Stolen:** valid copies can be used; hash-based does not detect replay on its own, while persistent-token only surfaces a signal when an old value reappears after rotation.
- **Replayed:** preserve an immutable copy of R1 for tests; do not let cookie jars overwrite it with R2 and distort results.
- **Persistent-token mismatch:** can trigger `CookieTheftException` and revoke user tokens, though concurrency can emit a similar signal.
- **Reject remembered-only at sensitive endpoints:** `fullyAuthenticated()` / step-up/MFA must be tested independently.
- **Never confuse session cookies with remember-me cookies:** tests must drop old sessions to exercise `RememberMeAuthenticationFilter` properly.

Prioritize **service + repository unit tests** to verify expiry, integrity, rotation, exceptions, and revocation; then add **MockMvc/E2E tests with isolated cookie jars** to prove browser/filter/authorization behavior. Use synthetic data, never log secrets, and combine HTTPS, cookie security, CSRF protection, cleanup, operational alerting, and incident response procedures.

### References

- Spring Security 6.5 Reference — Remember-Me Authentication: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/rememberme.html
- Spring Security 6.5 API — TokenBasedRememberMeServices: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/TokenBasedRememberMeServices.html
- Spring Security 6.5 API — PersistentTokenBasedRememberMeServices: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/PersistentTokenBasedRememberMeServices.html
- Spring Security 6.5 API — AbstractRememberMeServices: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/AbstractRememberMeServices.html
- Spring Security 6.5 API — PersistentTokenRepository: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/PersistentTokenRepository.html
- Spring Security 6.5 API — PersistentRememberMeToken: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/PersistentRememberMeToken.html
- Spring Security 6.5 Reference — Servlet Authentication and Session Management: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security 6.5 Reference — CSRF: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- OWASP — Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OWASP — Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
