# Creating an Endpoint or Task with Easily Verifiable Input and Output

## 1. Goal of the First Application

When starting the **SPRING_BOOT_NATIVE_IMAGE** module, you should pick a small feature with **deterministic inputs and predictable outputs** to test the exact same behavior on Spring Boot running on the JVM and on **GraalVM Native Image**. We will build a REST endpoint that calculates an order total. The example needs no database, accounts, or external services, making it easy to isolate issues across application code, Spring AOT, native compilation, and the runtime environment.

After this lesson, you will be able to:

1. Create a Spring Boot API accepting two integer parameters and returning JSON with the calculation, with clear input validation rules.
2. Run the API on the JVM, verifying valid results and error cases with `curl` or automated tests.
3. Build the same application into a native executable through Spring AOT and GraalVM Native Image using Maven or Gradle.
4. Re-run the exact same test suite against the native executable and compare results in a controlled way.
5. Record startup time and memory before expanding to reflection, resources, containers, and production operations.

```mermaid
flowchart LR
    A[HTTP GET + parameters] --> B[Spring MVC Controller]
    B --> C[Validate input]
    C --> D[Safe total calculation]
    D --> E[Structured JSON]
    E --> F[Test JVM and native]
```

**Example contract:** requesting `GET /api/orders/quote?unitPrice=12000&quantity=3` returns HTTP 200 with `unitPrice=12000`, `quantity=3`, `total=36000`. Monetary amounts in this example are in the **smallest integer unit defined by the system**, avoiding floating-point numbers to represent currency. The endpoint only computes a quote; it does not create a payment transaction.

## 2. Creating a Minimal Spring Boot Project

You can create the project via Spring Initializr or an equivalent project generator, choosing a Spring Boot version supported by GraalVM and Native Build Tools, a compatible Java version, and dependencies:

- **Spring Web**: build the REST controller, map requests, and return JSON.
- **Spring Boot Test**: write tests to verify JSON and HTTP status codes.

Spring Data, a database, security, or templating are not required for this example. For Maven, confirm the project has the Spring Boot Maven Plugin and the proper version of the native profile / Native Build Tools configuration. For Gradle, use the Spring Boot plugin and a compatible GraalVM Native Build Tools plugin. The build commands in later sections assume this configuration is present.

Illustrative structure:

```text
src/
  main/
    java/com/example/quote/
      QuoteApplication.java
      QuoteController.java
    resources/
      application.properties
  test/
    java/com/example/quote/
      QuoteControllerTest.java
```

File `QuoteApplication.java`:

```java
package com.example.quote;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class QuoteApplication {
    public static void main(String[] args) {
        SpringApplication.run(QuoteApplication.class, args);
    }
}
```

Place the controller in the same package or a subpackage so default component scanning detects it properly. If you change the package, re-check the component scan scope.

## 3. Designing an Endpoint with Immediately Verifiable Results

Create `QuoteController.java`:

```java
package com.example.quote;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class QuoteController {

    @GetMapping("/api/orders/quote")
    public Quote quote(
            @RequestParam long unitPrice,
            @RequestParam long quantity) {

        if (unitPrice < 0) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "unitPrice must be >= 0");
        }
        if (quantity <= 0) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "quantity must be > 0");
        }

        final long total;
        try {
            total = Math.multiplyExact(unitPrice, quantity);
        } catch (ArithmeticException ex) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "total exceeds supported range", ex);
        }

        return new Quote(unitPrice, quantity, total);
    }

    public record Quote(long unitPrice, long quantity, long total) {}
}
```

Here:

- `@RestController` turns the return value into a serialized HTTP response, typically JSON when Jackson is present via Spring Web.
- `@GetMapping` specifies the URL and HTTP method. `@RequestParam` binds query string parameters to `long` integers.
- `Math.multiplyExact` throws `ArithmeticException` when multiplication overflows `long`, preventing silent integer overflow.
- `ResponseStatusException` returns HTTP 400 for invalid inputs. The error JSON structure can vary across Spring Boot versions/configurations; this lesson only requires verifying the **HTTP status** for error cases.
- Java `record` models an immutable result type convenient for serialization. The program uses a Java version that supports `record`.

`long` is chosen over `double` so the example performs exact integer arithmetic. For real monetary systems, you must define currency, smallest unit, rounding rules, and business limits; this example focuses solely on testing the data path.

### Example Inputs and Outputs

| Request | Expected Result | HTTP status |
|---|---|---|
| `?unitPrice=12000&quantity=3` | `{"unitPrice":12000,"quantity":3,"total":36000}` | 200 |
| `?unitPrice=0&quantity=2` | `{"unitPrice":0,"quantity":2,"total":0}` | 200 |
| `?unitPrice=-1&quantity=2` | Input error | 400 |
| `?unitPrice=5&quantity=0` | Input error | 400 |
| `?unitPrice=9223372036854775807&quantity=2` | Overflow error | 400 |
| `?unitPrice=abc&quantity=2` | Parameter type conversion error | 400 |
| Missing `quantity` | Missing required parameter | 400 |

