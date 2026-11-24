# 17.2 Subject, Principal, and Public or Private Credentials

In **JAAS (Java Authentication and Authorization Service)**, an authentication result is not necessarily represented by a single username string or an `isLoggedIn` boolean. JAAS groups **identities**, identifying attributes, and related **authentication credentials** into a **`javax.security.auth.Subject`** object. One `Subject` can hold **multiple Principals**, multiple **public credentials**, and multiple **private credentials**. Understanding these three sets is foundational for `LoginContext`, `LoginModule`, Kerberos/GSS-API, and Java code that uses subject-scoped keys or credentials.

This lesson focuses on **`Subject` structure and the meaning of Principal/public/private credentials**, while explaining a safe lifecycle. Two Java 17+ programs below exercise the APIs, from `getPrincipals(Class)` to `setReadOnly` and `Destroyable.destroy`, along with a minimal JAAS `login → commit → logout` flow.

## 1. Who Is `Subject`, and What Does `Principal` Represent?

In JAAS, a **Subject** represents **an entity** such as a user, service, or process; a Subject may carry multiple identities across different systems or roles. A **Principal** is an object implementing `java.security.Principal`, representing **an identity or an aspect of identity**.

~~~text
Subject (post-authentication entity)
  |
  +-- Set<Principal>
  |      UserId("alice")
  |      Role("auditor")
  |      RealmIdentity("alice@EXAMPLE.REALM")
  |
  +-- Set<Object> publicCredentials
  |      Public X.509 certificate, shareable data
  |
  +-- Set<Object> privateCredentials
         Sensitive Kerberos credentials, secret keys,
         proof of possession, or secret credentials
~~~

The classes `UserId`, `Role`, and `RealmIdentity` in the diagram are **illustrative names**, not standard Java classes. Built-in concrete types depend on the JAAS `LoginModule`/provider, such as `KerberosPrincipal` or OS-login principals. The runnable examples define their own Java records `UserId` and `Role`.

**Core principles:**

- `Subject` represents a **subject/entity**, not merely a username.
- `Principal` describes an **identity** belonging to the Subject, not a password, session token, or the private key itself.
- One `Subject` **can have multiple Principals**: user, role, group, realm, service, or corresponding identifiers.
- `Subject` **does not self-verify** a manually added Principal string. Any code with permission to mutate the Subject can create a Principal; trustworthiness comes from the **authentication process**.
- `Subject` is not a standalone permission engine, does not replace RBAC/ABAC, and does not issue JWTs or HTTP sessions by itself.

### 1.1. The Small Yet Crucial `Principal` Interface

~~~java
package java.security;

public interface Principal {
    String getName();
}
~~~

This is a condensed API shape for explanation, not the full JDK interface source. `getName()` returns **the name representing the identity**. Concrete implementations must define proper **`equals` and `hashCode`**, because Principals are stored in a **`Set`**. Two objects with the same identifier must compare consistently according to that type's policy; a Java 17 `record` provides value-based equality on its components, making it convenient for illustrative Principals.

~~~java
public record UserId(String name)
        implements java.security.Principal, java.io.Serializable {
    @Override
    public String getName() {
        return name;
    }
}
~~~

The record snippet above clarifies the interface; the hands-on program provides the enclosing class and tests. In production, include **issuer/realm/tenant** in the identity if the same username can appear across multiple systems; never compare solely on a non-unique display name.

### 1.2. Are User Principals and Role Principals the Same?

No. `UserId("alice")` identifies **a specific user**, whereas `Role("admin")` describes a **role/group facet** attached by a trusted system. If a Java service inserts a role from an untrusted HTTP header, it must not turn into administrative authority merely by sitting inside a `Subject`.

Distinguish:

- **Identity Principal:** username, account ID, service account ID, or Kerberos principal.
- **Group/Role Principal:** group/role belonging to the verified identity.
- **Realm/Tenant Principal:** identity boundary that prevents confusing same-named users across tenants.

**A Role Principal does not make authorization decisions on its own.** Code must evaluate **dedicated authorization policies**, resources, actions, tenants, and request state.

## 2. The Three Sets Inside a `Subject`

Java SE 17 `Subject` maintains three `Set`s:

| Collection | Java Method | Return Type | Meaning |
| --- | --- | --- | --- |
| **Principals** | `getPrincipals()` | `Set<Principal>` | Identities / identity facets of the Subject. |
| **Public credentials** | `getPublicCredentials()` | `Set<Object>` | Authentication data designed to be shared per the application model, such as public certificates. |
| **Private credentials** | `getPrivateCredentials()` | `Set<Object>` | Sensitive authentication data requiring separate protection, such as secret keys or tokens. |

Each collection is a **`Set`**, not a `List`:

- There is no meaningful guaranteed order for picking "the first principal" or "credential #0."
- Duplicates are rejected according to the elements' `equals`/`hashCode`.
- The same Principal name may exist in two different concrete classes and still be two distinct objects.
- Credentials hold `Object`s of arbitrary types; applications must know the **accepted classes** and trust constraints.

### 2.1. What Is a Public Credential?

JAAS documentation cites **public-key certificates** or certain service tickets designed to be shared. However, the word **public in the collection name does not mean anyone may read, log, or export it externally**. Safe disclosure depends on the credential type and policy.

Conceptual examples:

- `X509Certificate` is a public certificate; the private key is **not** inside the certificate.
- Verified certificate/realm metadata can assist in selecting a public key.
- A public credential in the demo is `PublicProfile("training-cert-label")`: **merely a label**, not a real certificate.

**A bearer token is still a secret** even though another endpoint can "see" the token on the wire. Do not place API keys or session secrets into `publicCredentials` just because you intend to transmit them between services. Classify based on **impersonation risk** and exposure impact.

### 2.2. What Is a Private Credential?

Private credentials are sensitive material needing extra protection, for example:

- Secret keys / HMAC keys used to prove identity or perform authorized operations.
- Sensitive Kerberos credentials/tickets per profile capable of executing operations under that identity.
- Tokens / proof-of-possession material or private-key handles needing restricted access.
- Credential types implementing **`javax.security.auth.Destroyable`** or **`Refreshable`** for lifecycle management.

A private credential **is not a database password hash** and does not have to be a `PrivateKey`. It can be any object a login provider uses to prove authority. Choose **concrete credential classes** and enforce appropriate access controls.

