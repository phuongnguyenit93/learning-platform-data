# Distinguishing input validation, business rules, and storage constraints

> Knowledge article under **Spring Framework – validation/data binding**. Examples use Java 17+, Spring Framework 6/Spring Boot 3, and Jakarta Bean Validation. The focus is on correctly identifying each layer's responsibilities, how to coordinate them in a use case, and the limits of each mechanism.

## 1. Why separate the three kinds of checks?

Suppose an API receives an account registration request with `email` and `password`. These three questions are very different:

1. **Input validation:** is the email empty or malformed? Is the password long enough per the request contract?
2. **Business rule:** is the system currently open for registration? Is the user eligible to register? Is a previously used email allowed to re-register if the account was locked or soft-deleted?
3. **Storage constraint:** will the DB accept two rows with the same `normalized_email`? Can `NULL` be written into a required column? Are foreign key relationships still valid?

A request that passes `@Valid` can still be rejected in the service. A use case that passed state checks in the service can still fail on write because another transaction just changed the data.

**Principle:** each layer checks what it knows and what it has the ability to guarantee. Some invariants need protection across two or three layers for different purposes; that is intentional coordination, provided they share the exact same definition.

## 2. Comparison table

| Criterion | Input validation | Business rule | Storage constraint |
| --- | --- | --- | --- |
| Question | Does the received data match the expected structure, type, range, and format? | Is the action or state allowed by product policy? | Does stored data always satisfy persistence invariants? |
| Data needed | Request DTO, JSON, types, related fields inside the request | Domain objects, current state, permissions, time, policy | Rows/columns, keys, relations, data inside the transaction |
| Typically implemented at | Converter/data binder, DTO, Jakarta Bean Validation, Spring MVC | Application service, domain model, domain service | Schema/migrations, constraints, indexes, transactions/locking |
| Example | Non-blank email, at most 254 characters | Register only while campaign is open | `UNIQUE(normalized_email)` |
| Response | Field-level error or unreadable payload error | Meaningful business error | Constraint error recognized/translated appropriately by the app |
| What it does not guarantee | Does not know state already modified by another transaction | Pre-write checks can suffer race conditions | Cannot express all permissions, workflows, or external service rules |

Classification cannot rely solely on annotation syntax. For instance, "quantity must be greater than 0" may appear as `@Positive` on a DTO, a domain condition, and `CHECK (quantity > 0)` in the DB. Each place guards a different boundary.

## 3. Request flow in Spring

```text
Client
  |
  v
HTTP -> JSON parsing / Data binding / Type conversion
         |  invalid JSON, wrong type -> read or bind error
         v
      Bean Validation on Request DTO
         |  blank, wrong format, out of range -> input error
         v
      Controller
         v
      Application/Domain Service
         |  check policies, permissions, and use-case invariants
         v
      Repository (JPA/JDBC)
         v
      Database
            NOT NULL / UNIQUE / CHECK / FOREIGN KEY
            transaction + concurrency control
```

**Data binding and validation are two distinct steps.** The payload `{"quantity":"abc"}` cannot bind to a numeric type at the conversion step. The payload `{"quantity":-2}` can bind successfully yet violates `@Positive`. Invalid JSON and bound values violating constraints must not be collapsed into one technical error category.

In Spring MVC, `@Valid @RequestBody` triggers object validation after the request body is read and converted into a Java object (when a suitable Bean Validation provider is present). Constraint errors usually result in `MethodArgumentNotValidException`; unreadable JSON usually results in `HttpMessageNotReadableException`. With `@ModelAttribute` or method parameters, the binding path and exceptions may differ. Applications should handle each actual type.

## 4. Input validation: the contract between client and system

These are conditions determinable from the request without querying mutable system state:

- **Requiredness:** `@NotNull` only forbids `null`; `@NotBlank` also forbids empty/whitespace-only strings; `@NotEmpty` forbids empty strings or collections.
- **Range:** `@Size` for strings/collections, `@Min`/`@Max`/`@Positive`/`@DecimalMin` for numbers.
- **Format:** `@Email`, `@Pattern`, custom validators per API definition.
- **Nested data:** `@Valid` cascades validation; if the nested object itself must be present, also add `@NotNull`.
- **Cross-field request relationships:** e.g., `startDate <= endDate` can live in a custom class-level validator if it does not depend on system state.

