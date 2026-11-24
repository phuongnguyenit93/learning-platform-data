# Distinguishing Business Role Names from Authorities in an Application

In a retail system, a user might be called **"Store Manager"**, stored in the database with role code `STORE_MANAGER`, and recognized by Spring Security as `ROLE_STORE_MANAGER`. All three labels are related, yet **they are not three values you can substitute arbitrarily for one another**. Mixing up display labels, business role codes, and the authorities Spring Security actually checks easily leads to "logged in yet getting 403" bugs, over-privileged grants, or missed boundaries between stores.

This lesson focuses on defining what each name means, understanding `GrantedAuthority` and `hasRole`/`hasAuthority`, converting business roles to authorities in a controlled way, and testing that mapping in Spring Security.

## 1. Three naming layers commonly confused

Consider the same person holding a store manager role:

| Layer | Example value | Source and purpose |
| --- | --- | --- |
| **Display label** | `Store Manager` | UI text; can be translated into other languages and rephrased. |
| **Business role code** | `STORE_MANAGER` | Stable concept defined by the business domain; usually resides in enums, role tables, or assignment tables. |
| **Spring GrantedAuthority** | `ROLE_STORE_MANAGER` | Authority string attached to `Authentication` for Spring Security authorization checkers to match. |
| **Action-specific authority** | `ORDER_VIEW`, `ORDER_APPROVE` | Operation permissions the application chooses to grant; not necessarily roles. |

**Display labels are not authorization keys.** Today the UI reads "Store Manager", tomorrow it changes to "Branch Manager" or a localized translation; changing copy must never accidentally alter permissions. Always rely on stable codes, never comparing UI strings such as `hasAuthority("Store Manager")`.

**Business role codes do not automatically become authorities.** A database record `role_code = STORE_MANAGER` is merely application data. Spring Security does not query that table automatically, nor does it implicitly attach `ROLE_` when saving or reading data. The application must decide at authentication time which `GrantedAuthority` instances to translate trusted roles/permissions into.

**Authority is how permissions are represented to Spring Security.** `Authentication.getAuthorities()` returns a collection of `GrantedAuthority` instances; each common authority exposes a string via `getAuthority()`. For instance, both `ROLE_STORE_MANAGER` and `ORDER_APPROVE` can be represented by `SimpleGrantedAuthority`. Spring Security does not infer business meaning from the string `ORDER_APPROVE`; the application must define which actions it permits.

In other words:

~~~text
UI Label ("Store Manager")
       |
       | displays friendly name, grants no permission
       v
Business role (STORE_MANAGER)
       |
       | mapped per application rules, after verifying the user
       v
GrantedAuthority ("ROLE_STORE_MANAGER", "ORDER_VIEW", "ORDER_APPROVE")
       |
       | used by AuthorizationManager / method security
       v
Access decision (ALLOW / DENY)
       |
       + data conditions: store, owner, status, limits...
~~~

The arrow between role and authority is **a mapping that must be designed**, not a law of the framework. Two applications may define the exact same `STORE_MANAGER` role yet grant completely different permissions.

## 2. How `hasRole` and `hasAuthority` differ in matching

In standard Spring Security configuration, roles are represented as authorities prefixed with **`ROLE_`**. Standard checkers follow these conventions:

| Expression | Authority checked under default role prefix | Meaning |
| --- | --- | --- |
| `hasRole("STORE_MANAGER")` | `ROLE_STORE_MANAGER` | Checks role by prefix convention. |
| `hasAuthority("ROLE_STORE_MANAGER")` | `ROLE_STORE_MANAGER` | Checks exact authority string. |
| `hasAuthority("STORE_MANAGER")` | `STORE_MANAGER` | Checks exact string, **does not add** `ROLE_`. |
| `hasAuthority("ORDER_APPROVE")` | `ORDER_APPROVE` | Checks action permission, adds no role prefix. |
| `hasAnyRole("STORE_MANAGER", "SUPPORT")` | One of `ROLE_STORE_MANAGER`, `ROLE_SUPPORT` | Checks multiple roles. |
| `hasAnyAuthority("ORDER_VIEW", "ORDER_APPROVE")` | Either verbatim string | Checks multiple authorities. |

