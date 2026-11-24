# setDisallowedFields and the limitations of denylists

## 1. Why do we need to control which fields are bound?

When Spring Framework receives form parameters, `DataBinder` can map each parameter name to a JavaBean property, convert its type, and invoke the corresponding setter. For example, `displayName=Lan` can invoke `setDisplayName("Lan")`. With `@ModelAttribute` in Spring MVC, this mechanism is used to create and populate form/command objects.

The problem arises when the target object also has properties **not meant to be edited by the client**, such as `role`, `admin`, `ownerId`, `approved`, or `version`. The absence of an input field in the UI does not mean a client cannot send a parameter bearing that property's name.

For example, an HTTP form attempting to send:

~~~text
displayName=Lan
role=ADMIN
admin=true
~~~

If the object has matching setters and property binding is unrestricted, a client can attempt to alter both the name and privileges. This is the *mass assignment* risk: the system inadvertently lets external data control fields outside the business contract.

`setDisallowedFields(String... patterns)` is a feature of `org.springframework.validation.DataBinder` that lets you declare **property/path names to exclude from a property binding pass**. For example:

~~~java
DataBinder binder = new DataBinder(form, "profile");
binder.setDisallowedFields("role", "admin");
~~~

During binding, Spring blocks fields matching `role` or `admin`. The remaining fields, such as `displayName`, can still be assigned if the property is writable and the value is valid.

Key point: this is a **denylist**. It enumerates what is known to be forbidden. It does not define everything that is permitted, so a new property added to the model can be bound if the blocklist is not updated.

## 2. How DataBinder handles disallowed fields

During property binding, the binder typically goes through these steps:

~~~text
       Request data / PropertyValues
                    |
                    v
           DataBinder / WebDataBinder
                    |
       Check allowed/disallowed fields
                    |
         +----------+----------+
         |                     |
  Excluded field          Allowed field
         |                     |
   Setter not called      Type conversion
   to assign the field         |
         |               Assign value or
   Record field name      record binding error
   in suppressed               |
         |                     |
         +----------+----------+
                    |
                    v
              BindingResult
         getSuppressedFields()
         getFieldErrors()
         hasErrors()
~~~

Concepts to distinguish:

- **Suppressed field**: excluded by the allowed/disallowed policy. It is not assigned by this property binding pass.
- **Binding error**: an allowed field that cannot be converted or assigned. For example, `age=abc` when the property is `Integer` can produce a `typeMismatch` error.
- **Validation error**: the bound value fails constraints such as `@NotBlank` or `@Min(1)`.
- **Unknown field**: a name that does not correspond to a property on the target; behavior depends on `ignoreUnknownFields` and the property access mechanism.

**A suppressed field does not automatically generate a `FieldError`.** Therefore, `BindingResult.hasErrors()` can be `false` even though the client sent a field disallowed by the binder. If the API requires rejecting requests containing out-of-contract fields, the application must check `getSuppressedFields()` separately.

`setDisallowedFields` must be configured **before** `bind(...)`. By default there are no disallowed patterns, meaning no extra blocklist is applied by this API.

## 3. Name and pattern syntax

`setDisallowedFields(...)` accepts property names or `*` patterns using Spring's simple pattern matching rules. These are **not regular expressions**.

| Pattern | Example matching fields | Things to watch out for |
|---|---|---|
| `"role"` | `role` | Specific name; does not automatically cover nested paths |
| `"admin"` | `admin`, `ADMIN` | Disallowed matching is case-insensitive |
| `"secret*"` | `secret`, `secretKey` | Blocks names starting with `secret` |
| `"*Password"` | `oldPassword`, `temporaryPassword` | Blocks names ending accordingly |
| `"address.*"` | `address.street`, `address.ownerId` | Pattern for nested property paths |
| `"items[*].ownerId"` | `items[0].ownerId`, `items[7].ownerId` | `*` matches the index position in the path |
| `"*role*"` | Any name containing `role` | Easy to accidentally block valid fields |

