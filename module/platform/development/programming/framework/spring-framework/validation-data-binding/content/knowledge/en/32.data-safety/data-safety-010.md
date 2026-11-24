# Reviewing Model Changes to Prevent Unintended Bindable Fields

## 1. The Problem: Adding a Single Setter Can Expand the Attack Surface

In Spring Framework, a tiny change to a Java model can alter what HTTP clients are allowed to modify. When a handler accepts `@ModelAttribute` and uses **property binding**, Spring reads request parameter names, locates matching properties, and invokes setters or traverses nested property paths. By default, a `WebDataBinder` can bind every accessible property matching an input.

Suppose the initial model is:

~~~java
public class Account {
    private String displayName;

    public String getDisplayName() { return displayName; }
    public void setDisplayName(String value) {
        this.displayName = value;
    }
}
~~~

The controller accepts:

~~~java
@PostMapping("/account/edit")
public String edit(@ModelAttribute Account account) {
    // Update profile.
    return "ok";
}
~~~

A request `displayName=Lan` sets `displayName`. Later, another pull request adds:

~~~java
private boolean verified;

public boolean isVerified() { return verified; }
public void setVerified(boolean verified) {
    this.verified = verified;
}
~~~

The model author only intended `verified` for an administrative workflow. Yet if the controller still property-binds directly from requests, `verified=true` now has a matching setter. The binding surface changed **without a single line changing in the controller**.

This is **mass assignment**, also called *over-posting*: clients send attribute names the product never meant to make editable, and the framework assigns them automatically because the target has a matching write path.

**The goal of this lesson** is to establish a code-review and testing workflow that:
1. Identifies every model/DTO change capable of widening the input contract.
2. Locks binding strictly to approved fields, even when models gain new setters.
3. Distinguishes setter/property binding, constructor binding, and JSON deserialization.
4. Controls nested properties, indexed paths, headers, and path variables.
5. Designs regression tests so an "innocent setter" never silently turns into a new edit capability.
6. Avoids confusing `@Valid` constraints with authorization, and never relies on denylists as the primary shield.

Content targets **Spring Framework 6.2, Java 17, and Spring Boot 3.5.7**. The runnable example uses Spring MVC, though the principles around `DataBinder`, model design, and input DTOs are equally critical in WebFlux.

## 2. Understanding Every Path Into an Object

### 2.1. `@ModelAttribute` with property binding

When a controller declares:

~~~java
@PostMapping("/profiles")
public String update(@ModelAttribute("profileForm") ProfileForm form) {
    return "done";
}
~~~

Spring MVC can pull request parameters—including query and form fields, plus URI template variables and headers per source precedence rules—to construct or populate the model attribute. Whenever the object has matching writable properties, field names can be bound.

Example form:

~~~text
displayName=Lan
contactEmail=lan@example.com
verified=true
preferences.notificationsEnabled=false
items[0].price=0
~~~

`verified`, `preferences.notificationsEnabled`, and `items[0].price` all belong in your threat model; clients are never constrained to the input elements rendered in the HTML UI. Users can append arbitrary query or form parameters.

**Never treat entity/domain model setters as public API by default.** A setter may exist for database mapping, tests, or internal business logic—that does not mean clients may invoke it indirectly via the binder.

### 2.2. Constructor binding

Spring Framework 6.1+ supports constructor binding for `@ModelAttribute`. Spring locates the required constructor parameters, resolves them from request values, and instantiates the object. This works well for immutable DTOs:

~~~java
public record ProfileChanges(
        String displayName,
        String contactEmail) {
}
~~~

A constructor makes the input list explicit and avoids arbitrary setters. **Yet adding a new constructor parameter or record component also widens the input contract.** If `boolean verified` is added to the record, constructor binding can now bind `verified=true`. PRs must review constructor signatures and record components, not setters alone.

Property binding can be restricted via:

~~~java
@InitBinder("profileForm")
void init(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
~~~

When `declarativeBinding=true`, constructor binding still binds constructor parameters, while property binding runs only if `allowedFields` is configured. This is **not an allowlist for constructor parameters**. Designing constructors to accept only genuinely public inputs is a separate requirement.

### 2.3. JSON `@RequestBody` does not follow the form binder's allowlist

~~~java
@PostMapping("/api/profiles")
public void update(@Valid @RequestBody ProfileJsonInput body) {
    // ...
}
~~~

Spring MVC reads JSON via `HttpMessageConverter`/Jackson. Jackson follows its own rules for properties, constructors, and deserialization; `WebDataBinder#setAllowedFields` for `@ModelAttribute` property binding **does not filter JSON properties automatically**.

Consequently, two separate surfaces must be reviewed independently:
- **Form/query/model attribute:** JavaBean/constructor binding, `WebDataBinder`, and `@InitBinder`.
- **JSON body:** Jackson DTOs, record constructors, setters, fields/creators, and Jackson configuration.

Reusing the exact same Java class for both paths is a red flag deserving close review. Whenever possible, create **dedicated input DTOs per use case** containing only the fields the product intends to make editable.

### 2.4. Validation and authorization do not replace each other

~~~java
@NotNull
private Boolean verified;
~~~

This annotation checks only whether a value is present; it **does not decide whether the caller is authorized to set `verified=true`**. `@Min`, `@Pattern`, `@Email`, and `@Valid` perform validation—they never turn an unsafe setter into authorized access.

Safe flow:

~~~text
HTTP request
    |
    v
Dedicated input DTO / constructor contract
    |
    v
Allowed property paths (if setter binding is needed)
    |
    v
Conversion + Bean Validation
    |
    v
Authenticated principal + authorization
    |
    v
Service applies permitted fields onto the domain entity
    |
    v
Dedicated response DTO, never serialize entities arbitrarily
~~~

## 3. Classifying Model Changes in Pull Requests

### 3.1. Risk matrix

| Change in PR | Binding risk | What to verify |
| --- | --- | --- |
| Adding `setVerified(boolean)` to entity | New setter can accept `verified=true` | Any `@ModelAttribute Entity` controller? Is an allowlist enforced? |
| Adding `setRole(String)` | Client can propose higher privileges | Never bind `role`; assign roles only in authorized services |
| Adding `setOwnerId(...)` | User can alter ownership | Derive scoped ID from path/principal and authorization |
| Adding `setInternalNote(...)` | Internal data becomes writable | Does any public DTO expose this field? |
| Adding `verified` component to record constructor | Constructor binding opens a new input | Audit constructor/`@BindParam` and input contract |
| Adding nested `preferences`/`settings` | Can expose paths like `settings.admin` | Audit wildcards and nested `allowedPaths` |
| Changing type from `String` to `List<X>` | Opens indexed paths | Check auto-grow, counts, conversion, and allowlist |
| Widening `setAllowedFields("address*")` | Wildcard admits future fields | Narrow to explicit paths |
| Switching `@ModelAttribute` to `@RequestBody` | Moves to Jackson rules | Test JSON unknown fields and permissions |
| Adding `@JsonProperty`/`@JsonAlias`/creator | Adds new JSON input keys or aliases | Audit both primary names and aliases |
| Adding `@BindParam` on constructor | Changes accepted HTTP key | Test public field names and edit permissions |
| Removing `setDeclarativeBinding(true)` | May re-enable property binding | Regression tests for extra setters |
| Removing `@ModelAttribute(binding=false)` | Model object may start getting bound | Confirm whether the contract really wants binding |
| Adding global `@ControllerAdvice @InitBinder` | Changes binder policy across controllers | Test advice scope and configuration ordering |
| Adding a custom converter or formatter | Previously unparseable strings may now bind | Audit valid values, field scope, and validation |

**Review trigger:** do not wait for controller files to change. Any change to models, DTOs, constructors, setters, nested types, converters, serializers, or binder configs can alter the input contract.

### 3.2. Reviewing a concrete diff

Before the change:

~~~java
public class ProfileForm {
    private String displayName;
    private String contactEmail;
    // Getters/setters for two properties.
}
~~~

After the change:

~~~java
public class ProfileForm {
    private String displayName;
    private String contactEmail;
    private boolean verified;
    private String timezone;
    // Getters/setters for all four properties.
}
~~~

The two new fields do not carry identical risk:
- `verified` is **protected state**: never allow users to change it merely by editing their profile.
- `timezone` may be a **public profile preference**, yet the current edit endpoint may not yet be authorized to accept it. Permit it only when the API/product contract requires it.

Review must answer **"Who, via which endpoint, may edit which field?"**, not simply `"Does this field have @NotNull?"`. New fields should remain **unbindable by default** until an explicit decision and tests are in place.

## 4. First Defense Layer: Dedicated Input DTOs

Never expose entities directly:

~~~java
// Anti-pattern: entity also exposes internal fields.
@PostMapping("/account/edit")
public void edit(@ModelAttribute AccountEntity entity) {
    accountRepository.save(entity);
}
~~~

Concise as this looks, every new setter on `AccountEntity` can mutate the input contract. Entities also carry nested associations, roles, owners, billing status, and persistence state.

Replace with a fixed request DTO:

~~~java
public record UpdateProfileRequest(
        String displayName,
        String contactEmail) {
}
~~~

In the service, look up the existing entity **by the authenticated principal or an authorized ID**, then apply only the fields belonging to the operation:

~~~java
// Method illustration, not a standalone Java file.
public void updateProfile(Account account, UpdateProfileRequest input) {
    account.changeDisplayName(input.displayName());
    account.changeContactEmail(input.contactEmail());
    // Do not touch role, ownerId, verified, or billingState.
}
~~~

Never use a mapping library configured to "copy every same-named property" from DTO to entity if adding a field to the DTO later will automatically copy it. Explicit mapping allowlists, manual mapping methods, or contract-tested mappers are safer.

### 4.1. Separate DTOs do not stay safe automatically forever

Once a developer adds a field to an input DTO, the surface can widen again. Therefore:
- Review every addition to constructor components, setters, Jackson creators, and aliases.
- Maintain an approved list of public fields per operation.
- When opening a new field, update authorization and tests **deliberately**.
- With Jackson, enforce an unknown-fields policy (`FAIL_ON_UNKNOWN_PROPERTIES` or equivalent) if fail-fast is desired.
- Never scatter `@JsonIgnore` across an entity as a substitute for dedicated DTOs; one omitted annotation can expose a field.

### 4.2. Never use an output DTO as an input DTO

An API response may display `verified`, `accountId`, or `role`. That **does not mean** clients may send them back in update requests. Separate them:

~~~text
ProfileResponse:
  accountId, displayName, contactEmail, verified, role

UpdateProfileInput:
  displayName, contactEmail
~~~

Using a single class for both reads and writes creates pressure to add UI-display properties, after which nobody notices the new setter became writable input.

## 5. Second Defense Layer: `setAllowedFields` for Property Binding

When a mutable JavaBean form is needed, specify an explicit allowlist:

~~~java
@InitBinder("profileForm")
void initProfileBinder(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
    binder.setAllowedFields("displayName", "contactEmail");
}
~~~

### 5.1. How the two mechanisms work together

- `setDeclarativeBinding(true)`: prioritizes constructor contracts and does not enable setter binding without `allowedFields`.
- `setAllowedFields(...)`: permits property binding only for property paths in the allowlist.

Per Spring Framework 6.2, allowed fields default to **all fields**, and allowlist matching is **case-sensitive**. Patterns support `*`, such as `name*` or `*Address`, yet broad wildcards can accidentally match new setters.

For the model in section 3, the allowlist:

~~~text
displayName
contactEmail
~~~

excludes:
- `verified`.
- `timezone`.
- `role`.
- `ownerId`.
- `settings.admin`.
- Unapproved nested indexed paths.

If `timezone` is opened later after product approval, the change must be explicit:

~~~java
binder.setAllowedFields(
        "displayName", "contactEmail", "timezone");
~~~

along with matching positive, negative, and authorization tests.

### 5.2. `getSuppressedFields()` is an important signal

Spring provides:

~~~java
String[] suppressed =
        binder.getBindingResult().getSuppressedFields();
~~~

Fields blocked by the allowlist are recorded here. **`getSuppressedFields()` does not necessarily create a `FieldError` or make `hasErrors()` return true.** Therefore, if you want to reject requests attempting to submit protected inputs, check it separately.

Handler example:

~~~java
@PostMapping("/form")
public ResponseEntity<?> update(
        @Valid @ModelAttribute("profileForm") ProfileForm form,
        BindingResult errors) {

    if (errors.getSuppressedFields().length > 0) {
        return ResponseEntity.badRequest()
                .body(Map.of("code", "UNEXPECTED_FIELDS"));
    }
    if (errors.hasErrors()) {
        return ResponseEntity.badRequest()
                .body(Map.of("code", "INVALID_INPUT"));
    }
    // Call service ...
}
~~~

This snippet illustrates part of a controller; the complete version is in section 9. **Never echo raw suppressed field names** if they might contain client-controlled Map keys, emails, or tokens; return generic error codes or safely canonicalized paths.

### 5.3. `setIgnoreUnknownFields(false)` is not enough

`DataBinder#setIgnoreUnknownFields(false)` makes unknown property binding fail, yet it **does not prevent drift when a new setter is added**: `verified` used to be unknown, and once a setter is added it is no longer unknown.

Thus "reject unknown" cannot replace "only approved fields." Never assume `@Valid` catches client attempts to alter sensitive fields either: if a setter accepts a valid Boolean, validation can pass completely.

### 5.4. Never use a denylist as the primary line of defense

~~~java
binder.setDisallowedFields(
        "role", "verified", "ownerId");
~~~

This list **names only what someone remembered to block**. When the model gains `isStaff`, `billingEnabled`, or `transferOwner`, the old denylist does not update itself. Spring officially recommends allowlists over `disallowedFields`; patches have been required in the past for denylist-check bypasses.

For example, Spring advisory `CVE-2025-22233` described affected versions 6.2.0–6.2.6 and identified 6.2.7 as fixed. The lesson is not to treat CVEs as a substitute for reviews, but **never to use brittle denylists as a security boundary**; stay on supported Spring versions and apply patches proactively.

## 6. Constructor Binding Must Also Be Audited on Model Changes

A record:

~~~java
public record ProfileCommand(
        String displayName,
        String contactEmail) {
}
~~~

has no setters, limiting property binding. With Spring constructor binding, each component is an input candidate. If a PR adds:

~~~java
public record ProfileCommand(
        String displayName,
        String contactEmail,
        boolean verified) {
}
~~~

then the input contract **has changed**, even with `setDeclarativeBinding(true)` enabled. Constructor arguments must be reviewed just like public fields.

### 6.1. `@BindParam` and renaming inputs

~~~java
public record ProfileCommand(
        @BindParam("display-name") String displayName,
        String contactEmail) {
}
~~~

`@BindParam` (since Spring Framework 6.1) on a constructor parameter or matching field allows a request key such as `display-name` to bind to `displayName`. Adding or changing this annotation lets clients submit **a new key**. Test old/new input names, compatibility, and authorization.

### 6.2. Indexed constructor arguments

In Spring Framework 6.2, constructor binding supports Lists/Maps/arrays with indexed/keyed paths such as `items[0].code` or `preferences[theme]`. If a PR adds a List to a constructor, audit:
- Collection lengths and index bounds.
- Nested child types and constructors.
- Which fields are genuinely public input.
- Resource/JSON/form field-count limits.
- Rules preventing clients from specifying owner/price/role.

`allowedFields` for property binding **does not automatically act as a constructor allowlist**. Keep constructor DTOs small, constrain types, and test declared inputs deliberately.

### 6.3. `@ModelAttribute(binding=false)` when only reading an object

Some handlers receive a preloaded object and must prevent requests from binding onto it. Spring supports:

~~~java
@ModelAttribute(value = "account", binding = false)
Account account
~~~

This is an illustrative parameter; Spring requires `account` to exist in the model or be resolved properly. `binding=false` means **do not apply request property binding to this attribute**; it neither loads the account nor checks permissions. Use it when reading a server-controlled model object while accepting updates via a separate DTO.

## 7. Nested Properties, Wildcards, and Map Keys in PRs

### 7.1. One nested setter can open multiple entry points

Suppose the model has:

~~~java
public class Preferences {
    private boolean notificationsEnabled;
    private boolean administrativeAlerts;

    public boolean isNotificationsEnabled() {
        return notificationsEnabled;
    }
    public void setNotificationsEnabled(boolean value) {
        notificationsEnabled = value;
    }

    public boolean isAdministrativeAlerts() {
        return administrativeAlerts;
    }
    public void setAdministrativeAlerts(boolean value) {
        administrativeAlerts = value;
    }
}
~~~

If `ProfileForm` exposes `getPreferences()` and the binder can traverse nested objects, paths such as:

~~~text
preferences.notificationsEnabled=true
preferences.administrativeAlerts=true
~~~

can be processed by property binding depending on the target structure. If a PR adds `setAdministrativeAlerts`, **even nested objects** must be audited.

Never write:

~~~java
binder.setAllowedFields("preferences*");
~~~

because the wildcard can cover future nested properties. List only approved fields:

~~~java
binder.setAllowedFields(
        "displayName",
        "contactEmail",
        "preferences.notificationsEnabled");
~~~

### 7.2. Collection indices and Map keys

Form parameter names can look like:

~~~text
addresses[0].city=Hanoi
addresses[0].ownerId=another-user
labels[public].name=Important
labels[secret@example.com].name=Unexpected
~~~

To let users edit `city` without altering ownership, select only the exact pattern:

~~~java
binder.setAllowedFields("addresses[*].city");
binder.setAutoGrowCollectionLimit(10);
~~~

**Note:** calling `setAllowedFields` twice in a row **replaces the previous list** rather than appending to it. To permit multiple fields, pass them all in **a single call**:

~~~java
binder.setAllowedFields(
        "displayName",
        "contactEmail",
        "addresses[*].city");
~~~

`setAutoGrowCollectionLimit(10)` caps certain list/array auto-growth scenarios; it **is not a total HTTP body quota**, does not bound arbitrary map keys, and does not stop clients from sending thousands of field names. Enforce body size, parameter count, index, and depth limits at the web/proxy layer and write boundary tests.

When Map keys are user-controlled, path names themselves can hold emails or tokens. Never echo raw suppressed paths or rejected values in error bodies or logs.

### 7.3. Headers and URI variables are also in the threat model

In annotated Spring MVC 6.2, model attribute binding can pull data from:
- request parameters (query/form).
- URI template variables.
- headers whose names match property names, subject to precedence rules when not overridden by request parameters.

Never use `@ModelAttribute` as the trusted source of ownership, role, or tenant ID. If the path contains `/accounts/{accountId}`, inject `@PathVariable` explicitly, verify the caller is authorized for that ID, and then call the service. Clients can supply a query/form field with the same name; never rely on implicit precedence for access control.

## 8. JSON Model Drift: Jackson Has Its Own Surface

### 8.1. Why doesn't `setAllowedFields` protect JSON?

Given:

~~~java
public class JsonAccountInput {
    private String displayName;
    private boolean verified;

    public void setDisplayName(String value) {
        displayName = value;
    }
    public void setVerified(boolean value) {
        verified = value;
    }
}
~~~

Jackson can deserialize JSON:

~~~json
{"displayName":"Lan","verified":true}
~~~

into a `JsonAccountInput` with `verified=true`, even if another controller defines an `@InitBinder` allowlist. This is an **illustrative anti-pattern**, not a safe endpoint.

A better approach is a JSON DTO containing only permitted properties, such as record `JsonProfileInput(String displayName, String contactEmail)`. Whenever a record component is added, the reviewer must ask: "should this field become JSON input?".

### 8.2. Failing on unknown JSON fields when needed

Jackson configuration controls whether unknown JSON keys are ignored or rejected. In Spring Boot, you can enable fail-fast behavior:

~~~properties
spring.jackson.deserialization.fail-on-unknown-properties=true
~~~

Sending `"verified":true` into a record **without** a `verified` field will then fail as an unreadable body (HTTP 400). This catches clients sending out-of-contract keys, yet **does not stop drift if someone adds `verified` to the input DTO itself**: the new field becomes a known property. Schema/constructor reviews and regression tests remain essential.

If an API must allow unknown fields for backwards compatibility, it remains safe as long as it deserializes into a DTO with approved fields and **never auto-maps unknown data onto the domain**. Choose strict or tolerant JSON per your product contract, never treating strict mode as a substitute for security review.

### 8.3. Annotations and creators that alter accepted inputs

Whenever a PR adds or modifies:
- `@JsonProperty`, `@JsonAlias`.
- `@JsonCreator` and constructor parameters.
- Setters visible to Jackson.
- Field visibility rules.
- Custom deserializers.
- `Map`/`JsonNode`/`Object` accepting unstructured input.
- Polymorphic types / `@JsonTypeInfo`.
- Global `ObjectMapper` configuration.

treat it as an **API surface change**. Never assume a Java class accepts only property names matching its getters; aliases and creators can introduce additional public input names.

### 8.4. Never use deserialization for authorization

`@JsonIgnore` and read-only properties help constrain mapping, yet authorization is not Jackson's job. If a user submits another account's `accountId`, successful JSON parsing does not mean they may edit it; the service must verify principal, tenant, and ownership.

## 9. Runnable Project: Spring Boot 3.5.7 / Java 17

The example below demonstrates **a mutable DTO that deliberately gained extra setters during refactoring**, guarded by `@InitBinder` and `allowedFields`, alongside a JSON input record with strict unknown-field handling. Tests cover both failure cases and the happy path.

### 9.1. Project structure

~~~text
pom.xml
src/main/
  java/com/example/bindingreview/
    BindingReviewApplication.java
    ProfileForm.java
    JsonProfileInput.java
    ProfileUpdateService.java
    ProfileController.java
    SafeErrorAdvice.java
  resources/
    application.properties
src/test/java/com/example/bindingreview/
  ProfileBindingContractTest.java
  ProfileHttpSecurityTest.java
~~~

In production, **keep protected fields off input DTOs entirely**. `ProfileForm` here intentionally includes `verified` and `timezone` to verify that newly added setters **are not automatically exposed** on the existing form endpoint.

### 9.2. `pom.xml`

~~~xml
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

    <groupId>com.example</groupId>
    <artifactId>model-binding-review</artifactId>
    <version>1.0.0</version>

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
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

Uses the Spring MVC Servlet stack; omit `spring-boot-starter-webflux` in this example. `spring-boot-starter-validation` provides the Jakarta provider, and `spring-boot-starter-test` brings JUnit 5 and MockMvc.

### 9.3. Main application

~~~java
// src/main/java/com/example/bindingreview/BindingReviewApplication.java
package com.example.bindingreview;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BindingReviewApplication {
    public static void main(String[] args) {
        SpringApplication.run(BindingReviewApplication.class, args);
    }
}
~~~

### 9.4. `ProfileForm`: spotting drift when setters are added

~~~java
// src/main/java/com/example/bindingreview/ProfileForm.java
package com.example.bindingreview;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class ProfileForm {

    @NotBlank
    @Size(max = 80)
    private String displayName;

    @NotBlank
    @Email
    private String contactEmail;

    // Assume another PR added these two setters.
    // Neither is approved for the profile edit endpoint.
    private boolean verified;
    private String timezone;

    public ProfileForm() {}

    public String getDisplayName() {
        return displayName;
    }
    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getContactEmail() {
        return contactEmail;
    }
    public void setContactEmail(String contactEmail) {
        this.contactEmail = contactEmail;
    }

    public boolean isVerified() {
        return verified;
    }
    public void setVerified(boolean verified) {
        this.verified = verified;
    }

    public String getTimezone() {
        return timezone;
    }
    public void setTimezone(String timezone) {
        this.timezone = timezone;
    }
}
~~~

`@NotBlank`/`@Email`/`@Size` validate public fields only; no constraint grants permission for clients to set `verified`. By default `verified=false` and `timezone=null`. After form binding with the allowlist, they must stay unchanged even if the request sends matching names.

**In real projects**, rather than keeping a DTO with protected fields just to test forever, remove them from the input DTO. The demo retains them to build a clear regression/security contract test.

### 9.5. JSON record accepting only public input

~~~java
// src/main/java/com/example/bindingreview/JsonProfileInput.java
package com.example.bindingreview;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record JsonProfileInput(
        @NotBlank @Size(max = 80) String displayName,
        @NotBlank @Email String contactEmail) {
}
~~~

When Jackson reads JSON, only two record components are expected as input. If anyone adds `boolean verified` to the record, this exact file shows up in the PR diff and schema tests must be reviewed and updated.

### 9.6. Service applying strictly the two approved fields

~~~java
// src/main/java/com/example/bindingreview/ProfileUpdateService.java
package com.example.bindingreview;

import org.springframework.stereotype.Service;
import java.util.Map;

@Service
public class ProfileUpdateService {

    public Map<String, Object> update(
            String displayName, String contactEmail) {

        // Simulate an entity loaded by the server after authorization.
        Account account = new Account();
        account.changeContact(displayName, contactEmail);

        return Map.of(
                "displayName", account.displayName,
                "contactEmail", account.contactEmail,
                "role", account.role,
                "verified", account.verified);
    }

    private static final class Account {
        private String displayName = "Old";
        private String contactEmail = "old@example.com";
        private final String role = "USER";
        private final boolean verified = false;

        void changeContact(String name, String email) {
            this.displayName = name;
            this.contactEmail = email;
        }
    }
}
~~~

There is no database in the demo; it simulates safely loaded server data. In production, the service must verify principal/tenant/ownership before mutating a real entity. The key here is that the service **accepts and applies only the two approved values**, never calling `BeanUtils.copyProperties(request, entity)` or a generic mapper that could copy new properties automatically.

Returning `role=USER` and `verified=false` is solely so tests confirm protected state stays unchanged. Real systems need a dedicated response DTO and careful review of which fields may be exposed.

### 9.7. Controller: `@InitBinder` preserves the invariant contract

~~~java
// src/main/java/com/example/bindingreview/ProfileController.java
package com.example.bindingreview;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api/profiles")
public class ProfileController {

    private final ProfileUpdateService service;

    public ProfileController(ProfileUpdateService service) {
        this.service = service;
    }

    @InitBinder("profileForm")
    void configure(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
        binder.setAllowedFields(
                "displayName", "contactEmail");
    }

    @PostMapping(path = "/form",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> updateForm(
            @Valid @ModelAttribute("profileForm") ProfileForm form,
            BindingResult errors) {

        // A suppressed property is not a FieldError by default.
        if (errors.getSuppressedFields().length > 0) {
            return ResponseEntity.badRequest()
                    .body(Map.of("code", "UNEXPECTED_FIELDS"));
        }

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest()
                    .body(Map.of("code", "INVALID_INPUT"));
        }

        return ResponseEntity.ok(
                service.update(
                        form.getDisplayName(),
                        form.getContactEmail()));
    }

    @PostMapping(path = "/json",
                 consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<?> updateJson(
            @Valid @RequestBody JsonProfileInput input) {

        return ResponseEntity.ok(
                service.update(
                        input.displayName(),
                        input.contactEmail()));
    }
}
~~~

Explanation:
1. `@InitBinder("profileForm")` applies to the binder of the exact model attribute named `profileForm`.
2. `setDeclarativeBinding(true)` keeps the setter-binding contract explicit.
3. `setAllowedFields("displayName","contactEmail")` permits only the two approved properties.
4. If a client also submits `verified`/`timezone`, the binder records suppressed fields. The handler returns 400 **without echoing field names or raw values**.
5. If public input fails `@NotBlank`/`@Email`, `BindingResult` immediately after the form returns `INVALID_INPUT`.
6. The JSON endpoint uses a separate `JsonProfileInput`; the form allowlist **is not** a JSON filter. JSON unknown-field handling is shown next.
7. The service processes only `displayName` and `contactEmail`; authorization on the real entity is still required in production.

### 9.8. JSON strict mode and error advice without leaking internals

**`src/main/resources/application.properties`:**

~~~properties
spring.jackson.deserialization.fail-on-unknown-properties=true
server.error.include-message=never
server.error.include-stacktrace=never
server.error.include-binding-errors=never
~~~

Strict JSON causes inputs sending `verified` outside `JsonProfileInput` to fail instead of being ignored. The two protections differ: **the DTO protects domain fields**, while **strict mode** helps catch out-of-contract client payloads.

**`SafeErrorAdvice.java`:**

~~~java
// src/main/java/com/example/bindingreview/SafeErrorAdvice.java
package com.example.bindingreview;

import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.Map;

@RestControllerAdvice
public class SafeErrorAdvice {

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<Map<String, String>> invalidJson(
            HttpMessageNotReadableException ignored) {

        // Do not return Jackson parser exceptions or raw JSON.
        return ResponseEntity.badRequest()
                .body(Map.of("code", "INVALID_JSON"));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, String>> invalidObject(
            MethodArgumentNotValidException ignored) {

        // Do not return FieldError.rejectedValue.
        return ResponseEntity.badRequest()
                .body(Map.of("code", "INVALID_INPUT"));
    }
}
~~~

This advice is tailored for the demo; in production, standardize on `ProblemDetail`, stable error codes, safe issue paths, and multiple locales. Still, never return raw `BindingResult`/`ConstraintViolation` objects or exception messages in public responses. Strict JSON violations caused by unknown `verified` are handled safely with `INVALID_JSON`.

## 10. Testing: Catching Setter Drift Before Production

### 10.1. Direct unit tests on `WebDataBinder` and JavaBean descriptors

~~~java
// src/test/java/com/example/bindingreview/ProfileBindingContractTest.java
package com.example.bindingreview;

import org.junit.jupiter.api.Test;
import org.springframework.beans.BeanUtils;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.web.bind.WebDataBinder;

import java.beans.PropertyDescriptor;
import java.util.Arrays;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ProfileBindingContractTest {

    @Test
    void unprotectedPropertyBindingSeesNewSetter() {
        ProfileForm form = new ProfileForm();
        WebDataBinder open =
                new WebDataBinder(form, "profileForm");

        open.bind(new MutablePropertyValues(
                Map.of("verified", "true")));

        // Demonstrates the attack surface without an allowlist.
        assertTrue(form.isVerified());
    }

    @Test
    void guardedBinderSuppressesUndeclaredFields() {
        ProfileForm form = new ProfileForm();
        WebDataBinder guarded =
                new WebDataBinder(form, "profileForm");

        new ProfileController(new ProfileUpdateService())
                .configure(guarded);

        guarded.bind(new MutablePropertyValues(Map.of(
                "displayName", "Lan",
                "contactEmail", "lan@example.com",
                "verified", "true",
                "timezone", "Sensitive-zone"
        )));

        assertEquals("Lan", form.getDisplayName());
        assertEquals("lan@example.com", form.getContactEmail());
        assertFalse(form.isVerified());
        assertNull(form.getTimezone());

        Set<String> suppressed = Set.copyOf(Arrays.asList(
                guarded.getBindingResult().getSuppressedFields()));
        assertEquals(Set.of("verified", "timezone"), suppressed);
        assertFalse(guarded.getBindingResult().hasErrors());
        // Suppressed fields by themselves are not validation errors.
    }

    @Test
    void anyNewWritablePropertyRequiresReview() {
        Set<String> actualWritable = Arrays.stream(
                BeanUtils.getPropertyDescriptors(ProfileForm.class))
                .filter(p -> p.getWriteMethod() != null)
                .map(PropertyDescriptor::getName)
                .collect(Collectors.toSet());

        assertEquals(Set.of(
                "displayName", "contactEmail", "verified", "timezone"),
                actualWritable,
                "A setter changed the binding surface: review policy and tests");
    }

    @Test
    void serviceCanOnlyApplyPublicFields() {
        Map<String, Object> output =
                new ProfileUpdateService().update(
                        "Lan", "lan@example.com");

        assertEquals("Lan", output.get("displayName"));
        assertEquals("lan@example.com",
                output.get("contactEmail"));
        assertEquals("USER", output.get("role"));
        assertEquals(false, output.get("verified"));
    }
}
~~~

**Why the reflection test matters:** if a developer adds a new setter—say `setBillingEnabled(boolean)`—the set of writable properties changes and the third test **fails**, forcing the reviewer to classify the field and deliberately update the inspected list. This is not an automatic security system; it is a **CI tripwire** flagging model-surface changes.

For projects using Lombok `@Data`, `@Setter`, builders, records, Kotlin data classes, or Jackson visibility settings, reviews must inspect **generated properties and JSON creators** as well, not only Java source setter methods. A JavaBean descriptor test covers `ProfileForm`'s setter surface; it **does not** replace JSON contract tests.

### 10.2. MockMvc integration tests for form and JSON

~~~java
// src/test/java/com/example/bindingreview/ProfileHttpSecurityTest.java
package com.example.bindingreview;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProfileHttpSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validFormEditsOnlyPublicFields() throws Exception {
        mvc.perform(post("/api/profiles/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "Lan")
                .param("contactEmail", "lan@example.com"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.displayName").value("Lan"))
            .andExpect(jsonPath("$.contactEmail")
                    .value("lan@example.com"))
            .andExpect(jsonPath("$.role").value("USER"))
            .andExpect(jsonPath("$.verified").value(false));
    }

    @Test
    void extraFormSettersAreRejected() throws Exception {
        mvc.perform(post("/api/profiles/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "Lan")
                .param("contactEmail", "lan@example.com")
                .param("verified", "true")
                .param("timezone", "Sensitive-zone"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("UNEXPECTED_FIELDS"))
            .andExpect(content().string(not(
                    containsString("Sensitive-zone"))));
    }

    @Test
    void invalidFormStillRunsBeanValidation() throws Exception {
        mvc.perform(post("/api/profiles/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", " ")
                .param("contactEmail", "bad-email"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_INPUT"));
    }

    @Test
    void jsonUnknownProtectedFieldIsNotAccepted()
            throws Exception {
        mvc.perform(post("/api/profiles/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"displayName":"Lan",
                     "contactEmail":"lan@example.com",
                     "verified":true}
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_JSON"));
    }

    @Test
    void validJsonHasOnlyExpectedPublicInput()
            throws Exception {
        mvc.perform(post("/api/profiles/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"displayName":"Lan",
                     "contactEmail":"lan@example.com"}
                    """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.role").value("USER"))
            .andExpect(jsonPath("$.verified").value(false));
    }

    @Test
    void invalidJsonValueIsValidated() throws Exception {
        mvc.perform(post("/api/profiles/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"displayName":"",
                     "contactEmail":"bad-email"}
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_INPUT"));
    }
}
~~~

**Expected outcome:** 10 JUnit tests PASS (4 `ProfileBindingContractTest` + 6 `ProfileHttpSecurityTest`) with Spring Boot 3.5.7 and the project layout above. This is an **analytical expectation from API/code review**, not observed Maven execution output.

Run:

~~~bash
mvn test
~~~

Run only the contract tests:

~~~bash
mvn -Dtest=ProfileBindingContractTest test
~~~

Start the server:

~~~bash
mvn spring-boot:run
~~~

Send a valid request:

~~~bash
curl -i -X POST http://localhost:8080/api/profiles/form \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "displayName=Lan" \
  --data-urlencode "contactEmail=lan@example.com"
~~~

Expected JSON response (no key-order guarantee):

~~~json
{
  "displayName": "Lan",
  "contactEmail": "lan@example.com",
  "role": "USER",
  "verified": false
}
~~~

Try an extra field:

~~~bash
curl -i -X POST http://localhost:8080/api/profiles/form \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "displayName=Lan" \
  --data-urlencode "contactEmail=lan@example.com" \
  --data-urlencode "verified=true"
~~~

Expected HTTP 400, body `{"code":"UNEXPECTED_FIELDS"}`. If the controller lacked the allowlist, `verified` has a setter and could be set to true as demonstrated in `unprotectedPropertyBindingSeesNewSetter`.

### 10.3. Why is asserting status 400 alone insufficient?

If you only assert that bad requests return 400, you can miss:
- Out-of-contract input getting bound and only failing a later constraint.
- Protected fields being assigned before the service happens to overwrite them.
- A new mapping copying extra fields into the domain unobserved by HTTP tests.
- JSON unknown keys previously failing until a PR added the component to the DTO.
- Another controller missing `@InitBinder` still accepting the protected field.

Combine **contract tests**, **binder tests**, **HTTP-level tests**, **service mapping tests**, and (in production) **authorization tests**. At minimum, have a test proving protected fields **remain unchanged** after submitting malicious payloads.

## 11. PR/CI Review Workflow for Model Changes

### Step 1 — Identify all binding paths

Locate everywhere the class appears:
- `@ModelAttribute` in MVC/WebFlux annotated controllers.
- `@RequestBody`/`@RequestPart` and JSON DTO mappings.
- Custom `WebDataBinder`, `@InitBinder`, and `@ControllerAdvice`.
- Constructor binding, records, and `@BindParam`.
- Generated setters from Lombok/Kotlin.
- Generic mappers, form-to-entity converters, and property-copying code.
- Service/domain layers accepting the request object directly.

Do not grep only direct controllers: an object can also be resolved from the model/session or consumed by another method.

### Step 2 — Build a public/protected field table

| Field | Who may supply it? | Public input? | Where verified |
| --- | --- | --- | --- |
| `displayName` | Profile owner | Yes, after auth | DTO + binder + service |
| `contactEmail` | Profile owner | Yes, after auth | DTO + validator + service |
| `timezone` | Not yet approved by product | Not yet | Regression test |
| `verified` | Server/admin workflow | No | Service-only, no setter binding |
| `role` | Server/admin per policy | No | Security/authorization |
| `ownerId` | Server/principal/verified path | Never client-chosen | Service permission check |
| `billingState` | Billing subsystem | No | Domain invariant |

This table can live in API schema or code-ownership documentation; in a PR, update the right place whenever a field is intentionally opened. Never infer permissions from annotations like `@NotNull` or variable names.

### Step 3 — Audit every new property path

Inspect:
- New setters, record components, and constructor parameters.
- Nested objects, collections, and map properties.
- `@JsonProperty`, `@JsonAlias`, polymorphism, and creator metadata.
- `@BindParam` and field-name aliases.
- Binder allowlist patterns, especially `*` wildcards.
- `setDeclarativeBinding` and `@ModelAttribute(binding=false)`.
- `ConversionService`/custom editors that might make a previously unparseable value bindable.
- Model attributes loaded from the database/session and subsequently bound again.

Never ask only "is the new field in the HTML form?". HTML does not constrain handcrafted HTTP requests.

### Step 4 — Update tests before merging

At minimum:
1. Requests with only public fields are accepted.
2. Requests attempting to send each protected field leave protected state unchanged.
3. New fields outside the allowlist are rejected or ignored per contract.
4. JSON bodies with extra properties follow policy (strict vs. tolerant).
5. Out-of-scope nested/indexed/map-key paths do not bind.
6. Constructor DTO changes fail schema/contract tests until reviewed.
7. Validation still runs on public fields.
8. Services never copy all properties from input onto entities.
9. Callers with different roles/tenants cannot edit unowned objects.

### Step 5 — Review compatibility and migrations

Exposing a new field is an **API change**, not just adding a Java property:
- Will older clients keep working?
- If newer clients send a field absent from older backends, is it ignored or rejected?
- Do multi-version backend rollouts require feature flags?
- What are the null/default semantics for optional fields?
- If opening a field like `timezone`, is it safely wired through to the service update?
- Are error message translations and OpenAPI docs updated?

Never open wildcards "to avoid errors from new clients" during rolling upgrades; exposing all future fields is an unnecessary security tradeoff.

### Step 6 — Refresh security reviews on version/framework upgrades

A Spring or Jackson upgrade can change property matching, introspection, or constructor behavior. Review security patches, test malicious payloads, and run regression suites in a real context. `disallowedFields` has a history of security advisories; dedicated DTOs, allowlists, and tests minimize reliance on denylist behavior.

## 12. Traps That Cause Reviews to Miss Input Surfaces

| Scenario | Why it is dangerous | Fix |
| --- | --- | --- |
| Controller unchanged, only entity gained a setter | Binder auto-matches the new field | Never bind entities directly; DTO + allowlist |
| `@Valid` present so assumed safe | Validation does not decide permissions | Authorization, DTO mapping |
| Using only `setDisallowedFields` | Each new field must be remembered | Explicit `setAllowedFields` |
| `setIgnoreUnknownFields(false)` | New setter turns unknown into known | Contract tests + allowlist |
| `allowedFields("settings*")` | Wildcard matches future nested fields | Enumerate approved paths explicitly |
| Calling `setAllowedFields` twice | Second call replaces the first list | Pass all paths in a single call |
| Checking only `errors.hasErrors()` | Suppressed input is not a `FieldError` | Check `getSuppressedFields()` |
| Skipping review because record is immutable | Adding a constructor component opens new input | Test constructor contract |
| Relying on `@InitBinder` for `@RequestBody` | Jackson JSON uses a different pipeline | JSON DTO / strict policy |
| Relaxing because JSON unknown-field fails | Adding property to DTO makes it known | Schema diff gate |
| Using output DTO as input DTO | Readable fields are not automatically editable | Separate read/write DTOs |
| New nested collection gains a setter | Exposes `items[0].price` or Map keys | Path allowlist + size caps |
| Mapper copying all properties | New DTO field updates entity automatically | Explicit service mapping |
| Owner ID placed in request body | Client picks target object/tenant | Use authorized principal/path |
| Testing only HTML UI | Clients send arbitrary HTTP parameters | HTTP negative tests |
| Another controller lacks binder rules | Local `@InitBinder` protects only its controller | Test every entrypoint or scoped advice |
| Logging raw suppressed field paths | Map keys can carry emails/tokens | Redact/canonicalize logs |
| Reading only source-code getters | Lombok/Jackson can generate accessors/aliases | Inspect effective runtime binding contract |
| Testing only happy paths | Never catches mass assignment | Fuzz unauthorized property names |

## 13. Self-Practice Exercises

1. Add `boolean billingEnabled` and a setter to `ProfileForm`, then run the reflection test. Explain why the test failure is a **review signal**, not a broken test to delete.
2. Keep the allowlist unchanged and send `billingEnabled=true` via form; inspect suppressed fields, the 400 response, and unchanged domain state.
3. Product approves `timezone` as a public preference. Update DTO/allowlist/service/tests explicitly while keeping `verified` protected.
4. Convert mutable `ProfileForm` into an immutable record and enable `setDeclarativeBinding(true)`. Try adding a protected constructor component and explain why the flag alone does not block it.
5. Create nested `preferences.notificationsEnabled` and `preferences.administrativeAlerts`. Allow binding only `notificationsEnabled`; test a broad wildcard and then fix it.
6. Send JSON containing unknown `verified` with strict mode enabled and disabled. Confirm that once the JSON input DTO includes `verified`, strict mode **no longer blocks** that key.
7. Apply `@BindParam("display-name")` on a record component and write a test for the accepted HTTP parameter name.
8. Create two controllers sharing the same DTO; place a local `@InitBinder` on one controller, then test the other to observe that protection **does not automatically propagate**.
9. Create a Map property with email keys; verify policies handling paths/rejected values never leak information in responses or logs.
10. Write an architecture rule or test listing writable bean properties and JSON input properties. Whenever a property is added, CI must require reviewer confirmation of the contract.
11. Inspect an API using `@ModelAttribute(binding=false)`: remove the flag in a test branch to observe the behavior difference, then restore it.
12. Review a project using generic `BeanUtils.copyProperties` and identify which future fields could accidentally flow into the domain.

## 14. Checklist Before Approving a Model-Change PR

- [ ] Listed all endpoints using the modified class, including `@ModelAttribute`, `@RequestBody`, constructor binding, JSON creators, and shared DTOs.
- [ ] Class is a dedicated input DTO, not a domain/JPA entity or arbitrarily reused response DTO.
- [ ] Every new setter, record component, and constructor arg is classified as public or protected.
- [ ] `@InitBinder`/`setAllowedFields` is present wherever property binding is required, without relying on denylists.
- [ ] `setDeclarativeBinding(true)` is enabled when restricting setter binding; constructor parameters are also audited.
- [ ] Wildcard/nested/indexed allowed paths cannot accidentally match protected future fields.
- [ ] `hasErrors()` is never treated as a substitute for checking `getSuppressedFields()`.
- [ ] `@Valid` enforces data constraints while authorization lives at the service/security boundary.
- [ ] JSON `@RequestBody` has its own DTO and unknown-field policy; `allowedFields` is not expected to filter JSON.
- [ ] Services copy only approved fields; `role`/`owner`/`verified`/`billingState` never come from HTTP forms or JSON.
- [ ] Negative tests exist for new setters, nested paths, unknown JSON keys, and permission regressions.
- [ ] Schema/reflection/contract tests make input-surface changes explicit in CI.
- [ ] Responses and logs never echo raw suppressed fields, rejected values, or sensitive Map keys.
- [ ] Spring/Jackson patches, compatibility, and rollout plans are checked when intentionally opening a field.
- [ ] Documentation, OpenAPI specs, and error messages accurately reflect the updated contract.

## 15. Conclusion

**A new field must never become editable merely because it appeared in a Java model.** In Spring Framework, setters, constructor parameters, nested properties, and Jackson inputs are surfaces requiring the same review rigor as API endpoints. The most durable defense combines:

1. **Dedicated input DTOs** containing only permitted fields.
2. **Explicit allowlists** whenever property binding remains necessary.
3. **Declarative/constructor binding** with an audited constructor contract.
4. **Explicit service mapping** after authentication and authorization.
5. **Negative regression tests** that alert CI whenever a new setter or field appears.
6. **Separate review of form and JSON paths** to prevent vulnerabilities from false assumptions.

If a PR adds a setter without updating the input contract, authorization, and tests, treat it as an **unreviewed surface change**, never as automatic permission to edit.

## 16. References

- Spring Framework 6.2 — MVC `@InitBinder`, model design, `allowedFields`, `declarativeBinding`: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Framework 6.2 — MVC `@ModelAttribute` and constructor/property binding: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework 6.2 — MVC Data Binding: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-data-binding.html
- Spring Framework 6.2 — Core DataBinder Javadoc: https://docs.spring.io/spring-framework/docs/6.2.13/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework 6.2 — `@BindParam` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.13/javadoc-api/org/springframework/web/bind/annotation/BindParam.html
- Spring Framework 6.2 — MVC `@RequestBody`: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring Framework 6.2 — WebFlux DataBinder safety: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-initbinder.html
- Spring Security Advisory — CVE-2025-22233: https://spring.io/security/cve-2025-22233/
- Spring Security Advisory — CVE-2024-38820: https://spring.io/security/cve-2024-38820/
- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- OWASP — Mass Assignment Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html
