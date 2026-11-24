# Proxying Return Objects, Nested Types, and Compatibility Limits

## 1. Context: a service's result is not necessarily safe for every reader

In Spring Security, permitting a service call does not imply permitting access to **every field of the object** the service returns. A profile may hold a public display name, personal email, phone number, address, and financial information. A response may span multiple nesting levels such as `Order → Customer → Contact`. Permission to view Order does not automatically imply permission to view Contact.

An object with an annotation on a getter:

```java
public class UserProfile {
    public String getDisplayName() { ... }

    @PreAuthorize("hasAuthority('profile:email:read')")
    public String getEmail() { ... }
}
```

is not guaranteed to be protected when it is merely a POJO created by the service via `new` and handed outward. Common method-security annotations are evaluated on **calls passing through an interceptor/proxy**. If a consumer receives a **raw** reference, `getEmail()` can execute without passing any gate.

Spring Security 6.3+ provides `@AuthorizeReturnObject`: it marks a method returning an object that needs to be **wrapped with authorization advice**. When the caller subsequently accesses a security-annotated getter/method on the proxied object, Spring Security can check permissions on that very invocation.

This lesson focuses on five practical questions:

1. What is the difference between `@PostAuthorize`, `@PostFilter`, and `@AuthorizeReturnObject`?
2. Which objects get proxied, when, and when are getters checked for permission?
3. How are nested objects, `List`, `Optional`, `Map`, arrays, and streams handled?
4. Why do `final`/`record` types, `String`, Jackson, Hibernate, AOT, and type erasure impose limits?
5. How do you test so you do not miss data leaks via raw references, serialization, or cross-tenant access?

**Foundational principle:** return proxying is a **complementary** tool. It does not replace authentication, roles/permissions, ownership, tenant-scoped queries, safe DTOs, or consistency checks during data writes.

### Visualizing the lifecycle

```text
Controller / caller
      |
      v
Spring-managed service proxy
      |
      v
@PreAuthorize checks whether service call is allowed?
      |
      v
Service creates raw ProfileView
      |
      v
@AuthorizeReturnObject
      |
      v
Proxied ProfileView
      |
      +-- getDisplayName() --> less sensitive value
      |
      +-- getContact()     --> ContactView proxied further?
                                   |
                                   v
                           getEmail()
                           @PreAuthorize
                             /     \
                           DENY    ALLOW
                            |        |
                          exception  email
```

The question mark on the child object is a reminder to **design and test proxy paths at every level**. The framework does not promise automatic protection for every field if code accesses it directly or retains the original reference.

## 2. Three non-equivalent result-checking mechanisms

| Tool | When checked | Target | Effect | Key takeaway |
| --- | --- | --- | --- | --- |
| `@PostAuthorize` | After method body executes, before allowed result is returned | `returnObject` | Allows/denies the entire return | Method logic already ran; side effects may have occurred |
| `@PostFilter` | After method produces a supported container result | Each `filterObject` | Removes elements lacking permission | May already have loaded excessive unnecessary data into memory |
| `@AuthorizeReturnObject` | When return value is produced; wraps object in proxy | Returned object, supported nested objects/containers | Checks subsequent getter/method calls | Depends on proxyable types, context, and proper call path |

### 2.1. `@PostAuthorize` — evaluating the entire result after the method

```java
@PostAuthorize("returnObject.owner == authentication.name")
public AccountView readAccount(long accountId) {
    return repository.read(accountId);
}
```

Spring Security allows using `returnObject` in an expression to inspect data of the just-returned object. If the owner differs from the principal name, the method call can be denied. This is a complementary check when ownership info is only known after loading.

**Never rely solely on `@PostAuthorize` for writes:** for transferring money, sending emails, deleting records, or calling webhooks, side effects may already have occurred before the decision. If inside a transaction, rollback behavior also depends on advice ordering and side-effect types. Pre-method checks and DB write conditions are still required.

### 2.2. `@PostFilter` — removing elements

```java
@PostFilter("filterObject.owner == authentication.name")
public List<AccountView> listAccounts() {
    return repository.findCandidates();
}
```

Only elements satisfying the expression remain after filtering. However, `findCandidates()` may already have loaded cross-tenant/cross-owner accounts into memory; for large lists, N+1 SQL and filtering costs can be high. Scoped database queries by verified tenant and owner/shares remain the default path.

`@PostFilter` **does not automatically create getter proxies** for the remaining accounts. Deciding “which elements may appear in the list” is different from “which attributes of each element may be viewed”.

### 2.3. `@AuthorizeReturnObject` — wrapping the object for further checks

```java
public class ProfileView {
    private final String name;
    private final String email;

    public ProfileView(String name, String email) {
        this.name = name;
        this.email = email;
    }

    public String getName() {
        return name;
    }

    @PreAuthorize("hasAuthority('profile:email:read')")
    public String getEmail() {
        return email;
    }
}

@Service
public class ProfileService {
    @AuthorizeReturnObject
    public ProfileView getProfile(long id) {
        return repository.findVisibleProfile(id);
    }
}
```

This example is **Spring integration code**, not a standalone Java file. It needs annotation imports, repository, service, context, and principal. When the service is called via a Spring proxy and return-object advice is active, the returned object can be a proxy; `getEmail()` is evaluated when the caller **actually invokes the getter** on that proxy.

A test that only calls `getProfile(...)` successfully **is insufficient**: it does not prove a user lacking email permission is blocked when retrieving the email.

