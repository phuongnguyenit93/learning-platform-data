# Registering PermissionEvaluator with MethodSecurityExpressionHandler

## 1. Goal and context

In Spring Security, checking a role with `hasRole('ADMIN')` or an authority with `hasAuthority('DOC_READ')` only tells you what permissions a user holds globally. A document system must also answer a finer-grained question: **Does Alice have permission to read document #17?** That decision typically depends on the caller, owner, tenant, state, and business rules.

`PermissionEvaluator` is a Spring Security extension point for **object-level permission expressions**. It allows `hasPermission(...)` inside `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, or `@PostFilter` to delegate checks to application Java code.

For Spring Security Method Security to actually use your custom evaluator, you must **register it on the `MethodSecurityExpressionHandler`** — typically `DefaultMethodSecurityExpressionHandler` — via `setPermissionEvaluator(...)`, and enable `@EnableMethodSecurity`. Merely declaring a class that `implements PermissionEvaluator` and calling `hasPermission` in an annotation is **not enough to prove** the expression handler is using that class.

After this lesson, you will be able to:

1. Distinguish the `PermissionEvaluator` interface from `MethodSecurityExpressionHandler` and the Spring AOP method-security interceptor.
2. Correctly implement **both overloads** of `hasPermission`: the object form and the ID + object-type form.
3. Configure `@Bean static MethodSecurityExpressionHandler` with `setPermissionEvaluator` in Spring Security 6.x.
4. Accurately write `hasPermission(#document, 'READ')` and `hasPermission(#id, 'DOCUMENT', 'READ')` expressions.
5. Write Spring/JUnit tests proving the evaluator is invoked, access is granted/denied, `@PreAuthorize` blocks before the method body, and `@PostAuthorize` blocks after the method body.
6. Spot common mistakes: missing handler, wrong parameter names, missing proxy, mismatched resource-type strings, unsafe null handling, and policies trusting client-supplied data.

**Illustrative environment:** Java 17+, Spring Security 6.5.x, Spring Framework 6.2.x, JUnit 5, and Spring Test; the Gradle sample project uses the Spring Boot 3.5.0 BOM for dependency management. The content focuses on **method security on Spring beans**; `hasPermission` in HTTP authorization requires separate configuration when needed.

## 2. Flow from annotation to PermissionEvaluator

Example service method:

```java
@PreAuthorize("hasPermission(#id, 'DOCUMENT', 'READ')")
public Document read(@P("id") Long id) {
    return repository.findById(id).orElseThrow();
}
```

This is an **illustrative snippet**, depending on a real `repository`. With `@EnableMethodSecurity` and invocation through a Spring proxy, the conceptual flow is:

```text
Controller / other service / test
           |
           v
Spring bean proxy
           |
           v
AuthorizationManagerBeforeMethodInterceptor
           |
           v
PreAuthorizeAuthorizationManager
           |
           v
MethodSecurityExpressionHandler
   creates EvaluationContext and root for SpEL
           |
           v
hasPermission(#id, 'DOCUMENT', 'READ')
           |
           v
PermissionEvaluator.hasPermission(
    authentication, id, "DOCUMENT", "READ")
           |
        +--+---------------------+
        |                        |
      true                     false
        |                        |
        v                        v
Method body executes    AccessDeniedException
                        method did not run
```

Reading the diagram from the outside in: `@EnableMethodSecurity` tells Spring to register advisors/interceptors; `DefaultMethodSecurityExpressionHandler` teaches SpEL to understand security expressions such as `hasPermission`; and `PermissionEvaluator` **only performs the specific permission decision**.

| Component | Responsibility | What it does not do automatically |
| --- | --- | --- |
| `@EnableMethodSecurity` | Enables method authorization infrastructure | Does not automatically infer per-document policies |
| Spring AOP proxy | Routes calls through interceptors | Does not intercept `this.method()` in standard proxy mode |
| `PreAuthorizeAuthorizationManager` / `PostAuthorizeAuthorizationManager` | Evaluates pre/post annotations respectively | Does not implicitly replace `hasPermission` logic with app policy |
| `MethodSecurityExpressionHandler` | Builds SpEL context for the method and security root | Does not replace owner/tenant decisions |
| `PermissionEvaluator` | Returns `boolean` for a permission by object or ID | Does not modify user authorities, query DB, or create ACLs by itself |
| `@PreAuthorize` / `@PostAuthorize` | Chooses **when** to check (before/after method) | Does not filter individual elements out of a collection |

A service can use the same evaluator in `@PreAuthorize`, `@PostAuthorize`, or filtering expressions. However, **execution timing differs**: with `@PostAuthorize`, the method body has already run; the evaluator cannot undo side effects that already happened.

## 3. Two signatures to implement accurately

The `org.springframework.security.access.PermissionEvaluator` interface has two methods:

```java
public interface PermissionEvaluator {

    boolean hasPermission(
        Authentication authentication,
        Object targetDomainObject,
        Object permission
    );

    boolean hasPermission(
        Authentication authentication,
        java.io.Serializable targetId,
        String targetType,
        Object permission
    );
}
```

Mapping table between SpEL and overloads:

| Spring Security expression | Java signature invoked | When appropriate |
| --- | --- | --- |
| `hasPermission(#document, 'READ')` | `hasPermission(Authentication, Object, Object)` | Already have a trusted domain object and want to check it directly |
| `hasPermission(returnObject, 'READ')` | `hasPermission(Authentication, Object, Object)` | Check the object **after** the service returns it |
| `hasPermission(#id, 'DOCUMENT', 'READ')` | `hasPermission(Authentication, Serializable, String, Object)` | Only have an ID; evaluator fetches metadata/owner itself |
| `hasPermission(filterObject, 'READ')` | `hasPermission(Authentication, Object, Object)` | Check each element in `@PreFilter`/`@PostFilter` |

**Explaining the arguments:**

- `authentication` is the identity being checked, typically holding `getName()`, `getPrincipal()`, and `getAuthorities()`. Use the `Authentication` **passed by the framework**, never an arbitrary username taken from the request.
- `targetDomainObject` is a real object instance; it may be `null`. By the `PermissionEvaluator` contract, a null target should normally return `false`.
- `targetId` must be `Serializable`, such as `Long`, `UUID`, or `String` depending on the system. This is an **ID**, not an entity.
- `targetType` is the domain type string provided by the expression, such as `"DOCUMENT"`. Spring Security **does not automatically turn** this string into an entity class or repository; the evaluator must interpret it.
- `permission` has type `Object`; in the example it is `"READ"` or `"WRITE"`. When using enums/bitmasks/ACL permission objects, check the specific type rather than blindly converting via string coercion.
- Returning `true` means allow, `false` means deny. An I/O or database error must never be masked by returning `true`; design error handling and auditing separately.

**Signature differences are the easiest place to make mistakes:** the **two-argument SpEL form** `hasPermission(target, permission)` calls the object overload; the **three-argument SpEL form** `hasPermission(id, type, permission)` calls the ID overload. Both Java methods take `Authentication` as their first parameter, supplied by Spring, so the SpEL argument count is one fewer than the Java parameter count.

## 4. Registering the evaluator on the expression handler

### 4.1. Recommended Spring Security 6.x configuration

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodPermissionConfig {

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            PermissionEvaluator evaluator) {
        DefaultMethodSecurityExpressionHandler handler =
            new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(evaluator);
        return handler;
    }
}
```

This is an **illustrative configuration class**: a `PermissionEvaluator` bean must exist in the context, such as one declared via `@Bean` or `@Component`. For Spring Security 6.x, the documentation uses **`static @Bean`** for `MethodSecurityExpressionHandler` so Spring publishes the handler early enough before method-security infrastructure is initialized.

What matters is the `MethodSecurityExpressionHandler` **bean type** and the `handler.setPermissionEvaluator(evaluator)` call. You do not need to manually re-register the default `@PreAuthorize`/`@PostAuthorize` interceptors when `@EnableMethodSecurity` is enabled. Do not accidentally set `@EnableMethodSecurity(prePostEnabled = false)` if you expect pre/post annotations to work.

If your project already defines a custom `MethodSecurityExpressionHandler` for `RoleHierarchy`, `ParameterNameDiscoverer`, `TrustResolver`, or parsers, **configure that existing handler bean** to add `PermissionEvaluator`; avoid creating two competing handlers where it is unclear which bean is active.

### 4.2. XML registration (when a project uses XML)

With XML-based method security infrastructure, you can configure a `MethodSecurityExpressionHandler` bean and have the method-security namespace reference it:

```xml
<sec:method-security>
    <sec:expression-handler ref="myMethodExpressionHandler"/>
