# AuthenticationUserDetailsService and Mapping CAS Attributes to Authorities in Spring Security

**Problem:** When an application uses Central Authentication Service (CAS) for single sign-on, the CAS Server authenticates the user and can return **principal attributes**—such as employee ID, department, groups, or affiliation—in the Service Ticket validation response. However, the Spring Security application still needs to decide **which local user** is logging in and which **`GrantedAuthority`** values they receive. **`AuthenticationUserDetailsService`** is an appropriate integration point for bringing CAS authentication results into the application's account and authorization model.

**Core principle:** Convert attributes only from a **CAS assertion verified by `TicketValidator`**, then apply **application-managed policies** scoped by CAS context/service, local account, and tenant. Never pass every CAS group value straight through as `ROLE_ADMIN` or a business permission. **Successful CAS login does not mean permission to view or modify every resource in the application.**

This article belongs to **Spring Security – Federation -> CAS Integration**, covering the difference between `UserDetailsService` and `AuthenticationUserDetailsService`, `Assertion` data, how Spring Security CAS invokes the service, helper classes for building authorities, safe mapping patterns, a standalone Java 17 example, integration code, error handling, testing, and operations.

## 1. Authentication and Authorization in a CAS-Enabled Application

CAS solves authentication: the logged-in user has been verified by the CAS Server per CAS policy. After the CAS Service Ticket (ST) is validated, Spring Security builds an `Authentication` object; the application must still determine account status, roles, tenant membership, and resource access permissions.

~~~text
Browser -> SP Portal -> CAS /login
                         |
                    CAS authenticates
                         |
                   CAS issues ST for Portal
                         |
Browser -> Portal /login/cas?ticket=ST-...
                         |
                 CasAuthenticationFilter
                         |
                CasAuthenticationProvider
                         |
               TicketValidator calls CAS
              /serviceValidate with service
                         |
                   CAS Assertion
                 principal + attributes
                         |
       AuthenticationUserDetailsService
         local account lookup + policy
                         |
           UserDetails + GrantedAuthority
                         |
          CasAuthenticationToken / SecurityContext
                         |
       AuthorizationFilter / @PreAuthorize
               + domain/tenant policy
~~~

Trust boundaries:

- **CAS Server:** verifies credentials or SSO session; issues an ST bound to a service.
- **TicketValidator:** validates the ST with the CAS Server over HTTPS with the right service and protocol.
- **CAS Assertion:** contains the authenticated principal and any released attributes.
- **AuthenticationUserDetailsService:** looks up the user profile or builds `UserDetails` from an `Authentication` token carrying the assertion.
- **Authorization:** decides how authorities apply to endpoints, methods, and objects; domain policies may require additional backend data.

Never map authorities by reading the `ticket` query parameter and guessing the user. An ST is a short-lived, single-use bearer credential; it must be validated.

## 2. Components in Spring Security CAS

| Component | Role |
| --- | --- |
| **CasAuthenticationEntryPoint** | Redirects the browser to the CAS login page and passes the service URL |
| **ServiceProperties** | Defines the application's service callback, e.g., `https://portal.example.test/login/cas` |
| **CasAuthenticationFilter** | Receives the ST at the callback and passes it to `AuthenticationManager` |
| **CasAuthenticationProvider** | Invokes `TicketValidator`, validates the ticket, and builds the authenticated `Authentication` |
| **TicketValidator** | Calls the CAS server validation endpoint; verifies the ST matches the service |
| **CasAssertionAuthenticationToken** | Intermediate token holding the `Assertion` processed by the CAS provider, passed to the user details loader |
| **AuthenticationUserDetailsService<T>** | Looks up or constructs `UserDetails` from an `Authentication` token `T` |
| **UserDetailsService** | Looks up `UserDetails` by a username string |
| **UserDetailsByNameServiceWrapper** | Adapter that delegates by username to a `UserDetailsService` |
| **GrantedAuthorityFromAssertionAttributesUserDetailsService** | Built-in class that converts values of specified CAS attributes into authorities |
| **GrantedAuthoritiesMapper** | Can transform the authority set before storing `Authentication` |
| **UserDetailsChecker** | Checks `UserDetails` status per provider configuration |
| **SimpleGrantedAuthority** | Common implementation for string-named authorities |

Spring Security CAS uses the **spring-security-cas** module and Apereo CAS Client. It is not an automatic part of `saml2Login` or `oauth2Login`. CAS, SAML2, and OIDC all share the `GrantedAuthority` concept, yet **their message validation and identity attribute parsing are completely different**.

## 3. How Does `AuthenticationUserDetailsService` Differ from `UserDetailsService`?

**UserDetailsService** defines the contract:

~~~java
UserDetails loadUserByUsername(String username);
~~~

It fits when only a username is needed to look up a local account and roles. **UserDetailsByNameServiceWrapper** can wrap a `UserDetailsService` as an `AuthenticationUserDetailsService` for the CAS provider to invoke.

**AuthenticationUserDetailsService<T extends Authentication>** defines the contract:

~~~java
UserDetails loadUserDetails(T token);
~~~

In CAS integration, the token type is typically **CasAssertionAuthenticationToken**; it exposes the **CAS Assertion** and its attributes, not just the username.

| Need | Appropriate Approach |
| --- | --- |
| CAS returns only username; local DB holds all roles | `UserDetailsService` + `UserDetailsByNameServiceWrapper` |
| Must read groups/departments from CAS assertion | `AuthenticationUserDetailsService<CasAssertionAuthenticationToken>` |
| Must check tenant, account status, and mapping allowlist | Custom `AuthenticationUserDetailsService` or application-controlled policy service |
| CAS releases standardized role strings trusted by admins | May consider `GrantedAuthorityFromAssertionAttributesUserDetailsService` after risk assessment |
| Need global post-processing authority mapping | `GrantedAuthoritiesMapper`, though it does not replace attribute scope/origin checks |
| Need up-to-date entitlements on every request | Domain authorization/database policy, not only login-time `UserDetails` snapshots |

**Do not treat `UserDetailsService` as a place to re-verify a CAS password.** The CAS provider uses `TicketValidator` to verify the ST. `UserDetails` returns account metadata and authorities; local passwords are not used to verify STs.

## 4. `CasAssertionAuthenticationToken` and CAS Assertion Data

After the CAS Server validates a Service Ticket, the CAS client receives an **org.apereo.cas.client.validation.Assertion**. Spring Security uses **CasAssertionAuthenticationToken** as the intermediate object when loading `UserDetails`.

Example API usage **inside a custom loader**:

