# Input Validation and Parameterized Queries Remain the Application's Responsibility

> Scope: data protection in Java 17+ applications using Spring Boot 3.x, Spring Security 6.x, Spring MVC, and JDBC. Focus is on **distinguishing access protection from input validation and query protection**, practicing Bean Validation, JDBC prepared statements, allowlists when SQL structure must vary, and testing strategies to reduce SQL injection risk. Spring Security is an important defense layer, yet it **does not automatically validate every parameter or fix SQL statements that an application builds unsafely**.

## 1. Three Distinct Layers of Control

Suppose there is a customer search API:

```http
GET /api/customers?nameContains=Ali&sort=NAME&limit=20
Authorization: Basic ...
```

Before returning data, the application must resolve three independent questions:

1. **Authentication and authorization — may the caller access the API?** Spring Security checks credentials, creates `Authentication`, and decides whether the caller holds the `READER` role. Unauthenticated callers may be challenged; authenticated callers lacking permission may receive HTTP 403.
2. **Input validation — does the submitted data conform to the API contract?** `limit` must be an integer within the allowed range; `sort` may accept only valid criteria; `nameContains` needs a length limit. These checks are the application's responsibility at the input boundary and in the business layer where needed.
3. **Query safety — can untrusted data alter query syntax?** The SQL query must keep a fixed structure, binding parameters via `PreparedStatement`/`JdbcTemplate` or an equivalent API. If users can choose a sort column, the application maps the choice to a set of SQL keywords **defined in source code**, never concatenating client-supplied strings into SQL.

A request that passes `hasRole("READER")` **can still carry a SQL injection payload or malformed data**. A legitimate user can intentionally send malicious payloads; an application can also receive dirty data from imports, jobs, message queues, or partner services. Never treat "logged in" as a certificate of trust for input contents.

| Mechanism | Goal | Example | Primary owner |
| --- | --- | --- | --- |
| Spring Security authentication | Prove identity | Correct HTTP Basic password | Security filters, `AuthenticationManager`, providers |
| Spring Security authorization | Check permissions | Only `ROLE_READER` can call `GET /api/customers` | `SecurityFilterChain`, authorization policies |
| Bean Validation / request binding | Check input contract | `1 <= limit <= 50`; `nameContains` max 80 chars | Controller/DTO and validation boundary |
| Domain validation | Protect business invariants | Non-negative totals; quantity within quota | Service/domain |
| Parameterized SQL | Prevent input values from becoming SQL code | `WHERE LOWER(name) LIKE LOWER(?)` | Repository/data access |
| Allowlisted SQL identifiers | Constrain non-bindable syntax parts | `NAME -> name ASC`, `CREATED -> created_at DESC` | Repository/query builder |
| Data access control | Return only rows belonging to permitted tenant/owner | `WHERE tenant_id = ?` with trusted tenant | Authorization + repository/data policy |

**Design takeaway:** Security filters decide *who may reach an endpoint*; validation decides *whether input is valid*; parameterization decides *that input enters SQL as data values, not executable commands*. These layers complement rather than replace one another.

## 2. How Does SQL Injection Happen?

SQL injection occurs when untrusted data is **concatenated into SQL syntax**. The flawed example below is a **counter-example**—never use it in real applications:

```java
// Unsafe: user input is concatenated into SQL syntax.
String sql = "SELECT id, name FROM customers WHERE name = '"
        + nameFromRequest + "'";
List<CustomerRow> rows = jdbc.query(sql, rowMapper);
```

If `nameFromRequest` contains quotes and SQL operators, the concatenated text can alter the `WHERE` condition, for example:

```text
' OR '1'='1
```

The vulnerable query becomes:

```sql
SELECT id, name FROM customers WHERE name = '' OR '1'='1'
```

The condition `'1'='1'` is always true; unintended records may be returned. Exact impact depends on database privileges, query shape, dialect, and environment; not every payload succeeds everywhere, yet you must **never construct SQL in a way where input can alter its structure**.

The right approach keeps the SQL fixed and binds values:

```java
String sql = "SELECT id, name FROM customers WHERE name = ?";
List<CustomerRow> rows = jdbc.query(sql, rowMapper, nameFromRequest);
```

This is an **illustrative snippet inside a repository**: `jdbc`, `rowMapper`, and `nameFromRequest` must exist in the calling context. The `?` is a placeholder for a **value**, not text substitution before execution. `JdbcTemplate` uses JDBC parameter binding for the call. Now `' OR '1'='1` is **comparison data**, never becoming a SQL clause.

**Why is "filtering quotes" not enough?** Blacklisting characters like `'`, `;`, or keywords like `SELECT` easily misses encodings, variants, and dialects, while breaking legitimate data like the name `O'Reilly`. Prepared statements are the primary barrier for SQL **data values**. Input validation is still needed for contracts, performance, and business rules, but **must never be treated as a substitute for bind parameters**.

## 3. Input Validation: What to Check and Where?

### 3.1. Data Types, Lengths, Ranges, and Allowed Sets

Examples:

- `limit` is an integer from 1 to 50 to cap rows per search.
- `nameContains` is a string up to 80 characters; apostrophes can be valid parts of names and should not be blindly blocked just because they look like payload fragments.
- `sort` must belong to a predefined set: `NAME` or `CREATED`; actual SQL column names are chosen by the application.
- For a customer-creation API, `name` may need `@NotBlank` and `@Size(max = 120)`; email may use `@NotBlank` and `@Email`. `@Email` only checks format, **never proving the address exists or belongs to the sender**.
- Prices, payment dates, and workflow states also need domain validation in the service; syntactically valid input is not necessarily business-valid.

If a user sends `limit=abc`, integer binding fails before querying. If they send `limit=9999`, Bean Validation must reject it per `@Max(50)`. If they send `sort=PASSWORD`, a value outside the enum fails during binding. These are **invalid request** errors; never throw `AuthenticationException` to report bad data.

### 3.2. Bean Validation on `@ModelAttribute` and `@RequestBody`

Spring Boot 3 uses Jakarta Validation (`jakarta.validation.*`). Add `spring-boot-starter-validation` to include constraints and an implementation.

- For query/form parameters, a `@Valid @ModelAttribute SearchCriteria` bean lets Spring MVC bind and validate the data.
- For JSON request bodies, use `@Valid @RequestBody CreateCustomerRequest` to validate the deserialized object.
- `@NotNull` differs from `@NotBlank`: `@NotNull` only forbids `null`, whereas `@NotBlank` requires non-whitespace content.
- `@Size` checks string/collection length; `@Min`/`@Max` constrain numbers; `@Pattern` expresses string structure when the contract genuinely requires it.
- For nested inputs, place `@Valid` on nested properties so validation cascades.
- Avoid using "anti-SQL-injection regexes" across all text fields. Allow users to enter legitimate content and protect SQL at the query layer.

Illustrative DTO example for POST:

```java
public record CreateCustomerRequest(
        @NotBlank @Size(max = 120) String name,
        @NotBlank @Email String email) {
}
```

This snippet is not part of the runnable GET program in section 5; it illustrates defining a JSON contract. In a real POST endpoint, the controller can accept `@Valid @RequestBody CreateCustomerRequest request`, yet the service must still check business rules like duplicate emails, write permissions, and transactions. Controller validation does not protect other service entry points if domain invariants are left unguarded.

### 3.3. Not Just HTTP Data

Untrusted sources include query strings, path variables, JSON bodies, HTTP headers, imported CSV/Excel files, message queues, legacy databases, webhooks, and partner service responses. The fact that a value is **already stored in the database** does not make it safe when used to build dynamic SQL later (second-order injection).

Apply validation in two layers:

1. **Boundary validation:** DTOs/adapters check format, type, length, and API or transport constraints.
2. **Domain validation:** services/domain enforce mandatory invariants regardless of whether calls arrive from REST, batch jobs, event consumers, or tests.