</sec:method-security>

<bean id="myMethodExpressionHandler"
      class="org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler">
    <property name="permissionEvaluator" ref="myPermissionEvaluator"/>
</bean>

<bean id="myPermissionEvaluator" class="demo.DocumentPermissionEvaluator"/>
```

This XML snippet **only illustrates wiring**, assuming the `sec` and `beans` namespaces are declared properly and `demo.DocumentPermissionEvaluator` exists with an appropriate constructor. In pure Java-config applications, prefer the `@Bean` example above.

### 4.3. Do not confuse with web security expression handlers

`MethodSecurityExpressionHandler` applies to annotations **on methods** protected by Spring Method Security. It does not automatically configure every `hasPermission` in `HttpSecurity` HTTP rules or in messaging/reactive security. Modern Spring Security prefers `AuthorizationManager` for HTTP authorization, which has its own extension points. Never use the success of a `@PreAuthorize` test to claim an endpoint is fully protected.

## 5. Java 17+ example: document permissions from configuration to tests

The example below intentionally uses an immutable static store in tests to distinguish the two overloads cleanly without needing a database or web server. In a real system, the ID-based evaluator must query a repository/policy on server-side data, enforcing tenant controls and performance safeguards.

### 5.1. Gradle project layout

```text
permission-evaluator-demo/
├── settings.gradle
├── build.gradle
└── src/test/java/demo/PermissionEvaluatorRegistrationTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'permission-evaluator-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.5.0')
    testImplementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Since the project contains only test code, `testImplementation` dependencies suffice. When integrating into a real application, `spring-boot-starter-security` and the evaluator implementation belong in `implementation`; test dependencies remain in the test configuration.

