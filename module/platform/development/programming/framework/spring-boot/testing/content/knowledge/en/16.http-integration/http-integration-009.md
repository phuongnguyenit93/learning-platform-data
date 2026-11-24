# Distinguishing Backend HTTP Testing from Browser End-to-End Testing

## 1. Why are the two test types easily conflated?

A Spring Boot API can return the right HTTP 200 and JSON `{"sku":"SKU-7","available":5}` when tested with `MockMvc`, `TestRestTemplate`, `RestAssured`, `WebTestClient`, `curl`, or Postman. Yet that **does not prove a user can open the page, type a SKU, click a button, and see the result**. JavaScript in the browser can still call the wrong URL, mishandle errors, display the wrong JSON field, or suffer from cookie, CORS, DOM, and UI state bugs.

Conversely, a Playwright test seeing the text `SKU-7: 5 in stock` does not automatically prove the API enforces all status/header/error constraints for every input. The UI might be using mocked data, or the browser test might only exercise a happy path without verifying backend-specific contracts.

In the **Spring Boot - testing** module, under **HTTP integration**, we must separate two questions:

- **Backend HTTP testing:** When a client sends an HTTP request to Spring Boot (or when Spring MVC is simulated by test infrastructure), does the server process and return **status, headers, content type, body, and errors** per contract?
- **Browser end-to-end (E2E) testing:** When a user interacts with the **real interface** inside a browser, do JavaScript, DOM, network, backend, and visual output work together as a cohesive journey?

A high-quality strategy typically uses **both in different places**: many fast, targeted API tests; fewer browser E2E tests focused on critical user journeys.

## 2. Four testing levels to place side by side

Do not lump every "test involving HTTP" into one category:

| Level | Illustrative tools | Runs Spring context? | Real socket/server? | Real browser? | What it proves |
| --- | --- | --- | --- | --- | --- |
| Plain controller/service unit test | JUnit, Mockito, direct method calls | Optional | No | No | Java rules and collaborator coordination |
| Spring MVC HTTP boundary | `@WebMvcTest` + `MockMvc` | Yes, web slice | No | No | MVC mapping, converters, validation, responses |
| HTTP integration over real server | `@SpringBootTest(RANDOM_PORT)` + `TestRestTemplate`/`RestAssured` | Yes, typically broader | **Yes** | No | HTTP over socket, server/dispatcher/wiring, and API contract |
| Browser E2E | Playwright/Selenium/Cypress | Depends on target system | Usually yes | **Yes** | UI rendering, DOM interaction, JavaScript, network calls, and visible output |

These are **levels/scopes**, not winners-vs-losers labels. `@WebMvcTest` checks the MVC HTTP contract without opening a network socket. `@SpringBootTest(RANDOM_PORT)` tests the backend over real HTTP without launching Chrome. Playwright can test the browser against a real backend **or** mocked network; only the real-backend configuration proves browser ↔ real backend integration within the connected scope.

### Two path diagrams

HTTP testing through a real server:

~~~text
JUnit / TestRestTemplate
        |
        | HTTP request, host:port
        v
Spring Boot embedded server
        |
        v
Spring MVC / Controller / Service / Related beans
        |
        v
HTTP status + headers + body
        |
        v
Java test assertions
~~~

Browser end-to-end testing:

~~~text
Playwright / user
        |
        v
Chromium (DOM + JavaScript + cookies + browser network)
        |
        | open page, type SKU, click Check
        v
JavaScript fetch('/api/stock/SKU-7')
        |
        | HTTP over socket
        v
Spring Boot backend -> JSON response
        |
        v
JavaScript updates DOM
        |
        v
Playwright waits and asserts visible content
~~~

The two paths intersect at the backend, yet **their starting points, observed targets, and classes of bugs caught differ**.

## 3. What does backend HTTP testing answer?

By sending HTTP/MockMvc requests and inspecting responses, we can protect:

1. **Routing:** `GET /api/stock/{sku}` hits the intended controller/method.
2. **Status:** success is `200 OK`, missing is `404 Not Found`, invalid payload is `400 Bad Request`, etc. per contract.
3. **Headers:** `Content-Type`, `Cache-Control`, `Location`, `ETag`, custom headers.
4. **Body schema and values:** field `sku` is a String, `available` is a Number, error codes match.
5. **Request parsing and validation:** path/query/header/body types; malformed JSON or Jakarta validation constraints.
6. **Server-side authorization:** with real security enabled, tests prove 401/403/200 based on credentials or tokens.
7. **Backend integration:** when keeping real services/repositories/DBs, HTTP tests exercise those layers end-to-end.

**Never infer from a backend HTTP test** that buttons are visible, inputs are focusable, JS throws no errors, disabled/enabled states behave sensibly, CSS does not obscure elements, browsers persist cookies properly, or users complete the journey cleanly.

With `MockMvc`, requests pass through Spring MVC infrastructure on mock servlet objects; this is **not a real TCP request**. With `@SpringBootTest(webEnvironment = RANDOM_PORT)`, the embedded server genuinely listens on a port and an HTTP client connects over a socket. Both are backend tests, but their scopes differ.

### Choosing tools for the backend

