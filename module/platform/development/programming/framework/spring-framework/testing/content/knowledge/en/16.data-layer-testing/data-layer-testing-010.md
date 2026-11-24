# Distinguishing Real Repository Tests from Mock Repository Tests

In Spring applications, repositories are typically where services access data. With Spring Data JPA, you declare an interface such as `BookRepository extends JpaRepository<Book, Long>`; Spring generates an implementation at runtime and connects it to the JPA provider and datasource.

When testing code that uses a repository, there are two common approaches:

- **Testing the real repository**: initialize the Spring Data-generated repository and run it against a test database. This verifies the path from the repository through JPA to the database.
- **Testing with a mock repository**: replace the repository with a test double created by Mockito. This verifies that the service or component calling the repository behaves properly when given predetermined results.

These two approaches answer different questions. A service test with mocks can run very fast, yet it does not prove the repository query is right. Conversely, a real repository test confirms queries work, yet does not necessarily verify business rules inside services.

## 1. What Is a Real Repository in Spring Data JPA?

Suppose a book management application has the following repository:

```java
public interface BookRepository extends JpaRepository<Book, Long> {

    Optional<Book> findByIsbn(String isbn);

    List<Book> findByTitleContainingIgnoreCase(String keyword);
}
```

This is only an interface. When the application starts, Spring Data JPA creates an implementation for this interface. Calls such as `findByIsbn` are parsed by Spring Data from the method name and translated into an appropriate query. If a repository uses `@Query`, the JPA provider must also parse and execute that query.

A real repository test uses the actual implementation created by Spring. The test initializes the persistence context, entity mappings, datasource, and test database. When calling `repository.findByIsbn(...)`, the invocation travels through Spring Data and JPA down to the database.

Depending on configuration, the test database can be in-memory H2 or a real database instance launched for tests, such as PostgreSQL via Testcontainers. Thus, "real repository" means using the real implementation and persistence flow; it does not automatically mean using the exact production DBMS.

### What This Testing Approach Can Verify

- Whether Spring Data creates and initializes the repository properly.
- Whether query method names are interpreted as intended, such as `findByTitleContainingIgnoreCase`.
- Whether JPQL or native SQL in `@Query` is valid and returns expected results.
- Whether entities map properly to tables, columns, primary keys, relationships, and data types.
- Whether save, update, delete, pagination, and sorting operations work as expected.
- Whether database constraints such as `NOT NULL`, `UNIQUE`, and foreign keys are enforced as expected.

These are behaviors a mock cannot verify, because a mock executes no SQL and involves no JPA provider or database executing queries.

## 2. Writing Real Repository Tests with `@DataJpaTest`

With Spring Boot, `@DataJpaTest` is usually the right choice for testing the JPA layer. This annotation loads configuration required for entities and Spring Data JPA repositories rather than booting the entire application like `@SpringBootTest`.

Example entity:

```java
@Entity
@Table(name = "books")
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String isbn;

    @Column(nullable = false)
    private String title;

    protected Book() {
    }

    public Book(String isbn, String title) {
        this.isbn = isbn;
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getIsbn() {
        return isbn;
    }

    public String getTitle() {
        return title;
    }
}
```

Repository:

```java
public interface BookRepository extends JpaRepository<Book, Long> {

    List<Book> findByTitleContainingIgnoreCase(String keyword);
}
```

Test:

```java
@DataJpaTest
class BookRepositoryTest {

    @Autowired
    private BookRepository bookRepository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void findsBooksByTitleWithoutConsideringCase() {
        entityManager.persist(new Book("ISBN-001", "Spring Framework Guide"));
        entityManager.persist(new Book("ISBN-002", "Learning Java"));
        entityManager.flush();
        entityManager.clear();

        List<Book> result = bookRepository.findByTitleContainingIgnoreCase("SPRING");

        assertThat(result)
                .extracting(Book::getIsbn)
                .containsExactly("ISBN-001");
    }
}
```

In this example:

1. `@DataJpaTest` instructs Spring to initialize the JPA configuration for tests.
2. `@Autowired` obtains the real repository from the Spring context. This is not a mock.
3. `TestEntityManager` creates test data using JPA.
4. `flush()` pushes pending changes down to the database so the database executes them.
5. `clear()` evicts entities held in the current persistence context. This prevents the test from inadvertently reading back objects still sitting in memory.
6. The repository call executes the query; AssertJ asserts the returned results.

