# Saml2AuthenticatedPrincipal, Saml2Authentication, and Accessing SAML 2.0 Attributes

> **Topic:** Spring Security – federation. **Group:** Identity and Authorities. This lesson explains how Spring Security converts an authenticated SAML 2.0 Response/Assertion into a user object in a Java application, how to read NameID and SAML attributes, how to use `Saml2Authentication` and `GrantedAuthority`, and a very important difference between **Spring Security 6.x** and **7.x**.

## 1. Lesson Objectives

After this lesson, you will be able to:

1. Distinguish **SAML Assertion**, **Principal**, **Authentication**, **Credentials**, and **Authorities**.
2. Use `Saml2AuthenticatedPrincipal` in Spring Security 6.x systems to retrieve `getName()`, `getAttributes()`, `getAttribute(name)`, and `getFirstAttribute(name)`.
3. Retrieve session and registration information: `getRelyingPartyRegistrationId()` and `getSessionIndexes()` according to each version's API.
4. Distinguish `Saml2Authentication` (authenticated result) from `Saml2AuthenticationToken` (authentication request being processed).
5. Avoid confusing **SAML attributes** with **Spring Security GrantedAuthority** or **business permissions**.
6. Safely handle missing attributes, multi-valued attributes, type mismatches, mismatched names/namespaces, and IdP configuration changes.
7. Write a Spring Boot controller/service that reads identity with proper type checks, does not expose raw `SAMLResponse`, and maps roles via an allowlist.
8. Understand the Spring Security 7 change: `Saml2AuthenticatedPrincipal` has been marked **deprecated**, and assertion data has moved to `Saml2ResponseAssertionAccessor`/`Saml2AssertionAuthentication`. Do not write code assuming a single cast always works on both versions.

**Quick answer:** In a default Spring Security 6.x application, `Authentication.getPrincipal()` is typically `Saml2AuthenticatedPrincipal`, and the Authentication object is `Saml2Authentication`. In Spring Security 7.x, the default may return `Saml2AssertionAuthentication` (a subclass of `Saml2Authentication`), and SAML attributes reside on the **assertion accessor in credentials**, rather than in the principal by default. Check the version before choosing an access pattern.

## 2. From SAML Response to Spring Security Authentication

Spring Security Servlet SAML2 Login allows an application to act as a **Service Provider (SP/Relying Party)**. When a user finishes logging in at an Identity Provider (IdP/Asserting Party):

~~~text
Browser sends SAMLResponse (HTTP POST)
           |
           v
Saml2WebSsoAuthenticationFilter
           |
           v
Saml2AuthenticationTokenConverter
           |  resolve RelyingPartyRegistration
           v
Saml2AuthenticationToken        [NOT authenticated]
           |
           v
AuthenticationManager -> OpenSaml5AuthenticationProvider
           |  - verify IdP issuer and trust
           |  - verify Response/Assertion signature
           |  - decrypt Assertion/attributes if needed
           |  - check Audience, Recipient, Conditions, time, request state...
           v
Saml2Authentication / Saml2AssertionAuthentication
           |  [AUTHENTICATED if successful]
           |  principal + authorities + corresponding SAML data
           v
SecurityContextHolder -> Controller/Service/Authorization
~~~

Depending on the Spring Security version, the provider may use different OpenSAML classes or validator ordering. The key point: **only after the response and assertion have been authenticated** should you read NameID/attributes to determine an account or permissions. Never Base64-decode `SAMLResponse` yourself from an HTTP request and trust `NameID`/`role` values.

### Five concepts to separate

| Object / concept | Role | Example |
|---|---|---|
| **SAML Response** | Message sent by the IdP to the ACS, containing status and one/more Assertions | XML `samlp:Response` |
| **SAML Assertion** | Data about the subject asserted by the IdP with usage conditions | `NameID`, `AttributeStatement`, `AuthnStatement` |
| **Principal** | User identity in Spring after authentication | Principal name or object containing user info |
| **Authentication** | Authentication result used by Spring in `SecurityContext` | `Saml2Authentication` / `Saml2AssertionAuthentication` |
| **GrantedAuthority** | Permission/role used by Spring to make access decisions | `ROLE_USER`, `ROLE_REPORT_VIEW`, `FACTOR_SAML_RESPONSE` |

**Example:** The IdP sends `groups=finance-readers` in an Assertion. First and foremost, this is just a **SAML Attribute**. Only when a verified mapping policy emits `GrantedAuthority("ROLE_REPORT_VIEW")` will `hasAuthority("ROLE_REPORT_VIEW")` allow access. Do not treat arbitrary strings in `AttributeStatement` as authorities automatically.

## 3. Which parts of an Assertion relate to identity?

The XML example below is an **illustrative fragment**; other required fields such as issuer, conditions, signature, and the enclosing SAML Response have been omitted, so **do not use it as a valid Assertion for login**:

~~~xml
<saml:Assertion xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
                ID="_sample_assertion">
  <saml:Subject>
    <saml:NameID
        Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent">
      8f91a1c9-identity-key
    </saml:NameID>
  </saml:Subject>
  <saml:AuthnStatement SessionIndex="_session_01"
                       AuthnInstant="2026-11-07T02:30:00Z">
    <!-- AuthnContext omitted -->
  </saml:AuthnStatement>
  <saml:AttributeStatement>
    <saml:Attribute Name="email">
      <saml:AttributeValue>reader@example.org</saml:AttributeValue>
    </saml:Attribute>
    <saml:Attribute Name="department">
      <saml:AttributeValue>Finance</saml:AttributeValue>
    </saml:Attribute>
    <saml:Attribute Name="groups">
      <saml:AttributeValue>report-readers</saml:AttributeValue>
      <saml:AttributeValue>finance-users</saml:AttributeValue>
    </saml:Attribute>
  </saml:AttributeStatement>
