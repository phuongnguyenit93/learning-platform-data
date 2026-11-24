# Binding Constraints and Preventing Unintended Property Updates in Spring Boot

## 1. Goals and the Problem to Solve

A form or JSON request may only display two fields, **displayName** and **bio**, yet the Java object or database entity also has other properties such as **admin**, **role**, **ownerId**, **tenantId**, **approved**, **balance**, or **createdAt**. If the application automatically binds every field sent by the client onto the entity and saves it, a user can manually submit fields absent from the UI and alter sensitive data.

This is the **mass assignment** problem, also known as **over-posting**, **unsafe property binding**, or **unintended property updates**.

After this lesson, you will be able to:

1. Explain accurately why clients can add fields to a request even when an HTML form does not render them.
2. Distinguish **Spring WebDataBinder** used by **@ModelAttribute** from Jackson JSON deserialization via **@RequestBody**.
3. Create narrow **input DTOs** and apply **allowedFields**, **declarativeBinding**, or constructor binding in the right places.
4. Avoid confusing **@Valid/Bean Validation** with field allowlists and authorization.
5. Map update data explicitly, preserving server-managed sensitive fields.
6. Test forms, JSON, nested fields, unknown properties, ownership, and PUT/PATCH risks.
7. Run a complete **Java 17 / Spring Boot 3.5 / Maven** example and test it with MockMvc.

This lesson belongs to the **Request Data** group and focuses on the **Spring MVC Servlet stack**. Similar design principles apply to **Spring WebFlux**, though its JSON and form readers differ in implementation details.

## 2. What Can a Malicious Request Do?

Suppose an account entity has these fields:

~~~java
public class Account {
    private Long id;
    private Long ownerId;
    private String displayName;
    private String bio;
    private boolean admin;
    private String approvalStatus;

    // Other getters/setters of the entity.
}
~~~

This is an illustrative Java sketch, not a standalone runnable class. A poorly designed controller might accept the domain object directly:

~~~java
// UNSAFE pattern: binding client data into an entity with sensitive fields.
@PostMapping("/accounts/{id}")
public Account update(@PathVariable Long id,
                      @ModelAttribute Account account) {
    return accountRepository.save(account);
}
~~~

A client can send:

~~~http
POST /accounts/42
Content-Type: application/x-www-form-urlencoded

displayName=An&bio=Hello&admin=true&ownerId=1&approvalStatus=APPROVED
~~~

If the data binder can set those properties and the save logic accepts them, **admin** and **ownerId** can be altered. Not rendering an admin input on the UI **does not stop** a client from submitting that field name.

JSON carries a similar risk:

~~~json
{
  "displayName": "An",
  "bio": "Hello",
  "admin": true,
  "ownerId": 1,
  "approvalStatus": "APPROVED"
}
~~~

If the server uses **@RequestBody Account** and updates the entire entity, Jackson can populate those valid JSON properties onto the object. Adding **@Valid** does not reject **admin=true** when a Boolean value is valid for its type.

### 2.1. Distinguishing Four Layers of Protection

| Concern | Question | Solution |
|---|---|---|
| **Field selection** | Which fields may the client propose changing? | Input DTO / allowlist |
| **Value validation** | Are the values of allowed fields valid? | Bean Validation and business rules |
| **Object authorization** | Is the caller allowed to modify this record? | Principal, tenant, owner, ACL |
| **Persistence mapping** | Which fields are actually updated? | Explicit mapping, service layer |

For example, a DTO containing only displayName/bio prevents changing role, yet if user A can submit user B's ID and the service does not verify ownership, a **BOLA/IDOR** vulnerability still exists. Conversely, being logged in does not grant permission to alter approval status or admin roles.

## 3. Two Key Binding Mechanisms in Spring

### 3.1. @ModelAttribute: Binding Forms/Queries with WebDataBinder

Spring MVC can instantiate a model object and bind request parameters through **WebDataBinder**:

~~~java
@PostMapping("/profiles/form")
public String update(@ModelAttribute ProfileForm form) {
    return form.getDisplayName();
}
~~~

Here **@ModelAttribute** can receive form fields, query parameters, and certain path/header values depending on argument resolution. WebDataBinder supports conversion, formatting, validation, and both **constructor binding** and **property/setter binding**.

On objects with many setters, property binding can accept more fields than the developer intended. Spring Framework recommends using **dedicated model objects**, **constructor binding**, or configuring **allowedFields** when property binding is still needed.

### 3.2. @RequestBody: Deserializing JSON with Jackson

~~~java
@PostMapping("/profiles/json")
public void update(@RequestBody UpdateProfileJson request) {
    // ...
}
~~~

In Spring MVC, **@RequestBody** is read by an **HttpMessageConverter**, normally using Jackson for application/json. Jackson constructs the DTO based on constructors, properties, and JSON configuration.

**Warning:** calling **WebDataBinder.setAllowedFields("displayName","bio")** does not directly filter JSON properties deserialized by Jackson from **@RequestBody**. For JSON, the primary protection is a **narrow DTO + explicit mapping**, optionally paired with Jackson settings to reject unknown properties.

### 3.3. Choosing Matching Protections

| Source | Processing path | Recommended constraints |
|---|---|---|
| URL-encoded HTML form | @ModelAttribute/WebDataBinder | DTO, allowedFields, declarativeBinding |
| Form-like query | @RequestParam or @ModelAttribute | Explicit parameters/DTO, validation |
| Path ID | @PathVariable | Resource lookup and authorization checks |
| JSON object | @RequestBody/Jackson | Narrow DTO, strict unknown policy where suitable, explicit mapping |
| Multipart fields | @ModelAttribute or @RequestPart | DTO, field allowlist, part/file limits |
| WebFlux form | Reactive model binder | Dedicated DTO, @InitBinder |
| WebFlux JSON | Reactive HttpMessageReader/codecs | Dedicated DTO, explicit mapping |

Never use a single class simultaneously as **database entity, input command, response DTO, and security principal**.

## 4. Default Defense: Narrow Input DTOs

If the domain model has:

~~~java
public record Profile(
        long id,
        long ownerId,
        boolean admin,
        String displayName,
        String bio) {
}
~~~

then the DTO for updating a personal profile should only contain:

~~~java
public record UpdateProfileRequest(
        String displayName,
        String bio) {
}
~~~

This means the client cannot submit **ownerId** or **admin** as properties that the DTO knows how to store. In the service, perform an intentional update:

~~~java
Profile updated = new Profile(
        existing.id(),
        existing.ownerId(),
        existing.admin(),
        request.displayName(),
        request.bio());
~~~

This is an illustrative snippet; **existing** must be loaded from server state after an authorization check, not created from the request.

With JPA entities, it is generally better to write:

~~~java
existing.setDisplayName(request.displayName());
existing.setBio(request.bio());
~~~

Avoid blind copying:

~~~java
// Avoid when the source can contain out-of-contract properties.
BeanUtils.copyProperties(request, existing);
~~~

**BeanUtils.copyProperties** is not inherently a vulnerability in every context, but copying all matching properties from a request object to an entity makes newly added entity fields silently writable without code review. If you use an automated mapper, enforce an explicit **field allowlist** and add tests whenever the domain schema changes.

### 4.1. Per-Operation DTOs

An account may have distinct command DTOs:

- **RegisterAccountRequest**: email, password, initial name; no admin role.
- **UpdateProfileRequest**: displayName, bio, avatar if specified.
- **ChangePasswordRequest**: currentPassword, newPassword.
- **AdminChangeRoleRequest**: targetId, role; callable only on admin endpoints.
- **AccountResponse**: fields permitted for display; never serialize the entity as-is.

A single "AccountRequest" containing every field for every operation makes access control very hard to enforce.

## 5. @InitBinder and allowedFields for Forms

For a form model attribute named **profileForm**:

~~~java
@InitBinder("profileForm")
public void initBinder(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "bio");
}
~~~

Imports:

~~~java
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
~~~

**setAllowedFields** only permits property names in the declared set. This list is **case-sensitive** and can cover nested property paths.

For instance, if a form genuinely permits updating an address:

~~~java
binder.setAllowedFields(
        "displayName",
        "shippingAddress.city",
        "shippingAddress.postalCode");
~~~

Do not broaden this to **shippingAddress.\*** if the nested object contains protected fields, and avoid **setAllowedFields("*")**, which effectively negates the allowlist.

### 5.1. Why allowedFields Is Better Than disallowedFields

A blocklist:

~~~java
binder.setDisallowedFields("admin", "role", "ownerId");
~~~

requires remembering every sensitive field, including fields added in the future. If a new **isVerified** or **tenantId** field is added, the old blocklist can miss it. Certain Spring Framework versions have also had security advisories around **disallowedFields** name checks, so keeping patches current and preferring a whitelist is the stronger practice.

### 5.2. declarativeBinding in Spring Framework 6.1+

You can configure:

~~~java
@InitBinder("profileForm")
public void configure(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
    binder.setAllowedFields("displayName", "bio");
}
~~~

When **declarativeBinding=true**, the framework still performs **constructor binding**, but only enables **property/setter binding** when allowedFields are configured. If you set declarativeBinding without allowedFields, setter binding is not opened up.

**Note:** constructor binding can still bind constructor parameters. If a DTO record includes **admin**, **role**, and **ownerId**, enabling declarativeBinding does not remove those constructor arguments. The DTO itself must be designed properly.

### 5.3. BindingResult and Suppressed Fields

Properties outside the allowlist can be recorded in **BindingResult.getSuppressedFields()**.

~~~java
@PostMapping("/profiles/form")
public ResponseEntity<Void> update(
        @Valid @ModelAttribute("profileForm") ProfileForm form,
        BindingResult result) {

    if (result.hasErrors()
            || result.getSuppressedFields().length > 0) {
        return ResponseEntity.badRequest().build();
    }
    return ResponseEntity.noContent().build();
}
~~~

This is an illustrative snippet; the ProfileForm class and imports are in the full demo below.

Checking suppressed fields and returning 400 is useful when you want to **reject requests carrying out-of-contract fields** instead of silently ignoring them. However, having zero suppressed fields **does not prove** the request is safe overall; you still need a proper DTO, validation, and authorization. Never log sensitive values from suppressed fields.

### 5.4. Global Configuration via @ControllerAdvice

If an organization standardizes on allowing property binding only when explicitly declared, it can define:

~~~java
@ControllerAdvice
public class BindingPolicy {
    @InitBinder
    public void configure(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
    }
}
~~~

This applies broadly and can break legacy forms that relied on setter binding. Test every controller during migration. For endpoints needing setters, declare **allowedFields** in the appropriate binder scope.

### 5.5. Nested and Indexed Properties

WebDataBinder supports nested field names:

~~~text
address.city
roles[0].name
contacts[2].phone
preferences[marketing]
profile.admin
~~~

For nested properties, constrain the **property path**, index/key rules, and collection size limits. Allowing a top-level property like **address** or **address.\*** can inadvertently make many nested child properties writable.

Never assume a nested property path cannot be submitted merely because no HTML field renders it.

## 6. @Valid and Bean Validation Are Not Write Permissions

Example DTO:

~~~java
public record UpdateProfileJson(
        @NotBlank @Size(max = 80) String displayName,
        @Size(max = 250) String bio) {
}
~~~

With **jakarta.validation.Valid**, Spring MVC normally returns **HTTP 400** when an object fails validation. Validation is well suited to checking:

- displayName is non-blank and at most 80 characters;
- bio is at most 250 characters;
- email has valid format;
- monetary amounts, dates, and business constraints are valid.

However, **@Valid on an entity with an admin field still allows admin=true** if a Boolean is valid. Validation **does not decide whether the client is authorized to change the admin field**.

