# RequestAuthorizationContext and MethodInvocation as Decision Contexts

## 1. The Problem: An Authorization Decision Must Know **What It Is Protecting**

In Spring Security, an `AuthorizationManager<T>` receives two inputs:

- `Supplier<Authentication>`: how to obtain the authenticated identity, including granted authorities.
- `T`: **the context of the action to be allowed or denied**.

`T` is not a fixed type. When protecting an HTTP request in a Servlet application, Spring Security typically uses `RequestAuthorizationContext`; when protecting a service method call via Spring AOP, the context is `MethodInvocation`. The two objects carry different data, appear at different times, and apply to different protection boundaries.

This lesson focuses on reading and using the **right decision context**, especially when writing a custom `AuthorizationManager`: avoiding confusion between URLs and method parameters, avoiding trusting client-asserted data, choosing the right enforcement point, and testing allow/deny decisions.

Sample scenario: an application has `Document` resources. A user may read a document if they have the `document:read` authority, belong to a valid tenant, and are the owner according to the database. When accessing `GET /api/documents/7`, the HTTP layer has the path and path variable `7`; when the service `readDocument(7L)` runs, the method layer has `MethodInvocation` with argument `7L`. Both need a trusted policy to know **who owns document 7**.

## 2. The AuthorizationManager<T> Contract

In Spring Security 6.4+ and 7.x, the modern API defines the primary decision method as `authorize(...)`:

```java
AuthorizationResult authorize(
    Supplier<Authentication> authentication,
    T object
);
```

The signature above is **abbreviated for readability**; API documentation for specific versions may include nullability annotations or wildcards on `Supplier`. The return type is typically `AuthorizationDecision`, an implementation of `AuthorizationResult`, carrying the `isGranted()` state. Older applications may encounter `check(...)` returning `AuthorizationDecision`; use the exact signature from your actual dependency rather than copying across versions.

Semantically, there are three possible outcomes:

| Result | Interpretation |
| --- | --- |
| `new AuthorizationDecision(true)` | This rule allows the action |
| `new AuthorizationDecision(false)` | This rule denies the action |
| `null` | Abstain — the manager makes no decision |

**Do not use `null` to represent denial.** How abstain is handled depends on the caller and how managers are composed; for critical policies, return an **explicit denial** when identity, resource, or trusted data is missing. `AuthorizationManager.verify(...)` is responsible for throwing `AccessDeniedException` upon receiving a denial decision.

The reason for using `Supplier<Authentication>` rather than eagerly passing an authentication object is to support **fetching identity only when actually needed**. For example, a `permitAll` rule may never need to access `Authentication`. When writing a custom manager, only call `authentication.get()` if identity is needed; avoid calling it repeatedly or assuming the result is always non-`null`.

Naming note: `AuthenticationManager` handles **authentication** of credentials, whereas `AuthorizationManager` handles **authorization** of an action on an object/context. Those are two different roles.

## 3. RequestAuthorizationContext: Decisions at the HTTP Boundary

Java type:

```java
org.springframework.security.web.access.intercept.RequestAuthorizationContext
```

This is the Servlet context for request-based decisions. Notable APIs:

- `getRequest()` returns `jakarta.servlet.http.HttpServletRequest`, including HTTP method, URL, headers, parameters, and request attributes.
- `getVariables()` returns `Map<String, String>` containing variables **extracted by the request matcher**, such as `documentId` from pattern `/api/documents/{documentId}`.
- Constructors accept `HttpServletRequest`, or the request together with a map of path variables — useful in unit tests.

When using `HttpSecurity.authorizeHttpRequests(...)`, Spring Security selects the matching rule, invokes the `AuthorizationManager<RequestAuthorizationContext>` configured for that rule, and allows or denies based on the decision. In the modern Servlet pipeline, `AuthorizationFilter` performs this authorization step.

Data semantics example:

```text
HTTP GET /api/documents/7?view=full
  |
  | requestMatcher: /api/documents/{documentId}
  v
RequestAuthorizationContext
  getRequest().getMethod()  -> "GET"
  getRequest().getRequestURI() -> "/api/documents/7"
  getVariables().get("documentId") -> "7"
  getRequest().getParameter("view") -> "full"
```

