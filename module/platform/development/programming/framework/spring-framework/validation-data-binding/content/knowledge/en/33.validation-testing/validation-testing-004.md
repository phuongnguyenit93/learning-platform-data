# Testing allowedFields, suppressedFields, and Auto-Grow Limits in Spring Data Binding

## 1. Lesson Objectives

**Data binding** turns HTTP request parameters, form fields, or other input values into Java object properties. This feature is convenient, but it easily leads to **mass assignment/overposting** if a client can send extra field names that the UI does not expose.

For example, a profile edit page only allows updating `nickname` and `address.city`. However, the JavaBean also has `admin`, `address.verified`, and `items[0].discount`. A client can craft a request:

~~~http
POST /binding/profile
Content-Type: application/x-www-form-urlencoded

nickname=Lan&admin=true&address.verified=true&items[0].discount=99
~~~

To test a binder safely, you must prove **both what is allowed and what is forbidden**:

1. `setAllowedFields(...)` actually restricts writable property paths.
2. `BindingResult#getSuppressedFields()` records fields dropped on the **property binding** path.
3. `getSuppressedFields()` is not synonymous with `hasErrors()` and **does not automatically turn the request into HTTP 400**.
4. Nested paths, indexed paths, and wildcard patterns do not widen the writable surface beyond the design.
5. `setAutoGrowNestedPaths(...)` controls instantiating nested objects from null.
6. `setAutoGrowCollectionLimit(...)` controls **how far lists/arrays can auto-expand**, and indexes just below and right at the limit must be tested.
7. `setDeclarativeBinding(true)`, constructor binding, and `@RequestBody` JSON follow different rules; do not generalize property-binding test results to all input pathways.

This lesson includes **unit tests using `DataBinder`** and **integration tests using `MockMvc`**, with Java 17+, Spring Boot 3.2+ (Spring Framework 6.1+). The final section explains security boundaries, including the Spring advisory published in 2026 regarding self-populating custom lists.

## 2. Core APIs and applicability

| API | Meaning | Key assertion |
| --- | --- | --- |
| `DataBinder#setAllowedFields(String...)` | Registers an allowlist for property/setter binding. | Allowed properties are assigned; remaining fields stay unchanged. |
| `BindingResult#getSuppressedFields()` | Property names dropped by the allowed/disallowed fields filter during binding. | Contains the blocked fields; may be empty if input was skipped by another mechanism. |
| `BindingResult#hasErrors()` | Indicates binding/conversion/validation errors exist. | Does not replace checking suppression. |
| `DataBinder#setAutoGrowNestedPaths(boolean)` | Allows auto-creating null intermediate objects and growing collections on index access. | When enabled, nested beans can be created; when disabled, they are not. |
| `DataBinder#setAutoGrowCollectionLimit(int)` | Limits auto-growth for lists/arrays during setter/property binding. | Indexes below limit can succeed; at/above limit do not auto-grow. |
| `DataBinder#getAutoGrowCollectionLimit()` | Current limit value. | Default is **256** on standard DataBinder. |
| `DataBinder#setDeclarativeBinding(true)` | Constructor binding remains allowed; property binding runs only if `allowedFields` is set. | No allowlist on a setter-only JavaBean → setters are not bound. |
| `DataBinder#setIgnoreUnknownFields(...)` | Controls handling of non-existent properties. | Unknown fields are not necessarily suppressed fields. |
| `DataBinder#setIgnoreInvalidFields(...)` | Handles certain inaccessible nested properties. | Not a mechanism to permit binding arbitrary invalid paths. |
| `WebDataBinder` and `@InitBinder` | Wires the policy to a controller/model attribute. | HTTP integration tests prove the right binder is invoked. |
| `@Valid`/`@Validated` | Constraint validation after binding. | Test separately from suppression and conversion. |

**Distinction:** the allowlist answers **which fields may be written**; the auto-grow limit answers **how far a collection may auto-expand**. A path can still exceed the limit even when allowlisted; an index within the limit must still be blocked if the path is outside the allowlist.

## 3. Essential tests for allowedFields

### 3.1. Without an allowlist: test to see the risk clearly

Example JavaBean:

~~~java
public class ProfileForm {
    private String nickname;
    private boolean admin;

    public String getNickname() { return nickname; }
    public void setNickname(String value) { this.nickname = value; }
    public boolean isAdmin() { return admin; }
    public void setAdmin(boolean value) { this.admin = value; }
}
~~~

This is an abbreviated snippet; the full runnable file in section 8 adds nested objects and a list.

If fields are unrestricted:

~~~java
ProfileForm form = new ProfileForm();
DataBinder binder = new DataBinder(form, "profileForm");

binder.bind(new MutablePropertyValues(Map.of(
        "nickname", "Lan",
        "admin", "true"
)));

assertEquals("Lan", form.getNickname());
assertTrue(form.isAdmin());
~~~

In this case, default binding can set `admin=true`. This is an **anti-pattern regression test** showing why an input policy is needed, not advice to bind a JPA entity directly to a public API.

### 3.2. Allowlist permitting only nickname

