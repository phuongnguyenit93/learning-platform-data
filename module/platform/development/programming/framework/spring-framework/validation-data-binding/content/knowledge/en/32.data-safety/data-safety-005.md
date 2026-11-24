# Unexpected Nested Objects, Map Keys, and Collection Indices in Spring Data Binding

## 1. Scenario: A Valid Form Can Contain Dangerous Field Names

A Spring MVC API accepts fields from a shipment creation form:

```http
POST /api/shipments/form
Content-Type: application/x-www-form-urlencoded

reference=SHP-001&
contact.email=mai@example.com&
addresses[0].city=Ha+Noi&
labels[color]=blue
```

The field names demonstrate all three kinds of property paths:

- `contact.email`: the `email` property of the **nested object** `contact`.
- `addresses[0].city`: the `city` property of element 0 in the **List** `addresses`.
- `labels[color]`: the value for key `color` in the **Map** `labels`.

If the model object also exposes fields that must not be edited, a client can inject extra parameters:

```text
approved=true
contact.admin=true
ownerId=someone-else
labels[role]=administrator
labels[internal_note]=change-approval
addresses[999999].city=Unexpected
addresses[2].city=Extra
```

**Nothing forces a client to send only the inputs rendered by the HTML UI.** A crafted request can submit nested property names, Map keys absent from the form, or huge collection indices. If the binding policy is too broad, the application risks **mass assignment / over-posting**, unintended object-graph mutations, or resource exhaustion while auto-growing Lists/nested objects.

**This lesson focuses on data safety in Spring MVC `WebDataBinder`:**
1. Bean property paths and how Spring interprets nested objects, Lists, and Maps.
2. Risks of binding domain entities directly or using overly broad wildcards.
3. Exact allowlists via `setAllowedFields(...)` and checking `getSuppressedFields()`.
4. `setAutoGrowNestedPaths`, `setAutoGrowCollectionLimit`, and the limits of what they **do not** protect.
5. Jakarta Validation for nested objects/containers and why validation never replaces binding policy.
6. Constructor binding / `setDeclarativeBinding(true)` and allowlist boundaries.
7. Differences from `@RequestBody`/Jackson, and protecting server-owned fields.
8. A **Java 17 + Spring Boot 3.5.6 + MockMvc** example with tests blocking unexpected keys, indices, and nested fields.

Module context: **Spring Framework — validation/data-binding**, **Data Safety** series. The main example uses the Spring MVC Servlet stack and `@ModelAttribute`; do not equate all argument-resolver conclusions with WebFlux or JSON.

## 2. How Are HTTP Field Names Interpreted?

Given a Java DTO:

```java
public class ShipmentForm {
    private Contact contact;
    private List<Address> addresses = new ArrayList<>();
    private Map<String, String> labels = new LinkedHashMap<>();
    // getters/setters
}
```

Spring's `WebDataBinder` can resolve property paths through bean property access, type conversion, and nested path navigation.

| Request field | Data meaning | Risk to examine |
| --- | --- | --- |
| `contact.email` | Sets `email` on the `contact` object | May instantiate child object if null |
| `contact.admin` | Sets `admin` property on the child object | Escalates into non-form state |
| `addresses[0].city` | Sets `city` of List element at 0 | Auto-grows object/collection |
| `addresses[2].city` | Sets element beyond the two expected slots | Exceeds business limits of the form |
| `addresses[999999].city` | Probes huge index | Binding errors / memory overhead if policy is missing |
| `labels[color]` | Map key `color` | Business-valid key |
| `labels[role]` | Map key `role` | Injects unauthorized metadata/role |
| `ownerId` | Direct setter on server-owned field | Mass assignment |
| `approved` | Setter for approval state | Privilege bypass if uncontrolled |

### 2.1. Property paths are a client-controlled interface

In `@ModelAttribute` form/query binding, parameter names sent by the client act as **property paths**. With a mutable bean and public setters, Spring can assign values across multiple levels.

A common anti-pattern:

```java
@PostMapping("/edit")
public String edit(@ModelAttribute AccountEntity account) {
    repository.save(account);
    return "ok";
}
```

This is an **anti-pattern illustration** without `AccountEntity` or `repository` definitions. A JPA entity may contain `id`, `role`, `enabled`, `owner`, or relationship collections; binding directly onto the entity and saving easily lets clients touch unapproved fields.

**Preference:** use a request DTO/command object holding only editable inputs, then have the service look up the real entity, verify permissions, and map **each permitted attribute**.

### 2.2. Map keys do not necessarily correspond to bean property names

For:

```java
private Map<String, String> labels = new LinkedHashMap<>();
```

`labels[color]` typically writes an entry with key `"color"`, whereas `labels[role]` attempts to write another entry into the same Map. That a Map can accept arbitrary keys does not mean **every key belongs to the API contract**.

A Map can hold configuration, classification tags, metadata, or special permissions. If business rules allow only `color` and `tier`, constrain keys **before or during binding**, rather than hoping users stick to the form.

### 2.3. List indices are inputs that can expand the object graph

A path `addresses[1].city` may ask the binder to:
1. Access the `addresses` bean property.
2. Ensure the List has an element at index 1.
3. Instantiate `Address` if the binder has auto-grow enabled and the type can be constructed.
4. Convert the String and set the `city` property.

Thus index `999999` is not merely a "business-invalid value"; with overly broad and unbounded binding settings, it can cause resource pressure or exceptions before Bean Validation runs.

Spring `DataBinder` versions have a default auto-grow limit (commonly 256 elements), yet **defaults do not replace explicit field, request-size, and resource policies for your application**.

## 3. Rule Number One: Dedicated DTOs, Never Bind Entities Directly

Safer design:

```java
public record CreateShipmentCommand(
        String reference,
        String contactEmail,
        List<String> cities,
        Map<String, String> labels) {
}
```

The service accepts the command after validation and authorization checks:

```java
Shipment shipment = shipmentRepository.findById(id)
        .orElseThrow(...);

// Map only fields the client is authorized to change.
shipment.changeReference(command.reference());
shipment.changeContactEmail(command.contactEmail());

// approved/ownerId/role come from the server and authorization.
```

This is an **illustrative fragment** (assuming service, repository, and domain methods exist). The rule is **never** call `BeanUtils.copyProperties(input, entity)` or blindly auto-map every field from a request.

