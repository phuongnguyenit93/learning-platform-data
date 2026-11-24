# `application/x-www-form-urlencoded` and Form Data Binding

Not every request sending data to an API uses JSON. Many web forms transmit data in the `application/x-www-form-urlencoded` format, where fields are encoded as name-value pairs. For example, a subscription form might send `email=dev%40example.com&plan=pro` in the body of the HTTP request.

In Spring Boot, Spring MVC can bind form data into method parameters or a command object using `@RequestParam` and `@ModelAttribute`. `springdoc-openapi` allows describing this request body in the OpenAPI specification so Swagger UI displays the proper content type, fields, constraints, and examples for integrators.

This lesson walks through the form-urlencoded structure, binding, validation, OpenAPI description, and testing. It focuses on Spring MVC on the Servlet stack; with WebFlux, accessing form data has some API differences that should be checked against your framework version.

## Objectives

After this lesson, you will be able to:

- Explain how `application/x-www-form-urlencoded` encodes data and distinguish it from JSON or multipart.
- Send form data using browsers, curl, and HTTP clients.
- Bind form fields into parameters or DTOs in Spring MVC.
- Apply Bean Validation and handle form data errors.
- Describe form-urlencoded request bodies using OpenAPI and `springdoc-openapi`.
- Verify the generated specification alongside actual HTTP behavior.
- Recognize caveats around special characters, repeated fields, CSRF, and sensitive data.

## 1. What is `application/x-www-form-urlencoded`?

`application/x-www-form-urlencoded` is a media type used to send form data as a string of `name=value` pairs separated by `&`. Names and values are URL-encoded so special characters do not break the structure:

~~~http
POST /api/subscriptions HTTP/1.1
Host: localhost:8080
Content-Type: application/x-www-form-urlencoded
Accept: application/json

email=dev%40example.com&plan=pro&note=Spring+Boot
~~~

In this example:

- `email` has the value `dev@example.com`; the `@` character is encoded as `%40`.
- `plan` has the value `pro`.
- `note` has the value `Spring Boot`; spaces are represented by plus signs in standard form encoding.

This format suits forms with text fields, selections, checkboxes, and simple string or numeric data. It is not JSON: the server does not receive a JSON object in the body, but rather a set of encoded form parameters.

### Data structure after decoding

The form string:

~~~text
email=dev%40example.com&plan=pro&note=Spring+Boot
~~~

Is interpreted as the pairs:

| Field name | Decoded value |
|---|---|
| email | dev@example.com |
| plan | pro |
| note | Spring Boot |

Names and values are decoded according to URL encoding rules. A plus sign in form data represents a space; if a value genuinely contains a plus sign, the client must encode it as `%2B`. For example, phone numbers or strings containing `+` must be properly encoded so the server does not mistake a plus sign for a space.

### `Content-Type` and `Accept`

The two headers play distinct roles:

- `Content-Type` describes the body format sent by the client. For form-urlencoded, the value is `application/x-www-form-urlencoded`.
- `Accept` indicates the format in which the client wants to receive the response, such as `application/json`.

An endpoint can accept form-urlencoded yet return JSON. Therefore, a request can carry `Content-Type: application/x-www-form-urlencoded` and `Accept: application/json` at the same time.

## 2. How do browsers submit forms?

A basic HTML form:

~~~html
<form method="post"
      action="/api/subscriptions"
      enctype="application/x-www-form-urlencoded">
    <label>
        Email
        <input type="email" name="email" required>
    </label>

    <label>
        Service Plan
        <select name="plan">
            <option value="basic">Basic</option>
            <option value="pro">Pro</option>
        </select>
    </label>

    <label>
        Note
        <input type="text" name="note">
    </label>

    <button type="submit">Subscribe</button>
</form>
~~~

With a standard POST form, the browser sends fields in the body and sets `Content-Type` to match `enctype`. `application/x-www-form-urlencoded` is the default for HTML forms when no other `enctype` is specified. Declaring `enctype` explicitly makes it clear to readers which format the endpoint expects.

The `name` attribute determines the parameter name the server receives. The `id` attribute and visible `label` text do not dictate the submitted field name. If an input lacks a `name`, its value is normally not sent in the form submission.

