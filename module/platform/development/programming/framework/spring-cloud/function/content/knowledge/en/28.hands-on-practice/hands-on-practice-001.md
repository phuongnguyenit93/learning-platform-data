# Building a Supplier, Function, and Consumer Suite for Text Processing

## 1. Practice Problem and Expected Outcomes

In the **Spring Cloud Function** (`SPRING_CLOUD_FUNCTION`) module, the goal is not just to write a few Java lambdas, but to package business logic into functions that can be **reused independently of the invocation protocol**. `FunctionCatalog` helps register and look up functions, supporting composition and message conversion; adapters can bring the same logic to HTTP, event-driven systems, or serverless environments.

In this hands-on lab, we build **Text Function Lab**: an application that receives input text, normalizes whitespace and letter casing, adds a tag, counts words, and records processed content.

Instead of creating a controller for each business operation, we register functional beans:

| Bean | Java Interface | Role | Example |
| --- | --- | --- | --- |
| `sampleText` | `Supplier<String>` | Provides sample text | `"  Spring   Cloud  Function  "` |
| `normalizeText` | `Function<String, String>` | Normalizes whitespace and converts to uppercase | `"SPRING CLOUD FUNCTION"` |
| `tagText` | `Function<String, String>` | Prepends a prefix to the result | `"[TEXT] SPRING CLOUD FUNCTION"` |
| `countWords` | `Function<String, Integer>` | Counts space-separated words | `3` |
| `auditText` | `Consumer<String>` | Records text after processing | Adds to an in-memory audit store |

Flow of using the beans:

~~~text
                  +----------------+
                  | sampleText     |  Supplier<String>
                  +--------+-------+
                           |
                           v
                  "  Spring   Cloud  Function  "
                           |
                           v
                  +----------------+
                  | normalizeText  |  Function<String,String>
                  +--------+-------+
                           |
                "SPRING CLOUD FUNCTION"
                      /         \
                     v           v
             +-----------+   +-----------+
             | tagText   |   | countWords|
             +-----------+   +-----------+
                     |
                     v
                +-----------+
                | auditText |  Consumer<String>
                +-----------+
~~~

**Expected outputs upon completion:**

1. Create a Spring Boot application containing `Supplier`, `Function`, and `Consumer` beans.
2. Look up and invoke each bean through `FunctionCatalog` instead of depending on implementation classes.
3. Chain `normalizeText|tagText` using composition and observe the result.
4. Test pure logic and test the Spring context with JUnit 5.
5. Run the web adapter and test `GET`/`POST` with `curl`.
6. Clearly recognize the limitations: the in-memory audit store is not durable, HTTP input needs validation, and having a web adapter does not mean a message broker is present.

> **Scope:** Write only **one practice application** and its related tests. Do not add Kafka/RabbitMQ, a database, or real serverless deployment yet; the lesson will show how to extend it without distorting the core logic.

## 2. Prerequisites and Version Selection

To follow the example, you need:

- JDK **17 or higher** and Maven 3.9+.
- An IDE that supports Java/Spring or a terminal.
- Localhost port `8080` available (or change it in configuration).
- `curl` to make HTTP requests, and JUnit running via Maven.

**Demonstrated compatible version pair:** Spring Boot **3.5.0** and Spring Cloud release train **2025.0.0**. Spring Cloud Function belongs to the Spring Cloud BOM; **do not mix arbitrary versions** of Boot and Cloud Function. For a new project, you should upgrade to supported patch versions while keeping a compatible release train pair. In this lab, we pin the above version pair so that the code snippets and dependencies share a consistent baseline.

You do not need to install Docker, Kafka, RabbitMQ, or a serverless CLI to complete the main hands-on lab.

## 3. Project Structure

Create the project directory `text-function-lab`:

~~~text
text-function-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/textlab/
    │   │   ├── TextLabApplication.java
    │   │   ├── TextOperations.java
    │   │   ├── TextAuditStore.java
    │   │   └── TextFunctions.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/com/example/textlab/
            ├── TextOperationsTest.java
            ├── TextFunctionCatalogTest.java
            └── TextFunctionHttpTest.java
~~~

**Package convention:** the classes below all belong to `com.example.textlab`. Placing the `@SpringBootApplication` class in the same package lets Spring scan the required beans according to standard component scanning rules.

## 4. Declaring Dependencies with Maven

