# Determining Default Values and When They Apply in Spring Input Objects

## 1. What Is a Default Value and Why Does "Timing" Matter?

In Spring Framework, a **default value** is a value chosen by the system for a field or parameter when the caller does not provide one under a defined convention. It is part of the **input contract**, not merely a way to avoid `null`.

For example, a search API lets clients omit `limit`; the application chooses a default of `20`. You must answer five questions together:

1. **Which value is defaulted?** `limit=20`, `sort=newest`, `notificationsEnabled=true`, etc.
2. **Which condition triggers the default?** An absent parameter, an empty string, an absent JSON property, JSON `null`, or an invalid value?
3. **Who decides it?** Spring argument resolver, Java constructor/field initializer, Jackson, application service, or database?
4. **When is it applied?** Before type conversion, at object construction, during data binding, after validation, during business logic, or on DB insert?
5. **Does the default value go through validation?** A bad default is still input to the use case and must obey the corresponding constraints.

Without separating these steps, an API may silently replace a client's intentional input with a default, validate at the wrong time, or let other entry points (scheduled jobs/message consumers) behave inconsistently.

## 2. Distinguishing "Missing", "Empty", "Null", "0", and "False"

These states do not carry the same meaning:

| Scenario | Example | Usual Meaning |
| --- | --- | --- |
| URL parameter omitted | `GET /items` | `limit` is **absent** |
| URL parameter sent with no content | `GET /items?limit=` | `limit` is **present but empty** |
| Whitespace sent | `GET /items?sort=%20` | Value contains whitespace; handling depends on binder/converter |
| Numeric value 0 | `GET /items?limit=0` | Client supplied `0`; not equivalent to missing |
| Boolean value false | `{"notificationsEnabled":false}` | Client explicitly chose `false` |
| JSON property absent | `{}` | That property was not supplied |
| JSON property is null | `{"notificationsEnabled":null}` | Client explicitly sent `null` |
| Empty JSON string | `{"locale":""}` | Empty string, not JSON `null` |
| Wrong JSON type or syntax | `{"limit":"abc"}` when DTO expects a number | Read/conversion error; do not turn into default |

**Safe rule:** never use a blanket expression like "if false, 0, or empty string then take the default". `false` and `0` can be valid client choices. With partial updates (*PATCH*), "not sent" can even mean "keep unchanged", which is completely different from "reset to default".

## 3. Map of Default Mechanisms in Spring

| Mechanism | Used For | When Applied | Key Notes |
| --- | --- | --- | --- |
| `@RequestParam(defaultValue = "...")` | Query/form parameter resolved directly as a method argument | When Spring resolves controller arguments, before calling the method | Applies on missing or empty value; default is a string and then converted to the target type |
| `@RequestHeader(defaultValue = "...")`, `@CookieValue(defaultValue = "...")` | Header/cookie resolved into parameter | During the corresponding argument resolution step | Specific to that input source; does not apply to JSON fields |
| JavaBean field initializer or constructor | `@ModelAttribute` and Java objects | When object is instantiated, **before** binder assigns submitted data | Bound fields can overwrite defaults, including with empty strings or `null` after conversion |
| Field initializer / constructor when Jackson creates DTO | JSON `@RequestBody` | When Jackson instantiates the object, before populating JSON properties | Missing properties usually keep initial value; `null` properties usually overwrite with `null` |
| Immutable DTO constructor/normalization | Records, immutable DTOs | When constructor is invoked during deserialization/binding | Must write default rules explicitly; decide missing vs `null` semantics separately |
| Application/domain service | Defaults depending on use case, config, user, or time | After receiving data, when enforcing policy | Must validate the resulting value and keep HTTP/jobs/messages consistent |
| `DEFAULT` in SQL schema | Database column | When DB executes a matching `INSERT` | Does not populate request DTOs; typically takes effect only if column is omitted from `INSERT` |