Example where caller has:

~~~text
Authentication.authorities = [
  "ROLE_STORE_MANAGER",
  "ORDER_VIEW",
  "ORDER_APPROVE"
]
~~~

Under default prefix configuration:

- `hasRole("STORE_MANAGER")` → **true**.
- `hasAuthority("ROLE_STORE_MANAGER")` → **true**.
- `hasAuthority("STORE_MANAGER")` → **false**.
- `hasAuthority("ORDER_APPROVE")` → **true**.
- `hasRole("ORDER_APPROVE")` → **false**, because the role check looks for `ROLE_ORDER_APPROVE`, not `ORDER_APPROVE`.

Specifically, do not write `hasRole("ROLE_STORE_MANAGER")` out of a habit of **prepending the prefix to the role argument**. In default APIs, `hasRole` already handles the prefix and may reject an argument already prefixed with `ROLE_`; pass `STORE_MANAGER` to `hasRole`, or pass the full string to `hasAuthority`.

The `ROLE_` rule is a **configurable convention** in some components, for example via `GrantedAuthorityDefaults`. A system that changes the prefix must apply the convention consistently and have tests for both HTTP authorization and method security; never change the prefix merely to work around a data-mapping bug. Clearly separating **role code** (domain) and **role authority** (Spring) prevents cross-cutting breakage when config changes.

Authority strings are compared **exactly**; `STORE_MANAGER`, `store_manager`, and `Store_Manager` are distinct values. If data comes from multiple sources, normalize server-side at a trusted mapping boundary and test abnormal inputs. Never automatically turn arbitrary client-supplied strings into `ROLE_<value>`.

## 3. Business roles stored in the database differ from authentication-time authorities

An illustrative data model:

~~~text
users
  id | username
  17 | alice

business_roles
  code           | display_name_vi
  STORE_MANAGER  | Store Manager
  SALES_ASSISTANT| Sales Assistant

store_role_assignments
  user_id | store_id | role_code
  17      | store-7  | STORE_MANAGER
~~~

The `store_role_assignments` table says **Alice is manager of `store-7`**. It does not mean Alice holds the manager role at every store. If you merely put `ROLE_STORE_MANAGER` into a flat authority set while dropping `store_id`, the application risks treating Alice as manager of `store-9` when an endpoint only checks `hasRole("STORE_MANAGER")`.

A typical flow:

1. The user is authenticated via session, username/password, or a verified token.
2. The server fetches role codes, permissions, and applicable scopes from a trusted datastore/authorization ruleset.
3. A **mapper** translates active codes into `GrantedAuthority` instances, e.g., `STORE_MANAGER` into `ROLE_STORE_MANAGER`, `ORDER_APPROVE` into `ORDER_APPROVE`.
4. Spring Security stores those authorities in `Authentication`, where checkers can consume them.
5. When accessing a **specific record**, the service still checks tenant/store, ownership, status, or conditions that authorities alone cannot express.

When using `UserDetailsService`, the application must return `UserDetails` with mapped authorities. With an OAuth2 Resource Server using JWT, authorities can be produced from the JWT via a custom converter or default configuration; **not every claim named `roles` automatically becomes `ROLE_...`**. The default configuration of `JwtGrantedAuthoritiesConverter` typically maps token scopes to `SCOPE_<scope>` authorities (e.g., `scope=orders.read` becomes `SCOPE_orders.read`), rather than turning them into `ROLE_STORE_MANAGER`.

