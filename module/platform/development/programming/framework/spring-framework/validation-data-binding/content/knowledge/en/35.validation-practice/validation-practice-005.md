# Designing Forms with Nested Addresses, Lists, and Maps in Spring MVC

## 1. Objectives of This Hands-On Lesson

A delivery order form does not consist of just a few flat `String`s. It can contain:

- Customer details: `customerName`.
- **Nested address**: `address.street`, `address.city`, `address.postalCode`.
- **Recipient list**: `recipients[0].name`, `recipients[0].email`, `recipients[1].name`...
- **Preferences Map**: `preferences[language]`, `preferences[deliveryWindow]`.

The goal is to build **a real HTML form** using Spring MVC + Thymeleaf, bind it to a dedicated JavaBean DTO, handle recursive validation, receive errors on exact property paths, and restrict which fields clients are allowed to submit.

Desired outcomes:

1. `GET /delivery` renders with two initial recipient rows, an address section, and two preference options.
2. The user fills out the form or clicks **Add recipient** to add a third row.
3. `POST /delivery` binds request parameters via `@ModelAttribute("deliveryForm")`.
4. `@Valid` validates `AddressForm`, each `RecipientForm`, and the values inside the `Map`.
5. `BindingResult` records errors at paths such as `address.city` and `recipients[1].email`.
6. `@InitBinder` declares an allowlist for the exact nested paths, indexed paths, and Map keys.
7. The controller rejects out-of-contract fields (e.g., `accountRole=ADMIN` or `preferences[admin]=true`).
8. MockMvc tests the GET view, valid POST, invalid POST, dynamic row addition, and over-posting.

**Technical context:** Java 17+, Spring Boot 3.4.x, Spring Framework 6.2, Jakarta Validation, Spring MVC Servlet stack, and Thymeleaf. This is **form-urlencoded data binding**, not Jackson `@RequestBody` JSON. Differences with JSON and WebFlux are noted explicitly rather than mixing pipelines.

## 2. Designing the Object Structure Before Writing HTML

A request has the logical structure:

```text
DeliveryForm
├── customerName : String
├── address : AddressForm
│   ├── street : String
│   ├── city : String
│   └── postalCode : String
├── recipients : List<RecipientForm>
│   ├── [0]
│   │   ├── name : String
│   │   └── email : String
│   └── [1]
│       ├── name : String
│       └── email : String
└── preferences : Map<String, String>
    ├── [language]       -> "vi" or "en"
    └── [deliveryWindow] -> "day" or "evening"
```

We do not persist the entire object graph to a database in the demo. `DeliveryForm` is an **input command DTO**, not a JPA entity. This matters because web data binding can populate any property that has a setter. Binding directly to an entity with `id`, `role`, `tenantId`, or `verified` easily creates mass-assignment risk.

### 2.1. Distinguishing Dots and Square Brackets

Spring `DataBinder`/`BeanWrapper` uses property paths following JavaBeans conventions:

| Request parameter name | Target data | Meaning |
| --- | --- | --- |
| `customerName` | `form.customerName` | Top-level property |
| `address.street` | `form.address.street` | Property in nested object |
| `address.city` | `form.address.city` | String in nested object |
| `recipients[0].name` | `form.recipients.get(0).name` | Property of List element at index 0 |
| `recipients[1].email` | `form.recipients.get(1).email` | Property of List element at index 1 |
| `preferences[language]` | `form.preferences.get("language")` | Map entry with key language |
| `preferences[deliveryWindow]` | `form.preferences.get("deliveryWindow")` | Map entry with key deliveryWindow |

In an **HTTP name attribute**, you do not need quotes around a simple key: `preferences[language]`. `[0]` is a numeric **List index**; `[language]` is a **String Map key**.

Example raw payload:

```text
customerName=Lan
address.street=12 Nguyen Hue
address.city=Ho Chi Minh City
address.postalCode=70000
recipients[0].name=Lan
recipients[0].email=lan@example.org
recipients[1].name=Minh
recipients[1].email=minh@example.org
preferences[language]=vi
preferences[deliveryWindow]=day
```

The lines above represent **parameter names and values**; they are not a JSON object and do not use JSON-style nesting. HTTP form-urlencoded transmits a flat stream of parameter pairs, and the Spring binder interprets dots/brackets to construct the object graph.

### 2.2. Do Not Use HTML Names Independent of the DTO

Contract mismatch:

```html
<input name="city">
<input name="recipient.email">
<input name="language">
```

If the DTO only has `address.city`, `recipients` as a List, and `preferences` as a Map, those names do not express the target paths. Spring has no reason to guess that `city` should map to `address.city`.

Correct:

```html
<input name="address.city">
<input name="recipients[0].email">
<input name="preferences[language]">
```

To avoid typos when authoring views, use Thymeleaf's `th:object` + `th:field`. They connect HTML inputs to the form-backing object and Spring `BindingResult`, while also preserving entered values after validation fails.

## 3. How Do @ModelAttribute, WebDataBinder, and BindingResult Coordinate?

When a request arrives at the controller:

```text
Browser POST application/x-www-form-urlencoded
             |
             v
Servlet request parameters (name -> String)
             |
             v
@ModelAttribute("deliveryForm")
             |
             v
Form object retrieved from Model or newly created
             |
             v
WebDataBinder:
  - allowlist/disallowed fields
  - nested property access
  - indexed List access
  - Map[key] access
  - type conversion
             |
             v
@Valid -> Jakarta Bean Validation:
  - nested @Valid AddressForm
  - List<@Valid RecipientForm>
  - Map<String, @NotBlank String>
             |
             v
BindingResult (immediately after form argument)
             |
             +--> hasErrors(): re-render form with errors
             |
             +--> no errors: call service, render confirmation
```

Spring Framework 6.2 allows `@ModelAttribute` to use constructor binding as well as property/setter binding. This example deliberately chooses **JavaBean setters** to highlight the property paths of an HTML form.

**Note:** `BindingResult` or `Errors` must be placed **immediately after** the bound/validated argument:

```java
public String submit(
        @Valid @ModelAttribute("deliveryForm") DeliveryForm form,
        BindingResult errors,
        Model model) {
    // ...
}
```

Do not insert `Model`, `Locale`, `@RequestParam`, or another DTO between `form` and `errors`. Without a result in the proper position, validation failure can turn into `MethodArgumentNotValidException` and skip the controller's local error-handling branch.

## 4. Nested DTO Design Rules

### 4.1. Each Class Accepts Only Data Matching Its Responsibility

- `AddressForm`: address fields.
- `RecipientForm`: recipient name/email.
- `DeliveryForm`: combines those parts and the allowed preference keys.
- `DeliverySummary`: output for the confirmation page, not the entire domain entity.

Do not place `userId`, `accountRole`, or `billingLimit` from a domain entity into a form that only needs delivery details.

### 4.2. Initializing Nested Objects and Collections

With property binding, a DTO with:

```java
private AddressForm address = new AddressForm();
private List<RecipientForm> recipients = new ArrayList<>();
private Map<String, String> preferences = new LinkedHashMap<>();
```

has ready containers for the binder to access. If a nested path is null, Spring `DataBinder` can auto-grow the object graph in default mode, but you should not rely on that behavior as a business contract. Initializing in the constructor gives the GET form the structural data it needs to render and keeps tests clear.