Safe order of operations:
1. Define the input contract.
2. Block unauthorized property paths/keys/indices.
3. Convert data types.
4. Validate structure/content.
5. Check authorization and business invariants in the service.
6. Write only permitted attributes into the model/domain.

Having an `approved` field on the DTO in the demo project below is **intentional to prove the risk**. Real applications should **exclude server-owned fields from input DTOs altogether**, not merely block them in the binder.

## 4. `setAllowedFields`: Positive Allowlist for Property Binding

Spring recommends explicitly declaring which fields may be property-bound:

```java
@InitBinder("shipmentForm")
void configure(WebDataBinder binder) {
    binder.setAllowedFields(
            "reference",
            "contact.email",
            "addresses[0].city",
            "addresses[1].city",
            "labels[color]",
            "labels[tier]");
}
```

Meaning:
- `reference` is allowed.
- `contact.email` is allowed, while `contact.admin` is not.
- Only `addresses[0].city` and `addresses[1].city` are permitted via setter/property binding.
- Only the two keys `labels[color]` and `labels[tier]` are allowed; `labels[role]` is disallowed.
- `approved` and `ownerId` are absent from the list and therefore blocked.

This is an allowlist **over property path names** during binding, not a list of fields that the Jakarta Validation provider will inspect.

### 4.1. Allowed fields support patterns, yet keep them as narrow as possible

Spring supports simple wildcard matching for allowed field patterns. For example:

```java
binder.setAllowedFields("addresses[*].city");
```

can permit many different indices; `*` is a pattern wildcard. If the form only allows two addresses, this broad pattern is **less appropriate** than listing the two exact indices.

Similarly:

```java
binder.setAllowedFields("labels[*]");
```

can accept Map keys outside business rules. Never use a wildcard on sensitive paths merely because it is shorter.

**Recommendation:** paths representing privileges, money, permissions, roles, IDs, owners, or approvals should be removed from request DTOs and controlled in the service. Allowlists serve as an additional layer of defense.

### 4.2. Comparing `setAllowedFields` with `setDisallowedFields`

| API | Principle | Risk |
| --- | --- | --- |
| `setAllowedFields(...)` | Disallows property binding outside the stated set by default | Must be updated whenever the contract changes |
| `setDisallowedFields(...)` | Allows property binding by default except forbidden names | New fields may become bindable before anyone remembers the denylist |
| `setDeclarativeBinding(true)` | Prefers constructor binding; setter binding only when `allowedFields` is configured | Does not block poorly designed constructor arguments |
| Immutable DTO containing only public inputs | Restricts fields directly in the data structure | Requires explicit mapping onto domain entities |

The Spring reference notes that `allowedFields` patterns are **case-sensitive**, whereas `disallowedFields` patterns are handled **case-insensitively**. For security, an allowlist is generally stronger than a denylist.

### 4.3. Canonical property names and quoted key notation

Spring normalizes certain property path forms, such as bracket-quoted map keys. Therefore:
- Whether a key in the URL appears as `labels[color]` or quoted does not inherently create a separate security namespace.
- Do not hand-roll raw URL string allowlist checks assuming they match how `WebDataBinder` canonicalizes field names.
- Use the binder's policy for property binding and test syntax variants accepted by the framework.

Canonicalized field names may differ from their literal appearance in the request; in security tests, prioritize asserting **actual bound values** and the suppressed fields list rather than assuming every syntactic variant behaves identically.

## 5. Detecting Blocked Fields: `getSuppressedFields()`

When a client sends a field name absent from the allowlist, Spring `DataBinder` can **suppress** that field from property binding and record its name in `BindingResult`.

```java
@PostMapping("/form")
public ResponseEntity<?> submit(
        @Valid @ModelAttribute("shipmentForm") ShipmentForm form,
        BindingResult errors) {

    String[] suppressed = errors.getSuppressedFields();

    if (suppressed.length > 0) {
        return ResponseEntity.badRequest().build();
    }

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().build();
    }

    return ResponseEntity.ok().build();
}
```

This is a fragment; the full project classes appear in section 12.

**Key point:** `errors.hasErrors()` **does not necessarily return true just because fields were suppressed**. Suppression reflects binder policy metadata rather than always producing a validator `FieldError`. Therefore, if you want to **reject** requests with out-of-contract fields, inspect `getSuppressedFields()` **separately**.

A public response might look like:

```json
{"code":"UNEXPECTED_FIELD","suppressedCount":2}
```

The demo returns only the **count** of suppressed fields, without echoing client-supplied field names verbatim. In internal logs as well, bound the length/cardinality of unknown names and avoid logging raw PII.

### 5.1. Suppressed vs. unknown field vs. constraint violation

| Category | Example | Where handled |
| --- | --- | --- |
| Suppressed as disallowed | `labels[role]` outside allowlist | `BindingResult.getSuppressedFields()` |
| Unknown property | `unknownField` absent on the bean | Binder ignores/rejects per config; with a narrow allowlist it may also be suppressed |
| Type mismatch | `addresses[0].number=abc` on an allowed `Integer` field | Type conversion/binding error |
| Jakarta constraint violation | `addresses[0].city=""` | `@NotBlank` after binding |
| Out-of-bounds List index | `addresses[999999].city` | May be suppressed first, or trigger property-access/auto-grow errors depending on policy |
| Business-invalid Map key | `labels[role]` | Allowlist or dedicated validation/key policy |

Do not rely on `@Valid` to "forbid extra fields" if the binder ignored them or they do not exist on the DTO. Bean Validation checks **the post-binding object**, not every raw field name the client sent.

### 5.2. Endpoint error-handling order

In the complete project, the controller checks:

```text
if suppressed fields not empty:
    HTTP 400, code UNEXPECTED_FIELD
else if BindingResult contains errors:
    HTTP 400, code INVALID_FORM
else:
    HTTP 200, mapped safe response
```

This ordering is deliberate: when **blocked fields** are present, the request is rejected even if other allowed fields also fail validation. Other applications may return multiple error categories together, provided the ordering is defined and tested. Never let blocked fields reach a domain write.

## 6. Two Auto-Grow Settings: Distinct Roles and Limits

### 6.1. `setAutoGrowNestedPaths(boolean)`

```java
binder.setAutoGrowNestedPaths(true);
```

Allows the binder to instantiate intermediate objects/collections for certain property paths when instantiable:

```text
contact == null
  + request contact.email="mai@example.com"
  => instantiate Contact and set email (when applicable)
```

This simplifies forms by avoiding pre-initializing every nested object before binding. Yet it can also expand the object graph unexpectedly if field names are unrestricted.