Similarly, validating a request's **ownerId** with @NotNull does not make ownerId trustworthy. Owner/tenant must be derived or verified against server-side identity.

## 7. JSON: Unknown Properties and Strict Deserialization

Spring Boot 3.x uses Jackson in Spring MVC. Jackson can be configured to **ignore JSON properties missing from the DTO**, so unexpected JSON fields do not automatically trigger an error.

For example, a client sends:

~~~json
{
  "displayName": "Mai",
  "bio": "About me",
  "admin": true,
  "ownerId": 3
}
~~~

If the target is a record containing only **displayName** and **bio**, extra fields cannot become domain admin/ownerId when the service maps only those two DTO values. If the API wants to **reject unknown fields**, configure **application.yml**:

~~~yaml
spring:
  jackson:
    deserialization:
      fail-on-unknown-properties: true
~~~

Then JSON containing extra **admin** triggers a parse/deserialization error and HTTP 400. This is an **optional** API contract feature and does not replace business-layer protection. Enabling strict mode can affect backward compatibility if existing clients send extra fields that were previously ignored.

**@JsonIgnore**, **@JsonProperty(access = READ_ONLY)**, Jackson views, or custom deserializers help within serialization/deserialization, but should not be relied on as your sole authorization barrier. The foundation remains **operation-specific DTOs and explicit mapping**.

## 8. Runnable Spring Boot 3.5 / Java 17 Demo

The demo uses **Spring Boot 3.5.16** from Maven Central, Java 17, and **spring-boot-starter-web**. Boot 3.5 is an older branch used for educational purposes; for production, choose a currently supported version with active security updates.

Business requirement: a profile has **id=1**, **ownerId=9001**, **admin=false**, name **An**, and an initial bio. The client may only propose updates to **displayName** and **bio**. The server must reject or ignore attempts to modify **ownerId** or **admin** through the profile endpoint.

### 8.1. Structure

~~~text
safe-binding-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/safebinding/
    │   │   ├── SafeBindingApplication.java
    │   │   ├── ProfileService.java
    │   │   ├── ProfileForm.java
    │   │   └── ProfileController.java
    │   └── resources/application.yml
    └── test/java/com/example/safebinding/
        └── ProfileSecurityTest.java
~~~

### 8.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>safe-binding-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
    </dependencies>

    <build>
        <plugins>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugins>
    </build>
</project>
~~~

**spring-boot-starter-validation** is declared explicitly because the example uses Jakarta Bean Validation.

### 8.3. SafeBindingApplication.java

~~~java
package com.example.safebinding;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeBindingApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeBindingApplication.class, args);
    }
}
~~~

### 8.4. ProfileService.java

~~~java
package com.example.safebinding;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class ProfileService {

    private final Map<Long, Profile> profiles =
            new ConcurrentHashMap<>();

    public ProfileService() {
        profiles.put(1L,
                new Profile(1L, 9001L, false, "An", "About me"));
    }

    public Profile find(long id) {
        Profile p = profiles.get(id);
        if (p == null) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Profile not found");
        }
        return p;
    }

    public Profile update(long id, String name, String bio) {
        Profile p = profiles.computeIfPresent(id, (key, old) ->
                new Profile(
                        old.id(),
                        old.ownerId(),
                        old.admin(),
                        name,
                        bio));
        if (p == null) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Profile not found");
        }
        return p;
    }

    public record Profile(
            long id,
            long ownerId,
            boolean admin,
            String displayName,
            String bio) {
    }
}
~~~

**Security point:** the update method only accepts name and bio. Inside update, **id/ownerId/admin** are always copied from **old** (server-side state), never from client input. The demo uses ConcurrentHashMap to run standalone without a database; it does not replace transactions, locking, or real authorization.

### 8.5. ProfileForm.java