**Do not use `List.of(...)` or `Map.of(...)` to initialize a structure that the binder must mutate.** Those factories create immutable collections/maps. Use `ArrayList` and `LinkedHashMap` for mutable forms.

### 4.3. Recursive Validation with @Valid

A `@Valid` annotation on an object field:

```java
@Valid
@NotNull
private AddressForm address;
```

instructs Jakarta Validator to descend into `AddressForm`'s constraints. Without `@Valid`, constraints on `address.street`/`address.city` may not be evaluated when validating the root `DeliveryForm`.

For a List:

```java
@NotEmpty
@Size(max = 3)
private List<@Valid RecipientForm> recipients;
```

- `@NotEmpty`: the list must have at least one element.
- `@Size(max=3)`: at most three recipients in the demo contract.
- `@Valid` on the element type: every `RecipientForm` is validated.
- `@NotBlank`/`@Email` inside `RecipientForm` produce violations with indexed paths.

For a Map:

```java
private Map<String, @NotBlank String> preferences;
```

places `@NotBlank` on the **String value** rather than on the whole Map. To require the Map itself to be non-empty, add `@NotEmpty` on the Map field. With dynamic Map keys, constraints can also be placed on the key type argument, but in the demo the key set is explicitly allowlisted on the binder, so there is no need to open up the entire key space.

**Null semantics:** constraints such as `@Email` typically treat null as valid to keep requiredness separate; combine with `@NotBlank` when the email must not be blank.

## 5. @InitBinder: Restricting Bindable Fields

If you rely solely on a DTO with setters, a client can send extra parameters not shown in HTML. Spring recommends a dedicated DTO or constructor binding; when using property binding, configure a **positive allowedFields** list.

Example:

```java
@InitBinder("deliveryForm")
void initBinder(WebDataBinder binder) {
    binder.setAllowedFields(
            "customerName",
            "address.street",
            "address.city",
            "address.postalCode",
            "recipients[*].name",
            "recipients[*].email",
            "preferences[language]",
            "preferences[deliveryWindow]"
    );
    binder.setAutoGrowCollectionLimit(3);
}
```

**Annotations:**

- `"customerName"`: a scalar field.
- `"address.city"`: only the exact allowed property; avoid overly broad `"address*"`.
- `"recipients[*].email"`: wildcard index for the List, matching `recipients[0].email`, `recipients[1].email`...
- `"preferences[language]"` and `"preferences[deliveryWindow]"`: **only the two published keys**, do not use `"preferences*"`.
- `setAutoGrowCollectionLimit(3)`: caps automatic growth of indexed collections during property binding, **not** total HTTP body/request limits.
- `@InitBinder("deliveryForm")` matches by **model attribute objectName**. If you rename `@ModelAttribute("deliveryForm")`, update the binder accordingly.
- `setAllowedFields(...)` uses **case-sensitive** patterns in Spring Framework 6.x; do not rely on case folding.

### 5.1. Why Check getSuppressedFields?

When a client sends:

```text
accountRole=ADMIN
preferences[admin]=true
```

the two keys are outside the allowlist. `DataBinder` can **suppress** them and record them in `BindingResult#getSuppressedFields()`. However, `hasErrors()` **does not automatically become true just because suppressed fields exist**.

In this lesson, the controller checks:

```java
if (result.getSuppressedFields().length > 0) {
    result.reject("unexpected.fields",
            "Form contains unsupported fields");
}
```

Turning suppressed fields into a global error is an **intentional application policy**. If an API chooses to ignore unknown fields for compatibility, the service still must not use them; never equate “ignored” with safe omission of authorization.

Do not return raw suppressed field values to the UI or unredacted logs. A stable error code or generic message is enough.

### 5.2. Be Careful with Wildcards and Large Indices

A pattern like `"recipients[*].email"` permits **the email path at any index matching the wildcard**, without proving that the index is authorized or within data-size bounds.

Combine it with:

- `@Size(max=3)` / business limits.
- `setAutoGrowCollectionLimit(3)`.
- Server-side request parameter count/body size limits.
- Early checks for abnormal indices before the binder touches them (when a public API needs a consistent 4xx contract).
- Validation rules on element IDs when updating existing records.

An index exceeding the auto-grow limit can trigger a binding exception in infrastructure, **not automatically turning into a readable FieldError**. Do not promise that every `recipients[999999]` payload will always return a 400 validation response. Test the behavior on your actual Spring version and guard requests early.

### 5.3. Constructor Binding and @RequestBody Have Different Scopes

`setAllowedFields` governs **property/setter binding**. It is not a general filter for constructor arguments or JSON keys deserialized by Jackson via `@RequestBody`. If converting form-urlencoded to JSON REST, use a dedicated input DTO/record, configure Jackson's unknown-property policy as needed, and test the JSON pipeline.

Spring 6.2 provides `setDeclarativeBinding(true)` to favor constructor binding and allow property binding only when allowed fields are configured. This is worth considering when standardizing multiple forms, though regression tests are needed, especially for nested lists and Maps.

## 6. Java 17 Project: Complete Thymeleaf Form

### 6.1. Directory Structure

```text
nested-form-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── NestedFormApplication.java
    │   │   ├── AddressForm.java
    │   │   ├── RecipientForm.java
    │   │   ├── DeliveryForm.java
    │   │   ├── DeliverySummary.java
    │   │   ├── DeliveryService.java
    │   │   └── DeliveryController.java
    │   └── resources/templates/
    │       ├── delivery-form.html
    │       └── delivery-success.html
    └── test/java/demo/
        ├── DeliveryBinderTest.java
        └── DeliveryMvcTest.java
```

The project intentionally uses a real template engine so you can inspect the exact rendered field names. No database is needed; `DeliveryService` simply returns a summary. In production, data storage, authentication/authorization, and persistence invariants must be designed as well.

### 6.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>nested-form-demo</artifactId>
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
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
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

The Boot parent manages Spring MVC and Thymeleaf versions, preventing manual mismatched version configurations. `spring-boot-starter-validation` provides the Jakarta Bean Validation provider, typically Hibernate Validator.