By default, `@DataJpaTest` tests run inside a transaction that usually rolls back after each test. This ensures one test's data does not linger to affect the next test. If a test needs to verify commit behavior or multiple independent transactions, design the test's transaction handling to fit the behavior under test.

### Configuring the Database for Tests

For a Spring Boot project using Gradle, a simple configuration may look like:

```groovy
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("com.h2database:h2")
}
```

When H2 is on the test classpath, `@DataJpaTest` typically auto-configures an embedded database for tests. This is fast and convenient for common queries, mappings, and JPA operations.

However, H2 is not PostgreSQL, MySQL, or Oracle. SQL syntax, data types, collations, JSON handling, sequences, locks, database functions, and certain transaction behaviors can differ. A query passing on H2 can still fail when run against the production database.

If the application relies on behavior specific to the production database, run repository tests with that exact DBMS. Testcontainers can launch the database used in tests. Example PostgreSQL setup:

```java
@Testcontainers
@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
class BookRepositoryPostgresTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void configureDatasource(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    // Put repository tests here.
}
```

The test needs Testcontainers libraries for JUnit Jupiter and PostgreSQL, plus the PostgreSQL JDBC driver at test runtime. `@AutoConfigureTestDatabase(replace = Replace.NONE)` tells Spring to keep the configured datasource rather than replacing it with an embedded database. `@DynamicPropertySource` supplies connection details from the container to Spring.

Testcontainers is not needed for every test. H2 suits many routine repository tests; a container database is valuable when you need to confirm compatibility with the production database or test its engine-specific features.

## 3. What Is a Mock Repository?

A mock repository is a test double replacing `BookRepository` in a test. Mockito creates this object; the test specifies which calls return which values.

Example service using a repository:

```java
public class BookService {

    private final BookRepository bookRepository;

    public BookService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    public Book getRequiredBook(Long id) {
        return bookRepository.findById(id)
                .orElseThrow(() -> new BookNotFoundException(id));
    }
}
```

We can test the service's processing rules without booting Spring or a database:

```java
@ExtendWith(MockitoExtension.class)
class BookServiceTest {

    @Mock
    private BookRepository bookRepository;

    @InjectMocks
    private BookService bookService;

    @Test
    void returnsBookWhenItExists() {
        Book book = new Book("ISBN-001", "Spring Framework Guide");
        when(bookRepository.findById(10L)).thenReturn(Optional.of(book));

        Book result = bookService.getRequiredBook(10L);

        assertThat(result.getIsbn()).isEqualTo("ISBN-001");
        verify(bookRepository).findById(10L);
    }

    @Test
    void throwsExceptionWhenBookDoesNotExist() {
        when(bookRepository.findById(99L)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> bookService.getRequiredBook(99L))
                .isInstanceOf(BookNotFoundException.class);
    }
}
```

Here, `@Mock` creates the mock repository and `@InjectMocks` injects that mock into the service. `when(...).thenReturn(...)` stubs the return value. When the service calls `findById`, Mockito returns the exact configured result; no query is sent to any database.

This test can verify:

- The service returns the expected data when the repository finds a record.
- The service properly handles the case when the repository returns `Optional.empty()`.
- The service transforms data, applies business rules, or throws exceptions appropriately based on the returned outcome.
- The service calls the repository with the required arguments, when that interaction is a key part of the behavior to assert.

This test does not verify that `findById` or a custom query method executes properly on a database. It only verifies the service reacts properly to the results provided by the mock.

## 4. Comparing the Two Approaches

| Criterion | Real Repository | Mock Repository |
| --- | --- | --- |
| Subject under test | Spring Data repository and persistence flow | Service or component depending on the repository |
| Repository used | Implementation generated by Spring | Test double created by Mockito |
| Database | Has a test database, e.g., H2 or container database | No database needed |
| SQL/JPQL statements | Executed and verifiable through results | Not executed |
| Entity mappings | Can be verified | Not verified |
| Business rules in service | Verified only if the test brings the service into scope | Can be verified directly |
| Speed and startup scope | Usually slower than unit tests; needs JPA config | Usually fast, minimal environment dependencies |
| Bugs caught | Wrong queries, mappings, persistence config, database constraints | Wrong service branches, transformations, or decisions |

