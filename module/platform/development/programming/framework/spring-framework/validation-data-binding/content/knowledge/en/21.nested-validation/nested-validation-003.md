# Container Element Constraints: Validating Elements in List<@NotBlank String> and Nested Containers

## 1. The Problem: Validate the List or Validate Each Element?

An endpoint receives a list of tags:

```json
{
  "tags": ["java", " ", "spring"]
}
```

If the DTO only declares `@NotEmpty List<String> tags`, the list has three elements and therefore passes the non-empty constraint. However, the second element is a string containing only spaces, which should not be accepted if tags must have content.

Jakarta Bean Validation solves this with **container element constraints**: placing an annotation directly on the element type rather than only on the list variable itself.

```java
import java.util.List;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;

public record TagRequest(
        @NotEmpty List<@NotBlank String> tags) {
}
```

The two annotations check **two different levels**:

- `@NotEmpty` placed on `List`: the list must not be null or empty.
- `@NotBlank` placed on the `String` type argument: every element in the list must be non-null and contain at least one non-whitespace character.
- `List<@NotBlank String>` does not mean "at least one element is valid"; **every element yielded by the container must satisfy the constraint**.
- If the entire list is `null` and there is no `@NotEmpty` or `@NotNull` on the container, the engine has no elements to validate; an element constraint does not automatically catch a missing container.

This is a **Bean Validation** (Jakarta Validation) feature, which Spring integrates into the binding/validation process when an appropriate trigger is present; Java generics by themselves do not check values at runtime.

After this lesson, you should be able to explain annotation placement accurately, distinguish container/element/cascade checks, apply them to List/Set/Map/Optional/nested containers, understand `ValueExtractor`, and test results via `Validator` and Spring MVC.

## 2. TYPE_USE Syntax and the Role of Each Annotation

Since Bean Validation 2.0, standard constraints can be placed at **type use** positions (`ElementType.TYPE_USE`) inside generic type arguments:

```java
List<@NotBlank String> names;
List<@NotNull Integer> counts;
List<@Positive Integer> quantities;
List<@Email String> emails;
List<@Valid Address> addresses;
```

These are illustrative fragments; the `Address` class must be defined and the annotations must be imported.

Reading each line accurately:

- `List<@NotBlank String>`: rejects `null`, `""`, and whitespace-only strings for each element.
- `List<@NotNull Integer>`: rejects null elements; negative numbers or zero are still allowed unless constrained otherwise.
- `List<@Positive Integer>`: each non-null number must be greater than 0; `@Positive` alone **allows null**, so add `@NotNull` if null is disallowed.
- `List<@Email String>`: validates email format on non-null elements; if a non-blank email is required, combine `@NotBlank @Email`.
- `List<@Valid Address>`: traverses into each `Address` bean and checks constraints **inside** that bean. `@Valid` is a cascade directive, not a String validation constraint.

The following declarations have different meanings:

```java
@NotEmpty List<String> tags;               // Check List only
List<@NotBlank String> tags;               // Check elements only
@NotEmpty List<@NotBlank String> tags;     // Both List and elements
```

**Do not write `@NotBlank List<String> tags`** to require non-blank elements. `@NotBlank` is designed for `CharSequence`; when applied to `List`, a standard Bean Validation provider has no compatible `ConstraintValidator` and may throw `UnexpectedTypeException` instead of validating all the strings.

To avoid confusion with nested `@Valid` forms, remember this diagram:

```text
@NotEmpty  List<@NotBlank String>
    |         |
    |         +-- constraint runs on each String
    +------------ constraint runs on the List itself

@NotNull   List<@NotNull @Valid Address>
    |                  |       |
    |                  |       +-- descends into Address constraints
    |                  +---------- Address element must not be null
    +----------------------------- the List itself must not be null
```

## 3. Understanding the Outcome of List<@NotBlank String>

Suppose the declaration is:

```java
record Form(@NotEmpty List<@NotBlank String> tags) {}
```

The following table distinguishes container errors from element errors:

| Value of `tags` | `@NotEmpty` on List | `@NotBlank` on Element | Conclusion |
| --- | --- | --- | --- |
| `null` | Fail | Cannot traverse elements | Invalid |
| `[]` | Fail | No elements | Invalid |
| `["java"]` | Pass | Pass | Valid |
| `["java", "spring"]` | Pass | All pass | Valid |
| `[""]` | Pass | Fail | Invalid |
| `[" "]` | Pass | Fail | Invalid |
| `[null]` | Pass | Fail because `@NotBlank` treats null as invalid | Invalid |
| `["ok", " "]` | Pass | Second element fails | Invalid |
| `["ok", null]` | Pass | Second element fails | Invalid |

`@NotBlank` differs from `@NotEmpty` when used on `String`: `@NotEmpty` accepts a string containing a single space, whereas `@NotBlank` does not. If content must not be all whitespace, use `@NotBlank`.

### 3.1. When Element Count Is Bounded

If you need at least 1 and at most 5 tags, and each tag must be between 2 and 20 characters:

```java
import java.util.List;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

record Tags(
        @Size(min = 1, max = 5)
        List<@NotBlank @Size(min = 2, max = 20) String> values) {
}
```

`@Size(min=1,max=5)` outside `List` limits the **number of elements**. `@Size(min=2,max=20)` inside limits **the length of each string**. `@NotBlank` also catches null and whitespace-only values; `@Size` on `String` normally treats null as valid, so do not omit `@NotBlank` when content is required.

None of the annotations in this example automatically trim leading/trailing whitespace or normalize letter casing. The string `" Java "` can still pass if it meets the rules. If business logic requires trimming/normalization, perform it explicitly per the data contract and test the order of **normalization before validation**.

## 4. The ValueExtractor Mechanism Behind the Scenes

When Bean Validation sees `List<@NotBlank String>` on a property being validated, it must extract **the elements** from the list. The standard mechanism is `jakarta.validation.valueextraction.ValueExtractor`.

```text
Validator.validate(request)
        |
        v
TagRequest.tags = List
        |
        +--> @NotEmpty evaluates the list
        |
        +--> Bean Validation detects @NotBlank on type argument
                   |
                   v
             List ValueExtractor
                   |
             +-----+-----+
             |     |     |
             0     1     2
             |     |     |
            "a"   " "   "b"
             |     |     |
             pass  fail  pass
```

Key points:

1. A container element constraint is **metadata attached to a `TYPE_USE` type argument**, not an annotation on an individual `String` instance.
2. The provider selects a `ValueExtractor` matching the container; for `List`, the extractor yields each element along with its corresponding index.
3. The engine applies the constraint to **the extracted values**. For `Map`, extractors for keys and values are distinct; for `Optional`, the extracted value can be null when the Optional is empty.
4. Errors carry `ConstraintViolation.getPropertyPath()` describing the path from the root bean to the element, usually including the list index or map key.
5. If a custom container (`Box<T>`, `Either<L,R>`, etc.) lacks a compatible value extractor, placing a type-argument constraint on it can cause a declaration/resolution error. The system must configure an appropriate `ValueExtractor`; **do not assume every generic class is supported out of the box**.

Bean Validation provides standard extractors for containers such as `Iterable`, `List`, `Map`, `Optional`, and primitive Optionals. Therefore, common cases like `List<@NotBlank String>` **do not require writing a custom ValueExtractor**.

### 4.1. Element Error Paths

With Hibernate Validator, an error on the second element of a `tags` list typically has a path like:

```text
tags[1].<list element>
```

When an error comes from a constraint inside a bean of `List<@Valid Address>`, you typically see a path such as:

```text
addresses[0].city
```

Container node names, how Spring maps paths to field errors, and the iteration order of `ConstraintViolation` sets may depend on the provider/version/integration. In tests, assert constraint types and paths based on the essential data; if you need a fixed error contract, explicitly define how `ConstraintViolation` is transformed into a stable response structure.

## 5. Distinguishing Element Constraints from Cascaded Validation with @Valid

Consider two cases:

```java
import java.util.List;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

record Address(@NotBlank String city) {}

record Form(
        List<@NotBlank String> tags,
        List<@Valid Address> addresses) {
}
```

- `List<@NotBlank String>` places a **constraint directly on the String value**; each String is validated **without needing @Valid on the List**.
- `List<@Valid Address>` instructs the provider to **enter each Address bean** to check `city`. If `@Valid` is omitted on the type argument and only `@NotBlank` exists inside `Address`, validating `Form` normally does not enter `Address.city`.
- `List<@NotNull @Valid Address>` also rejects `null` elements. `@Valid` alone does not treat a null bean element as a violation.
- Marking `@Valid` on the parent object validated by a Bean Validation provider **differs** from annotations on container elements. An entry point from a controller or `Validator.validate(...)` must exist first.