Validation does not mean automatically "sanitizing every input". Never silently strip valid characters or alter data meaning arbitrarily. Normalization of whitespace, Unicode, and casing must fit business, storage, and search requirements.

## 4. Parameterized Queries: Capabilities and Limits

### 4.1. JDBC, `JdbcTemplate`, and `NamedParameterJdbcTemplate`

With raw JDBC:

```java
String sql = "SELECT id, name FROM customers WHERE id = ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, customerId);
    try (ResultSet rs = ps.executeQuery()) {
        // Read ResultSet; do not concatenate customerId into SQL.
    }
}
```

This snippet assumes `Connection`, `PreparedStatement`, `ResultSet`, and `customerId` are in scope. `PreparedStatement` is key: `setLong(1, customerId)` passes a **bound value** for the first placeholder.

With Spring JDBC:

```java
jdbc.query(
        "SELECT id, name FROM customers WHERE name = ?",
        rowMapper,
        nameFromRequest);
```

With named parameters:

```java
String sql = "SELECT id, name FROM customers WHERE name = :name";
MapSqlParameterSource params =
        new MapSqlParameterSource("name", nameFromRequest);
namedJdbc.query(sql, params, rowMapper);
```

Both Spring snippets above are **repository examples** requiring corresponding variables and imports; `NamedParameterJdbcTemplate` eases maintaining complex queries with multiple named parameters. Whether using positional or named binding, the principle is **application code controls SQL logic while input data is always bound**.

Spring Data JPA follows the same rule:

```java
@Query("select c from CustomerEntity c where c.email = :email")
List<CustomerEntity> findByEmail(@Param("email") String email);
```

This is an illustrative JPA repository signature that runs only inside a project with matching entities/repositories; it is not standalone code. JPQL parameters avoid concatenating `email` into the query string. `EntityManager.createNativeQuery(...)` or manually concatenated query strings can still suffer from SQL injection even when using an ORM.

### 4.2. Never Bind Column Names, Table Names, or `ORDER BY` Keywords with `?`

Placeholders are for **data values**, not SQL syntax:

```sql
-- Does NOT mean "sort by the user-selected column":
SELECT id, name FROM customers ORDER BY ?
```

In many databases, `ORDER BY ?`, even if accepted, evaluates a constant value expression and **does not select a column**. Never write `"ORDER BY " + sortFromRequest`.

Instead, map input to a **fixed SQL fragment owned by the application**:

```java
String orderBy = switch (sortField) {
    case NAME -> "name ASC, id ASC";
    case CREATED -> "created_at DESC, id ASC";
};
String sql = "SELECT id, name, created_at FROM customers ORDER BY "
        + orderBy
        + " LIMIT ?";
```

This is a repository snippet. `sortField` must be a valid enum, never an arbitrary string; `orderBy` can only take one of two literals. Even though string concatenation is used, untrusted data **never enters the SQL structure**. `LIMIT ?` is still bound as a value.

Similarly, when selecting table names, column names, `ASC`/`DESC` direction, operators, or dynamic query parts, use enums, allowlists, or controlled query builders; never think prepared statements can "bind any kind of SQL token".

### 4.3. `LIKE` Still Has Wildcards: `%`, `_`, and Escaping

`LIKE` normally treats `%` as any sequence of characters and `_` as a single character. Parameter binding **prevents SQL syntax modification**, but does not make `%` or `_` literal inside `LIKE`. For instance, if a user searches for names literally containing an underscore, `nameContains=_` should not match "every name with at least one character".

One strategy is specifying an explicit escape character in the SQL:

```sql
WHERE LOWER(name) LIKE LOWER(?) ESCAPE '!'
```

And preparing the pattern:

```java
static String literalContainsPattern(String raw) {
    String escaped = raw.replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_");
    return "%" + escaped + "%";
}
```

Here `!` is the `LIKE` escape character: `!%` represents a literal percent sign, `!_` a literal underscore, and `!!` a literal exclamation mark. `LIKE` escaping handles **search semantics**, while parameter binding handles **SQL injection**. Some dialects differ on `ESCAPE` syntax; the runnable example in section 5 uses H2, which supports this syntax.

