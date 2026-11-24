# Constructor Binding and Limiting the Mutable Surface in Spring Data Binding

## 1. The Security Problem: What Can HTTP Input Modify?

**Data binding** enables Spring to convert request parameters, form fields, and certain HTTP data sources into Java objects. This convenience becomes a risk when the target has properties that **clients must not edit** yet can still be assigned from the request.

Suppose an application has an entity:

~~~java
public class Account {
    private Long id;
    private String displayName;
    private String contactEmail;
    private String role;
    private boolean locked;
    private Long tenantId;

    // getters, setters, and persistence logic ...
}
~~~

This is an **entity illustration snippet**, not a standalone file. The "Edit Profile" UI only displays `displayName` and `contactEmail`. A malicious client can still append extra parameters:

~~~http
POST /accounts/7/profile
Content-Type: application/x-www-form-urlencoded

displayName=Lan&contactEmail=lan@example.com&role=ADMIN&locked=false&tenantId=999
~~~

If the controller binds the request directly into `Account`, which has public setters for `role`, `locked`, and `tenantId`, Spring **can assign even fields the UI does not show**. This is a **mass assignment / overposting / unsafe object binding** risk.

**What needs restricting is not merely whether input is valid in type or format; it is the *mutable surface***: the set of fields, nested properties, collection elements, or constructor arguments that a client is permitted to supply.

The related, non-interchangeable layers of defense are:

1. **Dedicated input DTO/command object**: declares only the values the client is allowed to send.
2. **Constructor binding**: selects only the necessary constructor parameters rather than arbitrarily invoking every setter.
3. **`DataBinder#setDeclarativeBinding(true)`**: puts the binder in declarative mode, allowing only constructor binding and explicitly permitted property binding.
4. **`WebDataBinder#setAllowedFields(...)`**: restricts property/setter binding when a mutable bean is still needed.
5. **Validation** (`@Valid`, `@NotBlank`, `@Email`, ...): checks whether data is valid; it **does not** decide who is authorized to edit an attribute.
6. **Authorization and selective updates in the service/domain layer**: ensures the user has permission to edit the target resource and writes only permitted fields.

**Key takeaway:** constructor binding shrinks the mutable surface **when the constructor/DTO is designed properly**. It does not automatically make every constructor argument "authorized." If you put `role` or `tenantId` into a constructor receiving HTTP input, clients can still supply them.

## 2. How Does Spring Distinguish Constructor Binding from Property Binding?

Spring `DataBinder`/`WebDataBinder` provides two distinct binding paths:

| Characteristic | Constructor binding | Property/setter binding |
| --- | --- | --- |
| Target | Parameters of a data/primary constructor | JavaBean properties, setters, or direct field access if configured |
| Data lookup | By constructor argument name (customizable via `@BindParam`) | By property path name from the request |
| Surface considered | Parameters appearing in the chosen constructor, including applicable nested constructor binding | Writable properties in the target/object graph |
| With Java records | Well suited: the record canonical constructor clearly declares the input schema | Records lack component setters; still, do not generalize to nested mutable objects |
| With JavaBean having a no-arg constructor | Constructor supplies no field values; usually relies on setter binding | Uses setters to populate fields |
| Controls | Constructor design + DTO exposing only public parameters | `setAllowedFields`, dedicated DTO, field access policy |
| Extra input | Constructor binding consumes only values needed for the constructor; extra inputs may be ignored | By default can bind any matching writable property |
| Security caveat | A constructor containing sensitive fields still accepts sensitive values | Public setters/nested paths can widen modification rights |

Per Spring Framework 6.1/6.2 documentation, **both constructor binding and property binding can apply by default**. Therefore, do not assume "Spring found a primary constructor" means "all subsequent setter binding is definitely disabled." For objects with setters, binder configuration remains critical.

### High-level flow when receiving `@ModelAttribute`

~~~text
Request: displayName=Lan, contactEmail=lan@example.com,
         role=ADMIN, locked=false
        |
        v
Spring @ModelAttribute argument resolver
        |
        +--> Create or retrieve target object
        |      |
        |      +--> Constructor binding:
        |             only the required constructor parameters
        |
        +--> Property binding:
        |      may still apply if the binder permits
        |
        +--> @Valid / @Validated (if declared)
        |
        +--> BindingResult
        |
        v
Controller receives bound command object
        |
        v
Service checks permissions, updates only allowed fields
~~~

In a Servlet Spring MVC application, `@ModelAttribute` can read request parameters including query/form data, and can supplement them with URI path variables or headers according to Spring's precedence rules. All of these sources **are untrusted input** and do not become trustworthy merely by appearing in a path or header.

## 3. Constructor Binding with Java Records: Declaring an Explicit Input Contract

Instead of binding `Account` directly, use a record accepting only the two permitted fields:

~~~java
public record AccountChangeForm(
        @NotBlank String displayName,
        @NotBlank @Email String contactEmail) {
}
~~~

When a handler declares:

~~~java
@PostMapping("/accounts/{id}/profile")
ResponseEntity<?> change(
        @PathVariable long id,
        @Valid @ModelAttribute("changeForm")
                AccountChangeForm form,
        BindingResult errors) {
    // ...
}
~~~

Spring MVC can construct `AccountChangeForm` via its constructor using the input names `displayName` and `contactEmail`, then validate the record.

Form:

~~~text
displayName=Lan
contactEmail=lan@example.com
role=ADMIN
locked=false
tenantId=999
~~~

**There are no constructor parameters** for `role`, `locked`, or `tenantId`, so constructor binding for `AccountChangeForm` **does not pick them up**. Still, **do not rely solely on record immutability to declare the whole application safe from mass assignment**:

- Ensure the target is genuinely an **input DTO**, not an entity whose data constructor includes server-owned fields.
- Enable **`declarativeBinding`** on the binder when you want to guarantee no unintended property binding occurs.
- Never embed a mutable entity, an open `Map<String,Object>`, or an overly broad object graph inside a record constructor and consider it "locked down."
- Check separate policies for **JSON `@RequestBody`**, as that uses Jackson decoding rather than the `WebDataBinder` path.
- In the service layer, still verify permissions against the account ID and current user; a small DTO **does not replace authorization**.

### Which constructor is selected

Spring can instantiate an object using a default constructor or a "primary/data constructor." According to the DataBinder documentation, constructor binding relies on **constructor parameter names** preserved in bytecode, `@ConstructorProperties`, or corresponding resolution mechanisms. Java records have a canonical constructor and explicit component metadata, making them ideal for this example.

If a regular class has multiple overloaded constructors or a default constructor, Spring may prefer the default constructor followed by setter binding. **Do not assume Spring automatically picks the constructor with the most parameters.** Designing a simple command object with one clear data constructor reduces ambiguity.

For regular classes, when reflection-based parameter names are needed, ensure the build preserves parameter names (e.g., compiler `-parameters`) or use Spring-supported annotations. Without parameter name metadata, constructor binding may fail to bind inputs properly.

## 4. `setDeclarativeBinding(true)`: The Key Cutoff

Since **Spring Framework 6.1**, `DataBinder` provides:

~~~java
binder.setDeclarativeBinding(true);
~~~

Exact meaning (per Javadoc):

- Enables **constructor binding**.
- Performs **property binding** only when matching `allowedFields` are configured.
- The default value of this flag is **`false`**, so you cannot assume property binding is disabled by default.

Controller example:

~~~java
@InitBinder("changeForm")
void configureChangeForm(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
~~~

With `@InitBinder("changeForm")`, the configuration applies to the binder of the model attribute named **`changeForm`**. This scopes by model attribute name, not a field-name allowlist.

### Behavior matrix to distinguish

| `declarativeBinding` | `allowedFields` | Property/setter binding behavior | Constructor binding |
| --- | --- | --- | --- |
| `false` (default) | Not configured | Can bind matching writable properties | May run when creating target |
| `false` | `{"nickname","language"}` | Only allowed properties | May run when creating target |
| **`true`** | **No allowlist** | **Property binding does not run** | Still runs when creating target |
| **`true`** | **`{"nickname","language"}`** | **Binds only properties in the allowlist** | Still runs when creating target |

**Pitfall:** A JavaBean with a **no-arg constructor** and only setters will **receive no populated properties** if `setDeclarativeBinding(true)` is set without adding `allowedFields`. Spring does not "magically constructor-bind every setter property." Choose one of these two options deliberately:

1. Migrate input to a record/immutable command object with an appropriate data constructor.
2. Keep a mutable JavaBean, but declare `allowedFields` explicitly.

### Can it be configured globally?

Yes. `@ControllerAdvice` can contain `@InitBinder` to apply a binder policy across multiple controllers, or Spring offers `ConfigurableWebBindingInitializer` for global setup. However, enabling global declarative binding can cause existing JavaBean forms to **suddenly stop receiving setter values**. To apply it system-wide, you need an inventory, migration plan, and regression tests; for a single lesson, a local `@InitBinder("changeForm")` is easier to control.

Do not alter global configuration just to fix one form without assessing impact across all routes.

## 5. `setAllowedFields` for Mutable Forms: Allowlist Beats Denylist

Suppose a form still needs JavaBean setters for UI compatibility:

~~~java
public class PreferencesForm {
    private String nickname;
    private String language;
    private boolean admin;

    // public getters/setters...
}
~~~

When handling requests, the application only allows clients to change `nickname` and `language`. You can configure:

~~~java
@InitBinder("preferencesForm")
void configurePreferences(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
    binder.setAllowedFields("nickname", "language");
}
~~~

Now a client sending `admin=true` cannot setter-bind it through this binder. Importantly:

- `setAllowedFields` controls **property binding**; it does not guarantee constructor arguments are filtered. Never put `admin` into an input-accepting data constructor.
- The allowlist applies to **property paths**, which may include nested/indexed paths. Verify exact paths and patterns, avoiding an overly broad `"*"`.
- `setDisallowedFields("admin")` is a **denylist** that easily misses newly added fields, aliases, or nested paths. Spring recommends an explicit **allowedFields** allowlist instead of relying on a denylist.
- Do not rely on hidden UI fields, disabled HTML controls, or frontend JavaScript filtering. HTTP clients can craft arbitrary requests.

### `BindingResult#getSuppressedFields()`

When property binding runs with `allowedFields`, disallowed fields can appear in:

~~~java
String[] rejectedFields =
        bindingResult.getSuppressedFields();
~~~

Thus, if policy requires **rejecting the entire request when an overposted parameter is present**, the controller can check:

~~~java
if (bindingResult.hasErrors()
        || bindingResult.getSuppressedFields().length > 0) {
    return ResponseEntity.badRequest()
            .body("INVALID_PREFERENCES");
}
~~~

This is a controller snippet. **Do not return names or raw values of suppressed fields** if they are internal details or sensitive data. The full runnable code in section 9 includes this branch.

**Critical limitation:** If `declarativeBinding=true` is set **without configuring `allowedFields`**, Spring can **skip the property-binding step entirely**; therefore, you cannot rely on `getSuppressedFields()` as a universal detector for all extra input in constructor-only mode. **Constructor binding simply ignores unused inputs**, rather than acting as a validator that "forbids every unknown key." If the API must reject unknown inputs, design an explicit input-key check at the appropriate boundary.

### Nested/collection variants

Suppose a form has the structure:

~~~text
address.city=Da Nang
address.postalCode=550000
role.name=ADMIN
items[0].quantity=2
items[1].quantity=3
~~~

If only the address and item quantities should be editable, prefer a dedicated DTO and path-based allowlist:

~~~java
binder.setAllowedFields(
        "address.city",
        "address.postalCode",
        "items*.quantity");
~~~

This is a **policy snippet**, not a guarantee that wildcards behave like regex; exact pattern matching is defined by `DataBinder#setAllowedFields`. Test `items[0].quantity`, `items[1].quantity`, and indexed/mapped path variants, especially when auto-grow is enabled. Never use `"address*"` if the `address` object contains secret or server-only fields.

Bounding collection sizes, nesting depth, and payload size is also essential to prevent DoS. Inspect `setAutoGrowCollectionLimit` and input size limits whenever binding complex structures.

## 6. The "Mutable" Surface Is Not Just Setters

### 6.1. Constructors with sensitive fields remain dangerous

The following code is a **bad design example**:

~~~java
// Do not use this type as a DTO for HTTP input.
public record DangerousAccountCommand(
        String displayName,
        String role,
        boolean locked) {
}
~~~

Even though the record is completely immutable, a request with `role=ADMIN&locked=false` still flows into **constructor parameters**. Post-construction immutability **does not equal a safe input contract**.

The fix:

~~~java
public record ChangePublicProfile(
        @NotBlank String displayName) {
}
~~~

`role` and `locked` come from the **stored account** or server-side security context and do not appear in the input DTO.

### 6.2. Nested mutable objects can widen the surface

A record like:

~~~java
public record BadInput(
        AccountEntity account) {
}
~~~

can still expose a broad object graph if Spring is permitted to perform nested constructor binding or related resolution. Do not "wrap" an entity with sensitive fields inside a record and assume it is safe. Use small nested input DTOs:

~~~java
public record AddressInput(
        String city,
        String postalCode) {
}

public record UpdateProfileInput(
        String displayName,
        AddressInput address) {
}
~~~

With collections/maps, inspect the **element** type as well. A `List<AccountEntity>` can be just as dangerous as a single entity; replace it with `List<AccountReferenceInput>` if only IDs are needed, and authorize each ID individually.

### 6.3. Type conversion is not authorization either

When Spring parses `@PathVariable Long accountId` or a `@ModelAttribute` holding an ID value object, type conversion verifies only **the shape of the ID**. It does not verify that the user may view or edit that account. For instance, `accountId=7` and `accountId=8` are both valid numbers, yet only one belongs to the caller.

Do not do this:

~~~java
// Authorization flaw if trusting client ID alone.
Account account = repository.findById(accountId)
        .orElseThrow();
account.setRole(request.getRole());
repository.save(account);
~~~

This snippet intentionally illustrates an anti-pattern, not standalone runnable code. Check ownership/tenant/permissions in the service and update only approved fields.

## 7. `@BindParam`, Parameter Names, and Model Attribute Binding

Constructor binding retrieves values by parameter name. Spring supports `@BindParam` to map a request parameter name that differs from the Java name:

~~~java
public final class ContactForm {

    private final String contactEmail;

    public ContactForm(
            @BindParam("contact-email")
            String contactEmail) {
        this.contactEmail = contactEmail;
    }

    public String getContactEmail() {
        return contactEmail;
    }
}
~~~

This is a **class snippet** requiring `org.springframework.web.bind.annotation.BindParam`. When a request contains `contact-email=lan@example.com`, the constructor receives the value via the `contactEmail` parameter without needing a Java property containing a hyphen.

**Security warning:** `@BindParam` only **renames the lookup key for a constructor argument**. It does not restrict modification rights or make data from `contact-email` trustworthy. If the constructor declares a `role` parameter, clients can still supply it when resolved.

For regular Java classes, to avoid relying on guessed names, preserve compiler parameter metadata (e.g., `-parameters`) or use `@ConstructorProperties`/`@BindParam` per the Spring API. For records, the canonical constructor exposes component names that the framework can read.

### If the object is already in Model/Session

`@ModelAttribute` can retrieve an existing object from the Model, SessionAttributes, or an appropriate converter instead of constructing a fresh instance every time. In that case, **property binding** onto an existing mutable object can become significant.

If an object was loaded from the DB and only needs to be passed to the handler **without allowing the request to bind onto it**, you can use:

~~~java
@ModelAttribute("account")
public Account loadAccount(@PathVariable long id) {
    return accountService.findForAuthorizedUser(id);
}

@PostMapping("/accounts/{id}/action")
public ResponseEntity<?> action(
        @ModelAttribute(binding = false) Account account) {
    // Account loaded from server and not property-bound by the request.
    return ResponseEntity.ok().build();
}
~~~

This is an **architectural snippet** omitting `Account`, service, and controller imports. `binding=false` prevents data binding on that argument; the service must still enforce permissions, and this snippet must not be read as providing automatic authentication/authorization. In real applications, avoid rendering/serializing an entity directly to clients if it holds server-only fields.

## 8. `@ModelAttribute` vs. `@RequestBody`: Same DTO, Different Pipeline

**Spring MVC `@ModelAttribute`:**

- Uses `WebDataBinder`, constructor binding, and potentially property binding.
- Reads form/query request parameters (and optionally path/header values per Spring rules).
- `@InitBinder`, `setDeclarativeBinding`, and `setAllowedFields` apply to this binder.
- `@Valid` can populate `BindingResult` if placed immediately after the parameter.
- Without an adjacent `BindingResult`, an individual argument validation failure typically raises `MethodArgumentNotValidException`.

**Spring MVC `@RequestBody`:**

- JSON is read via `HttpMessageConverter`/Jackson.
- Jackson has its own rules for choosing constructors/creators and handling unknown JSON properties.
- **`WebDataBinder`'s `setDeclarativeBinding(true)` and `setAllowedFields(...)` are not a JSON property allowlist**.
- Using a dedicated request DTO reduces surface area, yet if you need to **reject extra JSON keys**, you must configure Jackson/deserialization and test the JSON contract.
- `@Valid @RequestBody` still runs Spring Validator/Bean Validation after the object is deserialized.

Example:

~~~java
@PostMapping(path = "/profile-json",
             consumes = MediaType.APPLICATION_JSON_VALUE)
ResponseEntity<?> json(
        @Valid @RequestBody AccountChangeForm form) {
    // Jackson instantiates the record from JSON, without using
    // @ModelAttribute setter-binding to select properties.
    return ResponseEntity.ok().build();
}
~~~

Controller snippet. In a Spring Boot application, the default policy for **unknown JSON properties** can vary by `ObjectMapper`, annotations, and version. **Do not treat Jackson's incidental ignoring of unknown keys as proof that the API enforces a strict input schema.** Test explicitly if you want 400 responses on unknown keys.

### Do not use JPA entities as request DTOs

JPA entities typically have no-arg constructors, setters, and nested relationships for persistence. That structure is ill-suited for a narrow public form surface. Use:

~~~text
HTTP form/JSON
  -> request DTO/record (public fields only)
  -> @Valid + conversion
  -> authentication/authorization
  -> service: load existing entity
  -> update explicit allowed fields
  -> save
  -> dedicated response DTO
~~~

In this update flow, `role`, `tenantId`, `accountId`, and `locked` stay server-managed and are never drawn from the request DTO simply because the client included extra keys.

## 9. Runnable Example: Spring Boot 3.2+, Java 17+, REST Form and JSON

The demo covers **two binding styles**:

1. `AccountChangeForm` is a record whose constructor accepts only two public attributes; the binder enforces **constructor-only** mode.
2. `PreferencesForm` is a JavaBean with setters; the binder allows only two properties via **`allowedFields`** and rejects requests with suppressed fields.

The demo also includes a JSON endpoint to illustrate that Jackson `@RequestBody` **does not use the form binder's property allowlist**.

**Important limitation:** To run without a database, `AccountService` creates an existing demo snapshot and returns a new snapshot; **it does not persist data or authenticate users**. In production, replace it with a real repository/service with authentication, authorization, tenant isolation, and optimistic locking/transactions where appropriate. The demo proves **binding surface behavior**, not full application security.

### 9.1. Maven dependencies

Create a Spring Boot **3.2+** (Spring Framework **6.1+**), Java 17+, Maven project. Use the standard Spring Boot parent/BOM and these dependencies:

~~~xml
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
~~~

The project needs the usual Spring Boot Maven parent/plugin setup. The security starter is omitted from the demo so tests measure binding behavior directly; when enabling security in production, configure authentication and CSRF policies separately.

Java files live under `src/main/java/com/example/safebinding/`; test files live under `src/test/java/com/example/safebinding/`.

### 9.2. `SafeBindingApplication.java`

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

### 9.3. `AccountChangeForm.java`: immutable input record

~~~java
package com.example.safebinding;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

public record AccountChangeForm(
        @NotBlank String displayName,
        @NotBlank @Email String contactEmail) {
}
~~~

**Only two constructor parameters.** Neither `role`, `locked`, `tenantId`, nor `id` exists on the DTO. `@NotBlank`/`@Email` are validation constraints; they **do not grant authorization**. Only if the form is valid does the service decide which account may be modified.

### 9.4. `PreferencesForm.java`: mutable JavaBean with a non-editable field

~~~java
package com.example.safebinding;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

public class PreferencesForm {

    @NotBlank
    private String nickname;

    @NotBlank
    @Pattern(regexp = "vi|en")
    private String language;

    private boolean admin;

    public PreferencesForm() {
    }

    public String getNickname() {
        return nickname;
    }

    public void setNickname(String nickname) {
        this.nickname = nickname;
    }

    public String getLanguage() {
        return language;
    }

    public void setLanguage(String language) {
        this.language = language;
    }

    public boolean isAdmin() {
        return admin;
    }

    public void setAdmin(boolean admin) {
        this.admin = admin;
    }
}
~~~

`admin` intentionally has a setter to simulate a legacy DTO with extra writable fields; the endpoint may only receive `nickname` and `language`. **Do not treat this class as an ideal production model**: remove `admin` from request DTOs entirely whenever possible. We keep it in the demo to **verify that `setAllowedFields` actually blocks field overposting**.

### 9.5. `AccountSnapshot.java`: server-managed object

~~~java
package com.example.safebinding;

public record AccountSnapshot(
        long id,
        String displayName,
        String contactEmail,
        String role,
        boolean locked) {
}
~~~

This type **must never be used as `@ModelAttribute` or `@RequestBody`**. It simply represents a snapshot containing server-controlled fields. The demo returns `role`/`locked` so tests are easy to inspect. In production APIs, do not return sensitive/unnecessary fields just to prove they were not modified.

### 9.6. `AccountService.java`: selective update after binding

~~~java
package com.example.safebinding;

import org.springframework.stereotype.Service;

@Service
public class AccountService {

    public AccountSnapshot updatePublicProfile(
            long accountId, AccountChangeForm input) {

        // DEMO: simulates an account loaded from the server.
        // Production: authenticate, authorize, load + persist.
        AccountSnapshot existing = new AccountSnapshot(
                accountId,
                "Existing",
                "existing@example.com",
                "MEMBER",
                true);

        // Modify only the two fields in the input contract.
        return new AccountSnapshot(
                existing.id(),
                input.displayName(),
                input.contactEmail(),
                existing.role(),
                existing.locked());
    }
}
~~~

The code preserves **`id`, `role`, and `locked`** from the server-side snapshot rather than reading them from the form. In a real application, verify that the current user has permission to edit that specific account ID and tenant before updating. Having `role` or `accountId` in the API does not make them authentication proof.

### 9.7. `AccountController.java`: two binder policies in one controller

~~~java
package com.example.safebinding;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api")
public class AccountController {

    private final AccountService accountService;

    public AccountController(AccountService accountService) {
        this.accountService = accountService;
    }

    @InitBinder("changeForm")
    public void bindImmutableProfile(WebDataBinder binder) {
        // Constructor-only binding for AccountChangeForm.
        binder.setDeclarativeBinding(true);
    }

    @InitBinder("preferencesForm")
    public void bindMutablePreferences(WebDataBinder binder) {
        // Allow setter binding for these two properties, not admin.
        binder.setDeclarativeBinding(true);
        binder.setAllowedFields("nickname", "language");
    }

    @PostMapping(
            path = "/accounts/{id}/profile",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> updateProfileForm(
            @PathVariable("id") long id,
            @Valid @ModelAttribute("changeForm")
                    AccountChangeForm change,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest()
                    .body(Map.of("code", "INVALID_PROFILE"));
        }

        // Demo only; authorization must live in a real service.
        return ResponseEntity.ok(
                accountService.updatePublicProfile(id, change));
    }

    @PostMapping(
            path = "/preferences",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> updatePreferences(
            @Valid @ModelAttribute("preferencesForm")
                    PreferencesForm form,
            BindingResult errors) {

        if (errors.hasErrors()
                || errors.getSuppressedFields().length > 0) {
            return ResponseEntity.badRequest()
                    .body(Map.of("code", "INVALID_PREFERENCES"));
        }

        return ResponseEntity.ok(Map.of(
                "nickname", form.getNickname(),
                "language", form.getLanguage(),
                "admin", form.isAdmin()));
    }

    @PostMapping(
            path = "/accounts/{id}/profile-json",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<?> updateProfileJson(
            @PathVariable("id") long id,
            @Valid @RequestBody AccountChangeForm change) {

        // Jackson deserializes @RequestBody.
        // @InitBinder allowedFields is not its JSON input allowlist.
        return ResponseEntity.ok(
                accountService.updatePublicProfile(id, change));
    }
}
~~~

**Examine the key differences in the code:**

- `@InitBinder("changeForm")` is paired with `@ModelAttribute("changeForm")`. Setting the flag to `true` allows **constructor binding** while preventing arbitrary property binding.
- `AccountChangeForm` has **two** components; inputs `role=ADMIN` or `locked=false` do not map onto any field in the record, so they never reach the service update.
- `@InitBinder("preferencesForm")` is paired with `@ModelAttribute("preferencesForm")`. With `setAllowedFields("nickname","language")`, property binding applies only to those two fields.
- `BindingResult` placed **immediately after the `@ModelAttribute` parameter** lets the controller handle validation/binding errors.
- On `/preferences`, `getSuppressedFields()` is checked to **return 400** when a setter property is overposted. Rejected values are not echoed in the JSON.
- `/profile-json` uses `@RequestBody` and Jackson; despite sharing the DTO, the `@ModelAttribute` `WebDataBinder` policy **is not** the JSON deserializer policy.
- Even though forms are bound safely, authorization is absent from the demo; do not expose these endpoints to real users without adding permission checks.

## 10. Integration Testing with MockMvc: "Not Bound" Differs from "Invalid"

Create `src/test/java/com/example/safebinding/SafeBindingApplicationTest.java`:

~~~java
package com.example.safebinding;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class SafeBindingApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void recordConstructorBindsOnlyPublicFields() throws Exception {
        mvc.perform(post("/api/accounts/7/profile")
                    .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                    .param("displayName", "Lan")
                    .param("contactEmail", "lan@example.com"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(7))
                .andExpect(jsonPath("$.displayName").value("Lan"))
                .andExpect(jsonPath("$.contactEmail")
                        .value("lan@example.com"))
                .andExpect(jsonPath("$.role").value("MEMBER"))
                .andExpect(jsonPath("$.locked").value(true));
    }

    @Test
    void overpostedRoleAndLockedCannotChangeServerState()
            throws Exception {
        mvc.perform(post("/api/accounts/7/profile")
                    .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                    .param("displayName", "Lan")
                    .param("contactEmail", "lan@example.com")
                    .param("role", "ADMIN")
                    .param("locked", "false")
                    .param("tenantId", "999"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.role").value("MEMBER"))
                .andExpect(jsonPath("$.locked").value(true))
                .andExpect(jsonPath("$.id").value(7));
    }

    @Test
    void recordConstructorDoesNotAcceptIdOverpost()
            throws Exception {
        mvc.perform(post("/api/accounts/7/profile")
                    .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                    .param("displayName", "Lan")
                    .param("contactEmail", "lan@example.com")
                    .param("id", "999"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(7));
    }

    @Test
    void invalidDisplayNameFailsBeanValidation()
            throws Exception {
        mvc.perform(post("/api/accounts/7/profile")
                    .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                    .param("displayName", "")
                    .param("contactEmail", "lan@example.com"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_PROFILE"));
    }

    @Test
    void malformedEmailFailsBeanValidation()
            throws Exception {
        mvc.perform(post("/api/accounts/7/profile")
                    .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                    .param("displayName", "Lan")
                    .param("contactEmail", "not-an-email"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_PROFILE"));
    }

    @Test
    void missingConstructorArgumentFailsValidation()
            throws Exception {
        mvc.perform(post("/api/accounts/7/profile")
                    .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                    .param("displayName", "Lan"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_PROFILE"));
    }

    @Test
    void allowedMutableFieldsAreBound() throws Exception {
        mvc.perform(post("/api/preferences")
                    .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                    .param("nickname", "Mai")
                    .param("language", "vi"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.nickname").value("Mai"))
                .andExpect(jsonPath("$.language").value("vi"))
                .andExpect(jsonPath("$.admin").value(false));
    }

    @Test
    void disallowedAdminSetterIsSuppressedAndRejected()
            throws Exception {
        mvc.perform(post("/api/preferences")
                    .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                    .param("nickname", "Mai")
                    .param("language", "vi")
                    .param("admin", "true"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_PREFERENCES"));
    }

    @Test
    void invalidLanguageFailsValidation() throws Exception {
        mvc.perform(post("/api/preferences")
                    .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                    .param("nickname", "Mai")
                    .param("language", "xx"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_PREFERENCES"));
    }

    @Test
    void missingMutableFieldFailsValidation() throws Exception {
        mvc.perform(post("/api/preferences")
                    .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                    .param("language", "vi"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_PREFERENCES"));
    }

    @Test
    void validJsonRecordUsesJackson() throws Exception {
        mvc.perform(post("/api/accounts/7/profile-json")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "displayName":"Lan",
                              "contactEmail":"lan@example.com"
                            }
                            """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.role").value("MEMBER"))
                .andExpect(jsonPath("$.displayName").value("Lan"));
    }

    @Test
    void invalidJsonRecordUsesBodyValidation() throws Exception {
        mvc.perform(post("/api/accounts/7/profile-json")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "displayName":"",
                              "contactEmail":"not-an-email"
                            }
                            """))
                .andExpect(status().isBadRequest());
    }

    @Test
    void mismatchedContentTypeIsUnsupported()
            throws Exception {
        mvc.perform(post("/api/accounts/7/profile")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"displayName":"Lan"}
                            """))
                .andExpect(status().isUnsupportedMediaType());
    }
}
~~~

**13 integration tests** are included in the demo. With Spring Boot 3.2+ MVC/Validation/Test:

- The overposting test **does not expect** the constructor-only endpoint to return 400 for every extra key. It verifies that **server-owned fields remain unchanged** when requests send `role=ADMIN`/`locked=false`.
- The `/preferences` test conversely returns **400** when a suppressed property is sent. That is the controller's explicit policy, not a rule that constructor binding behaves the same way.
- `@Valid` tests confirm input DTOs are validated after binding.
- JSON tests show Jackson reads the record via its own constructor; the form binder allowlist is not a JSON input allowlist.
- The HTTP 415 test simply verifies the `consumes` contract.

Run:

~~~bash
./mvnw test -Dtest=SafeBindingApplicationTest
~~~

With the Maven wrapper on Windows:

~~~powershell
mvnw.cmd test -Dtest=SafeBindingApplicationTest
~~~

If Maven is installed globally, use `mvn test -Dtest=SafeBindingApplicationTest`. These tests require no database or remote APIs. **Do not treat passing tests as proof of authorization**: the simulated service intentionally omits security checks.

### Typical results

| Request | HTTP | What to verify |
| --- | --- | --- |
| Valid form `displayName=Lan&contactEmail=lan@example.com` | 200 | DTO receives the two public fields. |
| Form adding `role=ADMIN&locked=false&tenantId=999` | 200 | `role=MEMBER`, `locked=true`, `id` still comes from path. |
| Form adding `id=999`, URL `/accounts/7` | 200 | Snapshot still has `id=7`. |
| `displayName=""` or invalid email | 400 | `@Valid` catches invalid input. |
| Valid preferences | 200 | Only nickname/language are bound; `admin` stays false. |
| Preferences adding `admin=true` | 400 | Property outside allowlist is suppressed. |
| Preferences `language=xx` | 400 | `@Pattern` fails. |
| Valid JSON record | 200 | Jackson deserializes and validation succeeds. |
| JSON record failing constraints | 400 | Bean Validation on `@RequestBody`. |
| JSON sent to form-only mapping | 415 | Unsupported media type. |

With real data, never return `role`, `locked`, or `tenantId` if the public API has no need for them; the demo includes them solely to **clearly illustrate the immutability of server-owned state**.

## 11. Unit Testing `DataBinder#setDeclarativeBinding` Directly

To observe the effect of the `declarativeBinding` flag **without going through HTTP**, use `DataBinder` on a mutable JavaBean.

Create `src/test/java/com/example/safebinding/DataBinderPolicyTest.java`:

~~~java
package com.example.safebinding;

import org.junit.jupiter.api.Test;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.DataBinder;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class DataBinderPolicyTest {

    @Test
    void declarativeModeWithoutAllowedFieldsSkipsSetters() {
        PreferencesForm form = new PreferencesForm();
        DataBinder binder = new DataBinder(form, "preferencesForm");

        binder.setDeclarativeBinding(true);
        binder.bind(new MutablePropertyValues(Map.of(
                "nickname", "Lan",
                "admin", "true")));

        // No constructor arguments on this mutable bean;
        // declarative mode does not setter-bind these inputs.
        assertNull(form.getNickname());
        assertFalse(form.isAdmin());
    }

    @Test
    void allowedFieldsEnableOnlySelectedSetterBinding() {
        PreferencesForm form = new PreferencesForm();
        DataBinder binder = new DataBinder(form, "preferencesForm");

        binder.setDeclarativeBinding(true);
        binder.setAllowedFields("nickname");

        binder.bind(new MutablePropertyValues(Map.of(
                "nickname", "Lan",
                "admin", "true")));

        assertEquals("Lan", form.getNickname());
        assertFalse(form.isAdmin());
        assertArrayEquals(new String[] {"admin"},
                binder.getBindingResult().getSuppressedFields());
    }

    @Test
    void unconstrainedPropertyBindingCanSetSensitiveSetter() {
        PreferencesForm form = new PreferencesForm();
        DataBinder binder = new DataBinder(form, "preferencesForm");

        // Anti-pattern: default mode without allowedFields.
        binder.bind(new MutablePropertyValues(Map.of(
                "nickname", "Lan",
                "admin", "true")));

        // Demonstrates WHY a binder policy matters.
        assertEquals("Lan", form.getNickname());
        assertTrue(form.isAdmin());
    }
}
~~~

These are **three tests illustrating binder behavior**, not a recommendation to run an allowlist-free binder in production. The third test intentionally performs an unsafe binding to **demonstrate the default setter surface**; asserting `admin==true` is expected in an anti-pattern test.

Run only the unit tests:

~~~bash
./mvnw test -Dtest=DataBinderPolicyTest
~~~

Or run all **16 tests** (13 MVC + 3 binder):

~~~bash
./mvnw test -Dtest=SafeBindingApplicationTest,DataBinderPolicyTest
~~~

Calling `DataBinder.bind(...)` alone does not prove Bean Validation `@NotBlank` ran: to check constraints in a unit test, register a validator and call `validate()`, or use `@Valid` on an MVC handler as in section 10.

## 12. Special Case: Constructor-Only Mode Can Ignore Extra Input

In some systems, policy requires **strictly forbidding unknown parameters**, not merely preventing them from changing state. Distinguish:

- **No surface to bind onto**: the record constructor holds only two fields, and all other fields go unused.
- **Detecting extra keys**: a request parser, argument resolver, or validation policy inspects all keys against an allowlist.
- **Rejecting with HTTP 400**: the controller/advice returns an error when an out-of-schema key appears.

`setDeclarativeBinding(true)` restricts property binding; it **is not a schema validator for input keys**. Do not write a test asserting "unknown keys always return 400" if the code only uses constructor-only binding without a dedicated policy.

When a strict form input contract is required, you can:

1. Define an allowlist of input keys per route, accounting for field markers, indexed paths, and framework parameters.
2. Use an appropriate filter, interceptor, or service parser to compare request parameter names and return 400 if unexpected keys appear.
3. Still keep dedicated input DTOs and declarative binding to protect state even if the filter is misconfigured.
4. Test mixed query/form parameters, duplicate keys, casing, percent-encoding, nested paths, and multipart requests.

For JSON, strict unknown-fields handling is usually configured **on Jackson/ObjectMapper** (or specific annotations), not via `WebDataBinder#setAllowedFields`. Evaluate backwards compatibility before enabling reject-unknown API-wide.

### Constructors can accept collection/nested arguments

Spring constructor binding supports lists, maps, arrays, and indexed keys in applicable cases. Example input names:

~~~text
items[0].sku=P01
items[0].quantity=2
items[1].sku=P02
items[1].quantity=3
~~~

Do not assume that because the top-level DTO is a record, no child object graph can be constructed. If the command constructor declares `List<ItemInput>`, the framework can instantiate multiple `ItemInput` instances from indexed request values.

Review the permitted surface for **every nested DTO/constructor component**, not only the top-level class. Cap collection growth, nesting depth, and request size; never permit a nested entity with `role`/`tenantId` just because it sits inside a list.

## 13. Distinguishing Binding Defenses from Other Layers

### 13.1. Validation does not eliminate mass assignment

~~~java
public record UnsafeUpdate(
        @NotBlank String displayName,
        @NotBlank String role) {
}
~~~

If `role` `"ADMIN"` is a non-blank string, `@NotBlank` **passes**. Yet it remains a value the client **is not authorized to set**. You cannot use `@Valid` to replace field-level authorization policy.

### 13.2. Authorization does not replace a narrow schema

Even when a client is authenticated, the user may only be allowed to change their email, not their role or tenant. "Authenticated" ≠ "authorized to edit every field." The service must verify action/resource/tenant and update **only approved fields**.

### 13.3. Concurrency, idempotency, and transactions

A request binding a valid DTO can still overwrite updates from a concurrent request. Where lost updates must be prevented, consider optimistic locking (`@Version`) or a service concurrency policy. No constructor-binding mechanism resolves race conditions on its own.

For patch/partial updates, distinguish:

- field **omitted**;
- field **sent as null/blank**;
- field intending to **clear a value**.

A record with simple nullable components may be unable to distinguish all three states. Use a dedicated patch DTO with presence tracking, JSON Patch/Merge Patch, and explicit rules. Do not assume constructor binding solves PATCH semantics automatically.

### 13.4. Avoid binding JPA-managed entities

An entity may already reside in a persistence context. Property binding directly onto it can cause client changes to be dirty-checked and flushed even when the controller never explicitly calls a setter. This is a serious risk due to the implicit mutation surface. Use an input DTO, load the entity in the service under proper authorization, and assign **only permitted fields**.

### 13.5. Do not rely on field visibility or HTML disabled attributes

An HTML `disabled` field or hidden input can still be altered or manually submitted by clients. Even a `private` Java field can have a public setter that Spring `BeanWrapper` can invoke. Protection must live in the **server input contract and service**, not in frontend widgets.

## 14. Securing Messages, Logs, and Error Handling

If a client attempts to send `role=ADMIN` or unknown fields, avoid dumping the full form or query map into logs:

~~~java
// Do not use in production:
logger.warn("Rejected input = {}", request.getParameterMap());
logger.warn("Validation result = {}", bindingResult);
~~~

Safer log message:

~~~java
logger.warn("Rejected profile update: route={}, code={}",
        "/api/accounts/{id}/profile",
        "INVALID_INPUT");
~~~

This snippet assumes a `logger`. Never write passwords, tokens, emails, or rejected values into default telemetry. When recording audit events for overposting attempts, classify by error code and safe metadata while following retention and access policies.

With `BindingResult`, you can inspect conversion/validation errors, yet never serialize raw `FieldError` objects directly because `getRejectedValue()` may contain sensitive data. Public responses should return generic codes or allowlisted field names.

### Distinguishing HTTP status codes

| Cause | Typical appropriate HTTP status |
| --- | --- |
| Missing `displayName`, `@NotBlank` fails | 400 |
| Invalid email/locale format | 400 |
| Setter overposting under a reject policy | 400 |
| Client lacks permission to edit account | 403 (or appropriate policy to avoid leaking resource existence) |
| Account ID does not exist | 404 |
| Concurrent update conflict | 409 |
| DB/implementation error | 5xx |

Do not collapse every failure into 400. In particular, authorization failures must be evaluated independently of form binding.

## 15. Spring WebFlux and Java Records

Spring WebFlux also provides `@ModelAttribute` and `WebDataBinder`, supporting constructor binding and property-binding restrictions. The principles of **dedicated DTOs, declarative binding, allowedFields, and authorization** still apply, though HTTP input sources and the exception pipeline **differ from Servlet MVC**:

- WebFlux `@RequestParam` **reads query parameters only**; form data can bind via `@ModelAttribute` or be read with `ServerWebExchange#getFormData()`.
- WebFlux validation uses `WebExchangeBindException` and potentially `HandlerMethodValidationException` depending on method signature and version.
- JSON `@RequestBody Mono<Dto>` uses reactive codecs/`HttpMessageReader` rather than `@ModelAttribute` setter binding.
- Converters/validators in WebFlux should be fast and avoid blocking JDBC/HTTP calls on the event loop.

The full runnable example in section 9 uses **Servlet MVC + MockMvc**, so do not treat those tests as proof that WebFlux form binding has identical semantics. For WebFlux, write corresponding `WebTestClient` integration tests and verify the binder policy per endpoint.

## 16. Common Pitfalls and Fixes

| Anti-pattern | Risk | Fix |
| --- | --- | --- |
| `@ModelAttribute AccountEntity account` on a name-edit form | Clients can submit `role`/`locked`/`tenantId`. | Dedicated request DTO, selective update in service. |
| Record constructor includes `role` or `tenantId` | Clients can still bind those constructor arguments. | Include only public mutable fields in the constructor. |
| Assuming a primary constructor disables setters | By default Spring can apply **both constructor and property binding**. | `setDeclarativeBinding(true)` and/or `setAllowedFields`. |
| Enabling declarative mode on a no-arg bean without an allowlist | Setter fields stop binding even on valid UI requests. | Switch to a data constructor or configure `allowedFields`. |
| Using denylist `setDisallowedFields("role")` | Newly added entity fields are missed by the denylist. | Explicit allowlist; prefer small DTOs. |
| Using `setAllowedFields` to "lock down" constructor arguments | Allowed fields apply to property binding, not constructor inputs. | Design the constructor/DTO to match the contract. |
| Using `getSuppressedFields()` as a universal unknown-key detector | Constructor-only mode does not guarantee reporting all unknown keys as suppressed. | Dedicated strict request-keys validator if needed. |
| Thinking `@Valid` stops users from changing their own role | Validation checks format/invariants, not permissions. | Enforce authorization in service; omit `role` from DTO. |
| Treating a path ID as trustworthy | Path variables are still client-supplied. | Verify ownership/tenant and resource access. |
| Relying on binder allowlist to protect Jackson `@RequestBody` | JSON uses a deserializer, bypassing the property binder. | DTO + Jackson policy + tests. |
| Embedding arbitrary nested entities/maps in a DTO | Mutable surface expands across the object graph. | Small nested DTOs; limit paths, collections, and sizes. |
| Enabling global `declarativeBinding` without testing | Legacy JavaBean forms may stop setter-binding. | Migration plan, endpoint tests, intentional rollout. |
| Returning raw entities or `BindingResult` in responses | Leaks server-owned fields or rejected inputs. | Response DTO + redaction/allowlist. |
| Writing tests only for valid UI payloads | Misses overposting crafted by arbitrary HTTP clients. | Add tests sending `role`, `locked`, `tenant`, and indexed paths. |

## 17. Pre-Release Checklist

- [ ] Form and JSON inputs use **dedicated DTOs**, never broad JPA entities or domain objects.
- [ ] DTOs/constructors **omit** `role`, `tenantId`, `locked`, `isAdmin`, or server-owned IDs when clients must not set them.
- [ ] Nested DTOs, collections, and constructor args are reviewed to prevent object-graph expansion.
- [ ] For constructor-only `@ModelAttribute`, `@InitBinder` + `setDeclarativeBinding(true)` is applied to the right model attribute.
- [ ] For mutable JavaBeans, `setAllowedFields` is configured explicitly and suppressed fields are tested.
- [ ] `allowedFields` (property binding) is not confused with a constructor-parameter allowlist.
- [ ] **Ignoring extra input** is not confused with **returning 400 on unknown keys**.
- [ ] If strict schema enforcement is required, dedicated input-key validation/Jackson config and regression tests exist.
- [ ] For record/class constructors, parameter names and `@BindParam` compile and resolve accurately.
- [ ] `@Valid`/`@Validated` validates local format/business rules after binding without replacing authorization.
- [ ] Services load resources under proper authentication/authorization and assign only approved fields.
- [ ] Tests cover happy-path forms, overposted role/locked/tenant/id, missing/invalid values, mutable allowlists, and JSON.
- [ ] JPA-managed entities are shielded from request binding, with transactions, concurrency, and PATCH semantics handled.
- [ ] Responses use dedicated DTOs, never leaking server-owned fields or rejected values.
- [ ] For WebFlux, separate `WebTestClient` tests exist and converters/validators are non-blocking.
- [ ] Global binder changes have a migration plan and regression tests so legacy forms do not silently lose data.

**Conclusion:** Spring constructor binding is a powerful tool for **narrowing the HTTP input binding surface**. Yet **a constructor itself does not authorize**: only arguments belonging to a **properly designed request DTO** should come from clients. Combine `setDeclarativeBinding(true)` to block unintended setter binding, `setAllowedFields` where mutable JavaBeans remain, `@Valid` to check data constraints, and **authorization + selective updates** in the service to protect server state. That architecture prevents mass assignment far more reliably than hiding form fields or denylisting a few attributes.

## References

- Spring Framework Reference 6.2 — **MVC @ModelAttribute Argument** (constructor/property binding, `@BindParam`): https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework Reference 6.2 — **MVC @InitBinder and Model Design** (allowedFields, declarative binding): https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Framework Reference — **Core Data Binding** (constructor vs. property): https://docs.spring.io/spring-framework/reference/core/validation/beans-beans.html
- Spring Framework Javadoc 6.2 — **DataBinder#setDeclarativeBinding / setAllowedFields**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework Reference — **MVC Data Binding** (security considerations and property paths): https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html
- Spring Framework Reference 6.2 — **WebFlux @ModelAttribute**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/modelattrib-method-args.html
- Spring Framework Reference — **MVC Validation**: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- OWASP Cheat Sheet — **Mass Assignment**: https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html
