# Authorization Checks and Input Constraints When Selecting Classes or Methods via Java Reflection

## 1. The Problem: Reflection Turns Names into Executable Behavior

Reflection lets a program look up `Class`, `Method`, `Field`, or `Constructor` at runtime. If class/method names, parameter types, or target objects are chosen **directly from a request, JSON, query parameter, header, external configuration, or queue message**, the application can inadvertently create a mechanism for **invoking arbitrary functionality**.

A dangerous design example, **solely for analysis—do not use in applications**:

~~~java
// UNSAFE example. This is an excerpt, not a standalone program.
Class<?> clazz = Class.forName(requestedClassName);
Object object = clazz.getDeclaredConstructor().newInstance();
Method method = clazz.getMethod(requestedMethodName, String.class);
Object result = method.invoke(object, requestedArgument);
~~~

Here, `requestedClassName` and `requestedMethodName` must not be arbitrarily decided by the client. If software contains many classes affecting data, a user's permissions should allow calling only a narrow set of tasks; the snippet above imposes no such boundary.

**Protection goal:** callers may select only **published actions**, on **resources they are authorized for**, with **validated arguments**, through **receivers and Methods controlled by trusted code**.

An important rule: **`public` in Java does not mean "the current user is allowed to call it via an API"**. Likewise, `setAccessible(true)` relates to reflection access checks and module boundaries; **it performs no business authorization checks whatsoever**.

## 2. Threat Model: Distinguishing Four Data Sources

| Component | Expected trusted source | Risk if client-controlled |
| --- | --- | --- |
| **Identity and role** | Server-verified authentication context, signature/validity-verified token, valid session | Client claims to be `ADMIN`, spoofs tenant or principal |
| **Operation name** | Short key in a server-defined allowlist, e.g. `profile.read` | Invoking internal methods like `resetAll` or picking unintended classes |
| **Receiver/Method** | Instance/Method pre-resolved, registered, and cached by the server | Arbitrarily choosing a class or method; instantiating out-of-scope objects |
| **Business arguments** | Strings/IDs/schemas parsed, validated, and ownership-checked | IDOR/BOLA, cross-tenant access, oversized payloads, wrong type conversions |

*Authentication* answers "who is the caller?". *Authorization* answers "is the caller allowed to perform **this action on this resource**?". *Input validation* answers "does the data have the right type, format, and bounds?". All three steps must be executed **independently**; one step cannot replace another.

For example, a user may be allowed to read their own profile but is **not by default** allowed to read someone else's profile; an admin may be allowed certain privileged actions, yet each action still needs a specific policy. In multi-tenant systems, checking the target object's tenant matters even more than checking only the method name.

## 3. Recommended Architecture: Action Allowlist Instead of Arbitrary Name-Based Reflection

~~~text
Client:
  action = "profile.read"
  userId = "U-0001"
      |
      v
[1] Obtain identity from server-authenticated session/token
      |
      v
[2] Look up action in fixed allowlist
    "profile.read" -> ProfileService.read(String)
    "account.lock" -> AdminService.lock(String)
      |
      v
[3] Validate input: type, length, pattern, element count...
      |
      v
[4] Authorization: role + permissions on resource/tenant
      |
      v
[5] Invoke exact server-registered Method/receiver
      |
      v
[6] Return appropriate public result; controlled logging/auditing
~~~

Do not expose full class names like `com.company.AdminService` or arbitrary Java signatures in the request interface. Map a stable action code to a **server-owned** receiver and method:

- The allowlist must be **explicit**: for example `"profile.read"` and `"account.lock"`, not scanning all `public` methods and assuming all are allowed.
- Fix signatures: `getMethod("read", String.class)` differs from `getMethod("read", Object.class)` and other overloads.
- Bind the **security policy to the registered route**; do not merely validate a request name and then pick a different `Method` afterward.
- If no route matches, **deny by default**. Do not fall back to `Class.forName(userInput)` or `getDeclaredMethod(userInput)`.
- If reflection is unnecessary, direct Java calls or an interface/strategy router are usually easier to audit and safer. Reflection is not mandatory for dynamic dispatch.

## 4. Complete Java 17+ Program: Safe Method Selection

A minimal illustrative example: two actions are exposed, actors hold `USER` or `ADMIN`, reading a profile is permitted **for oneself** or an admin, while locking an account is allowed only for admins. Services in the demo return strings and **do not actually access or modify accounts**.

Save as **`SafeReflectionRouterDemo.java`**:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.Map;
import java.util.regex.Pattern;