If disabled:

```java
binder.setAutoGrowNestedPaths(false);
```

the binder no longer auto-instantiates intermediate properties in the same way. If the form needs `contact.email`, you can **pre-initialize** `contact = new Contact()` in the DTO, or redesign with constructor binding/different DTOs. Disabling auto-grow is not a standalone mass-assignment fix.

### 6.2. `setAutoGrowCollectionLimit(int)`

```java
binder.setAutoGrowCollectionLimit(4);
```

Caps auto-growth of **arrays/Lists** when the binder encounters indexed property paths. For example, a limit of 4 prevents requests from growing indices into the thousands when a binder still allows a broad index pattern.

**Do not misunderstand it:**
- It **does not** guarantee every List holds at most 4 elements regardless of origin; it caps **auto-grow during binding**.
- It **is not** a general limit on the number of **Map entries** when an attacker sends distinct map keys.
- It **does not** limit HTTP body size, request parameter count, string length, or converter cost.
- It **does not** guarantee an out-of-range index merely goes into `BindingResult`; depending on binder path/config it may raise an exception requiring handling and tests.

Use together:
1. **Allowlist** for exact business-permitted indices.
2. **Auto-grow collection limit** as a secondary guardrail.
3. **HTTP/request limits** at the server/container/proxy level.
4. **Bean Validation** on element count after binding.
5. **Business validation** on counts/indices relative to the user/tenant.

### 6.3. Example of a large index blocked before auto-grow

With the allowlist:

```java
binder.setAllowedFields(
        "addresses[0].city",
        "addresses[1].city");
binder.setAutoGrowCollectionLimit(4);
```

a request `addresses[999999].city=Rogue` fails the allowlist and can be **suppressed** before the binder attempts to grow the List. In the complete example, tests verify:
- `addresses[999999].city` appears in suppressed fields.
- The List contains only elements that were actually permitted and submitted.
- The API returns `UNEXPECTED_FIELD` and stores no out-of-contract data.

If you used `addresses[*].city` instead of the two explicit indices, the allowlist would stop blocking arbitrary indices; only the auto-grow limit and downstream layers would remain, making behavior harder to control.

## 7. Map Keys: Allowlists, Entry Caps, and "Dangerous Metadata"

### 7.1. Use exact keys

If the contract permits only two tags:

```text
labels[color]
labels[tier]
```

then the allowlist should name them explicitly:

```java
binder.setAllowedFields(
        "labels[color]",
        "labels[tier]");
```

Requests with `labels[role]`, `labels[isAdmin]`, `labels[tenantId]`, or `labels[discount]` should never be bound simply because `labels` is a `Map<String,String>`.

An open Map is a **caller-controlled data field**; if arbitrary keys are allowed, enforce:
- Allowed key naming rules and server-reserved key namespaces.
- Entry count and key/value length limits before or during decoding.
- Duplicate-key and canonicalization policies.
- Dedicated schema/validation for value types.
- Authorization whenever keys carry business meaning.

### 7.2. `@Size(max=2)` does not replace a key allowlist

```java
@Size(max = 2)
Map<String, String> labels;
```

This constraint checks entry count **after the object is bound**, yet does not decide **which keys** are allowed and does not prevent resource work already spent parsing a huge request. Two entries `role` and `tenantId` still satisfy `max=2` while violating the contract.

Similarly:

```java
Map<@NotBlank String, @NotBlank String> labels;
```

can enforce non-blank keys/values via container element constraints, but **does not** replace a key allowlist like `color` or `tier`.

### 7.3. Map keys and business semantics

If a system uses a Map as a "bag of fields," never let downstream backend logic treat client-sent keys named `role`, `approved`, or `owner` as authority to alter corresponding entity properties. When flexible metadata is needed:
- Separate the **user-defined** namespace from the **server-owned** namespace.
- Enforce key patterns and size limits.
- Block reserved keys.
- Require separate authorization for any action affecting permissions or billing.

**Post-binding key checks remain useful, yet insufficient:** if the binder already accepted thousands of keys before validation ran, resource cost has already been incurred. Block as early as possible.

## 8. Nested Objects: Cascaded Validation Differs from Field Write Access

### 8.1. `@Valid` traverses into objects, but does not choose bindable fields

```java
public class Contact {
    @NotBlank
    @Email
    private String email;

    private boolean admin;
    // getters/setters...
}

public class ShipmentForm {
    @NotNull
    @Valid
    private Contact contact;
}
```

`@NotNull` forbids `contact=null`; `@Valid` tells Jakarta Validation to cascade into `Contact.email`. Yet if the binder has no allowlist and a client sends `contact.admin=true`, Bean Validation **does not block it by default**; no constraint forbids boolean `admin`.

Three independent questions:
- **Bind:** may this field be accepted from the client?
- **Validate:** once bound, does the data satisfy constraints?
- **Authorize:** does the caller have permission to make this change?

Never treat one of the three as a substitute for the other two.

### 8.2. Collection element cascading

```java
@Size(min = 1, max = 2)
private List<@Valid Address> addresses = new ArrayList<>();
```

`@Size` checks **List length after binding**; `@Valid` on each element triggers validation on `Address.city`. With `Address.city @NotBlank`:
- An element at index 0 with a blank city → constraint violation.
- Zero addresses → `@Size(min=1)` fails.
- Null element → `@Valid` cascading typically skips null; to forbid nulls, use `List<@NotNull @Valid Address>`.

If a request includes `addresses[2].city` while the form allows only indices 0 and 1, the **allowlist** must exclude it up front. `@Size(max=2)` is not enough for index security.

### 8.3. Preventing object-graph explosion

When nested paths like `orders[10].items[50].options[99].value` are open, expansion can grow rapidly. Avoid:
- Self-referential/cyclic DTOs with public setters exposed to the binder.
- Exposing JPA entity relationships as the request property graph.
- Broad `*` patterns spanning multiple levels.
- Unbounded nested lists without business caps.

Bound not just **a single collection**, but **total element count, path depth, field count, and processing cost** across the entire request.

## 9. Constructor Binding and `setDeclarativeBinding(true)`

Spring Framework 6.1+ supports:

```java
@InitBinder
void init(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
```

When **declarative binding** is enabled, Spring prefers constructor binding; property/setter binding does not happen automatically unless `allowedFields` is configured.

This helps immutable/record DTOs maintain a narrow input contract:

```java
public record ShipmentInput(
        String reference,
        String contactEmail,
        List<String> cities) {}
```

**Important nuance:** `setAllowedFields` is a policy for **property binding**; it is **not** a general filter for constructor arguments. Spring MVC can also perform constructor binding from indexed Map/List request values when declared on the constructor. Never define a constructor taking `admin`, `role`, or `ownerId` assuming setter allowlists will shield it.

To stay safe with constructor binding:
1. Build constructors/records accepting only genuinely public input attributes.
2. For Maps/Lists in constructors, control **keys/indices/sizes** and validate the resulting object.
3. Never use a domain entity constructor as the input contract.
4. Keep server-owned fields out of request constructors.
5. Test requests with extra keys, indices, and nested paths.

In the runnable project in section 12, we use a **mutable DTO + explicit allowlist** so `getSuppressedFields()` can be observed directly, leaving declarative binding off to avoid mixing the two mechanisms.

## 10. JSON via `@RequestBody`: Do Not Trust Binder Allowlists to Filter Jackson

Example:

```java
@PostMapping("/json")
public ResponseEntity<?> create(
        @Valid @RequestBody ShipmentForm body) {
    // ...
}
```

When `Content-Type: application/json`, Jackson/`HttpMessageConverter` reads JSON and instantiates the object. `WebDataBinder#setAllowedFields` for form property binding **does not control Jackson field deserialization** in the same manner.

JSON:

```json
{
  "reference": "SHP-001",
  "approved": true,
  "contact": {
    "email": "mai@example.com",
    "admin": true
  },
  "labels": {
    "role": "administrator"
  }
}
```

can be deserialized by Jackson into a mutable DTO with matching setters even if `@InitBinder` allowlisted only `contact.email`/`labels[color]` for form binding. **Never expose a JSON endpoint like that with an input DTO containing server-owned fields.**

A better pattern is a dedicated request record:

```java
public record CreateShipmentJson(
        @NotBlank String reference,
        @NotBlank @Email String contactEmail,
        @Size(max = 2) Map<String, String> labels) {}
```

After decoding, enforce schema/key policies and service authorization; `approved`/`ownerId` are set solely by the server. If unknown JSON properties must be rejected, configure Jackson/DTOs **explicitly** and test specifically rather than relying on the form binder. Jackson has its own rules for type coercion, unknown properties, duplicate JSON keys, and creators.

**A precise detail:** Spring MVC may still create a `WebDataBinder` for the **validation** step after Jackson instantiates the DTO. Thus do not say "`@InitBinder` never runs with `@RequestBody`"; the accurate statement is that **WebDataBinder's setter field allowlist does not govern how Jackson decodes JSON**.

## 11. Defining a Safe API Contract for Field Paths

Before writing the binder, translate a permission table into code:

| Kind | Valid name | Rule |
| --- | --- | --- |
| Flat field | `reference` | Non-blank string |
| Nested | `contact.email` | Valid email format, present |
| List index | `addresses[0].city`, `addresses[1].city` | Up to two addresses; each city non-blank |
| Map entry | `labels[color]`, `labels[tier]` | Only these two keys accepted |
| Server-owned | `approved`, `ownerId`, `contact.admin` | Cannot be modified by client |
| Out-of-range index | `addresses[2].city` and higher | Reject/suppress |
| Disallowed Map key | `labels[role]`, `labels[tenant]` | Reject/suppress |

Crucially, this table governs **field input permission**. Bean Validation is added **on top** to check the quality of permitted values.

If the UI can add a variable number of addresses (e.g., 0 to 10), design:
- A dedicated JSON API with a list DTO and size bounds, enforcing body size limits early.
- Or a form endpoint with a dynamic allowlist built **from trusted server permissions/schema**, combined with index validation and `autoGrowCollectionLimit`.
- Never take a client parameter (like `count=100000`) to blindly expand the allowlist.

## 12. Complete Project: Spring Boot 3.5.6 + Java 17

The demo project provides two verification layers:
- **MockMvc**: sends real form requests through the controller and verifies the server rejects unexpected nested properties, Map keys, and indices.
- **`WebDataBinder` unit tests**: verify exactly which fields are suppressed and that the object graph **never receives** unauthorized values.

In production, remove sensitive setters from request DTOs entirely; the demo keeps them so the additional defense layer can be tested explicitly.

### 12.1. Directory layout

```text
safe-binding-demo/
├── pom.xml
├── src/main/java/demo/safebinding/
│   ├── SafeBindingApplication.java
│   ├── ShipmentForm.java
│   └── ShipmentController.java
└── src/test/java/demo/safebinding/
    ├── ShipmentControllerTest.java
    └── ShipmentBinderTest.java
```

### 12.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>safe-binding-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

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

`spring-boot-starter-web` runs Spring MVC Servlet and MockMvc. `spring-boot-starter-validation` supplies the Bean Validation provider so `@Valid`, `@NotBlank`, `@Email`, and `@Size` execute. No WebFlux starter is needed for this lesson.

### 12.3. `SafeBindingApplication.java`

```java
package demo.safebinding;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeBindingApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeBindingApplication.class, args);
    }
}
```

### 12.4. `ShipmentForm.java`

```java
package demo.safebinding;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class ShipmentForm {

    @NotBlank(message = "reference.required")
    private String reference;

    @NotNull(message = "contact.required")
    @Valid
    private Contact contact;

    @Size(min = 1, max = 2, message = "addresses.size")
    private List<@Valid Address> addresses = new ArrayList<>();

    @Size(max = 2, message = "labels.size")
    private Map<String, String> labels = new LinkedHashMap<>();

    // Exists solely to demonstrate mass assignment risk in this demo.
    private boolean approved;
    private String ownerId;

    public String getReference() {
        return reference;
    }

    public void setReference(String reference) {
        this.reference = reference;
    }

    public Contact getContact() {
        return contact;
    }

    public void setContact(Contact contact) {
        this.contact = contact;
    }

    public List<Address> getAddresses() {
        return addresses;
    }

    public void setAddresses(List<Address> addresses) {
        this.addresses = addresses;
    }

    public Map<String, String> getLabels() {
        return labels;
    }

    public void setLabels(Map<String, String> labels) {
        this.labels = labels;
    }

    public boolean isApproved() {
        return approved;
    }

    public void setApproved(boolean approved) {
        this.approved = approved;
    }

    public String getOwnerId() {
        return ownerId;
    }

    public void setOwnerId(String ownerId) {
        this.ownerId = ownerId;
    }

    public static class Contact {
        @NotBlank(message = "email.required")
        @Email(message = "email.invalid")
        private String email;

        // Intentionally public setter, yet policy forbids binding this field.
        private boolean admin;

        public String getEmail() {
            return email;
        }

        public void setEmail(String email) {
            this.email = email;
        }

        public boolean isAdmin() {
            return admin;
        }

        public void setAdmin(boolean admin) {
            this.admin = admin;
        }
    }

    public static class Address {
        @NotBlank(message = "city.required")
        private String city;

        public String getCity() {
            return city;
        }

        public void setCity(String city) {
            this.city = city;
        }
    }
}
```

