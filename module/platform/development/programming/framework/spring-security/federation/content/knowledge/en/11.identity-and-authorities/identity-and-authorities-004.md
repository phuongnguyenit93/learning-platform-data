# Reading Single-Valued, Multi-Valued, and Missing Required Attributes

## 1. Why must SAML attributes be validated?

When a **Service Provider (SP)** uses Spring Security SAML2 to log in with an **Identity Provider (IdP)**, a SAML Assertion may contain identity and organizational attributes such as **employeeId, email, displayName, groups, department, costCenter**. After Spring Security/OpenSAML validates the SAMLResponse, the application needs to read these attributes for account linking, profile display, and business authorization.

However, SAML allows an **Attribute to have multiple AttributeValues**. From the application's perspective:

- A field expected to be **single-valued** might be missing, have two conflicting values, contain an empty value, or have an incompatible type.
- A **multi-valued** field might be a list of groups, roles, units, or entitlements; the list might be empty, contain duplicates, or contain elements of the wrong type.
- A **required** field for account linking might not be issued by the IdP due to mapping issues, privacy rules, schema changes, or tenant policies.
- A successful SAML login **does not guarantee** that every needed business attribute exists or is valid.
- Shortcuts like taking the "first value" or assigning a "default role" when an attribute is missing can lead to **mis-linked identities or wrongful privilege grants**.

**Core focus:** read from **Saml2AuthenticatedPrincipal** after SAML has been verified; distinguish optional/required and single/multi; check type, value, cardinality, and trusted source; handle missing data following the **fail closed** principle at the right layer.

Examples use **Java 17, Spring Boot 3.3.5, and Spring Security 6.x**. Details in Spring Security 7.x may differ because SAML APIs changed; verify against the Javadoc for your actual version.

## 2. Structure of AttributeStatement and AttributeValue

This is an illustrative XML fragment, **not a complete/signed Assertion**:

~~~xml
<saml:AttributeStatement
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">

  <saml:Attribute Name="employeeId">
    <saml:AttributeValue>EMP-041</saml:AttributeValue>
  </saml:Attribute>

  <saml:Attribute Name="groups">
    <saml:AttributeValue>team-java</saml:AttributeValue>
    <saml:AttributeValue>team-ops</saml:AttributeValue>
  </saml:Attribute>

  <saml:Attribute Name="displayName"
      FriendlyName="Display name">
    <saml:AttributeValue>Nguyễn An</saml:AttributeValue>
  </saml:Attribute>

</saml:AttributeStatement>
~~~

A real issued XML document also requires Response, Assertion, Issuer, signature, Subject/NameID, Conditions, and other protocol elements. **Do not use this fragment to log in or bypass signature verification.**

| Concept | Meaning |
| --- | --- |
| **Subject/NameID** | Subject identifier issued by the IdP. **Not a SAML Attribute named employeeId or email**; stability depends on the NameID format and IdP contract. |
| **AttributeStatement** | A group of attributes inside an Assertion; there may be multiple attributes. |
| **Attribute.Name** | Standard key identifying a SAML Attribute, which may be a short name or a URN/OID. |
| **Attribute.FriendlyName** | Human-readable label; do not use instead of Attribute.Name for reliable identification. |
| **Attribute.NameFormat** | Format of the Name, e.g., basic, URI, or unspecified. |
| **AttributeValue** | Data value; may have **0, 1, or many values**, and its type is not necessarily String. |
| **EncryptedAttribute** | Encrypted attribute; requires matching SP decryption credentials before reading. |

Names like **email**, **mail**, **urn:oid:0.9.2342.19200300.100.1.3**, or **http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress** can all represent email across different IdPs. Spring Security **does not automatically normalize all these names into email**. The IdP contract must specify the **actual Attribute.Name**, NameFormat where meaningful, type, cardinality, and release conditions.

### Multi-value is not CSV

An Attribute with two **AttributeValue** elements differs from a single AttributeValue containing **"team-java,team-ops"**. Do not split on commas automatically unless IdP and SP explicitly agreed on a CSV/custom format.

