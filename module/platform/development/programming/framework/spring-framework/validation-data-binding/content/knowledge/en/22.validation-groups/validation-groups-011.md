# Criteria for Choosing Multiple DTOs Instead of One Model with Too Many Groups

> **Context:** Jakarta Bean Validation and Spring Framework, **Validation Groups** section. This article helps decide when to use a single DTO with `Create`/`Update` groups versus splitting into `CreateRequest`, `UpdateRequest`, `PatchRequest`, and `Response`. It includes a decision matrix, runnable Java 17+ examples with Maven/Hibernate Validator, Spring MVC code, a migration strategy, testing, and common mistakes.

## 1. Asking the Right Question Before Choosing a Design

Suppose an account management application has these operations:

- `POST /accounts`: client sends a name and an initial code; server generates `id`.
- `PUT /accounts/{id}`: client can edit the name, but must not change the initial code or admin role through this API.
- `PATCH /accounts/{id}`: client can send only the specific fields to update.
- `GET /accounts/{id}`: returns `id`, name, and public status, without returning secrets.

There are two approaches:

1. **One DTO + validation groups:** put all fields into `AccountInput`, using `@NotBlank(groups = Create.class)` and `@NotNull(groups = Update.class)`; controllers select groups via `@Validated(Create.class)` or `@Validated(Update.class)`.
2. **Multiple use-case DTOs:** `CreateAccountRequest`, `UpdateAccountRequest`, `PatchAccountRequest`, and `AccountResponse`. Each type contains only the fields belonging to its contract, typically using `@Valid` to check the `Default` group.

Both approaches can produce the same Bean Validation outcome, yet they **do not provide the same clarity of data contract**. Groups are a tool for choosing which constraints run; DTOs are a tool for describing the **shape and meaning** of data. Groups **do not remove fields from JSON**, do not stop clients from sending a property present on the class, and do not replace write-permission checks.

```text
                      Operations / use cases
                                │
                    Are shape and meaning similar?
                          /             \
                        Yes              No
                         │                │
               One DTO + groups      Separate DTOs
               can stay simple     are usually clearer
                         │                │
                         └───────┬────────┘
                                 ▼
                       Clear mapper / command
                                 ▼
                 Domain + authorization + database
```

**There is no rule saying "once you have two groups, you must split the DTO".** You must examine differences in shape, write permissions, lifecycle, evolution rate, and the complexity of the group matrix.

## 2. Distinct Responsibilities of DTOs, Groups, and Domain

| Layer / Mechanism | Primary responsibility | Not its responsibility |
| --- | --- | --- |
| Request DTO | Which fields clients can send for an operation; input constraints | System-wide business rules |
| Bean Validation group | Select which constraint set is evaluated on an object | Hiding fields, blocking mass assignment, authorization |
| Service / domain | Invariants, state, authorization, transactions, cross-entity rules | Being a mirror of every JSON request |
| Response DTO | Which fields the server exposes publicly | Using a request or entity containing secrets as a response |
| Mapper | Map only allowed fields into domain commands/entities | Copying every property just because names match |

In Jakarta Validation:

- Constraints **without `groups` declared** belong to `jakarta.validation.groups.Default`.
- A constraint `@NotBlank(groups = Create.class)` belongs only to `Create`, **not automatically to `Default`**.
- `validator.validate(bean)` checks the default group; `validate(bean, Create.class)` checks the selected group and relationships defined per the specification.
- `@Valid` on a Spring MVC argument normally selects `Default`; `@Validated(Create.class)` lets you request a custom group.
- Passing `validate(bean, Default.class, Create.class)` selects both; it does not guarantee execution order without `@GroupSequence`.

**Mini-conclusion:** replacing a shared DTO with separate DTOs can remove the need to pick custom groups in controllers, yet it does not by itself solve business rules, JSON parsing errors, or permission checks.

## 3. Two Designs on the Same Example

### 3.1. One DTO with Two Validation Groups

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public interface Create {}
public interface Update {}

public class AccountInput {
    @NotBlank(groups = {Create.class, Update.class})
    private String displayName;

    @NotBlank(groups = Create.class)
    private String initialCode;

