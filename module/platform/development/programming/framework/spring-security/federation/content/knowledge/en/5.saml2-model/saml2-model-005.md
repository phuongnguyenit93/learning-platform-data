# AttributeStatement, Single-Valued, and Multi-Valued Attributes in SAML 2.0

> **Scope:** Spring Security – federation → SAML2 Model. This lesson focuses on how a SAML Assertion represents user attributes via `AttributeStatement`, distinguishing 0/1/many values, how the SP reads and uses them in Spring Security, along with security boundaries and IdP interoperability.

## 1. Why Understanding Attribute Cardinality Matters

When an application logs in via SAML 2.0, the IdP can send information such as email, employee ID, department, group lists, or business attributes. A common mistake is assuming every attribute is **a single string**. In reality, a `<saml:Attribute>` may contain **zero, one, or many** `<saml:AttributeValue>` elements. Taking only the first value when the data is actually multi-valued can drop information; splitting a single string into a list can alter the attribute's meaning.

For example:

- `mail` is usually specified by the IdP/SP contract as having only **one** email for the application.
- `groups` usually has **multiple** groups such as `portal-readers` and `invoice-approvers`.
- `employeeId` may be required as **one** identifier.
- `costCenters` may have **0 to many** codes if an employee oversees multiple units.
- `displayName` is display information and may not be issued; lacking `displayName` does not necessarily mean authentication failed.

**Goal:** read the SAML structure accurately; understand the data contract for each attribute; avoid using `getFirstAttribute()` for inherently multi-valued data; verify the assertion before trusting attributes; and never turn IdP groups directly into all application permissions.

## 2. Position of AttributeStatement in a SAML Assertion

SAML 2.0 distinguishes several statement types:

| Component | Role |
| --- | --- |
| `<saml:Subject>` / `<saml:NameID>` | Identifies the subject referenced by the assertion |
| `<saml:AuthnStatement>` | Asserts the authentication event/method; may contain `AuthnInstant`, `SessionIndex`, `AuthnContext` |
| `<saml:AttributeStatement>` | Set of attributes describing the subject via `Attribute` / `AttributeValue` |
| `<saml:AuthzDecisionStatement>` | Another statement type for authorization decisions, rarely used in typical Web SSO |
| `<saml:Conditions>` | Constrains assertion validity, audience, and other conditions |

Typical structural diagram (simplified):

```text
<samlp:Response>
  └── <saml:Assertion>                       [verified by appropriate signing mechanism]
       ├── <saml:Issuer> ...
       ├── <saml:Subject>
       │    └── <saml:NameID> ...
       ├── <saml:Conditions> ...
       ├── <saml:AuthnStatement> ...
       └── <saml:AttributeStatement>
            ├── <saml:Attribute Name="...mail">
            │    └── <saml:AttributeValue>linh@example.org
            ├── <saml:Attribute Name="...groups">
            │    ├── <saml:AttributeValue>portal-readers
            │    └── <saml:AttributeValue>invoice-approvers
            └── <saml:Attribute Name="...costCenter">
                 └── (no AttributeValue)
```

This is a **diagram**, not valid standalone XML. In a SAML document, `AttributeStatement` belongs to the **assertion**; it is not something the application arbitrarily appends after SP authentication. An assertion may contain multiple statements; the application must not assume there is always an `AttributeStatement` or a specific attribute type. `EncryptedAttribute` may appear instead of cleartext attributes, depending on the IdP/profile and decryption capabilities configured at the SP.

**Distinction:** `NameID` is **not** an `Attribute` of `AttributeStatement`. They may hold the same string (e.g. email), yet they are not equivalent by default in uniqueness, stability, intended audience, or usage policy. Depending on the application, `NameID`/subject identifier is typically used as input for account mapping; `mail`/`displayName` are supplemental claims.

## 3. Anatomy of an Attribute

A `<saml:Attribute>` has three important XML attributes:

| Field | Required? | Meaning |
| --- | --- | --- |
| `Name` | Yes | Technical name of the SAML attribute, e.g. `urn:example:claims:groups` or an OID URI |
| `NameFormat` | No | Format/naming domain of `Name`, e.g. `urn:oasis:names:tc:SAML:2.0:attrname-format:uri` |
| `FriendlyName` | No | Human-readable label for administrators, e.g. `groups`; **not** a canonical identifier for formal matching |
| `AttributeValue` (child element) | 0 to many | Each element carries one attribute value; may be simple or complex |

Example of a **structurally complete XML fragment** for `AttributeStatement` using synthetic values; this is **not** a signed SAML Assertion and cannot be used to log in by itself:

```xml
<saml:AttributeStatement
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">

    <!-- Single value -->
    <saml:Attribute
        Name="urn:example:claims:mail"
        NameFormat="urn:oasis:names:tc:SAML:2.0:attrname-format:uri"
        FriendlyName="mail">
        <saml:AttributeValue xsi:type="xs:string">linh@example.org</saml:AttributeValue>
    </saml:Attribute>

    <!-- Multiple values: two AttributeValues in one Attribute -->
    <saml:Attribute
        Name="urn:example:claims:groups"
        NameFormat="urn:oasis:names:tc:SAML:2.0:attrname-format:uri"
        FriendlyName="groups">
        <saml:AttributeValue xsi:type="xs:string">portal-readers</saml:AttributeValue>
        <saml:AttributeValue xsi:type="xs:string">invoice-approvers</saml:AttributeValue>
    </saml:Attribute>

    <!-- Attribute present but has no values yet -->
    <saml:Attribute
        Name="urn:example:claims:costCenters"
        NameFormat="urn:oasis:names:tc:SAML:2.0:attrname-format:uri"
        FriendlyName="costCenters"/>
</saml:AttributeStatement>
```

Reading layer by layer:

1. `AttributeStatement` contains multiple **distinct attributes**: `mail`, `groups`, and `costCenters`.
2. Each `Attribute` has a **technical name** `Name` and a list of **values**. `mail` has one, `groups` has two, `costCenters` has none.
3. `FriendlyName="groups"` is solely for human readability; integration must use the identifier agreed upon by IdP/SP (including `NameFormat` when namespace disambiguation is needed).
4. `xsi:type="xs:string"` indicates XML Schema string data in the example. SAML `AttributeValue` has base type `xs:anyType`; an IdP may supply other simple types or complex XML depending on profile.
5. This XML snippet lacks SAML Response, signature, `Issuer`, `Conditions`, and `SubjectConfirmation`. Never “trust” an attribute merely because it parses.

### 3.1. NameFormat: Does the Same Name Always Mean the Same Attribute?

Do not assume so. SAML Core and Errata note that identifying an attribute may require inspecting the **`(NameFormat, Name)` pair**; a `Name` alone may be insufficient if the IdP uses multiple namespaces. When `NameFormat` is omitted, SAML Core interprets it as `unspecified`; do not infer it as `uri`. Common values:

- `urn:oasis:names:tc:SAML:2.0:attrname-format:unspecified` – no specific naming convention.
- `urn:oasis:names:tc:SAML:2.0:attrname-format:uri` – name in URI form.
- `urn:oasis:names:tc:SAML:2.0:attrname-format:basic` – simple name namespace per SAML rules.

For instance, a contract might pick `Name=urn:example:claims:groups` and `NameFormat=...:uri`. Do not substitute `FriendlyName=groups` as the mapping key if the actual `Name` is a URI.

**In Spring Security 6.x**, `Saml2AuthenticatedPrincipal#getAttributes()` exposes attributes as `Map<String, List<Object>>` keyed by **string name**. This is a convenient mapping model, **not exposing all metadata of every `Attribute` intact**. If two attributes share `Name` with different `NameFormat`s, the application must control schema/IdP mapping before collapsing them into a single string key; do not assume getters automatically detect or resolve namespace collisions.

### 3.2. Type of AttributeValue

`<saml:AttributeValue>` is an XML value with no guarantee that “everything is a Java String.” For example:

```xml
<saml:Attribute
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    Name="urn:example:claims:employeeLevel">
    <saml:AttributeValue xsi:type="xs:integer">4</saml:AttributeValue>
</saml:Attribute>
```

In XML Schema semantics, `4` has integer type via `xsi:type`. Yet once passed through a specific converter, the Java value may be materialized according to library rules and versions. The application must **check the actual object type** before casting, and agree on schemas between IdP/SP. Never call `toString()` indiscriminately on a complex XML object and treat it as a business value.

If an `Attribute` has multiple `AttributeValue` elements declaring `xsi:type`, SAML Core requires declared types to be consistent within the same attribute. A complex value may require a custom schema and converter; test the exact IdP profile.

## 4. Single-Valued, Multi-Valued, Absent, and Empty Attributes

### 4.1. Actual Cardinality

| Source XML | `AttributeValue` count | Technical semantics | Suggested policy when app reads |
| --- | ---: | --- | --- |
| No `<Attribute Name="mail">` | N/A | Attribute absent | Required → reject mapping; optional → treat as missing |
| `<Attribute Name="mail"/>` present | 0 | Attribute present with no values | Do not automatically treat as empty string or null; handle per contract |
| One `<AttributeValue>linh@example.org</...>` | 1 | One value | Allowed for contractually single-valued attribute |
| Two `<AttributeValue>reader</...>` and `<AttributeValue>editor</...>` | 2 | Two independent values | Read as a list; do not randomly pick the first |
| One `<AttributeValue>reader,editor</...>` | 1 | **One** string containing a comma | Split only if IdP/SP agreed on CSV encoding |
| One `<AttributeValue></AttributeValue>` | 1 | One value with empty content per encoding | Distinct from having zero values; consider rejecting for required fields |
| Two `<Attribute>` elements with same name | Element-dependent | Two declarations of the same attribute name | Have an explicit merge/deduplicate/reject policy; do not rely on ordering |

> **Key point:** “Single-valued”/“multi-valued” is typically a **contract for an attribute** in the application or SAML profile; the `Attribute` element itself has no `single=true` flag. The XML schema of `AttributeValue` allows 0 to many.

### 4.2. Do Not Conflate Four Cases

**A. Absent:** No matching key. In Spring Security, `getAttribute(name)` usually returns `null` when the attribute is absent from the map. Do not treat `null` as a one-element list containing `null`.

