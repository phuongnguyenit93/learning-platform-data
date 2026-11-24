# Identify Input Conditions and Expected Outcomes

When designing a test, two questions need clear answers: **what input conditions is the subject under test receiving?** and **given those conditions, what outcome must the system produce?** Simply invoking a method and checking that it throws no error usually does not adequately describe the behavior the application must guarantee.

In Spring Framework Testing, defining inputs and expected outcomes helps choose the right way to build test data, configure the Spring context, mock dependencies, and write assertions. A good test case describes externally observable behavior while being specific enough that when it fails, you know which condition was not met.

## 1. Understand Inputs and Expected Outcomes Properly

**Input** is every piece of information that can affect the behavior under test. It is not limited to parameters passed to a method. Depending on the test scope, inputs may include:

- Direct values: strings, numbers, objects, HTTP requests, messages, or events.
- Initial state: whether a record already exists, whether an account is active or locked, whether a cart is empty or holds items.
- Dependency responses: whether a repository returns data or finds nothing, whether an external service succeeds or fails.
- Configuration and environment: properties, profiles, selected beans, time zone, locale, or access permissions.
- Timing and lifecycle state: whether data has expired, whether a transaction is open or has ended.

**Expected outcome** is the behavior that can be observed and verified after executing the operation. An outcome can consist of multiple parts:

- Return value or return type.
- Exception thrown in invalid-input cases.
- HTTP status, response body, headers, or redirect from an endpoint.
- State of data saved, updated, or deleted.
- Required interactions with dependencies, such as saving only once or not calling an external service when input is invalid.
- Events emitted, transaction commit/rollback, or another state change belonging to the feature's contract.

Not every test case needs to check all the outcome types above. Choose the outcomes that are meaningful for the behavior under test.

### Distinguish Inputs, Preconditions, and Outcomes

These three concepts are related but answer different questions:

| Element | Question to answer | Account registration example |
|---|---|---|
| Input | What does the user or caller provide? | Email, password |
| Precondition | What state already exists before the action begins? | Email is unused; repository contains an account with a duplicate email |
| Dependency response | How do collaborators respond within test scope? | `existsByEmail` returns `true` or `false` |
| Expected outcome | What must the action return or raise? | Create account or throw `DuplicateEmailException` |
| Side effects | What is the system allowed to change? | Save the account exactly once; do not save when email already exists |

For example, saying "input is a valid email" is not enough to describe a registration test case. We also need to know whether that email already exists, whether the password meets the minimum length, and when registration succeeds whether the account is saved with a normalized email.

## 2. Start from the Behavior Contract

Before writing a test, express the behavior to protect as a statement with condition and outcome:

> When **input conditions and initial state** are ..., if **action** ... is performed, the system must **produce observable outcome** ... .

Example:

> When the email is not yet in use and the password meets the minimum length, if the user registers with an email containing leading/trailing spaces and uppercase letters, the system creates an account with the normalized email and stores an encoded password.

This statement tells us we need to prepare an unused email, provide a valid password, invoke registration, and verify both the resulting data and the save operation. It also avoids writing a test that merely checks the method returns a non-`null` object.

You can define the contract in the following sequence:

1. **Choose the behavior to test.** Identify a method, use case, endpoint, or processing flow observable by users or other components.
2. **List input data.** Note parameters, request fields, headers, messages, and configuration values with direct impact.
3. **Define initial state.** Specify data that must exist or must not exist before the action runs.
4. **Define dependency responses.** If the outcome depends on a repository, gateway, or another service, specify how the dependency responds in the test.
5. **Write expected outcomes.** Use concrete verifiable values, state, exceptions, or interactions.
6. **Specify what must not happen.** For example: do not persist data when validation fails, do not send an email when a transaction is rejected.

Writing down both what must happen and what must not happen helps catch side-effect bugs. An operation might throw the right exception while still writing bad data beforehand; checking only the exception would miss that bug.

## 3. Partition the Input Domain into Meaningful Cases

Do not pick just one "normal" dataset and call it sufficient. Classify values by how they affect behavior.

