# Linking and Unlinking External Accounts with Internal Identities

## 1. Core Concepts and Requirements

A local account is an identity record managed by your application with a stable ID, business data, roles, and lifecycle state. An external identity is an identity authenticated by an OpenID Provider (OIDC) or an appropriate OAuth2 provider. **Account linking** associates a verified external identity with a local account whose owner has authenticated and consented. **Unlinking** removes that relationship so the external identity can no longer sign in to the local account via that mapping.

Example: Alice has local user ID `u-123`. Alice signs in with her password/passkey and chooses to link an OIDC account so she can use SSO next time. The backend must verify: Alice of `u-123` initiated the request, the OIDC identity truly belongs to Alice, the OAuth transaction belongs to that exact linking session, and the external identity does not already belong to another local user.

**Never auto-link by email alone.** OIDC Core defines `iss` + `sub` as the stable identifier pair; `email`, `email_verified`, `preferred_username`, and display names carry no guarantee of uniqueness, immutability, or non-recycling. `email_verified=true` does not prove the user consented to linking into this local account.

Key distinctions in this lesson:

| Operation | Meaning | NOT equivalent to |
| --- | --- | --- |
| External login | OP authenticates and the app looks up an existing link to resolve the local user | Automatically creating a link by email |
| Link account | Add an external identity → local ID mapping with consent and fresh authentication | Merging two local accounts |
| Unlink account | Revoke an existing mapping | Deleting the account at the OP or deleting local data |
| OAuth authorized client | Store access/refresh tokens to call external APIs | Login-linking key |
| Merge accounts | Consolidate data, roles, and billing of two local accounts | A normal step of OAuth2 login |

**Learning outcomes:** pick the right external key, design link/unlink flows resistant to account takeover, handle sessions and provider tokens after changes, avoid race conditions, and understand what Spring Security provides versus what belongs to business logic.

## 2. Choosing the Identity Key and a Safe Schema

For OIDC, the primary key for linking is:

~~~text
local_user_id = "u-123"
external_key = (
    issuer  = "https://idp.example.test/realms/main",
    subject = "00uAK1pQ"
)
~~~

`issuer` must be the issuer from a verified ID token, never a URI supplied by an unauthenticated request. `subject` is the verified subject within that issuer. Two distinct issuers can emit the same `sub`. A provider using pairwise subjects may issue different `sub` values per client ID or sector; plan a reliable migration if changing client IDs/sectors rather than falling back to email matching.

Reference PostgreSQL schema:

~~~sql
CREATE TABLE local_account (
    id VARCHAR(64) PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    security_version BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE external_identity (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    local_user_id VARCHAR(64) NOT NULL
        REFERENCES local_account(id),
    issuer VARCHAR(512) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    registration_id VARCHAR(120) NOT NULL,
    linked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (issuer, subject)
);

CREATE INDEX idx_external_identity_user
    ON external_identity(local_user_id);
~~~

This schema is **illustrative**, not a full migration. If using soft deletes, use ACTIVE/REVOKED statuses, audits/tombstones, and suitable unique constraints or partial unique indexes so **one external key belongs to at most one ACTIVE local account**. A database unique index matters far more than checking `findByIssuerAndSubject` in application code: two concurrent requests can both observe “not yet present.”

If a provider **supports only OAuth2** without an OIDC ID token, use an immutable identifier from a trusted resource endpoint paired with a properly configured **provider/tenant namespace**. Never assume an OAuth2 access token carries an OIDC-semantic `sub`; consult each provider's documentation.

Never turn email, picture, scope, access tokens, or refresh tokens into the ownership key for a local account. Those fields have separate lifecycles and assurance guarantees.

## 3. Linking Flow: Both Local Account and External Identity Must Be Proven

### Step A — The Local Account Owner Initiates Linking

1. Allow `POST /settings/external-links/start` only from an authenticated local session; enforce **CSRF** protection for browsers.
2. Require **fresh re-authentication/step-up** commensurate with risk, especially if the account has MFA. A login cookie from days ago is insufficient to add a new login path.
3. Read `localUserId` from the trusted internal principal, **never from body/query parameters**. Verify the account is ACTIVE, the provider is allowed, linking is permitted, and no policy blocks it.
4. The user selects the provider and confirms consent. The server creates a short-lived pending `purpose=LINK` record storing user ID, registration ID, session binding, security version, and protected nonce/state.
5. Initiate **Authorization Code + PKCE** and OIDC `nonce` per protocol. `state` must be random, bound to the transaction, and single-use; the redirect URI must come from a registered allowlist.

### Step B — The External Identity Is Verified

6. The browser redirects to the chosen issuer. The OP authenticates the external user and returns `code` and `state` to the callback.
7. The OAuth/OIDC client validates the response against the request: `state`/PKCE, issuer, redirect URI, `nonce` when present, ID token signature/algorithm, `iss`, `aud`, and `exp`/timestamps; use standard library validators instead of parsing claims from URLs manually.
8. Extract `(validated iss, validated sub)`. **Never use email or nickname** to choose which local account gets linked.
9. Load the server-side pending LINK intent and **re-bind/verify** it against the authenticated local session, purpose, provider, user, and version. If the user logged out and signed into a different account in another tab, reject the callback.
10. Use a DB transaction + unique constraint to insert the mapping. If the external key already belongs to another user, return a conflict without silently merging or transferring ownership. If it already belongs to this same user, handle idempotently per policy.
11. Consume the pending intent once, audit and notify via the previously verified channel, review session/security version, and render the updated Settings page.

~~~text
Authenticated local session (Alice, u-123)
    -> POST start LINK, CSRF + fresh step-up
    -> Pending LINK[u-123, provider-A, session, state, expiry]
    -> Redirect OP A + PKCE/nonce
    -> OP callback: code + state
    -> Validate OAuth2/OIDC transaction
    -> Validated issuer + subject
    -> Re-check pending user, local session, purpose, expiry
    -> DB unique(issuer,subject) + atomic insert
    -> Notify, audit, cleanup pending
~~~

### What Should a Pending Intent Contain?

| Field | Purpose |
| --- | --- |
| `id` and `purpose=LINK` | Distinguishes from ordinary login; prevents callback misrouting |
| `localUserId` | Target captured from internal auth, immutable across the flow |
| `registrationId` and issuer allowlist | Defends against provider mix-up |
| `stateHash` | Single-use transaction lookup without storing raw state in DB/logs |
| `nonce` + PKCE verifier/challenge | Binds the OIDC token and authorization code |
| `sessionBinding` | Prevents completing the callback under a different user's session |
| `securityVersion` | Detects whether the local session was revoked/changed mid-flow |
| `expiresAt`, `consumedAt` | TTL and replay protection |
| `returnPath` allowlisted | Prevents open redirects to attacker domains |

`state`, PKCE, and `nonce` complement one another and do not fully replace each other. When supporting multiple authorization servers, defend against **authorization-server mix-up** (such as distinct per-provider redirect URIs and issuer binding where appropriate). Never accept a dynamic issuer from query parameters to fetch arbitrary keys.

### Example Multi-Tab / Session Swap Risk

Tab A: Alice is logged in and starts linking Google. Tab B: Alice logs out and Bob logs into the same browser. The callback from Tab A returns. If your code simply reads `SecurityContextHolder.getContext().getAuthentication()` during the callback and links Google to the “current user,” it links Alice's identity into Bob's account. Pending LINK must record the **initiating `userId`** and confirm the **current local identity/session still matches**. If session IDs rotate after re-auth, design session binding properly rather than assuming raw `JSESSIONID` never changes.

**Fail closed:** invalid/expired `state`/`nonce`/PKCE, replayed callbacks, untrusted issuers, changed user/session/version, or an external key owned by another local user must never create a mapping. Log safe metadata without logging codes, tokens, or cookies.

## 4. Spring Security 6.x: `oauth2Login` Verifies Identity, Does Not Auto-Link

In a Spring Boot 3.x / Java 17+ app, declare `spring-boot-starter-oauth2-client` and configure trusted providers. Example `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          external-a:
            provider: external-idp
            client-id: demo-client
            client-secret: configured-in-secret-manager
            authorization-grant-type: authorization_code
            scope: [openid, profile, email]
        provider:
          external-idp:
            issuer-uri: https://idp.example.test/realms/main
~~~

URLs under `example.test` are illustrative only, not real IdPs. `client-secret` must come from a secret store or environment variable in production, never hardcoded. For public clients, PKCE and client authentication policies differ.

Baseline configuration:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/login", "/error").permitAll()
            .requestMatchers("/settings/external-links/**")
                .authenticated()
            .anyRequest().authenticated())
        .oauth2Login(Customizer.withDefaults())
        .build();
}
~~~

Import `HttpSecurity`, `SecurityFilterChain`, and `Customizer`. **This is only a snippet enabling login and guarding Settings**, not a full link/unlink system. `.authenticated()` does not enforce fresh MFA/re-auth; the service layer must enforce that policy, and a dedicated callback route must align with the protocol flow.

### Extracting the External ID from a Verified OidcUser

After successful framework OAuth2/OIDC login, Spring Security can populate an `OAuth2AuthenticationToken` whose principal is an `OidcUser`. Extract `issuer + subject` as follows (snippet inside a Java class with imports and method):

~~~java
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

record ExternalKey(String issuer, String subject) {}

static ExternalKey externalKey(OAuth2AuthenticationToken auth) {
    if (!(auth.getPrincipal() instanceof OidcUser oidcUser)) {
        throw new IllegalArgumentException("OIDC identity required");
    }
    var idToken = oidcUser.getIdToken();
    if (idToken.getIssuer() == null
            || idToken.getSubject() == null) {
        throw new IllegalArgumentException("missing issuer/subject");
    }
    return new ExternalKey(
        idToken.getIssuer().toString(),
        idToken.getSubject());
}
~~~

**Limitation:** this snippet reads from the ID token **after** the framework has validated the OIDC flow. Constructing an `OidcIdToken` manually from unverified claims provides zero security. `getEmail()` and `email_verified` are secondary attributes, not identity keys.

### Pitfalls When Using `successHandler` for Linking

`oauth2Login()` is designed as a **sign-in flow**. After callback, it can replace the current Authentication with `OAuth2AuthenticationToken` (the external principal), losing Alice's local principal. Therefore, never write “callback succeeded → call `currentUser()` → insert mapping” if `currentUser()` now points to the external principal.

A sound approach is **separating the LINK flow from LOGIN**, using a server-side pending intent and a dedicated callback built on Spring's OAuth2 client/validator primitives—or carefully customizing `oauth2Login().successHandler(...)` and the authorization request repository bound to the existing session, then restoring/persisting the local `SecurityContext` via `SecurityContextRepository` per policy.

A `successHandler` **by itself** does not make account linking safe. When a callback was meant solely for LINK yet Spring OAuth2Login stored an authorized client/token under the external principal, clean up or re-associate `OAuth2AuthorizedClient` and avoid retaining unnecessary bearer/refresh tokens.

Never hand-roll custom code/token parsers just to preserve the local session; always rely on trusted protocol clients and validators.

### Two Distinct Stores

| Store | What is it for? |
| --- | --- |
| `external_identity(issuer,sub,user_id)` | Determines which local account an external login may access |
| `OAuth2AuthorizedClientService` / repository | Stores OAuth access/refresh tokens for calling provider APIs |
| `SecurityContextRepository` / `HttpSession` | Persists local `Authentication` across HTTP requests |
| Internal user/role store | Manages application permissions and account status |

Losing a refresh token does not automatically remove an identity link; removing a link does not automatically revoke every access token at the IdP. Design each component's lifecycle explicitly.

## 5. Unlinking and Handling Remaining Access Methods

Unlinking is sensitive because it alters how the local account can be accessed. Safe workflow:

1. `POST /settings/external-links/{linkId}/unlink` with CSRF; user authenticated as the local principal.
2. Require fresh re-auth/step-up using a current method, not merely an old cookie session. Verify the account is active.
3. Load the link server-side by ID and assert **`link.localUserId == authenticated localUserId`** (preventing IDOR). Never trust `userId` from a JSON body.
4. Verify that **after unlinking, at least one viable login/recovery method remains**: a verified password/passkey, another ACTIVE external link, or an explicit recovery policy. Counting rows is not enough if another provider is disabled.
5. In a DB transaction: lock the account/link, re-verify owner and version, revoke/delete the mapping, bump `security_version`, and record audit + outbox notification.
6. Force stale sessions to re-evaluate or invalidate them per policy, especially if unlinking due to suspected compromise. Redirect to Settings.
7. Clean up the OAuth authorized client and request grant revocation at the provider when appropriate; never claim “all revoked” without confirmation. Alert the contact verified **before the change**.

~~~text
POST unlink
  -> authenticated local user + CSRF + fresh step-up
  -> check ownership + alternate viable login method
  -> transaction with lock/version
  -> revoke mapping + bump security_version + audit
  -> notify, invalidate stale sessions, cleanup tokens/grants
  -> future login through removed (iss,sub) must fail
~~~

**Never silently delete the last remaining login path.** If a user has only one linked IdP and no password, passkey, or recovery method, block unlinking or guide them through onboarding another method/recovery first. NIST SP 800-63C requires RPs to define policies when an account loses its federated identifier without remaining access/recovery mechanisms.

### Unlink Is Not Logout or Provider Account Deletion

- Unlink: delete/revoke the external → local mapping, blocking future logins via that identity.
- Local logout: clear the local `Authentication`/session.
- Logout at OP: ends the SSO session at the provider, which does not automatically propagate to the app.
- Revoke OAuth grant: restricts the client from continuing to use access/refresh tokens at the provider, depending on provider APIs.
- Delete external account: an action at the provider, outside the app's unlink operation.
- Delete local account: a separate internal data lifecycle (subject to retention/legal constraints).

**After unlinking, forbid fallback auto-linking by email.** If the app uses “just-in-time provisioning,” signing in again with the unlinked external key may guide the user to onboard a new account or run a verified re-linking workflow, but **must never regain access to the old account merely via matching email**.

Send security notifications to contacts verified prior to the change, naming the provider, timestamp, and how to lock the account if unauthorized. Audit metadata should include local user, issuer/provider, operation, timestamp, actor, outcome, and request ID; never log raw codes, refresh/access tokens, or session cookies.

## 6. Standalone Java 17: Checking Uniqueness and Unlink-Last-Method

This is a **domain simulation** assuming the OIDC identity was already verified at the protocol layer. The code does not call an IdP, verify JWT signatures, or enforce HTTP/CSRF; it models solely the rules **never steal someone else's link** and **never remove the last access method**. Compiles with JDK 17 without Spring.

Save as `ExternalLinkDemo.java`:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class ExternalLinkDemo {

    record Key(String issuer, String subject) {
        Key {
            Objects.requireNonNull(issuer);
            Objects.requireNonNull(subject);
            if (issuer.isBlank() || subject.isBlank()) {
                throw new IllegalArgumentException("empty key");
            }
        }
    }

    enum Link { LINKED, ALREADY_LINKED, CONFLICT }
    enum Unlink { UNLINKED, NOT_OWNER, NOT_LINKED, LAST_METHOD }

    private final Map<Key, String> owner = new HashMap<>();

    // Demo is atomic only within one JVM. Production uses a DB transaction
    // with UNIQUE(issuer, subject) and row locking.
    synchronized Link link(String localUserId, Key external) {
        Objects.requireNonNull(localUserId);
        Objects.requireNonNull(external);

        String existing = owner.get(external);
        if (existing == null) {
            owner.put(external, localUserId);
            return Link.LINKED;
        }
        return existing.equals(localUserId)
            ? Link.ALREADY_LINKED
            : Link.CONFLICT;
    }

    synchronized Unlink unlink(
            String localUserId, Key external, boolean viableBackup) {
        Objects.requireNonNull(localUserId);
        Objects.requireNonNull(external);
        String current = owner.get(external);
        if (current == null) return Unlink.NOT_LINKED;
        if (!current.equals(localUserId)) return Unlink.NOT_OWNER;
        if (!viableBackup) return Unlink.LAST_METHOD;
        owner.remove(external);
        return Unlink.UNLINKED;
    }

    public static void main(String[] args) {
        ExternalLinkDemo store = new ExternalLinkDemo();
        Key key = new Key("https://idp.example.test", "sub-77");

        System.out.println("first=" + store.link("alice", key));
        System.out.println("again=" + store.link("alice", key));
        System.out.println("conflict=" + store.link("bob", key));
        System.out.println("wrongOwner="
            + store.unlink("bob", key, true));
        System.out.println("lastMethod="
            + store.unlink("alice", key, false));
        System.out.println("removeWithBackup="
            + store.unlink("alice", key, true));
        System.out.println("newLink="
            + store.link("bob", key));
    }
}
~~~

Compile and run:

~~~bash
javac ExternalLinkDemo.java
java ExternalLinkDemo
~~~

Exact stdout, independent of time or randomness:

~~~text
first=LINKED
again=ALREADY_LINKED
conflict=CONFLICT
wrongOwner=NOT_OWNER
lastMethod=LAST_METHOD
removeWithBackup=UNLINKED
newLink=LINKED
~~~

**Limitations to understand:** `localUserId` must come from an authenticated principal; the demo passes it as a parameter purely to focus on rules. In production, `viableBackup` must be **computed by the service** from account state and remaining login methods inside the same transaction, never read from a form boolean. `synchronized` protects only one JVM, not multiple nodes; use DB unique indexes, transactions/locking, and concurrency tests. After unlinking, the demo lets Bob link the freed identity; real systems may enforce a cooling-off period, tombstone, or dispute review before reassigning an identity that previously belonged to another user.

### JUnit 5 for Domain Rules

With JUnit Jupiter available, create `ExternalLinkDemoTest.java` in the same package as the demo:

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ExternalLinkDemoTest {
    @Test
    void existingExternalIdentityCannotBeStolen() {
        var store = new ExternalLinkDemo();
        var key = new ExternalLinkDemo.Key(
            "https://idp.example.test", "subject");

        assertEquals(ExternalLinkDemo.Link.LINKED,
            store.link("alice", key));
        assertEquals(ExternalLinkDemo.Link.ALREADY_LINKED,
            store.link("alice", key));
        assertEquals(ExternalLinkDemo.Link.CONFLICT,
            store.link("bob", key));
    }

    @Test
    void unlinkChecksOwnerAndLastMethod() {
        var store = new ExternalLinkDemo();
        var key = new ExternalLinkDemo.Key(
            "https://idp.example.test", "subject");
        store.link("alice", key);

        assertEquals(ExternalLinkDemo.Unlink.NOT_OWNER,
            store.unlink("bob", key, true));
        assertEquals(ExternalLinkDemo.Unlink.LAST_METHOD,
            store.unlink("alice", key, false));
        assertEquals(ExternalLinkDemo.Unlink.UNLINKED,
            store.unlink("alice", key, true));
    }

    @Test
    void sameSubFromDifferentIssuerIsDifferentIdentity() {
        var store = new ExternalLinkDemo();
        var first = new ExternalLinkDemo.Key("issuer-1", "same-sub");
        var second = new ExternalLinkDemo.Key("issuer-2", "same-sub");

        assertEquals(ExternalLinkDemo.Link.LINKED,
            store.link("alice", first));
        assertEquals(ExternalLinkDemo.Link.LINKED,
            store.link("bob", second));
    }
}
~~~

Domain tests do not prove OAuth state/nonce/PKCE/session security or production DB concurrency. Those require dedicated integration tests.

## 7. Security Testing and Common Pitfalls

### Test Matrix

| Scenario | Desired outcome |
| --- | --- |
| Link valid new OIDC identity with valid local step-up | One `iss/sub → localUserId` mapping created, audited, and notified |
| Start linking without a local session | Rejected; no auto-link by email |
| Callback after logging out Alice and logging in Bob | Rejected due to pending local identity/session mismatch |
| ID token with wrong issuer/audience/signature/expiry | Rejected; no DB write |
| Invalid `state`, PKCE, or `nonce` | Rejected; no link created |
| Authorization response from a different provider | Rejected (mix-up defense) |
| Duplicate callback with same state | Consumed at most once; no replay |
| External key already owned by another local account | 409/denied; no auto-merge or ownership transfer |
| Two competing link requests across two nodes | Unique constraint lets only one commit win |
| Same email, different `sub` | No auto-link |
| Unlink someone else's link ID | 403/404 per policy; mapping unchanged |
| Unlink with stale un-reauthenticated session | Requires fresh step-up; deletion blocked |
| Unlink the last login method | Blocked or routed to controlled recovery |
| After unlink, old external identity logs in again | Cannot enter old local account even if email matches |
| Stale sessions after unlink | Invalidated or re-evaluated via `security_version` |
| OAuth authorized client/tokens still in store | Cleaned up/revoked per policy; unlink not confused with revoke |
| Disabled provider account or locked local account | No local session granted |
| Role/tenant changed at IdP | Enforced against local policy; never blindly escalates internal privileges |

Never conclude an OAuth flow is secure merely because Spring Security's `oidcLogin()` test postprocessor builds a principal in `MockMvc`; that helper simulates `Authentication` without executing full OAuth callbacks or validating signatures, `state`, PKCE, or `nonce`. Add integration tests with a test IdP/dummy issuer, valid and invalid signed JWTs, two browser sessions, DB transaction concurrency, and token cleanup.

### Ten Major Architectural Mistakes

1. Auto-linking by `email` or `email_verified` without local authenticated consent.
2. Keying by `sub` alone instead of `iss + sub`, causing cross-issuer collisions.
3. Taking the link owner's user ID from request inputs instead of the internal principal.
4. Failing to bind pending state to purpose, session, registration, and expiry.
5. Treating the link callback like standard OAuth login so the external principal overwrites the local account.
6. Skipping reauthentication when adding or removing sensitive login methods.
7. Checking uniqueness only in application code without a DB unique constraint.
8. Automatically merging two local accounts on conflict, leaking data and privileges.
9. Unlinking without blocking fallback email auto-linking or checking remaining access methods.
10. Conflating OAuth tokens/grants, local sessions, and external links: each has its own lifecycle and revocation mechanics.

### Pre-Production Checklist

- [ ] Use a stable local account ID and external key `(validated issuer, validated subject)`.
- [ ] Start linking only from an authenticated local session + CSRF + fresh re-auth/step-up.
- [ ] Store pending LINK state server-side with TTL, `state`, PKCE, `nonce`, provider allowlist, and session binding.
- [ ] Validate full OAuth/OIDC rules at callback; verify local identity and `securityVersion` still match before commit.
- [ ] Enforce DB unique constraints and transactions against duplicates, replays, and ownership conflicts.
- [ ] Verify link ownership and a remaining viable login/recovery path before unlinking.
- [ ] Align logout, token cleanup, and session invalidation with policy without making false revocation claims.
- [ ] Keep tokens, codes, cookies, and unnecessary PII out of notifications and audit logs.
- [ ] Test negative cases: login CSRF, state injection, session swap, races, last-method removal, and stale sessions.
- [ ] Define provider-specific rules for issuer/tenant boundaries, pairwise subjects, and onboarding/merges.

**Conclusion:** Spring Security handles OIDC/OAuth2 authentication mechanics, while **linking external accounts to internal IDs is application security logic**. Always require an authenticated local session, a verified external identity, transactional binding against CSRF/replays, and keying by `iss + sub`. When unlinking, block sign-in through the removed identity without stranding the user without a recovery path.

## 8. Authoritative References

- OpenID Connect Core 1.0, Claim Stability and Uniqueness: https://openid.net/specs/openid-connect-core-1_0.html
- NIST SP 800-63C-4, Account Linking: https://pages.nist.gov/800-63-4/sp800-63c.html
- OWASP Authentication Cheat Sheet — Secure Federated Account Linking: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP OAuth2 Cheat Sheet — state/PKCE/nonce/mix-up: https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html
- Spring Security — OAuth2 Client/Login: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/index.html
- Spring Security — Advanced OAuth2 Login: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/advanced.html
- Spring Security 6.5 — OidcUser Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/core/oidc/user/OidcUser.html
- Spring Security — Authorized Clients: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/client/authorized-clients.html
- RFC 9700 — OAuth 2.0 Security Best Current Practice: https://www.rfc-editor.org/rfc/rfc9700.html
