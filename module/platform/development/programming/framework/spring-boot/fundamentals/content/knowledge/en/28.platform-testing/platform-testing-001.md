# Unit Testing a Service Designed with Constructor Injection

In Spring Boot, a service often depends on a repository, HTTP client, encoder, system clock, or another service. **Constructor injection** makes those dependencies explicit in the constructor, allowing a service to be instantiated directly in a unit test **without starting the Spring ApplicationContext**.

This is an important benefit: unit tests verify the logic of a unit of code under controlled conditions, while Spring only needs to participate when the testing goal involves wiring mechanisms, transactions, persistence, HTTP, or integration across multiple components.

This lesson demonstrates how to design a testable service, use JUnit Jupiter and Mockito, verify outputs alongside dependency interactions, control time, and distinguish the scope of unit tests from integration tests.

## 1. What does a service unit test check?

Suppose the business requirement is user registration:

1. Email and password must not be blank.
2. Email is normalized before lookup.
3. If the email already exists, registration is rejected.
4. Password must be converted into a hash before saving.
5. The registration timestamp is recorded.
6. The repository persists the data and returns the result.

A unit test should focus on the decisions that the service is responsible for. It does not necessarily need to open a real database connection, start an HTTP server, or run all of Spring Boot's auto-configuration.

For example, with a `UserRepository` dependency, a test can simulate an "email does not exist" or "email already exists" response to verify both execution branches.

| Component | In a service unit test | Goal |
|---|---|---|
| Service under test | **Real object** created via constructor | Verify real logic |
| Repository | Mock or fake | Control query/save results |
| PasswordHasher | Mock or fake | Verify the service uses hashing |
| Clock | Real fixed clock | Verify deterministic time |
| ApplicationContext | Not needed | Keep tests focused and fast |
| Database, HTTP server | Not needed | Avoid external infrastructure dependencies |

The common term for the object under test is **SUT** (*System Under Test*). In this lesson, the SUT is `RegistrationService`.

## 2. Why does constructor injection make unit testing simpler?

Consider a service using field injection:

~~~java
@Service
public class LegacyRegistrationService {

    @Autowired
    private UserRepository repository;

    @Autowired
    private PasswordHasher hasher;

    // Business logic ...
}
~~~

Dependencies are assigned after Spring creates the bean. If a test directly calls `new LegacyRegistrationService()`, those fields have not been injected by Spring and will typically be `null`.

To test it, a developer has to boot an ApplicationContext, use reflection to assign fields, or rely on mock injection tools. These approaches can work, but they make the conditions for constructing the service less visible.

With constructor injection:

~~~java
@Service
public class RegistrationService {

    private final UserRepository repository;
    private final PasswordHasher hasher;

    public RegistrationService(
            UserRepository repository,
            PasswordHasher hasher) {
        this.repository = repository;
        this.hasher = hasher;
    }
}
~~~

A test can instantiate the service directly:

~~~java
UserRepository repository = mock(UserRepository.class);
PasswordHasher hasher = mock(PasswordHasher.class);

RegistrationService service =
        new RegistrationService(repository, hasher);
~~~

The service's dependencies appear in the constructor and can be replaced with test doubles. Adding a new dependency to the constructor forces call sites that instantiate the service to update, making design changes visible instead of silently leaving a dependency unconfigured.

Constructor injection also allows using `final` fields, reducing the chance of unexpectedly mutating dependencies after the object is created.

### Is @Autowired needed on the constructor?

For a Spring bean with a **single constructor**, Spring can use that constructor to inject dependencies without needing `@Autowired`. Therefore, a typical service can use plain Java constructor injection:

~~~java
@Service
public class BillingService {

    private final PaymentGateway gateway;