~~~java
@Override
public UserDetails loadUserDetails(
        CasAssertionAuthenticationToken token) {
    org.apereo.cas.client.validation.Assertion assertion =
            token.getAssertion();

    String casSubject = assertion.getPrincipal().getName();
    Map<String, Object> attributes =
            assertion.getPrincipal().getAttributes();

    // Use casSubject + attributes in the SP's policy service.
    // Return UserDetails constructed by the app from the local account.
}
~~~

This is a **code snippet**, not an independently compilable method; it requires a class implementing the interface, imports, and returning `UserDetails`. Never construct a **CasAssertionAuthenticationToken** from HTTP query parameters in a controller and pretend it was validated.

Distinguish three values:

1. **Ticket ST:** bearer string the browser passes to the application callback.
2. **Assertion principal name:** ID confirmed by CAS, retrieved via `getPrincipal().getName()`.
3. **Assertion principal attributes:** `Map<String,Object>` supplied by CAS per its attribute release policy.

**`Map<String,Object>` does not guarantee every value is a `String`.** A group attribute can be a `String`, `Collection<?>`, or another structure depending on CAS client/server and validation protocol. Parse data strictly according to the contract.

## 5. Authorization Flow After Service Ticket Validation

Suppose CAS has verified a user with subject **`user-104`** and released groups **`portal-readers`** and **`finance-reviewers`**.

~~~text
CAS Server
  ST issued for service Portal
        |
        v
CAS /p3/serviceValidate (or matching endpoint)
  authenticationSuccess:
    user = user-104
    attributes:
      memberOf = [portal-readers, finance-reviewers]
        |
        v
TicketValidator -> verified Assertion
        |
        v
AuthenticationUserDetailsService
  1. Identify configured CAS trust context
  2. Map CAS subject to local account
  3. Reject disabled/suspended accounts
  4. Verify tenant membership
  5. Parse memberOf per CAS contract
  6. Map allowlisted groups -> local roles
  7. Combine with local entitlements per policy
        |
        v
UserDetails:
  username = local-account-57
  authorities = [
    ROLE_AUTHENTICATED,
    ROLE_VIEWER,
    ROLE_APPROVER
  ]
        |
        v
Spring Security authorization + object checks
~~~

**Important:** The case above is valid only when CAS server/service policy permits releasing those attributes, the ST was validated for the right service, and the user is linked to the local account in the right tenant. If CAS returns only a username without groups, the custom loader needs an explicit policy: baseline access or denial where privileged roles are required.

Never use email or display name as the sole account-linking key across multiple CAS servers, brokers, or tenants.

## 6. CAS Attribute Resolution and Attribute Release Are Two Separate Steps

Apereo CAS separates two stages:

- **Attribute Resolution:** CAS fetches principal attributes from LDAP, a database, a directory, or another source and attaches them to the principal.
- **Attribute Release:** CAS decides which attributes may be returned to a **specific service** in the validation response.

A CAS Server may know a user's groups, yet **Portal sees none of them** if the service registry has not authorized release. That can be intentional for data minimization.

| Stage | Question to Check |
| --- | --- |
| CAS authentication | Under which policy was the user authenticated? |
| Principal resolution | Which attributes did CAS resolve? |
| Service registry | Is Portal permitted to receive the `memberOf` attribute? |
| Attribute release policy | Which values are filtered/released to Portal? |
| Service validation endpoint | Is the client calling a CAS protocol endpoint that supports attributes? |
| CAS assertion | Does `getPrincipal().getAttributes()` have the expected types/values? |
| Application mapping | Which authorities may be derived from CAS groups? |

A CAS 3.x setup can return attributes via **`/p3/serviceValidate`**, and some validation implementations support attributes in specific formats. If the client uses a validator/version that reads only the username, the mapper will see empty attributes. **Never invent a high-privilege default group as a workaround for missing attributes.**

**Distinguish CAS principal attributes from authentication attributes:** authentication metadata describes the login event, handler, timestamp, or assurance; principal attributes typically include group, department, and email. Never feed an authentication attribute that happens to share a group-like name into permission mapping if the contract covers only principal attributes.

## 7. What Does an XML Validation Response Containing Attributes Look Like?

Extended CAS 3.x structural example illustrating multi-valued attributes:

~~~xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>user-104</cas:user>
    <cas:attributes>
      <cas:memberOf>portal-readers</cas:memberOf>
      <cas:memberOf>finance-reviewers</cas:memberOf>
      <cas:department>finance</cas:department>
    </cas:attributes>
  </cas:authenticationSuccess>
</cas:serviceResponse>
~~~

This is an **illustrative template**, not a live CAS response and not guaranteed to match the serialization format of every version. The names **`memberOf`** and **`department`** are defined for this example; an actual contract must specify attribute names, types, casing, multi-value representation, and release policies.

**Do not parse XML with custom regex or XPath** in a Spring application when the CAS client validator already handles it; use the `Assertion` returned by the library after validation. If custom XML parsing is ever unavoidable, preserve parser/XML schema protections, TLS, service matching, and single-use ticket semantics.

For multi-valued data, never arbitrarily grab just the first element and drop the rest. Conversely, never take every key in the map and treat it as a role.

## 8. How Dangerous Is Granting Permissions Directly from CAS Attributes?

Suppose CAS returns:

~~~text
memberOf = [
  "portal-readers",
  "ROLE_ADMIN",
  "finance-reviewers"
]
~~~

A flawed implementation:

~~~java
// DO NOT USE:
List<GrantedAuthority> authorities = rawGroups.stream()
    .map(group -> new SimpleGrantedAuthority(group.toString()))
    .toList();
~~~

If a value from a directory/LDAP modifiable by a user or partner is named **`ROLE_ADMIN`**, it turns directly into a real application authority. Other failure modes:

- IdP/CAS A and CAS B both have an **`admins`** group, yet only A is authorized to grant an administrative role.
- A user belongs to **`finance-reviewers`** in tenant X, not in tenant Y.
- A CAS group uses a mutable display name; substring matching on `"admin"` grants the wrong role.
- Group attributes are partially released or mis-typed, and the app falls back to an overly privileged role.
- One user shares an email with another user in a different CAS context and gets linked to the wrong local account.

**Solution:** application-owned allowlists, source binding, account status, tenant membership, and object-level authorization.

## 9. Built-In Helper: `GrantedAuthorityFromAssertionAttributesUserDetailsService`

Spring Security provides **`org.springframework.security.cas.userdetails.GrantedAuthorityFromAssertionAttributesUserDetailsService`**:

~~~java
// API configuration snippet, not a complete Spring bean setup:
GrantedAuthorityFromAssertionAttributesUserDetailsService loader =
    new GrantedAuthorityFromAssertionAttributesUserDetailsService(
        new String[] { "memberOf" });

loader.setConvertToUpperCase(false);
casProvider.setAuthenticationUserDetailsService(loader);
~~~