### 5.1. Do Not Duplicate @Valid on the Same Path

For containers holding beans that need cascading, you may encounter the legacy syntax:

```java
@Valid
List<Address> addresses;
```

The modern syntax explicitly states the element position:

```java
List<@Valid Address> addresses;
```

Along the same path, **there is no need** to use `@Valid List<@Valid Address>` simultaneously; Jakarta Bean Validation recommends choosing one way to mark cascading so elements are not validated twice. For String content constraints, use `List<@NotBlank String>`, and do not add `@Valid` just to make `@NotBlank` work.

### 5.2. @Valid Does Not Replace @NotNull or @NotEmpty

Each annotation addresses a distinct requirement:

| Requirement | Placement |
| --- | --- |
| List must exist | `@NotNull List<...>` |
| List must have elements | `@NotEmpty List<...>` |
| Every String is non-blank | `List<@NotBlank String>` |
| Every bean element is non-null | `List<@NotNull @Valid Address>` |
| Every child bean must have internal constraints checked | `List<@Valid Address>` |

An empty list has **no elements violating** `@NotBlank`; to require a non-empty list, you always need a constraint on the container.

## 6. Map: Constraining Keys and Values Differently

A `Map<K,V>` container has two type arguments, allowing each branch to be annotated independently:

```java
import java.util.Map;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

record Contact(@NotBlank String name) {}

record ContactDirectory(
        Map<@NotBlank String, @NotBlank @Email String> emailsByRole,
        Map<@NotBlank String, @NotNull @Valid Contact> contactsByRole) {
}
```

`emailsByRole` enforces:
- Each **key** (a role such as `"admin"` or `"support"`) is non-null and non-blank.
- Each **value** must be a non-null, non-blank String and a valid `@Email`; `@Email` alone generally does not require content, so combine it with `@NotBlank`.
- The Map itself can still be null or empty unless `@NotNull`/`@NotEmpty` is added to the Map.

`contactsByRole` also descends into `Contact.name` of each bean in **values**, though `@NotNull` is still needed on the value if you want to forbid null instead of letting cascade skip it.

Key takeaway: `Map<@NotBlank String, Contact>` checks **keys**, while `Map<String, @Valid Contact>` checks **bean contents in values**. Do not put annotations on the wrong type argument when writing multiple generics.

## 7. Optional and Nested Containers

### 7.1. Optional<T>

Example:

```java
import java.util.Optional;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

record Profile(
        Optional<@NotBlank String> nickname,
        Optional<@Valid Address> deliveryAddress) {
}
```

The `Optional` extractor retrieves the contained value, or passes **null** to the validator if `Optional.empty()`:

- `Optional.of("ok")` passes `@NotBlank`.
- `Optional.of(" ")` violates `@NotBlank`.
- `Optional.empty()` also **violates `@NotBlank` on the type argument**, because the extracted value is null and `@NotBlank` rejects null. If the field is genuinely optional, choose a constraint that accepts null, a different model, or a specific policy for Optional.
- With `Optional<@Valid Address>`, the empty case has no bean to cascade into and does not raise an error on its own; if an `Address` is present, its internal constraints are checked.

`@NotNull Optional<...>` only requires the **Optional object itself not to be null**; `Optional.empty()` is still a non-null instance. Do not treat `@NotNull` on `Optional` as checking whether a value is present inside. Also, never leave an `Optional` field itself as `null` if code expects safe `Optional` usage.

### 7.2. List of Lists

Constraints can be placed deep down on the type inside a second container:

```java
import java.util.List;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;

record Matrix(
        @NotEmpty
        List<@NotEmpty List<@NotBlank String>> groups) {
}
```

Here:
- Outermost `@NotEmpty`: there must be at least one group.
- `@NotEmpty` on the inner `List`: each group must be non-null/non-empty.
- `@NotBlank` on `String`: every string in every group must not be blank.

For example, `groups = [["java"], []]` will be rejected because the second group is empty. `groups = [["java"], [" "]]` is rejected because the string in the second group is blank. `groups = []` is rejected because the outer list of groups is empty.