~~~java
ProfileForm form = new ProfileForm();
DataBinder binder = new DataBinder(form, "profileForm");
binder.setAllowedFields("nickname");

binder.bind(new MutablePropertyValues(Map.of(
        "nickname", "Lan",
        "admin", "true"
)));

assertEquals("Lan", form.getNickname());
assertFalse(form.isAdmin());
assertArrayEquals(
        new String[] {"admin"},
        binder.getBindingResult().getSuppressedFields());
~~~

Spring removes `admin` from the property values to assign. However, **field-blocking policy and HTTP error-response policy are two separate things**.

### 3.3. suppressedFields differs from binding errors

With the example above, typical output:

~~~text
nickname = "Lan"
admin = false
getSuppressedFields() = ["admin"]
hasErrors() = false
~~~

Because the field was **dropped before writing**, Spring does not necessarily generate a `FieldError`. You must not check only `result.hasErrors()` to assert that no overposting occurred.

If a business API requires rejecting requests carrying fields outside the schema:

~~~java
if (result.hasErrors()
        || result.getSuppressedFields().length > 0) {
    return ResponseEntity.badRequest()
            .body(Map.of("code", "INVALID_INPUT"));
}
~~~

Here HTTP 400 is a **controller decision**, not a default guarantee of `DataBinder`. Another application might ignore suppressed fields and return 200 if that is its desired contract.

### 3.4. Comparing multiple suppressed fields

If a request contains `admin=true` and `address.verified=true`, tests can compare sets:

~~~java
Set<String> actual = Set.copyOf(Arrays.asList(
        result.getSuppressedFields()));

assertEquals(Set.of("admin", "address.verified"), actual);
~~~

Do not rely on returned order if ordering is not part of the contract. Keeping property names aids debugging, but **do not log/serialize raw input values**; rejected values may be passwords, tokens, or sensitive data.

## 4. Nested and indexed property paths

Suppose the object has:

~~~text
nickname
admin
address.city
address.verified
items[0].sku
items[0].quantity
items[0].discount
items[1].sku
items[2].sku
~~~

Allowlist configuration:

~~~java
binder.setAllowedFields(
        "nickname",
        "address.city",
        "items[0].sku",
        "items[1].sku");
~~~

| Input key | Allowed? | Why |
| --- | --- | --- |
| `nickname` | Yes | Exact field name match. |
| `address.city` | Yes | Exact nested property path. |
| `address.verified` | No | Same bean, different property. |
| `items[0].sku` | Yes | Matching element 0 and matching property. |
| `items[1].sku` | Yes | Matching element 1 and matching property. |
| `items[2].sku` | No | Index 2 is not in the allowlist. |
| `items[0].quantity` | No | Quantity is not permitted in this form. |
| `items[0].discount` | No | Server-owned property. |
| `admin` | No | Server-owned property. |

### When using wildcards

~~~java
binder.setAllowedFields("nickname", "items*.sku");
~~~

The pattern `items*.sku` allows various indexed paths, such as `items[0].sku` or `items[50].sku`. If the API must not accept more than 2 items, **do not rely solely on wildcards**. Combine input-size/index policies, auto-grow limits, and Bean Validation.

The pattern `items*` is even broader and can match `items[0].discount`. Never use `*` for an entire object when server-owned fields must be protected. `setAllowedFields` supports simple Spring pattern matching wildcards, **not arbitrary regex**.

Property names may be canonicalized by Spring during binding, especially with map keys and bracket notation. If tests use `addresses['home'].city` or nested maps, inspect the actual `getSuppressedFields()` and compare according to the corresponding canonicalization rules.

## 5. Auto-grow nested paths vs collection limits

### 5.1. Auto-creating nested objects from null

When `ProfileForm.address == null` and the request sends `address.city=Da Nang`, under defaults:

~~~java
binder.setAutoGrowNestedPaths(true);
binder.setAllowedFields("address.city");
binder.bind(new MutablePropertyValues(
        Map.of("address.city", "Da Nang")));
~~~

Spring can instantiate `Address` if the type has an appropriate constructor, then assign `city`. Assertions:

~~~java
assertNotNull(form.getAddress());
assertEquals("Da Nang", form.getAddress().getCity());
~~~

`setAutoGrowNestedPaths(true)` is enabled by default on standard `DataBinder`. It also enables growing collection elements when accessing an index beyond the current size, subject to `autoGrowCollectionLimit`.

### 5.2. Disabling auto-grow

~~~java
binder.setAutoGrowNestedPaths(false);
binder.setIgnoreInvalidFields(false);
binder.setAllowedFields("address.city");
~~~

If `address` remains null, the binder does not auto-create it. With default-style error handling, a `NullValueInNestedPathException` may be thrown; if `ignoreInvalidFields=true` is set, path-ignoring behavior can differ. **Test the actual configuration** rather than writing exception-class assertions based on guesses or a different Spring version.

### 5.3. Configuring before binder initialization

With `DataBinder`, call auto-grow setters **before** `getBindingResult()`/`bind(...)`:

~~~java
DataBinder binder = new DataBinder(form, "profileForm");
binder.setAutoGrowNestedPaths(true);
binder.setAutoGrowCollectionLimit(2);
binder.setAllowedFields("address.city", "items*.sku");