Create `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>text-function-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>text-function-lab</name>
    <description>Supplier, Function, Consumer text processing lab</description>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.cloud</groupId>
                <artifactId>spring-cloud-dependencies</artifactId>
                <version>2025.0.0</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <!-- Spring Boot MVC/Tomcat for HTTP testing -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <!-- Web adapter and required Spring Cloud Function components -->
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-function-web</artifactId>
        </dependency>

        <!-- JUnit 5, SpringBootTest, MockMvc -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

In this example:

- `spring-boot-starter-web` enables a web application using Spring MVC.
- `spring-cloud-function-web` provides the mechanism to export functional beans over HTTP and integrates `FunctionCatalog`.
- The Spring Cloud BOM manages the corresponding Spring Cloud Function module versions, avoiding specifying versions individually per artifact.
- `spring-boot-starter-test` provides JUnit Jupiter, MockMvc, and the Spring Test infrastructure.

**Note:** `spring-cloud-function-web` and `spring-cloud-starter-function-web` are two different ways of declaring dependencies mentioned in the documentation; this lab intentionally uses `spring-cloud-function-web` together with the Spring MVC starter. You do not need to add both to the same project. When switching to Spring Boot 4.x, recheck the corresponding web starter name and Cloud release train rather than changing version numbers mechanically.

## 5. Creating the Spring Boot Startup Class

Create `src/main/java/com/example/textlab/TextLabApplication.java`:

~~~java
package com.example.textlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TextLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(TextLabApplication.class, args);
    }
}
~~~

`@SpringBootApplication` scans components in `com.example.textlab` and its subpackages. `TextFunctions` below uses `@Configuration`/`@Bean`, while `TextAuditStore` uses `@Component`.

## 6. Writing Framework-Independent Text Processing Logic

Create `src/main/java/com/example/textlab/TextOperations.java`:

~~~java
package com.example.textlab;

import java.util.Locale;
import java.util.regex.Pattern;

public final class TextOperations {

    private static final Pattern WHITESPACE = Pattern.compile(
            "\\s+",
            Pattern.UNICODE_CHARACTER_CLASS);

    private TextOperations() {
    }

    public static String normalize(String input) {
        if (input == null) {
            throw new IllegalArgumentException("text must not be null");
        }

        String trimmed = input.strip();
        if (trimmed.isEmpty()) {
            return "";
        }

        String collapsed = WHITESPACE.matcher(trimmed)
                .replaceAll(" ");
        return collapsed.toUpperCase(Locale.ROOT);
    }

    public static int countWords(String input) {
        String normalized = normalize(input);
        if (normalized.isEmpty()) {
            return 0;
        }

        return normalized.split(" ").length;
    }
}
~~~

This is the **pure Java business core**, with no dependency on Spring. It handles two tasks:

1. `normalize`: strips leading and trailing whitespace with `strip()`, collapses whitespace groups into a single space, and converts to uppercase using `Locale.ROOT`.
2. `countWords`: normalizes the input and counts space-separated character groups.

**Why use `Locale.ROOT`?** Calling `String.toUpperCase()` without passing a locale can be affected by the machine's default locale. When results need to be consistent between development machines and deployment environments, using `Locale.ROOT` reduces surprises.

**Why use `Pattern.UNICODE_CHARACTER_CLASS`?** With Vietnamese data or Unicode text, whitespace forms can be broader than ASCII spaces. Compiling the pattern this way allows `\\s` to handle Unicode whitespace according to Java rules. However, this example only teaches **whitespace-based word splitting**, not natural language word segmentation: punctuation remains attached to tokens, and multi-syllable Vietnamese words do not necessarily align one-to-one with semantic words.

### 6.1. Example Results

| Input | `normalize(input)` | `countWords(input)` |
| --- | --- | ---: |
| `"  Spring   Cloud  Function  "` | `"SPRING CLOUD FUNCTION"` | 3 |
| `"  học    Java  "` | `"HỌC JAVA"` | 2 |
| `"hello"` | `"HELLO"` | 1 |
| `"  "` | `""` | 0 |
| `null` | Throws `IllegalArgumentException` | Throws `IllegalArgumentException` |

We define an explicit policy for null input instead of letting a `NullPointerException` happen arbitrarily during string processing. At the HTTP/messaging boundary, converting this error into a status code or error message depends on the adapter; do not assume every `IllegalArgumentException` automatically becomes HTTP 400.

## 7. Creating a Store to Record Consumer Results

Create `src/main/java/com/example/textlab/TextAuditStore.java`:

~~~java
package com.example.textlab;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.stereotype.Component;

@Component
public class TextAuditStore {

    private final CopyOnWriteArrayList<String> entries =
            new CopyOnWriteArrayList<>();

    public void record(String value) {
        entries.add(value);
    }

    public List<String> snapshot() {
        return List.copyOf(entries);
    }

    public void clear() {
        entries.clear();
    }
}
~~~

`TextAuditStore` is a **Spring component** injected into the consumer bean. `CopyOnWriteArrayList` keeps simple add/read operations safe from concurrent access errors in the lab.

**Do not use this design for production:**

- Data is lost when the application restarts.
- Memory grows if unbounded text inputs are received.
- `CopyOnWriteArrayList` copies the backing array on writes, making it unsuitable for write-heavy streams.
- Text may contain personal data or secrets; it should not be retained indefinitely or printed verbatim to logs.

In a real application, replace it with an audit interface and an implementation backed by an appropriate store or queue, along with retention policies, access control, and error observability.

## 8. Registering Supplier, Function, and Consumer as @Bean

Create `src/main/java/com/example/textlab/TextFunctions.java`:

~~~java
package com.example.textlab;

import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Supplier;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class TextFunctions {

    private static final Logger LOGGER =
            LoggerFactory.getLogger(TextFunctions.class);

    @Bean
    public Supplier<String> sampleText() {
        return () -> "  Spring   Cloud  Function  ";
    }

    @Bean
    public Function<String, String> normalizeText() {
        return TextOperations::normalize;
    }

    @Bean
    public Function<String, String> tagText() {
        return value -> "[TEXT] " + value;
    }

    @Bean
    public Function<String, Integer> countWords() {
        return TextOperations::countWords;
    }

    @Bean
    public Consumer<String> auditText(TextAuditStore auditStore) {
        return value -> {
            auditStore.record(value);
            // In this lab, log only the character count to avoid logging raw text.
            LOGGER.info("Recorded text of {} characters",
                    value.length());
        };
    }
}
~~~

The code above demonstrates three bean types:

**Supplier:** `sampleText()` returns a zero-argument function. The framework calls `get()` to fetch the sample text when the corresponding adapter needs data.

**Function:** `normalizeText()`, `tagText()`, and `countWords()` take a `String` and return a result. Thanks to explicit generic return types, `FunctionCatalog` and adapters have target type information for conversion.

**Consumer:** `auditText()` takes a `String`, records it using `TextAuditStore`, and returns no business result. In Java, `accept(...)` returns `void`; this is **not** a `Function<String, Void>`.

### 8.1. Do Not Confuse Bean Names with Class Names

| Bean in catalog | Created by method | Java functional interface |
| --- | --- | --- |
| `sampleText` | `TextFunctions.sampleText()` | `Supplier<String>` |
| `normalizeText` | `TextFunctions.normalizeText()` | `Function<String,String>` |
| `tagText` | `TextFunctions.tagText()` | `Function<String,String>` |
| `countWords` | `TextFunctions.countWords()` | `Function<String,Integer>` |
| `auditText` | `TextFunctions.auditText(...)` | `Consumer<String>` |

Default names in `FunctionCatalog` come from the bean/`@Bean` method name. When a project has multiple functional beans, always **look up by the exact name** or select the function via adapter configuration; do not rely on the fallback mechanism intended for single-function catalogs.

### 8.2. Why Are get/apply/accept Not Called Directly Inside @Bean?

Each `@Bean` method returns **an object implementing a functional interface**, such as a lambda. It does not execute the business logic immediately when Spring creates the bean:

~~~text
Spring creates bean normalizeText
        |
        v
Bean holds Function<String,String>
        |
        v
FunctionCatalog looks up or adapter selects function
        |
        v
apply(input) is called when data arrives
~~~

This matters for `Supplier`: creating the `sampleText` bean does not mean the sample payload has already been published to Kafka or returned to a client. Only an adapter or code calling `get()` actually retrieves the value.

## 9. Configuring application.yml for the HTTP Lab

Create `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: text-function-lab
  cloud:
    function:
      single-function-fallback-enabled: false