The `Contact` field starts as null; `WebDataBinder` can auto-grow it upon receiving `contact.email`. The `addresses` List and `labels` Map are pre-initialized empty so the binder only needs to add elements/entries on permitted paths.

### 12.5. `ShipmentController.java`

```java
package demo.safebinding;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Arrays;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/shipments")
public class ShipmentController {

    @InitBinder("shipmentForm")
    void initBinder(WebDataBinder binder) {
        binder.setAllowedFields(
                "reference",
                "contact.email",
                "addresses[0].city",
                "addresses[1].city",
                "labels[color]",
                "labels[tier]");

        binder.setAutoGrowNestedPaths(true);
        binder.setAutoGrowCollectionLimit(4);
    }

    public record ShipmentView(
            String reference,
            String email,
            List<String> cities,
            Map<String, String> labels) {
    }

    public record ApiResult(
            String code,
            int suppressedCount,
            List<String> fields,
            ShipmentView shipment) {
    }

    @PostMapping(
            path = "/form",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<ApiResult> create(
            @Valid @ModelAttribute("shipmentForm") ShipmentForm form,
            BindingResult errors) {

        String[] suppressed = errors.getSuppressedFields();

        // Check suppression separately: hasErrors() can be false.
        if (suppressed.length > 0) {
            return ResponseEntity.badRequest().body(
                    new ApiResult(
                            "UNEXPECTED_FIELD",
                            suppressed.length,
                            List.of(),
                            null));
        }

        if (errors.hasErrors()) {
            List<String> fields = errors.getFieldErrors()
                    .stream()
                    .map(e -> e.getField())
                    .distinct()
                    .sorted()
                    .toList();

            return ResponseEntity.badRequest().body(
                    new ApiResult("INVALID_FORM", 0, fields, null));
        }

        // Emit only a "view" of the data the client is permitted to submit.
        var cities = form.getAddresses().stream()
                .map(ShipmentForm.Address::getCity)
                .toList();

        var view = new ShipmentView(
                form.getReference(),
                form.getContact().getEmail(),
                cities,
                Map.copyOf(form.getLabels()));

        return ResponseEntity.ok(
                new ApiResult("ACCEPTED", 0, List.of(), view));
    }
}
```

**Deliberate details in the code:**
- `@InitBinder("shipmentForm")` configures only the binder whose object name matches `@ModelAttribute("shipmentForm")`.
- `setAllowedFields` blocks `approved`, `ownerId`, `contact.admin`, unknown Map keys, and List indices outside [0] and [1].
- `setAutoGrowNestedPaths(true)` allows instantiating valid `Contact` and `Address` objects during binding; the allowlist keeps arbitrary paths closed.
- `setAutoGrowCollectionLimit(4)` serves as a secondary layer alongside the allowlist, not a replacement for explicit index limits.
- `@Valid` triggers Bean Validation; `BindingResult` sits **immediately after** the DTO.
- `suppressed.length > 0` is checked **before** `errors.hasErrors()`.
- Raw suppressed field names are not returned in the response to avoid reflecting untrusted input.
- `ShipmentView` omits permission, owner, and approval fields.
- In this example, data is only returned, **not persisted**. Production must enforce server-side authorization and selectively map onto entities.

The `Arrays` import in the controller above is unnecessary; if your IDE flags an unused import, you can remove `import java.util.Arrays;` without affecting functionality.

### 12.6. `ShipmentControllerTest.java` — HTTP testing with MockMvc