Element constraints continue to run according to validation groups (`Default` or selected groups) just like regular field constraints; if a group is not part of the current validation pass, the constraint may not run.

## 8. Runnable Java 17+ Example: Jakarta Validator + Hibernate Validator

This program demonstrates the exact cases:
- a `List<@NotBlank String>` with whitespace and null elements;
- a `List<@NotNull @Valid Address>` with an invalid child bean and a null element;
- an empty container rejected by `@NotEmpty`;
- valid input producing zero violations.

The runtime requires the **Jakarta Validation API** and a **provider** such as Hibernate Validator. Running `javac` on a single file without a classpath will miss dependencies. The example below uses Maven and JDK 17+.

Directory structure:

```text
container-validation-demo/
├── pom.xml
└── src/main/java/example/ContainerConstraintDemo.java
```

### 8.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>container-validation-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.2.Final</version>
        </dependency>
        <dependency>
            <groupId>org.glassfish.expressly</groupId>
            <artifactId>expressly</artifactId>
            <version>5.0.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

In a real Spring Boot 3.x application, use Boot's dependency management and `spring-boot-starter-validation` rather than mechanically copying the pinned versions from this small example.

### 8.2. src/main/java/example/ContainerConstraintDemo.java

```java
package example;

import java.util.Arrays;
import java.util.List;
import java.util.Set;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

public final class ContainerConstraintDemo {

    public record Address(@NotBlank String city) {}

    public record Registration(
            @NotEmpty List<@NotBlank String> tags,
            @NotEmpty List<@NotNull @Valid Address> addresses) {
    }

    private static long countFor(
            Set<ConstraintViolation<Registration>> errors,
            String fieldPrefix) {

        return errors.stream()
                .filter(e -> e.getPropertyPath()
                        .toString().startsWith(fieldPrefix))
                .count();
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            Registration valid = new Registration(
                    List.of("java", "spring"),
                    List.of(new Address("Ha Noi")));

            Registration invalid = new Registration(
                    Arrays.asList("java", " ", null),
                    Arrays.asList(new Address(""), null));

            Registration empty = new Registration(
                    List.of(),
                    List.of(new Address("Da Nang")));

            System.out.println("valid="
                    + validator.validate(valid).size());

            Set<ConstraintViolation<Registration>> errors =
                    validator.validate(invalid);

            System.out.println("invalid=" + errors.size());
            System.out.println("tags=" + countFor(errors, "tags"));
            System.out.println("addresses=" + countFor(errors, "addresses"));
            System.out.println("emptyTags="
                    + validator.validate(empty).size());
        }
    }
}
```

In the `container-validation-demo` directory, run:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.ContainerConstraintDemo
```

Expected `System.out.println` lines (Maven/provider logs, if any, are separate):

```text
valid=0
invalid=4
tags=2
addresses=2
emptyTags=1
```

Exact explanation:
- `valid=0`: tags all have text, and Address has a valid city.
- `invalid=4`: `tags[1]` is whitespace-only, `tags[2]` is null, `addresses[0].city` is empty, `addresses[1]` is null.
- `tags=2`: both string errors come from `List<@NotBlank String>`, without needing `@Valid`.
- `addresses=2`: one `@NotBlank` error from the child bean due to `@Valid`, and one `@NotNull` error on the Address element.
- `emptyTags=1`: empty List violates `@NotEmpty` on the container, even though there are no elements to run `@NotBlank`.

`Arrays.asList(...)` is intentionally used in the invalid sample because it allows null elements; JDK's `List.of(...)` forbids null and would throw `NullPointerException` right when creating the list, before reaching Bean Validation.

The `countFor` helper uses a property path prefix to avoid depending on internal node details like `<list element>`; if you need to assert exact indices, add index assertions according to the provider used in your project.

## 9. JUnit 5 Unit Tests for Key Boundaries

This example uses the two public nested `record` types in `ContainerConstraintDemo` from Section 8. Create `src/test/java/example/ContainerConstraintTest.java`; configure JUnit Jupiter for Maven or your build system.

```java
package example;

