# Restricting Bound Fields to Prevent Out-of-Contract Property Modification in Spring MVC

> **Context:** Spring Web MVC (Servlet stack), Java 17+, and Spring Boot 3.x. The focus is preventing **mass assignment / over-posting**: when a client sends extra field names outside the API contract and the framework inadvertently assigns them to properties the user is not permitted to modify. This lesson covers DTO design, `@InitBinder` with `WebDataBinder#setAllowedFields`, checking suppressed fields, restricting constructor binding, distinguishing form binding from JSON deserialization, and controlling updates in the business layer.

## 1. The Problem: Clients Can Send More Than the UI Displays

Suppose an endpoint allows users to update only their display name and bio:

```http
POST /profiles/42
Content-Type: application/x-www-form-urlencoded

displayName=Lan&bio=Java+learner
```

An arbitrary client can append:

```http
POST /profiles/42
Content-Type: application/x-www-form-urlencoded

displayName=Lan&bio=Java+learner&admin=true&ownerId=7
```

The fields `admin` and `ownerId` **are not part of the profile editing contract**. The fact that the HTML UI does not render corresponding inputs does not stop a client from submitting those parameters.

**Unsafe** example:

```java
// Risk illustration, do not use in a real application.
@PostMapping("/profiles/{id}")
public String update(@PathVariable long id,
                     @ModelAttribute Account account) {
    accountRepository.save(account);
    return "saved";
}
```

If `Account` exposes public setters for `admin`, `role`, or `ownerId`, property binding can assign those client-supplied fields to the object. Putting an ID in the URL does not automatically verify ownership; calling `save` does not guarantee the user is permitted to modify the entire object.

**Principle:** controlling **which fields the client is allowed to supply** and **which business properties may be modified** are two separate boundaries. Safe binding does not replace authentication, authorization, or record ownership checks.

## 2. Where Does Spring MVC Binding Operate?

With `@ModelAttribute`, Spring MVC creates or retrieves a model object, then uses `WebDataBinder` to accept request data and convert types for the object. Input sources can include request parameters (query string/form data), URI variables, or request headers per the `@ModelAttribute` mechanism; request parameters take appropriate precedence on name collisions.

Example:

```java
@PostMapping("/profiles")
public void update(@ModelAttribute ProfileForm form) {
    // form is created/populated by Spring before the method runs.
}
```

With a mutable JavaBean, fields matching public setters can be populated via **property binding**. Spring also supports **constructor binding**, where inputs matching constructor parameters are used to instantiate the object. For objects that may hold privileged data, exposing a broad object with many setters without restricting inputs is risky.

Flow diagram:

```text
HTTP form/query/path inputs
          |
          v
Handler mapping selects controller method
          |
          v
@ModelAttribute creates/retrieves object
          |
          v
WebDataBinder
    ├─ constructor binding (constructor parameters)
    └─ property binding (setters/fields per configuration)
          |
          v
BindingResult (conversion errors, validation, suppressed fields)
          |
          v
Controller checks errors and permissions -> updates authorized properties
```

**Distinguish three questions:**

1. **Which fields to bind?** Addressed by dedicated DTOs/forms, `setAllowedFields`, or intentional constructor binding.
2. **Are values valid?** Addressed by validation (`@Valid`, Bean Validation, application logic).
3. **Who is allowed to change what on which resource?** Addressed by authorization, ownership checks, and server-side business rules.

A value can be completely **type-valid** (e.g., `admin=true`) yet still **prohibited from being updated**.

## 3. Preferred Approach: Input DTO Containing Only Allowed Fields

Create an object dedicated to the edit operation, separate from the entity persisted in the database:

```java
public record EditProfileRequest(String displayName, String bio) {
}
```

The contract specifies two fields: `displayName` and `bio`. Because `admin`, `role`, and `ownerId` are absent, business code cannot accidentally copy those properties from the DTO.

Example of intentional updating:

```java
// Business logic illustration, not a standalone program.
@PostMapping("/profiles/{id}/edit")
public String edit(@PathVariable long id,
                   @ModelAttribute EditProfileRequest input,
                   Principal principal) {
    Account account = accountRepository.findById(id)
            .orElseThrow(() -> new ResponseStatusException(
                    HttpStatus.NOT_FOUND));

    authorizationService.requireCanEdit(principal, account);
    account.setDisplayName(input.displayName());
    account.setBio(input.bio());
    accountRepository.save(account);
    return "saved";
}
```

This snippet assumes the application provides `Account`, `accountRepository`, and `authorizationService`. The key point is **assigning only the two permitted properties** onto a server-resolved and authorized entity.

DTOs are the preferred option because the type structure expresses the contract directly in source code. However, understand accurately that with `@ModelAttribute`, **constructor binding only restricts parameters declared in the constructor**; if a DTO still has other setters or configuration permits subsequent property binding, control that mechanism as shown in Section 5.

**Avoid binding directly into JPA entities** containing properties such as `id`, `tenantId`, `owner`, `status`, `balance`, `approved`, `isAdmin`, or `permissions`. A persistence entity generally has a wider surface than an API contract.

## 4. `@InitBinder` + `setAllowedFields`: Allowed Fields List

When property binding into a mutable JavaBean is required, proactively register an **allowlist**:

```java
@InitBinder("profileForm")
void initProfileBinder(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "bio");
}
```

- `@InitBinder("profileForm")`: applies binder customization to the model attribute named `profileForm` within the controller's scope. The name must match `@ModelAttribute("profileForm")` on the handler method.
- `WebDataBinder`: the binder Spring MVC creates **per eligible request/target** to perform binding and conversion.
- `setAllowedFields("displayName", "bio")`: permits property binding for **only** these two names. Other fields, including `admin`, are not written via setter/property binding.
- Field name strings in the allowlist are **case-sensitive**; use exact JavaBean property names. Wildcards are supported but should be used very sparingly.

Example HTTP form:

```text
displayName=Lan&bio=Java+learner&admin=true
```

With the restricted binder, `displayName` and `bio` are accepted; `admin` is excluded from property binding. If the `admin` property defaults to `false`, it remains `false` after binding.

### 4.1. Is `setDisallowedFields` a Good Choice?

```java
// Not recommended as the primary defense.
binder.setDisallowedFields("admin", "role", "ownerId");
```

A blocklist only enumerates fields already known to be dangerous. A new property such as `discountLimit` or `securityFlags` can later be added to the model while someone forgets to update the blocklist. Therefore, an **explicit allowlist** is safer and easier to review. In newer Spring Framework documentation, `setDisallowedFields` is also considered fragile and on a deprecation path in corresponding versions; prefer `setAllowedFields`.

### 4.2. Nested Property Names, Collections, and Wildcards

Spring can bind into property paths, not just flat properties:

```text
contact.email
addresses[0].city
settings[theme]
```

The allowlist can name the exact paths needed, for example:

```java
binder.setAllowedFields(
        "displayName",
        "contact.email",
        "addresses[0].city");
```

This illustrates a form object that genuinely has those nested properties. Do not blindly use `addresses*` or `*` when the contract allows only specific fields: wildcards widen the input surface and can allow modifying other elements or auxiliary properties. If a list needs flexible editing, enforce bounds on element count, valid indices, and validate each property inside a DTO instead of letting the client dictate arbitrary paths.

**Limitation note:** `setAllowedFields` governs **property binding**. It does not govern every object creation mechanism or every other data-writing path—in particular, it is not a default barrier for JSON `@RequestBody`. See Section 7.

## 5. Constructor Binding and `setDeclarativeBinding(true)`

Starting in Spring Framework **6.1**, `WebDataBinder` supports:

```java
@InitBinder
void initBinder(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
```

When this flag is enabled:

- **Constructor binding** continues to work, based on the declared constructor parameters.
- **Property binding** occurs only if the binder has `allowedFields` configured.