- **`MockMvc` + `@WebMvcTest`** when the focus is mainly controllers, conversion, status/body, and fast feedback.
- **`MockMvc` + `@SpringBootTest` + `@AutoConfigureMockMvc`** when you need a broader context without opening an HTTP port.
- **`TestRestTemplate`, RestAssured, Java `HttpClient`, or server-bound `WebTestClient`** with `RANDOM_PORT` when you want real HTTP requests over a network socket.
- **`WebTestClient`** is the natural choice for Spring WebFlux; it can bind to a mock WebFlux context or a real HTTP server depending on setup.
- **Contract tests** with schema/OpenAPI or consumer-driven contracts can complement tests for service-to-service compatibility without driving a UI.

**An HTTP test can be an integration test** even without a browser. The phrase "end-to-end" should always name its **concrete boundary**: service/backend E2E is not necessarily user UI E2E.

## 4. What extra coverage does Browser E2E add?

Browser E2E typically uses Playwright, Selenium, or Cypress to drive a real browser engine, load pages, execute JavaScript, interact with the DOM, and observe what a user sees.

Bugs that backend HTTP tests easily miss:

| Bug | Can API tests still PASS? | Suitable for browser tests? |
| --- | --- | --- |
| "Check" button lacks an event listener | Yes | Yes: click and assert UI |
| Frontend calls `/api/stocks` instead of `/api/stock` | Yes | Yes: traverses real network |
| JS reads `data.count` while API returns `available` | Yes | Yes: assert displayed text |
| UI ignores `404` and spins on Loading forever | Yes | Yes: test missing branch |
| Browser omits cookies due to `SameSite`/CORS/credentials | Yes if API tests inject headers directly | Yes, when run with real origin and auth flow |
| UI button is covered by an overlay | Yes | Yes: click/actionability fails |
| Responsive CSS or layout overflows | Yes | Yes with appropriate visual/viewport assertions |
| An API returns the wrong JSON contract | API tests usually catch it | Browser test can fail too, though diagnostics are less specific |
| Bug inside transaction/repository | Caught if HTTP integration uses a real DB | Caught only if browser hits real DB and scenario exercises the bug |

**Browser E2E is not magic:** if the test calls `page.route(...)` to mock all API responses, it is testing the frontend against a **mock backend** and cannot claim to have verified real backend integration. If the database is also faked, production queries are not proven either.

There are two distinct browser testing styles, both useful:

- **Frontend-focused browser tests:** use mocked network to verify DOM/JS and edge cases quickly without backend dependencies.
- **Full-flow browser E2E:** connect real UI and real HTTP backend (with appropriate DB/test dependencies) to test journeys across system boundaries.

State clearly which style is running and do not mix them in reports.

## 5. Decision matrix: where should assertions live?

| Requirement | Preferred level | Why? |
| --- | --- | --- |
| GET returns 200 and body `available = 5` | Backend HTTP | Specific, cheap, easy to pinpoint failures |
| Error JSON has code `NOT_FOUND` | Backend HTTP | Contract relied on by all clients |
| MVC validation returns 400 | `MockMvc`/Backend HTTP | Catches handler/validation errors |
| Response has `Cache-Control: no-store` | Backend HTTP | Explicit HTTP contract |
| User types SKU and sees result on page | Browser E2E | Involves DOM, JS, and user interaction |
| UI shows "Not found" when server returns 404 | Browser E2E | Frontend error-handling logic |
| Login, cookies, redirects, logout in browser | Browser E2E + HTTP/security tests | Needs both browser state and server authorization |
| Repository saves/reads data properly | Data slice / HTTP integration with real DB | Browser tests are slow and blur DB failure causes |
| Form validates required field and shows error | Browser E2E; frontend unit/component tests | JavaScript, HTML validation, and UX |
| App works behind real reverse proxy/TLS | Environment integration/E2E on target infra | Local random port lacks real proxy/TLS |
| API compatibility for mobile / third-party clients | Contract + Backend HTTP | No browser UI involved |
| Critical purchase checkout journey | Selected browser E2E + backend/data tests | Covers both end-to-end flow and layer-specific faults |

If a rule can be cleanly proven by a unit or API test, **do not test it solely in the browser**. Browser E2E tests are slow, have many moving parts, and make root-cause isolation harder; reserve them for protecting end-to-end user-journey integration.

## 6. Consistent example: one application for both test types

We build **Stock Lookup**:

- A Spring Boot 3.5 / Java 17 backend returns stock availability.
- `index.html` is served from the application's own static resources.
- The user enters a SKU and clicks Check; JS calls the API and updates page text.
- The backend has **one fixed SKU** so results are deterministic without needing a database, OAuth server, or external network.
- The exact same backend is tested via `MockMvc`, `TestRestTemplate`, and Chromium via Playwright Java.

Contract:

| Request/action | Expectation |
| --- | --- |
| HTTP `GET /api/stock/SKU-7` | 200 JSON `{"sku":"SKU-7","available":5}` and `Cache-Control: no-store` |
| HTTP `GET /api/stock/UNKNOWN` | 404 JSON `{"code":"NOT_FOUND"}` |
| Browser opens `/`, enters `SKU-7`, clicks Check | Page shows `SKU-7: 5 in stock` |
| Browser enters `UNKNOWN` and clicks Check | Page shows `Not found: UNKNOWN` |
| Browser clicks Check with empty/whitespace input | Shows `Enter a SKU.`, does not call API |

