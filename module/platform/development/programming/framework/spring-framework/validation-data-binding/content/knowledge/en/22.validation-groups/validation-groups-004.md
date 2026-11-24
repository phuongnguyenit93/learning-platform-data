# Create, Update, and Specialized Task Groups in Jakarta Validation and Spring

> **Module:** Spring Framework – validation-data-binding  
> **Topic:** Validation groups  
> **Focus:** Designing `Create`, `Update`, and task-specific groups such as `Publish`, `Approve`, and `Dispatch`; selecting the right constraints at each trigger point using Spring `@Validated` while ensuring shared rules are not missed.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain why a DTO type needs different rule sets for creation, updates, and specialized business steps.
2. Define groups using **marker interfaces** and declare `groups` on Jakarta Validation constraints.
3. Distinguish the `Default` group from `Create`, `Update`, and `Publish`; understand that selecting a custom group **does not implicitly run** `Default`.
4. Use `@Validated({Default.class, Create.class})` in Spring MVC and `Validator.validate(bean, groups...)` in tests.
5. Design group inheritance, group sequences, and group conversions where needed; recognize when to split DTOs instead of stacking more groups.
6. Apply validation to forms and JSON requests while distinguishing controller validation from service method validation.
7. Write and run a Java 17+ example with deterministic output for all groups and group combinations.
8. Avoid confusing validation groups with authorization, workflow state, transaction rules, or database constraints.

## 2. The Problem: One Object, Multiple Contexts

Suppose a document management system has the workflow:

~~~text
Create Draft (Create) --> Edit (Update) --> Publish (Publish)
                                         \
                                          --> Approve (Approve)
~~~

Each task has different requirements:

| Field | Create | Update | Publish | Approve |
| --- | --- | --- | --- | --- |
| `id` | Must be `null` (server-generated) | Required | Required | Depends on task contract |
| `title` | Must not be blank | Must not be blank | Must not be blank | May not need to be sent |
| `ownerEmail` | Valid email syntax | Valid email syntax | Valid email syntax | Depends on contract |
| `reviewed` | Not checked yet | Not checked yet | Must be `true` | May be unrelated |
| `approver` | Not needed yet | Not needed yet | Not needed yet | Must not be blank |

If a DTO places all constraints in the default group, creation could be blocked because `id` has not been generated yet, or updates could be blocked because `reviewed` is not `true` even though publishing has not happened yet.

**Validation groups** let the same constraint take effect only when **the corresponding group is requested**. This is a **Jakarta Validation** mechanism, not a feature limited to Spring.

Three layers must be kept distinct:

~~~text
1. Constraint metadata on the DTO
   @NotNull(groups = Update.class)
   @AssertTrue(groups = Publish.class)

2. Execution context
   @Validated({Default.class, Update.class})
   or validator.validate(dto, Update.class, Default.class)

3. Result
   Set<ConstraintViolation<T>> / BindingResult / HTTP errors
~~~

Writing `groups` is only **declaring the rules**. Without a `Validator` or Spring integration triggering validation, annotations do not run automatically when instantiating a bean, calling a constructor, or calling setters.

## 3. How to Define a Group

A group is typically an empty interface:

~~~java
public interface Create {}
public interface Update {}
public interface Publish {}
public interface Approve {}
~~~

These interfaces serve solely as **group names**; the DTO does not need to `implements` them, nor do they need any methods.

A manageable way to organize them in a real project:

~~~java
package example.validation;

public final class ValidationGroups {
    private ValidationGroups() {}

    public interface Create {}
    public interface Update {}
    public interface Publish {}
    public interface Approve {}
    public interface Dispatch {}
}
~~~

The `ValidationGroups.java` file above compiles with plain Java 17. Later you can reference them, for example:

~~~java
import static example.validation.ValidationGroups.Create;
import static example.validation.ValidationGroups.Update;
~~~

This is an **import fragment** used in another source file. You can name groups after business actions such as `Submit`, `ConfirmPayment`, `CloseBooking`, or `Archive`. However, standardize naming conventions and avoid creating dozens of nearly overlapping groups.

## 4. Declaring Constraints by Group on a DTO

Example defining a Java 17 DTO using a record:

~~~java
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Null;

public record DocumentCommand(
        @Null(groups = Create.class)
        @NotNull(groups = {Update.class, Publish.class})
        Long id,

        @NotBlank(groups = {Create.class, Update.class, Publish.class})
        String title,

        @NotBlank
        @Email
        String ownerEmail,

        @NotNull(groups = Publish.class)
        @AssertTrue(groups = Publish.class)
        Boolean reviewed,

        @NotBlank(groups = Approve.class)
        String approver) {
}
~~~

This snippet is a **model fragment**, assuming the marker interfaces `Create`, `Update`, `Publish`, and `Approve` are imported.

Meaning:

- `id`: on `Create`, `@Null` requires no ID yet; on `Update`/`Publish`, `@NotNull` requires an ID to be present.
- `title`: must be non-blank in `Create`, `Update`, and `Publish`. Omitted from `Approve` assuming a standalone approval task does not modify content.
- `ownerEmail`: `@NotBlank` and `@Email` **omit `groups`** and therefore belong to the standard `jakarta.validation.groups.Default` group.
- `reviewed`: must be non-null and `true` on `Publish`. `@AssertTrue` by itself allows `null`, so `@NotNull` is required if the field is mandatory in this step.
- `approver`: only required to be non-blank on `Approve`.