    @NotNull(groups = Update.class)
    private Long id;
}
```

These are **illustrative fragments**; when compiling, each top-level `public` type needs its own file, and the DTO needs constructors/accessors matching your binding mechanism.

Logic table:

| Requested group | `displayName` | `initialCode` | `id` |
| --- | --- | --- | --- |
| `Default` | Not checked | Not checked | Not checked |
| `Create` | `@NotBlank` | `@NotBlank` | Not checked |
| `Update` | `@NotBlank` | Not checked | `@NotNull` |

If an endpoint only puts `@Valid` without specifying `Create`/`Update`, the constraints above may not run because they belong only to custom groups. This bug easily occurs when the number of groups grows and every controller must remember its own group.

Moreover, `AccountInput` still carries all three fields for both create and update. If a client sends `id` during create, the fact that `Create` does not validate `id` **does not mean Jackson rejects that property**, and a mapper might accidentally use it.

### 3.2. Separate DTOs per Operation

```java
import jakarta.validation.constraints.NotBlank;

public record CreateAccountRequest(
        @NotBlank String displayName,
        @NotBlank String initialCode) {
}

public record UpdateAccountRequest(
        @NotBlank String displayName) {
}

public record AccountResponse(
        Long id,
        String displayName) {
}
```

The records above are fragments; each `public record` needs its own file when top-level. With `PUT /accounts/{id}`, the ID is in the path so `UpdateAccountRequest` does not need another ID; a different API might intentionally put the ID in the body if its contract specifies so.

Benefits:

- `CreateAccountRequest` has no `id` field.
- `UpdateAccountRequest` has no `initialCode` field.
- Constraints belong to `Default`, fitting `@Valid` naturally.
- Requests and responses have distinct schemas; the type system and reviewers immediately see which fields exist.
- The create API can evolve without necessarily changing update.
- During mapping, each request type leads to a specific command/domain operation.

The cost is additional classes, tests, and mappers. Having `displayName` in two DTOs is **intentional contract duplication**, not necessarily business-logic duplication.

## 4. Criteria Where **Multiple DTOs** Are Usually Better

### 4.1. Accepted Fields Differ

If create accepts `initialCode` while update must not accept it, or only an admin API may edit `role`, placing every field into one shared DTO creates a "superset" that is easy to misuse.

For example:

- `CreateUserRequest`: `email`, `password`.
- `UpdateProfileRequest`: `displayName`, `avatarUrl`.
- `ChangePasswordRequest`: `oldPassword`, `newPassword`.
- `AdminChangeRoleRequest`: `role`, `reason`.

These four operations have distinct meanings and access rights. Using one giant DTO with four groups might reduce class count, yet increases meaningless states and obscures which fields may be bound. **Separate DTOs express input rights at the shape level**; even then, server-side authorization and mapping allowlists are still required.

### 4.2. Many Fields Are Null Because "Not Applicable to This Step"

If create always has `id=null`, update always has `initialCode=null`, and publish always has `draftOnlyFlag=null`, the service must know which group ran in order to interpret null values. Risk rises when a single type can represent many business-invalid state combinations.

**Signal to split:** service code has many `if (creating)`/`if (updating)` branches just to decide which fields to read. Use-case DTOs eliminate fields that do not exist in that context, rather than merely skipping constraints.

Do not split if a field is genuinely **optional** in both operations with the exact same meaning.

### 4.3. Security and Internal Data

`groups` is **not** a data-binding allowlist. An `isAdmin` field not validated in the `Update` group can still be deserialized if the type declares that field and the mapper accepts it. Separate DTOs help reduce unwanted fields on requests, yet do not replace:

- Identity and authorization checks.
- Mapping only updatable properties.
- Service/domain business rules.
- Re-checking state from the database instead of trusting all client-supplied data.

Do not reuse the same class for requests and responses if the class holds `passwordHash`, `initialCode`, tokens, internal flags, or audit metadata. Validation groups do not control which fields Jackson serializes.

### 4.4. Contracts and Schemas Evolve Differently

If create needs a new `invitationToken` while update does not change, separate DTOs isolate impact and simplify updating OpenAPI specs and client SDKs. With a shared DTO, adding a field can alter schemas across multiple endpoints even when the corresponding group does not apply.

Splitting DTOs helps when:

- Endpoints have different versioning/deprecation schedules.
- Different client types use different payloads.
- An import/batch step has a completely different shape from CRUD.
- Responses contain computed fields clients never send.

However, if two endpoints genuinely share the same schema and always evolve together, a shared DTO can still keep maintenance costs low.

### 4.5. Too Many Groups Force Readers to Deduce Behavior

Warning signs to reconsider the design:

- Most constraints have long group lists: `{Create.class, Update.class, Import.class, Publish.class, Admin.class, ...}`.
- Numerous `@GroupSequence`, `@ConvertGroup`, and inheritance hierarchies exist solely to serve different endpoints.
- Tests must combine multiple groups just to catch one missing field.
- A change to create routinely breaks update/import tests.
- Reviewers cannot tell from the type alone: "is this request allowed to send `role`?".
- Bugs occur because endpoints confuse `@Valid` with `@Validated(SomeGroup.class)`.

There is **no fixed threshold** for group count. Two or three clear groups are not automatically wrong; even a single group can be overloaded if the DTO holds inappropriate sensitive fields.

### 4.6. PATCH Has Three States to Distinguish

PATCH usually carries different semantics from PUT:

1. **Absent:** field was not sent; keep existing value.
2. **Present-null:** field is present as `null`; may mean clearing the value.
3. **Present-value:** field is present with a new value.

In an ordinary `String displayName` DTO, absent and explicit `null` can both bind to `null`, so adding `@NotNull(groups = Patch.class)` does not reveal "whether the field was sent".

If an API needs these semantics, use a `PatchAccountRequest` with an explicit **field-presence** mechanism (dedicated present/value wrapper, JSON Merge Patch/JSON Patch, or an intentional parser). Thoroughly test Jackson/HTTP boundary behavior; `Optional<T>` does not handle every absent/null case consistently under all configurations.

## 5. When a Shared DTO with Groups Makes Sense

Groups remain a standard, useful feature. A shared DTO is often worth keeping when:

- Two use cases share **the exact same set of fields and meaning**, differing only in a few constraints.
- No sensitive fields are forbidden from appearing in one of the operations.
- Multiple stages of the **same form** (`draft → submit`) require different validation strictness while keeping the same shape.
- There are few groups, with clear selection and testing.
- The DTO is used internally as a command/state object rather than a superset across all REST boundaries.

Example of a form saved as a draft and later submitted:

```java
public interface OnSubmit {}