### 2.4. Placing both an entry gate and a return gate

```java
@PreAuthorize("hasAuthority('profile:read')")
@AuthorizeReturnObject
public ProfileView getProfile(long id) {
    return repository.findVisibleForCurrentTenant(id);
}
```

The `profile:read` rule guards the profile-fetching feature. The rule on the email getter guards the sensitive attribute. Yet `findVisibleForCurrentTenant` must genuinely constrain tenant/owner/shares; an out-of-tenant object could still leak name/metadata via other getters even if email is denied.

## 3. Enabling infrastructure and identifying proxy boundaries

### 3.1. `@EnableMethodSecurity`

With Spring Security Servlet 6.5:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
```

By default, method security registers advisors for `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter`. `@Secured`/JSR-250 annotations only work when their corresponding flags are enabled; do not assume the proxy factory includes all advice types if the app disabled or customized configuration.

The method returning the object must also be called through a Spring-managed bean/proxy or proper interception mechanism. If the service is instantiated with `new`, or called via `this.getProfile()` inside the same object in AOP proxy mode, advice may be bypassed.

### 3.2. Difference between bean proxies and object proxies

Within a single request, several distinct things may all be called proxies:

- **Service security proxy:** intercepts calls into a Spring-managed service.
- **Return-object authorization proxy:** wraps a returned object to intercept its getters/methods.
- **Hibernate/JPA proxy:** lazy-loads entities/associations from the DB.
- **JDK interface proxy:** implements interfaces by delegation.
- **Class-based proxy:** usually generates a subclass within JVM-permitted boundaries.

They serve **different purposes** and are not interchangeable. A DTO that is not a Spring bean can still be guarded by a return-object proxy; that does not magically give the DTO transactions or dependency injection.

### 3.3. Since which version does `@AuthorizeReturnObject` exist?

Javadoc for `@AuthorizeReturnObject` and `AuthorizeReturnObjectMethodInterceptor` states **Since: 6.3**. Spring Security 6.5 docs cover container/nested proxying and AOT; factory/visitor APIs evolved across 6.x releases. Spring Security 7.x continues supporting this mechanism, yet when implementing you must consult docs for **the exact pinned version in your project**.

Never copy 6.5/7.x `AuthorizationAdvisorProxyFactory`/`TargetVisitor` APIs into 6.2 expecting them to compile.

### 3.4. Test the proxied object, not the raw object

Consider:

```java
ProfileView raw = new ProfileView("Alice", "secret@example.test");
ProfileView secured = service.getProfile(42L);
```

If a test calls `raw.getEmail()`, it only proves a raw POJO returns the email. Only when a test calls `secured.getEmail()` with an unauthorized principal does it verify the return-object interceptor.

You must also ensure other code **does not retain raw references** to pass to JSON serializers, caches, exporters, or loggers outside the gate.

## 4. Nested types: Profile → Contact → Email

A profile containing a separate Contact object may require a different permission for `getEmail()`. We must determine whether **every edge of the object tree** passes through a proxy.

### 4.1. Code illustrating a two-level structure

```java
public class ContactView {
    private final String label;
    private final String email;

    public ContactView(String label, String email) {
        this.label = label;
        this.email = email;
    }

    public String getLabel() {
        return label;
    }

    @PreAuthorize("hasAuthority('profile:email:read')")
    public String getEmail() {
        return email;
    }
}
```

Parent class:

```java
public class ProfileView {
    private final String displayName;
    private final ContactView contact;

    public ProfileView(
            String displayName, ContactView contact) {
        this.displayName = displayName;
        this.contact = contact;
    }

    public String getDisplayName() {
        return displayName;
    }

    @AuthorizeReturnObject
    public ContactView getContact() {
        return contact;
    }
}
```

Service:

```java
@Service
public class ProfileService {
    @PreAuthorize("hasAuthority('profile:read')")
    @AuthorizeReturnObject
    public ProfileView findVisibleById(long id) {
        return repository.findVisibleForVerifiedActor(id);
    }
}
```

These are **Spring Security fragments**, not a runnable project; they need imports, Spring context, repository, and domain types. Classes must be compatible with the proxy mechanism used by your version.

Expected flow:

1. Spring checks `profile:read` before the service runs.
2. Service returns `ProfileView` wrapped by `@AuthorizeReturnObject`.
3. Caller invokes `getDisplayName()`, receiving the name per the use case's public/tenant policy.
4. Caller invokes `getContact()`. The annotation on this getter requests further proxying of the returned `ContactView`.
5. Caller invokes `getEmail()` on the proxied ContactView; `@PreAuthorize` checks `profile:email:read`.
6. A user lacking email permission is denied **right at the getter**, even after receiving ProfileView.

### 4.2. What if the nested getter is not annotated?

If `ProfileView.getContact()` merely returns a raw ContactView and **no other proxy mechanism applies**, you must not assume method security on `ContactView.getEmail()` will work. Proxying is not a magic filter automatically attached to every field or arbitrary deep graph object.

Sketch each edge:

```text
Service.findById() -> ProfileView         [@AuthorizeReturnObject]
ProfileView.getContact() -> ContactView   [@AuthorizeReturnObject]
ContactView.getEmail() -> String          [@PreAuthorize]
```

If you add `ProfileView.getOrders() -> List<OrderView>` and `OrderView.getPayment() -> PaymentView`, decide at each object-returning method where proxying is needed. Test both nested getters and collection elements.

### 4.3. Why are annotations on getters better than raw field access?

Method security checks advised method invocations. If a library reads fields directly via reflection, or code keeps the original object and reads fields, it may bypass the getter proxy.

Therefore:

- Never use public fields for sensitive data when relying on getter authorization.
- Never serialize raw entities containing secrets expecting getter proxies to intervene.
- Never send raw objects into uncontrolled logs/caches.
- Minimize retained raw references after proxy creation.
- Enforce query scoping and DTO projections where data is fetched from the DB.

### 4.4. Owner, tenant, and attribute permissions

`hasAuthority('profile:email:read')` is only a functional permission. A user holding this permission in tenant A must not automatically read emails of users in tenant B. To protect individual objects, use a policy bean or scoped query:

```text
CAN_READ_EMAIL =
  authenticated
  AND sameTenant
  AND has(profile:email:read)
  AND (isOwner OR permittedAuditor OR explicitlyShared)