If the form uses `method="get"`, the browser places fields into the URL query string instead of sending a form-urlencoded body. This lesson focuses on POST forms with a body.

## 3. Sending forms with curl

When testing an API, use `--data-urlencode` so curl encodes each field:

~~~bash
curl -i -X POST http://localhost:8080/api/subscriptions \
  -H "Accept: application/json" \
  --data-urlencode "email=dev@example.com" \
  --data-urlencode "plan=pro" \
  --data-urlencode "note=Spring Boot and OpenAPI"
~~~

When `--data-urlencode` is used, curl sends the body in form-urlencoded format and sets the matching `Content-Type`. This option properly handles spaces, Vietnamese diacritics, and special characters.

You can manually send an already encoded string:

~~~bash
curl -i -X POST http://localhost:8080/api/subscriptions \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data "email=dev%40example.com&plan=pro&note=Spring+Boot"
~~~

With the second approach, the author must ensure the string is properly encoded. Never concatenate user-supplied values into a form string without URL encoding; `&`, `=`, `+`, or Unicode characters can corrupt the data.

## 4. Binding form fields to parameters with `@RequestParam`

In Spring MVC, `@RequestParam` can extract values from request parameters. On the Servlet stack, request parameters include query parameters and parsed form-urlencoded data. Thus, this annotation fits endpoints with a few simple fields:

~~~java
@RestController
@RequestMapping("/api/subscriptions")
public class SubscriptionController {

    @PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public SubscriptionResponse create(
            @RequestParam String email,
            @RequestParam String plan,
            @RequestParam(required = false) String note) {

        return subscriptionService.create(email, plan, note);
    }
}
~~~

Spring retrieves values by parameter name. If a required field is absent, the request may be rejected due to a missing parameter. For optional fields, set `required = false` or use a type capable of representing an absent value.

You can specify the field name explicitly:

~~~java
@RequestParam(name = "email") String email
~~~

Specify the name explicitly when the Java parameter name differs from the form field name or when you want a stable contract regardless of compiler flag changes. Do not rely on the compiler preserving parameter names if the project has not enabled the corresponding metadata.

### Default values and data types

`@RequestParam` can convert strings into basic Java types:

~~~java
@PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
public SearchResponse search(
        @RequestParam String keyword,
        @RequestParam(defaultValue = "1") int page,
        @RequestParam(defaultValue = "20") int size,
        @RequestParam(required = false) Boolean includeArchived) {

    return searchService.search(keyword, page, size, includeArchived);
}
~~~

If the client sends an unconvertible value—such as `page=abc` for an `int` parameter—Spring MVC can return a binding error before invoking the service. Define the status code and error schema the API should publish for this case.

Note that `@RequestParam` in Spring MVC reads both query parameters and form data. If the same name appears in both the query string and the body, the application may see values from the merged request parameter map. If you need a strict boundary between body data and query data, design field names to avoid collisions and test duplicate submissions; do not assume this annotation reads only the body.

## 5. Binding multiple fields to a DTO with `@ModelAttribute`

When a form has many fields, using a DTO groups the data and decouples the request contract from the controller. `@ModelAttribute` instructs Spring to bind request parameters to an object's properties or constructor:

~~~java
public class SubscriptionForm {

    private String email;
    private String plan;
    private String note;

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public String getPlan() {
        return plan;
    }

    public void setPlan(String plan) {
        this.plan = plan;
    }

    public String getNote() {
        return note;
    }

    public void setNote(String note) {
        this.note = note;
    }
}
~~~

Controller:

~~~java
@PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
public ResponseEntity<SubscriptionResponse> create(
        @Valid @ModelAttribute SubscriptionForm form) {

    SubscriptionResponse created = subscriptionService.create(form);
    return ResponseEntity.status(HttpStatus.CREATED).body(created);
}
~~~

With modern Java and Spring versions supporting constructor binding for records, you can express the DTO concisely as a record:

~~~java
public record SubscriptionForm(
    String email,
    String plan,
    String note
) {}
~~~

`@ModelAttribute` lets the controller receive an object bound from request parameters. In Spring MVC, a model attribute can be constructed via a constructor or by invoking setters. For objects with setters, include in the DTO only the fields clients are allowed to modify; avoid binding persistence entities directly that contain sensitive properties.

### Choosing `@RequestParam` or `@ModelAttribute`?