    public BillingService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

A unit test creates `BillingService` with `new`. When running the real application, Spring creates the bean and supplies `PaymentGateway`.

Two different paths for object creation, yet **business logic uses the exact same class**.

## 3. Running example: user registration service

We use the following illustrative structure:

~~~text
src/
├── main/java/com/example/registration/
│   ├── RegistrationService.java
│   ├── RegisterUserCommand.java
│   ├── RegisteredUser.java
│   ├── UserRepository.java
│   ├── PasswordHasher.java
│   └── DuplicateEmailException.java
└── test/java/com/example/registration/
    └── RegistrationServiceTest.java
~~~

All classes belong to the `com.example.registration` package. This design separates **business decision-making** from concrete storage and hashing mechanisms.

### Command and model

~~~java
package com.example.registration;

public record RegisterUserCommand(
        String email,
        String password
) {
}
~~~

~~~java
package com.example.registration;

import java.time.Instant;

public record RegisteredUser(
        String email,
        String passwordHash,
        Instant createdAt
) {
}
~~~

`RegisterUserCommand` describes the input, while `RegisteredUser` holds the processed data before persistence. Using `record` creates immutable value objects with clear `equals()` and accessors.

### Dependency interfaces

~~~java
package com.example.registration;

public interface UserRepository {

    boolean existsByEmail(String email);

    RegisteredUser save(RegisteredUser user);
}
~~~

~~~java
package com.example.registration;

public interface PasswordHasher {

    String hash(String rawPassword);
}
~~~

`UserRepository` describes the **data access capability the service needs**, without forcing unit tests to use a real database. `PasswordHasher` describes the capability to convert a password into a hash, without forcing tests to run a specific hashing algorithm.

A real application may have a JPA adapter for the repository and a cryptographic adapter for hashing; those implementations are tested separately within their appropriate scopes.

### Business exception

~~~java
package com.example.registration;

public class DuplicateEmailException extends RuntimeException {

    public DuplicateEmailException(String email) {
        super("Email already registered: " + email);
    }
}
~~~

The exception helps callers distinguish a registration rejection due to a duplicate email from persistence errors or invalid input errors.

In a real application, sensitive information should not be placed into logs or exceptions indiscriminately; the example uses `example.test` addresses for illustration.

## 4. Service code designed for testability

~~~java
package com.example.registration;

import java.time.Clock;
import java.time.Instant;
import java.util.Locale;
import java.util.Objects;

import org.springframework.stereotype.Service;

@Service
public class RegistrationService {

    private final UserRepository repository;
    private final PasswordHasher hasher;
    private final Clock clock;

    public RegistrationService(
            UserRepository repository,
            PasswordHasher hasher,
            Clock clock) {

        this.repository = Objects.requireNonNull(
                repository, "repository"
        );
        this.hasher = Objects.requireNonNull(
                hasher, "hasher"
        );
        this.clock = Objects.requireNonNull(
                clock, "clock"
        );
    }