### 6.3. src/main/java/demo/NestedFormApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class NestedFormApplication {
    public static void main(String[] args) {
        SpringApplication.run(NestedFormApplication.class, args);
    }
}
```

### 6.4. src/main/java/demo/AddressForm.java

```java
package demo;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public class AddressForm {

    @NotBlank
    @Size(max = 120)
    private String street;

    @NotBlank
    @Size(max = 80)
    private String city;

    // Pattern illustrating simple postal codes;
    // production must enforce country-specific policies.
    @NotBlank
    @Pattern(regexp = "[A-Za-z0-9 -]{3,12}")
    private String postalCode;

    public String getStreet() {
        return street;
    }

    public void setStreet(String street) {
        this.street = street;
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }

    public String getPostalCode() {
        return postalCode;
    }

    public void setPostalCode(String postalCode) {
        this.postalCode = postalCode;
    }
}
```

**Explanation:** `AddressForm` is a nested bean with an implicit public no-arg constructor and public getters/setters. `@NotBlank` prevents null/empty/blank values; `@Size` limits length; `@Pattern` is merely a lesson policy, not a global postal validator.

When a user leaves the city blank, validation produces an error on path `address.city` because the root `DeliveryForm` has `@Valid` on `address`.

### 6.5. src/main/java/demo/RecipientForm.java

```java
package demo;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class RecipientForm {

    @NotBlank
    @Size(max = 80)
    private String name;

    @NotBlank
    @Email
    @Size(max = 254)
    private String email;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
```

Each entry in the List is a complete `RecipientForm`. Validation on `email` executes because the root form cascades `@Valid` to the element. `@Email` only checks format per the provider; it does not prove the email is verified or that the recipient consented.

### 6.6. src/main/java/demo/DeliveryForm.java

```java
package demo;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public class DeliveryForm {

    @NotBlank
    @Size(max = 80)
    private String customerName;

    @Valid
    @NotNull
    private AddressForm address = new AddressForm();

    @NotEmpty
    @Size(max = 3)
    private List<@Valid RecipientForm> recipients =
            new ArrayList<>();

    @NotEmpty
    private Map<String, @NotBlank String> preferences =
            new LinkedHashMap<>();

    public DeliveryForm() {
        // Pre-populate 2 recipient rows on GET /delivery.
        recipients.add(new RecipientForm());
        recipients.add(new RecipientForm());

        // Initialize and render the two valid keys.
        preferences.put("language", "vi");
        preferences.put("deliveryWindow", "day");
    }

    public String getCustomerName() {
        return customerName;
    }

    public void setCustomerName(String customerName) {
        this.customerName = customerName;
    }

    public AddressForm getAddress() {
        return address;
    }

    public void setAddress(AddressForm address) {
        this.address = address;
    }

    public List<RecipientForm> getRecipients() {
        return recipients;
    }

    public void setRecipients(List<RecipientForm> recipients) {
        this.recipients = recipients;
    }

    public Map<String, String> getPreferences() {
        return preferences;
    }

    public void setPreferences(
            Map<String, String> preferences) {
        this.preferences = preferences;
    }
}
```

**Analyzing design decisions:**

1. `address` is initialized immediately instead of waiting for the binder to create it because it is required form data.
2. `recipients` is a mutable `ArrayList` pre-populated with 2 entries. That lets Thymeleaf render two rows with paths `recipients[0].name`, `recipients[1].name`.
3. `@NotEmpty @Size(max=3)` expresses the 1–3 recipients limit, reinforced at the binder.
4. `List<@Valid RecipientForm>` makes the provider validate each element.
5. `preferences` is a mutable `LinkedHashMap` with two fixed keys. `LinkedHashMap` preserves insertion order for rendering; it has no special security role of its own.
6. `Map<String, @NotBlank String>` demonstrates **container-element constraints** for map values. Unexpected values like `language=javascript` are not blocked by `@NotBlank` alone since that is a non-blank string; the controller checks the valid value set.
7. Uses JavaBean getters/setters so the property binder works. Switching to record constructor binding requires redesigning List/Map initialization and understanding differences around `allowedFields`.

**Point to remember:** when a user submits the form omitting a field (e.g., `preferences[language]`), the model factory defaults to `vi` and the binder may retain that value. This is **intentional defaulting semantics** in the demo. In APIs that must distinguish missing fields from explicit nulls or require the client to choose an option, create a new DTO without auto-populated defaults and use appropriate validation/tri-state types.

### 6.7. src/main/java/demo/DeliverySummary.java

```java
package demo;

public record DeliverySummary(
        String customerName,
        String city,
        int recipientCount,
        String language,
        String deliveryWindow) {
}
```

The output DTO includes only the necessary summary, without exposing full recipient addresses/emails on the confirmation page. A real system needs dedicated policies on what data may be viewed and stored.

### 6.8. src/main/java/demo/DeliveryService.java

```java
package demo;

import org.springframework.stereotype.Service;

@Service
public class DeliveryService {

    public DeliverySummary review(DeliveryForm form) {
        // Do not create JPA entities or write to a database
        // in a lesson focused on data binding.
        return new DeliverySummary(
                form.getCustomerName().strip(),
                form.getAddress().getCity().strip(),
                form.getRecipients().size(),
                form.getPreferences().get("language"),
                form.getPreferences().get("deliveryWindow")
        );
    }
}
```

The service performs only a projection after the controller confirms the form is valid. In applications with multiple entry points beyond HTTP, **never assume the service only receives DTOs already checked by `@Valid`**. Enforce domain/business validation at the service boundary when rules matter; authentication, authorization, and persistence are separate layers.

### 6.9. src/main/java/demo/DeliveryController.java

```java
package demo;

import java.util.Set;

import jakarta.validation.Valid;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;

@Controller
@RequestMapping("/delivery")
public class DeliveryController {

    private static final Set<String> LANGUAGES =
            Set.of("vi", "en");

    private static final Set<String> WINDOWS =
            Set.of("day", "evening");

    private final DeliveryService service;

    public DeliveryController(DeliveryService service) {
        this.service = service;
    }

    // Invoked by Spring to prepare the model for both GET and POST.
    @ModelAttribute("deliveryForm")
    public DeliveryForm createForm() {
        return new DeliveryForm();
    }

    @InitBinder("deliveryForm")
    public void configureBinder(WebDataBinder binder) {
        binder.setAllowedFields(
                "customerName",
                "address.street",
                "address.city",
                "address.postalCode",
                "recipients[*].name",
                "recipients[*].email",
                "preferences[language]",
                "preferences[deliveryWindow]"
        );
        binder.setAutoGrowCollectionLimit(3);
    }

    @GetMapping
    public String showForm() {
        return "delivery-form";
    }

    // POST /delivery/add: same form input,
    // skip validating empty fields when the user
    // only wants to add another recipient row.
    @PostMapping("/add")
    public String addRecipient(
            @ModelAttribute("deliveryForm") DeliveryForm form,
            BindingResult errors) {

        if (errors.getSuppressedFields().length > 0) {
            errors.reject("unexpected.fields",
                    "Biểu mẫu có trường không được phép");
        }

        if (errors.hasErrors()) {
            return "delivery-form";
        }

        if (form.getRecipients().size() < 3) {
            form.getRecipients().add(new RecipientForm());
        }

        return "delivery-form";
    }

    // POST /delivery: validate the entire object graph.
    @PostMapping
    public String submit(
            @Valid @ModelAttribute("deliveryForm") DeliveryForm form,
            BindingResult errors,
            Model model) {

        if (errors.getSuppressedFields().length > 0) {
            errors.reject("unexpected.fields",
                    "Biểu mẫu có trường không được phép");
        }

        String language =
                form.getPreferences().get("language");
        if (!LANGUAGES.contains(language)) {
            errors.rejectValue(
                    "preferences[language]",
                    "invalid.language",
                    "Ngôn ngữ không hợp lệ");
        }

        String window =
                form.getPreferences().get("deliveryWindow");
        if (!WINDOWS.contains(window)) {
            errors.rejectValue(
                    "preferences[deliveryWindow]",
                    "invalid.deliveryWindow",
                    "Khung giao hàng không hợp lệ");
        }

        if (errors.hasErrors()) {
            return "delivery-form";
        }

        model.addAttribute(
                "summary",
                service.review(form));

        return "delivery-success";
    }
}
```

**Controller design notes:**

- Uses `@Controller` because it returns HTML views, not `@RestController` for template names.
- `@ModelAttribute("deliveryForm")` provides a fresh object pre-initialized with address/List/Map for GET and POST.
- `@InitBinder("deliveryForm")` matches the exact `objectName`. Only allow required paths.
- `@PostMapping("/add")` separates adding a row from submitting, **without passing a button parameter name into the binder**, so the action is not mistaken for a suppressed field.
- When adding a row, **omit `@Valid`** on the add handler: the user has not finished the form yet; still keep `BindingResult` for binding/conversion errors.
- `@PostMapping` triggers `@Valid`. `BindingResult` immediately after the form is required by Spring MVC.
- `getSuppressedFields()` does not automatically create a `FieldError`, so the controller explicitly calls `reject(...)` so the form is not accepted when the client sends disallowed fields.
- `LANGUAGES` and `WINDOWS` enforce allowed **values**, complementing the binder's allowed **field names**. `@NotBlank` alone cannot block a string like `hacker`.
- `rejectValue("preferences[language]",...)` creates a field error for the Map value; if the key is missing while the form has a default, `Set.contains` still checks the existing value.
- The service is called only when there are no errors; the demo **does not persist data**.

**Production concerns:** the controller lacks authentication/authorization, CSRF configuration, transactions, or auditing. If updating a real logged-in user's address, the service must determine the actor and target resource. Never submit `accountId`/`role` from a form and trust them as user privileges.

### 6.10. src/main/resources/templates/delivery-form.html

```html
<!doctype html>
<html lang="vi"
      xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Đăng ký giao hàng</title>
</head>
<body>
<h1>Thông tin giao hàng</h1>

<form th:action="@{/delivery}"
      th:object="${deliveryForm}"
      method="post">

    <div role="alert" th:if="${#fields.hasAnyErrors()}">
        Biểu mẫu có lỗi. Vui lòng kiểm tra lại dữ liệu.
    </div>

    <section>
        <h2>Người đặt</h2>
        <label for="customerName">Họ tên</label>
        <input type="text"
               th:field="*{customerName}">
        <span th:if="${#fields.hasErrors('customerName')}"
              th:errors="*{customerName}">Lỗi họ tên</span>
    </section>

    <section>
        <h2>Địa chỉ giao hàng</h2>

        <label for="address.street">Đường</label>
        <input type="text"
               th:field="*{address.street}">

        <label for="address.city">Thành phố</label>
        <input type="text"
               th:field="*{address.city}">
        <span th:if="${#fields.hasErrors('address.city')}"
              th:errors="*{address.city}">Lỗi thành phố</span>

        <label for="address.postalCode">Mã bưu chính</label>
        <input type="text"
               th:field="*{address.postalCode}">
    </section>

    <section>
        <h2>Danh sách người nhận (tối đa 3)</h2>

        <div th:each="recipient, stat : *{recipients}">
            <h3 th:text="'Người nhận ' + ${stat.count}">
                Người nhận
            </h3>

            <label>Họ tên</label>
            <input type="text"
                   th:field="*{recipients[__${stat.index}__].name}">

            <label>Email</label>
            <input type="email"
                   th:field="*{recipients[__${stat.index}__].email}">

            <span th:if="${#fields.hasErrors(
                      'recipients[' + stat.index + '].email')}"
                  th:errors="*{recipients[__${stat.index}__].email}">
                Email không hợp lệ
            </span>
        </div>

        <button type="submit"
                th:formaction="@{/delivery/add}">
            Thêm người nhận
        </button>
    </section>

    <section>
        <h2>Tùy chọn</h2>

        <label>Ngôn ngữ</label>
        <select th:field="*{preferences[language]}">
            <option value="vi">Tiếng Việt</option>
            <option value="en">English</option>
        </select>

        <label>Khung giờ giao hàng</label>
        <select th:field="*{preferences[deliveryWindow]}">
            <option value="day">Ban ngày</option>
            <option value="evening">Buổi tối</option>
        </select>
    </section>

    <button type="submit">Xác nhận</button>