This lets you design record/immutable DTOs whose constructors accept only contract fields while preventing unintended setter binding. If a constructor accepts `admin` or `ownerId`, those values **can still be bound via the constructor**; the flag cannot make an unsafe constructor safe. Declare only components you truly accept from the client.

Example using immutable input:

```java
// Illustrative snippet for Spring Framework 6.1+.
public record UpdateContact(String displayName, String phone) {
}

@ControllerAdvice
class BindingPolicy {

    @InitBinder
    void bindOnlyDeclaredFields(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
    }
}
```

This is a broad policy option for controllers covered by `@ControllerAdvice`; do not apply it unexpectedly across the whole application without auditing existing forms that previously relied on setter binding. For mutable JavaBean forms requiring property binding, configure `allowedFields` on the relevant controller/attribute. You can scope `@ControllerAdvice` by package or controller type.

Comparison:

| Implementation | Characteristics | Recommendation |
| --- | --- | --- |
| Mutable entity + direct binding | Broader than contract, risks exposing sensitive setters | Avoid |
| Mutable DTO + `@InitBinder` allowlist | Controls property binding per field | Good when JavaBean/form is needed |
| Record/immutable DTO with contract fields only | Narrow input surface, easy to review | Preferred when suitable |
| Declarative binding + safe DTO | Constructor binding only; setter binding only when allowed | Suitable for Spring 6.1+ |
| Blocklist `disallowedFields` | Easy to miss newly added fields | Do not use as primary control |

## 6. Runnable Spring Boot 3.x Example: Blocking `admin=true` from an HTML Form

This example **intentionally** includes an `admin` property on the form bean to demonstrate the risk and how an allowlist blocks it. In production code, **omit sensitive properties entirely from input DTOs**, as shown in Section 3.

### 6.1. Preparing the Project