**There is no single global Spring "default" mechanism** that applies identically across query parameters, form objects, JSON bodies, records, and databases.

## 4. Timing Flow: Before, During, and After Data Binding

For a typical HTTP request:

```text
Incoming request
  |
  +--> Read data source (query/form/JSON/header)
  |
  +--> Instantiate object or resolve parameters
  |       - Java field initializer / constructor default
  |       - @RequestParam defaultValue if missing/empty
  |
  +--> Data binding / deserialization / type conversion
  |       - Present values may overwrite field initializers
  |       - Type mismatches may be rejected at this step
  |
  +--> Bean Validation (when triggered)
  |       - Checks FINAL values after binding/defaulting
  |
  +--> Controller -> application/domain service
  |       - Determine policy/context-dependent defaults
  |       - Check business invariants after values are decided
  |
  +--> Repository/SQL -> database
          - DB defaults/constraints/transaction
```

This is a conceptual diagram; exact paths differ among `@RequestParam`, `@ModelAttribute`, and `@RequestBody`. Key points to keep in mind:

- **Java field initializers run when the object is instantiated**. They do not "re-run" after a setter or Jackson overwrites a property.
- **Spring binding does not treat every invalid input as missing.** `limit=abc` must be handled as a type-conversion error instead of becoming `limit=20`.
- **Bean Validation does not generate default values.** `@NotNull`, `@NotBlank`, `@Min`, and `@Valid` only check; they do not choose new values.
- **Business defaults must be decided before checking business invariants that rely on them.** If policy depends on user/tenant/time, the DTO constructor usually lacks enough context.

## 5. Direct Parameters: `@RequestParam(defaultValue)`

Example:

```java
@GetMapping("/items")
public Map<String, Object> items(
        @RequestParam(defaultValue = "20") int limit,
        @RequestParam(defaultValue = "newest") String sort) {
    return Map.of("limit", limit, "sort", sort);
}
```

Spring applies `defaultValue` while resolving method arguments:

| Request | `limit` | `sort` | Explanation |
| --- | ---: | --- | --- |
| `GET /items` | `20` | `newest` | Both are absent |
| `GET /items?limit=` | `20` | `newest` | `limit` is present but empty |
| `GET /items?limit=5&sort=price` | `5` | `price` | Client overrides defaults |
| `GET /items?limit=0` | `0` | `newest` | `0` is a real value; needs a separate rule if disallowed |
| `GET /items?limit=abc` | Fails to run handler | — | String cannot convert to valid `int` |

Important characteristics:

- `defaultValue` accepts a **string** in the annotation; for `int`/`long`/`enum`, Spring must still convert that string to the target type. If the declared default cannot convert, the request can also fail.
- Declaring `defaultValue` implicitly makes the parameter non-required (`required=false`). Do not simultaneously interpret `required=true` as "guaranteed sent by the client".
- `@RequestParam(required = false) Integer limit` receives `null` when omitted so code can decide itself. Use wrapper `Integer` when you need to represent "no value provided"; avoid relying on primitive `int` to signal absence.
- If business rules require **missing = 20, but empty string = error**, `defaultValue` does not fit because it treats empty strings as triggering the default. Design a contract/parser that distinguishes parameter presence.
- `@RequestParam` governs URL/form parameters (via argument resolution) and **does not assign defaults to fields inside a JSON body**.

`@PathVariable` comes from the route path. Do not use `@RequestParam(defaultValue)` as a workaround for an absent path segment; instead, define separate routes or query parameters according to API semantics.

## 6. `@ModelAttribute` Objects: Defaults Before Spring Assigns Properties

For form/query inputs bound to a JavaBean, field initialization is a clear way to define defaults. Example:

```java
package demo.defaults;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class SearchForm {
    @NotNull
    @Min(1)
    @Max(100)
    private Integer limit = 20;

    @NotBlank
    private String sort = "newest";

    public SearchForm() {}

    public Integer getLimit() { return limit; }
    public void setLimit(Integer limit) { this.limit = limit; }

    public String getSort() { return sort; }
    public void setSort(String sort) { this.sort = sort; }
}
```