</form>
</body>
</html>
```

**Template explanation:**

1. `th:object="${deliveryForm}"` (written in actual HTML as a Thymeleaf expression with a dollar sign) selects the **form-backing object**.
2. `th:field="*{address.city}"` generates `name="address.city"` while also reading the value through Spring's binding infrastructure.
3. `th:each="recipient, stat : *{recipients}"` iterates the List with a 0-based `stat.index`.
4. `__${stat.index}__` is **Thymeleaf expression preprocessing**. It substitutes the actual index into the property path before Spring evaluates it. For row index 1, `*{recipients[__${stat.index}__].email}` becomes `*{recipients[1].email}`.
5. `th:field="*{preferences[language]}"` uses the Map key `language`. The submitted field name is `preferences[language]`.
6. The Add button uses `formaction="/delivery/add"` via `th:formaction`; regular submit posts to `/delivery`.
7. `#fields.hasAnyErrors()` displays the banner whenever any field/global error exists in the form's `BindingResult`.
8. `th:errors` displays messages for the corresponding fields, including nested/indexed paths.

**Copy-paste note:** in the saved Markdown, every dollar sign above is a literal dollar sign; no placeholder replacement is needed. The template expressions are HTML/Thymeleaf syntax, not JavaScript template literals.

### 6.11. src/main/resources/templates/delivery-success.html

```html
<!doctype html>
<html lang="vi"
      xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Thông tin đã được kiểm tra</title>
</head>
<body>
<h1>Biểu mẫu hợp lệ</h1>
<p>Người đặt: <strong th:text="${summary.customerName}">Tên</strong></p>
<p>Thành phố: <span th:text="${summary.city}">Thành phố</span></p>
<p>Số người nhận:
    <span th:text="${summary.recipientCount}">0</span>
</p>
<p>Ngôn ngữ: <span th:text="${summary.language}">vi</span></p>
<p>Khung giao:
    <span th:text="${summary.deliveryWindow}">day</span>
</p>
<a th:href="@{/delivery}">Tạo biểu mẫu khác</a>
</body>
</html>
```

This page uses `th:text`, so strings are HTML-escaped. Never use `th:utext` to output raw user input. This is a post-validation confirmation page, **not a claim of database persistence**.

## 7. Testing DataBinder Directly: Proving Property Paths

Beyond MockMvc, you can use `DataBinder` from Spring Core to verify exactly how nested/List/Map property paths are resolved. This test does not need to start a server.

### 7.1. src/test/java/demo/DeliveryBinderTest.java