**Intentional limitation:** the example uses a real backend and real browser, yet backend data is static in-memory. It proves **browser → HTML/JS → HTTP → controller → UI**, **not databases or external systems**. If a real system uses PostgreSQL, message queues, or OAuth, add separate integration tests for those components.

File tree:

~~~text
src/main/java/com/example/httptesting/
  StockApplication.java
  StockView.java
  ApiError.java
  StockController.java
src/main/resources/static/
  index.html
src/test/java/com/example/httptesting/
  StockMvcSliceTest.java
  StockHttpIntegrationTest.java
  StockBrowserE2ETest.java
build.gradle
~~~

All Java files use package `com.example.httptesting`. The code below is complete for building the example with Spring Boot 3.5.x; you need a generated Gradle Wrapper for the project and JDK 17+.

## 7. Complete Java backend: app, DTOs, and controller

### 7.1. Spring Boot entry point

**`src/main/java/com/example/httptesting/StockApplication.java`:**

~~~java
package com.example.httptesting;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StockApplication {
    public static void main(String[] args) {
        SpringApplication.run(StockApplication.class, args);
    }
}
~~~

### 7.2. Two JSON records

**`src/main/java/com/example/httptesting/StockView.java`:**

~~~java
package com.example.httptesting;

public record StockView(String sku, int available) {
}
~~~

**`src/main/java/com/example/httptesting/ApiError.java`:**

~~~java
package com.example.httptesting;

public record ApiError(String code) {
}
~~~

Spring Boot 3.5 with `spring-boot-starter-web` and Jackson serializes/deserializes these Java records out of the box. Record `equals` compares component-by-component, which is handy in HTTP integration assertions.

### 7.3. REST controller with two clear branches

**`src/main/java/com/example/httptesting/StockController.java`:**

~~~java
package com.example.httptesting;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/stock")
public class StockController {

    @GetMapping(
            value = "/{sku}",
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<?> getStock(@PathVariable String sku) {
        if ("SKU-7".equals(sku)) {
            return ResponseEntity.ok()
                    .cacheControl(CacheControl.noStore())
                    .body(new StockView("SKU-7", 5));
        }

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError("NOT_FOUND"));
    }
}
~~~

This controller hits no database and has no service/repository to mock. To highlight test boundaries cleanly, the code stays minimal: success carries `Cache-Control: no-store`, while a missing SKU returns 404 with an explicitly designed JSON error body.

**Do not assume** every Spring Boot application automatically returns `{"code":"NOT_FOUND"}`. That contract is defined by this example's code. In systems using `@ControllerAdvice`, `ProblemDetail`, or another error envelope, tests must assert the format published by that application.

### 7.4. Running manually to inspect the API

When running the application via Gradle:

~~~bash
./gradlew bootRun
~~~

Without overriding `server.port`, the Boot servlet server normally listens at `http://localhost:8080`. You can test with:

~~~bash
curl -i http://localhost:8080/api/stock/SKU-7
curl -i http://localhost:8080/api/stock/UNKNOWN
~~~

Depending on the server, client, and configuration, headers such as `Date`, `Transfer-Encoding`, `Connection`, or header ordering can vary. The **contractually required parts of this example** are status 200/404, matching JSON bodies, and `Cache-Control: no-store` on success; never treat a curl transcript containing dynamic headers as an exact byte-for-byte golden output.

When running tests with `RANDOM_PORT`, **never hardcode 8080**: tests receive a dynamic port from Spring Boot, as shown in Sections 10 and 11.

## 8. HTML + JavaScript frontend: the part only a browser executes fully

**File `src/main/resources/static/index.html`:**

~~~html
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Stock Lookup</title>
</head>
<body>
  <h1>Stock Lookup</h1>

  <form id="stock-form">
    <label for="sku">SKU</label>
    <input id="sku" type="text" data-testid="sku-input">
    <button type="submit" data-testid="lookup-button">Check</button>
  </form>

  <p role="status" aria-live="polite"
     data-testid="stock-result"></p>

  <script>
    const form = document.getElementById("stock-form");
    const output = document.querySelector(
      '[data-testid="stock-result"]'
    );

    form.addEventListener("submit", async function (event) {
      event.preventDefault();

      const sku = document.getElementById("sku").value.trim();
      if (!sku) {
        output.textContent = "Enter a SKU.";
        return;
      }

      output.textContent = "Loading...";

      try {
        const response = await fetch(
          "/api/stock/" + encodeURIComponent(sku),
          { headers: { "Accept": "application/json" } }
        );

        if (response.status === 404) {
          output.textContent = "Not found: " + sku;
          return;
        }

        if (!response.ok) {
          throw new Error("HTTP " + response.status);
        }

        const stock = await response.json();
        output.textContent =
          stock.sku + ": " + stock.available + " in stock";
      } catch (error) {
        output.textContent = "Request failed.";
      }
    });
  </script>
</body>
</html>
~~~