Controller example in the same project:

```java
@GetMapping("/form")
public Map<String, Object> form(
        @Valid @ModelAttribute SearchForm form) {
    return Map.of(
            "limit", form.getLimit(),
            "sort", form.getSort());
}
```

With the JavaBean above, the sequence works as follows:

1. Spring instantiates `SearchForm`; at this moment `limit=20` and `sort="newest"`.
2. Spring binds submitted parameters. If the client sends `limit=5`, the setter receives the converted value and overwrites `20`. If `limit` is omitted, the field stays `20`.
3. Bean Validation is triggered by `@Valid` and checks the **post-binding values**. `limit=0` violates `@Min(1)`; `sort=` violates `@NotBlank`.
4. The controller is invoked only on the binding/validation success path (aside from explicit error-handling mechanisms like `BindingResult`).

**Common trap:** `?sort=` is a provided value, so the setter can replace `"newest"` with an empty string, which validation then rejects. This differs from `@RequestParam(defaultValue="newest")`, where an empty string triggers the default.

For `Integer limit`, an empty form value is usually converted to `null`; `@NotNull` catches this case. `@Min` by itself does not treat `null` as a violation. For `limit=abc`, binding reports a type error rather than silently keeping the old default as a fallback.

`@ModelAttribute` also supports other instantiation styles and constructor binding depending on the object's structure. For a JavaBean DTO with a no-arg constructor and setters as shown, the **instantiate first, bind present values, then validate** rule is particularly easy to control. If using a parameterized constructor or record, be explicit about which constructor receives data and when defaults apply.

## 7. JSON `@RequestBody`: Jackson and the Difference Between Missing and `null`

In Spring MVC with the Jackson JSON converter, `@RequestBody` goes through deserialization rather than `@ModelAttribute` property binding. A JavaBean request can declare initial defaults:

```java
package demo.defaults;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class PreferenceRequest {
    @NotNull
    private Boolean notificationsEnabled = Boolean.TRUE;

    @NotBlank
    private String locale = "vi-VN";

    public PreferenceRequest() {}

    public Boolean getNotificationsEnabled() {
        return notificationsEnabled;
    }
    public void setNotificationsEnabled(Boolean value) {
        this.notificationsEnabled = value;
    }

    public String getLocale() { return locale; }
    public void setLocale(String locale) { this.locale = locale; }
}
```

Controller:

```java
@PostMapping("/request-body")
public Map<String, Object> requestBody(
        @Valid @RequestBody PreferenceRequest request) {
    return Map.of(
            "notificationsEnabled", request.getNotificationsEnabled(),
            "locale", request.getLocale());
}
```

Typical behavior with a JavaBean and default Jackson configuration:

| Submitted JSON | `notificationsEnabled` | `locale` | Outcome |
| --- | --- | --- | --- |
| `{}` | `true` | `vi-VN` | No property overwrites the initializers |
| `{"notificationsEnabled":false}` | `false` | `vi-VN` | `false` is preserved |
| `{"notificationsEnabled":null}` | `null` | `vi-VN` | `@NotNull` rejects; does not fall back to `true` |
| `{"locale":""}` | `true` | `""` | `@NotBlank` rejects |
| `{"locale":"en-US"}` | `true` | `en-US` | Client-supplied value overrides default |

**An absent JSON property** usually does not call that property's setter, so the field initializer stays intact. **A JSON property with `null`** usually overwrites an object-typed field with `null`. Thus, a JavaBean with defaults still needs validators and a policy for explicit null.

Avoid primitive `boolean` or `int` when the contract must distinguish "omitted" from "client deliberately sent `false`/`0`". Primitives receive Java-language defaults as soon as the object is created, and JSON `null` coercion also has specific semantics depending on Jackson configuration. Use `Boolean`/`Integer` wrappers or presence-aware types to avoid losing meaning.