To apply one rule to multiple groups:

~~~java
@NotBlank(groups = {Create.class, Update.class, Publish.class})
String title
~~~

There is no need to duplicate three properties or write three identical custom validators.

**What to avoid:** `groups` controls **which constraints are evaluated**; it does not mutate DTO data, generate `id`, hide fields from JSON, or prevent users from sending fields they are not authorized to edit.

## 5. `Default` Is a Particularly Important Group

A constraint **without `groups` declared** is assigned to `Default`:

~~~java
@NotBlank              // belongs to Default
private String email;

@NotBlank(groups = Create.class)
private String title;  // belongs to Create, does not automatically belong to Default
~~~

If `Create` is an independent interface, the following calls differ:

~~~java
validator.validate(command);
validator.validate(command, Create.class);
validator.validate(command, Update.class);
validator.validate(command, Default.class, Create.class);
~~~

- `validate(command)`: evaluates `Default`.
- `validate(command, Create.class)`: evaluates `Create`, **without automatically including `Default`**.
- `validate(command, Update.class)`: evaluates `Update`.
- `validate(command, Default.class, Create.class)`: evaluates both groups.

In Spring, the corresponding rules are:

~~~java
@Validated(Create.class)
@Validated({Default.class, Create.class})
~~~

These are **two independent alternatives**; do not place both annotations repeatedly on the same parameter.

| When choosing | Risk if `Default` is forgotten |
| --- | --- |
| `@Validated(Create.class)` | May skip `@Email` / `@NotBlank` declared without `groups` |
| `@Validated(Update.class)` | May skip constraints shared across all operations |
| `@Validated({Default.class, Create.class})` | Validates both common rules and `Create` |
| `@Validated({Default.class, Update.class})` | Validates both common rules and `Update` |

**There is nothing wrong** with intentionally choosing a single group. The mistake is when developers assume `Default` always runs automatically and accidentally skip mandatory constraints. If a group is designed to extend `Default` or uses a group sequence, behavior can differ; know your project's own design.

## 6. Choosing Groups for Each Specialized Task

### 6.1. Creation (`Create`)

What typically needs checking:

- Server-generated ID must be absent: `@Null(groups=Create.class)`.
- Fields required on creation: `@NotBlank(groups=Create.class)` / `@NotNull(groups=Create.class)`.
- Common constraints such as email or code format: run `Default` if they belong to that group.

Example:

~~~java
@Validated({Default.class, Create.class})
@RequestBody DocumentCommand request
~~~

The fragment above is a **controller parameter**, not a complete method. In real APIs, `id` can be omitted entirely from a Create DTO to prevent clients from sending an arbitrary ID; using `@Null` on a shared model is not always necessary.

### 6.2. Updating (`Update`)

What typically needs checking:

- Required ID: `@NotNull(groups=Update.class)`.
- Name or fields meaningful on update: `@NotBlank(groups=Update.class)`.
- May require a version/`ETag` token when optimistic locking is needed; validation groups do not resolve concurrent update conflicts on their own.

~~~java
@Validated({Default.class, Update.class})
@RequestBody DocumentCommand request
~~~

If the Update API uses **PUT** with full payloads, `@NotBlank` can make sense. If the Update API uses **PATCH**, omitted fields can mean "keep unchanged"; using the same `@NotBlank` on every field is usually inappropriate. PATCH is analyzed in section 14.

### 6.3. Publishing (`Publish`)

Publish may require:

- The entity already exists (non-null ID).
- The content has a title.
- `reviewed == true`.
- The owner email is valid per the common group.

~~~java
@Validated({Default.class, Publish.class})
@RequestBody DocumentCommand request
~~~

`@AssertTrue` checks a `Boolean` value at validation time. It does not verify that a review was actually completed by an authorized person; that requires domain logic, audit logs, and authorization in the service layer.

### 6.4. Approval (`Approve`)

The `Approve` task may use a dedicated DTO:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record ApprovalCommand(
        @NotNull Long documentId,
        @NotBlank String approver,
        @NotBlank String comment) {}
~~~

This is an **illustrative DTO model**. Because the shape of approval differs completely from Create/Update, **splitting the DTO** here is usually simpler than adding an `Approve` group across every field of a large DTO. The `Approve` group truly pays off when only a few constraints differ and DTO reuse is desired.

### 6.5. Other Specialized Tasks

| Task | Suggested group name | Example group-scoped constraint |
| --- | --- | --- |
| Complete submission | `Submit` | `@NotBlank(groups=Submit.class)` on document number |
| Dispatch shipment | `Dispatch` | `@NotNull(groups=Dispatch.class)` on address |
| Payment checkout | `Checkout` | `@NotNull(groups=Checkout.class)` on payment method |
| Close accounting period | `ClosePeriod` | `@NotNull(groups=ClosePeriod.class)` on closing date |
| Publish content | `Publish` | `@AssertTrue(groups=Publish.class)` on reviewed flag |
| Resolve ticket | `Resolve` | `@NotBlank(groups=Resolve.class)` on resolution note |

**Warning:** Even if a request passes the `Checkout` group's constraints, that **does not mean** the transaction has been paid or the caller is permitted to pay. Groups categorize **validation**; they neither perform actions nor grant permissions.

## 7. Group and Violation Count Prediction Table

With `DocumentCommand` from section 4, suppose:

~~~text
id         = 7
title      = ""
ownerEmail = "not-mail"
reviewed   = false
approver   = ""
~~~