**B. Attribute present with zero values:** XML has `Attribute` and zero `AttributeValue` elements. In Java, test your converter: it may yield an empty list or be omitted depending on implementation/mapping. Do not assume a single representation if your logic must distinguish the two states.

**C. One value whose content is empty or whitespace-only:** Structurally, this is an actual value. The application may forbid it under the contract for `employeeId`/`mail`, but should not silently convert every empty string into “absent” if empty values are permitted.

**D. Multiple values:** Each element carries one value. XML order should not determine privilege priority unless the contract defines ordering. For groups/roles, usually think in terms of **sets** after contract-compliant normalization; for ordered contact addresses, explicit metadata may be needed rather than assuming “first element is primary.”

### 4.3. Delimiter-Separated String Does Not Equal Multiple Values

The following two representations are **not equivalent** unless the IdP/SP explicitly agreed otherwise:

```xml
<!-- 2 SAML values -->
<saml:Attribute xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
                Name="urn:example:claims:groups">
    <saml:AttributeValue>team-a</saml:AttributeValue>
    <saml:AttributeValue>team-b</saml:AttributeValue>
</saml:Attribute>
```

```xml
<!-- 1 SAML value; the comma is string data -->
<saml:Attribute xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
                Name="urn:example:claims:groups">
    <saml:AttributeValue>team-a,team-b</saml:AttributeValue>
</saml:Attribute>
```

If a provider truly sends CSV inside a single `AttributeValue`, define the delimiter, escaping, whitespace, empty values, ordering, handling of commas inside names, and length limits. Without a contract, **never auto-split** with `String.split(",")` and assign roles.

### 4.4. Two Attributes with the Same Name: Consistent Handling

Some federated payloads may contain duplicate `Attribute` `Name` entries within the same or across different statements. How the library maps them into `Map<String, List<Object>>` depends on its merge/overwrite/precedence behavior. For sensitive attributes:

- Prefer configuring the IdP to emit **one Attribute with multiple AttributeValues** instead of multiple duplicate-named Attributes when multi-valued data is needed.
- Document duplicate behavior: reject, merge per policy, or treat as a schema error; never “pick the last occurrence” since an attacker could exploit ambiguity.
- Test payloads with identical `Name`, differing `NameFormat`, differing `FriendlyName`, conflicting values, and reversed order.
- For required scalars like `employeeId`, reject multiple values regardless of whether they are identical or different, unless the business contract truly allows them with clear rules.

## 5. Post-Authentication Attribute Mapping Workflow

```text
IdP issues Assertion
  │
  ▼
Browser sends SAMLResponse to SP's ACS
  │
  ▼
Spring Security / OpenSAML:
  verify issuer, signature/trust, destination, audience,
  time conditions, subject confirmation, and login transaction
  │
  ▼
Decrypt EncryptedAttribute (if configured and needed)
  │
  ▼
Extract AttributeStatement per converter rules
  │
  ▼
Map<String, List<Object>> on authenticated principal
  │
  ▼
APPLICATION MAPPING:
  1. select contracted attribute names
  2. validate presence + cardinality + type + format
  3. normalize in a controlled manner
  4. link (issuer, subject, tenant) to internal user
  5. translate claims into permissions per allowlist/policy
  │
  ▼
SecurityContext + session; subsequent requests enforce authorization
```

**Security boundary:** Attributes are trustworthy **only after** SAML validation succeeds for the right IdP/SP and the exact assertion being used. Reading Base64-decoded XML, extracting email/groups from the ACS request before signature validation, or hand-parsing XML with XPath unconstrained by signed scope risks principal spoofing and XML signature wrapping.

**Point-in-time nature:** Groups/department in an assertion are a **snapshot** issued by the IdP at login time. When groups change at the IdP, the local session may not reflect them immediately. Systems requiring rapid privilege revocation need session timeouts/re-auth, re-fetching permissions from a business source, or proper revocation policies; never rely on `AttributeStatement` self-updating.

## 6. Reading Attributes with Spring Security 6.x

In a Servlet application logging in via `saml2Login()`, `Saml2Authentication#getPrincipal()` is typically a `Saml2AuthenticatedPrincipal` after validation succeeds. Spring Security 6.x Javadoc defines these getters:

```java
<A> A getFirstAttribute(String name)
<A> List<A> getAttribute(String name)
Map<String, List<Object>> getAttributes()
```

- `getAttributes()`: maps all converted attribute names to lists of Java values.
- `getAttribute("...")`: retrieves a **list**, typically `null` if the attribute is absent; the generic `<A>` **does not guarantee the runtime type** of every element.
- `getFirstAttribute("...")`: retrieves the first value or `null`. Use only when the IdP contract defines a **single-valued** attribute and wrong cardinality has already been handled; this getter **does not automatically verify** that the list has exactly one value.
- Under default SAML configuration, `principal.getName()` usually maps from `NameID`; it is not synonymous with `getFirstAttribute("mail")`.

Brief example showing the distinction:

```java
// Fragment inside controller/service, only after SAML authentication succeeds.
String mail = principal.getFirstAttribute("urn:example:claims:mail");
List<Object> groups = principal.getAttribute("urn:example:claims:groups");
Map<String, List<Object>> attributes = principal.getAttributes();
```

This is only a fragment; it assumes `principal` is a `Saml2AuthenticatedPrincipal` variable provided by Spring Security. **Do not** write `List<String> groups = principal.getAttribute(...)` without checking types if the IdP might send XML/complex values.

### 6.1. Example Controller: Checked Scalar and List Handling

The example below targets a Spring MVC application with the Spring Security SAML2 Service Provider dependency and a configured IdP. It is a **source-level standalone Java class** inside a Spring project, though it will not run with plain `javac` alone because it requires Spring libraries and an active SAML-authenticated session.

Create `SamlProfileController.java`:

```java
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class SamlProfileController {

    private static final String MAIL = "urn:example:claims:mail";
    private static final String GROUPS = "urn:example:claims:groups";

    public record Profile(String subject, String mail, List<String> groups) {}

    @GetMapping("/api/me/saml")
    public Profile profile(
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {

        if (principal == null) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }

        String mail = requiredScalarString(principal.getAttribute(MAIL));
        List<String> groups = optionalStringList(principal.getAttribute(GROUPS));
        return new Profile(principal.getName(), mail, groups);
    }

    private static String requiredScalarString(List<Object> values) {
        if (values == null || values.size() != 1) {
            throw new ResponseStatusException(
                    HttpStatus.FORBIDDEN, "Invalid cardinality for mail");
        }
        Object raw = values.get(0);
        if (!(raw instanceof String)) {
            throw new ResponseStatusException(
                    HttpStatus.FORBIDDEN, "Invalid type for mail");
        }
        String value = (String) raw;
        if (value.isBlank()) {
            throw new ResponseStatusException(
                    HttpStatus.FORBIDDEN, "Empty required mail");
        }
        return value;
    }

    private static List<String> optionalStringList(List<Object> values) {
        if (values == null) {
            return List.of();
        }
        Set<String> distinct = new LinkedHashSet<>();
        for (Object raw : values) {
            if (!(raw instanceof String)) {
                throw new ResponseStatusException(
                        HttpStatus.FORBIDDEN, "Invalid groups value type");
            }
            String group = (String) raw;
            if (group.isBlank()) {
                throw new ResponseStatusException(
                        HttpStatus.FORBIDDEN, "Blank groups value");
            }
            distinct.add(group);
        }
        return new ArrayList<>(distinct);
    }
}
```

**Exact explanation:**

- `MAIL` and `GROUPS` are **names agreed upon by IdP/SP**; replace with actual names rather than `FriendlyName`. The example returns selected claims for the **currently logged-in user**. The endpoint must enforce `authenticated()` and appropriate personal data protection policies; never dump the entire assertion as JSON.
- `requiredScalarString` **checks that the list has exactly 1 element** before reading it. An email with multiple values is rejected per the example contract instead of silently picking one value.
- `optionalStringList` treats an absent attribute as an empty list and actively rejects non-String values. `LinkedHashSet` deduplicates while preserving occurrence order in the example data; **deduplication is only sensible for set-like groups**, not blindly for every attribute.
- In a real application, IdP schema errors may be reported with appropriate business errors/logs; `403` in the example is an illustrative choice for a claim failing the endpoint's policy, **not a mandatory SAML protocol status**. Avoid exposing overly detailed internal validation messages to clients.
- The generic `principal.getAttribute(MAIL)` is type-inferred by Java to `List<Object>`; at runtime every element still must be checked. Complex values require dedicated converters/validation.
- Because this code lives in Spring MVC, do not try to run it directly with `java SamlProfileController`; it requires Spring application startup, an IdP registration, and a valid SAML session.

### 6.2. SAML Login and Accessing the Principal