~~~java
package com.example.safebinding;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class ProfileForm {

    @NotBlank
    @Size(max = 80)
    private String displayName;

    @Size(max = 250)
    private String bio;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getBio() {
        return bio;
    }

    public void setBio(String bio) {
        this.bio = bio;
    }
}
~~~

The form DTO exposes only two writable properties. **Never pass an entity with admin or ownerId into @ModelAttribute**. Even with only two fields, the controller still configures allowedFields to make the contract explicit and guard against future DTO expansion.

### 8.6. ProfileController.java

~~~java
package com.example.safebinding;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/profiles")
public class ProfileController {

    private final ProfileService service;

    public ProfileController(ProfileService service) {
        this.service = service;
    }

    @InitBinder("profileForm")
    public void initForm(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
        binder.setAllowedFields("displayName", "bio");
    }

    @GetMapping("/{id}")
    public ProfileView find(@PathVariable long id) {
        return view(service.find(id));
    }

    @PostMapping(
            path = "/{id}/form",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ProfileView updateForm(
            @PathVariable long id,
            @Valid @ModelAttribute("profileForm") ProfileForm form,
            BindingResult result) {

        if (result.hasErrors()
                || result.getSuppressedFields().length > 0) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid form");
        }

        return view(service.update(
                id, form.getDisplayName(), form.getBio()));
    }