Spring Boot serves `static/index.html` at the root path `/` via Spring MVC auto-configuration's welcome-page rules. The browser loads the page, builds the DOM, executes the script, and `fetch(...)` sends a same-origin request to the API.

Intentional details:

- Uses `data-testid` for test locators resilient to CSS changes.
- `event.preventDefault()` prevents form submission from reloading the page.
- `trim()` strips whitespace from input.
- `encodeURIComponent(sku)` encodes the SKU as a URL path segment per JS rules; backends must still validate inputs in real deployments.
- `response.status === 404` renders the not-found message instead of letting JSON parsing or network errors mask it.
- `response.ok` catches other failure statuses.
- `output.textContent` avoids injecting unescaped response text as HTML; the demo never uses `innerHTML`.
- `role="status"` and `aria-live="polite"` denote a live status region, though by themselves they **do not replace comprehensive accessibility testing**.

An HTTP test calling only `GET /api/stock/SKU-7` **never executes** this JavaScript. Even an HTTP test calling `GET /` and receiving the HTML still does not prove the event listener works, data gets fetched, or DOM text updates properly.

## 9. First test: `@WebMvcTest` + `MockMvc`, no socket

**File `src/test/java/com/example/httptesting/StockMvcSliceTest.java`:**

~~~java
package com.example.httptesting;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(StockController.class)
class StockMvcSliceTest {
    @Autowired
    MockMvc mvc;

    @Test
    void knownSku_returns200JsonAndCacheControl() throws Exception {
        mvc.perform(get("/api/stock/SKU-7")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        HttpHeaders.CACHE_CONTROL, "no-store"
                ))
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON
                ))
                .andExpect(jsonPath("$.sku").value("SKU-7"))
                .andExpect(jsonPath("$.available").value(5));
    }

    @Test
    void unknownSku_returns404ErrorJson() throws Exception {
        mvc.perform(get("/api/stock/UNKNOWN")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isNotFound())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON
                ))
                .andExpect(jsonPath("$.code").value("NOT_FOUND"));
    }
}
~~~

**Two things proven:** Spring MVC routes properly and the real controller returns the expected status/headers/body; Jackson's message converter produces valid JSON. It does not open a real HTTP socket, launch a browser, or run JS from `index.html`.

If a controller depends on a `@Service` excluded from the web slice, use `@MockitoBean` matching your Spring Framework version to provide a mock bean in the context; **never mock the controller under test**. Here the controller has no dependencies, so no mock is needed.

## 10. Second test: backend HTTP integration over a real port

**File `src/test/java/com/example/httptesting/StockHttpIntegrationTest.java`:**

~~~java
package com.example.httptesting;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class StockHttpIntegrationTest {

    @Autowired
    TestRestTemplate http;

    @Test
    void knownSku_overHttp_returns200TypedJsonAndCacheHeader() {
        ResponseEntity<StockView> response = http.getForEntity(
                "/api/stock/SKU-7",
                StockView.class
        );

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals(
                new StockView("SKU-7", 5),
                response.getBody()
        );

        MediaType contentType = response.getHeaders().getContentType();
        assertNotNull(contentType);
        assertTrue(contentType.isCompatibleWith(MediaType.APPLICATION_JSON));

        assertEquals(
                "no-store",
                response.getHeaders().getFirst(HttpHeaders.CACHE_CONTROL)
        );
    }

    @Test
    void unknownSku_overHttp_returns404TypedError() {
        ResponseEntity<ApiError> response = http.getForEntity(
                "/api/stock/UNKNOWN",
                ApiError.class
        );

        assertEquals(HttpStatus.NOT_FOUND, response.getStatusCode());
        assertEquals(
                new ApiError("NOT_FOUND"),
                response.getBody()
        );
    }

    @Test
    void homepageOverHttp_returnsHtmlButDoesNotExecuteScript() {
        ResponseEntity<String> response = http.getForEntity(
                "/", String.class
        );

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertNotNull(response.getBody());
        assertTrue(response.getBody().contains(
                "data-testid=\"sku-input\""
        ));

        MediaType contentType = response.getHeaders().getContentType();
        assertNotNull(contentType);
        assertTrue(contentType.isCompatibleWith(MediaType.TEXT_HTML));
    }
}
~~~

### Why is this a real HTTP integration test?

- `@SpringBootTest(webEnvironment = RANDOM_PORT)` starts an embedded servlet HTTP server on an available port.
- In Spring Boot **3.5**, a `TestRestTemplate` configured for the embedded server can be `@Autowired` into the test. Relative URLs like `"/api/stock/SKU-7"` go to the test server, not a mock `MockHttpServletRequest`.
- `ResponseEntity<T>` lets you assert **status, headers, and deserialized body** together.
- `TestRestTemplate` is suited for checking 4xx/5xx: it does not throw exceptions by default on HTTP 404 like some `RestTemplate` setups.
- Checking that `GET /` returns HTML proves only that **the server serves the HTML file**, not that a browser executes the script.

**The third test's takeaway is crucial:** `response.getBody().contains("data-testid=...")` proves the HTML source contains the marker. However, a Java HTTP client does not build a DOM, execute event listeners, or fire `fetch` upon clicking a button. That exact gap is what browser E2E addresses.