| Group executed | Violating properties | Total errors |
| --- | --- | ---: |
| `Default` | `ownerEmail` due to `@Email` | 1 |
| `Create` | `id` due to `@Null`, `title` due to `@NotBlank` | 2 |
| `Update` | `title` due to `@NotBlank` | 1 |
| `Publish` | `title` due to `@NotBlank`, `reviewed` due to `@AssertTrue` | 2 |
| `Approve` | `approver` due to `@NotBlank` | 1 |
| `Default + Create` | `ownerEmail`, `id`, `title` | 3 |
| `Default + Publish` | `ownerEmail`, `title`, `reviewed` | 3 |

In `Publish`, `reviewed=false` **passes `@NotNull`** but **fails `@AssertTrue`**. If `reviewed=null`, by constraint semantics `@AssertTrue` considers `null` valid and `@NotNull` fails: still one violation on `reviewed` under two different scenarios.

The order of a `Set<ConstraintViolation<?>>` is not guaranteed. The table lists items by meaning, not by provider callback order.

## 8. Runnable Java 17+ Program: Verifying the Groups

A plain Jakarta Validation example lets you verify groups without starting an HTTP server. Once you understand the output, you can apply the same group selection using `@Validated` in Spring.

### 8.1. Maven Project Structure

~~~text
validation-groups-demo/
├── pom.xml
└── src/main/java/example/groupdemo/ValidationGroupsDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>validation-groups-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.1.Final</version>
        </dependency>
        <dependency>
            <groupId>org.glassfish</groupId>
            <artifactId>jakarta.el</artifactId>
            <version>4.0.2</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Hibernate Validator 8 is a provider compatible with Jakarta Validation 3.0. The Jakarta EL dependency supports default message interpolation. The versions above are for a reproducible example; real Spring Boot projects should let the BOM/parent manage compatible versions.

### 8.2. Complete Java Code

Save `src/main/java/example/groupdemo/ValidationGroupsDemo.java`:

~~~java
package example.groupdemo;

import java.util.stream.Collectors;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.groups.Default;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Null;

public final class ValidationGroupsDemo {

    public interface Create {}
    public interface Update {}
    public interface Publish {}
    public interface Approve {}

    public record Document(
            @Null(groups = Create.class)
            @NotNull(groups = {Update.class, Publish.class})
            Long id,

            @NotBlank(groups = {
                    Create.class, Update.class, Publish.class
            })
            String title,

            @NotBlank
            @Email
            String ownerEmail,

            @NotNull(groups = Publish.class)
            @AssertTrue(groups = Publish.class)
            Boolean reviewed,

            @NotBlank(groups = Approve.class)
            String approver) {}

    private static String invalidFields(
            Validator validator, Document document, Class<?>... groups) {
        return validator.validate(document, groups).stream()
                .map(v -> v.getPropertyPath().toString())
                .distinct()
                .sorted()
                .collect(Collectors.joining(","));
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            Document invalid =
                    new Document(7L, "", "not-mail", false, "");

            System.out.println("default="
                    + invalidFields(validator, invalid));
            System.out.println("create="
                    + invalidFields(validator, invalid, Create.class));
            System.out.println("update="
                    + invalidFields(validator, invalid, Update.class));
            System.out.println("publish="
                    + invalidFields(validator, invalid, Publish.class));
            System.out.println("approve="
                    + invalidFields(validator, invalid, Approve.class));
            System.out.println("default+create="
                    + invalidFields(validator, invalid,
                                    Default.class, Create.class));
            System.out.println("default+publish="
                    + invalidFields(validator, invalid,
                                    Default.class, Publish.class));

            Document validCreate =
                    new Document(null, "Guide", "a@example.com",
                                 null, null);
            Document validPublish =
                    new Document(8L, "Guide", "a@example.com",
                                 true, "reviewer");

            System.out.println("valid-create-count="
                    + validator.validate(
                            validCreate, Default.class,
                            Create.class).size());
            System.out.println("valid-publish-approve-count="
                    + validator.validate(
                            validPublish, Default.class,
                            Publish.class, Approve.class).size());
        }
    }
}
~~~

Run in the project directory:

~~~bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=example.groupdemo.ValidationGroupsDemo
~~~

**Stdout printed by the program**, excluding Maven/provider logs:

~~~text
default=ownerEmail
create=id,title
update=title
publish=reviewed,title
approve=approver
default+create=id,ownerEmail,title
default+publish=ownerEmail,reviewed,title
valid-create-count=0
valid-publish-approve-count=0
~~~

Detailed explanation:

- `Default`: `ownerEmail="not-mail"` passes `@NotBlank` but fails `@Email`.
- `Create`: `id` must be null and `title` must be non-blank; Publish/Approve constraints do not run.
- `Update`: `id=7L` passes `@NotNull`; `title=""` fails.
- `Publish`: `id=7L` passes; `title=""` and `reviewed=false` fail.
- `Approve`: `approver=""` fails.
- `Default+Create`: properly combines shared and group-specific constraint sets.
- `validCreate`: null ID is valid in `Create`; `reviewed` and `approver` are not required on creation.
- `validPublish`: all conditions across the three requested groups pass.

The `invalidFields` helper uses `distinct()` and `sorted()` to produce deterministic output independent of `Set<ConstraintViolation<Document>>` order. In a real application, do not compare only field names: if the same property violates multiple constraints, keep individual error codes and messages; here `distinct()` is only for demonstrating the set of fields.