### When You Want JSON `null` to Keep the Default Too

If the contract specifies that both a missing property **and explicit null** mean "use the default value", Jackson supports this on JavaBean properties:

```java
import com.fasterxml.jackson.annotation.JsonSetter;
import com.fasterxml.jackson.annotation.Nulls;

@JsonSetter(nulls = Nulls.SKIP)
private Boolean notificationsEnabled = Boolean.TRUE;
```

With this setting, Jackson skips assigning `null` to that property, leaving the initialized value untouched. Use this only when **null semantics are explicitly decided**; if sending null must be rejected, keep `@NotNull` without `Nulls.SKIP` as in the earlier example.

Beware of commonly misunderstood annotations:

- Jackson's `@JsonProperty(defaultValue = "...")` provides metadata about the default value and **does not automatically make Jackson assign that value when a property is missing** during standard databinding.
- `@Schema(defaultValue = "...")` documents the OpenAPI contract; it **does not execute** defaults when receiving requests.
- Validation annotations such as `@NotNull`, `@Min`, and `@Size` do not auto-populate defaults.
- `@RequestParam(defaultValue)` does not apply to fields inside `@RequestBody`.

## 8. Runnable Spring Boot 3.x Example

To run the Java 17 example above, create a Spring Boot 3.x project with **Spring Web** and **Validation** dependencies, then place the following classes in package `demo.defaults`:

- `DefaultsApplication.java`: startup class below.
- `DefaultsController.java`: controller below.
- `SearchForm.java` and `PreferenceRequest.java`: keep the two classes shown in sections 6–7 unchanged.

```java
// src/main/java/demo/defaults/DefaultsApplication.java
package demo.defaults;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DefaultsApplication {
    public static void main(String[] args) {
        SpringApplication.run(DefaultsApplication.class, args);
    }
}
```

```java
// src/main/java/demo/defaults/DefaultsController.java
package demo.defaults;

import jakarta.validation.Valid;
import java.util.Map;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/demo")
public class DefaultsController {

    @GetMapping("/items")
    public Map<String, Object> items(
            @RequestParam(defaultValue = "20") int limit,
            @RequestParam(defaultValue = "newest") String sort) {
        return Map.of("limit", limit, "sort", sort);
    }

    @GetMapping("/form")
    public Map<String, Object> form(
            @Valid @ModelAttribute SearchForm form) {
        return Map.of(
                "limit", form.getLimit(),
                "sort", form.getSort());
    }

    @PostMapping("/request-body")
    public Map<String, Object> requestBody(
            @Valid @RequestBody PreferenceRequest request) {
        return Map.of(
                "notificationsEnabled", request.getNotificationsEnabled(),
                "locale", request.getLocale());
    }
}
```

Run the project via Maven Wrapper (assuming Maven config generated by Spring Initializr):

```bash
./mvnw spring-boot:run
```

On Windows Command Prompt/PowerShell, use `mvnw.cmd spring-boot:run`.

Test commands:

```bash
curl "http://localhost:8080/demo/items"
curl "http://localhost:8080/demo/items?limit=&sort="
curl "http://localhost:8080/demo/form"
curl "http://localhost:8080/demo/form?limit=0"
curl -X POST "http://localhost:8080/demo/request-body" -H "Content-Type: application/json" -d '{}'
curl -X POST "http://localhost:8080/demo/request-body" -H "Content-Type: application/json" -d '{"notificationsEnabled":null}'
```

Expected results:

- The first two `/demo/items` requests return JSON with `limit: 20` and `sort: "newest"`.
- `/demo/form` with no parameters returns `20` and `"newest"` from the JavaBean initializers.
- `/demo/form?limit=0` is rejected by validation with HTTP 400 under standard MVC configuration.
- POST `{}` returns JSON with `notificationsEnabled: true` and `locale: "vi-VN"`.
- POST with explicit `null` for `notificationsEnabled` is rejected by `@NotNull`, typically HTTP 400.