A role from an external identity system requires an **explicit mapping contract**: which claim holds roles, which issuer/audience is trusted, which values are accepted, which tenant scope the role carries, and whether that role grants corresponding application permissions. Taking an `ADMIN` string from a self-declared request header and creating `ROLE_ADMIN` is an authorization flaw.

## 4. Intentionally mapping role → authority and permission

Suppose the retail domain has two roles:

| Business role | Role authority | Application permissions that may be granted |
| --- | --- | --- |
| `STORE_MANAGER` | `ROLE_STORE_MANAGER` | `ORDER_VIEW`, `ORDER_APPROVE`. |
| `SALES_ASSISTANT` | `ROLE_SALES_ASSISTANT` | `ORDER_VIEW`. |

This is an **illustrative policy**, not a default feature of Spring Security. In real authorization, keep a single source of truth for mapping: controlled configuration, change-managed role-permission tables, or domain policy code. Do not hard-code permissions repeatedly across controllers, services, mappers, and UI where they easily drift apart.

The bridge to Spring Security can use `SimpleGrantedAuthority`:

~~~java
import java.util.HashSet;
import java.util.Set;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public final class BusinessAuthorityMapper {
    public static Set<GrantedAuthority> map(
            Set<String> businessRoleCodes,
            Set<String> grantedPermissions) {
        Set<GrantedAuthority> result = new HashSet<>();

        for (String roleCode : businessRoleCodes) {
            // roleCode must come from a server-managed trusted role set.
            result.add(new SimpleGrantedAuthority("ROLE_" + roleCode));
        }
        for (String permission : grantedPermissions) {
            // Permissions must also be granted from a trusted source.
            result.add(new SimpleGrantedAuthority(permission));
        }
        return Set.copyOf(result);
    }

    private BusinessAuthorityMapper() {}
}
~~~

This is an **illustrative class requiring Spring Security libraries on the classpath**, not a file runnable standalone with `java`. A real application must also reject/normalize invalid codes; in particular, the function above **must never be called with role sets sent by the client**. If the database already stores `ROLE_STORE_MANAGER`, clearly specify whether to strip the prefix before mapping to avoid producing `ROLE_ROLE_STORE_MANAGER`. It is usually easier to govern when **domain role codes omit the `ROLE_` prefix**, and the mapper owns the framework convention.

There are two common ways to grant permissions; choose one consistently:

- **Derived from role:** role `STORE_MANAGER` is defined to grant `ORDER_VIEW` and `ORDER_APPROVE`. At authentication time, the mapper expands the role into permission authorities.
- **Granted individually:** two users share role `STORE_MANAGER`, yet only some are additionally granted `ORDER_APPROVE` after training/approval. The mapper reads effective roles and permissions from separate authorization data.

In either approach, **having a role authority does not implicitly generate permission authorities** unless the application performs the mapping. For example, `hasAuthority("ORDER_APPROVE")` does not become true merely because the caller has `ROLE_STORE_MANAGER`.

Some systems define a **role hierarchy** (e.g., `ROLE_ADMIN` implies `ROLE_STORE_MANAGER`). If using this mechanism, configure it intentionally and test the expansion rules; do not treat hierarchy as a Spring default. Role hierarchy also does not replace record and tenant checks.

## 5. Standalone Java 17+ example: seeing both namespaces clearly

The following program **does not require Spring**; it simulates how business roles are converted into authority strings and how a decision still depends on order data. This lets you inspect the essence of mapping without filter or proxy noise.

Save with exact name **BusinessRoleAuthorityDemo.java**:

~~~java
import java.util.HashSet;
import java.util.Set;

public class BusinessRoleAuthorityDemo {
    enum BusinessRole { STORE_MANAGER, SALES_ASSISTANT }

    record User(String id, String storeId, Set<BusinessRole> businessRoles) {}
    record Order(String storeId, boolean awaitingApproval) {}

