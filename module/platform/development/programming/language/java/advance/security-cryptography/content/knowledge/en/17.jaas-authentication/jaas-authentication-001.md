# 17.1 Distinguishing Identity Authentication from Application Authorization Decisions

## Objectives

After this lesson, you will be able to:

1. Clearly answer two distinct security questions: **Authentication — "Who are you?"** and **Authorization — "Are you permitted to perform this action on this specific resource, in the current context?"**
2. Understand JAAS (**Java Authentication and Authorization Service**) in Java 17, especially **`LoginContext`**, **`LoginModule`**, **`Configuration`**, **`CallbackHandler`**, **`Subject`**, **`Principal`**, and the **`login/commit/abort/logout`** phases.
3. Distinguish **`LoginContext.login()` succeeding** from the decision to permit reading an invoice, editing a profile, calling an admin API, or accessing resources belonging to another tenant.
4. Design authorization checking **actor + action + resource + context**, applying **deny-by-default**, **least privilege**, **tenant isolation**, and **per-object permission checks** rather than checking only login status or roles.
5. Run a Java 17+ example with a **custom `LoginModule`**, a `Subject` receiving a `Principal` after authentication, and **application policy** denying cross-tenant or non-owner access even when the caller logged in validly.
6. Recognize the relationship between traditional JAAS Authorization and **Java Security Manager/Policy** in legacy docs; understand why **`Subject.doAs`** must not be treated as automatic business authorization on modern JDKs.
7. Build proper tests and audits for **unauthenticated**, **authenticated but unauthorized**, **revoked permissions**, **impersonation**, **IDOR/BOLA**, and **mixed session context** cases.

**Key takeaway:** Authentication gives the application an **identity verified through a trusted mechanism**; authorization is **a separate decision, repeated at every resource and operation boundary**. **Being logged in does not mean being allowed to do everything.** While JAAS includes historical authorization APIs and docs, **authentication success does not automatically grant business permissions** to every invoice, tenant, database row, or API.

## 1. Two Questions: Authentication and Authorization

### 1.1 Authentication — Verifying Identity

**Authentication (AuthN)** answers: has an entity (user, host, service, or process) genuinely proven the identity it claims?

Examples of evidence:

- A password verified against a proper salted password verifier and KDF.
- A token/session with verified signature/MAC, issuer, audience, validity, and required bindings.
- A private key proven via mTLS or a valid challenge-signing protocol.
- A Kerberos ticket verified through JAAS/GSS-API mechanisms.
- MFA/passkey, per identity provider and application policy.

Once evidence is valid, the system can establish an **authentication context**: stable user ID, authentication method, timestamp, assurance level, linked tenant, session ID, and verified claims. Without valid evidence, **never accept an actor identity from client-supplied data**.

Example:

~~~text
HTTP request
Authorization: Bearer <token>

   Token/credential validation
       |
       +--- Invalid ----------> Reject (unauthenticated)
       |
       +--- Valid ------------> Authenticated identity:
                             userId = "alice"
                             authMethod = "oidc"
                             session = ...
~~~

**Authentication does not say whether Alice may view Bob's invoice #127.** It only says the system has grounds to trust the caller is Alice based on that verification step.

### 1.2 Authorization — Deciding Access on Resources

**Authorization (AuthZ)** answers: is an authenticated actor (or an anonymous/public actor permitted by policy) allowed to perform **an action** on **a resource** within **a context**?

Model:

~~~text
Authorize(
    actor    = Alice,
    action   = "invoice:read",
    resource = Invoice 127,
    context  = {tenant: "tenant-A", time, authStrength, ...}
)
    => ALLOW or DENY
~~~

Policy may simultaneously require:

- Alice was authenticated from a trusted source.
- Alice holds the **INVOICE_READER** privilege in a trusted role/permission store.
- Invoice 127 belongs to **tenant-A** and Alice has valid membership in that tenant.
- Alice is the **owner** or explicitly authorized to read that resource.
- The invoice is not locked/impounded and is in a business state permitting reads.
- The session is still valid, with recent MFA or compliant device status if the operation is sensitive.
- No explicit deny or permission revocation overrides the allow conditions.

If any mandatory condition fails, the result must be **DENY**.

### 1.3 Authentication and Authorization Are Independent Yet Related

| Aspect | Authentication (AuthN) | Authorization (AuthZ) |
| --- | --- | --- |
| Question | Who is calling? Is identity evidence valid? | What may this actor do, on which resource, and when? |
| Input data | Credentials, session/token, client certificate, challenge | Authenticated identity, policy/roles, tenant, object permissions, context |
| Typical components | `LoginContext`/`LoginModule`, IdP, session verifier | Authorization service, policy decision point, ACL/RBAC/ABAC/ReBAC |
| Outcome | Trusted identity or failure | ALLOW/DENY for an action/resource |
| Timing | At login or request/session verification | **Every sensitive operation/resource**; may have short-lived caching per policy |
| Common changes | Logout, session expiry, invalid token, MFA | Role changes, permission revocation, resource owner changes, tenant switch |
| Pitfall | Accepting client-declared `userId` | Allowing access merely because user logged in without object-level checks |
| Security goal | Prevent identity spoofing | Prevent privilege escalation, unauthorized reads, and cross-tenant access |

**A public resource may be accessed without login** if policy intentionally allows an anonymous actor to perform that specific action. Conversely, even an authenticated admin is **not necessarily allowed to read all data** when policies enforce tenant boundaries, separation of duties, or restricted data.

### 1.4 Short Example: Login Succeeds, Access Still Denied

~~~text
Alice logs in with valid password        -> AuthN: SUCCESS
Alice opens an invoice owned by Alice    -> AuthZ: ALLOW (if policy permits)
Alice opens an invoice in tenant-B       -> AuthZ: DENY
Alice edits admin-only system config     -> AuthZ: DENY
Alice's invoice.read role was revoked    -> AuthZ: DENY on the next check
~~~

**AuthN succeeding + AuthZ failing is completely normal behavior and must be tested.**

## 2. Where Does JAAS Fit in This Story?

**JAAS** is the Java SE component for **pluggable authentication across multiple providers/modules**. JAAS also includes a **Subject/Principal-based authorization** model integrated with Java's traditional permission/security policy system. Therefore, it is inaccurate to claim "JAAS only does authentication and has no authorization at all"; yet it is equally wrong to claim "JAAS login automatically grants API permissions."

In modern applications, clearly separate:

- **JAAS authentication layer**: identifies and verifies identity, populating `Subject`/`Principal`s per configured modules.
- **Application authorization policy**: decides whether a user/service may execute an action on a specific resource.
- **Historical JAAS permission-based authorization**: uses `Subject`/`Principal`, `Subject.doAs`, `AccessControlContext`, `Policy`, and Security Manager in older Java architectures; **not an automatic business RBAC/tenant enforcement layer**.

### 2.1 Main JAAS Classes and Interfaces

| API | Responsibility |
| --- | --- |
| **`javax.security.auth.login.LoginContext`** | Coordinates login by configuration name, invokes `LoginModule`s; handles `login`/`logout` and retrieving `Subject` |
| **`javax.security.auth.login.Configuration`** | Chooses which `LoginModule`s run, their order, control flags, and per-module options |
| **`javax.security.auth.spi.LoginModule`** | Authenticates via a concrete mechanism: Kerberos, password backend, smartcard, etc. |
| **`javax.security.auth.callback.CallbackHandler`** | Supplies answers to `Callback`s (name, password, PIN...), decoupling UI/credential source from modules |
| **`NameCallback` / `PasswordCallback`** | Carriers for passing username and password to a `LoginModule` |
| **`javax.security.auth.Subject`** | Holds `Principal`s and credentials associated with an authenticated or authenticating entity |
| **`java.security.Principal`** | Identity/identifying attribute represented as an object with `getName()` |
| **`AppConfigurationEntry`** | `LoginModule` class name, control flag, and options in configuration |
| **`LoginException` / `FailedLoginException`** | Signals login/module failure; application must reject identity when login fails |

A `Subject` can hold **multiple `Principal`s** representing different identities or identifier types—for example, an account user, a Kerberos principal, and groups/other identities. Never assume a `Subject` has only one `Principal` or that every `Principal` is a **role**.

### 2.2 Typical JAAS Authentication Flow

~~~text
Application calls LoginContext("appName")
              |
        Read Configuration
              |
       Select one or more LoginModules
              |
    LoginModule.initialize(subject, callbackHandler,
                           sharedState, options)
              |
    LoginModule.login()     -> verify credentials
              |
       Overall success?
          /              \
        NO                YES
        |                  |
  abort()/exception   modules' commit()
        |                  |
    Do not trust       Subject holds Principals /
    identity           credentials added by modules
                           |
                       LoginContext.getSubject()
                           |
                Application authentication context
                           |
                   Per-request authorization
~~~

**Two crucial phases:**

1. **`login()`**: the module verifies identity evidence and holds temporary state internally; it should not yet add Principals to `Subject` before knowing overall authentication succeeded.
2. **`commit()`**: once required modules pass, the module adds appropriate `Principal`s/credentials to `Subject`. If overall login fails, the system invokes **`abort()`** to clean state; **`logout()`** removes data committed by the module.

Having a `Subject` contain a `Principal` created by a trusted module after `LoginContext.login()` succeeds **carries identity meaning**. It does not by itself prove the actor may read every object.

### 2.3 Configuration and Control Flags

A traditional JAAS configuration file might look like:

~~~text
BusinessApp {
    com.example.auth.CompanyLoginModule required;
    com.example.auth.AdditionalCheckModule requisite;
};
~~~

This is **conceptual configuration illustration**, which cannot run unless `com.example...` classes exist in the application. Class names and options must point to valid `LoginModule`s.

JAAS flags:

| Flag | Role |
| --- | --- |
| **`REQUIRED`** | Module must succeed; even if it fails, evaluation continues through subsequent modules before overall login fails |
| **`REQUISITE`** | Module must succeed; failure stops evaluation immediately |
| **`SUFFICIENT`** | If it succeeds and no prior `REQUIRED`/`REQUISITE` failed, login may finish early; if it fails, evaluation continues |
| **`OPTIONAL`** | Individual success/failure may not decide the whole; if no mandatory modules exist, at least one optional/sufficient module must succeed |

Flags govern **composite authentication success**, **not** permissions like `invoice:read`, `admin:write`, or tenant membership.

**Misconfiguring JAAS** can accidentally turn a weak module into an alternate login path bypassing a strong module. Yet even with a sound login config, resource authorization must still be checked independently.

## 3. `Subject`, `Principal`, and Claims: Not Pre-Granted Permissions

### 3.1 A `Principal` Is an Identity, Not a Global Permission

**`Principal`** is an object representing an identity attached to a `Subject`. Having a Principal named `"alice"` does not mean "Alice may read all invoice tables."

Example:

~~~text
Subject:
  Principals:
    UserPrincipal("alice")
    KerberosPrincipal("alice@EXAMPLE.TEST")
  PublicCredentials:   ...
  PrivateCredentials:  ... (may contain secrets)
~~~

This is a **conceptual representation**, not fixed JAAS output. Real modules/providers supply their own `Principal` types.

`Subject` may contain sensitive credentials. Never dump full **`Subject.toString()`**, `getPrivateCredentials()`, or raw tickets/tokens into logs or responses. Capture only permitted audit fields (`userId`, mechanism, session reference, outcome).

### 3.2 Having a `Principal` in an Object Is Not Proof of Login

A **`Subject` can be created or modified by Java code** in permitted contexts. Code must never trust an arbitrary `Subject` object or `Principal` string **supplied freely by a client** as proof of login.

An "authenticated" event must originate from a **trusted credential/token verification path**. When a service blindly constructs an identity from headers:

~~~text
X-User-Id: admin
X-Role: OWNER
X-Tenant: tenant-A
~~~

without verifying the headers came from an authenticated upstream identity gateway protected against spoofing, external callers can choose any identity/role. Likewise, **`new UserPrincipal("admin")`** in a request layer grants no real authority beyond whatever buggy code trusts it.

**Rule:** obtain authenticated principals only from a controlled boundary such as a successful JAAS login, an authenticated framework security context, or a valid token/session verifier.

### 3.3 When Can Roles/Groups in a `Principal` or JWT Be Used?

A JAAS/IdP system may attach **groups/roles/claims** to a `Subject` or token. However, the application must verify:

- Which source is authorized to issue those roles/claims?
- Have the claims had their signature/issuer/audience/timestamp verified?
- Do the claims match the current **tenant, application, resource, and audience**?
- Has the role expired or been revoked?
- Is the role sufficient for this action on this specific object?
- Is access restricted by explicit denies, ownership, separation of duties, or other policies?

**A verified role is an input to authorization policy**, not always an automatic allow decision. For example, `"MANAGER"` in `tenant-A` does not grant access to confidential documents in `tenant-B`.

### 3.4 Authentication Strength and Step-Up

Some actions require stronger conditions than merely "logged in": recent MFA, managed device, fresh session, approved network/region, or two-person approval. Those are **context conditions** for authorization.