JSON property order and error response format depend on serializer and Spring Boot error handling, so **do not write tests comparing raw JSON strings by property order**. Assert values and HTTP statuses instead of coupling to default framework error messages.

### Pure Java Example Demonstrating Initialization and Override Order

If you only want to verify JavaBean mechanics without running Spring, save as `DefaultsTimingDemo.java`:

```java
public class DefaultsTimingDemo {
    static class Filter {
        String sort = "newest";

        void setSort(String value) {
            sort = value;
        }
    }

    public static void main(String[] args) {
        Filter missing = new Filter();

        Filter empty = new Filter();
        empty.setSort("");

        Filter explicitNull = new Filter();
        explicitNull.setSort(null);

        System.out.println("missing = " + missing.sort);
        System.out.println("empty = '" + empty.sort + "'");
        System.out.println("explicit null = " + explicitNull.sort);
    }
}
```

Run with JDK 17+:

```bash
javac DefaultsTimingDemo.java
java DefaultsTimingDemo
```

Exact stdout:

```text
missing = newest
empty = ''
explicit null = null
```

This snippet illustrates Java initializers and setters; Spring MVC/Jackson decides **when setters are called and which values are passed**.

## 9. Timing of Defaulting Relative to Validation

Suppose `limit` must be in the range 1–100, defaulting to 20. There are three distinct decisions:

1. **Choose default before validation:** with `@ModelAttribute SearchForm` having initializer `20`, validation sees `20` if the field is missing; if the client sends `0`, validation sees `0` and rejects it.
2. **Do not repair bad input with a default:** if `limit=abc` fails type conversion, return an error. If `limit=0` violates business/constraint rules, return an error. Silently turning them into `20` hides client mistakes.
3. **Apply defaults after DTO intake when context is needed:** for example, the default limit varies by service plan, tenant, or runtime config. The DTO only captures "unspecified", the service uses policy/config to pick the value, **and then validates the chosen value** against business invariants.

Do not rely on validation to detect absence after assigning a default. Once a JavaBean initializes `limit=20`, a `@NotNull` validator can no longer tell whether the client actually provided a value. If auditing requires knowing "did the client send limit or did the system default it", record a separate presence signal prior to or alongside defaulting.

When using a nullable wrapper:

```java
Integer effectiveLimit =
        requestedLimit != null ? requestedLimit : 20;
```

The expression above preserves `0` if the client chose `0`, and the `1..100` constraint must be checked in the next step. Conversely, checking `requestedLimit == 0` as a missing-value sentinel loses a real input case that must be handled.

## 10. Dynamic Defaults, Time, and Permissions Belong in the Right Layer

Not every default is a constant. Examples:

- `pageSize` defaults based on user tier.
- `currency` defaults based on market/tenant.
- `createdAt` takes the server timestamp when the object is created.
- `ownerId` comes from the authenticated identity.
- `status` of a new order is always `PENDING` per workflow.

Values depending on **business context or authorization** should be determined in the service/domain layer, rather than letting clients control them directly or hardcoding static defaults into a DTO.

Conceptual example:

```java
// Illustrative service snippet: tierPolicy and clock are injected dependencies.
int effectiveLimit = requestedLimit != null
        ? requestedLimit
        : tierPolicy.defaultPageSizeFor(currentUser);

if (effectiveLimit < 1 || effectiveLimit > tierPolicy.maxPageSizeFor(currentUser)) {
    throw new IllegalArgumentException("Invalid page size");
}

java.time.Instant createdAt = clock.instant();
```

For time, choosing **when** it is captured is part of the requirement:

- `Instant.now()` in a field initializer runs when the DTO is constructed/deserialized, which may be earlier than when the business operation actually creates the record.
- `clock.instant()` in the service represents the time the use case executes (with `Clock` injected for deterministic tests).
- `DEFAULT CURRENT_TIMESTAMP` in the database is tied to DB/transaction timing semantics, not necessarily when the HTTP request arrived.