## 3. How does Spring Security 6.x convert attributes into a principal?

In Servlet SAML2 login, the general flow is:

~~~text
Browser POST SAMLResponse
  -> Saml2WebSsoAuthenticationFilter
  -> AuthenticationManager / OpenSAML authentication provider
  -> verify signature, issuer, destination, audience, time,
     SubjectConfirmation, Recipient, InResponseTo, replay policy
  -> decrypt Assertion/Attribute if needed
  -> extract AttributeStatement into Map<String, List<Object>>
  -> create Saml2Authentication + Saml2AuthenticatedPrincipal
  -> application's SecurityContext
~~~

Only **after** validation steps succeed should the application use the principal for business logic.

APIs of **Saml2AuthenticatedPrincipal** in Spring Security 6.x:

| API | Return value | Proper usage |
| --- | --- | --- |
| **getName()** | String principal name, typically from NameID by default provider. | Do not automatically treat as a stable employeeId/email. |
| **getAttributes()** | **Map<String, List<Object>>**. | Preferred for strict type and cardinality checks. |
| **getAttribute(name)** | Generic **List<A>**, may be **null** if attribute is absent. | Use for multi-value when type from IdP is known for certain. |
| **getFirstAttribute(name)** | Generic **A**, may be **null** when absent. | Convenient only when contract truly guarantees single value. |
| **getRelyingPartyRegistrationId()** | String registrationId of the SP–IdP relationship. | Helps select schema/mapping for the authenticated partner. |

Quick read example after SAML login:

~~~java
// Only an illustrative snippet, inside a controller with a valid principal
String displayName = principal.getFirstAttribute("displayName");
List<String> groups = principal.getAttribute("groups");
~~~

**Limitations:** getFirstAttribute only takes the **first element**, without checking whether the list has two values. getAttribute uses generics without checking each **Object** at runtime. If the IdP sends groups as a non-String type, iterating a List<String> can throw ClassCastException. For identifiers or permissions, use **getAttributes()** and verify elements via **instanceof String**.

In Spring Security 7.x, several legacy SAML principal APIs are marked deprecated and replaced by a new accessor/authentication model; this lesson intentionally uses **Security 6.x**.

## 4. Clear policy for four attribute categories

| Category | Example | Missing / empty | Multiple / wrong type |
| --- | --- | --- | --- |
| **Optional single** | displayName | May use Optional.empty or a default display label. | Should report contract error, not silently take the first value on wrong cardinality. |
| **Required single** | stableSubjectId, employeeId | **Reject** account linking/functionality requiring identity. | **Reject** due to ambiguity or invalid type. |
| **Optional multi** | groups for display info | May return an empty list; **never auto-grant permissions**. | Check each element; deduplicate only if policy permits. |
| **Required multi** | at least one required entitlement code | **Reject** functionality requiring membership. | Check each element and allowlist; reject unknown values. |

For **required single**, distinguish:

- **MISSING:** map lacks the key.
- **EMPTY:** key exists, but list is empty, or string is empty or blank.
- **CARDINALITY:** map has two or more values even if each looks valid.
- **TYPE:** a value is not of the agreed type (e.g., Integer instead of String).
- **FORMAT:** a String has invalid characters, length, or format per contract.
- **TRUST:** data did not come from an allowed IdP/registration, or SAML has not been validated.

**Never default employeeId to "guest", tenantId to "default", or pick the first element of a list arbitrarily.** If an attribute affects identification/authorization, any anomaly must **fail closed**.

### Optional does not mean ignoring all errors

If displayName is **missing**, you can display "Not provided". But if displayName has **three values** when the IdP contract only allows one, that is a **schema violation**; depending on the system, you can omit displaying it and log a warning, or reject the business step. Never conflate **missing** with **invalid present value** in security decisions.

## 5. Multi-valued attributes and access permissions

**groups, memberOf, roles, entitlements** are typically multi-valued. A group may be duplicated, an IdP may cap the number of groups in an Assertion, or omit releasing groups for certain accounts.