```java
package demo.safebinding;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ShipmentControllerTest {

    @Autowired
    MockMvc mvc;

    private MockHttpServletRequestBuilder form(
            String reference, String email, String city) {
        return post("/api/shipments/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("reference", reference)
                .param("contact.email", email)
                .param("addresses[0].city", city)
                .param("labels[color]", "blue");
    }

    @Test
    void validNestedListAndMapAreAccepted() throws Exception {
        mvc.perform(form("SHP-001", "mai@example.com", "Hue"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value("ACCEPTED"))
                .andExpect(jsonPath("$.suppressedCount").value(0))
                .andExpect(jsonPath("$.shipment.reference")
                        .value("SHP-001"))
                .andExpect(jsonPath("$.shipment.email")
                        .value("mai@example.com"))
                .andExpect(jsonPath("$.shipment.cities[0]")
                        .value("Hue"))
                .andExpect(jsonPath("$.shipment.labels.color")
                        .value("blue"));
    }

    @Test
    void allowedSecondAddressIndexWorks() throws Exception {
        mvc.perform(form("SHP-001", "mai@example.com", "Hue")
                        .param("addresses[1].city", "Da Nang")
                        .param("labels[tier]", "regular"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.shipment.cities[1]")
                        .value("Da Nang"))
                .andExpect(jsonPath("$.shipment.labels.tier")
                        .value("regular"));
    }

    @Test
    void rejectTopLevelApprovedField() throws Exception {
        mvc.perform(form("SHP-001", "mai@example.com", "Hue")
                        .param("approved", "true"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("UNEXPECTED_FIELD"))
                .andExpect(jsonPath("$.suppressedCount").value(1));
    }

    @Test
    void rejectTopLevelOwnerId() throws Exception {
        mvc.perform(form("SHP-001", "mai@example.com", "Hue")
                        .param("ownerId", "other-user"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("UNEXPECTED_FIELD"));
    }

    @Test
    void rejectUnexpectedNestedAdminProperty() throws Exception {
        mvc.perform(form("SHP-001", "mai@example.com", "Hue")
                        .param("contact.admin", "true"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("UNEXPECTED_FIELD"));
    }

    @Test
    void rejectUnexpectedMapKey() throws Exception {
        mvc.perform(form("SHP-001", "mai@example.com", "Hue")
                        .param("labels[role]", "administrator"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("UNEXPECTED_FIELD"))
                .andExpect(jsonPath("$.suppressedCount").value(1));
    }

    @Test
    void rejectUnexpectedAddressIndexTwo() throws Exception {
        mvc.perform(form("SHP-001", "mai@example.com", "Hue")
                        .param("addresses[2].city", "Unknown"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("UNEXPECTED_FIELD"));
    }

    @Test
    void rejectVeryLargeAddressIndex() throws Exception {
        mvc.perform(form("SHP-001", "mai@example.com", "Hue")
                        .param("addresses[999999].city", "Rogue"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("UNEXPECTED_FIELD"));
    }

    @Test
    void rejectUnknownParameterInsteadOfIgnoringIt() throws Exception {
        mvc.perform(form("SHP-001", "mai@example.com", "Hue")
                        .param("surprise", "unexpected"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("UNEXPECTED_FIELD"));
    }

    @Test
    void blankNestedEmailFailsBeanValidation() throws Exception {
        mvc.perform(form("SHP-001", "", "Hue"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_FORM"))
                .andExpect(jsonPath("$.fields[0]")
                        .value("contact.email"));
    }

    @Test
    void malformedEmailFailsBeanValidation() throws Exception {
        mvc.perform(form("SHP-001", "not-email", "Hue"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_FORM"))
                .andExpect(jsonPath("$.fields[0]")
                        .value("contact.email"));
    }

    @Test
    void blankListElementCityFailsBeanValidation() throws Exception {
        mvc.perform(form("SHP-001", "mai@example.com", ""))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_FORM"))
                .andExpect(jsonPath("$.fields[0]")
                        .value("addresses[0].city"));
    }

    @Test
    void absentListFailsSizeMin() throws Exception {
        mvc.perform(post("/api/shipments/form")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("reference", "SHP-001")
                        .param("contact.email", "mai@example.com"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_FORM"))
                .andExpect(jsonPath("$.fields[0]").value("addresses"));
    }

    @Test
    void absentContactFailsNotNull() throws Exception {
        mvc.perform(post("/api/shipments/form")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("reference", "SHP-001")
                        .param("addresses[0].city", "Hue"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_FORM"))
                .andExpect(jsonPath("$.fields[0]").value("contact"));
    }

    @Test
    void blankReferenceFailsNotBlank() throws Exception {
        mvc.perform(form("   ", "mai@example.com", "Hue"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_FORM"))
                .andExpect(jsonPath("$.fields[0]").value("reference"));
    }

    @Test
    void unexpectedFieldHasPriorityOverOtherInvalidValues()
            throws Exception {
        mvc.perform(form("", "mai@example.com", "Hue")
                        .param("labels[role]", "admin"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("UNEXPECTED_FIELD"))
                .andExpect(jsonPath("$.suppressedCount").value(1));
    }
}
```

The suite above has **16 test cases**: 2 success cases, 7 checking unexpected fields/indices/keys, 5 verifying nested/list/form constraints, plus contract/error-priority cases. Counting `@Test` methods is the authoritative source; when adding or removing tests, update category breakdowns rather than relying on an unchecked fixed total.

**Core point:** testing only `200` on a valid form proves nothing about blocking `approved`, `contact.admin`, `labels[role]`, or `addresses[999999]`. Negative tests are the most important part of a data-safety lesson.

### 12.7. `ShipmentBinderTest.java` — asserting exact suppressed fields

```java
package demo.safebinding;

import org.junit.jupiter.api.Test;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.web.bind.WebDataBinder;

import java.util.Arrays;
import java.util.Set;
import java.util.TreeSet;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ShipmentBinderTest {

    @Test
    void unexpectedNestedMapAndListPathsAreSuppressed() {

        ShipmentForm target = new ShipmentForm();

        WebDataBinder binder =
                new WebDataBinder(target, "shipmentForm");

        // Reuse the controller's exact @InitBinder configuration.
        new ShipmentController().initBinder(binder);

        MutablePropertyValues values = new MutablePropertyValues();
        values.add("reference", "SHP-001");
        values.add("contact.email", "mai@example.com");
        values.add("addresses[0].city", "Hue");
        values.add("labels[color]", "blue");

        values.add("approved", "true");
        values.add("ownerId", "another-user");
        values.add("contact.admin", "true");
        values.add("labels[role]", "administrator");
        values.add("addresses[999999].city", "Rogue");

        binder.bind(values);

        Set<String> suppressed = new TreeSet<>(
                Arrays.asList(
                        binder.getBindingResult().getSuppressedFields()));

        assertEquals(
                Set.of(
                        "approved",
                        "ownerId",
                        "contact.admin",
                        "labels[role]",
                        "addresses[999999].city"),
                suppressed);

        // Only valid property paths mutate the DTO.
        assertFalse(target.isApproved());
        assertNull(target.getOwnerId());
        assertFalse(target.getContact().isAdmin());
        assertEquals("mai@example.com",
                target.getContact().getEmail());

        assertEquals(1, target.getAddresses().size());
        assertEquals("Hue",
                target.getAddresses().get(0).getCity());

        assertEquals(1, target.getLabels().size());
        assertEquals("blue", target.getLabels().get("color"));
        assertFalse(target.getLabels().containsKey("role"));
    }

    @Test
    void allowedFieldsCanBindTwoAddressesAndTwoLabels() {

        ShipmentForm target = new ShipmentForm();

        WebDataBinder binder =
                new WebDataBinder(target, "shipmentForm");
        new ShipmentController().initBinder(binder);

        MutablePropertyValues values = new MutablePropertyValues();
        values.add("addresses[0].city", "Hue");
        values.add("addresses[1].city", "Da Nang");
        values.add("labels[color]", "blue");
        values.add("labels[tier]", "regular");

        binder.bind(values);

        assertTrue(binder.getBindingResult()
                .getSuppressedFields().length == 0);
        assertEquals(2, target.getAddresses().size());
        assertEquals("Da Nang",
                target.getAddresses().get(1).getCity());
        assertEquals(2, target.getLabels().size());
    }
}
```

These two `WebDataBinder` tests run **without a Spring ApplicationContext**: they instantiate the binder manually and invoke the same configuration method as the controller. They prove specifically:
- Unexpected fields are recorded in `getSuppressedFields()`.
- Nested `contact.admin` stays false.
- `approved` and `ownerId` never receive client values.
- A huge index does not expand the List once excluded by the allowlist.
- The Map accepts only permitted keys.
- Both allowed List indices and Map keys still work.