### 2.3. Public/Private Is a JAAS Classification, Not Encryption

**Adding an object to `getPrivateCredentials` does not automatically encrypt it**, does not put keys into an HSM, does not wipe memory when a session expires, and does not isolate access across all code in the same process. In environments using a **Security Manager** (historical model), Java checked `PrivateCredentialPermission` on private credential access. However, the Security Manager was **deprecated for removal in Java 17**; modern security architectures must not rely solely on those checks.

Real protection requires **application trust boundaries, avoiding indiscriminate object sharing, IAM/KMS/HSM, avoiding logging, logout/expiry lifecycles, and independent authorization**.

## 3. Creating a `Subject` and Adding Principals/Credentials

In Java 17:

~~~java
Subject subject = new Subject();
subject.getPrincipals().add(new UserId("alice"));
subject.getPrincipals().add(new Role("reader"));
subject.getPublicCredentials().add(new PublicProfile("training"));
subject.getPrivateCredentials().add(secretCredential);
~~~

This is an **illustrative snippet** requiring the `UserId`, `Role`, `PublicProfile` classes and a `secretCredential` variable; the complete program appears below. The `new Subject()` constructor creates three empty sets.

Another constructor has the form:

~~~java
new Subject(
    false,
    Set.of(new UserId("alice")),
    Set.of(new PublicProfile("training")),
    Set.of(secretCredential)
);
~~~

The first boolean parameter is **`readOnly`**. The constructor copies elements into **new internal `Set`s** rather than retaining the passed-in `Set`s directly; **however, it does not deep-copy the objects** inside. Both constructors and set methods reject null collections and null elements.

**Distinguish clearly:**

- `new Subject()` → writable, no verified identity yet.
- `new Subject(true, ...)` → populated with initial data, but the `Set`s prohibit subsequent add/remove.
- `new Subject(false, ...)` → populated with initial data and mutable subject to permissions/policy.
- `LoginContext.login()` + `LoginModule.commit()` → the standard JAAS path to **attach verified data**, rather than trusting a self-assembled `Subject`.

### 3.1. Add/Remove and Duplicate Principals

~~~java
subject.getPrincipals().add(new UserId("alice")); // new element
subject.getPrincipals().add(new UserId("alice")); // duplicate not added
~~~

With a single-field `name` record in Java, two `UserId`s for `"alice"` have identical `equals`/`hashCode`. Because it is a `Set`, size increases only once. That **does not prevent a `Subject` from holding two different `UserId`s**; if business logic requires a single account ID, the application must validate that invariant.

Never rely on `Principal.getName()` alone to conclude that Principals of different types or realms represent the same identity. Maintain explicit namespaces/issuers/tenants.

## 4. Live Sets vs. Class-Filtered Copies

An easily misunderstood detail of the Java 17 `Subject` API:

| Method | Is the returned set backed by Subject? | Consequence |
| --- | --- | --- |
| `getPrincipals()` | **Yes** | add/remove on the returned set mutates the Subject's Principal set. |
| `getPublicCredentials()` | **Yes** | add/remove on the returned set mutates the public credential set. |
| `getPrivateCredentials()` | **Yes** | add/remove on the returned set mutates the private credential set. |
| `getPrincipals(UserId.class)` | **No**, new filtered set | clear/add/remove on the filtered set does not modify the Subject. |
| `getPublicCredentials(MyClass.class)` | **No**, new filtered set | The filtered result set is not a way to update the Subject. |
| `getPrivateCredentials(MyClass.class)` | **No**, new filtered set | Does not deep-copy secret objects, and still enforces relevant permission checks. |

**The new typed set** does not create **deep copies of credential objects**: it holds **references to the same objects**. Mutating or destroying a mutable private credential affects every holder of that reference, even though the filtered set is not backed by the Subject.

### 4.1. Risks of Exposing Live Sets

Suppose a service returns `subject.getPrincipals()` directly to an untrusted plugin or component. When the Subject is writable, the plugin could add `Role("admin")` or remove roles, corrupting identity data trusted by downstream code.

**Better design:** expose a read-only facade or DTO containing only safe data; allow only the authentication module/trust layer to add/remove Principals. `Collections.unmodifiableSet(subject.getPrincipals())` **is not an immutable snapshot**: the wrapper blocks writes through itself yet reflects underlying Subject changes. For a stable identity snapshot, copy into a new set of immutable Principals or a DTO.

### 4.2. Accessing Private Credentials and `PrivateCredentialPermission`

In Java 17, **when a Security Manager is present**:

- Modifying Principal/public/private sets may require the corresponding **`AuthPermission`**.
- Iterating over untyped `getPrivateCredentials()` can throw **`SecurityException`** if **`PrivateCredentialPermission`** is missing for a credential.
- `getPrivateCredentials(SomeClass.class)` requires permission for matching credentials per its contract; if missing, it can throw `SecurityException`.

These checks depend on an active **Security Manager** and policy. They are JAAS compatibility details and **do not replace least privilege, process isolation, and application-level authorization**.

## 5. Read-Only `Subject`: Locks the Sets, Not Every Object

Once JAAS finishes authentication and roles/credentials should no longer change, an application may call **`subject.setReadOnly()`**.

~~~java
subject.setReadOnly();
boolean locked = subject.isReadOnly();
~~~

After `setReadOnly`:

1. Principals or public/private credentials cannot be added/removed **through the `Subject`'s `Set`s**; any mutation attempt throws **`IllegalStateException`**.
2. There is no API to turn a read-only `Subject` back into writable.
3. **Existing credential objects** do not automatically become deeply immutable. A private credential can still have internal state mutated or have **`Destroyable.destroy()`** called even when the Subject is read-only.
4. A destroyed object may **still remain in the `Set`** because destroying contents is not equivalent to removing from the Subject; in a read-only Subject, removing the credential object may be rejected.
5. **Read-only is not a security boundary protecting secrets**: code holding a reference to a secret object or able to use a key still needs separate access controls.

~~~text
Subject writable:
  + add/remove Principal
  + add/remove credentials
  + mutate/destroy credential object (per object contract)

subject.setReadOnly()

Subject read-only:
  - add/remove in the three Subject sets -> IllegalStateException
  + destroy credential object (if supported by class)
  ? object may still be mutable if not immutable
