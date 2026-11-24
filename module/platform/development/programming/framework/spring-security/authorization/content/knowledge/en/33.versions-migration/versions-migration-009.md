# Changes to check, authorize, AuthorizationResult, and Combining Managers

## 1. Objectives and Context

**AuthorizationManager<T>** in Spring Security is the extension point for deciding whether an **Authentication** is permitted to access a protected target. That target may be a **RequestAuthorizationContext** for HTTP, a **MethodInvocation** for methods, or a domain class in a test. The same user may be allowed on one target and denied on another.

When upgrading Spring Security between versions, authorization logic commonly breaks in three places: code still calls the old **check(...)** method; result variables remain tied to **AuthorizationDecision** while the new API returns **AuthorizationResult**; and **AuthorizationManagers.allOf/anyOf** compositions accidentally turn mandatory conditions into optional ones or treat **abstain (null)** as allow.

After this lesson, you will:

1. Accurately distinguish the shift from **check** to **authorize**, when **AuthorizationResult** appeared, and compilation requirements across Spring Security 6.x/7.x.
2. Understand **allow**, **deny**, **abstain**, how to use **verify(...)**, and why null requires an explicit policy.
3. Combine multiple AuthorizationManagers with **allOf**, **anyOf**, and **not** while preserving security boundaries.
4. Build a runnable Java 17+ example with Spring Security 7, integrate managers into HTTP/method security, and run version-migration regression tests.

**Scope:** focuses on `AuthorizationManager` API changes and policy aggregation in Spring Security's authorization module. Authentication, caching, and ACLs are mentioned only where they directly affect decisions.

## 2. API Change Milestones by Version

| Version Line | AuthorizationManager Method | Return Type | Migration Notes |
| --- | --- | --- | --- |
| **6.2–6.3** | **check(Supplier<Authentication>, T)** | **AuthorizationDecision** or null | Uses `check` in code not yet upgraded |
| **6.4–6.5** | **check(...)** deprecated; **authorize(...)** added as a **default method** | `authorize` returns **AuthorizationResult** or null | Update call sites to `authorize`; custom classes in 6.5 must still satisfy abstract `check` |
| **7.0+** | **authorize(...)** is the functional/abstract method; **check(...)** is no longer on the interface | **AuthorizationResult** or null | Change classes overriding `check` to override `authorize` and update remaining `check` call sites |

**AuthorizationResult** was introduced in **6.3**; **AuthorizationManager.authorize** arrived in **6.4**. This explains why a project can have the **AuthorizationResult** type yet still fail to call **manager.authorize** on Spring Security 6.3.

In Spring Security 6.4–6.5, default **authorize** delegates to **check** on legacy implementations. Hence a class overriding only **check** continues working with callers invoking **authorize**. However, adding only an **authorize** override to a 6.5 custom class may not compile because the interface still declares abstract **check**. By 7.x, you must implement **authorize** with the new signature.

**AuthorizationDecision** is not removed in 7.x: it remains a simple class implementing **AuthorizationResult**. New code can continue to **return new AuthorizationDecision(true)** or **false**. The change lies in the manager's return contract, without requiring a new result class.

Do not manually mix **spring-security-core**, **spring-security-web**, and **spring-security-config** across different major versions; let the Spring Boot/Spring Security BOM align versions and verify with a build.

## 3. What Does AuthorizationManager Receive and Return?

Two primary parameters:

- **Supplier<Authentication> authentication**: supplies the authenticated user. Passing a Supplier lets managers avoid retrieving Authentication if policy does not require it. Never cache Authentication retrieved from the current request as the result for another request.
- **T object**: the context/target under evaluation. For example, **RequestAuthorizationContext** holds the request, while **MethodInvocation** holds the method and arguments; a domain object itself may carry id/owner/tenant. Type `T` must match where the manager is applied.

**AuthorizationResult** is an interface with **boolean isGranted()**. **AuthorizationDecision** is a common implementation:

~~~java
AuthorizationResult yes = new AuthorizationDecision(true);
AuthorizationResult no = new AuthorizationDecision(false);
boolean allow = yes.isGranted(); // true
boolean deny = no.isGranted();   // false
~~~

This is a partial snippet requiring imports from **org.springframework.security.authorization** and Spring Security dependencies. You cannot write **new AuthorizationResult(true)** because it is an interface. Do not cast the result to `AuthorizationDecision` unnecessarily; another manager may return a different `AuthorizationResult` type.

**Three decision states:**

| authorize(...) returns | Meaning | How Should the Application Handle the Result? |
| --- | --- | --- |
| **result != null && result.isGranted()** | ALLOW | Grant access only when it is the final policy outcome |
| **result != null && !result.isGranted()** | DENY | Deny per the active security contract |
| **result == null** | ABSTAIN, no decision rendered | Do not treat as ALLOW; apply defined fallback/aggregation |

Buggy code example:

~~~java
AuthorizationResult result = manager.authorize(authSupplier, target);
boolean allow = result == null || result.isGranted(); // WRONG if null is unhandled
~~~

If a policy returns null due to a missing tenant or unsupported object type, the snippet above allows a request where no manager took responsibility. At sensitive decision call sites, switch to **fail closed** if policy requires it:

~~~java
AuthorizationResult result = manager.authorize(authSupplier, target);
boolean allow = result != null && result.isGranted();
~~~

Distinction: **null** does not automatically mean deny in every filter/interceptor; understand where `AuthorizationManager` is used and the aggregator's fallback. For **mandatory** conditions, return an explicit deny decision when data is insufficient instead of abstaining.

## 4. check, authorize, verify

**check(Supplier<Authentication>, T)** is the historical method returning **AuthorizationDecision**. In 6.4–6.5 it is deprecated, and in 7.x it is gone. Calling **check** in new code targeting 7.x will not compile.

**authorize(Supplier<Authentication>, T)** (exact signature varies slightly by version) returns **AuthorizationResult** or null. It is useful when you need the decision for auditing, logging, composite policy checks, or reading result attributes provided by an implementation.

**verify(...)** is a default method that **throws AccessDeniedException upon receiving a deny decision**. It suits code that merely needs to enforce access, yet **does not turn null into deny in every situation**. When strict enforcement is needed, configure the composite manager to deny on all-abstain or handle the result directly:

~~~java
AuthorizationResult result = manager.authorize(() -> authentication, document);
if (result == null || !result.isGranted()) {
    throw new AccessDeniedException("Access denied");
}
~~~

The snippet above is **not standalone**; `manager`/`authentication`/`document` must exist and **AccessDeniedException** must be imported for the right module/version.

**AuthorizationManager differs from AuthenticationManager:** `AuthenticationManager` handles login/credentials; `AuthorizationManager` decides HTTP/method/object permissions for an `Authentication`. Moving from `check` to `authorize` does not change authentication APIs.

## 5. Custom Implementations: Old Code and New Code

### Spring Security 6.4–6.5

When a project still targets the legacy API, a custom manager may look like:

~~~java
final class DocumentOwnerManager implements AuthorizationManager<Document> {
    @Override
    public AuthorizationDecision check(
            Supplier<Authentication> authentication,
            Document document) {
        Authentication user = authentication.get();
        return new AuthorizationDecision(
                user != null && user.getName().equals(document.owner()));
    }
}
~~~

This is **illustrative code**, omitting imports and domain types. Version 6.5 includes default **authorize**, so callers invoking **manager.authorize(...)** still run this `check` logic. When moving the target to 7.x, update the override point.

### Spring Security 7.x

An equivalent implementation in 7.x:

~~~java
final class DocumentOwnerManager implements AuthorizationManager<Document> {
    @Override
    public AuthorizationResult authorize(
            Supplier<? extends Authentication> authentication,
            Document document) {
        Authentication user = authentication.get();
        return new AuthorizationDecision(
                user != null
                && user.isAuthenticated()
                && user.getName().equals(document.owner()));
    }
}
~~~