binder.bind(new MutablePropertyValues(Map.of(
        "address.city", "Hue")));
~~~

The `setAutoGrowCollectionLimit` Javadoc states this setting cannot be changed after the binder initializes its `BindingResult`; calling it too late may throw `IllegalStateException`. That is why there is a unit test for "configuration-after-initialization fails".

## 6. autoGrowCollectionLimit: testing exact 0-based boundaries

`DataBinder.DEFAULT_AUTO_GROW_COLLECTION_LIMIT` is **256**. When configured with:

~~~java
binder.setAutoGrowCollectionLimit(2);
~~~

and `items` is `new ArrayList<LineItem>()`, the indexes behave as:

| Index | Elements needed after auto-grow | With limit = 2 |
| --- | --- | --- |
| `items[0].sku` | 1 | Can be created. |
| `items[1].sku` | 2 | Can be created. |
| **`items[2].sku`** | **3** | **Does not auto-grow to a third element**. |
| `items[999999].sku` | Very large | Must not auto-grow. |

This is a limit on **auto-growth via property binding on lists/arrays**, not a general validation for all collections on an object, not a Map limit, and **does not apply to constructor binding `DataBinder.construct(...)`** per the 6.x Javadoc.

### Testing the last valid index

~~~java
DataBinder binder = new DataBinder(form, "profileForm");
binder.setAutoGrowCollectionLimit(2);
binder.setAllowedFields("items*.sku");

binder.bind(new MutablePropertyValues(
        Map.of("items[1].sku", "P02")));

assertEquals(2, form.getItems().size());
assertEquals("P02", form.getItems().get(1).getSku());
~~~

For this snippet to run, `ProfileForm` must have `List<LineItem> items = new ArrayList<>()` and `LineItem` must have a public no-arg constructor/getters/setters; the full version is in section 8.

### Testing the first out-of-bounds index

~~~java
DataBinder binder = new DataBinder(form, "profileForm");
binder.setAutoGrowCollectionLimit(2);
binder.setAllowedFields("items*.sku");

assertThrows(InvalidPropertyException.class, () ->
        binder.bind(new MutablePropertyValues(
                Map.of("items[2].sku", "P03"))));
~~~

With **Spring Framework 6.1/6.2 and a standard `ArrayList`**, attempting to access an out-of-bounds element when auto-grow is disallowed typically throws `InvalidPropertyException`. That is infrastructure behavior; **do not automatically infer HTTP 400**. If another version reports errors via `BindingResult` or a wrapper exception, the invariant to protect is **not expanding the list beyond policy** and ensuring the endpoint handles invalid input properly.

### Blocking large indexes before property traversal

If the binder allows only `nickname`:

~~~java
binder.setAllowedFields("nickname");
binder.bind(new MutablePropertyValues(
        Map.of("items[999999].sku", "P99")));

assertEquals(0, form.getItems().size());
assertArrayEquals(
        new String[] {"items[999999].sku"},
        binder.getBindingResult().getSuppressedFields());
~~~

The path is blocked by the allowlist **before Spring accesses the collection**, so using a large index in this case is safe with a standard `ArrayList`. Do not use custom self-populating lists or unbounded stress tests in production environments.

### Other limits still needed

- HTTP request body size, parameter count, and nested input depth.
- Business-rule count of collection items, e.g., `@Size(max=2)`.
- Constructor binding and `@RequestBody` JSON/Jackson require separate limits.
- Lists that already contain many elements initially do not shrink when a new limit is set.
- Map entries are not constrained by the list/array auto-grow limit.
- Object graph structure and collection implementations can affect behavior.

In particular, `@Size(max=2)` runs **after input has already been bound**, so it is not a barrier against excessive allocation during the binding phase.

## 7. Three failure types that should be tested separately

| Type | Example | Signal |
| --- | --- | --- |
| **Suppression** | `admin=true` outside allowlist | `getSuppressedFields()` contains `admin`, `hasErrors()` may be `false`. |
| **Type mismatch** | `items[0].quantity=abc` when quantity is allowed to bind to `int` | `FieldError` with code `typeMismatch`, not a suppressed field. |
| **Bean Validation** | `nickname=""` and `@NotBlank` | `NotBlank` error after binding/validation. |
| **Auto-grow path limit** | `items[2].sku`, allowlist `items*.sku`, limit 2 | Does not auto-grow; property accessor exception possible. |
| **Unknown property** | `ghost=1` when target has no `ghost` | Governed by `setIgnoreUnknownFields`; not synonymous with suppressed. |

Do not assert only `hasErrors()` to prove overposting is prevented. To test conversion, you must **allow** the target field; if you forbid `quantity`, Spring suppresses it beforehand and no conversion remains to test.

Plain `DataBinder#bind` **does not automatically run `@NotBlank`** on a JavaBean. Binding unit tests and validation tests must be separated; an MVC endpoint with `@Valid @ModelAttribute` is what triggers Bean Validation (when a provider is configured).

## 8. Runnable sample project: Java 17+, Spring Boot 3.2+, and JUnit 5

Use a Maven project configured with the Spring Boot parent/BOM, choosing a Framework version patched per security policy. Add:

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