    @PostMapping(
            path = "/{id}/json",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ProfileView updateJson(
            @PathVariable long id,
            @Valid @RequestBody UpdateProfileJson input) {
        return view(service.update(
                id, input.displayName(), input.bio()));
    }

    private ProfileView view(ProfileService.Profile profile) {
        return new ProfileView(
                profile.id(), profile.displayName(), profile.bio());
    }

    public record UpdateProfileJson(
            @NotBlank @Size(max = 80) String displayName,
            @Size(max = 250) String bio) {
    }

    public record ProfileView(
            long id,
            String displayName,
            String bio) {
    }
}
~~~

**Key points to note:**

- **@InitBinder("profileForm")** configures only the model attribute named profileForm.
- **setDeclarativeBinding(true)** and **setAllowedFields** constrain setter binding for the form.
- **BindingResult** immediately follows @Valid @ModelAttribute so the controller can inspect validation and suppressed fields.
- JSON uses the **UpdateProfileJson** record, which has no admin or ownerId.
- **ProfileService.update** updates only the two editable properties.
- **ProfileView** omits administrative fields from the response.

### 8.7. application.yml

~~~yaml
server:
  port: 8080

spring:
  jackson:
    deserialization:
      fail-on-unknown-properties: true
~~~

With strict JSON enabled, clients sending properties not declared in **UpdateProfileJson** are normally rejected with HTTP 400. This is a **Jackson** setting, not WebDataBinder.

### 8.8. Running and Verifying

In the directory containing pom.xml:

~~~bash
mvn spring-boot:run
~~~

Read the initial profile:

~~~bash
curl -i "http://localhost:8080/api/profiles/1"
~~~

Expect HTTP 200 and JSON:

~~~json
{"id":1,"displayName":"An","bio":"About me"}
~~~

**Valid form:**

~~~bash
curl -i \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "displayName=Bình" \
  --data-urlencode "bio=Learning Spring" \
  "http://localhost:8080/api/profiles/1/form"
~~~

Expect HTTP 200:

~~~json
{"id":1,"displayName":"Bình","bio":"Learning Spring"}
~~~

**Form submitting disallowed extra fields:**

~~~bash
curl -i \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "displayName=Mai" \
  --data-urlencode "bio=Test" \
  --data-urlencode "admin=true" \
  --data-urlencode "ownerId=1" \
  "http://localhost:8080/api/profiles/1/form"
~~~

Expect **HTTP 400** because fields outside allowedFields are suppressed and the controller rejects the request. This **leaves** admin and ownerId unchanged in ProfileService.

**Valid JSON:**

~~~bash
curl -i \
  -H "Content-Type: application/json" \
  --data-binary '{"displayName":"Hà","bio":"JSON"}' \
  "http://localhost:8080/api/profiles/1/json"
~~~

Expect HTTP 200:

~~~json
{"id":1,"displayName":"Hà","bio":"JSON"}
~~~

**JSON submitting extra admin:**

~~~bash
curl -i \
  -H "Content-Type: application/json" \
  --data-binary '{"displayName":"Mai","bio":"JSON","admin":true}' \
  "http://localhost:8080/api/profiles/1/json"
~~~

Expect **HTTP 400** because strict unknown properties is enabled. Without strict mode, unknown fields are ignored by Jackson; either way, the service never maps admin from input.

The commands above use Bash. On PowerShell, use **curl.exe** and consider UTF-8 JSON files to avoid escaping issues.

## 9. Automated Testing with MockMvc

Create **src/test/java/com/example/safebinding/ProfileSecurityTest.java**:

~~~java
package com.example.safebinding;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class ProfileSecurityTest {

    @Autowired MockMvc mvc;
    @Autowired ProfileService service;

    @Test
    void formAllowsOnlyEditableFields() throws Exception {
        mvc.perform(post("/api/profiles/1/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "Bình")
                .param("bio", "Learning Spring"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.displayName").value("Bình"));

        assertThat(service.find(1).admin()).isFalse();
        assertThat(service.find(1).ownerId()).isEqualTo(9001L);
    }

    @Test
    void extraFormFieldsAreRejected() throws Exception {
        mvc.perform(post("/api/profiles/1/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "Mai")
                .param("bio", "Test")
                .param("admin", "true")
                .param("ownerId", "1"))
            .andExpect(status().isBadRequest());

        assertThat(service.find(1).admin()).isFalse();
        assertThat(service.find(1).ownerId()).isEqualTo(9001L);
    }

    @Test
    void jsonAllowsOnlyEditableFields() throws Exception {
        mvc.perform(post("/api/profiles/1/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"Hà\",\"bio\":\"JSON\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.displayName").value("Hà"));

        assertThat(service.find(1).admin()).isFalse();
        assertThat(service.find(1).ownerId()).isEqualTo(9001L);
    }

    @Test
    void extraJsonFieldsAreRejected() throws Exception {
        mvc.perform(post("/api/profiles/1/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"Mai\",\"bio\":\"JSON\","
                        + "\"admin\":true,\"ownerId\":1}"))
            .andExpect(status().isBadRequest());

        assertThat(service.find(1).admin()).isFalse();
        assertThat(service.find(1).ownerId()).isEqualTo(9001L);
    }

    @Test
    void blankDisplayNameFailsValidation() throws Exception {
        mvc.perform(post("/api/profiles/1/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"  \",\"bio\":\"test\"}"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void missingResourceIs404() throws Exception {
        mvc.perform(get("/api/profiles/999"))
            .andExpect(status().isNotFound());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

When all tests pass, Maven exits with code **0**; exact log output depends on the Surefire version.

The test suite verifies both the input contract and **server-side state**. Asserting **admin=false** and **ownerId=9001** directly from ProfileService is more important than merely checking that the response omits those fields.

**Demo limitation:** there is no authentication or ownership check on the profile ID. Therefore the test suite **does not prove** user A is blocked from updating user B's profile; that check must be added in real applications.

## 10. Caller and Resource Authorization

Preventing mass assignment differs from preventing IDOR/BOLA. Even if a client cannot modify admin, they might still send:

~~~http
POST /api/profiles/987/json
Content-Type: application/json

{"displayName":"Change another user's name","bio":"..."}
~~~

If the service simply looks up id=987 and updates it without verifying the principal, authorization is still missing.

Proper production design includes:

1. Authenticate the caller and obtain user/tenant identity from a **trusted security context**.
2. Load the resource from the database by id.
3. Verify that the principal has permission to **edit** that resource, or holds valid administrative authority.
4. Validate business invariants after restricting field inputs.
5. Update only permitted properties inside an appropriate transaction.
6. Audit sensitive changes without logging passwords or raw tokens.

Illustrative **pseudocode snippet** (not a standalone compilable class):

~~~java
Profile entity = repository.findById(id)
        .orElseThrow(() -> new ResourceNotFoundException());

authorization.requireCanEdit(currentPrincipal, entity);

entity.setDisplayName(request.displayName());
entity.setBio(request.bio());

repository.save(entity);
~~~

Entity owner/tenant/role must come from server state. **Never** treat a client-supplied ownerId as proof of ownership. For role changes or approval status updates, create a **separate command/endpoint** with admin permissions, review, and auditing. Browser apps using session cookies must also enforce **CSRF protection** on state-changing requests.

## 11. Constructor Binding and Records

In modern Spring MVC, **@ModelAttribute** supports constructor binding. An input record:

~~~java
public record ChangeAddressForm(
        String city,
        String postalCode) {
}
~~~

has only two constructor parameters, so there is no admin parameter to bind. Combined with **setDeclarativeBinding(true)**, Spring can use constructor binding without opening default setter binding.

However, a record like the following is still unsafe if the client is not authorized to change roles:

~~~java
public record UnsafeAccountInput(
        String city,
        boolean admin) {
}
~~~

Constructor binding **does not automatically filter** constructor parameters. The DTO design itself decides which fields are accepted. For legacy entities with many setters and nested properties, use an intermediate DTO or allowedFields rather than hoping constructor binding "automatically skips" sensitive fields.

## 12. PUT/PATCH and Distinguishing Absent vs. Null

Mass assignment also affects partial-update endpoints. If an API accepts arbitrary JSON PATCH payloads and loops through every key in a Map<String,Object> to set fields on an entity, clients can target **role**, **ownerId**, or out-of-contract nested properties.

With PATCH, distinguish:

- **Field omitted**: typically keep existing value.
- **Field sent as null**: may intend to clear the value, depending on the contract.
- **Specific value sent**: update only if the field is writable.

A plain nullable DTO sometimes cannot distinguish the first two cases. Use a patch command tracking field presence, or controlled JSON Merge Patch/JSON Patch, and enforce an allowlist against **every JSON path**. Never use generic reflection setters over client-supplied keys.

With PUT, clarify whether omitted fields clear prior values; never blindly copy nulls from a DTO onto an entity in a way that wipes sensitive or unintended data.

## 13. Spring WebFlux: Similar Boundaries

In Spring WebFlux:

- **@ModelAttribute** still uses a data binder for forms, queries, and model objects; you can configure **@InitBinder**, DTOs, constructor binding, and allowedFields.
- **@RequestBody Mono<Dto>** uses reactive **HttpMessageReader/codecs** for JSON; it is not filtered by WebDataBinder's setAllowedFields.
- **RouterFunction/ServerRequest** requires designing explicit command binding/deserialization and controlled mapping.

Illustrative snippet (does not compile standalone without a reactive service):

~~~java
@PostMapping("/api/profiles/{id}")
public Mono<ProfileView> update(
        @PathVariable long id,
        @Valid @RequestBody Mono<UpdateProfileRequest> input) {

    return input.flatMap(dto ->
            service.updateEditableFields(
                    id, dto.displayName(), dto.bio()));
}
~~~

In WebFlux, using Mono does not replace DTO allowlists or authorization. When receiving large bodies, you must also limit codec memory and HTTP payload sizes; that is a separate concern from mass assignment.

## 14. Common Mistakes and Fixes

| Symptom | Cause | Fix |
|---|---|---|
| Client adds admin=true to form and changes role | Direct entity binding | DTO, allowedFields, explicit mapping |
| allowedFields configured, yet JSON still binds admin | Jackson @RequestBody bypasses WebDataBinder allowlist | Dedicated JSON DTO and strict policy |
| @Valid still does not block admin=true | Validation does not enforce field access control | Field selection + authorization |
| Unknown JSON field does not return 400 | Boot/Jackson ignores unknown fields by default | Enable strict mode if contract permits |
| Nested field mutates hidden state | Form binds nested property paths | Narrow property-path allowlist |
| PUT input erases existing fields | Copying nulls or replacing whole entity | Define explicit update semantics |
| User edits another user's profile | Service lacks resource authorization | Principal + owner authorization |
| Role changes without audit trail | Generic profile update endpoint reused | Separate admin endpoint with audit |
| Global declarativeBinding breaks legacy forms with empty fields | Legacy forms relied on implicit setter binding | Migrate and add explicit allowedFields |
| Narrow DTO, yet mapper updates restricted columns | Mapper uses convention matching sensitive fields | Explicit mapping + verify persisted state |
| Large payload causes memory spike | No request or collection size limits | Limit size, nesting depth, and rate |
| Suppressed fields go unreported | Binder silently ignores out-of-allowlist fields | Check BindingResult.getSuppressedFields |

### 14.1. Logging and Monitoring

- Log requests rejected due to unknown or suppressed fields with enough detail for investigation, without logging password/token values.
- Log correlation ID, endpoint, and violation category; never expose internal class names or stack traces to clients.
- Alert if repeated requests attempt to inject privileged property names or unusual nested paths.
- Whenever adding a field to an entity or DTO, add a test confirming out-of-contract properties remain unmodifiable.

## 15. Code Review Checklist

- [ ] Never bind entities or domain objects with sensitive fields directly from requests.
- [ ] Dedicated input DTOs exist for each operation.
- [ ] @ModelAttribute uses allowedFields whenever setter/property binding is needed.
- [ ] Consider setDeclarativeBinding(true) to restrict implicit property binding.
- [ ] Do not rely solely on disallowedFields/blocklists.
- [ ] JSON @RequestBody accepts only permitted DTOs; unknown-properties policy is explicit.
- [ ] @Valid validates data; it does not replace authorization.
- [ ] Service updates explicit fields rather than copying all properties blindly.
- [ ] Owner/tenant/role/status are derived server-side or modified via separately authorized commands.
- [ ] PATCH handles absent/null and property paths intentionally.
- [ ] Nested paths, collection indexes, payload sizes, and uploads are constrained.
- [ ] Tests submit extra admin/ownerId fields in forms and unknown fields in JSON.
- [ ] Tests verify persisted entity state after updates, not just the response.
- [ ] Production applications test user/tenant resource permissions.
- [ ] Keep Spring Framework, Jackson, and dependencies patched.

## 16. Official References

1. Spring Framework 6.2 – Spring MVC **@InitBinder** and model design: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html
2. Spring Framework 6.2 – **@ModelAttribute** method arguments: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
3. Spring Framework – MVC Data Binding, property paths: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html
4. Spring Framework – **@RequestBody** via HttpMessageConverter: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html
5. Spring Framework 6.2 – WebFlux **@InitBinder**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-initbinder.html
6. Spring Framework 6.2 – WebFlux **@RequestBody**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestbody.html
7. Spring Boot 3.5 – Common Application Properties, Jackson deserialization: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/
8. Spring Security – Method Security/Authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
9. Spring Framework security advisory **CVE-2025-22233** (related to disallowedFields): https://spring.io/security/cve-2025-22233/
10. Spring Boot 3.5.16 official announcement: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/

## 17. Summary

Preventing **mass assignment** requires specifying exactly **which properties a client is allowed to send and modify**. In Spring MVC, **@ModelAttribute** needs narrow DTOs and allowedFields/declarativeBinding when setter binding is used; JSON **@RequestBody** must be protected with narrow DTOs, an appropriate Jackson policy, and explicit service-layer mapping.

**@Valid only validates data; it does not grant permission.** Fields such as **id, ownerId, tenantId, admin, role, balance, and approvalStatus** must be controlled by the server or updated only through separately authorized endpoints. When testing, always submit out-of-contract properties and verify **the state stored on the server** to confirm no unintended updates occurred.