This is only an illustrative diagram for a request matching that pattern. `getVariables()` is not an arbitrary map of every query parameter or every controller variable; if the matcher does not extract variables, the map may be empty. If using prefixes, servlet paths, proxies, or other matcher configurations, verify the actual URL and extracted variables in integration tests.

**Important boundary:** path variables, headers, query parameters, and bodies are all caller-controlled data. The variable `documentId=7` only says the user is requesting **document 7**. It **does not prove** the user owns or has permission to read that document.

### Read the Request to Decide, But Do Not Trust the Request as the Source of Truth

A good rule can use the request context to:

1. Check the allowed HTTP action, such as `GET` only.
2. Extract an identifier from the matcher and validate its type/range.
3. Obtain identity from `Supplier<Authentication>` and check authorities.
4. Look up resource/tenant/ACL data via a trusted policy.
5. Return an explicit boolean decision, favoring deny if information is missing.

Do not use `request.getParameter("role")` to let clients choose the required role; do not treat `X-Tenant-Id` as self-proving tenant access. If a tenant ID arrives in a header, it is only a **requested tenant selection input** and must be verified against server-side authenticated membership.

## 4. Implementing a Manager at the HTTP Layer

The following snippets are **components for a Spring Boot application using Spring Security 6.4+ or 7.x on Servlet**, not a standalone Java program. They assume application beans `DocumentPolicy`, `DocumentRepository`, and entity `Document` exist.

First, a shared policy bean checks permissions based on identity and **real data**:

```java
import java.util.Optional;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component
public class DocumentPolicy {
    private final DocumentRepository documents;
    private final TenantAccess tenantAccess;

    public DocumentPolicy(
            DocumentRepository documents, TenantAccess tenantAccess) {
        this.documents = documents;
        this.tenantAccess = tenantAccess;
    }

    public boolean canRead(Authentication auth, Long id) {
        if (auth == null || !auth.isAuthenticated()
                || auth instanceof AnonymousAuthenticationToken
                || id == null || id <= 0L) {
            return false;
        }

        boolean hasAuthority = auth.getAuthorities().stream()
            .anyMatch(a -> "document:read".equals(a.getAuthority()));
        if (!hasAuthority) {
            return false;
        }

        // TenantAccess is a business service that verifies membership
        // from a trusted source, not just from a client-sent header.
        Optional<String> tenant = tenantAccess.authorizedTenant(auth);
        if (tenant.isEmpty()) {
            return false;
        }

        return documents.existsByIdAndTenantIdAndOwnerUsername(
            id, tenant.get(), auth.getName());
    }
}
```

In this example, `DocumentRepository` needs a derived query `existsByIdAndTenantIdAndOwnerUsername(Long id, String tenantId, String ownerUsername)` or an equivalent query; `TenantAccess.authorizedTenant(...)` is an application contract we must implement. The policy intentionally **allows only the owner to read**. If the product supports sharing via ACL/groups, the check must be extended using trusted business logic and data, never relaxed by accepting `owner` from the request.

Next, the HTTP request manager. We use a **lambda** to avoid depending on wildcard variance in `authorize` signatures across versions, while still implementing `AuthorizationManager<RequestAuthorizationContext>`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

@Configuration
public class DocumentHttpAuthorizationConfig {
    @Bean
    AuthorizationManager<RequestAuthorizationContext> documentRequestManager(
            DocumentPolicy policy) {
        return (authentication, context) -> {
            String rawId = context.getVariables().get("documentId");
            Long id = parsePositiveId(rawId);
            if (id == null) {
                return new AuthorizationDecision(false);
            }

            Authentication actor = authentication.get();
            return new AuthorizationDecision(policy.canRead(actor, id));
        };
    }

    private static Long parsePositiveId(String raw) {
        if (raw == null || !raw.matches("[1-9][0-9]{0,17}")) {
            return null;
        }
        try {
            return Long.valueOf(raw);
        } catch (NumberFormatException ex) {
            return null;
        }
    }
}
```

Here `context.getVariables().get("documentId")` comes from the route matcher. `parsePositiveId` illustrates an input contract restricting positive decimal IDs up to 18 digits; projects using UUIDs or other ID formats must substitute the corresponding parser/validator. Invalid input returns `false` rather than throwing unnecessary exceptions or "defaulting to allow."

Registering the manager on a specific path:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

@Configuration
public class ApiSecurityConfig {
    @Bean
    SecurityFilterChain api(
            HttpSecurity http,
            AuthorizationManager<RequestAuthorizationContext> documentRequestManager
    ) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/documents/{documentId}")
                .access(documentRequestManager)
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
```