Minimal security configuration class (requires real dependencies and IdP config):

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/me/saml").authenticated()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());

        return http.build();
    }
}
```

Spring Security requires a `RelyingPartyRegistration`/trusted IdP metadata, signing certificates, `entityId`, ACS URL, and related settings. Default ACS paths and certificate/validator mechanisms vary by version/configuration, independent of the `/api/me/saml` controller. The controller is invoked only after authentication succeeds.

**Version note:** examples use common **Spring Security 6.x** APIs. When upgrading Spring Security major versions, consult the Javadoc and migration guide because authentication/principal and converter classes can change; never assume an old sample remains immutable forever.

## 7. Plain Java 17 Exercise: Counting and Validating Cardinality

To observe “single-valued vs. multi-valued” without connecting to an IdP, we simulate an **already-verified and converted map**. The following program **does not receive or verify SAML XML**; it solely interprets an existing map of value lists.

Save `AttributeCardinalityDemo.java`:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class AttributeCardinalityDemo {

    static String requiredOneString(
            Map<String, List<Object>> attributes, String name) {

        List<Object> values = attributes.get(name);
        if (values == null || values.size() != 1) {
            throw new IllegalArgumentException("Expected one value: " + name);
        }
        Object raw = values.get(0);
        if (!(raw instanceof String text) || text.isBlank()) {
            throw new IllegalArgumentException("Invalid string: " + name);
        }
        return text;
    }

    static List<String> optionalStringSet(
            Map<String, List<Object>> attributes, String name) {

        List<Object> values = attributes.get(name);
        if (values == null) {
            return List.of();
        }
        Set<String> distinct = new LinkedHashSet<>();
        for (Object raw : values) {
            if (!(raw instanceof String text) || text.isBlank()) {
                throw new IllegalArgumentException("Invalid value: " + name);
            }
            distinct.add(text);
        }
        return new ArrayList<>(distinct);
    }

    public static void main(String[] args) {
        Map<String, List<Object>> attributes = new LinkedHashMap<>();
        attributes.put("mail", List.<Object>of("linh@example.org"));
        attributes.put("groups", List.<Object>of(
                "portal-readers", "invoice-approvers", "portal-readers"));
        attributes.put("costCenters", List.of());

        System.out.println("mail = "
                + requiredOneString(attributes, "mail"));
        System.out.println("groups = "
                + optionalStringSet(attributes, "groups"));
        System.out.println("costCenters present = "
                + attributes.containsKey("costCenters"));
        System.out.println("costCenters values = "
                + attributes.get("costCenters").size());
        System.out.println("department present = "
                + attributes.containsKey("department"));

        try {
            requiredOneString(attributes, "groups");
        } catch (IllegalArgumentException ex) {
            System.out.println("groups as scalar = rejected");
        }
    }
}
```

Run with JDK 17 or newer:

```bash
javac AttributeCardinalityDemo.java
java AttributeCardinalityDemo
```

Exact stdout:

```text
mail = linh@example.org
groups = [portal-readers, invoice-approvers]
costCenters present = true
costCenters values = 0
department present = false
groups as scalar = rejected
```

Key observations:

- `mail` has exactly one string → readable as a scalar.
- `groups` has three raw values, with `portal-readers` appearing twice. The demo policy treats groups as a set, resulting in two groups. **Raw SAML does not automatically remove duplicate values.**
- `costCenters` has a key with an empty list → **present-empty**. `department` has no key → **absent**. Real-world SAML converters may behave differently when converting an Attribute with zero values; this demo simply distinguishes the two states in a Java map.
- Attempting to read `groups` as a scalar is rejected rather than silently picking the first element. That is the right business decision under the example's multi-valued contract.
- The output does not prove signature, subject, issuer, audience, or source-of-truth of any assertion. Real systems must verify SAML **before** running such helpers.

## 8. Mapping Attributes to the Domain Model

The same raw SAML payload should not be passed directly through every application layer. Create a boundary layer translating **external claims → internal profile** with an explicit schema:

```text
SAML Claim (issuer, NameFormat, Name, values)
       ↓ validation & policy
ExternalIdentity {
  issuer
  subjectId
  tenantId / registrationId
  email: Optional<String>
  department: Optional<String>
  groups: Set<String>
}
       ↓ identity linking / business authorization
InternalUser {
  userId
  tenantId
  active
  appRoles
  object-level permissions
}
```

The app does not have to use this exact model, but must have a **contract** for each field.

| Attribute | Illustrative contract | When violating contract |
| --- | --- | --- |
| `employeeId` | Exactly one, non-blank, String, right issuer/tenant | Reject account mapping / report attribute provisioning error |
| `mail` | Zero or one, valid email if app uses it for notifications | Do not use as unique key; per policy default or hide |
| `displayName` | Zero or one, length and escaping suitable for UI | Fall back to subject ID for display if appropriate |
| `groups` | Zero or many, each value is an allowed group ID | Absent → no group permissions; wrong type → reject or fail closed |
| `costCenters` | Zero or many, valid unit codes | Mark data missing rather than guessing a unit |
| `locale` | Zero or one per BCP 47 if profile specifies | Use application default locale |
| `isContractor` | Zero or one, boolean per profile type | Do not infer arbitrarily from `"false"`/`"0"` text |

### 8.1. Sensible Processing Order

1. **Verify SAML** via a trusted provider and matching registration; never read raw XML into the domain model before this.
2. **Resolve canonical identity** based on issuer/subject/tenant. Email is merely a claim, not a globally guaranteed stable ID.
3. **Select** attributes by agreed technical name/schema; if `NameFormat` must be checked, inspect it at the appropriate configuration/converter layer because the getter map may have already lost this context.
4. **Validate cardinality**: required 1 → exactly 1; optional 1 → 0 or 1; collection → 0..N within bounds.
5. **Validate type and content**: String/number/bool/complex XML, length, allowed character set, format per contract; malformed values must fail closed.
6. **Normalize** intentionally: trim/lowercase only when the business contract requires it. For example, group IDs may be case-sensitive; email normalization and Unicode handling need dedicated policies.
7. **Authorize**: map external groups against an allowlist of roles, or look up permissions from an internal database. Never trust every group string to be a valid Spring `ROLE_*`.
8. **Persist/cache minimally**: keep only needed claims, with TTL and refresh/revocation workflows when IdP state changes.

### 8.2. “Groups” Are Not Automatically `GrantedAuthority`

Suppose the IdP sends:

```text
groups = ["portal-readers", "invoice-approvers"]
```

The application can explicitly define:

| External group sent by IdP | Internal authority | Policy |
| --- | --- | --- |
| `portal-readers` | `ROLE_PORTAL_READER` | Read-only portal access |
| `invoice-approvers` | `INVOICE_APPROVE` | Allowed to approve if object/tenant policies also pass |
| Group outside allowlist | No corresponding authority | Never escalate privileges by default |

Spring Security does not automatically convert all `groups` into authorities matching the raw strings. Mapping to `GrantedAuthority` is an **application/configuration decision**. If using a custom authentication converter/authorities mapper, **preserve default SAML checks** and process claims **only after validation**. Never configure `hasRole("ADMIN")` merely based on a substring `"admin"` inside some group name.

With multiple tenants, distinguish source keys such as `(issuer, tenant, subject)` and scope group mappings per tenant. Tenant A's `admins` group must never automatically become `ROLE_ADMIN` in tenant B.

### 8.3. Do Not Auto-Pick “Primary” from a Multi-Valued List

If the IdP returns two emails or two addresses, `getFirstAttribute("mail")` hides the anomaly. The application needs to:

- Add a dedicated attribute like `preferredMail` with a single-valued contract, **or**
- Define a deterministic rule for primary from a specific data source/contract, **or**
- Reject ambiguity and ask IdP admins to fix the mapping.

Do not rely on XML ordering because the IdP may reorder elements in future assertions.

## 9. AttributeStatement and Requested Attributes in Metadata

The IdP can learn what data the SP needs through connection configuration or `AttributeConsumingService` in SAML SP metadata containing `RequestedAttribute` elements. However, **requested** only expresses interoperability need/terms; it does not prove the IdP released the data.

Illustrative metadata fragment:

```xml
<md:AttributeConsumingService
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    index="1">
    <md:ServiceName xml:lang="en">Learning Portal</md:ServiceName>
    <md:RequestedAttribute
        Name="urn:example:claims:mail"
        NameFormat="urn:oasis:names:tc:SAML:2.0:attrname-format:uri"
        isRequired="true"/>
    <md:RequestedAttribute
        Name="urn:example:claims:groups"
        NameFormat="urn:oasis:names:tc:SAML:2.0:attrname-format:uri"
        isRequired="false"/>
</md:AttributeConsumingService>
```

- `RequestedAttribute` in **metadata** differs from an actual `Attribute` in **AttributeStatement**.
- `isRequired="true"` expresses SP requirements per profile/agreement; the SP must still validate actual received data and handle absence per policy.
- Not every IdP automatically reads/honors metadata identically; some providers configure attribute release manually.
- If the SP needs a groups array, the contract must specify **true multi-valued encoding**: multiple `AttributeValue` elements; if a provider only emits a concatenated string, agree on a parser.
- Do not request excessive personal data “just in case” when the app only needs a few fields. Data minimization reduces exposure risk and complex sync constraints.

## 10. Integration Bugs and How to Diagnose Them

| Symptom | Common cause | Inspection and fix |
| --- | --- | --- |
| `getFirstAttribute("groups")` sees only one group | Using single-valued getter for a multi-valued attribute | Use `getAttribute("groups")`, verify `AttributeValue` count after validation |
| Getter returns `null` even though IdP “configured groups” | `Name`/`NameFormat` mismatch, missing release policy, wrong registration | Compare technical names/IdP config and verified principal output |
| Only `NameID` present, no `mail` | IdP did not emit `AttributeStatement` or mapping missing | Do not assume `NameID` automatically populates an email attribute |
| Receiving `"A;B;C"` as one string instead of 3 elements | IdP serialized list into a single value | Align schema, prefer multiple `AttributeValue` elements; parse only per contract |
| Casting to `List<String>` causes `ClassCastException` | Actual Java value has a different runtime type | Use `List<Object>`, check `instanceof` and specific parsers |
| `groups` has two duplicate values | IdP emitted duplicates, or aggregated mapping | With set semantics, deduplicate intentionally; test data characteristics |
| Attribute has two different `NameFormat`s with the same `Name` | Inconsistent namespaces/schemas | Inspect config/converter before collapsing to a string map key |
| `FriendlyName=mail` is set, while `Name` is an OID | Code looks up `mail` instead of canonical name | Use actual `Name`; never substitute `FriendlyName` as key |
| Overly broad permissions | Direct group → ROLE without allowlist or tenant check | Explicit permission mapping + resource-scoped policy |
| Group changed at IdP, yet app still sees old permissions | Session holds snapshot claims from prior login | Define refresh/re-login/revocation and timeouts |
| Assertion has `EncryptedAttribute`, yet getter misses it | SP lacks matching decryption key/config or decrypt failed | Inspect OpenSAML/Spring decryption setup and authentication errors |
| Complex XML attribute turns into cryptic string | Converter does not support complex types | Design proper codec/schema and test after validation |
| Production behaves differently from dev | Different IdP config, metadata/certificate versions | Version-control mappings, test with synthetic sample assertions, log safe error codes |

### 10.1. Debugging Workflow Without Leaking Data