import java.util.Arrays;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.Validation;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.ConstraintViolation;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ContainerConstraintTest {

    @Test
    void validatesEveryStringAndNestedBean() {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            var validator = factory.getValidator();

            var invalid = new ContainerConstraintDemo.Registration(
                    Arrays.asList("java", " ", null),
                    Arrays.asList(
                            new ContainerConstraintDemo.Address(""),
                            null));

            var violations = validator.validate(invalid);

            assertEquals(4, violations.size());

            Set<String> paths = violations.stream()
                    .map(v -> v.getPropertyPath().toString())
                    .collect(Collectors.toSet());

            assertTrue(paths.stream()
                    .anyMatch(path -> path.startsWith("tags[1]")));
            assertTrue(paths.stream()
                    .anyMatch(path -> path.startsWith("tags[2]")));
            assertTrue(paths.stream()
                    .anyMatch(path -> path.startsWith("addresses[0]")));
            assertTrue(paths.stream()
                    .anyMatch(path -> path.startsWith("addresses[1]")));
        }
    }

    @Test
    void rejectsEmptyListButAcceptsValidItems() {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            var validator = factory.getValidator();

            var empty = new ContainerConstraintDemo.Registration(
                    List.of(),
                    List.of(new ContainerConstraintDemo.Address("Hue")));
            assertEquals(1, validator.validate(empty).size());

            var valid = new ContainerConstraintDemo.Registration(
                    List.of("java", "spring"),
                    List.of(new ContainerConstraintDemo.Address("Hue")));
            assertTrue(validator.validate(valid).isEmpty());
        }
    }
}
```

**Additional test setup:** `pom.xml` in Section 8 only serves running `main`; to run JUnit 5, add a compatible `org.junit.jupiter:junit-jupiter` dependency and configure Maven Surefire accordingly. In a Spring Boot project, `spring-boot-starter-test` typically provides the required test dependencies. The test above is a Java file executable on a classpath that already has JUnit, not a Maven test ready to run immediately against the main-only `pom.xml`.

Run through your build's test task (e.g., `mvn test` after adding JUnit/Surefire), then verify violation paths on your project's provider version. The assertions here verify real runtime behavior rather than just checking for annotations via reflection.

## 10. Integrating into Spring MVC: @RequestBody DTO Wrapping a List

For HTTP APIs receiving JSON, use a **request DTO** to clearly express container and element constraints. With Spring Boot 3.x, you typically need `spring-boot-starter-web` along with `spring-boot-starter-validation` and a Boot entry point with appropriate component scanning.

### 10.1. DTO and Controller

**File `src/main/java/com/example/api/LabelRequest.java`:**

```java
package com.example.api;

import java.util.List;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;

public record LabelRequest(
        @NotEmpty List<@NotBlank String> labels) {
}
```

**File `src/main/java/com/example/api/LabelController.java`:**

```java
package com.example.api;

