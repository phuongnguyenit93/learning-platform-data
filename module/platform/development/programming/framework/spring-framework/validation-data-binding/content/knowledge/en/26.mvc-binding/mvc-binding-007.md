# Binding Collections, Maps, and Indexed Field Names in Spring MVC

## 1. Problem: a form is not just flat fields

An order entry page often has multiple line items, optional labels, and grouped contact details:

- Line item 0: code `PEN`, quantity `2`.
- Line item 1: code `BOOK`, quantity `1`.
- Label `priority` has value `high`.
- Email of group `support` is `help@example.com`.

With Spring MVC's `@ModelAttribute`, this data can flow from request parameters into a Java object containing `List` and `Map` properties **without manually parsing parameter names**. For Spring to know which element is being updated, the HTML form must name its inputs using **bracketed property paths** (*indexed/keyed property paths*).

~~~text
items[0].sku                 = PEN
items[0].quantity            = 2
items[1].sku                 = BOOK
items[1].quantity            = 1
labels[priority]             = high
contacts[support].email      = help@example.com
tags[0]                     = spring
~~~

Desired structure in Java:

~~~text
OrderForm
├── items: List<LineItem>
│   ├── [0] -> { sku="PEN",  quantity=2 }
│   └── [1] -> { sku="BOOK", quantity=1 }
├── labels: Map<String, String>
│   └── ["priority"] -> "high"
├── contacts: Map<String, Contact>
│   └── ["support"] -> { email="help@example.com" }
└── tags: List<String>
    └── [0] -> "spring"
~~~

Four key points:

1. `[0]`, `[1]` are **positions** in a `List`/array, starting at 0; `[priority]` and `[support]` are **keys** in a `Map`.
2. The dot `.` navigates into a property of the **object inside the element**, e.g., `items[0].sku` and `contacts[support].email`.
3. Spring reads field names from the **request**, converts types, and assigns values via `WebDataBinder`. This is **data binding**, distinct from Bean Validation.
4. Client-sent path names are **untrusted input**. Restrict bindable fields, maximum index, and request size, and validate the structure before running business logic.

The context of this article is the **Spring MVC Servlet stack**, primarily with `application/x-www-form-urlencoded` or multipart forms and `@ModelAttribute`. JSON goes through `@RequestBody` and Jackson via a separate mechanism, distinguished in section 8.

## 2. Field name syntax and how it is interpreted

| Field name in request/HTML | Target Java property | Meaning |
| --- | --- | --- |
| `customerName` | `String customerName` | Simple property |
| `address.city` | `Address address` | Nested property |
| `items[0].sku` | `List<LineItem> items` | `sku` of the list element at index 0 |
| `items[3].quantity` | `List<LineItem> items` | `quantity` of the element at index 3 |
| `tags[0]` | `List<String> tags` | String at index 0 |
| `codes[1]` | `String[] codes` | Array element at index 1 |
| `labels[priority]` | `Map<String,String> labels` | Value for key `"priority"` |
| `contacts[support].email` | `Map<String,Contact> contacts` | `email` property of the object under key `"support"` |

Square brackets are interpreted according to the **declared property type**:

- For `List<T>` or an array, the value inside brackets is a **non-negative integer index**.
- For `Map<K,V>`, the value inside brackets is interpreted as a **key**, which may require conversion to type `K` (e.g., `Integer`).
- For nested beans, dots separate properties along the object graph.
- For multi-level object graphs, paths like `groups[0].members[1].name` can be used if actual properties, constructors, setters, and data structures support them.

`items[0].sku` is the **complete parameter name**. Do not write `items.0.sku` to mimic an index; for JavaBean property binding, the two are not equivalent. Do not use an unindexed name `items` expecting it to always split into multiple `LineItem` instances; for lists of objects, use explicit indexed fields.

### Corresponding HTML form

~~~html
<form method="post" action="/orders">
  <input name="items[0].sku" value="PEN">
  <input name="items[0].quantity" type="number" value="2">

  <input name="items[1].sku" value="BOOK">
  <input name="items[1].quantity" type="number" value="1">

  <input name="labels[priority]" value="high">
  <input name="contacts[support].email" type="email"
         value="help@example.com">
  <input name="tags[0]" value="spring">

  <button type="submit">Submit Order</button>
</form>
~~~

Browsers URL-encode special characters on form submission. For example, `items[0].sku` may appear as `items%5B0%5D.sku` in the HTTP body. Spring receives values already decoded by the Servlet container, so the logical field name remains `items[0].sku`.