1. Verify whether SAML login **succeeded**. If not, investigate signature/trust/time/audience/ACS first; never tweak cardinality to “ignore” authentication failures.
2. After validation in a test environment, log only key names, value counts, and Java class types—**never log identity values** unnecessarily. In production, even key details can be sensitive; use allowlists and strict audit controls.
3. Compare the mapping contract: exact `Name`, `NameFormat`, value count, type, and encoding; check IdP attribute release.
4. Test 0/1/2+ values for every constrained field, especially required scalars and groups.
5. Check the behavior of your exact Spring Security/OpenSAML version; do not rely on a SAML screenshot from a different provider version.
6. Only once the data is right, test domain mapping and authorization.

## 11. Security: Attributes Are Claims, Not a Pass to Bypass Authorization

### 11.1. Assertion Verification Is a Prerequisite

SAML attributes can transit the browser as XML/Base64, so the SP must verify:

- Signing key belongs to the right trusted IdP; signature is valid and protects **the exact assertion being consumed**.
- `Issuer`, SP `entityID`/`AudienceRestriction`, `Destination`, ACS/`Recipient`, and `InResponseTo` when applicable.
- `NotBefore`/`NotOnOrAfter`, subject confirmation, response validity, and anti-replay per policy.
- Decryption of `EncryptedAttribute` if present, using the right key/configuration; encryption **does not replace** signature validation.
- Registration/tenant/account mapping respects trust boundaries; never link users by email across two IdPs without a trusted workflow.

Defend against XML signature wrapping: never use one signed assertion to “green-light” authentication while reading attributes from another unsigned assertion in the same XML. Avoid hand-parsing raw `SAMLResponse` in controllers. Applications should consume the **verified** result produced by Spring Security.

### 11.2. How Cardinality Affects Security

**Scalar confusion:** If `isAdmin` is defined as a single-valued boolean yet the IdP sends `true` and `false`, picking the first or last element makes the outcome order-dependent. Reject contract-violating input or enforce a deterministic fail-safe policy.

**Group injection:** If groups is a list and code runs `contains("admin")` on a joined CSV string, `not-admin` can be misidentified as admin. Check **exact whole elements** after explicit mapping, never substrings.

**Type confusion:** Complex XML or numeric values materialized by converters into non-String Java objects can break unchecked casts, or calling `toString()` followed by naive parsing can yield unintended privileges.

**Cardinality explosion:** A multi-valued attribute can contain huge numbers of values or oversized values. Even when signed by an IdP, the application needs sensible bounds to avoid memory/log/CPU spikes; handle outliers explicitly.

**Duplicate ambiguity:** When the same key appears multiple times, components may merge/pick-first/pick-last differently. Configure a consistent policy, test adversarial payloads, and reject conflicts on sensitive attributes.

**XSS/PII:** `displayName`, `department`, and `mail` may contain strings unsafe for HTML or JSON logs. Apply escaping/output encoding on display; never return all of `getAttributes()` to clients by default.

**Authorization:** Group attributes are merely input to **mapping decisions**. Spring Security requires authority policies and permission checks on endpoints, tenants, and objects. Successful login does not automatically permit accessing all data.

### 11.3. Do Not Cache Claims Indefinitely

Assertions are typically short-lived for authentication, whereas application sessions can last longer. After SSO, attributes are held in the session or account cache depending on the application. If a group is revoked at the IdP, session permissions can become stale; sensitive systems need short timeouts, dynamic permission checks, or re-login/claim-refresh mechanisms. Agree on who is the **source of truth** for each attribute: IdP, HR, directory service, or application.

## 12. Integration Exercise with Acceptance Criteria

Design a SAML SP application with this contract:

```yaml
# Illustrative contract document, NOT Spring Boot properties
issuer: "https://idp.example.org/saml"
attributes:
  employeeId:
    samlName: "urn:example:claims:employeeId"
    type: string
    cardinality: "1..1"
  mail:
    samlName: "urn:example:claims:mail"
    type: string
    cardinality: "0..1"
  groups:
    samlName: "urn:example:claims:groups"
    type: string
    cardinality: "0..N"
    semantics: set
    allowedValues:
      - portal-readers
      - invoice-approvers
  costCenters:
    samlName: "urn:example:claims:costCenters"
    type: string
    cardinality: "0..N"
```

Reading the contract:

- `employeeId` is a required single value: missing, blank, or 2 values must **fail mapping**.
- `mail` may be omitted, but if present must be singular and pass format validation.
- `groups` is a multi-valued set, allowlisted when mapped to app roles. Unrecognized groups **do not** elevate privileges.
- `costCenters` is an optional list; do not auto-pick the first cost center as a “default.”
- `issuer` is the trusted IdP; this contract **does not replace** signature verification and SAML condition checks.

### 12.1. Suggested Test Suite