Example data after validation:

~~~text
groups = ["team-java", "team-ops", "team-java"]
~~~

If the contract treats groups as a **membership set**, you can deduplicate while preserving first-seen order. If group order carries meaning, do not replace it with a Set automatically. Do not automatically lowercase or trim every group/identifier when the contract is case- or whitespace-sensitive.

**Authorization must follow an application allowlist**:

| Verified registration | Group in Assertion | Internal authority that may be granted |
| --- | --- | --- |
| corp | app-reports-view | REPORT_READ |
| corp | app-reports-edit | REPORT_WRITE |
| partner | app-reports-view | Do not auto-grant unless partner policy allows |
| Any | admin, superuser, or unknown value | Never auto-create ROLE_ADMIN |

Do not feed every value from the IdP directly into **SimpleGrantedAuthority("ROLE_" + value)** without an agreed allowlist and tenant scope. If groups is **missing**, grant no corresponding permissions by default; never assume missing groups means the user belongs to all groups.

**getAttributes() is not always live data:** once the SP creates a local HttpSession, attributes reflect the Assertion at login time. If a group/role is revoked at the IdP mid-session, the application needs appropriate session lifetime, reauthentication, synchronization, or server-side authorization checks. Never claim that changing a group at the IdP immediately updates all SP sessions.

## 6. Designing a standalone Java 17 validator class

Use an **AttributeReader** class accepting the exact **Map<String, List<Object>>** type. It checks String elements, cardinality, and blanks, classifying causes **without leaking sensitive values**. This is a **post-SAML-validation** attribute reader; it **does not** verify signatures or process raw SAMLResponses.

### 6.1. AttributeReader.java

Create **src/main/java/com/example/samlattrs/AttributeReader.java**:

~~~java
package com.example.samlattrs;

import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

public final class AttributeReader {
    private final Map<String, List<Object>> attributes;

    public AttributeReader(Map<String, List<Object>> attributes) {
        this.attributes = Objects.requireNonNull(attributes, "attributes");
    }

    public String requiredSingle(String name) {
        List<Object> values = attributes.get(name);
        if (values == null) {
            throw new AttributeProblem("MISSING", name);
        }
        if (values.isEmpty()) {
            throw new AttributeProblem("EMPTY", name);
        }
        if (values.size() != 1) {
            throw new AttributeProblem("CARDINALITY", name);
        }
        return nonBlankString(values.get(0), name);
    }

    public Optional<String> optionalSingle(String name) {
        List<Object> values = attributes.get(name);
        if (values == null || values.isEmpty()) {
            return Optional.empty();
        }
        if (values.size() != 1) {
            throw new AttributeProblem("CARDINALITY", name);
        }
        Object raw = values.get(0);
        if (!(raw instanceof String value)) {
            throw new AttributeProblem("TYPE", name);
        }
        String normalized = value.strip();
        return normalized.isEmpty()
                ? Optional.empty() : Optional.of(normalized);
    }

    public List<String> optionalMany(String name) {
        List<Object> values = attributes.get(name);
        if (values == null || values.isEmpty()) {
            return List.of();
        }

        LinkedHashSet<String> distinct = new LinkedHashSet<>();
        for (Object raw : values) {
            distinct.add(nonBlankString(raw, name));
        }
        return List.copyOf(distinct);
    }

    public List<String> requiredMany(String name) {
        List<String> values = optionalMany(name);
        if (values.isEmpty()) {
            String code = attributes.containsKey(name) ? "EMPTY" : "MISSING";
            throw new AttributeProblem(code, name);
        }
        return values;
    }

    private static String nonBlankString(Object raw, String name) {
        if (!(raw instanceof String value)) {
            throw new AttributeProblem("TYPE", name);
        }
        String normalized = value.strip();
        if (normalized.isEmpty()) {
            throw new AttributeProblem("EMPTY", name);
        }
        return normalized;
    }

    public static final class AttributeProblem extends IllegalArgumentException {
        private final String code;