If you are using Spring Boot **4.x**, REST test client modules/packages have changed; verify against your version's reference. The code in this lesson is pinned to **Spring Boot 3.5.16** for consistent imports.

### Is `@LocalServerPort` mandatory with `TestRestTemplate`?

Not when using relative URLs as shown above: Boot configures the test client with the server port. However, an external tool like Playwright needs the full URL; in that case use `@LocalServerPort` and assemble host/port at runtime.

### Transactions when testing over real HTTP

If a backend test writes data via HTTP requests running on a separate thread, `@Transactional` on the test method **does not automatically roll back** server-created transactions. This example only performs GETs over immutable data, so no reset is needed. In apps with POST/PUT/DELETE, create test-specific data with reliable cleanup, test across the right transaction boundaries, or reset the DB between runs.

## 11. Third test: Playwright Java with a real Chromium browser

This is the test layer an HTTP client cannot replace: launching a browser, loading the page, typing input, clicking, letting JavaScript call the HTTP backend, and waiting for DOM updates.

### 11.1. Browser end-to-end test

**File `src/test/java/com/example/httptesting/StockBrowserE2ETest.java`:**

~~~java
package com.example.httptesting;

import com.microsoft.playwright.Browser;
import com.microsoft.playwright.BrowserType;
import com.microsoft.playwright.Page;
import com.microsoft.playwright.Playwright;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static com.microsoft.playwright.assertions.PlaywrightAssertions.assertThat;

@Tag("browser-e2e")
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class StockBrowserE2ETest {

    @LocalServerPort
    int port;

    private void withPage(java.util.function.Consumer<Page> scenario) {
        try (Playwright playwright = Playwright.create()) {
            Browser browser = playwright.chromium().launch(
                    new BrowserType.LaunchOptions().setHeadless(true)
            );

            try {
                Page page = browser.newPage();
                page.navigate("http://127.0.0.1:" + port + "/");
                scenario.accept(page);
            } finally {
                browser.close();
            }
        }
    }

    @Test
    void userCanLookUpKnownSkuAndSeeStock() {
        withPage(page -> {
            page.getByTestId("sku-input").fill("SKU-7");
            page.getByTestId("lookup-button").click();

            assertThat(page.getByTestId("stock-result"))
                    .hasText("SKU-7: 5 in stock");
        });
    }

    @Test
    void userSeesNotFoundForUnknownSku() {
        withPage(page -> {
            page.getByTestId("sku-input").fill("UNKNOWN");
            page.getByTestId("lookup-button").click();

            assertThat(page.getByTestId("stock-result"))
                    .hasText("Not found: UNKNOWN");
        });
    }

    @Test
    void blankSkuShowsValidationMessageBeforeFetch() {
        withPage(page -> {
            page.getByTestId("sku-input").fill("   ");
            page.getByTestId("lookup-button").click();

            assertThat(page.getByTestId("stock-result"))
                    .hasText("Enter a SKU.");
        });
    }
}
~~~

In each test, `withPage` launches a headless Chromium browser and a fresh page using the dynamic URL from `@LocalServerPort`. `page.navigate(...)` loads the **real HTML** from Spring Boot; `fill` types text; `click` triggers the form event; JavaScript `fetch` calls the API; and Playwright's `assertThat(locator).hasText(...)` automatically waits until the DOM displays the expected text or times out.

**Never use `Thread.sleep(2000)`** to wait for the network. Playwright provides auto-waiting for actionability and auto-retrying assertions, making tests far less sensitive to machine speed. When other scenarios require waiting, wait on meaningful DOM/network conditions rather than sleeping arbitrarily.

### 11.2. Analyzing the three cases

| Case | What does the browser do? | Backend involved? | What the browser test proves |
| --- | --- | --- | --- |
| Valid SKU | Types `SKU-7`, clicks Check | Yes, GET 200 + JSON | UI calls the right API, parses `available`, and renders result |
| Missing SKU | Types `UNKNOWN`, clicks | Yes, GET 404 | JS handles error status and renders message |
| Blank input | Types whitespace, clicks | No API call needed per JS | Client-side validation renders prompt |

The third case **cannot prove by UI text alone that the backend received zero requests**; JavaScript code shows an early return, yet if an assertion must enforce zero network calls, observe requests via Playwright route/request listeners or unit-test the JS/component directly. Never extrapolate beyond what the assertion actually measures.

### 11.3. Why can Browser E2E catch bugs missed by HTTP tests?

Suppose the frontend accidentally writes:

~~~javascript
output.textContent =
  stock.sku + ": " + stock.count + " in stock";
~~~

The backend still returns `available: 5`, so `StockHttpIntegrationTest` continues to PASS. Yet the browser renders `SKU-7: undefined in stock`, causing `userCanLookUpKnownSkuAndSeeStock` to FAIL. That clearly demonstrates the value of a browser E2E test.

If someone deletes the event listener in `index.html`, HTTP GETs for the page and API still PASS; the browser click test sees no expected output. If an overlay covers the button or blocks clicks, Playwright catches an interaction failure that `TestRestTemplate` never sees.

### 11.4. Does this browser test prove the database?