| Scenario | Appropriate approach |
|---|---|
| One or two simple fields | `@RequestParam` |
| Multiple fields belonging to one form | `@ModelAttribute` with a DTO |
| DTO-level validation needed | `@Valid @ModelAttribute` |
| Collecting multiple values under one name | `MultiValueMap<String, String>` or an appropriate collection |
| Receiving files alongside form fields | `multipart/form-data` and `MultipartFile` |

Do not use `@RequestBody` with a JSON DTO for form-urlencoded and expect Spring to bind it like JSON. `@RequestBody` is intended to read the body via an `HttpMessageConverter`; for forms on the Servlet stack, Spring MVC typically uses request parameters and data binding via `@RequestParam` or `@ModelAttribute`. Avoid reading the same request body through multiple mechanisms.

## 6. Validating form data

Form data still needs server-side validation. HTML validation in the browser only assists user input; clients can bypass it or send requests directly.

Example DTO with Bean Validation:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

@Schema(name = "SubscriptionForm", description = "Subscription form data")
public record SubscriptionForm(
    @NotBlank
    @Email
    @Schema(description = "Email address", example = "dev@example.com")
    String email,

    @NotBlank
    @Schema(description = "Subscription plan code", example = "pro",
            allowableValues = {"basic", "pro"})
    String plan,

    @Size(max = 250)
    @Schema(description = "Optional note", example = "Contact in the afternoon")
    String note
) {}
~~~

Controller using `@Valid`:

~~~java
@PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
public ResponseEntity<SubscriptionResponse> create(
        @Valid @ModelAttribute SubscriptionForm form) {
    return ResponseEntity.status(HttpStatus.CREATED)
        .body(subscriptionService.create(form));
}
~~~

The project needs the corresponding Bean Validation dependency, typically `spring-boot-starter-validation`. Spring checks constraints before calling the service. If the data is invalid, an exception or `BindingResult` is handled by Spring MVC's validation mechanism.

### Handling binding and validation errors

With `@ModelAttribute`, if you want to construct the response directly inside the controller, place `BindingResult` immediately after the validated parameter:

~~~java
@PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
public ResponseEntity<?> create(
        @Valid @ModelAttribute SubscriptionForm form,
        BindingResult bindingResult) {

    if (bindingResult.hasErrors()) {
        Map<String, String> errors = bindingResult.getFieldErrors().stream()
            .collect(Collectors.toMap(
                FieldError::getField,
                error -> error.getDefaultMessage() == null
                    ? "Invalid value"
                    : error.getDefaultMessage(),
                (first, ignored) -> first
            ));

        return ResponseEntity.badRequest()
            .body(new ApiError("VALIDATION_FAILED", errors));
    }

    SubscriptionResponse created = subscriptionService.create(form);
    return ResponseEntity.status(HttpStatus.CREATED).body(created);
}
~~~

This illustrative snippet requires the `ApiError` type and appropriate imports. If `BindingResult` is not placed immediately after the model attribute, Spring typically translates binding/validation errors into an exception for centralized handling. A `@RestControllerAdvice` can standardize error responses across endpoints.

Distinguish missing-field errors, type-conversion errors, and business errors. For instance, an invalid email format is validation; a non-existent plan code may be a business error; a user lacking permission to subscribe to a plan is an authorization error. Choose stable status codes and error codes for each category.

## 7. Multiple values for the same field name

An HTML form can send multiple values under the same `name`, commonly seen with checkboxes or multi-select inputs:

~~~html
<label><input type="checkbox" name="topics" value="spring"> Spring</label>
<label><input type="checkbox" name="topics" value="java"> Java</label>
<label><input type="checkbox" name="topics" value="api"> API</label>
~~~

The body can take the form:

~~~text
topics=spring&topics=java&topics=api
~~~

Spring MVC can bind repeated values into a collection:

~~~java
@PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
public PreferencesResponse save(
        @RequestParam List<String> topics) {
    return preferencesService.save(topics);
}
~~~

If you need to preserve all values under every name or handle dynamic forms, you can accept `MultiValueMap<String, String>`. Specify clearly which fields are repeatable, whether empty lists are allowed, and element count limits.

With HTML checkboxes, browsers normally send only checked boxes. If no value is selected, the key may be completely absent. The DTO or controller should define how a missing field is interpreted, such as an empty list or a validation error.