This class implements **`AuthenticationUserDetailsService<CasAssertionAuthenticationToken>`**. Per its Javadoc, it reads the specified attributes and turns **each value** of those attributes into a `GrantedAuthority`. An option exists to convert values to uppercase.

### When Can It Be Used?

Consider it only when all of the following conditions hold:

1. The CAS Server is trusted and the ST was validated for the exact service.
2. The specified attribute is released specifically for **this application** and carries true role semantics, not generic groups.
3. CAS **already scopes/transforms** the values accurately into the SP's authority namespace.
4. There are no tenant/source collisions or app-specific conditions that a direct mapper cannot express.
5. Users cannot edit the attribute values themselves, and groups cannot originate from unapproved sources.
6. Tests cover role injection, unexpected values, and revocation procedures.

**`setConvertToUpperCase` is not a security control.** It only changes letter casing; it does not turn a group into an allowlist, resolve IdP/tenant scoping, or prove that a value is a valid permission.

### When Should It Not Be Used Directly?

If CAS returns general LDAP groups, display names, tenant groups, or data from multiple upstream providers, a **1-to-1 conversion to `GrantedAuthority`** can over-privilege users. Use a custom `AuthenticationUserDetailsService` and an application-controlled policy instead.

In particular, **never configure this class with uncertain attribute names**, such as broad department/email fields or user-editable attributes.

## 10. Designing a Safe Mapping Policy

A mapping should bind at minimum:

| Element | Example | Who Manages It? |
| --- | --- | --- |
| CAS trust context | **corp-cas** | SP/operations, never read from query params |
| Service identity | **https://portal.example.test/login/cas** | CAS service registry and SP config |
| CAS principal ID | **user-104** | CAS after ticket validation |
| Local account | **acct-57** | SP database, trusted linking |
| Tenant scope | **north** | SP membership check |
| CAS attribute | **memberOf** | Contract with CAS admin |
| Group value | **finance-reviewers** | CAS directory group ID |
| Internal authority | **ROLE_APPROVER** | SP policy owner |
| Additional requirements | active account, MFA/assurance if needed, resource ownership | SP + CAS policy |

Example:

| CAS Context / Tenant | `memberOf` Value | Permitted Authority |
| --- | --- | --- |
| corp-cas / north | portal-readers | ROLE_VIEWER |
| corp-cas / north | finance-reviewers | ROLE_APPROVER |
| partner-cas / north | partner-readers | ROLE_VIEWER |
| corp-cas / south | finance-reviewers | No mapping, not granted |
| partner-cas / north | finance-reviewers | No mapping, not granted |
| Any | ROLE_ADMIN | Never granted from raw group name alone |

**Why exact mapping?** A group named `finance-reviewers` does not automatically equal a role in another tenant. Every permission must be explicitly named and conditioned by the domain owner. If administrative privileges are required, enforce a dedicated policy with approvers, MFA, and database-backed account entitlements.

## 11. Multi-Type CAS Attributes: Parse Carefully

**`Map<String,Object>`** may contain:

- A `String`: **`portal-readers`**.
- A `List` or `Collection`: **`[portal-readers, finance-reviewers]`**.
- An array of values or another serializer format depending on the client.
- `null` or an unreleased attribute.
- An unexpected type, such as a number, XML object, `Map`, or nested collection.
- Unusually long strings or an excessive number of groups.

A defensive policy should:

1. Read only **agreed attribute names** (e.g., `memberOf`).
2. Define **accepted value types** per CAS validator/version; never blindly call `toString()` on arbitrary objects.
3. For multiple values, verify each element is a valid `String` and deduplicate.
4. Enforce size and count limits; reject oversized payloads to protect performance.
5. Match exact group IDs, not broad regexes or substring checks.
6. Grant only authorities present in the allowlist for the **exact CAS context/tenant**.
7. Never grant sensitive permissions if the attribute is missing or malformed; if the attribute is mandatory for login itself, fail cleanly.
8. Never silently treat empty strings, whitespace, or differing letter case as the same group unless the policy explicitly states so.
9. Never split a string **`a,b,c`** into three groups unless the CAS contract explicitly specifies a serialized comma-delimited list.
10. For LDAP DN groups, map by approved canonical ID/DN rather than extracting `CN` and trusting any group with a matching `CN`.

**Fail closed** means sensitive permissions are denied without sufficient proof—it does not necessarily require blocking users from public informational pages.

## 12. Standalone Java 17: Mapping Groups to Roles via Allowlist

The example below **runs on JDK 17+** using only the standard library. It simulates policy enforcement after the CAS ticket has already been verified and does not handle the CAS protocol itself. Context and tenant are assumed to be determined server-side.

Create file **CasAuthorityPolicyDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

public class CasAuthorityPolicyDemo {

    record Scope(String casContext, String tenant) {}

    private static final Map<Scope, Map<String, String>> ALLOWED =
            Map.of(
                new Scope("corp-cas", "north"),
                    Map.of("portal-readers", "ROLE_VIEWER",
                           "finance-reviewers", "ROLE_APPROVER"),
                new Scope("partner-cas", "north"),
                    Map.of("partner-readers", "ROLE_VIEWER")
            );

    static Set<String> authorities(
            String casContext, String tenant, Object rawGroups) {

        Map<String, String> mapping =
                ALLOWED.get(new Scope(casContext, tenant));

        if (mapping == null || rawGroups == null) {
            return Set.of();
        }

        Collection<?> values;
        if (rawGroups instanceof String string) {
            values = List.of(string);
        } else if (rawGroups instanceof Collection<?> collection) {
            values = new ArrayList<>(collection);
        } else {
            throw new IllegalArgumentException("Unsupported groups type");
        }

        TreeSet<String> result = new TreeSet<>();
        for (Object value : values) {
            if (!(value instanceof String group)) {
                throw new IllegalArgumentException("Unsupported group value");
            }
            String role = mapping.get(group);
            if (role != null) {
                result.add(role);
            }
        }
        return result;
    }

    public static void main(String[] args) {
        System.out.println("corp/north: " + authorities(
            "corp-cas", "north",
            List.of("portal-readers", "finance-reviewers",
                    "ROLE_ADMIN", "portal-readers")));

        System.out.println("partner/north: " + authorities(
            "partner-cas", "north",
            List.of("finance-reviewers")));

        System.out.println("corp/south: " + authorities(
            "corp-cas", "south",
            List.of("finance-reviewers")));

        System.out.println("single value: " + authorities(
            "partner-cas", "north", "partner-readers"));

        try {
            authorities("corp-cas", "north",
                List.of("portal-readers", 7));
        } catch (IllegalArgumentException error) {
            System.out.println("bad type: REJECT");
        }
    }
}
~~~