### 4.4. `IN` Clauses, Paginated Search, and Multi-Tenant Queries

For a set of IDs, never write `"... IN (" + idListFromClient + ")"`. Use `NamedParameterJdbcTemplate` to bind collections for `IN (:ids)` or generate the exact number of placeholders for a bounded list, handling empty lists properly. Input lists must still have their size capped.

In multi-tenant systems, parameterization **does not restrict which tenant's rows are accessed**. Conceptual example:

```sql
SELECT id, name FROM customers
WHERE tenant_id = ? AND LOWER(name) LIKE LOWER(?)
```

`tenant_id` must come from a verified, system-trusted identity/permission context—never directly from a self-asserted query parameter. Apply least privilege to the database account, bound returned data, and use transactions/locking on writes to preserve consistency.

## 5. Runnable Java 17+ Example: Spring Security + `@Valid` + `JdbcTemplate`

### 5.1. Functionality and Design

The application exposes a single read endpoint:

```http
GET /api/customers?nameContains=Ali&sort=NAME&limit=20
```

- Account `reader`/`reader-pass` with `ROLE_READER` may search customers.
- Account `guest`/`guest-pass` with `ROLE_GUEST` is authenticated but unauthorized: 403.
- Anonymous or invalid credentials: typically 401 with HTTP Basic.
- `limit` is in `1..50`; `nameContains` max length 80; `sort` is only `NAME` or `CREATED`.
- SQL filters names via bound parameters, limit is bound; `ORDER BY` comes from an allowlisted enum.
- Searching strings with quotes, `%`, or `_` never alters query logic. `LIKE` handling treats `%`/`_` as literal characters in the search term.
- Uses in-memory H2 and demo records; the API uses GET only so no CSRF change is needed to test with curl.

### 5.2. Declaring Dependencies

In a Spring Boot 3.x project with the Gradle plugin configured, the `dependencies` block of `build.gradle` needs:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

This is only the **`dependencies` section**, not a full Gradle build script. Maven projects use the corresponding starters. Spring Boot auto-configures an in-memory H2 `DataSource` and `JdbcTemplate` when these dependencies are present.

### 5.3. Complete Java File

Create `src/main/java/demo/DemoApplication.java`:

```java
package demo;

import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Repository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demoData(JdbcTemplate jdbc) {
        return args -> {
            jdbc.execute(
                    "CREATE TABLE customers ("
                    + "id BIGINT PRIMARY KEY, "
                    + "name VARCHAR(120) NOT NULL, "
                    + "created_at TIMESTAMP NOT NULL)");

            jdbc.update(
                    "INSERT INTO customers(id, name, created_at) "
                    + "VALUES (?, ?, ?)",
                    1L, "Alice", Timestamp.valueOf("2025-02-01 10:00:00"));
            jdbc.update(
                    "INSERT INTO customers(id, name, created_at) "
                    + "VALUES (?, ?, ?)",
                    2L, "Bob", Timestamp.valueOf("2025-02-02 10:00:00"));
            jdbc.update(
                    "INSERT INTO customers(id, name, created_at) "
                    + "VALUES (?, ?, ?)",
                    3L, "O'Reilly Books",
                    Timestamp.valueOf("2025-02-03 10:00:00"));
            jdbc.update(
                    "INSERT INTO customers(id, name, created_at) "
                    + "VALUES (?, ?, ?)",
                    4L, "A_100", Timestamp.valueOf("2025-02-04 10:00:00"));
        };
    }
}

@Configuration
class SecurityConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("reader")
                        .password(encoder.encode("reader-pass"))
                        .roles("READER")
                        .build(),
                User.withUsername("guest")
                        .password(encoder.encode("guest-pass"))
                        .roles("GUEST")
                        .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/customers")
                        .hasRole("READER")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}

enum SortField {
    NAME,
    CREATED
}

class CustomerSearch {
    @Size(max = 80)
    private String nameContains = "";

    @NotNull
    @Min(1)
    @Max(50)
    private Integer limit = 20;

    @NotNull
    private SortField sort = SortField.NAME;

    public CustomerSearch() {
    }

    public String getNameContains() {
        return nameContains;
    }

    public void setNameContains(String nameContains) {
        this.nameContains = nameContains;
    }

    public Integer getLimit() {
        return limit;
    }

    public void setLimit(Integer limit) {
        this.limit = limit;
    }

    public SortField getSort() {
        return sort;
    }

    public void setSort(SortField sort) {
        this.sort = sort;
    }
}

record CustomerRow(long id, String name, LocalDateTime createdAt) {
}

@Repository
class CustomerRepository {
    private final JdbcTemplate jdbc;

    CustomerRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    List<CustomerRow> search(CustomerSearch request) {
        String orderBy = switch (request.getSort()) {
            case NAME -> "name ASC, id ASC";
            case CREATED -> "created_at DESC, id ASC";
        };

        String needle = request.getNameContains() == null
                ? ""
                : request.getNameContains().strip();
        String pattern = literalContainsPattern(needle);

        String sql = "SELECT id, name, created_at "
                + "FROM customers "
                + "WHERE LOWER(name) LIKE LOWER(?) ESCAPE '!' "
                + "ORDER BY " + orderBy + " LIMIT ?";

        return jdbc.query(
                sql,
                (rs, rowNum) -> new CustomerRow(
                        rs.getLong("id"),
                        rs.getString("name"),
                        rs.getTimestamp("created_at").toLocalDateTime()),
                pattern,
                request.getLimit());
    }

    private static String literalContainsPattern(String raw) {
        String escaped = raw.replace("!", "!!")
                .replace("%", "!%")
                .replace("_", "!_");
        return "%" + escaped + "%";
    }
}

@RestController
class CustomerController {
    private final CustomerRepository repository;

    CustomerController(CustomerRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/api/customers")
    List<CustomerRow> search(@Valid @ModelAttribute CustomerSearch criteria) {
        return repository.search(criteria);
    }
}
```

**Why this is a runnable program:** one file holds the matching `public DemoApplication` class; the other classes/enums/records share package `demo` without `public`. `@SpringBootApplication` scans the package to register security/controller/repository beans. `CommandLineRunner` creates the table and four rows on a fresh in-memory H2 instance at startup. `LocalDateTime` and `record` are supported in Java 17.

**Separation of responsibilities in the code:**

- `SecurityConfig` handles HTTP Basic authentication and protects the URL with `hasRole("READER")`. This role corresponds to authority `ROLE_READER` from server-side accounts.
- `CustomerSearch` defines the query contract: search term, limit, and sort choice. Spring MVC binds into the bean, and `@Valid` runs Jakarta Bean Validation; type/constraint failures typically return HTTP 400.
- `CustomerController` receives the validated DTO and calls the repository without concatenating SQL or decoding passwords.
- `CustomerRepository` builds static SQL structure, binds `pattern` and `limit`, and concatenates only `orderBy` derived from an enum. User data is never spliced into the query.
- `literalContainsPattern` handles wildcards for "contains literal" semantics, not as an anti-SQL-injection defense. SQL injection is prevented by placeholders and JDBC binding.

**Demo limitations:** the sample app uses an in-memory database, a couple of hardcoded sample accounts, and BCrypt generated at startup. Production requires a persistent user store, HTTPS authentication, per-tenant/per-object access control, pooling/timeouts, monitoring, and sensitive-data management. Search APIs may need cursor pagination instead of offset and should return only truly needed fields.

### 5.4. Running Locally and Observing Behavior

With the Gradle Wrapper:

```bash
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Once Boot is listening on `http://localhost:8080` (assuming default `server.port`), use curl in another terminal:

```bash
# No credentials: typically 401, with WWW-Authenticate Basic.
curl -i "http://localhost:8080/api/customers"

# Authenticated but lacks READER role: 403.
curl -i -u guest:guest-pass "http://localhost:8080/api/customers"

# Valid reader searching Alice: 200, one record.
curl -i -u reader:reader-pass \
  "http://localhost:8080/api/customers?nameContains=Ali&sort=NAME&limit=20"

# Limit violates contract: 400, query does not run as a valid request.
curl -i -u reader:reader-pass \
  "http://localhost:8080/api/customers?limit=999"

# Sort field not in enum: 400 due to binding failure.
curl -i -u reader:reader-pass \
  "http://localhost:8080/api/customers?sort=UNSAFE"

# Single quote is data, not query syntax: finds O'Reilly.
curl -i -u reader:reader-pass -G \
  --data-urlencode "nameContains=O'Reilly" \
  "http://localhost:8080/api/customers"

# String looking like SQL injection is still a bound value.
curl -i -u reader:reader-pass -G \
  --data-urlencode "nameContains=' OR 1=1 --" \
  "http://localhost:8080/api/customers"

# Underscore is searched as a literal character.
curl -i -u reader:reader-pass -G \
  --data-urlencode "nameContains=_" \
  "http://localhost:8080/api/customers"
```

In PowerShell, use `curl.exe` if `curl` aliases `Invoke-WebRequest`. Lines ending with `\` use Bash line continuation; in PowerShell, put each `curl.exe` command on one line or use PowerShell's line continuation.

| Request | Expected HTTP | Result / meaning |
| --- | --- | --- |
| No credentials | 401 | Spring Security requires authentication |
| `guest:guest-pass` | 403 | Valid credentials, lacks `ROLE_READER` |
| `reader` with `nameContains=Ali` | 200 | JSON array containing `Alice` |
| `reader` with `limit=999` | 400 | `@Max(50)` rejects input |
| `reader` with `sort=UNSAFE` | 400 | Cannot convert to `SortField` enum |
| `reader` searching `O'Reilly` | 200 | Returns `O'Reilly Books`; quote does not alter SQL syntax |
| `reader` with `' OR 1=1 --` | 200 | Empty JSON array `[]`; does not expand results to full table |
| `reader` searching `_` | 200 | Returns `A_100` thanks to `LIKE` wildcard escaping |

Abbreviated example body for `nameContains=Ali` (actual JSON structure also includes `id` and `createdAt`):

```json
[
  {
    "id": 1,
    "name": "Alice",
    "createdAt": "2025-02-01T10:00:00"
  }
]
```

HTTP statuses/bodies can differ if you add exception handlers, alter Spring Security config, or hit infrastructure errors. Table rows are seeded by `CommandLineRunner` and exist only in the demo H2 database, so the results above assume running this exact application.

## 6. Testing: Proving All Three Barriers Work

Good tests do not merely send a SQL injection payload and hope no SQL error appears. Test authentication/authorization, input bounds, query safety, and literal search semantics together.

Create `src/test/java/demo/CustomerApiTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CustomerApiTest {
    @Autowired
    MockMvc mvc;

    @Test
    void anonymousIsNotAllowed() throws Exception {
        mvc.perform(get("/api/customers"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedGuestLacksRole() throws Exception {
        mvc.perform(get("/api/customers")
                        .with(httpBasic("guest", "guest-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void readerCanSearchAlice() throws Exception {
        mvc.perform(get("/api/customers")
                        .with(httpBasic("reader", "reader-pass"))
                        .param("nameContains", "Ali"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].name").value("Alice"));
    }

    @Test
    void limitOutsideRangeIsRejected() throws Exception {
        mvc.perform(get("/api/customers")
                        .with(httpBasic("reader", "reader-pass"))
                        .param("limit", "999"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void sortOutsideAllowListIsRejected() throws Exception {
        mvc.perform(get("/api/customers")
                        .with(httpBasic("reader", "reader-pass"))
                        .param("sort", "UNSAFE"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void quotesAreBoundAsData() throws Exception {
        mvc.perform(get("/api/customers")
                        .with(httpBasic("reader", "reader-pass"))
                        .param("nameContains", "' OR 1=1 --"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$").isEmpty());
    }

    @Test
    void likeUnderscoreIsLiteral() throws Exception {
        mvc.perform(get("/api/customers")
                        .with(httpBasic("reader", "reader-pass"))
                        .param("nameContains", "_"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].name").value("A_100"));
    }
}
```