Differences are **authorize**, **AuthorizationResult**, and the wildcarded Supplier signature in the 7.x API. For Java files that must build across versions, verify compilation on each line: generic **Supplier<Authentication>** and **Supplier<? extends Authentication>** in an override must not be assumed to have identical signatures.

A simple lambda returning `AuthorizationDecision` reduces boilerplate and improves compatibility across 6.5/7.x because the compiler binds to whichever abstract method the active interface defines:

~~~java
AuthorizationManager<Document> owner = (authentication, document) -> {
    Authentication user = authentication.get();
    return new AuthorizationDecision(user != null
            && user.isAuthenticated()
            && user.getName().equals(document.owner()));
};
~~~

When dependencies, database queries, observability, or complex policies are needed, a well-named class is easier to test and audit.

## 6. Combining Managers with AuthorizationManagers

**AuthorizationManagers** (plural) is the utility for composing an `AuthorizationManager`. Three main factories:

| Factory | Mental Model | Example |
| --- | --- | --- |
| **allOf(m1, m2, …)** | AND: policy must satisfy every required condition | authenticated AND same tenant AND read scope |
| **anyOf(m1, m2, …)** | OR: at least one valid allowance path | owner OR public document |
| **not(m)** | Inverts `m`'s decision | not in a banned group, if policy `m` always renders a clear decision |

**Example of proper boundaries:**

~~~text
ALLOW = authenticated
    AND sameTenant
    AND hasAuthority("document:read")
    AND (isOwner OR isPublished)
~~~

If you write **anyOf(authenticated, sameTenant, hasRead, isOwner, isPublished)**, a user only needs to satisfy one condition (such as being logged in) to be allowed. That is a security flaw even though the API compiles cleanly. Use **allOf** for mandatory gates, and use **anyOf** only for *genuinely* alternative paths.

### 6.1. all-abstain and empty manager lists

The factories have overloads accepting **AuthorizationDecision allAbstainDefaultDecision**. This defines the fallback when every delegate abstains or no delegate applies; it is very useful when policy demands deny-by-default:

~~~java
AuthorizationManager<Document> guardedAnd = AuthorizationManagers.allOf(
        new AuthorizationDecision(false),
        authenticated, sameTenant, canRead);

AuthorizationManager<Document> guardedOr = AuthorizationManagers.anyOf(
        new AuthorizationDecision(false),
        isOwner, isPublished);
~~~

This is an illustrative snippet; **authenticated**, **sameTenant**, **canRead**, **isOwner**, and **isPublished** must all be managers of the same type **AuthorizationManager<Document>**. Never assume managers with different `T` types can be composed directly.

The Javadoc notes that **allOf(...)** without a default returns **grant** when the delegate list is empty; **anyOf(...)** without a default returns **deny** when the list is empty. Never let misconfiguration create an empty manager list and trust `allOf` to protect you. When managers can return null, pass an explicit deny default as required.

A mandatory condition like **sameTenant** must return **deny** if the tenant cannot be verified, rather than null. **allOf** may ignore an abstaining delegate when other delegates grant; an *all-abstain* deny default does not convert every individual null into deny. Therefore, mandatoriness must come from each manager and a test matrix, not from the factory alone.

### 6.2. Critical matrix

Notation **A**: allow, **D**: deny, **Ø**: abstain.

| Manager 1 | Manager 2 | allOf (guided) | anyOf (guided) |
| --- | --- | --- | --- |
| A | A | A | A |
| A | D | D | A |
| D | D | D | D |
| D | Ø | D | D when deny fallback is set |
| Ø | Ø | D when all-abstain default = deny | D when all-abstain default = deny |
| A | Ø | May be A since the other policy abstained | A |

**A + Ø** is dangerous if Ø occurs because a mandatory condition lacked data. Do not blindly coerce every null to false; instead, define which managers may abstain and which must render a decision.