```

If a getter takes no ID argument yet has a target object, authorization can be designed around trusted metadata on the object and actor; verify expression target access and evaluation mechanics for your version. In many APIs, checking object ownership in the service/query before returning a DTO is easier to test than encoding all ownership rules in getter SpEL.

## 5. `Optional`, `List`, `Map`, arrays, `Stream`, and `Iterator`

Spring Security 6.5 docs describe `AuthorizationProxyFactory` supporting standard containers by proxying **elements**, and for maps proxying **values**.

| Return type | Unit wrapped under standard support | Must test |
| --- | --- | --- |
| `ProfileView` | Direct object | Annotated getters |
| `Optional<ProfileView>` | Inner object when present | Empty and non-empty |
| `List<ProfileView>` | Each element | Iterator/get returns secured reference |
| `Set<ProfileView>` | Each element | Equality, hashCode, and collection behavior |
| `ProfileView[]` | Each element | Array component compatibility |
| `Map<String, ProfileView>` | **Map values** | Keys may still expose metadata |
| `Stream<ProfileView>` | Elements as stream processes | Deferred execution/context/lifetime |
| `Iterator<ProfileView>` | Iterated elements | Context during iteration |
| Custom container | No default guarantee | Custom `TargetVisitor`/adapter if needed |

### 5.1. Does the `List` contain only authorized objects?

A service:

```java
@AuthorizeReturnObject
public List<ProfileView> listProfiles() {
    return repository.findAllProfiles();
}
```

is unsafe if `findAllProfiles()` fetches profiles across all tenants. Even if the email getter is blocked, list length, display names, or IDs can still leak data. **Return-object proxying guards element methods; it does not replace list membership/visibility policies.**

Better:

```java
@PreAuthorize("hasAuthority('profile:list')")
@AuthorizeReturnObject
public List<ProfileView> listProfiles() {
    return repository.findVisibleForVerifiedActor();
}
```

The query must constrain tenant/owner/shares; getter proxying afterward is only an extra layer.

### 5.2. `Optional`

With `Optional<ProfileView>`, when present, the element can be proxied; with `Optional.empty()`, there is no object to wrap. Do not equate empty with permission or not-found; that is a business/API contract to define explicitly.

Test that:

- Empty causes no unexpected proxy error.
- Non-empty returns an element whose getters are blocked properly.
- Unauthenticated and wrong-tenant requests do not leak profile existence through unintended error differences.

### 5.3. `Map`

With `Map<String, ProfileView>`, the factory can proxy values. Yet keys might be emails, usernames, customer IDs, or departments; **proxying values does not automatically hide keys**. Confidential data in keys or collection order/size can leak as soon as the caller reads the Map.

Do not use sensitive keys or return cross-tenant maps hoping getter proxies suffice. Design shape and access scope upfront.

### 5.4. `Stream` and `Iterator`

With streams/iterators, element access can occur **after** the service returns or on another thread. Risks:

- `SecurityContextHolder` on the getter-calling thread no longer matches the caller.
- ORM session/transaction closed before lazy associations are touched.
- Parallel streams do not automatically carry `SecurityContext` to worker threads.
- Cursor-backed streams must be closed properly.
- AOT generic erasure can make element types hard to scan ahead of time.

For public APIs, scoped queries + DTO snapshots are usually easier to manage across lifecycles than long-lived streams containing secured entity proxies.

### 5.5. Container proxying differs from `@PostFilter`

Side by side:

```text
@AuthorizeReturnObject List<User>:
  Keeps elements; each element can be proxied
  Sensitive getters are checked when called.

@PostFilter List<User>:
  Filters out unauthorized elements per filterObject
  Does not promise protecting getters of remaining elements.
```

Neither replaces DB queries scoped by tenant/owner. For large datasets, evaluate load/iteration cost and metadata-leak risks before choosing an approach.

## 6. Class-level proxying and value types

### 6.1. Why are class-level annotations error-prone?

`@AuthorizeReturnObject` can be placed at class level, equivalent to applying it to methods in the class. Example:

```java
@AuthorizeReturnObject
@Service
public class MixedReturnService {
    public ProfileView findProfile(long id) { ... }
    public String getStatusText() { ... }
    public int countProfiles() { ... }
    public List<String> listTags() { ... }
}
```

Some return types like `String`, `Integer`, and primitives are not domain types suitable for class-based authorization proxies. Spring Security documentation warns against Spring attempting to proxy such value types when annotated at class level.

**Prefer placing `@AuthorizeReturnObject` on specific methods** rather than annotating the entire class broadly when a service returns mixed types. If class-level is mandatory, test every return type.

### 6.2. Skipping value types with `TargetVisitor`

Per Spring Security 6.5 docs, a visitor configuration bean:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.method.AuthorizationAdvisorProxyFactory.TargetVisitor;

@Configuration
public class ReturnObjectProxyConfiguration {

    @Bean
    static TargetVisitor skipValueTypes() {
        return TargetVisitor.defaultsSkipValueTypes();
    }
}
```