**Compiling with plain `javac`:** The Java source is complete, but uses Jakarta Validation/Hibernate Validator; running `javac ValidationGroupsDemo.java` in a directory without a classpath will fail due to missing libraries. Maven loads dependencies automatically; if using `javac`/`java -cp`, you must provide **all relevant JARs**. Do not mistake a missing classpath error for a group issue.

## 9. Spring MVC: Selecting Groups for Create, Update, and Publish

In Spring Boot 3.x / Spring Framework 6.x, projects typically use:

~~~xml
<!-- Two dependencies in a pom.xml that already has a Spring Boot parent/BOM -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

This is a **dependency fragment**, not a standalone `pom.xml`. The validation starter typically provides Hibernate Validator and the necessary integration; do not assume having only the web starter will run validation annotations.

### 9.1. Java 17+ Spring Boot Application

In a Spring Boot project configured with the starters above, create `src/main/java/example/groupweb/GroupWebApplication.java`:

~~~java
package example.groupweb;

import java.util.Map;

import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Null;
import jakarta.validation.groups.Default;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class GroupWebApplication {

    public static void main(String[] args) {
        SpringApplication.run(GroupWebApplication.class, args);
    }

    public interface Create {}
    public interface Update {}
    public interface Publish {}

    public record ArticleRequest(
            @Null(groups = Create.class)
            @NotNull(groups = {Update.class, Publish.class})
            Long id,

            @NotBlank(groups = {
                    Create.class, Update.class, Publish.class
            })
            String title,

            @NotBlank
            @Email
            String contactEmail,

            @NotNull(groups = Publish.class)
            @AssertTrue(groups = Publish.class)
            Boolean reviewed) {}

    @RestController
    @RequestMapping("/documents")
    public static class DocumentController {

        @PostMapping
        public Map<String, String> create(
                @Validated({Default.class, Create.class})
                @RequestBody ArticleRequest request) {
            return Map.of("operation", "create",
                          "title", request.title());
        }

        @PutMapping
        public Map<String, String> update(
                @Validated({Default.class, Update.class})
                @RequestBody ArticleRequest request) {
            return Map.of("operation", "update",
                          "id", request.id().toString());
        }

        @PostMapping("/publish")
        public Map<String, String> publish(
                @Validated({Default.class, Publish.class})
                @RequestBody ArticleRequest request) {
            return Map.of("operation", "publish",
                          "id", request.id().toString());
        }
    }
}
~~~

This is a **complete application file** when placed in a Spring Boot project with matching dependencies/versions and build wrapper. You do not need to add `@Valid` alongside `@Validated` on the same parameter to select groups: Spring MVC recognizes `@Validated` and passes the groups to the validator.

Run using your project's build tool:

~~~bash
./mvnw spring-boot:run
~~~

or:

~~~bash
./gradlew bootRun
~~~

These wrapper commands exist only if the project actually contains `mvnw` or `gradlew` respectively.

### 9.2. Trying the Endpoints

Assuming the application runs on port `8080`:

~~~bash
curl -i -X POST http://localhost:8080/documents \
  -H "Content-Type: application/json" \
  -d '{"id":null,"title":"First draft","contactEmail":"a@example.com","reviewed":null}'

curl -i -X PUT http://localhost:8080/documents \
  -H "Content-Type: application/json" \
  -d '{"id":12,"title":"Revised draft","contactEmail":"a@example.com","reviewed":false}'

curl -i -X POST http://localhost:8080/documents/publish \
  -H "Content-Type: application/json" \
  -d '{"id":12,"title":"Ready article","contactEmail":"a@example.com","reviewed":true}'
~~~

With standard Spring MVC configuration and no special security/filters, the valid requests above return **HTTP 200**, containing `operation=create`, `operation=update`, and `operation=publish` respectively in the JSON response. JSON key ordering is not guaranteed.

Try the invalid requests:

~~~bash
# Create where client supplies an ID -> @Null(Create) fails
curl -i -X POST http://localhost:8080/documents \
  -H "Content-Type: application/json" \
  -d '{"id":99,"title":"Draft","contactEmail":"a@example.com","reviewed":null}'

# Update missing ID -> @NotNull(Update) fails
curl -i -X PUT http://localhost:8080/documents \
  -H "Content-Type: application/json" \
  -d '{"id":null,"title":"Draft","contactEmail":"a@example.com","reviewed":false}'

# Publish not yet reviewed -> @AssertTrue(Publish) fails
curl -i -X POST http://localhost:8080/documents/publish \
  -H "Content-Type: application/json" \
  -d '{"id":12,"title":"Draft","contactEmail":"a@example.com","reviewed":false}'

# Invalid email even when Create fields are valid -> @Email(Default) fails
curl -i -X POST http://localhost:8080/documents \
  -H "Content-Type: application/json" \
  -d '{"id":null,"title":"Draft","contactEmail":"invalid","reviewed":null}'
~~~

In the standard `@RequestBody` validation path, failed constraints typically result in **HTTP 400**, such as `MethodArgumentNotValidException`. Error JSON structure depends on `@ControllerAdvice`, Problem Details, and Spring Boot settings; do not assume a fixed payload.

**Distinction to keep in mind:** Jackson deserializes JSON first, and Jakarta Validation runs afterwards. `"id":"not-a-long"` can fail **data type conversion** before group constraints are evaluated. By contrast, `id=null` converts to `Long` and can be rejected by `Update`'s `@NotNull`.