        public AttributeProblem(String code, String name) {
            super("Invalid SAML attribute " + name + " (" + code + ")");
            this.code = code;
        }

        public String code() {
            return code;
        }
    }
}
~~~

### Explaining the design decisions

1. **Map<String, List<Object>>** mirrors the Spring 6.x API without casting the entire List.
2. **requiredSingle** demands exactly one non-empty String value, preventing arbitrary selection.
3. **optionalSingle** permits absence while still failing if a present value has an invalid type/cardinality.
4. **optionalMany** returns List.of() when absent; when data is present, every element is checked.
5. **LinkedHashSet** deduplicates and preserves first-seen order; use only when business logic treats values as a membership set.
6. **AttributeProblem.code()** allows logging error codes instead of raw attribute values.
7. **strip()** is an illustrative rule; apply only if the identity contract allows stripping leading/trailing whitespace. For identifiers where whitespace is significant, change the rule.
8. The code does not yet enforce regex/max-length/allowlists; add those per schema before production.

### 6.2. Test program requiring no Spring or IdP

Save **src/main/java/com/example/samlattrs/AttributeReaderDemo.java**:

~~~java
package com.example.samlattrs;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class AttributeReaderDemo {
    public static void main(String[] args) {
        Map<String, List<Object>> values = new LinkedHashMap<>();
        values.put("employeeId", List.of("EMP-041"));
        values.put("groups", List.of("team-java", "team-ops", "team-java"));
        values.put("email", List.of("a@example.org", "b@example.org"));
        values.put("quota", List.of(42));
        values.put("emptyValue", List.of());

        AttributeReader reader = new AttributeReader(values);

        System.out.println("employeeId=" +
                reader.requiredSingle("employeeId"));
        System.out.println("groups=" + reader.optionalMany("groups"));
        System.out.println("department=" +
                reader.optionalSingle("department").orElse("(missing)"));

        printError("email", () -> reader.requiredSingle("email"));
        printError("emptyValue",
                () -> reader.requiredSingle("emptyValue"));
        printError("quota", () -> reader.requiredSingle("quota"));
        printError("unknown", () -> reader.requiredSingle("unknown"));
    }

    private static void printError(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + "=VALID");
        }
        catch (AttributeReader.AttributeProblem ex) {
            System.out.println(label + "=" + ex.code());
        }
    }
}
~~~

Run with JDK 17+ from the project root directory:

~~~bash
javac -d out src/main/java/com/example/samlattrs/AttributeReader.java src/main/java/com/example/samlattrs/AttributeReaderDemo.java
java -cp out com.example.samlattrs.AttributeReaderDemo
~~~

**Exact stdout:**

~~~text
employeeId=EMP-041
groups=[team-java, team-ops]
department=(missing)
email=CARDINALITY
emptyValue=EMPTY
quota=TYPE
unknown=MISSING
~~~

The **email** field has two values so it returns **CARDINALITY**, rather than picking the first address. **quota** has an Integer instead of a String so it returns **TYPE**, rather than auto-converting to "42". **unknown** missing a key and **emptyValue** having an empty list are two distinct cases. **department** is optional so absence is allowed. **groups** is deduplicated per the illustrative policy. The demo does not verify SAML signatures and cannot log into an IdP.

### Extending validation per contract

- For **email**, only parse/normalize after deciding whether email is strictly for contact or for account linking; never assume email is an immutable global ID by default.
- For **employeeId**, add rules for format, length, uniqueness per issuer, and active account status.
- For **groups**, add a maximum value count and per-registration allowlist; never grant permissions for unknown groups.
- For **Date/Integer/Boolean**, define explicit type conversions and catch parse failures; never use **String.valueOf** as a general solution.
- For Unicode, define normalization and case sensitivity explicitly; never auto-convert identifier casing.
- For sensitive data, log **field names and error codes**, never raw attribute values.

## 7. Spring Boot 3.3.5 example reading principal after SAML login