    static Set<String> authoritiesFor(Set<BusinessRole> roles) {
        Set<String> result = new HashSet<>();
        for (BusinessRole role : roles) {
            result.add("ROLE_" + role.name());
            switch (role) {
                case STORE_MANAGER -> {
                    result.add("ORDER_VIEW");
                    result.add("ORDER_APPROVE");
                }
                case SALES_ASSISTANT -> result.add("ORDER_VIEW");
            }
        }
        return Set.copyOf(result);
    }

    static boolean hasRole(Set<String> authorities, String role) {
        return authorities.contains("ROLE_" + role);
    }

    static boolean hasAuthority(Set<String> authorities, String authority) {
        return authorities.contains(authority);
    }

    static boolean canApprove(User user, Order order) {
        Set<String> authorities = authoritiesFor(user.businessRoles());
        return authorities.contains("ORDER_APPROVE")
                && user.storeId().equals(order.storeId())
                && order.awaitingApproval();
    }

    public static void main(String[] args) {
        User manager = new User("u17", "store-7",
                Set.of(BusinessRole.STORE_MANAGER));
        User assistant = new User("u28", "store-7",
                Set.of(BusinessRole.SALES_ASSISTANT));
        Set<String> managerAuthorities =
                authoritiesFor(manager.businessRoles());
        Set<String> assistantAuthorities =
                authoritiesFor(assistant.businessRoles());

        System.out.println("Business role: "
                + BusinessRole.STORE_MANAGER.name());
        System.out.println("Role authority: "
                + hasRole(managerAuthorities, "STORE_MANAGER"));
        System.out.println("Raw role name as authority: "
                + hasAuthority(managerAuthorities, "STORE_MANAGER"));
        System.out.println("Manager approve permission: "
                + hasAuthority(managerAuthorities, "ORDER_APPROVE"));
        System.out.println("Assistant approve permission: "
                + hasAuthority(assistantAuthorities, "ORDER_APPROVE"));
        System.out.println("Same-store pending order: "
                + canApprove(manager, new Order("store-7", true)));
        System.out.println("Other-store pending order: "
                + canApprove(manager, new Order("store-9", true)));
        System.out.println("Same-store completed order: "
                + canApprove(manager, new Order("store-7", false)));
    }
}
~~~

Compile and run on JDK 17 or higher:

~~~bash
javac BusinessRoleAuthorityDemo.java
java BusinessRoleAuthorityDemo
~~~

Exact output:

~~~text
Business role: STORE_MANAGER
Role authority: true
Raw role name as authority: false
Manager approve permission: true
Assistant approve permission: false
Same-store pending order: true
Other-store pending order: false
Same-store completed order: false
~~~

**Explanation of each key point:**

- `BusinessRole.STORE_MANAGER.name()` returns **`STORE_MANAGER`**, the unprefixed business code.
- The mapper prepends `ROLE_` to create **`ROLE_STORE_MANAGER`**; hence `hasRole(..., "STORE_MANAGER")` returns true.
- `hasAuthority(..., "STORE_MANAGER")` returns false because the authority set **does not contain the verbatim string** `STORE_MANAGER`.
- `ORDER_APPROVE` is an **action** authority, granted only due to the example's explicit permission assignment rule.
- Having `ORDER_APPROVE` is still insufficient to approve every order. `canApprove` requires matching `storeId` and an order awaiting approval. The last two outputs are false even though the manager still holds the exact same authorities.

In this program, the role set was constructed manually for illustration. In real deployments, roles must come from verified assignments; the caller's `storeId` must be tied to a trusted context, and order status must be loaded from fresh data. Never take roles/authorities from a payload and treat them as granted.

## 6. Using in Spring Security: checking the right name type

### HTTP layer

This is a **configuration snippet placed inside a Spring Boot application with the Spring Security dependency**, not a standalone program (add imports for `@Configuration`, `@Bean`, `HttpSecurity`, `SecurityFilterChain`):