### 5.2. A complete single-file Java test

Create `src/test/java/demo/PermissionEvaluatorRegistrationTest.java`:

```java
package demo;

import java.io.Serializable;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringJUnitConfig(PermissionEvaluatorRegistrationTest.Config.class)
@WithMockUser(username = "alice")
public class PermissionEvaluatorRegistrationTest {

    private static final Map<Long, Document> STORE = Map.of(
        1L, new Document(1L, "alice"),
        2L, new Document(2L, "bob")
    );

    @Autowired DocumentService service;
    @Autowired DocumentPermissionEvaluator evaluator;
    @Autowired Probe probe;

    @BeforeEach
    void resetCounters() {
        probe.reset();
        evaluator.reset();
    }

    public record Document(Long id, String owner) { }

    public static class Probe {
        private final AtomicInteger executions = new AtomicInteger();

        void mark() { executions.incrementAndGet(); }
        int count() { return executions.get(); }
        void reset() { executions.set(0); }
    }

    // Centralized policy: only allow READ on a Document owned by the principal,
    // while verifying the object matches the trusted record in STORE.
    public static class DocumentPermissionEvaluator
            implements PermissionEvaluator {

        private final AtomicInteger objectCalls = new AtomicInteger();
        private final AtomicInteger idCalls = new AtomicInteger();

        @Override
        public boolean hasPermission(Authentication auth,
                                     Object target,
                                     Object permission) {
            objectCalls.incrementAndGet();

            if (!validUser(auth) || !"READ".equals(permission)
                    || !(target instanceof Document document)) {
                return false;
            }

            Document persisted = STORE.get(document.id());
            return persisted != null
                && persisted.equals(document)
                && persisted.owner().equals(auth.getName());
        }

        @Override
        public boolean hasPermission(Authentication auth,
                                     Serializable targetId,
                                     String targetType,
                                     Object permission) {
            idCalls.incrementAndGet();

            if (!validUser(auth)
                    || !"DOCUMENT".equals(targetType)
                    || !"READ".equals(permission)
                    || !(targetId instanceof Long id)) {
                return false;
            }

            Document persisted = STORE.get(id);
            return persisted != null
                && persisted.owner().equals(auth.getName());
        }

        private static boolean validUser(Authentication auth) {
            return auth != null && auth.isAuthenticated();
        }

        int objectCalls() { return objectCalls.get(); }
        int idCalls() { return idCalls.get(); }

        void reset() {
            objectCalls.set(0);
            idCalls.set(0);
        }
    }

    public static class DocumentService {
        private final Probe probe;

        public DocumentService(Probe probe) {
            this.probe = probe;
        }

        @PreAuthorize("hasPermission(#document, 'READ')")
        public String describe(@P("document") Document document) {
            probe.mark();
            return document.id() + ":" + document.owner();
        }

        @PreAuthorize("hasPermission(#id, 'DOCUMENT', 'READ')")
        public String readById(@P("id") Long id) {
            probe.mark();
            Document document = STORE.get(id);
            return document == null ? "MISSING" : document.id().toString();
        }

        @PreAuthorize("hasPermission(#id, 'INVOICE', 'READ')")
        public String unsupportedType(@P("id") Long id) {
            probe.mark();
            return "UNEXPECTED";
        }

        @PreAuthorize("hasPermission(#document, 'WRITE')")
        public String unsupportedPermission(@P("document") Document document) {
            probe.mark();
            return "UNEXPECTED";
        }

        @PostAuthorize(
            "returnObject != null and hasPermission(returnObject, 'READ')"
        )
        public Document readAfter(Long id) {
            probe.mark();
            return STORE.get(id);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableMethodSecurity
    public static class Config {

        @Bean
        static DocumentPermissionEvaluator permissionEvaluator() {
            return new DocumentPermissionEvaluator();
        }

        @Bean
        static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
                DocumentPermissionEvaluator evaluator) {
            DefaultMethodSecurityExpressionHandler handler =
                new DefaultMethodSecurityExpressionHandler();
            handler.setPermissionEvaluator(evaluator);
            return handler;
        }

        @Bean
        Probe probe() {
            return new Probe();
        }

        @Bean
        DocumentService documentService(Probe probe) {
            return new DocumentService(probe);
        }
    }

    @Test
    void serviceReallyIsProxied() {
        assertThat(AopUtils.isAopProxy(service)).isTrue();
    }

    @Test
    void objectOverloadAllowsAliceDocument() {
        assertThat(service.describe(STORE.get(1L)))
            .isEqualTo("1:alice");
        assertThat(probe.count()).isEqualTo(1);
        assertThat(evaluator.objectCalls()).isEqualTo(1);
        assertThat(evaluator.idCalls()).isZero();
    }

    @Test
    void objectOverloadDeniesBobsDocumentBeforeBody() {
        assertThatThrownBy(() -> service.describe(STORE.get(2L)))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count()).isZero();
        assertThat(evaluator.objectCalls()).isEqualTo(1);
    }

    @Test
    void idOverloadAllowsAliceDocument() {
        assertThat(service.readById(1L)).isEqualTo("1");
        assertThat(probe.count()).isEqualTo(1);
        assertThat(evaluator.idCalls()).isEqualTo(1);
        assertThat(evaluator.objectCalls()).isZero();
    }

    @Test
    void idOverloadDeniesBobsDocumentBeforeBody() {
        assertThatThrownBy(() -> service.readById(2L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count()).isZero();
        assertThat(evaluator.idCalls()).isEqualTo(1);
    }

    @Test
    void missingDocumentIsDeniedBeforeBody() {
        assertThatThrownBy(() -> service.readById(999L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count()).isZero();
    }

    @Test
    void unsupportedTargetTypeIsDenied() {
        assertThatThrownBy(() -> service.unsupportedType(1L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count()).isZero();
        assertThat(evaluator.idCalls()).isEqualTo(1);
    }

    @Test
    void unsupportedPermissionIsDenied() {
        assertThatThrownBy(() -> service.unsupportedPermission(STORE.get(1L)))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count()).isZero();
        assertThat(evaluator.objectCalls()).isEqualTo(1);
    }

    @Test
    void postAuthorizeAllowsOwnedReturnObject() {
        assertThat(service.readAfter(1L)).isEqualTo(STORE.get(1L));
        assertThat(probe.count()).isEqualTo(1);
        assertThat(evaluator.objectCalls()).isEqualTo(1);
    }

    @Test
    void postAuthorizeDeniesOtherOwnerAfterBody() {
        assertThatThrownBy(() -> service.readAfter(2L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count()).isEqualTo(1);
        assertThat(evaluator.objectCalls()).isEqualTo(1);
    }

    @Test
    void postAuthorizeRejectsNullReturnObject() {
        assertThatThrownBy(() -> service.readAfter(999L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count()).isEqualTo(1);
        // SpEL 'and' short-circuits: evaluator does not receive null.
        assertThat(evaluator.objectCalls()).isZero();
    }

    @Test
    @WithMockUser(username = "bob")
    void anotherPrincipalCanReadHisDocumentById() {
        assertThat(service.readById(2L)).isEqualTo("2");
        assertThat(probe.count()).isEqualTo(1);
        assertThat(evaluator.idCalls()).isEqualTo(1);
    }
}
```