Example:

~~~text
Alice logged in with a password yesterday.
Action: change company payout details.

Policy:
  user is authenticated
  AND has billing:update permission
  AND belongs to the right tenant
  AND MFA step-up within the last 5 minutes
  AND account is not locked
=> if recent MFA is missing: require step-up, deny immediate UPDATE.
~~~

**Do not confuse an MFA requirement** (raising authentication assurance) with **business permission**. Both conditions may need to hold simultaneously.

## 4. Authorization Decision Model for Java Applications

Design a logical enforcement point:

~~~text
AUTHZ(actor, action, resource, context):
    if actor is unauthenticated and resource is not public:
        DENY

    fetch policy/roles/tenant from trusted source
    load resource with tenant/owner and status
    apply explicit deny & business constraints
    ALLOW only if all mandatory conditions pass
    otherwise DENY
~~~

**Deny-by-default** means anything without an explicit allow rule is denied. Never write:

~~~text
if (user != null) {
    return ALLOW;
}
~~~

for sensitive operations. An authenticated user is the **starting precondition**, not the entire policy.

### 4.1 Actor + Action + Resource + Context

| Field | Example | Why needed |
| --- | --- | --- |
| **Actor** | `userId` `"alice"`, tenant membership | Who is actually making the request |
| **Action** | `invoice.read`, `invoice.approve`, `invoice.delete` | Each operation carries different risk/privileges |
| **Resource** | invoice ID 127, `tenant-A`, owner `alice` | Permissions must bind to a specific object |
| **Context** | invoice status, MFA age, time, environment | Decisions depend on runtime conditions |
| **Policy** | role grants + owner + tenant + explicit deny | Separates rules from HTTP plumbing |
| **Decision** | ALLOW/DENY + internal reason code | Easy to test/audit without leaking sensitive info |

Someone permitted **`invoice.read`** is not necessarily permitted **`invoice.delete`** or **`invoice.approve`**. Even a public resource may allow reading while forbidding modification.

### 4.2 RBAC: Role-Based Access Control

RBAC assigns permissions to **roles**, and roles to actors:

~~~text
Role INVOICE_READER -> invoice:read
Role INVOICE_EDITOR -> invoice:read, invoice:update
Role AUDITOR        -> invoice:read (within assigned scope)
~~~

RBAC is convenient to administer, yet does not handle object/tenant boundaries by itself:

- Alice has role `INVOICE_READER` in `tenant-A`.
- Invoice X belongs to `tenant-B`.
- Checking only the RBAC role could wrongly ALLOW.
- **Tenant checks** must be added, potentially along with owner, purpose, or resource ACL checks.

### 4.3 ABAC: Attribute-Based Access Control

ABAC evaluates attributes of the actor, resource, action, and environment:

~~~text
allow if
    actor.active
    AND actor.tenantId == resource.tenantId
    AND action == "invoice.read"
    AND "INVOICE_READER" in actor.permissions
    AND resource.status != "SEALED"
~~~

Never trust attributes from a request when those attributes must be server-controlled. For example, a **`tenantId`** sent in a URL is only the **target identifier**, not proof the caller belongs to that tenant. Verify membership from a trusted directory/token and database state.

### 4.4 ReBAC: Relationship-Based Access Control

ReBAC relies on relationships between actor and resource:

~~~text
Alice --owns--> Invoice 127
Bob   --reviewer-of--> Invoice 127
Carol --member-of--> Team Finance --owns--> Folder F
~~~

It is especially effective for resources with ownership, sharing, or team hierarchies. Still verify relationship provenance and revocation; never treat a client-sent ID list as proof.

### 4.5 ACLs, Capabilities, and Other Models

- **ACLs** on resources define which users or groups have access; protect ACL updates carefully.
- **Capability tokens** can grant access to a specific resource when properly authenticated and bounded, such as a signed short-lived download URL. Capabilities need tight scope/expiry/audience.
- **Policy-as-code / authorization services** centralize decisions; a policy engine does not protect an endpoint if the backend forgets to call it.

You can combine RBAC + ABAC + ReBAC; you do not have to pick just one model to be secure.

## 5. Object-Level Authorization: Preventing IDOR/BOLA and Tenant Leaks

A critical mistake:

~~~text
GET /api/invoices/127
    |
Security filter: "User logged in? YES"
    |
db.findInvoiceById(127)
    |
return invoice
~~~

If invoice 127 belongs to Bob or `tenant-B`, Alice can fetch it simply by guessing IDs. This is **Broken Object Level Authorization (BOLA)** / **Insecure Direct Object Reference (IDOR)**.

The right version:

~~~text
GET /api/invoices/127
    |
AuthN: verify Alice's identity
    |
AuthZ: does Alice have invoice:read in tenant-A?
    |
Data layer: fetch invoice 127 within allowed tenant
    |
AuthZ: do object's owner/ACL/status allow Alice to read?
    |
ALLOW -> serialize only allowed fields
DENY  -> return error per policy without leaking data
~~~

**Note:** checking permissions at the start of a request is necessary yet insufficient if permissions or resource ownership change between check and use. For critical transactions, embed conditions into the update query, transaction, or appropriate locking/version checks.

### 5.1 Query Missing a Tenant Filter

Unsafe code:

~~~java
// Anti-pattern example; not a standalone Java program.
Invoice invoice = repository.findById(request.invoiceId());
return invoice;
~~~

Fixed pattern:

~~~java
// Illustrative example, depending on repository and actor context.
Invoice invoice = repository.findByIdAndTenantId(
        request.invoiceId(), authenticatedActor.tenantId());
authorization.requireCanRead(authenticatedActor, invoice);
return invoice;
~~~

When multiple tenants share role names, omitting the tenant condition in queries leaks data. Checking a role in the controller and then calling `findById` does not provide tenant isolation.

### 5.2 Even Admin Roles Have Scopes

**ADMIN** privileges can be scoped in multiple ways:

- Admin within one project;
- Admin within `tenant-A`;
- Tenant administrator;
- System administrator;
- Read-only compliance auditor;
- Break-glass account under special workflow.

Never use a single global **`isAdmin`** boolean when real policies span multiple scopes; that is a frequent source of **privilege escalation**.

## 6. Complete Java 17+ Example: JAAS Login + Separate Permission Check

This example uses **a self-contained program**. It demonstrates:

1. **`LoginContext`** loading **`DemoLoginModule`** via a Java-constructed `Configuration`, avoiding external config files.
2. **`CallbackHandler`** supplying username/password to the `LoginModule`.
3. **`LoginModule.login()`** verifying training credentials, while only **`commit()`** adds `UserPrincipal` to `Subject`.
4. After authentication, **`canRead(...)`** is an **independent application policy**, reading roles/tenants from a simulated internal directory and checking **tenant + owner** of the invoice.
5. Testing that Alice can view her own invoice, yet is blocked across tenants or owners even though login succeeded.
6. **`logout()`** removing the Principal added by the module. Wrong-password login is rejected.

**Safety limits:** **test-only** credentials are hardcoded to keep the example self-contained. **Never use this `LoginModule` in production.** There is no password hashing, real user store, rate limiting, MFA, session manager, or auditing. The fixed `directory` `Map` **simulates entitlement data from a trusted backend**, not claims sent by a browser.

### 6.1 Standalone Code: `JaasDecisionDemo.java`

Create the file **`JaasDecisionDemo.java`** in UTF-8:

~~~java
import java.io.IOException;
import java.security.Principal;
import java.util.Arrays;
import java.util.Map;
import java.util.Set;

import javax.security.auth.Subject;
import javax.security.auth.callback.*;
import javax.security.auth.login.*;
import javax.security.auth.spi.LoginModule;

public class JaasDecisionDemo {
    public record UserPrincipal(String name) implements Principal {
        @Override
        public String getName() { return name; }
    }

    public record Invoice(String tenant, String owner) { }

    public record Entitlement(
            Set<String> roles, Set<String> tenants) { }

    // Training auth provider: never hardcode passwords in production.
    public static final class DemoLoginModule implements LoginModule {
        private Subject subject;
        private CallbackHandler handler;
        private UserPrincipal user;
        private boolean loggedIn;
        private boolean committed;

        @Override
        public void initialize(Subject subject, CallbackHandler handler,
                               Map<String, ?> sharedState,
                               Map<String, ?> options) {
            this.subject = subject;
            this.handler = handler;
        }

        @Override
        public boolean login() throws LoginException {
            if (handler == null) {
                throw new LoginException("No callback handler");
            }

            NameCallback name = new NameCallback("Username: ");
            PasswordCallback pass =
                    new PasswordCallback("Password: ", false);
            char[] received = null;

            try {
                handler.handle(new Callback[]{name, pass});
                received = pass.getPassword();

                if (!"alice".equals(name.getName())
                        || received == null
                        || !Arrays.equals(received,
                            new char[]{'t','e','s','t','-',
                                       'o','n','l','y'})) {
                    throw new FailedLoginException(
                            "Invalid credentials");
                }
                user = new UserPrincipal("alice");
                loggedIn = true;
                return true;
            } catch (IOException | UnsupportedCallbackException e) {
                throw new LoginException("Cannot obtain credentials");
            } finally {
                pass.clearPassword();
                if (received != null) {
                    Arrays.fill(received, '\0');
                }
            }
        }

        @Override
        public boolean commit() throws LoginException {
            if (!loggedIn) return false;
            if (subject.isReadOnly()) {
                throw new LoginException("Read-only Subject");
            }
            subject.getPrincipals().add(user);
            committed = true;
            return true;
        }

        @Override
        public boolean abort() throws LoginException {
            if (committed) return logout();
            user = null;
            loggedIn = false;
            return true;
        }

        @Override
        public boolean logout() throws LoginException {
            if (committed && !subject.isReadOnly()) {
                subject.getPrincipals().remove(user);
            }
            committed = false;
            loggedIn = false;
            user = null;
            return true;
        }
    }

    private static CallbackHandler credentials(
            String name, char[] secret) {
        return callbacks -> {
            for (Callback cb : callbacks) {
                if (cb instanceof NameCallback n) {
                    n.setName(name);
                } else if (cb instanceof PasswordCallback p) {
                    p.setPassword(secret);
                } else {
                    throw new UnsupportedCallbackException(cb);
                }
            }
        };
    }

    // Configuration lives in code so the program is standalone and easy to run.
    private static Configuration config() {
        return new Configuration() {
            @Override
            public AppConfigurationEntry[] getAppConfigurationEntry(
                    String name) {
                if (!"demo".equals(name)) return null;
                return new AppConfigurationEntry[]{
                    new AppConfigurationEntry(
                        DemoLoginModule.class.getName(),
                        AppConfigurationEntry.LoginModuleControlFlag.REQUIRED,
                        Map.of())
                };
            }
        };
    }

    // Simulates a trusted SERVER-SIDE entitlement store.
    // Never build this Map from user-supplied requests/headers.
    private static final Map<String, Entitlement> directory = Map.of(
        "alice", new Entitlement(
                Set.of("INVOICE_READER"), Set.of("tenant-A"))
    );

    // APPLICATION AUTHORIZATION DECISION, NOT LOGIN.
    private static boolean canRead(
            Subject authenticated, Invoice invoice) {
        if (authenticated == null || invoice == null) return false;

        Set<UserPrincipal> users =
                authenticated.getPrincipals(UserPrincipal.class);
        if (users.size() != 1) return false;

        UserPrincipal user = users.iterator().next();
        Entitlement rights = directory.get(user.getName());

        return rights != null
                && rights.roles().contains("INVOICE_READER")
                && rights.tenants().contains(invoice.tenant())
                && invoice.owner().equals(user.getName());
    }

    public static void main(String[] args) throws Exception {
        char[] goodSecret = "test-only".toCharArray();
        LoginContext login = new LoginContext(
            "demo", null,
            credentials("alice", goodSecret), config());

        login.login();               // AuthN succeeds.
        Arrays.fill(goodSecret, '\0');

        Subject subject = login.getSubject();
        System.out.println("JAAS authenticated: "
                + subject.getPrincipals(UserPrincipal.class)
                        .contains(new UserPrincipal("alice")));

        System.out.println("Own invoice allowed: "
                + canRead(subject, new Invoice("tenant-A", "alice")));

        System.out.println("Cross-tenant denied: "
                + !canRead(subject, new Invoice("tenant-B", "alice")));

        System.out.println("Other owner denied: "
                + !canRead(subject, new Invoice("tenant-A", "bob")));

        login.logout();
        System.out.println("Principals removed on logout: "
                + subject.getPrincipals(UserPrincipal.class).isEmpty());

        char[] badSecret = "wrong".toCharArray();
        LoginContext badLogin = new LoginContext(
            "demo", null,
            credentials("alice", badSecret), config());

        boolean rejected = false;
        try {
            badLogin.login();
        } catch (LoginException expected) {
            rejected = true;
        } finally {
            Arrays.fill(badSecret, '\0');
        }
        System.out.println("Wrong password rejected: " + rejected);
    }
}
~~~