### 3.1. Equivalence Partitioning

Equivalence partitioning divides the input domain into groups where values in the same group are expected to be handled identically. We typically select one or a few representatives per group rather than testing every possible value.

For example, a registration feature requires passwords of at least 12 characters:

| Input group | Representative value | Outcome to verify |
|---|---|---|
| Missing password | `null` or empty string | Reject input |
| Shorter than limit | 11 characters | Reject input |
| Exact limit | 12 characters | Accept if other conditions are valid |
| Longer than limit | 13 characters | Accept if other conditions are valid |

If the business rule only distinguishes passwords under 12 characters from 12 characters or more, there is no need to write dozens of tests for lengths 13, 14, 15... A few representatives suffice to prove the important groups.

### 3.2. Boundary Value Testing

Bugs often appear at the transition between valid and invalid. With a minimum limit of 12, notable values are 11, 12, and 13. With a maximum limit of 100, pay attention to 99, 100, and 101.

Boundary values also apply to:

- Item counts in a collection: 0, 1, and the allowed limit.
- Dates and times: right before, right at, and right after expiration.
- Monetary amounts: 0, minimum amount, free-shipping threshold, or discount tier threshold.
- Pagination: first page, last page, page size 0, or exceeding the limit.

Distinguish the business rule carefully. For example, "at least 12 characters" includes 12; "more than 12 characters" excludes it. Testing right at the boundary catches off-by-one bugs such as confusing `>` with `>=`.

### 3.3. Decision Tables for Multiple Conditions

When the outcome depends on multiple conditions simultaneously, a decision table exposes the important combinations. For example, an order is confirmed only when inventory is sufficient and payment succeeds:

| Sufficient inventory | Payment succeeds | Expected outcome |
|---|---|---|
| Yes | Yes | Confirm order |
| Yes | No | Reject confirmation, keep unpaid state |
| No | Yes | Do not confirm; process refund or hold payment per defined contract |
| No | No | Reject confirmation |

The third row shows why defining the full outcome matters: "order is not confirmed" may be incomplete if money was already charged. The effect on payment must be clearly specified in the functional contract before writing assertions.

### 3.4. State and State-Transition Testing

For objects with a lifecycle, inputs also include the current state. A cancel-order request may be valid when the order is `PENDING`, yet invalid when it is already `SHIPPED` or `CANCELLED`.

Specify the tuple **initial state → action → final state**. When multiple states exist, test allowed transitions and transitions that must be rejected. This approach is helpful for workflows, orders, login sessions, approval pipelines, and stateful entities.

### 3.5. Avoid Mechanical Cartesian Combinations

When a feature has many input fields, taking the Cartesian product of all values can produce a huge number of tests. Not all combinations carry equal value.

- Prioritize combinations representing each business rule and each decision branch.
- Test conditions that can mask each other separately, such as an empty email and a too-short password.
- Test high-risk interactions, such as a locked user whose request still carries a valid token.
- When there are many independent parameters, pairwise techniques can select a set covering pairs of values; still add any combinations explicitly required by business rules.

The goal is covering meaningful behaviors, not inflating test count at any cost.

## 4. Specify Concrete Expected Outcomes

An outcome like "processed successfully" or "returns an error" is too vague. State clearly what proves that success or error.

| Behavior category | Assertions that may be needed |
|---|---|
| Calculation function | Exact return value, unit, and rounding rules |
| Validation | Exception or validation error of the right type; no data written |
| Search | Element count, contents, ordering, and empty-result handling |
| Data write | Record created/updated with accurate fields; no duplicates created |
| HTTP communication | Status, headers, body, content type, and error structure |
| Dependency interaction | Dependency called with right arguments and count when interaction is part of the contract |
| Transaction | Data committed or rolled back per required behavior |
| Events | Required event published with appropriate payload |

Prefer checking observable outcomes. If the contract only requires the account to be saved properly, asserting that a private method was called couples the test to implementation. Conversely, if the contract specifies an email is sent only once, the call count to the mail gateway is worth asserting.

For error cases, specify all relevant parts:

- Exception type or HTTP status to return.
- Error code or stable error fields that clients rely on, if any.
- Data state after the error occurs.
- Side effects that must be prevented.

Do not lock tests onto the full error message string if that text is not a public contract. Copy may be edited without changing behavior. Assert exception types, error codes, or stable response fields according to application requirements.

## 5. Applying This When Testing Spring Applications

Spring offers several ways to set up test conditions. The choice depends on the scope of behavior to verify.

### 5.1. Unit Tests for Standalone Logic

When testing rules inside a service without needing a Spring container, use JUnit and mock external dependencies. This gives exact control over repository or gateway responses while keeping tests fast.

For example, suppose `RegistrationService` has this contract:

- Reject blank emails.
- Require passwords of at least 12 characters.
- Normalize email by trimming surrounding whitespace and converting to lowercase.
- Reject already-existing emails.
- Encode the password before saving the account.

A test case matrix can be drafted before writing code:

| Case | Input and initial state | Expected outcome |
|---|---|---|
| Blank email | Email containing only whitespace | `IllegalArgumentException`; do not touch repository or encoder |
| Too-short password | Valid email, 11-character password | `IllegalArgumentException`; do not save account |
| Duplicate email | Normalized email already exists in repository | `DuplicateEmailException`; do not encode and do not save |
| Valid registration | Unused email, sufficiently long password | Return saved account with normalized email and encoded password |
| Exact password boundary | Password of exactly 12 characters | Accepted if other conditions are valid |

Test example using JUnit 5 and Mockito:

```java
@ExtendWith(MockitoExtension.class)
class RegistrationServiceTest {

    @Mock
    private AccountRepository repository;

    @Mock
    private PasswordEncoder passwordEncoder;

    @InjectMocks
    private RegistrationService service;

    @Test
    void rejectsBlankEmailBeforeCallingDependencies() {
        assertThrows(IllegalArgumentException.class,
                () -> service.register("   ", "valid-password-123"));

        verifyNoInteractions(repository, passwordEncoder);
    }

    @Test
    void rejectsDuplicateEmailWithoutEncodingOrSaving() {
        when(repository.existsByEmail("user@example.com")).thenReturn(true);

        assertThrows(DuplicateEmailException.class,
                () -> service.register(" USER@example.com ", "valid-password-123"));

        verify(repository).existsByEmail("user@example.com");
        verifyNoMoreInteractions(repository);
        verifyNoInteractions(passwordEncoder);
    }

    @Test
    void normalizesEmailAndSavesEncodedPassword() {
        when(repository.existsByEmail("user@example.com")).thenReturn(false);
        when(passwordEncoder.encode("valid-password-123"))
                .thenReturn("encoded-value");
        when(repository.save(any(Account.class)))
                .thenAnswer(invocation -> invocation.getArgument(0));

        Account result = service.register(
                " USER@example.com ", "valid-password-123");

        assertEquals("user@example.com", result.email());
        assertEquals("encoded-value", result.passwordHash());

        ArgumentCaptor<Account> captor = ArgumentCaptor.forClass(Account.class);
        verify(repository).save(captor.capture());
        assertEquals("user@example.com", captor.getValue().email());
        assertEquals("encoded-value", captor.getValue().passwordHash());
    }
}
```

The snippet assumes `Account` is a record with accessors `email()` and `passwordHash()`, `AccountRepository` has `existsByEmail` and `save`, and `RegistrationService` implements the stated contract. Actual class names and APIs must match the real application.

The first test checks invalid input and verifies no dependency is called. The second sets up the "email already exists" state, then checks the exception and prevents encoding/saving. The third stubs dependency responses to verify normalized and saved data. Each test thus has one clear purpose and verifies both outcome and relevant side effects.

Length boundaries can be verified with a parameterized test:

```java
@ParameterizedTest
@ValueSource(strings = {"", "12345678901"})
void rejectsPasswordShorterThanTwelveCharacters(String password) {
    assertThrows(IllegalArgumentException.class,
            () -> service.register("user@example.com", password));

    verifyNoInteractions(repository, passwordEncoder);
}
```