In a real application, combine this configuration with API authentication, CSRF/CORS, exception handling, and other endpoints as required by the product. Because the sample uses `anyRequest().denyAll()`, other routes will be denied unless matched by appropriate chains/rules. `RequestAuthorizationContext.getVariables()` must be verified against the **actually configured matcher**: changing matchers, servlet mappings, or framework versions can affect how variables are extracted.

**Rule placement:** `authorizeHttpRequests` evaluates request matchers in declaration order; the first matching rule wins. Therefore, place specific patterns before broad wildcards, include an appropriate `denyAll`/authentication fallback rule, and test path variants (encoded characters, slashes, suffixes, HTTP method differences).

## 5. MethodInvocation: Decisions at the Method Invocation Boundary

Java type:

```java
org.aopalliance.intercept.MethodInvocation
```

`MethodInvocation` represents **a Java method call currently intercepted by Spring AOP**. It is not an `HttpServletRequest` and can exist whether the method is invoked from a scheduled job, message listener, batch job, test, or another service.

Commonly used members:

| API | Meaning and usage |
| --- | --- |
| `getMethod()` | Reads the `Method` reflecting the invoked method: name, parameter types, and annotations depending on proxy mode |
| `getArguments()` | Accesses the runtime argument array in declaration order |
| `getThis()` | The target object on which the call is executed, not HTTP caller information |
| `proceed()` | `MethodInvocation` method for interceptors to continue execution; **do not call it inside AuthorizationManager** |
| `getStaticPart()` | Static joinpoint metadata, usually unnecessary for simple policies |

A typical `AuthorizationManager<MethodInvocation>` **only reads** the method name and arguments, retrieves `Authentication`, checks the policy, and returns a decision. Proceeding or blocking the invocation is performed by `AuthorizationManagerBeforeMethodInterceptor`; the business method does not run if the manager denies.

Example:

```text
Controller / message listener / other service
     -> DocumentService.readDocument(7L)
         |
         v
     Spring AOP proxy
         |
         v
     MethodInvocation
       getMethod().getName() -> "readDocument"
       getArguments()[0] -> Long(7)
       getThis() -> DocumentService target
         |
         v
     AuthorizationManager<MethodInvocation>
         |
         +-- DENY -> block before method
         |
         +-- GRANT -> invoke target method
```

Do not rely on `getThis()` being an HTTP controller or being able to obtain a request from it. When a policy must apply across **all invocation paths** of a service, `MethodInvocation` and method security have a clear advantage over HTTP-only checks.

### Why Arguments Are Not Authorization Proof

Suppose a caller invokes `readDocument(7L)`. The argument `7L` is a request to read the document; it **does not prove** the user is allowed to read it. If a method receives a `Document` entity deserialized from a client, the `ownerUsername` field inside that entity must not be treated as actual authority either. Always read owner/tenant/ACL attributes from a server-controlled source, or use queries constrained by the verified identity.

`MethodInvocation.getArguments()` is an `Object[]`: validate its length, types, `null`s, and format before casting. With overloads or signature changes, indexing `args[0]` can break or misbehave; pair it with a tight pointcut, test signatures, and consider specific method names/annotations.

## 6. Implementing a Manager at the Method Layer

Suppose our real service is:

```java
package com.example.documents;

import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    private final DocumentRepository documents;

    public DocumentService(DocumentRepository documents) {
        this.documents = documents;
    }

    public Document readDocument(Long documentId) {
        return documents.findById(documentId).orElseThrow();
    }
}
```

This is a component service class requiring an implemented entity/repository. When invoked through a proxy, we want to **block before** `readDocument` queries the repository.

Method manager:

```java
import org.aopalliance.intercept.MethodInvocation;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;

@Configuration
public class DocumentMethodManagerConfig {
    @Bean
    AuthorizationManager<MethodInvocation> documentMethodManager(
            DocumentPolicy policy) {
        return (authentication, invocation) -> {
            Object[] args = invocation.getArguments();
            if (args.length != 1 || !(args[0] instanceof Long id)) {
                return new AuthorizationDecision(false);
            }

            Authentication actor = authentication.get();
            return new AuthorizationDecision(policy.canRead(actor, id));
        };
    }
}
```