**Test note:** `new WebDataBinder(...)` does not automatically include a Jakarta Validation provider like an MVC-configured binder. These two tests verify **binding/suppression** only, not `@NotBlank`/`@Size`; Bean Validation is tested via MockMvc in the preceding class.

### 12.8. Running tests and starting the server

In the `safe-binding-demo` directory:

```bash
mvn test
```

All **18 tests** (16 MockMvc + 2 WebDataBinder) are expected to pass in a Java 17/Maven environment with dependencies available. These are **expected results of the sample code**, not observed execution results in the authoring environment.

Start the server:

```bash
mvn spring-boot:run
```

No database is required. Spring Boot's web starter provides the embedded Servlet server. Be sure to send `application/x-www-form-urlencoded` when testing the form; sending JSON to the same endpoint will not exercise the binding path demonstrated here.

## 13. Testing with curl

### 13.1. Valid form

```bash
curl -i -X POST \
  'http://localhost:8080/api/shipments/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'reference=SHP-001' \
  --data-urlencode 'contact.email=mai@example.com' \
  --data-urlencode 'addresses[0].city=Hue' \
  --data-urlencode 'labels[color]=blue'
```

Expected HTTP **200** with a body equivalent to:

```json
{
  "code": "ACCEPTED",
  "suppressedCount": 0,
  "fields": [],
  "shipment": {
    "reference": "SHP-001",
    "email": "mai@example.com",
    "cities": ["Hue"],
    "labels": {"color": "blue"}
  }
}
```

### 13.2. Injecting an unexpected Map key

```bash
curl -i -X POST \
  'http://localhost:8080/api/shipments/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'reference=SHP-001' \
  --data-urlencode 'contact.email=mai@example.com' \
  --data-urlencode 'addresses[0].city=Hue' \
  --data-urlencode 'labels[color]=blue' \
  --data-urlencode 'labels[role]=administrator'
```

Expected HTTP **400**:

```json
{
  "code": "UNEXPECTED_FIELD",
  "suppressedCount": 1,
  "fields": [],
  "shipment": null
}
```

**Why isn't it a constraint error?** Key `role` was suppressed by the binder for not being in the allowlist; it never even becomes a Map entry before being rejected.

### 13.3. Huge List index

```bash
curl -i -X POST \
  'http://localhost:8080/api/shipments/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'reference=SHP-001' \
  --data-urlencode 'contact.email=mai@example.com' \
  --data-urlencode 'addresses[0].city=Hue' \
  --data-urlencode 'addresses[999999].city=Unexpected'
```

Expected HTTP **400** with `UNEXPECTED_FIELD`. With an exact allowlist, the huge index is blocked rather than used to allocate elements. `setAutoGrowCollectionLimit(4)` remains helpful as a secondary safeguard if policy later changes.

### 13.4. Privileged nested field

```bash
curl -i -X POST \
  'http://localhost:8080/api/shipments/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'reference=SHP-001' \
  --data-urlencode 'contact.email=mai@example.com' \
  --data-urlencode 'addresses[0].city=Hue' \
  --data-urlencode 'contact.admin=true' \
  --data-urlencode 'approved=true'
```

Expected HTTP **400**, `suppressedCount=2`. No code accepts `approved` state from the client. A real system requires service-layer authorization whenever an endpoint approves shipments.

### 13.5. Allowed field failing constraints

```bash
curl -i -X POST \
  'http://localhost:8080/api/shipments/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'reference=SHP-001' \
  --data-urlencode 'contact.email=not-an-email' \
  --data-urlencode 'addresses[0].city=Hue'
```

Expected HTTP **400**:

```json
{
  "code": "INVALID_FORM",
  "suppressedCount": 0,
  "fields": ["contact.email"],
  "shipment": null
}
```

This is **Bean Validation after binding**. It differs from `UNEXPECTED_FIELD`, which occurs when a policy-disallowed field name is submitted.

## 14. Field Suppression, Validation, and Authorization Do Not Replace Each Other

| Layer | Input controlled | Question answered |
| --- | --- | --- |
| HTTP/server limits | Body/param count/size | Can the request be processed at reasonable cost? |
| Binder allowlist | Names/property paths | May the client supply this field? |
| Auto-grow cap | Indexed list/array expansion | How far can an indexed field grow automatically? |
| Jakarta Validation | Values, nested objects, container elements | Does the post-binding object meet data constraints? |
| Service authorization | Caller, tenant, entity, operation | Does this caller have rights to modify this object/field? |
| Domain invariants | State transitions, quantities, references | Is the change business-valid? |
| Persistence mapping | Exact fields actually saved | Are any server-owned fields accidentally copied? |

Examples:
- `labels[role]` is blocked by the allowlist even when its value is non-blank.
- `contact.email="bad-email"` is accepted by the allowlist yet rejected by `@Email`.
- `approved=true` is blocked by the allowlist, yet the server still needs authorization on any dedicated approval endpoint.
- `addresses[1].city` passes the allowlist yet may be business-invalid if the user is not allowed to add a second address; that check belongs in the service.
- `addresses[999999].city` is not "just a size constraint"; the index path is evaluated while the binder runs.

## 15. Common Design Mistakes and Attack Vectors

### 15.1. Overly broad wildcards

```java
binder.setAllowedFields("contact.*", "labels[*]", "addresses[*].*");
```

This is an **anti-pattern** when objects contain privileged properties. It can open paths to `contact.admin`, arbitrary Map keys, and future properties added later.

A technically valid wildcard does not imply **authorization**. If a form genuinely has dynamic fields, determine allowed keys/indices from a server-side schema and test the bounds.

### 15.2. Denylist missing new fields

```java
binder.setDisallowedFields("admin", "role");
```

This misses other paths such as `contact.admin`, `approved`, or Map entries. A field added during a refactor can become bindable even though it is absent from the UI. A positive allowlist is far more reliable.

### 15.3. Believing `@Valid` forbids extra fields

`@Valid` checks constraints on the object Spring/Jackson already constructed. It has no awareness of out-of-schema input names if they were never bound onto the object or the validator was not built to inspect the raw request.

### 15.4. Using `@Size(max=2)` instead of an auto-grow limit

`@Size` is evaluated **after binding**; if the binder already expanded a huge List beforehand, Bean Validation arrives too late. Combine an exact index allowlist, `setAutoGrowCollectionLimit`, and request limits.

### 15.5. Removing setters while leaving privileged fields in the constructor