**No.** Both the backend and HTML are real in the demo, yet the backend returns fixed values from the controller. To prove a production flow through a database, replace the demo data with real repositories/test DBs, seed isolated data, and clean up afterward. Calling this test "browser-to-backend E2E for the Stock Lookup demo" is much more accurate than "full production system E2E".

## 12. Full Gradle build: separating fast tests from browser tests

A maintainable setup runs backend slice + HTTP integration tests under `./gradlew test`, while running browser E2E in a dedicated task (e.g., `browserE2eTest`). This separation lets CI run fast tests frequently and run browser tests in a stage equipped with browser binaries.

**`build.gradle` (Groovy DSL, standalone example):**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'com.microsoft.playwright:playwright:1.64.0'
}

tasks.named('test', Test) {
    useJUnitPlatform {
        excludeTags 'browser-e2e'
    }
}

tasks.register('installChromium', JavaExec) {
    group = 'verification'
    description = 'Install Chromium expected by Playwright Java'
    classpath = sourceSets.test.runtimeClasspath
    mainClass = 'com.microsoft.playwright.CLI'
    args 'install', 'chromium'
}

tasks.register('browserE2eTest', Test) {
    group = 'verification'
    description = 'Run browser E2E scenarios using Chromium'
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
    useJUnitPlatform {
        includeTags 'browser-e2e'
    }
    shouldRunAfter tasks.named('test')
}
~~~

This is a **complete build file for the example's core dependencies**. The project still needs a working Gradle Wrapper, appropriate Gradle settings, and Maven Central access to download dependencies. Spring Boot `3.5.16` and Playwright Java `1.64.0` are pinned versions matching the lesson's APIs/imports.

**Install the browser binary once for the Playwright version in use:**

~~~bash
./gradlew installChromium
~~~

**Run both groups:**

~~~bash
./gradlew test
./gradlew browserE2eTest
~~~

**Run a specific class when debugging:**

~~~bash
./gradlew test --tests "com.example.httptesting.StockHttpIntegrationTest"
./gradlew browserE2eTest --tests "com.example.httptesting.StockBrowserE2ETest"
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat installChromium
.\gradlew.bat test
.\gradlew.bat browserE2eTest
~~~

### Prerequisites for E2E that cannot be skipped

- **Java 17+**, a Gradle version compatible with Spring Boot plugin 3.5, dependencies, and the Chromium binary managed by the **same Playwright version**.
- Linux CI runners may need extra OS libraries for the browser. Refer to Playwright docs for `install --with-deps chromium` or use a suitable CI image; `installChromium` alone installs only the browser binary and **does not guarantee all OS dependencies exist**.
- Never run browser tests against production. Use a test instance and dummy data; ensure tests never send real emails or payments.
- For UI E2E with user accounts, use least-privilege test accounts, manage secrets through CI, and avoid logging tokens or committing credentials to the repo.
- When tests run in parallel, never share mutable accounts/data that cause contention. `RANDOM_PORT` avoids port collisions, yet **does not** resolve database or test-tenant collisions.

The sample tests do not call `System.out.println`, so there is **no fixed application stdout**. Gradle/JUnit and Playwright log formats vary. Because this is Spring Boot + Playwright/JUnit code, you cannot compile and run it with bare `javac StockBrowserE2ETest.java` without the dependencies and browser binary.

## 13. Interpreting results accurately

Several common cases lead to over-generalization:

### 13.1. HTTP 200 does not guarantee UI success

If `StockHttpIntegrationTest` PASSES while Playwright FAILS, the cause may be frontend issues such as selectors, JS `fetch`, rendering, browser state, or network policies. **Do not alter the backend API to turn UI tests green** when the API contract is right and the frontend is misreading it.

### 13.2. Browser E2E PASS does not guarantee full API coverage

A happy-path browser run only proves "this user journey works with this dataset". It does not cover all status codes, pagination, ETags, authentication edge cases, validation rules, or database states. Use API tests for broad contract coverage.

### 13.3. MockMvc does not use sockets

`MockMvc` still runs MVC mappings, filters, converters, and handlers inside test infrastructure, yet skips the TCP/network stack and does not prove TLS or external proxy config. To test over sockets, use `RANDOM_PORT` with an HTTP client; to test browser behavior, use browser automation.

### 13.4. A browser test mocking the network is not full E2E

Playwright provides `page.route(...)` to intercept and stub responses. Such tests are great for frontend isolation, yet **the real API server may never be called**. Label its name/scope clearly, such as `frontend-browser-with-mocks`, instead of claiming full-system integration verification.

### 13.5. E2E depends on the actual runtime environment

Real projects may use a separate frontend dev server, reverse proxies, auth cookies, `SameSite`, CORS, and HTTPS. The demo is **same-origin** because Boot serves both HTML and the API. That does not prove a cross-origin deployment has configured CORS/cookies properly. If production uses separate domains, test in an equivalent setup.

### 13.6. `@Transactional` on the test client does not roll back server requests

With `@SpringBootTest(RANDOM_PORT)`, HTTP requests to the server run on a different thread/transaction from the test method. Even if the test method uses `@Transactional`, server-side transactions do not roll back automatically with the client test transaction. Seed/clean up via APIs, test DBs, fixture isolation, or intentional database resets.

## 14. Organizing the suite to be both fast and trustworthy