## 8. Describing `form-urlencoded` in OpenAPI

In OpenAPI, a `form-urlencoded` request body is declared in `requestBody.content` with the exact media type `application/x-www-form-urlencoded`. The schema is typically an object whose properties correspond to the form fields:

~~~yaml
paths:
  /api/subscriptions:
    post:
      summary: Subscribe to a service plan
      requestBody:
        required: true
        description: Subscription data sent as a form
        content:
          application/x-www-form-urlencoded:
            schema:
              type: object
              required:
                - email
                - plan
              properties:
                email:
                  type: string
                  format: email
                  example: dev@example.com
                plan:
                  type: string
                  enum: [basic, pro]
                note:
                  type: string
                  maxLength: 250
            examples:
              subscription:
                summary: Subscribe to Pro plan
                value:
                  email: dev@example.com
                  plan: pro
                  note: Contact in the afternoon
      responses:
        '201':
          description: Subscription created
        '400':
          description: Invalid form data
~~~

In Swagger UI, the request body is rendered as individual form fields instead of a single JSON text box. Integrators can see field names, data types, required fields, limits, and examples.

### Schema and encoding

For standard scalar fields, OpenAPI can rely on default form serialization. If you need to specify how a complex property is encoded, you can declare `encoding`:

~~~yaml
requestBody:
  required: true
  content:
    application/x-www-form-urlencoded:
      schema:
        type: object
        properties:
          topics:
            type: array
            items:
              type: string
      encoding:
        topics:
          style: form
          explode: true
~~~

With `style: form` and `explode: true`, an array is typically represented by repeating the key, such as `topics=spring&topics=java`. The Encoding Object allows describing how properties are serialized when defaults are insufficient. Check the output of client generator tools, as serialization support can vary.

Do not confuse OpenAPI's `encoding` with the charset or content type of the entire request. `encoding` here describes how each property is represented inside the form media type.

## 9. Declaring `form-urlencoded` request bodies with `springdoc-openapi`

Springdoc can infer a lot of information from mappings, parameters, and DTOs. However, with `@ModelAttribute`, depending on the version and declaration style, properties may be represented as parameters. If the contract must clearly show a `form-urlencoded` request body, declare the media type and schema explicitly using OpenAPI annotations.

Example:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SubscriptionController {

    @Operation(
        summary = "Subscribe to a service plan",
        requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
            description = "Subscription form fields",
            required = true,
            content = @Content(
                mediaType = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
                schema = @Schema(implementation = SubscriptionForm.class)
            )
        )
    )
    @PostMapping(
        path = "/api/subscriptions",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<SubscriptionResponse> create(
            @Valid @ModelAttribute SubscriptionForm form) {

        SubscriptionResponse created = subscriptionService.create(form);
        return ResponseEntity.status(HttpStatus.CREATED).body(created);
    }
}
~~~

Here there are two annotations with different roles:

- `io.swagger.v3.oas.annotations.parameters.RequestBody` sits in the `requestBody` attribute of `@Operation` to describe the OpenAPI contract.
- Spring MVC's `@ModelAttribute` binds request parameters into the DTO at runtime.

Do not replace `@ModelAttribute` with Spring's `@RequestBody` annotation merely to make Swagger UI display a body. Doing so alters how the application reads data and may not suit how the Servlet container parses forms.

After running the application, open `/v3/api-docs` and confirm the operation has `requestBody.content.application/x-www-form-urlencoded` with the `SubscriptionForm` schema. If springdoc also generates duplicate query parameters matching the form fields, adjust how model attribute parameters are documented for your version and re-check the generated JSON. The final specification should have a single unambiguous representation for body data.

With springdoc versions that infer `@ModelAttribute` into individual parameters, you can hide that inference on the Spring parameter with `@Parameter(hidden = true)` while keeping the explicitly declared `requestBody` in `@Operation`:

~~~java
import io.swagger.v3.oas.annotations.Parameter;

@Operation(
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        content = @Content(
            mediaType = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
            schema = @Schema(implementation = SubscriptionForm.class)
        )
    )
)
@PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
public ResponseEntity<SubscriptionResponse> create(
        @Parameter(hidden = true)
        @Valid @ModelAttribute SubscriptionForm form) {
    // Process form and return response.
}
~~~