### 9.3. `@ModelAttribute` and `BindingResult`

For form data, select groups similarly:

~~~java
@PostMapping("/draft-form")
public String submitForm(
        @Validated({Default.class, Create.class})
        @ModelAttribute DraftForm form,
        BindingResult bindingResult) {
    if (bindingResult.hasErrors()) {
        return "invalid-form";
    }
    return "accepted";
}
~~~

This is a **method fragment**; `DraftForm` and imports must be declared in a real controller. `BindingResult` must be placed **immediately after** the model parameter being handled so it receives binding and validation errors for that model.

In Spring MVC 6.1+, if a handler also has constraints directly on method parameters (such as `@Min` on `@RequestParam`), built-in method validation can change the execution path and raise `HandlerMethodValidationException`. Do not design error handlers assuming every case throws `MethodArgumentNotValidException`.

## 10. Distinguishing Two Uses of `@Validated` in Spring

`org.springframework.validation.annotation.Validated` has related usages that are **not identical**:

| Placement of `@Validated` | Primary purpose | Prerequisite |
| --- | --- | --- |
| On a Spring MVC DTO parameter, e.g., `@Validated(Create.class) @RequestBody` | Selects groups to validate the **request object** | Spring MVC + Bean Validation provider |
| On a Spring service class `@Validated` | Marks bean for **AOP method validation** | `MethodValidationPostProcessor`/proxy, provider, method constraints |
| On a service method in a bean with method validation enabled | Can specify method-level validation hints/groups | Verify Spring wiring, proxy, and group selection |
| On a Spring MVC 6.1+ controller class | Can route handlers into AOP method validation | Not recommended when you want built-in MVC method validation |

### 10.1. Method Validation on a Service

Implementation fragment:

~~~java
import jakarta.validation.constraints.NotNull;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class DocumentService {

    public interface Publish {}

    public void publish(
            @NotNull(groups = Publish.class) Long documentId) {
        // Call repository, check authorization, perform publish...
    }
}
~~~

**Example warning:** Class-level `@Validated` above **does not select the `Publish` group**; it uses the default group when no other group/hint is declared on the method. Therefore `@NotNull(groups=Publish.class)` alone **will not run** under `Default`! To enforce `Publish` validation on this method, design it explicitly:

~~~java
@Service
@Validated(DocumentService.Publish.class)
public class DocumentService {
    public interface Publish {}

    public void publish(
            @NotNull(groups = Publish.class) Long documentId) {
        // ...
    }
}
~~~

This is an **alternative approach**, not two class declarations placed in the same source file. When Spring method validation infrastructure is active, calls through the Spring proxy to `publish(null)` can be rejected.

Important notes:
- A Bean Validation provider and `MethodValidationPostProcessor` or appropriate auto-configuration must be present.
- The **proxy** must intercept the call. Calling `this.publish(null)` from within the same bean typically bypasses the proxy due to self-invocation.
- `new DocumentService()` has no Spring proxy.
- By default, AOP method validation typically throws `ConstraintViolationException`. Depending on Spring configuration, it may translate to `MethodValidationException` when violation adaptation is enabled.
- Constraints do not replace checking whether the caller has permission to publish, whether the record exists, or whether the state transition is valid.

### 10.2. Newer Spring MVC Validation Path

Since Spring Framework 6.1, Spring MVC includes built-in method validation for handlers with constraints directly on parameters or return values. If a controller also carries class-level `@Validated`, it can trigger the AOP method validation path instead of the built-in MVC mechanism. Spring's guidance when you want built-in method validation is to **remove class-level `@Validated` from controllers**, and then use appropriate parameter annotations.

Therefore, when learning groups, prefer `@Validated(Group.class)` **directly on the endpoint's DTO parameter** when the simple goal is selecting groups for the request object.

## 11. `Default` Group, Group Inheritance, and Group Structure

There are two main ways to combine common and specific rules.

### Approach A: Explicitly Request Both Groups at the Endpoint

~~~java
@Validated({Default.class, Create.class})
~~~

Pros:
- Easy to see which endpoint runs which rules.
- Does not pull in unwanted constraints elsewhere.
- Easy to use for a few endpoints with clear policies.

Cons:
- Every trigger point must choose correctly; `Default.class` can be forgotten when copying code.

### Approach B: Group Interface Extending the Common Group

~~~java
import jakarta.validation.groups.Default;

public interface Create extends Default {}
public interface Update extends Default {}
~~~

In this design, requesting `Create.class` also includes constraints belonging to the inherited `Default` group via Jakarta Validation **group inheritance**. Thus `@Validated(Create.class)` also checks `Default` constraints. For a fair comparison with Approach A, note that these are **two alternative designs**; once you define `Create extends Default`, the table in section 5 (which assumed independent groups) no longer applies verbatim.

Pros:
- Reduces the risk of forgetting the common group.
- Fits well when **every** Create/Update check must include `Default`.

Cons:
- Can pull in common constraints even in flows where you only want partial data validated.
- Requires understanding inheritance when combined with group sequences and cascades.
- When group hierarchies get complex, readers must trace interface relationships to know exactly which constraints run.

**Design recommendation:** Pick **one** convention for a module and document it in technical docs. Do not mix both styles implicitly so endpoint maintainers cannot predict which rules execute.

## 12. `@GroupSequence`: When Group Ordering Is Needed

If validation needs two phases:

1. Check basic rules such as required fields and syntax.
2. Only when phase 1 succeeds, check expensive or specialized rules.