public class ApplicationDraft {
    @NotBlank
    private String applicantName; // Default

    @NotNull(groups = OnSubmit.class)
    private Long chosenProgramId;
}
```

This is illustrative code. When calling `validate(draft, OnSubmit.class)`, `applicantName` (belonging only to `Default`) **does not run automatically**; to check both on submit, select `Default.class, OnSubmit.class` or use explicit inheritance/sequencing.

Because the same application keeps the same fields across stages, groups express the requirement cleanly without splitting `DraftRequest` and `SubmitRequest` when both contracts genuinely share the same shape.

## 6. Runnable Java 17+: Same Rules Under Both Approaches

The example below uses Jakarta Validation/Hibernate Validator to demonstrate: (1) a shared DTO with custom groups may not be checked under `Default`; (2) separate DTOs with default constraints catch equivalent errors while making clear which fields belong to which use case.

Structure:

```text
dto-design-demo/
├── pom.xml
└── src/main/java/demo/DtoDecisionDemo.java
```

**`pom.xml`** — uses the Spring Boot validation starter as a dependency, while `main` is **standalone Java** without starting Spring:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>dto-design-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/demo/DtoDecisionDemo.java`**:

```java
package demo;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.util.List;

public final class DtoDecisionDemo {
    private DtoDecisionDemo() {}

    public interface Create {}
    public interface Update {}

    public record SharedRequest(
            @NotBlank(groups = {Create.class, Update.class})
            String displayName,
            @NotBlank(groups = Create.class)
            String initialCode,
            @NotNull(groups = Update.class)
            Long id) {
    }

    public record CreateRequest(
            @NotBlank String displayName,
            @NotBlank String initialCode) {
    }

    public record UpdateRequest(
            @NotNull Long id,
            @NotBlank String displayName) {
    }

    public static void main(String[] args) {
        SharedRequest sharedBad = new SharedRequest("", "", null);
        CreateRequest createBad = new CreateRequest("", "");
        UpdateRequest updateBad = new UpdateRequest(null, "");

        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            show(validator, "shared.Default", sharedBad);
            show(validator, "shared.Create", sharedBad, Create.class);
            show(validator, "shared.Update", sharedBad, Update.class);
            show(validator, "createDTO.Default", createBad);
            show(validator, "updateDTO.Default", updateBad);

            show(validator, "shared.createValid",
                    new SharedRequest("Mai", "CODE-1", null),
                    Create.class);
            show(validator, "shared.updateValid",
                    new SharedRequest("Mai", null, 7L),
                    Update.class);
            show(validator, "createDTO.valid",
                    new CreateRequest("Mai", "CODE-1"));
            show(validator, "updateDTO.valid",
                    new UpdateRequest(7L, "Mai"));
        }
    }

    private static void show(Validator validator,
                             String label,
                             Object bean,
                             Class<?>... groups) {
        List<String> errors = validator.validate(bean, groups)
                .stream()
                .map(v -> v.getPropertyPath().toString() + ":"
                        + v.getConstraintDescriptor()
                                .getAnnotation()
                                .annotationType()
                                .getSimpleName())
                .sorted()
                .toList();

        System.out.println(label + " -> " + errors);
    }
}
```