This workaround depends on the actual generated specification, not a mandatory annotation for every project. Inspect the generated JSON to ensure `requestBody` remains intact and fields are not duplicated under `parameters`.

### Describing responses alongside the request body

You can combine the request body with success and error responses:

~~~java
@Operation(
    summary = "Subscribe to a service plan",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        content = @Content(
            mediaType = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
            schema = @Schema(implementation = SubscriptionForm.class)
        )
    )
)
@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Subscription created",
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = SubscriptionResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "400",
        description = "Invalid form data",
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = ApiError.class)
        )
    )
})
~~~

This snippet supplements the operation in the previous example. Ensure actual responses share the same status codes, media types, and body schemas as described. Annotations only generate OpenAPI metadata and do not change HTTP responses themselves.

## 10. Verifying the generated OpenAPI structure

A proper `form-urlencoded` operation typically has a structure like:

~~~yaml
paths:
  /api/subscriptions:
    post:
      requestBody:
        required: true
        content:
          application/x-www-form-urlencoded:
            schema:
              $ref: '#/components/schemas/SubscriptionForm'
      responses:
        '201':
          description: Subscription created
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/SubscriptionResponse'
        '400':
          description: Invalid form data
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ApiError'
~~~

Check the following points in the JSON/YAML:

- Request body has the `application/x-www-form-urlencoded` media type.
- Schema is an object with field names matching the HTML form and DTO.
- Required fields appear in `required`; optional fields are not mistakenly marked required.
- Data types, formats, enums, and limits match validation rules.
- Responses have accurate status codes, media types, and schemas.
- No duplicate query parameters appear for fields already described in the body, unless the API genuinely accepts them in the query too.

Swagger UI should display the corresponding form fields. If the UI still displays a JSON box, inspect the content type in the OpenAPI JSON first; Swagger UI renders strictly from the specification it receives.

### Difference between `requestBody` and `parameters`

A `form-urlencoded` POST has a body in OpenAPI:

~~~yaml
requestBody:
  content:
    application/x-www-form-urlencoded:
      schema:
        type: object
        properties:
          email:
            type: string
~~~

Query parameters live in the URL and are declared under `parameters`:

~~~yaml
parameters:
  - name: page
    in: query
    required: false
    schema:
      type: integer
~~~

A request can have both query parameters and a form body. For instance, `POST /api/subscriptions?source=campaign` can accept `source` in the query and `email`, `plan` in the body. Describe them in their respective locations so clients send accurate requests.

## 11. Distinguishing `form-urlencoded` from `multipart/form-data` and JSON

Choose the media type according to the data shape:

| Format | Structure | When to use |
|---|---|---|
| `application/x-www-form-urlencoded` | URL-encoded key/value pairs | Forms with text, numeric, or choice fields |
| `multipart/form-data` | Multiple parts, each with its own headers | Forms containing files or binary data |
| `application/json` | JSON object or array | APIs exchanging nested data structures |

For forms with files, use `multipart/form-data`:

~~~java
@PostMapping(
    path = "/api/documents",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
public DocumentResponse upload(
        @RequestPart("title") String title,
        @RequestPart("file") MultipartFile file) {
    return documentService.upload(title, file);
}
~~~

OpenAPI describes multipart with the `multipart/form-data` media type and a schema with matching properties. Do not use `application/x-www-form-urlencoded` to send standard binary files.

JSON is better suited when bodies have deeply nested objects, complex data types, or structures requiring clear typing. Form-urlencoded suits traditional HTML forms and APIs requiring key/value formatting. Do not pick a media type solely because the controller can bind it; choose based on the contract clients should send.

## 12. Caveats when binding form data

### Avoid binding entities directly

Do not bind entire persistence entities directly from requests:

~~~java
// Avoid: clients can send unexpected entity fields.
public ResponseEntity<?> update(@ModelAttribute UserEntity user) {
    // ...
}
~~~

Use a DTO containing only fields the client is allowed to submit. If an entity has properties like `role`, `accountStatus`, `ownerId`, or `internalFlag`, automatic binding can introduce mass assignment risks if those fields are altered unintentionally.

~~~java
public record UpdateProfileForm(
    @NotBlank String displayName,
    @Email String contactEmail
) {}
~~~

The controller only accepts fields defined in the DTO:

~~~java
@PostMapping(
    path = "/api/profile",
    consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
)
public ProfileResponse updateProfile(
        @Valid @ModelAttribute UpdateProfileForm form) {
    return profileService.updateCurrentUser(form);
}
~~~

### Controlling bindable fields

With setter-based DTOs and custom data binders, Spring MVC allows configuring allowed fields via `@InitBinder`. This provides an extra layer of protection when you need to restrict exactly which properties are bound:

~~~java
@InitBinder("profileForm")
void configureProfileBinder(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "contactEmail");
}
~~~