```java
package demo;

import java.util.LinkedHashMap;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.DataBinder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DeliveryBinderTest {

    private DataBinder newBinder(DeliveryForm form) {
        DataBinder binder =
                new DataBinder(form, "deliveryForm");

        binder.setAllowedFields(
                "customerName",
                "address.street",
                "address.city",
                "address.postalCode",
                "recipients[*].name",
                "recipients[*].email",
                "preferences[language]",
                "preferences[deliveryWindow]"
        );
        binder.setAutoGrowCollectionLimit(3);
        return binder;
    }

    @Test
    void nestedListAndMapPathsReachTheirTargets() {
        DeliveryForm form = new DeliveryForm();
        DataBinder binder = newBinder(form);

        Map<String, String> params = new LinkedHashMap<>();
        params.put("customerName", "Lan");
        params.put("address.city", "Da Nang");
        params.put("recipients[1].name", "Minh");
        params.put("recipients[1].email",
                "minh@example.org");
        params.put("preferences[language]", "en");

        binder.bind(new MutablePropertyValues(params));

        assertEquals("Lan", form.getCustomerName());
        assertEquals("Da Nang",
                form.getAddress().getCity());
        assertEquals("Minh",
                form.getRecipients().get(1).getName());
        assertEquals("minh@example.org",
                form.getRecipients().get(1).getEmail());
        assertEquals("en",
                form.getPreferences().get("language"));
        assertTrue(binder.getBindingResult()
                .getSuppressedFields().length == 0);
    }

    @Test
    void unlistedMapKeyIsSuppressed() {
        DeliveryForm form = new DeliveryForm();
        DataBinder binder = newBinder(form);

        Map<String, String> params = new LinkedHashMap<>();
        params.put("preferences[language]", "en");
        params.put("preferences[admin]", "true");
        params.put("accountRole", "ADMIN");

        binder.bind(new MutablePropertyValues(params));

        assertEquals("en",
                form.getPreferences().get("language"));
        assertTrue(!form.getPreferences()
                .containsKey("admin"));
        assertEquals(2, binder.getBindingResult()
                .getSuppressedFields().length);
    }
}
```

**QA note:** this is a pure binder test verifying only paths and the allowlist. It **does not run Jakarta Bean Validation** because no validator is invoked, does not prove Thymeleaf renders the field names, and cannot replace MockMvc integration tests. However, it is very useful when suspecting a wrong property path or Map key.

## 8. MockMvc Integration Tests: Real Form and Error Handling

### 8.1. src/test/java/demo/DeliveryMvcTest.java

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

@SpringBootTest
@AutoConfigureMockMvc
class DeliveryMvcTest {

    @Autowired
    MockMvc mvc;

    private MockHttpServletRequestBuilder validForm(String path) {
        return post(path)
                .contentType(
                        MediaType.APPLICATION_FORM_URLENCODED)
                .param("customerName", "Lan")
                .param("address.street", "12 Nguyen Hue")
                .param("address.city", "Da Nang")
                .param("address.postalCode", "55000")
                .param("recipients[0].name", "Lan")
                .param("recipients[0].email",
                        "lan@example.org")
                .param("recipients[1].name", "Minh")
                .param("recipients[1].email",
                        "minh@example.org")
                .param("preferences[language]", "vi")
                .param("preferences[deliveryWindow]", "day");
    }

    @Test
    void getRendersNestedListAndMapNames() throws Exception {
        mvc.perform(get("/delivery"))
                .andExpect(status().isOk())
                .andExpect(view().name("delivery-form"))
                .andExpect(content().string(
                        containsString("name=\"address.city\"")))
                .andExpect(content().string(
                        containsString("name=\"recipients[0].name\"")))
                .andExpect(content().string(
                        containsString("name=\"recipients[1].email\"")))
                .andExpect(content().string(
                        containsString("name=\"preferences[language]\"")));
    }

    @Test
    void validNestedFormProducesSummary() throws Exception {
        mvc.perform(validForm("/delivery"))
                .andExpect(status().isOk())
                .andExpect(view().name("delivery-success"))
                .andExpect(model().attributeExists("summary"))
                .andExpect(content().string(
                        containsString("Da Nang")))
                .andExpect(content().string(
                        containsString("Số người nhận")));
    }

    @Test
    void blankNestedCityProducesFieldError()
            throws Exception {
        mvc.perform(validForm("/delivery")
                        .param("address.city", ""))
                .andExpect(status().isOk())
                .andExpect(view().name("delivery-form"))
                .andExpect(model().attributeHasFieldErrors(
                        "deliveryForm", "address.city"));
    }

    @Test
    void invalidSecondRecipientEmailHasIndexedPath()
            throws Exception {
        mvc.perform(validForm("/delivery")
                        .param("recipients[1].email",
                                "not-an-email"))
                .andExpect(view().name("delivery-form"))
                .andExpect(model().attributeHasFieldErrors(
                        "deliveryForm",
                        "recipients[1].email"));
    }

    @Test
    void blankRecipientNameIsValidatedByCascade()
            throws Exception {
        mvc.perform(validForm("/delivery")
                        .param("recipients[0].name", ""))
                .andExpect(view().name("delivery-form"))
                .andExpect(model().attributeHasFieldErrors(
                        "deliveryForm",
                        "recipients[0].name"));
    }

    @Test
    void disallowedRoleIsRejected() throws Exception {
        mvc.perform(validForm("/delivery")
                        .param("accountRole", "ADMIN"))
                .andExpect(status().isOk())
                .andExpect(view().name("delivery-form"))
                .andExpect(model().attributeHasErrors(
                        "deliveryForm"));
    }

    @Test
    void unknownPreferenceKeyIsRejected() throws Exception {
        mvc.perform(validForm("/delivery")
                        .param("preferences[admin]", "true"))
                .andExpect(view().name("delivery-form"))
                .andExpect(model().attributeHasErrors(
                        "deliveryForm"));
    }

    @Test
    void invalidPreferenceValueIsRejected() throws Exception {
        mvc.perform(validForm("/delivery")
                        .param("preferences[language]",
                                "invalid"))
                .andExpect(view().name("delivery-form"))
                .andExpect(model().attributeHasFieldErrors(
                        "deliveryForm",
                        "preferences[language]"));
    }

    @Test
    void addRecipientRendersThirdRow() throws Exception {
        mvc.perform(validForm("/delivery/add"))
                .andExpect(status().isOk())
                .andExpect(view().name("delivery-form"))
                .andExpect(content().string(
                        containsString(
                                "name=\"recipients[2].email\"")));
    }

    @Test
    void threeRecipientsCanBeSubmitted()
            throws Exception {
        mvc.perform(validForm("/delivery")
                        .param("recipients[2].name", "An")
                        .param("recipients[2].email",
                                "an@example.org"))
                .andExpect(view().name("delivery-success"))
                .andExpect(content().string(
                        containsString("Số người nhận")))
                .andExpect(model().attribute(
                        "summary",
                        new DeliverySummary(
                                "Lan", "Da Nang", 3,
                                "vi", "day")));
    }