If using Thymeleaf, once the model holds `orderForm`, you can write `th:field="*{items[0].sku}"` inside `th:object="\${orderForm}"`. In that case Thymeleaf generates appropriate `name` and `id` attributes. Binding errors for that field can be displayed with `th:errors="*{items[0].sku}"`. **The HTML lines above are plain HTML**, requiring no Thymeleaf dependency in the Maven example below.

## 3. Spring MVC pipeline: request → object → errors

~~~text
HTTP form/query parameters
      |
      | items[0].sku=PEN, labels[priority]=high, ...
      v
Spring MVC handler argument @ModelAttribute("orderForm")
      |
      v
Create/retrieve OrderForm instance
      |
      v
WebDataBinder for current request
  |-- check allowedFields
  |-- resolve property paths: items[0].sku, labels[priority]
  |-- auto-grow nested/list paths within configured limits
  |-- ConversionService/PropertyEditor converts String -> Integer, ...
  |-- record conversion errors in BindingResult
      |
      v
@Valid / @Validated (if requested)
  |-- @NotBlank, @NotNull, @Min, @Valid, ...
  |-- add validation errors to BindingResult
      |
      v
Controller:
  BindingResult.hasErrors() -> handle errors or proceed with business logic
~~~

`WebDataBinder` operates on the named object in MVC; by default Spring supports **constructor binding** and **property binding**. The examples use mutable JavaBeans with no-args constructors and setters to clearly demonstrate property binding and indexed property paths. For records/immutable DTOs, Spring also supports constructor binding and various indexed/keyed parameter styles; however, **property binding's auto-grow capability is not a feature of constructor binding**.

If a request sends `items[0].quantity=abc` while the Java property is `Integer`, the error belongs to **conversion/binding**, not `@Min`. Conversely, `items[0].quantity=0` converts cleanly, yet fails `@Min(1)` during validation. Both show up in `BindingResult`, though their causes and error codes differ.

Note: `@ModelAttribute` does not create a `Map` in the same way as `@RequestParam Map<String,String>`. In this lesson, we bind into a **form object's `labels` property**, whereas `@RequestParam Map` typically captures a flat map of request parameters (section 8).

## 4. Runnable project: Java 17 and Spring Boot 3.5.7

The example uses:
- Spring MVC with `@ModelAttribute` accepting form-urlencoded input.
- `List<LineItem>` for line items; `List<String>` for tags.
- `Map<String,String>` for labels; `Map<String,Contact>` for keyed contacts.
- `@Valid`, Bean Validation, and `BindingResult` reporting errors at exact paths.
- `@InitBinder` to guard property binding and limit auto-grow indices.

Structure:

~~~text
pom.xml
src/main/java/com/example/binding/
  BindingApplication.java
  LineItem.java
  Contact.java
  OrderForm.java
  OrderController.java
src/test/java/com/example/binding/
  OrderControllerTest.java
  DataBinderTest.java
~~~

### 4.1. Maven configuration

~~~xml
<!-- pom.xml -->
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
    <artifactId>indexed-binding-demo</artifactId>
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

`spring-boot-starter-web` provides Spring MVC and JSON response support; `spring-boot-starter-validation` adds the Jakarta Validation provider; `spring-boot-starter-test` supplies JUnit 5 and MockMvc integration. The sample needs no database.

### 4.2. Application entry point

~~~java
// src/main/java/com/example/binding/BindingApplication.java
package com.example.binding;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BindingApplication {
    public static void main(String[] args) {
        SpringApplication.run(BindingApplication.class, args);
    }
}
~~~

### 4.3. Collection element DTO