Property names can look like `address.ownerId`, `items[0].approved`, or `metadata[key]` depending on whether the structure is an object, nested bean, List, or Map. Configuring only `"role"` **does not guarantee** blocking paths like `"account.role"` or `"items[0].role"`.

Patterns containing `*` can also match more names than expected. Always test with the exact property paths your application receives; do not assume a denylist analyzes the entire object graph or business permissions.

### Case sensitivity and precedence

Under the Spring Framework 6.x contract:

- `setDisallowedFields` matches **case-insensitively**.
- `setAllowedFields` matches **case-sensitively**.
- If a field matches both an allowed and a disallowed pattern, **disallowed wins**: the field is still excluded.

For example:

~~~java
binder.setAllowedFields("displayName", "email", "role");
binder.setDisallowedFields("role");
~~~

`role` is still excluded; `displayName` and `email` are allowed unless blocked by another disallowed pattern. For an endpoint that only permits editing name and email, writing `setAllowedFields("displayName", "email")` directly is usually clearer.

Case-insensitive disallowed matching mitigates one trivial bypass, but **it does not protect newly added properties or unlisted aliases/paths**. If you override `isAllowed(...)` in a subclass, preserve Spring's matching and precedence contract.

## 4. Java 17+ example: a denylist missing a new property

The following program illustrates this concrete risk. A form has four properties:

- `displayName`: editable by the user.
- `role` and `admin`: privileged attributes blocked by the denylist.
- `canExport`: a sensitive property **added later** without updating the denylist.

We use the same input set to compare a denylist and an allowlist. The example runs on Java 17+ with Spring Framework 6.2.x; no server or database is needed.

Directory structure:

~~~text
binding-policy-demo/
├── pom.xml
└── src/main/java/demo/BindingPolicyDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>binding-policy-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.6.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

File `src/main/java/demo/BindingPolicyDemo.java`:

~~~java
package demo;

import java.util.Arrays;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

public final class BindingPolicyDemo {

    public static final class ProfileForm {
        private String displayName = "Guest";
        private String role = "USER";
        private boolean admin;
        private boolean canExport;

        public String getDisplayName() {
            return displayName;
        }

        public void setDisplayName(String displayName) {
            this.displayName = displayName;
        }

        public String getRole() {
            return role;
        }

        public void setRole(String role) {
            this.role = role;
        }

        public boolean isAdmin() {
            return admin;
        }

        public void setAdmin(boolean admin) {
            this.admin = admin;
        }

        public boolean isCanExport() {
            return canExport;
        }

        public void setCanExport(boolean canExport) {
            this.canExport = canExport;
        }
    }

    static MutablePropertyValues request() {
        MutablePropertyValues values = new MutablePropertyValues();
        values.add("displayName", "Lan");
        values.add("role", "ADMIN");
        values.add("admin", "true");
        values.add("canExport", "true");
        return values;
    }

    static String suppressed(BindingResult result) {
        String[] fields = result.getSuppressedFields();
        Arrays.sort(fields);
        return Arrays.toString(fields);
    }

    public static void main(String[] args) {
        ProfileForm denyTarget = new ProfileForm();
        DataBinder deny = new DataBinder(denyTarget, "profile");
        deny.setDisallowedFields("role", "admin");
        deny.bind(request());

        System.out.println("deny.name=" + denyTarget.getDisplayName());
        System.out.println("deny.role=" + denyTarget.getRole());
        System.out.println("deny.admin=" + denyTarget.isAdmin());
        System.out.println("deny.canExport=" + denyTarget.isCanExport());
        System.out.println("deny.suppressed="
                + suppressed(deny.getBindingResult()));
        System.out.println("deny.hasErrors="
                + deny.getBindingResult().hasErrors());

        ProfileForm allowTarget = new ProfileForm();
        DataBinder allow = new DataBinder(allowTarget, "profile");
        allow.setAllowedFields("displayName");
        allow.bind(request());

        System.out.println("allow.name=" + allowTarget.getDisplayName());
        System.out.println("allow.role=" + allowTarget.getRole());
        System.out.println("allow.admin=" + allowTarget.isAdmin());
        System.out.println("allow.canExport=" + allowTarget.isCanExport());
        System.out.println("allow.suppressed="
                + suppressed(allow.getBindingResult()));

        ProfileForm upperTarget = new ProfileForm();
        DataBinder upper = new DataBinder(upperTarget, "profile");
        upper.setDisallowedFields("role");

        MutablePropertyValues upperRequest =
                new MutablePropertyValues();
        upperRequest.add("ROLE", "ADMIN");
        upper.bind(upperRequest);

        System.out.println("uppercase.role=" + upperTarget.getRole());
        System.out.println("uppercase.suppressed="
                + suppressed(upper.getBindingResult()));
    }
}
~~~