Run from the directory containing `pom.xml` with Maven and JDK 17+:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.DtoDecisionDemo
```

**Lines printed by the program** (excluding auxiliary Maven/provider logs):

```text
shared.Default -> []
shared.Create -> [displayName:NotBlank, initialCode:NotBlank]
shared.Update -> [displayName:NotBlank, id:NotNull]
createDTO.Default -> [displayName:NotBlank, initialCode:NotBlank]
updateDTO.Default -> [displayName:NotBlank, id:NotNull]
shared.createValid -> []
shared.updateValid -> []
createDTO.valid -> []
updateDTO.valid -> []
```

Explanation:

1. `shared.Default` is empty because every constraint on `SharedRequest` specifies `Create`/`Update`, none belong to `Default`. A controller mistakenly using `@Valid` would miss those errors.
2. `shared.Create` selects name + code; `id` is not checked.
3. `shared.Update` selects name + ID; code is not checked.
4. The two separate DTOs contain only their required constraints, all in the default group, so `validator.validate(bean)` produces matching results.
5. With valid data, neither approach produces violations, yet the shared DTO still carries unused fields in each operation.

The code sorts violations by path/constraint name so output does not depend on `Set` order, and avoids printing localized messages. `ValidatorFactory` is properly closed via `try-with-resources`.

This is a **demonstration of Bean Validation**, not proof that Jackson will reject fields from another group or that services will automatically enforce authorization.

## 7. Spring MVC: Groups Select Constraints, DTOs Select Contracts

### 7.1. If Keeping One Shared DTO

The fragments below belong in a Spring Boot 3 application with Spring Web MVC and `starter-validation`:

```java
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SharedAccountController {
    @PostMapping("/shared-accounts")
    public void create(
            @Validated(Groups.Create.class)
            @RequestBody SharedAccountRequest request) {
        // Map only Create fields.
    }

    @PutMapping("/shared-accounts")
    public void update(
            @Validated(Groups.Update.class)
            @RequestBody SharedAccountRequest request) {
        // Map only Update fields.
    }
}
```

This is **illustrative integration code**, requiring `Groups`, `SharedAccountRequest`, packages/imports, and a service. Forgetting `@Validated(...)` or passing the wrong group can cause constraints not to run as expected.

### 7.2. If Using Use-Case DTOs

```java
import jakarta.validation.constraints.NotBlank;

public record CreateAccountRequest(
        @NotBlank String displayName,
        @NotBlank String initialCode) {}

public record UpdateAccountRequest(
        @NotBlank String displayName) {}
```

Each `public record` goes in its own Java file; controller:

```java
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/accounts")
public class AccountController {
    @PostMapping
    public ResponseEntity<Void> create(
            @Valid @RequestBody CreateAccountRequest input) {
        // accountService.create(input);
        return ResponseEntity.noContent().build();
    }