    public RegisteredUser register(RegisterUserCommand command) {
        Objects.requireNonNull(command, "command");

        if (command.email() == null || command.email().isBlank()) {
            throw new IllegalArgumentException("email is required");
        }

        if (command.password() == null
                || command.password().isBlank()) {
            throw new IllegalArgumentException("password is required");
        }

        String email = command.email()
                .trim()
                .toLowerCase(Locale.ROOT);

        if (repository.existsByEmail(email)) {
            throw new DuplicateEmailException(email);
        }

        String passwordHash = hasher.hash(command.password());

        RegisteredUser candidate = new RegisteredUser(
                email,
                passwordHash,
                Instant.now(clock)
        );

        return repository.save(candidate);
    }
}
~~~

The service only knows the contracts it needs:

- `UserRepository` to check for duplicates and save.
- `PasswordHasher` to turn a raw password into a hash.
- `Clock` to obtain the current time.

There is no `new JdbcTemplate(...)`, `DriverManager.getConnection(...)`, or direct HTTP call inside the service. There is no manual lookup of dependencies from `ApplicationContext`.

`Clock` is a particularly useful dependency. If the service calls `Instant.now()` directly, tests have to compare timestamps with a tolerance or depend on execution timing. By injecting `Clock`, unit tests use a fixed point in time and can assert exact values.

### Configuring Clock in the real application

Unit tests can pass `Clock.fixed(...)` directly. For Spring to create the `RegistrationService` bean in the application, a corresponding `Clock` bean is needed:

~~~java
package com.example.registration;

import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class TimeConfiguration {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

In production, Spring injects `Clock.systemUTC()`. In unit tests, we provide a fixed clock. This is an example of **the same service with different dependency implementations depending on the test environment**.

## 5. Setting up JUnit Jupiter and Mockito

Spring Boot projects typically use the test starter:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

With Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

The test starter provides standard tools in the Spring Boot testing ecosystem, including JUnit Jupiter, Mockito, and assertion libraries aligned with managed dependency versions.

If a project does not use the Spring Boot test starter, JUnit Jupiter, Mockito Core, and `mockito-junit-jupiter` can be declared individually with compatible versions. This lesson assumes the project already includes JUnit Jupiter and the Mockito Extension.

Key annotations and APIs:

| Annotation / API | Purpose |
|---|---|
| `@Test` | Marks a test method |
| `@BeforeEach` | Prepares fixtures before each test |
| `@ExtendWith(MockitoExtension.class)` | Connects Mockito with the JUnit Jupiter lifecycle |
| `@Mock` | Creates a test double with Mockito |
| `when(...).thenReturn(...)` | Configures mock return values |
| `verify(...)` | Verifies that an interaction occurred |
| `assertEquals(...)`, `assertThrows(...)` | Checks results and exceptions |
| `ArgumentCaptor` | Captures arguments passed to a mock |

There is no need to place `@SpringBootTest` on this unit test class. `MockitoExtension` does not start Spring; it only helps create and manage Mockito mocks during tests.

## 6. Creating a test fixture via constructor

A basic fixture:

~~~java
package com.example.registration;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class RegistrationServiceTest {

    @Mock
    UserRepository repository;

    @Mock
    PasswordHasher hasher;

    private RegistrationService service;

    @BeforeEach
    void setUp() {
        Clock fixedClock = Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                ZoneOffset.UTC
        );

        service = new RegistrationService(
                repository,
                hasher,
                fixedClock
        );
    }
}
~~~

Each test receives a fresh set of mocks per the Mockito Extension lifecycle and recreates the SUT in `@BeforeEach`. Tests do not share mutable service state across cases.

Constructing the SUT explicitly via its constructor illustrates the principle clearly:

~~~text
JUnit / Mockito
       |
       +--> mock UserRepository
       +--> mock PasswordHasher
       +--> fixed Clock
                 |
                 v
new RegistrationService(...)
                 |
                 v
       Execute real method
                 |
                 v
      Assertions and verify
~~~

`Clock` does not need to be mocked. A real object with deterministic behavior like `Clock.fixed` is usually easier to understand and more reliable than mocking a pure Java API just to return a timestamp.

## 7. Unit test for the successful registration branch

The successful registration test needs to prove that the service:

1. Normalizes the email.
2. Checks for duplicate email with the repository.
3. Calls the hasher with the raw password.
4. Saves an object containing the hash and fixed timestamp.
5. Returns the result provided by the repository.

Example:

~~~java
@Test
void registersUserWhenEmailIsAvailable() {
    // Arrange
    when(repository.existsByEmail("linh@example.test"))
            .thenReturn(false);

    when(hasher.hash("valid-password"))
            .thenReturn("hash-123");

    when(repository.save(any(RegisteredUser.class)))
            .thenAnswer(invocation -> invocation.getArgument(0));

    // Act
    RegisteredUser result = service.register(
            new RegisterUserCommand(
                    "  LINH@Example.Test ",
                    "valid-password"
            )
    );

    // Assert: returned state
    assertEquals("linh@example.test", result.email());
    assertEquals("hash-123", result.passwordHash());
    assertEquals(
            Instant.parse("2026-01-01T00:00:00Z"),
            result.createdAt()
    );

    // Assert: dependency interactions
    verify(repository).existsByEmail("linh@example.test");
    verify(hasher).hash("valid-password");

    ArgumentCaptor<RegisteredUser> captor =
            ArgumentCaptor.forClass(RegisteredUser.class);

    verify(repository).save(captor.capture());

    RegisteredUser saved = captor.getValue();
    assertEquals("linh@example.test", saved.email());
    assertEquals("hash-123", saved.passwordHash());
    assertEquals(
            Instant.parse("2026-01-01T00:00:00Z"),
            saved.createdAt()
    );

    verifyNoMoreInteractions(repository, hasher);
}
~~~

Static imports used in the test class example:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoMoreInteractions;
import static org.mockito.Mockito.when;

import org.mockito.ArgumentCaptor;
import org.junit.jupiter.api.Test;
~~~

### Why use thenAnswer for save?

`UserRepository.save(...)` has a contract that returns a `RegisteredUser`. In this example, the mock is configured to return the exact object passed in by the service:

~~~java
when(repository.save(any(RegisteredUser.class)))
        .thenAnswer(invocation -> invocation.getArgument(0));
~~~

Because of this, the service does not need to know about Mockito; it simply works with the repository interface. This is a straightforward simulation and does not prove that real persistence works.

In another test, you might want to simulate the repository returning an object with a database-assigned ID. In that case, declare a specific result object instead of having every `save` return its argument as-is.

### When is ArgumentCaptor needed?

`ArgumentCaptor` is useful when you need to inspect **the data a service sends to a collaborator**. In this example, we want to be sure the raw password is not passed to the repository and that the registration timestamp is accurate.

If you only need to confirm a simple call, you can use:

~~~java
verify(repository).existsByEmail("linh@example.test");
~~~

You do not need a captor for every parameter; use the least complex tool sufficient to prove the important behavior.

## 8. Unit test for duplicate email

When the repository reports that the email already exists, the service must throw an exception and neither call the hasher nor save:

~~~java
@Test
void rejectsDuplicateEmailWithoutHashingOrSaving() {
    // Arrange
    when(repository.existsByEmail("linh@example.test"))
            .thenReturn(true);

    // Act
    DuplicateEmailException error = assertThrows(
            DuplicateEmailException.class,
            () -> service.register(
                    new RegisterUserCommand(
                            "LINH@example.test",
                            "valid-password"
                    )
            )
    );

    // Assert
    assertTrue(error.getMessage().contains("linh@example.test"));

    verify(repository).existsByEmail("linh@example.test");
    verify(repository, never()).save(any(RegisteredUser.class));
    verifyNoInteractions(hasher);
}
~~~

Additional static imports:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verifyNoInteractions;
~~~

This test verifies both **the outcome** and **disallowed side effects**. If it only asserted the exception, the service could accidentally hash or save data before detecting the duplicate email without the test catching it.

For business logic that requires avoiding side effects on failure paths, verifying negative interactions is a meaningful part of the service contract.

## 9. Unit test for invalid input

Input validation checks should happen before calling the repository or hasher. Parameterized tests can be used to avoid repeating very similar cases.

~~~java
@ParameterizedTest
@NullSource
@ValueSource(strings = {"", "   "})
void rejectsMissingOrBlankEmail(String email) {
    IllegalArgumentException error = assertThrows(
            IllegalArgumentException.class,
            () -> service.register(
                    new RegisterUserCommand(email, "valid-password")
            )
    );

    assertEquals("email is required", error.getMessage());
    verifyNoInteractions(repository, hasher);
}
~~~

Corresponding imports:

~~~java
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullSource;
import org.junit.jupiter.params.provider.ValueSource;
~~~

If the password is invalid:

~~~java
@Test
void rejectsBlankPasswordBeforeAccessingDependencies() {
    IllegalArgumentException error = assertThrows(
            IllegalArgumentException.class,
            () -> service.register(
                    new RegisterUserCommand(
                            "linh@example.test",
                            " "
                    )
            )
    );

    assertEquals("password is required", error.getMessage());
    verifyNoInteractions(repository, hasher);
}
~~~

For an entirely `null` command:

~~~java
@Test
void rejectsNullCommand() {
    assertThrows(
            NullPointerException.class,
            () -> service.register(null)
    );

    verifyNoInteractions(repository, hasher);
}
~~~

In this example, `Objects.requireNonNull(command, "command")` intentionally produces a `NullPointerException`. A project may choose a different exception or validate using Jakarta Validation at the API layer; unit tests should reflect the service's agreed-upon contract.

### Do not test multiple unrelated behaviors in one test

A test should have a clear reason to fail. Do not test duplicate email, blank password, and repository failure in the same method with dozens of calls.

Naming a test like `rejectsDuplicateEmailWithoutHashingOrSaving` helps describe both the scenario and the expected outcome.

## 10. When a dependency throws an exception

A service might intentionally not catch exceptions from the repository. In that case, errors propagate to the caller by design. A unit test can document this behavior:

~~~java
@Test
void propagatesRepositoryFailure() {
    when(repository.existsByEmail("linh@example.test"))
            .thenReturn(false);

    when(hasher.hash("valid-password"))
            .thenReturn("hash-123");

    when(repository.save(any(RegisteredUser.class)))
            .thenThrow(new IllegalStateException("storage unavailable"));

    IllegalStateException error = assertThrows(
            IllegalStateException.class,
            () -> service.register(
                    new RegisterUserCommand(
                            "linh@example.test",
                            "valid-password"
                    )
            )
    );

    assertEquals("storage unavailable", error.getMessage());

    verify(repository).existsByEmail("linh@example.test");
    verify(hasher).hash("valid-password");
    verify(repository).save(any(RegisteredUser.class));
}
~~~

This is not a database connection test. It only verifies how the service behaves when a collaborator reports an error.

If business requirements dictate translating infrastructure exceptions into domain exceptions, the test should assert the translated exception type. Do not add catch/retry behavior just to increase branch coverage in tests.

## 11. Arrange – Act – Assert makes tests readable

Each unit test can be divided into three parts:

**Arrange:** prepare inputs, test doubles, return values, and fixed time.

**Act:** invoke a single primary behavior of the SUT.

**Assert:** verify the returned value or exception; when needed, verify dependency interactions.

Condensed example:

~~~java
@Test
void rejectsDuplicateEmail() {
    // Arrange
    when(repository.existsByEmail("taken@example.test"))
            .thenReturn(true);

    // Act
    Executable action = () -> service.register(
            new RegisterUserCommand(
                    "taken@example.test",
                    "valid-password"
            )
    );

    // Assert
    assertThrows(DuplicateEmailException.class, action);
    verifyNoInteractions(hasher);
}
~~~

`Executable` in this example is `org.junit.jupiter.api.function.Executable`.

Tests should be independent of execution order: do not use one test to set up state for the next test. Mockito Extension and fixtures recreated in `@BeforeEach` help limit shared state.

## 12. @Mock, @InjectMocks, and manual SUT construction

Mockito provides `@InjectMocks` to attempt injecting mocks into the object under test:

~~~java
@ExtendWith(MockitoExtension.class)
class ExampleTest {