The goal is configuring processing to exclude basic value types from proxy attempts. If configuring a custom `TargetVisitor`, consult Javadoc for your exact version; a wrong visitor can skip **objects that actually need protection**.

Carefully distinguish **skipping value types** from **skipping permission checks**. A `String` should only appear in a public response if the service/getter already applied an appropriate policy before returning it; skipping proxying is not `permitAll`.

### 6.3. `final`, `record`, `sealed`, and interfaces

In Java:

- `record` is final by default; standard subclass class-based proxies cannot be generated.
- `final class` and `final method` restrict subclass-based interception.
- `sealed class` restricts permitted subclasses, so arbitrary proxy subclasses are not automatically allowed.
- An interface projection may work with JDK dynamic proxies, provided return types/serialization match.
- Kotlin classes/methods may be final by default without open configuration/plugins.
- ORM entities may already be proxied, causing interactions with lazy loading and equality.

Never claim a single flag makes every final object proxyable. When proxying gets complex, it can be safer to **decide permissions upfront, map to a record/DTO containing only allowed fields, and return directly**.

### 6.4. `equals`, `hashCode`, `getClass`, `toString`

Proxies can change the class observed via `getClass()` and reference identity. `equals/hashCode` depend on implementation/proxy behavior, which can surprise code using them as HashMap keys, HashSet elements, or ORM identity-map entries.

Compare by explicit domain ID, avoid placing secured proxies into persistence graphs, and test `toString()`/logging. A record or entity `toString()` can print an email even when getter authorization is enabled elsewhere.

## 7. Creating proxies programmatically

Spring Security also provides `AuthorizationProxyFactory` to wrap objects that do not originate directly from an annotated method.

Fragment per 6.5 docs:

```java
@Autowired
AuthorizationProxyFactory proxyFactory;

public void demo() {
    ProfileView raw = new ProfileView(...);
    ProfileView secured = proxyFactory.proxy(raw);
}
```

Using with collections:

```java
List<ProfileView> securedList =
    proxyFactory.proxy(List.of(rawA, rawB));
```

This snippet shows API usage and requires imports, beans, and concrete objects. The factory picks up `AuthorizationAdvisor` beans configured in the application; if creating `AuthorizationAdvisorProxyFactory.withDefaults()` manually, verify whether it includes your project's custom advisors, role hierarchy, and denied handlers.

**Do not treat the proxy factory as a replacement for authentication.** The caller must have a valid `SecurityContext` when getters are evaluated. A proxied POJO does not automatically gain Spring transactions, JPA sessions, or context propagation.

## 8. Standalone Java 17: simulating object and nested object proxies

The following Java code **compiles and runs with JDK 17**, without Spring libraries. It illustrates the mechanism via `java.lang.reflect.Proxy`:

- A proxied Profile checks tenant before allowing name/contact access.
- When `contact()` is called, the wrapper returns a **further-proxied** Contact.
- The `email()` getter requires `profile:email:read` and that the caller is the owner or an auditor in the same tenant.
- List/Optional hold only secured references.
- A retained raw reference can **bypass** the proxy; this is why raw entities must never reach untrusted callers.

This is a **conceptual model**, not a simulation of Spring's internals or class-based proxies/AOT/Jackson.

Save as `ReturnedObjectProxyDemo.java`:

```java
import java.lang.reflect.Proxy;
import java.util.List;
import java.util.Optional;
import java.util.Set;

public class ReturnedObjectProxyDemo {

    interface Profile {
        String displayName();
        Contact contact();
    }

    interface Contact {
        String label();
        String email();
    }

    record RawContact(
        String label, String email
    ) implements Contact {}

    record RawProfile(
        String displayName, Contact contact,
        String ownerId, String tenantId
    ) implements Profile {}

    record Actor(
        String id, String tenantId,
        Set<String> grants, boolean active
    ) {}

    static void requireTenant(Actor actor, String tenant) {
        if (actor == null || !actor.active()
                || actor.tenantId() == null
                || !actor.tenantId().equals(tenant)) {
            throw new SecurityException("Tenant denied");
        }
    }

    static Profile secureProfile(
            RawProfile raw, Actor actor) {

        return (Profile) Proxy.newProxyInstance(
            Profile.class.getClassLoader(),
            new Class<?>[] {Profile.class},
            (proxy, method, args) -> {
                requireTenant(actor, raw.tenantId());

                return switch (method.getName()) {
                    case "displayName" -> raw.displayName();
                    case "contact" -> secureContact(
                        raw.contact(), actor,
                        raw.ownerId(), raw.tenantId()
                    );
                    default -> throw new UnsupportedOperationException(
                        method.getName()
                    );
                };
            }
        );
    }

    static Contact secureContact(
            Contact raw, Actor actor,
            String ownerId, String tenantId) {

        return (Contact) Proxy.newProxyInstance(
            Contact.class.getClassLoader(),
            new Class<?>[] {Contact.class},
            (proxy, method, args) -> {
                requireTenant(actor, tenantId);

                return switch (method.getName()) {
                    case "label" -> raw.label();
                    case "email" -> {
                        boolean allowedPermission =
                            actor.grants() != null
                            && actor.grants().contains(
                                "profile:email:read"
                            );
                        boolean owner =
                            actor.id() != null
                            && actor.id().equals(ownerId);
                        boolean auditor =
                            actor.grants() != null
                            && actor.grants().contains(
                                "ROLE_TENANT_AUDITOR"
                            );

                        if (!allowedPermission
                                || !(owner || auditor)) {
                            throw new SecurityException(
                                "Email denied"
                            );
                        }
                        yield raw.email();
                    }
                    default -> throw new UnsupportedOperationException(
                        method.getName()
                    );
                };
            }
        );
    }

    static boolean denied(Runnable read) {
        try {
            read.run();
            return false;
        } catch (SecurityException e) {
            return true;
        }
    }

    static void show(String label, Object value) {
        System.out.println(label + ": " + value);
    }

    public static void main(String[] args) {
        RawProfile aliceRaw = new RawProfile(
            "Alice",
            new RawContact("work", "alice@example.test"),
            "alice", "T1"
        );
        RawProfile bobRaw = new RawProfile(
            "Bob",
            new RawContact("private", "bob@example.test"),
            "bob", "T1"
        );

        Actor alice = new Actor(
            "alice", "T1",
            Set.of("profile:email:read"), true
        );
        Actor bob = new Actor(
            "bob", "T1", Set.of(), true
        );
        Actor auditor = new Actor(
            "audit", "T1",
            Set.of("ROLE_TENANT_AUDITOR",
                   "profile:email:read"), true
        );
        Actor foreignAuditor = new Actor(
            "audit", "T2",
            Set.of("ROLE_TENANT_AUDITOR",
                   "profile:email:read"), true
        );

        Profile aliceView = secureProfile(aliceRaw, alice);
        Profile bobView = secureProfile(aliceRaw, bob);
        Profile auditorView = secureProfile(aliceRaw, auditor);
        Profile foreignView =
            secureProfile(aliceRaw, foreignAuditor);

        show("alice display", aliceView.displayName());
        show("alice email", aliceView.contact().email());
        show("bob display", bobView.displayName());
        show("bob email denied", denied(
            () -> bobView.contact().email()
        ));
        show("auditor email", auditorView.contact().email());
        show("foreign display denied", denied(
            () -> foreignView.displayName()
        ));

        List<Profile> forBob = List.of(
            secureProfile(aliceRaw, bob),
            secureProfile(bobRaw, bob)
        );
        show("secured list size", forBob.size());
        show("list first email denied", denied(
            () -> forBob.get(0).contact().email()
        ));

        Optional<Profile> optional =
            Optional.of(secureProfile(aliceRaw, alice));
        show("optional email",
            optional.orElseThrow().contact().email());

        // Purpose: prove raw reference has no proxy.
        show("raw reference unprotected",
            aliceRaw.contact().email().equals(
                "alice@example.test"
            ));
    }
}
```

Run:

```bash
javac ReturnedObjectProxyDemo.java
java ReturnedObjectProxyDemo
```

Expected stdout output:

```text
alice display: Alice
alice email: alice@example.test
bob display: Alice
bob email denied: true
auditor email: alice@example.test
foreign display denied: true
secured list size: 2
list first email denied: true
optional email: alice@example.test
raw reference unprotected: true
```

**Reading the output:**

1. Alice is the T1 owner with email permission, so she can view the email.
2. Bob in the same tenant can view the name per demo policy, yet lacks email permission so he is blocked at the nested Contact getter.
3. The T1 auditor has the audit role and permission, so email access is allowed per the explicit exception.
4. The T2 tenant auditor fails the tenant check despite identical role/permission.
5. The List holds two secured references; the first element still blocks email for Bob.
6. The Optional holds a secured reference; unwrapping does not strip getter protection.
7. The final line shows a **raw** reference can read the email without passing through the proxy. In production, never keep or pass raw objects to untrusted callers.

The program intentionally limits supported handler methods; it does not fully implement `equals/hashCode/toString`, has no Spring `SecurityContextHolder`, validates no tokens, connects to no DB, and proxies no concrete classes. Its purpose is clarifying **authorization after returning an object and accessing child objects**.

## 9. Serialization, Jackson, and the difference between deny and redaction

### 9.1. Getters can be called indirectly by Jackson

In REST APIs, Jackson typically invokes getters to build JSON. If a getter has `@PreAuthorize` and the caller lacks permission, the serializer may hit an exception. That **does not guarantee** JSON will automatically omit the field or replace it with null.

Expected product response example:

```json
{
  "displayName": "Alice",
  "contact": {
    "label": "work"
  }
}
```

To meet this contract, you need a safe DTO/mapper or a configured denied handler/masking and **real HTTP tests**. Never rely solely on a getter throwing `AccessDeniedException` assuming Jackson automatically drops the field.

Differences can occur in status codes (403, serializer error, 500), graph depth, and when response body bytes are flushed. If a response has partially streamed, a subsequent exception cannot retract bytes already sent. Spring Security 6.5 improves MVC integration for `@AuthorizeReturnObject`, yet you must test your exact Boot/Spring/Jackson stack.

### 9.2. Sanitized DTOs are usually easier to keep safe

A stable public API can use records:

```java
public record PublicProfileResponse(
    String displayName,
    String contactLabel
) {}

public record PrivateProfileResponse(
    String displayName,
    String contactLabel,
    String email
) {}
```