public class SafeReflectionRouterDemo {
    enum Role { USER, ADMIN }
    enum Policy { SELF_OR_ADMIN, ADMIN_ONLY }

    // Actor is created only from a trusted server-side authentication context.
    record Actor(String userId, Role role) {}

    record Route(Object receiver, Method method, Policy policy) {}

    public static final class ProfileService {
        public String read(String userId) {
            return "profile:" + userId;
        }
    }

    public static final class AdminService {
        public String lock(String userId) {
            return "locked:" + userId;
        }
    }

    // Resource ID is fixed ASCII; does not accept paths or class names.
    private static final Pattern USER_ID = Pattern.compile("U-[0-9]{4}");

    // Method/receiver are resolved from trusted constants once.
    private static final Map<String, Route> ROUTES = buildRoutes();

    private static Map<String, Route> buildRoutes() {
        try {
            ProfileService profile = new ProfileService();
            AdminService admin = new AdminService();

            return Map.of(
                "profile.read",
                new Route(
                    profile,
                    ProfileService.class.getMethod("read", String.class),
                    Policy.SELF_OR_ADMIN),
                "account.lock",
                new Route(
                    admin,
                    AdminService.class.getMethod("lock", String.class),
                    Policy.ADMIN_ONLY)
            );
        } catch (NoSuchMethodException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    static String dispatch(Actor actor, String action, String targetId) {
        // Action code is neither a Java class name nor a method name.
        if (action == null || action.length() > 40) {
            throw new IllegalArgumentException("UNSUPPORTED_ACTION");
        }

        Route route = ROUTES.get(action);
        if (route == null) {
            throw new IllegalArgumentException("UNSUPPORTED_ACTION");
        }

        if (targetId == null || !USER_ID.matcher(targetId).matches()) {
            throw new IllegalArgumentException("INVALID_ID");
        }

        // Identity must come from the auth system, not the JSON request.
        if (actor == null || actor.role() == null) {
            throw new SecurityException("DENIED");
        }

        boolean permitted = switch (route.policy()) {
            case ADMIN_ONLY -> actor.role() == Role.ADMIN;
            case SELF_OR_ADMIN -> actor.role() == Role.ADMIN
                    || actor.userId().equals(targetId);
        };

        if (!permitted) {
            throw new SecurityException("DENIED");
        }

        try {
            return (String) route.method().invoke(
                    route.receiver(), targetId);
        } catch (IllegalAccessException ex) {
            throw new IllegalStateException("SERVER_CONFIGURATION_ERROR", ex);
        } catch (InvocationTargetException ex) {
            // Do not return stack traces or target exception details to the client.
            throw new IllegalStateException("OPERATION_FAILED");
        }
    }

    static void show(Actor actor, String action, String userId) {
        try {
            System.out.println(action + " -> "
                    + dispatch(actor, action, userId));
        } catch (IllegalArgumentException | SecurityException ex) {
            System.out.println(action + " -> " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        Actor owner = new Actor("U-0001", Role.USER);
        Actor admin = new Actor("U-9000", Role.ADMIN);

        show(owner, "profile.read", "U-0001");
        show(owner, "profile.read", "U-0002");
        show(owner, "account.lock", "U-0002");
        show(admin, "account.lock", "U-0002");
        show(owner, "java.lang.Runtime.exec", "U-0001");
        show(admin, "profile.read", "U-0001/../../");
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -encoding UTF-8 SafeReflectionRouterDemo.java
java SafeReflectionRouterDemo
~~~

Expected output:

~~~text
profile.read -> profile:U-0001
profile.read -> DENIED
account.lock -> DENIED
account.lock -> locked:U-0002
java.lang.Runtime.exec -> UNSUPPORTED_ACTION
profile.read -> INVALID_ID
~~~

### Why Is This Example Safer Than Arbitrary Class/Method Selection?

1. **Clients choose a key, not a Class.** `"java.lang.Runtime.exec"` is not a registered key so it is rejected; there is no `Class.forName(action)` call.
2. **Receivers and Methods are fixed.** `ProfileService.class.getMethod(...)` and `AdminService.class.getMethod(...)` execute only on server constants resolved at startup. There is no wildcard like "every public method of a class".
3. **Policies are bound to Routes.** `profile.read` accepts only the owner or an admin; `account.lock` accepts only an admin. Having a valid action name **is not enough** to be permitted to execute.
4. **Arguments are constrained.** `U-[0-9]{4}` is an example of a valid ID with exactly 6 characters. Path-like strings are rejected; the regex uses `matches()`, so it must match the **entire** value rather than a partial match.
5. **Every request is still authorized.** Caching `Method` only avoids repeated lookups; **never cache an "allowed" result to reuse for other callers**.
6. **No elevation of reflection access.** The example uses only registered `public` methods. It does not call `setAccessible(true)` or `trySetAccessible()` to open private members.

**Limitations of the demo:** `Actor` is constructed directly in `main` to simulate an authenticated context. In a real service, **never** construct `Actor(userId, role)` from two client-supplied fields. Use verified identity/claims from the auth layer, and check the target object via database/service by tenant and ownership. `ProfileService` and `AdminService` in the example only return strings and thus do not represent real data validation, transactions, auditing, or rate limiting.

## 5. Verification Layers Required in Production

### 5.1. Authentication: Where Do Caller Privileges Come From?

- The server validates the session or token: signature, issuer, audience, expiration, and revocation when the system supports it.
- Identity, role, and tenant must never be determined merely by `request.getParameter("role")` or a JSON field.
- In service-to-service calls, distinguish end-user identity from machine identity; a service account is not automatically permitted to perform every operation on behalf of users.
- Missing or invalid requests must fail closed before invoking members that affect data.

### 5.2. Authorization: Check Both Operation and Resource

| Question | Example |
| --- | --- |
| Is the caller allowed to invoke the action? | Regular users cannot invoke `account.lock` |
| Does the caller have rights on **this object**? | Permitted for `profile.read`, but only for profiles within granted scope |
| Does the resource belong to the right tenant/organization? | Do not read another tenant's account even if the ID format matches |
| Does the resource state permit the operation? | Locked or deleted accounts must be handled per state machine |
| Must rights be rechecked right before mutation? | Avoid TOCTOU when permissions or data state can change |
| Who records the change? | Audit actor, action, resource ID, outcome; strip secret data |

**An ID matching a regex is not proof of ownership.** The example illustrates only self-or-admin; in real applications, object-level authorization must be enforced against trusted data. In multi-tenant systems, you can query resources using the **pair** `(tenantId, resourceId)` and verify permissions before processing. The service/domain layer should enforce corresponding permission checks so they cannot be bypassed if invoked outside the HTTP router.

### 5.3. Input Validation: Limit Cost and Attack Surface

Do not validate only class/method names. Every argument passed to reflection is also input data:

- **Action allowlist:** only registered keys. Constrain length, encoding, and format; do not accept arbitrary fully qualified class names.
- **Arity and types:** the selected `Method` must match the exact registered signature; parse JSON into fixed DTOs/schemas before invoking. Do not let clients pass type names in a `Class<?>[]` array to pick overloads themselves.
- **Strings, IDs, and paths:** constrain length and character sets; when paths are needed, canonicalize and verify paths remain inside an allowed root **after resolution**, preventing traversal and out-of-scope symlinks.
- **Size and depth:** limit request body size, collection element count, nesting depth, call count, and timeouts/rate limits. Even an allowed action can cause resource exhaustion if payloads are uncapped.
- **Numeric types and enums:** check min/max bounds, overflow, and valid values; do not rely on `Method.invoke` to catch every business error.
- **Output:** filter allowed return fields; do not serialize entire internal objects or exceptions/stack traces.
- **Logging:** never log passwords, tokens, sensitive PII, or raw `args`. You may log action keys, correlation IDs, and authorization decisions.

### 5.4. Class Selection in Plugins/Configuration

Some applications genuinely need configurable class names (such as plugin architectures). In that case:

1. Distinguish **operator-managed config** from end-user input. Do not treat both sources with the same level of trust.
2. Apply an allowlist or registry of approved providers; verify artifact origin, signatures, and versions per your deployment model.
3. After `Class.forName(...)`, check `expectedInterface.isAssignableFrom(clazz)` and allowed APIs/constructors. **Type checking only confirms type compatibility; it does not prove the code is trustworthy.**
4. Restrict privileges and resources at the **process/container/OS/service-account** level for untrusted plugins; a separate class loader **is not a security sandbox**.
5. Authorize and validate arguments separately for each capability. Do not turn "loaded plugin" into "plugin allowed to do anything".
6. Prefer controlled capability registration or factories instead of accepting arbitrary class names from requests.

Note that `Class.forName(String)` is not a harmless verification step: the single-argument overload can trigger **class initialization** per API semantics, so `static` initializers in the class also matter. The `Class.forName(name, false, loader)` overload can avoid initialization at that step, yet **does not make arbitrary class loading safe**, nor does it replace access control.

## 6. Reflection Access Differs from Business Authorization

Java has multiple layers of control; do not confuse them:

| Layer | Mechanism | What it does not guarantee |
| --- | --- | --- |
| Java language | `public`, `protected`, package-private, `private` | Does not verify an HTTP user has business rights |
| Reflection API | `getMethod`/`getDeclaredMethod`, `canAccess`, `trySetAccessible` | Does not check ownership, role, or tenant |
| Java module system (JPMS) | `exports`, `opens`, and deep reflection rules | Does not confirm a request is behaviorally valid |
| Application | Authentication, authorization, tenant/object policy, validation, audit | Must be explicitly programmed; the JVM does not infer business rules |

`getDeclaredMethod(...)` can **locate** a private method, which does not mean the caller is permitted to invoke it. `setAccessible(true)` only requests bypassing certain access checks **within module-permitted boundaries** and can throw `InaccessibleObjectException`; it does not make an operation valid for security. Avoid using `--add-opens` to open modules merely to "make every request run".

In addition, Java reflection has runtime exceptions that must be handled properly: `NoSuchMethodException` when lookup finds nothing, `IllegalAccessException` when invocation is not permitted, `IllegalArgumentException` when receiver/arguments are wrong, and `InvocationTargetException` wrapping causes thrown by the method body. These errors **do not replace** logic that rejects requests before execution.

## 7. Anti-Patterns and Alternatives

| Anti-pattern | Why it is dangerous | Alternative design |
| --- | --- | --- |
| `Class.forName(request.className)` on arbitrary input | Selects classes outside intended functionality, may trigger initialization | Trusted class registry/allowlist or disallow class selection |
| `clazz.getMethod(request.methodName, ...)` then invoke | A public method is not synonymous with exposed to requests | Fixed action key → `Route` containing Method and policy |
| `setAccessible(true)` to call private APIs | Expands deep reflection surface; bypasses design boundaries | Audited public facade; least-privilege OS/module permissions |
| `isAdmin = request.get("admin")` | Client decides its own privileges | Principal and claims from verified auth server |
| Checking only `id.matches(...)` | Well-formed, yet may belong to another user | Object/tenant authorization from trusted data sources |
| Caching authorization decisions per method | Different users have different rights | Cache metadata, **evaluate policy per call** |
| Auto-exposing every method annotated with `@Action` | Annotations are insufficient without review/policy control | Approved registry, explicit policies, controlled scanning |
| Returning `ex.getCause().toString()` to clients | Leaks internals and potentially sensitive data | Standardized public error codes, protected internal logs |
| Checking `startsWith("com.safe.")` and accepting any class | Package/namespace does not prove code or capabilities are trusted | Concrete type allowlist and artifact/source control |

## 8. Pre-Production Checklist

1. The request interface selects only **published action codes**; it does not accept arbitrary class names, private methods, or constructors.
2. The registry stores **receiver + Method + policy** established by the server. No route → deny.
3. Identity/role/tenant come from an **authenticated source**; never read directly from payload to determine privileges.
4. Enforce authorization **on every call** for both action and resource/tenant; for state-mutating operations, also consider race/TOCTOU conditions.
5. Constrain schemas/types/lengths/counts/depth/rates; do not delegate validation to `Method.invoke`.
6. Never use `setAccessible` or `--add-opens` as an authorization mechanism; treat public APIs and authorization as two separate concerns.
7. Test cases: unknown actions, method overloads, users lacking roles, cross-tenant IDs, oversized requests, null inputs, and target exceptions.
8. Audit denials and critical operations with minimal data; client-facing error messages must not leak stack traces/internals.
9. Caching `Method` to reduce lookups is fine, **never skip policy checks** just because the Method is cached.
10. For dynamic plugin classes, require allowlists/artifact governance and system-level isolation if code is untrusted.

## 9. Self-Check

- Why must authorization still be checked separately even though `getMethod(...)` returns a public method?
- If a user has the `profile.read` permission, why are they not necessarily authorized for every valid user ID?
- What is the difference between an **action allowlist** and **filtering packages by prefix**?
- Why is calling `Class.forName(untrustedName)` from a request risky even before `Method.invoke(...)`?
- Should you cache `"allowed to invoke this Method"` across all users? Why?
- When plugins run external organization code, is creating a new `ClassLoader` alone sufficient to create a sandbox?

### Official Documentation

- Java SE 21 — `Class` and `Class.forName`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html
- Java SE 21 — `Method` and `Method.invoke`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html
- Java SE 21 — `AccessibleObject`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html
- Java SE 21 — `InaccessibleObjectException`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html
- OWASP Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OWASP Input Validation Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html