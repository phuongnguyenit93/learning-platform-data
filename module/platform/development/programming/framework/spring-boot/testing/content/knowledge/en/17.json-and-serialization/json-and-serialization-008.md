# Testing That Sensitive Fields Never Appear in Responses

In Spring Boot's **JSON and serialization** area, an easily overlooked security flaw occurs when an API returns **more data than the contract permits**. For example, a domain entity/object has `passwordHash`, `resetToken`, or an integration access key, yet the controller returns that object directly for Jackson to serialize. The JSON is still valid, HTTP still returns 200, and tests asserting only `id`/`displayName` still stay green—while secret data has appeared in the response.

**Lesson goal:** design responses around an **allowlist** and write tests guaranteeing that **sensitive fields truly do not exist in the JSON**, even when the field is `null`, inside a nested object, across multiple array elements, or inside an error response. Tests must inspect the **final JSON payload received by the client**, not just an annotation or the pre-serialization Java object.

Primary tools:

- **Response DTO/projection:** specifies exactly which fields are permitted to appear.
- **Jackson:** `@JsonIgnore`, `@JsonProperty(access = WRITE_ONLY)`, `ObjectMapper`, and `JsonNode`.
- **Spring Boot `@JsonTest`:** verifies Jackson-serialized JSON structure within a narrow scope.
- **Spring MVC `@WebMvcTest` + `MockMvc`:** verifies HTTP response JSON with the mappings/advice/converters active in the web slice.
- **`jsonPath(...).doesNotHaveJsonPath()`:** asserts a JSON path is **absent even when its value is `null`**.

The examples below target **Java 17+, Spring Boot 3.4/3.5, Jackson 2, and Spring Framework 6.2**. For Spring Boot 4.x, the boundary split and verification techniques remain useful, though packages for some test annotations and newer Jackson management may differ; use the exact APIs for your project version.

## 1. Define "does not appear" properly before testing

Suppose an API produces two JSON payloads:

```json
{
  "id": 42,
  "displayName": "Linh"
}
```

and:

```json
{
  "id": 42,
  "displayName": "Linh",
  "passwordHash": null
}
```

These two responses are **not equivalent** if the contract states `passwordHash` **must not appear**. In the second JSON, the **field name is still disclosed**, letting clients infer that the system has that property. A `null` value does not satisfy a "field forbidden" policy.

Therefore, distinguish three assertions:

| Check | What it proves | Accepts `{"secret":null}`? |
| --- | --- | --- |
| `jsonPath("$.secret").doesNotExist()` | No **non-null value** at the path | **Possibly yes** |
| `jsonPath("$.secret").doesNotHaveJsonPath()` | **No path exists**, including null | **No** |
| `JsonNode.has("secret") == false` | Object node has no such key | **No** |

Spring MockMvc's `doesNotHaveJsonPath()` API is designed for "path absent including null." It is usually a more accurate choice than `doesNotExist()` when writing security regression tests for **not leaking field names**.

**What tests like this do not automatically guarantee:** secret data could be placed under a **different field name** (e.g. `debugMessage` containing a token), written to HTTP headers, logs, traces, cookies, or leaked on another endpoint. Beyond forbidding keys, check the **full response schema**, sentinel values, and other permitted boundaries.

## 2. Why is returning an entity or domain object directly risky?

A domain object can hold several kinds of data:

```text
Account (internal)
├── id
├── displayName
├── locale
├── passwordHash          [DO NOT RETURN]
├── resetToken            [DO NOT RETURN]
├── internalNote          [DO NOT RETURN]
└── integrations
    ├── provider          [MAY RETURN]
    └── apiKey            [DO NOT RETURN]
```

If the controller does:

```java
@GetMapping("/{id}")
public Account get(@PathVariable long id) {
    return lookup.find(id); // Anti-pattern if Account contains secrets.
}
```

then the serializer can see `Account`'s accessors and turn them into JSON properties. Whether the resulting JSON is filtered depends on annotations/configuration; **never rely on luck** or on "the current UI doesn't display that field."

Risk is especially high when:

- Returning JPA entities/repository results directly instead of response DTOs.
- Using `Map<String, Object>` with many keys copied from internal models.
- Returning an object with nested `credentials`/`sessions`/`integrations`.
- Using reflection/automatic object mapping that copies every property.
- Adding a new sensitive field to a domain model and forgetting to update tests.
- An exception handler exposing `exception.getMessage()`, stack traces, or internal details in the response.
- List responses only test the first element while subsequent elements leak secrets.

**Preferred safeguard:** use a **response DTO with a field allowlist**, then write tests at both the **serializer boundary** and the **HTTP boundary**. Hiding annotations on domain objects can serve as an extra defense-in-depth layer, yet response DTOs clarify the contract and limit the blast radius of domain changes.

## 3. Three common Jackson strategies

### 3.1. Response DTO (preferred)

Instead of serializing `Account` directly, create `AccountResponse` containing only permitted data:

```java
public record AccountResponse(
        long id,
        String displayName,
        Meta meta,
        List<IntegrationView> integrations) {
    public record Meta(String locale) {}
    public record IntegrationView(String provider) {}
}
```

This is a conceptual declaration, not a standalone source file since it omits the `List` import and conversion function. The runnable section in section 5 has complete classes.

When a new `privateKey` field is added to `Account`, it **does not automatically appear** in `AccountResponse`, because the response explicitly lists output properties. This is a relatively strong **fail-closed by design** characteristic: exposing an additional field requires intentionally updating the contract and mapping.

**DTOs do not replace authorization:** `displayName`, `locale`, or `provider` can also be personal/sensitive data in certain contexts. Return them only when endpoint policy allows, and always check that the caller is authorized to read that record.