**not(manager)** does not automatically turn null into grant; if the inner manager can abstain, test and handle the fallback. When expressing negation of a mandatory permission, explicit boolean-returning logic makes fail-closed behavior easier to guarantee.

## 7. Runnable Java 17+ Example with Spring Security 7

The standalone program below creates managers for: holding authority **document:read**, owning the document, and public documents. Final rule: **hasRead AND (isOwner OR isPublished)**. One manager returns null to demonstrate all-abstain default deny. The program uses **Spring Security 7.0.7** and JDK 17+; it starts no web server and assumes no controller or database.

Create **build.gradle**:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:7.0.7'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.AuthorizationMigrationDemo'
}
~~~

Create **src/main/java/demo/AuthorizationMigrationDemo.java**:

~~~java
package demo;

import java.util.List;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationManagers;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public class AuthorizationMigrationDemo {

    record Document(long id, String owner, boolean published) {}

    private static boolean allowed(AuthorizationManager<Document> manager,
                                   Authentication auth, Document document) {
        AuthorizationResult result = manager.authorize(() -> auth, document);
        return result != null && result.isGranted();
    }

    public static void main(String[] args) {
        Authentication alice = UsernamePasswordAuthenticationToken.authenticated(
                "alice", "n/a",
                List.of(new SimpleGrantedAuthority("document:read")));
        Authentication bob = UsernamePasswordAuthenticationToken.authenticated(
                "bob", "n/a",
                List.of(new SimpleGrantedAuthority("document:write")));

        AuthorizationManager<Document> hasRead =
                AuthorityAuthorizationManager.hasAuthority("document:read");

        AuthorizationManager<Document> isOwner = (authentication, doc) -> {
            Authentication user = authentication.get();
            return new AuthorizationDecision(user != null
                    && user.isAuthenticated()
                    && user.getName().equals(doc.owner()));
        };

        AuthorizationManager<Document> isPublished =
                (authentication, doc) -> new AuthorizationDecision(doc.published());

        AuthorizationManager<Document> ownerOrPublic = AuthorizationManagers.anyOf(
                new AuthorizationDecision(false), isOwner, isPublished);

        AuthorizationManager<Document> readPolicy = AuthorizationManagers.allOf(
                new AuthorizationDecision(false), hasRead, ownerOrPublic);

        Document ownPrivate = new Document(101L, "alice", false);
        Document otherPublic = new Document(102L, "carol", true);
        Document otherPrivate = new Document(103L, "carol", false);

        System.out.println("alice-own=" + allowed(readPolicy, alice, ownPrivate));
        System.out.println("alice-public=" + allowed(readPolicy, alice, otherPublic));
        System.out.println("alice-other-private=" +
                allowed(readPolicy, alice, otherPrivate));
        System.out.println("bob-no-read=" +
                allowed(readPolicy, bob, otherPublic));

        AuthorizationManager<Document> abstain =
                (authentication, doc) -> null;

        AuthorizationManager<Document> strict = AuthorizationManagers.allOf(
                new AuthorizationDecision(false), abstain);
        System.out.println("all-abstain=" + allowed(strict, alice, ownPrivate));

        try {
            readPolicy.verify(() -> alice, otherPrivate);
            System.out.println("verify=allow");
        } catch (AccessDeniedException ex) {
            System.out.println("verify=deny");
        }
    }
}
~~~

Run from the project directory with Gradle Wrapper:

~~~bash
./gradlew run --quiet
~~~

Without a Wrapper, use **gradle run --quiet** if Gradle is installed; on Windows use **gradlew.bat run --quiet**. With working JDK/Gradle/dependencies, stdout from the program is:

~~~text
alice-own=true
alice-public=true
alice-other-private=false
bob-no-read=false
all-abstain=false
verify=deny
~~~

Explanation: Alice has read permission and owns document 101; she has permission to read public document 102; she is blocked on private document 103 owned by someone else. Bob has write but lacks read, so he is blocked even on the public document. An always-abstaining manager wrapped in **allOf(default deny, …)** does not grant access. **verify** throws an error when `readPolicy` denies.