Compile and run:

~~~bash
javac CasAuthorityPolicyDemo.java
java CasAuthorityPolicyDemo
~~~

**Exact stdout:**

~~~text
corp/north: [ROLE_APPROVER, ROLE_VIEWER]
partner/north: []
corp/south: []
single value: [ROLE_VIEWER]
bad type: REJECT
~~~

### Explaining Each Case

- `corp/north` has two approved groups and receives `ROLE_APPROVER` and `ROLE_VIEWER`. `ROLE_ADMIN` is ignored and duplicate groups are deduplicated.
- `partner/north` cannot use `corp-cas`'s `finance-reviewers`, so no corp authority is granted.
- `corp/south` has no policy, so it cannot gain `north` permissions.
- A single `String` value is also handled per contract.
- A numeric element in the list causes the mapper to reject rather than calling `toString()` and pretending it is a valid group.

**Clear limitations:** this program only tests the group-mapping function; it does not connect to CAS, validate an ST, authenticate a principal, verify tenant membership in a database, or construct Spring `GrantedAuthority` objects. In production, **`casContext` and `tenant` must come from server-verified configuration/accounts**, never directly from HTTP query parameters or headers. Never use this function as a CAS `TicketValidator`.

## 13. Custom `AuthenticationUserDetailsService` in a Spring Project

The following sample targets **Spring Security 6.x/7.x with the CAS module and Java 17+**, using published APIs: **`CasAssertionAuthenticationToken.getAssertion()`**, **`Assertion.getPrincipal().getAttributes()`**, and **`AuthenticationUserDetailsService.loadUserDetails()`**.

File **src/main/java/com/example/security/ScopedCasUserDetailsService.java**:

~~~java
package com.example.security;

import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.cas.authentication.CasAssertionAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.AuthenticationUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UsernameNotFoundException;

public final class ScopedCasUserDetailsService
        implements AuthenticationUserDetailsService<CasAssertionAuthenticationToken> {

    public interface AccountDirectory {
        LocalAccount findByCasIdentity(String context, String subject);
    }

    public record LocalAccount(
            String localId, String tenant, boolean active) {}

    private final AccountDirectory accounts;

    // This is a SERVER-designated CAS context for this provider,
    // never taken from browser query params or attributes.
    private static final String CAS_CONTEXT = "corp-cas";

    private static final Map<String, Map<String, String>> RULES =
            Map.of("north",
                Map.of("portal-readers", "ROLE_VIEWER",
                       "finance-reviewers", "ROLE_APPROVER"));

    public ScopedCasUserDetailsService(AccountDirectory accounts) {
        this.accounts = accounts;
    }

    @Override
    public UserDetails loadUserDetails(CasAssertionAuthenticationToken token) {
        if (token == null || token.getAssertion() == null
                || token.getAssertion().getPrincipal() == null) {
            throw new BadCredentialsException("Missing verified CAS assertion");
        }

        String subject = token.getAssertion().getPrincipal().getName();
        if (subject == null || subject.isBlank()) {
            throw new BadCredentialsException("Missing CAS subject");
        }

        LocalAccount local = accounts.findByCasIdentity(CAS_CONTEXT, subject);
        if (local == null) {
            throw new UsernameNotFoundException(
                    "No linked local account for CAS subject");
        }
        if (!local.active()) {
            throw new DisabledException("Local account is disabled");
        }

        Map<String, Object> attributes =
                token.getAssertion().getPrincipal().getAttributes();

        // Fixed baseline authority, NOT an administrative permission.
        Set<String> roles = new TreeSet<>();
        roles.add("ROLE_AUTHENTICATED");

        Map<String, String> allowed = RULES.get(local.tenant());
        if (allowed != null && attributes != null) {
            Object raw = attributes.get("memberOf");
            Collection<?> groups;
            if (raw == null) {
                groups = List.of();
            } else if (raw instanceof String one) {
                groups = List.of(one);
            } else if (raw instanceof Collection<?> many) {
                groups = new ArrayList<>(many);
            } else {
                throw new BadCredentialsException("Invalid CAS groups type");
            }

            if (groups.size() > 100) {
                throw new BadCredentialsException("Too many CAS groups");
            }
            for (Object value : groups) {
                if (!(value instanceof String group) || group.length() > 256) {
                    throw new BadCredentialsException("Invalid CAS group value");
                }
                String role = allowed.get(group);
                if (role != null) {
                    roles.add(role);
                }
            }
        }

        List<GrantedAuthority> authorities = roles.stream()
                .map(SimpleGrantedAuthority::new)
                .map(x -> (GrantedAuthority) x)
                .toList();

        // "!" is a placeholder password marker unused in CAS login.
        // Do not configure DaoAuthenticationProvider for this account.
        return new User(local.localId(), "!", true, true, true, true,
                authorities);
    }
}
~~~

**Security controls enforced:**

1. Extracts principal/attributes from the assertion received by the CAS provider after validation, never from a form or raw HTTP ticket.
2. Resolves the account by **`CAS_CONTEXT + subject`**, never using a bare subject string across all CAS environments.
3. Rejects accounts with no identity link or marked disabled.
4. Uses the tenant from the **looked-up local account**, never a browser-supplied tenant.
5. Reads only `memberOf` and accepts only `String` or `Collection` of `String` values.
6. Enforces count and length bounds without arbitrary type coercion.
7. Assigns `ROLE_AUTHENTICATED` as an **SP-defined baseline authority**, distinct from `ROLE_APPROVER`/`ADMIN`.
8. Grants elevated roles solely via `RULES` for the exact tenant; unrecognized groups yield no authorities.
9. Returns `UserDetails` so the provider builds `Authentication`; Spring must still enforce domain permissions after login.

**This class is meant for a Spring project**; it cannot be run standalone with plain `javac` and has no fixed stdout. You must implement **`AccountDirectory`** backed by a local repository/database and expose a bean for the class. This sample illustrates a single CAS provider; with multiple CAS servers, create loaders/policies with distinct CAS contexts rather than sharing a single constant context across all providers.

**Protecting the password marker:** the `UserDetails` contract requires a password argument on `User`, even though authentication here relies on a CAS ST. The `"!"` marker is not a usable password and **must never be exposed through a password-based login flow**. If the system supports multiple authentication mechanisms, separate principal/credential handling cleanly and use an appropriate `PasswordEncoder`.

## 14. Wiring the Loader into `CasAuthenticationProvider`

In a Spring Configuration that already defines **`ServiceProperties`** and **`TicketValidator`**, integrate the custom loader:

~~~java
@Bean
ScopedCasUserDetailsService casUserDetails(
        ScopedCasUserDetailsService.AccountDirectory directory) {
    return new ScopedCasUserDetailsService(directory);
}