Java classes use package `com.example.bindingtests`. This project uses **Servlet Spring MVC and MockMvc**, not Spring WebFlux; form data is built in tests using `.param(...)`. No database, security, or persistence layer is needed to test the binder. In real applications, you must also enforce authorization/tenant checks during updates.

### 8.1. File `BindingTestsApplication.java`

Create `src/main/java/com/example/bindingtests/BindingTestsApplication.java`:

~~~java
package com.example.bindingtests;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BindingTestsApplication {

    public static void main(String[] args) {
        SpringApplication.run(BindingTestsApplication.class, args);
    }
}
~~~

### 8.2. File `ProfileForm.java`

Create `src/main/java/com/example/bindingtests/ProfileForm.java`:

~~~java
package com.example.bindingtests;

import jakarta.validation.constraints.NotBlank;

import java.util.ArrayList;
import java.util.List;

public class ProfileForm {

    @NotBlank
    private String nickname;

    private boolean admin;

    private Address address;

    private List<LineItem> items = new ArrayList<>();

    public ProfileForm() {
    }

    public String getNickname() {
        return nickname;
    }

    public void setNickname(String nickname) {
        this.nickname = nickname;
    }

    public boolean isAdmin() {
        return admin;
    }

    public void setAdmin(boolean admin) {
        this.admin = admin;
    }

    public Address getAddress() {
        return address;
    }

    public void setAddress(Address address) {
        this.address = address;
    }

    public List<LineItem> getItems() {
        return items;
    }

    public void setItems(List<LineItem> items) {
        this.items = items;
    }

    public static class Address {

        private String city;
        private boolean verified;

        public Address() {
        }

        public String getCity() {
            return city;
        }

        public void setCity(String city) {
            this.city = city;
        }

        public boolean isVerified() {
            return verified;
        }

        public void setVerified(boolean verified) {
            this.verified = verified;
        }
    }

    public static class LineItem {

        private String sku;
        private int quantity;
        private int discount;

        public LineItem() {
        }

        public String getSku() {
            return sku;
        }

        public void setSku(String sku) {
            this.sku = sku;
        }

        public int getQuantity() {
            return quantity;
        }

        public void setQuantity(int quantity) {
            this.quantity = quantity;
        }

        public int getDiscount() {
            return discount;
        }

        public void setDiscount(int discount) {
            this.discount = discount;
        }
    }
}
~~~

Fields `admin`, `verified`, and `discount` are included **solely to test that the binder refuses to modify them**. Production code should use a request DTO without server-owned properties rather than passing a JPA entity to `@ModelAttribute`. `ArrayList` and public nested classes with no-arg constructors allow Spring to exercise auto-grow paths.

### 8.3. File `BindingController.java`

Create `src/main/java/com/example/bindingtests/BindingController.java`:

~~~java
package com.example.bindingtests;

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

import java.util.Map;

@RestController
@RequestMapping("/binding")
public class BindingController {

    @InitBinder("profileForm")
    public void configure(WebDataBinder binder) {
        binder.setAutoGrowNestedPaths(true);
        binder.setAutoGrowCollectionLimit(2);
        binder.setAllowedFields(
                "nickname",
                "address.city",
                "items[0].sku",
                "items[1].sku");
    }

    @PostMapping(path = "/profile",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> save(
            @Valid @ModelAttribute("profileForm") ProfileForm form,
            BindingResult result) {

        if (result.hasErrors()
                || result.getSuppressedFields().length > 0) {
            return ResponseEntity.badRequest()
                    .body(Map.of("code", "INVALID_INPUT"));
        }

        String city =
                form.getAddress() == null
                || form.getAddress().getCity() == null
                    ? ""
                    : form.getAddress().getCity();

        return ResponseEntity.ok(Map.of(
                "nickname", form.getNickname(),
                "city", city,
                "admin", form.isAdmin(),
                "itemCount", form.getItems().size()));
    }
}
~~~

`@InitBinder("profileForm")` binds the binder policy specifically to `@ModelAttribute("profileForm")`. The controller explicitly returns HTTP **400** when binding errors **or** suppressed fields exist. If it checked only `result.hasErrors()`, it could ignore overposted fields and return 200.

There is no need to expose suppressed field names or raw values in the response. Returning `admin=false` in the demo is only to verify mass assignment did not occur; do not expose security flags in public APIs unless needed.

### 8.4. File `DataBinderPolicyTest.java` — 15 unit tests

Create `src/test/java/com/example/bindingtests/DataBinderPolicyTest.java`:

~~~java
package com.example.bindingtests;

import org.junit.jupiter.api.Test;
import org.springframework.beans.InvalidPropertyException;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.beans.NullValueInNestedPathException;
import org.springframework.validation.DataBinder;

import java.util.Arrays;
import java.util.Map;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

class DataBinderPolicyTest {

    private DataBinder binder(ProfileForm form, String... fields) {
        DataBinder binder = new DataBinder(form, "profileForm");
        binder.setAllowedFields(fields);
        return binder;
    }