    @Mock
    UserRepository repository;

    @Mock
    PasswordHasher hasher;

    @InjectMocks
    SomeService service;
}
~~~

This can be convenient for simple constructors. However, it **does not replace Spring dependency injection** and does not guarantee all required collaborators can be constructed.

In a service that also has an unmocked `Clock`, using `@InjectMocks` can make it harder to notice which dependency is missing or assigned `null`. Therefore, in this lesson, writing:

~~~java
service = new RegistrationService(
        repository,
        hasher,
        Clock.fixed(fixedInstant, ZoneOffset.UTC)
);
~~~

is clearer:

- Readers see all dependencies.
- The test explicitly chooses the implementation for each dependency.
- It does not rely on Mockito's injection inference mechanism.
- When the constructor changes, the compiler immediately flags test sites that need updating.

This is one of the key strengths of constructor injection: **no container and no magic injection needed in tests**.

## 13. Mocks and fakes: choosing the right test double

Not every dependency should be mocked.

| Test double | Idea | Suitable when |
|---|---|---|
| Mock | Configure outputs and verify interactions | Checking calls to a repository, gateway, or notifier |
| Stub | Return fixed data for calls | Only needing to control dependency outputs |
| Fake | Lightweight implementation with real working behavior | Simulating an in-memory store or simple algorithm |
| Spy | Wraps a real object and can observe/override some calls | Specialized needs, requiring caution about side effects |

Example of a fake repository keeping users in memory:

~~~java
import java.util.HashMap;
import java.util.Map;

final class InMemoryUserRepository implements UserRepository {