Use a **group sequence**:

~~~java
import jakarta.validation.GroupSequence;
import jakarta.validation.groups.Default;

public interface Publish {}

@GroupSequence({Default.class, Publish.class})
public interface PublishChecks {}
~~~

In a complete program, place these interfaces in appropriate files and packages; this is a **design fragment**.

Usage:

~~~java
validator.validate(bean, PublishChecks.class);
~~~

or:

~~~java
@Validated(PublishChecks.class)
~~~

When evaluating the `PublishChecks` sequence, the provider evaluates `Default` first. If there are violations in this step, `Publish` constraints **are not evaluated**. Only if step 1 passes does validation proceed to `Publish`. Thus a request with an invalid email may only receive the email error, even if `reviewed=false` also fails `Publish`.

**Unlike**:

~~~java
@Validated({Default.class, Publish.class})
~~~

The multi-group syntax above **does not guarantee ordering** and does not stop later groups when an earlier group fails; only a group sequence provides ordering and short-circuiting across declared groups.

Notes:
- Do not define a cyclic group sequence.
- If **redefining a class's `Default` group via `@GroupSequence` on that class itself**, specification rules differ from the sequence interface example; the sequence must include the bean class itself per spec rules.
- Group sequences are useful for performance and phased error reporting, not as a replacement for an entire business state machine.

## 13. Cascading and Group Conversion for Child Objects

A Create request might include an address, while Publish needs to validate the address under stricter rules.

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.groups.ConvertGroup;

interface Publish {}
interface VerifyAddress {}

class DeliveryAddress {
    @NotBlank(groups = VerifyAddress.class)
    private String city;
}

class DocumentWithDelivery {
    @NotNull(groups = Publish.class)
    @Valid
    @ConvertGroup(from = Publish.class, to = VerifyAddress.class)
    private DeliveryAddress address;
}
~~~

This is an **illustrative model**, not a standalone runnable application.

When validating `DocumentWithDelivery` with the `Publish` group:
- `address == null`: violates `@NotNull(Publish)`; `@Valid` skips cascading into `null`.
- `address != null`: `@NotNull` passes and `@Valid` cascades.
- `@ConvertGroup` instructs that the `Publish` group at this association be converted to `VerifyAddress` to validate the child bean's `city`.

If you omit `@ConvertGroup`, cascading passes the active group down to the child object by default; `city`'s constraint, belonging only to `VerifyAddress`, would not run when the input group is `Publish`. If you omit `@Valid`, group conversion has no valid cascade point.

With lists or maps, you can use container element constraints:

~~~java
import java.util.List;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;

private List<@NotNull(groups = Publish.class) @Valid DeliveryAddress> stops;
~~~

Notes:
- `@NotNull` on the **element** forbids null elements, **not a null list itself**.
- `@Valid` on the element cascades into the child bean when the element is non-null.
- To forbid a null or empty list, add a constraint on the **container**, e.g., `@NotEmpty(groups=Publish.class)`.
- Selecting groups also controls whether `@NotNull` runs: validating only `Create` will not automatically check a constraint marked `Publish`.

## 14. For PATCH, Do Not Use Groups Mechanically

The `Update` group usually fits **PUT** or a full update form. For **PATCH** modifying individual fields, two requests have different meanings:

~~~json
{"title":"New title"}
~~~

and:

~~~json
{"title":null}
~~~

The first request may mean: update `title`, **keep `email` unchanged**. The second request may mean: **clear `title`** or send an invalid value. If both deserialize into the same DTO with nullable fields, in many cases you cannot tell "omitted" apart from "explicit `null`".

Applying `@NotBlank(groups=Update.class)` to every field of a PATCH DTO can reject a single-field patch because the remaining fields are `null`. You can design:

- A `CreateRequest` with full required fields.
- A `ReplaceRequest` for PUT, with full constraints.
- A `PatchRequest` tracking **presence** of fields, e.g., via a patch command, `JsonNode`, or a mechanism that distinguishes absent from explicit `null`.
- Validate only **present values**, apply changes to the existing entity, and then validate the entire business state.

Groups do not detect which properties appeared in JSON. Do not create a `Patch` group and assume it solves the difference between missing and `null`.

## 15. Choosing Groups vs. Splitting DTOs?

| Criterion | DTO with Create/Update groups | Separate DTOs per operation |
| --- | --- | --- |
| Data shape is very similar | Usually suitable | May duplicate code |
| Only a few constraints differ | Concise and clear | May add boilerplate |
| Request structures differ greatly | Quickly becomes confusing | Usually clearer |
| Sparse PATCH payloads | Does not solve absent vs. `null` by itself | Often fits well with a presence model |
| Controlling writable fields | Needs a mechanism beyond groups | Separate DTOs restrict fields better |
| Multi-step Publish/Approve/Dispatch | Useful when every step shares nearly the same model | Better if each command has a distinct shape |
| Reusing groups for service validation | Can be convenient | Depends on service contract |

A hybrid architecture often works well:

~~~text
HTTP API
  |
  +-- CreateDocumentRequest -> Default/Create groups (or Default)
  |
  +-- UpdateDocumentRequest -> Default/Update groups (or Default)
  |
  +-- PublishDocumentCommand -> Publish group
  |
  +-- ApproveDocumentCommand -> Approve group
  |
  v
Service: check permissions, state, idempotency, transaction
  |
  v
Database: unique, foreign key, concurrent consistency
~~~

