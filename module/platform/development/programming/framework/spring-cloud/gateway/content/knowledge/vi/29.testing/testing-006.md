# MockMvc hoặc client HTTP cho Gateway Server Web MVC

## 1. Vì sao cần phân biệt MockMvc và client HTTP thật?

**Spring Cloud Gateway** thường là điểm vào của microservices: chọn route dựa trên path, method hoặc header; chạy các filter để đổi đường dẫn/header; phân giải service bằng `lb://`; xác thực, giới hạn lưu lượng, retry, circuit breaker, TLS và quan sát request. Một lỗi nhỏ ở cổng vào có thể làm nhiều backend nhận sai request, lộ thông tin người dùng hoặc trả sai HTTP status.

Riêng **Spring Cloud Gateway Server Web MVC** chạy trên **Spring MVC, Servlet API và WebMvc.fn**. Nó không dùng cùng request lifecycle và hợp đồng `GatewayFilterChain.filter(exchange)` trả `Mono<Void>` như Gateway Server WebFlux. Bởi vậy, chọn đúng công cụ kiểm thử cũng là một phần của thiết kế kiến trúc:

- **`MockMvc`** gửi request vào hạ tầng Spring MVC bằng **mock Servlet request/response**, không mở một cổng HTTP thật cho inbound request. Nó phù hợp để kiểm tra mapping, controller, Servlet security, validation, status và một phần route/filter behavior.
- **HTTP client kết nối tới cổng thật** như JDK `HttpClient`, `RestClient` hoặc một test HTTP client khác gửi request qua socket tới **Servlet container thực**. Nó hữu ích khi cần xác minh inbound HTTP transport, proxy outbound, TLS, encoding, streaming, cancellation và cấu hình reverse proxy.
- **Backend stub** (HTTP server giả hoặc mock server) giúp kiểm tra **upstream thực sự đã nhận method/path/header/body nào**, trả status nào và có bao nhiêu lần gọi.

Điểm quan trọng: **MockMvc không tự biến HTTP client outbound của Gateway thành mock**. Nếu `HandlerFunctions.http()` của Gateway MVC gọi Catalog qua mạng, chạy MockMvc mà không cấu hình backend stub vẫn có thể tạo một request HTTP thật và thất bại vì backend không tồn tại.

Bài “**MockMvc hoặc client HTTP cho Gateway Server Web MVC**” thuộc chương **Kiểm thử** của module **SPRING_CLOUD_GATEWAY**, với mục tiêu biến các khái niệm route predicates, filter chain, rewrite/header, discovery, security, retry và TLS thành những **assertions có bằng chứng ở đúng lớp**.

### Kết quả học tập

Sau bài này, người học có thể:

1. Mô tả những gì `MockMvc` kiểm thử được và những gì chỉ có HTTP integration test mới kiểm chứng đủ.
2. Phân biệt `@WebMvcTest`, `@SpringBootTest(webEnvironment = MOCK)` và `RANDOM_PORT`.
3. Dùng `@AutoConfigureMockMvc`, `MockMvc.perform(...)`, `@LocalServerPort` và JDK `HttpClient` đúng hoàn cảnh.
4. Dựng backend HTTP stub có **request counter/journal** để kiểm tra path rewrite, custom request header và số attempts.
5. Kiểm tra cả **response cuối từ client** và **request thật tới backend**, không chỉ một HTTP 200.
6. Thiết kế negative tests cho **authentication, authorization, rate limiting, retry/idempotency, circuit breaker, TLS và route miss**.
7. Tránh trộn API reactive `WebTestClient`/WebFlux với MVC theo cách sai, nhưng hiểu khi nào WebTestClient vẫn dùng như **network client** được.
8. Cô lập bài test trong CI, tránh cổng cố định, token thật, backend thật hoặc kiểm thử phá hoại production.

> **Phạm vi phiên bản:** Ví dụ áp dụng cho **Gateway Server Web MVC** cùng các dòng Spring Boot/Spring Cloud tương thích, dùng namespace route `spring.cloud.gateway.server.webmvc.routes` trong những phiên bản hỗ trợ. Starter, namespace, filter factory và configuration properties có thể khác ở dòng cũ (`spring.cloud.gateway.mvc.routes`) hoặc bản phát hành mới hơn. Luôn kiểm tra BOM/API thực tế. Phần lớn mã minh họa chạy trên Java 17+, Spring MVC và Spring Boot Test; những biến thể khác cần điều chỉnh import/cấu hình.

## 2. Kiến trúc dưới góc nhìn kiểm thử

Một request qua Gateway MVC có các điểm quan sát khác nhau:

~~~mermaid
flowchart TD
    C["Test HTTP client / Browser"] --> S["Servlet container"]
    S --> F["Servlet FilterChain + Spring Security"]
    F --> D["DispatcherServlet"]
    D --> R["WebMvc.fn RouterFunctionMapping"]
    R --> P["Gateway MVC predicates + before/after filters"]
    P --> H["Gateway outbound HTTP handler/client"]
    H --> B["Backend HTTP stub / service"]
    B --> H
    H --> P
    P --> D
    D --> S
    S --> C
    M["MockMvc"] -. "Mock Servlet request trực tiếp" .-> F
~~~

Trong bài này, ta tách **ba loại sự thật**:

| Lớp | Câu hỏi chính | Công cụ |
| --- | --- | --- |
| **Inbound Servlet/MVC** | Spring Security cho request qua chưa? Route/method/path nào match? | MockMvc với application context phù hợp |
| **Outbound Gateway → backend** | Backend nhận URL, method, header, body nào? Có bị retry/redirect không? | Backend stub có request journal/counter |
| **HTTP end-to-end** | Client thực nhận status/header/body thế nào qua socket và Servlet container? | HTTP client gọi `RANDOM_PORT`; test TLS/ingress riêng khi cần |

Ví dụ client gọi `GET /edge/catalog/items/42?lang=vi`:

1. Servlet Security có thể trả 401/403 **trước khi route Gateway chạy**.
2. `Path=/edge/catalog/**` và `Method=GET` quyết định route nào được chọn.
3. `StripPrefix=1` đưa backend path thành `/catalog/items/42`; query `lang=vi` phải được giữ nếu contract quy định.
4. Header `X-Gateway-Probe: catalog-edge` có thể được thêm **chỉ vào request outbound**.
5. Catalog có thể trả HTTP 200/404/503, ETag, Cache-Control, redirect hoặc body lớn.
6. Gateway trả response qua Servlet container; response filters có thể thay header/status.

**Một assertion `status().isOk()` tại MockMvc không tự chứng minh bước 3–5 đúng.** Cần evidence ở backend và, khi có yêu cầu transport, request qua cổng thật.

## 3. Ma trận lựa chọn: dùng công cụ nào trước?

| Mục tiêu | MockMvc | HTTP client + backend stub | Hệ thống staging/e2e |
| --- | --- | --- | --- |
| MVC HandlerMapping và route predicates | Rất phù hợp khi full Gateway context được nạp | Phù hợp | Có ích khi cần đường ingress |
| Servlet Security/CSRF/authorization rules | Rất phù hợp, nhanh | Cần thiết để kiểm tra token/JWKS thực | Cần thiết cho identity/network policy |
| Before/after filter logic | Có thể kiểm thử | Xác minh kết quả HTTP thực | Kiểm tra tương tác nhiều proxy |
| Outbound request path/header/body | Cần backend stub; MockMvc **không tự mock outbound** | Rất phù hợp | Cần khi service discovery/network thật quan trọng |
| TCP connect, TLS handshake, socket reset | Không mô phỏng inbound transport thật | Có thể kiểm thử với stub/HTTPS test server | Cần khi có ingress/mTLS thật |
| Header serialization, HTTP framing | Chỉ mức mô phỏng Servlet | Kiểm chứng trên HTTP socket | Kiểm tra HTTP/2/ingress/CDN |
| SSE/large downloads/cancellation | Hạn chế, không đại diện cho network thật | Rất phù hợp nếu test streaming | Cần thêm để kiểm tra proxy chain |
| Multi-replica routing, DNS/discovery | Không đủ | Chỉ đủ khi test hạ tầng tương ứng | Phù hợp |
| Retry/breaker attempts | Stub counter cần có ở cả hai | Stub counter phù hợp | Cần kiểm tra fleet-level policy |
| Tốc độ test | Nhanh | Chậm hơn một chút | Chi phí và độ không ổn định cao hơn |

**Khuyến nghị:** Một bộ kiểm thử tốt thường có **nhiều MockMvc tests** cho mapping/security, **một tập HTTP integration tests nhỏ hơn** cho những hợp đồng proxy quan trọng và **một tập e2e có chọn lọc** cho TLS, ingress, discovery và rolling deployment. Không cần đẩy mọi edge case lên staging, cũng không nên chỉ có test mock.

## 4. Đúng dependency, web application type và test context

Với Gateway **Server Web MVC**, starter trong những dòng mới thường có dạng:

~~~xml
<!-- Version lấy từ Spring Cloud BOM tương thích Spring Boot. -->
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway-server-webmvc</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Tên starter ở những release cũ có thể là `spring-cloud-starter-gateway-mvc`. Nếu kiểm thử auth bằng Spring Security, bổ sung test support tương ứng:

~~~xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Phải kiểm tra dependency graph để chắc chắn runtime là **Servlet MVC**. Khi vô tình đưa `spring-cloud-starter-gateway-server-webflux` vào hoặc import nhầm `web.reactive.function.server.RouterFunction`, bài test sẽ không còn đo đúng Gateway Server MVC.

### @WebMvcTest khác @SpringBootTest thế nào?

| Annotation/config | Tác động chính | Nên dùng |
| --- | --- | --- |
| `@WebMvcTest(Controller.class)` | Slice cho MVC controllers và những bean cần thiết, **không mặc định khởi động đầy đủ Gateway MVC auto-configuration** | Test controller hoặc request validation độc lập |
| `@SpringBootTest(webEnvironment = MOCK)` + `@AutoConfigureMockMvc` | Nạp application context; không mở inbound HTTP port thật, MockMvc gọi hạ tầng Servlet mock | Kiểm tra route mappings/security/filters trong app gần production |
| `@SpringBootTest(webEnvironment = RANDOM_PORT)` | Khởi động Servlet container với port ngẫu nhiên | HTTP integration test thực qua network stack |
| `@SpringBootTest(RANDOM_PORT)` + `@AutoConfigureMockMvc` | Có thể sử dụng **cả MockMvc và HTTP client** trong cùng context | So sánh hành vi ở hai mức |