server:
  port: 8080
~~~

Because the application has **multiple beans**, this lab uses HTTP paths matching the exact **function names**: `/sampleText`, `/normalizeText`, `/auditText`, etc. Do not set `spring.cloud.function.definition` just to pick one bean, because we want to test all functions in the same web application.

`single-function-fallback-enabled: false` prevents the case where a catalog with a single function falls back to that function for any name. This property makes testing invalid names clearer; it is **not** a toggle to enable or disable beans in the Spring context.

### 9.1. When Is spring.cloud.function.definition Needed?

When using Spring Cloud Stream, you should declare the function to bind:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeText
~~~

With the web adapter, `definition` can be used to choose which functions are exported, specify composition, or map a function to the root path. **Do not combine this illustrative configuration with the lab configuration that tests all endpoints** unless you understand the function filtering rules. The same `FunctionCatalog` can hold multiple beans, while an adapter exports or binds only what the configuration requests.

## 10. Step-by-Step Testing with Pure Java

Before bootstrapping Spring, verify `TextOperations` independently. Create `src/test/java/com/example/textlab/TextOperationsTest.java`:

~~~java
package com.example.textlab;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class TextOperationsTest {

    @Test
    void normalizesSpacesAndUppercase() {
        assertEquals("SPRING CLOUD FUNCTION",
                TextOperations.normalize(
                        "  Spring   Cloud  Function  "));
    }

    @Test
    void supportsVietnameseLetters() {
        assertEquals("HỌC SPRING CLOUD",
                TextOperations.normalize(
                        "  học   Spring\t Cloud "));
    }

    @Test
    void countsWordsAndHandlesBlankText() {
        assertEquals(3,
                TextOperations.countWords(
                        "  Spring  Cloud Function  "));
        assertEquals(0, TextOperations.countWords("  \t  "));
        assertEquals("", TextOperations.normalize("  \t  "));
    }

    @Test
    void rejectsNullExplicitly() {
        assertThrows(IllegalArgumentException.class,
                () -> TextOperations.normalize(null));
        assertThrows(IllegalArgumentException.class,
                () -> TextOperations.countWords(null));
    }
}
~~~