The service checks permissions/owner/tenant and selects the appropriate projection. The public DTO **does not contain email**, so it cannot leak email just because a serializer reads fields rather than getters. Final records are awkward for class-based proxies, yet once sanitized, no field-level proxy is needed to hide a secret that isn't there.

For GraphQL/REST with sensitive fields, controlled schema/DTO projections are often clearer than returning raw entities + multiple proxy layers.

### 9.3. Denied handlers and masking

Spring Security 6.5 has `@HandleAuthorizationDenied` and handler mechanisms for certain pre/post denials. If you want a getter to return null or a masked value when permission is missing, study your exact version and verify:

- When denied, the handler never returns the raw secret.
- Null may serialize as a null key or be omitted depending on Jackson config.
- Bugs where a getter already caused side effects are not solved by masking output.
- The API schema must specify which fields are optional and what masked values mean.
- Test end-to-end with authorized and unauthorized principals, not just handler unit tests.

## 10. JPA/Hibernate, transactions, and object identity

### 10.1. Proxy stacked on proxy

An object from Hibernate may already be a lazy proxy. Wrapping it in an authorization proxy creates a chain:

```text
Spring Security return proxy
   -> Hibernate entity proxy
      -> entity / lazy association
         -> database
```

Risks:

- Method visibility differences between entity/proxy/concrete type.
- Calling a getter after the transaction closes can trigger `LazyInitializationException`.
- Lazy associations during serialization lead to N+1 SQL.
- `equals/hashCode/getClass` behave unexpectedly.
- Final classes/methods or constructors incompatible with proxying.
- ORM/persistence caches hold raw references without security advice.

Do not treat enabling Open Session in View as a complete security solution. Scoped queries and projections/DTOs with clear transaction boundaries are usually easier to control.

### 10.2. `@PostAuthorize` after writes is too late

`@PostAuthorize` checks `returnObject` after the method, without preventing the method from already updating the database or sending messages. Transaction rollback on an exception depends on advice ordering and design, while non-DB side effects never roll back automatically.

For writes/approvals/deletes, use `@PreAuthorize`, server-side policies, and conditional UPDATEs on tenant/owner/status/version. If permissions are revoked between two points in time, enforce transactional rechecks per business rules.

### 10.3. Identity and `hashCode`

A secured proxy may not have the same observable reference or class as the raw object. Using `==` or `getClass()` to decide ownership is wrong; use domain IDs and verified principals.

If proxies are used as Map keys or Set elements, test `equals/hashCode`. Avoid logging `toString()` of entities holding secrets, since getter proxies do not guard every object representation.

## 11. AOT / GraalVM Native and generic erasure

### 11.1. Why must AOT know return types?

On a normal JVM, proxies can be generated at runtime. Native/AOT needs proxy classes and reflection/runtime hints prepared upfront. Spring Security 6.5 scans beans with `@AuthorizeReturnObject` and inspects return types; when encountering nested annotated methods, it continues traversing.

```text
Controller.getMessage()
   @AuthorizeReturnObject -> MessageView
MessageView.getRecipient()
   @AuthorizeReturnObject -> UserView
UserView.getEmail()
   @PreAuthorize(...)
```

When types are explicit, the scanner can collect the objects needing advice/hints.

### 11.2. Generic erasure

A method:

```java
@AuthorizeReturnObject
public List<MessageView> getMessages() {
    return repository.findVisibleMessages();
}
```

can challenge the AOT scanner because Java erases parts of generic information at runtime. Spring Security 6.5 docs use a similar scenario to explain why the scanner cannot always discover concrete type `MessageView` before build time.

`Object`, raw collections, generic wildcards, polymorphism, and custom wrappers require even closer attention. Passing JVM tests **does not prove** the native image has sufficient proxy hints.

### 11.3. Registrar for hard-to-discover types

Per Spring Security 6.5, you can register a `SecurityHintsRegistrar` using `AuthorizeReturnObjectHintsRegistrar` for types not discovered automatically:

```java
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Role;
import org.springframework.security.aot.hint.SecurityHintsRegistrar;
import org.springframework.security.aot.hint.AuthorizeReturnObjectHintsRegistrar;
import org.springframework.security.authorization.method.AuthorizationProxyFactory;

@Bean
@Role(BeanDefinition.ROLE_INFRASTRUCTURE)
static SecurityHintsRegistrar registerReturnObjectHints(
        AuthorizationProxyFactory factory) {
    return new AuthorizeReturnObjectHintsRegistrar(
        factory, MessageView.class, UserView.class
    );
}
```

This fragment must reside in a configuration class, with real `MessageView`/`UserView` classes. Verify Javadoc for the exact Spring Security patch used. The registrar only prepares metadata/proxies for AOT; **it does not grant permissions**. If a native image reports a missing type, fix hints and test deny/allow instead of disabling authorization.

### 11.4. Custom containers and `TargetVisitor`

A custom container does not automatically traverse like `List`/`Optional`/`Map`. To have the factory proxy elements, you may need a custom `TargetVisitor` matching your version's API. Never replace the default visitor with one that skips all unknown types; that can skip the very objects needing protection.

Runtime wrapping and AOT hints are **two separate requirements**. You must verify both runtime proxy creation and type registration in native builds.

## 12. Proper testing guidance: getters, nested, HTTP, and native

### 12.1. Test the Spring-managed service, not a raw POJO