### 3.2. `@JsonIgnore`: excluding properties from JSON per Jackson config

Illustrative example:

```java
public class InternalUser {
    public String username;

    @JsonIgnore
    public String passwordHash;
}
```

With standard Jackson 2 configuration, `@JsonIgnore` prevents `passwordHash` from appearing during serialization. Keep in mind:

- Annotations on fields/getters/record components interact with Jackson's property discovery rules; test the **actual `ObjectMapper` used by the application**.
- `@JsonIgnore` does not mean "nobody can read the field in memory," nor does it scrub data from databases/logs.
- For input that must be **deserializable yet never serialized**, `@JsonProperty(access = WRITE_ONLY)` usually expresses intent more clearly.
- If switching to another serializer library or customizing `ObjectMapper`, verify actual behavior; never treat an annotation as sole proof.

This is a separate class example without imports and is not used in the runnable set below. If you apply annotations on domain objects, keep **real JSON tests** in case refactoring alters property visibility.

### 3.3. `@JsonProperty(access = WRITE_ONLY)`: accept on input, omit on output

For a request containing a password, the application may need to **receive** the password in JSON for authentication, yet **must not serialize it back** if that object is used in output. Jackson provides:

```java
@JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
String password
```

`WRITE_ONLY` is named from the **perspective of the Java property**: Jackson may **write** a value into the property during *deserialization*, yet must not **read** it for *serialization*. It does **not** mean "clients may only read the password."

| Access | Serialize object → JSON | Deserialize JSON → object |
| --- | --- | --- |
| `AUTO` | Per visibility/config | Per visibility/config |
| `READ_ONLY` | May be emitted | Not read from JSON |
| `WRITE_ONLY` | **Not emitted** | May be read from JSON |
| `READ_WRITE` | May be emitted | May be read |

**Note:** `WRITE_ONLY` does not automatically ensure passwords are hashed, stored securely, scrubbed from logs, or protected against other response mapping bugs. A request DTO containing a password can accept input; response DTOs should avoid having a password property in the first place.

### 3.4. Do not use null exclusion as a security policy

`@JsonInclude(Include.NON_NULL)` omits **properties whose value is null**, yet once a secret field holds a non-null value, it **still appears**. It is a JSON formatting rule, **not access control for sensitive data**.

Likewise, do not treat `@Schema(hidden = true)` (OpenAPI docs), `@ToString.Exclude` (affects string representation), or frontend field hiding as mechanisms that stop Jackson serialization. Each tool has a distinct scope.

## 4. Strong testing approach: positive contract + negative contract

A security regression test should check both sides:

**Positive contract:**
- Endpoint returns the right status/media type.
- Permitted fields such as `id` and `displayName` have expected values.
- Nested objects and arrays match the right schema/values.
- You did not accidentally wipe out all response data and still pass negative assertions.

**Negative contract:**
- Sensitive paths **do not exist even as null**.
- No forbidden keys appear at any nesting depth.
- No sensitive sentinel values appear inside a renamed field.
- Response contains no properties outside the allowlist.
- Error responses do not contain error messages leaking secrets, internal SQL/JWTs/tokens.

An example:

```java
mvc.perform(get("/accounts/42"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.displayName").value("Linh"))
        .andExpect(jsonPath("$.passwordHash")
                .doesNotHaveJsonPath())
        .andExpect(jsonPath("$.integrations[0].apiKey")
                .doesNotHaveJsonPath());
```

This is a snippet inside a test with a configured `MockMvc`, not a standalone class. Asserting `$.integrations[0].apiKey` checks only the **first element**. For multi-element lists, inspect **all elements** and nested objects; never rely on a single index to claim the entire payload is safe.

## 5. Complete Java 17+ example: domain with secrets, allowlist response

We build a small API demonstrating how to minimize exposed data and test JSON.

**Internal data:**
- `Account` holds `id`, `displayName`, `locale`.
- Secret fields: `passwordHash`, `resetToken`, `internalNote`.
- `Integration` list containing provider name and `apiKey`.

**Data permitted in the example response:**
- `id`, `displayName`.
- `meta.locale`.
- `integrations` array containing only `provider`.

**Security note:** this API demonstrates serialization **without authentication/authorization**. In real applications, who may read an `Account` and its provider info depends on policy; never deploy this illustrative endpoint publicly without access controls.

Project structure:

```text
src/
├── main/java/example/testing/redaction/
│   ├── AccountApplication.java
│   ├── Account.java
│   ├── AccountLookup.java
│   ├── AccountResponse.java
│   ├── AccountController.java
│   ├── LoginRequest.java
│   └── AccountMappingDemo.java
└── test/java/example/testing/redaction/
    ├── AccountResponseJsonTest.java
    └── AccountControllerTest.java
```

### 5.1. Boot entrypoint: AccountApplication.java

Create `src/main/java/example/testing/redaction/AccountApplication.java`:

```java
package example.testing.redaction;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AccountApplication {
    public static void main(String[] args) {
        SpringApplication.run(AccountApplication.class, args);
    }
}
```

Place this class in the example's root package so Spring Boot locates the configuration. **This API uses `@WebMvcTest` with a mocked `AccountLookup`**, so a database-backed implementation is not required in the example. To run the full application via `SpringApplication.run`, an `AccountLookup` implementation bean must be provided; that belongs to production wiring and is not the focus of the two test slices provided.

Do not conclude that a green `@WebMvcTest` proves the production app has an `AccountLookup` bean. Mocked beans in a slice only prove the controller and serializer work within the test context.