</saml:Assertion>
~~~

If the IdP issues the corresponding Assertion and Spring Security verifies it successfully, semantically:

- **NameID:** subject identifier; may be persistent ID, emailAddress, transient, unspecified, etc., depending on IdP configuration and the federation contract.
- **Attributes:** set of attributes as **name → list of values**. A single name `groups` can have **two values**. Values may be objects rather than always `String`.
- **AuthnStatement.SessionIndex:** SAML session information provided by the IdP, which can be used in SAML Single Logout; it is **not Spring's HttpSession ID**, nor is it an authority value.
- **Conditions/Audience/SubjectConfirmation:** determine whether the Assertion is valid for the SP, within the time window, and for the right audience/recipient.
- **Signature:** protects the signed content; must be verified along with IdP trust before creating a principal.

### Three data types commonly misunderstood

1. **NameID differs from Attribute `email`.** An IdP may set `NameID` to an opaque persistent ID while `email` is a changeable mailbox address.
2. **Attribute `groups` differs from `GrantedAuthority`.** A mapper must decide which claims to trust and which authorities to grant.
3. **SessionIndex differs from the application's Session ID.** IdP SSO logout may rely on SessionIndex; the internal app session is still managed by its own security context/session.

## 4. Spring Security 6.x: Saml2AuthenticatedPrincipal

In Spring Security 6.x, `org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal` is an interface extending `AuthenticatedPrincipal`. The common implementation is `DefaultSaml2AuthenticatedPrincipal`.

Commonly used methods:

| Method | Data type | Meaning |
|---|---|---|
| `getName()` | `String` | Principal name, by default typically from the NameID in the Assertion used |
| `getAttributes()` | `Map<String, List<Object>>` | All SAML attributes mapped from AttributeStatement |
| `getAttribute("groups")` | `List<A>` or null | List of values for an attribute by the given name |
| `getFirstAttribute("email")` | `A` or null | First element of the attribute; may be missing |
| `getRelyingPartyRegistrationId()` | `String` | Registration ID of the selected RP/SP ↔ IdP |
| `getSessionIndexes()` | `List<String>` | SAML SessionIndexes in the Assertion/Authentication |

`getFirstAttribute` is convenient for fields that are single-valued by contract, but **does not normalize** a field that is inherently multi-valued. For groups/entitlements, use the **full list**, rather than taking only the first value and discarding the rest. `getAttribute("unknown")` and `getFirstAttribute("unknown")` can return `null`: code must handle this.

**Generic warning:** `<A> A getFirstAttribute(String name)` is generic based on the caller's expected return type, with **no runtime schema mechanism automatically verifying that the IdP returned a `String`**. If the IdP sends another type, assigning directly to `String` can cause a `ClassCastException`. For external data, prefer receiving `Object` and checking `instanceof String` or using a well-defined converter.

### 4.1. Accessing it in a Spring Security 6.x controller

Example in a Spring Boot MVC application with SAML2 login enabled. File `src/main/java/com/example/portal/LegacySamlProfileController.java`:

~~~java
package com.example.portal;

import java.util.List;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class LegacySamlProfileController {

    @GetMapping("/me")
    public Map<String, Object> me(
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {

        if (principal == null) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }

        Object department = principal.getFirstAttribute("department");
        List<?> groups = principal.getAttribute("groups");

        return Map.of(
                "name", principal.getName(),
                "registrationId", principal.getRelyingPartyRegistrationId(),
                "department", department == null ? "(missing)" : department.toString(),
                "groupCount", groups == null ? 0 : groups.size());
    }
}
~~~

**Example characteristics:** The Java class has full imports and valid syntax for the appropriate Spring Security 6.x version, but is **not a standalone `javac` program**. It requires a Spring Boot Servlet/Security/SAML2 module project and a registered IdP, plus a protected `/me` route. Null handling is included; `Map.of` does not accept null, so the code converts a missing department into an internal placeholder string. The sample API **returns only the group count**, not the entire raw assertion or sensitive claims. In production, check policies regarding what identifying data may be displayed.

Do not blindly populate an endpoint with all attributes from `principal.getAttributes()`: email, department, groups, employee number, or PII can be sensitive. Only return fields permitted by authorization/privacy policy.

### 4.2. Accessing via Authentication in 6.x

Besides `@AuthenticationPrincipal`, a controller/service can receive `Authentication` directly:

~~~java
@GetMapping("/session-type")
public String sessionType(Authentication authentication) {
    if (authentication instanceof Saml2Authentication saml) {
        Object principal = saml.getPrincipal();
        if (principal instanceof Saml2AuthenticatedPrincipal samlPrincipal) {
            return samlPrincipal.getRelyingPartyRegistrationId();
        }
    }
    return "not-legacy-saml-principal";
}
~~~

This is a **method fragment** placed inside a controller with appropriate imports, not a standalone compilable class. Check `instanceof` instead of casting directly; if the application has multiple authentication mechanisms or a custom converter, the principal type may differ. In Spring Security 7.x, this pattern is even more important because `Saml2AuthenticatedPrincipal` may no longer be the default principal.

## 5. Saml2Authentication: representing the authentication result

`org.springframework.security.saml2.provider.service.authentication.Saml2Authentication` is a Spring Security `Authentication` implementation extending `AbstractAuthenticationToken`. It contains:

- **`getPrincipal()`:** the authenticated user. Its static type is `Object` in modern APIs; do not always assume `Saml2AuthenticatedPrincipal`.
- **`getName()`:** authentication name; in the default flow it usually reflects the NameID of the Assertion used.
- **`getAuthorities()`:** the set of `GrantedAuthority` instances Spring uses to check access.
- **`isAuthenticated()`:** authentication state managed by the provider.
- **`getCredentials()`:** credentials field per the Authentication interface; **exact content depends on subclass/version**.
- **`getSaml2Response()`:** SAML Response XML as a decoded string; **may contain PII/identifiers, assertions, or elements that remain encrypted**.
- **`getDetails()`:** authentication details added by the framework/config, **not a SAML attributes map** by default.

**Never log or directly return `getSaml2Response()` in a web API.** Raw XML can contain NameID, groups, email, attributes, and sensitive login details. Whether some components are signed or encrypted does not change the requirement to restrict access to the raw response.

### 5.1. Saml2AuthenticationToken vs. Saml2Authentication

| Type | At which stage | Can be used as proof of identity? |
|---|---|---|
| `Saml2AuthenticationToken` | Filter receives HTTP SAMLResponse and passes it to AuthenticationManager/provider to **authenticate** | **No**; it is an unauthenticated request |
| `Saml2Authentication` | Provider authenticates successfully and creates Authentication | **Can** be used in SecurityContext with an authorization policy |
| `Saml2AssertionAuthentication` (7.x) | Subclass authentication result containing an assertion accessor | **Yes**, after the provider completes validation |
| `Saml2AuthenticatedPrincipal` (6.x) | Data-rich principal from the Assertion | **Yes**, but must come from an authenticated Authentication, never manually constructed from raw XML |

A critical mistake is reading `Saml2AuthenticationToken.getSaml2Response()` in an unverified filter to assign user roles, or manually creating an authenticated token using data from the browser. Let Spring Security/OpenSAML verify the IdP signature/trust and SAML conditions first.

### 5.2. Authorities and access control

Authorities granted in the authentication result **do not automatically equal every group value at the IdP**. According to Spring Security's SAML2 Login Overview for the branch described, the default provider grants `ROLE_USER` and `FACTOR_SAML_RESPONSE`; the authority set can change when using a custom converter or in a specific version.

Example rules in `HttpSecurity`:

~~~java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/reports/**").hasAuthority("ROLE_REPORT_VIEW")
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated()
    )
    .saml2Login(Customizer.withDefaults());
~~~

This is a **configuration fragment** to place into a Servlet `SecurityFilterChain`. `hasRole("ADMIN")` checks `ROLE_ADMIN` with the default role prefix, whereas `hasAuthority("ROLE_REPORT_VIEW")` matches the exact authority string. Merely enabling `saml2Login` **does not create** the custom authority `ROLE_REPORT_VIEW`; trusted SAML groups/claims must be mapped to authorities by policy before the reports path is permitted.

## 6. Spring Security 7.x: notable API changes

**Spring Security 7.x separates SAML Assertion information from the principal.** The migration documentation explains this change helps Spring Security obtain the assertion details needed for SAML Single Logout even when the application creates a custom principal.

- `Saml2AuthenticatedPrincipal` and `DefaultSaml2AuthenticatedPrincipal` are marked **@Deprecated** in Spring Security 7.1 JavaDoc.
- `Saml2AssertionAuthentication` (since 7.0) is a subclass of `Saml2Authentication`.
- `Saml2AssertionAuthentication.getCredentials()` returns `Saml2ResponseAssertionAccessor` instead of just an untyped generic object.
- `Saml2ResponseAssertionAccessor` provides `getNameId()`, `getAttributes()`, `getAttribute(name)`, `getFirstAttribute(name)`, `getSessionIndexes()`, and `getResponseValue()`.
- `Saml2AssertionAuthentication.getRelyingPartyRegistrationId()` returns the registration ID; this no longer needs to be retrieved from `Saml2AuthenticatedPrincipal`.
- With default Spring Security 7 configuration, you **must not blindly cast** `Authentication.getPrincipal()` to `Saml2AuthenticatedPrincipal` assuming the cast always succeeds.

This means the **distinction between Principal and Assertion data** becomes explicit: the principal can be an internal identity chosen by the application, while the assertion accessor represents the IdP-issued SAML data verified by the provider.

### 6.1. API comparison table: 6.x vs. 7.x

| Need | Common in Spring Security 6.x | Default in Spring Security 7.x |
|---|---|---|
| Authentication type | `Saml2Authentication` | `Saml2AssertionAuthentication`, a subclass of `Saml2Authentication` |
| Default principal | `Saml2AuthenticatedPrincipal` | May be a different principal; do not assume the legacy interface |
| Username | `authentication.getName()` / `principal.getName()` | `authentication.getName()` / `accessor.getNameId()` when original NameID is needed |
| Single SAML attribute | `principal.getFirstAttribute(name)` | `accessor.getFirstAttribute(name)` |
| All attribute values | `principal.getAttribute(name)` | `accessor.getAttribute(name)` |
| All attributes | `principal.getAttributes()` | `accessor.getAttributes()` |
| Registration ID | `principal.getRelyingPartyRegistrationId()` | `saml2AssertionAuthentication.getRelyingPartyRegistrationId()` |
| SAML SessionIndex | `principal.getSessionIndexes()` | `accessor.getSessionIndexes()` |
| Raw SAMLResponse | `authentication.getSaml2Response()` | `authentication.getSaml2Response()` or `accessor.getResponseValue()` depending on API; **avoid logging** |
| New application development | Continue using per locked version | Prefer 7.x APIs and review the migration guide |

**Do not misunderstand:** `Saml2Authentication` **was not removed** in 7.x; the subclass `Saml2AssertionAuthentication` is itself a `Saml2Authentication`. The main change is that **Assertion details no longer have to live inside the principal**. A custom `ResponseAuthenticationConverter` can still return legacy `Saml2Authentication` when compatibility is needed, but that does not turn deprecated APIs into a long-term solution.

### 6.2. Spring Security 7.x Java Controller

Example in a Spring Boot project using Spring Security **7.x**; all imports are complete. File `src/main/java/com/example/portal/Saml7ProfileController.java`:

~~~java
package com.example.portal;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.saml2.provider.service.authentication.Saml2AssertionAuthentication;
import org.springframework.security.saml2.provider.service.authentication.Saml2ResponseAssertionAccessor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class Saml7ProfileController {

    @GetMapping("/me")
    public Map<String, Object> me(Authentication authentication) {
        if (!(authentication instanceof Saml2AssertionAuthentication saml)) {
            throw new ResponseStatusException(
                    HttpStatus.UNAUTHORIZED, "SAML authentication required");
        }

        Saml2ResponseAssertionAccessor assertion = saml.getCredentials();
        Object department = assertion.getFirstAttribute("department");
        List<?> groups = assertion.getAttribute("groups");

        Map<String, Object> profile = new LinkedHashMap<>();
        profile.put("principalName", saml.getName());
        profile.put("nameId", assertion.getNameId());
        profile.put("registrationId", saml.getRelyingPartyRegistrationId());
        profile.put("department",
                department == null ? "(missing)" : department.toString());
        profile.put("groupCount", groups == null ? 0 : groups.size());
        return profile;
    }
}
~~~

**Code explanation:**

1. `Authentication authentication` is obtained by Spring MVC from the authenticated SecurityContext.
2. `instanceof Saml2AssertionAuthentication` explicitly handles the 7.x API; if the app allows multiple authentication mechanisms, or a custom provider returns another subclass, it will not cast incorrectly.
3. `getCredentials()` on this subclass has type `Saml2ResponseAssertionAccessor`. This is **assertion data**, not a returned password.
4. `getFirstAttribute("department")` is a **nullable** value and its type is not guaranteed to always be String.
5. `getAttribute("groups")` retrieves the list. The controller in this example returns only the **count**, without exposing all claims.
6. `getName()` and `getNameId()` may represent two different purposes if the principal is customized by the application; do not assume they are always equal in every system.
7. `registrationId` is Spring's configuration identifier, **not the IdP's issuer/entityID**.

This code lives inside an application with a security filter chain protecting `/me`. **Does not run standalone with `javac`**; requires matching Spring Boot/Web MVC/SAML2 SP dependencies, a compatible Java version for Spring Boot, and a valid registered IdP. If a legacy `Saml2Authentication` arrives from a custom converter on 7.x, the example intentionally returns an error rather than assuming credentials hold an assertion accessor; this is an explicit outcome to verify during migration.

### 6.3. Why not write a controller with a hardcoded cast?

The following snippet is an **anti-pattern when upgrading to 7.x**:

~~~java
// ClassCastException risk: principal may no longer be
// Saml2AuthenticatedPrincipal by default in Spring Security 7.x.
Saml2AuthenticatedPrincipal principal =
        (Saml2AuthenticatedPrincipal) authentication.getPrincipal();
String email = principal.getFirstAttribute("email");
~~~

Reason: In the 7.x line, assertion attributes are no longer forced onto the principal; an application may have a custom principal while the framework needs a separate accessor to handle SLO. Code using `@AuthenticationPrincipal Saml2AuthenticatedPrincipal` may be valid in 6.x, but is **not guaranteed to remain compatible by default in 7.x**.

**Migration path:** before upgrading Spring Security, audit usages of `Saml2AuthenticatedPrincipal`, `DefaultSaml2AuthenticatedPrincipal`, `getRelyingPartyRegistrationId()`, and `getSessionIndexes()`; write login tests against a real IdP; migrate assertion reads to `Saml2ResponseAssertionAccessor` and registration IDs to `Saml2AssertionAuthentication` per 7.x. If you temporarily need to retain the old authentication shape, consult the migration guide on `ResponseAuthenticationConverter`, while planning to remove deprecated code.

## 7. Reading attributes properly: names, types, multi-value, and null

SAML `AttributeStatement` maps a field by the **IdP's configured name** to a list of values. This differs from a JSON DTO with fixed properties.

### 7.1. Attribute names must not be guessed

| Business info | Name the IdP might provide | Issue |
|---|---|---|
| Email | `email`, `mail`, URI claim | Not every IdP uses `email` |
| Full name | `displayName`, `givenName`, `sn` | May be missing or inconsistent |
| Groups | `groups`, `memberOf`, URI group claim | List, group IDs instead of names |
| Department | `department`, custom URI | May contain locale or internal code values |
| User ID | `employeeNumber`, `uid`, NameID | May differ from NameID; do not trust email as a durable key |
| Roles | `roles`, `Role`, URI claim | A value `"admin"` does not automatically grant a GrantedAuthority |

You must verify the **IdP attribute mapping contract** and the actual names in a validated assertion. SAML `NameFormat` and attribute `Name` also matter; libraries and IdPs may represent names differently. Do not simply patch code to probe 20 different names and pick "whichever exists" when used for identity binding or permissions.

### 7.2. The map holds lists, not a single String

Hypothetical data (after provider verification):

~~~text
{
  "email": ["reader@example.org"],
  "department": ["Finance"],
  "groups": ["report-readers", "finance-users"],
  "employeeNumber": ["E-12345"]
}
~~~

`getAttributes()` returns `Map<String, List<Object>>`. Therefore:

- `getFirstAttribute("email")` may be suitable when it is agreed that email has exactly one value.
- `getAttribute("groups")` retrieves the **full** list; calling `getFirstAttribute("groups")` drops the remaining groups.
- `getAttribute("missing")` can be `null`; always have a fallback/validation.
- Do not cast `List<Object>` to `List<String>` without checking each element.
- If a verified, single-valued email is required, **check that condition** instead of taking the first of two emails and treating it as valid.
- Values may contain different whitespace/casing/encoding; normalize according to a **controlled contract**, rather than applying arbitrary trim/lowercase to IDs/roles without consulting the IdP.

### 7.3. A type-safe Java utility

**Standalone** Java example that only processes a hypothetical attributes map **already produced by a trusted SAML validator**, without validating a SAML Response itself. File `SamlAttributeReaderDemo.java`:

~~~java
import java.util.List;
import java.util.Map;

public class SamlAttributeReaderDemo {

    static String firstString(Map<String, List<Object>> attrs, String key) {
        List<Object> values = attrs.get(key);
        if (values == null || values.size() != 1) {
            return "(missing-or-ambiguous)";
        }
        Object value = values.get(0);
        if (!(value instanceof String str) || str.isBlank()) {
            return "(missing-or-ambiguous)";
        }
        return str;
    }

    static int stringGroupCount(Map<String, List<Object>> attrs) {
        List<Object> values = attrs.get("groups");
        if (values == null) {
            return 0;
        }
        int count = 0;
        for (Object value : values) {
            if (value instanceof String group && !group.isBlank()) {
                count++;
            }
        }
        return count;
    }

    public static void main(String[] args) {
        Map<String, List<Object>> attributes = Map.of(
                "email", List.<Object>of("reader@example.org"),
                "groups", List.<Object>of("report-readers", "finance-users"),
                "department", List.<Object>of("Finance"));

        System.out.println("email=" + firstString(attributes, "email"));
        System.out.println("unknown=" + firstString(attributes, "unknown"));
        System.out.println("groups=" + stringGroupCount(attributes));
    }
}
~~~

Compile and run **without Spring** using Java 17+:

~~~bash
javac SamlAttributeReaderDemo.java
java SamlAttributeReaderDemo
~~~

Exact stdout:

~~~text
email=reader@example.org
unknown=(missing-or-ambiguous)
groups=2
~~~

**Takeaway from the utility:** Attribute names can be missing, element counts may not match expectations, and values may not be Strings. For identity/authorization, **fail closed** when the contract is not met, instead of force-casting or trusting arbitrary data.

**Explicit limitation:** The utility accepts a map we constructed ourselves. It **does not** verify XML signatures, IdP issuer, Audience, Recipient, time, SessionIndex, or replay. In production, only supply attributes **after** Spring Security/OpenSAML has authenticated the SAML message.

## 8. User identity: getName, NameID, email, and local key

### 8.1. How is getName() formed?

According to the traditional SAML2 Login pipeline in Spring Security documentation, `Authentication#getName()` defaults to the **NameID of the selected Assertion**. With a custom `ResponseAuthenticationConverter` or custom principal, `getName()` can be changed to a local user ID.

Several common possibilities:

| Value | Meaning | Suitable as local key? |
|---|---|---|
| SAML persistent NameID | Stable ID per IdP/SP if the IdP enforces policy properly | Usually suitable, but must be paired with IdP issuer/tenant |
| SAML transient NameID | Per-session / short-lived identifier | Not suitable as a long-term key |
| Email NameID | User mailbox | Can change/be recycled; must be evaluated |
| Attribute `email` | Contact/claim info | Not guaranteed unique/verified across all tenants by default |
| Attribute `employeeNumber` | Employee ID | Use only after contract confirms uniqueness/lifecycle |
| Local account ID | Application's internal user identifier | Suitable once IdP issuer + subject mapping is governed |

**Recommendation:** When linking federated identities to local accounts, treat identity as at least the **pair (IdP issuer or stable registration, verified subject ID)**, accompanied by tenant/IdP change policies and JIT provisioning rules. Do not merge two users solely because they share an email if different IdPs can issue the same email string.

### 8.2. Authentication.getName differs from Attribute

Example:
- `authentication.getName() = "8f91a1c9-identity-key"`;
- `email = "reader@example.org"`;
- `department = "Finance"`.

These three values serve different purposes. If the application wants to display email while storing user relationships by persistent NameID, keep the **public display attribute** and **stable identity binding key** clearly separated.

## 9. Authorities: mapping SAML groups to GrantedAuthority

### 9.1. Do not grant roles from arbitrary strings

Values such as:

~~~text
groups=["finance-users","report-readers"]
department=["Finance"]
title=["Director"]
~~~

do not carry the same trust or privilege level on their own. Authority mapping typically requires:

1. Verifying the Response/Assertion signature **with the right trusted IdP key**.
2. Confirming the correct issuer, audience, recipient, time, subject, and registration.
3. Identifying which **IdP/tenant** is permitted to issue group claims for the application.
4. Mapping only an **allowlist** of specific group IDs to internal authorities.
5. Rejecting or ignoring values not in the allowlist; never auto-creating `ROLE_` from arbitrary strings.
6. Keeping access decisions in the application via `@PreAuthorize`, `hasAuthority`, and business permission policies.
7. Having a revocation process: when a user leaves a group or is disabled at the IdP, existing SP sessions must obey session expiry/re-authentication/disable policies.

### 9.2. Standalone mapping function example with tenant restriction

File `SamlAuthorityMapperDemo.java` – standalone Java 17 code simulating mapping from a **list already authenticated by the provider**:

~~~java
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class SamlAuthorityMapperDemo {

    static Set<String> map(String registrationId, List<?> groups) {
        if (!"corporate".equals(registrationId) || groups == null) {
            return Set.of();
        }

        Map<String, String> allowed = Map.of(
                "report-readers", "ROLE_REPORT_VIEW",
                "report-editors", "ROLE_REPORT_EDIT");

        Set<String> result = new LinkedHashSet<>();
        for (Object group : groups) {
            if (group instanceof String name) {
                String authority = allowed.get(name);
                if (authority != null) {
                    result.add(authority);
                }
            }
        }
        return Set.copyOf(result);
    }

    public static void main(String[] args) {
        List<String> groups = List.of("report-readers", "unknown-group");
        System.out.println("corporate=" + map("corporate", groups).contains("ROLE_REPORT_VIEW"));
        System.out.println("other=" + map("other-tenant", groups).contains("ROLE_REPORT_VIEW"));
        System.out.println("admin=" + map("corporate", groups).contains("ROLE_ADMIN"));
    }
}
~~~

Run:

~~~bash
javac SamlAuthorityMapperDemo.java
java SamlAuthorityMapperDemo
~~~

Exact stdout:

~~~text
corporate=true
other=false
admin=false
~~~

The sample restricts **registrationId** and allowlisted groups, and does not auto-create admin permissions. In multi-tenant systems, prefer keying trust by **verified issuer and federation contract**, not solely on a name `corporate` from a request parameter. `registrationId` is only meaningful after Spring Security has verified the mapping to the right IdP.

**Example limitation:** This function returns `Set<String>`, not `Collection<GrantedAuthority>`, so it **does not plug into SecurityContext on its own**. In Spring Security, proper integration requires a converter/provider for authorities post-authentication, typically creating `SimpleGrantedAuthority` from the allowlisted set and returning an `Authentication` with the corresponding authorities. Never construct `new Saml2Authentication(...)` from unsigned/unverified input to "enable roles".

### 9.3. Authorization in HTTP Security and method security

Servlet fragment example:

~~~java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/reports/**").hasAuthority("ROLE_REPORT_VIEW")
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated())
    .saml2Login(Customizer.withDefaults());
~~~

Here:
- A user with only the default `ROLE_USER` cannot view reports or admin pages.
- A user with `ROLE_REPORT_VIEW` after policy-compliant mapping can view reports.
- `hasRole("ADMIN")` requires `ROLE_ADMIN` with the default prefix.
- Beyond URL rules, service methods may still need business authorization by resource owner/department/transaction, not just coarse roles.

**Do not check group text directly in every controller.** A mapping layer that validates schema, issuer, and policy prevents each endpoint from interpreting `groups` differently.

## 10. Spring Security 7.x and Single Logout: why separate the accessor?

SAML2 Single Logout (SLO) may require assertion values such as **NameID, SessionIndex, and Relying Party registration**. Before Spring Security 7, the principal held much of that data. If an application wanted a custom principal (for example, a domain user object), SLO could struggle when needing assertion details from a principal that no longer implemented the legacy interface.

In Spring Security 7:

- The assertion is exposed via `Saml2ResponseAssertionAccessor`, accessed through `Saml2AssertionAuthentication.getCredentials()`.
- `getNameId()` provides the original NameID.
- `getSessionIndexes()` provides the associated SessionIndexes.
- `getRelyingPartyRegistrationId()` resides on the authentication subclass.
- The principal can be a separate object, without needing to carry an attribute map or SessionIndex.

### What not to do

- Storing `SessionIndex` as the HttpSession ID: they are two different kinds of data.
- Calling `getSessionIndexes().get(0)` without checking for an empty list; some assertions may have no SessionIndex.
- Printing raw `getSaml2Response()` or `getResponseValue()` to debug SLO in production.
- Injecting NameID/SessionIndex from an HTTP request into SLO without tying it to an authenticated Authentication.
- Assuming `Saml2AuthenticatedPrincipal` was removed in 7.x: **it is deprecated, which does not mean immediately deleted**, though an upgrade plan is needed.

**Example:** If an IdP uses SessionIndex `_session_01` to manage SAML SSO, the SP still has its own HTTP session managed by the container/Spring. When local logout happens, the HTTP session may be invalidated while the IdP SSO session remains; when SLO is properly implemented, the framework needs the authentication's identity and SessionIndex to exchange LogoutRequest/LogoutResponse messages with the IdP per the profile.

## 11. Accessing Authentication in controllers, services, and background code

### 11.1. Controller receiving Authentication directly

In Spring MVC:

~~~java
@GetMapping("/whoami")
public String whoami(Authentication authentication) {
    return authentication.getName();
}
~~~

This is a fragment, **not a standalone class**. When an endpoint requires an authenticated user, Spring MVC resolves the current Authentication. If multiple authentication types exist (SAML, form login, bearer JWT), do not assume every `Authentication` is SAML; check the type before reading SAML-specific properties.

### 11.2. SecurityContextHolder in synchronous services

For synchronous Servlet code:

~~~java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
if (authentication == null || !authentication.isAuthenticated()) {
    // Do not use as application identity.
}
~~~

This is also a fragment. `isAuthenticated()` can be true for certain special non-real-user tokens (e.g., anonymous tokens depending on configuration), so business flows must rely on **security rules and principal type/policy**. Never use `isAuthenticated()==true` as the sole condition for granting admin access.

### 11.3. Async/background jobs

`SecurityContextHolder` is typically bound to the request-processing thread/context according to Spring Security's strategy. When offloading work to an executor, queue, or scheduled job, do not assume SecurityContext automatically follows across every thread. When work must execute under a verified identity, use appropriate context propagation/`DelegatingSecurityContext` or pass a controlled immutable **business identity key**. Do not serialize raw `Saml2Authentication`/`SAMLResponse` onto a queue for convenience.

### 11.4. WebFlux differs from Servlet

Spring Security SAML2 Service Provider login is officially focused on **Servlet** in the documentation. `@AuthenticationPrincipal` and `Authentication` above belong to Spring MVC examples; do not copy `HttpSecurity.saml2Login` into WebFlux `ServerHttpSecurity` and expect it to work. If a WebFlux application consumes OIDC from an identity broker, the principal/attributes are OAuth2/OIDC APIs, **not `Saml2AuthenticatedPrincipal`**.

## 12. Spring Boot Servlet configuration and demo scope

To run the controller examples in a project, you need compatible Spring Boot Servlet, Security, and SAML2 SP modules. In a `pom.xml` with a Spring Boot BOM or parent, dependencies look like:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-saml2-service-provider</artifactId>
  </dependency>
</dependencies>
~~~

OpenSAML dependencies/repositories must be added according to the exact Spring Security version and project build policy. Do not mix Spring Security 6 and 7 APIs in the same artifact without a compatibility plan.

Example IdP metadata config (illustrative URL, **not a live ready-to-run IdP**):

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            assertingparty:
              metadata-uri: "https://idp.example.org/metadata"
~~~

The IdP must actually register the **SP entityID/ACS** and provide a trusted public signing certificate. Add a `SecurityFilterChain` for Servlet (fragment):

~~~java
@Bean
SecurityFilterChain samlSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/error").permitAll()
            .requestMatchers("/reports/**").hasAuthority("ROLE_REPORT_VIEW")
            .anyRequest().authenticated())
        .saml2Login(Customizer.withDefaults())
        .build();
}
~~~

To run a Spring Boot project with Maven wrapper and a properly configured IdP:

~~~bash
./mvnw spring-boot:run
~~~

There is no fixed stdout/login result because it depends on the IdP, user, and policy. The fragments above must be placed inside classes with appropriate annotations/imports; the 6.x controller and 7.x controller above **are two choices for two versions**—do not put the same `/me` mapping into the same project.

## 13. Testing at the right layers: unit mapping, Spring MVC, and SAML integration

### 13.1. Testing attribute reading

Cases to cover:

| Test | Hypothetical input from validated SAML assertion | Expected outcome |
|---|---|---|
| Email single-value | `email=["a@example.org"]` | Reads the value accurately |
| Email missing | no `email` | Null/fallback or reject per policy |
| Email multi-value | `email=["a@x","b@x"]` | Reject if contract requires uniqueness |
| Group multi-value | `groups=["readers","finance"]` | Retains both values |
| Group type mismatch | `groups=[123]` | Does not blindly cast to String |
| NameID differs from email | opaque NameID and different email | Does not overwrite stable identity with email |
| Different attribute names | IdP sends `mail` instead of `email` | Warn/map per contract, do not silently miss |
| Login from another tenant | different issuer, same email | No automatic account-linking or privilege escalation |

### 13.2. Testing against the right Spring Security version

- **6.x:** test principal type `Saml2AuthenticatedPrincipal` and the getter methods used in controllers.
- **7.x:** test default authentication type `Saml2AssertionAuthentication`, `getCredentials()` being `Saml2ResponseAssertionAccessor`, registration ID, and SessionIndexes.
- **Upgrade:** test that `@AuthenticationPrincipal Saml2AuthenticatedPrincipal` is no longer assumed by default on 7.x.
- **Mixed login:** if the app also supports form/Basic/OIDC, controllers reading SAML attributes must handle non-SAML authentications.
- **Custom converter:** test that a custom principal still gives the app access to business identity and gives SLO the assertion details per the API version.

### 13.3. Integration testing with an IdP

A test that merely constructs `DefaultSaml2AuthenticatedPrincipal` manually and invokes a service **does not verify SAML**. You need tests with a **test IdP/fixture with valid signatures** to confirm:

- The SP verifies the trusted signature of the Response/Assertion.
- Issuer, AudienceRestriction, Recipient/Destination, timing, and InResponseTo are checked.
- NameID and attributes are read from an Assertion **that has been verified**.
- Multiple Assertions/EncryptedAttributes are handled properly by the pipeline.
- User/group mapping follows policy and does not escalate privileges via invalid claims.
- Logout includes SessionIndexes when needed and follows the protocol.
- Sensitive data is not logged/exposed in raw form.

You can use `MockMvc` and Spring Security test support to test controllers/authorization, but mock tests **do not replace real integration tests** with IdP signatures, metadata/certificates, and SAML conditions.

## 14. Common mistakes and fixes

| Symptom | Common cause | Resolution |
|---|---|---|
| `ClassCastException` when casting principal | 7.x app or custom principal is not `Saml2AuthenticatedPrincipal` | Check `instanceof`; use `Saml2AssertionAuthentication.getCredentials()` on the matching version |
| `@AuthenticationPrincipal Saml2AuthenticatedPrincipal` is null | Principal is another type or not a SAML login | Check actual Authentication/version; use Authentication + type checks |
| `getFirstAttribute("email")` returns null | IdP sends a different name, no email, or unmapped | Align on attribute contract; handle missing values |
| Role from IdP present, yet Spring returns 403 | SAML group **not yet mapped** to the required GrantedAuthority | Add allowlist mapping in the post-validation pipeline |
| Multiple groups exist, but app sees only one | Used `getFirstAttribute("groups")` | Use `getAttribute("groups")` / map `List<Object>` |
| `ClassCastException` from `List<String>` | IdP emits non-String values | Iterate `Object` items, check type, and reject per policy |
| Principal name changes when NameID format changes | App uses unstable NameID/email as user key | Design durable subject binding with issuer and stable ID |
| Only `ROLE_USER` appears | Default provider does not auto-map arbitrary group claims | Add custom converter/authority mapping after verifying IdP trust |
| `getSessionIndexes()` is empty | Assertion lacks SessionIndex or IdP omits it | Do not call `get(0)` unchecked; evaluate SLO support |
| Logout fails after introducing custom principal | SAML assertion details no longer where the framework expects | Use Spring Security 7 accessor/credential API or supported migration path |
| `/me` returns raw groups/email to unauthorized users | Controller exposes too many attributes | Restrict fields, check authz and privacy |
| Reading `getSaml2Response()` to parse directly | Bypasses validators and duplicates XML parsing | Use typed, validated attribute APIs and the OpenSAML pipeline |
| `getDetails()` lacks email | Details are not SAML AttributeStatement | Use the version-appropriate principal/accessor |
| `hasRole("ADMIN")` fails even though groups contain `"admin"` | `ROLE_ADMIN` not granted in authorities | Never auto-grant; define explicit mapping policy and test |
| Session/SLO mismatch | Using SessionIndex as HTTP session ID | Separate IdP SessionIndex, SP session, and logout protocol |

## 15. Code review and operations checklist

- [ ] Exact Java, Spring Boot, Spring Security, and OpenSAML versions are pinned.
- [ ] Confirmed whether 6.x or 7.x to select the SAML attribute reading API.
- [ ] `Saml2AuthenticationToken` is used strictly as an **unauthenticated request**.
- [ ] Controllers/services only read data after the framework produces an authenticated Authentication.
- [ ] For 6.x, `Saml2AuthenticatedPrincipal` is obtained from SecurityContext or `@AuthenticationPrincipal` with null/type checks.
- [ ] For 7.x, code accepts `Saml2AssertionAuthentication`, reads `Saml2ResponseAssertionAccessor` and registration ID per the API.
- [ ] `getAttribute` and `getFirstAttribute` handle null, multi-values, types, and attribute names.
- [ ] NameID, email, user ID, issuer, and registration ID are not confused with each other.
- [ ] Groups/roles are mapped via an allowlist scoped by issuer/tenant and business policy, never auto-creating authorities from arbitrary claims.
- [ ] `hasRole`/`hasAuthority` and Method Security actually consume the granted GrantedAuthorities.
- [ ] Do not expose `getSaml2Response()`, `getResponseValue()`, private keys, or sensitive NameID/groups in logs/public APIs.
- [ ] Tests exist with a real IdP and negative cases: invalid signature, wrong issuer/audience, expired assertion, replay, untrusted group.
- [ ] SessionIndex and SLO are handled per protocol, not used as an HTTP session ID.
- [ ] Custom converters do not bypass signature/conditions validation; compatibility tests exist for Spring Security upgrades.
- [ ] SecurityContext/Authentication is not casually passed to background jobs.

## 16. Self-check questions

1. **What is `Saml2AuthenticatedPrincipal`?** In 6.x, it is the principal interface holding authenticated information from a SAML Assertion, providing getters for NameID-like name, attributes, registration, and SessionIndex. Deprecated in 7.x.
2. **How does `Saml2Authentication` differ from `Saml2AuthenticationToken`?** The former is the provider's authenticated result; the latter is the unauthenticated SAMLResponse request.
3. **Why does `getAttributes()` return a Map of Lists?** A SAML Attribute can contain **multiple AttributeValues** under the same Name.
4. **Should you call `getFirstAttribute("groups")`?** Not if groups are multi-valued; use `getAttribute("groups")` and process the full list.
5. **What if `getFirstAttribute` returns null?** The attribute may be missing or named differently; handle per business contract, never cast or elevate privileges by default.
6. **Do groups from an IdP automatically become GrantedAuthorities?** No. You need a converter/mapping governed by trust and an allowlist.
7. **Where does Spring Security 7.x obtain attributes?** In the default SAML7 flow, from `Saml2AssertionAuthentication.getCredentials()`, which returns `Saml2ResponseAssertionAccessor`.
8. **Can you cast `authentication.getPrincipal()` directly to `Saml2AuthenticatedPrincipal` in 7.x?** Not guaranteed; check types and migration guidance.
9. **Why might the principal name differ from NameID?** A custom principal may hold a local user ID; the SAML accessor still retains the original NameID.
10. **Is `getSessionIndexes()` an HttpSession ID?** No. It relates to IdP SAML sessions/SLO.
11. **Should you log `getSaml2Response()`?** No, because the XML may contain PII/claims/session info.
12. **What is needed to grant a user `ROLE_REPORT_VIEW`?** Verify the IdP/Assertion, map a valid group via allowlist to `ROLE_REPORT_VIEW`, and enforce authorization rules.

## 17. Official documentation to cross-check by version

- Spring Security SAML2 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security Authenticating SAML2 Responses and customizing Converters: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security 7 SAML2 Migration (deprecated principal and accessor): https://docs.spring.io/spring-security/reference/migration/servlet/saml2.html
- JavaDoc Saml2AuthenticatedPrincipal: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/authentication/Saml2AuthenticatedPrincipal.html
- JavaDoc Saml2Authentication: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/authentication/Saml2Authentication.html
- JavaDoc Saml2AssertionAuthentication: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/authentication/Saml2AssertionAuthentication.html
- JavaDoc Saml2ResponseAssertionAccessor: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/authentication/Saml2ResponseAssertionAccessor.html
- Spring Security Authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- OASIS SAML 2.0 Core (Assertion/AttributeStatement): https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf

**Summary:** `Saml2Authentication` represents an Authentication verified by Spring Security; `Saml2AuthenticatedPrincipal` is the familiar way to read the principal and attributes in Spring Security 6.x, whereas in 7.x you should move to `Saml2AssertionAuthentication` + `Saml2ResponseAssertionAccessor`. Regardless of the API, **NameID ≠ email**, **SAML Attribute ≠ GrantedAuthority**, **SessionIndex ≠ HttpSession**, and only data that has passed validation and policy mapping may be used to identify users or grant permissions.