With JUnit 5 and Spring Security Test:

```java
@SpringBootTest
class ProfileProxyTest {
    @Autowired ProfileService service;

    @Test
    @WithMockUser(authorities = {
        "profile:read", "profile:email:read"
    })
    void emailAllowed() {
        ProfileView view = service.findVisibleById(42L);
        assertEquals(
            "alice@example.test",
            view.getContact().getEmail()
        );
    }

    @Test
    @WithMockUser(authorities = {"profile:read"})
    void emailDenied() {
        ProfileView view = service.findVisibleById(42L);
        assertNotNull(view.getDisplayName());
        assertThrows(
            AccessDeniedException.class,
            () -> view.getContact().getEmail()
        );
    }
}
```

This is **integration test code**, needing proper imports, service, fixture data, and Spring classes. With `@WithMockUser`, Authentication is mocked; this test does not prove JWT validation or real role mapping.

Fixtures must allow the test user to view Profile 42 under the tenant/owner policy to isolate **the email getter**; otherwise the service may block earlier.

### 12.2. Test matrix

| Case | What to prove |
| --- | --- |
| Missing email permission yet has profile permission | Receives profile, yet email getter is denied |
| Has both profile and email permissions | Email getter allowed per policy |
| Document belongs to another tenant | Cannot fetch record/metadata, not just blocking email getter |
| Nested Contact not proxied | Test detects raw `getEmail` exposure risk |
| List with two elements | Each element is proxied, not just the list |
| Sensitive Map keys | Keys are not leaked despite value proxying |
| Optional empty/non-empty | No errors and proper element behavior |
| Lazy Stream across threads | Context/permissions checked properly, not bypassed |
| Class-level String/Integer | Value types do not cause proxy failures |
| Record/final type | Proper DTO/projection alternative in place |
| Jackson serialization | Exact status, fields, null/omission behavior |
| Hibernate lazy association | No session error, N+1, or cross-tenant data |
| Native generic `List<T>` | Sufficient hints, genuine getter denial |
| Raw objects/logs/caches | No secret leak paths outside proxy |
| Method self-invocation | No bypass of service authorization |

### 12.3. MockMvc verifying serialization

For endpoint `GET /profiles/42`, create two principals: one with `profile:read` lacking `profile:email:read`, and one with both. Pick **one API contract** for unauthorized email: full-response 403, null, masked, or omitted field; then verify exact status + JSON body.

Never treat an HTTP 403 as proof the getter ran: it could come from a URL matcher or `@PreAuthorize` on the service. Separately test the method through the proxy with a user permitted to fetch the profile to confirm getter-level denial. When a field is denied mid-serialization, ensure no partial JSON leaks.

### 12.4. Native/AOT tests

For native apps, build and run cases where `@AuthorizeReturnObject` returns Objects, Lists, Optionals, and nested Contacts. Test both sufficient and missing permissions inside the native image. A green JVM test run is insufficient if runtime hints are missing.

## 13. Version-based compatibility limits

| Version line | Key facts |
| --- | --- |
| Before 6.3 | Do not assume `@AuthorizeReturnObject` exists |
| 6.3 | Return-object annotation/interceptor introduced |
| 6.4 | Factory/visitor APIs evolved; verify Javadoc signatures for exact version |
| 6.5 | Docs cover containers, nested, TargetVisitor skipping, AOT hints, denied handlers, and MVC integration |
| 7.x | Preserves concepts, yet defaults/annotations/factories/hints must be verified per patch |

Before upgrading, inspect the project's dependency tree rather than guessing from Spring Boot's name. Never copy 7.x code into Spring Security 6.2 expecting classes/methods to exist.

## 14. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `@PreAuthorize` on a raw POJO | Getter has no advice | Create return-object proxy at proper boundary |
| `@AuthorizeReturnObject` on method bypassing Spring proxy | Result not wrapped | Call real bean/proxy |
| Nested getter returns raw object | Child getter not blocked | Wrap required nested edges |
| List contains cross-tenant records | Count/name/ID leakage | Scoped DB query |
| Map keys contain secret emails | Keys leak despite value protection | Avoid sensitive keys |
| Class-level proxy on String/Integer | Runtime proxy errors | Method-level or `TargetVisitor` skip |
| Record/final class needing subclass proxy | Proxy cannot be created | Interface projection/safe DTO |
| Jackson invokes denied getter | Serialization exception | DTO/denied handler + HTTP tests |
| Jackson/mapper reads raw fields | Secret leaks bypassing getters | Never expose raw secrets at boundary |
| JPA lazy proxy + security proxy | Session/identity/N+1 errors | Projections/transaction boundaries |
| `@PostAuthorize` as write gate | Side effects before denial | Pre-check + DB guards |
| Generic erased in native | Missing proxy type hints | Hints registrar + native tests |
| Parallel stream switches threads | Wrong/lost `SecurityContext` | Context propagation or DTOs |
| Logger prints raw object | Data leak | Redact/map before logging |
| Confusing proxies with record masking | Broken API contract | Dedicated DTOs or tested handlers |
| Tests only load the object | Unclear whether getters are blocked | Test getter deny/allow |
| Fixing 403 with `permitAll` | Disables authorization | Diagnose the right layer |

## 15. Practice exercises