**Why does this example demonstrate evaluator registration rather than just illustrating a boolean function?**

- `@EnableMethodSecurity` actually enables the advisors that read `@PreAuthorize` and `@PostAuthorize`.
- `@Bean static MethodSecurityExpressionHandler` configures `DefaultMethodSecurityExpressionHandler` with the **exact `DocumentPermissionEvaluator`** injected into the test.
- `DocumentPermissionEvaluator.objectCalls` and `idCalls` count how many times the framework calls each overload; assertions verify the right overload matches the right SpEL syntax.
- `Probe` confirms execution order: **pre deny** keeps `probe.count() == 0`, while **post deny** occurs after the body runs so `probe.count() == 1`.
- Static configuration registers the handler early; `@P("id")` and `@P("document")` keep SpEL parameter names stable without relying on the `-parameters` flag.
- The immutable `STORE` data is a **server-side fixture**; the object overload verifies the passed-in record matches trusted data before comparing owner. This is a minimal example to understand mechanics, not a production user/permission storage policy.
- `@WithMockUser(username = "alice")` provides `Authentication` in tests; Bob's case overrides the principal, proving the policy does not hardcode Alice.
- Because there is no web server, tests check `AccessDeniedException` rather than claiming HTTP 403. In an app with a servlet filter chain, exception translation determines the response according to configuration.