~~~

**Note when using `LoginContext.logout`:** a `LoginModule` typically needs to remove the exact Principals/credentials it added in `commit`. If you call `setReadOnly` too early, `logout` may **fail to remove entries from the `Set`**; a compliant implementation can destroy credentials yet cannot remove the objects. Design the lifecycle explicitly: who is allowed to close the session, when to mark read-only, and how to ensure expired session data is never still trusted by the application.

### 5.1. Read-Only Differs from an Immutable DTO

An **immutable DTO** typically carries only business-needed fields, such as `userId`, `tenantId`, `roles`, and `issuedAt`. It holds no private secrets. **`Subject.setReadOnly`** only forbids mutating the collections and still retains credential objects. Never pass a `Subject` directly into an HTTP response, Redis, JSON logger, or distributed cache.

To export allowed identity information, **map from `Subject` to a safe DTO using an allowlist**. Never serialize or stringify an entire `Subject` as a shortcut.

## 6. Private Credentials and `Destroyable`

**`javax.security.auth.Destroyable`** provides two methods:

~~~java
void destroy() throws DestroyFailedException;
boolean isDestroyed();
~~~

This is an illustrative interface outline, omitting default-method details. `Destroyable` **does not guarantee every implementation wipes memory**, because the default `destroy` may throw **`DestroyFailedException`**; inspect the **concrete implementation**. Sensitive objects can implement `destroy` to zero `char[]`/`byte[]` arrays or release key handles.

**A credential management strategy needs:**
- Clear **ownership**: who creates, who issues, who closes/destroys.
- Minimized copies, lifetimes, logging, and transmission.
- Calling destroy/logout/revoke when a session ends per the credential's contract.
- Handling destroy exceptions and refusing to use credentials after destruction.
- Separating **removing a reference from `Subject`** from **wiping secret material**. The two operations are not equivalent.
- Not relying on the JVM GC to promptly zero secret bytes; not claiming `Arrays.fill` erases every copy in frameworks or native heaps.

### 6.1. Public Credentials Still Need Lifecycle Management

A public-key certificate may be shareable yet still has **validity periods, key usage, issuer, revocation status**, and policies. Having a public certificate inside a `Subject` does not mean its chain was verified for every business action. Conversely, if a "ticket" is a replayable bearer capability that impersonates the subject, treat it as **sensitive** regardless of JAAS documentation examples listing shareable ticket types.

### 6.2. Do Not Print `Subject` or Credentials Arbitrarily

**`Subject.toString()`, `Object.toString()`, and collection logging** can invoke `toString` on Principals or credentials and leak information. You should:
- Avoid logging an entire `Subject`, especially private credentials.
- For custom credentials, override `toString` to return a **redacted value**.
- Audit using **permitted account/tenant IDs, event types, trace IDs, and outcomes**; never print passwords, session secrets, private keys, tokens, or Kerberos tickets.
- Never put credentials into `equals`/`hashCode` used for caching or logging. `Subject` equality depends on its Principal/credential sets; it is not a stable account identity.

## 7. Java 17+ — Program 1: `Subject`, `Principal`, and the Three Sets

A standalone example using `UserId`/`Role` records, a `PublicProfile` record, and a `SessionSecret` class implementing `Destroyable`. `SessionSecret` is **not a real credential**; it only illustrates destroying an internal `char[]`. The program intentionally adds the same `UserId` twice to demonstrate `Set` deduplication, and exercises typed snapshots, live sets, and read-only mode.

Create the file **`SubjectCredentialDemo.java`**:

~~~java
import java.io.Serializable;
import java.security.Principal;
import java.util.Arrays;
import java.util.Set;
import javax.security.auth.Destroyable;
import javax.security.auth.Subject;

public class SubjectCredentialDemo {
    public record UserId(String name) implements Principal, Serializable {
        @Override public String getName() { return name; }
    }
    public record Role(String name) implements Principal, Serializable {
        @Override public String getName() { return name; }
    }
    public record PublicProfile(String label) {}

    public static final class SessionSecret implements Destroyable {
        private char[] value;
        public SessionSecret(char[] input) { value = input.clone(); }
        @Override public synchronized void destroy() {
            if (value != null) {
                Arrays.fill(value, '\0');
                value = null;
            }
        }
        @Override public synchronized boolean isDestroyed() {
            return value == null;
        }
        @Override public String toString() {
            return "SessionSecret[REDACTED]";
        }
    }

    public static void main(String[] args) throws Exception {
        Subject subject = new Subject();
        subject.getPrincipals().add(new UserId("alice"));
        subject.getPrincipals().add(new UserId("alice"));
        subject.getPrincipals().add(new Role("reader"));
        subject.getPublicCredentials().add(new PublicProfile("training-cert-label"));

        char[] original = "fake-session-material".toCharArray();
        SessionSecret secret = new SessionSecret(original);
        Arrays.fill(original, '\0');
        subject.getPrivateCredentials().add(secret);

        System.out.println("Distinct Principals: " + subject.getPrincipals().size());
        System.out.println("UserId: " + subject.getPrincipals(UserId.class).size());
        System.out.println("Public profile: " +
                subject.getPublicCredentials(PublicProfile.class).size());
        System.out.println("Private credential: " +
                subject.getPrivateCredentials(SessionSecret.class).size());

        Set<UserId> snapshot = subject.getPrincipals(UserId.class);
        snapshot.clear();
        System.out.println("Clearing snapshot does not change Subject: " +
                (subject.getPrincipals(UserId.class).size() == 1));

        Set<Principal> live = subject.getPrincipals();
        live.add(new Role("auditor"));
        System.out.println("Live set modifies Subject: " +
                (subject.getPrincipals().size() == 3));

        subject.setReadOnly();
        boolean blocked = false;
        try {
            subject.getPrincipals().add(new Role("admin"));
        } catch (IllegalStateException expected) {
            blocked = true;
        }
        System.out.println("Read-only rejects set mutation: " + blocked);
        secret.destroy();
        System.out.println("Private credential still destroyable: " +
                secret.isDestroyed());
        System.out.println("Credential object remains in set: " +
                (subject.getPrivateCredentials().size() == 1));
    }
}
~~~

Run with JDK 17 or newer:

~~~bash
javac --release 17 -encoding UTF-8 SubjectCredentialDemo.java
java SubjectCredentialDemo
~~~

Verified stdout:

~~~text
Distinct Principals: 2
UserId: 1
Public profile: 1
Private credential: 1
Clearing snapshot does not change Subject: true
Live set modifies Subject: true
Read-only rejects set mutation: true
Private credential still destroyable: true
Credential object remains in set: true
~~~

### 7.1. Analyzing the Results

- **Distinct Principals: 2**: `UserId("alice")` was added twice, yet the `Set` keeps only one `UserId` and one `Role("reader")`.
- **Public profile: 1**: the `training-cert-label` label is illustrative metadata, containing no real certificate or secret.
- **Private credential: 1**: one `SessionSecret` object resides in `privateCredentials`; neither `char[]` nor a revealing `toString` is printed.
- **Clearing snapshot does not change Subject: true**: `getPrincipals(UserId.class)` creates a new `Set`, so `clear` only mutates the filtered collection.
- **Live set modifies Subject: true**: `Set<Principal>` from `getPrincipals()` is backed by the `Subject`; adding `Role("auditor")` brings the total to 3.
- **Read-only rejects set mutation: true**: after `setReadOnly`, `Role("admin")` cannot be added.
- **Private credential still destroyable: true**: `SessionSecret.destroy` wipes the internal `char[]` and updates its status.
- **Credential object remains in set: true**: `destroy` differs from `remove`; the destroyed object stays inside the read-only `Subject`.

**Test limitations:** Principals were added manually to demonstrate collection semantics, **which does not prove user `alice` actually logged in**. The program does not implement Kerberos, an IAM system, or authorization policies. The `"fake-session-material"` string is test data, not a production credential.

### 7.2. Why Is `Serializable` Needed on `Principal`?

Java 17 `Subject` supports `Serializable`; per its Javadoc, **Principals inside a `Subject` can be serialized**, whereas **the credential sets are not serialized**. Because `java.security.Principal` **does not itself extend `Serializable`**, concrete Principal classes must implement `Serializable` if you want to serialize a `Subject`. **Never use `Subject` serialization as full login-session persistence or to transport private credentials**.

Actively restrict `Subject` serialization because it may contain **sensitive identities and untrusted Principal classes**. Prefer verified DTOs with versioned schemas.

### 7.3. Practical Read-Only Takeaway

**`Subject.setReadOnly` does not erase secrets** and does not perform logout. When terminating a session, invoke **`LoginContext.logout`** or a dedicated revocation/`credential.destroy` flow while the sets are still mutable if the `LoginModule` needs to remove items. A destroyed credential must never be reused even if an object reference still exists.

## 8. `LoginContext` and `LoginModule`: When Does `Subject` Receive Its Principals?

A `Subject` created via `new Subject()` with manually added `Role`s is just a data object. In JAAS **structured authentication**, **`LoginContext`** coordinates one or more **`LoginModule`**s according to a **`Configuration`**. Normally, a module verifies credentials during the `login` phase, and **only when overall authentication succeeds** does it attach Principals and credentials to the `Subject` during the `commit` phase.

~~~text
Application creates LoginContext(name, Subject/handler/config)
                    |
                    v
               LoginContext.login()
                    |
                    v
      LoginModule.initialize(Subject, CallbackHandler, ...)
                    |
                    v
      LoginModule.login() -- verify secret/identity
                    |
             sufficient modules succeed?
               /              \
             Yes               No
              |                  |
              v                  v
      LoginModule.commit()   LoginModule.abort()
      attach Principal/cred  clear temp state, do not attach invalid identity
              |
              v
    LoginContext.getSubject()
    authenticated identity/credential
              |
              v
    LoginContext.logout()
    LoginModule.logout() removes and destroys only the
    Principals/credentials that the module added
~~~

### 8.1. `LoginModule` Methods

| Method | Timing | Responsibility |
| --- | --- | --- |
| **`initialize`** | `LoginContext` prepares the module | Receives `Subject`, `CallbackHandler`, `sharedState`, and `options`. Does not assert login success yet. |
| **`login`** | Authentication phase | Obtains/verifies credentials and keeps temporary state; returns `true`/`false` or throws `LoginException` per contract. |
| **`commit`** | Overall login succeeds per module flags | Attaches **only the module's Principals and credentials** to `Subject`; clears authentication state no longer needed. |
| **`abort`** | Authentication/commit fails | Removes/destroys temporary state or partially committed data; leaves no invalid identity behind. |
| **`logout`** | When application explicitly ends the JAAS session | Removes Principals and credentials **created by this module** and destroys secrets appropriately. |

When multiple `LoginModule`s share one `LoginContext`, **each module should manage only the elements it added**. Clearing the entire `Subject` in one module's logout can destroy data added by another module or independently verified by the application.

### 8.2. Module Control Flags

In **JAAS Configuration**, each `LoginModule` has a flag:

- **`REQUIRED`**: must succeed, yet execution continues to remaining modules; if it fails, overall login fails.
- **`REQUISITE`**: must succeed; if it fails, the login phase terminates early.
- **`SUFFICIENT`**: success may allow skipping remaining modules if no prior `REQUIRED`/`REQUISITE` module failed.
- **`OPTIONAL`**: may succeed or fail; overall outcome still follows the rules for remaining modules.

For multi-module coordination details and corner cases, consult the `Configuration` Javadoc and the JAAS LoginModule Developer's Guide. **Never interpret `OPTIONAL` as "every user is allowed to log in."** In all cases, business code may trust a `Subject` only after **`LoginContext.login()` returns normally**.

### 8.3. `CallbackHandler` and Secrets

**`NameCallback`** and **`PasswordCallback`** are commonly used for password-login demos; real systems may use Kerberos, tokens, PKCS#11, or provider-specific login. **`PasswordCallback`** accepts `char[]` and supports `clearPassword`; both the caller and `LoginModule` should wipe temporary `char[]` arrays. Never log passwords and never store them in `Subject` as Principals. A module may attach a private credential **after authentication** if required, without storing the raw password.

**Do not treat `LoginModule` as a password hasher**: production password authentication requires a proper KDF/verifier, a trusted identity source, and rate limiting against online guessing. The example below is intentionally an **in-memory training module** comparing a test password solely to illustrate the JAAS lifecycle, and must never be used as a real login system.