~~~java
// src/main/java/com/example/binding/LineItem.java
package com.example.binding;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class LineItem {
    @NotBlank(message = "SKU must not be blank")
    private String sku;

    @NotNull(message = "Quantity is required")
    @Min(value = 1, message = "Quantity must be at least 1")
    private Integer quantity;

    public LineItem() {
    }

    public String getSku() {
        return sku;
    }

    public void setSku(String sku) {
        this.sku = sku;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}
~~~

`LineItem` has a **public no-args constructor** and property getters/setters. When property binding needs to grow `items[0]` into an instance, Spring has a path to instantiate the object and navigate into `sku` or `quantity`. In immutable or constructor-based binding models, ensure matching constructor mappings instead of expecting auto-instantiation via setters.

### 4.4. DTO for an object-valued Map entry

~~~java
// src/main/java/com/example/binding/Contact.java
package com.example.binding;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

public class Contact {
    @NotBlank(message = "Email must not be blank")
    @Email(message = "Invalid email format")
    private String email;

    public Contact() {
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
~~~

In `Map<String, Contact>`, the name `contacts[support].email` needs to locate the `Contact` object under key `support` and then set its `email` property. To avoid depending on whether a missing map key is auto-instantiated in every context, the example **pre-populates the `support` key** in `OrderForm`.

### 4.5. Form object with List, Map, and nested Map value

~~~java
// src/main/java/com/example/binding/OrderForm.java
package com.example.binding;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class OrderForm {

    @NotEmpty(message = "At least one line item is required")
    private List<@NotNull @Valid LineItem> items = new ArrayList<>();

    @Size(max = 4, message = "Maximum four tags")
    private List<@NotBlank String> tags = new ArrayList<>();

    private Map<String, @NotBlank String> labels = new LinkedHashMap<>();

    private Map<String, @Valid Contact> contacts = new LinkedHashMap<>();

    // Included solely to demonstrate mass assignment; clients must not modify it.
    private boolean managerApproved;

    public OrderForm() {
        contacts.put("support", new Contact());
    }

    public List<LineItem> getItems() {
        return items;
    }

    public void setItems(List<LineItem> items) {
        this.items = items;
    }

    public List<String> getTags() {
        return tags;
    }

    public void setTags(List<String> tags) {
        this.tags = tags;
    }

    public Map<String, String> getLabels() {
        return labels;
    }

    public void setLabels(Map<String, String> labels) {
        this.labels = labels;
    }

    public Map<String, Contact> getContacts() {
        return contacts;
    }

    public void setContacts(Map<String, Contact> contacts) {
        this.contacts = contacts;
    }

    public boolean isManagerApproved() {
        return managerApproved;
    }

    public void setManagerApproved(boolean managerApproved) {
        this.managerApproved = managerApproved;
    }
}
~~~

Explanation:

- `List<@NotNull @Valid LineItem>`: elements cannot be `null`, and Bean Validation cascades into each item's `sku`/`quantity`.
- `@NotEmpty` on `items`: the list must contain at least one element.
- `List<@NotBlank String> tags`: each tag cannot be whitespace-only; `@Size(max=4)` limits collection size.
- `Map<String,@NotBlank String> labels`: constraints apply to each entry's **value**, not its key.
- `Map<String,@Valid Contact> contacts`: validation cascades into `Contact` instances when validating `OrderForm`.
- `contacts.put("support", new Contact())`: pre-creates the object for nested path `contacts[support].email`, keeping binding behavior clear and consistent.
- `managerApproved` is an example of a property **clients should not be able to manipulate**. Real applications should keep approval authority in service/domain logic and omit sensitive properties from form DTOs.

Important: generic type arguments carrying `@Valid`/constraints are read by Jakarta Validation during validation; Spring's use of generic types to infer which element type to instantiate/convert during **binding** is a separate step.

### 4.6. Controller and `@InitBinder` restricting fields/indices

~~~java
// src/main/java/com/example/binding/OrderController.java
package com.example.binding;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

@RestController
public class OrderController {

    @InitBinder("orderForm")
    void configureBinder(WebDataBinder binder) {
        binder.setAllowedFields(
                "items[*].sku",
                "items[*].quantity",
                "tags[*]",
                "labels[priority]",
                "contacts[support].email"
        );
        binder.setAutoGrowNestedPaths(true);
        binder.setAutoGrowCollectionLimit(8);
    }

    @PostMapping(
            path = "/orders",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<Map<String, Object>> submit(
            @Valid @ModelAttribute("orderForm") OrderForm form,
            BindingResult result) {

        if (result.hasErrors()) {
            List<String> fields = result.getFieldErrors().stream()
                    .map(FieldError::getField)
                    .distinct()
                    .sorted()
                    .toList();
            return ResponseEntity.badRequest()
                    .body(Map.of("errors", fields));
        }

        return ResponseEntity.ok(Map.of(
                "itemCount", form.getItems().size(),
                "firstSku", form.getItems().get(0).getSku(),
                "tags", form.getTags(),
                "priority", form.getLabels()
                        .getOrDefault("priority", ""),
                "supportEmail", form.getContacts()
                        .get("support").getEmail(),
                "managerApproved", form.isManagerApproved()
        ));
    }
}
~~~

**`@InitBinder("orderForm")`** customizes the binder only for the model attribute named `orderForm` in this controller. Other object names need their own configuration; this lesson avoids applying settings indiscriminately to the whole model.

`setAllowedFields(...)` establishes an **allowlist**. Patterns support `*`:
- `items[*].sku` permits `items[0].sku`, `items[1].sku`, etc.
- `items[*].quantity` permits binding each line's quantity.
- `tags[*]` permits binding indexed tags.
- `labels[priority]` permits only the `priority` key in `labels`.
- `contacts[support].email` permits updating email only on the `support` entry.

Any other property binding field, such as `managerApproved=true` or `contacts[admin].email=x`, is excluded from the bound property values. They are typically recorded in **`BindingResult#getSuppressedFields()`**, without necessarily creating a `FieldError`. In production, consider monitoring suppressed fields; never return sensitive details or rejected values directly to clients.

`setAutoGrowCollectionLimit(8)` is an **auto-grow limit for arrays/lists** during property binding, not a total HTTP request size limit and not a direct cap on map keys. It prevents creating hundreds or thousands of list slots from an arbitrarily large index. Behavior when a request exceeds the limit depends on whether the path is reached and how exceptions are handled; enforce input/index validation at the HTTP/application layer if you always want a 400 response. **Do not assume this setting guarantees malicious requests always return 400.**

`BindingResult` sits **immediately after** the `@ModelAttribute` parameter. This ordering is required for Spring to attach binding/validation results to that exact form object. If the form has errors, the example returns HTTP 400 with the list of field names; if valid, it returns a summary JSON response without persisting data.

### 4.7. Sending test requests with curl

~~~bash
curl -i -X POST http://localhost:8080/orders \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "items[0].sku=PEN" \
  --data-urlencode "items[0].quantity=2" \
  --data-urlencode "items[1].sku=BOOK" \
  --data-urlencode "items[1].quantity=1" \
  --data-urlencode "labels[priority]=high" \
  --data-urlencode "contacts[support].email=help@example.com" \
  --data-urlencode "tags[0]=spring"
~~~

Expected JSON response (key order is not guaranteed):

~~~json
{
  "itemCount": 2,
  "firstSku": "PEN",
  "tags": ["spring"],
  "priority": "high",
  "supportEmail": "help@example.com",
  "managerApproved": false
}
~~~

To run the application:

~~~bash
mvn spring-boot:run
~~~

The `curl` command above is for shells supporting `\` line continuation (Linux/macOS or Git Bash). On PowerShell, use a single-line `curl.exe` command or PowerShell line continuation; do not paste Unix `\` line continuations verbatim into PowerShell 5.1.

## 5. Testing indexed binding, map binding, and mass assignment protection

### 5.1. MockMvc integration test

~~~java
// src/test/java/com/example/binding/OrderControllerTest.java
package com.example.binding;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasItem;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void bindsListMapAndNestedMapObject() throws Exception {
        mvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("items[0].sku", "PEN")
                .param("items[0].quantity", "2")
                .param("items[1].sku", "BOOK")
                .param("items[1].quantity", "1")
                .param("labels[priority]", "high")
                .param("contacts[support].email", "help@example.com")
                .param("tags[0]", "spring")
                .param("managerApproved", "true"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.itemCount").value(2))
            .andExpect(jsonPath("$.firstSku").value("PEN"))
            .andExpect(jsonPath("$.priority").value("high"))
            .andExpect(jsonPath("$.supportEmail")
                    .value("help@example.com"))
            .andExpect(jsonPath("$.tags[0]").value("spring"))
            .andExpect(jsonPath("$.managerApproved").value(false));
    }

    @Test
    void validationErrorsRetainIndexedPaths() throws Exception {
        mvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("items[0].sku", " ")
                .param("items[0].quantity", "0")
                .param("labels[priority]", "high")
                .param("contacts[support].email", "bad-email"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.errors",
                    hasItem("items[0].sku")))
            .andExpect(jsonPath("$.errors",
                    hasItem("items[0].quantity")));
    }

    @Test
    void conversionFailureRetainsTheOriginalFieldPath()
            throws Exception {
        mvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("items[0].sku", "PEN")
                .param("items[0].quantity", "not-an-integer")
                .param("contacts[support].email", "help@example.com"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.errors",
                    hasItem("items[0].quantity")));
    }
}
~~~

The first test proves the list accepts two consecutive items, the string map receives key `priority`, the object map accesses key `support` to bind its email, and the tag is assigned at index 0. More importantly, the client tries sending `managerApproved=true`, yet the response remains `false` because the field is absent from `allowedFields`. This tests **mass assignment protection**, not validation: the property is simply never assigned.

The second test checks `@NotBlank` and `@Min(1)` errors at the exact paths `items[0].sku` and `items[0].quantity`. The third test sends a string that cannot convert to `Integer`, proving binding errors also pinpoint the exact indexed path. The tests do not assert exact message text because message locales can differ.

### 5.2. Direct `DataBinder` test to inspect suppressed fields

~~~java
// src/test/java/com/example/binding/DataBinderTest.java
package com.example.binding;

import org.junit.jupiter.api.Test;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.DataBinder;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class DataBinderTest {

    @Test
    void bindsAllowedIndexedPathsAndSuppressesForbiddenField() {
        OrderForm form = new OrderForm();
        DataBinder binder = new DataBinder(form, "orderForm");

        binder.setAllowedFields(
                "items[*].sku",
                "items[*].quantity"
        );
        binder.setAutoGrowCollectionLimit(8);

        binder.bind(new MutablePropertyValues(Map.of(
                "items[0].sku", "PEN",
                "items[0].quantity", "2",
                "managerApproved", "true"
        )));

        assertEquals(1, form.getItems().size());
        assertEquals("PEN", form.getItems().get(0).getSku());
        assertEquals(2, form.getItems().get(0).getQuantity());
        assertFalse(form.isManagerApproved());

        assertArrayEquals(
                new String[]{"managerApproved"},
                binder.getBindingResult().getSuppressedFields()
        );
    }
}
~~~

Using `DataBinder` directly is helpful when HTTP or controllers are unnecessary. `MutablePropertyValues` passes parameter-like name/value pairs to the binder; we inspect both the bound object and the rejected field list. This test **only tests binding** and does not invoke Bean Validation, because neither `binder.validate()` nor a validator on the binder is configured.

Run tests:

~~~bash
mvn test
~~~

With the code above, **4 JUnit tests are expected to PASS**: 3 MockMvc tests and 1 direct DataBinder test. This is the expected outcome per framework semantics; exact Maven/Surefire log line counts and test execution order vary by environment, so Maven stdout is not hardcoded here.

## 6. BindingResult: which index/key failed?

### 6.1. Binding errors vs validation errors

For example, both requests below make `BindingResult#hasErrors()` return `true`, for different reasons:

~~~text
items[0].quantity=abc
   -> String "abc" cannot convert to Integer
   -> binding/conversion error, code is typically typeMismatch

items[0].quantity=0
   -> converts to Integer 0
   -> violates @Min(1) during validation
   -> validation error, code is typically Min
~~~

Spring stores the full field path in `FieldError#getField()`, e.g., `items[0].quantity`. With Maps and nested values, `FieldError#getField()` can contain paths like `contacts[support].email` or container-element paths formatted by the Bean Validation provider. If processing raw `ConstraintViolation` paths directly, inspect `Path.Node` (kind/index/key) when precision is needed rather than guessing from string paths.

To inspect error codes, you can read:

~~~java
// Illustrative snippet inside a handler that already has BindingResult result.
for (var error : result.getFieldErrors()) {
    String field = error.getField();       // e.g. "items[0].quantity"
    String code = error.getCode();         // e.g. "typeMismatch" or "Min"
    String message = error.getDefaultMessage();

    // Depending on architecture, map field/code/message to a safe response.
}
~~~

Never return raw `FieldError#getRejectedValue()` to clients, because some forms may contain sensitive data. In the controller example, the response lists only the **field names** that had errors.

### 6.2. `@Valid` on List/Map and element constraints

In `OrderForm`, constraints operate at three levels:

~~~java
@NotEmpty
private List<@NotNull @Valid LineItem> items;

@Size(max = 4)
private List<@NotBlank String> tags;

private Map<String, @Valid Contact> contacts;
~~~

The snippet above shows only **abbreviated declarations**; the complete runnable code is in section 4.

- `@NotEmpty` checks that the `items` collection itself is not empty.
- `@NotNull` on the type argument checks that each element is non-null.
- `@Valid` on the type argument cascades into `LineItem.sku` and `LineItem.quantity`.
- `@NotBlank` on `List<String>` checks each individual tag (not the list itself).
- `@Valid` on the `Map` value cascades into `Contact.email`.

Container element extractors (*value extractors*) for `List`/`Map` are built into standard Jakarta Validation providers. For custom container types, a matching `ValueExtractor` is required for type-argument constraints to work.

**Binding does not equal validation:** `items[0].sku=" "` can bind cleanly; only after `@Valid` runs is `@NotBlank` flagged. Conversely, a binding type error does not need `@Min` to tell that the input is invalid.

### 6.3. Multi-level nested Lists

The same rules extend to nested lists:

~~~text
groups[0].members[0].name = An
groups[0].members[1].name = Binh
groups[1].members[0].name = Chi
~~~

Suppose the form has `List<GroupForm> groups` and each `GroupForm` has `List<MemberForm> members`. The path breaks down as:
- `groups[0]`: selects the group element at index 0.
- `members[1]`: selects member index 1 within that group.
- `name`: property on the selected member.

For binding to succeed, intermediate properties must also have appropriate structures and instantiation mechanisms. Using multiple levels of indexing also increases auto-grow risk, so control nesting depth, element counts, and submitted payloads.

## 7. Auto-grow: convenient but bounded

### 7.1. Why is auto-grow needed?

A new form starts with:

~~~java
private List<LineItem> items = new ArrayList<>();
~~~

Initially the list is empty. Upon receiving `items[0].sku=PEN`, the property binder can **grow the list**, instantiate `LineItem` at index 0 via its no-args constructor, and call `setSku("PEN")`. If a path encounters a `null` nested object and a default instantiation path exists, `setAutoGrowNestedPaths(true)` allows traversing into that property.

By default `DataBinder` enables auto-grow nested paths with a default collection auto-grow limit of **256** (in Spring Framework 6.x). `setAutoGrowCollectionLimit(int)` adjusts this cap; this lesson sets **8** to demonstrate reducing risk on small forms.

### 7.2. Avoid sending sparse indices arbitrarily

~~~text
items[0].sku=PEN
items[7].sku=BOOK
~~~

Spring may have to allocate/grow intermediate slots `1..6`. Depending on element type and binder behavior, they may become default objects or `null`; this is not a reliable way to represent “two line items”. If a form has only two rows left after the user deletes items, **renumber indices consecutively**:

~~~text
items[0].sku=PEN
items[1].sku=BOOK
~~~

Do not assume `items[-1]`, `items[9999999]`, or a malformed index will automatically turn into `BindingResult`/HTTP 400. Spring may throw an exception when a property is inaccessible or exceeds the limit. If an API must return consistent errors, validate counts/indices before or inside an appropriate request-handling layer, and cap body sizes at the server/proxy.

### 7.3. Auto-grow limit is not a quota for Maps

`setAutoGrowCollectionLimit` governs array/collection auto-growing during **setter/property binding**. It does not directly stop a client from sending thousands of `labels[someKey]` keys. For Maps:

- Allow only expected keys, e.g., `labels[priority]`, if business logic has a fixed key set.
- When keys are genuinely dynamic, validate key allowlists/format/length and limit **entry count** after binding or at the input layer.
- Never bind directly into an internal domain map that could hold sensitive properties/permissions.
- Enforce request size, parameter count, and object-graph depth limits outside `DataBinder` as needed.

**Do not raise `autoGrowCollectionLimit` to a huge number** just because a form is dynamic. Set the limit to the maximum legitimate item count, and consider a different API design if the form structure grows too large.

### 7.4. Constructor binding is a separate mechanism

Spring supports constructor binding for immutable objects, including `List`, `Map`, and array parameters via indexed keys or convertible values. However, the Javadoc for `setAutoGrowNestedPaths`/`setAutoGrowCollectionLimit` states they apply to **property binding via `bind(PropertyValues)`**, not to constructor binding via `construct(ValueResolver)`.

Therefore, if switching the mutable `OrderForm` to records:

~~~java
public record OrderInput(
        List<LineItemInput> items,
        Map<String, String> labels
) {}

public record LineItemInput(String sku, Integer quantity) {}
~~~

test constructor binding separately for the corresponding field names, conversion, and validation rather than expecting JavaBean setter auto-instantiation behavior to stay identical. The records above are an **alternative model option**, not part of the runnable project in section 4.

## 8. Distinguishing `@ModelAttribute`, `@RequestParam`, and `@RequestBody`

### 8.1. `@ModelAttribute` for HTML forms

~~~java
@PostMapping("/orders")
public void submit(@ModelAttribute("orderForm") OrderForm form) {
    // form.getItems(), form.getLabels(), ...
}
~~~

This is an illustrative handler without validation/response handling. Using `@ModelAttribute`, Spring MVC binds request parameters (query/form, plus supported value sources) into the object graph. This is the exact context for `items[0].sku` and `labels[priority]`.

### 8.2. `@RequestParam Map` for flat parameters

~~~java
@PostMapping("/raw")
public void raw(@RequestParam Map<String, String> params) {
    String sku = params.get("items[0].sku");
    // key is the raw parameter name, not a List<LineItem>.
}
~~~

With `@RequestParam Map<String,String>`, keys are **parameter names** and values are raw request strings. The method above does not construct `OrderForm.items`. If a key can have multiple values, consider `MultiValueMap<String,String>`, since `Map<String,String>` retains only one value per key.

### 8.3. `@RequestBody` for JSON

In JSON, object and array structures are represented using native JSON syntax:

~~~json
{
  "items": [
    {"sku": "PEN", "quantity": 2},
    {"sku": "BOOK", "quantity": 1}
  ],
  "labels": {"priority": "high"},
  "contacts": {
    "support": {"email": "help@example.com"}
  },
  "tags": ["spring"]
}
~~~

Controller:

~~~java
@PostMapping("/orders-json")
public void submitJson(@Valid @RequestBody OrderForm body) {
    // Jackson converts JSON -> Java DTO; @Valid validates the DTO.
}
~~~

This is an illustrative snippet; this method is not in the runnable source from section 4. In the JSON pipeline, **Jackson** deserializes arrays and maps from JSON structure; it does not treat string field names like `items[0].sku` as JavaBean property indices along the form-binding path. `WebDataBinder#setAllowedFields` in section 4 is **not a JSON deserialization allowlist**. For JSON, use dedicated input DTOs alongside appropriate Jackson and validation policies. Do not assume an `@InitBinder` protects `@RequestBody` endpoints the same way it protects form binding.

### 8.4. Flat Lists/Maps and simple form patterns

With repeated parameters sharing one name, for example:

~~~text
tag=java&tag=spring
~~~

Spring can resolve this directly into `@RequestParam List<String> tag`; this differs from the `tags[0]` property path in `@ModelAttribute`. Do not mix the two styles haphazardly; choose one clear request contract and test the exact payload your browser/client sends.

## 9. Security: from mass assignment to oversized payloads

### 9.1. Over-posting / mass assignment

If a form object exposes a setter `setManagerApproved(boolean)`, a client can freely submit:

~~~text
managerApproved=true
~~~

With unrestricted property binding, Spring can invoke that setter. In the example, `@InitBinder` permits only `items[*].sku`, `items[*].quantity`, `tags[*]`, `labels[priority]`, and `contacts[support].email`. Consequently, `managerApproved` is suppressed even though the class still has the setter.

**Safer design:** omit sensitive properties such as roles, payment status, manager approval, and `ownerId` from web input DTOs that have setters. Domain entities and web forms have separate responsibilities. Allowlist binding is an extra line of defense, never an excuse to casually reuse domain entities as form objects.

### 9.2. `allowedFields` is better than denylists alone

~~~java
// Illustrates the principle in @InitBinder:
binder.setAllowedFields(
        "items[*].sku",
        "items[*].quantity",
        "labels[priority]"
);
~~~

The `*` pattern is not a full regular expression; Spring supports wildcard patterns for property names. Allowlists must account for nested paths as well. Using an overly broad `items*` pattern can inadvertently allow unintended item properties. Prefer specific paths and tightly controlled field groups.

`setDisallowedFields(...)` can block certain fields, but denylists easily miss newly added fields as DTOs evolve. For untrusted input, allowlists and dedicated DTOs are much easier to keep secure.

### 9.3. Brackets are not proof of authorization

A key like `contacts[admin].email` only states that the client wants to target key `admin`; it **does not prove** the user is allowed to edit that contact. When handling dynamic keys, the server must verify ownership/authorization for every entry against authenticated user data. Never use client-sent map keys as an authorization basis.

Similarly, `items[0].id` may appear in an entity-editing form. Never read an ID from input and update blindly: query records scoped by tenant/owner, verify permissions, and explicitly map only permitted fields.

### 9.4. Limit both structure and values

Beyond `@Size(max=4)` on `tags`, consider:
- Maximum list/map element counts (at both HTTP layer and model/business validation).
- Maximum index and total nested path depth.
- String key/value lengths and total request body size.
- Maximum request parameter count accepted by the Servlet container.
- Rate limiting if the endpoint can be abused.

`@Size` runs **after binding**, so it is insufficient on its own to protect **data structure construction**. Do not rely on post-binding validation to prevent all forms of resource exhaustion inside the binder.

## 10. Common pitfalls and how to fix them

| Symptom | Common cause | How to check/fix |
| --- | --- | --- |
| `items[0].sku` is not populated | Target lacks matching property/constructor/setter, or blocked by allowlist | Check DTO, `@InitBinder`, `getSuppressedFields()` |
| `items[2]` fails on empty list | Auto-grow unavailable or index exceeds limit | Send consecutive indices, configure reasonable limit, check binding mode |
| `contacts[support].email` cannot be accessed | Map entry `support` has no object yet, or no instantiation path | Pre-populate key/value or define clear binding strategy |
| `items[0].quantity=abc` causes an error | `String` cannot convert to `Integer` | Check `BindingResult`, error code `typeMismatch` |
| `items[0].quantity=0` causes an error | Conversion succeeded but violates `@Min(1)` | Check validation messages and rules |
| `items[0].sku` binds but blank value isn't flagged | `@Valid` not running or element cascading missing | Use `@Valid @ModelAttribute` and `List<@Valid Item>` |
| `labels[priority]` is ignored | `allowedFields` lacks the exact path/key | Check patterns, case sensitivity, and suppressed fields |
| Client sends `managerApproved=true` and value changes | Sensitive property exposed to binding | Use dedicated DTO, allowlist, never let clients manage internal state |
| Form field name mismatches error | Using `items.0.sku` or wrong index renaming | Verify literal `name` and `FieldError#getField()` |
| JSON has key `items[0].sku` but list stays empty | JSON uses Jackson, not form indexed property-name binding | Send proper JSON array/object structure |
| Data lost after deleting a dynamic row | Client-side indices left gaps | Renumber indices consecutively before submitting |
| Request with huge index throws an exception | Growth limit or property accessibility exceeded | Reject early, configure size/index limits, test boundaries |

### Complex Map keys

Map keys like `billing.eu` or `special[guest]` can conflict intuitively with dot/bracket property path syntax. If your application accepts arbitrary keys, check the parser/escaping behavior of **your running Spring version** and add round-trip tests from request name → Map key. For standard forms, prefer simple, stable keys containing only alphanumeric characters and underscores to ease debugging and reduce property-path injection risks.

### Sets and collections without stable indices

`Set<T>` does not have stable element positions like `List<T>`. For forms with repeating rows, `List<LineItem>` is usually more suitable because indices `[0]`, `[1]` match input order. If the business domain requires a `Set` to prevent duplicates, bind into a `List` on the input DTO first, validate, then convert to a `Set` in the service layer and handle duplicates explicitly.

### Arrays and index limits

`String[]` can use `codes[0]`, `codes[1]` through bean property binding when the binder can grow arrays within limits. Arrays are less convenient than `List` for forms with dynamic row additions/removals. With the same data, test both index 0 and large indices to confirm behavior matches your configured growth limit.

## 11. Practical application checklist

1. Design a dedicated web DTO: properties and setters strictly for valid input.
2. Use well-structured field names: `items[0].sku`, `tags[1]`, `labels[priority]`, `contacts[support].email`.
3. For bean `List`s, prepare generic types, no-args constructors, and matching property setters; use consecutive indices starting at 0.
4. For object-valued `Map`s, clarify which keys/values exist and how nested objects are created; do not assume arbitrary map keys are auto-instantiated.
5. Configure `@InitBinder`/`allowedFields` and auto-grow limits according to legitimate form size. Do not rely on auto-grow limits as the sole defense.
6. Apply `@Valid`/`@Validated` and constraints at the right levels: collection, element, nested object; place `BindingResult` immediately after the model attribute.
7. Distinguish conversion error codes like `typeMismatch` from constraint errors like `NotBlank` and `Min`; preserve indexed field paths in responses.
8. Write MockMvc tests covering lists, maps, nested maps, multiple indices, type mismatches, blank inputs, and over-posting.
9. If an API receives JSON, use `@RequestBody` with native JSON arrays/objects and dedicated deserialization protections.
10. Bound input size, check authorization for Map keys/object IDs, and never bind directly onto domain entities.

## References

- Spring Framework 6.2 – MVC Data Binding: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-data-binding.html
- Spring Framework 6.2 – `@ModelAttribute` method arguments, indexed constructor binding: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework 6.2 – Core Data Binding: https://docs.spring.io/spring-framework/reference/6.2/core/validation/data-binding.html
- Spring Framework 6.2 – DataBinder Javadoc (`setAllowedFields`, `setAutoGrowCollectionLimit`): https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework 6.2 – `BindingResult` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/BindingResult.html
- Spring Boot 3.5 – Validation: https://docs.spring.io/spring-boot/3.5/reference/io/validation.html