### 5.3. Running the project and expectations

In the directory containing `build.gradle`:

```bash
gradle test --tests demo.PermissionEvaluatorRegistrationTest
```

When using a Gradle Wrapper, run `./gradlew test --tests demo.PermissionEvaluatorRegistrationTest` on Linux/macOS or `gradlew.bat test --tests demo.PermissionEvaluatorRegistrationTest` on Windows.

**Expected result when properly configured:** **12 tests pass**, Gradle reports `BUILD SUCCESSFUL`. This is an **expected outcome deduced from the sample code**, not stdout captured from an actual run. See details at `build/reports/tests/test/index.html` and check the actual resolved dependency versions.

Key outcome matrix:

| Scenario | Evaluator overload | Does method body run? | Outcome |
| --- | --- | --- | --- |
| Alice reads Alice's object | Object | Yes, 1 time | Allow |
| Alice reads Bob's object | Object | No | Deny |
| Alice reads ID 1 | ID + type | Yes, 1 time | Allow |
| Alice reads ID 2 | ID + type | No | Deny |
| Nonexistent ID | ID + type | No | Deny |
| Unsupported target type `INVOICE` | ID + type | No | Deny |
| Unsupported permission `WRITE` | Object | No | Deny |
| After receives Alice's object | Object | Yes, 1 time | Allow |
| After receives Bob's object | Object | Yes, 1 time | Deny after body |
| After receives `null` | Evaluator not called due to guard expression | Yes, 1 time | Deny |
| Bob reads ID 2 | ID + type | Yes, 1 time | Allow |