**Splitting DTOs does not mean abandoning groups**, and using groups is no excuse to create a "God DTO" holding every field in the system.

## 16. Validation Groups Are Not a State Machine or Authorization

Suppose the client sends:

~~~json
{"id":12,"title":"Ready","contactEmail":"a@example.com","reviewed":true}
~~~

If the request passes `@Validated({Default.class, Publish.class})`, that only proves:
- Constraints belonging to the selected groups passed.
- Other rules—undeclared or belonging to other groups—may not have been checked.

It **does not prove**:
- The client is a valid reviewer.
- Document ID 12 actually exists.
- The document is in a state eligible for publishing.
- No required approvals are missing.
- The transaction committed or the DB has no race condition.
- Input data remains valid after server state changes.

Distinguish the layers:

| Layer | Responsibility |
| --- | --- |
| JSON parse/data binding | Produce appropriate Java types from input |
| Jakarta Validation | Evaluate declared constraints and requested groups |
| Spring Security/authorization | Is the user allowed to perform the operation? |
| Service/domain policy | Does the entity exist, is the state transition valid, is data consistent? |
| Transaction/database | Uniqueness, locks, foreign keys, transactions, and concurrency conflicts |

Do not attach `groups = Admin.class` and treat passing validation as proof that the user has admin privileges; any caller can send data satisfying that constraint. Authorization must be evaluated from identity and access policies.

## 17. Common Mistakes When Selecting Groups

1. **Forgetting `Default`:** `@Validated(Update.class)` causes `@Email` belonging only to `Default` not to run, if `Update` does not extend `Default`.
2. **Putting `@NotNull` without `groups` on ID:** Create requires a null ID, so it fails `Default`. Move the constraint to `Update` or use separate DTOs.
3. **Just calling a constructor and expecting annotations to run:** You need `Validator.validate` or framework-triggered validation.
4. **Switching from `@Valid` to `@Validated` and forgetting cascades:** Spring's `@Validated` selects groups; child beans still need `@Valid` on the association and possibly `@ConvertGroup`.
5. **Assuming `@Validated({A.class, B.class})` checks A before B:** If ordering is needed, use `@GroupSequence`.
6. **Using groups while still letting clients update disallowed fields:** Groups are not mass-assignment protection.
7. **Assuming `@NotBlank(groups=Publish.class)` on a property runs on every endpoint:** It only runs when `Publish` or a related group is requested.
8. **Missing Bean Validation provider:** Annotations may not take effect as expected in Spring.
9. **Mixing `javax.validation` and `jakarta.validation`:** Spring 6/Boot 3 uses the Jakarta namespace; compatible dependencies are required.
10. **Assuming all HTTP errors are `MethodArgumentNotValidException`:** Method constraints in MVC 6.1+ can follow built-in method validation and throw `HandlerMethodValidationException`.
11. **Thinking AOP method validation runs on `this.method()`:** Self-invocation normally bypasses the proxy.
12. **Creating too many overlapping specialized groups:** Hurts readability and makes it easy to miss constraints when adding new endpoints.
13. **Using `Update` for PATCH without distinguishing absent fields:** Easily rejects valid requests or allows clearing critical fields.
14. **Comparing `Set<ConstraintViolation>` order:** Not guaranteed; sort in tests.
15. **Validating format constraints while forgetting business checks:** Valid email syntax does not mean the email exists; client-supplied `reviewed=true` does not confirm a review happened.
16. **Placing `@AssertTrue` thinking it forbids `null`:** If the `Boolean` is required, combine with `@NotNull`.
17. **Thinking `@Valid` requires a child object to be non-null:** Cascade skips null references; use `@NotNull` with the appropriate group if required.

## 18. Minimum Test Suite for Create, Update, and Specialized Tasks

In a real application, test both **Jakarta `Validator`** and the **Spring MVC boundary**.

| Case | Group(s) | Expected outcome |
| --- | --- | --- |
| Create with `id=null`, valid title/email | `Default+Create` | Pass |
| Create with `id != null` | `Default+Create` | ID error |
| Create with invalid email | `Default+Create` | `Default` email error |
| Create selecting only `Create`, invalid email | `Create` alone | Email **is not checked** (demonstrates why `Default` is needed) |
| Update missing ID | `Default+Update` | ID error |
| Update with blank title | `Default+Update` | Title error |
| Publish with `reviewed=false` | `Default+Publish` | `reviewed` error |
| Publish with `reviewed=null` | `Default+Publish` | `reviewed` error via `NotNull` |
| Publish with `reviewed=true` and valid ID | `Default+Publish` | Pass if other fields are valid |
| Approve missing approver | `Approve` | Approver error |
| DTO with nested bean needing a separate group | `Publish` with `ConvertGroup` | Group properly propagated/converted to child |
| JSON with wrong type for `id` | Any | Deserialization/binding error **before** validation |
| Calling service through proxy | Method validation group | Constraint executes if fully configured |
| Self-invocation within same bean | Method validation group | May **bypass** AOP interceptor |
| Group sequence `Default` then `Publish` | `PublishChecks` | `Publish` does not run if `Default` fails |

**Assertion design:** Compare property paths, error codes/violation counts, or appropriate exception types. Avoid relying on error order, default locale, or JSON key ordering not guaranteed by the API.

### 18.1. Testing MVC with MockMvc