If you need "the time the order was confirmed", capture the timestamp during the confirmation action and store it. If you need "the time the DB inserted the row", consider DB mechanisms. Do not pick randomly between the two, as they can produce different values.

Never accept `role=ADMIN` or `ownerId` from the client and treat a `USER` default as a security mechanism. Role/ownership attributes must be determined from the authenticated principal and business policy; also restrict bindable fields to prevent modifying internal attributes.

## 11. Database Defaults Differ from DTO Defaults

Example DDL:

```sql
CREATE TABLE tasks (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

The database can apply its default if an `INSERT` omits the column:

```sql
INSERT INTO tasks DEFAULT VALUES;
```

However, if SQL explicitly sends **`status = NULL`**, the `NOT NULL` constraint can reject the insert instead of substituting `PENDING`. With JPA/Hibernate, an entity having `status = null` does not mean the ORM omits the column from `INSERT`; many configurations explicitly send `NULL`. Therefore, do not expect DB defaults to silently fill in every field missing from requests.

Points to check:

- Hibernate's `@ColumnDefault` relates to schema/DDL generation; it **does not set values on Java request DTOs**.
- `@Column(nullable = false)` describes mapping/nullability and **does not initialize Java values**.
- An entity's Java initializer and a DB default can specify two different values, causing different behavior between JPA and raw SQL. Choose a single consistent policy.
- Never let a DB default silently replace an important business rule. If a default depends on the user or use-case state, resolve it in the domain/service before persisting.

## 12. Immutable DTOs, Records, and Distinguishing Missing from Explicit Null

With Java records, there are no setters or JavaBean-style field initializers for individual record components. You can use a compact constructor:

```java
public record SearchJson(Integer limit, String sort) {
    public SearchJson {
        if (limit == null) {
            limit = 20;
        }
        if (sort == null) {
            sort = "newest";
        }
    }
}
```

This example is valid in Java 17; calling `new SearchJson(null, null)` yields a record holding `20` and `"newest"`. When Jackson deserializes a record, both **missing** properties and **explicit null** properties can pass `null` arguments into the constructor. This is appropriate **only if the contract intends both cases to have the same meaning**.

If the product specifies:
- `limit` omitted → use `20`;
- `"limit": null` sent → return error;
- `"limit": 0` sent → return range error;

then a simple constructor like above **lacks enough information** to separate the first case from the second. Use a presence-aware input type, a custom deserializer, or inspect the JSON tree before converting into a domain command. Never assume null means "not sent" if the API must distinguish them.

Similarly, Lombok's `@Builder.Default` only carries semantics for construction via its builder; do not assume Jackson or Spring's binder always uses that builder.

## 13. Create and Partial Update Have Different Semantics

For **create** requests, missing properties are often interpreted as "use default" if the contract specifies one. For **PATCH** requests, missing properties normally mean "do not change existing data".

Suppose an account currently has `displayName = "Linh"`:

| JSON PATCH | Intended Meaning That May Be Desired |
| --- | --- |
| `{}` | Keep `"Linh"` unchanged |
| `{"displayName":"An"}` | Change to `"An"` |
| `{"displayName":null}` | Clear value, if permitted; or reject |
| `{"displayName":""}` | Change to empty string if permitted; or validation error |

If you initialize `displayName = "Guest"` when instantiating a PATCH DTO and then copy all fields onto the entity, `{}` risks renaming `"Linh"` to `"Guest"` unexpectedly.

For PATCH, preserve **whether each field appeared** (e.g., using a three-state type or checking presence in a JSON tree) and update only the fields the client sent. Validation and defaults for update contexts must be designed separately; never mechanically reuse creation DTOs.

## 14. Testing When Defaults Apply

At a minimum, test both valid and invalid paths:

| Test Case | Expected Result |
| --- | --- |
| `GET /demo/items` | `limit=20`, `sort=newest` |
| `GET /demo/items?limit=` | `limit=20` due to `@RequestParam(defaultValue)` |
| `GET /demo/items?limit=abc` | Conversion error, does not fall back to `20` |
| `GET /demo/items?limit=0` | Value `0` passed to controller; endpoint must add validation to disallow it |
| `GET /demo/form` | JavaBean initializer sets `limit=20` |
| `GET /demo/form?sort=` | `@NotBlank` error after binding |
| `GET /demo/form?limit=0` | `@Min(1)` error after binding |
| POST JSON `{}` | Keeps defaults on `PreferenceRequest` |
| POST JSON `{"notificationsEnabled":false}` | Keeps `false` |
| POST JSON `{"notificationsEnabled":null}` | `@NotNull` rejects |
| Service with different tiers | Picks right dynamic default per tier |
| PATCH JSON `{}` | Leaves existing fields unchanged |
| DB `INSERT` omitting defaulted column | Receives DB schema default |
| DB `INSERT` explicitly setting `NULL` on `NOT NULL` column | Rejected |

In Spring, use `MockMvc`/`@WebMvcTest` to test controller binding and validation, unit tests for default-selection policies in the service, and integration tests for JPA and database behavior. Do not merely test instantiating an object with `new` and conclude HTTP requests behave identically, because binders and JSON deserializers can overwrite initializers.

## 15. Common Mistakes

**Mistake 1: Assuming missing properties and null properties are always identical.** They are distinct states in JSON; JavaBeans, records, Jackson settings, and the API contract decide whether they merge.

**Mistake 2: Using defaults to mask errors.** Sending `limit=abc` or `limit=0` does not mean "not sent". Falling back to a default hides input bugs.

**Mistake 3: Assuming `@RequestParam(defaultValue)` works on `@RequestBody`.** These are two different data-resolution mechanisms; JSON DTOs need defaults handled in deserialization, constructors, or normalization separately.

**Mistake 4: Applying defaults too early.** Setting tenant/user/tier defaults inside a DTO constructor without context can produce wrong results. Choose them in the service and validate again.

**Mistake 5: Using primitives to infer whether data was sent.** `0` and `false` can be genuine values, not safe sentinels for "absent".

**Mistake 6: Expecting descriptive annotations to execute.** `@JsonProperty(defaultValue)`, OpenAPI `@Schema(defaultValue)`, and some DB mapping annotations do not replace actual value-assignment logic.

**Mistake 7: Using a creation DTO for PATCH and applying defaults onto an existing entity.** An absent field can overwrite live data; PATCH must preserve presence information.

**Mistake 8: Failing to re-validate after applying business defaults.** Values loaded from config/policy can also be wrong or out of bounds. Ensure the final state satisfies domain invariants.

## 16. Quick Guide for Deciding Where to Place Defaults

1. **A fixed default for a URL/header/cookie parameter?** Use the argument resolver's `defaultValue` if **missing and empty are allowed to mean the same thing**.
2. **A JavaBean receiving form/query inputs where omitted fields should keep initial values?** Initialize in fields/constructor for `@ModelAttribute` and check overwrite behavior when values are sent.
3. **A JSON request body where omitted properties should take defaults?** Choose initializers/constructors or deliberate Jackson settings; decide explicit `null` separately.
4. **A default depending on user, tier, tenant, policy, or use-case timing?** Resolve in the application/domain service, then validate the effective value.
5. **A default belonging solely to record storage?** Consider DB defaults, inspect ORM-generated SQL, and never use DB defaults in place of business rules.
6. **Is it a PATCH?** Keep absent, null, and present values distinct; creation defaults rarely apply as-is.

A clear design always answers: **which input triggers the default, where the value is assigned, whether it applies before or after binding/validation, and whether explicit client values are preserved**. When those answers align, Spring input objects are easy to test, easy to explain, and unlikely to cause unexpected data bugs.