The manager must not let `null` or wrong types slip through as an "undecided" result. Checking `instanceof Long id` works for `readDocument(Long documentId)`; if the parameter is primitive `long`, the value in `Object[]` is still boxed as `Long`. If a service has multiple parameters or multiple methods matched by the same pointcut, match conditions against the exact signature and write tests.

Registering an advisor **applied only to the target service method**:

```java
import org.aopalliance.intercept.MethodInvocation;
import org.springframework.aop.Advisor;
import org.springframework.aop.aspectj.AspectJExpressionPointcut;
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Role;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.method.AuthorizationManagerBeforeMethodInterceptor;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class DocumentMethodSecurityConfig {
    @Bean
    @Role(BeanDefinition.ROLE_INFRASTRUCTURE)
    Advisor documentReadAdvisor(
            AuthorizationManager<MethodInvocation> documentMethodManager) {
        AspectJExpressionPointcut pointcut = new AspectJExpressionPointcut();
        pointcut.setExpression(
            "execution(* com.example.documents.DocumentService.readDocument(..))"
        );
        return new AuthorizationManagerBeforeMethodInterceptor(
            pointcut, documentMethodManager);
    }
}
```

Prerequisites: the target class is in the matching package, the application has Spring AOP, the advisor is registered in the container, and calls go **through the proxy**. When using the corresponding Spring Boot starter and `@EnableMethodSecurity`, make sure you do not accidentally register two conflicting policies on the same method. A method already annotated with `@PreAuthorize` can also receive additional advisors; multiple checks may apply together.

We have separated:

- **Manager**: boolean decision from `Authentication + MethodInvocation`.
- **Pointcut**: selects **which methods** require that manager.
- **Before interceptor**: invokes the manager **before** the method and blocks or allows execution.
- **Policy bean**: checks resource permissions against real data.

For ordinary needs, writing `@PreAuthorize("@documentPolicy.canRead(authentication, #documentId)")` on the service is simpler than maintaining a custom advisor. A custom `AuthorizationManager<MethodInvocation>` is useful when you need a unified Java policy across many methods, custom pointcuts, or framework-level interception customization.

## 7. Comparing the Two Contexts from a Design Perspective

| Dimension | `RequestAuthorizationContext` | `MethodInvocation` |
| --- | --- | --- |
| Protection level | HTTP Servlet request | Java method call via AOP |
| Common coordinator | `AuthorizationFilter`, `authorizeHttpRequests` | `AuthorizationManagerBeforeMethodInterceptor` / method security |
| Primary inputs | `HttpServletRequest` + matcher path variables | `Method`, `Object[]` arguments, target |
| Manager type | `AuthorizationManager<RequestAuthorizationContext>` | `AuthorizationManager<MethodInvocation>` |
| Best suited for | Endpoint authorization, HTTP method, path/route, coarse-grained access | Business operation and resource authorization in services, independent of caller source |
| Watch out for | Client-controlled URL/headers/query params; matcher might not extract variables | Caller/client-controlled arguments; proxy self-invocation; overloads |
| Built-in HTTP response/status? | Authorization decision feeds the filter; does not write responses directly | HTTP-independent, errors may occur in batch/jobs |
| Built-in database ownership? | **No** | **No** |
| Can reuse a shared policy? | Yes, via `DocumentPolicy` bean | Yes, via the same `DocumentPolicy` bean |

**Core distinction:** the context answers "which request / which method is being invoked," not "is this action allowed" or "is the input data truthful." Authentication and policy answer the rest.

## 8. Multi-Layer Authorization Without Accidentally Duplicating Logic

In a real application, an HTTP action may pass through both layers:

```text
GET /api/documents/7
  -> SecurityFilterChain:
       Authentication + RequestAuthorizationContext
       check endpoint / authority
  -> Controller:
       parse path variable -> Long(7)
  -> Service proxy:
       Authentication + MethodInvocation(readDocument, [7L])
       check permission on document 7
  -> Repository:
       query constrained by tenant/owner/ACL
  -> Response
```