~~~java
@Configuration
class WebAuthorizationConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/backoffice/**").hasRole("STORE_MANAGER")
            .requestMatchers("/api/orders/**").authenticated()
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
~~~

`hasRole("STORE_MANAGER")` looks for **`ROLE_STORE_MANAGER`** under the default prefix. If the authenticator produces an unprefixed `STORE_MANAGER` authority, a legitimate manager will still be denied on this branch. Putting `hasAuthority("STORE_MANAGER")` by mistake when `ROLE_STORE_MANAGER` is actually produced also fails to match.

Conversely, `authenticated()` for `/api/orders/**` only requires an authenticated user; it **does not check edit rights, ownership, or store**. On an API serving multi-store data, the business layer must check `order.storeId` against the caller's verified scope.

### Method layer

You can enable `@EnableMethodSecurity` in configuration and apply an expression:

~~~java
@PreAuthorize("hasRole('STORE_MANAGER') and hasAuthority('ORDER_APPROVE')")
public void approveOrder(long orderId) {
    // Service loads the order from the server and checks storeId, status,
    // assignee, and other business rules.
}
~~~

This is an **illustrative method** inside a Spring bean, not a standalone runnable class. `@PreAuthorize` only checks roles and permissions present in `Authentication`. The comment must be replaced with real enforcement logic against the actual record; omitting that check lets one store's manager attempt to approve another store's order.

Distinguish two business contracts:

- If **having permission `ORDER_APPROVE` is sufficient functionally**, use `hasAuthority('ORDER_APPROVE')` and evaluate order data; do not force an extra role check if the application may legitimately grant that permission to a new role.
- If **both being a store manager and holding approval permission are mandatory**, use the combined expression above. When organizational models change, update and test the contract before changing annotations.

Method security in Spring relies on AOP proxies. Internal calls from one method to another on the **same instance** can bypass the interceptor. Therefore, data invariants (tenant, owner, status) must be enforced consistently at the service/policy layer and inside update transactions, rather than relying solely on controller annotations.

### When the mapper constructs `GrantedAuthority` objects

Once you have a verified set of roles and permissions, creating:

~~~java
new SimpleGrantedAuthority("ROLE_STORE_MANAGER")
new SimpleGrantedAuthority("ORDER_APPROVE")
~~~

corresponds to two **distinct** authorities. `hasRole` uses the first authority; `hasAuthority("ORDER_APPROVE")` uses the second. Do not confuse the `hasRole("STORE_MANAGER")` argument with the `SimpleGrantedAuthority` constructor syntax: the constructor takes the **entire authority string**, without adding `ROLE_` itself.

## 7. Comparing identity sources and how the framework builds authorities

Authority names in an application depend on **how you construct `Authentication`**, not merely on database column names.

| Source | Source value | Authority visible in Spring | What to verify |
| --- | --- | --- | --- |
| Internal DB role | `STORE_MANAGER` | `ROLE_STORE_MANAGER` if mapper prepends prefix | Is there a trusted mapper and role source? |
| Database permission | `ORDER_APPROVE` | `ORDER_APPROVE` if mapper builds exact value | Who grants the permission; does it have expiry/scope? |
| `UserDetails` | `GrantedAuthority` list returned by app | Exact strings created | Was `roles(...)` or `authorities(...)` used when building user? |
| Default JWT scope | `orders.read` in `scope`/`scp` | Usually `SCOPE_orders.read` | Is there a custom converter? Is a scope a business permission? |
| Custom JWT role claim | `roles: ["STORE_MANAGER"]` | Only produces role authority if app **maps** that claim | Is issuer trusted, converter accurate, which tenant applies? |

In Spring Security builders, `roles("STORE_MANAGER")` (under defaults) creates an authority with `ROLE_`; `authorities("STORE_MANAGER")` represents the verbatim string and does not treat it as a role. When mocking in tests, `@WithMockUser(roles = "STORE_MANAGER")` creates `ROLE_STORE_MANAGER`; `@WithMockUser(authorities = "STORE_MANAGER")` creates `STORE_MANAGER`. This causes many "tests pass yet production returns 403" incidents when test fixtures and production mappers disagree.

With JWTs, a token having `scope=orders.read` **does not mean** it has `ROLE_STORE_MANAGER`. Using `hasAuthority('SCOPE_orders.read')` can be right when the authority source is verified scopes and the API is designed around that scope. If policy relies on business roles, define a dedicated role converter/source and check tenant scope.

A person may hold different roles across different organizations. Two common implementation patterns are: select the active organization from verified context and build authorities effective for that scope; or keep per-organization role assignments and evaluate membership when accessing each resource. Either way, **flat role authorities do not encode data scope automatically**.

## 8. Why does 403 appear even when the database has the role?

Consider a concrete investigation:

1. Database shows `role_code = STORE_MANAGER`.
2. User logs in successfully.
3. Endpoint checks `hasRole('STORE_MANAGER')`.
4. API returns 403.

Do not immediately remove `hasRole` or add `permitAll`. Verify step by step:

| What to inspect | Correct example | Common mismatch |
| --- | --- | --- |
| Was the business role granted to the **right person and right scope**? | `user=17, store=store-7, role=STORE_MANAGER` | Role belongs to another store or assignment expired. |
| Did the mapper read the valid role? | Reads `STORE_MANAGER` from trusted source | Mapper skips role or queries wrong table. |
| What is currently in `Authentication.getAuthorities()`? | `ROLE_STORE_MANAGER` | Only `STORE_MANAGER`, `SCOPE_...`, or empty set. |
| What is the condition checking? | `hasRole('STORE_MANAGER')` | `hasAuthority('STORE_MANAGER')` when only `ROLE_STORE_MANAGER` exists. |
| Is the data scope valid? | User belongs to the order's store | Right role but different tenant or forbidden status. |
| Did permissions change after login? | Permissions in session/token remain valid | Role added but old session not updated, or revoked while old token still active. |

An authority can be attached to `Authentication` at authentication time and persist until the session refreshes or the token expires. If permissions change frequently or must be revoked immediately, design permission refresh, request-time lookup, or appropriate session/token mechanisms. Never "fix" permission caching issues by accepting arbitrary roles sent by the frontend.

When logging to aid debugging, log only necessary permission/scope codes, verified user, and denial reason at an appropriate level. Never print passwords, access tokens, cookies, or sensitive claims. API responses must also avoid accidentally disclosing another tenant's records just because the caller holds the right role.

## 9. Common design mistakes

1. **Using UI labels as security keys.** Changing "Store Manager" in a translation breaks role checks. → Use stable domain codes; labels are for display only.
2. **Assuming the database grants permissions to Spring automatically.** Role exists in table yet `Authentication.getAuthorities()` lacks the matching role. → Define and test the mapper.
3. **Prepending `ROLE_` in both data and mapper.** Produces `ROLE_ROLE_STORE_MANAGER`. → Standardize one source-data convention and one conversion point.
4. **Confusing `hasRole` with `hasAuthority`.** `hasAuthority('STORE_MANAGER')` does not match `ROLE_STORE_MANAGER`. → Compare against actual authority strings.
5. **Equating roles with permissions.** `ROLE_STORE_MANAGER` does not mean `ORDER_APPROVE` if the system has not defined that grant relationship. → Map permissions intentionally.
6. **Using a global role across every tenant.** A manager in store-7 accidentally manages store-9. → Enforce store/tenant scope at the data layer.
7. **Trusting client-entered roles/scopes.** Allows privilege escalation via body/header. → Only use verified identities/claims and permissions from trusted server sources.
8. **Over-relying on `@PreAuthorize`.** An internal call bypasses the proxy or an operation skips record state checks. → Keep invariants in services/policies and test multiple entry paths.
9. **Testing with roles built differently from production.** Tests pass while real users get 403. → Reuse mapping rules or assert production authority sets.
10. **Relying on stale authority snapshots.** Permission revoked while token remains valid. → Consider session/token lifetimes and revocation mechanisms when risk requires.

## 10. Testing namespace and scope properly

Write tests at **two layers**: (a) the mapper converting business roles into authorities, and (b) policies using authorities alongside resource constraints.

Basic case table:

| Input or context | Check | Expected |
| --- | --- | --- |
| Business role `STORE_MANAGER` | Mapper produces `ROLE_STORE_MANAGER` | Yes. |
| Business role `STORE_MANAGER` | Mapper produces unprefixed `STORE_MANAGER` | No, unless intentionally granted separately. |
| `ROLE_STORE_MANAGER` in Authentication | `hasRole('STORE_MANAGER')` | ALLOW at role layer. |
| Only `STORE_MANAGER` | `hasRole('STORE_MANAGER')` | DENY by default. |
| Only `ROLE_STORE_MANAGER` | `hasAuthority('STORE_MANAGER')` | DENY. |
| Has `ORDER_VIEW` but lacks `ORDER_APPROVE` | Approval permission | DENY. |
| Has `ROLE_STORE_MANAGER` and `ORDER_APPROVE`, same store | Order awaiting approval | May ALLOW if all business conditions hold. |
| Same authorities but order in different store | Approve other store's order | DENY. |
| JWT with only `SCOPE_orders.read` | `hasRole('STORE_MANAGER')` | DENY unless role authority is also mapped. |
| Mock user with `roles = "STORE_MANAGER"` | Authority set | Must contain `ROLE_STORE_MANAGER`. |
| Mock user with `authorities = "STORE_MANAGER"` | Authority set | Contains only declared `STORE_MANAGER`. |

In Spring Security Test, `@WithMockUser` is convenient for testing `hasRole`/`hasAuthority`; for a JWT resource server, test the security context/converter against actual token configuration. Unit-testing the mapper catches bugs that turn `STORE_MANAGER` into `ROLE_ROLE_STORE_MANAGER` or drop permissions. Integration tests must verify 403 responses when unauthorized and tenant isolation even when the role is valid.

One key test case is **renaming the display label**: update `display_name_vi` from "Store Manager" to "Shop Manager" in UI data, while verifying code `STORE_MANAGER`, authority `ROLE_STORE_MANAGER`, and check results **remain unchanged**. This case proves display names do not govern security logic.

## 11. Reliable naming and mapping workflow

For a new role, such as "Reconciliation Staff", follow this workflow:

1. Define a **stable business code** such as `RECONCILIATION_STAFF` and an independent localized display label.
2. Clearly specify the scope at which the role is granted: system-wide, tenant, store, or project.
3. Define the permissions actually needed, e.g., `RECONCILIATION_READ`; do not grant approval or export permissions by default.
4. In a controlled mapper, convert the role into `ROLE_RECONCILIATION_STAFF` and permissions into verbatim authorities.
5. Configure `hasRole('RECONCILIATION_STAFF')` when the **role group** is the business condition; `hasAuthority('RECONCILIATION_READ')` when checking the **action**.
6. Enforce resource constraints on the server, including tenant scope, assignments, status, and any further approval requirements.
7. Test ALLOW and DENY cases across mapper, method/HTTP, and data layers. Document how permissions are refreshed when assignments change.

**Key point to remember:** A business role names a responsibility in the domain; `GrantedAuthority` is the concrete permission representation passed into Spring Security. The `ROLE_` prefix serves the role-checking convention—it does not automatically turn a display label or database row into a permission. Designing **role code → mapper → authority → policy + resource conditions** cleanly makes UI label changes safe, keeps 403 debugging accurate, and prevents cross-scope privilege leaks.

### References

- [Spring Security – Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
