# DTOs and Restricting Accepted or Returned Data Fields

## 1. The Security Problem DTOs Solve

When an API receives JSON from a client or returns JSON to a client, **not every field present in an entity/domain model is allowed to cross the HTTP boundary**. For example, an accounts table may have `id`, `email`, `displayName`, `role`, `admin`, `passwordHash`, `internalNote`, `locked`, and `createdAt`. A user permitted to change their display name should likely send only `displayName`; a profile page should likely receive only `id`, `email`, and `displayName` when reading.

A **DTO (Data Transfer Object)** is a data type created to represent the exchange contract at a boundary, such as an API request or response. Using dedicated DTOs per operation makes it explicit:

- **Input:** **which fields**, which data types, and which validation rules the client is allowed to supply.
- **Output:** **which fields** the client is allowed to **see**, on which endpoint, and in which permission context.
- **Mapping:** the service decides **which fields are actually updated** and which data must come from the authenticated session or server.
- **API stability:** internal table/entity changes do not automatically become public JSON changes.

This is a mechanism for **reducing attack surface and reducing data exposure** within Spring Security's *Data Protection* topic. DTOs **do not replace** authentication, authorization, ownership checks, validation, CSRF, transport encryption, or tenant data filtering; they are one control layer that must work together with those layers.

Goals: recognize **mass assignment/overposting** and **excessive data exposure**; design separate input DTOs and output DTOs; restrict accepted/returned fields; apply Bean Validation; perform allowlist mapping instead of copying all properties; and test attack cases as well.

## 2. Two Classic Vulnerability Patterns

### 2.1. Accepting Too Many Fields: Mass Assignment / Overposting

Suppose a profile update endpoint accepts the entity directly:

```java
@PutMapping("/api/me")
public Account update(@RequestBody Account body) {
    return repository.save(body); // Overposting-vulnerable example: DO NOT use
}
```

Entity `Account` has `admin` and `role` properties. A client can send:

```json
{
  "displayName": "Mai",
  "email": "mai@example.test",
  "admin": true,
  "role": "ADMIN"
}
```

If code binds and saves the entire entity without restriction, the client-supplied `admin`/`role` fields can alter privileges. This is **mass assignment (CWE-915)**: HTTP data controls properties the sender is not allowed to modify. An endpoint does not need to document dangerous field names; attackers can guess or probe property names.

Primary defense: define a request DTO containing only fields the client may edit and **update each property in the service using an allowlist**. Checking permissions on the target object is a separate layer that must never be skipped.

### 2.2. Returning Too Many Fields: Excessive Data Exposure

Another mistake is returning the whole entity:

```java
@GetMapping("/api/me")
public Account me() {
    return repository.findCurrentAccount(); // Data-exposure example: DO NOT use
}
```

If Jackson serializes every visible property, the response risks leaking `passwordHash`, `internalNote`, `mfaSecret`, lock status, internal tokens, or another tenant's data. **Hiding fields in the frontend provides no protection**: callers can still see the JSON in the Network tab or with `curl`.

Primary defense: response DTOs contain only fields permitted to be returned. For sensitive fields, consider projecting directly in the DB query so extra data is never even read; endpoints and services must still enforce authorization policies.

### 2.3. Comparing Three Layers of Defense

| Layer | Purpose | Does it solve every flaw alone? |
| --- | --- | --- |
| Request/Response DTO | Restricts **data shape** at the API boundary | No: permitted input fields still require authorization checks |
| Bean Validation like `@NotBlank`, `@Email`, `@Size` | Restricts **values and formats** | No: `"ADMIN"` may be validly formatted yet unauthorized |
| Spring Security, service authorization, tenant/object checks | Decides **who can do what on which object** | No: still need to avoid returning secret fields and accidental binding |

## 3. Distinguishing Entities, Input DTOs, Output DTOs, and Domain Commands

A typical flow:

```text
Client JSON
   │
   ▼
@RequestBody → Jackson deserialization
   │
   ▼
UpdateProfileRequest (allowlist input)
   │
   ▼
@Valid + caller authentication + authorization
   │
   ▼
ProfileService: update only permitted fields
   │
   ▼
Account entity / database
   │
   ▼
ProfileResponse (allowlist output)
   │
   ▼
Jackson serialization → HTTP JSON
```

| Object type | Purpose | Should it be used directly at HTTP? |
| --- | --- | --- |
| JPA entity / persistence model | Stores state, DB relations, metadata, internal fields | Avoid accepting/returning raw entities on public APIs |
| `CreateAccountRequest` | Fields allowed to be provided on creation | Yes, at the creation endpoint |
| `UpdateProfileRequest` | Fields allowed when editing a profile | Yes, at the profile-edit endpoint |
| `ProfileResponse` | Fields allowed to be shown to the account owner | Yes, at read/edit endpoints |
| `PublicProfileResponse` | Smaller subset visible to other users | Yes, at public endpoints |
| `AdminAccountResponse` | Extra fields granted only to administrators | Yes, **after** verifying ADMIN privileges |
| Domain command | Validated/normalized business command | Usually sits between controller and service |