Run:

```bash
./gradlew test
```

- 401/403 tests confirm Spring Security is wired to the endpoint; they **do not prove** SQL is parameterized.
- 400 tests prove DTO validation/binding rejects out-of-contract parameters; they **do not prove** SQL injection is blocked on every code path.
- Tests with quotes and wildcards prove this query avoids turning input into SQL syntax while preserving search semantics.
- In code reviews, still inspect every SQL/raw query—especially dynamic queries, stored procedures with dynamic SQL, string-built EntityManager queries, and non-HTTP input paths.
- When protecting sensitive data, add integration tests with tenants A and B to ensure a valid role **cannot view another tenant's data**, even with a guessed ID.

## 7. Common Misconceptions and How to Handle Them

### 7.1. "With Spring Security in Place, the API Is Safe from SQL Injection"

False. Spring Security is primarily responsible for authentication, authorization, headers, and web protections; it **does not analyze and rewrite unsafe SQL** written by the application. An authorized caller can still send `nameContains` containing SQL metacharacters. Repositories must parameterize.

### 7.2. "We Validated Alphanumerics Only, So PreparedStatement Is Unnecessary"

False. Blacklists/regexes are not a reliable defense against SQL injection; many real business cases require apostrophes, Unicode, and punctuation. Moreover, data can enter SQL from another source that bypassed that validator. Bind every **data value** via the proper API even when data looks harmless.

### 7.3. "Using an ORM/JPA Makes SQL Injection Impossible"

False. Safe ORM query methods reduce risk, yet JPQL or native SQL concatenated from untrusted input remains injectable. Use query parameters for values, structured query builders, and allowlists for dynamic syntax parts. Never turn a raw request string into JPQL/SQL.

### 7.4. "PreparedStatement Is Enough to Substitute Column Names"

False. Column names, tables, keywords, and SQL fragments are not data values. `ORDER BY ?` does not pick a column from input as desired. For selectable structural parts, map choices to code-owned literals or use controlled builders; reject anything outside the allowlist.

### 7.5. "Using `LIKE ?` Treats `%` and `_` as Plain Characters"

False for search semantics. Bound parameters protect SQL syntax, yet `%` and `_` remain `LIKE` wildcards. Escape patterns when the contract specifies literal substring matching, as in the `ESCAPE '!'` example; if the contract allows wildcards, define and bound that behavior explicitly.

### 7.6. "Frontend Validation Is Enough"

False. Clients can bypass the UI, tamper with requests, or call APIs via scripts. Validate on the server; also enforce domain invariants in the service/domain layer so other flows (batches, jobs, events) cannot bypass them.

### 7.7. "Any Request with the Role Can Run Any Query"

False. The `READER` role in the demo illustrates only **endpoint access**. If a real database stores multiple tenants or private profiles, every query must also enforce ownership/tenant policy from a trusted source. Syntactically safe SQL can still **leak data due to missing authorization conditions**.

### 7.8. "HTML Escaping Prevents SQL Injection"

Wrong defense layer. Output encoding/HTML escaping addresses rendering data in HTML; it does not replace prepared statements. Likewise, password hashing does not fix SQL bugs, and CSRF checks do not replace body validation. Each threat requires its own control.

### 7.9. "Return 401/403 for Input Errors"

Do not mix error categories:

| Case | Typical HTTP | Responsible layer |
| --- | --- | --- |
| Missing credentials when required | 401 with HTTP Basic | Authentication |
| Valid credentials lacking role | 403 | Authorization |
| `limit` outside 1..50, invalid sort | 400 | Binding/validation |
| Valid request violating domain invariant | 400/409/422 per contract | Business |
| Resource not found after authorization check | 404 | Domain/data |
| DB unavailable or programming bug | Appropriate 5xx; log server-side | Infrastructure/ops |