The program uses **`record`** and pattern matching **`instanceof`**, both standard features in **Java 17**. **`DemoLoginModule`** is a `public static` nested class inside the outer `public` class with a default public no-arg constructor, allowing `LoginContext` to instantiate the module from the class name supplied by `Configuration`.

Compile and run:

~~~bash
javac -encoding UTF-8 JaasDecisionDemo.java
java JaasDecisionDemo
~~~

Expected stdout:

~~~text
JAAS authenticated: true
Own invoice allowed: true
Cross-tenant denied: true
Other owner denied: true
Principals removed on logout: true
Wrong password rejected: true
~~~

**Step-by-step explanation:**

1. **`JAAS authenticated: true`:** `LoginModule` receives callbacks, checks demo username/password, and commits `UserPrincipal("alice")` to `Subject`; `LoginContext.login()` returns normally.
2. **`Own invoice allowed: true`:** the `canRead` policy checks server-side entitlements showing Alice has role `INVOICE_READER`, `tenant-A` membership, and owner Alice, so it allows.
3. **`Cross-tenant denied: true`:** Alice is still logged in, yet the invoice belongs to `tenant-B`, failing the membership check.
4. **`Other owner denied: true`:** the invoice belongs to `tenant-A` yet its owner is Bob, and the example policy requires the actor to be the owner.
5. **`Principals removed on logout: true`:** `LoginModule.logout()` removes the `UserPrincipal` that the module added.
6. **`Wrong password rejected: true`:** another `LoginContext` receives a wrong password, `login()` fails, and no valid authenticated context is created.

**All permission checks in the example reside in `canRead(...)`, not `LoginModule.login()`.** Separating the functions demonstrates responsibility boundaries: the module verifies "who Alice is," while the policy service decides "whether Alice may read this object."

### 6.2 Why Does the Demo Use a `directory` Map Instead of a Role Principal?

The **`directory`** Map represents the application's trusted database/identity directory. Although a real `LoginModule` could attach a **`RolePrincipal`** from a trusted source, the example emphasizes that **authorization does not look merely at a single claim or login status**.

In production, the directory needs to:

- Update roles, membership status, and delegated permissions from an authoritative admin backend.
- Verify tenant/project scope, resource owner, ACLs, and explicit denies.
- Enforce cache/TTL/invalidation policies to minimize stale use of revoked permissions.
- Separate trusted role sources from user-supplied form/header/URL data.
- Reject user attempts to mutate maps/policies or forge arbitrary `Subject`s bypassing `LoginContext`.

### 6.3 What the Demo Intentionally Omits

The example is deliberately scoped down:

- No user DB, password hashes, salts, MFA, session cookies, JWTs, or OIDC.
- Hardcoded **`test-only`** training password, unsafe for production.
- Static AuthZ policy, not loaded from a real database, with no TTL/cache/revocation.
- `Invoice` is just a record with tenant and owner; no ID, status, ACL, or amount.
- No HTTP server, input validation, CSRF/XSS/CORS, or audit storage.
- Does not handle concurrency or TOCTOU when permissions/objects change between check and DB write.
- The `Subject` in the demo is produced via an application-trusted login path. **A Java `Subject` itself is not a security boundary if untrusted code can create/modify it**.
- **`LoginContext.logout()` does not invalidate API tokens, session cookies, or cached permission decisions** in other layers. Session/revocation management is an additional application responsibility.

Never turn this example into a "production login template" by replacing the password string in source; use maintained/vetted identity mechanisms and proper security frameworks.

## 7. Placing AuthN/AuthZ in the Request Pipeline

An ideal web/API pipeline separates responsibilities cleanly:

~~~text
Client Request
      |
[Transport / TLS / input-size and syntax validation]
      |
[Authentication Filter]
  validate session / JWT / mTLS / JAAS-backed mechanism
      |
      +--> no valid identity -> reject or public policy
      |
[Trusted Authentication Context]
  actorId, authMethod, tenant memberships, session metadata
      |
[Authorization Decision]
  actor + action + resource + context + current policy
      |
      +--> DENY --> reject; no read/write side effect
      |
[Business Service]
  enforce resource-level policy close to data operation
      |
[Repository / DB]
  tenant-scoped query + transaction/row-level guard
      |
[Response]
  expose only fields within approved scope
~~~

**Never assume every API controller will remember to check permissions.** Enforce policy in a shared layer (method boundary/service/repository) and write integration tests to catch any endpoint missing a check.

However, a security filter that only checks "did the caller log in validly" **cannot decide access for an object that has not been loaded yet**. Many applications need coarse-grained route checks plus **fine-grained checks once the resource is known**.

### 7.1 AuthN Context Must Be Correct Per Request

With thread pools, async tasks, messaging, or reactive pipelines, prevent **request A's principal from leaking into request B**. Even if a framework uses a thread-local security context, never assume it propagates across `CompletableFuture`, executors, callbacks, or message consumers.

Safer practices:

- Pass a **verified** authentication context explicitly where needed using framework-supported propagation.
- In queue consumers, authenticate the service/producer or verify message provenance before accepting an actor context.
- Never use a global `static currentUserId` variable.
- Clean context at request end and test cross-request isolation.
- Never trust a `userId`/`tenantId` inside a job payload without appropriate bindings/permissions.

### 7.2 401, 403, and 404

For HTTP APIs, standard status codes are:

- **401 Unauthorized**: request lacks valid authentication credentials; may include a `WWW-Authenticate` challenge per protocol.
- **403 Forbidden**: server understood the request and identity may be valid, yet policy **denies** the action/resource.
- **404 Not Found**: may be returned by policy to **avoid disclosing the existence** of a resource the actor is not allowed to know about.

Choosing 403 vs. 404 to prevent object enumeration must be **consistent**, yet never replaces real permission checks. Never return sensitive data and then merely swap the status to 403; side effects would already have occurred.

For JSON APIs, never leak private policy details, missing roles of other users, or unauthorized resource names in error messages. Record internal reason codes under access-controlled logging, never in client responses.

## 8. Authentication Succeeded, Yet Session or Permissions Changed

### 8.1 Logout Does Not Equal Revoking All Sessions Everywhere

**`LoginContext.logout()`** calls `logout` on `LoginModule`s and cleans up module-managed `Principal`s/credentials. It **does not automatically invalidate** issued JWT access tokens, clear external server-side session stores, broadcast role-revocation notices to other services, or magically clear authz caches.

Systems may need:

- Proper session invalidation and cookie deletion.
- Token expiry/refresh rotation/revocation suited to the threat model.
- Updating permissions from authoritative sources after role/membership revocation.
- Auditing user/session logouts and handling multi-device sessions.
- CSRF protection on session cookies where applicable.
- Handling background jobs holding stale principals/entitlements.

### 8.2 Permissions Can Be Revoked Between Two Requests

~~~text
10:00 Alice logs in successfully.
10:01 Alice is granted invoice:read for tenant-A.
10:05 Admin revokes Alice's invoice:read permission.
10:06 Alice sends a new request to read an invoice.

AuthN may still be VALID (session remains active).
AuthZ must evaluate against current permissions/valid policy cache:
       DENY.
~~~

If the system reads roles once at login and caches them indefinitely, revoked privileges stay usable. Design freshness to match sensitivity: short caches, version/policy epochs, event invalidation, or authoritative checks for sensitive actions.

**Never equate authentication credential expiry with entitlement expiry.** The two lifetimes can differ.

### 8.3 A Token Containing Roles Does Not Guarantee Those Roles Stay Valid Forever

A JWT or signed token may carry role/permission claims; once verified, those are claims **asserted by the issuer at issuance time**, not necessarily reflecting every change since. Evaluate:

- Token lifetime and rotation/revocation.
- Audience, issuer, signature/MAC, and allowed algorithms.
- Tenant scope and resource scope.
- Whether dynamic entitlement checks are needed for sensitive data.
- Which protocol lets services trust an upstream identity context.

**Never Base64-decode a JWT payload and trust its claims without verifying signature, issuer/audience, and expiry.** Base64 is merely encoding, not authentication.

## 9. Legacy JAAS Authorization and Limits on Modern Java

### 9.1 JAAS Historically Supported Principal-Based Access Control

Java SE 17's JAAS Authorization guide describes combining **`Subject`/`Principal`** with **`java.security.Policy`**, **`AccessControlContext`**, **`Subject.doAs`**, and the **Security Manager** to check permissions inside the classic Java sandbox.

Historical idea:

~~~text
Authenticated Subject
        |
   Subject.doAs(subject, action)
        |
AccessControlContext binds Subject/Principals
        |
Security Manager + Policy evaluate Permission
        |
Java runtime may block protected operations
~~~

This is a **Java API/resource permission policy model** belonging to the Security Manager architecture, **not automatically equivalent** to business policies like "which tenant's invoices Alice may delete."

### 9.2 Distinguishing Java 17 and JDK 24+

- **Java 17:** Security Manager is **deprecated for removal** under JEP 411. Some traditional JAAS authorization APIs still exist and older tutorials describe them.
- **JDK 18+:** several `AccessControlContext`/Security Manager-dependent APIs such as `Subject.doAs` are marked deprecated for removal, with newer `Subject.current`/`Subject.callAs` alternatives introduced.
- **JDK 24+:** under **JEP 486**, the Security Manager is **permanently disabled**; it cannot be re-enabled via startup properties or custom `SecurityManager` installation. Security Manager-based permission checks are no longer a viable foundation for protecting resources.
- **JAAS authentication APIs do not all vanish with it.** `LoginContext`, `LoginModule`, and `Subject` remain relevant where pluggable authentication is needed, depending on JDK/provider.

Therefore **never design a new REST/API authorization system solely around `Subject.doAs` + `java.policy` expecting future JDKs to block cross-tenant data automatically**. Instead, implement **explicit authorization checks in the service/repository/policy layer**, backed by testable and observable enforcement.

### 9.3 `Subject.doAs` Does Not Execute `requirePermission` Automatically

Even in legacy Java code:

~~~java
// Illustrates legacy concept; NOT recommended code
// for new API authorization on JDK 24+.
Subject.doAs(subject, (java.security.PrivilegedAction<Void>) () -> {
    readSomeResource();
    return null;
});
~~~

The code above **contains no invoice/tenant permission check**. Permission-based enforcement depended on policy files, the Security Manager, and APIs actually issuing permission checks. Never infer:

~~~text
"Running under Alice's Subject"
           =>
"Alice is automatically prevented from viewing Bob's invoice"
~~~

That is a **false** conclusion for business authorization unless you implement explicit object-level rules.

### 9.4 Should `Principal` Be Used as a Role?

A framework may define `RolePrincipal` or `GroupPrincipal`, but clarify:

- Which module has authority to assert the role?
- Is the role bound to a tenant and expiration?
- Does it grant access to specific objects?
- Where does code actually **enforce** (`require`) the permission?
- When a `Principal` is removed/changed, do session/policy caches retain stale privileges?

**A `Principal` is identity/security-context data, not a policy enforcement point.** Never treat an arbitrary class name or `getName()` as a complete security check.

## 10. Protecting Resources at the Service and DB Layers

### 10.1 Check Close to Where the Action Occurs

Example money-transfer service:

~~~text
POST /transfers
   -> valid authn
   -> authz account.transfer on source account
   -> verify owner/membership from DB
   -> check account status, limits, MFA
   -> within transaction confirm conditions still hold
   -> record transfer & audit
~~~

Do not check merely "has role `TRANSFER_USER`" on the endpoint and let the caller pass any **`fromAccountId`**. Many critical vulnerabilities stem from **IDOR on write operations**, not just reads.

### 10.2 TOCTOU: Time of Check vs. Time of Use

Suppose a service:

1. Checks Alice is the invoice owner.
2. Another request transfers ownership or revokes membership.
3. The service still updates the invoice based on the stale check.

When operations require consistency, approaches include:

- Performing the policy check and UPDATE inside the **same transaction** with appropriate isolation.
- Embedding tenant/owner/status predicates into **`UPDATE ... WHERE ...`** and verifying the affected row count.
- Using optimistic locking/versions to prevent unexpected state transitions.
- Re-checking entitlements or policy epochs at commit time when needed.
- Avoiding long-cached roles/ownership for critical mutations.

The exact mechanism depends on the database and concurrency model; the core principle is **never decoupling the permission check from the protected operation**.

### 10.3 Field-Level Authorization

An actor allowed to view an Invoice is not necessarily allowed to view every field:

~~~text
Invoice:
  id, date, status, amount            -> standard reader
  customerPersonalId, bankAccount     -> requires sensitive permission
  internalRiskNotes, fraudFlags       -> compliance only
~~~

After object-level allow, response serialization may need to **filter fields** by policy. Never return entire ORM entities hoping the front-end hides fields with CSS.

### 10.4 Multi-Tenant Data Access

In SaaS systems:

- Every read/list/update/delete must enforce tenant boundaries.
- A tenant header/subdomain/URL only identifies the **requested tenant**, never proving membership.
- Policies/roles themselves can be tenant-scoped.
- Background jobs/scheduled workflows also need actor/service authorization, never bypassing checks as "internal."
- DB row-level security (RLS), tenant-scoped repositories, and API authorization reinforce each other; never treat one layer as an excuse to drop all others.

## 11. Logs and Errors Must Reflect the Difference

### 11.1 Log AuthN and AuthZ Separately

Suggested events:

~~~text
AUTHN_SUCCESS user=alice mechanism=JAAS sessionRef=...
AUTHN_FAILURE reasonCode=INVALID_CREDENTIALS ...
AUTHZ_ALLOW actor=alice action=invoice.read resource=127 tenant=A
AUTHZ_DENY  actor=alice action=invoice.read resource=127 reasonCode=TENANT_SCOPE
AUTHZ_DENY  actor=alice action=invoice.update reasonCode=MISSING_PERMISSION
~~~

This is an **illustrative log structure**, not real data and not a mandatory format. In production, avoid logging passwords, access tokens, private credentials, raw `Subject`s, session secrets, sensitive PII, or resource values the caller may not see. Define correlation IDs, retention periods, log access controls, and intrusion detection.

**Do not distinguish "username does not exist" from "wrong password" in public login responses** if that enables user enumeration. Store appropriate internal reason codes instead.

### 11.2 An AuthZ Denial Is Not a Login Failure

If Alice is validly logged in yet blocked from `invoice:delete`, do not automatically report **"invalid password"** or log the user out solely because the action was unauthorized. Report **authorization denied** for that action, unless session compromise is suspected or risk policy dictates otherwise.

Keeping them distinct prevents misleading support teams, audits, and tests.

## 12. Essential Test Matrix

| Test case | AuthN | AuthZ | Expected outcome |
| --- | --- | --- | --- |
| Missing cookie/token on login-required endpoint | FAIL | No access granted | 401/challenge per protocol |
| Login with wrong demo password | FAIL | No trusted actor created | Cannot access protected resources |
| Valid login as Alice | PASS | Not yet decided for objects | Authenticated Subject/context established |
| Alice reads tenant-A invoice owned by Alice | PASS | ALLOW | Authorized fields returned |
| Alice reads tenant-B invoice | PASS | DENY | No data returned |
| Alice reads Bob's invoice in same tenant-A | PASS | DENY per example policy | No data returned |
| Alice lacks editor role yet calls `invoice:update` | PASS | DENY | No update performed |
| Alice has reader role yet lacks required MFA step-up | PASS | DENY or prompt step-up | Sensitive action blocked |
| Alice has active session yet role was just revoked | PASS | DENY once policy update takes effect | Permission change is honored |
| Client sends `X-User-Id: admin` without trust boundary | FAIL | Header untrusted | No impersonation |
| Caller constructs `Subject`/`Principal` bypassing trusted login | No identity proof | Rejected | No privilege escalation |
| Object changes owner between check and write | PASS | Must be checked consistently | Write aborted if condition no longer holds |
| User may read invoice yet may not view `bankAccount` | PASS | Object ALLOW, field DENY | Response does not leak field |
| Service/queue consumer lacks valid actor context | FAIL or per service identity policy | DENY if caller required | Never runs as default admin |
| JAAS logout called, yet external session store still active | Architecture-dependent | Revoke session explicitly | Never equate JAAS logout with system-wide invalidation |
| Developer forgets authz check on a new endpoint | PASS | Must not allow bypass | Integration/security test catches it |

### 12.1 Test Permissions Directly Across Layers

Do not test service methods solely with `isAdmin=true`. Test:

- Unit policy tests with valid and invalid actor/action/resource/context combinations.
- Endpoint integration tests: login plus object permissions, status/response/body, zero side effects on deny.
- Database query/transaction tests: tenant scoping, row counts, racing ownership/permission changes.
- Multi-tenant negative tests: identical IDs across tenants, guessable IDs, list/export endpoints.
- Role revocation and expired sessions.
- Async message/job propagation and cross-request context isolation.
- Audit events free of secrets.
- Unauthorized field serialization and bulk endpoints.

A critical test is **"authenticated yet unauthorized,"** because many APIs only test "unauthenticated" and miss object-level policy.

## 13. Common Mistakes and Fixes

1. **"`LoginContext.login()` threw no exception, so every API is ALLOW."** False; enforce AuthZ per action/resource.
2. **"Principal is named `admin`, so it is a system-wide admin."** False; verify role provenance, scope, and policy.
3. **"Having role `USER` allows reading every user."** False; enforce owner/ACL and tenant scoping.
4. **"Client sent `tenantId`, so that is their tenant membership."** False; membership must come from a trusted backend/token.
5. **"Using `Subject.doAs` makes JAAS block cross-tenant SQL SELECTs automatically."** False; enforce explicit policies.
6. **"Security Manager still works identically on every JDK."** False; JDK 24+ permanently disabled it.
7. **"Let admins bypass all checks for convenience."** Escalation risk; enforce admin scopes, break-glass flows, and auditing.
8. **"Roles at login never change."** False; handle revocation and freshness.
9. **"Signed JWT is present, so resource IDs in the URL must be authorized."** False; JWT identity does not grant object permissions.
10. **"Return all invoice fields since the caller has `invoice.read`."** False; field-level authorization may apply.
11. **"Internal services do not need authz."** False; service principals also need least privilege and tenant scoping.
12. **"Reading user from a thread-local inside any async task works."** False; verify context propagation and cleanup.
13. **"Only controllers need checks; repositories need no tenant filter."** False; multiple code paths can bypass controllers.
14. **"Once permission is checked, DB writes are always safe."** False under race/TOCTOU; use transactions and guarded conditions.
15. **"Logging out of `LoginContext` definitely revokes the JWT at the IdP."** False; session/token lifecycles are independent.
16. **"Java Policy permissions in old tutorials are an equivalent replacement for API RBAC."** No; Security Manager semantics and availability have changed.
17. **"401 and 403 are interchangeable."** No; identity failure differs from insufficient permissions, though 404 may be used by policy to hide resource existence.
18. **"On AuthZ DENY, print all claims, resources, and policies to the client."** False; log minimally with access controls and avoid data leaks.
19. **"List endpoints have tenant filters; export/bulk endpoints do not need them."** False; every data-reading path must enforce scope.
20. **"`LoginModule` decides which invoices Alice may read."** Poor separation of concerns; modules authenticate, while policy services evaluate resources/actions.

## 14. Review Questions

**Q1.** How do authentication and authorization differ?