    @PutMapping("/{id}")
    public ResponseEntity<Void> update(
            @PathVariable Long id,
            @Valid @RequestBody UpdateAccountRequest input) {
        // accountService.update(id, input);
        return ResponseEntity.noContent().build();
    }
}
```

The code above is an **integration fragment**, not a standalone program. Returning 204 is merely an illustrative choice, not a mandatory rule for every REST API; many create endpoints return 201 Created or 200 depending on contract.

Spring MVC normally triggers Jakarta Validation for `@Valid @RequestBody` after deserialization. If the body has invalid syntax or wrong types, Jackson/message converters can fail *before* validation. For methods with direct constraints on parameters/return values, Spring Framework 6.1+ method validation can produce `HandlerMethodValidationException` instead of `MethodArgumentNotValidException`; test your exact signatures and error handlers.

**What stays unchanged:** separate DTOs still need `@Valid`/a provider, `@Valid` on nested fields when cascading is needed, safe field mapping, and service-layer authorization checks.

## 8. Splitting DTOs Does Not Mean Duplicating Domain Invariants

Some rules belong to input shapes, while others belong to domain data itself:

- Create request: `initialCode` is required for initialization.
- Update request: new name must not be blank.
- Domain account: rules governing when an account may change its name, email, or status.
- Database: appropriate storage and integrity constraints.

When splitting DTOs, do not copy all business logic out into each controller. Keep shared rules in **domain services / value objects / database** as required; DTOs validate only their specific input payloads.

Mapping fragment:

```java
// Fragment: Account, repository, and exception are not defined here.
public Account create(CreateAccountRequest input) {
    Account account = Account.create(
            input.displayName(),
            input.initialCode());
    return repository.save(account);
}