Do not validate by comparing the raw JSON string verbatim, because field ordering and whitespace formatting are not part of the contract. Checking by field name and value is more robust.

## 4. Running on the JVM and Testing Manually

Run from the Maven project directory:

```bash
./mvnw spring-boot:run
```

Or Gradle:

```bash
./gradlew bootRun
```

If using Windows, replace `./mvnw` with `mvnw.cmd` or `./gradlew` with `gradlew.bat` in the corresponding terminal.

Once the application is ready on the default port 8080, call:

```bash
curl -i "http://localhost:8080/api/orders/quote?unitPrice=12000&quantity=3"
```

Relevant part of the response:

```http
HTTP/1.1 200

{"unitPrice":12000,"quantity":3,"total":36000}
```

Actual headers, error formatting, and field ordering may differ. Next, test one more valid case and two error cases:

```bash
curl -i "http://localhost:8080/api/orders/quote?unitPrice=0&quantity=2"
curl -i "http://localhost:8080/api/orders/quote?unitPrice=-1&quantity=2"
curl -i "http://localhost:8080/api/orders/quote?unitPrice=5&quantity=0"
```

Expected statuses are 200, 400, and 400 respectively. If port 8080 is occupied, configure `server.port` or stop the other application; when comparing JVM and native, record the exact URL used.

## 5. Writing Reusable Contract Tests

Automated tests catch logic errors before spending time on a native build. The following example uses `MockMvc` on a Spring Boot application with JUnit 5.

```java
package com.example.quote;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class QuoteControllerTest {
    @Autowired MockMvc mvc;

    @Test
    void computesTotal() throws Exception {
        mvc.perform(get("/api/orders/quote")
                .param("unitPrice", "12000")
                .param("quantity", "3"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.unitPrice").value(12000))
            .andExpect(jsonPath("$.quantity").value(3))
            .andExpect(jsonPath("$.total").value(36000));
    }

    @Test
    void rejectsNegativePrice() throws Exception {
        mvc.perform(get("/api/orders/quote")
                .param("unitPrice", "-1")
                .param("quantity", "2"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsOverflow() throws Exception {
        mvc.perform(get("/api/orders/quote")
                .param("unitPrice", Long.toString(Long.MAX_VALUE))
                .param("quantity", "2"))
            .andExpect(status().isBadRequest());
    }
}
```

**Version note:** depending on the Spring Boot version, package imports and test starters for MockMvc may vary. Align APIs with your project's Spring Boot version; the rule is to keep the same requests and expected responses for both JVM and native.

Run Maven tests:

```bash
./mvnw test
```

Or:

```bash
./gradlew test
```

MockMvc tests verify the Spring MVC pipeline and application logic inside the JVM test environment. They **do not replace** making real HTTP calls to the compiled native executable.

## 6. Compiling into a GraalVM Native Image

Spring AOT analyzes bean configuration, generates code, and produces Runtime Hints for dynamic mechanisms; GraalVM Native Image then performs reachability analysis and builds a native machine executable. For this simple controller, standard Spring configuration typically includes AOT support out of the box, so no manual reflection hints are needed merely for having a `@RestController` or returning a JSON `record`.

### Maven

With a project configured with the native profile and GraalVM Native Build Tools:

```bash
./mvnw -Pnative native:compile
```

### Gradle

With a project configured with the appropriate Native Build Tools plugin:

```bash
./gradlew nativeCompile
```

Native compilation usually consumes significantly more build time and RAM than a normal JAR build. Verify the **completed build log**, exit code, and newly created executable file, rather than only seeing the `processAot` step succeed.

The artifact typically resides in `target/` for Maven or `build/native/nativeCompile/` for Gradle; the file name depends on `artifactId`, project name, and configuration. On Windows, the executable usually ends in `.exe` and requires a compatible MSVC/Windows SDK; on Linux, it requires a toolchain matching the Linux environment. Do not copy a Windows executable into a Linux image to run directly.

### Running Native and Repeating Requests

Assuming the built file is named `quote` in `target/` on Linux:

```bash
./target/quote
```

In another terminal:

```bash
curl -i "http://localhost:8080/api/orders/quote?unitPrice=12000&quantity=3"
curl -i "http://localhost:8080/api/orders/quote?unitPrice=-1&quantity=2"
curl -i "http://localhost:8080/api/orders/quote?unitPrice=9223372036854775807&quantity=2"
```

The expected results are HTTP 200 with `total=36000`, HTTP 400, and HTTP 400 respectively. Stop the JVM version before running native on the same port 8080, or choose two different ports. If you get 404, first verify the exact executable and URL; if startup fails, check profiles and logs.

## 7. Testing JVM and Native with the Same Comparison Table