Example DTO:

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record RegisterAccountRequest(
    @NotBlank
    @Email
    @Size(max = 254)
    String email,

    @NotBlank
    @Size(min = 12, max = 128)
    String password
) {}
```

`@Email` only evaluates format according to the validator in use; it **does not verify that the mailbox exists, ownership, or email uniqueness**. `@Size` on `String` constrains character length; actual byte limits in protocols or the DB must be considered separately if relevant.

The controller accepts the DTO to decouple the API contract from persistence entities:

```java
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import java.util.Map;

@RestController
@RequestMapping("/accounts")
public class AccountController {
    private final RegistrationService registrationService;

    public AccountController(RegistrationService registrationService) {
        this.registrationService = registrationService;
    }

    @PostMapping
    public ResponseEntity<Map<String, Long>> register(
            @Valid @RequestBody RegisterAccountRequest request) {
        long id = registrationService.register(request);
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of("id", id));
    }
}
```

This is illustrative code for a Spring project with configured dependencies and `RegistrationService`; **not a standalone program runnable directly via `javac`**. Spring Framework 6/Spring Boot 3 uses the `jakarta.validation` namespace instead of the previous generation's `javax.validation` namespace.

Distinguish:

- `@Valid` is the trigger/cascade mechanism for Jakarta Bean Validation. Spring's `@Validated` supports validation groups and can be used in appropriate method validation setups; neither replaces business conditions.
- DTO validators should only check fields the client is authorized to submit. Avoid binding requests directly into entities with `id`, `role`, `approved`, or internal `status`: this can lead to *mass assignment* vulnerabilities.
- If the service is also called from scheduled jobs, consumers, or internal processes, core domain rules must still be enforced in the service/domain. Controller validation cannot be treated as the sole shield.

## 5. Business rules: validity of an action

Business rules describe product behavior. A few examples:

- Only `ACTIVE` accounts may place orders.
- Orders already handed off to shipping cannot be canceled.
- Refund amount must not exceed the remaining refundable total.
- Users may apply only one promo code per campaign.
- Account registration is only valid while registration policy is open.

These conditions typically require reading repositories, querying the domain, checking state, or verifying permissions. They belong in the application service/domain model/domain service rather than inside a request DTO.

Example registration business logic:

```java
import java.util.Locale;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RegistrationService {
    private final AccountRepository accounts;
    private final RegistrationPolicy policy;
    private final PasswordEncoder passwordEncoder;

    public RegistrationService(
            AccountRepository accounts,
            RegistrationPolicy policy,
            PasswordEncoder passwordEncoder) {
        this.accounts = accounts;
        this.policy = policy;
        this.passwordEncoder = passwordEncoder;
    }

    @Transactional
    public long register(RegisterAccountRequest request) {
        if (!policy.isRegistrationOpen()) {
            throw new RegistrationClosedException();
        }

        // Normalization must be consistent with product policy and the DB.
        String normalizedEmail = request.email()
                .trim().toLowerCase(Locale.ROOT);

        if (accounts.existsByNormalizedEmail(normalizedEmail)) {
            throw new EmailAlreadyUsedException();
        }

        Account account = new Account(
                normalizedEmail,
                passwordEncoder.encode(request.password())
        );
        return accounts.save(account).getId();
    }
}
```

Types like `Account`, `AccountRepository`, `RegistrationPolicy`, and the exceptions are other application components to define; this example illustrates responsibility boundaries, not a complete buildable project. `PasswordEncoder` comes from Spring Security Crypto and requires the corresponding dependency.

Here `policy.isRegistrationOpen()` is a business condition. `existsByNormalizedEmail(...)` helps return a friendly error when an email already exists. Deciding how emails are normalized and whether soft-deleted accounts free up emails are also **business policies**, which must align with how data is stored and indexed.

**Limitation of pre-write business checks:** if two concurrent requests both observe that an email does not exist yet, both can still attempt to create the account. A standard `@Transactional` does not automatically make "check-then-insert" atomic at all isolation levels. For data requiring uniqueness, the database needs a protective constraint.

For rules like "sufficient inventory to deduct", merely reading stock and checking in Java is also vulnerable to races. Optimistic locking, pessimistic locking, conditional updates, or appropriate transaction isolation may be needed. Business rules state *what must be true*; concurrency design determines *how to keep it true under contention*.

## 6. Storage constraints: protecting data even outside the REST API

Storage constraints are rules enforced by the data management system on writes. They remain active when data is inserted by jobs, imports, SQL scripts, other applications, or concurrent transactions.

Example PostgreSQL DDL:

```sql
CREATE TABLE accounts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    normalized_email VARCHAR(254) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',

    CONSTRAINT uq_accounts_normalized_email
        UNIQUE (normalized_email),
    CONSTRAINT ck_accounts_status
        CHECK (status IN ('ACTIVE', 'LOCKED'))
);
```

- `NOT NULL` forbids SQL `NULL`, though it does not prevent `''` or whitespace-only strings.
- `UNIQUE` enforces uniqueness per the DB/index semantics defined. If a column allows `NULL`, how multiple `NULL`s are treated can vary across DBs/constraint types; combine with `NOT NULL` for required fields.
- `CHECK` protects invariants expressible as DB predicates, such as `CHECK (quantity > 0)` or allowed status values.
- `FOREIGN KEY` ensures referenced rows exist and are protected by referential integrity; it **does not verify user authorization** to access a record.
- Transactions, locks, and isolation coordinate with constraints to maintain consistency across multi-step changes.

JPA annotations like `@Column(nullable = false)` or `@Table(uniqueConstraints = ...)` describe mappings and can influence automatic schema generation, yet **do not prove the actual production schema has those constraints**. For databases managed with Flyway/Liquibase, write accurate DDL migrations and test against the deployed schema. Bean Validation's `@NotNull` cannot substitute for DB `NOT NULL`.

### Race condition when checking duplicate emails

```text
Time            Transaction T1              Transaction T2
---------       -------------------------   -------------------------
t1              SELECT email -> not found
t2                                          SELECT email -> not found
t3              INSERT -> succeeds
t4                                          INSERT -> UNIQUE violation
```

Without a unique constraint, two transactions can create two duplicate rows. When the DB has a unique constraint, one transaction is rejected; the application should translate an **identified unique violation** into the corresponding business error code (typically HTTP 409 Conflict). Never assume every `DataIntegrityViolationException` means a duplicate email, because it can also represent `FOREIGN KEY`, `NOT NULL`, `CHECK`, or other integrity failures.

With JPA, constraint errors can surface at `flush` or transaction `commit`, not necessarily right at `repository.save()`. Handle them at a boundary that observes post-write/post-commit failures and identify causes using reliable DB constraint names/error codes. Never return raw SQL messages to clients, as they can leak table names, schemas, or sensitive data.

## 7. One rule can appear in multiple layers

| Requirement | Input | Business | Storage |
| --- | --- | --- | --- |
| Registration email | `@NotBlank`, `@Email`, `@Size` | Whether registration is allowed; normalization policy; handling used emails | `NOT NULL`, `UNIQUE(normalized_email)` |
| Purchase quantity | `@Positive` | Does not exceed order limit/stock; handle concurrent updates | `CHECK(quantity > 0)` on order line; transaction/locking for stock |
| Appointment booking | Date/time types, start before end if static condition | No overlapping slot; within business hours; authorized | Appropriate locks/constraints/transactions for expressible invariants |
| Order cancellation | Order ID valid type/format | User has permission; status allows cancellation | FK and expressible status constraints |
| Role assignment | Accept only client-allowed fields | Granter has sufficient authority and approval | `FOREIGN KEY` to role, `UNIQUE(user_id, role_id)` |

For example, **uniqueness** must be understood in terms of both policy and enforcement:

- The service can pre-check to give a clear "Email already registered" message.
- The DB holds `UNIQUE` to prevent races or bypasses by jobs/imports.
- If business policy permits reusing emails of soft-deleted accounts, a plain `UNIQUE(email)` may conflict with policy; design the key/index (such as a partial unique index in PostgreSQL) and error translation consistently.
- If the business treats emails case-insensitively, lowercasing only in the service while legacy data/jobs write mixed case creates a gap; enforce consistent normalization across all writers and/or corresponding DB index strategies.

You do not need to "force" every rule into all three layers. Some rules live only at the request boundary (a UI parameter with a specific format), only in the domain (workflow state), or only practically in the DB (certain integrity constraints). Choose based on risk and enforcement capability.

## 8. Classifying and returning errors intentionally

| Case | Where detected | API response direction |
| --- | --- | --- |
| Malformed JSON, unconvertible type | Parsing/binding | Typically HTTP 400; describe unreadable request |
| Blank email, too-short password | Bean Validation | Typically HTTP 400; list of field errors |
| Registration closed | Service/domain | Meaningful business error; status per contract (e.g., 403/409/422) |
| Duplicate email per policy | Service or DB `UNIQUE` | Same application error code; typically HTTP 409 |
| Unexpected DB constraint violation | DB | Log for investigation; do not guess it is an email error |
| Lost DB connection | Infrastructure | Appropriate system error; do not turn into "validation failed" |

Use `@RestControllerAdvice` and `@ExceptionHandler` to standardize responses. For `MethodArgumentNotValidException`, extract field errors rather than returning the raw exception. For business errors, define explicit domain exceptions/error codes. For DB errors, translate only after identifying the exact cause; otherwise return a safe error response and log for investigation.

Example response for an invalid request (specific format defined by your API):

```json
{
  "code": "INVALID_INPUT",
  "errors": [
    {
      "field": "email",
      "message": "Invalid email format"
    }
  ]
}
```

For duplicate email, you can return `code: "EMAIL_ALREADY_USED"` and HTTP 409 regardless of whether detected in the service or DB. Do not expose constraint names, SQL, or password data. Also remember that HTTP 400/409/422 are API contract design choices; Spring does not decide all your business semantic status codes for you.

## 9. Process for placing a condition in the right layer

1. **Write the rule as concrete requirements.** "Email non-empty; registration must be open; normalized email has at most one active account."
2. **Extract conditions evaluable solely from the request.** Place in DTO, conversion, or validator. If it is a static cross-field request relationship, a class-level validator may fit.
3. **Extract conditions depending on state/permissions/policy.** Place in the application/domain service, close to state-mutating operations so other adapters also obey them.
4. **Identify invariants that must hold under concurrent writes.** Choose unique indexes, versioning, locks, conditional updates, or suitable DB mechanisms. A `SELECT` before `INSERT` does not replace a constraint.
5. **Manage DDL via migrations and test on a real DB.** Align data types, nullability, sizes, normalization, and uniqueness across API, domain, and schema.
6. **Define error responses and observability.** Distinguish input errors, business rejections, known integrity conflicts, and infrastructure failures; unify error codes for the same root cause.
7. **Test at appropriate boundaries.** DTO/MVC tests, unit tests for domain policies, integration tests for constraints and concurrent transactions.

Key test cases to include:

| Case | Expectation |
| --- | --- |
| Missing or malformed email | Blocked before executing the use case |
| Password fails `@Size` | Error on `password` field |
| Valid input while registration is closed | Service returns business error |
| Pre-existing email | Client receives appropriate conflict response |
| Two concurrent requests with same email | Only one record satisfying unique constraint is persisted |
| Direct SQL inserting `normalized_email = NULL` | DB rejects via `NOT NULL` |
| Direct SQL inserting status outside allowed set | DB rejects via `CHECK` |
| DB integrity error unrelated to email | Not mistranslated as `EMAIL_ALREADY_USED` |

A unit test with a mocked repository returning `existsBy... = false` does not prove race protection. Integration tests with two real transactions are required to verify constraints and error translation.

## 10. Common design mistakes

**Mistake 1 – Thinking `@Valid` proves the use case is valid:** annotations mainly check supplied input data; they do not replace checking permissions, inventory, state, or write contention.

**Mistake 2 – Putting all business rules in controllers/custom constraints:** easily mixes API with business logic, drags DB dependencies into validators, and becomes hard to reuse from jobs/consumers. Business rules belong where actions execute.

**Mistake 3 – Checking duplicates in the service and omitting `UNIQUE`:** the race between SELECT and INSERT still exists. DB constraints are the final line of defense.

**Mistake 4 – Relying solely on the DB and returning raw SQL errors:** data may stay protected, yet clients cannot understand the error and responses may leak internal details. Map errors meaningfully and safely.

**Mistake 5 – Assuming JPA annotations equal deployed schema:** editing an entity does not guarantee migrations ran. Verify the actual schema and data contract.

**Mistake 6 – Layers interpreting rules differently:** API allows longer strings than the DB column; service compares emails case-insensitively while the index is case-sensitive; business permits soft-delete reuse while the DB blocks it. Keep semantics and normalization aligned and test end-to-end.

**Mistake 7 – Collapsing every error into validation:** malformed JSON, bean constraints, business rejections, and storage constraints have distinct causes and owners. Separating them keeps the API clear and the system maintainable.

## 11. Short design checklist

- If it can be decided purely by looking at the request, it is usually **input validation**.
- If it needs to know the actor, system state, current time, or product policy, it is a **business rule**.
- If it must hold even when jobs, scripts, or concurrent transactions write directly to the DB, consider **storage constraints** with appropriate concurrency control.
- If a rule spans multiple layers, verify their definitions are **completely consistent**.
- When a constraint fails, only translate it into a business error once the specific cause is identified; do not turn every DB error into one generic code.

The three layers serve a single goal at different boundaries: **valid inputs to process, valid actions by business rules, and stored data preserving integrity**. A sound system needs both clear feedback and safety under concurrent load.