### 5.2. Domain object: Account.java

Create `src/main/java/example/testing/redaction/Account.java`:

```java
package example.testing.redaction;

import java.util.List;

public record Account(
        long id,
        String displayName,
        String locale,
        String passwordHash,
        String resetToken,
        String internalNote,
        List<Integration> integrations) {

    public Account {
        integrations = List.copyOf(integrations);
    }

    public record Integration(
            String provider,
            String apiKey) {
    }
}
```

This is a Java 17 record with auto-generated accessors. **Never serialize `Account` directly in HTTP responses**: because Jackson sees record components, `passwordHash`, `resetToken`, `internalNote`, and `integrations[*].apiKey` would become JSON properties.

`List.copyOf` keeps an unmodifiable copy by reference on the record. The example assumes `integrations` is non-null, contains no null elements, and input was validated beforehand; if production domain rules permit null, define explicit normalization and separate tests. This is not a serializer security control.

### 5.3. Dependency: AccountLookup.java

Create `src/main/java/example/testing/redaction/AccountLookup.java`:

```java
package example.testing.redaction;

import java.util.List;

public interface AccountLookup {
    Account find(long id);
    List<Account> list();
}
```

This is a **port/interface**. In `@WebMvcTest`, `@MockitoBean` supplies the mock so the controller gets its dependency. Production needs a real adapter/service implementation when booting the full app.

### 5.4. Response DTO: AccountResponse.java

Create `src/main/java/example/testing/redaction/AccountResponse.java`:

```java
package example.testing.redaction;

import java.util.List;

public record AccountResponse(
        long id,
        String displayName,
        Meta meta,
        List<IntegrationView> integrations) {

    public AccountResponse {
        integrations = List.copyOf(integrations);
    }

    public static AccountResponse from(Account account) {
        List<IntegrationView> visibleIntegrations =
                account.integrations().stream()
                        .map(item ->
                                new IntegrationView(item.provider()))
                        .toList();

        return new AccountResponse(
                account.id(),
                account.displayName(),
                new Meta(account.locale()),
                visibleIntegrations);
    }

    public record Meta(String locale) {
    }

    public record IntegrationView(String provider) {
    }
}
```

**Why is this an allowlist?** The response record has only 4 top-level components. Nested `Meta` has only `locale`; `IntegrationView` has only `provider`. Neither `passwordHash`, `resetToken`, `internalNote`, nor `apiKey` exists for Jackson to serialize.

Mapping is written explicitly instead of copying all properties. If `Account` later adds `secretKey`, the output does not automatically expose the new property. To return an extra field, you must deliberately update `AccountResponse` and the response contract tests.

**Types alone do not solve authorization:** account ID, display name, locale, and provider lists may also require permission checks. DTO design guards **response shape**, not the entire data access policy.

### 5.5. Real controller: AccountController.java

Create `src/main/java/example/testing/redaction/AccountController.java`:

```java
package example.testing.redaction;

import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/accounts")
public class AccountController {
    private final AccountLookup lookup;

    public AccountController(AccountLookup lookup) {
        this.lookup = lookup;
    }

    @GetMapping(
            path = "/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public AccountResponse detail(@PathVariable long id) {
        return AccountResponse.from(lookup.find(id));
    }

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    public List<AccountResponse> list() {
        return lookup.list().stream()
                .map(AccountResponse::from)
                .toList();
    }

    @ExceptionHandler(IllegalArgumentException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public ApiError invalidRequest(
            IllegalArgumentException exception) {
        // Intentionally do not serialize exception.getMessage().
        return new ApiError("INVALID_ACCOUNT_REQUEST");
    }

    public record ApiError(String code) {
    }
}
```

In the example, `@ExceptionHandler` returns a fixed error code and **never puts the raw exception message into JSON**. This prevents an error message containing tokens/SQL/internal details from appearing just because a service threw an exception with an unsuitable message. In real applications, error responses should enforce consistent policies across other exception types, including framework errors and global `@RestControllerAdvice`.

**Important:** the tests in the next section inspect HTTP responses inside the MVC test slice. They do not test authentication, authorization, or permission to view an Account ID; those boundaries require dedicated tests.

### 5.6. Input DTO and WRITE_ONLY: LoginRequest.java

Create `src/main/java/example/testing/redaction/LoginRequest.java`:

```java
package example.testing.redaction;

import com.fasterxml.jackson.annotation.JsonProperty;

public record LoginRequest(
        String username,
        @JsonProperty(
                access = JsonProperty.Access.WRITE_ONLY)
        String password) {
}
```

This is an **input DTO** illustrating Jackson access control. With Jackson 2's Java record support, JSON can be deserialized into `password`, yet serializing `LoginRequest` omits that key.

**Never send `LoginRequest` back to clients as a response in real designs.** `WRITE_ONLY` is only an extra defense-in-depth layer; responses should still use a separate DTO. For a password reset or secret exchange endpoint, never echo such data back even with the annotation.

### 5.7. Plain Java demo without Spring/Jackson: AccountMappingDemo.java

Create `src/main/java/example/testing/redaction/AccountMappingDemo.java`:

```java
package example.testing.redaction;

import java.util.List;

public class AccountMappingDemo {
    public static void main(String[] args) {
        Account account = new Account(
                42L,
                "Linh",
                "vi-VN",
                "HASH_TEST_ONLY",
                "RESET_TEST_ONLY",
                "NOTE_TEST_ONLY",
                List.of(
                        new Account.Integration(
                                "billing", "KEY_TEST_ONLY"),
                        new Account.Integration(
                                "analytics", "KEY_TEST_ONLY")));

        AccountResponse response =
                AccountResponse.from(account);

        System.out.println(response.id());
        System.out.println(response.displayName());
        System.out.println(response.meta().locale());
        System.out.println(
                response.integrations().stream()
                        .map(AccountResponse
                                .IntegrationView::provider)
                        .toList());
    }
}
```