import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class LabelController {

    @PostMapping("/labels")
    public ResponseEntity<Void> create(
            @Valid @RequestBody LabelRequest request) {

        // Validation demonstration only; data is not persisted.
        return ResponseEntity.noContent().build();
    }
}
```

Two notable positions:
1. `@Valid` on the method parameter tells Spring MVC that after Jackson deserializes JSON into `LabelRequest`, MVC should apply Bean Validation to this root object.
2. `List<@NotBlank String>` in the DTO tells the Bean Validation provider to check **each label** when the root is validated. No extra `@Valid` is needed on the `labels` field just because the elements are Strings.

With a configured Bean Validation provider and a controller using standard MVC validation:

| JSON body | Result |
| --- | --- |
| `{"labels":["java","spring"]}` | 204 No Content |
| `{"labels":[]}` | 400 Bad Request due to `@NotEmpty` |
| `{"labels":[""]}` | 400 due to `@NotBlank` on element |
| `{"labels":["java"," "]}` | 400 due to whitespace-only second label |
| `{"labels":["java",null]}` | 400 due to `@NotBlank` on null |
| `{"labels":null}` | 400 due to `@NotEmpty` on List |
| `{}` | Usually 400 because `labels` deserializes to null, then `@NotEmpty` fails |
| Unparseable JSON | Deserialization error (typically 400) before Bean Validation |

**Do not assume a single universal JSON error response format.** That depends on Spring Boot version, Problem Details, `@ControllerAdvice`, and message configuration. Bean Validation errors on a `@Valid @RequestBody` command object in MVC typically go through `MethodArgumentNotValidException`; JSON parsing errors may go through `HttpMessageNotReadableException`.

### 10.2. MockMvc Verifying That Elements Are Actually Rejected

**File `src/test/java/com/example/api/LabelControllerTest.java`:**

```java
package com.example.api;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.MethodArgumentNotValidException;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(LabelController.class)
class LabelControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void acceptsValidLabels() throws Exception {
        mvc.perform(post("/labels")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"labels\":[\"java\",\"spring\"]}"))
                .andExpect(status().isNoContent());
    }

    @Test
    void rejectsBlankElement() throws Exception {
        mvc.perform(post("/labels")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"labels\":[\"java\",\" \"]}"))
                .andExpect(status().isBadRequest())
                .andExpect(result -> {
                    assertTrue(result.getResolvedException()
                            instanceof MethodArgumentNotValidException);

                    var ex = (MethodArgumentNotValidException)
                            result.getResolvedException();

                    assertTrue(ex.getBindingResult().getFieldErrors()
                            .stream()
                            .anyMatch(e -> e.getField()
                                    .startsWith("labels[1]")));
                });
    }

    @Test
    void rejectsEmptyContainer() throws Exception {
        mvc.perform(post("/labels")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"labels\":[]}"))
                .andExpect(status().isBadRequest());
    }
}
```

`@WebMvcTest` requires appropriate test dependencies (typically `spring-boot-starter-test`) and an active validation provider in the test context. The tests prove both list-level and element-level constraints rather than merely asserting annotations exist in source code.

### 10.3. Why Not Write `@RequestBody List<@NotBlank String>` Directly?

Example:

```java
@PostMapping("/labels")
void create(@Valid @RequestBody List<@NotBlank String> labels) {
    // You cannot assume by default that MVC will validate a List directly as a command object.
}
```

The snippet above is a **discussion fragment**, not a guaranteed endpoint contract. Per Spring MVC's mechanism, `@Valid @RequestBody` on a command object (DTO) has a different bean validation path than when the parameter is directly a `Collection`/`Map`. Method validation also has its own activation rules, especially in Spring MVC 6.1+. If an API needs to accept a raw JSON array directly, test the actual validation mechanism or enable appropriate method validation; **a wrapper DTO is the clearest, most maintainable approach** when validating `List<@NotBlank String>`.

## 11. Container Element Constraints on Method Parameters and Return Values

Outside DTOs, Jakarta Bean Validation allows placing type argument constraints on:
- fields and bean getters;
- method or constructor parameters;
- method return value types.

Fragment example:

```java
import java.util.List;
import jakarta.validation.constraints.NotBlank;

public interface LabelService {
    List<@NotBlank String> normalize(
            List<@NotBlank String> incoming);
}
```

The annotations describe **input and output** constraints on the method. However, if the method is called as plain Java `new LabelServiceImpl().normalize(...)`, the annotations do not run automatically. A method validation mechanism that actually invokes `ExecutableValidator` is needed; for Spring service beans, this is typically method validation via Spring proxy/AOP when configured and invoked from outside the proxy.

Spring MVC 6.1+ has built-in method validation for handler methods when constraints appear directly on method parameters/return values. `@Valid` is **not** a constraint annotation; `@Valid` alone does not mean "every method will automatically be validated." Exceptions can differ between request object validation (`MethodArgumentNotValidException`) and method validation (`HandlerMethodValidationException`).

For return values, Bean Validation may run after the method returns; output failures typically indicate a server/invariant bug and should not blindly return HTTP 400 like client input errors.

## 12. Validation Groups and Relationship with @Validated

Example of a constraint active only during creation:

```java
import java.util.List;
import jakarta.validation.constraints.NotBlank;
import org.springframework.validation.annotation.Validated;

interface CreateGroup {}

record Command(
        List<@NotBlank(groups = CreateGroup.class) String> tags) {
}