    @Test
    void allowedNicknameAndSuppressedAdmin() {
        var form = new ProfileForm();
        var binder = binder(form, "nickname");

        binder.bind(new MutablePropertyValues(Map.of(
                "nickname", "Lan", "admin", "true")));

        assertEquals("Lan", form.getNickname());
        assertFalse(form.isAdmin());
        assertArrayEquals(new String[] {"admin"},
                binder.getBindingResult().getSuppressedFields());
    }

    @Test
    void suppressedDoesNotAutomaticallyMeanBindingError() {
        var binder = binder(new ProfileForm(), "nickname");

        binder.bind(new MutablePropertyValues(
                Map.of("admin", "true")));

        assertFalse(binder.getBindingResult().hasErrors());
        assertArrayEquals(new String[] {"admin"},
                binder.getBindingResult().getSuppressedFields());
    }

    @Test
    void compareMultipleSuppressedFieldsWithoutOrdering() {
        var form = new ProfileForm();
        var binder = binder(form, "nickname", "address.city");

        binder.bind(new MutablePropertyValues(Map.of(
                "nickname", "Lan",
                "admin", "true",
                "address.verified", "true")));

        Set<String> suppressed = Set.copyOf(Arrays.asList(
                binder.getBindingResult().getSuppressedFields()));

        assertEquals(Set.of("admin", "address.verified"),
                suppressed);
        assertFalse(form.isAdmin());
    }

    @Test
    void nestedCityIsBoundButVerifiedFlagIsNot() {
        var form = new ProfileForm();
        var binder = binder(form, "address.city");

        binder.bind(new MutablePropertyValues(Map.of(
                "address.city", "Da Nang",
                "address.verified", "true")));

        assertNotNull(form.getAddress());
        assertEquals("Da Nang", form.getAddress().getCity());
        assertFalse(form.getAddress().isVerified());
        assertArrayEquals(
                new String[] {"address.verified"},
                binder.getBindingResult().getSuppressedFields());
    }

    @Test
    void nestedAutoGrowIsEnabledByDefault() {
        var form = new ProfileForm();
        var binder = binder(form, "address.city");

        assertTrue(binder.isAutoGrowNestedPaths());
        binder.bind(new MutablePropertyValues(
                Map.of("address.city", "Hue")));

        assertEquals("Hue", form.getAddress().getCity());
    }

    @Test
    void disablingNestedAutoGrowDoesNotCreateAddress() {
        var form = new ProfileForm();
        var binder = new DataBinder(form, "profileForm");
        binder.setAutoGrowNestedPaths(false);
        binder.setIgnoreInvalidFields(false);
        binder.setAllowedFields("address.city");

        assertThrows(NullValueInNestedPathException.class,
                () -> binder.bind(new MutablePropertyValues(
                        Map.of("address.city", "Hue"))));

        assertNull(form.getAddress());
    }

    @Test
    void explicitIndexPolicySuppressesNextIndex() {
        var form = new ProfileForm();
        var binder = new DataBinder(form, "profileForm");
        binder.setAutoGrowCollectionLimit(2);
        binder.setAllowedFields("items[0].sku");

        binder.bind(new MutablePropertyValues(Map.of(
                "items[0].sku", "P01",
                "items[1].sku", "P02")));

        assertEquals(1, form.getItems().size());
        assertEquals("P01", form.getItems().get(0).getSku());
        assertArrayEquals(
                new String[] {"items[1].sku"},
                binder.getBindingResult().getSuppressedFields());
    }

    @Test
    void wildcardIndexBelowLimitCanGrowList() {
        var form = new ProfileForm();
        var binder = new DataBinder(form, "profileForm");
        binder.setAutoGrowCollectionLimit(2);
        binder.setAllowedFields("items*.sku");

        binder.bind(new MutablePropertyValues(
                Map.of("items[1].sku", "P02")));

        assertEquals(2, form.getItems().size());
        assertEquals("P02", form.getItems().get(1).getSku());
        assertFalse(binder.getBindingResult().hasErrors());
    }

    @Test
    void indexAtLimitIsNotAllowedToAutoGrowArrayList() {
        var form = new ProfileForm();
        var binder = new DataBinder(form, "profileForm");
        binder.setAutoGrowCollectionLimit(2);
        binder.setAllowedFields("items*.sku");

        assertThrows(InvalidPropertyException.class,
                () -> binder.bind(new MutablePropertyValues(
                        Map.of("items[2].sku", "P03"))));

        assertTrue(form.getItems().size() <= 2);
    }

    @Test
    void hugeDisallowedIndexIsSuppressedWithoutGrowth() {
        var form = new ProfileForm();
        var binder = binder(form, "nickname");

        binder.bind(new MutablePropertyValues(
                Map.of("items[999999].sku", "P99")));

        assertEquals(0, form.getItems().size());
        assertArrayEquals(
                new String[] {"items[999999].sku"},
                binder.getBindingResult().getSuppressedFields());
    }

    @Test
    void standardDefaultCollectionLimitIs256() {
        var binder = new DataBinder(
                new ProfileForm(), "profileForm");

        assertEquals(
                DataBinder.DEFAULT_AUTO_GROW_COLLECTION_LIMIT,
                binder.getAutoGrowCollectionLimit());
        assertEquals(256, binder.getAutoGrowCollectionLimit());
    }