Compile and run from the project root directory:

```bash
javac -d out src/main/java/example/testing/redaction/Account.java src/main/java/example/testing/redaction/AccountResponse.java src/main/java/example/testing/redaction/AccountMappingDemo.java
java -cp out example.testing.redaction.AccountMappingDemo
```

Exact stdout:

```text
42
Linh
vi-VN
[billing, analytics]
```

This is a **plain Java demo** of DTO mapping, not a JSON serialization test since it loads neither Jackson nor Spring. Values like `HASH_TEST_ONLY`, `RESET_TEST_ONLY`, and `KEY_TEST_ONLY` are **test sentinels**, not real passwords/tokens. The goal is showing that the mapper transfers only permitted data without leaking secrets into visible properties.

## 6. `@JsonTest`: verifying the Jackson-serialized schema

Create `src/test/java/example/testing/redaction/AccountResponseJsonTest.java`:

```java
package example.testing.redaction;

import java.util.List;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.json.JsonTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@JsonTest
class AccountResponseJsonTest {

    @Autowired
    private ObjectMapper mapper;

    @Test
    void responseHasExactlyTheAllowedJsonProperties()
            throws Exception {
        Account domain = new Account(
                42L, "Linh", "vi-VN",
                "HASH_TEST_ONLY",
                "RESET_TEST_ONLY",
                "NOTE_TEST_ONLY",
                List.of(new Account.Integration(
                        "billing", "KEY_TEST_ONLY")));

        JsonNode actual = mapper.readTree(
                mapper.writeValueAsString(
                        AccountResponse.from(domain)));

        JsonNode expected = mapper.readTree("""
                {
                  "id": 42,
                  "displayName": "Linh",
                  "meta": {"locale": "vi-VN"},
                  "integrations": [{"provider": "billing"}]
                }
                """);

        assertEquals(expected, actual);
        assertFalse(actual.has("passwordHash"));
        assertFalse(actual.has("resetToken"));
        assertFalse(actual.has("internalNote"));
        assertFalse(actual.path("integrations")
                .get(0).has("apiKey"));
    }

    @Test
    void writeOnlyPasswordCanBeReadButNotSerialized()
            throws Exception {
        LoginRequest input = mapper.readValue(
                """
                {"username":"demo","password":"PASS_TEST_ONLY"}
                """,
                LoginRequest.class);

        assertEquals("demo", input.username());
        assertEquals("PASS_TEST_ONLY", input.password());

        JsonNode serialized = mapper.readTree(
                mapper.writeValueAsString(input));

        assertEquals("demo",
                serialized.path("username").asText());
        assertFalse(serialized.has("password"));
    }

    @Test
    void jsonNullIsDifferentFromAbsentProperty()
            throws Exception {
        JsonNode node = mapper.readTree("""
                {"id":42,"resetToken":null}
                """);

        assertTrue(node.has("resetToken"));
        assertFalse(node.hasNonNull("resetToken"));
        assertFalse(node.has("passwordHash"));
    }
}
```

**Why is this test important?**

- `@JsonTest` creates a Spring Boot **JSON slice**, sufficient to test Jackson serialization under the slice's config without starting the full MVC server or database.
- `ObjectMapper.writeValueAsString(...)` generates real JSON; `readTree(...)` parses it into a tree to inspect keys/values.
- `assertEquals(expected, actual)` on two `JsonNode` instances verifies the **exact output structure**. If the serializer adds any new key—even one not on a known sensitive list—the assertion fails.
- The `WRITE_ONLY` test verifies **both deserialization and serialization**, rather than just reading the annotation.
- The `null` test shows `JsonNode.has(...)` returns true when a key is present with `null`, whereas `hasNonNull(...)` returns false. A "does not appear" policy must check `has(...) == false`.

**Limitation:** the JSON slice proves mapper behavior in the test context, not that the HTTP endpoint uses the right DTO, routes, roles, or exception handling. Therefore, add `MockMvc` tests as well.

With Spring Boot 3.4/3.5, importing `@JsonTest` from `org.springframework.boot.test.autoconfigure.json.JsonTest` and Jackson 2 `ObjectMapper` from `com.fasterxml.jackson.databind.ObjectMapper` is appropriate. For Spring Boot 4.x, check the corresponding modules/packages and Jackson version; do not mix Boot/Jackson generations.

## 7. `@WebMvcTest` + `MockMvc`: checking real JSON returned over HTTP

Create `src/test/java/example/testing/redaction/AccountControllerTest.java`:

```java
package example.testing.redaction;

import java.util.List;
import java.util.Set;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(AccountController.class)
class AccountControllerTest {

    private static final Set<String> FORBIDDEN_KEYS = Set.of(
            "passwordHash", "resetToken", "internalNote",
            "apiKey", "accessToken", "clientSecret");

    private static final Set<String> TEST_SENTINELS = Set.of(
            "HASH_TEST_ONLY", "RESET_TEST_ONLY",
            "NOTE_TEST_ONLY", "KEY_TEST_ONLY");

    @Autowired
    private MockMvc mvc;

    @Autowired
    private ObjectMapper mapper;

    @MockitoBean
    private AccountLookup lookup;

    private static Account account(
            long id, String displayName, String locale) {
        return new Account(
                id, displayName, locale,
                "HASH_TEST_ONLY",
                "RESET_TEST_ONLY",
                "NOTE_TEST_ONLY",
                List.of(new Account.Integration(
                        "billing", "KEY_TEST_ONLY")));
    }

    @Test
    void detailExposesOnlyTheAllowlistedJson()
            throws Exception {
        when(lookup.find(42L))
                .thenReturn(account(42L, "Linh", "vi-VN"));

        String json = mvc.perform(get("/accounts/42"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.displayName")
                        .value("Linh"))
                .andExpect(jsonPath("$.passwordHash")
                        .doesNotHaveJsonPath())
                .andExpect(jsonPath("$.resetToken")
                        .doesNotHaveJsonPath())
                .andExpect(jsonPath("$.integrations[0].apiKey")
                        .doesNotHaveJsonPath())
                .andReturn()
                .getResponse()
                .getContentAsString();

        JsonNode actual = mapper.readTree(json);
        JsonNode expected = mapper.readTree("""
                {
                  "id": 42,
                  "displayName": "Linh",
                  "meta": {"locale": "vi-VN"},
                  "integrations": [{"provider": "billing"}]
                }
                """);

        assertEquals(expected, actual);
        assertNoSensitiveData(actual);
        verify(lookup).find(42L);
    }

    @Test
    void listChecksEveryAccountAndNestedIntegration()
            throws Exception {
        when(lookup.list()).thenReturn(List.of(
                account(42L, "Linh", "vi-VN"),
                account(43L, "Mai", "en-US")));

        String json = mvc.perform(get("/accounts"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$[0].id").value(42))
                .andExpect(jsonPath("$[1].id").value(43))
                .andReturn()
                .getResponse()
                .getContentAsString();

        JsonNode actual = mapper.readTree(json);
        JsonNode expected = mapper.readTree("""
                [
                  {
                    "id":42,
                    "displayName":"Linh",
                    "meta":{"locale":"vi-VN"},
                    "integrations":[{"provider":"billing"}]
                  },
                  {
                    "id":43,
                    "displayName":"Mai",
                    "meta":{"locale":"en-US"},
                    "integrations":[{"provider":"billing"}]
                  }
                ]
                """);

        assertEquals(expected, actual);
        assertNoSensitiveData(actual);
        verify(lookup).list();
    }

    @Test
    void errorResponseNeverEchoesExceptionSecrets()
            throws Exception {
        when(lookup.find(0L)).thenThrow(
                new IllegalArgumentException(
                        "RESET_TEST_ONLY"));

        String json = mvc.perform(get("/accounts/0"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_ACCOUNT_REQUEST"))
                .andExpect(jsonPath("$.message")
                        .doesNotHaveJsonPath())
                .andReturn()
                .getResponse()
                .getContentAsString();

        assertEquals(
                mapper.readTree(
                        """
                        {"code":"INVALID_ACCOUNT_REQUEST"}
                        """),
                mapper.readTree(json));
        assertNoSensitiveData(mapper.readTree(json));
        verify(lookup).find(0L);
    }

    private static void assertNoSensitiveData(JsonNode node) {
        if (node.isObject()) {
            node.fieldNames().forEachRemaining(key -> {
                assertFalse(FORBIDDEN_KEYS.contains(key),
                        "Forbidden JSON key: " + key);
                assertNoSensitiveData(node.get(key));
            });
        } else if (node.isArray()) {
            node.forEach(
                    AccountControllerTest::assertNoSensitiveData);
        } else if (node.isTextual()) {
            for (String sentinel : TEST_SENTINELS) {
                assertFalse(node.textValue().contains(sentinel),
                        "Sensitive test value leaked");
            }
        }
    }
}
```

**Three controller tests check distinct boundaries:**

1. **Single account detail:** checks HTTP 200, JSON media type, valid fields, absence of three sensitive paths, and the **entire schema** matching the allowlist. If a developer switches the controller to `return lookup.find(id)`, extra keys appear and the test turns red.
2. **Account list:** verifies both elements of the JSON array, not just `$[0]`. `assertNoSensitiveData` recursively walks **every object and every array**, catching forbidden keys at any depth.
3. **Error response:** mocks the dependency to throw an exception whose message contains `RESET_TEST_ONLY`. The handler must return a fixed code without echoing the message. The test checks the **entire error JSON** and scans for sentinels to catch leaks.

The recursive helper intentionally checks both **key names** and **sentinel values**. If `apiKey` were accidentally renamed to `debugValue` containing `KEY_TEST_ONLY`, a key-only check might miss it, yet sentinel scanning and schema comparison catch it.

**Note on `jsonPath(...).doesNotHaveJsonPath()`:** checks specific paths, including null values. It complements, rather than replaces, JSON tree comparison and recursion. Checking only `$.integrations[0].apiKey` can miss secrets in subsequent elements or nested objects elsewhere; that is why the list test traverses the entire response body.

**Why use `@MockitoBean`?** In `@WebMvcTest`, services/adapters outside the MVC slice are normally not loaded. `@MockitoBean` creates or replaces the `AccountLookup` bean so the controller gets its dependency, while the real controller and MVC serialization execute. This tests the HTTP presentation layer, **without proving a repository or production lookup bean exists**.

## 8. Gradle configuration and running the example set

With **Spring Boot 3.4/3.5** and matching plugin/dependency management configured, the relevant snippet in `build.gradle` (Groovy DSL):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is an **additive configuration snippet**, not a complete build file. Java 17 must be configured in the project's toolchain/source compatibility. With Boot 3.4/3.5, the web starter provides MVC + Jackson 2 and the test starter provides JUnit Jupiter/MockMvc test support. `@MockitoBean` belongs to Spring Framework TestContext 6.2+, so do not use this exact annotation with Spring Boot 3.3 or earlier.

