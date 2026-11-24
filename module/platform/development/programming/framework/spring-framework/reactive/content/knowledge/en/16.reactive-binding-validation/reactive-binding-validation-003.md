# Constructor Binding and Restricting Updatable Properties in Spring WebFlux

## 1. The security problem: mass assignment / over-posting

A controller usually receives client-sent data to create or update a resource. If Spring binds the request directly into an object that has more properties than the endpoint allows, a client can try sending extra fields that the normal UI does not display.

An example account entity:

~~~java
public class Account {
    private Long id;
    private String displayName;
    private String email;
    private String role;
    private boolean enabled;
    private boolean emailVerified;
    private Long ownerId;

    // getters and setters
}
~~~

The endpoint is only meant to let users change their name and email:

~~~text
POST /accounts/42/edit

displayName=Alice
email=alice@example.com
role=ADMIN
enabled=true
ownerId=1
~~~

If the request is bound directly into an object that has setters for all properties, fields such as `role`, `enabled`, or `ownerId` can be changed even though the feature is only meant to allow editing the name and email. This class of bug is commonly called **mass assignment**, **over-posting**, or **broken object property level authorization**.

It is important to distinguish three questions:

1. **Binding**: which values did the client send, and how does Spring put them into the object?
2. **Validation**: are the values in the right format and do they follow the data rules?
3. **Authorization / business rules**: does the current user have permission to modify that property or resource?

A value that is valid in type and validation can still be **not allowed to be updated**. For example, the string `ADMIN` is a valid role, but an ordinary user does not have permission to assign that role to themselves.

Spring provides two important tools to control binding:

- **Constructor binding**: creates the object only from the parameters that the constructor declares.
- **`WebDataBinder.setAllowedFields(...)`**: uses an allowlist to restrict which properties may receive data when property/setter binding is enabled.

For web data, prefer a DTO dedicated to the request and an immutable constructor; if you truly need property binding, declare a specific allow list.

## 2. Which kinds of requests does data binding in WebFlux apply to?

In an annotated controller, `@ModelAttribute` is the common entry point for data binding. Spring WebFlux can bind the following sources into a model object:

- Form data, for example `application/x-www-form-urlencoded`.
- Query parameters in the URL.
- URI path variables.
- Request headers according to Spring's binding rules.

When sources share the same name, **form data and query parameters take precedence over URI variables and headers**; URI variables and headers are used only when they are not overridden by a request parameter of the same name. Header names are handled by removing hyphens.

Example:

~~~java
@PostMapping("/tenants/{tenantId}/profile")
Mono<String> update(
        @ModelAttribute ProfileForm form) {
    return Mono.just(form.toString());
}
~~~

With `@ModelAttribute`, Spring creates or retrieves the model object, then binds the matching request values into that object.

**Do not confuse `@ModelAttribute` with `@RequestBody`.**

| Way of receiving data | Main mechanism | Example |
| --- | --- | --- |
| `@ModelAttribute` | `WebDataBinder`: constructor binding and/or property binding | Form, query parameter, URI variable, header |
| `@RequestBody` | `HttpMessageReader` and HTTP message codecs to decode the body | JSON/XML to DTO |
| `@RequestParam` | Binds one query parameter (or a map of query parameters) | `?page=2` |
| `@PathVariable` | Gets the value of a URI template variable | `/orders/{id}` |

**`allowedFields` is a WebDataBinder setting for property binding of a model attribute. It is not an automatic allowlist for JSON decoded through `@RequestBody`.** For JSON, you still need a dedicated request DTO, control over the deserialized data types, and explicit mapping to a command/domain object.

In functional endpoints, WebFlux has the `ServerRequest.bind` API and corresponding overloads for binding data. The principles of object design and input restriction still need to be applied at that boundary.

## 3. Two binding strategies: constructor and property

Spring's `DataBinder` supports two ways of creating/updating an object.

### 3.1. Constructor binding

Constructor binding takes request values by constructor parameter name and then calls the constructor to create the object. With a Java record:

~~~java
public record ChangeEmailForm(
        String currentEmail,
        String newEmail) {
}
~~~

Spring can create the object from the `currentEmail` and `newEmail` values. Other request parameters such as `role` or `enabled` are not constructor parameters, so they are not put into the object through constructor binding.

Constructor binding suits an object that:

- Has immutable state after creation.
- Has a constructor that declares exactly the set of data the client is allowed to provide.
- Has no public setters that would let a request change other properties after creation.
- Is designed specifically for one use case, for example `ChangeEmailForm`, `CreateOrderCommand`, or `UpdateDisplayNameRequest`.