Với một Gateway route được tạo bởi auto-configuration, `@WebMvcTest` rất dễ cho kết quả **404 vì bean RouterFunction không được nạp**, dù production hoạt động đúng. Hãy chọn full context khi test route end-to-end hoặc import đúng những thành phần cần thiết nếu thực sự chủ đích slice test.

### MockMvc không phải WebTestClient reactive

`MockMvc` dùng `MockHttpServletRequest`/`MockHttpServletResponse` và hạ tầng Servlet/MVC. `WebTestClient` thường được sử dụng trong WebFlux, **nhưng nó cũng có thể đóng vai trò HTTP client thực** khi `bindToServer()` gọi một Gateway MVC ở port đang chạy. Không nên kết luận rằng “dùng WebTestClient là Gateway đã thành WebFlux”; hãy phân biệt **client test** với **runtime ứng dụng**.

Trong bài, ví dụ sử dụng `MockMvc` để kiểm thử Servlet và **JDK HttpClient** để tránh nhầm stack.

## 5. Tạo một route có thể kiểm chứng

Giả sử một Catalog backend stub nghe ở một URL lấy từ property `catalog.stub.base-url`. Client đi vào:

~~~text
GET /edge/catalog/items/42?lang=vi
~~~

Ta muốn Gateway gửi:

~~~text
GET /catalog/items/42?lang=vi
X-Gateway-Probe: catalog-edge
~~~