    @Test
    void missingCustomerNameProducesFieldError()
            throws Exception {
        mvc.perform(post("/delivery")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("address.street",
                                "12 Nguyen Hue")
                        .param("address.city", "Da Nang")
                        .param("address.postalCode", "55000")
                        .param("recipients[0].name", "Lan")
                        .param("recipients[0].email",
                                "lan@example.org")
                        .param("recipients[1].name", "Minh")
                        .param("recipients[1].email",
                                "minh@example.org"))
                .andExpect(view().name("delivery-form"))
                .andExpect(model().attributeHasFieldErrors(
                        "deliveryForm", "customerName"));
    }
}
```

The **11 integration tests** above check each layer:

| Group | Test | What to observe |
| --- | --- | --- |
| Rendering | GET form | HTML contains exact nested, indexed, and Map `name` attributes |
| Happy path | Valid POST | Confirmation page and accurate summary |
| Nested validation | Blank city | `address.city` has FieldError |
| List element validation | Second email invalid | `recipients[1].email` has FieldError |
| List element validation | First name blank | `recipients[0].name` has FieldError |
| Binding security | Unknown `accountRole` field | Form rejected; does not reach success |
| Map key security | `preferences[admin]` | Out-of-allowlist key rejected |
| Map value rules | `language=invalid` | FieldError on Map entry |
| Dynamic row | POST /delivery/add | Renders List row index 2 |
| Dynamic row | POST with index 2 | Summary has three recipients |
| Required field | `customerName` omitted | FieldError from `@NotBlank` |

**Note when reading tests:** because this is an HTML form, the controller returns the error template with **HTTP 200** (a common pattern for server-rendered forms). REST APIs may choose 400/422. Do not interpret status 200 as “input accepted” if the response is the form with `BindingResult` errors. In the demo, `delivery-success` is the accepted branch.

### 8.2. Why Is MockMvc More Important Than Unit-Testing Setters Alone?

If you call:

```java
DeliveryForm form = new DeliveryForm();
form.getAddress().setCity("Da Nang");
```

you only prove that Java setters work. You have **not proved** that the request name `address.city` is bound by Spring, Thymeleaf renders the indexed fields properly, `@InitBinder` matches the right `objectName`, or nested `@Valid` runs.

`MockMvc` uses real Spring MVC infrastructure (with `@SpringBootTest`) to test the entire pipeline from request parameters to controller and view. Use `DataBinder` unit tests for property path mechanics, and MockMvc to prove integration.

## 9. Running the Project and Trying in a Browser

### 9.1. Running Tests

Requires JDK 17+ and Maven:

```bash
mvn -q clean test
```

**Expected per sample code:** 2 DataBinder unit tests + 11 MockMvc integration tests = **13 tests**. With matching Maven dependencies and environment, tests are expected to pass with Maven exit code 0. This is an **expected outcome from the code**, not a build executed/observed during authoring; run CI to verify in practice.

### 9.2. Starting the Server

```bash
mvn spring-boot:run
```

Open:

```text
http://localhost:8080/delivery
```

You will see a form with customer, address, two recipients, and two preferences. Clicking **Thêm người nhận** (Add recipient) once adds a third row. Clicking **Xác nhận** (Confirm) after entering valid data shows the summary page with customer, city, recipient count, and the two preferences.

### 9.3. Testing form-urlencoded with curl

```bash
curl -i -X POST \
  'http://localhost:8080/delivery' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'customerName=Lan' \
  --data-urlencode 'address.street=12 Nguyen Hue' \
  --data-urlencode 'address.city=Da Nang' \
  --data-urlencode 'address.postalCode=55000' \
  --data-urlencode 'recipients[0].name=Lan' \
  --data-urlencode 'recipients[0].email=lan@example.org' \
  --data-urlencode 'recipients[1].name=Minh' \
  --data-urlencode 'recipients[1].email=minh@example.org' \
  --data-urlencode 'preferences[language]=vi' \
  --data-urlencode 'preferences[deliveryWindow]=day'
```

The response is an **HTML document**, not JSON; the demo uses response status 200. The page displays `Biểu mẫu hợp lệ` and recipient count 2 when all constraints/rules are satisfied.

Try injecting a field:

```bash
curl -i -X POST \
  'http://localhost:8080/delivery' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'customerName=Lan' \
  --data-urlencode 'address.street=12 Nguyen Hue' \
  --data-urlencode 'address.city=Da Nang' \
  --data-urlencode 'address.postalCode=55000' \
  --data-urlencode 'recipients[0].name=Lan' \
  --data-urlencode 'recipients[0].email=lan@example.org' \
  --data-urlencode 'recipients[1].name=Minh' \
  --data-urlencode 'recipients[1].email=minh@example.org' \
  --data-urlencode 'preferences[language]=vi' \
  --data-urlencode 'preferences[deliveryWindow]=day' \
  --data-urlencode 'accountRole=ADMIN'
```

Expected: the controller detects the suppressed field, adds a global error, and returns `delivery-form` instead of the success page. The lesson protects **property binding**, not complete authorization for an application.

## 10. Adding and Removing List Rows: Handling Indices Properly

### 10.1. Why Do Dynamic Forms Use Indices Instead of DOM IDs?

Spring property binding reads `name="recipients[1].email"`, ignoring whether an input has id `recipient-email-2`. HTML `id` is for CSS, accessibility, and labels; **`name` determines request parameter binding**.

When iterating:

```html
<div th:each="r, s : *{recipients}">
    <input th:field="*{recipients[__${s.index}__].name}">
    <input th:field="*{recipients[__${s.index}__].email}">
</div>
```

Thymeleaf preprocessing turns `s.index` into a literal index before the Spring field expression is evaluated. Do not write `*{recipients[s.index].email}` expecting Spring EL to resolve `s.index` inside brackets; they are not equivalent.

### 10.2. An Add-Row Handler Should Not Require Completing Every Field First

The `POST /delivery/add` handler in the demo **does not use `@Valid`**, because the user may still be partway through filling out the form. It still binds current values so entered data is not lost when rendering the new row.

The final submit route applies `@Valid` and validates the entire object graph.

**Caution:** when adding without validation, temporarily invalid data may be re-rendered; that is acceptable for form UX, but it must never be persisted or sent downstream as a validated command.

### 10.3. Deleting a Row: Must Re-Index

Example 3-element List:

```text
recipients[0] = Lan
recipients[1] = Minh
recipients[2] = An
```

After deleting index 1, the List holds Lan and An; when re-rendered, the names must be:

```text
recipients[0].name = Lan
recipients[1].name = An
```

If HTML still submits `recipients[2].name` without index 1, Spring may auto-grow an empty element in between, causing validation errors or logic bugs. The demo intentionally **omits a delete button** to keep the runnable example concise and avoid mixing in session state. When adding deletion, manipulate the list on the server and re-render from the List with sequential indices; never merely hide a row with CSS.

### 10.4. Indices Are Not Business IDs

When updating recipients stored in a DB, never assume `recipients[0]` corresponds to an old database row ID. A form index is only the **render/submit position**; it shifts when adding, deleting, or sorting. Use a stable identifier whose ownership is checked by the server, or a command with explicit add/update/remove operations. Never bind directly to a JPA entity graph allowing clients to edit `recipients[0].id` arbitrarily.

## 11. Map Field Names and Key Security

### 11.1. Fixed Keys

In this lesson, only these are accepted:

```text
preferences[language]
preferences[deliveryWindow]
```

They are two configuration fields with distinct semantics:

- `language`: one of `vi`, `en`.
- `deliveryWindow`: one of `day`, `evening`.

`@NotBlank` on Map values only forbids blank strings, not invalid values. That is why the controller adds allowlists for **values**.

### 11.2. Dynamic Keys

If a product allows arbitrary Map keys, you must decide:

- Allowed character set and maximum key length.
- Whether keys are case-sensitive.
- How to handle keys containing dots, brackets, spaces, and special characters.
- Depth/nested paths for `Map<String,SomeObject>`.
- Maximum number of keys and map growth cost.
- Actor permissions for each Map entry.
- Handling collisions, duplicate parameters, and canonicalization.

Never use `binder.setAllowedFields("preferences*")` just because “the Map has dynamic keys”; a wildcard can expose more property paths than intended. If Map keys cannot be constrained by a clear pattern, consider another request DTO such as `List<PreferenceEntry>` with `key`/`value` and a validator, letting the service build the Map after checking duplicates and business rules.

### 11.3. Keys Containing Dots or Brackets

A name like `preferences[user.news]` may be parsed by Spring's property path parser differently from `preferences[user].news`; dots **inside brackets** denote the key, whereas dots outside brackets traverse nested properties. However, arbitrary key names with special syntax characters must be properly encoded/canonicalized and tested against the actual binder.

Recommendation for public HTML forms: use simple keys (letters/digits/_/-), allowlist them, and avoid dynamic arbitrary property paths unless genuinely needed.

### 11.4. Input Maps Are Not Storage Objects

Do not do:

```java
for (var entry : form.getPreferences().entrySet()) {
    entity.setProperty(entry.getKey(), entry.getValue());
}
```

This is an **anti-pattern fragment**, not runnable code. A Map from HTTP must never turn directly into entity property updates. In the service, map only known keys explicitly, verify the actor, and preserve domain invariants.

## 12. Reading BindingResult When Nested Errors Occur

A `BindingResult` can contain:

```text
address.street
address.city
recipients[0].name
recipients[1].email
preferences[language]
preferences[deliveryWindow]
```

The actual path of **container-element violations** in a Map may include node names like `<map value>` depending on how the adapter/provider renders `Path.Node`. Therefore, do not try to parse error paths with `split(".")` or assume every Map violation matches a single literal field name.

Basic handling example:

```java
for (FieldError error : result.getFieldErrors()) {
    String field = error.getField();
    boolean conversionFailure = error.isBindingFailure();
    String code = error.getCode();
}
```

This is a fragment requiring `import org.springframework.validation.FieldError` and an existing `BindingResult result`. Classification:

- `isBindingFailure()==true`: type conversion or binding error.
- Constraint error: Jakarta/Spring validation (e.g., `@NotBlank`).
- `getGlobalErrors()`: object-wide errors, possibly added via `result.reject(...)` for suppressed fields.
- `getSuppressedFields()`: field names blocked during property binding; **not automatically included in `getFieldErrors()`**.

With Thymeleaf, you can use:

```html
<span th:if="${#fields.hasErrors('address.city')}"
      th:errors="*{address.city}">
    City error