In real tests, add a case of exactly 12 characters to verify the accepted boundary. To include `null`, you can combine `@NullSource` with `@MethodSource` or write a separate test matching the method signature.

### 5.2. When Spring TestContext Is Needed

When behavior depends on Spring creating beans, injecting dependencies, applying profiles, handling transactions, or configuring the application context, test inside Spring TestContext.

With JUnit Jupiter, `SpringExtension` integrates JUnit's test lifecycle with the Spring TestContext Framework. `@ContextConfiguration` specifies the configuration to load:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestApplicationConfig.class)
class RegistrationServiceContextTest {

    @Autowired
    private RegistrationService service;

    @Test
    void serviceIsCreatedWithRequiredDependencies() {
        assertNotNull(service);
    }
}
```

The example above only illustrates loading a context and injecting a bean. If the target is verifying registration rules, the test must prepare appropriate dependencies and data and assert business outcomes; checking only that a bean is non-`null` does not prove those rules work.

Choose just enough test configuration:

- Use a unit test when only single-class logic needs verification.
- Use Spring TestContext when verifying wiring, bean lifecycle, profiles, properties, or Spring-managed transactions.
- Use a test slice when only one infrastructure layer is needed, such as the web or persistence layer in a Spring Boot application.
- Use `@SpringBootTest` when testing multiple components configured together at application scope; avoid using it by default for every small rule.

Spring Boot test annotations such as `@WebMvcTest` and `@DataJpaTest` are Spring Boot slice options. With plain Spring MVC Test, `MockMvc` can be built from a controller via `MockMvcBuilders` without starting the whole application.

### 5.3. Testing the Web Layer with MockMvc

For HTTP endpoints, treat the request as input comprising method, path, query parameters, headers, content type, body, and authentication state. Expected outcomes should specify status, response body, and important headers.

Example of a hypothetical contract for an account creation endpoint:

```java
mockMvc.perform(post("/accounts")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
                {
                  "email": "user@example.com",
                  "password": "valid-password-123"
                }
                """))
    .andExpect(status().isCreated())
    .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
    .andExpect(jsonPath("$.email").value("user@example.com"));
```

This is an example of expressing assertions, not a mandatory convention for every API. If the application contract requires `201 Created`, a `Location` header, or a specific response DTO, assert those parts. For invalid requests, check the status and error structure published by the API, and verify no unintended data was written.

### 5.4. Testing Persistence and Transactions

When queries or data mappings need verification, use persistence tests against an appropriate database. Mocking a repository only verifies how a service interacts with the repository; it does not prove SQL statements, mappings, or database constraints work properly.

In Spring-managed transactional tests, data is usually rolled back after each test under Spring TestContext's default configuration. However, do not assume every effect rolls back automatically: operations on another thread, independent transactions like `REQUIRES_NEW`, outbound messages, or HTTP calls lie outside the current test transaction. Design preconditions and cleanup strategies around real transaction boundaries.

## 6. Preparing Dependencies So Test Conditions Are Controllable

When the outcome depends on other components, treat dependency responses as part of the test condition. In unit tests, Mockito can simulate those responses. In integration tests, prefer real components or a test double fitting the target.

For example, when testing an order-processing service:

- The repository returns an order in `PENDING` state.
- The payment gateway returns success.
- The inventory service confirms sufficient stock.
- The expected outcome is that the order moves to `CONFIRMED` and emits a confirmation event per contract.

Another test can configure the payment gateway to return failure. In that case, specify which state the order keeps, whether an event is published, and whether the shipping service is called.

Avoid letting mocks return unintended default values. For every dependency affecting the outcome, configure explicit responses so readers understand what state the test simulates. Likewise, mock only dependencies outside the target behavior's scope; mocking the very component you aim to verify prevents testing real behavior.

## 7. Organizing Readable and Maintainable Test Cases

A test case should have a clean structure:

1. **Arrange:** create data, initial state, configuration, and dependency responses.
2. **Act:** perform exactly one primary action.
3. **Assert:** check outcomes and important side effects.

Test names can describe behavior using `method_condition_expectedOutcome`, for example:

```java
@Test
void cancel_whenOrderIsAlreadyShipped_throwsInvalidStateException() {
    // Arrange: order is in SHIPPED state
    // Act: request order cancellation
    // Assert: operation is rejected and state remains unchanged
}
```

Test names should clarify condition and outcome, avoiding generic names like `test1`, `testSuccess`, or `shouldWork`.

When multiple cases test the same rule, `@ParameterizedTest` shares execution and highlights input data. When cases differ substantially in setup or assertions, separate tests are usually easier to read than one large test full of `if` branches.

You can document a test case before writing code using this template:

| Field | What to record |
|---|---|
| Test name | Primary condition and outcome |
| Behavior | Method, use case, or endpoint under test |
| Precondition | Initial data and environment state |
| Input | Parameters, request, headers, or message |
| Dependencies | Required responses from repositories, gateways, or other services |
| Outcome | Return value, exception, HTTP response, or new state |
| Side effects | Allowed and disallowed calls, records, or events |
| Cleanup | How to restore data or resources after the test if needed |

## 8. Keeping Tests Stable and Independent

Input conditions must be explicitly constructed so tests run repeatably with identical results. Common causes of flaky tests include:

- Depending on current date/time. Inject a `Clock` or controllable time source and fix the instant in tests.
- Depending on data created by an earlier test. Each test must prepare its own state or use controlled fixtures.
- Using random data without fixing the seed or logging values on failure.
- Calling real external services in unit tests, making results depend on networks, credentials, or external system state.
- Sharing mutable objects across multiple tests, causing execution order changes to alter results.
- Checking only the response without checking persisted state, letting data bugs slip through.

For integration tests, decide explicitly where data is created, whether it is isolated by transactions or separate schemas, and how it is cleaned up. Tests must not depend on execution order or leftover data from a previous run.

## 9. Common Design Mistakes

**Testing only the happy path.** A feature usually has rejection branches, boundary data, and abnormal states. Partition inputs and pick cases representing critical rules.

**Omitting initial state.** "Send an order cancellation request" is incomplete; outcomes differ depending on whether the order is `PENDING`, `SHIPPED`, or `CANCELLED`.

**Overly generic expected outcomes.** Assertions like `assertNotNull(result)` do not prove content, state, or side effects are right. Check key contract properties.

**Bundling multiple independent behaviors into one test.** When one test registers an account, sends an email, logs in, and updates a profile, a failure at any step fails the test. Split tests by behavior or by genuine integration flows needing verification.

**Testing implementation details too deeply.** Verifying every internal call breaks tests during refactoring even when external behavior is unchanged. Verify interactions only when part of the contract or needed to prove side effects.

**Mocking the entire system.** If every component is mocked, the test only proves mocks were configured and called as scripted. Pick the right boundary: unit tests mock dependencies; integration tests keep components that must be verified together.

**Failing to assert what must not happen.** In error cases, besides asserting the exception or HTTP status, verify no unwanted records, payments, or events were created.

**Using too broad a Spring context for a small rule.** Starting the entire application slows tests and increases the number of moving parts. Load a context only when the behavior under test genuinely depends on Spring configuration or integration.

## 10. Workflow for Finalizing Conditions and Outcomes

Before implementing tests, ask yourself:

- What behavior is being protected and who observes it?
- Which parameters, states, configurations, and dependency responses can alter the outcome?
- Which valid partitions, invalid partitions, and boundary values exist in the input domain?
- Which initial states lead to different outcomes?
- Is the outcome to verify a return value, exception, response, persisted data, or side effect?
- When the operation fails, which changes must strictly not occur?
- Is the right test scope a unit test, Spring TestContext, MVC test, or persistence integration test?
- Are data and dependencies prepared clearly enough for the test to run independently and repeatably?

When answers to these questions appear in the test case, Arrange holds deterministic data and state; Act focuses on the behavior under test; Assert verifies concrete outcomes. Each test thus becomes a readable example of the Spring application's contract while pinpointing exactly which condition caused a behavioral deviation.