**You do not need a DTO for every Java class.** Create DTOs by *contract* and *access policy*: two endpoints with the same shape, semantics, and policy can share a DTO. Conversely, merging create, patch, admin, and public operations into one giant `AccountDto` with dozens of nullable fields usually breaks clear boundaries.

**An input DTO is not trusted data just because it is a Java type.** Jackson has parsed JSON into an object, yet the client still controls every value inside the declared fields. The service must normalize and validate them.

## 4. Designing Allowlists by Business Use Case

Example account API with `PUT /api/profile`:

| Internal account field | May client send to edit? | May client see in `ProfileResponse`? | Who controls it? |
| --- | --- | --- | --- |
| `id` | **No** | Yes | Server / database |
| `username` | Not in this profile-edit operation | Optional per contract | Identity system |
| `displayName` | **Yes** | **Yes** | User within policy limits |
| `email` | Yes if business allows, may need separate verification | Yes for the owner | User + verification flow |
| `role` | **No** | Not in standard profile | Permission management workflow |
| `admin` | **No** | No | Server / authorization policy |
| `passwordHash` | **No** | **Never** | Authentication subsystem |
| `internalNote` | No | No | Administration system |
| `locked` | No | Usually no | Anti-abuse system |
| `createdAt` | No | Per contract | Database |

Field selection must follow each operation: a password-change endpoint may accept `currentPassword` and `newPassword` but never `passwordHash`; an avatar-upload endpoint may accept a file but never an unapproved internal resource URL. Separate the flows accordingly.

In the example below, `email` is edited directly **solely to illustrate the DTO technique**. Real systems usually require verifying the new address via email before updating `verifiedEmail` or email-based privileges. Never treat an email the client just sent as already verified.

## 5. Runnable Java 17+ Example: Separate Input DTO and Output DTO

Example using **Spring Boot 3.5.7 / Spring Security 6.x, Spring MVC, Jackson, and Jakarta Bean Validation**. For easy testing, account data is stored in memory and authentication uses HTTP Basic with a demo account. The configuration **keeps default CSRF enabled** to demonstrate safety requirements on state-changing methods.

Demo goals:

- `GET /api/profile`: only an authenticated user reads **their own** profile; response contains `id`, `displayName`, `email`.
- `PUT /api/profile`: accepts only `displayName` and `email`; rejects `id`, `admin`, `role`, `passwordHash`.
- JSON with unknown fields returns **400** thanks to strict Jackson configuration; this is a transparent choice for the API contract.
- JSON missing required values or with invalid formats returns **400** via `@Valid`.
- HTTP Basic is not used as an excuse to disable CSRF arbitrarily. Tests must supply a valid CSRF token for PUT to succeed.
- Every response is built from a DTO; the internal account record is never serialized.

### 5.1. Project Structure

```text
dto-boundary-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/DtoBoundaryApplication.java
    │   └── resources/application.yml
    └── test/
        └── java/demo/DtoBoundaryApplicationTests.java
```

### 5.2. Maven: `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>dto-boundary-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
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
```

The validation starter is declared explicitly because Bean Validation should not be assumed present solely from the web starter. The security-test dependency provides `csrf()` and `httpBasic()` for MockMvc.

### 5.3. Jackson Configuration: `src/main/resources/application.yml`

```yaml
spring:
  jackson:
    deserialization:
      fail-on-unknown-properties: true