The program uses **mock Authentications for illustration**, with no real account authentication. In web applications, trust only Authentications issued by a trusted authentication system; never construct an authenticated `Authentication` from client-supplied data.

**Version constraint:** The example pins 7.0.7 to demonstrate the new `authorize` API. In a Spring Boot project managing versions, take the compatible Spring Security version from the BOM rather than pulling an isolated 7.x module into a 6.x set. If targeting 6.3, code calling `authorize` will not compile; upgrade dependencies or revert to `check` while unable to upgrade.

## 8. Plugging Managers into HTTP Authorization

**HttpSecurity.authorizeHttpRequests** allows using a custom manager via **.access(...)**. Servlet configuration example (illustrative code, requires imports, beans, and Spring Security web/config dependencies):

~~~java
@Bean
SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        AuthorizationManager<RequestAuthorizationContext> reportPolicy)
        throws Exception {

    return http
            .authorizeHttpRequests(registry -> registry
                    .requestMatchers("/reports/**").access(reportPolicy)
                    .anyRequest().denyAll())
            .build();
}
~~~

Managers sharing the `RequestAuthorizationContext` type can be composed:

~~~java
AuthorizationManager<RequestAuthorizationContext> scope =
        AuthorityAuthorizationManager.hasAuthority("SCOPE_reports.read");

AuthorizationManager<RequestAuthorizationContext> sameTenant =
        (authentication, context) -> {
            Authentication user = authentication.get();
            boolean permitted = user != null
                    && tenantPolicy.canAccessRequest(user, context.getRequest());
            return new AuthorizationDecision(permitted);
        };

AuthorizationManager<RequestAuthorizationContext> reportPolicy =
        AuthorizationManagers.allOf(
                new AuthorizationDecision(false), scope, sameTenant);
~~~

**tenantPolicy** in the snippet is a service requiring an implementation that verifies the tenant from a trusted source. Never grant access based solely on user-supplied headers/IDs; and if the tenant cannot be determined, return deny. When the HTTP route lacks full resource details, object-level checks in the service remain necessary.