Spring can bind into a Java record or a class with a suitable constructor. Constructor binding also supports nested objects; nested values are created recursively according to the property path. Parameters of type `List`, `Map`, and array can be converted from a single string or received through index/entry-style keys such as `items[2].name` and `labels[locale]`.

**Constructor binding does not verify business permissions on its own.** If you put `role` into the constructor of a DTO meant for ordinary users, you have widened the input contract. Declare only the fields the endpoint truly accepts.

### 3.2. Property binding

Property binding creates the object (usually with a no-argument constructor), then assigns values to JavaBean properties through setters.

~~~java
public class ChangeEmailForm {
    private String currentEmail;
    private String newEmail;

    public String getCurrentEmail() {
        return currentEmail;
    }

    public void setCurrentEmail(String currentEmail) {
        this.currentEmail = currentEmail;
    }

    public String getNewEmail() {
        return newEmail;
    }

    public void setNewEmail(String newEmail) {
        this.newEmail = newEmail;
    }
}
~~~

Property binding is flexible for traditional forms, but if the target object has many setters, a request can try to assign additional properties that do not belong to the form. This is why you must use a narrowly scoped DTO or an allowlist.

### 3.3. By default Spring applies both

By default, `DataBinder` applies **constructor binding and property binding**. That means creating only an immutable constructor object is not enough if you also put a mutable bean with many setters into the same binding path.

For clearer control, Spring has `declarativeBinding`:

~~~java
@InitBinder
void initBinder(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
~~~

When `declarativeBinding` is enabled:

- **Constructor binding is always applied.**
- **Property/setter binding is applied only when `allowedFields` is configured.**

This is a useful mechanism for accepting, by default, only the inputs declared through the constructor; if a specific form needs setter binding, open it with its own allowlist.

## 4. Designing immutable DTOs for constructor binding

A good request DTO should express exactly the input contract of the endpoint.

Example:

~~~java
public record CreateProfileForm(
        String displayName,
        String email) {
}
~~~

This DTO accepts only `displayName` and `email`. If the Account entity also has `id`, `role`, `enabled`, `ownerId`, those properties do not appear in the constructor, so the client cannot control them through the DTO.

After binding, the service can create a domain command or invoke the business logic:

~~~java
@PostMapping("/profiles")
Mono<ProfileResponse> create(
        @Valid @ModelAttribute CreateProfileForm form) {

    CreateProfileCommand command =
            new CreateProfileCommand(
                    form.displayName(),
                    form.email());

    return profileService.create(command);
}
~~~

This is an **illustrative snippet**, assuming `ProfileResponse`, `CreateProfileCommand`, and `profileService` exist. Do not map a request directly into a persistence entity if the entity contains internal or permission-related properties.

### 4.1. Constructor parameter names and `-parameters`

By default, Spring looks up values by constructor parameter name. To keep parameter names in the bytecode, the compiler needs to store parameter-name metadata (for example the `-parameters` flag).

With the Maven Compiler Plugin, you can configure:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <maven.compiler.parameters>true</maven.compiler.parameters>
</properties>
~~~

When the request name differs from the Java name, use `@BindParam`:

~~~java
public record CreateProfileForm(
        @BindParam("display-name") String displayName,
        @BindParam("email-address") String email) {
}
~~~

The client sends:

~~~text
display-name=Alice
email-address=alice@example.com
~~~

Spring maps `display-name` to the constructor argument `displayName` and `email-address` to `email`. `@BindParam` can be placed on the constructor parameter or the corresponding field; this is an annotation in `org.springframework.web.bind.annotation`.

If you need a system-wide naming rule, `DataBinder` also supports a `NameResolver` to determine the lookup name of a constructor argument. For most applications, an explicit `@BindParam` is easier to inspect.

### 4.2. Nested constructors and collections

Constructor binding can create nested objects:

~~~java
public record AddressForm(
        String city,
        String postalCode) {
}

public record CreateCustomerForm(
        String name,
        AddressForm address) {
}
~~~

The request can use the corresponding property paths such as `name`, `address.city`, and `address.postalCode`.

Collections can also receive values in a structured form:

~~~text
tags=java,reactive,spring
addresses[0].city=Hanoi
addresses[1].city=DaNang
labels[locale]=vi-VN
~~~

Remember that a nested DTO is also part of the input contract. Do not put a broad domain object or an unbounded collection into a constructor just because Spring can bind it. Limit the size, the number of elements, and the nested structure according to the endpoint's needs.

## 5. `declarativeBinding` and combining constructors with an allowlist

A commonly used configuration:

~~~java
@Controller
class ProfileController {

    @InitBinder
    void enableDeclarativeBinding(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
    }
}
~~~

In that case:

| Target object | `allowedFields` | Behavior |
| --- | --- | --- |
| Immutable record with a constructor | Not needed | Constructor binding creates the object |
| DTO with a clear constructor | Not needed for constructor inputs | Only constructor parameters are used to create the object |
| Mutable bean with a no-arg constructor and setters | None | Property binding is disabled when declarative binding is on |
| Mutable bean with a no-arg constructor and setters | Has an allowlist | Property binding accepts only the allowed properties |

**Important point:** `allowedFields` restricts **property binding**; it is not a list that excludes constructor parameters. If your constructor accepts `role`, then `role` is still a valid constructor input even if the property allowlist does not contain `role`. Therefore, the constructor DTO must still be designed with the right scope.

A global declarative configuration can be placed in a `@ControllerAdvice` to apply to many controllers. However, you need to check the advice's scope and the model attributes that use setter binding; the safe approach is to enable an allowlist only for the specific form that needs property binding.

## 6. Restricting property binding with `setAllowedFields`

If you must use a mutable bean, declare a **positive allowlist**:

~~~java
@Controller
class ChangeEmailController {

    @InitBinder("changeEmailForm")
    void initBinder(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
        binder.setAllowedFields(
                "currentEmail",
                "newEmail");
    }
}
~~~

In this example:

- `changeEmailForm.currentEmail` is allowed to bind.
- `changeEmailForm.newEmail` is allowed to bind.
- Other properties not in the allowlist are not bound by property binding.
- Field names are matched **case-sensitively**.

The name in `@InitBinder("changeEmailForm")` must correspond to the model attribute name:

~~~java
@PostMapping("/change-email")
Mono<String> change(
        @ModelAttribute("changeEmailForm")
        ChangeEmailForm form) {
    // ...
}
~~~

If you omit the model attribute name, the binder can apply to the model attributes within the controller's scope. A named configuration helps avoid accidentally applying one form's allowlist to another form.

### 6.1. Scope of `@InitBinder`

- Place `@InitBinder` in a `@Controller` to apply it in that controller.
- Use `@InitBinder("attributeName")` to restrict by model attribute name.
- Place it in a `@ControllerAdvice` to share the configuration across multiple matching controllers.
- Each request uses its own `WebDataBinder`; binder configuration is not a mutable object shared across all requests.

With global configuration, consider every form within the advice's scope. An allowlist that suits `ProfileEditForm` can break the binding of `SearchForm` if applied by mistake.

### 6.2. Property paths and wildcards

`allowedFields` supports property paths, not just top-level field names.

| Pattern | Meaning |
| --- | --- |
| `displayName` | The top-level property `displayName` |
| `address.city` | The `city` property in the `address` object |
| `addresses[0].city` | The `city` property of the element at index 0 |
| `labels[locale]` | The entry with key `locale` in the `labels` map |
| `labels*` | The entries/indexes of the `labels` property by wildcard |
| `*Address` | Property names ending in `Address` |

The `*` wildcard follows Spring's pattern rules, **not an arbitrary regex**. Nested, indexed, and map property paths use the same syntax as JavaBean property read/write operations.

For sensitive data, prefer specific property names:

~~~java
binder.setAllowedFields(
        "displayName",
        "address.city",
        "address.postalCode");
~~~

Avoid broad allowlists such as `*`, `account*`, or `*Id` if the endpoint does not really need every matching property. A wildcard can accidentally widen binding permissions when fields are added to the DTO in the future.

### 6.3. Why is an allowlist better than a denylist?

You can configure `setDisallowedFields` to list the forbidden fields, but a denylist is easy to leave gaps in: when the domain object gains a new field, the new field can automatically become input if it is not added to the deny list.

**An allowlist describes exactly what the endpoint permits.** The current Spring Framework documentation notes that `disallowedFields` is deprecated in Spring Framework 7.1 because it easily drifts out of step with the actual properties over time. Prefer `setAllowedFields` and small-scope DTOs.

## 7. Checking blocked fields

When property binding encounters a field that is not in the allowlist, the binder removes that field from the property values list and records it in the `BindingResult` as a suppressed field.

Example:

~~~java
@PostMapping("/edit")
Mono<ResponseEntity<?>> edit(
        @Valid @ModelAttribute("profileEditForm")
        ProfileEditForm form,
        BindingResult result) {

    String[] suppressed = result.getSuppressedFields();

    if (suppressed.length > 0) {
        // A request tried to bind a field that is not allowed.
    }

    // ...
}
~~~

`BindingResult.getSuppressedFields()` is useful for:

- Detecting that a client sent fields outside the allowlist.
- Writing security logs at an appropriate level.
- Rejecting the request if the contract requires that there be no extra fields.
- Writing tests that confirm `role` or `enabled` was blocked.

**Distinguishing constructor binding and property binding:** parameters not used in constructor binding are ignored because they are not constructor arguments. Do not assume that every extra parameter ignored by constructor binding will appear in `getSuppressedFields()`. The suppressed fields list reflects fields blocked during property binding.

If the API needs to reject every unknown key even when only constructor binding is used, you need a separate step that checks the input keys against the contract or a suitable request validation mechanism. Constructor binding protects the object from having properties outside the constructor assigned, but it is not by itself a system for detecting every extra parameter.

## 8. Binding, conversion, and validation are three different steps

A request can fail at several stages:

1. **Binding**: Spring determines which input goes into the model object.
2. **Type conversion**: converts a string to a Java type, for example `"42"` to `Long`.
3. **Validation**: checks data constraints, for example `@NotBlank`, `@Email`, `@Size`, or a custom validator.

Example:

~~~java
public record CreateProfileForm(
        @NotBlank
        @Size(max = 80)
        String displayName,

        @NotBlank
        @Email
        String email) {
}
~~~

Controller:

~~~java
@PostMapping("/profiles")
Mono<String> create(
        @Valid @ModelAttribute CreateProfileForm form) {
    return Mono.just("accepted:" + form.displayName());
}
~~~

`@Valid` triggers validation after binding. It **does not replace an allowlist** and does not confirm that the user has permission to modify the property.

In WebFlux, if binding/validation fails and there is no `BindingResult` immediately following the `@ModelAttribute` argument, a `WebExchangeBindException` is raised by default. You can declare a `BindingResult` immediately after the model attribute to handle errors in the controller:

~~~java
@PostMapping("/profiles")
Mono<String> create(
        @Valid @ModelAttribute CreateProfileForm form,
        BindingResult result) {

    if (result.hasErrors()) {
        return Mono.error(
                new IllegalArgumentException("Invalid form"));
    }

    return Mono.just("accepted");
}
~~~

This is an illustrative example; a real application should translate the error into an appropriate 400 response via an error handler/advice or return a structured error response. You should not throw a generic exception just for illustration in production.

If you use a reactive wrapper such as `@ModelAttribute Mono<Account>`, WebFlux also supports that reactive type; binding errors can be handled in the pipeline in a suitable way.

## 9. Constructor binding does not replace authorization

Even when the DTO accepts exactly two fields, the service must still verify permission on the resource.

Example:

~~~java
Mono<Profile> update(
        Long profileId,
        ChangeEmailForm form,
        AuthenticatedUser currentUser) {

    return profileRepository.findById(profileId)
        .switchIfEmpty(Mono.error(new ProfileNotFoundException()))
        .flatMap(profile ->
            authorizationService
                .checkCanChangeEmail(currentUser, profile)
                .then(profileService.changeEmail(
                        profile, form.newEmail())));
}
~~~

This is **illustrative code**; the services and exceptions need to be defined. The fact that the constructor does not accept `role` does not prove that the user has permission to change the email of the specified profile.

Principles:

- Do not accept `ownerId`, `tenantId`, `role`, `enabled`, or `emailVerified` from an ordinary form if the user is not allowed to decide them.
- Get the current user from the authenticated security context; do not trust permission IDs sent by the client.
- Check permission on the specific resource in the service/use case.
- Use a separate DTO for each operation: `CreateAccountForm`, `ChangeEmailForm`, `AdminChangeRoleCommand`.
- Only a protected admin endpoint should accept admin fields; authorization still needs to check the current role.

**An allowlist is one defensive layer of binding, not the entire authorization model.**

## 10. `@ModelAttribute` is not a mechanism for restricting the fields of a JSON `@RequestBody`

A common configuration mistake is adding:

~~~java
@InitBinder
void initBinder(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "email");
}
~~~