    private final Map<String, RegisteredUser> users =
            new HashMap<>();

    @Override
    public boolean existsByEmail(String email) {
        return users.containsKey(email);
    }

    @Override
    public RegisteredUser save(RegisteredUser user) {
        users.put(user.email(), user);
        return user;
    }

    RegisteredUser get(String email) {
        return users.get(email);
    }
}
~~~

You can pass this fake along with a simple fake hasher into the service and assert the resulting state after invocation. This approach works well if the fake's read/write behavior is small and easy to understand.

Keep in mind that a fake is extra code to maintain. If a custom fake behaves differently from the real repository, unit tests can remain green even when database integration fails. A fake does not replace testing the persistence adapter.

### Why not mock every value object?

`RegisterUserCommand`, `RegisteredUser`, `Instant`, and `Clock.fixed(...)` are all trivial to construct directly. Mocking them ties tests to accessor calls or unnecessary stubbing.

A pragmatic rule: **mock collaborators at system boundaries; use real objects for data and pure computations**.

## 14. State-based or interaction-based verification?

There are two common styles of assertions.

**State-based testing** observes the output:

~~~java
assertEquals("linh@example.test", result.email());
assertEquals("hash-123", result.passwordHash());
~~~

**Interaction-based testing** verifies calls to collaborators:

~~~java
verify(repository).existsByEmail("linh@example.test");
verify(hasher).hash("valid-password");
verify(repository).save(any(RegisteredUser.class));
~~~

Both are useful, but avoid verifying every internal call that is not part of the business contract. The more tightly a test is coupled to implementation details, the more brittle it becomes during refactoring that leaves user-observable behavior unchanged.

For example, if the service is refactored from `String.trim().toLowerCase(...)` to a dedicated helper while producing the same normalized email, unit tests should not break just because of the helper name.

Conversely, checking that the service **does not save a user when the email is duplicate** is a meaningful interaction, because it represents an important business rule and side effect.

### Avoid indiscriminate verifyNoMoreInteractions

`verifyNoMoreInteractions(...)` helps catch unexpected calls, but it can also tightly couple tests to implementation details.

Use it when the requirement genuinely states "no other interactions may occur" or when strictly guarding side effects. Do not use it mechanically in every test just to add more assertions.

## 15. Mockito stubbing: when is it needed and when not?

With Mockito, an unstubbed mock generally returns default values:

- `boolean` is typically `false`.
- Reference types are typically `null` or an appropriate empty value per API.
- Collections/optionals may have specific defaults depending on type and version.

Do not rely heavily on defaults when that value is a business precondition. For instance, in a success test, explicitly write:

~~~java
when(repository.existsByEmail("linh@example.test"))
        .thenReturn(false);
~~~

This makes the condition that the email does not exist clear.

For validation tests that do not touch dependencies, do not stub the repository or hasher. Mockito Extension commonly flags unnecessary stubbing; trying to stub every method in `@BeforeEach` can create unused stubbings for tests taking other branches.

### Do not arbitrarily mix matchers and literal values

When a mock method has multiple parameters, if you use a matcher for one parameter, you should use matchers for the remaining parameters in the same stubbing/verify call per Mockito's rules.

Example:

~~~java
verify(gateway).send(
        eq("welcome"),
        any(String.class)
);
~~~

Do not mix `eq(...)` or `any(...)` with an unwrapped literal argument in the same invocation.

### Stubbing does not prove real side effects

The statement:

~~~java
when(repository.save(any(RegisteredUser.class)))
        .thenReturn(savedUser);
~~~

does not write data to a database. It only instructs the mock to return `savedUser`. Unit tests should verify that the service **decides to call save properly**, not claim to have verified transactions or persistence.

## 16. Time, randomness, and external data: adding intentional seams

A reliable unit test needs deterministic inputs. Common sources of nondeterminism include:

- System time: `Instant.now()`, `LocalDate.now()`.
- Random ID or token generation: `UUID.randomUUID()`.
- Environment variables, global configuration, or system properties.
- HTTP, database, filesystem.
- Threads or asynchronous executors.

Constructor injection lets you replace these sources with controllable interfaces or concrete objects.

Example with time:

~~~java
Clock clock = Clock.fixed(
        Instant.parse("2026-01-01T00:00:00Z"),
        ZoneOffset.UTC
);
~~~

If business logic generates a registration ID, you can inject an `IdGenerator`:

~~~java
public interface IdGenerator {
    String nextId();
}
~~~

Then a test provides a generator returning a fixed ID. There is no need to alter `UUID.randomUUID()` with static mocking tools when the ID source can be modeled as a service dependency.

This does not mean every pure calculation must be abstracted into an interface. The goal is to introduce seams where logic depends on **the outside world or nondeterministic sources**, not to multiply classes unnecessarily.

## 17. A unit test does not validate the entire Spring Boot runtime

In this lesson, the test calls:

~~~java
RegistrationService service =
        new RegistrationService(repository, hasher, fixedClock);
~~~

This is a **pure unit test**. The `@Service` annotation on the class does not participate in constructing the SUT. Because there is no ApplicationContext, the following mechanisms are **not tested**:

- Component scanning and bean registration.
- Autowiring multiple implementations.
- `@Transactional` proxies and real commit/rollback.
- `@Async` and executor advice.
- `@Cacheable` and cache interceptors.
- JPA mapping, queries, and database constraints.
- HTTP mapping, serialization, authentication, and authorization.
- `@ConfigurationProperties` binding or profile activation.

For example, if a method is annotated with `@Transactional`, a unit test instantiating the service with `new` **does not prove** that the transaction interceptor will run when the real application invokes it through a Spring proxy.

To verify those mechanisms, a different kind of test is needed.

| Goal | Typically suitable test type |
|---|---|
| Business branches inside a service | Unit test with JUnit + Mockito/fake |
| JPA mapping and repository queries | Persistence integration/slice test, e.g. `@DataJpaTest` |
| MVC routing, request validation, JSON, and controller advice | Web slice test, e.g. `@WebMvcTest` |
| Bean wiring, AOP, transactions, or real multi-component flows | Spring context/integration test |
| Contracts with databases or external systems | Integration/contract test with appropriate infrastructure |

Spring Boot provides `@SpringBootTest` for integration tests requiring a broad context, but it should not be used just because the class under test is annotated with `@Service`. When testing pure logic, startup time and environment dependencies rarely provide proportional value.

## 18. When is an additional integration test needed?

A unit test can prove that `RegistrationService` calls `repository.save(...)` once with the expected data. However, it does not prove:

- The database has a unique constraint on email.
- The transaction rolls back when the repository throws an error.
- The email is stored with the right column type and encoding in the database.
- The production `PasswordHasher` implementation actually produces a secure hash.
- Spring can inject all required `UserRepository`, `PasswordHasher`, and `Clock` beans.

These concerns should be verified at their respective layers.

For example, consider a race condition risk: two concurrent requests might both receive `existsByEmail(...) == false` before both calling `save(...)`. A service unit test expresses the intended rule, but **does not replace a database unique constraint** and constraint-violation handling.

Similarly, a unit test using a mock hasher does not evaluate cryptographic strength. Test the hashing adapter separately and choose an implementation meeting the system's security standards.

Designing tests across multiple layers helps pinpoint failures at the right boundary instead of forcing a unit test to simulate databases, HTTP, transactions, and thread scheduling.

## 19. Common test design mistakes

### Using @SpringBootTest for every service test

This makes tests slower, increases configuration coupling, and can cause failures due to unrelated beans. If a service has a clear constructor, simply instantiate the SUT directly and replace collaborators with mocks or fakes.

### Only verifying calls without asserting results

Checking `verify(repository).save(...)` may not be enough. If a method is supposed to return the saved object, assert the return value and key data rules.

### Only asserting results while forgetting forbidden side effects

In the duplicate email branch, the service must not hash or save data. When avoiding a side effect is part of the business rule, verify that unwanted interactions did not occur.

### Mocking the service under test itself

Do not write:

~~~java
RegistrationService service = mock(RegistrationService.class);
when(service.register(any())).thenReturn(expected);
~~~

and conclude that `RegistrationService` logic has been tested. At that point, the test only confirms behavior defined by Mockito itself.

**The SUT must be a real object**, while its dependencies are replaced with test doubles as needed.

### Using live wall-clock time

For example:

~~~java
assertEquals(Instant.now(), result.createdAt());
~~~

is almost guaranteed to be flaky because the two calls happen at different instants. Injecting `Clock` and using `Clock.fixed(...)` is much clearer.

### Allowing mocks to be reused across tests

When mock state or stubbing is accidentally shared, tests can become order-dependent. Use independent fixtures per test and avoid unnecessary mutable global state.

### Stubbing everything in @BeforeEach

An invalid-input test never calls the repository, so stubbing the repository in a shared fixture adds noise and may trigger unused stubbing warnings in Mockito. Keep stubbing close to each scenario being tested.

### Relying on exceptions from a concrete dependency implementation in every test

If the service only cares about a repository contract, do not tie every unit test to exceptions or behavior of a specific JDBC driver. SQL or mapping scenarios belong in dedicated persistence adapter tests.

### Relying on @InjectMocks to hide a complex constructor

If a service has too many dependencies, is hard to set up in tests, and has unclear responsibilities, that may be a sign the service is doing too much. Rather than relying more heavily on automatic injection, revisit its responsibility boundaries.

## 20. Testing after refactoring a service

A well-designed unit test suite remains resilient when implementation details are refactored without changing the contract.

Suppose previously the service called `repository.existsByEmail` and then `repository.save`. Later, the business logic switches to a specialized repository method for an atomic insert. If the business behavior remains "reject duplicate email, save valid email," outcome assertions should continue to hold.

Interaction verification tests may need updating because the repository contract changed. That is normal when the repository interface itself changes.

Conversely, renaming local variables, extracting private helpers, or replacing loops with Streams should not force tests to change if observable outputs and important side effects stay intact.

Useful criteria when designing service unit tests:

- Each test expresses a clear business rule.
- The SUT is created via constructor with explicit dependencies.
- Tests do not depend on ApplicationContext unless Spring behavior is being verified.
- Time, randomness, and infrastructure inputs are controlled.
- Assertions favor observable behavior over private implementation details.
- Meaningful interactions such as "do not save on invalid input" are verified.
- Each test can run independently on developer machines and CI.

## 21. Extended exercises

You can apply the same constructor injection pattern to improve test quality.

**Exercise 1 — Validate minimum password length.** Add a minimum password length rule in the service and write a parameterized test for short strings. Verify no repository/hasher calls occur when validation fails.

**Exercise 2 — Register at another fixed timestamp.** Pass a `Clock.fixed(...)` with a different instant and assert `createdAt` matches exactly. This reinforces avoiding system clock coupling.

**Exercise 3 — Repository returns a different object.** Instead of having `save(...)` return its argument, configure the mock to return a differently constructed `RegisteredUser` per the repository contract and verify the service returns the repository's value.

**Exercise 4 — Add a welcome notification.** Inject a `WelcomeNotifier` via constructor, then write a test verifying that only the success branch sends a notification. Consider practically that notifications should not be sent before the database transaction commits; coordinating around commit requires integration testing or an appropriate outbox/event design.

**Exercise 5 — Try a fake repository.** Write `InMemoryUserRepository` to test storing and reading in unit tests, then add a separate integration test for the real JPA repository.

## 22. Conclusion

A service that is easy to unit test does not require writing test-specific production code. What matters is clear dependency design:

~~~text
Spring Boot production:
ApplicationContext
     |
     +--> real UserRepository
     +--> real PasswordHasher
     +--> Clock.systemUTC()
              |
              v
      RegistrationService


JUnit unit test:
Mockito mocks + Clock.fixed()
              |
              v
new RegistrationService(...)
              |
              v
   Assert result and side effects
~~~

Constructor injection allows **using the exact same service logic in both environments** without invoking the Spring container in unit tests. JUnit expresses expected behavior; Mockito controls collaborators at the boundaries; real objects like `Clock.fixed` keep test results deterministic.

Keep unit tests focused on service logic, and use integration tests for wiring, AOP, databases, HTTP, and real system dependencies. This separation yields a test suite that is fast, clear, and capable of catching failures at the right layer of a Spring Boot application.