Run the two classes:

```bash
./gradlew test --tests example.testing.redaction.AccountResponseJsonTest
./gradlew test --tests example.testing.redaction.AccountControllerTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.testing.redaction.AccountResponseJsonTest"
.\gradlew.bat test --tests "example.testing.redaction.AccountControllerTest"
```

**Expected:** `AccountResponseJsonTest` has **3 test methods**; `AccountControllerTest` also has **3 test methods**; all **6 JUnit tests** pass when sources and dependencies match the example.

These unit/slice tests require no real HTTP server and no database. Exact stdout printed by JUnit/Gradle depends on the runner; **there is no single universal stdout** for `gradlew test` commands. Inspect the test report to verify test names and outcomes.

To run the **full application** via Boot `main` or `@SpringBootTest`, add an `AccountLookup` implementation bean (plus authentication/authorization if routes are used for real). Here the example is intentionally scoped to two **test slices** to verify the serialization contract; never claim "full production boot works" just because slices pass.

## 9. Checking all array/nested fields, not just the first index

Suppose JSON returns:

```json
[
  {"id": 42, "integrations": [{"provider": "billing"}]},
  {"id": 43, "integrations": [
    {"provider": "analytics", "apiKey": "LEAK_TEST_ONLY"}
  ]}
]
```

A single assertion `jsonPath("$[0].integrations[0].apiKey").doesNotHaveJsonPath()` still **passes**, because the secret key is on the second element.

**Three complementary tactics:**

- **Compare full JSON against an allowlisted expected payload:** accurate for small/stable response DTOs, catching any out-of-contract property.
- **Recursive `JsonNode` traversal:** fits deeply nested responses or long arrays, catching any forbidden key; the test in section 7 also scans for sentinel values.
- **Recursive JSONPath:** you can use expressions like `$..apiKey` and assert the path does not appear, though you must understand how the library evaluates indefinite paths/arrays; under strict policy, recursive traversal or JSON schema allowlists reduce the risk of query-syntax oversights.

Distinguish clearly:

- `JsonNode.has(field)` → key exists, even if its value is null.
- `JsonNode.hasNonNull(field)` → key has a non-null value.
- `JsonNode.path(field)` → returns a missing node when absent; check `isMissingNode()` instead of just calling `asText()` with its default value.
- `JsonNode.get(field)` → returns Java `null` when absent; do not confuse with `NullNode` representing JSON `null`.
- `JsonPathResultMatchers.doesNotExist()` → does not require the key to be strictly absent if its value is null.
- `JsonPathResultMatchers.doesNotHaveJsonPath()` → asserts absence even for null.

**Never rely on string matching alone.** Searching for `"password"` in the body can trigger false positives (legitimate prose containing the word "password") or false negatives when keys are renamed, escaped, case-converted, or secrets leak under another property name. Parse JSON and verify against a permitted schema.

## 10. Negative tests to avoid false greens

A test checking only absence easily becomes false green if the controller accidentally returns an empty response, a wrong HTTP status, or an error body instead of the expected payload.

Therefore, write tests with **input state containing non-null secrets**. If you initialize `passwordHash = null`, `@JsonInclude(NON_NULL)` can make the test pass while real production data leaks. Test sentinels like `HASH_TEST_ONLY` ensure non-empty sensitive data is genuinely stripped.

**Mental mutation testing:** suppose a developer accidentally edits:

```java
// Anti-pattern example; do not apply in production:
@GetMapping("/{id}")
public Account detail(@PathVariable long id) {
    return lookup.find(id);
}
```

Output changes from:

```json
{"id":42,"displayName":"Linh","meta":{"locale":"vi-VN"},"integrations":[{"provider":"billing"}]}
```

to an object with extra fields, possibly:

```json
{"id":42,"displayName":"Linh","locale":"vi-VN","passwordHash":"HASH_TEST_ONLY","resetToken":"RESET_TEST_ONLY","internalNote":"NOTE_TEST_ONLY","integrations":[{"provider":"billing","apiKey":"KEY_TEST_ONLY"}]}
```

At that point, `JsonNode expected == actual` and the key/sentinel scan **must fail**. That signals the test genuinely guards the contract rather than merely passing against the current implementation.

Do not put the anti-pattern into production code. The goal is identifying bugs tests must catch during review or when validating test strength via mutation testing.

## 11. Never return arbitrary error messages, exceptions, or debug context

An often-forgotten leak vector is **error responses**:

```json
{
  "error": "Token invalid: RESET_TEST_ONLY",
  "sql": "SELECT ...",
  "internalNote": "..."
}
```

Even when the happy path returns a clean DTO, a `@RestControllerAdvice` or `@ExceptionHandler` calling `ex.getMessage()` directly can leak implementation details or secrets into the HTTP body.

A safer pattern is a **controlled error code**:

```java
@ExceptionHandler(IllegalArgumentException.class)
@ResponseStatus(HttpStatus.BAD_REQUEST)
public ApiError invalidRequest(
        IllegalArgumentException exception) {
    return new ApiError("INVALID_ACCOUNT_REQUEST");
}
```

This snippet comes from the runnable controller in section 5.5. Do not conclude every error must return the same code; real systems classify input, authorization, conflict, and server errors, yet **public messages must be deliberately designed**, never auto-exposing internal exceptions.

For Spring `ProblemDetail` or error endpoints, test `detail`, `instance`, and extension properties whenever they might carry sensitive data. Check **error status and schema** with `MockMvc`/`WebTestClient` at the right boundary, not only happy-path DTOs.