and then thinking that every JSON body in the controller is restricted to two fields. That is not correct: `@RequestBody` in WebFlux is decoded by `HttpMessageReader`/codecs, and does not go through the same `@ModelAttribute` data binding process.

For JSON, you should use an explicit DTO:

~~~java
public record UpdateProfileJson(
        @NotBlank String displayName,
        @Email String email) {
}

@PostMapping(path = "/profiles/json",
             consumes = MediaType.APPLICATION_JSON_VALUE)
Mono<ProfileResponse> updateJson(
        @Valid @RequestBody UpdateProfileJson request) {
    // Map the request to a business command.
}
~~~

This is an illustrative example; you need to define `ProfileResponse` and the service mapping. The record's fields create the JSON input structure that the endpoint supports. Do not put an entity with administrative privileges into a `@RequestBody` parameter just because Jackson can deserialize it.

If you need to reject JSON with unknown fields, configure the unknown-property policy of the JSON codec/ObjectMapper appropriately for your application and test it; `WebDataBinder`'s `allowedFields` does not do that by itself.

## 11. A runnable Java 17+ Spring Boot WebFlux program

This example demonstrates two endpoints:

1. `POST /api/profiles/create` uses **record constructor binding**. The request only creates `CreateProfileForm` from two constructor arguments.
2. `POST /api/profiles/{id}/edit` uses a **mutable form + allowlist**. Only `displayName` and `email` are property-bound; `role` and `enabled` are suppressed.