If a record exposes `boolean approved` in its primary constructor, Spring constructor binding can populate it from the request. `setAllowedFields` governs property binding only, not a universal shield over constructor arguments.

### 15.6. Using JPA entities directly

The binder can traverse relationships/collections, mix client input with entity state, and bypass authorization if code saves too early. Create dedicated input DTOs and map selectively.

### 15.7. Sharing a sensitive DTO between JSON and forms

A DTO guarded by `@InitBinder` for forms is not automatically safe when reused in `@RequestBody` JSON. Jackson deserializes through a separate mechanism. Create API-specific DTOs and test each content type.

### 15.8. Ignoring suppressed fields because `hasErrors()==false`

If policy requires rejecting extra inputs, read `BindingResult.getSuppressedFields()`. Never assume suppression produces a `FieldError` or a Bean Validation violation.

### 15.9. Assuming Map keys cannot affect privileges

A metadata Map can be interpreted downstream as permissions, discounts, or internal state. Block reserved keys before they affect business logic; do not validate values with regex alone.

### 15.10. Echoing attacker-supplied field names in responses

Field names can be arbitrarily long or contain client-crafted content. If detailed feedback is needed, cap length, escape properly for encoding, and distinguish contract field paths from raw keys. The demo uses an error code and suppressed count instead of echoing raw input.

## 16. Checklist When Implementing or Maintaining Nested Forms

1. Clearly separate request DTOs from server-stateful entities.
2. Are any `id`, `owner`, `admin`, `approved`, or `role` fields exposed via public setters or constructors?
3. Enumerate **every** nested property path the UI actually uses.
4. Enumerate **every** public Map key, avoiding `map[*]` whenever keys carry business meaning.
5. Enumerate permitted **List indices** or derive bounds from a server schema.
6. Register `@InitBinder("attributeName")` with the exact model attribute name.
7. Use `setAllowedFields(...)` and never substitute a denylist just for brevity.
8. Configure `setAutoGrowNestedPaths` and `setAutoGrowCollectionLimit` per business rules.
9. Enforce HTTP body size, parameter count, and object-graph depth limits.
10. Decide whether to **reject or silently ignore** suppressed fields; if rejecting, inspect `getSuppressedFields()` explicitly.
11. Place `BindingResult` immediately after `@Valid @ModelAttribute` for clear error handling.
12. Put `@NotNull` on required nested objects and `@Valid` to cascade.
13. Use `List<@Valid Item>` and `@Size` for collections; do not treat them as an index allowlist.
14. When using `Map<K,V>`, enforce entry count, key policy, and value types—not `@NotBlank` alone.
15. Verify constructor binding and `setDeclarativeBinding` do not expose server-owned arguments.
16. If a JSON endpoint exists, test Jackson unknown fields and property write rules separately.
17. In the service, verify permissions from the authenticated principal/tenant, never taking `ownerId` from forms.
18. Map only permitted fields explicitly, avoiding generic property copies onto entities.
19. Write negative tests for malicious nested properties, Map keys, and huge List indices.
20. Test valid field names rejected by Bean Validation to contrast with suppression.
21. Verify outputs never echo raw inputs or leak sensitive details.
22. Re-test whenever a DTO gains a new property/setter; an allowlist fails closed if kept narrow.

## 17. Self-Practice Exercises

1. Change `setAllowedFields("labels[color]","labels[tier]")` to `"labels[*]"` and send `labels[role]`. Observe why the unexpected Map key is no longer blocked by the allowlist.
2. Add setter `Contact.setRole` to the DTO and send `contact.role=admin`. Verify the current policy still suppresses it.
3. Replace `addresses[1].city` in the allowlist with a wildcard and try a large index; compare results with `setAutoGrowCollectionLimit(4)`.
4. Disable `setAutoGrowNestedPaths` and send `contact.email` when `contact=null`. Explain the difference compared to a pre-initialized child object.
5. Remove `@Valid` from `contact` while keeping `@NotNull`; send an invalid email and explain why cascading no longer runs.
6. Remove `@NotNull` while keeping `@Valid` on `contact`, send a request omitting `contact`, and observe the outcome.
7. Remove `@Size(max=2)` from the List while keeping the index allowlist. Contrast binding limits with validation limits.
8. Check only `errors.hasErrors()` without `getSuppressedFields()`; send `approved=true` and determine what response the endpoint could return.
9. Create an immutable record accepting only `reference`, `contactEmail`, and `cities` and enable `setDeclarativeBinding(true)`; add Map key checks if a Map is included in the constructor.
10. Write a test sending raw JSON containing `approved=true` into a DTO with a setter, then replace it with a JSON DTO exposing only public input fields.
11. Add Map key `labels[tenantId]`, enforce a reserved-keys policy before persistence, and test that it cannot affect tenant state.
12. Build a service taking the authenticated principal, rejecting client-sent `ownerId`, and allowing contact-email updates only when authorized.
13. Add server-side request size/parameter count limits and test a request carrying a large number of Map keys.
14. Trigger both a validation error on an empty `Address.city` and suppression on `addresses[99].city` in one request; verify the policy prioritizes `UNEXPECTED_FIELD`.
15. Try bracketed quoted keys like `labels['color']`; test how Spring canonicalizes paths in your exact version rather than guessing.
16. Design a schema/`ProblemDetail` response for unexpected fields without reflecting unbounded client-supplied raw paths.

**Conclusion:** With form/query binding, names like `contact.email`, `labels[key]`, and `addresses[index].city` form part of your application's **input surface**. Protect them with **dedicated request DTOs**, **positive path-specific allowed fields**, **suppressed-field checks**, and **auto-grow plus request resource limits**, followed by Jakarta Validation and authorization. Never rely on a single mechanism to replace all the remaining layers.

## 18. Official Documentation

- [Spring Framework 6.2 — `@InitBinder` and Model Design](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework 6.2 — `@ModelAttribute` and Data Binding Security](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework 6.2 — Spring MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework 6.2 — `DataBinder` JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework 6.2 — `WebDataBinder` JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/bind/WebDataBinder.html)
- [Spring Framework 6.2 — `BindingResult` JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework 6.2 — `PropertyAccessorUtils` canonical names](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/PropertyAccessorUtils.html)
- [Spring Framework 6.2 — MVC `@RequestBody` (Jackson)](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Boot 3.5 — Testing web applications with MockMvc](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Jakarta Validation 3.0 — Container element validation and cascades](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)