// Snippet of a controller with MVC validation mechanism:
void create(@Validated(CreateGroup.class) Command command) {
}
```

During a `CreateGroup` validation pass, each String in `tags` is subject to that group's `@NotBlank` constraint. When validating only the `Default` group, constraints assigned solely to `CreateGroup` **do not run automatically**. Group behavior for container elements works just like regular field constraints; annotation placement does not alter the group.

Distinguish:
- `@Valid` (Jakarta): tells the provider to descend into child beans/cascade paths, or in MVC serves as the marker to validate a DTO at the entry point.
- `@Validated` (Spring): supports selecting validation groups at Spring integration points and is used in certain method validation configurations.
- `@NotBlank`: is the constraint that **actually validates** the String value; when placed inside `List<...>`, it applies to each element.

If a child bean needs a group change during cascading, Jakarta Bean Validation provides `@ConvertGroup` along the `@Valid` path. Do not add `@ConvertGroup` to every container when the contract does not require group switching.

## 13. Common Mistakes When Writing Container Element Constraints

1. **Putting `@NotBlank` on the whole List:** `@NotBlank List<String>` is the wrong constraint type; place it on the type argument like `List<@NotBlank String>`.
2. **Using only `@NotEmpty List<String>`:** the list can still contain `""`, `" "`, or `null`; element constraints are needed.
3. **Using only `List<@NotBlank String>`:** a null or empty List may report no errors; `@NotNull`/`@NotEmpty` on the List is needed per contract.
4. **Using `@Valid` for Strings:** `@Valid` does not substitute for `@NotBlank`; `String` has no internal constraints to cascade into.
5. **Forgetting `@Valid` on bean elements:** `List<Address>` does not automatically check `Address.city` when validating the root; use `List<@Valid Address>`.
6. **Forgetting `@NotNull` on object elements:** `@Valid` skips null beans; use `List<@NotNull @Valid Address>` if null elements are forbidden.
7. **Forgetting to trigger Bean Validation:** annotations on DTOs do not run when calling `new`; you need `Validator.validate` or Spring integration.
8. **Missing a provider on the classpath:** having only the Jakarta Validation API without Hibernate Validator/a provider will not run validation fully.
9. **Confusing List structure with field paths:** indices may appear alongside `<list element>` nodes; inspect according to your provider/integration.
10. **Putting annotations on the wrong `Map` type argument:** keys and values are two independent positions.
11. **Assuming `Optional.empty()` is always valid:** if the type argument carries `@NotBlank`, the extractor supplies null and can violate it; `@Valid` handles null differently.
12. **Writing `@Valid List<@Valid Address>`:** duplicate annotations on the same path can cause redundant traversal; pick one cascade location.
13. **Putting constraints on a custom generic without an extractor:** you must provide a compatible `ValueExtractor`.
14. **Assuming controllers accepting a List directly are always validated:** test Spring MVC method validation and consider a wrapper DTO.
15. **Thinking malformed JSON types are `@NotBlank` errors:** deserialization/binding can fail before Bean Validation runs.
16. **Believing validated fields keep every layer safe:** services, message consumers, batch jobs, and repositories have other entry points; ensure validation is actually triggered.
17. **Relying on unstable error structures:** for consistent API responses, map fields/indices/codes explicitly instead of hardcoding English messages or `Set<ConstraintViolation>` order.

## 14. Practice Checklist

1. Determine whether the container needs **a value** (`@NotNull`), **elements** (`@NotEmpty`), or an element count limit (`@Size`).
2. Place constraints on the exact **extracted value type**, e.g., `List<@NotBlank String>`, `List<@Positive Integer>`, `Map<@NotBlank String, @Email String>`.
3. For child beans, use `List<@Valid Address>`; add `@NotNull` for elements if required. Do not repeat `@Valid` on the same path.
4. For nested containers, annotate each level per requirements: `List<@NotEmpty List<@NotBlank String>>`.
5. Consider `null` at **three places**: null container, empty container, null element; each case requires different constraints.
6. Ensure the provider supports the extractor; standard containers use built-in extractors, custom containers require designing a `ValueExtractor`.
7. Test directly at bean level with `Validator.validate` using valid, empty, whitespace, null elements, and nested beans.
8. Test Spring MVC end-to-end with `MockMvc`, asserting HTTP status and violated fields/indices; if accepting JSON, also test deserialization errors separately from validation.
9. If using validation groups/method validation, test the active group and invocations through real Spring integration/proxies.
10. Keep error responses stable by categorizing container, element, and nested object errors rather than relying on default messages/locales.

### References

- [Jakarta Bean Validation 3.0 Specification — Container element constraints and ValueExtractor](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html).
- [Hibernate Validator 8 Reference Guide — Container element constraints](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/).
- [Spring Framework — Validation in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html).
- [Spring Framework — @RequestBody and @Valid](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html).
- [Spring Framework — Bean Validation integration](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html).