@Bean
CasAuthenticationProvider casAuthenticationProvider(
        ServiceProperties serviceProperties,
        TicketValidator ticketValidator,
        ScopedCasUserDetailsService casUserDetails) {

    CasAuthenticationProvider provider = new CasAuthenticationProvider();
    provider.setServiceProperties(serviceProperties);
    provider.setTicketValidator(ticketValidator);
    provider.setAuthenticationUserDetailsService(casUserDetails);
    provider.setKey("portal-cas-provider-identity-v1");
    return provider;
}
~~~

**This is a bean setup snippet inside `@Configuration`, not a standalone class.** Required imports:

- **org.springframework.security.cas.authentication.CasAuthenticationProvider**
- **org.springframework.security.cas.ServiceProperties**
- **org.apereo.cas.client.validation.TicketValidator**

You also need **CasAuthenticationFilter**, **CasAuthenticationEntryPoint**, `AuthenticationManager`/`ProviderManager`, `SecurityFilterChain`, and the exact CAS service URL per Spring Security docs. Do not merely create the provider bean and assume the filter and entry point will wire themselves in every project.

### Choosing a Suitable `TicketValidator` to Receive Attributes

Apereo CAS Client provides protocol-specific validators, including **Cas20ServiceTicketValidator** and **Cas30ServiceTicketValidator**. Use the validator compatible with your CAS Server endpoint and required attribute types. For a CAS 3.x system releasing multi-valued attributes, you typically need **`/p3/serviceValidate`** or a matching validation profile.

**If the assertion has no attributes**, check the CAS service registry release policy, validation endpoint/validator version, and attribute mapping first. Never fall back to granting `ROLE_ADMIN` or bypassing validation.

## 15. `UserDetailsByNameServiceWrapper`: When Permissions Live Entirely in the Local DB

If you want CAS solely to verify the username while all roles live in the application database, use a `UserDetailsService`:

~~~java
UserDetailsService localUserDetails = username -> {
    // Application repository looks up the user:
    // use only when the provider's CAS trust context is explicit,
    // avoiding collisions across multiple CAS servers.
    return localAccountService.loadUserByCasSubject("corp-cas", username);
};

UserDetailsByNameServiceWrapper<CasAssertionAuthenticationToken> adapter =
        new UserDetailsByNameServiceWrapper<>(localUserDetails);

casProvider.setAuthenticationUserDetailsService(adapter);
~~~

**The snippet above assumes `localAccountService` is provided by the app** and placed in a proper Spring configuration; it cannot be copied and run standalone. It illustrates the trade-off: the wrapper is simple, yet if CAS sends group attributes, the wrapper **ignores those attributes** unless the local service accesses them separately. Never look up `localUserDetails` by email alone if CAS providers span multiple subject namespaces.

This approach works well when:

- CAS attributes are used solely for display.
- Permissions are managed independently inside the application/authorization service.
- Permission revocation must take effect faster than the SSO session lifetime.
- The application owner does not want the IdP dictating app roles directly.
- Database-backed auditing and account status policies exist.

## 16. Can `GrantedAuthoritiesMapper` Replace a Custom Service?

**`CasAuthenticationProvider#setAuthoritiesMapper`** allows transforming the resulting `GrantedAuthority` set. It can apply a **prefix**, rename roles, or strip undesired authorities.

Example:

~~~java
GrantedAuthoritiesMapper mapper = originals -> originals.stream()
    .filter(a -> Set.of("ROLE_AUTHENTICATED", "ROLE_VIEWER",
            "ROLE_APPROVER").contains(a.getAuthority()))
    .map(a -> new SimpleGrantedAuthority(a.getAuthority()))
    .collect(java.util.stream.Collectors.toSet());

casProvider.setAuthoritiesMapper(mapper);
~~~

**This is only a snippet inside Spring configuration**, not standalone. Filtering authorities by name helps block unexpected strings, yet **it is insufficient for multi-tenant/cross-CAS mapping** once source/tenant metadata is lost. Therefore, perform group->role decisions inside a custom `AuthenticationUserDetailsService` where both the assertion and account context are available.

**Note:** when combining a custom loader and an authorities mapper, define their order and semantics clearly so the mapper never inadvertently introduces permissions outside policy.

## 17. `ROLE_` Prefix, `hasRole`, and `hasAuthority`

Spring Security uses `GrantedAuthority` to express permissions. With the default role prefix:

- **`hasAuthority('ROLE_APPROVER')`** checks the exact string.
- **`hasRole('APPROVER')`** checks the authority matching the standard **`ROLE_`** prefix.
- **`hasAuthority('payment:approve')`** can express action-specific permissions.
- **`ROLE_AUTHENTICATED`** in the examples is just an application-defined baseline role with no universal security meaning.

Example in a service with Method Security enabled:

~~~java
@PreAuthorize("hasRole('APPROVER')")
public void approveInvoice(long invoiceId) {
    // Beyond role, check object tenant and invoice state.
}
~~~

In a real application, protect the domain object further:

~~~java
@PreAuthorize("hasAuthority('ROLE_APPROVER')"
    + " and @invoiceAccess.canApprove(authentication, #invoiceId)")
public void approveInvoice(long invoiceId) {
    // Update the invoice only after the service policy approves.
}
~~~

**The two methods above are alternative examples; do not place identical signatures in one class.** Enable **`@EnableMethodSecurity`** and define the `invoiceAccess` bean with matching name and domain logic. Never use a single global role to grant invoice approval across all tenants.

## 18. Enforcing CAS Trust Context and Account Linking

A system may accept tickets from multiple CAS servers or a broker fronting multiple identity sources. Username **`alice`** at corp CAS does not automatically equal username **`alice`** at partner CAS. Nor can matching emails be merged blindly into one local account.

Safe linking data:

~~~text
federated_identity:
  cas_context      = corp-cas
  cas_subject      = alice
  local_account_id = acct-57
  tenant_id        = north
  UNIQUE(cas_context, cas_subject)

federated_identity:
  cas_context      = partner-cas
  cas_subject      = alice
  local_account_id = acct-91
  tenant_id        = partner-tenant
~~~

**`cas_context`** in this example is an **SP-assigned trust configuration identifier** for the CAS server and service; the CAS protocol has no mandatory **`iss`** claim like OIDC. Never treat a bare username as a global namespace, and never use a browser-supplied login URL to pick the trust context.

If the system runs multiple CAS clients/filters, ensure the right `TicketValidator` and `AuthenticationProvider` for the intended CAS context execute. Never casually fall back to another CAS's validator simply because an ST failed validation.

### Tenant Authorization

Even when an account is linked properly, group mapping must grant permissions only within the authorized tenant. When accessing an object, verify:

1. Local account is active.
2. Account is a member of the current tenant.
3. Policy permits the CAS group to grant authority in this tenant.
4. Specific object-level permissions, ownership, and approval workflow checks pass.
5. For sensitive actions, authentication assurance/step-up and session freshness suffice.

Never trust a **`?tenant=north`** browser parameter as a source of truth before granting `ROLE_APPROVER`.

## 19. Minimal Attribute Release and Security at the CAS Server

An application should not request every attribute CAS holds. For a Portal needing only groups and department, the CAS admin should configure a **per-service release policy**:

| Attribute | Release Needed? | Reason |
| --- | --- | --- |
| Stable principal ID | Yes | Internal account linking |
| `memberOf` (groups scoped to Portal) | If policy depends on groups | Input for authority mapping |
| `department` | Only if domain policy needs it | Contextual metadata |
| `email` | Optional for UX/notifications | Never use as unique identity key |
| password/credential | **No** | Authentication secret, never released |
| TGT/TGC/PGT values | **No** except under ultra-strict protocol-specific proxy policies | Sensitive credentials |
| All LDAP attributes | Usually no | Violates least privilege and increases PII exposure |

Apereo CAS supports **Return Allowed**, **Mapped**, and other policy types; services need an owner approving which attributes are released. Groups used for authorization should have **stable identifiers and defined semantics** rather than mutable display names.

**Two-sided boundary:** CAS restricts what is released; the SP must still **restrict what privileges are granted**. Successful CAS release never turns a value into `ROLE_ADMIN` automatically.

## 20. Do Permissions Update Immediately When CAS Groups Change?

Not by default. At login time, `AuthenticationUserDetailsService` creates a **`UserDetails`/authorities snapshot**. Spring Security stores `Authentication` in `SecurityContext` and the local session. When CAS/LDAP groups change later:

- The CAS TGT may still be valid.
- The SP's local session may still be valid.
- `UserDetails`/`GrantedAuthority` in the SP session may retain stale roles.
- CAS does not re-invoke `AuthenticationUserDetailsService` on every request.
- CAS Single Logout can terminate the local session when integrated properly, yet it does not replace real-time authorization checks.

Controls based on sensitivity:

1. Limit SP session timeout and idle timeout.
2. For high-privilege actions, query current entitlements from the authorization service on critical requests.
3. Enforce account or tenant-role version/epoch revocation in the backend.
4. Require reauthentication/`renew` on sensitive steps if CAS assurance policy calls for it.
5. Connect role-change and account-lock events to session invalidation.
6. Audit caches in `UserDetailsService`, `CasAuthenticationProvider`, and the app to avoid retaining stale roles too long.
7. Test access after a user is disabled or removed from a group—not only on fresh logins.

**Never rely on TGC/TGT expiration to assume local sessions and API tokens have expired.** Each application is responsible for the sessions and tokens it issues.

## 21. Separating Login Authority, Functional Authority, and Data Authority

A well-structured security mapping typically has three layers:

| Layer | Example | When Checked |
| --- | --- | --- |
| Authentication baseline | `ROLE_AUTHENTICATED` | After CAS ST validation and active local account |
| Application function | `ROLE_VIEWER`, `ROLE_APPROVER` | In `AuthorizationFilter` / `@PreAuthorize` |
| Object / tenant | Permitted to approve invoice 123 of tenant `north` | In domain service / authorization component |

**A user holding `ROLE_APPROVER` is not automatically authorized to approve every invoice.** If the same local account is Approver in `north` yet only Viewer in `south`, scope roles by tenant or enforce tenant-aware domain policies on every operation. A global role alone is not a tenant boundary.

A general policy:

~~~text
ALLOW approve(invoiceId)
  IF verified CAS login
  AND local account active
  AND current tenant membership active
  AND permitted app authority
  AND invoice belongs to current tenant
  AND invoice state permits approval
  AND approval separation-of-duties check succeeds
ELSE DENY
~~~

Never put sensitive authorization logic in JSPs/templates or rely on hiding frontend buttons. Server-side enforcement is mandatory.

## 22. Edge Cases: Missing, Wrongly Typed, or Renamed Groups

| Verified Input from CAS | Safe Behavior |
| --- | --- |
| `memberOf` absent | Grant no elevated roles; retain baseline per policy |
| `memberOf` = empty Collection | Grant no elevated roles |
| `memberOf` = `portal-readers` | Map strictly to `ROLE_VIEWER` within approved scope |
| `memberOf` = unrecognized `ROLE_ADMIN` | Do not copy verbatim as `ROLE_ADMIN` |
| `memberOf` has duplicate values | Deduplicate |
| `memberOf` contains `Integer` or `Map` | Reject/ignore per contract; never call `toString()` to grant access |
| `memberOf` overly long / too many items | Enforce limits and reject safely |
| Group renamed from `finance-reviewers` to `finance-approvers` | Do not grant new authority until policy is approved |
| Attribute renamed from `memberOf` to `groups` | Do not guess; coordinate with CAS admin to update release contract |
| Tenant not linked to account | Grant no tenant-specific permissions |
| CAS returns attributes but local DB fails | Fail closed for sensitive roles; never fall back to admin |
| Local account disabled | Reject login or invalidate session per policy |
| CAS principal `alice` appears in two trust contexts | Keep identity links separate; never merge by username |
| Unknown group outside allowlist | Grant no new authority; audit appropriately |

**User-facing note:** When CAS authentication succeeds yet the SP grants insufficient permissions, the user should receive **403 Forbidden** instead of looping back to CAS login. This is normally a role/tenant configuration issue, not proof that CAS ST validation failed.

## 23. Testing: Mapper Unit Tests and CAS Integration Tests

### Unit Test Cases