For example, if `findByTitleContainingIgnoreCase` misspells a property name or `@Query` contains invalid JPQL, a repository test catches the problem at initialization or query execution. A service test with mocks would still pass, because Mockito simply returns the list configured by the test.

Conversely, if a service is supposed to throw `BookNotFoundException` when a book is missing yet returns `null` instead, a service test with mocks catches that bug without needing a database.

## 5. Common Misconceptions

### A Mock Repository Is Not a Repository Test

If a test creates `@Mock BookRepository` and calls `bookRepository.findByTitleContainingIgnoreCase(...)`, the result comes solely from `when(...).thenReturn(...)` stubbing. That test never runs Spring Data's implementation. Hence, it cannot prove method names, JPQL, native SQL, or mappings are right.

Place mocks at the boundary between service and repository when the goal is testing the service. When the goal is testing queries or persistence, inject the real repository in a JPA test.

### H2 Is Not Equivalent to the Production Database

A test using a real repository with H2 is still a repository integration test: Spring Data, the JPA provider, and a database all participate. Yet its results only prove behavior on H2. For queries using PostgreSQL-specific functions, specialized data types, or database-dependent locking behavior, run tests against PostgreSQL.

### `@DataJpaTest` and `@SpringBootTest` Have Different Scopes

`@DataJpaTest` focuses on the persistence layer and typically starts faster. `@SpringBootTest` loads a broader application context, suitable when testing how multiple application components work together. Do not use `@SpringBootTest` for every repository query when a JPA slice suffices to verify behavior.

### Fakes, Stubs, and Mocks Are Not Identical

In conversation, these terms are sometimes loosely grouped together as "fake repositories", yet they carry different meanings:

- **Stub** provides canned answers to calls, such as `findById(10L)` returning a `Book`.
- **Mock** can also provide answers while recording calls so tests can verify interactions, such as confirming the repository was called once with the expected ID.
- **Fake** is a simplified implementation with working behavior, such as a repository storing data in an in-memory `Map`.

A fake can be useful in certain unit tests, yet it still does not test Spring Data JPA or a database. A fake's data and rules can diverge from the real implementation.

## 6. Choosing the Testing Approach Based on the Question

Start by identifying the component and behavior that need confirmation:

| Question | Appropriate Testing Approach |
| --- | --- |
| Does `findByEmail` find the right record in the database? | Real repository |
| Is the JPQL in `@Query` valid and returning the right results? | Real repository |
| Does the `@OneToMany` relationship persist and load properly? | Real repository |
| Does the unique constraint prevent duplicate data? | Real repository |
| Does the service throw an exception when the repository finds no record? | Mock repository in a service test |
| Does the service calculate fees or transition state properly from repository data? | Mock repository in a service test |
| Do service flow, transactions, and database coordinate properly in the application? | Broader integration test, potentially using `@SpringBootTest` and an appropriate database |

A project usually needs both groups of tests. Repository tests focus on queries, mappings, and persistence behavior. Service unit tests use mocks to test business branches independently of the database. Where risks exist across component boundaries, add integration tests covering that exact flow.

### Recommended Workflow for Repository Tests

1. Identify the query or persistence behavior to test, such as status filtering, pagination, or uniqueness enforcement.
2. Create input data containing both matching and non-matching cases.
3. Use the real repository injected by Spring into the test.
4. Flush data before querying; consider clearing the persistence context when you need to ensure the test reloads from the database.
5. Call the repository method and verify result contents, counts, ordering, or empty cases.
6. If the application uses production-database-specific features, run tests on that exact DBMS.

### Recommended Workflow for Service Tests with Mocks

1. Identify possible return values from the repository and the corresponding business branches.
2. Create a mock for the repository and stub outcomes via `when(...).thenReturn(...)` or `thenThrow(...)` when simulating failures.
3. Invoke the service method.
4. Assert outputs, exceptions, or business state changes.
5. Use `verify(...)` only when the repository interaction itself is meaningful to the behavior under test; avoid verifying unnecessary internal calls.

## 7. Conclusion

Real repository tests answer the question: **do the repository and persistence layer work properly with the database?** Mock repository tests inside service tests answer the question: **does the service handle the results and scenarios returned by the repository properly?**

Use `@DataJpaTest` with real repositories to verify queries, mappings, and database behavior. Use Mockito to replace repositories when testing service logic. Combining both test types along responsibility boundaries catches both query bugs and business-logic bugs while keeping most unit tests fast and easy to maintain.