The `serviceReallyIsProxied` test is an extra infrastructure check. It is insufficient on its own: having a proxy does not guarantee the right `PermissionEvaluator` is wired; the counter tests prove **the handler is actually invoking your registered evaluator**.

## 6. Adapting expressions for common scenarios

### 6.1. Checking an input object

```java
@PreAuthorize("hasPermission(#document, 'READ')")
public void inspect(@P("document") Document document) {
    // Runs only if the evaluator grants READ for document.
}
```

Here `#document` is a SpEL parameter variable, not the string literal `'document'`. `@P` or an appropriate parameter-name discovery mechanism is required; compiling Java with `-parameters` is another option.

**Trust boundary warning:** If `document` comes directly from client-submitted JSON, the client can forge the `owner` field. A safer pattern typically accepts `id` and lets the evaluator/repository check permission against the **real record** on the server. The test example above still compares the object against `STORE` precisely to illustrate this point.

### 6.2. Checking by ID + resource type

```java
@PreAuthorize("hasPermission(#id, 'DOCUMENT', 'READ')")
public Document find(@P("id") Long id) {
    return repository.findById(id).orElseThrow();
}
```

This is a **repository-dependent snippet**, not a standalone program. The ID overload receives `targetId` of type `Serializable`, `targetType` as a string you define (here `"DOCUMENT"`), and a permission string. If the expression passes `'Document'` while the evaluator only supports `'DOCUMENT'`, the example policy will deny. Standardize type/permission names deliberately and verify them with tests.

In multi-tenant setups, lookups should rely on both **ID and verified tenant**; checking only an owner string is insufficient when IDs could overlap across tenants. In large systems, optimize permission lookup counts and consider caching keyed by principal, tenant, permission, and data-change lifecycle.

### 6.3. Checking returned data

```java
@PostAuthorize("returnObject != null and hasPermission(returnObject, 'READ')")
public Document read(@P("id") Long id) {
    return repository.findById(id).orElse(null);
}
```

`returnObject` is the return value; SpEL's short-circuit `and` guarantees the evaluator is not called when the result is null. Here **null is denied** by the example policy. An application may prefer turning `null` into 404/not-found, or treating null as non-sensitive and allowing it; that is a **business rule**, not a requirement of `PermissionEvaluator`.

With `@PostAuthorize`, the service **has already run** before denial; never use an after-check as the sole guard against payments, data deletion, event publishing, or sensitive logging.

### 6.4. Filtering each collection element

When you need to filter a collection, you can write:

```java
@PostFilter("hasPermission(filterObject, 'READ')")
public java.util.List<Document> findAll() {
    return new java.util.ArrayList<>(repository.findAll());
}
```

`filterObject` represents each element in turn, so the object-based evaluator is called **for every element**. The snippet depends on `repository` and is illustrative only. With `@PreFilter`, ensure the collection is mutable because the interceptor may need to remove items. `@PostFilter` can cause N+1 permission checks and broken pagination due to post-query filtering; large datasets usually need constraints pushed directly into the query.

### 6.5. Combining role/authority checks with object permissions

```java
@PreAuthorize(
    "hasAuthority('DOCUMENT_VIEW') and hasPermission(#id, 'DOCUMENT', 'READ')"
)
public Document read(@P("id") Long id) {
    return repository.findById(id).orElseThrow();
}
```

`hasAuthority` checks the coarse-grained permission; `hasPermission` checks the specific resource. The `and` expression may short-circuit, so the evaluator is not necessarily called if the general authority already fails. Outcomes should be tested across **all four combinations**: with/without authority, and with/without object permission.

## 7. What if you already use Spring Security ACL?

Spring Security provides `AclPermissionEvaluator` to evaluate domain object ACLs. The wiring idea remains the same:

```java
@Bean
static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
        AclPermissionEvaluator aclPermissionEvaluator) {
    DefaultMethodSecurityExpressionHandler handler =
        new DefaultMethodSecurityExpressionHandler();
    handler.setPermissionEvaluator(aclPermissionEvaluator);
    return handler;
}
```

This is a **component configuration snippet**, which only works once the project has configured `AclService`, ACL cache/lookup strategies, permission granting, and the required data structures. Merely declaring `AclPermissionEvaluator` or adding the `spring-security-acl` dependency without an ACL store does not grant or enforce object permissions.

A custom domain evaluator fits well when policy centers on owner/tenant/state and business data sources. `AclPermissionEvaluator` fits when the application genuinely manages **access control entries** per object/SID/permission. Both run through `hasPermission` once wired into the expression handler.

## 8. Common failures and diagnostics

| Symptom | Common cause | How to check/fix |
| --- | --- | --- |
| `hasPermission` always returns false even though unit tests on custom evaluator return true | Expression handler uses the default `DenyAllPermissionEvaluator` or has no evaluator attached | Register `MethodSecurityExpressionHandler` with `setPermissionEvaluator`; test that call counters actually increment |
| Annotations appear inactive | Missing `@EnableMethodSecurity`, test uses `new Service()`, or self-invocation | Inject the Spring-managed bean and write a test proving denial happens before the body |
| Evaluator bean exists but Spring ignores it | Only `@Component PermissionEvaluator` exists, another handler bean wins, or late registration | Inspect `MethodSecurityExpressionHandler` beans, prefer `static @Bean` and explicit wiring |
| `#id` becomes null or wrong value | Bytecode lacks parameter names, wrong `@P`, or wrong casing | Use `@P("id")` or compile with `-parameters` |
| Wrong overload called | Writing `hasPermission(#id, 'READ')` when intending type-specific lookup | Use three arguments: `hasPermission(#id, 'DOCUMENT', 'READ')` |
| All object types denied | `targetType` in SpEL differs from the string accepted by the evaluator | Standardize types and assert unsupported cases too |
| `ClassCastException` / `NullPointerException` | Casting target/permission without type checks, or null result | Use `instanceof`, null guards, and fail closed |
| Client-supplied object alters `owner` to bypass policy | Trusting properties from the request body | Load the trusted record by ID/tenant instead of trusting DTO fields |
| Post-authorize denies yet database was already modified | Method ran before the after-check | Prevent side effects using pre-checks/policies/appropriate transaction boundaries |
| Filtering large lists is slow | `@PostFilter` calls the evaluator repeatedly, querying per item | Filter in repository/query directly, batch/cache per security design |
| Expecting HTTP rules to use the method evaluator | Confusing web and method security configuration | Check both `MethodSecurityExpressionHandler` and the HTTP authorization subsystem |
| Forgetting to test other users | Policy implicitly hardcodes Alice or caches wrongly | Test Bob, another tenant, null, invalid permissions, and permission changes |

### Practical debugging checklist

1. Verify `@EnableMethodSecurity` is active in the Spring context where the bean runs, and annotations sit on methods interceptable by the proxy.
2. Ensure calls reach the method through the **Spring bean proxy**, not `new` or `this.method()`.
3. Confirm only **one primary handler** is used for annotations: bean type `MethodSecurityExpressionHandler`, with `setPermissionEvaluator(...)` receiving the right evaluator.
4. For parameter-based expressions, verify `#id`/`#document` are resolved via `@P` or `-parameters`, not passed as literals without `#`.
5. Test both overloads separately and verify with counters/safe logging; never log sensitive data.
6. Test both positive and negative cases: Alice reads Alice's doc, Alice is denied Bob's doc, Bob reads Bob's doc, and unsupported permissions/types are denied.
7. For `@PostAuthorize`, account for the fact that the method body already executed before denial and handle side effects accordingly.
8. In multi-tenant environments, add tenant scoping, time-varying permissions, and appropriate caching.
9. When upgrading framework versions, check the `PermissionEvaluator` API, expression handler, and Method Security configuration against the actual version.

## 9. Design decisions for safe adoption