Ví dụ `application-test.yml` **dùng trong hướng dẫn**, không phải file cần tạo trong workspace của worker:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: catalog-read
              uri: ${catalog.stub.base-url}
              predicates:
                - Path=/edge/catalog/**
                - Method=GET
              filters:
                - StripPrefix=1
                - SetRequestHeader=X-Gateway-Probe,catalog-edge
~~~

Đây là ví dụ dành cho những bản Gateway Server MVC đọc namespace `spring.cloud.gateway.server.webmvc.routes`. Nếu phiên bản thực dùng `spring.cloud.gateway.mvc.routes`, hãy đổi **đúng namespace** và kiểm tra các filter factory có hỗ trợ ở release đó; **không khai báo đồng thời cả hai và đoán binder nào chạy**.

Vì `StripPrefix=1` loại segment `edge`, path còn `/catalog/items/42`. Nếu backend chỉ nhận `/items/42`, phải chọn `StripPrefix=2` hoặc rewrite thích hợp, rồi test tại backend; không đoán. Ta dùng **`SetRequestHeader`**, không phải `AddRequestHeader`, để thay giá trị do client cố tình giả mạo. Nếu chỉ cần thêm một header không ảnh hưởng bảo mật, `AddRequestHeader` cũng có vai trò riêng nhưng thường **không ghi đè** header cũ.

### Vì sao property URI phải do test kiểm soát?

Nếu route trong CI gọi một host dev/staging thật, test có thể gây side effect, phụ thuộc mạng, rò token hoặc flake khi service thay đổi. `catalog.stub.base-url` nên được cấp bằng **test backend stub trên loopback/isolated network**, có port tự động và request journal.

Nếu route dùng `lb://catalog-service`, cần thêm fake/service-instance provider thích hợp cho test; không dùng thật service registry sản xuất.

## 6. Tạo backend stub HTTP có request journal, không dựa vào mock giả

Để xác minh Gateway **thật sự đã gửi request outbound**, ta cần một HTTP endpoint quan sát được. Có thể dùng WireMock, MockWebServer hoặc một backend test Spring Boot riêng. Ví dụ sau dùng **JDK `com.sun.net.httpserver.HttpServer`**, tránh thêm dependency ngoài; nó chỉ phục vụ lab, không dùng làm HTTP server sản xuất.

~~~java
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

final class CatalogStubFixture {

    static final AtomicInteger HITS = new AtomicInteger();
    static final AtomicReference<String> LAST_PATH =
            new AtomicReference<>();
    static final AtomicReference<String> LAST_QUERY =
            new AtomicReference<>();
    static final AtomicReference<String> LAST_MARKER =
            new AtomicReference<>();
    static final AtomicReference<String> LAST_METHOD =
            new AtomicReference<>();

    private static final HttpServer SERVER = start();

    private CatalogStubFixture() {}

    private static HttpServer start() {
        try {
            HttpServer server = HttpServer.create(
                    new InetSocketAddress("127.0.0.1", 0), 0);
            server.createContext("/", CatalogStubFixture::reply);
            server.start();
            return server;
        } catch (IOException error) {
            throw new ExceptionInInitializerError(error);
        }
    }

    static String baseUrl() {
        return "http://127.0.0.1:" + SERVER.getAddress().getPort();
    }

    static void reset() {
        HITS.set(0);
        LAST_PATH.set(null);
        LAST_QUERY.set(null);
        LAST_MARKER.set(null);
        LAST_METHOD.set(null);
    }

    static void stop() {
        SERVER.stop(0);
    }

    private static void reply(HttpExchange exchange) throws IOException {
        HITS.incrementAndGet();
        String path = exchange.getRequestURI().getRawPath();
        LAST_PATH.set(path);
        LAST_QUERY.set(exchange.getRequestURI().getRawQuery());
        LAST_METHOD.set(exchange.getRequestMethod());
        LAST_MARKER.set(
                exchange.getRequestHeaders().getFirst("X-Gateway-Probe"));

        int status = path.endsWith("/missing") ? 404
                : path.endsWith("/busy") ? 503 : 200;
        String body = status == 404
                ? "{\"error\":\"NOT_FOUND\"}"
                : status == 503
                ? "{\"error\":\"UPSTREAM_BUSY\"}"
                : "{\"id\":\"42\",\"source\":\"catalog-stub\"}";
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);

        exchange.getResponseHeaders().set(
                "Content-Type", "application/json;charset=UTF-8");
        exchange.getResponseHeaders().set(
                "X-Catalog-Backend", "stub");
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream stream = exchange.getResponseBody()) {
            stream.write(bytes);
        }
    }
}
~~~

**Ý nghĩa của fixture:**

- Port `0` yêu cầu hệ điều hành cấp một port còn trống; test không tranh giành `9001` với ứng dụng khác.
- Fixture thực sự nhận request qua TCP/HTTP khi Gateway outbound client gọi; đây **không phải mock bean** của Gateway.
- `HITS` đếm số **outbound HTTP attempts**, `LAST_PATH`/`LAST_QUERY` giữ URI cuối; `LAST_MARKER` ghi header backend nhận.
- Stub trả 200, 404 hoặc 503 theo path. Đây là **HTTP responses bình thường**, khác hoàn toàn exception TCP/TLS.
- Các `AtomicReference` là ví dụ tối giản; khi kiểm thử requests **song song** cần journal có request IDs và concurrency safety, không dùng một `LAST_*` rồi suy luận request nào viết sau cùng.

Mã chỉ ghi path/query của **dữ liệu thử nghiệm không nhạy cảm**. Trong production, không đặt access tokens, cookies hoặc PII vào một request journal/log mặc định. Khi dùng module system (JPMS), JDK `HttpServer` thuộc module `jdk.httpserver`; cấu hình build/test phải cho phép sử dụng module này.

### Một phép thử phải có cả outbound counter

Nếu route có `SetRequestHeader` và `StripPrefix`, điều cần chứng minh không chỉ là client thấy body JSON 200 mà còn:

~~~text
HITS        = 1
LAST_METHOD = GET
LAST_PATH   = /catalog/items/42
LAST_QUERY  = lang=vi
LAST_MARKER = catalog-edge
~~~

Đây là **kết quả kỳ vọng khi Gateway dùng đúng config**, chưa phải số liệu chạy thực. Nếu HITS bằng 0, một MockMvc response vẫn có thể do Spring Security, MVC controller khác, fallback hoặc cache tạo; không được kết luận upstream đã được gọi.

## 7. MockMvc kiểm thử route/filter trong ngữ cảnh Spring Boot

Để nạp đủ Gateway MVC auto-configuration, có thể dùng:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
@ActiveProfiles("test")
class GatewayMvcMockTest {
    // @Autowired MockMvc mockMvc;
}
~~~

Trong bài thực hành ở phần tiếp theo, ta dùng **`RANDOM_PORT` kết hợp `@AutoConfigureMockMvc`** để chạy cả hai loại test trong cùng một application context. Nếu chỉ muốn test MockMvc, `MOCK` thường nhẹ hơn.

### 7.1. Assertions phổ biến của MockMvc

~~~java
mockMvc.perform(get("/edge/catalog/items/42")
                .queryParam("lang", "vi"))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.id").value("42"));
~~~

Imports cốt lõi:

~~~java
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;
~~~

**Đây là đoạn dùng trong class đã có `MockMvc mockMvc`**, không phải Java file độc lập. Cần xác nhận route thực sự match và backend stub chạy. Đặc biệt, `jsonPath("$.id")` chỉ kiểm tra response cuối, **không chứng minh`StripPrefix` đã đổi path**, nên phải assert thêm `LAST_PATH` của stub.

### 7.2. Kiểm tra route miss và method mismatch

~~~java
int before = CatalogStubFixture.HITS.get();

mockMvc.perform(post("/edge/catalog/items/42")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{}"))
        .andExpect(status().is4xxClientError());

assertEquals(before, CatalogStubFixture.HITS.get());
~~~

**Không cứng nhắc status 404 cho mọi method mismatch.** Một Servlet handler mapping có thể trả 405 khi path có handler nhưng method không được hỗ trợ; route miss có thể trở thành 404, còn security deny-by-default có thể trả 403 **trước khi MVC chọn route**. Vì vậy ví dụ chỉ assert nhóm 4xx, và điều quan trọng hơn là **không có call trái phép tới Catalog qua route GET-only**. Trong dự án thật, nên đặt expected status chính xác theo security/router contract sau khi đã xác định đúng lớp xử lý.

### 7.3. MockMvc có thể thấy HTTP response đã mock như thế nào?

MockMvc cho phép kiểm tra status, response headers, cookies, body content và resolved exception. Tuy nhiên, Servlet mock **không mô phỏng tất cả chi tiết**:

- TCP socket lifecycle và congestion.
- HTTP/1.1 keep-alive, chunked transfer framing hoặc HTTP/2 multiplexing.
- Reverse proxy đang rewrite URL/Host/forwarded headers.
- TLS handshake/client certificate/mTLS.
- Client disconnect giữa lúc response được ghi.
- Servlet connector và HTTP client outbound pool dưới tải thật.

Do đó, kiểm tra những thứ này cần **HTTP client thật** và test environment đủ gần production.

## 8. Một integration test dùng cả MockMvc lẫn HTTP client

Đây là ví dụ trung tâm của bài. **Một test class** dùng `@SpringBootTest(RANDOM_PORT)` để tạo inbound HTTP port thật, đồng thời `@AutoConfigureMockMvc` để thực hiện request in-process. Backend HTTP stub được bắt đầu trong `CatalogStubFixture` từ phần 6.

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureMockMvc
@ActiveProfiles("test")
class GatewayMvcProxyIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @LocalServerPort
    int gatewayPort;

    @DynamicPropertySource
    static void backendUrl(DynamicPropertyRegistry properties) {
        properties.add(
                "catalog.stub.base-url",
                CatalogStubFixture::baseUrl);
    }

    @BeforeEach
    void resetJournal() {
        CatalogStubFixture.reset();
    }

    @AfterAll
    static void stopBackend() {
        CatalogStubFixture.stop();
    }

    @Test
    void mockMvcChecksMvcRouteAndOutboundHeaders() throws Exception {
        mockMvc.perform(get("/edge/catalog/items/42")
                        .queryParam("lang", "vi")
                        .header("X-Gateway-Probe", "attacker"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON));

        assertEquals(1, CatalogStubFixture.HITS.get());
        assertEquals("GET", CatalogStubFixture.LAST_METHOD.get());
        assertEquals("/catalog/items/42",
                CatalogStubFixture.LAST_PATH.get());
        assertEquals("lang=vi",
                CatalogStubFixture.LAST_QUERY.get());
        assertEquals("catalog-edge",
                CatalogStubFixture.LAST_MARKER.get());
    }

    @Test
    void realHttpClientChecksServletTransportAndStatus() throws Exception {
        HttpClient client = HttpClient.newBuilder()
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();

        URI address = URI.create("http://127.0.0.1:"
                + gatewayPort + "/edge/catalog/items/busy");
        HttpRequest request = HttpRequest.newBuilder(address)
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(503, response.statusCode());
        assertTrue(response.body().contains("UPSTREAM_BUSY"));
        assertEquals(1, CatalogStubFixture.HITS.get());
    }
}
~~~

**Điều kiện chạy:** Ứng dụng test phải thật sự có Gateway Server Web MVC, route YAML phần 5 được nạp bằng profile `test`, và không có SecurityFilterChain chặn requests thử nghiệm hoặc đã cấp authentication hợp lệ. `CatalogStubFixture` phải nằm trong test source set. Chỉ test này sở hữu fixture; khi tách thành nhiều test classes, hãy xây lifecycle theo context/extension để tránh đóng stub khi class khác còn dùng.

**Phiên bản Boot:** Package `@AutoConfigureMockMvc`, `@LocalServerPort` và API test có thể đổi qua major release; đối chiếu phiên bản đang dùng. Với một dự án Java module, cho phép sử dụng `jdk.httpserver`.

### 8.1. Test này chứng minh gì?

- **Test MockMvc** đi qua MVC handler/router/filter với Servlet mock, nhưng outbound HTTP vẫn tới stub thật.
- **Test HttpClient** đi từ socket vào Servlet container thật của Gateway, rồi từ Gateway qua socket đến stub.
- Trong cả hai test, `HITS` đo số upstream requests và `LAST_*` ghi những gì backend nhận.
- `ResponseEntity` hoặc response được Spring/Gateway tạo vẫn được kiểm tra từ phía client.

Đây là **mã minh họa, chưa chạy thực tế trong bài**. Để test đầu tiên không bị Spring Security chặn, cần policy cụ thể trong profile test; **không đưa `permitAll()` cho toàn bộ routes lên production**.

### 8.2. Test lifecycle và chạy song song

Fixture dùng `HITS.reset()` và `LAST_*` nên nếu hai test methods chạy song song, kết quả có thể **race**. Cần tắt JUnit parallel execution cho class, dùng `@Execution(SAME_THREAD)` theo JUnit 5 nếu cần, hoặc xây request journal với correlation IDs và asserts riêng.

Một `HttpServer` có thể nhận nhiều requests đồng thời, nhưng `LAST_*` chỉ lưu **request cuối**; nó không đủ để chứng minh thứ tự attempts hoặc fan-out. Để test retry/breaker, dùng một queue/journal có timestamp, attempt number và thread-safe storage.

## 9. Phân biệt các kiểu MockMvc test theo mục tiêu

### 9.1. Test MVC controller riêng

Nếu ứng dụng có controller `@RestController` riêng, dùng `@WebMvcTest` để test validation, argument binding, status hoặc exception handler; mock collaborators bằng công cụ phù hợp với Spring Boot version. **Nó không nạp toàn bộ route/filter của Gateway MVC** trừ khi test tự thêm cấu hình cần thiết.

### 9.2. Test Gateway route definitions

Với route từ YAML hoặc `RouterFunction` Gateway MVC, dùng `@SpringBootTest` đủ auto-configuration. Có thể dùng MockMvc để kiểm tra rằng `Path` và `Method` đưa request tới HTTP handler đúng, sau đó assert backend journal để xác nhận path/header.

### 9.3. Test custom Servlet Filter/Security

MockMvc phù hợp để kiểm tra `SecurityFilterChain`, CSRF và `Filter` order bằng request processors thích hợp. Nhưng nếu bạn khởi tạo standalone `MockMvcBuilders.standaloneSetup(controller)`, toàn bộ filter chain và Gateway routing có thể không tồn tại, nên test sẽ **không đại diện production**. Dùng Spring Boot context hoặc `webAppContextSetup`/filter registration đầy đủ khi cần.

### 9.4. Test Gateway MVC before/after filters

Một route filter như `SetRequestHeader`, `StripPrefix`, `AddResponseHeader` hay `RewritePath` cần hai bộ assertion:

1. **Request phía backend:** method, raw path, raw query, headers và body sau filter.
2. **Response phía client:** status, response headers và body sau tất cả lớp xử lý.

Chỉ kiểm tra một header response **không chứng minh** request header filter đã chạy. Tương tự, backend thấy path đúng **không chứng minh** response body hoặc security đúng.

## 10. Những thứ MockMvc thường không thể chứng minh

| Quan sát ở MockMvc | Không nên suy ra | Loại test bổ sung |
| --- | --- | --- |
| `status().isOk()` | TCP/TLS/streaming vận hành đúng dưới tải | HTTP client + transport test |
| Mock security `jwt()` có scope | JWT chữ ký/issuer/audience thật đều đúng | Signed test JWT qua real resource-server decoder |
| JSON body đúng | HTTP/2/framing, compression, Content-Length đúng | HTTP client và các proxy thật |
| Route match | Registry có backend instance khỏe | Test load balancer/discovery |
| 503 trả nhanh | Circuit breaker thật đang OPEN | Breaker metrics + outbound counter |
| Header xuất hiện trong mock response | CDN/ingress vẫn giữ header đó | E2E qua ingress |
| Timeout test với stub Mono/scheduler | Servlet socket timeout ở mức HTTP client thật | Fault injection vào HTTP stub |
| Một request trả 200 | Không có retry lặp, POST không có side effect | Backend request journal/idempotency test |
| Response body có text | Cookie/CORS/caching đúng với browser | Real HTTP + browser contract test |

Quy tắc cốt lõi: **Chọn assertion ở cùng lớp với tuyên bố bạn muốn chứng minh.** Nếu nói “client kết nối HTTPS thành công”, phải có TLS/HTTP test. Nếu nói “JWT scope được yêu cầu”, MockMvc/Spring Security test có thể đủ cho **authorization rule**, nhưng **chưa đủ** cho việc verify signed token end-to-end.

## 11. Kiểm thử bảo mật Servlet bằng MockMvc

Gateway Server Web MVC dùng **Spring Security Servlet**, không dùng `SecurityWebFilterChain` của WebFlux. Các request tới Gateway thường đi qua `SecurityFilterChain` trước khi `RouterFunctionMapping` chọn route.

Giả sử contract:

- `GET /edge/catalog/**` là public.
- `GET /edge/orders/**` yêu cầu access token với `SCOPE_orders.read`.
- Những method/paths khác phải từ chối theo policy.

Một security configuration **minh họa Bearer-only stateless API**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class GatewaySecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                HttpMethod.GET, "/edge/catalog/**")
                            .permitAll()
                        .requestMatchers(
                                HttpMethod.GET, "/edge/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .anyRequest()
                            .denyAll()
                )
                .oauth2ResourceServer(resourceServer ->
                        resourceServer.jwt(Customizer.withDefaults()))
                .sessionManagement(session ->
                        session.sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                .csrf(csrf -> csrf.disable())
                .build();
    }
}
~~~

**Điều kiện quan trọng:** Tắt CSRF ở ví dụ chỉ hợp lý nếu API thuần Bearer token không dùng browser cookie/session authentication. Nếu dùng cookie/CSRF-protected admin UI, cần cấu hình bảo vệ CSRF, không copy tùy tiện dòng disable. Cũng phải cấu hình **JWT issuer, chữ ký, thời hạn và audience** đúng với API thực; không tự tin chỉ vì `issuer-uri` đã được đặt.

### 11.1. MockMvc negative tests cho quyền đọc Orders

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class GatewayMvcAuthorizationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void anonymousCannotReadOrders() throws Exception {
        mockMvc.perform(get("/edge/orders/42"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void tokenWithoutOrdersScopeIsForbidden() throws Exception {
        mockMvc.perform(get("/edge/orders/42")
                        .with(jwt().authorities(
                                new SimpleGrantedAuthority(
                                        "SCOPE_catalog.read"))))
                .andExpect(status().isForbidden());
    }
}
~~~

Hai tests **không cần backend Orders chạy** nếu security chặn request trước handler; điều cần chứng minh tiếp là **outbound counter = 0** trên các requests bị chặn. HTTP status 401/403 ở đây giả định Resource Server authentication entry point và access denied behavior theo cấu hình minh họa; custom entry point có thể trả status khác.

### 11.2. Mock JWT không giống signed JWT thật

`.with(jwt())` trong `spring-security-test` tạo authentication giả hợp lệ cho security test. Nó hữu ích để kiểm tra **authorization rules, authority mapping đã gán trong test, matcher order** nhưng thường **không xác minh chữ ký, JWKS retrieval, issuer, expiration hoặc audience** giống resource server production.

Để kiểm tra authentication end-to-end:

1. Dựng **test Identity Provider/JWKS server** hoặc tạo signed test JWT bằng key chỉ dùng cho lab.
2. Cấu hình decoder kiểm tra issuer/audience/scope theo chính sách.
3. Gửi token qua **HTTP client thật** với `Authorization: Bearer ...`.
4. Thử chữ ký sai, `exp` hết hạn, `iss` sai, `aud` sai và thiếu scope.
5. Không dùng token production, không dump JWT lên test logs.

**Tách bài toán:** Test 401/403 của Spring Security, test route matching của Gateway và test backend authorization **đều cần**, vì backend vẫn phải kiểm tra ownership/tenant và quyền thao tác, không chỉ tin Gateway.

### 11.3. Route predicate không phải authorization

`Method=GET`, `Path=/edge/orders/**` hoặc `Host=admin.example.test` chỉ kiểm soát cách chọn route. Chúng không chứng minh client có danh tính/quyền tương ứng. Test path traversal, encoded path, query và forwarding headers cần chạy qua **đúng trust boundary**; tránh cho một alternate path đi vào backend mà Spring Security matcher không bảo vệ.

### 11.4. Kiểm thử Actuator riêng

Nếu Gateway MVC expose Actuator, test `/actuator/health` với quyền cho probe và negative test cho những endpoints nhạy cảm. Một Gateway route filter không tự bảo vệ các Actuator handler mappings. Với **management port riêng**, cần HTTP test đúng cổng và security context thật; MockMvc của application context không bảo đảm bao phủ management server riêng.

## 12. Kiểm thử method, path, query, header và encoded URI

Một route `Path=/edge/catalog/**` có thể hoạt động với URL ASCII đơn giản nhưng sai khi gặp dấu slash, encoding hoặc host forwarding.

| Request đầu vào | Điều cần kiểm tra | Ghi chú |
| --- | --- | --- |
| `GET /edge/catalog/items/42` | Backend nhận `/catalog/items/42` | Cơ sở `StripPrefix=1` |
| `GET /edge/catalog/items/42?lang=vi` | Query còn đúng ở backend | Kiểm tra `getRawQuery()` của stub |
| `POST /edge/catalog/items/42` | Không proxy qua route GET-only | Status có thể 404/405 theo MVC |
| `GET /edge/unknown` | Không tới Catalog | Kiểm tra route miss/catch-all |
| `GET /edge/catalog/items/%2F42` | Hành vi encoded slash có chủ đích | Container/proxy có thể decode/reject |
| `GET /edge/catalog/items/a%2Bb` | Không biến encoded plus thành space | Kiểm tra path raw và backend semantics |
| `GET /edge/catalog/items/42?tag=a%2Bb` | Query `+` được giữ đúng | Không so sánh trên decoded representation duy nhất |
| `GET /edge/catalog//items/42` | Double slash được chấp nhận/từ chối có chủ đích | Có thể bị ingress normalize |
| `GET /edge/catalog/items/42/` | Trailing slash semantics | Kiểm thử đúng MVC version |
| `HEAD /edge/catalog/items/42` | Có route HEAD không? | HEAD có semantics MVC riêng |
| `GET` với header spoof | `SetRequestHeader` overwrite đúng | Header inbound client không thành trusted identity |
| `Host: attacker.example` | Không đổi target backend tùy ý | Không dùng client Host làm URI |

**Đừng suy luận rằng mọi `%2F` đi qua Servlet container đều nguyên trạng.** Tomcat/Jetty, ingress và Spring MVC path matching có thể có chính sách decode/reject khác nhau. Cần kiểm thử với **HTTP socket thật** trên phiên bản/container của production; MockMvc có thể bỏ qua normalization ở HTTP connector.

### 12.1. Query raw khác decoded parameters

Nếu test chỉ assert:

~~~java
assertEquals("a+b", request.getParameter("tag"));
~~~

bạn chưa biết client đã gửi `tag=a%2Bb` hay `tag=a+b` và container đã decode theo rule nào. Với proxy path/query integrity, backend stub nên ghi **raw query** và, nếu cần, so sánh với decoded parameter. Điều này rất quan trọng khi request signing hoặc authorization dựa trên canonical URI.

### 12.2. Xử lý forwarding headers

Client HTTP có thể gửi `Forwarded` và `X-Forwarded-*` giả. Nếu Gateway nằm sau ingress, chỉ tin những headers đã được **proxy tin cậy chuẩn hóa** theo cấu hình. Test trực tiếp port Gateway và qua ingress có thể cho kết quả khác; ghi rõ điểm vào của test.

Không gửi header `X-User-Role: ADMIN` rồi cho rằng middleware ở backend phải chấp nhận. Backend chỉ tin principal/token/mTLS identity đáng tin.

## 13. Kiểm thử response status, headers và body ở đúng phía

Một contract Gateway không chỉ có route URL. HTTP client phải nhận đúng status, end-to-end headers và body representation:

| Backend trả | Client nên nhận trong pass-through bình thường | Lưu ý |
| --- | --- | --- |
| 200 + JSON | 200, Content-Type JSON, body phù hợp | Không phải 200 do fallback giả |
| 201 + Location | 201 và Location theo policy public | Location nội bộ cần rewrite/allowlist |
| 204 No Content | 204, không body | Không tự thêm `{}` |
| 304 Not Modified | 304 với validator hợp lệ, không body | Không phá `ETag` |
| 400 | 400 nếu lỗi client hợp lệ | Không retry vô hạn |
| 401/403 | Bảo toàn bảo mật theo contract | Không đổi 403 thành 200 |
| 404 | 404; phân biệt backend 404 với route miss | Xem backend counter |
| 429 + Retry-After | 429 và hướng dẫn retry nếu policy cho phép | Không tự bỏ qua quota |
| 503 | 503/fallback minh bạch theo route policy | Kiểm tra circuit/retry |
| 206 + Content-Range | 206, range bytes đúng | Cần test full HTTP/streaming |
| 302 + Location | Theo redirect policy | Không tự theo host ngoài |

### 13.1. Kiểm tra response header thật

Một request với MockMvc:

~~~java
mockMvc.perform(get("/edge/catalog/items/42"))
        .andExpect(status().isOk())
        .andExpect(header().string(
                "X-Catalog-Backend", "stub"));
~~~

Nếu Gateway config có response header filters hoặc ingress chỉnh header, **HTTP client thật** phải kiểm tra final response ở đúng URL và port, không chỉ lấy header từ backend stub. Ví dụ:

~~~java
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());
assertEquals("stub",
        response.headers()
                .firstValue("X-Catalog-Backend")
                .orElse(""));
~~~

Với `Set-Cookie` nhiều giá trị hoặc `Vary`, tránh test chỉ lấy `getFirst()` nếu hợp đồng yêu cầu nhiều giá trị. HTTP response field names không phân biệt hoa/thường.

### 13.2. Hop-by-hop headers và body encoding

Không đòi Gateway copy nguyên `Connection`, `Transfer-Encoding` hoặc `Content-Length` từ backend. Chúng có semantics theo từng HTTP hop. Nếu Gateway rewrite hoặc decompress body, `Content-Encoding`, `ETag`, `Vary`, `Content-Range` và `Content-Length` phải nhất quán với bytes thật.

Chỉ dùng `jsonPath` chưa đủ để tìm lỗi framing, gzip hoặc response cắt dở; test binary/raw bytes và kết nối thật khi API phụ thuộc các yếu tố đó.

### 13.3. 404 có thể đến từ ba nguồn

~~~text
1. MVC/Gateway route không match -> 404
2. Gateway match và Catalog trả 404 -> 404
3. Security/error handler cố ý che thông tin -> 404
~~~

Trong cả ba trường hợp client có thể nhận 404. **Backend stub counter** phân biệt số 2 với số 1/3; logs/traces đã sanitize và security tests giúp phân biệt tiếp.

## 14. Fault injection: timeout, refused, reset và upstream 5xx

Kiểm thử Gateway MVC cần mô phỏng lỗi ở đúng lớp để hiểu lỗi cuối cùng.

| Fault | Cách tạo trong lab | Tín hiệu cần đo |
| --- | --- | --- |
| Backend trả 503 | Stub trả HTTP status 503 bình thường | HTTP upstream status, attempts, final status |
| Backend trả 429 | Stub trả 429 và Retry-After | Rate/budget, header policy |
| TCP refused | Proxy route tới một port test không có listener | Connect exception và response/error handler |
| Connect timeout | Controlled network blackhole/test proxy | Bounded timeout, không chờ vô hạn |
| Response timeout | Stub chấp nhận kết nối rồi delay có giới hạn | Read/response timeout và latency |
| Reset sau headers/body | Stub đóng connection giữa stream | Partial response/connection error |
| TLS certificate invalid | HTTPS stub dùng CA không được trust | Fail closed, không bypass TLS verification |
| No service instance | Fake discovery trả tập rỗng | Không gọi một host tùy ý |
| Circuit breaker OPEN | Circuit test fixture chuyển sang trạng thái OPEN | Upstream counter không tăng |
| Retry hết budget | Stub lỗi liên tục | Attempts dừng đúng giới hạn |

**Không cố đạt timeout bằng cách `Thread.sleep()` trong filter chạy trên Gateway**, vì làm vậy có thể tạo một loại bottleneck không đại diện cho lỗi backend. Nếu cần delay, đặt nó ở **backend stub** hoặc network test proxy có giới hạn và timeout cho test. Đừng thử phá kết nối production.

### 14.1. Backend 503 khác transport exception

Nếu stub trả HTTP 503 với JSON, Gateway có thể hoàn tất HTTP proxy bình thường về mặt transport, chỉ status là lỗi. Với một TCP reset, có thể **không có ResponseEntity từ backend**. Gateway phải tạo hoặc để framework tạo error response phù hợp, nhưng status cụ thể phụ thuộc filters/error handlers/version.

Không viết test khẳng định “mọi exception phải là 503”; hãy định nghĩa contract dự án: chẳng hạn backend unavailable → 502/503, response timeout → 504, auth failure → 401/403. Bổ sung test phân biệt transport exception với backend-generated 503.

### 14.2. Deadline và giới hạn test duration

Một test timeout cần:

- Timeout của HTTP client Gateway.
- Timeout của HTTP client test để không chờ mãi.
- Deadline của test framework/CI.
- Điều kiện backend stub kết thúc hoặc được teardown an toàn.

Nếu test chỉ kiểm tra “thất bại trong dưới 30 giây”, nó có thể chạy chậm và flaky. Dùng các giá trị nhỏ nhưng **có khoảng cách đủ lớn** so với scheduling jitter trong CI. Test không được phụ thuộc vào thứ tự chạy hoặc một thread pool bên ngoài do test khác dùng.

### 14.3. Tại sao MockMvc một mình không đủ cho timeout socket?

MockMvc không có inbound TCP socket, vì vậy các lỗi như client disconnect, HTTP parser limit, server keep-alive và TLS ở inbound không xảy ra như ở Tomcat thật. Tuy nhiên **outbound** từ Gateway MVC tới một HTTP stub có thể vẫn là network call thật ngay cả khi inbound do MockMvc kích hoạt. Phân biệt hai hướng này khi diễn giải kết quả.

## 15. Kiểm thử route dùng lb:// và service discovery

Trong production, route có thể trỏ tới `lb://catalog-service` thay vì URL `http://127.0.0.1:port`. Khi đó Gateway phải phân giải service ID thành một hoặc nhiều **ServiceInstance** thông qua Spring Cloud LoadBalancer và discovery integration tương ứng với dòng MVC.

~~~mermaid
flowchart TD
    R["Gateway MVC route: lb://catalog-service"] --> LB["LoadBalancer / discovery adapter"]
    LB --> A["Catalog stub A: HTTP port ngẫu nhiên"]
    LB --> B["Catalog stub B: HTTP port ngẫu nhiên"]
    A --> J["Backend request journal"]
    B --> J
~~~

### 15.1. Test đơn vị của lựa chọn instance

Khi cần test routing với ServiceInstance giả, nên cung cấp một **test bean/service-instance supplier** theo API Spring Cloud LoadBalancer đang dùng. Không tự tạo một `ReactiveLoadBalancerClientFilter` kiểu WebFlux để ép vào Gateway MVC; tên lớp và integration khác.

Những assertions quan trọng:

1. Route `lb://catalog-service` được resolve từ **service ID đã định nghĩa**, không từ query/header do Internet client gửi.
2. Instance A/B trong test có host/port từ hai stubs thực sự đang nghe.
3. Khi chỉ có A, request phải tới A.
4. Khi không có instance, request phải thất bại theo contract, **không tự chuyển tới localhost/admin endpoint**.
5. Nếu một instance bị remove khỏi discovery, requests mới không tiếp tục chọn nó sau khoảng cập nhật được hỗ trợ (có thể có cache delay).
6. Khi instance metadata nói HTTPS, certificate/trust của outbound client phải được xác minh theo policy.

### 15.2. Đừng kiểm tra phân phối bằng một request

Load balancing không bảo đảm A và B mỗi cái được chọn chính xác 50% trong 2 requests. Thuật toán, cache, traffic, phiên bản và health filtering có thể thay đổi kết quả. Nếu policy yêu cầu round robin hoặc weighted distribution, dùng đủ mẫu **trong lab**, giới hạn thời gian, cho phép sai số phù hợp và kiểm tra instrumentation. Không viết assertion flake như “request thứ hai nhất thiết vào B” nếu thuật toán chưa được cố định trong test fixture.

### 15.3. Kiểm tra consistency nhiều Gateway replicas

Một HTTP test tới một instance Gateway không chứng minh mọi replica có cùng route definitions hoặc discovery view. Trong e2e môi trường staging, truy cập từng Gateway pod/instance bằng kênh được phê duyệt, so sánh route/config revision và backend journal. Khi rollout, test readiness để instance chưa đồng bộ không nhận user traffic.

## 16. Kiểm thử Retry, CircuitBreaker và rate limiting

Ba cơ chế này có cùng mục tiêu làm hệ thống bền vững, nhưng có **hành vi kiểm thử khác nhau**:

| Cơ chế | Câu hỏi chính | Bằng chứng bắt buộc |
| --- | --- | --- |
| **Retry** | Khi lỗi xảy ra, có thêm bao nhiêu upstream attempts? | Backend journal/counter, final status và latency |
| **CircuitBreaker** | Khi dependency suy giảm, request bị ngắt trước HTTP call không? | Breaker state, số calls outbound, fallback behavior |
| **RateLimiter** | Request vượt quota bị chặn tại Gateway trước upstream không? | Quota/clock/key policy, 429 hoặc response theo contract, outbound counter |

**Gateway Server MVC và WebFlux có thể khác filter factory options**, nên không copy nguyên cấu hình từ stack kia. Cố định phiên bản, filter order và policy trước khi khẳng định hành vi.

### 16.1. Retry không phải chỉ kiểm tra response cuối

Giả sử cấu hình một retry bổ sung cho GET khi Catalog trả 503:

~~~text
Inbound request: 1
Attempt #1: Catalog trả 503
Attempt #2: Catalog trả 200
Final response: 200
~~~

Kỳ vọng:

- `HITS = 2` ở stub.
- Client nhận 200 với body của attempt thứ hai.
- Nếu Catalog luôn trả 503, `HITS` vẫn phải dừng ở **tối đa 2**, không tăng không giới hạn.
- Khi backend trả 400/401/403/404 và chúng không thuộc policy retry, `HITS = 1`.
- Nếu client deadline hết, hệ thống không tiếp tục tạo calls không còn ích.

Lưu ý: `retries: 1` trong những filter semantics thường nghĩa là **một lần thử bổ sung sau attempt đầu**, nhưng phải xác minh Gateway MVC version cụ thể. Nếu test chỉ assert status cuối 200, một implementation có lỗi tạo **5 attempts rồi 200** cũng có thể làm test pass.

### 16.2. Retry đa tầng khuếch đại tải

Ví dụ client 3 attempts, Gateway 3 attempts và SDK backend 2 attempts:

\[
A_{\max} = 3\times3\times2 = 18
\]

Đây là cận trên **cho một nhánh tuần tự tương ứng**, không bao gồm fan-out song song và hedging. Test ở một lớp riêng không đủ để phát hiện amplification nhiều tầng: cần metric operation-level ở client và outbound attempts ở từng service. Không tăng `retries` khi backend đang quá tải chỉ vì response cuối 503.

### 16.3. CircuitBreaker OPEN

Khi breaker đã OPEN, một test tốt xác minh:

1. Gateway nhận inbound request hợp lệ.
2. **Backend request counter không tăng**, vì cuộc gọi bị chặn.
3. Response được tạo là fail-fast hoặc fallback theo API contract, không trả dữ liệu của tenant khác.
4. Metrics cho thấy call bị từ chối, không nhầm với HTTP 503 do Catalog đã trả.
5. Khi chuyển HALF_OPEN/CLOSED theo policy, test khôi phục state trước test khác.

**Tránh kiểm thử breaker bằng cách “gửi đúng 3 lỗi thì chắc chắn OPEN”** nếu chưa cố định sliding window, minimum number of calls, failure threshold, wait duration và các lỗi được record. Dùng test clock/breaker test instance có kiểm soát khi library hỗ trợ.

### 16.4. Rate limiter và trạng thái chia sẻ

Rate limiter dùng Redis hoặc một store chia sẻ có thể không được kiểm thử trung thực bằng mock bean chỉ trả “allowed”. Hãy test:

- Key resolver lấy danh tính đúng, không dùng `X-User-Id` do client khai khi chưa xác thực.
- Quota đầu đủ, sau đó vượt quota thì response đúng policy.
- Request bị chặn **không gọi backend**.
- Nếu nhiều replicas, rate limit là **toàn cụm hay cục bộ** theo thiết kế.
- Khi store lỗi, fail-open hay fail-closed phù hợp API và security policy.

Để test thời gian/rate deterministic, không dựa vào `Thread.sleep(1000)` tùy ý; dùng fake clock, test window hoặc dependency test đã cô lập nếu có. Có thể có một số filter/rate limiter khác nhau giữa Gateway MVC releases, nên bảo đảm policy thực sự được nạp trước khi assert.

## 17. Request/response bodies, streaming và client cancellation

**MockMvc mạnh về body ngắn**: bạn có thể gửi JSON và assert response JSON bằng `content().json(...)` hoặc `jsonPath(...)`. Nhưng nhiều API Gateway vận chuyển file, multipart hoặc luồng sự kiện có vòng đời dài.

### 17.1. Test JSON/body nhỏ

Với route POST (nếu được phép), một request test:

~~~java
mockMvc.perform(post("/edge/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"A-42\",\"quantity\":2}"))
        .andExpect(status().isAccepted());
~~~

Đoạn này là **phác thảo với route Orders riêng**: chưa có route POST/handler trong YAML phần 5. Để test có ý nghĩa phải dựng Orders stub và cấu hình đúng security, method/predicate và response contract; không phải cứ gửi POST là Gateway tự nhận.

Thêm backend journal cho **body bytes**, media type, charset và `Content-Length` hoặc transfer encoding thực. Với dữ liệu nhạy cảm, journal nên ghi **hash hoặc kích thước đã giới hạn** thay vì lưu raw request body.

### 17.2. Upload multipart

Multipart có boundary do HTTP client/Servlet parser tạo, có thể chứa file lớn và metadata. `MockMultipartFile` trong MockMvc kiểm thử tốt MVC argument binding, nhưng **không chứng minh** HTTP connector, backend streaming, timeout hoặc memory behavior với file thật. Bổ sung HTTP test có payload thử nghiệm kích thước vừa phải, giới hạn maximum size và kiểm tra backend nhận đủ bytes.

### 17.3. Streaming response và SSE

SSE/NDJSON có thể giữ kết nối lâu và flush dữ liệu từng phần. Với **HTTP client thật**, bạn có thể dùng:

~~~java
HttpClient client = HttpClient.newHttpClient();
HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + gatewayPort
                        + "/edge/reports/stream"))
        .GET()
        .build();

HttpResponse<java.io.InputStream> response = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());

try (java.io.InputStream body = response.body()) {
    // Đọc có giới hạn những bytes/event đầu tiên ở lab.
    // Không gom một stream vô hạn thành String hoặc byte[].
}
~~~

Đây là **đoạn phác thảo cho một route streaming riêng**, không phải route Catalog phần 5. Phải thiết kế body read deadline, test timeout và teardown; nếu chỉ `close()` stream, không tự khẳng định backend đã nhận cancellation ngay lập tức. Kiểm tra cleanup qua server metrics/journal thay vì suy từ một callback local.

### 17.4. Response đã commit

Khi client đã nhận status 200 và một phần SSE/file, Gateway không thể trả một HTTP 503 mới trên cùng response. Test nên mô phỏng backend gửi vài bytes rồi reset connection và xác nhận client **không bị nhận một JSON error nối vào stream**. Trạng thái cuối có thể là connection reset hoặc incomplete body, tùy transport; không bắt buộc một mã HTTP status mới.

### 17.5. Cancellation không đồng nghĩa rollback

Nếu request POST đã tới Orders và backend commit DB rồi client ngắt kết nối, cancellation ở Gateway **không đảo ngược side effect**. Thử nghiệm giao dịch cần idempotency key, deduplication atomic ở backend, trạng thái operation và status lookup. Không tự retry POST vì thấy socket bị đóng.

## 18. Kiểm thử HTTPS, mTLS và reverse proxy thực

MockMvc không dựng inbound TLS handshake, nên không thể chứng minh:

- Chứng chỉ server có đúng hostname/SAN và trust chain hay không.
- Client certificate được yêu cầu/xác minh bằng mTLS như policy không.
- HTTP/1.1 ↔ HTTP/2 ALPN hoặc TLS version/ciphers được đàm phán thế nào.
- Ingress nhận và chuẩn hóa `Forwarded`/`X-Forwarded-*` đúng không.
- HSTS/CORS/SameSite/cookie attributes thực sự tới browser.

### 18.1. HTTPS test server cho outbound

Để test Gateway MVC → backend TLS:

1. Dựng HTTPS stub với **chứng chỉ test** có SAN đúng host thử nghiệm.
2. Cấu hình HTTP client truststore của Gateway tin CA test.
3. Gọi route và assert backend nhận request đúng.
4. Thử cert hết hạn/không tin hoặc hostname mismatch; kết nối phải **fail closed**.
5. Nếu mTLS được yêu cầu, thử client cert hợp lệ, thiếu cert và cert không được trust.

**Không dùng `trustAllCertificates` hoặc `NoopHostnameVerifier` để làm test xanh.** Một test như vậy chứng minh hệ thống *không kiểm chứng bảo mật*, ngược mục tiêu.

### 18.2. Inbound HTTPS và ingress

Để kiểm tra client → Gateway TLS, chạy Gateway tại HTTPS port hoặc đặt ingress/nginx/service mesh test phía trước. Test trực tiếp random HTTP port không đủ, vì TLS termination có thể xảy ra ở ingress. Ghi rõ **điểm TLS kết thúc và điểm nào được test**.

### 18.3. Forwarded headers và trusted proxy

Một test quan trọng là gửi từ Internet/test client:

~~~http
X-Forwarded-Host: attacker.example
X-Forwarded-Proto: http
~~~

Gateway **không được tin những giá trị đó** nếu không đến từ proxy đáng tin. Dùng inbound HTTP test qua ingress để kiểm tra normalization, CORS, redirects và absolute links; không lấy `Host` hoặc `X-Forwarded-Host` do client gửi làm backend URI, tránh SSRF.

## 19. Kỹ thuật test doubles: chọn stub, mock bean hay một service thật?

| Test double | Điểm mạnh | Giới hạn |
| --- | --- | --- |
| **Mock bean** của một service nội bộ | Nhanh, tập trung logic controller/security | Không chứng minh outbound HTTP |
| **JDK HttpServer stub** | Có socket thật, port động, không cần thư viện ngoài | Khó mô phỏng HTTP/2, TLS, network faults phức tạp |
| **WireMock/MockWebServer** | Request journal, header matching, delay, reset, fault injection | Cần dependency/config test và quản lý server lifecycle |
| **Containerized backend** | Gần production hơn về HTTP/server behavior | Chậm hơn, cần container/runtime và cleanup |
| **Staging service thật** | Thấy discovery/TLS/network thực | Dữ liệu thay đổi, flake, nguy cơ side effect và secret exposure |

### 19.1. MockRestServiceServer có dùng được không?

`MockRestServiceServer` của Spring giúp kiểm thử một số HTTP client **nếu** Gateway thực sự dùng một `RestClient`/`RestTemplate` hoặc request factory mà test có thể gắn mock vào. **Không giả định nó tự bắt mọi outbound call của Gateway MVC**. Nếu Gateway MVC tự tạo HTTP client hoặc route handler dùng request factory khác, một `MockRestServiceServer` gắn nhầm bean sẽ không thấy request.

Vì vậy, khi chưa xác minh khả năng inject/mock đúng HTTP client cho phiên bản Gateway, **backend HTTP stub qua loopback** là cách đơn giản và rõ ràng hơn để chứng minh wire-level request.

### 19.2. MockBean/MockitoBean và phiên bản

Spring Boot/Spring Framework đã thay đổi API hỗ trợ test mocks theo các dòng phiên bản; một số codebase dùng `@MockBean`, một số dùng `@MockitoBean`. Không cần phụ thuộc vào annotation đó để test proxy bằng backend stub. Nếu test controller độc lập cần mock collaborators, chọn annotation tương thích BOM thực tế.

### 19.3. Tránh test phụ thuộc dịch vụ ngoài

Một test Gateway không nên đi đến Catalog staging bằng hostname do developer đặt cứng rồi coi HTTP 200 là passed. Điều đó gây flake, khó replay, có thể ghi dữ liệu thật và không chắc version backend. Dùng test backend controlled data, unique request IDs và timeout; chỉ một số e2e có phê duyệt mới gọi môi trường staging.

## 20. Ma trận kiểm thử đầy đủ cho Gateway Server Web MVC

Một bộ kiểm thử có hệ thống nên có **ít nhất một bằng chứng cho từng ranh giới quan trọng**, không phải lặp hàng chục test chỉ assert HTTP 200:

| ID | Kịch bản | Công cụ chính | Assertion bắt buộc |
| --- | --- | --- | --- |
| T01 | GET đúng route Catalog | MockMvc + stub | 200, HITS=1, đúng raw path |
| T02 | GET có query | MockMvc + stub | Raw query được giữ theo hợp đồng |
| T03 | POST vào route GET-only | MockMvc | Không có outbound attempt qua route đó |
| T04 | Request không match route | MockMvc | Không gửi tới Catalog; final status theo HandlerMapping |
| T05 | Xung đột hai routes | MockMvc + stub | Route/đích được chọn đúng order |
| T06 | Client spoof header nội bộ | MockMvc + stub | SetRequestHeader thay giá trị client |
| T07 | Response header được thêm | MockMvc và HTTP client | Client thấy response header đúng |
| T08 | Backend trả HTTP 404 | HTTP client + stub | 404, HITS=1; không nhầm route miss |
| T09 | Backend trả HTTP 503 | HTTP client + stub | Final 503/fallback đúng policy |
| T10 | Backend trả HTTP 204 | HTTP client | Không gửi body sai quy tắc |
| T11 | Backend trả 302 | HTTP client | Redirect/destination policy được giữ |
| T12 | Header Cookie/Authorization | Security + stub | Không rò credentials trái contract |
| T13 | Host/X-Forwarded-Host giả | HTTP client qua edge | Không SSRF, không trust proxy giả |
| T14 | Encoded slash/plus | HTTP client + stub | Path/query normalization theo policy |
| T15 | JSON/body nhỏ | MockMvc + stub | Content-Type, charset và payload |
| T16 | Multipart/body lớn | HTTP client + stub | Không mất bytes, có size limit |
| T17 | Gzip/Content-Encoding | HTTP client raw bytes | Encoding/header nhất quán |
| T18 | 206 Partial Content | HTTP client + stub | Content-Range/bytes đúng |
| T19 | Anonymous gọi Orders | MockMvc Security | Bị chặn; HITS=0 |
| T20 | JWT thiếu scope | MockMvc Security | 403 theo policy; HITS=0 |
| T21 | Signed JWT sai issuer/audience | HTTP client + test IdP | Bị reject bởi real JWT decoder |
| T22 | Token hợp lệ | MockMvc/HTTP client | Đi đúng backend; backend kiểm tra quyền |
| T23 | Backend connect refused | HTTP client + fault fixture | Không treo; status/error an toàn |
| T24 | Backend response timeout | HTTP client + delayed stub | Dừng trong deadline |
| T25 | TLS cert sai | HTTPS stub | Không bypass certificate/hostname |
| T26 | Load balancer có 2 instances | HTTP client + 2 stubs | Chỉ gọi instances được phê duyệt |
| T27 | Load balancer không có instance | HTTP client + fake discovery | Không gọi destination ngẫu nhiên |
| T28 | Retry 503 rồi 200 | HTTP client + counter | Attempts nằm trong budget, final đúng |
| T29 | Circuit breaker OPEN | MockMvc/HTTP client + counter | Không gọi backend; fallback đúng |
| T30 | Rate limit vượt quota | MockMvc/HTTP client | Request bị chặn; backend HITS không tăng |
| T31 | SSE partial stream | HTTP client streaming | Không viết 503 JSON sau response commit |
| T32 | Client disconnect | Real HTTP client + stub | Resource cleanup theo khả năng/timeout |
| T33 | 2 Gateway replicas | E2E | Route/security/metrics nhất quán |
| T34 | Actuator management | HTTP client đến management port | Public client không đọc/sửa được routes |
| T35 | CI lặp nhiều lần | Test suite | Không port conflicts, races hay phụ thuộc thứ tự |

**Không nhất thiết mọi dự án phải triển khai đủ 35 tests** trong một sprint. Chọn theo threat model và API contract. Tuy nhiên cần có **coverage cho positive, negative và failure paths**, ưu tiên những rủi ro cao: authentication bypass, sai route, rò token, retry duplication và TLS.

### Phân nhóm smoke, regression và chuyên sâu

- **Smoke (mỗi commit):** T01–T04, T06, T08/T09, T19/T20, T23, cùng kiểm tra backend HITS.
- **Regression route/header (pull request):** T05, T07, T10–T18, T22, các cases encoded path và header spoof.
- **Resilience/security integration (CI định kỳ hoặc trước release):** T21, T24–T30, TLS/circuit/real JWT và resource limits.
- **E2E/soak/chaos có phê duyệt:** T31–T35, multi-replica, ingress, cancellations và tải kéo dài.

Một số test phù hợp nhiều nhóm tùy mức rủi ro. Chẳng hạn tổ chức bán hàng trực tuyến có thể cần idempotency/retry tests **mỗi pull request**, không chờ pre-release.

## 21. Làm test deterministic và an toàn trong CI

Gateway test có nhiều nguồn không ổn định: cổng TCP, quá trình khởi động Spring, caching, time-based policy, scheduler và asynchronous I/O. Kết quả tốt phải **lặp lại được**.

### 21.1. Quản lý cổng và fixture lifecycle

**Nên:**

- `@SpringBootTest(webEnvironment = RANDOM_PORT)` cho Gateway inbound.
- Backend stub listen trên port `0`, lấy port thực sau khi start.
- `@DynamicPropertySource` cấp backend base URL cho route.
- Fixture/server cleanup ở `@AfterAll` hoặc test extension có ownership rõ.
- Cấu hình timeout cho cả outbound client và test client.
- Không share một mutable `LAST_REQUEST` nếu test methods chạy parallel.

**Tránh:**

- Hardcode 8080/9001 cho mọi test class trong CI.
- Dùng static HTTP server shared rồi đóng từ một class khi class khác còn dùng.
- Dùng `Thread.sleep` để “đợi route sẵn sàng” mà không có readiness condition.
- Test gọi Internet/DNS thật khi không có chủ đích và quyền.
- Bỏ HTTP client timeouts khiến build treo vô hạn.

### 21.2. Static state, profiles và context caching

Spring Test có thể **cache application contexts** giữa các test classes. Nếu class A dùng `@DynamicPropertySource` trỏ tới stub A, class B có context config giống nhưng lại muốn stub B, việc cache context sai mục đích có thể gây leak URL hoặc gọi server đã tắt.

Đối với test suite lớn:

1. Cố định fixture theo nhóm test/context.
2. Dùng test extension hoặc container lifecycle có trách nhiệm rõ.
3. Chỉ dùng `@DirtiesContext` khi thật sự cần reset Spring context; nó làm suite chậm hơn.
4. Dùng những profile/configuration keys khác nhau nếu cần context khác.
5. Reset circuit breaker/rate limiter/store state sau test, không để thứ tự test quyết định kết quả.
6. Gắn request correlation ID **chỉ cho dữ liệu test**, tránh dùng ID người dùng/secret làm nhãn metrics.

### 21.3. Không dùng test secrets production

Test JWT phải được ký bằng key dành cho test hoặc cấp bởi test IdP. Không commit private keys production, API keys hoặc refresh tokens vào repository. Không ghi header `Authorization`, `Cookie` hoặc full URI có query nhạy cảm vào logs của request journal hoặc CI artifacts.

Một chuỗi `Bearer fake-demo-token` dùng để test header stripping là **dữ liệu giả**, nhưng khi Spring Security resource server được bật, token đó có thể bị chặn **trước Gateway handler**. Cần tách test header forwarding trong security-isolated context với test authentication bằng signed JWT hợp lệ.

### 21.4. Không che lỗi bằng retry trong test harness

Một test có thể “ổn định hơn” nếu HTTP client thử lại khi socket refused, nhưng như vậy có thể che lỗi application startup/readiness. Nên sử dụng readiness probes/wait strategy rõ ràng rồi gọi một request **có số attempts đã biết**. Nếu retry là thứ cần test, đặt nó trong Gateway policy hoặc test client theo hợp đồng và đo attempts ở backend; không âm thầm tăng retries của test framework.

### 21.5. Chạy test trong pipeline

Một thứ tự hợp lý:

~~~mermaid
flowchart LR
    A["Compile / unit tests"] --> B["MockMvc routes & Security"]
    B --> C["HTTP Gateway + stub integration"]
    C --> D["Fault/TLS/discovery tests"]
    D --> E["Staging E2E + rollout checks"]
~~~

Quyết định một stage fail hay retry job dựa trên **nguyên nhân**. Một test hỏng lặp lại ở 404 route misconfiguration không được bỏ qua như “flake” chỉ vì app chạy tốt với một route khác.

## 22. Chẩn đoán khi MockMvc và HTTP client cho kết quả khác nhau

Nếu cùng một URL mà MockMvc pass còn HTTP client fail, hãy lần lượt kiểm tra những ranh giới bị thay đổi:

| Triệu chứng | Giả thuyết có cơ sở | Kiểm tra |
| --- | --- | --- |
| MockMvc 200, HTTP client connection refused | Servlet server chưa chạy/port sai | `@SpringBootTest(MOCK)` không mở socket; dùng RANDOM_PORT |
| MockMvc 200, HTTP client 401/403 | Security chain, forwarded headers hoặc auth context khác | Kiểm tra mock JWT vs Bearer thật |
| MockMvc 200, HTTP client 404 | Context path, ingress rewrite, normalization, HandlerMapping | Ghi raw URL và servlet context path an toàn |
| MockMvc 200, HTTP client 405 | Method thật khác hoặc preflight | Kiểm tra HTTP method, CORS/OPTIONS |
| MockMvc 200, HTTP client 502/503 | Backend URL/port, TLS/DNS, instance resolution | Kiểm tra outbound stub/journal, transport exception |
| MockMvc header đúng, HTTP client không thấy | Container/ingress/response filters thay header | So sánh response trước/sau proxy |
| MockMvc body đúng, HTTP client body hỏng | Encoding, gzip, Content-Length, HTTP framing | Kiểm tra raw bytes và response headers |
| MockMvc không test được cancellation | Không có inbound socket | Dùng real HTTP client và streaming backend |
| HTTP client test flaky khi chạy song song | Port/static state/context caching | Dùng port 0, isolated journal, per-context fixture |
| Backend HITS=0 dù response 200 | Cache/fallback/another handler | Kiểm tra route match, response provenance |
| Backend HITS lớn hơn 1 | Retry/redirect/client repeats | Bật attempt-level tracing, kiểm tra budgets |
| HTTP client bỏ qua redirect 302 | Client tự follow redirects | Tắt follow trong test; kiểm tra Gateway outbound client riêng |
| 503 chỉ xảy ra trên một replica | Route/config/discovery mismatch | E2E tới từng instance |
| 401/403 chỉ xảy ra trên `/actuator` | Management context/security khác | Kiểm tra management port/matcher |
| MockMvc tests xanh nhưng CPU cao khi load | Không test connector threads/HTTP pool | Load test bounded, thread/connection metrics |

### Quy trình điều tra 10 bước

1. **Xác định điểm vào:** MockMvc hay HTTP client? Direct Gateway hay qua ingress?
2. **Xác nhận stack:** Gateway Server Web MVC/Servlet, không lẫn reactive Gateway Server.
3. **Xác minh ứng dụng đang chạy:** MockMvc có thể chạy không cần HTTP listener; RANDOM_PORT có thật và sẵn sàng chưa?
4. **Spring Security:** Request bị chặn ở authentication, authorization hay CSRF trước route?
5. **Route binding:** Namespace YAML và Java DSL/factory có được nạp không?
6. **Predicates:** Path, Method, Host và Header match thế nào khi Servlet đã normalize URL?
7. **Filters:** StripPrefix/SetRequestHeader/RewritePath biến đổi đầu vào thành gì?
8. **Outbound:** Có HTTP attempt thật không? ServiceInstance, DNS/TCP/TLS/pool/timeout thế nào?
9. **Response:** Backend status hay fallback/error handler? Headers/body/encoding cuối ra sao?
10. **Tái hiện:** Dùng fixture và profile cô lập, đảm bảo cùng version/container, không đổi policy bảo mật để test pass.

Đặc biệt, nếu lỗi chỉ xảy ra ở HTTP client, **không nên sửa Mockito mock của controller** trước khi kiểm tra socket, forwarded headers và real JWT. Ngược lại, nếu lỗi chỉ xảy ra trong MockMvc, cần xem có mock server request thiếu context path/headers hoặc test slice không nạp đúng filters không.

## 23. Bài thực hành: kiểm chứng cùng một route bằng hai cách

**Bối cảnh:** Đội phát triển có một Gateway Server Web MVC proxy Catalog và Orders. Catalog là API đọc; Orders yêu cầu access token hợp lệ. Bạn được giao xác nhận trước khi triển khai rằng route/path/header đúng, security không bị bypass, backend không nhận requests không cần thiết và HTTP client thực nhìn thấy kết quả hợp đồng.

### Phần A — Khởi tạo dự án thử nghiệm

1. Chọn **Spring Boot + Spring Cloud BOM** tương thích với Gateway Server Web MVC, JDK phù hợp, test dependencies và `spring-security-test` khi cần.
2. Tạo một Spring Boot application sử dụng **Servlet Web MVC**, không vô tình chạy Server WebFlux.
3. Đưa route Catalog từ phần 5 vào test profile, dùng đúng namespace của release.
4. Dùng `CatalogStubFixture` ở phần 6 để sinh một URL backend từ port động.
5. Cấp URI stub cho route bằng `@DynamicPropertySource`; không gọi backend staging.
6. Khởi động Gateway với `@SpringBootTest(RANDOM_PORT)` và `@AutoConfigureMockMvc`.
7. Nếu đã bật Spring Security cho Catalog, dùng auth/permission test phù hợp; không lén bỏ security production bằng một profile test không được review.

### Phần B — Kiểm tra bằng MockMvc

1. Gửi GET hợp lệ `/edge/catalog/items/42?lang=vi`.
2. Assert response HTTP 200, Content-Type JSON và body mong đợi.
3. Assert backend `HITS=1`, method `GET`, raw path `/catalog/items/42`, raw query `lang=vi`.
4. Gửi header `X-Gateway-Probe: attacker` từ client, xác minh backend **chỉ thấy giá trị tin cậy** `catalog-edge` trong policy `SetRequestHeader`.
5. Gửi POST tới route GET-only, xác minh backend HITS không tăng.
6. Gửi URL không match Catalog, xác minh không gọi nhầm backend.
7. Cho stub trả 404 và 503, xác minh response client không bị đổi thành 200 ngoài contract.

### Phần C — Kiểm tra bằng HTTP client thật

1. Lấy inbound port Gateway từ `@LocalServerPort`.
2. Tạo JDK `HttpClient` có test timeout hợp lý và redirect policy rõ ràng.
3. Gửi cùng GET tới `http://127.0.0.1:<port>/edge/catalog/items/42`.
4. Assert status/Content-Type/body ở **response thực từ Servlet container**.
5. So sánh backend journal của request này với MockMvc: cùng path, query và marker.
6. Thử `/edge/catalog/items/busy` rồi kiểm tra status 503.
7. Gửi encoded slash/plus/query đặc biệt bằng URI hợp lệ; ghi lại chỗ nào container reject hoặc decode khác với MockMvc.
8. Ghi rõ điều gì HTTP client chứng minh mà MockMvc không thể chứng minh, đặc biệt inbound socket/TLS/encoding.

### Phần D — Bảo mật negative tests

1. Bật Servlet `SecurityFilterChain` cho Orders.
2. Với anonymous GET Orders, kỳ vọng bị từ chối trước backend.
3. Với mock JWT thiếu `SCOPE_orders.read`, kỳ vọng 403 theo policy.
4. Với signed test JWT đúng issuer/audience/scope qua HTTP client, kiểm tra access và backend authorization (tenant/ownership) riêng.
5. Với JWT hết hạn, chữ ký sai hoặc audience sai, xác minh resource server từ chối.
6. Gửi `X-User-Role: ADMIN` mà không có token tin cậy; không được cấp quyền.
7. Nếu có Actuator, kiểm tra management port và bảo vệ route listing riêng, không nhầm với Gateway route filters.

### Phần E — Độ tin cậy và fault injection

1. Stub trả 503 cố định; kiểm tra final status và **số attempts** theo cấu hình Retry của Gateway MVC.
2. Stub trả 503 lần đầu/200 lần sau; kiểm tra số lần gọi và thời gian tổng.
3. Mô phỏng TCP refused, response delay và reset để phân biệt HTTP error với transport failure.
4. Test CircuitBreaker OPEN: inbound request vẫn có response theo policy, backend **không nhận call**.
5. Test rate limiting: vượt quota, requests bị chặn trước backend.
6. Nếu dùng `lb://`, cung cấp instances test và mô phỏng no-instance.
7. Test TLS failure với HTTPS backend giả và CA không được trust, không tắt verification.
8. Với upload hoặc SSE, kiểm tra giới hạn memory/streaming qua HTTP client thật, không ép MockMvc mô phỏng hoàn toàn network behavior.

### Phần F — So sánh hai cách kiểm thử

Điền bảng sau bằng **kết quả thực chạy**, không sao chép giá trị kỳ vọng làm kết quả:

| Tiêu chí | MockMvc | HTTP client thật | Kết luận |
| --- | --- | --- | --- |
| Có mở inbound TCP port không? | Không cần | Có | |
| Có chạy Spring MVC HandlerMapping không? | Có với context phù hợp | Có | |
| Có gọi HTTP outbound thật tới stub không? | Có thể có | Có | |
| Có kiểm tra được backend path/header không? | Có với stub/journal | Có với stub/journal | |
| Có kiểm tra inbound TLS handshake không? | Không | Có khi test HTTPS | |
| Có kiểm tra socket disconnect không? | Không đầy đủ | Có trong giới hạn setup | |
| Có test auth matcher không? | Có | Có | |
| Có validate signed JWT thật không? | Không nếu chỉ dùng `jwt()` mock | Có khi dùng decoder/test IdP | |
| Có thể test HTTP content encoding/framing thực không? | Hạn chế | Có | |
| Có phát hiện retry amplification không? | Chỉ khi đo backend attempts | Có khi đo backend attempts | |

### Phần G — Báo cáo cần nộp

- **Version matrix:** Spring Boot, Spring Cloud Gateway Server Web MVC, Java, Servlet container.
- **Test context:** MockMvc hay RANDOM_PORT, profile và backend fixture/ports.
- **Sơ đồ call path:** client/MockMvc → Security → DispatcherServlet → Gateway MVC → outbound HTTP stub.
- **Kết quả route:** raw path/query, method, inbound và outbound headers đã allowlist.
- **HTTP contract:** status/headers/body của client với 200, 404, 503 và lỗi transport.
- **Security evidence:** anonymous/wrong scope/signed JWT; backend counter bằng 0 khi bị chặn.
- **Reliability evidence:** retry attempts, breaker OPEN, timeout, rate limiting.
- **Transport evidence:** TLS, encoded path, streaming/body lớn theo khả năng của bài lab.
- **CI evidence:** chạy lặp lại không port conflict, không test-order dependency và không lộ secrets.

**Tiêu chí đạt:** Người học không chỉ chỉ ra **cách gọi `MockMvc.perform()` hay `HttpClient.send()`**, mà còn chứng minh được **mỗi lời khẳng định về Gateway bằng đúng bằng chứng ở đúng tầng**, đồng thời biết giới hạn của từng công cụ.

## 24. Những phản mẫu cần loại khỏi bộ kiểm thử

| Phản mẫu | Vì sao nguy hiểm | Thay bằng |
| --- | --- | --- |
| Chỉ assert HTTP 200 | Có thể do fallback/cache, không có upstream call | Assert backend counter và path/header |
| Dùng `@WebMvcTest` để kết luận toàn Gateway MVC routing hoạt động | Không nạp đủ Gateway auto-configuration | Full context khi test route |
| Xem MockMvc là inbound TCP socket | Không kiểm tra connector/TLS/framing | HTTP client đến RANDOM_PORT |
| Mock một service bean rồi kết luận Gateway đã proxy HTTP đúng | Không có outbound request | HTTP stub qua socket |
| Gắn `MockRestServiceServer` vào RestClient không được Gateway dùng | Mock không bắt request thật | Kiểm tra client bean/integration hoặc HTTP stub |
| Hardcode port 8080/9001 cho tất cả tests | Port conflict và CI flakes | Port 0/RANDOM_PORT + DynamicPropertySource |
| Gửi test request đến Catalog staging/production | Có side effect/data dependence | Backend stub/test namespace |
| Dùng `AddRequestHeader` để bảo đảm overwrite header giả mạo | Có thể chỉ thêm giá trị mới | `SetRequestHeader` hoặc header sanitizer |
| Dùng `X-User-Id` do client gửi làm principal | Bypass authorization | Signed JWT/mTLS identity đáng tin |
| Test `.with(jwt())` rồi kết luận issuer/audience được verify | Mock authentication bỏ qua real JWT decoder | Signed test token + HTTP client |
| Bỏ SecurityFilterChain trong mọi integration test | Không thấy 401/403 và policy drift | Có security integration suite riêng |
| Tắt CSRF vô điều kiện để test POST xanh | Có thể che lỗ hổng cookie/session auth | Thiết kế CSRF theo auth model |
| Thử retry nhưng chỉ xem status cuối | Không thấy 10 attempts tới backend | Request journal + attempt budget |
| Circuit OPEN nhưng không reset state giữa tests | Test-order dependency | Fixture per-test, reset có kiểm soát |
| Dùng sleep dài rồi chờ kết quả | Chậm và flaky | Clock/controlled delay, timeout bounded |
| Gửi SSL request với trust-all certificate | Không kiểm tra TLS security | Truststore test và negative cert cases |
| Dùng raw HTTP body toàn bộ trong logs | Lộ token/PII và nổ cardinality | Data test, metadata allowlist, content hash |
| Gộp SSE vô hạn thành `byte[]` | Tăng memory, treo test | Streaming client, bounded read |
| Thấy HTTP 404 rồi mặc định route không match | Backend cũng có thể trả 404 | Counter và trace |
| Đòi một load balancer chia 50/50 qua hai requests | Ngẫu nhiên, thuật toán/cache khác | Kiểm thử phân phối có mẫu và config cố định |
| Thử POST/DELETE management endpoints trên production để chứng minh bị chặn | Có thể thực hiện thay đổi thật nếu config sai | Test sandbox, network/security policy |
| Bỏ qua lỗi test flake vì lần sau pass | Che race, timeout hoặc route drift | Tái hiện/giải thích nguyên nhân |

## 25. Checklist trước khi merge thay đổi Gateway MVC

Một pull request thay đổi route/filter/security nên có ít nhất:

~~~text
[ ] BOM/starter và property namespace đúng Gateway Server Web MVC.
[ ] Route Path/Method/Host predicates được kiểm tra bằng request thật.
[ ] StripPrefix/RewritePath giữ method, raw query và encoding theo contract.
[ ] Headers outbound được kiểm tra từ backend request journal.
[ ] Headers response/status/body được kiểm tra từ phía client.
[ ] Không forward token/cookie sang upstream không có quyền nhận.
[ ] Không tin spoofed Host/X-Forwarded-*/X-User-* từ client.
[ ] Anonymous/insufficient-scope requests không gọi backend.
[ ] Có test signed JWT decoder khi thay đổi authn/issuer/audience.
[ ] 404 route miss khác 404 backend; 503 backend khác transport error.
[ ] Retry/circuit/rate limit đếm số upstream attempts và không tạo storm.
[ ] Timeout/TLS hostname verification có negative tests.
[ ] Large body/streaming/cancellation được kiểm tra khi API liên quan.
[ ] Test sử dụng random ports và fixture cleanup rõ ràng.
[ ] Không gọi staging/production trừ khi e2e được phê duyệt.
[ ] Không log credentials, PII hoặc raw sensitive HTTP payload.
[ ] CI chạy ổn định, test không phụ thuộc thứ tự/parallel race.
~~~