| Case | Input Data | Expected Result |
| --- | --- | --- |
| 01 | `corp-cas`/`north` + `portal-readers` | `ROLE_VIEWER` |
| 02 | `corp-cas`/`north` + `finance-reviewers` | `ROLE_APPROVER` |
| 03 | `corp-cas`/`north` + both groups | Viewer and Approver |
| 04 | `corp-cas`/`north` + `ROLE_ADMIN` | Does not auto-grant Admin |
| 05 | `partner-cas`/`north` + `finance-reviewers` | Grants no corp permissions |
| 06 | `corp-cas`/`south` + `finance-reviewers` | Grants no north permissions |
| 07 | Duplicate group | Only one corresponding authority |
| 08 | Numeric group value | Rejected or fails closed per mapper |
| 09 | `memberOf` null/empty | Baseline authority only |
| 10 | Attribute name changed | Does not fall back to another field to grant roles |
| 11 | Local account unlinked | Creates no elevated `Authentication` |
| 12 | Local account disabled | Rejected per account status |
| 13 | Users in CAS A and CAS B share username | Independent local identities |
| 14 | Tenant X membership revoked | Access to Tenant X resources denied |
| 15 | Policy service timeout | Sensitive permissions fail closed |
| 16 | Group changes while local session active | Verify revocation/session policy |
| 17 | Has `ROLE_APPROVER` but invoice belongs to another tenant | Denied at object-level authorization |
| 18 | Multi-valued CAS attribute | Iterated completely and mapped accurately |
| 19 | Custom `ROLE_` prefix | `hasRole`/`hasAuthority` behave consistently |
| 20 | Case-sensitive group ID | Not silently normalized |
| 21 | Concurrent local DB lookup/provisioning | No duplicate accounts created |
| 22 | Null CAS assertion or missing principal | Rejected |
| 23 | Ticket validation network failure | Loader never called with unverified data |
| 24 | Service URL mismatch | CAS does not return `authenticationSuccess` |
| 25 | CAS `/serviceValidate` releases no groups | App never fabricates roles when data is absent |

### Integration Tests with Real or Test CAS Server

1. Browser is redirected to CAS login for the registered service.
2. CAS issues an ST for the right service; Spring `CasAuthenticationProvider` invokes `TicketValidator`.
3. Validation response contains real principal + `memberOf`; custom loader receives exact assertions.
4. `UserDetails` returns local account ID and allowlisted authorities.
5. With an ST from another service, CAS validation fails **before** the user loader runs.
6. Re-login with changed groups after policy update; new permissions apply at the expected lifecycle point.
7. CAS logout/SLO and SP session invalidation are tested separately.
8. HTTPS, reverse proxy URLs, cookies, single-use tickets, XML parsing, and client versions are verified.

**Never treat unit tests with fake `Assertion` objects as proof of production SSO.** They only test the mapper; protocol trust must be verified against a CAS Server and configured `TicketValidator`.

## 24. Common Troubleshooting

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| CAS login succeeds yet Spring returns 403 | Missing local roles or domain policy denial | Check `UserDetails` authorities and tenant membership |
| CAS assertion contains only username | Service not authorized to release attributes | Check CAS Service Registry and attribute release policy |
| Attributes still empty despite LDAP groups in CAS | Validator uses protocol/endpoint that omits attributes | Check `/p3/serviceValidate`, CAS client version, and assertion parsing |
| `CasAuthenticationProvider` never calls custom loader | `setAuthenticationUserDetailsService` not set on the active instance | Verify provider bean, filter, and manager wiring |
| App loads roles only from DB despite CAS groups | Using `UserDetailsByNameServiceWrapper` | Switch to custom loader when CAS groups are needed |
| An unknown group becomes `ROLE_ADMIN` | Raw attribute mapped without allowlist | Enforce exact group->role policy; never auto-name |
| Corp user gains partner permissions | Missing CAS context/tenant scoping | Separate trust namespaces and memberships |
| Login fails with username not found | External identity unlinked | Approved onboarding/JIT, never match blindly by email |
| Disabled account still enters app | Custom loader skips status check or old session remains | Check active status and revoke sessions |
| Has `ROLE_VIEWER` yet `hasRole('VIEWER')` fails | Prefix/case mismatch | Check `ROLE_` prefix and authority names |
| Has `ROLE_APPROVER` yet can act on another tenant's invoice | Missing object-level authorization | Enforce resource tenant and business checks |
| ST invalid/expired | CAS single-use ticket, service mismatch, timeout | Check CAS client validation; never retry ST blindly |
| Spring 5 code fails to compile on Spring 6/7 | `org.jasig` vs. `org.apereo` packages and API changes | Update dependencies/imports per version BOM |
| Reloading local DB reflects role changes slowly | Authorities cached in `SecurityContext`/session | Design re-login, refresh, or revocation |
| One node sees groups, another does not | Divergent CAS attribute cache or client version config | Align CAS/Spring cluster configuration |
| Attribute value is `Collection` yet code casts to `String` | `ClassCastException` or missing roles | Strict parser supporting multi-value |
| Client sets `acceptAnyProxy` to bypass errors | Widens trust excessively for proxy tickets | Lock down proxy policy; disable when unneeded |

**Safe logging:** correlation ID, service identity, CAS trust context, anonymized local account ID where needed, policy version, valid group count, granted authority count, and error code. **Never log** STs, TGTs, TGCs, raw CAS assertions containing PII, passwords, or private/proxy credentials.

## 25. Advanced Security and Operations

### Service-Specific Authority Policy

The CAS Service Registry can release a different attribute set to each service. The same directory group **`finance-reviewers`** may mean different things in Portal vs. HRM. Never share one enterprise-wide mapping table if role semantics differ.

**Right:** each application has its own policy owner, group IDs, role names, tenant scope, and tests. **Wrong:** every service applies a blanket rule "any group containing `admin` -> `ROLE_ADMIN`."

### Session Refresh and Privilege Revocation

If a group is removed in CAS/LDAP, the local session may still hold stale authorities. For elevated privileges, check entitlements server-side or invalidate sessions when policies change. Set TTLs based on sensitivity rather than relying solely on TGT lifetime.

### Consent and PII

Request and release only essential attributes. If email or department is needed for display, never treat them as sufficient proof for account linking or privileges. CAS service release policies should block passwords and proxy-granting credentials outside strictly controlled use cases.

### Rate Limiting and DoS Prevention

Reject tens of thousands of group values, nested objects, oversized strings, or dangerous regexes in role mapping. Enforce bounds and fail cleanly to controlled authentication failures or authorization denials.

### Coordinating Group Renames

CAS admins and app owners need a change process: standardize group IDs, assess semantic differences, update allowlist mapping tables, canary test, roll out, and only then retire old names. Never auto-alias arbitrary group names via lowercase/trim alone.

### Multiple CAS Servers

An application may connect to multiple CAS servers under an explicit architecture; each server needs separate trust config/validators, service IDs, and identity namespaces. Never join two CAS contexts solely on principal username without verified account-link proof.

## 26. End-to-End Implementation Runbook