</span>
```

For Lists:

```html
<span th:errors="*{recipients[__${stat.index}__].email}">
    Email error
</span>
```

In a JSON API, convert `FieldError`s into a **stable error schema**. For HTML forms, `th:errors` and `#fields` display errors next to fields, while still keeping a general banner for global errors.

## 13. Common Errors and Fixes

### 13.1. Null Nested Address Causes Binding Exception

**Symptom:** `address.city` fails to bind because `address` is null or lacks a setter/no-arg constructor.

**Fix:** initialize `address = new AddressForm()` in the input DTO; verify standard JavaBeans getters/setters and `WebDataBinder` property access. Do not expect Spring to instantiate arbitrary custom immutable nested value objects without an appropriate constructor/converter.

### 13.2. List Renders Properly, but POST Fails to Bind

**Symptom:** HTML input has `id="recipient0.email"` but lacks `name="recipients[0].email"`.

**Fix:** use `th:field="*{recipients[__${stat.index}__].email}"` or write the exact `name`. Inspect the actual DOM and network request rather than relying only on visible IDs.

### 13.3. Using List.of or Map.of to Pre-Populate a Mutable Form

**Symptom:** `UnsupportedOperationException` or inability to mutate indexed elements.

**Fix:** use `ArrayList`/`LinkedHashMap` for editable forms. Immutable collections may suit outputs/domain models, not mutable structures for property binding.

### 13.4. Forgetting @Valid on Nested Objects or Elements

**Symptom:** `customerName` is validated, but `address.city` and `recipients[1].email` produce no errors.

**Fix:** add `@Valid` on `address` and on List elements `List<@Valid RecipientForm>`, along with constraints on the child classes.

### 13.5. Placing @NotBlank Directly on List or Map

**Symptom:** `UnexpectedTypeException` because `@NotBlank` requires a `CharSequence`-compatible type.

**Fix:** use `@NotEmpty` or `@Size` on the collection/map, and `@NotBlank` on String elements/values.

### 13.6. @Size(max=3) Still Accepts Very Large Indices

**Symptom:** the binder encounters `recipients[999999]` before `@Size` ever runs.

**Fix:** use `setAutoGrowCollectionLimit`, request parameter count limits, input prefiltering, and tests for out-of-range paths. `@Size` checks an already-bound object; it is not a firewall stopping the binder from allocating oversized objects.

### 13.7. Missing HTML Checkbox Does Not Mean False

An unchecked checkbox typically **omits its key**. If a Map value is Boolean, omitting the parameter can retain the old/default value or require field-marker support. Spring `WebDataBinder` has field marker/default prefixes; Thymeleaf `th:field` for checkboxes can emit hidden markers.

The demo uses **select dropdowns with String values** for both preferences to avoid checkbox pitfalls. When adding checkboxes to a nested Map, test checked, unchecked, and missing-marker cases, and restrict allowed keys. Never assume `false` appears automatically from an unchecked HTML checkbox.

### 13.8. Map Value Error Does Not Show Beside Select

**Symptom:** the global banner appears, but `th:errors="*{preferences[language]}"` does not match a violation path containing a container node.

**Fix:** inspect actual `BindingResult#getFieldErrors()` and paths. Use a banner/summary for Map constraints or call custom `rejectValue` with an explicit property path; do not assume Hibernate Validator always formats the exact same key across versions.

### 13.9. @InitBinder Does Not Run

**Symptom:** `getSuppressedFields()` is empty even when unknown properties are sent.

**Fix:** check the binder `objectName`: `@InitBinder("deliveryForm")` and `@ModelAttribute("deliveryForm")` must match. Check controller/advice scope and whether the request actually uses property binding.

### 13.10. Extra Form Button Name Causes Allowlist Rejection

If a submit button has `name="submit"` while the binder allows only business fields, `submit` may be treated as an unknown property and suppressed. The demo separates row addition to `/delivery/add` and uses **nameless** buttons. In applications with multiple action buttons via request parameters, design routing, parameter preprocessing, or intentional allowlists; avoid accidentally accepting action flags as business fields.

### 13.11. Using @RequestBody JSON and Expecting setAllowedFields to Protect It

`@RequestBody` is deserialized by an HTTP message converter, not the form property-binding pipeline. Use task-specific records/DTOs and test Jackson unknown fields separately. Do not treat form-urlencoded tests as security proof for JSON endpoints.

### 13.12. Mixing Up List Indices with Database IDs

`recipients[0]` is a position, not a persistent primary key. When updating existing recipients, the server must verify IDs/ownership; never trust a client-supplied index as authorization for a row.

### 13.13. Treating an Arbitrary Map as Database Configuration

A map permitting keys `admin`, `featureFlags`, or `permissions` can enable mass assignment. Use exact-key allowlists and explicit service mapping; reject extra keys if the contract requires it.

### 13.14. Failing to Re-Render Entered Values on Error

If the controller constructs a fresh DTO and returns the view instead of keeping the bound object and current `BindingResult`, the fields the user entered are lost. In Spring MVC, when local `BindingResult` has errors, return the template directly from the handler to preserve the model attribute and binding state.

### 13.15. Testing One Valid Form and Assuming Coverage Is Complete

The happy path does not verify nested validation, Map key restrictions, or indexed paths. Write negative tests at every layer: blank nested field, invalid indexed email, unlisted map key, and out-of-range List index.

## 14. Practical Extensions: Dynamic Rows, Partial Updates, and Persistence