If both the HTTP manager and method manager call an expensive policy (for instance, querying the DB each time), a single request can perform duplicate checks. A reasonable design usually looks like:

1. The HTTP layer requires authentication, route authorities, HTTP method checks, and valid request conditions.
2. The service layer enforces operation permissions tied to the **actual resource**, effective across non-HTTP callers as well.
3. The repository guarantees reads/writes are constrained by tenant/owner/ACL per policy, especially for updates or large lists.

The dual-manager configuration above **intentionally reuses the same policy** to illustrate both context structures; depending on business needs, you can omit redundant DB queries at the HTTP layer and let the method/repository layers enforce resource permissions. Do not drop method-level policy just because the HTTP filter appears to check it when the service is also called by jobs, listeners, or other entry points.

**Critical point for writes:** check before updating state; watch for TOCTOU if permissions change between the check and the transaction. Enforce permission predicates inside the update query/transaction when needed. `@PostAuthorize` runs after the method, so it is not a reliable mechanism to prevent side effects that have already happened.

## 9. Data Types, Timing, Immutability, and Logging

### Data in RequestAuthorizationContext

Values like `request.getParameter("tenant")` or `context.getVariables().get("documentId")` originate from the request and must be validated and cross-checked against server data. Never concatenate them directly into SpEL, SQL, or paths to other resources. Each request has its own context; never store contexts or requests in singleton fields reused across threads.

If you need a JSON body to decide, avoid forcing an authorization filter to read and consume the request body early: filters may run before controllers and message converters, and improper body handling can break downstream processing. Rules tied to parsed/validated payloads usually belong in service methods with explicit DTOs and Java policies.

### Data in MethodInvocation

`invocation.getMethod()` may reflect the interface-declared method when using JDK proxies; if you need annotations or generic types from the implementation, choose an appropriate resolution strategy and test both interface proxies and class proxies. Never use `getMethod().getName()` alone as a security rule key when overloads exist or multiple services share method names.

`invocation.getArguments()` reflects arguments **at interceptor invocation time**. Passing through a controller does not make those values trustworthy. Never let a manager call `proceed()` itself or mutate arguments to "redirect" conditions; the manager's job is to decide, not execute business logic.

### Authentication and Threads

`authentication.get()` does not read raw request headers; it returns the authentication object established by Spring Security. Even so, not every `Authentication` is a real logged-in user; anonymous authentication can report `isAuthenticated() == true`. The sample policy rejects `AnonymousAuthenticationToken` and requires explicit authorities. With OAuth2/JWT or pre-auth, verify how the system maps principal, scopes, tenant, and authorities.

With `@Async`, executors, and other threads, `SecurityContext` may not propagate automatically; method-level managers must be tested on real threads. Never pass a request context to another thread by retaining the request object in a singleton.

### Logging, Auditing, and Sensitive Data

You may log the endpoint or operation name together with `GRANT/DENY`, timestamps, and an appropriate correlation ID. Never log the full `Authentication`, tokens, sessions, URLs containing secrets, personal parameters, or a dump of all `MethodInvocation.getArguments()`. A manager's denial result does not itself expose a reason to clients; auditing should distinguish "missing permission" from "resource not found" in line with non-disclosure policies.

## 10. Standalone Java 17 Example to Understand Both Context Types

The following example **simulates** a web context and a method context using Java records; it does not use Spring Security/AOP and does not replace integration tests. Its purpose is to show that even with different contexts, both can pass the **resource ID** to the same trusted policy.

Save as `AuthorizationContextDemo.java`:

```java
import java.util.Set;

public class AuthorizationContextDemo {
    record Actor(String name, String tenant, Set<String> authorities) {}
    record Document(long id, String tenant, String owner) {}
    record WebContext(String httpMethod, String idFromPath) {}
    record MethodContext(String name, Object[] arguments) {}

    static boolean policy(Actor actor, Document document) {
        return actor != null
            && actor.authorities().contains("document:read")
            && actor.tenant().equals(document.tenant())
            && actor.name().equals(document.owner());
    }

    static boolean webAllowed(
            Actor actor, WebContext context, Document document) {
        if (!"GET".equals(context.httpMethod())) {
            return false;
        }

        long requestedId;
        try {
            requestedId = Long.parseLong(context.idFromPath());
        } catch (NumberFormatException ex) {
            return false;
        }

        return requestedId > 0
            && requestedId == document.id()
            && policy(actor, document);
    }

    static boolean methodAllowed(
            Actor actor, MethodContext context, Document document) {
        Object[] args = context.arguments();
        if (!"readDocument".equals(context.name())
                || args.length != 1
                || !(args[0] instanceof Long id)) {
            return false;
        }
        return id == document.id() && policy(actor, document);
    }

    public static void main(String[] args) {
        Actor alice = new Actor(
            "alice", "tenant-a", Set.of("document:read"));
        Actor bob = new Actor(
            "bob", "tenant-a", Set.of("document:read"));
        Document aliceDoc = new Document(7, "tenant-a", "alice");

        WebContext getSeven = new WebContext("GET", "7");
        MethodContext readSeven =
            new MethodContext("readDocument", new Object[] {7L});

        System.out.println("Alice web: "
            + webAllowed(alice, getSeven, aliceDoc));
        System.out.println("Bob web: "
            + webAllowed(bob, getSeven, aliceDoc));
        System.out.println("Alice service: "
            + methodAllowed(alice, readSeven, aliceDoc));
        System.out.println("Bob service: "
            + methodAllowed(bob, readSeven, aliceDoc));
        System.out.println("Invalid path ID: "
            + webAllowed(alice, new WebContext("GET", "abc"), aliceDoc));
    }
}
```

Compile and run on JDK 17 or later:

```bash
javac AuthorizationContextDemo.java
java AuthorizationContextDemo
```

Exact stdout:

```text
Alice web: true
Bob web: false
Alice service: true
Bob service: false
Invalid path ID: false
```

In this code, `WebContext` carries the ID as a `String` and must parse it. `MethodContext` carries a `Long` argument already passed by the caller layer. **Even though the data types differ, both still invoke `policy(...)`** to verify authority, tenant, and owner. This code does not touch the framework; in a real application, you must test the matcher/proxy and database queries.

## 11. Testing the Manager and Integration Paths

Do not only test `DocumentPolicy.canRead`. Ensure **the actual context reaches the manager** and the interceptor is genuinely enforced.

### 11.1 Unit Testing the Web Manager

You can construct `MockHttpServletRequest` and `RequestAuthorizationContext` directly with:

```java
import java.util.Map;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

MockHttpServletRequest request =
    new MockHttpServletRequest("GET", "/api/documents/7");
RequestAuthorizationContext context =
    new RequestAuthorizationContext(
        request, Map.of("documentId", "7"));
```

This is a **test fragment** requiring `spring-test` and a real initialized/injected manager. Unit tests with a manually built context verify the manager's parse/deny logic, but **do not prove the real matcher extracts variables**. You must have MockMvc or Servlet integration tests running through `SecurityFilterChain`.

Minimum test cases: missing `documentId`, blank, malformed, overflow, negative/zero ID, missing authority, anonymous, different tenant, different owner, and valid role. An important test is ensuring `GET` is allowed by policy while `POST` on the same path is denied by the HTTP method rule in the chain.

### 11.2 Unit Testing the Method Manager

Use Mockito or a test double to construct a `MethodInvocation` with the matching method signature and an `Object[]` containing `Long`. Verify:

- `readDocument(7L)` with valid owner, tenant, and authority -> `isGranted() == true`.
- `null` ID, wrong type, wrong argument count -> `false`.
- Valid ID but wrong tenant/owner or missing authority -> `false`.
- `authentication.get()` returns `null` or anonymous -> `false`.

However, a manager passing standalone unit tests **does not guarantee** the service is proxied and the advisor is applied. In integration tests, retrieve `DocumentService` from the Spring context and call the public method; assert the body/repository does not run when denied. Test calls from controllers, schedulers, and other beans as well.

### 11.3 Testing Real Paths and Data

| Scenario | What must be proven |
| --- | --- |
| Valid HTTP path + authorized user | Matcher extracts `documentId` and manager grants access |
| Valid HTTP path + unauthorized user | Returns 401/403 per auth/entry-point config without reading unauthorized document |
| Path does not match rule | Fallback protection/deny rule takes effect |
| Direct service call from another bean | Method manager still checks permissions |
| `this.readDocument(...)` inside the same service | May bypass Spring AOP proxy; detect and fix design |
| Concurrent tenant/owner change | Policy and transaction/query prevent unauthorized read/write due to race |
| HTTP manager and method manager both running | No excessive duplicate DB queries, no conflicting allow branches |
| Async or message processing | `Authentication`/SecurityContext is properly available or safely denies |
| Invocation with wrong signature | Explicit deny, no `ClassCastException` or silent allow |