An effective strategy partitions tests by **failure target**:

| Group | Primary goal | How often / when to run? |
| --- | --- | --- |
| Unit tests | Pure Java data/business rules | Every build/commit |
| MVC slice / JSON / validation | HTTP contract right at the web boundary | Every build/commit |
| HTTP integration with real server | Server startup, wiring, API contract over socket | Frequent CI runs |
| Browser component/DOM with mock API | UI rendering, interactions, handling stubbed responses | Frontend CI as needed |
| Full-flow browser E2E | User journeys across selected real services | Smoke tests, key PRs, pre-release |
| Staging/proxy/network E2E | TLS, gateways, cross-origin, cookies, deployment integration | Managed staging environments |

No single fixed ratio fits every team. **Cover broadly with cheap, targeted tests; be selective with resource-heavy E2E tests.** When a bug only manifests in the browser, add a browser test for that user journey; when a JSON schema breaks, prefer an HTTP test that pinpoints it immediately.

### Keeping test data independent

- Deterministic data: create dedicated SKUs/test users with explicit seeding, avoiding dependencies on other tests' data.
- If a test creates data, tear it down; cleanup should run even when assertions fail.
- Avoid relying on test class execution order; each test is an independent scenario.
- When using databases/containers, wait for readiness via health checks rather than fixed `Thread.sleep`.
- When running multiple parallel workers, tag data with test IDs/namespaces to prevent collisions.

### Browser flakiness: fixing root causes

- Use semantic locators (`getByRole`, `getByLabel`, `getByTestId`) instead of brittle DOM-order CSS selectors or pixel coordinates.
- Wait for required states using auto-retrying assertions; avoid fixed sleeps.
- Separate network timeouts from assertion timeouts; choose deliberate thresholds for CI.
- On failures, capture screenshots/traces/videos **if CI workflows permit**; keep sensitive data out of traces.
- Avoid sharing a single browser page/session across tests without strict isolation.
- Separate visual screenshot tests from functional E2E if snapshots are sensitive to fonts, OS, and viewports.
- Pin browser versions via Playwright; re-install browsers whenever upgrading the dependency.
- Keep the E2E suite lean and focused on catching the most critical user-facing regressions.

## 15. Extending to login, sessions, cookies, CSRF, and security

For systems with Spring Security, the two testing layers complement each other:

**Backend HTTP security tests** prove:

- Requests lacking a valid token/cookie are rejected with 401 or 403 per config.
- Insufficient roles are rejected even when calling the API directly without the UI.
- CSRF protection works at the HTTP boundary.
- Cookie attributes, redirect `Location`, and cache headers satisfy the contract.
- The server does not leak data across accounts/tenants.

**Browser E2E security tests** prove:

- Users can log in via the form or test provider and land on the expected page.
- Sessions/cookies persist across in-browser navigation per browser rules.
- Logout clears session state in the UI and prevents accessing auth-protected features.
- Login redirects and protected routes work through real JS/routers.
- CORS/preflight, `SameSite`, `Secure`, mixed content, or third-party cookie policies do not break supported flows.

**Never use browser E2E as the sole substitute for security tests.** A UI can hide a button while the backend leaves the API wide open; server-side authorization must be tested directly. Conversely, a backend accepting a token does not guarantee the browser sends cookies/tokens properly in page context.

When using `page.route` to fake authentication responses or bypass auth in browser tests, label them explicitly as UI-isolation tests; never present them as complete login/security E2E verification.

## 16. A debugging scenario based on test signals

Suppose CI reports:

~~~text
StockMvcSliceTest              PASS
StockHttpIntegrationTest       PASS
StockBrowserE2ETest            FAIL
Expected: SKU-7: 5 in stock
Actual:   Request failed.
~~~

This is an **illustrative diagnostic example**, not actual stdout captured during this session.

How to trace the root cause:

1. **Backend contract:** The HTTP tests already proved the API serves the right data on the test server. Do not assume the API is bug-free everywhere, yet check the UI layer first.
2. **URL/browser origin:** check whether the browser navigated to `http://127.0.0.1:<port>/` and JS called `/api/stock/SKU-7`.
3. **Network response:** inspect which browser request failed, its status, redirects, CORS errors, or JS exceptions.
4. **JS parsing/rendering:** check if the frontend read `stock.available` or mistakenly read `stock.count`; inspect console errors.
5. **Selectors and timing:** verify locator `data-testid="stock-result"` exists and see what condition auto-wait was waiting on.
6. **Environment:** check whether browser binaries/OS libraries, ports, proxies, or CI settings differ from local.
7. **Narrow the regression test:** if it is pure rendering, add a frontend/component test; if it is HTTP negotiation, add a focused backend test.

If the reverse happens — the browser test PASSES while a backend 404 error-JSON test FAILS — verify the API contract and whether the browser actually exercised that error branch. A test never covers paths it did not execute.

## 17. Common misconceptions and mistakes