```

This enables Jackson's `DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES` on the mapper managed by Spring Boot 3.5. If JSON sends an unknown field such as `admin` to a DTO without that field, the HTTP message converter throws a JSON read error and Spring MVC returns **400 Bad Request**.

**Very important note:** whether unknown properties are ignored or rejected by default can vary by configuration, version, custom `ObjectMapper`, and annotations. **Never rely on unverified defaults.** Using allowlist DTOs and explicit mapping is the root defense: even if an unknown JSON field is ignored instead of returning 400, it must still never alter the entity. Reject-unknown mode helps detect clients violating the contract, though it can affect API compatibility when clients send newer fields; choose based on your versioning and testing strategy.

### 5.4. Application: `src/main/java/demo/DtoBoundaryApplication.java`

```java
package demo;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class DtoBoundaryApplication {

    public static void main(String[] args) {
        SpringApplication.run(DtoBoundaryApplication.class, args);
    }

    @Bean
    UserDetailsService demoUsers() {
        // Demo only. Production must hash passwords and manage secrets securely.
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password("{noop}demo123")
                        .roles("USER")
                        .build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/profile").authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                // Do not disable CSRF: PUT must carry a valid token.
                .build();
    }

    // Input DTO containing only properties the user is allowed to edit.
    public record UpdateProfileRequest(
            @NotBlank @Size(max = 80) String displayName,
            @NotBlank @Email @Size(max = 254) String email) {}

    // Output DTO containing only properties permitted to be exposed.
    public record ProfileResponse(
            long id, String displayName, String email) {}

    @Service
    public static class ProfileService {
        private final Map<String, Account> accounts =
                new ConcurrentHashMap<>();

        public ProfileService() {
            accounts.put("alice", new Account(
                    101L,
                    "alice",
                    "Alice",
                    "alice@example.test",
                    "internal-password-hash-placeholder",
                    "USER",
                    false,
                    "Internal review only"));
        }

        public ProfileResponse getProfile(String username) {
            Account account = accounts.get(username);
            if (account == null) {
                throw new ResponseStatusException(HttpStatus.NOT_FOUND);
            }
            return toResponse(account);
        }

        public ProfileResponse updateProfile(
                String username, UpdateProfileRequest input) {
            Account updated = accounts.computeIfPresent(
                    username,
                    (key, current) -> new Account(
                            current.id(),
                            current.username(),
                            input.displayName().strip(),
                            input.email().strip(),
                            current.passwordHash(),
                            current.role(),
                            current.admin(),
                            current.internalNote()));

            if (updated == null) {
                throw new ResponseStatusException(HttpStatus.NOT_FOUND);
            }
            return toResponse(updated);
        }

        private static ProfileResponse toResponse(Account account) {
            return new ProfileResponse(
                    account.id(),
                    account.displayName(),
                    account.email());
        }

        // Illustrative entity containing fields that MUST NEVER
        // cross the HTTP boundary directly.
        private record Account(
                long id,
                String username,
                String displayName,
                String email,
                String passwordHash,
                String role,
                boolean admin,
                String internalNote) {}
    }

    @RestController
    @RequestMapping("/api/profile")
    public static class ProfileController {
        private final ProfileService profiles;

        public ProfileController(ProfileService profiles) {
            this.profiles = profiles;
        }

        @GetMapping
        public ProfileResponse me(Authentication authentication) {
            // Username is obtained from authentication verified by Spring Security.
            return profiles.getProfile(authentication.getName());
        }

        @PutMapping
        public ProfileResponse update(
                Authentication authentication,
                @Valid @RequestBody UpdateProfileRequest input) {
            return profiles.updateProfile(
                    authentication.getName(), input);
        }
    }
}
```

**Why does this code enforce field boundaries?**

1. `UpdateProfileRequest` **lacks** `admin`, `role`, `passwordHash`, and `id`. Jackson cannot turn an `admin` value in JSON into a property of that DTO; the strict config also rejects requests with unknown fields.
2. The service calls `new Account(...)` using values from the **existing account** and replaces only `displayName` and `email`. `id`, `role`, `admin`, `passwordHash`, and `internalNote` stay intact on the server. There is no `BeanUtils.copyProperties(input, entity)` or `repository.save(requestBody)` bulk copy.
3. `ProfileController` does not accept the target `username` from the client body or headers. It takes the principal from `Authentication#getName()`. For APIs acting on a path ID, verify permissions on the **exact target object** before reading or editing.
4. `ProfileResponse` has only `id`, `displayName`, and `email`. Jackson serializes only the response record's fields; there is no path for password hashes or internal notes to enter the JSON.
5. `@Valid` triggers Jakarta Bean Validation on the input DTO. `@NotBlank` rejects blank/null, `@Email` checks basic syntax, and `@Size` bounds length. Checking whether an email exists, uses a trusted domain, or is verified belongs to separate business logic.
6. `SecurityFilterChain` requires authentication before entering the controller. The demo's HTTP Basic with `{noop}` is **for easy execution only** and must never be used for production accounts. Use HTTPS, a proper password encoder, and secure secret storage in real deployments.
7. `ConcurrentHashMap#computeIfPresent` replaces the record atomically across concurrent requests in this demo. This is not a real persistence layer; production databases need transactions, locking, and race-condition controls.
8. `CSRF` remains enabled by default. Browsers can attach HTTP Basic credentials automatically, so never assume HTTP Basic is inherently immune to CSRF.

### 5.5. Observing Output via HTTP

In the directory containing `pom.xml`, with Java 17+ and Maven:

```bash
mvn -q test
mvn -q -DskipTests package
java -jar target/dto-boundary-demo-0.0.1-SNAPSHOT.jar
```

In another terminal:

```bash
curl -i http://localhost:8080/api/profile
curl -i -u alice:demo123 http://localhost:8080/api/profile
```

Expected results:

- Request without credentials: **401 Unauthorized**, no profile returned.
- Request with valid credentials: **200 OK**, initial JSON looks like this (ignoring field order differences):

```json
{
  "id": 101,
  "displayName": "Alice",
  "email": "alice@example.test"
}
```

The response **contains no** `passwordHash`, `role`, `admin`, or `internalNote`. Never return the entity and hope the frontend strips them out.

If you try calling PUT as shown below **without supplying a CSRF token**:

```bash
curl -i -u alice:demo123 -X PUT \
  -H 'Content-Type: application/json' \
  -d '{"displayName":"Alicia","email":"alicia@example.test"}' \
  http://localhost:8080/api/profile
```

the expected result is **403 Forbidden due to CSRF**, even when credentials and fields are valid. This is intentional behavior in the demo. The tests below use Spring Security Test's `csrf()` to simulate a valid token and verify the PUT flow. To perform PUT with `curl` in a real cookie/session app, design a proper mechanism to issue and submit CSRF tokens; never disable CSRF just so a `curl` command returns 200.

### 5.6. MockMvc Tests: Verifying the Real Flow with Validation and Spring Security

**`src/test/java/demo/DtoBoundaryApplicationTests.java`:**

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DtoBoundaryApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCannotReadProfile() throws Exception {
        mvc.perform(get("/api/profile"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void responseContainsOnlyPublicContractFields() throws Exception {
        mvc.perform(get("/api/profile")
                        .with(httpBasic("alice", "demo123")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(101))
                .andExpect(jsonPath("$.displayName").exists())
                .andExpect(jsonPath("$.email").exists())
                .andExpect(jsonPath("$.passwordHash").doesNotExist())
                .andExpect(jsonPath("$.role").doesNotExist())
                .andExpect(jsonPath("$.admin").doesNotExist())
                .andExpect(jsonPath("$.internalNote").doesNotExist());
    }

    @Test
    void validDtoUpdatesOnlyAllowedFields() throws Exception {
        mvc.perform(put("/api/profile")
                        .with(httpBasic("alice", "demo123"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "displayName": "Alicia",
                                  "email": "alicia@example.test"
                                }
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.displayName").value("Alicia"))
                .andExpect(jsonPath("$.email")
                        .value("alicia@example.test"))
                .andExpect(jsonPath("$.admin").doesNotExist());
    }

    @Test
    void rejectsUnknownAdminField() throws Exception {
        mvc.perform(put("/api/profile")
                        .with(httpBasic("alice", "demo123"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "displayName": "Alicia",
                                  "email": "alicia@example.test",
                                  "admin": true
                                }
                                """))
                .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsInvalidUserInput() throws Exception {
        mvc.perform(put("/api/profile")
                        .with(httpBasic("alice", "demo123"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "displayName": "   ",
                                  "email": "not-an-email"
                                }
                                """))
                .andExpect(status().isBadRequest());
    }

    @Test
    void unsafeMethodWithoutCsrfTokenIsForbidden() throws Exception {
        mvc.perform(put("/api/profile")
                        .with(httpBasic("alice", "demo123"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "displayName": "Alicia",
                                  "email": "alicia@example.test"
                                }
                                """))
                .andExpect(status().isForbidden());
    }
}
```

Run `mvn test`. The tests are expected to pass when using the exact files above without altering Spring Security/Jackson behavior. The suite verifies:

- Unauthenticated HTTP flow receives 401.
- Response DTO omits secret fields.
- Valid request DTO updates when credentials and CSRF token are present.
- Adding `admin` to JSON yields 400 under strict Jackson configuration.
- Bean Validation rejects invalid data with 400.
- PUT request without a CSRF token receives 403.

Tests can run in any order; the profile read test checks shape rather than assuming the display name still equals the initial seed value. For production projects, add tests asserting `admin`/`role` in the domain **genuinely remain unchanged**, plus concurrent updates, transactions, and another user trying to access `alice`'s data.

## 6. Input DTOs: Defining Which Fields Clients May Edit

### 6.1. Allowlist per Operation—Never Reuse Entities "for Convenience"

Suppose an account has `id`, `username`, `email`, `passwordHash`, `role`, `locked`. These actions have different contracts:

| API | Input DTO should contain | Should NOT accept |
| --- | --- | --- |
| `POST /accounts` create account | `email`, `displayName`, maybe `password` | `id`, `role`, `locked`, `passwordHash` |
| `PUT /api/profile` update profile | `displayName`, `email` | `role`, `admin`, `ownerId`, `createdAt` |
| `POST /api/password/change` | `currentPassword`, `newPassword` | `passwordHash`, `role` |
| `PUT /admin/accounts/{id}/status` | A constrained `status` enum | The entire entity |
| `POST /orders` | Product code, quantity, allowed address | Server-calculated `unitPrice`, `paid`, `ownerId`, `discountApproved` |

If a client sends a price or `paid=true` in an order request, the service must pull pricing from an authoritative catalog and keep payment status tied to trusted payment events. JSON can be completely type-valid yet unauthorized.

### 6.2. Bean Validation Only Checks Validity—It Does Not Guarantee Authorization

Example:

```java
public record CreateInvoiceRequest(
        @NotBlank String customerId,
        @NotNull @Positive BigDecimal amount) {}
```

The snippet above is **merely an illustrative fragment**. It needs `BigDecimal`, `NotBlank`, `NotNull`, `Positive` imports and cannot run standalone. Even if `customerId` is non-blank and `amount` is positive, the user may still lack permission to create an invoice for that customer or submit arbitrary amounts. Those checks belong in the service/domain layer.

Useful rules include: `@NotNull` to require a value, `@NotBlank` for non-whitespace strings, `@Size` to bound string/collection length, `@Pattern` for formats, `@Email` for email syntax, and custom validators for complex business rules. `@Valid` triggers nested validation, provided constraints are placed on child DTOs. Cap HTTP request body size and JSON depth separately to prevent excessive resource consumption; Bean Validation does not cap raw HTTP payload size on its own.

Never echo full rejected values, tokens, or passwords into error messages. A standard validation response should expose only error codes and necessary field names; `ProblemDetail`/`@RestControllerAdvice` can provide a uniform contract without leaking stack traces or private data.

### 6.3. Unknown Fields: Ignore or Reject?

Two valid choices exist depending on the contract:

- **Strict**: reject JSON containing unknown properties, helping catch client bugs and detect overposting. The demo enables `fail-on-unknown-properties` and expects 400.
- **Lenient**: ignore unknown fields for forward compatibility. Still safe against overposting **provided** the DTO contains only allowlisted fields and the service copies only those fields.

Never think ignoring unknown fields means the API is fully protected. If the request DTO itself declares `role` or the service maps a `Map<String,Object>` onto an entity by name, the vulnerability still exists.

### 6.4. POST, PUT, and PATCH Do Not Share the Same Semantics

- **Create**: new object; the server assigns ID, ownership, timestamps, and default state.
- **PUT**: typically represents updating/replacing a resource per contract; if required fields are absent, reject rather than accidentally writing `null`.
- **PATCH**: modifies only specified fields; distinguish **field omitted** from **field sent with `null`**. Simple nullable Java records cannot always tell these two states apart.
- **JSON Patch (RFC 6902)**: if dynamic paths are supported, validate path allowlists, operations, and object permissions before applying; forbid patching `/roles`, `/passwordHash`, or `/ownerId`.

Never use `BeanUtils.copyProperties(patch, entity)` without controlling allowed fields; copying `null` and newly added fields can cause unintended mutations. MapStruct or similar mappers help only when explicitly configured with permitted fields; auto-mapping by name from overly broad DTOs remains risky.

## 7. Output DTOs: Preventing Data Leaks per Object and Audience

### 7.1. A Response DTO Is an Output Allowlist

For example, a domain account has `passwordHash`, `mfaSecret`, `lastLoginIp`, `riskScore`, and `email`. A public endpoint typically only needs:

```java
public record PublicProfileResponse(
        String displayName, String avatarUrl) {}
```

The user's own endpoint may additionally return `email` and `id`. An ADMIN endpoint may have another DTO, but only after the service/endpoint has enforced authorization. Never add a client-supplied `isAdmin` flag to decide whether private fields appear in the response.

**Split DTOs by audience:**

| Audience | DTO | Example fields |
| --- | --- | --- |
| Unauthenticated visitor | `PublicProfileResponse` | Approved `displayName`, `avatarUrl` |
| Account owner | `SelfProfileResponse` | Public fields + viewable `email` |
| Support staff with specific role | `SupportAccountResponse` | Necessary support statuses, audited |
| Security administrator | `SecurityAuditResponse` | Metadata per specific permission, secret data restricted |

Even administrators should not receive `passwordHash`; authentication systems have no need to export hashes over REST. Data needed internally can remain protected via DB permissions, encryption at rest, and logging policies.

### 7.2. Leaks Can Happen Inside Nested Objects

A top-level DTO with only three fields can still leak deep data if a `customer` or `address` field holds a raw **entity with bidirectional relations**. Use explicit child DTOs and bound nesting depth:

```java
public record OrderResponse(
        long id,
        String status,
        CustomerSummary customer) {}

public record CustomerSummary(
        long id,
        String displayName) {}
```

This snippet illustrates the model, not a standalone Java file. Never place `CustomerEntity` inside `OrderResponse` and assume the outer DTO is enough protection. Returning JPA entities directly can also trigger lazy loading, N+1 queries, or serialization cycles.

### 7.3. Field-Level Authorization Differs from Static DTOs

Some fields are visible only under dynamic conditions: for instance, invoice amounts visible only to the owner or an accountant. Static per-audience DTOs can be paired with policy-driven mapping:

```text
Verified Authentication
        │
        ▼
Service confirms object + tenant access permission
        │
        ▼
Select response DTO and permitted fields
        │
        ▼
Serialize JSON
```

Do not merely strip fields from a response if the user **is not allowed to know the object exists**; that case may require 403/404 per resource-hiding policy. DTOs prevent field leakage; they do not solve IDOR/BOLA (Broken Object Level Authorization) on their own.

### 7.4. Minimize Data in Both Queries and Processing Pipelines

If a list endpoint only needs `id` and `displayName`, a query projection selecting those two columns reduces data moving through the DB, network, and memory. However, query projection does not replace response DTOs or authorization. When handling PII, consider `Cache-Control: no-store`, HTTPS, avoiding arbitrary body logging, and preventing shared caches across users.

## 8. Jackson Annotations: Helpful, Not a Replacement for Clear DTOs

Common Jackson annotations:

| Annotation | Meaning | Caveat |
| --- | --- | --- |
| `@JsonIgnore` | Skips a property during JSON processing per config | Can affect both read and write; does not replace field policies |
| `@JsonProperty(access = READ_ONLY)` | Property emitted during serialization only, not read from JSON | "Read" from Java/Jackson's perspective, not "client authorized to read" |
| `@JsonProperty(access = WRITE_ONLY)` | Property accepted on deserialization, omitted from JSON output | Useful for password inputs in dedicated DTOs; avoid mixing with output |
| `@JsonView` | Selects fields by view during serialization/deserialization | Gets complex across many views/endpoints; still needs authorization |
| `@JsonIgnoreProperties` | Declares ignored properties / unknown policy | Not a substitute for specifying updatable fields |
| `@JsonInclude` | Controls whether `null`/empty values are emitted | Not an authorization mechanism |

Illustrative Jackson fragment:

```java
public record RegistrationRequest(
        String email,
        @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
        String password) {}
```

When serialized, `password` is omitted per the access rule. Nevertheless, `RegistrationRequest` is an **input** type and should not be reused as a response type just because `WRITE_ONLY` is set. A separate `RegistrationResponse` is easier to audit.

If you rely on entities with `@JsonIgnore` on `passwordHash`, a developer later adding a `recoveryToken` field and forgetting the annotation can leak data. Explicit response DTOs prevent new fields from automatically entering the API contract.

## 9. Distinguishing JSON `@RequestBody` from Form/Query `@ModelAttribute`

In Spring MVC, the two binding mechanisms are related but **not equivalent**:

| Request type | Common binding mechanism | Primary tools |
| --- | --- | --- |
| JSON request body | `@RequestBody`, Jackson via `HttpMessageConverter` | Input DTO, ObjectMapper, Bean Validation |
| Form-urlencoded / query parameters | `@ModelAttribute`, `WebDataBinder` | Dedicated form object, `setAllowedFields` on binder, Bean Validation |

Spring Framework provides `WebDataBinder#setAllowedFields(...)` to allowlist properties bound from form/model binding. Illustrative fragment for a controller handling `@ModelAttribute`:

```java
@InitBinder
void initBinder(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "email");
}
```

The snippet above requires importing `InitBinder` and `WebDataBinder`. **Never assume `setAllowedFields` controls Jackson deserializing JSON `@RequestBody`**; for JSON, use dedicated input DTOs, strict Jackson settings, and allowlist service mapping. Applying rules without understanding the binding path creates a false sense of security.

Form binding must also watch out for nested paths like `account.roles[0]` or `owner.id`. Narrow-contract DTOs prevent binders from reaching sensitive state. In Spring Framework, constructor binding can also populate data, so checking setters alone is insufficient; clear input class/record design remains essential.

## 10. Coordinating with Spring Security: Permissions Are Decided on the Server

### 10.1. Never Take Identity/Ownership from the Client When It Can Come from the Principal

For instance, `PUT /accounts/{accountId}` must verify the actor has permission to modify `accountId`. Never write:

```java
if (requestBody.ownerId().equals(accountId)) {
    // Wrong: ownerId can be controlled by the client
}
```

Instead, take the verified identity from `Authentication` or `@AuthenticationPrincipal`, load the resource from the DB, and verify ownership/tenant in the service:

```text
authenticated user ──► subjectId
requested accountId ─► account in DB
                             │
                             ▼
                  does subjectId have permission on accountId?
                        │             │
                       Yes            No
                        │             │
                     update         403/404
                        │
                     response DTO
```

With OAuth2/JWT, subject and tenant claims are trustworthy only after the Resource Server validates the token and maps it per issuer; OAuth2 client ID tokens or arbitrary caller-sent fields are no substitute for authorization.

### 10.2. Blocking Behavior at Both URL and Business Layers

`authorizeHttpRequests` can verify requests are authenticated. For sensitive actions, `@EnableMethodSecurity` and `@PreAuthorize`/`AuthorizationManager` place rules close to services. Even so, expressions like `hasRole("ADMIN")` only check authorities; ownership, tenant, and object-state permissions still require checking actual data.

Do not rely on `@PreAuthorize` to protect a method if internal same-bean calls bypass the proxy unexpectedly. Test both service-level authorization and HTTP statuses.

### 10.3. DTOs Do Not Solve CSRF, CORS, Injection, or Encryption

- **CSRF**: browsers can automatically attach cookies or Basic credentials; unsafe operations need proper CSRF policies. The demo keeps CSRF enabled and tests with `csrf()`.
- **CORS**: restricts browser origins, not a substitute for authorization. Disabling CORS does not block `curl`; enabling CORS for an origin does not mean data is authorized to be viewed.
- **SQL injection**: use parameterized prepared statements/ORMs even after input enters a DTO.
- **XSS**: output DTOs reduce returned data, but do not replace proper escaping when frontends render HTML.
- **Passwords/tokens**: never return secrets via DTOs; still apply hashing/encryption, TLS, storage permissions, and log redaction.
- **File upload**: a DTO carrying file metadata does not replace checking size, format, safe storage, and content scanning.

## 11. Choosing DTOs in Real APIs

When implementing an endpoint, build a **contract table** before writing code:

1. **Object and action**: create, read, full update, partial update, delete, or admin action.
2. **Actor/audience**: anonymous, account owner, same-tenant member, support staff, admin.
3. **Input allowlist**: field names, types, required vs. optional, value constraints, and trusted sources for server-owned fields.
4. **Output allowlist**: permitted public field names, field-level authorization rules, privacy conditions.
5. **Authorization decisions**: authentication, object ownership, role/permission, tenant, business state.
6. **Mapping**: input DTO → command/per-field update → domain; domain/query projection → response DTO.
7. **Error semantics**: 400 malformed/invalid input, 401 unauthenticated, 403 forbidden, 404 not found/hidden, 409 state conflict where appropriate.
8. **Negative testing**: overposting, unknown fields, secret fields in JSON responses, other users, other tenants, missing CSRF, null/blank, nested objects.
9. **Operations**: auditing, log redaction, caching, request size limits, versioning, schema evolution.

Example `POST /orders`: the client sends `productId` and `quantity`. The server fetches `unitPrice` from the catalog, computes `totalPrice`, assigns `ownerId` from the principal, and keeps `paid=false` until receiving a trusted payment event. The response returns `orderId`, status, and total price per contract—never internal account numbers or payment-processing tokens. If a DTO contains `paid` while the service "hopes the frontend won't send it", one mapper refactor can open a vulnerability.

## 12. Common Mistakes and How to Avoid Them

1. **Returning JPA entities directly**: accidentally leaks secret fields, nested relations, lazy loading, or JSON cycles. Use response DTOs/projections.
2. **Accepting entities from `@RequestBody` and calling `save`**: clients overwrite system fields. Use narrow input DTOs and per-field updates.
3. **Using a single `AccountDto` across every endpoint**: admin fields leak into public APIs. Split contracts by operation/audience.
4. **Assuming `@Valid` replaces authorization**: a format-valid request can still modify someone else's data. Enforce ownership and tenant checks.
5. **Using `BeanUtils.copyProperties` unconditionally**: name-based mapping picks up newly added fields unexpectedly. Use explicit allowlist mapping.
6. **Relying solely on `@JsonIgnore` on entities to stop leaks**: newly added fields can easily miss the annotation. Output DTOs restrict fields by design.
7. **Only hiding fields in the frontend**: JSON is still exposed. Enforce at the backend.
8. **Thinking `@InitBinder#setAllowedFields` governs JSON `@RequestBody`**: JSON is deserialized by Jackson and must be controlled separately.
9. **Failing to distinguish omitted vs. `null` in PATCH**: unintentionally overwrites fields. Use explicit PATCH DTOs or operation models.
10. **Letting clients choose `ownerId`/`tenantId`**: easily causes BOLA/IDOR. Derive from authentication and verify against actual records.
11. **Returning raw validation exceptions**: can leak sensitive values or stack traces. Return safe error codes and redacted logs.
12. **Overlooking nested data**: an entity-typed field inside a DTO still leaks relations. Use child DTOs and limit depth.
13. **Skipping CSRF because the demo uses Basic**: browser PUT/POST requests using cookies or Basic still carry risk; evaluate CSRF per client type.
14. **Believing strict unknown-JSON rejection protects everything**: if the DTO itself includes `role` or the mapper allows writing `admin`, completely valid JSON is still dangerous.
15. **Forgetting data exposure in lists/exports/logs**: a DTO on `GET /me` does not automatically cover search APIs, CSV exports, event payloads, or application logs. Check every boundary.

## 13. When the Application Uses Spring WebFlux

DTO principles remain the same, except requests are read via WebFlux HTTP message readers/codecs, controllers work with `Mono`/`Flux`, and security uses `SecurityWebFilterChain` instead of the Servlet filter chain.

**Fragment inside a WebFlux controller with an existing reactive service**, not a standalone Java file:

```java
@PutMapping("/api/profile")
public Mono<ProfileResponse> update(
        @Valid @RequestBody UpdateProfileRequest input,
        Authentication authentication) {
    return service.updateSelf(authentication.getName(), input);
}
```

Input/output DTOs must still be allowlist types; mapping server-owned fields stays inside the service. In WebFlux, validation failures typically surface as `WebExchangeBindException`; in Spring MVC, `@Valid @RequestBody` without an adjacent `BindingResult` typically produces `MethodArgumentNotValidException` (400). Use the error-handling mechanism for the right stack. Avoid blocking JDBC on the event loop and avoid manual `block()`/`subscribe()` inside reactive handlers.

If accepting the request body as `Mono<UpdateProfileRequest>`, validation triggering and handling can differ from synchronous signatures; test the real pipeline. Even in reactive apps, never deserialize JSON into an entity with sensitive fields.

## 14. Checklist and Practice Exercises

### Pre-Merge API Checklist

- [ ] Every endpoint takes an input DTO containing only fields the caller is permitted to send.
- [ ] Entities are never bound directly from untrusted JSON/forms into persistence calls.
- [ ] Services update only allowlisted fields and derive `ownerId`, `role`, `paid`, and timestamps from trusted sources.
- [ ] Inputs have required validation without confusing validation with authorization.
- [ ] Response DTOs contain only audience-appropriate fields; never leak hashes, tokens, secrets, internal flags, or sensitive nested relations.
- [ ] Object/tenant authorization exists independently of DTO shape.
- [ ] Unknown fields, missing fields, nulls, PATCH semantics, and nested objects have clear rules.
- [ ] Tested 400/401/403, CSRF, overposting, output exposure, and cross-tenant users.
- [ ] Logs/exceptions/caching/exports do not inadvertently expose fields that response DTOs hid.
- [ ] API contracts remain protected across model refactors and new field additions.

### Practice Questions

1. A rename API accepts `@RequestBody UserEntity` with `role` and `isAdmin`. Redesign `UpdateDisplayNameRequest` and the service update logic to prevent mass assignment.
2. Why does `@Email` on a DTO not prove the user owns the new email? What flow must be added?
3. An endpoint returns `OrderResponse(CustomerEntity customer)`. Why does an excessive data exposure risk remain even though the outer type is a DTO?
4. What is the difference between `@JsonProperty(access = WRITE_ONLY)` and separate `CreateAccountRequest`/`AccountResponse` types?
5. Why can a `PUT` request with valid credentials and a valid DTO still receive 403 in the demo? When might a different CSRF design be appropriate?
6. When switching from `PUT` to `PATCH`, how should omitted fields vs. `null` fields be distinguished to avoid overwriting data?
7. Why does checking `request.ownerId() == pathId` not solve BOLA/IDOR?
8. If an entity adds a `mfaSecret` field in a migration, which API is safer against that change: returning the entity directly or returning an explicit DTO? Explain via the serializer boundary.

## 15. Official Documentation and Recommendations

- [OWASP — Mass Assignment Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html)
- [OWASP — API Security Top 10: Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
- [OWASP — API Security Top 10: Broken Object Property Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa3-broken-object-property-level-authorization/)
- [Spring Framework — `@RequestBody` (Spring MVC)](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework — Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/beans-beans.html)
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — MockMvc CSRF Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html)
- [Spring Framework — `@RequestBody` (WebFlux)](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html)
- [Jackson — `JsonProperty.Access`](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/2.18.3/com/fasterxml/jackson/annotation/JsonProperty.Access.html)

**Key takeaway:** a well-designed DTO makes explicit what data enters **and** leaves an API. The complete defense is **input allowlist + explicit mapping + service authorization + output allowlist + negative tests**. When an entity changes, new fields stay on the server until deliberately added to the API contract.