The following application is a **Spring SAML2 Service Provider** with one IdP registration. It completes the full login flow only when a real IdP has registered the **SP entityID, ACS, and certificate/trust**, and releases attributes matching the contract.

### 7.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>saml-attributes-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <repositories>
        <repository>
            <id>shibboleth-releases</id>
            <url>https://build.shibboleth.net/maven/releases/</url>
            <snapshots><enabled>false</enabled></snapshots>
        </repository>
    </repositories>
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
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 7.2. application.yml

**src/main/resources/application.yml**

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              metadata-uri: ${SAML_IDP_METADATA_URI}

server:
  port: 8080
~~~

**SAML_IDP_METADATA_URI** is an environment variable holding a real, organization-approved IdP metadata URL. To log in, a real IdP with matching SP entityID/ACS and trust is required; this example does not provide an IdP or issue Assertions itself.

### 7.3. Application and security configuration

**src/main/java/com/example/samlattrs/SamlAttributesApplication.java**

~~~java
package com.example.samlattrs;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SamlAttributesApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlAttributesApplication.class, args);
    }
}
~~~

**src/main/java/com/example/samlattrs/SecurityConfig.java**

~~~java
package com.example.samlattrs;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

**Note:** Spring Security handles the **/login/saml2/sso/{registrationId}** callback automatically. Do not write a controller receiving SAMLResponse to parse it manually.

### 7.4. Controller using AttributeReader

**src/main/java/com/example/samlattrs/ProfileController.java**