**Answer:** Authentication verifies who the actor genuinely is; authorization checks whether that actor may perform a given action on a specific resource in the current context.

**Q2.** Does a successful `LoginContext.login()` automatically grant `invoice.read`?

**Answer:** No. You need permission policies from a trusted source and resource-level scope checks.

**Q3.** What is the role of `LoginModule.commit()`?

**Answer:** When overall login meets policy conditions, `commit` adds the relevant `Principal`/credentials to `Subject`; the earlier `login` phase only verifies credentials and holds temporary state.

**Q4.** If `Subject` contains `UserPrincipal("alice")`, is Alice guaranteed to have logged in?

**Answer:** Only if `Subject` came from a server-trusted authentication flow and was not spoofed/tampered with; a self-constructed `Subject` is not cryptographic proof.

**Q5.** Why is role `INVOICE_READER` not enough to view a `tenant-B` invoice?

**Answer:** The role may be granted only within `tenant-A`; you must check tenant/resource scope and owner/ACL rules.

**Q6.** How does RBAC differ from ABAC?

**Answer:** RBAC maps role → permission; ABAC evaluates attributes of actor/resource/action/context. Both can be combined with ReBAC to protect objects.

**Q7.** Why is finding invoices solely by ID vulnerable to BOLA/IDOR?

**Answer:** Logged-in users can guess other users' resource IDs; verify owner/tenant/ACL before returning data.

**Q8.** Must permissions be re-evaluated after a user's role is revoked?

**Answer:** Yes. Caching/revalidation policies must reflect revocation within a window appropriate to the action's sensitivity.

**Q9.** Does `Subject.doAs` automatically protect every application resource?

**Answer:** No. Historical permission-based JAAS relied on `Policy`/Security Manager and permission checks, and JDK 24 disabled the Security Manager. Business APIs need explicit authorization enforcement.

**Q10.** Does JAAS logout automatically revoke an external JWT?

**Answer:** No. Token/session managers and revocation policies belong to their respective systems.

**Q11.** How are HTTP 401 and 403 typically used?

**Answer:** 401 when valid authentication is missing; 403 when the operation is forbidden. 404 may be used by policy to conceal resource existence.

**Q12.** Why does AuthZ need actor/action/resource/context rather than username alone?

**Answer:** Access depends on what is being done, who owns/tenants the object, its state, and current conditions; a bare username cannot decide that.

**Q13.** Can a `tenant-A` admin read `tenant-B` data?

**Answer:** Not by default. Admins are normally scoped; global access exists only when explicitly permitted and controlled by policy.

**Q14.** For which resources might authentication not be required?

**Answer:** For resources/actions explicitly designated public by policy, anonymous actors may be allowed; that does not make every action on that resource public.

**Q15.** Why test for races between permission checks and DB updates?

**Answer:** Resource ownership or memberships can change after the check; transactions, row predicates, and locking/versions keep the decision valid at the time of use.

## 15. Deployment Checklist

- [ ] Trusted **identity source** (`LoginModule`/IdP/session verifier).
- [ ] Separate AuthN context from AuthZ decisions; never trust `userId`/roles from unprotected headers.
- [ ] Clear **actor → scoped roles/permissions** mapping managed by an authoritative backend.
- [ ] Policy defined for every **action/resource**, including intentional public access.
- [ ] **Default DENY** when actor, policy, tenant, or ownership is missing.
- [ ] **Object-level** and **field-level** checks where needed, not only route-level checks.
- [ ] Every read/list/update/delete/export/bulk endpoint enforces tenant scope.
- [ ] Revoked permissions have bounded lifetimes, cache invalidation, or authoritative checks.
- [ ] Critical checks and writes are protected against TOCTOU.
- [ ] Async/thread/queue contexts never leak principals across users.
- [ ] Sessions, tokens, and JAAS logout are handled cleanly at each layer.
- [ ] Logging distinguishes authn failure from authz denial without recording credentials or sensitive `Subject`s.
- [ ] Never rely on **`SecurityManager`/`Subject.doAs`** as a new RBAC engine for REST APIs.
- [ ] Tests cover **authenticated-but-denied**, cross-tenant, missing role, impersonation, revocation, and field leaks.
- [ ] Least privilege enforced across services, DBs, networks, and secret stores.

## 16. Official References

- [Oracle Java SE 17 — JAAS Authentication](https://docs.oracle.com/en/java/javase/17/security/jaas-authentication.html): explains pluggable authentication, `LoginContext`, `Subject`, and `Principal`.
- [Oracle Java SE 17 — JAAS Authentication Tutorial](https://docs.oracle.com/en/java/javase/17/security/jaas-authentication-tutorial.html): login flow with JAAS.
- [Oracle Java SE 17 — JAAS LoginModule Developer's Guide](https://docs.oracle.com/en/java/javase/17/security/java-authentication-and-authorization-service-jaas-loginmodule-developers-guide1.html): `login/commit/abort/logout` phases and `CallbackHandler`.
- [Oracle Java SE 17 — JAAS Authorization](https://docs.oracle.com/en/java/javase/17/security/jaas-authorization.html): legacy authorization based on `Principal` and Java permission policies.
- [Oracle Java SE 17 — LoginContext API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/login/LoginContext.html): constructors, `login`, `getSubject`, and `logout`.
- [Oracle Java SE 17 — Configuration API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/login/Configuration.html): `REQUIRED`/`REQUISITE`/`SUFFICIENT`/`OPTIONAL` flags.
- [Oracle Java SE 17 — Subject API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/Subject.html): `Principal` and credential sets.
- [OpenJDK JEP 411](https://openjdk.org/jeps/411): deprecating the Security Manager in Java 17.
- [OpenJDK JEP 486](https://openjdk.org/jeps/486): permanently disabling the Security Manager as of JDK 24.
- [Oracle JDK 24 — Security Manager Permanently Disabled](https://docs.oracle.com/en/java/javase/24/security/security-manager-is-permanently-disabled.html): impact on legacy permission/security APIs.

## Conclusion

**Identity authentication is the starting point, not a blanket license.** JAAS can authenticate users/services via `LoginContext` and `LoginModule`, placing trusted `Principal`s/credentials into a `Subject`. However, the application must still evaluate **actor, action, resource, and context** under explicit policy, check scope/tenant/owner/ACL at time of use, and deny by default when conditions are insufficient.

**JAAS authorization built on the Java Security Manager is a historical mechanism with major limits on modern JDKs** and does not replace business authorization. For Java 17+ and REST API services, enforce policy explicitly, test cases where authenticated users have **insufficient permissions**, and manage session/role revocation rather than checking `LoginContext.login()` alone.