Run with Maven and JDK 17+:

~~~bash
cd binding-policy-demo
mvn -q compile exec:java -Dexec.mainClass=demo.BindingPolicyDemo
~~~

Output printed by the program:

~~~text
deny.name=Lan
deny.role=USER
deny.admin=false
deny.canExport=true
deny.suppressed=[admin, role]
deny.hasErrors=false
allow.name=Lan
allow.role=USER
allow.admin=false
allow.canExport=false
allow.suppressed=[admin, canExport, role]
uppercase.role=USER
uppercase.suppressed=[ROLE]
~~~

Maven may emit its own logs depending on the environment; the block above shows the `System.out.println` output from the Java code.

**How to read the output:**

1. The denylist blocks `role` and `admin`, so the target keeps `"USER"` and `false`.
2. `canExport=true` is still assigned because it is not in the denylist. Simply adding a new property with a setter widened the input surface the endpoint accepts.
3. `getSuppressedFields()` contains `admin` and `role`, yet `hasErrors()` remains `false` because they do not automatically create binding errors.
4. With an allowlist containing only `displayName`, all of `role`, `admin`, and `canExport` are blocked. New fields are unbindable by default.
5. The uppercase input `ROLE` is still rejected by the `role` denylist, illustrating case-insensitive matching.

The program intentionally uses a form with multiple setters to demonstrate the filtering mechanism. **You should not use a form containing privileged fields like this as a real-world input DTO.**

## 5. getSuppressedFields and request handling decisions

After `bind(...)`, retrieve the excluded field list:

~~~java
BindingResult result = binder.getBindingResult();
String[] suppressedFields = result.getSuppressedFields();

if (suppressedFields.length > 0) {
    // One or more fields were excluded by the allowed/disallowed policy.
}
~~~

The field names in this array are diagnostic and input-control metadata. They are not validation errors, do not contain all submitted values by default, and do not automatically fail the request.

A policy may choose either to **ignore** out-of-contract fields or to **reject** the request. For endpoints mutating sensitive data, rejecting out-of-contract input helps catch client bugs or unwanted behavior early. Which approach you choose must be clearly reflected in the API contract and tests.

For example:

~~~java
if (result.getSuppressedFields().length > 0) {
    throw new IllegalArgumentException("Disallowed input field");
}
if (result.hasErrors()) {
    // Report type conversion or validation errors.
}
~~~

This snippet illustrates the rule; in Spring MVC, if you want HTTP 400, use an appropriate response or exception mapping instead of assuming every `IllegalArgumentException` becomes a 400.

Do not treat `getSuppressedFields().length == 0` as proof that the object is safe. For example, the denylist missed `canExport`, so it was not suppressed even though binding it was undesirable.

## 6. @ModelAttribute and @InitBinder in Spring MVC

When handling form or query parameters with `@ModelAttribute`, Spring MVC uses `WebDataBinder`. You can configure disallowed fields via `@InitBinder`:

~~~java
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;

@Controller
class ProfileController {

    @InitBinder("profile")
    void configure(WebDataBinder binder) {
        binder.setDisallowedFields("role", "admin");
    }

    // A handler receiving @ModelAttribute("profile") ...
}
~~~