    @Test
    void configurationAfterResultInitializationFails() {
        var binder = new DataBinder(
                new ProfileForm(), "profileForm");

        binder.getBindingResult();
        assertThrows(IllegalStateException.class,
                () -> binder.setAutoGrowCollectionLimit(2));
    }

    @Test
    void declarativeModeWithoutAllowlistSkipsSetters() {
        var form = new ProfileForm();
        var binder = new DataBinder(form, "profileForm");
        binder.setDeclarativeBinding(true);

        binder.bind(new MutablePropertyValues(Map.of(
                "nickname", "Lan", "admin", "true")));

        assertNull(form.getNickname());
        assertFalse(form.isAdmin());
        assertEquals(0,
                binder.getBindingResult()
                        .getSuppressedFields().length);
    }

    @Test
    void declarativeModeWithAllowlistBindsOnlyNickname() {
        var form = new ProfileForm();
        var binder = new DataBinder(form, "profileForm");
        binder.setDeclarativeBinding(true);
        binder.setAllowedFields("nickname");

        binder.bind(new MutablePropertyValues(Map.of(
                "nickname", "Lan", "admin", "true")));

        assertEquals("Lan", form.getNickname());
        assertFalse(form.isAdmin());
        assertArrayEquals(new String[] {"admin"},
                binder.getBindingResult().getSuppressedFields());
    }