The object name in `@InitBinder` must match the model attribute name. For example, you can name it explicitly via `@ModelAttribute("profileForm")`. Even with allowed fields, still use a dedicated DTO with a small data surface; do not use the binder as an excuse to bind large entities.

### Empty values, missing fields, and checkboxes

The following states can behave differently:

- Field does not appear in the body.
- Field appears with an empty value, such as `note=`.
- Field appears with whitespace, such as `note=+++`.
- Field appears multiple times under the same name.

Validation rules like `@NotNull`, `@NotBlank`, and `@NotEmpty` handle these situations differently. `@NotBlank` is suitable for strings that must not be empty or whitespace-only. For collections, define explicitly whether a missing list means no items selected or an invalid request.

### Type conversion and date/time formats

Forms transmit values as strings. Spring must convert strings to target types. For dates, decimals, or enums, specify clear formats and test both valid and malformed values. Example:

~~~java
public record BookingForm(
    @NotNull
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    LocalDate startDate,
    @NotNull
    Integer guestCount
) {}
~~~

In OpenAPI, describe dates as `string` with format `date`, and guest count as `integer` with an appropriate minimum. Do not leave clients guessing date formats from browser or server locales.

## 13. Security when receiving form data

Form-urlencoded often appears in browser applications using session cookies. In that context, pay attention to:

- Enable and use Spring Security's CSRF protection for state-changing requests sent by browsers using cookies. Never disable CSRF just to make a form work.
- Use HTTPS to protect data in transit. URL encoding is not security encryption.
- Never put passwords, tokens, or sensitive data in query strings. Form bodies are not automatically safe either: proxies, application logs, or monitoring systems can still record bodies.
- Limit request size, field count, and value lengths to guard against oversized requests.
- Bind only fields clients are permitted to control; never trust `role`, `owner`, or permission states submitted by a form.
- Avoid logging entire forms if they contain personal information or secrets.

If the API is called by non-cookie clients using bearer tokens, configure authentication accordingly. How CSRF is handled depends on the authentication mechanism and browser context; follow the application's security model rather than broadly disabling protection.

## 14. Testing `form-urlencoded` endpoints

Tests must verify both binding and responses. With Spring MVC, `MockMvc` can simulate request parameters alongside content types:

~~~java
@WebMvcTest(SubscriptionController.class)
class SubscriptionControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    SubscriptionService subscriptionService;

    @Test
    void acceptsFormUrlEncodedFields() throws Exception {
        given(subscriptionService.create(any(SubscriptionForm.class)))
            .willReturn(new SubscriptionResponse(42L, "dev@example.com", "pro"));

        mockMvc.perform(post("/api/subscriptions")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .accept(MediaType.APPLICATION_JSON)
                .param("email", "dev@example.com")
                .param("plan", "pro")
                .param("note", "Spring Boot"))
            .andExpect(status().isCreated())
            .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.id").value(42));
    }

    @Test
    void rejectsInvalidEmail() throws Exception {
        mockMvc.perform(post("/api/subscriptions")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", "not-an-email")
                .param("plan", "pro"))
            .andExpect(status().isBadRequest());
    }
}
~~~

This example tests binding via MockMvc request parameters; `.param(...)` populates parameters in the mock request and does not itself verify how a browser URL-encodes a raw body. To validate the full `form-urlencoded` body pipeline, add integration tests sending an actual encoded body string via an HTTP client or running the application on a random port.

Example real request:

~~~bash
curl -i http://localhost:8080/api/subscriptions -H "Content-Type: application/x-www-form-urlencoded" -H "Accept: application/json" --data-urlencode "email=dev@example.com" --data-urlencode "plan=pro" --data-urlencode "note=Spring Boot & OpenAPI"
~~~