~~~java
package com.example.samlattrs;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class ProfileController {
    @GetMapping("/")
    public String home() {
        return "SAML attributes SP ready";
    }

    @GetMapping("/account")
    public Map<String, Object> account(
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {

        if (principal == null) {
            throw new ResponseStatusException(
                    HttpStatus.UNAUTHORIZED, "Authentication required");
        }

        AttributeReader reader = new AttributeReader(principal.getAttributes());

        try {
            String employeeId = reader.requiredSingle("employeeId");
            List<String> groups = reader.optionalMany("groups");
            String displayName = reader.optionalSingle("displayName")
                    .orElse("Unknown");

            Map<String, Object> result = new LinkedHashMap<>();
            result.put("employeeId", employeeId);
            result.put("displayName", displayName);
            result.put("groups", groups);
            return result;
        }
        catch (AttributeReader.AttributeProblem problem) {
            throw new ResponseStatusException(
                    HttpStatus.FORBIDDEN,
                    "Required identity data is unavailable");
        }
    }
}
~~~

Uses **AttributeReader.java** created in Section 6, in the same package **com.example.samlattrs**.

Run from the directory containing pom.xml:

~~~bash
mvn spring-boot:run
~~~

**Verifiable results:**

- **GET http://localhost:8080/** returns the exact body **SAML attributes SP ready**.
- **GET http://localhost:8080/account** when unauthenticated triggers SAML login if the IdP registration is valid.
- After IdP login and sending a valid Assertion with **employeeId, groups, displayName** as Strings, the endpoint returns JSON such as:

~~~json
{
  "employeeId": "EMP-041",
  "displayName": "Nguyễn An",
  "groups": ["team-java", "team-ops"]
}
~~~

- If **employeeId is missing/empty/multi-valued/wrong type**, the controller returns **403** per policy. For missing groups, it returns **[]** without inferring admin rights. For missing displayName, it uses the display label **Unknown**.
- NameID, attribute values, or SSO results cannot be guaranteed without a real IdP, valid certificate/metadata, and matching release policy.

**Crucial distinction:** the controller returning **403** due to a missing required employeeId **does not mean SAML login failed**. Spring may already have established a valid local SecurityContext/session. If employeeId is a **mandatory application-wide prerequisite**, enforce it in authentication conversion/account provisioning **after SAML authentication**, returning an authentication failure before permitting an application session.

## 8. Required attribute at login or at the endpoint?

### Required for account linking

If stableSubjectId/employeeId is necessary to know **who this user is in the internal system**, steps should include:

1. Verify SAMLResponse against IdP registration, signature, issuer, time, audience, recipient, and response correlation.
2. Determine the attribute schema by **registrationId/IdP**, avoiding mixing two organizations.
3. Read required-single by exact Attribute.Name.
4. Verify String, **size=1**, non-blank, and format/length per schema.
5. Link to the local account via an **IdP-namespaced** key, such as the issuer + stable subject pair; never use email alone to bind accounts.
6. Check local account active state, tenant, lifecycle, deprovisioning, and status.
7. If any step fails, do not create default accounts/authorities or accidentally fall back to a shared guest.

Enforce this before issuing application identity when policy demands it. In Spring Security 6.x, you can use a **custom authentication converter after default SAML validation** or a version-appropriate provisioning/hook layer; preserve all framework validations and test that missing required attributes actually block login.

### Required for a specific feature

If **costCenter** is needed to submit invoices, a user can log in validly yet:

- Without costCenter -> **cannot submit invoices**, returning 403 per business rules.
- Can still view profile or other pages not requiring costCenter.
- Never infer costCenter from email domain or groups.
- Never apply "broad default permissions" because group/costCenter is missing.

Good security means **failing closed in the right place**, without necessarily locking out the entire application if only one feature needs extra data.

### Metadata RequestedAttribute does not enforce at runtime

In **SPSSODescriptor**, metadata can declare:

~~~xml
<md:AttributeConsumingService
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    index="0">
  <md:ServiceName xml:lang="vi">Ứng dụng nội bộ</md:ServiceName>
  <md:RequestedAttribute Name="employeeId" isRequired="true"/>
</md:AttributeConsumingService>
~~~

This is an **attribute request during metadata exchange**. Do not assume that merely setting **isRequired=true** guarantees the IdP will release the value or that Spring Security will automatically fail login if it is missing. The application must still validate values at **runtime** and agree on an attribute release policy with the IdP.

## 9. Multi-IdP / multi-tenant design

There may be two registrations:

| Policy | IdP corp | IdP partner |
| --- | --- | --- |
| Stable identifier | employeeId | externalSubjectId |
| Email | mail | claims/emailaddress |
| Groups | memberOf | groups |
| Display name | displayName | fullName |
| Tenant code | corp | partner |

**Do not reuse the same Attribute.Name across all IdPs without a contract.** After login, obtain the verified registrationId to select the mapping from an **IdP allowlist**. One IdP can issue an employeeId colliding with another IdP; therefore never use employeeId alone as a cross-organization primary key.

**Never let an unauthenticated client choose the mapping/certificate/metadata URL** via a request parameter like tenant=... to gain permissions. Issuer or claim facts in a pre-validation SAMLResponse are untrusted inputs; rely on IdP trust configuration and completed Authentication.

If group overage or attribute release policy causes groups to be missing, treat the corresponding permissions as **unproven**. Coordinate with the IdP/admin and account sync processes rather than assuming "missing groups = full permissions".

## 10. Properly testing single-valued, multi-valued, and missing cases

Use a sandbox IdP issuing **valid signed SAMLResponses** to test each case. If you hand-edit signed XML, signature errors may occur before attribute reading, preventing conclusions about business validation.

| # | Data after SAML validation | Policy | Expected result |
| --- | --- | --- | --- |
| 1 | employeeId=["EMP-041"] | Required single | Accept if remaining schema/account mapping is valid. |
| 2 | employeeId absent | Required single | **MISSING**, reject identity binding operation. |
| 3 | employeeId=[] | Required single | **EMPTY**. |
| 4 | employeeId=[""] | Required single | **EMPTY**. |
| 5 | employeeId=["  "] | Required single | **EMPTY** per strip policy. |
| 6 | employeeId=["EMP-041","EMP-042"] | Required single | **CARDINALITY**, do not pick the first value. |
| 7 | employeeId=[42] | Required String | **TYPE**. |
| 8 | groups=["team-java","team-ops"] | Optional multi | Accept type-checked list. |
| 9 | groups absent | Optional multi | Empty list; grant no permissions from groups. |
| 10 | groups=["team-java","team-java"] | Optional multi set | Deduplicate if contract permits. |
| 11 | groups=["team-java",42] | Optional multi String | **TYPE**, do not treat unexpected data as a group. |
| 12 | groups=[""] | Required multi | **EMPTY**. |
| 13 | displayName absent | Optional single | May display Unknown. |
| 14 | email has 2 values | Expected single | **CARDINALITY**. |
| 15 | IdP renames mail to email | Schema mapping | Report missing/contract drift; fix mapping. |
| 16 | IdP A and B share employeeId | Multi-IdP binding | Do not auto-link to the same account. |
| 17 | unknown group "super-admin" | Authorization | Never auto-grant admin rights. |
| 18 | Invalid Response signature with nice employeeId | Authentication | Reject at SAML layer before entering app. |
| 19 | EncryptedAttribute without SP decryption key | Authentication | Do not use undecrypted value; handle SAML error. |
| 20 | NameID present but employeeId missing | Required identity | Do not substitute NameID for employeeId without a contract. |
| 21 | costCenter missing | Required on finance endpoint | Return 403 at endpoint, not necessarily failing login. |
| 22 | Metadata isRequired=true but IdP omits attribute | Contract/runtime | Reject functionality needing it, contact IdP admin. |

**A negative test passes** when the system **properly rejects the risk**, not by trying to make every case log in.

In JUnit 5 unit tests, add **AttributeReader** checks for null/missing/empty/blank, wrong types, multiple values, Unicode, oversized values, deduplication, and allowlists. In integration tests, use signed SAMLResponses from a test IdP to cover both authentication and attribute mapping.

## 11. Common issues and resolutions

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| getFirstAttribute("email") returns null | IdP uses mail/another URN or does not release it. | Check Attribute.Name, claim mapping, and IdP release policy. |
| getAttribute("groups") returns null | Group attribute missing/renamed/IdP limits groups. | Do not auto-grant permissions; check schema and IdP admin. |
| ClassCastException processing groups | List<Object> contains non-String elements. | Iterate Object with instanceof, never cast blindly. |
| /account returns 403 despite successful SAML login | Required employeeId violates contract. | Investigate schema release; distinguish business deny from login failure. |
| One of two employeeId values picked wrongly | getFirstAttribute used for required-single. | Check size==1 and reject CARDINALITY. |
| User jumps tenants | Account linked solely by email/employeeId without issuer. | Use stable subject with IdP/tenant namespace; verify local account. |
| Unknown group unexpectedly becomes ROLE_ADMIN | Direct mapping of every group to an authority. | Per-registration allowlist, deny by default. |
| SAML validation fails before obtaining principal | Signature, issuer, audience, time, subject confirmation, or decryption error. | Fix trust/metadata/certs; never bypass validator. |
| AttributeName changes after IdP upgrade | Schema drift. | Claim schema contract and versioning, regression tests. |
| Metadata isRequired=true yet data missing | Metadata does not force IdP runtime release automatically. | Validate at runtime and coordinate with partner. |
| Displayed data contains HTML/JS | Attribute treated as trusted content on output. | Context-appropriate output escaping; never inject raw into HTML. |
| Group changes do not take effect immediately | Local SP session caches attributes at login time. | Configure reauthentication/session sync/revocation policy accordingly. |

### Logging and privacy

Log only safe fields such as **registrationId**, allowlisted attribute names, error codes **MISSING/EMPTY/TYPE/CARDINALITY**, and a correlation ID. Never log raw SAMLResponse, email, real employeeId, personal attributes, private keys, or session cookies.

Example:

~~~text
event=saml_attribute_contract_failed registration=corp attribute=employeeId code=MISSING
~~~

Never return error messages containing sensitive attribute values to the browser. Provide guidance to contact IdP administrators to fix mapping rather than relaxing security rules.

## 12. Common pitfalls

1. **getFirstAttribute for required-single**: picks one element without detecting a second value.
2. **Trusting generic List<String> as a runtime guarantee**: getAttributes() holds List<Object>.
3. **Filling default employeeId/tenant when missing**: can mis-link accounts.
4. **Confusing FriendlyName with Attribute.Name**: lookup fails when IdP uses URNs/OIDs.
5. **Splitting group CSVs automatically** without an agreement.
6. **Treating email as an immutable identity** even though IdPs can change/reassign it.
7. **Omitting issuer/tenant from account keys** when supporting multiple IdPs.
8. **Granting ROLE_ADMIN when groups are missing** instead of denying.
9. **Auto-creating authorities from any external group** instead of allowlist mapping.
10. **Calling String.valueOf on arbitrary Objects** and using the result as a security identifier.
11. **Reading raw SAMLResponse before framework verification**.
12. **Assuming a controller 403 blocked login**, even though a session may already exist.
13. **Believing RequestedAttribute isRequired guarantees runtime claim presence**.
14. **Trimming/case-folding all identifier names** without schema rules.
15. **Logging raw attributes/Responses**, leaking private data.
16. **Disabling signature validation due to bad/missing attributes**, fixing the wrong layer and breaking trust.

## 13. Review questions

**Q1.** How do getFirstAttribute("groups") and getAttribute("groups") differ?  
**Answer:** getFirstAttribute returns the first value or null, while getAttribute returns a list or null. Use the list when expecting multiple groups and check types/cardinality per contract.

**Q2.** employeeId=["EMP-041","EMP-042"] is validly signed by the IdP. Can EMP-041 be used to link the account?  
**Answer:** Not if the contract requires single-valued; it must be rejected as **CARDINALITY**.

**Q3.** groups is absent, yet SAML login succeeded; can admin be granted?  
**Answer:** No. Missing groups do not prove membership; permissions follow deny by default and allowlist mapping.

**Q4.** Attribute.Name is urn:oid:0.9.2342.19200300.100.1.3 and FriendlyName is email. Will getAttribute("email") definitely return data?  
**Answer:** No; you must look up the exact Attribute.Name/id mapped by the IdP and Spring.

**Q5.** Number 42 appears in employeeId; can String.valueOf be used to proceed?  
**Answer:** Not by default. Type mismatches against the contract require **TYPE** failure or an explicitly approved converter.

**Q6.** Controller /account returns 403 when employeeId is missing. Was the entire SAML login rejected?  
**Answer:** Not necessarily; Saml2Authentication may already have been created. To block login, place required claim policy in post-validation auth conversion/provisioning.

**Q7.** Metadata has RequestedAttribute isRequired=true, yet the IdP omits the attribute. Is the application automatically protected?  
**Answer:** Do not assume so; the application must check actual received attributes and enforce a fail-closed policy.

**Q8.** Two IdPs issue the same employeeId; can they merge into one local account?  
**Answer:** Only with an approved account-linking policy; by default separate them by IdP/issuer or stable subject namespace.

## 14. Standard references

1. [Spring Security 6.5 API – Saml2AuthenticatedPrincipal](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/authentication/Saml2AuthenticatedPrincipal.html): getAttribute, getFirstAttribute, getAttributes, getRelyingPartyRegistrationId.
2. [Spring Security – Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): using Saml2AuthenticatedPrincipal, mapping authorities, and customization. Consult the reference matching your Spring Security version when implementing.
3. [Spring Security – SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): Response verification and mapping AttributeStatement to Map<String,List<Object>>.
4. [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): AttributeStatement, Attribute, AttributeValue, Name/NameFormat/FriendlyName.
5. [OASIS SAML 2.0 Metadata](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf): AttributeConsumingService and RequestedAttribute/isRequired.

**Key takeaway:** SAML attributes can be **single-valued, multi-valued, or missing**. After Spring Security validates the Assertion, the application must verify **presence, cardinality, type, format, and trusted source** before using them for identity or permissions. For required attributes, **fail closed at the right layer**; for optional attributes, use fallbacks only when security is unaffected.