These tests catch bugs in the normalization and word-counting algorithms quickly without starting a web server. However, they do not prove that Spring registered the functional beans or that `FunctionCatalog` looks them up under the expected names.

## 11. Testing the Full Supplier → Function → Consumer Flow via FunctionCatalog

Create `src/test/java/com/example/textlab/TextFunctionCatalogTest.java`:

~~~java
package com.example.textlab;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.util.List;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Supplier;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest(
        classes = TextLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class TextFunctionCatalogTest {

    @Autowired
    private FunctionCatalog catalog;

    @Autowired
    private TextAuditStore auditStore;

    @BeforeEach
    void resetAudit() {
        auditStore.clear();
    }

    @Test
    void executesSupplierFunctionConsumerPipeline() {
        Supplier<String> supplier = catalog.lookup("sampleText");
        Function<String, String> normalize =
                catalog.lookup("normalizeText");
        Consumer<String> consumer = catalog.lookup("auditText");

        assertNotNull(supplier);
        assertNotNull(normalize);
        assertNotNull(consumer);

        String raw = supplier.get();
        String processed = normalize.apply(raw);
        consumer.accept(processed);

        assertEquals("SPRING CLOUD FUNCTION", processed);
        assertEquals(
                List.of("SPRING CLOUD FUNCTION"),
                auditStore.snapshot());
    }

    @Test
    void countsWordsThroughCatalog() {
        Function<String, Integer> count =
                catalog.lookup("countWords");

        assertNotNull(count);
        assertEquals(3,
                count.apply("  Spring   Cloud   Function  "));
        assertEquals(0, count.apply(" "));
    }

    @Test
    void handlesUnknownName() {
        assertNull(catalog.lookup("missingFunction"));
    }
}
~~~

**What is proven:**

- The Spring context contains the required functional beans.
- `FunctionCatalog` recognizes `Supplier`, `Function`, and `Consumer` by name.
- Each function executes with the expected types and data.
- Consumer side effects can be observed through `TextAuditStore`.

**What is not yet proven:** HTTP endpoints, JSON conversion, Spring Cloud Stream bindings, broker acknowledgments, or retry behavior in serverless environments. Those require separate adapter tests.

### 11.1. Why Look Up via Catalog Instead of Calling the Raw Bean?

~~~java
// Raw bean: just the functional object created by Spring.
Function<String, String> original =
        new TextFunctions().normalizeText();

// Function via catalog: may be wrapped by SCF to support conversion/composition.
Function<String, String> instrumented =
        catalog.lookup("normalizeText");
~~~

The two functions may share the same business behavior, but **you should not compare their runtime classes or instance identity**: `FunctionCatalog` may return a wrapper distinct from the raw bean. In integration tests, verify lookup by name and actual output values.

## 12. Composition: Chaining Functions Without Writing a New Controller

Spring Cloud Function supports composition in the form:

~~~text
normalizeText|tagText
~~~

It represents:

~~~text
Input: "  Spring   Cloud Function  "
          |
          v
normalizeText.apply(...)
          |
          v
"SPRING CLOUD FUNCTION"
          |
          v
tagText.apply(...)
          |
          v
"[TEXT] SPRING CLOUD FUNCTION"
~~~

Add the following test to `TextFunctionCatalogTest`:

~~~java
@Test
void composesTwoFunctionsInOrder() {
    Function<String, String> pipeline =
            catalog.lookup("normalizeText|tagText");

    assertNotNull(pipeline);
    assertEquals(
            "[TEXT] SPRING CLOUD FUNCTION",
            pipeline.apply("  Spring   Cloud Function  "));
}
~~~

Composition **chains sequentially**; it does not fan out the same payload to two topics or automatically create multiple endpoints. `normalizeText|tagText` remains a single function taking a string and returning a string.

### 12.1. Signatures Between Two Functions Must Be Compatible

| Composition | Evaluation |
| --- | --- |
| `normalizeText|tagText` | Valid: String → String → String |
| `normalizeText|countWords` | Valid: String → String → Integer |
| `sampleText|normalizeText` | Supplier after composition: takes no input, returns String |
| `normalizeText|auditText` | Consumer after composition: takes String and ends with a side effect |
| `auditText|normalizeText` | Invalid: a consumer produces no output payload for the subsequent function |
| `countWords|tagText` | Not directly compatible: Integer → String, requires a converter or an explicit type-converting function |

Spring Cloud Function also supports compositions involving a `Supplier` or `Consumer` with their own result contracts. To keep the lab easy to verify, we use two `Function<String,String>` beans in the main composition test, while the Supplier-to-Consumer flow is demonstrated by invoking each bean directly.

### 12.2. Practicing Composition with a Numeric Result

Add another test:

~~~java
@Test
void composedFunctionCanReturnInteger() {
    Function<String, Integer> pipeline =
            catalog.lookup("normalizeText|countWords");

    assertNotNull(pipeline);
    assertEquals(3,
            pipeline.apply("  Spring Cloud   Function "));
}
~~~

Here `countWords` normalizes its input so it can stand alone; repeating normalization in the composition is acceptable in the lab, though it can be optimized at larger scale. **Do not** define `countWords` as a `Consumer` because the business requirement needs an `Integer` result.

## 13. Testing the HTTP Adapter with MockMvc

Because the project includes `spring-cloud-function-web` and Spring MVC, functions can be exported as endpoints using the function name in the URL.

Create `src/test/java/com/example/textlab/TextFunctionHttpTest.java`:

~~~java
package com.example.textlab;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(classes = TextLabApplication.class)
@AutoConfigureMockMvc
class TextFunctionHttpTest {

    @Autowired
    private MockMvc mvc;

    @Autowired
    private TextAuditStore auditStore;

    @BeforeEach
    void resetAudit() {
        auditStore.clear();
    }

    @Test
    void exposesFunctionOverHttp() throws Exception {
        mvc.perform(post("/normalizeText")
                        .contentType(MediaType.TEXT_PLAIN)
                        .accept(MediaType.TEXT_PLAIN)
                        .content("  Spring   Cloud Function  "))
                .andExpect(status().isOk())
                .andExpect(content().string("SPRING CLOUD FUNCTION"));
    }

    @Test
    void invokesConsumerOverHttp() throws Exception {
        mvc.perform(post("/auditText")
                        .contentType(MediaType.TEXT_PLAIN)
                        .content("SPRING CLOUD FUNCTION"))
                .andExpect(status().isAccepted());

        assertEquals(
                List.of("SPRING CLOUD FUNCTION"),
                auditStore.snapshot());
    }
}
~~~

**Why does the consumer test return 202?** The Spring Cloud Function web adapter documentation describes `POST /{consumer}` with status `202 Accepted` (and often echoes the request body). This differs from `POST /{function}`, which returns the processed result with `200 OK`. Status 202 does **not** mean data was durably persisted or sent to a broker; in this lab the consumer only writes to memory.

If an HTTP test behaves differently after a version upgrade, check the web adapter documentation and the actual HTTP response rather than arbitrarily altering assertions to make the test pass.

## 14. Running the Application and Calling Each Endpoint

Inside the `text-function-lab` directory, run the tests:

~~~bash
mvn test
~~~

If all tests pass, run the application:

~~~bash
mvn spring-boot:run
~~~

The Spring Boot application should listen at `http://localhost:8080` per `application.yml`. Open a **second terminal** to try the calls below.

### 14.1. Calling the Supplier with GET

~~~bash
curl -i http://localhost:8080/sampleText
~~~

Expected HTTP status: **200 OK**. The response body contains the sample string `"  Spring   Cloud  Function  "` with its original whitespace. A `Supplier` does not take a request body.

### 14.2. Calling the Normalization Function with POST

~~~bash
curl -i -X POST http://localhost:8080/normalizeText \
  -H "Content-Type: text/plain" \
  -H "Accept: text/plain" \
  --data-binary "  Spring   Cloud Function  "
~~~

Expected response body:

~~~text
SPRING CLOUD FUNCTION
~~~

Choose `Content-Type: text/plain` because the bean accepts `String`, and choose `Accept: text/plain` to request a text response. Examples containing whitespace use `--data-binary` to preserve the exact payload sent.

### 14.3. Counting Words

~~~bash
curl -i -X POST http://localhost:8080/countWords \
  -H "Content-Type: text/plain" \
  -H "Accept: application/json" \
  --data-binary "  Spring   Cloud   Function  "
~~~

The expected business result is the integer `3`. How the adapter formats the response (plain text or a JSON scalar) depends on conversion and content negotiation; therefore, inspect `Content-Type` on the response instead of assuming it is a JSON DTO with a `count` field.

### 14.4. Calling the Consumer and Inspecting Logs

~~~bash
curl -i -X POST http://localhost:8080/auditText \
  -H "Content-Type: text/plain" \
  --data-binary "SPRING CLOUD FUNCTION"
~~~

Expect HTTP **202 Accepted** and a log line similar to:

~~~text
Recorded text of 21 characters
~~~

This is a sample log describing the processing event; length is measured via Java's `String.length()` (number of UTF-16 code units, not necessarily equal to user-perceived characters for all Unicode text). `TextAuditStore` has received one entry, though there is no HTTP endpoint to read the audit store in the lab; we verify that via catalog/MockMvc tests.

### 14.5. Calling Composition via URL

The web adapter supports invoking composition with function names separated by commas or pipes. Use a **comma** to avoid `|` being interpreted by the shell:

~~~bash
curl -i -X POST "http://localhost:8080/normalizeText,tagText" \
  -H "Content-Type: text/plain" \
  -H "Accept: text/plain" \
  --data-binary "  Spring   Cloud  Function  "
~~~

Expected result:

~~~text
[TEXT] SPRING CLOUD FUNCTION
~~~

**Windows PowerShell:** in PowerShell versions where `curl` is an alias for `Invoke-WebRequest`, use `curl.exe` or convert the commands to `Invoke-RestMethod` syntax. The trailing `\` line continuation in the examples is Unix/Git Bash shell syntax, not PowerShell's default line continuation.

## 15. Distinguishing Function Invocation from Messaging Data Streams

In this lab, a `FunctionCatalog` holds multiple beans, but **there is no message binder yet**. If you later want to attach `normalizeText` to a Spring Cloud Stream topic, you must add the appropriate dependency/binder and select the function:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeText
    stream:
      bindings:
        normalizeText-in-0:
          destination: texts.raw
          content-type: text/plain
        normalizeText-out-0:
          destination: texts.normalized
          content-type: text/plain
~~~

Diagram:

~~~text
texts.raw
   |
   v
normalizeText-in-0
   |
   v
Function<String,String>
   |
   v
normalizeText-out-0
   |
   v
texts.normalized
~~~

This configuration is **strictly an illustrative extension**; the Maven project in this lab does not yet include Spring Cloud Stream or a binder, so it cannot send to or receive from a message broker.

### 15.1. Consumers and Delivery Failures

If you move `auditText` from HTTP to messaging, the consumer keeps its `Consumer<String>` contract, but introduces additional concerns:

- Processing the same message multiple times (*at-least-once delivery*) and idempotency.
- Number of processed messages and partition/binding metrics.
- Retry/DLQ, network errors, and durable persistence.
- Sensitive data controls and audit retention periods.

Those responsibilities belong to the adapter/binder and infrastructure layer; they do not appear automatically just because you use `Consumer`. **Calling `accept(text)` successfully in a unit test does not prove that a broker acknowledged the message.**

### 15.2. Reusing the Same Business Logic in Serverless

If you deploy a text-processing function to AWS Lambda, Azure Functions, or Google Cloud Functions, the `normalizeText` bean remains `String → String` logic. However, the serverless adapter must map request/event payloads and outputs to the specific trigger contract. Having an existing reusable function does not automatically create an HTTP route, SQS event source mapping, or output queue on the platform.

## 16. Graduated Extension Exercises

### Exercise A — Collapsing Whitespace While Preserving Casing

Add a bean:

~~~java
@Bean
public Function<String, String> collapseWhitespace() {
    return input -> {
        if (input == null) {
            throw new IllegalArgumentException("text must not be null");
        }
        return input.strip().replaceAll("\\s+", " ");
    };
}
~~~

This is a small example using a standard regex; to handle Unicode whitespace like `TextOperations.normalize`, reuse the pattern declared in the business core or extract an appropriate helper. Do not duplicate normalization policies across multiple places where they might diverge.

**Task:** Test `collapseWhitespace("  Hello  world  ") == "Hello world"`. Then compose `collapseWhitespace|normalizeText` and compare with calling `normalizeText` directly.

### Exercise B — Filtering Blank Strings

Write `Function<String, String> rejectBlank` that throws `IllegalArgumentException` when the input string contains only whitespace:

~~~java
@Bean
public Function<String, String> rejectBlank() {
    return text -> {
        String normalized = TextOperations.normalize(text);
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("text must not be blank");
        }
        return normalized;
    };
}
~~~

**Task:** Test both valid input and the exception case. Then write a separate HTTP test to observe how the adapter maps the error. Do not assume `IllegalArgumentException` always becomes HTTP 400 without configuring and verifying it.

### Exercise C — Structured Output

Add a DTO and function:

~~~java
public record TextSummary(String normalized, int words) {
}

@Bean
public Function<String, TextSummary> summarizeText() {
    return raw -> new TextSummary(
            TextOperations.normalize(raw),
            TextOperations.countWords(raw));
}
~~~

**Task:** Place `TextSummary` in its own Java file or declare it as an appropriate nested record in a real project. Write a unit/catalog test for `summarizeText` and an HTTP test with `Accept: application/json` to observe the JSON response containing `normalized` and `words`. A DTO makes the output contract clearer than returning a custom delimiter-joined string.

### Exercise D — Vietnamese Text and Punctuation

Try the input:

~~~text
  Xin   chào,   Spring Cloud Function!
~~~

Observe the result:

~~~text
XIN CHÀO, SPRING CLOUD FUNCTION!
~~~

**Question:** How many tokens will the simple counter count? Why is whitespace-based token counting insufficient for handling "words" in Vietnamese linguistics? Write a test locking down the current expectation, then document its limitations before upgrading the algorithm.

### Exercise E — Composition with a Consumer

Explore `normalizeText|auditText`. By contract, composing a Function with a Consumer yields a **Consumer**: it takes a String input and ends the pipeline with a side effect only.

**Task:** Create a catalog test that looks up this composition, calls `accept(...)`, and asserts the new entry in `TextAuditStore`. Do not test by expecting a String return value because a Consumer produces no payload.

## 17. Common Issues and Troubleshooting

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| `mvn test` fails with missing Cloud Function dependencies | Misconfigured Spring Cloud BOM or artifact | Check `dependencyManagement` and Boot/Cloud versions |
| App starts but `/normalizeText` returns 404 | Web adapter not enabled, wrong bean name, or filtered by `definition` | Check dependencies, `@Bean`, logs, and export configuration |
| `FunctionCatalog.lookup(...)` returns null | Bean not scanned or looked up with wrong name | Check packages and `@SpringBootApplication` |
| `POST /normalizeText` does not receive the string as expected | Wrong content type, charset, or body | Use `text/plain` and `--data-binary` |
| `GET /sampleText` returns the same string repeatedly | Supplier is currently implemented as a constant source | Expected behavior; swap the supplier when a dynamic source is needed |
| `POST /auditText` returns 202 but records disappear after restart | Store is in-memory only | Replace with durable storage if required by the business |
| Composition `tagText|normalizeText` yields a different result from `normalizeText|tagText` | Composition is order-dependent | Assert each step and its ordering |
| `countWords` is inaccurate with punctuation or Vietnamese | Only counts whitespace-delimited tokens | Document the contract; upgrade the tokenizer when needed |
| Audit test fails intermittently | Singleton store retains entries from other tests or parallel runs | Clear state, isolate tests, avoid uncontrolled parallelism |
| Code works on machine A but fails on machine B | Incompatible JDK/Maven/Boot/Cloud versions | Check Java 17+, BOM, and dependency graph |
| Confusing consumer response with a function's HTTP 200 | `Consumer` contract returns no payload | Check web adapter behavior and 202 status |
| Sensitive text appears in logs | Uncontrolled logging of raw input | Log only safe metadata and apply retention/security policies |

### 17.1. Quick Checks in Exact Order

1. Run `java -version` to confirm the JDK version.
2. Run `mvn -version` to confirm Maven and the JDK Maven uses.
3. Run `mvn test` and resolve compile or logic errors first.
4. Verify `@Bean` methods reside in a package scanned by Spring.
5. Verify `FunctionCatalog.lookup("normalizeText")` in a context test.
6. Run `mvn spring-boot:run` and check port 8080.
7. Send a `POST` with `text/plain` and inspect the status and content type.
8. Test composition using a comma-separated URL.
9. When adopting messaging or serverless, add dedicated integration tests for the adapter rather than inferring from HTTP tests.

## 18. Lab Completion Criteria

| Criterion | Evidence Required | Verification Method |
| --- | --- | --- |
| Supplier works | `sampleText.get()` returns sample text | Catalog test or `GET /sampleText` |
| Normalization Function works | Produces `"SPRING CLOUD FUNCTION"` | `TextOperationsTest`, catalog test, HTTP test |
| Word-count Function works | Sample text produces `3` | Unit/catalog test |
| Consumer has side effect | Audit store receives a normalized value | Catalog/MockMvc test |
| Composition works | `normalizeText|tagText` yields `[TEXT] ...` | Catalog test and HTTP |
| Clear error handling | `null` input rejected, blank string follows rules | Unit test |
| Integration layers distinguished | Clearly state catalog ≠ web route ≠ message broker | Analysis of test results |
| Limitations understood | Simple whitespace count; in-memory audit; no raw text logging | Explanation and upgrade proposals |

**Key Takeaways:** `Supplier` provides data, `Function` transforms data, and `Consumer` performs side effects. Logic can be tested and invoked via `FunctionCatalog` without being tied to HTTP; composition chains functions with compatible signatures. Adapters bring the same functions into new execution environments, yet each adapter retains its own contract, data conversion, security, and delivery guarantees.

## 19. Self-Check Questions

**Question 1.** Why not call `new TextFunctions().normalizeText()` instead of using `FunctionCatalog` everywhere?

**Answer:** Direct invocation only obtains the raw lambda, bypassing bean discovery, wrappers, type conversion, and composition provided by Spring Cloud Function. Unit tests can call it directly, while framework integration tests should go through the catalog.

**Question 2.** If `sampleText` returns the same data on every GET, is that a bug in `Supplier`?

**Answer:** No. That is because the implementation intentionally returns a constant string. `Supplier` only defines the contract of taking no input and producing an output; data can be constant, dynamic, or fetched from another source depending on business needs.

**Question 3.** `countWords` returns `Integer`. Can we chain `countWords|tagText` directly without considering types?

**Answer:** You should not. An `Integer` output is not directly compatible with `tagText`'s `String` input. To compose them, add a number-to-string function or verify converters and the contract explicitly.

**Question 4.** Why does a passing `auditText.accept(...)` test not mean messages are persisted permanently?

**Answer:** The lab uses an in-memory `TextAuditStore`. `Consumer` only describes a side effect; durability depends on the implementation, database, and/or binder.

**Question 5.** Does `POST /auditText` returning 202 prove that a message broker ACKed the message?

**Answer:** No. HTTP 202 is the web adapter contract for a consumer; this lab has no broker.

**Question 6.** Do `normalizeText|tagText` and `tagText|normalizeText` necessarily produce the same output?

**Answer:** No. Composition applies transformations **in exact order**. Only when transformations commute on the given data will the results match.

**Question 7.** Does using `Locale.ROOT` completely solve Vietnamese text processing?

**Answer:** No. It makes uppercase conversion more consistent; `whitespace`-based word splitting is still not morphological analysis or natural language processing.

**Question 8.** When migrating the lab to Kafka, do we need to replace all of `TextOperations`?

**Answer:** No. You can keep the normalization logic. You need to add Spring Cloud Stream/binder, configure bindings, and design error handling and delivery semantics for Kafka.

## References

- [Spring Cloud Function — Programming Model and FunctionCatalog](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Function — Standalone Web Applications, GET Supplier/POST Function/Consumer](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/standalone-web-applications.html)
- [Spring Cloud Function — Functional Bean Definitions](https://docs.spring.io/spring-cloud-function/reference/functional.html)
- [Spring Cloud — Compatibility between release train and Spring Boot](https://spring.io/projects/spring-cloud/)
- [Spring Cloud Stream — Functional binding names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Java — Supplier, Function, Consumer API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/package-summary.html)
- [Java — Pattern.UNICODE_CHARACTER_CLASS](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html)