Verify status `201`, response `Content-Type`, JSON body, and properly decoded values. Next, submit missing data, invalid emails, out-of-enum plans, Vietnamese characters, plus signs, ampersands, repeated fields, and wrong media type bodies to verify error handling.

### Verifying the springdoc specification

Within the same test context, you can call the OpenAPI endpoint and assert the content type:

~~~java
mockMvc.perform(get("/v3/api-docs"))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$.paths['/api/subscriptions'].post.requestBody.content['application/x-www-form-urlencoded']"
    ).exists());
~~~

The JSONPath above illustrates asserting the media type. You can inspect schema properties, `required`, and response codes even more deeply. If the app uses `GroupedOpenApi`, call the documentation endpoint of the group containing the operation.

## 15. Common errors and fixes

| Symptom | Possible cause | Fix |
|---|---|---|
| Received `415 Unsupported Media Type` | Client sent a Content-Type not accepted by the endpoint | Send `application/x-www-form-urlencoded` and declare `consumes` properly |
| DTO receives no values | Form field name mismatches property name or binder cannot instantiate DTO | Check `name`, getters/setters, or constructor binding |
| Plus sign turns into a space | Plus sign was not encoded when it is literal data | Encode literal plus signs as `%2B` |
| `&` splits a field | Value was not URL-encoded | Use `--data-urlencode` or the client's URL encoder |
| Checkbox list is missing | Browsers do not send unchecked checkboxes | Explicitly define whether a missing field means empty list or error |
| Swagger UI displays body as JSON | OpenAPI content has not declared `form-urlencoded` | Inspect `requestBody.content` in `/v3/api-docs` |
| Form fields appear as query parameters | Springdoc inferred `@ModelAttribute` differently than expected | Declare `requestBody` explicitly and inspect final specification |
| Validation does not run | Missing `@Valid`, constraints, or validation dependency | Add Bean Validation and inspect handler |
| Request rejected due to CSRF | CSRF token missing or invalid | Send token per Spring Security mechanism; keep CSRF protection enabled |
| Unexpected fields get updated | Entity bound directly or DTO exposes too many setters | Use a dedicated request DTO and restrict bindable fields |

## 16. Comprehensive practice exercise

Build a newsletter subscription endpoint:

1. Create `SubscriptionForm` with `email`, `plan`, `note`, and a `topics` list.
2. Apply `@NotBlank`, `@Email`, `@Size`, and appropriate enum/validation rules.
3. Create a POST endpoint with `consumes = application/x-www-form-urlencoded`.
4. Bind the DTO using `@ModelAttribute` and return `201 Created` on subscription creation.
5. Handle binding and validation errors as a consistent error response.
6. Declare the OpenAPI request body with the `form-urlencoded` media type, schema, and examples.
7. Confirm Swagger UI displays the proper fields, enums, and required fields.
8. Send requests using curl with spaces, Vietnamese characters, plus signs, and `&`.
9. Write MockMvc tests for valid data, missing fields, and invalid formats.
10. Verify CSRF if the endpoint is called by browsers using session cookies.
11. Compare the OpenAPI JSON against actual requests/responses and fix any mismatches.

### Completion criteria

- [ ] Endpoint accepts only the published media type.
- [ ] Spring binds form fields accurately to the DTO or parameters.
- [ ] Special characters and Unicode are URL-encoded and decoded accurately.
- [ ] Required, optional, and repeatable fields follow clear conventions.
- [ ] Bean Validation executes server-side and returns structured errors.
- [ ] OpenAPI declares `application/x-www-form-urlencoded` in `requestBody`.
- [ ] Swagger UI displays form fields instead of a JSON body box.
- [ ] Tests verify binding, validation, status codes, and response bodies.
- [ ] No sensitive data leaks via DTOs, logs, or query strings.

## Further reading

After this lesson, continue with `multipart/form-data` for file uploads, JSON request bodies, and how to describe `encoding` and examples in OpenAPI. When designing form-accepting endpoints, align three pieces: HTML field names, Spring MVC DTO/binding, and the `requestBody` schema in the specification. When all three agree, clients can send accurate data and the API documentation reflects the application's actual behavior.