**Selecting rules vs. composing policies:** **RequestMatcherDelegatingAuthorizationManager** picks a delegate by request matcher, depending on matcher order. A **/reports/** rule does not automatically AND with **anyRequest()** below it; to enforce both scope and tenant on `/reports/**`, pass **one `allOf(...)` manager** into that matcher. Place specific matchers before broad ones.

Never force-cast **AuthorizationManager<Document>** from Section 7 into **AuthorizationManager<RequestAuthorizationContext>**. They operate on different contexts. Use the right manager type or a controlled adapter translating contexts.

## 9. Java Methods and AuthorizationManager

In method security, the context can be **MethodInvocation**, distinct from an HTTP request. Spring Security provides interceptors like **AuthorizationManagerBeforeMethodInterceptor** and **AuthorizationManagerAfterMethodInterceptor** alongside **@PreAuthorize** and **@PostAuthorize**. Wiring a manager at the right interception point matters more than calling it manually in an unused helper.

Method security example:

~~~java
@Service
class DocumentService {

    @PreAuthorize("@documentPolicy.canRead(authentication, #documentId)")
    public Document read(long documentId) {
        return repository.findById(documentId).orElseThrow();
    }
}
~~~

This is **non-standalone code**, requiring **@EnableMethodSecurity**, the **documentPolicy** bean, a repository, and parameter-name retention (e.g., compiling with **-parameters**). `documentPolicy` must verify real permissions by `Authentication`/`documentId`; the annotation does not supply an ACL or database automatically. Under Spring AOP proxies, **self-invocation** within the same bean can bypass advice; tests should call through the actual Spring bean proxy.

An **AuthorizationManager<MethodInvocation>** can inspect method arguments and decide prior to invocation. When checking return values, consider post-authorization. Do not use an HTTP request context inside method interception because type `T` and execution contexts differ.

## 10. Spring Security 7: AuthorizationManagerFactory

Spring Security **7.0** introduces **AuthorizationManagerFactory<T>** to create standard managers such as **hasRole**, **hasAuthority**, **authenticated**, **permitAll**, **denyAll**, and related variants. **DefaultAuthorizationManagerFactory** supports configuring role prefixes, role hierarchies, and how authentication states are determined for managers created by the factory.

Distinguish clearly:

- **AuthorizationManagerFactory**: creates individual managers from built-in conditions.
- **AuthorizationManagers**: combines managers via **allOf**, **anyOf**, and **not**.
- **RequestMatcherDelegatingAuthorizationManager**: selects a manager by HTTP matcher.
- **AuthorizationManager**: interface executing decisions for a specific `T`.

For projects still on 6.x, do not copy 7.x-only factory APIs. For standard roles, **hasRole("ADMIN")** checks the prefixed authority **ROLE_ADMIN**; **hasAuthority("ROLE_ADMIN")** matches the exact string. Inconsistent prefix settings can cause false denials or false allows during migration.

## 11. Migrating from AccessDecisionManager/AccessDecisionVoter

Legacy models include **AccessDecisionVoter** with **ACCESS_GRANTED**, **ACCESS_DENIED**, and **ACCESS_ABSTAIN**; **AffirmativeBased**, **UnanimousBased**, and **ConsensusBased** aggregate votes by strategy. **AuthorizationManager** replaces this direction, yet composing with `allOf`/`anyOf` is not a strictly equivalent rename.

- **AffirmativeBased** can allow when any grant vote exists even if another voter denies (per its rules); switching to **allOf** denies if any manager denies.
- **UnanimousBased** and **allOf** differ on abstain/all-abstain details and defaults; regression tests are required.
- **ConsensusBased** counts votes and handles ties, which does not equal **anyOf** needing only one allow.
- A legacy voter might **abstain** when it does not recognize an attribute; when migrating to managers, separate "policy not applicable," "missing data," and "explicit deny."

If legacy policy relied on weights, priorities, or vetoes, you may need a **custom composite AuthorizationManager** with explicit semantics rather than forcing it into `allOf`/`anyOf`. Document the old input → decision matrix first, then test the new code with the same fixtures.

## 12. Regression Testing and Decision Matrix

| Test | Input | Expected |
| --- | --- | --- |
| **T1** | User has read, is owner | ALLOW |
| **T2** | User has read, public object | ALLOW |
| **T3** | User has read, private object owned by another | DENY |
| **T4** | User has only write, public object | DENY |
| **T5** | Missing Authentication or unauthenticated user | DENY |
| **T6** | User has role but belongs to another tenant | DENY |
| **T7** | Manager returns null, all delegates abstain | DENY when `allAbstainDefaultDecision=false` |
| **T8** | One manager allows, one abstains due to missing tenant | Mandatory tenant manager must return DENY |
| **T9** | Manager returns explicit deny, `verify` called | Throws `AccessDeniedException` |
| **T10** | Empty delegate list due to misconfiguration | Must not inadvertently allow |
| **T11** | Custom method migrated from `check` to `authorize` | Identical policy decision across all fixtures |
| **T12** | Specific HTTP matcher and broad matcher | Proper rule precedence, no skipped AND conditions |
| **T13** | Method called via proxy and self-invocation | Explicit path actually carrying the interceptor |
| **T14** | Spring Security 7 compile target | No remaining calls or overrides of legacy `check` |

Run **unit** tests on managers to catch logic errors, then **integration** tests through `SecurityFilterChain` or method proxies to prove enforcement points actually invoke the manager. For HTTP, assert both 401/403 codes per authentication/authorization handlers and zero data leakage; code may intentionally return 404 to hide resource existence.

### Safe migration checklist

1. Inspect the dependency tree and BOM; record exact versions of the Spring Security modules in use.
2. Search all **.check(...)** calls on `AuthorizationManager` and **@Override check(...)** in custom classes; verify whether code targets 6.x or 7.x.
3. Update **call sites** to **authorize(...)** (if targeting 6.4+), updating result variables to **AuthorizationResult**.
4. Check **null** branches. Never treat "no decision" as allow at the final enforcement point when policy requires deny-by-default.
5. For custom classes targeting 7.x, override **authorize(...)** with the exact signature; on 6.5, abstract `check` must still be satisfied until the major upgrade.
6. Review `allOf`/`anyOf` structures, distinguishing mandatory from alternative conditions; configure **allAbstainDefaultDecision** when needed.
7. Check generic `T` across HTTP/method/domain layers; never cast between incompatible contexts.
8. Compare before–after allow/deny/abstain matrices, including missing Authentication, cross-tenant, missing role/authority, and malformed data.
9. Run full builds/tests whenever upgrading dependencies; verify the runtime Spring Security filter chain and method interceptors.
10. Monitor authorization events/metrics and ensure sensitive credentials are never logged; handle denials per system policy.

### Common pitfalls

**Pitfall 1 – only renaming the method in a custom interface:** 6.5 code still requires abstract `check`; 7.x removes `check`. Pick the exact target version.

**Pitfall 2 – casting AuthorizationResult to AuthorizationDecision:** Another implementation can return a valid result of a different concrete class; `isGranted` suffices for boolean decisions.

**Pitfall 3 – `allOf` with no delegates:** Default can grant on an empty list; for sensitive policies, validate configuration and set an explicit default deny.

**Pitfall 4 – using `anyOf` to combine role and tenant:** Permits access whenever the role matches even if the tenant is wrong. Use `allOf` for mandatory gates.

**Pitfall 5 – assuming abstain means deny or allow at every layer:** The meaning of null depends on the composite and call site. Write tests specifically for null.

**Pitfall 6 – testing only by calling managers directly:** Does not prove the route or method actually enforces the policy. Pair with HTTP filter or AOP proxy integration tests.

**Pitfall 7 – using 7.x APIs in 6.3 code:** `AuthorizationManager.authorize` arrived in 6.4; compilation target and documentation must match the same version.

**Pitfall 8 – ignoring semantics of legacy voters:** Converting `AffirmativeBased` to `allOf` can change policy even when every class compiles.

## 13. Applied Exercises

**Exercise A – API migration:** on Spring Security 6.5, write a custom manager with **check(...)** and a caller using **authorize(...)**. Then upgrade to 7.x and update the custom class to override **authorize(...)**. Run the same test suite to prove unchanged outcomes.

**Exercise B – AND/OR:** build the policy **sameTenant AND hasRead AND (isOwner OR isPublished)**. Use at least two users, two tenants, and three objects; compare an intentionally wrong `anyOf` against the right `allOf` to spot privilege escalation.

**Exercise C – abstain:** build a manager that returns null when tenant info is missing. Compare `allOf`/`anyOf` with **allAbstainDefaultDecision=deny** and redesign the mandatory manager to return deny on missing data.

**Exercise D – enforcement points:** wire a manager into **authorizeHttpRequests().access(...)** on an endpoint, then test real requests for allow, deny, anonymous, and cross-tenant cases. Add a proxy-based method security test.

**Pass criteria:** understand `check`/`authorize` differences across versions; use `AuthorizationResult` and `isGranted` properly; distinguish allow/deny/abstain; compose policies accurately with AND/OR; prevent defaults/empty lists/nulls from creating vulnerabilities; and verify with regression tests at enforcement points on the target version.

## Official Documentation

- [Spring Security 6.5 — AuthorizationManager](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManager.html)
- [Spring Security 7 — AuthorizationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationManager.html)
- [AuthorizationResult](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationResult.html)
- [AuthorizationDecision](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationDecision.html)
- [AuthorizationManagers — allOf/anyOf/not](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationManagers.html)
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security 6.5 — Authorization Migrations](https://docs.spring.io/spring-security/reference/6.5/migration/servlet/authorization.html)