1. **`PostAuthorize` vs. return proxy:** Write a read-only service using `@PostAuthorize` to check ownership. Then use `@AuthorizeReturnObject` and `@PreAuthorize` on the email getter. Test both checkpoints.
2. **Nested objects:** Extend ProfileView → ContactView → AddressView, defining a dedicated permission for street. Test when label is readable but street is denied.
3. **Collections:** Return `List<ProfileView>` and `Map<String, ProfileView>`; verify element proxies and ensure no map key leakage.
4. **Class-level:** Annotate a class having methods returning String, Integer, and ProfileView; observe proxy behavior, then apply `TargetVisitor.defaultsSkipValueTypes()` in an appropriate test setup.
5. **Java 17:** Run `ReturnedObjectProxyDemo.java` and verify all 10 stdout lines. Add an inactive actor and test both raw and secured references.
6. **Serialization:** Use Jackson and MockMvc; decide whether missing email permission returns 403, null, or omits the key. Test zero secret leaks and zero partial JSON.
7. **Hibernate:** Create a lazy association, serialize outside the transaction, then replace with a scoped DTO projection to eliminate N+1/lazy failures.
8. **Native/AOT:** Return `List<MessageView>` with nested `UserView`, add hints if the scanner misses types, and test both allow and deny in a native image.

## 16. Pre-production checklist

- [ ] `@EnableMethodSecurity` is enabled and corresponding advisors are active.
- [ ] Service methods are called via Spring proxy, not self-invocation/`new` objects.
- [ ] `@AuthorizeReturnObject` is placed at the right object-returning boundaries.
- [ ] Sensitive getters/methods have `@PreAuthorize`/`@PostAuthorize` or appropriate managers.
- [ ] Every nested edge needing proxying is annotated and tested.
- [ ] List/Map/Optional/Stream wrap the exact elements/values expected.
- [ ] Queries constrain tenant/owner/shares; proxies are not relied on to hide unauthorized metadata.
- [ ] Class-level annotations do not unintentionally try to proxy String/Integer/primitives.
- [ ] Final/record DTOs are used when sensitive fields should be excluded altogether.
- [ ] Jackson/JSON contracts are tested with and without permissions.
- [ ] Raw references are not held in uncontrolled loggers/caches/exporters.
- [ ] Hibernate lazy loading and transaction boundaries are properly designed.
- [ ] Streams/async do not evaluate getters under the wrong `SecurityContext`.
- [ ] Native/AOT has complete runtime hints for erased/nested types.
- [ ] `@PostAuthorize` is not used as the sole gate for side effects.
- [ ] Real proxies are tested rather than checking annotations via reflection alone.
- [ ] Negative tests cover wrong tenant, missing permission, raw fields, nested getters, native, and serialization.

## 17. Self-check

1. **When does `@PostAuthorize` check?** After the method has run, before the result is permitted to return.
2. **What does `@PostFilter` do?** Removes unauthorized elements from a supported container.
3. **What does `@AuthorizeReturnObject` do?** Wraps the return object so methods/getters are checked for permission when called.
4. **Does the service returning Profile successfully mean email is permitted?** No.
5. **Is a nested Contact automatically proxied?** Only when the returning path has proper proxy/advice configuration.
6. **Are getter annotations on a raw POJO guaranteed to be enforced?** No.
7. **Are Maps proxied primarily on keys or values?** Values, per documented container support.
8. **Why is class-level `@AuthorizeReturnObject` risky?** It applies to every return type, including String/Integer.
9. **What does `TargetVisitor.defaultsSkipValueTypes` do?** Avoids attempting to proxy unsuitable value types.
10. **Are Java records convenient for subclass proxying?** No, records are final.
11. **Does Jackson automatically omit a denied getter?** Cannot be assumed.
12. **Why are sanitized DTOs useful?** They contain no secrets at the boundary, reducing leaks via serializers/logs.
13. **Is `@PostAuthorize` suitable as the sole gate before transferring money?** No, because the method has already executed.
14. **Where do AOT errors with `List<T>` usually come from?** Type erasure/build-time scanners may miss the concrete element type.
15. **Does a hints registrar grant permissions?** No; it only registers required metadata/proxies.
16. **How does `Stream` differ from `List`?** Lazy evaluation can occur after `SecurityContext`/transaction has changed.
17. **Does seeing 403 prove a getter was denied?** No, an HTTP/service gate may have denied earlier.
18. **What must tests cover?** A caller permitted to view the profile yet lacking email permission; nested getters must deny on a real proxy.
19. **What is the risk of retaining a raw reference?** It can bypass getter proxies and leak secrets.
20. **When should DTOs be preferred over return proxies?** Public APIs with strict schemas, highly sensitive data, or complex final/ORM/serializer types.

**Key takeaway:** `@AuthorizeReturnObject` is useful for attaching authorization advice to **calls on returned results**, including supported containers and nested objects. It does not filter datasets automatically, does not protect raw references, does not replace tenant/owner queries, and does not guarantee serializers drop denied fields. A safe choice combines **entry policies, proper proxy paths, appropriate DTOs/projections, negative tests, and control over data types/AOT**.

### Official references

- [Spring Security 6.5 – Method Security and Authorizing Arbitrary Objects](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 7.0 – Method Security](https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/method-security.html)
- [Spring Security 6.5 – AuthorizeReturnObject JavaDoc](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/authorization/method/AuthorizeReturnObject.html)
- [Spring Security 6.5 – AuthorizationAdvisorProxyFactory JavaDoc](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/authorization/method/AuthorizationAdvisorProxyFactory.html)
- [Spring Security 6.5 – AOT return-object hints](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html#method-security-aot)