**Logs and traces are a separate boundary:** stripping secrets from JSON responses does not guarantee loggers, MDC, tracing span attributes, stack traces, or application metrics are free of secrets. Add logging/security tests or masking policies, without substituting them for response-body assertions.

## 12. Authorization differs from field redaction

Hiding `passwordHash` does not make an endpoint secure if any user can call `GET /accounts/42` and view another person's data.

Separate at least three questions:

1. **Who is allowed to read this resource?** Authentication/authorization, ownership checks, method/URL security, preventing broken object-level authorization.
2. **Which fields may that caller see?** API DTO/field-level policy per role/context.
3. **Are disallowed fields genuinely absent after serialization?** `@JsonTest` and HTTP response-body assertions.

For instance, an endpoint for "users viewing their own account" must take the ID from the authentication principal, not trust an arbitrary client-supplied ID. An "admin viewing an account" endpoint may include more fields than a regular user's view, yet still should not return raw credentials/tokens.

When using role-based responses, design **explicit DTOs per contract** or explicit policy-driven mappings and write tests for each role:

| Caller | Permitted fields (example) | Forbidden fields |
| --- | --- | --- |
| Anonymous | Per public profile policy, perhaps only `displayName` | Email, tokens, reset data, internal notes |
| Owner | Policy-approved profile fields | Password hash, reset token, API keys |
| Admin | Selected administrative metadata if permitted | Raw credentials, tokens, private keys |

This table only illustrates policy; each app requires concrete business/legal decisions. **Never infer access permissions merely because a user can call a URL successfully.**

## 13. Slice tests vs full context and HTTP integration

| Option | What it proves | What it leaves unproven |
| --- | --- | --- |
| Plain JUnit on `AccountResponse.from(...)` | Java mapping puts no sensitive fields into the DTO | Jackson config/HTTP body |
| `@JsonTest` | Serialization/deserialization under the JSON slice mapper | Routes, services, security filters, DB |
| `@WebMvcTest` + `MockMvc` | MVC routes/controllers/advice/JSON responses in the web slice | Real service/repository when mocked; network stack |
| `@SpringBootTest` + `@AutoConfigureMockMvc` | Broader wiring/config, MVC response with real beans in context | Real sockets; mocked external infrastructure |
| `@SpringBootTest(webEnvironment = RANDOM_PORT)` | HTTP over a real port in the test environment | Does not prove external config/DB matches production |

For JSON field redaction, **start with narrow tests checking schema**, then add at least one HTTP presentation boundary test. When risks live in app-wide configuration (custom Jackson modules/mixins, global advice, security responses), add an appropriate **full-context smoke/contract test**.

**If using MockMvc:** it processes requests using mock servlet infrastructure without opening a real HTTP port. It still tests bodies generated by Spring MVC/Jackson. Not every "clean JSON response" test requires a `RANDOM_PORT` server test.

**If using Spring WebFlux:** use `WebTestClient` and `@WebFluxTest` or the corresponding integration setup; the goal remains inspecting the final payload, including nested arrays and error bodies. Do not treat `MockMvc` as usable for the reactive stack.

## 14. Special cases requiring explicit decisions

### 14.1. JSON naming strategies and aliases

Jackson may convert Java `passwordHash` into `password_hash` under a naming strategy. A test forbidding only `passwordHash` misses the renamed key.

Safeguard: **compare the entire response schema** or use a keyword/alias list matching real conventions. With an allowlist response DTO, a changed naming strategy alters the expected tree and fails the test, catching regressions.

### 14.2. Null, empty lists, and `@JsonInclude`

A property with a null value is still a property if JSON contains its key. `@JsonInclude(Include.NON_NULL)` omits nulls and `NON_EMPTY` can omit empty values depending on config; **never use these filters as a secret-hiding mechanism**.

If the contract allows `"integrations":[]` while forbidding omitting the property, positive tests must verify the empty array exists. Conversely, if an optional field must be absent rather than null, use `doesNotHaveJsonPath()`/`JsonNode.has(...) == false`.

### 14.3. `@JsonView` and role-specific serialization

`@JsonView` selects a subset of properties at serialization time. It helps when an application has an explicit view policy, yet is error-prone if a controller forgets the view, a view accidentally inherits fields, or default-view inclusion settings change.

For security-critical responses, **per-use-case DTOs** are usually easier to verify than a single domain model carrying many annotations/views. If using `@JsonView`, test each view and real HTTP responses to ensure forbidden fields do not leak.

### 14.4. Custom `ObjectMapper`, mixins, and Jackson modules

A module, custom serializer, or mixin can alter property discovery. Unit tests creating `new ObjectMapper()` are not guaranteed to match Spring Boot's configured mapper. `@JsonTest` loads matching JSON configuration in its slice; `@WebMvcTest` tests MVC serialization. When bugs stem from production-only config, add a full-context test using the application's real mapper.

Never configure a different `ObjectMapper` inside a test just to make assertions pass and claim the production contract is protected.

### 14.5. Polymorphism and custom nested objects

When a response contains `Object`, `Map<String,Object>`, sealed hierarchies, Jackson polymorphic type info, or generic wrappers, nested payloads can expose unexpected fields. Recursive JSON tree inspection and schema allowlists are far more valuable than asserting a single top-level path.

For paginated responses:

```json
{
  "items": [
    {"id":42,"displayName":"Linh"},
    {"id":43,"displayName":"Mai"}
  ],
  "total":2
}
```

Do not check only `$.items[0].passwordHash`. Inspect **every item** and every nested field. If an API returns many items, you do not need to snapshot every value, yet still traverse the full test payload and check list size.