| Criterion | JVM | Native | How to Conclude |
|---|---|---|---|
| HTTP status of valid request | 200 | 200 | PASS if equal |
| JSON `unitPrice`, `quantity`, `total` | Expected values | Expected values | PASS if content matches |
| Negative price or quantity equal to 0 | 400 | 400 | PASS if validation rules hold |
| Multiplication overflow | 400 | 400 | PASS if no incorrect result |
| Wrong parameter type or missing parameter | 400 | 400 | PASS if errors are handled properly |
| Application startup | No errors | No errors | PASS when server is genuinely ready |
| Startup time and RSS | Measure | Measure | Performance metrics, not contract pass/fail |

This table is a **criteria template**, not measured benchmark numbers. For integration testing, you can run a script that invokes `curl` and parses JSON with an appropriate tool across both variants. When switching only from JVM to native, do not alter the calculation or the test dataset.

When testing a native container, send the exact same requests after mapping the port and configuring the environment. If you want to add resource or reflection cases to practice compatibility, separate them into an extension step so you always retain a simple, working baseline.

## 8. Evaluating Startup and Memory Reproducibly

The module's goal is to evaluate startup time and memory benefits, while separating **functional correctness** from **performance**. Once JVM and native produce identical functional results:

1. Run each variant on the same machine or a clearly documented environment; avoid running both apps simultaneously competing for CPU and RAM.
2. Define startup as the duration from process launch until the endpoint is ready to serve, not merely when a log line appears.
3. Measure RSS/working set when stably idle and under equivalent load. Peak memory during the **build** is a separate metric, not the runtime memory required by the native application.
4. Repeat measurements multiple times and record JDK/GraalVM versions, plugins, OS, heap settings, profiles, and load to explain results.
5. Observe latency/throughput alongside RSS: a fast-starting application does not necessarily handle every load scenario better.

Template table for recording results, left blank for actual measurements:

| Metric | Spring Boot JVM | Spring Boot Native |
|---|---:|---:|
| Startup to ready | … ms | … ms |
| RSS after stabilization | … MiB | … MiB |
| Peak RSS at 100 requests/sec | … MiB | … MiB |
| p95 latency at same load | … ms | … ms |
| Peak RAM of build process | … MiB | … MiB |

Do not conclude "Native Image saves x% RAM" without data and measurement methodology. Depending on the application, Native Image can dramatically reduce startup time, but it also involves trade-offs in build time, artifact size, throughput, or library support.

## 9. Troubleshooting Common Errors

| Symptom | What to Check |
|---|---|
| HTTP 404 at `/api/orders/quote` | Whether controller package is scanned by Spring; URL and port are correct |
| HTTP 400 with `unitPrice=abc` | Expected result because Spring cannot convert the parameter to `long` |
| HTTP 500 when multiplying very large numbers | Check that `Math.multiplyExact` is used and caught to return HTTP 400 |
| AOT bean initialization error | Check `@SpringBootApplication`, component config, profiles, properties |
| Native build missing compiler/linker | Check GraalVM, C toolchain/MSVC, target OS/architecture |
| Native runtime reflection/resource error | Check Spring AOT hints, relevant libraries, and stack trace; avoid adding blanket metadata |
| Port 8080 already in use | Stop the running instance or change `server.port` |
| Native output differs from JVM | Check same code commit, config, inputs, and versions; reproduce with a minimal test |

If the native application builds successfully yet only one business flow fails, that is a runtime compatibility issue requiring dedicated investigation. A successful compilation does not guarantee every execution path and resource works, especially once a project begins using custom reflection, dynamic proxies, JNI, or libraries that generate bytecode at runtime.

## 10. Extending the Exercise

Once the minimal version works, you can increase complexity while keeping results easy to verify:

- Add a `/api/orders/discount` endpoint accepting integer `unitPrice`, `quantity`, and `discountPercent` in the range 0–100; check overflow and rounding rules.
- Read a `templates/receipt.txt` file from the classpath and return its content; verify that the resource is packaged into the native executable.
- Create a `@ConfigurationProperties` class for `maxQuantity` limits, observing how properties/configuration behave during native build and runtime.
- Package the native executable into a Linux container using a Linux pipeline, then run the same request table against the published port.

For each extension step, add corresponding JVM and native tests; document clearly which changes require Spring Runtime Hints or GraalVM metadata. Do not assume that adding a resource file or dynamic reflection call will always be analyzed automatically.

## 11. Self-Check Questions

1. Why should you choose an endpoint with deterministic inputs and outputs before introducing a database and external dependencies?
2. Why is `Math.multiplyExact` more useful than `unitPrice * quantity` in this test case?
3. Are MockMvc tests running on the JVM sufficient to conclude that the native executable serves HTTP properly? Why or why not?
4. When `spring-boot:process-aot` succeeds but `native:compile` fails, which stages do you need to inspect next?
5. Which three invalid input cases help verify that validation behaves identically on JVM and native?
6. When comparing startup time and RSS, which conditions must you hold constant or record?

**Takeaway:** your first native Spring Boot application should have a **small, verifiable HTTP contract**. Run tests on the JVM, compile via Spring AOT and GraalVM Native Image, then replay those exact requests against the native executable. Only when both are functionally correct should you measure startup and memory, then expand to reflection, resources, containers, and real-world compatibility issues.