In Spring Boot, an integration test typically checks:
- Valid POST Create and assert HTTP 200 or 201 **per your controller definition**.
- POST Create with non-null ID and assert HTTP 400.
- PUT Update missing ID and assert HTTP 400.
- POST Publish not reviewed and assert HTTP 400.
- POST Create with invalid email to verify `Default` is not skipped.
- Send requests with missing body or mismatched JSON types to verify binding errors.
- If `@ControllerAdvice` is present, assert the application's error schema (avoid asserting locale-specific messages unnecessarily).

Do not treat HTTP 400 alone as enough to prove the right **group** ran: include at least one test proving one rule **was selected** and another rule **was not selected** in the same scenario.

## 19. Review Questions

**Q1.** A DTO has `@NotNull(groups=Update.class) Long id`. During `Create`, does `id=null` cause an error?

**A:** No, if only `Create`/`Default` are validated and no other constraint forbids `null`; `Update`'s `@NotNull` is not selected.

**Q2.** `@Email String email` has no `groups`. The endpoint uses only `@Validated(Create.class)`, where `Create` is an independent marker interface. Does `email="invalid"` fail?

**A:** No, not from `Default`'s `@Email` in a pass that only checks `Create`. Use `@Validated({Default.class, Create.class})` or make `Create` extend `Default`.

**Q3.** What should you declare to require `id == null` on Create and `id != null` on Update?

**A:**

~~~java
@Null(groups = Create.class)
@NotNull(groups = Update.class)
Long id;
~~~

**Q4.** To run `Publish` only after `Default` has no errors, is `@Validated({Default.class, Publish.class})` enough?

**A:** No; multiple groups in a list do not enforce an execution order. Use `@GroupSequence({Default.class, Publish.class})` on a sequence interface and select that sequence.

**Q5.** An order has a child `address`. The parent is validated with `Publish`, while constraints inside the child belong only to `StrictAddress`. What is needed?

**A:** Place `@Valid` on the association and `@ConvertGroup(from=Publish.class, to=StrictAddress.class)` if group conversion on cascade is needed; if the child is required, add `@NotNull(groups=Publish.class)`.

**Q6.** A Create controller shares a DTO containing fields used only for approval. Must you add an `Approval` group?

**A:** No. If approval has a different data structure, splitting into a dedicated DTO/command can be clearer. Groups fit best when multiple contexts share nearly the same model.

**Q7.** When a controller has `@Validated` at the class level in a Spring MVC 6.1+ project, can it affect built-in method validation?

**A:** Yes. Spring recommends removing class-level `@Validated` on controllers if you want built-in MVC method validation, while selecting groups on DTO parameters as needed.

**Q8.** When PATCH sends only one field and the DTO does not distinguish absent from `null`, does the `Update` group guarantee safe updates?

**A:** No. You need a PATCH model representing field presence, appropriate constraints, and state merging/validation in the service.

**Q9.** If a request passes `@Validated(Approve.class)`, can you skip authorization in the service?

**A:** No. Validation groups check data content, not identity or approval permissions.

**Q10.** In the Java example in section 8, why is `validCreate` with `reviewed=null` and `approver=null` still valid?

**A:** Because in the `Default+Create` pass, `@NotNull`/`@AssertTrue` on `reviewed` belong to `Publish` and `@NotBlank` on `approver` belongs to `Approve`; they were not selected.

## 20. Pre-Production Checklist

- [ ] Each constraint has groups matching its business purpose.
- [ ] The `Default` group is handled consistently: explicit selection or inheritance.
- [ ] Each Create, Update, and Publish/Approve endpoint selects the right groups.
- [ ] Request DTOs do not expose writable fields that callers are not authorized to modify.
- [ ] Nested data has `@Valid` and group conversion where actually needed.
- [ ] Specialized groups are not confused with permissions or state transitions.
- [ ] A Jakarta Validation provider and proper Spring integration are present.
- [ ] You understand whether AOP proxy or built-in MVC method validation is being used.
- [ ] Error handlers cover binding errors, argument validation, and method validation.
- [ ] Tests cover valid, invalid, combined groups, and `Default` rules.
- [ ] PATCH handles missing vs. explicit `null` clearly; service and DB enforce consistency.

## 21. Summary

- **Groups are labels on constraints**, defined by Jakarta Validation. Spring `@Validated` is a way to select groups when the framework triggers validation.
- **Create** usually forbids client-supplied IDs, **Update** usually requires IDs, and tasks like **Publish/Approve** have their own rules.
- When `Create` and `Update` are independent groups, selecting them **does not automatically check `Default`**. This is the most common design mistake.
- Use `@Validated({Default.class, Create.class})` or inheritance per a consistent convention; use `@GroupSequence` when evaluation order is genuinely needed.
- Use `@Valid` for cascading and `@ConvertGroup` when changing groups on child objects is needed.
- Choose **separate DTOs** when Create/Update/Patch/Publish shapes differ significantly.
- Groups do not replace business validation, authorization, or transaction control.
- Before finishing, always test via `Validator` and via Spring MVC/service at the actual trigger points.

### References

- Jakarta Validation 3.1 Specification – Group definitions, group inheritance, group sequences, and group conversion: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html
- Jakarta Validation – `Default` group: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/groups/default
- Jakarta Validation – `@GroupSequence`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/groupsequence
- Jakarta Validation – `@ConvertGroup`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/groups/convertgroup
- Hibernate Validator 8 Reference Guide – Grouping constraints: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Spring Framework – `@Validated` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/annotation/Validated.html
- Spring Framework – Java Bean Validation and method validation: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring MVC – Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