Requirements: **JDK 17+**, **Maven 3.6.3+**, **Spring Boot 4.1.2**. The Boot BOM manages the versions of Spring Framework and the accompanying libraries.

Project structure:

~~~text
webflux-binding-demo/
  pom.xml
  src/main/java/example/binding/BindingDemoApplication.java
  src/main/java/example/binding/ProfileController.java
~~~

### 11.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>webflux-binding-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
        <maven.compiler.parameters>true</maven.compiler.parameters>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
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

### 11.2. Startup application

**src/main/java/example/binding/BindingDemoApplication.java**

~~~java
package example.binding;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BindingDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(BindingDemoApplication.class, args);
    }
}
~~~

### 11.3. Controller, records, and mutable form

**src/main/java/example/binding/ProfileController.java**

~~~java
package example.binding;

import java.util.Arrays;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.BindParam;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/profiles")
public class ProfileController {

    // Enable declarative binding for the model attributes in the controller.
    @InitBinder
    void enableDeclarativeBinding(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
    }

    // Allow property binding for only the two fields of the edit form.
    @InitBinder("profileEditForm")
    void configureProfileEdit(WebDataBinder binder) {
        binder.setAllowedFields("displayName", "email");
    }

    public record CreateProfileForm(
            @BindParam("display-name")
            @NotBlank
            @Size(max = 80)
            String displayName,

            @BindParam("email-address")
            @NotBlank
            @Email
            String emailAddress) {
    }

    public record CreateResponse(
            String displayName,
            String emailAddress) {
    }

    public record EditResponse(
            long id,
            String displayName,
            String email,
            String role,
            boolean enabled) {
    }

    public record ErrorResponse(
            String error,
            List<String> details,
            List<String> suppressedFields) {
    }

    public static class ProfileEditForm {
        @NotBlank
        @Size(max = 80)
        private String displayName;

        @NotBlank
        @Email
        private String email;

        // Internal fields that are not in the allowlist.
        private String role = "USER";
        private boolean enabled;

        public ProfileEditForm() {
        }

        public String getDisplayName() {
            return displayName;
        }

        public void setDisplayName(String displayName) {
            this.displayName = displayName;
        }

        public String getEmail() {
            return email;
        }

        public void setEmail(String email) {
            this.email = email;
        }

        public String getRole() {
            return role;
        }