**Choose a trusted source of truth:** An evaluator can receive `Document` through SpEL, yet domain data arriving from a client is merely **input**, not truth. When checking owner/tenant, read real metadata from a repository or use objects loaded from an authenticated-scoped data layer; avoid accepting any object just because its `owner` attribute matches the caller's username.

**Name permissions clearly:** Choose a consistent set of names such as `READ`, `WRITE`, `DELETE`, or a suitable enum. Never assume Spring automatically maps `'READ'` to ACL's `BasePermission.READ`: that is the responsibility of the evaluator or ACL system. If using global roles/authorities, add `hasAuthority` or integrate them into your policy.

**Watch performance:** `hasPermission(filterObject, ...)` can invoke the evaluator many times for a list; `hasPermission(id, ...)` can trigger a query per request. Use queries scoped by principal/tenant, caches with explicit invalidation, or batch policies when genuinely needed. Never cache permission results globally by ID alone while forgetting the principal.

**Stay fail closed:** Nulls, unknown target types, wrong permissions, and nonexistent resources should produce clear denials unless the business contract specifies otherwise. Storage/authentication errors must never default to allow. Ensure permissions are enforced across all critical call paths, including scheduled jobs and non-HTTP batch processes.

**Separate registration tests from policy tests:** A unit test calling `new DocumentPermissionEvaluator().hasPermission(...)` only tests Java logic; it does **not** prove Spring wired the evaluator into SpEL. Integrating context, annotations, and proxies as shown in the example is what proves wiring. In production tests, also verify database ownership, dynamic permissions, transactions, and null inputs per application requirements.

## 10. Practice exercises

1. **Add WRITE:** extend the evaluator for `WRITE` with rules such as Alice being the owner and the document being unlocked; add allow/deny tests. Do not simply change `'READ'` in the annotation while leaving the old evaluator unchanged.
2. **Parameter names:** remove `@P("id")`, compile Java with `-parameters`, and verify `#id` resolves. Try a mismatched name `#documentId` and explain why the expression fails to bind the value.
3. **Switch principals:** add a record owned by Carol and `@WithMockUser(username="carol")`; verify the right record is allowed and Bob/Alice cannot cross-read it.
4. **Forged input:** construct `Document(1L, "bob")` on the client side even though document #1 in `STORE` belongs to Alice. Verify the object overload denies it because it does not match the server record.
5. **Post-method policy:** replace `returnObject != null and ...` with a policy treating null as “not found” and allowing `null` to be returned; update tests to match the API contract instead of pretending it is an authorization error.
6. **Real ACL:** if your application uses ACLs, replace the domain evaluator with `AclPermissionEvaluator`, register it on the same handler, and build integration tests with one real ACL grant and one real ACL deny.

## 11. Key takeaways

- `PermissionEvaluator` is the extension point for `hasPermission` by **specific object** or **ID + resource type**.
- You must enable `@EnableMethodSecurity` and register `DefaultMethodSecurityExpressionHandler` with `setPermissionEvaluator(...)`; Spring Security 6.x recommends declaring the handler as a **`static @Bean`**.
- `hasPermission(target, permission)` invokes the object overload; `hasPermission(id, type, permission)` invokes the ID overload. Spring supplies `Authentication` to both.
- `@PreAuthorize` checks **before the body**; `@PostAuthorize` checks **after the body** and does not roll back side effects.
- Test **actual wiring through the proxy**: allow/deny cases, right overload, right principal, null, unsupported types/permissions, and trusted data.
- For data with tenants/ownership, evaluate against server-side sources instead of trusting self-reported DTOs. The expression handler only **forwards policy**—it does not guarantee the policy itself is sound.

## Official references

- Spring Security 6.5 — Method Security, `@EnableMethodSecurity`, method expressions, `@P`, custom handler: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 — Domain Object Security / Using the PermissionEvaluator, `setPermissionEvaluator` pattern: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html
- Spring Security 6.5 API — `PermissionEvaluator` and both overloads: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/PermissionEvaluator.html
- Spring Security 6.5 API — `DefaultMethodSecurityExpressionHandler`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/expression/method/DefaultMethodSecurityExpressionHandler.html