public void update(Long id, UpdateAccountRequest input) {
    Account account = repository.findById(id)
            .orElseThrow(/* appropriate exception */);
    account.rename(input.displayName());
}
```

With mapping frameworks, configure which fields are writable; never use copy-all-properties onto managed entities that contain fields like `role`, `ownerId`, or `balance`. Share value objects and custom constraints where appropriate instead of merging every request just to avoid repeating one `@NotBlank` annotation.

If using composition to share nested DTOs, remember to add `@Valid` when cascading is wanted and accept that the JSON shape changes to a nested structure. Do not use DTO inheritance just to save one or two fields if it drags unrelated fields into other requests.

## 9. Decision Matrix

The following matrix is a **design heuristic**, not a mandatory Jakarta or Spring rule:

| Question | If answered "yes" | Preferred direction |
| --- | --- | --- |
| Do two operations share the same fields and meaning, differing by only a few constraints? | Yes | One DTO + groups can make sense |
| Must a field **be excluded from the request** in another operation? | Yes | Separate DTOs |
| Are there secrets, roles, or audit fields at risk of improper binding? | Yes | Separate DTOs + authorization/allowlist |
| Do create, update, PATCH, and response have different shapes? | Yes | Separate DTOs per use case |
| Are many fields `null` because "unused in this group"? | Yes | Separate DTOs |
| Do multiple group inheritance, conversion, and sequence rules exist just for endpoints? | Yes | Consider splitting |
| Do draft and submit use the exact same form and shape? | Yes | Groups can be a good fit |
| Do APIs/schemas/client SDKs need to evolve independently per endpoint? | Yes | Separate DTOs |
| Would splitting produce dozens of identical DTOs with no independent contracts? | Yes | Consider a shared DTO |
| Have bugs occurred from picking the wrong group? | Yes | Split DTOs or simplify groups/tests |

Quick questions to ask:

- **Groups:** "Which *constraints* on this same object does this validation pass check?"
- **Separate DTOs:** "Which *fields* is this use case allowed to accept?"
- **Service/domain:** "Is this operation/state *valid according to business rules*?"
- **Authorization:** "*Who* has permission to perform this operation?"

Never let one of these four tools completely replace the other three.

## 10. Refactoring from One Many-Group DTO to Multiple DTOs

Controlled sequence:

1. **Inventory current contracts:** endpoints, selected groups, JSON/form shapes, bound fields, nested validation, mappers, schemas, and error responses.
2. **Write characterization tests** for currently accepted and rejected requests; cover absent, null, wrong types, child beans, group inheritance, and security.
3. **Define allowed fields per use case** before creating new DTOs. Do not blindly copy every property from the shared class.
4. **Declare the new DTOs** with default constraints fitting each operation. For PATCH, use a model capable of representing field presence when needed.
5. **Map per operation** to commands/domain; keep invariants and authorization in the service.
6. **Migrate controllers endpoint by endpoint** from `@Validated(Create.class) SharedRequest` to `@Valid CreateRequest`, confirming no constraints are lost from switching groups.
7. **Check backward compatibility:** changing Java types can alter JSON schemas, error messages, unknown-field handling, or pre-validation deserialization errors.
8. **Run regression tests** and contract tests: success, validation, forbidden fields, nested DTOs, write permissions, and no leaked secrets in responses.
9. **Remove old code/groups once no callers remain**, avoiding two parallel validation paths with untested gaps.

### Recommended Test Matrix

| Scenario | Required check |
| --- | --- |
| Create missing name/code | Violation per create contract |
| Update missing initial code | Does not demand create-only fields |
| Create sending client-chosen ID | Disallowed ID is not used; reject/ignore behavior verified |
| Update sending admin field | Cannot be updated via self-service endpoint |
| PATCH omitting a field | Field remains unchanged |
| PATCH sending `null` | Clears only if contract allows |
| Malformed JSON data | Handled as binding/deserialization error |
| Invalid child bean | `@Valid` cascades at the right spot |
| Response | No secrets or internal metadata exposed |
| Old group validations | No required rules lost after splitting DTOs |

Note when refactoring to Java records/constructor binding: Jackson's handling of missing, `null`, or wrong-type properties can differ from setter-based JavaBeans, so HTTP error behavior may change. Test it explicitly rather than assuming 100% compatibility.

## 11. Common Mistakes

| Mistake | Correct understanding |
| --- | --- |
| "Repeating `displayName` in two DTOs always violates DRY" | Two independent contracts may intentionally share a small declaration |
| "Groups make unrelated fields disappear from requests" | Groups select constraints, not JSON fields |
| "`@Valid` runs every custom group" | It normally uses `Default` |
| "`@Validated(Create.class)` automatically includes `Default`" | No, unless an appropriate group relationship is declared |
| "Splitting DTOs means `@Valid` is no longer needed" | You still must trigger validation and cascade where needed |
| "Separate DTOs replace security/authorization" | Permission checks and mapping allowlists are still required |
| "Multiple DTOs require duplicating business logic" | Shared invariants live in domain/service/value objects |
| "`@NotNull` + groups is enough for PATCH" | Does not distinguish absent from explicit `null` |
| "Requests can serve as responses by switching groups" | Groups do not control serialization |
| "One DTO with a couple of groups is always wrong" | When shapes are genuinely identical, groups can be simpler |
| "`@GroupSequence` solves field write permissions" | Sequences control validation order, not authorization |

## 12. Selection Checklist

- [ ] Have **allowed fields** been listed for each operation?
- [ ] Are shapes genuinely identical, or is the current DTO a superset of multiple contracts?
- [ ] Are there secrets, roles, `ownerId`, or audit fields that must not bind on certain endpoints?
- [ ] Do many `null`s appear because fields do not apply, or because they are truly optional?
- [ ] Must a change in create remain independent from update?
- [ ] Is it easy to accidentally confuse `@Valid` with `@Validated(Group.class)`?
- [ ] Do group inheritance, sequences, or conversions make the logic hard to follow?
- [ ] Is there a PATCH absent/null/value requirement?
- [ ] Do separate DTOs map cleanly to the domain using a mapping allowlist?
- [ ] Are there tests for API contracts, parsing, validation, authorization, and secret-free responses?
- [ ] If splitting DTOs, have impacts on JSON schemas and client compatibility been reviewed?

**Conclusion:** When **the same object and shape** simply need multiple staged validation levels, Bean Validation groups are very helpful. When operations have **distinct allowed fields, write permissions, data structures, or evolution lifecycles**, preferring multiple DTOs clarifies contracts and reduces risk. Groups only choose **which constraints run**; they do not replace contracts, mappers, domain invariants, or authorization.

### Official References

- [Jakarta Bean Validation 3.0 — Groups, Default, Group Sequence](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Hibernate Validator 8 — Grouping Constraints](https://docs.jboss.org/hibernate/validator/8.0/reference/en-US/html_single/)
- [Spring MVC — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring MVC — `@ModelAttribute` Binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