Create a Spring Boot 3.x project with Java 17+ and the **Spring Web** dependency on [Spring Initializr](https://start.spring.io/). In `src/main/java/com/example/demo/DemoApplication.java`, place all of the following code (one public class, two package-private classes; no database or Spring Security needed to run the demo):

```java
package com.example.demo;

import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@RestController
class ProfileController {

    @InitBinder("profileForm")
    void initProfileFormBinder(WebDataBinder binder) {
        binder.setAllowedFields("displayName", "bio");
    }

    @PostMapping(
            path = "/profiles/{id}",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<Map<String, Object>> update(
            @PathVariable("id") long id,
            @ModelAttribute("profileForm") ProfileForm form,
            BindingResult bindingResult) {

        // BindingResult must be placed immediately after the corresponding @ModelAttribute.
        String[] suppressed = bindingResult.getSuppressedFields();
        if (suppressed.length > 0) {
            Map<String, Object> rejected = new LinkedHashMap<>();
            rejected.put("error", "Fields not allowed");
            rejected.put("fields", Arrays.asList(suppressed));
            return ResponseEntity.badRequest().body(rejected);
        }

        if (bindingResult.hasErrors()) {
            Map<String, Object> rejected = new LinkedHashMap<>();
            rejected.put("error", "Invalid form input");
            return ResponseEntity.badRequest().body(rejected);
        }

        // Demo echoes the bound object only; no database write.
        Map<String, Object> accepted = new LinkedHashMap<>();
        accepted.put("id", id);
        accepted.put("displayName", form.getDisplayName());
        accepted.put("bio", form.getBio());
        accepted.put("admin", form.isAdmin());
        return ResponseEntity.ok(accepted);
    }
}

class ProfileForm {
    private String displayName = "";
    private String bio = "";
    private boolean admin;

    public ProfileForm() {
    }

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

    public boolean isAdmin() {
        return admin;
    }

    public void setAdmin(boolean admin) {
        this.admin = admin;
    }
}
```

**Code analysis:**

1. `@ModelAttribute("profileForm")` instantiates the `ProfileForm` JavaBean using its no-args constructor and performs property binding.
2. `@InitBinder("profileForm")` configures the binder for that exact model attribute. Only `displayName` and `bio` are allowed to be assigned, even though `ProfileForm` has a public `setAdmin(...)`.
3. `getSuppressedFields()` returns property paths excluded by the binder from property binding. The demo chooses to **reject the request with HTTP 400** if disallowed fields are present; this is an application policy decision. **Spring does not automatically turn every suppressed field into HTTP 400 by default.**
4. `bindingResult.hasErrors()` handles regular binding/conversion errors; it is not synonymous with `getSuppressedFields().length > 0`. In this example, valid fields are all of type `String`.
5. The method **persists no data**. The output shows `admin` stays `false`, and the request is accepted only when no out-of-contract fields are sent.

In a real system, after passing checks you must still resolve the current user, load the server record by ID, verify permissions, and update only permitted properties. Never use `form.isAdmin()` to decide privileges or admin state, even though the demo shows it was blocked.

### 6.2. Running and Checking HTTP Output

In the root directory of the Spring Initializr project:

```bash
# macOS / Linux
./mvnw spring-boot:run

# Windows PowerShell or Command Prompt
mvnw.cmd spring-boot:run
```

Valid request:

```bash
curl -sS -X POST 'http://localhost:8080/profiles/42' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'displayName=Lan' \
  --data-urlencode 'bio=Java learner'
```

With default configuration and no response-modifying filters, status is **200 OK**, JSON body:

```json
{"id":42,"displayName":"Lan","bio":"Java learner","admin":false}
```

Attack request (with an out-of-contract field):

```bash
curl -i -X POST 'http://localhost:8080/profiles/42' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'displayName=Lan' \
  --data-urlencode 'bio=Java learner' \
  --data-urlencode 'admin=true'
```

Expected status is **400 Bad Request** because of the suppressed-fields check **we wrote**, body:

```json
{"error":"Fields not allowed","fields":["admin"]}
```

Headers such as `Date` or `Connection` depend on the servlet container. If running in PowerShell, put the cURL command on a single line and use `curl.exe` instead of any existing alias:

```powershell
curl.exe -i -X POST "http://localhost:8080/profiles/42" -H "Content-Type: application/x-www-form-urlencoded" --data-urlencode "displayName=Lan" --data-urlencode "bio=Java learner" --data-urlencode "admin=true"
```

The result shows the server **detected** the forbidden input rather than silently ignoring it. If you remove the suppressed-fields check, `setAllowedFields` itself still prevents `admin` from being assigned; the status may remain 200 depending on handler code.

### 6.3. Why Must `BindingResult` Sit Immediately After the Form?

```java
public ResponseEntity<?> update(
        @ModelAttribute("profileForm") ProfileForm form,
        BindingResult errors,
        @PathVariable long id) { /* ... */ }
```

This is an **illustrative signature**, showing `BindingResult` immediately after the object it tracks. If another parameter is inserted between `@ModelAttribute` and `BindingResult`, Spring cannot associate binding errors with that object per the argument-resolution contract. Independent parameters may be placed before or after this pair.

## 7. Distinguishing Form `@ModelAttribute` from JSON `@RequestBody`

This is a very common security misconception:

| Entry point | Data transformation mechanism | Controlled directly by `@InitBinder#setAllowedFields`? |
| --- | --- | --- |
| Form/query bound to `@ModelAttribute` mutable bean | `WebDataBinder` / property binding | **Yes**, for properties bound via that mechanism |
| `@ModelAttribute` immutable record/constructor | Constructor binding | **Does not** restrict constructor parameters via `allowedFields`; must design safe constructors |
| JSON `@RequestBody` | `HttpMessageConverter`, typically Jackson deserialization | **Does not** use `allowedFields` as an allowlist of JSON keys |
| Updating a fetched JPA entity in a service | Business / persistence code | No; must assign fields intentionally and check permissions |

Dangerous JSON example:

```java
// DO NOT DO THIS: do not deserialize JSON directly into a broad entity.
@PatchMapping("/accounts/{id}")
public void patch(@PathVariable long id,
                  @RequestBody Account entity) {
    accountRepository.save(entity);
}
```

Jackson can populate any recognizable property on `Account` per its configuration. An `@InitBinder#setAllowedFields` meant for `@ModelAttribute` **does not automatically become an allowlist for this JSON deserialization step**.

Fix for JSON endpoints:

```java
// Illustrative snippet: service uses a database entity and checks permissions.
public record EditAccountJson(String displayName, String bio) {
}

@PatchMapping("/accounts/{id}")
public ResponseEntity<Void> patch(
        @PathVariable long id,
        @RequestBody EditAccountJson input,
        Principal currentUser) {

    Account saved = accountRepository.findById(id)
            .orElseThrow(() -> new ResponseStatusException(
                    HttpStatus.NOT_FOUND));

    authorizationService.requireCanEdit(currentUser, saved);
    saved.setDisplayName(input.displayName());
    saved.setBio(input.bio());
    accountRepository.save(saved);
    return ResponseEntity.noContent().build();
}
```

This code assumes `Account`, a repository, and a corresponding security service exist; it **cannot run standalone** without those components. The advantage is that the JSON DTO contains only two fields, and the service updates exactly two properties. If you need to **reject** any unknown JSON keys (such as `admin`), configure Jackson's unknown-properties policy appropriately for your DTOs and write dedicated tests; some default setups silently ignore unknown keys. Ignoring unknown keys and returning 2xx is **different** from actively rejecting the request.

With JSON APIs, `@JsonIgnore`, `@JsonProperty(access = READ_ONLY)`, or Jackson views can serve as supplementary layers in some scenarios, but should not replace dedicated request DTO design and authorization checks. Privileged fields should not appear in request DTOs only to require remembering to block them.

## 8. Preventing Binding into an Existing Entity: `@ModelAttribute(binding = false)`

Another pattern lets Spring provide an object already in the model while **not applying request parameters onto it**:

```java
// Illustrative code; requires application-defined repository and service.
@ModelAttribute("account")
public Account loadAccount(@PathVariable long id) {
    return accountRepository.findById(id)
            .orElseThrow(() -> new ResponseStatusException(
                    HttpStatus.NOT_FOUND));
}

@PostMapping("/accounts/{id}/edit")
public String update(
        @ModelAttribute("editForm") EditProfileRequest form,
        @ModelAttribute(value = "account", binding = false)
        Account account,
        Principal principal) {

    authorizationService.requireCanEdit(principal, account);
    account.setDisplayName(form.displayName());
    account.setBio(form.bio());
    accountRepository.save(account);
    return "saved";
}
```

`binding = false` tells Spring not to use request values to data-bind the **`account` model attribute in this method argument**. The controller must still check permissions and copy contracted fields from `editForm`. Note that another attribute or code outside the controller could still affect an entity; this is a handler-argument boundary safeguard, not an absolute object lock.

When a method has multiple `@ModelAttribute` parameters, explicit naming separates the input form binder from the domain entity binder. `@InitBinder("editForm")` should be scoped specifically to the input if you want a separate allowlist.

## 9. When to Configure per Controller vs. Globally?

### 9.1. Controller and Attribute Scope

```java
@Controller
class SettingsController {
    @InitBinder("settingsForm")
    void allowSettings(WebDataBinder binder) {
        binder.setAllowedFields("theme", "notificationsEnabled");
    }
}
```

Applies to `settingsForm` within the controller. Different forms with different contract properties should generally have distinct allowlists. Do not configure one shared field list for all domain objects merely because they pass through MVC.

### 9.2. `@ControllerAdvice`

```java
@ControllerAdvice(basePackages = "com.example.web")
class WebBindingPolicy {
    @InitBinder
    void configure(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
    }
}
```

This is a policy option for a defined package scope, well-suited when the application designs DTOs around constructor binding or declares explicit allowlists wherever property binding is needed. **Test existing forms** before enabling this across all controllers: forms that previously appeared to bind properly may stop receiving setter values when declarative binding is enabled without `allowedFields`.

If multiple `@InitBinder` methods target the same attribute, inspect the effective binder configuration and prevent binders from overwriting allowlists through unclear ordering or policies. Explicit form naming and clear scope boundaries simplify code reviews.

## 10. An Allowlist Is One Layer; Business Rules Remain Essential

Values that must not be edited typically sit **outside the input contract**, for example:

| Property | Why clients must not bind it arbitrarily | Safe handling |
| --- | --- | --- |
| `id` | Switching to another resource | ID from route, verify permission, load server record |
| `ownerId`, `tenantId` | Hijacking ownership / cross-tenant access | Resolve from authenticated identity and trusted org context |
| `role`, `isAdmin` | Privilege escalation | Dedicated administration, strict authorization |
| `price`, `balance` | Altering financial values | Protected business service, server-side calculation |
| `status`, `approved` | Bypassing approval workflows | Server-controlled state transitions |
| `createdAt`, `createdBy` | Tampering with audit trails | Set by server/persistence |
| `version` | Bypassing optimistic locking or corrupting state | Controlled concurrency handling |

Even fields inside an allowlist can still require business validation. For instance, `displayName` needs valid length, `email` may require verification, and a `published` status may require a specific permission.

In the service layer, proceed in order: identify the current principal → query the entity within permitted scope → verify operation permissions → validate values → assign allowed fields → save within a transaction as needed. Never trust any `ownerId`/`role` sent by the client whether in URL, query, form, or JSON.

## 11. Validation, Suppressed Fields, and Unknown Fields Differ

- `@Valid` / `@Validated`: checks value constraints on an object (such as `@NotBlank`, `@Size`); **not an allowlist**. To use Bean Validation with Spring Boot, add `spring-boot-starter-validation`.
- `BindingResult.hasErrors()`: reflects binding or validation errors that occurred. It should not be treated as a check for every blocked field.
- `BindingResult.getSuppressedFields()`: list of fields/property paths excluded by the binder because they are not allowed to bind. You can choose a policy to log safely, return 400, or simply ignore them depending on your API contract.
- `Unknown field`: a parameter name with no matching property, which the binder may ignore depending on configuration. Do not assume every unknown parameter appears in `getSuppressedFields()` or always triggers an error.
- `setIgnoreUnknownFields(false)` only adjusts how the binder handles non-existent properties during applicable operations; it is not a list of sensitive fields or an allowlist replacement.

If a **strict** contract (rejecting all extra parameters) is needed, beyond an allowlist you may need to compare permitted request keys against actual request keys, accounting for nested paths, multi-value params, and framework fields (such as CSRF tokens). Do not build naive string checks and assume the entire binding path is protected; write HTTP tests for valid, disallowed, and anomalous inputs.

## 12. Code Review Checklist and Valuable Tests

When reviewing an update endpoint using `@ModelAttribute` or `@RequestBody`, answer:

1. Is the input object a **request DTO** or an entity/domain object?
2. Which fields belong to the update contract? Are `role`, `admin`, `ownerId`, `status`, or JPA relationships accidentally editable?
3. For mutable `@ModelAttribute`, is `setAllowedFields` exact? Does `@InitBinder("...")` match the attribute name?
4. Is constructor binding used? Does the constructor inadvertently declare sensitive fields? Is `setDeclarativeBinding(true)` needed?
5. If using JSON `@RequestBody`, are there a dedicated DTO and an appropriate unknown-JSON-keys policy?
6. When the binder suppresses fields, does the handler inspect `getSuppressedFields()` and apply an explicit policy?
7. Does authorization verify **user + target resource + action** before modifying and saving?
8. Are nested properties/collections/indexed paths, empty values, invalid types, and extra fields tested?

Test suites should include both normal and attack requests:

| Input | Expectation |
| --- | --- |
| `displayName=Lan&bio=Java+learner` | Accepted, updates only those two properties |
| `displayName=Lan&admin=true` | Rejected or `admin` unchanged, per policy |
| `ownerId=7` | Does not transfer ownership |
| `role=ADMIN` | Does not change role |
| `addresses[0].isPrimary=true` outside allowlist | Does not bind out-of-contract nested property |
| JSON `{"displayName":"Lan","admin":true}` | JSON DTO disallows setting admin; extra key handled per policy |
| User A modifies User B's `/profiles/{id}` | Rejected at authorization layer, even if body has only allowed fields |

In a real application, use `MockMvc` or HTTP integration tests to verify status, response, and **database state after the request**. Checking only the JSON output without inspecting the persisted record can miss mass assignment inside the service.

## 13. Common Pitfalls

| Mistake | Consequence | Prevention |
| --- | --- | --- |
| Binding directly into a broad JPA entity | Client can assign sensitive properties | Dedicated DTO and explicit updates |
| Only hiding fields in HTML | Client can still submit those fields | Server-side allowlist |
| Only adding `@Valid` | Disallowed values can still pass constraint checks | Validation **plus** binding restrictions |
| Using `setDisallowedFields` as primary defense | Misses newly added properties | `setAllowedFields` or constructor DTO |
| Allowing overly broad wildcards | Accidentally exposes nested properties | List specific fields/paths |
| Assuming `setAllowedFields` protects JSON | Jackson still deserializes objects per its config | JSON request DTO and explicit mapping |
| Forgetting to inspect `getSuppressedFields()` | Client sends banned fields undetected | Define a suppressed-field policy |
| `@InitBinder("name")` differs from `@ModelAttribute("name")` | Allowlist does not apply to target | Match names consistently, write HTTP tests |
| Allowing `id`/`tenantId` binding from body | Cross-record/cross-tenant updates | Resolve resource server-side, check scope |
| Enabling `declarativeBinding` globally without testing | Existing forms stop property-binding | Audit DTOs/forms and scope config carefully |

## 14. Self-Check

**Question 1.** An HTML form only has two inputs: `displayName` and `bio`. Do you still need protection against `admin=true`?

**Answer:** Yes. Clients are not forced to use your application's HTML form; they can submit any arbitrary HTTP parameters.

**Question 2.** Does `binder.setAllowedFields("displayName", "bio")` automatically return 400 if `admin=true` is sent?

**Answer:** Not by default. It prevents property binding outside the allowlist. The application can inspect `BindingResult#getSuppressedFields()` and explicitly choose to reject, as shown in Section 6.

**Question 3.** Can `@InitBinder` alone stop a JSON body from assigning `role` onto a `@RequestBody` entity?

**Answer:** No. `@RequestBody` uses `HttpMessageConverter` (typically Jackson) to deserialize; accept JSON using a narrow request DTO and update only permitted fields.

**Question 4.** Does `setDeclarativeBinding(true)` block all constructor inputs?

**Answer:** No. Constructor binding still works. Constructors/records must contain only fields the client is allowed to send.

**Question 5.** If an allowlist already restricts inputs to `displayName` and `bio`, why do you still need to check user permissions against the ID in the URL?

**Answer:** Because an allowlist only governs **which fields** can be bound, not **who** is authorized to modify **which record**.

## 15. Official Documentation

- [Spring Framework — MVC Data Binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html): guidance on model design, allowlists, constructor binding, and declarative binding.
- [Spring Framework — `@InitBinder`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html): binder configuration scope in controllers and `@ControllerAdvice`.
- [Spring Framework — `@ModelAttribute`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): creating model attributes, accepting request values, and the `binding=false` option.
- [Spring Framework — `@RequestBody`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html): converting JSON/bodies via `HttpMessageConverter` and validation.
- [Spring Framework — MVC Method Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html): `BindingResult` placement and controller argument types.

**Practical conclusion:** Define minimal request DTOs per update operation, prefer constructor/immutable DTOs when suitable, restrict property binding via `@InitBinder#setAllowedFields` when using mutable forms, and inspect `getSuppressedFields()` if policy demands rejecting extra fields. For JSON `@RequestBody`, apply dedicated deserialization policies. Every entity change must go through server-controlled authorization checks and property mapping.