### 14.1. Adding Recipient Deletion

To support removal, add a dedicated `POST /delivery/remove` route taking an index, validate the index range, remove the element from the List, and re-render. After every deletion, Thymeleaf must regenerate sequential field names starting from index 0. For multi-step forms or redirects, you need explicit state persistence: session commands, a draft store, or idempotent operations.

Never just “delete from the DOM” without ensuring the server knows which item was removed. With persistence, use stable IDs and ownership checks to avoid deleting another account's recipient.

### 14.2. Should You Use Session for Multi-Step Forms?

`@SessionAttributes` can retain a form object across requests in the same session, but it introduces lifecycle/cleanup requirements, multi-tab concurrency issues, stale form data, and session security concerns. For a short form, stateless rebinding like the demo is usually easier to understand. For real wizards, consider draft IDs and server-side state.

### 14.3. CSRF and Form Methods

The demo does not enable Spring Security, so it has **no CSRF protection yet**. If endpoints are tied to user accounts and mutate data, production needs authentication, authorization, and CSRF defenses suited to cookie-based browser sessions. Thymeleaf integrates with Spring's `RequestDataValueProcessor` to add hidden fields when Spring Security CSRF is configured.

Never disable CSRF just to make a form submit work. Browsers can submit forms cross-site; verify the protection mechanism matches your authentication model.

### 14.4. Persistence and Transactions

After the form is validated, the service should:

1. Authenticate the actor and verify permission to modify the resource.
2. Map **only permitted fields** from the input DTO into the domain model.
3. Validate business invariants such as whether recipients contain duplicates.
4. Apply transactions/optimistic locking when updating the database.
5. Enforce appropriate UNIQUE/NOT NULL/FK/CHECK constraints in the database.
6. Return only the needed output DTO, never serialize the entity graph.

Data binding and Bean Validation **do not replace** database constraints or authorization. A syntactically valid email does not mean the recipient belongs to the caller, and a valid Map key does not mean the actor may change every system setting.

### 14.5. Forms with Large Lists

If a form has hundreds of recipients, server-rendered indexed fields produce huge requests that are hard to roll back and prone to DoS. Consider separate CRUD endpoints, pagination, size-limited batch APIs, and idempotency. Never raise `setAutoGrowCollectionLimit(1000000)` as a fix for large-index errors.

### 14.6. Updating a Single Element

If a feature only edits a specific recipient's email, a small DTO such as:

```java
public record ChangeRecipientEmail(
        @NotBlank @Email String email) {
}
```

is usually safer than re-binding an account's entire List. The resource ID is resolved from the route and authorization, never trusting a client-supplied index. This is a **fragment** requiring Jakarta Validation imports, not part of the full runnable form project.

## 15. QA Checklist for Nested Forms

### DTO / Property Paths

- [ ] Root form has an explicit model attribute name.
- [ ] Nested objects have clear constructors/getters/setters or a constructor-binding plan.
- [ ] Collections/Maps use mutable implementations when property binding must mutate them.
- [ ] Input DTO contains no sensitive domain fields.
- [ ] Names use `address.city`, `recipients[0].email`, `preferences[language]` accurately.
- [ ] `@Valid` cascades to `address` and every List element.
- [ ] Container constraints are applied at the proper List/Map/value level.
- [ ] Required fields have appropriate `@NotBlank`/`@NotNull`.
- [ ] Tests are updated whenever a nested property name changes.

### Controller / Security

- [ ] `@InitBinder` matches the `objectName` of `@ModelAttribute`.
- [ ] `setAllowedFields` uses exact paths/narrow wildcards.
- [ ] Auto-grow limits are configured for indexed collections.
- [ ] Request parameter/body size limits and abnormal-index handling are in place.
- [ ] `getSuppressedFields` is inspected when unknown fields must be rejected.
- [ ] Map keys and values are allowlisted according to semantics.
- [ ] `BindingResult` sits immediately after the validated argument.
- [ ] Service checks authentication/authorization before mutating real state.
- [ ] Never bind JPA entities directly from forms.
- [ ] Never use an arbitrary `Map<String,Object>` to copy properties onto an entity.

### Thymeleaf / UX

- [ ] `th:object` points to the right model attribute.
- [ ] `th:field` generates exact HTTP `name` attributes.
- [ ] For Lists, use `__${stat.index}__` preprocessing.
- [ ] Map fields use bracket key syntax and are tested.
- [ ] Field errors are displayed at nested/indexed paths.
- [ ] A global banner displays Map/global/suppressed errors.
- [ ] Users do not lose entered data when the form is invalid.
- [ ] Add/remove rows have limits and proper re-indexing.
- [ ] Never use `th:utext` for browser-supplied input.
- [ ] Production form mutations have CSRF protection.

### Tests

- [ ] GET test verifies `name="address.city"`.
- [ ] GET test verifies at least one `name="recipients[1].email"`.
- [ ] GET test verifies `name="preferences[language]"`.
- [ ] Valid form POST navigates to the success view.
- [ ] Blank address produces an error at `address.city`.
- [ ] Invalid List element produces an error at `recipients[1].email`.
- [ ] Out-of-set Map value is rejected.
- [ ] Out-of-allowlist Map key is not updated.
- [ ] Role/owner fields cannot be over-posted.
- [ ] Add row creates the proper index without triggering full validation while editing.
- [ ] Submitting 3 rows succeeds; 4+ rows are blocked per policy.
- [ ] Tests assert rejected inputs and model state, not just HTTP status.

## 16. Conclusion

**Designing forms with nested addresses, lists, and Maps** requires aligning three layers accurately:

1. **Object graph**: DTO has `AddressForm`, `List<RecipientForm>`, and `Map<String,String>` with appropriate structure and mutability.
2. **Property paths in HTTP/Thymeleaf**: use `address.city`, `recipients[0].email`, and `preferences[language]`; Thymeleaf `__${stat.index}__` produces accurate indexed paths when iterating.
3. **Data binding + validation + security**: `@ModelAttribute`, `WebDataBinder#setAllowedFields`, `@Valid` cascade, `BindingResult`, list size/auto-grow limits, and Map key/value policies.

The sample application renders the form, adds recipients, submits complete data, reports errors on nested paths, and blocks extra fields. MockMvc and pure `DataBinder` tests verify **actual framework behavior**, not merely that Java setters work.

**Key takeaways:** a List index is not a database ID, a client-supplied Map is not permission to modify an entity, and annotation validation does not replace authorization. Designing dedicated input DTOs, narrow allowlists, and negative tests from the start makes nested forms far easier to maintain.

## References

- [Spring Framework 6.2 — MVC Data Binding: nested, indexed, and Map property paths](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-data-binding.html)
- [Spring Framework 6.2 — @ModelAttribute: constructor and property binding](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework 6.2 — @InitBinder and Model Design](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework 6.2 — DataBinder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework 6.2 — BindingResult Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework — Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Framework 6.2 — MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Thymeleaf + Spring Tutorial 3.1 — th:object, th:field, and indexed preprocessing](https://www.thymeleaf.org/doc/tutorials/3.1/thymeleafspring.pdf)
- [Thymeleaf 3.1 — Using Thymeleaf](https://www.thymeleaf.org/doc/tutorials/3.1/usingthymeleaf.html)
- [OWASP — Mass Assignment Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html)