    @Test
    void unrestrictedPropertyBindingCanSetAdmin() {
        var form = new ProfileForm();
        var binder = new DataBinder(form, "profileForm");

        binder.bind(new MutablePropertyValues(
                Map.of("admin", "true")));

        // Negative-security regression: why an allowlist is necessary.
        assertTrue(form.isAdmin());
    }
}
~~~

These **15 unit tests** are designed to verify two boundaries clearly: **which property names may bind** and **how far the list can grow**. The test `indexAtLimitIsNotAllowedToAutoGrowArrayList` relies on `InvalidPropertyException` behavior in Spring 6.1/6.2 with standard `ArrayList`; if switching implementations or Spring versions, confirm the actual exception rather than asserting raw exception messages.

### 8.5. File `BindingControllerTest.java` — 7 MockMvc tests

Create `src/test/java/com/example/bindingtests/BindingControllerTest.java`:

~~~java
package com.example.bindingtests;

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
class BindingControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validFieldsReachController() throws Exception {
        mvc.perform(post("/binding/profile")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("nickname", "Lan")
                    .param("address.city", "Da Nang")
                    .param("items[0].sku", "P01"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.nickname").value("Lan"))
                .andExpect(jsonPath("$.city").value("Da Nang"))
                .andExpect(jsonPath("$.itemCount").value(1))
                .andExpect(jsonPath("$.admin").value(false));
    }

    @Test
    void secondItemWithinLimitCanGrow() throws Exception {
        mvc.perform(post("/binding/profile")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("nickname", "Lan")
                    .param("items[1].sku", "P02"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.itemCount").value(2));
    }

    @Test
    void overpostedAdminIsRejectedByController() throws Exception {
        mvc.perform(post("/binding/profile")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("nickname", "Lan")
                    .param("admin", "true"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_INPUT"));
    }

    @Test
    void nestedVerifiedFieldIsSuppressed() throws Exception {
        mvc.perform(post("/binding/profile")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("nickname", "Lan")
                    .param("address.city", "Da Nang")
                    .param("address.verified", "true"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_INPUT"));
    }

    @Test
    void itemDiscountIsNotWritable() throws Exception {
        mvc.perform(post("/binding/profile")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("nickname", "Lan")
                    .param("items[0].sku", "P01")
                    .param("items[0].discount", "99"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_INPUT"));
    }

    @Test
    void thirdSkuIndexIsSuppressedBeforeTraversal() throws Exception {
        mvc.perform(post("/binding/profile")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("nickname", "Lan")
                    .param("items[2].sku", "P03"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_INPUT"));
    }

    @Test
    void blankNicknameFailsBeanValidation() throws Exception {
        mvc.perform(post("/binding/profile")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("nickname", ""))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_INPUT"));
    }
}
~~~

**7 MockMvc tests** confirm that `@InitBinder` actually applies to HTTP requests. In particular, the 3rd-index HTTP test proves the **allowlist** blocks before property traversal; the wildcard unit test proves the **auto-grow** boundary. The two must not be conflated.

### 8.6. Running tests

~~~bash
./mvnw test -Dtest=DataBinderPolicyTest,BindingControllerTest
~~~

On Windows:

~~~powershell
mvnw.cmd test -Dtest=DataBinderPolicyTest,BindingControllerTest
~~~

Or `mvn test` if Maven is installed. There are **22 test cases** in total designed to pass when the code and dependencies match. Do not claim Maven/JUnit has been executed merely because the test sources exist. Surefire/JUnit output varies by configuration; the assertions themselves are the **exact contract**.

## 9. Test matrix and result analysis

| Group | Input/test | Expected outcome |
| --- | --- | --- |
| Positive allowlist | `nickname=Lan` | Nickname receives the exact string. |
| Overposting | `admin=true` | Admin remains false, field is suppressed. |
| Suppression vs errors | Only send `admin=true` | `hasErrors()==false`, suppressed non-empty. |
| Multi-suppressed | Admin + address verified | Compare `Set.of(...)` without ordering assumptions. |
| Nested allowed | `address.city=Hue` when address is null | Auto-creates Address, sets city. |
| Nested disallowed | `address.verified=true` | Verified flag stays unchanged. |
| Disable nested growth | `address.city=Hue`, autoGrow=false | Does not create Address; exception per test config. |
| Indexed allowlist | `items[0].sku` | Item 0 is assigned. |
| Indexed forbidden | `items[1].sku` when only index 0 allowed | Item 1 suppressed. |
| Boundary limit | `items[1].sku` with limit 2 | List has 2 elements. |
| Boundary overflow | `items[2].sku` with limit 2 | Third element not created; Spring 6.1/6.2 throws InvalidPropertyException. |
| Large index denied | `items[999999].sku` outside allowlist | Suppressed before list access. |
| Declarative without allowlist | Setter-only target | Does not bind setters; does not necessarily populate suppressed list. |
| Declarative with allowlist | Nickname and admin | Only nickname binds, admin suppressed. |
| No allowlist anti-pattern | `admin=true` | Test shows admin **can** become true. |
| HTTP positive | Valid form nickname/city/SKU | HTTP 200; values match. |
| HTTP overpost | Admin/verified/discount/index2 | HTTP 400 per controller policy. |
| Bean Validation | Blank nickname | HTTP 400 due to `@NotBlank`. |

Run tests before and after changing:
- Form DTO fields, nested object graph, or collection types.
- `@ModelAttribute` and `@InitBinder` names.
- Allowed field patterns, max list size, auto-grow settings.
- Spring Framework/Boot versions.
- MVC ↔ WebFlux, form ↔ JSON pipelines.

**Never make a test pass by loosening `allowedFields` too broadly**, unless the product/security contract genuinely permits that field.

## 10. When not to expect suppressedFields

### 10.1. Constructor-only binding

`setDeclarativeBinding(true)` allows constructor binding and skips property binding if `allowedFields` is not configured. That **does not mean** every extra HTTP key gets recorded in `getSuppressedFields()`. If the requirement is "every unknown input key returns 400", add a strict input schema check.

### 10.2. JSON body

`@RequestBody` JSON goes through Jackson/HTTP message converters. `WebDataBinder#setAllowedFields(...)` is not a whitelist for JSON properties. Use dedicated DTOs, configure Jackson's unknown-key policy, check JSON size/nesting, and validate collection constraints.

### 10.3. Unknown properties and suppressed fields

`setIgnoreUnknownFields(true)` ignores input properties that have no match on the target by default. It is not designed as an overposting error list. By contrast, `getSuppressedFields()` reflects fields rejected by the **binder policy**. If a strict schema is required, test unknown-field detection separately.

### 10.4. Type mismatch and validator errors

If `quantity` is allowed but receives `"abc"` which cannot convert to `int` → `FieldError` of type `typeMismatch`. The `@NotBlank` constraint on nickname is evaluated only when a validation step runs. Neither is a suppressed field, even though both should normally result in 400 at the API layer.

## 11. Security and auto-grow limits

### 11.1. Do not treat default 256 as a whole-HTTP-request limit

`autoGrowCollectionLimit=256` only controls one form of array/list growth inside the data binder. It does not replace:

- HTTP body size and total parameter count limits.
- Schemas for allowed indexed property names.
- Nesting depth limits and domain-level collection element counts.
- JSON parser constraints and Jackson settings.
- Service-layer authorization; never let clients change roles, tenants, or admin flags.
- Dedicated input DTOs; never bind directly onto JPA entities with sensitive setters.

For a form with at most 2 SKUs, configuring `allowedFields("items[0].sku","items[1].sku")` alongside `setAutoGrowCollectionLimit(2)` is easier to test safely than wildcard `items*`.

### 11.2. Spring Advisory CVE-2026-59282 (2026-08-20)

Spring published **CVE-2026-59282 — Denial of Service via Unbounded List Growth in Data Binding**, concerning **self-populating custom List** implementations whose `get(index)` operation creates elements automatically. When a nested property path uses a client-supplied index, such a list can allocate memory as soon as it is accessed, even when the binder limit prevents normal growth.

Spring documentation lists affected branches, for example:
- **7.0.0–7.0.8**, OSS patch **7.0.9**.
- **6.2.0–6.2.19**, patch **6.2.20** via the corresponding support channel.
- Branches 6.1/6.0/5.x also have dedicated patched releases per the advisory.

This is a **collection-implementation-specific issue**, **not the standard `ArrayList` in the test suite above**. Mitigation: upgrade Spring Framework per the advisory; do not pass untrusted indexed paths to self-populating lists; use small DTOs, explicit allowlists, request size limits, and input index bounds. **Never stress production with an unbounded-allocation PoC** just to test.

Official Spring source: https://spring.io/security/cve-2026-59282/

### 11.3. Safe testing instead of resource-exhaustion attacks

The test suite uses `items[1]`/`items[2]` with limit 2 to test boundaries, and uses a large key only when the allowlist blocks it **before traversal**. If implementing a custom collection, write security tests checking contract and memory budgets in a sandboxed environment with resource limits. Never run huge indexes against an unpatched self-populating collection.

## 12. Troubleshooting

### `getSuppressedFields()` is empty despite extra fields in the request

Check whether `@InitBinder` matches the right object name, whether `setAllowedFields` was called, whether constructor-only declarative mode or JSON `@RequestBody` is in use, and whether the field actually goes through the property-binding filter. Setting `setDeclarativeBinding(true)` without an allowlist skips **all setter binding**, so the suppressed list will not necessarily contain those keys.

### `address.city` is not assigned

Verify `Address` can be instantiated (public no-arg constructor/bean access), `setAutoGrowNestedPaths(true)`, exact allowed path `address.city`, getters/setters, and target object state. If `getBindingResult()` was called before configuring auto-grow, fix the initialization order.

### `items[1].sku` does not auto-grow

Check for a mutable `List`, an instantiable generic element type, `autoGrowNestedPaths` enabled, limit sufficient for index+1, matching allowed path, and whether the initial collection was replaced with an immutable `List.of(...)`. Not every List implementation supports mutation/auto-grow.

### Out-of-limit test throws an exception instead of returning HTTP 400

This is infrastructure behavior. Do not add `@ExceptionHandler(Exception.class)` returning 400 for everything. If out-of-bounds index inputs need a consistent 400 response, **reject keys/indexes against the route contract before binder traversal**, or handle a properly classified input error. Keep it separate from real server errors.

### `hasErrors()` is false even though admin was blocked

Expected in many setups: suppression is not synonymous with FieldError. The policy check should also inspect `getSuppressedFields().length > 0`.

### Sending JSON but allowedFields does not block unknown keys

Because JSON uses Jackson rather than the form property binder. Separate the DTO, deserialization policy, and tests.

### Upgrading versions causes specific exception tests to fail

Spring may adjust handling of invalid indexes, error resolution, or API packages. Keep the **security invariants**: do not bind forbidden fields, do not grow lists past policy, return the defined status. Then update the expected exception type if implementation details changed—never loosen the allowlist to hide a failure.

## 13. Pre-release testing checklist

- [ ] Include a positive test for every allowed field.
- [ ] Include negative tests for `admin`, `role`, `tenantId`, nested verification, and discount.
- [ ] Assert the target object is **not modified** by forbidden fields.
- [ ] Test `getSuppressedFields()` with single and multiple fields; do not assume order.
- [ ] Test `hasErrors()` separately from `getSuppressedFields()`.
- [ ] Test nested paths created from null when auto-grow is on; not created when off.
- [ ] Test the last valid index and first out-of-bounds index for `autoGrowCollectionLimit`.
- [ ] Test that auto-grow flags are configured **before** binder initialization.
- [ ] Test exact indexed allowlists and wildcards separately.
- [ ] Do not confuse suppressed indexes with indexes exceeding the auto-grow limit.
- [ ] Test `setDeclarativeBinding(true)` with and without an allowlist.
- [ ] Test form binding and JSON `@RequestBody` on separate pipelines.
- [ ] Test that `@InitBinder("...")` and `@ModelAttribute("...")` names match.
- [ ] Test `@Valid`, conversion errors, unknown keys, and business authorization separately.
- [ ] Include HTTP integration tests (MockMvc or WebTestClient depending on stack).
- [ ] Never return rejected values or internal object fields in responses/logs.
- [ ] Enforce request-size, parameter-count, index/schema, and nesting limits.
- [ ] Verify the Spring version patches data-binding security advisories.
- [ ] Do not use self-populating custom Lists with untrusted indexed input without risk assessment.
- [ ] Re-run security regression tests whenever DTOs, binder config, controllers, or dependencies change.

**Conclusion:** Testing `allowedFields` must verify both **allowed assignments** and **suppressed fields**; testing `autoGrowCollectionLimit` must target exact **boundary indexes** while recognizing it only constrains one form of property binding. `BindingResult#hasErrors()` does not replace `getSuppressedFields()`, while `setDeclarativeBinding(true)`/constructor binding and JSON take separate paths. Combining `DataBinder` unit tests, MockMvc integration tests, and DTO/authorization/payload policies reduces mass-assignment risk, binding regressions, and uncontrolled resource growth.

## References

- Spring Framework Javadoc 6.2 — `DataBinder`, `setAllowedFields`, `setAutoGrowCollectionLimit`, and `setDeclarativeBinding`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework Javadoc 6.2 — `BindingResult#getSuppressedFields()`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/BindingResult.html
- Spring Framework Reference 6.2 — Data Binding: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-data-binding.html
- Spring Framework Reference 6.2 — `@InitBinder`: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Framework Reference 6.2 — `@ModelAttribute`: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework Reference 6.2 — WebFlux data binding: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-initbinder.html
- Spring Security Advisory (2026-08-20) — CVE-2026-59282: https://spring.io/security/cve-2026-59282/
- OWASP Mass Assignment Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html