## 9. Java 17+ — Program 2: `LoginContext`, `commit`, and `logout`

The example supplies a programmatic `Configuration` (no need to edit the JVM's global JAAS login config), a `DemoLoginModule`, and a `CallbackHandler`. When the test username/password match, the module:
- Adds a **`UserId` Principal** representing the authenticated identity.
- Adds a **`PublicProfile`** containing only an illustrative public label.
- Adds a **`PrivateProof`** wrapping a mock `char[]` and implementing **`Destroyable`**.

On `logout`, the module removes **only the three elements it owns** and destroys the proof. With a wrong password, login fails and there is no authenticated `Subject` from the fresh `LoginContext`. The program never stores the user's password in the `Subject`.

Create the file **`JaasLoginSubjectDemo.java`**:

~~~java
import java.io.IOException;
import java.io.Serializable;
import java.security.Principal;
import java.util.Arrays;
import java.util.Map;
import javax.security.auth.Destroyable;
import javax.security.auth.Subject;
import javax.security.auth.callback.Callback;
import javax.security.auth.callback.CallbackHandler;
import javax.security.auth.callback.NameCallback;
import javax.security.auth.callback.PasswordCallback;
import javax.security.auth.callback.UnsupportedCallbackException;
import javax.security.auth.login.AppConfigurationEntry;
import javax.security.auth.login.Configuration;
import javax.security.auth.login.FailedLoginException;
import javax.security.auth.login.LoginContext;
import javax.security.auth.login.LoginException;
import javax.security.auth.spi.LoginModule;

public class JaasLoginSubjectDemo {
    public record UserId(String name) implements Principal, Serializable {
        @Override public String getName() { return name; }
    }
    public record PublicProfile(String source) {}
    public static final class PrivateProof implements Destroyable {
        private char[] contents;
        public PrivateProof(char[] input) { contents = input.clone(); }
        @Override public synchronized void destroy() {
            if (contents != null) {
                Arrays.fill(contents, '\0');
                contents = null;
            }
        }
        @Override public synchronized boolean isDestroyed() {
            return contents == null;
        }
        @Override public String toString() {
            return "PrivateProof[REDACTED]";
        }
    }

    public static final class DemoLoginModule implements LoginModule {
        private Subject subject;
        private CallbackHandler handler;
        private boolean authenticated;
        private boolean committed;
        private String account;
        private UserId principal;
        private PublicProfile profile;
        private PrivateProof proof;

        @Override public void initialize(Subject subject,
                CallbackHandler callbackHandler, Map<String, ?> sharedState,
                Map<String, ?> options) {
            this.subject = subject;
            this.handler = callbackHandler;
        }

        @Override public boolean login() throws LoginException {
            NameCallback user = new NameCallback("User");
            PasswordCallback pass = new PasswordCallback("Password", false);
            char[] supplied = null;
            try {
                handler.handle(new Callback[] { user, pass });
                supplied = pass.getPassword();
                char[] expected = "training-pass".toCharArray();
                boolean valid;
                try {
                    valid = "alice".equals(user.getName())
                            && Arrays.equals(supplied, expected);
                } finally {
                    Arrays.fill(expected, '\0');
                }
                if (!valid) {
                    throw new FailedLoginException("Invalid credentials");
                }
                account = user.getName();
                authenticated = true;
                return true;
            } catch (IOException | UnsupportedCallbackException error) {
                throw new LoginException("Credential callback failed");
            } finally {
                if (supplied != null) Arrays.fill(supplied, '\0');
                pass.clearPassword();
            }
        }

        @Override public boolean commit() {
            if (!authenticated) return false;
            principal = new UserId(account);
            profile = new PublicProfile("training-directory");
            char[] material = "not-a-real-token".toCharArray();
            try {
                proof = new PrivateProof(material);
            } finally {
                Arrays.fill(material, '\0');
            }
            subject.getPrincipals().add(principal);
            subject.getPublicCredentials().add(profile);
            subject.getPrivateCredentials().add(proof);
            account = null;
            committed = true;
            return true;
        }

        private void cleanup() {
            if (subject != null) {
                if (principal != null) subject.getPrincipals().remove(principal);
                if (profile != null) subject.getPublicCredentials().remove(profile);
                if (proof != null) {
                    subject.getPrivateCredentials().remove(proof);
                    proof.destroy();
                }
            }
            principal = null;
            profile = null;
            proof = null;
            account = null;
            authenticated = false;
            committed = false;
        }

        @Override public boolean abort() {
            boolean hadState = authenticated || committed;
            cleanup();
            return hadState;
        }
        @Override public boolean logout() {
            boolean hadState = committed;
            cleanup();
            return hadState;
        }
    }

    private static Configuration configuration() {
        return new Configuration() {
            @Override public AppConfigurationEntry[] getAppConfigurationEntry(
                    String name) {
                if (!"Training".equals(name)) return null;
                return new AppConfigurationEntry[] {
                        new AppConfigurationEntry(
                                DemoLoginModule.class.getName(),
                                AppConfigurationEntry.LoginModuleControlFlag.REQUIRED,
                                Map.of())
                };
            }
        };
    }

    private static CallbackHandler callbacks(String userName, char[] password) {
        return entries -> {
            for (Callback entry : entries) {
                if (entry instanceof NameCallback name) {
                    name.setName(userName);
                } else if (entry instanceof PasswordCallback pass) {
                    pass.setPassword(password);
                } else {
                    throw new UnsupportedCallbackException(entry);
                }
            }
        };
    }

    public static void main(String[] args) throws Exception {
        char[] accepted = "training-pass".toCharArray();
        try {
            LoginContext login = new LoginContext(
                    "Training", null, callbacks("alice", accepted),
                    configuration());
            login.login();
            Subject subject = login.getSubject();
            PrivateProof proof = subject.getPrivateCredentials(
                    PrivateProof.class).iterator().next();
            System.out.println("Login succeeded: " + (subject != null));
            System.out.println("Principal alice: " +
                    subject.getPrincipals(UserId.class).iterator().next().getName());
            System.out.println("Public credentials: " +
                    subject.getPublicCredentials(PublicProfile.class).size());
            System.out.println("Private credentials: " +
                    subject.getPrivateCredentials(PrivateProof.class).size());
            login.logout();
            System.out.println("Logout removes Principal: " +
                    subject.getPrincipals().isEmpty());
            System.out.println("Logout removes credentials: " +
                    (subject.getPublicCredentials().isEmpty()
                            && subject.getPrivateCredentials().isEmpty()));
            System.out.println("Logout destroys private proof: " + proof.isDestroyed());
        } finally {
            Arrays.fill(accepted, '\0');
        }

        char[] rejected = "wrong".toCharArray();
        try {
            LoginContext bad = new LoginContext(
                    "Training", null, callbacks("alice", rejected),
                    configuration());
            boolean denied = false;
            try {
                bad.login();
            } catch (LoginException expected) {
                denied = true;
            }
            System.out.println("Wrong password rejected: " + denied);
            System.out.println("Failure has no authenticated Subject: " +
                    (bad.getSubject() == null));
        } finally {
            Arrays.fill(rejected, '\0');
        }
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -encoding UTF-8 JaasLoginSubjectDemo.java
java JaasLoginSubjectDemo
~~~

Test output:

~~~text
Login succeeded: true
Principal alice: alice
Public credentials: 1
Private credentials: 1
Logout removes Principal: true
Logout removes credentials: true
Logout destroys private proof: true
Wrong password rejected: true
Failure has no authenticated Subject: true
~~~

### 9.1. What Is Demonstrated?

1. **`Configuration`** is supplied directly via the `LoginContext(name, subject, handler, config)` overload; no need to edit the JVM's global configuration file.
2. **`LoginContext.login`** coordinates the module with the `REQUIRED` flag; because there is only one module in the demo, login succeeds when that module authenticates successfully.
3. **`DemoLoginModule.login`** uses callbacks to read username/password; this is a **fixed string comparison for testing**, not secure production password verification.
4. **`commit`** attaches `UserId`, `PublicProfile`, and `PrivateProof`. They live in **three separate `Set`s**, not combined into one `Map`.
5. **`getSubject`** returns the `Subject` after successful login; never fetch it before login and assume it is authenticated.
6. **`logout`** removes only the three elements `DemoLoginModule` added and calls `destroy()` on `PrivateProof`.
7. **Failed login** leaves `LoginContext` with no authenticated `Subject` when the constructor received no `Subject` and authentication failed.
8. **`char[]` passwords** are wiped in `PasswordCallback` and the caller for the memory arrays they own; never assume every JVM copy was erased.

### 9.2. What Does This Minimal Sample Intentionally Omit?

- **Real identity store, salt/password hashing KDF, rate limiting, MFA, auditing, anti-enumeration, and account lockout**: production applications must supply these via appropriate providers/components.
- **Real proof management**: `PrivateProof` only holds a placeholder string; it is not a token/secret usable for system access.
- **Multiple `LoginModule`s**: the demo uses one `REQUIRED` module; real systems have multiple modules and must handle both `commit` and `abort` cleanup properly.
- **Transactional commit**: the demo lacks complex rollback if adding elements fails partway. Production implementations must clean up on commit errors and on re-invocation.
- **Read-only `Subject`**: the demo does not freeze the `Subject` before `logout` because it needs to remove the added elements.
- **HTTP session management**: JAAS `Subject` does not store browser sessions or issue cookies or access tokens.

**Important:** never copy `Arrays.equals` against a hardcoded password string into production. That is purely a self-contained test fixture with no resistance to password guessing. Production designs must use trusted authentication mechanisms and abuse controls.

## 10. `Subject.doAs`: Scoped Execution and Limitations of the Legacy Security Model

In Java SE 17, **`Subject.doAs(subject, PrivilegedAction)`** and **`Subject.doAs(subject, PrivilegedExceptionAction)`** run an action within an **`AccessControlContext`** bound to a `Subject`. The historical JAAS model combined this Principal information with the Java Security Manager/policy to evaluate certain permissions.

Example **code fragment**, not a standalone program:

~~~java
String answer = Subject.doAs(authenticatedSubject,
        (java.security.PrivilegedAction<String>) () -> {
            // Code executing an operation within the Subject's JAAS context.
            return "operation-finished";
        });
~~~

**Do not misunderstand:**

- `doAs` **does not authenticate** a user, does not turn a self-created Principal into a trusted identity, and does not authorize arbitrary operations.
- `doAs` **does not automatically forward bearer tokens/private credentials** to other services. Kerberos/GSS-API protocols or specific libraries may read Subject credentials, following provider APIs.
- `doAs` in Java 17 relies on **`AccessControlContext`/Security Manager**, a model with APIs already deprecated for removal. In particular, **`Subject.getSubject(AccessControlContext)`** is marked deprecated for removal in Java 17.
- Do not assume **`doAs` context propagates automatically across `ExecutorService`, `CompletableFuture`, or thread pools**. Check specific API/JDK/provider behavior and pass identity/authorization context across async boundaries explicitly and safely.
- For modern Java services, **authorization should be checked explicitly by identity, role, tenant, and resource** at the application layer or an actively maintained security framework; never treat `doAs` as a general authorization layer.

**This lesson mentions `doAs` only to show how `Subject` connects to the JAAS model**, without requiring a Security Manager or making it a prerequisite for the two runnable examples.

## 11. `Subject` Does Not Replace System Security Boundaries

A `Subject` can be consulted by application code to learn who is making a request. However:

1. **The `Subject` input must be trusted:** a `LoginModule`/provider or authentication layer verified the identity; never trust raw unverified cookies/headers.
2. **Select the right Principal class:** if the system supports multiple realms, never pick the first Principal or filter by name without a namespace.
3. **Clear credential scoping:** never keep secret credentials in a process-wide shared `Subject`; avoid leaking access tokens across tenants or services.
4. **Data in `Subject` has a lifecycle:** logout, session expiry, key rotation, credential refresh/revocation; an object still referenced after logout may linger if a caller holds its own reference.
5. **Check business permissions:** a `Subject` with `Role("admin")` does not guarantee the caller may view another tenant's records.
6. **Private key management:** a private-key handle from an HSM may be non-exportable; perform operations via the provider's policy without attempting to extract key bytes for debugging.
7. **Minimal auditing:** record authorized subject IDs, event types, issuers, actions, outcomes, and trace IDs; never log the full `Subject` or private credentials.

### 11.1. Designing Boundaries for a Web Service

~~~text
HTTP request (untrusted header/token/cookie)
             |
             v
Authentication layer (JAAS module, IdP, framework...)
       verify certificate/ticket/token/password
             |
      authentication succeeded?
        /            \
       no             yes
       |               |
     reject            v
                  Subject + Principal(s)
                  properly scoped public/private credentials
                       |
                       v
                 Build safe identity DTO
                 verified userId, tenantId, roles
                       |
                       v
                 Authorize action + resource
                       |
                       v
                    Business logic
                       |
                       v
                  session end / logout /
                  destroy secret / revoke
~~~

Many modern web systems use dedicated authentication/security frameworks rather than calling JAAS `LoginContext` directly. Even so, **separating identity (`Principal`), completed verification (authentication), and execution rights (authorization)** is core knowledge applicable everywhere.

### 11.2. Identity DTOs Differ from Credential Stores

A DTO intended for business logic should carry only necessary fields such as **stable user ID, tenant ID, approved roles, issuer, and authentication timestamp when needed**. It must not contain raw passwords, private keys, Kerberos tickets, or bearer tokens. Creating the DTO may filter by a specific Principal class and check uniqueness, remembering that typed `Set`s **do not deep-copy** mutable Principals; convert them into immutable application values.

## 12. Threading, Serialization, and Subtle Details

### 12.1. Do Not Share a Mutable `Subject` Across Requests

Because untyped sets are backed by the `Subject`, two threads can observe and mutate identity data without clear ownership. With multiple JAAS modules or session lifecycles, one request reading credentials could touch a credential just destroyed/logged out by another request.

Recommendations:
- Each authenticated session has its **own lifecycle**; never reuse one global `Subject` and swap Principals per request.
- Creation/commit/logout phases must align properly with the provider/lifecycle.
- **Never use `Subject` `equals`/`hashCode` as a stable cache key**: Principal/credential sets participate in equality and can change.
- For async work, pass an **immutable security context/DTO** or an explicitly scoped handle; never share raw private credentials with arbitrary jobs.
- **Do not expect read-only mode to prevent credential destruction**: every consumer must handle expired or destroyed credentials.

### 12.2. `Subject` Serialization Excludes Private Credentials

According to the Java 17 `Subject` Javadoc, `Subject` implements `Serializable`: **Principals are serialized**, while **credentials are not serialized**. Because `java.security.Principal` does not itself implement `Serializable`, Principal implementations must implement `Serializable` if you intend to serialize the `Subject`.

Therefore:
- Serializing/deserializing a `Subject` **does not round-trip credentials**. Never use it for session persistence or key backup.
- Never allow arbitrary deserialization of untrusted Java data; Java object deserialization carries independent risks.
- Build dedicated, versioned, field-controlled DTO schemas if you need to transmit identities across services.

### 12.3. Secret Destroyed While Object Remains in the `Set`

A credential implementing `Destroyable` can be destroyed while the `Subject` is **`read-only`**, per the `Subject` contract. The object can remain in `getPrivateCredentials()` because it cannot be removed. That does not mean the credential is still usable; consult `isDestroyed`/type-specific lifecycle. For credential classes that do not support destruction or fail to destroy, a login/logout framework needs an explicit error-handling strategy rather than silently claiming the secret was wiped.

## 13. Recommended Test Suite for `Subject` and `LoginModule`

| Group | Test | Expected Outcome |
| --- | --- | --- |
| **Fresh Subject** | `new Subject()` | Three empty sets, initially writable. |
| **Principal equality** | Add `UserId("alice")` twice | No duplicate with record value equality. |
| **Multiple Principals** | Add `UserId` and `Role` | Set retains both concrete types. |
| **Public credential** | Add `PublicProfile` label | Readable from public set; not confused with private set. |
| **Private credential** | Add `SessionSecret` | Readable by matching type; `char[]`/token never logged. |
| **Live set** | Call `getPrincipals()` then `add(Role)` | Subject is updated. |
| **Typed snapshot** | Call `getPrincipals(UserId.class)` then `clear` | Original Subject unchanged. |
| **Reference aliasing** | Typed filtered private set points to same object | Destroying object is visible everywhere holding a reference. |
| **Read-only** | `setReadOnly` then add/remove | `IllegalStateException`; cannot revert to writable. |
| **Destroy** | Destroy private credential after `setReadOnly` | Allowed if type supports it; distinct from removal from `Set`. |
| **Subject constructor** | Null set / null element, `readOnly` true | Rejects null, keeps initial elements, enforces read-only. |
| **Login success** | Callback supplies valid credentials, `login` | `commit` creates Principal/public/private in proper scope. |
| **Login failure** | Callback supplies wrong password | `LoginException`; no authenticated `Subject` when no initial `Subject` passed. |
| **Abort** | A required module fails or `commit` fails | Clears temporary state; leaves no leaked or partially committed credentials. |
| **Logout** | `login` followed by `logout` | Removes only elements the module added; destroys secrets. |
| **Multi-module** | Two `LoginModule`s share one `Subject` | Module A does not delete B's Principals/credentials. |
| **Private permission** | Java 17 Security Manager + restrictive policy | Private credential access checked via `PrivateCredentialPermission`; `SecurityException` handled. |
| **Serialization** | `Subject` with `Serializable` Principal and credentials | Credentials are not serialized per contract; not used as session token. |
| **Concurrent logout/use** | One thread logs out/destroys while another processes | Does not continue using destroyed secret; clear ownership. |
| **Log inspection** | Invoke logger with `Subject` | Audit logs do not print passwords or private credential material. |

With a real `LoginModule`, also test the **authentication source** (directory/Kerberos/IdP), account lockout/rate limiting, ticket expiry/refresh, permissions, revocation, and auditing. The two demos only verify **core `Subject`/`Principal`/credential contracts** and do not replace integration tests for production providers.

## 14. Common Mistakes

1. **Treating `Subject` as a username `String`.** It can hold multiple identities and credentials.
2. **Adding `Role("admin")` manually and thinking the user is authenticated.** Principals are trustworthy only after authentication and a proper trust boundary.
3. **Putting passwords or bearer tokens into `Principal`.** Principals describe identity; secrets belong in appropriate credential/secret layers.
4. **Assuming `publicCredentials` is always safe to log.** Depending on type, a ticket/token can still be a sensitive bearer capability.
5. **Assuming `privateCredentials` automatically encrypts or locks secrets with modern JVM permissions.** `Subject` is just a collection container; real protection must be designed explicitly.
6. **Confusing `getPrincipals()` and `getPrincipals(Class)`.** Untyped is live; typed is a new unbacked set.
7. **Mistaking a typed filtered credential set for a deep copy of secrets.** Elements are references to the original objects.
8. **Letting every layer hold a mutable `Subject`.** They could alter roles/credentials without a trust boundary.
9. **Using `Subject.setReadOnly` as a substitute for `logout`.** Read-only neither removes Principals nor erases secrets.
10. **Assuming read-only prevents credential destruction.** The contract permits destroying credentials even when `Subject` is read-only.
11. **Removing a credential from the `Set` and assuming secret bytes were wiped.** Reference removal and memory clearing are two different actions.
12. **Calling `destroy` and assuming every secret copy in the JVM vanished.** Copies and implementation-dependent state may still exist.
13. **Logging `Subject.toString()` or all credentials.** Risks leaking identities, secrets, and session details.
14. **Using `principal.getName()` without issuer/realm/tenant.** Easy to confuse same-named identities.
15. **Using `Subject.equals`/`hashCode` as a stable user ID.** Equality depends on credential/Principal sets, not account identity.
16. **Attaching a Principal to `Subject` inside `login()` before overall authentication succeeds.** Commit only after all modules satisfy policy; `abort` cleans up state.
17. **Wiping the entire `Subject` in `LoginModule.logout()`.** May erase items from other modules; remove only what you own.
18. **Calling `setReadOnly` before `LoginModule.logout`.** May prevent modules from removing their Principals/credentials.
19. **Reusing one person's `LoginContext` to authenticate another.** Create a separate `LoginContext` per Subject/session.
20. **Using `Subject.doAs` as complete authorization for a new web app.** That is a historical JAAS/`AccessControlContext` model, not a replacement for application RBAC/ABAC.
21. **Expecting JAAS to manage token refresh and network sessions automatically.** Refresh/logout/revocation paths depend on credential type, provider, and application.
22. **Serializing `Subject` to persist an entire session with credentials.** Credentials are not serialized per contract.

## 15. Self-Check Questions

**1. Can one `Subject` hold multiple Principals?**  
Yes. `Subject` has a `Set<Principal>`, and each Principal can represent a different identity, role, or realm.

**2. Are `UserId("alice")` and `Role("alice")` necessarily the same Principal?**  
No. They differ in concrete type and meaning; matching text alone is not enough to equate identities.

**3. Does `getPrincipals(UserId.class).clear()` remove `UserId` from the `Subject`?**  
No. The typed set returned is a new set, not backed by the `Subject`.

**4. Does `getPrincipals().add(new Role("admin"))` modify the `Subject`?**  
Yes, if the `Subject` is writable and the caller is permitted, because it is a live set. However, this **does not make the role authenticated**.

**5. Is a private credential automatically encrypted just by being in `privateCredentials`?**  
No. `Subject` organizes objects; how material is protected depends on the implementation, provider, and policy.

**6. Does `setReadOnly()` block `destroy()` on credentials?**  
No. The `Subject` contract still allows destroying credentials; it only forbids add/remove in the sets.

**7. If a credential is destroyed yet an object remains in the private `Set`, does that mean the secret was not destroyed?**  
Not necessarily. The object can remain in the `Set` after its material is destroyed. Check `isDestroyed` according to the concrete type.

**8. With the Java 17 Security Manager deprecated, should `PrivateCredentialPermission` be treated as the sole barrier?**  
No. You need application trust boundaries, least privilege, secret management, and explicit authorization.

**9. Should a `LoginModule` add Principals in `login()` or `commit()`?**  
Normally in **`commit()` after overall authentication succeeds**. `abort` cleans up state when login/commit fails.

**10. Should `logout` wipe every Principal/credential in the `Subject`?**  
No. Each `LoginModule` must remove/destroy only what **it owns**, without touching other modules' data.

**11. Does a manually constructed Principal record prove a valid password?**  
No. A Principal is just an object; proof comes from a trusted authentication outcome.

**12. Can `Subject` serialization be used to send credentials across the network?**  
No. Java 17 `Subject` serializes Principals but does not serialize credentials; use a dedicated secure protocol.

## 16. Summary and References

**`Subject`** is the container for **`Principal` identities** and **public/private credentials**. Principals answer "**how is this entity identified**," while credentials provide data for verification and authorized operations. The public/private split reflects access rules and sensitivity, yet does not create security automatically if the application leaks objects or mismanages secrets.

Essential Java 17 takeaways:

- **Untyped `getPrincipals`/`getPublicCredentials`/`getPrivateCredentials`** return live sets; typed getters return new filtered sets.
- **`setReadOnly`** blocks modifying the three `Set`s, yet **does not deep-freeze** credential objects and still permits destroying credentials.
- **`LoginContext.login` → `LoginModule.commit`** attaches Principals/credentials on successful authentication; **`abort`/`logout`** perform cleanup.
- **Identity is not authorization**; secrets still require least privilege, proper lifecycles, and safe logging.

Official references for deeper reading:

- [Java SE 17 — javax.security.auth.Subject](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/Subject.html)
- [Java SE 17 — java.security.Principal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Principal.html)
- [Java SE 17 — javax.security.auth.Destroyable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/Destroyable.html)
- [Java SE 17 — javax.security.auth.Refreshable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/Refreshable.html)
- [Java SE 17 — LoginContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/login/LoginContext.html)
- [Java SE 17 — LoginModule SPI](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/spi/LoginModule.html)
- [Java SE 17 — JAAS Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-authentication-authorization-service-jaas-reference-guide.html)
- [Java SE 17 — LoginModule Developer's Guide](https://docs.oracle.com/en/java/javase/17/security/java-authentication-and-authorization-service-jaas-loginmodule-developers-guide1.html)
- [Java SE 17 — Configuration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/login/Configuration.html)
- [Java SE 17 — PrivateCredentialPermission](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/PrivateCredentialPermission.html)