1. **Calling every `@WebMvcTest` an end-to-end test.** It opens neither a browser nor a socket. **Fix:** call it a web slice / MockMvc test.
2. **Calling every `@SpringBootTest(RANDOM_PORT)` a browser E2E test.** It starts a real server, yet Java HTTP clients still lack DOM/JS. **Fix:** distinguish it as backend HTTP integration.
3. **Testing only status 200 and claiming the API works.** Does not prove body/headers/errors. **Fix:** assert essential contract details.
4. **Testing only a browser happy path and claiming full backend coverage.** Misses edge API branches. **Fix:** supplement with HTTP contract tests.
5. **Mocking all network calls in Browser E2E yet reporting full-stack PASS.** Backend was never exercised. **Fix:** label it mocked-network E2E / frontend test.
6. **Calling controller methods directly and claiming HTTP serialization was tested.** Bypasses message converters and request mapping. **Fix:** use MockMvc or a real HTTP client.
7. **Hardcoding `localhost:8080` in `RANDOM_PORT` tests.** CI uses dynamic ports. **Fix:** use `@LocalServerPort` or `TestRestTemplate` relative URLs.
8. **Using `Thread.sleep` in browser tests.** Timing is unstable. **Fix:** Playwright auto-waiting and locator assertions.
9. **Using DOM/CSS-coupled locators.** Styling refactors break tests. **Fix:** prefer roles, labels, or stable test IDs.
10. **Skipping browser binary installation for the Playwright version.** Tests fail to launch the browser. **Fix:** run the install task whenever updating the dependency.
11. **Running tests against production.** Risks mutating live data, sending real emails, or charging payments. **Fix:** isolated environments/test accounts with bounded side effects.
12. **Sharing mutable accounts/data across parallel browser tests.** Tests flake due to contention. **Fix:** isolate and clean up data.
13. **Assuming client `@Transactional` rolls back real server commits.** Transactions run on different threads. **Fix:** reset data across the right boundary.
14. **Ignoring browser CSRF/cookie tests in cross-origin deployments.** Non-browser HTTP clients may hide browser restrictions. **Fix:** run browser E2E at a matching origin/environment.
15. **Seeing a UI error and immediately altering the backend.** It might just be a JS parse/render bug. **Fix:** diagnose layer-by-layer from API contract to browser network/DOM.
16. **Expecting visual layout proof from HTTP tests.** JSON/HTML source does not prove CSS rendering. **Fix:** use browser functional/visual tests.
17. **Assuming Playwright equals complete accessibility verification.** DOM interactions do not replace an A11y audit. **Fix:** add dedicated a11y assertions/audits when required.
18. **Browser test passes with mocked responses while the real backend route changed.** UI is decoupled from the real API. **Fix:** keep at least one unmocked full-flow smoke test.
19. **Putting all browser tests into the default unit test task.** Makes CI heavy and complicates browser management. **Fix:** split by tags/tasks/stages.
20. **Forgetting deployment topology:** reverse proxies, TLS, or CDNs differ from localhost. **Fix:** run staging tests for deployment infrastructure that must be protected.

## 18. Checklist for choosing the right level and writing assertions

Before writing a test, answer:

- [ ] Is the target **Java logic**, **HTTP responses**, **backend wiring/networking**, or a **browser user journey**?
- [ ] Is a Spring context needed? If not, use plain JUnit.
- [ ] Is a real HTTP socket needed? If not, consider `MockMvc`/slices.
- [ ] Are DOM/JavaScript/cookies/viewports involved? If yes, use a browser test.
- [ ] Does the test mock APIs or databases? If so, name and scope conclusions around what was faked.
- [ ] Do backend HTTP tests assert **status, headers, content type, body**, business errors, and required validation?
- [ ] Do browser E2E tests interact through stable locators and assert user-visible content?
- [ ] Do browser tests wait via retrying assertions instead of `Thread.sleep`?
- [ ] Does the test environment use appropriate databases, test accounts, cleanup, and secret management?
- [ ] Is `RANDOM_PORT` paired with dynamic ports instead of hardcoded 8080?
- [ ] Is security tested at both the server boundary and browser when journeys involve auth?
- [ ] Is there an E2E smoke check connecting the real frontend and real backend for key journeys?
- [ ] On failures, are HTTP logs and browser traces sufficient to isolate the faulty layer?
- [ ] Do tests run independently without relying on execution order or leftover state?
- [ ] Does CI install browser binaries/OS dependencies and pin the Playwright version?

### Conclusion

**Backend HTTP testing** answers: *"When the API is called, does Spring Boot respond per contract and integrate properly across loaded backend layers?"* **Browser E2E** answers: *"Can a user complete the UI journey with a real browser, JavaScript, and connected backends?"*

Never replace one group with the other. Write **many unit/API tests for detailed rules**, add **HTTP integration tests through a real server** where networking/wiring matters, and choose a **small, high-value set of browser E2E tests** for critical user-facing experiences.

### References

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — TestRestTemplate API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/web/client/TestRestTemplate.html)
- [Spring Boot — Embedded Web Servers and @LocalServerPort](https://docs.spring.io/spring-boot/how-to/webserver.html)
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)
- [Playwright Java — Installation](https://playwright.dev/java/docs/intro)
- [Playwright Java — Assertions and auto-retrying](https://playwright.dev/java/docs/test-assertions)
- [Playwright Java — Browser installation](https://playwright.dev/java/docs/browsers)
- [Playwright Java — Locators](https://playwright.dev/java/docs/locators)