Checklist không thay threat modeling hoặc SLO review; nó giúp những thay đổi nhỏ như **thêm một header, đổi một route predicate hoặc chỉnh retry** không vô tình làm Gateway trở thành nơi mở rộng quyền hoặc khuếch đại tải.

## 26. Tổng kết

- **Gateway Server Web MVC** chạy trên Servlet/Spring MVC/WebMvc.fn; kiểm thử phải dùng đúng MVC runtime, khác với Server WebFlux.
- **`MockMvc`** rất phù hợp cho route mapping, MVC filters, Servlet Security và response assertions nhanh, **nhưng không mở inbound TCP socket** và không tự mock outbound HTTP.
- **HTTP client thật** tới `@SpringBootTest(RANDOM_PORT)` bổ sung kiểm tra transport/HTTP serialization, network errors, TLS và streaming; không thay backend assertions.
- **Backend HTTP stub với request journal** là cầu nối quan trọng: chứng minh outbound method/path/query/header/body và số retry attempts, tránh kết luận sai chỉ từ HTTP status cuối.
- **`@WebMvcTest`** là MVC slice test; **`@SpringBootTest`** phù hợp hơn khi cần Gateway auto-configuration đầy đủ. Test context và starter phải đúng version/namespace.
- **Security tests có hai cấp:** MockMvc với `.with(jwt())` để kiểm tra authorization rules, và signed JWT qua HTTP client/real decoder để xác minh issuer, audience, chữ ký và thời hạn.
- **Route predicates và Gateway filters không thay authorization**. Test header spoofing, encoded paths và trust boundary; dùng `SetRequestHeader` khi cần overwrite giá trị client giả.
- **Fault tests cần tách HTTP errors khỏi transport failures**, đo retries, circuit breaker, rate limiting và client-visible final status; không cố “làm xanh” bằng infinite retry hay tắt TLS verification.
- **Body lớn, SSE, WebSocket, client disconnect, HTTP/2 và ingress/mTLS** cần full HTTP/e2e tests có chọn lọc, vì MockMvc không mô phỏng đầy đủ socket và streaming.
- **CI ổn định** dùng random ports, backend test riêng, deterministic fixtures, timeout hữu hạn và test secrets; không dựa vào dữ liệu sản xuất hay trạng thái từ tests trước.

Một bộ kiểm thử **SPRING_CLOUD_GATEWAY** đáng tin không phải bộ test có nhiều lời gọi `status().isOk()` nhất, mà là bộ test **biết chính xác điều gì được mock, điều gì thực sự chạy qua HTTP và điều gì đã được chứng minh tại backend cũng như client**. Hãy dùng **MockMvc để kiểm tra hành vi Servlet/MVC**, và **HTTP client cùng backend stub để kiểm chứng hợp đồng proxy ở cấp mạng**, rồi mở rộng sang TLS, discovery và nhiều replica khi rủi ro hệ thống yêu cầu.