Some projects handle "cannot view or does not exist" as HTTP 404 to limit resource existence leakage. That decision belongs to API/exception-handling design and must be consistent; `AuthorizationDecision(false)` does not automatically guarantee a specific status code in all configurations.

## 12. Common Mistakes and How to Fix Them

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Using `RequestAuthorizationContext` to get controller parsed/validated method arguments | It only holds the Servlet request and matcher variables | Use `MethodInvocation` for service parameters |
| Assuming `context.getVariables()` always holds all controller variables | Depending on the matcher, the map may be empty or lack the expected key | Test the matcher; treat missing variable as deny |
| Trusting `documentId`, `owner`, `tenant` from path/header as proof of ownership | Client-controlled input | Query owner/tenant/ACL using authenticated server identity |
| Calling `authentication.get()` and assuming actor is a real user | Auth may be missing or anonymous | Check identity, authorities, and real auth policy |
| Returning `null` when user lacks permission | `null` is abstain, not deny | Return `new AuthorizationDecision(false)` |
| Calling `invocation.proceed()` inside the manager | Mixes decision with business method execution | Only return the decision; the interceptor controls proceeding |
| Using `getArguments()[0]` without checking type/length | Prone to exceptions or wrong authorization if signature changes | Explicitly check types, tighten pointcut, and test overloads |
| Using method name as the sole policy key | Name collisions/overloads/interface proxies can fail | Use pointcut, signature, annotations, and tests |
| Protecting only URLs, skipping services reused by jobs | Non-HTTP paths lack checks | Add method security/service-layer enforcement |
| Protecting a method only with annotations and calling `this.method()` | Self-invocation can bypass the proxy | Design public entry points via Spring beans/proxies |
| Separating permission checks from tenant-scoped queries | Races or unconstrained data queries | Place permission predicates directly in data access, in the same transaction when needed |
| Debugging by dumping full requests and invocations | Leaks tokens, headers, sensitive data | Log minimal metadata, mask private details |

## 13. Context Selection Checklist

1. **Where does the policy apply?** HTTP endpoints use `RequestAuthorizationContext`; service operations use `MethodInvocation`.
2. **Extracting the right data?** HTTP: method/path/matcher variables. Method: signature and arguments.
3. **Which data is untrusted?** All path/header/query values and arguments passed by caller/HTTP can be forged.
4. **Obtained Authentication properly?** Check null/anonymous and system-granted authorities.
5. **Checked permissions on the real resource?** Use server policy + tenant/owner/ACL in the database.
6. **What if data is missing?** Return explicit deny; never confuse abstain with deny.
7. **Attached manager at the right enforcement point?** HTTP: `.access(manager)` on specific matcher. Method: `Advisor` and specific pointcut or appropriate annotation.
8. **Tested real matcher/proxy?** Unit tests on the manager do not replace integration tests.
9. **Accounted for non-HTTP call paths?** Schedulers, message listeners, internal services, async, self-invocation.
10. **Avoided double work and races?** Leverage HTTP coarse-grained checks, method-level resource policies, and constrained data queries.

**Lesson takeaway:** `RequestAuthorizationContext` answers "**which request is being made?**"; `MethodInvocation` answers "**which method with which arguments is being invoked?**". Together with `Authentication`, both supply input to `AuthorizationManager`, while the truth about resource access must be verified by **trusted policy and data**.

## Official Documentation

- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): `AuthorizationManager`, `AuthorizationResult`, supplier, and allow/deny/abstain decisions.
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `authorizeHttpRequests`, `requestMatchers`, `.access(...)`, and path variables.
- [Spring Security API — RequestAuthorizationContext](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/access/intercept/RequestAuthorizationContext.html): `getRequest()` and `getVariables()`.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, custom `AuthorizationManager<MethodInvocation>`, and `AuthorizationManagerBeforeMethodInterceptor`.
- [Spring Security API — AuthorizationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationManager.html): current API signature and the `authorize` method.