### 14.6. Requests and responses have different lifecycles

A field like `password` may need to be deserialized from a request, yet **must never be returned in a response**. `@JsonProperty(access=WRITE_ONLY)` offers one layer of protection. Still, in real endpoints, separate `LoginRequest` from `LoginResponse`; do not reuse an input DTO holding secrets as an output DTO just because an annotation currently hides it.

Do not overlook validation errors: if an error response echoes the raw request body or rejected values, input secrets can leak even if happy-path response DTOs omit passwords.

## 15. Common mistakes

**1. Asserting only HTTP 200 and one valid field.** Tests stay green even when the serializer adds password hashes/tokens. Add negative assertions and schema allowlists.

**2. Using `doesNotExist()` when the goal is absolute key absence.** `{"passwordHash":null}` can pass. Use `doesNotHaveJsonPath()`.

**3. Using `hasNonNull("secret") == false` as proof the property is absent.** That is also true when the key is present with `null`. Use `has("secret") == false`.

**4. Checking only the first element and concluding the whole array is clean.** Traverse every element or compare the full expected JSON.

**5. Blacklisting only a few keys while missing aliases.** Compare the full DTO schema or scan both keys and sentinel values; check naming strategies.

**6. Checking only keys while missing secrets leaked under another name.** Use non-null sentinel data and inspect response values/schemas.

**7. Testing secrets only as `null` in fixtures.** `NON_NULL` can make tests false green; use **non-null** test secrets.

**8. Returning JPA entities/domain models holding credentials directly.** Adding a single field automatically widens the JSON contract. Use allowlisted DTOs.

**9. Relying on `@JsonIgnore` without testing the real `ObjectMapper`.** Annotations/configs/modules can shift during refactoring; test serialized JSON.

**10. Misreading `WRITE_ONLY` as "client can only read."** Jackson `WRITE_ONLY` means accepted on deserialization, **never serialized on output**.

**11. Using `@JsonInclude(NON_NULL)` as a security control.** Non-null values still leak.

**12. Relying on `@Schema(hidden = true)` or hiding fields in the frontend.** OpenAPI/UI does not govern runtime response serialization.

**13. Mocking the controller or serializer in HTTP tests.** Tests bypass the very MVC/Jackson pipeline under protection. Mock only collaborators outside the scope being proven.

**14. Seeing `@JsonTest` green and inferring endpoints return the right DTO.** Controllers may return another object; use `MockMvc`/`WebTestClient` tests.

**15. Forgetting error responses and framework errors.** Exception messages/validation details can echo secrets; test risky error paths.

**16. Skipping authorization.** No credential leak does not mean callers have permission to read arbitrary resource IDs.

**17. Putting real secret fixtures into tests.** Use synthetic sentinels, never production passwords/tokens; test logs and CI artifacts also need protection.

**18. Putting `@SpringBootTest` on every JSON assertion.** Start with JSON/web slices where sufficient, adding full context only for real config/wiring risks.

## 16. Checklist for verifying responses never leak sensitive data

**Before writing tests:**

- Listed all forbidden fields per endpoint/role (passwords, tokens, apiKeys, reset data, internal notes, PII…)?
- Defined **which fields are permitted** using an explicit response schema/DTO?
- Checked whether domain objects have nested collections, Maps, polymorphic types, or field aliases?
- Do test fixtures contain **non-null secret values** to catch `NON_NULL`/mapping bugs?
- Could error handlers echo exception messages or rejected values?

**While writing tests:**

- Asserted status, media type, and permitted fields so negative tests cannot false-pass?
- Used `doesNotHaveJsonPath()` or `JsonNode.has(...) == false` instead of only `doesNotExist()`/`hasNonNull`?
- Compared the **entire allowlist schema** on simple responses and inspected all nested array items?
- Used sentinels to detect secrets leaked under renamed fields?
- Tested a single account, a multi-account list, and at least one error response with risky data?
- Verified tests go through real Jackson/MVC at the boundary being proven?

**After tests pass:**

- Confirmed controllers never accidentally return entities/domain objects?
- Verified adding a new sensitive field to the domain cannot automatically enter responses?
- Added separate permission/ownership tests outside serialization tests?
- Confirmed test contexts include any custom `ObjectMapper` modules/views being protected?
- Covered other endpoints (create/update/export/admin/errors) with similar risk?
- Verified CI logs, traces, headers, cookies, and debug payloads have separate anti-leak policies?

**Conclusion:** for sensitive data, "no value" and "no field" are two different contracts. Practical protection relies on **response DTOs with explicit allowlists**, test data containing non-null secrets, and verifying **actual serialized JSON** via `@JsonTest` and **HTTP responses** via `MockMvc`/`WebTestClient`. Use `doesNotHaveJsonPath()` when a field must be **absent even if null**, check the full schema and all nested arrays/error paths, and never treat field hiding as a substitute for authorization.

## 17. Official Reference Documentation

- [Spring Framework — JsonPathResultMatchers API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/web/servlet/result/JsonPathResultMatchers.html): `doesNotHaveJsonPath()`, `doesNotExist()`, `hasJsonPath()`.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@JsonTest`, `@WebMvcTest`, and `@SpringBootTest`.
- [Jackson 2 — JsonProperty.Access](https://javadoc.io/static/com.fasterxml.jackson.core/jackson-annotations/2.18.3/com/fasterxml/jackson/annotation/JsonProperty.Access.html): `WRITE_ONLY`, `READ_ONLY`, and serialization/deserialization semantics.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): testing Spring MVC with mock HTTP requests/responses.