HTTP 400 does not mean "all injection is prevented", and HTTP 200 with an empty array does not by itself prove the whole app is safe; inspect how SQL is constructed.

## 8. Raising the Bar for Production Systems

1. **Schemas and DTOs:** define clear API contracts with bounds on length, collection size, types, ranges, and allowed values; use validation groups only when distinct contexts genuinely require them to avoid overcomplication.
2. **Consistency between boundary and domain:** data entering via REST, messaging, imports, or batches must satisfy critical domain rules; never treat `@Valid` on a controller as the sole barrier.
3. **Queries:** review all `JdbcTemplate`, `NamedParameterJdbcTemplate`, JPA/JPQL, native queries, and stored procedures with dynamic SQL; bind values and allowlist identifiers.
4. **Performance limits:** enforce sensible `LIMIT`s, cap filters and pattern lengths, and index/plan queries properly. `LIKE '%term%'` can trigger expensive full scans; tailor rate limits, timeouts, and search strategies to scale.
5. **Data permissions:** authenticate callers, verify roles/scopes, obtain tenant/owner from verified principals, and enforce in policies/queries. Database accounts should follow least privilege.
6. **Errors and logging:** return validation messages clear enough for users without exposing SQL statements, stack traces, passwords, or sensitive rows. Technical logs should use error codes/correlation IDs and minimized/redacted data.
7. **Storage and data output:** encrypt sensitive data where needed, manage secrets, maintain audit trails, and avoid returning all entity columns when APIs need only a few fields; parameterization does not replace output data control.
8. **Testing at the right layers:** unit-test validators/query builders, integration-test SQL against H2 or real databases as required, test multi-tenant isolation, fuzz inputs, and run security testing tools where appropriate.
9. **Never drop other protections:** CSRF, CORS, authorization, and HTML output encoding protect distinct paths; never disable or swap them out because of input validation or SQL binding.

## 9. Self-Check Exercises

1. A user holds `ROLE_READER` and sends `' OR 1=1 --`. Does Spring Security automatically strip or block this string? Which component must ensure it remains a SQL **data value**?
2. Why is `@Size(max = 80)` insufficient to stop SQL injection, and why does a prepared statement not enforce `limit <= 50`?
3. Why can `ORDER BY ?` not replace mapping `SortField.NAME -> "name ASC"`? When can string concatenation in SQL be acceptable?
4. If an API searches for customer `A_100` by literal substring, does `LIKE ?` treat `_` as a literal underscore automatically? How do you fix it?
5. A logged-in user calls an API to fetch another tenant's profile. The query uses placeholders for all values yet still returns that profile. Is the flaw SQL injection or authorization?
6. `CreateCustomerRequest` has `@Email` and `@NotBlank`. Do these two annotations guarantee the email is unique, exists, and was verified by the user? Which rules belong to domain/verification?
7. Data fetched from an internal table earlier is later concatenated into a dynamic query. Why can second-order injection still occur?
8. If a client sends `sort=UNSAFE`, which layer should reject it? If a client sends `limit=999`, which layer is responsible?
9. What tests would you add to prove access control, contract validation, parameterized SQL, `LIKE` escaping, and tenant filtering all work together?

**Guidance:** (1) Spring Security does not replace query building—bind in the repository; (2) validation and parameterization address different risks; (3) placeholders represent values only, structural parts come from an allowlist; (4) escape wildcards when the contract calls for literal matching; (5) missing row-level/tenant authorization; (6) domain uniqueness and verification flows are still needed; (7) previously stored data can still act as untrusted input when concatenated into queries; (8) binding/Bean Validation, not authentication; (9) write adversarial tests for each barrier.

## Official Documentation and Security Guides

- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — HTTP Basic Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html)
- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework — JDBC Core and JdbcTemplate](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html)
- [Spring Framework — NamedParameterJdbcTemplate](https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html)
- [OWASP SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet)
- [OWASP Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html)