The name `"profile"` targets the configuration to the matching model attribute; it does not automatically apply to every handler, model attribute, or input mechanism.

A safer preferred configuration:

~~~java
@InitBinder("profile")
void configure(WebDataBinder binder) {
    binder.setAllowedFields("displayName");
}
~~~

For real endpoints, use a **dedicated form DTO** per use case, for example:

~~~java
import jakarta.validation.constraints.NotBlank;

public class ChangeDisplayNameForm {
    @NotBlank
    private String displayName;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
~~~

This DTO has no `role` or `admin` property to bind. When the underlying domain model gains an internal field, the display-name change API does not automatically expand with it.

### Checking suppressed and other errors separately in a handler

~~~java
import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Controller;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.server.ResponseStatusException;

@Controller
class ChangeDisplayNameController {

    private final ProfileService service;

    ChangeDisplayNameController(ProfileService service) {
        this.service = service;
    }

    @InitBinder("profile")
    void configure(WebDataBinder binder) {
        binder.setAllowedFields("displayName");
    }

    @PostMapping("/profile/display-name")
    String submit(
            @Valid @ModelAttribute("profile") ChangeDisplayNameForm form,
            BindingResult errors) {

        if (errors.getSuppressedFields().length > 0) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Disallowed field");
        }
        if (errors.hasErrors()) {
            return "profile/edit";
        }

        service.changeDisplayName(form.getDisplayName());
        return "redirect:/profile";
    }
}
~~~

This is **integration code**, not a standalone program runnable with `javac`: the project needs `ProfileService`, views, Spring MVC, and a Bean Validation provider. If CSRF protection is enabled, a real form also requires a CSRF token.

Notice that `BindingResult` appears **immediately after** the corresponding `@ModelAttribute`. The business branch only runs when there are neither suppressed fields nor binding/validation errors. The service must also verify that the caller is authorized to edit the specific profile.

## 7. Important limitation: JSON @RequestBody

`WebDataBinder`'s denylist is for **property binding** and must not be treated as a JSON filter for all endpoints.

~~~java
@PostMapping("/profile")
void update(@RequestBody ProfileRequest request) {
    // HTTP message conversion, typically via Jackson.
}
~~~

With `@RequestBody`, JSON is deserialized through an `HttpMessageConverter`, usually Jackson. `WebDataBinder`'s `setDisallowedFields` configuration **does not directly control which properties Jackson reads from JSON** as a global blocklist.

For JSON, use a DTO declaring only the fields the API accepts, configure unknown-field handling according to your contract, apply validation, and control mapping/authorization in the service layer. If you need to reject JSON containing unexpected properties, that is a separate deserialization policy, not `@ModelAttribute`'s `getSuppressedFields()`.

## 8. Important limitation: constructor binding

Spring Framework supports two main binding modes:

- **Constructor binding**: creates the object via a constructor and the required arguments.
- **Property binding**: assigns properties via setters/field access after the object exists.

`setDisallowedFields` controls the field list for **property binding**. It is **not a general blocklist for arguments in `DataBinder.construct(...)`**. An immutable DTO whose constructor accepts only the necessary inputs provides a cleaner boundary.

In Spring Framework 6.2, you can configure `setDeclarativeBinding(true)` so property binding only operates when allowed fields are configured, while constructor binding remains supported:

~~~java
@InitBinder
void configure(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
~~~

Apply this according to your Spring version and actual object design. This setting does not replace Bean Validation, authorization checks, or JSON protections handled by Jackson.

## 9. Security and maintenance limitations of denylists

### 9.1. Adding new fields to a model

A class initially has only `displayName`, `role`, and `admin`; the denylist contains `"role", "admin"`. When a developer adds `canExport` without auditing every endpoint using that class, the new field becomes bindable. The original configuration did not change, yet the externally accepted data surface grew.

Therefore, avoid sharing domain entities or internal models directly as command objects across multiple endpoints with different edit permissions.

### 9.2. Nested properties and collections

A denylist containing `"role"` does not automatically block paths like:

~~~text
account.role
items[0].role
items[1].role
metadata[role]
~~~

For object graphs with such properties, review each path and matching pattern carefully. Attempting to use a broad wildcard like `"*role*"` may accidentally block unrelated fields. A less error-prone approach is specifying permitted inputs explicitly and constraining nested DTO types.

### 9.3. Placing @InitBinder in the wrong scope

An `@InitBinder("profile")` method does not configure model attributes with other names, nor does it alter JSON deserialization. When auditing an endpoint, verify that the data actually passes through the configured binder. Do not assume that merely having the method in a controller proves the policy is applied.

### 9.4. Difference between "bindable field" and "authorized to edit resource"

Even if `displayName` is in the allowlist, a client still must not edit another user's account. Authorization depends on the caller, resource, state, and business rules. It must be enforced in the service or security layer and **cannot be inferred from field names**.

### 9.5. Resource controls

Property paths can include nested objects or collection indexes. If you need to bind lists, limit auto-grow, object depth, and request size. For example:

~~~java
binder.setAllowedFields("items[*].name", "items[*].quantity");
binder.setAutoGrowCollectionLimit(20);
~~~

`setAutoGrowCollectionLimit` helps reduce the risk of creating oversized collections via indexed property paths; it does not replace business-level item-count validation or mitigate every cost of complex object graphs.

### 9.6. Logging blocked field information

`getSuppressedFields()` provides **names**, not the field contents by default. Avoid logging raw requests or sensitive rejected values just to inspect denylist hits; apply count limits, length limits, and redaction when logging.

## 10. Comparing related DataBinder options

| API or setting | Purpose | Key distinction to remember |
|---|---|---|
| `setDisallowedFields` | Excludes property paths matching the denylist | New fields are not blocked automatically |
| `setAllowedFields` | Accepts only property paths in the allowlist | Safer when the target gains new properties |
| `getSuppressedFields` | Returns names of excluded fields | Does not automatically create a FieldError or HTTP 400 |
| `getFieldErrors` and `hasErrors` | Checks binding/validation errors | Does not replace suppressed-field checks |
| `setRequiredFields` | Specifies which fields must be present in input | Does not decide which fields users may modify |
| `setIgnoreUnknownFields` | Handles property names that do not exist | Unknown field differs from suppressed field |
| `setIgnoreInvalidFields` | Handles certain unreachable nested paths | Not an authorization policy |
| `setAutoGrowNestedPaths` | Instantiates nested objects/collections when possible | Can expand the property path surface |
| `setAutoGrowCollectionLimit` | Caps auto-growing collections | Does not replace business quotas |
| `setDeclarativeBinding(true)` | Restricts setter binding to allowed fields | Not a JSON filter or authorization mechanism |

One field may be allowed to bind yet carry an invalid type, producing a `FieldError`. Another field may be blocked by the denylist without producing any error. A third field may not exist at all and be ignored according to unknown-field settings. All three cases must be distinguished in request handling and tests.

## 11. Common mistakes

**Mistake 1: Setting a denylist and assuming the endpoint is secure.** Denylists easily miss new fields or nested paths. Prefer dedicated DTOs and allowlists.

**Mistake 2: Checking only `hasErrors()`.** Suppressed fields may not create binding errors, as shown by `deny.hasErrors=false` in the example. If you want to reject out-of-contract fields, check `getSuppressedFields()`.

**Mistake 3: Confusing `"role"` with every role path.** `account.role` or `items[0].role` are distinct field names. Verify nested models and patterns with tests.

**Mistake 4: Treating wildcards like regex.** `*` is Spring's simple matching wildcard, not a regular expression. Overly broad patterns can also cause false positives.

**Mistake 5: Ignoring case sensitivity rules.** In Spring 6.x, disallowed matching is case-insensitive while allowed matching is case-sensitive. Do not reimplement custom rules differently without good reason.

**Mistake 6: Thinking @InitBinder blocks JSON @RequestBody.** JSON deserialization goes through an HTTP message converter; use dedicated DTOs and JSON policies.

**Mistake 7: Binding requests directly into JPA/Hibernate entities.** Entities often have IDs, owners, statuses, and internal relationships; adding a setter accidentally expands the input surface. Use input DTOs and controlled mapping.

**Mistake 8: Forgetting authorization checks.** A bindable field name does not prove the user is allowed to modify that record. The service needs explicit authorization.

**Mistake 9: Logging all rejected values.** A field might carry tokens, passwords, or personal data; log minimally and avoid echoing sensitive input in responses.

## 12. Tests you should write

| Input and configuration | What to verify |
|---|---|
| `displayName=Lan` | Name binds successfully |
| Deny `role`, send `role=ADMIN` | Target role is unchanged; field appears in suppressed |
| Deny `role`, send `ROLE=ADMIN` | Case-insensitive matching works |
| Deny `role,admin`, send `canExport=true` | New field can slip through if missing from denylist |
| Allow `displayName`, send `canExport=true` | New field is suppressed |
| Field in both allowed and disallowed | Disallowed takes precedence |
| Field is suppressed without type mismatch | `hasErrors()` can still be `false` |
| Allowed field, send `age=abc` for `Integer` | Separate binding error, not confused with suppressed |
| Nested `items[0].ownerId` | Correct block pattern and server-managed field stays untouched |
| JSON `@RequestBody` with out-of-contract field | Handled separately by Jackson/DTO policy |
| User edits unauthorized resource | Service rejects despite valid fields |
| Out-of-contract input rejected | Write operation is never invoked |

In tests, do not assert `getSuppressedFields()` in a fixed order; sort it or match it as a set. Include regression tests when adding new fields to a model, as that is when a denylist is most likely to become incomplete.

Assertion example placed inside a test with the types from section 4's program:

~~~java
ProfileForm form = new ProfileForm();
DataBinder binder = new DataBinder(form, "profile");
binder.setDisallowedFields("role");

MutablePropertyValues values = new MutablePropertyValues();
values.add("role", "ADMIN");
binder.bind(values);

boolean unchanged = "USER".equals(form.getRole());
boolean suppressed = java.util.Arrays.asList(
        binder.getBindingResult().getSuppressedFields()).contains("role");

if (!unchanged || !suppressed) {
    throw new AssertionError("Role was not blocked properly");
}
~~~

This snippet illustrates an assertion in a test environment that already has imports and `ProfileForm`; when using JUnit, you can replace it with JUnit assertions.

## 13. Choosing the right approach in a project

To safely design an endpoint that accepts client data:

1. Identify the **exact set of properties the client is permitted to submit** per use case; create a dedicated request DTO.
2. For `@ModelAttribute` and setter/property binding, prefer `setAllowedFields(...)`.
3. Where appropriate, use immutable DTOs and constructor binding, and consider `setDeclarativeBinding(true)` depending on your Spring version.
4. If you must use `setDisallowedFields` for compatibility or as an extra safeguard, test new fields, nested paths, wildcards, case sensitivity, and precedence against allowlists.
5. Check `getSuppressedFields()` and `hasErrors()` separately if the contract requires detecting out-of-scope input.
6. For `@RequestBody` JSON, use dedicated DTO and deserialization policies.
7. In the service layer, verify permissions, enforce business invariants, and map only permitted attributes onto entities.
8. Enforce request size limits, collection auto-grow limits, and safe logging.

**Main takeaway:** `setDisallowedFields` answers "which fields do we already know to forbid?". It is a useful defensive layer, but an input contract is usually easier to reason about when it explicitly answers "which fields alone are allowed?" using DTOs and `setAllowedFields`.

### Official references

- Spring Framework Reference — Web MVC, `@InitBinder`, and Model Design.
- Spring Framework Reference — Core Technologies, Validation, and Data Binding.
- Spring Framework Javadoc — `DataBinder#setDisallowedFields`, `DataBinder#setAllowedFields`, `DataBinder#isAllowed`.
- Spring Framework Javadoc — `BindingResult#getSuppressedFields`.