1. **Agree on CAS contract:** confirm CAS Server URL, service callback, TLS trust, validation endpoint, and CAS client version.
2. **Register service:** CAS Service Registry permits Portal, configures strict service URL and attribute release policy.
3. **Verify payload:** use test users with single and multiple groups, inspect assertion principal/attributes post-validation; never log raw STs/PII.
4. **Design account linking:** map `(CAS context, CAS subject)` -> local account ID with uniqueness constraints and account-status checks.
5. **Design mapping:** per-service/per-tenant allowlists; sensitive privileges approved by app owners.
6. **Choose loader:** `UserDetailsService` wrapper when no CAS attributes are needed; custom `AuthenticationUserDetailsService` when assertions/tenants are needed.
7. **Wire provider:** set `setAuthenticationUserDetailsService` on the right `CasAuthenticationProvider`, paired with proper `TicketValidator`, `ServiceProperties`, filter, and entry point.
8. **Test roles:** CAS login succeeds, authorities match, `hasRole`/`hasAuthority` behave properly.
9. **Test fail-closed cases:** invalid ticket, missing attribute, unknown group, disabled account, wrong tenant, DB outage.
10. **Test session lifecycle:** logout, SLO, group changes, cache/session expiry, and revocation.
11. **Multi-node rollout:** align config, ticket validation TLS, access log redaction, metrics, and policy version.
12. **Audit:** record change owner, test results, CAS release policy, and rollback plan.

Never test only "can log in" while skipping verification of **which authorities were granted**. With a broken mapping, users may log in cleanly yet hit 403s or gain out-of-scope privileges.

## 27. Self-Assessment Questions

**1. What does `AuthenticationUserDetailsService` receive differently from `UserDetailsService`?**  
It receives an `Authentication` token—such as `CasAssertionAuthenticationToken` holding an `Assertion`—allowing it to read principal attributes rather than only a username.

**2. Does it validate the CAS Service Ticket itself?**  
No. `CasAuthenticationProvider` together with `TicketValidator` performs validation; the loader processes post-validation data in the proper flow.

**3. CAS returns `memberOf` containing `ROLE_ADMIN`; should Spring grant admin automatically?**  
No. Grant only authorities present in the application's allowlist for the exact CAS context, tenant, and business policy.

**4. What does `GrantedAuthorityFromAssertionAttributesUserDetailsService` do?**  
It converts values of specified CAS attributes directly into authorities; convenient, yet often lacks controls required for multi-tenant or cross-provider scenarios.

**5. Does `setConvertToUpperCase` make group mapping secure?**  
No. It only changes letter casing and does not validate privileges.

**6. Why must accounts be linked by CAS context + principal ID?**  
Because multiple CAS contexts can issue identical usernames; a bare username is not globally unique.

**7. If CAS does not release `memberOf`, should `ROLE_APPROVER` be granted by default?**  
No. Baseline authorities may be granted per app policy, whereas sensitive permissions must fail closed without proof.

**8. Why must `UserDetails` carry authorities after CAS already authenticated the user?**  
Because authentication proves identity only; Spring `AuthorizationFilter` and method security rely on authorities to make access decisions.

**9. Do CAS group changes immediately update authorities inside an active SP session?**  
Not by default; re-login, session invalidation, or server-side entitlement checks are required.

**10. If CAS shows the same user is Approver in `north` and Viewer in `south`, can a global `ROLE_APPROVER` be used?**  
No. Enforce tenant scoping and object-level permissions on the server.

## 28. Pre-Production Checklist

- [ ] CAS `TicketValidator` verifies Service Tickets over HTTPS with the right service identifier and CAS server.
- [ ] Custom user loader is never invoked with raw HTTP tickets or unverified Assertions.
- [ ] CAS Service Registry releases **only minimal required attributes** to Portal; never passwords or secret tokens.
- [ ] Validator and endpoint match the CAS version and support principal attributes where required.
- [ ] Deliberate choice made between `UserDetailsService` wrapper and `AuthenticationUserDetailsService`.
- [ ] If using `GrantedAuthorityFromAssertionAttributesUserDetailsService`, direct mapping and trust policy have been evaluated.
- [ ] Raw LDAP/CAS group strings never become authorities without passing an allowlist.
- [ ] Identity linking uses `CAS context + subject` -> local account and never auto-merges by email.
- [ ] Disabled or suspended local accounts are rejected.
- [ ] Attribute parser validates `String`/`Collection`, multi-values, nulls, duplicates, sizes, and unexpected types.
- [ ] Roles are mapped per tenant/service with zero privilege bleed across CAS contexts.
- [ ] Baseline authorities such as `ROLE_AUTHENTICATED` never confer elevated privileges.
- [ ] Method/resource authorization checks tenant, ownership, and business state.
- [ ] `ROLE_` prefix and `hasRole`/`hasAuthority` usage are consistent.
- [ ] Tests cover unknown `ROLE_ADMIN` group, wrong tenant, missing attribute, and database failure.
- [ ] Plans exist for session TTL, CAS logout/SLO, and role/account revocation.
- [ ] STs are never used as long-lived API tokens, and raw tickets/cookies/Assertions are never logged.
- [ ] Spring Security and Apereo CAS Client packages/APIs verified against the release BOM.
- [ ] Mapping config audit, owner, error monitoring, and rollback mechanisms are in place.

## 29. Conclusion

**`AuthenticationUserDetailsService<CasAssertionAuthenticationToken>`** bridges a **CAS Assertion verified by the CAS provider** and **Spring Security `UserDetails`/`GrantedAuthority`**. When only a username is needed to look up local roles, `UserDetailsByNameServiceWrapper` may suffice. When CAS attributes, multi-tenant policies, or account linking are required, a custom loader enforces stricter source validation and mapping.

**`GrantedAuthorityFromAssertionAttributesUserDetailsService`** can convert CAS attributes into authorities quickly, but it does not protect against **role injection**, **cross-CAS collisions**, or **cross-tenant privilege escalation**. In production, use an **application-owned allowlist**, verify local account status, tenant membership, and resource permissions, and implement risk-based session/authority revocation. **CAS authenticates the user; the application decides what that user may do.**

### Official Documentation

- Spring Security — CAS Authentication, `CasAuthenticationProvider`, and `UserDetailsService`: https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html
- Spring Security API — `AuthenticationUserDetailsService`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/AuthenticationUserDetailsService.html
- Spring Security API — `CasAssertionAuthenticationToken`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/authentication/CasAssertionAuthenticationToken.html
- Spring Security API — `CasAuthenticationProvider`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/authentication/CasAuthenticationProvider.html
- Spring Security API — `GrantedAuthorityFromAssertionAttributesUserDetailsService`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/userdetails/GrantedAuthorityFromAssertionAttributesUserDetailsService.html
- Spring Security API — `AbstractCasAssertionUserDetailsService`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/userdetails/AbstractCasAssertionUserDetailsService.html
- Apereo CAS 7.3 — Attribute Release: https://apereo.github.io/cas/7.3.x/integration/Attribute-Release.html
- Apereo CAS 7.3 — Attribute Release Policies: https://apereo.github.io/cas/7.3.x/integration/Attribute-Release-Policies.html
- Apereo CAS Java Client — documentation and validation: https://github.com/apereo/java-cas-client