| Mocked post-validation input | Expected result |
| --- | --- |
| `employeeId=["E-123"]`, `groups=["portal-readers","invoice-approvers"]` | Accept; user has 2 groups, permissions strictly per mapping |
| `employeeId=[]` | Reject required scalar |
| `employeeId=["E-123","E-124"]` | Reject multiple values |
| `groups=[]` or missing | Accept user with no group-specific roles (if policy permits) |
| `groups=["portal-readers","portal-readers"]` | Deduplicate per set policy |
| `groups=["portal-readers,invoice-approvers"]` | One value; do not split unless contract specifies it |
| `groups=["ROLE_ADMIN"]` outside allowlist | Grant no admin authority |
| `mail=["a@example.org","b@example.org"]` | Reject 0..1 cardinality violation |
| `mail=[""]` | Reject if email must be non-blank when present |
| `costCenters=["C01","C02","C03"]` | Preserve all 3 values; do not auto-pick C01 |
| Group value is a non-String object | Reject/schema error; no blind casting |
| `FriendlyName` matches but `Name` is wrong | Do not mis-map to the required attribute |
| Same `Name` with different `NameFormat`, ambiguous config | Reject or fix mapping contract; do not silently merge |
| Invalid assertion signature or wrong audience | Reject authentication **before** touching mapping |
| Two assertions present, provider picks wrong content | Use attributes only from the verified assertion supported by the converter |

Testing **SAML authentication** requires a test IdP or fixtures signed with **test** keys in an isolated environment. Never send customer data or real assertions through public debugging tools. Testing **mapping logic** can use unit tests with plain `Map<String, List<Object>>`, as in the pure Java exercise.

### 12.2. Criteria for a Complete Integration

- Agreed with the IdP on `Name`, `NameFormat`, data type, cardinality, optional/required, and semantics for every attribute.
- Verified SAML artifacts and IdP/SP trust with Spring Security before reading claims.
- Every scalar is validated for exact 0..1 or 1..1; every multi-valued field preserves all values or normalizes via transparent rules.
- Never use `FriendlyName` as canonical key; never use `getFirstAttribute()` in a way that drops multi-valued data.
- Never grant permissions directly from unrecognized groups or unmapped attributes.
- Negative tests exist for missing/empty/duplicate/wrong-type values, multiple IdPs, and delimiter-containing groups.
- Refresh/revocation mechanisms exist when claims change, and logs never expose PII or raw assertions.
- Cross-checked your Spring Security version to confirm exact behavior of the SAML attributes converter.

## 13. Review Questions

**1. What does an `Attribute` with two `AttributeValue` elements mean?**  
It represents **two values** of the same attribute, not two single-valued attributes. For `groups`, read the list and apply policy; do not pick only the first element.

**2. Is `FriendlyName=groups` sufficient to select an attribute?**  
No. `FriendlyName` is a human-readable label, not a canonical identifier. Use `Name` and consider `NameFormat`/namespace per the IdP/SP contract.

**3. Does `NameID` automatically appear in `getAttributes().get("mail")`?**  
Not by default. `NameID` lives in `Subject`; a mail attribute appears only if the IdP emits the corresponding attribute and the converter maps it.

**4. Does `getFirstAttribute("department")` returning `null` mean there is no `AttributeStatement`?**  
You cannot conclude that. The attribute may be absent, the mapping name may differ, the value list may be empty, or the provider may handle data differently. Check the contract and verified principal output.

**5. Are two values `"reader"` and `"editor"` equivalent to one value `"reader,editor"`?**  
No. A delimited string is still a single `AttributeValue`; parse it only if the contract specifies that serialization.

**6. Does reading `groups` from an authenticated principal mean `ROLE_ADMIN` may be granted?**  
No. The authenticated principal carries claims from a trusted IdP, yet application permissions must still pass through allowlist/mapping and authorization checks.

**7. If a Spring Security getter returns `List<A>`, is it guaranteed to be `List<String>`?**  
No. Generics do not guarantee runtime types. Validate each element against the agreed schema.

**8. Why should email not always be used as the account linking key across IdPs?**  
Emails can change, collide, remain unverified, or be unstable; distinguish issuer, subject, and tenant, and use a controlled account-linking workflow.

## 14. Standards and Spring Security References

- [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf) – `AttributeStatement`, `Attribute`, `AttributeValue`, `NameFormat`, `FriendlyName`, and value rules.
- [OASIS SAML 2.0 Errata 05](https://docs.oasis-open.org/security/saml/v2.0/errata05/os/saml-v2.0-errata05-os.html) – clarifies attribute identification via `NameFormat` and `Name`.
- [Spring Security: Authenticating SAML2 Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html) – using `Saml2AuthenticatedPrincipal`, `getFirstAttribute`/`getAttribute`, and customization.
- [Spring Security: SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html) – role of `AttributeStatement` in the login flow and principal creation.
- [Spring Security 6.5 Javadoc: Saml2AuthenticatedPrincipal](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/authentication/Saml2AuthenticatedPrincipal.html) – Java type signatures of `getAttributes()`, `getAttribute()`, and `getFirstAttribute()`.
- [OWASP SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet) – safe assertion consumption, XML signatures, audience, and authentication conditions.

**Remember:** `AttributeStatement` carries the subject's **attributes**; each `Attribute` may carry **0, 1, or many `AttributeValue` elements**. Applications must enforce cardinality per the IdP/SP contract, check types, pick the right identifier names, preserve multi-valued data, and translate verified claims into permissions strictly according to their own policies.