        public void setRole(String role) {
            this.role = role;
        }

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }
    }

    @PostMapping(
            path = "/create",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Mono<ResponseEntity<Object>> create(
            @Valid
            @ModelAttribute("createProfileForm")
            CreateProfileForm form,
            BindingResult result) {

        if (result.hasErrors()) {
            return Mono.just(ResponseEntity.badRequest().body(
                    (Object) new ErrorResponse(
                            "invalid input",
                            describeErrors(result),
                            List.of())));
        }

        return Mono.just(ResponseEntity.ok(
                (Object) new CreateResponse(
                        form.displayName(),
                        form.emailAddress())));
    }

    @PostMapping(
            path = "/{id}/edit",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Mono<ResponseEntity<Object>> edit(
            @PathVariable long id,
            @Valid
            @ModelAttribute("profileEditForm")
            ProfileEditForm form,
            BindingResult result) {

        String[] suppressed = result.getSuppressedFields();
        Arrays.sort(suppressed);

        if (result.hasErrors() || suppressed.length > 0) {
            return Mono.just(ResponseEntity.badRequest().body(
                    (Object) new ErrorResponse(
                            "invalid or unsupported input",
                            describeErrors(result),
                            List.of(suppressed))));
        }

        return Mono.just(ResponseEntity.ok(
                (Object) new EditResponse(
                        id,
                        form.getDisplayName(),
                        form.getEmail(),
                        form.getRole(),
                        form.isEnabled())));
    }

    private List<String> describeErrors(BindingResult result) {
        return result.getFieldErrors().stream()
                .map(error ->
                        error.getField() + ":" + error.getCode())
                .toList();
    }
}
~~~

**What happens in the controller?**

- `CreateProfileForm` is a record, so the data is created through the constructor. `@BindParam` maps the hyphenated form names to the Java parameter names.
- `declarativeBinding=true` keeps constructor binding and does not automatically enable property binding when there is no allowlist.
- `ProfileEditForm` has a no-argument constructor and setters, so this is a mutable form that needs property binding.
- `@InitBinder("profileEditForm")` allows exactly the two properties `displayName` and `email`.
- If the client also sends `role` or `enabled`, the binder records those fields in `BindingResult.getSuppressedFields()`; the endpoint returns 400.
- Validation still runs on the bound fields. An allowlist does not replace `@NotBlank` or `@Email`.

### 11.4. Running the program

In the directory containing `pom.xml`:

~~~bash
mvn clean package
mvn spring-boot:run
~~~

By default the server listens on port 8080.

**Try constructor binding:**

~~~bash
curl -i -X POST http://localhost:8080/api/profiles/create \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "display-name=Alice" \
  --data-urlencode "email-address=alice@example.com" \
  --data-urlencode "role=ADMIN"
~~~

Expected response body:

~~~json
{
  "displayName": "Alice",
  "emailAddress": "alice@example.com"
}
~~~

`role=ADMIN` is not a constructor argument of `CreateProfileForm`, so it does not become a property of the form. The record contains only the two declared values.

**Try property binding with a field outside the allowlist:**

~~~bash
curl -i -X POST http://localhost:8080/api/profiles/42/edit \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "displayName=Alice" \
  --data-urlencode "email=alice@example.com" \
  --data-urlencode "role=ADMIN" \
  --data-urlencode "enabled=true"
~~~

Expected response body:

~~~json
{
  "error": "invalid or unsupported input",
  "details": [],
  "suppressedFields": [
    "enabled",
    "role"
  ]
}
~~~

`displayName` and `email` are bound. `role` and `enabled` are not assigned to the bean; they appear in the suppressed list and the endpoint rejects the request.

**Try invalid data:**

~~~bash
curl -i -X POST http://localhost:8080/api/profiles/create \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "display-name=" \
  --data-urlencode "email-address=not-an-email"
~~~

The request fails the `@NotBlank` and `@Email` validation. The controller returns HTTP 400 along with the field error codes provided by Spring. The order of field errors may depend on the binding/validation process; do not rely on that order as an API contract.

This is a demo focused on binding and the allowlist, and does not save data to a database. In a real application, after binding/validation succeeds, the service still needs to check permissions, execute the business logic, and update only the permitted columns/properties.

## 12. BindingResult, suppressed fields, and default errors in WebFlux

There are two groups of results to observe:

| Situation | Result |
| --- | --- |
| `"abc"` cannot be converted to `Long` | Binding/type conversion error |
| `@NotBlank` or `@Email` fails | Validation error |
| A request tries to set a property not in the allowlist | Suppressed field |
| The constructor is missing a required value or nested conversion fails | Constructor binding error in BindingResult |
| No `BindingResult` immediately after `@ModelAttribute` | By default `WebExchangeBindException` may be raised |

`BindingResult` must be declared **immediately after** the `@ModelAttribute` argument it represents:

~~~java
@PostMapping("/edit")
Mono<String> update(
        @Valid @ModelAttribute("form") ProfileEditForm form,
        BindingResult result) {
    // Handle errors and suppressed fields here.
}
~~~

If there are several model attributes, each `BindingResult` must come immediately after its corresponding argument. Do not put another parameter in between.

In an application that needs security control, decide clearly on the policy for suppressed fields:

- **Controlled ignoring**: suitable for some backward-compatible forms, but log/observe if necessary.
- **Rejecting the request**: suitable when the client sends fields outside the contract or shows signs of trying to change sensitive properties.
- **Recording a security event**: consider rate, privacy, and avoid logging the entire payload containing personal data.

Do not return stack traces or the binder's internal details to the client.

## 13. Partial updates (PATCH) need clear semantics

Constructor binding suits cases where the input set has a clear structure, but PATCH has its own problem: **a field that is not sent** differs from **a field that is sent with a null value**.

Example:

~~~json
{
  "displayName": null
}
~~~

The client may want to clear the name, or may have accidentally sent null; whereas if the `displayName` key is absent, it may mean “keep unchanged”. A simple DTO with a nullable field may not fully express those two states.

Design approaches:

- Use a dedicated command for each clear operation, for example `ChangeDisplayName` or `ChangeEmail`.
- Use a three-state representation: absent, present-null, present-value, if the contract allows null.
- Use JSON Merge Patch/JSON Patch when you need standard patch semantics and have proper support.
- Apply only the fields that were actually sent and that authorization permits.
- Avoid binding PATCH directly into a persistence entity that holds old state.

For PUT, define clearly whether it replaces the entire representation or only part of it per the contract. Do not let Spring's skipping of absent fields decide in place of the API semantics.

## 14. Common mistakes

| Mistake | Risk | How to address |
| --- | --- | --- |
| Binding a JPA/Hibernate entity directly in `@ModelAttribute` | The client can try to update internal fields or nested properties | Create a request DTO dedicated to the use case |
| Thinking a record protects itself while the controller still uses another mutable bean | Setter binding can still widen the input | Use an immutable DTO and/or `declarativeBinding` |
| Setting only `allowedFields` without understanding constructor binding | Constructor arguments are still valid input | Design the constructor to match the contract; use declarative binding |
| Using `disallowedFields` to forbid a few fields | Easy to forget new fields when the model changes; deprecated in Spring 7.1 | Prefer a positive allowlist |
| An overly broad wildcard allowlist | May accidentally open new properties | Declare specific paths and review when the DTO changes |
| Thinking `allowedFields` restricts a JSON `@RequestBody` | JSON goes through the HTTP message codec | Use a JSON DTO, and configure deserialization and mapping separately |
| Thinking `@Valid` blocks mass assignment | Validation only checks data rules | Control binding and authorization separately |
| Thinking a suppressed field automatically causes a 400 | A suppressed field is recorded; the application decides the policy | Check `getSuppressedFields()` if you need to reject |
| Thinking constructor binding detects every unknown key | The constructor takes only the needed parameters; extra keys may be ignored | Check request keys separately if the contract requires strictness |
| Placing `BindingResult` away from `@ModelAttribute` | Spring does not associate the binding result with the right argument | Place it immediately after the argument to handle |
| Using the same DTO for user and admin profiles | Widens the input contract beyond the endpoint's needs | Separate forms/commands by use case and authorization |
| Letting the client send `ownerId` or `role` and then trusting the value | IDOR/BOLA and privilege escalation | Obtain a trustworthy identity, authorize in the service |
| Treating a nullable PATCH field as sufficient | Cannot distinguish absent from explicit null | Design three-state patch semantics or a dedicated command |

## 15. Testing constructor binding and the allowlist

A valuable test should check **accepted values and blocked values**, not just check that the endpoint returns 200.

### 15.1. Testing constructor binding

Send a form containing valid fields and one extra field, `role`. Verify that:

- `displayName` and `emailAddress` are in the response.
- There is no `role` field in the DTO/response.
- The constructor does not produce an administrative property from undeclared input.

### 15.2. Testing allowlist property binding

Send a form with `displayName`, `email`, `role`, and `enabled`. Verify that:

- The two allowed fields are bound.
- `role` and `enabled` are in `getSuppressedFields()`.
- The bean's default internal values are not changed.
- If the policy requires, the endpoint returns 400 when there is a suppressed field.

### 15.3. Testing nested property paths

If the allowlist has `address.city` or `items[0].name`, you need to test both the allowed path and the disallowed sibling/entry. A top-level allowlist such as `address` can open more nested properties than intended.

### 15.4. Testing validation and authorization separately

- An empty string, a wrong email, and a length over the limit must produce a validation error.
- A user without permission to update the resource must be rejected even when binding and validation both succeed.
- Changing `ownerId`, `role`, or the tenant ID must not help access data beyond permission.
- Test both form/query requests and JSON bodies because they go through different mechanisms.

You can use **WebTestClient** to send real HTTP requests to the WebFlux application; the test verifies binding, validation, response status, and body along the same processing path that the client uses.

## 16. Checklist before taking binding to production

- [ ] Each endpoint has its own request DTO, containing only the fields the client is allowed to send.
- [ ] Prefer record/immutable DTOs and constructor binding.
- [ ] Consider enabling `binder.setDeclarativeBinding(true)` at an appropriate scope.
- [ ] If using setter binding, declare a specific `setAllowedFields`.
- [ ] Review nested property paths, collection indexes, map keys, and wildcards.
- [ ] Do not directly bind domain/persistence entities that have many internal properties.
- [ ] Distinguish `@ModelAttribute` from a JSON `@RequestBody`.
- [ ] Check `BindingResult` and suppressed fields according to the API policy.
- [ ] Use `@Valid`/`@Validated` for validation, but do not confuse it with authorization.
- [ ] Take the user/tenant from the authenticated identity and check permission on each resource.
- [ ] Design PUT/PATCH semantics clearly, especially absent versus null.
- [ ] Test valid fields, fields outside the allowlist, nested paths, validation, and access rights.
- [ ] Do not log the entire sensitive payload or return internal binder errors to the client.

## 17. Self-check

**Question 1.** How does constructor binding differ from property binding?

Constructor binding creates the object from the constructor's arguments; property binding creates/receives an object and then assigns values to JavaBean setters/properties.

**Question 2.** Why is a Java record often suitable for a request DTO?

A record has a clear constructor and immutable state; the set of constructor components directly expresses the inputs the endpoint accepts.

**Question 3.** Does Spring enable constructor binding or property binding by default?

By default, both are applied. You can use `setDeclarativeBinding(true)` to always use constructor binding and enable property binding only when `allowedFields` is declared.

**Question 4.** Does `setAllowedFields("displayName", "email")` restrict constructor parameters?

No. It is an allowlist for property binding. Constructor arguments still have to be controlled by the design of the constructor/DTO itself.

**Question 5.** When declarative binding is enabled and no allowedFields is configured, does setter binding run?

No. Constructor binding still runs; property binding is applied conditionally only when there is an allowlist.

**Question 6.** What is `@BindParam("display-name")` used for?

It maps the request name `display-name` to a constructor parameter that has a different Java name, for example `displayName`.

**Question 7.** Does `getSuppressedFields()` always list every query parameter that the constructor does not use?

No. It reflects fields suppressed in property binding. An extra parameter that is not a constructor argument may be ignored without appearing in this list.

**Question 8.** Does `allowedFields` restrict a JSON `@RequestBody`?

No. A JSON body is decoded through the HTTP message codec; it needs a DTO and a separate deserialization policy.

**Question 9.** Does `@Valid` stop users from sending `role=ADMIN` themselves?

No. Validation checks data; the allowlist/constructor DTO restricts input, and authorization decides whether the user has permission to make the change.

**Question 10.** Why is a positive allowlist better than a denylist?

Because an allowlist clearly describes the set of permitted fields; when the model gains a property, the new property is not automatically opened just because it has not been added to the deny list.

## 18. Official references

- [Spring Framework — WebFlux Data Binding](https://docs.spring.io/spring-framework/reference/web/webflux/data-binding.html): scope of @ModelAttribute, model design, constructor binding, allowlist, and declarative binding.
- [Spring Framework — Core Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html): constructor binding, property binding, nested property path, type conversion.
- [Spring Framework — @ModelAttribute in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/modelattrib-method-args.html): request data sources, @BindParam, BindingResult, and validation.
- [Spring Framework — DataBinder in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-initbinder.html): @InitBinder, binder configuration scope, and Converter/Formatter.
- [Spring Framework — Validation, Data Binding, and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html): DataBinder, Validator, and the role of validation across layers.
- [Spring Framework — BindParam JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/bind/annotation/BindParam.html): annotation for the request name of a constructor parameter.
- [Spring Framework — BindingResult JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/BindingResult.html): errors and suppressed fields.
- [Spring Boot System Requirements](https://docs.spring.io/spring-boot/system-requirements.html): Java and build tool requirements for the selected Boot version.

**Remember:** Constructor binding restricts input to the declared constructor parameters; `declarativeBinding` keeps constructor binding and enables setter binding only when `allowedFields` is present. When you need property binding, use an allowlist with specific property paths and check suppressed fields. Use a separate DTO for each use case, distinguish `@ModelAttribute` from a JSON `@RequestBody`, and always handle validation, authorization, and update semantics at their own layers.