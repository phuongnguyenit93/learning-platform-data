# Kiểm chứng đường dẫn, header, body và status sau chuyển tiếp

## 1. Vì sao HTTP 200 chưa đủ chứng minh Gateway chuyển tiếp đúng?

**Spring Cloud Gateway** thường nằm trước các microservices để chọn tuyến theo route predicate, chạy filter chain, sửa đường dẫn/header, tìm service instance và thực hiện xác thực, giới hạn lưu lượng, circuit breaker, retry, TLS, observability. Khi Gateway được cấu hình sai, request có thể vẫn trả **HTTP 200**, nhưng đến **sai dịch vụ, sai path, sai body hoặc thiếu header quan trọng**.

Xét hợp đồng của API đơn hàng:

~~~text
Client gọi:
  POST /api/orders/create?source=mobile
  X-Request-Id: req-42
  Content-Type: application/json

  {"sku":"PEN-01","quantity":2}

Gateway:
  route = orders-api
  StripPrefix=1
  SetRequestHeader=X-Gateway-Source, edge
  RemoveRequestHeader=X-Debug-Only

Upstream thực sự phải nhận:
  POST /orders/create?source=mobile
  X-Gateway-Source: edge
  Content-Type: application/json

  {"sku":"PEN-01","quantity":2}

Upstream trả:
  201 Created
  Content-Type: application/json
  X-Upstream-Result: created
  {"accepted":true}

Client phải nhận:
  201 Created
  body JSON {"accepted":true}
  header X-Upstream-Result nếu không có filter xóa/đổi header này
~~~

Một test chỉ chạy `curl` và thấy `201` không thể chứng minh rằng backend nhận đúng `quantity=2`, path đã bỏ `/api`, header giả mạo đã bị loại, hay Gateway không gọi backend hai lần do Retry.

Đó là lý do bài **“Kiểm chứng đường dẫn, header, body và status sau chuyển tiếp”** trong chương **Kiểm thử** của module **SPRING_CLOUD_GATEWAY** tập trung vào **hợp đồng HTTP nhìn từ hai phía của Gateway**.

Sau bài này, bạn có thể:

1. Lập bảng kỳ vọng cho **request tới Gateway**, **request đến upstream** và **response trả client**.
2. Kiểm chứng route predicate, `StripPrefix`, `RewritePath`, query string và URL encoding.
3. Phân biệt kiểm thử header ở **request outbound** với **response inbound**, kể cả header có nhiều giá trị và hop-by-hop headers.
4. Kiểm thử JSON, form, binary, body rỗng và stream mà không giả định mọi byte luôn giữ nguyên khi có body transformation.
5. Kiểm tra status `201/204/302/400/401/403/404/429/500/503` và phân biệt nguồn tạo status.
6. Dùng **WebTestClient + một mock upstream thật** để đi qua HTTP routing pipeline của Gateway Server WebFlux.
7. Tạo test xác định được lỗi mà không phụ thuộc Internet, cổng cố định hoặc các upstream production.
8. Mở rộng sang retry, circuit breaker, rate limiting, service discovery, TLS và tracing.

> **Phạm vi:** ví dụ chính dùng **Spring Cloud Gateway Server WebFlux** và JUnit 5. Spring Cloud Gateway Server Web MVC hoặc Proxy Exchange MVC có framework/filter APIs khác, dù nguyên tắc kiểm chứng HTTP ở hai đầu vẫn tương tự. Các namespace cấu hình Gateway 4.x/5.x được phân biệt rõ. Những đoạn mã là ví dụ học tập, **không phải kết quả test đã được thực thi trong bài này**.

## 2. Định nghĩa đúng “đã chuyển tiếp thành công”

Đừng đồng nhất `Gateway response` với `backend request`. Một luồng điển hình gồm:

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Test HTTP Client
    participant G as Gateway WebFlux
    participant U as Mock Upstream
    C->>G: HTTP method + public path + headers + body
    G->>G: Match route predicates
    G->>G: Request filters: path/header/body
    G->>U: HTTP method + transformed path + headers + body
    U-->>G: Status + headers + response body
    G->>G: Response filters / status mapping
    G-->>C: Final HTTP status + headers + body
    Note over C,U: Test phải assert cả request vào mock và response ra client
~~~

Bốn nhóm tín hiệu cần đo:

| Nhóm | Câu hỏi cần kiểm chứng | Bằng chứng mạnh |
| --- | --- | --- |
| **Path/URI** | Request được định tuyến đến đúng route/upstream và path chưa bị sửa sai? | Mock upstream ghi method, path, query |
| **Headers** | Những header bắt buộc được thêm/sửa/xóa đúng chiều, không lộ secret? | Mock ghi request headers; client test đọc response headers |
| **Body** | Body còn đúng byte/JSON schema/content type sau proxy? | Mock nhận raw body, JSON parser, response body assertion |
| **Status** | Client thấy status gì, status đó đến từ backend hay filter/Gateway? | Mock chủ động trả status, test so sánh ở phía client và upstream counter |

Một test end-to-end đáng tin thường có **hai đầu quan sát**: client nhìn response và mock backend nhìn request. Nếu chỉ assert response từ Gateway, một route sai có thể đi đến một backend khác cũng trả `200`.

### 2.1. Ba loại kết quả đừng trộn lẫn

- **Routing success:** route được chọn và upstream nhận request đúng hợp đồng.
- **Backend business success:** backend thực thi nghiệp vụ và trả status/body phù hợp, ví dụ 201.
- **Gateway presentation success:** filters biến đổi response đúng chính sách và client nhận status/body cuối cùng đúng.

Gateway có thể route đúng nhưng backend trả 422 vì dữ liệu không hợp lệ. Đó không phải lỗi route. Gateway có thể route sai nhưng backend giả trả 200. Đó là lỗi route dù status đẹp.

## 3. Các tầng kiểm thử và thứ tự nên áp dụng

| Tầng | Công cụ | Kiểm tra tốt nhất | Hạn chế |
| --- | --- | --- | --- |
| Unit cho predicate/filter riêng | `MockServerWebExchange`, mock `GatewayFilterChain` | Điều kiện match, attribute/header/path mutation | Không chứng minh HTTP outbound thực |
| Test WebFlux mock application | `WebTestClient.bindToApplicationContext(...)` | Handler/filter WebFlux trong mock context | Chưa chắc chạy qua Netty routing socket thật |
| **HTTP integration test** | `@SpringBootTest(RANDOM_PORT)` + `WebTestClient.bindToServer()` + MockWebServer/WireMock | **Public request → Gateway → HTTP upstream → Gateway response** | Khởi động chậm hơn unit test |
| Contract test giữa services | Pact/OpenAPI + mock hoặc provider verification | Định dạng schema, status, header contract | Cần versioning provider/consumer |
| E2E staging | Gateway + service discovery + TLS + auth + real environment | Hạ tầng, nhiều replicas, resilience, network policy | Dễ flaky, tốn thời gian/cost |

**Nguyên tắc:** chạy test nhanh và ổn định ở tầng thấp, nhưng **ít nhất một nhóm phải đi qua HTTP server thật và mock upstream** để chứng minh `NettyRoutingFilter`/HTTP client routing đã hoạt động.

Với Server WebFlux, `WebTestClient.bindToServer()` nối đến **một HTTP server đang chạy**, khác `bindToController()` hoặc mock application context. Spring Boot `RANDOM_PORT` chạy server trong tiến trình test trên một cổng hệ điều hành cấp động.

### 3.1. Kiểm thử không cần backend Internet công khai

Không trỏ integration test mặc định đến `https://example.org`, một dịch vụ staging dùng chung hoặc một service production:

- Response có thể thay đổi theo thời gian.
- Network/TLS/DNS có thể làm test chập chờn.
- Thay đổi dữ liệu thật là nguy hiểm.
- Không kiểm soát status/body/headers khi muốn tái hiện lỗi.

Thay bằng **mock upstream điều khiển được**, có khả năng enqueue response và ghi từng request đã nhận. Ví dụ phổ biến là **OkHttp MockWebServer** hoặc WireMock.

## 4. Xây “hợp đồng hai chiều” trước khi viết test

Một bảng test case nên có cả input, cấu hình Gateway và expected output:

| Field | Client gửi | Gateway dự kiến làm | Upstream phải nhận |
| --- | --- | --- | --- |
| HTTP method | POST | Giữ nguyên | POST |
| Path | `/edge/echo` | `StripPrefix=1` | `/echo` |
| Query | `?request=integration` | Không sửa query | `?request=integration` |
| Header `X-Gateway-Source` | `spoofed` | `SetRequestHeader=..., gateway-test` | `gateway-test` |
| Header `X-Debug-Only` | `must-not-leak` | `RemoveRequestHeader` | Không tồn tại |
| Content-Type | `application/json` | Không đổi | `application/json` |
| Body | `{"item":"pen","quantity":2}` | Không sửa | Cùng JSON hợp đồng |

Và một bảng response:

| Field | Mock upstream trả | Response filter | Client cần thấy |
| --- | --- | --- | --- |
| Status | `201 Created` | Không đổi | 201 |
| Content-Type | `application/json` | Không đổi | JSON |
| Header `X-Upstream-Result` | `v1` | Không đổi | `v1` |
| Header `X-Edge-Test` | Không có | `AddResponseHeader` | `enabled` |
| Body | `{"accepted":true}` | Không đổi | JSON tương đương |

**Hai bảng chính là test oracle**: nguồn kỳ vọng độc lập với kết quả Gateway trả. Nếu sinh toàn bộ expected path bằng đúng một function đang dùng trong filter thật, bạn có thể sao chép cả lỗi vào test và nhận false positive.

## 5. Cấu hình route test cho Gateway Server WebFlux

### 5.1. Phiên bản theo namespace

Những tài liệu WebFlux 4.x phổ biến khai báo route tại:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: example
          uri: http://localhost:8081
          predicates:
            - Path=/edge/**
~~~

Trong nhánh **Server WebFlux 5.x**, cấu hình được tổ chức dưới:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: example
              uri: http://localhost:8081
              predicates:
                - Path=/edge/**
~~~

Hai đoạn là **lựa chọn theo release**, không phải hai route cần khai báo đồng thời. Với Gateway Server Web MVC, property là `webmvc` và các Java filter APIs cũng khác. Một route config không được bind có thể làm test 404, dù YAML hợp lệ.

### 5.2. Cấu hình riêng dành cho integration test

Tạo trong project mẫu **`src/test/resources/application-gateway-contract.yml`** (đây là **đường dẫn ví dụ trong bài học**, không phải file worker sẽ tạo trong repository hiện tại):

~~~yaml
server:
  port: 0

spring:
  cloud:
    gateway:
      routes:
        - id: contract-proxy
          uri: ${test.backend.uri}
          predicates:
            - Path=/edge/**
          filters:
            - StripPrefix=1
            - SetRequestHeader=X-Gateway-Source, gateway-test
            - RemoveRequestHeader=X-Debug-Only
            - AddResponseHeader=X-Edge-Test, enabled
~~~

Đây là ví dụ cho **Gateway Server WebFlux 4.x**. Test sẽ gắn profile `gateway-contract`, dùng `@DynamicPropertySource` để cung cấp `test.backend.uri` là URL mock HTTP server **được cấp port động**.

Giải thích kỹ filter:

- `Path=/edge/**` chọn các requests bắt đầu với `/edge/`.
- `StripPrefix=1` xóa segment `edge`; `/edge/echo` thành `/echo`.
- `SetRequestHeader` **thay** giá trị header cùng tên bằng `gateway-test`, không tin giá trị `spoofed` của client.
- `RemoveRequestHeader` **loại bỏ** header do client gửi trước outbound.
- `AddResponseHeader` thêm header cho **response gửi về client**, không phải request tới mock.
- Không có `Retry`, `SetStatus`, `ModifyRequestBody` hoặc `ModifyResponseBody` trong route này: việc kiểm thử “proxy giữ nguyên” nhờ vậy có contract rõ ràng.

Một test độc lập phải biết chính xác filter nào được áp dụng. Nếu cấu hình còn `default-filters` hoặc `GlobalFilter` của project thực, hãy đưa chúng vào test expectations hoặc dùng một application profile cô lập; đừng tắt security/filter trong production chỉ để test dễ hơn.

### 5.3. Cách chuyển sang cấu hình WebFlux 5.x

Khi chạy cùng bài với Gateway WebFlux 5.x, giữ toàn bộ route entries nhưng chuyển parent key:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: contract-proxy
              uri: ${test.backend.uri}
              predicates:
                - Path=/edge/**
              filters:
                - StripPrefix=1
                - SetRequestHeader=X-Gateway-Source, gateway-test
                - RemoveRequestHeader=X-Debug-Only
                - AddResponseHeader=X-Edge-Test, enabled
~~~

Chọn **một** namespace theo starter và release đang dùng. Nếu test có response `404` ngay từ Gateway và mock không thấy request, hãy kiểm tra **config binding/route matching trước khi kết luận upstream lỗi**.

## 6. Dependencies cho test

Với dự án Maven Gateway WebFlux 4.x đã có Spring Boot parent/BOM và Spring Cloud BOM tương thích:

~~~xml
<!-- Gateway dependency phải được quản lý đúng release train. -->
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway</artifactId>
</dependency>

<!-- JUnit 5, AssertJ, Spring Test và WebTestClient tools -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>

<!-- Mock upstream HTTP server; ví dụ dùng API dòng 4.x -->
<dependency>
    <groupId>com.squareup.okhttp3</groupId>
    <artifactId>mockwebserver</artifactId>
    <version>4.12.0</version>
    <scope>test</scope>
</dependency>
~~~

**Lưu ý version và dependency management:**

- Tên `spring-cloud-starter-gateway` thuộc nhánh được dùng phổ biến trước khi tách tên `spring-cloud-starter-gateway-server-webflux` ở các release mới. Chọn đúng starter của project.
- Ví dụ Java bên dưới dùng API của **MockWebServer 4.x**: `MockResponse`, `MockWebServer`, `RecordedRequest`; dòng 5.x có API khác và phải chuyển mã tương ứng.
- Nếu tổ chức quản lý version MockWebServer qua BOM/version catalog riêng, dùng version được phê duyệt thay vì rập khuôn `4.12.0`.
- Không tự thêm `spring-boot-starter-web` MVC vào Gateway WebFlux test để “có HTTP server”.
- Một số project đã có Spring Security mặc định: test cần mock identity/token hoặc cấu hình security riêng; route khớp không có nghĩa được bỏ qua authentication.

## 7. Test tích hợp hoàn chỉnh: WebTestClient + MockWebServer

**Mục tiêu:** gửi một POST đến Gateway thật, khiến mock upstream trả 201, rồi kiểm tra **cả outbound request và response cuối**.

### 7.1. Test class

~~~java
package example.gateway.testing;

import java.io.IOException;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
@ActiveProfiles("gateway-contract")
class GatewayForwardingContractTest {

    // Chỉ dùng chung trong class minh họa: các test không chạy song song.
    private static final MockWebServer upstream = startUpstream();

    @LocalServerPort
    int gatewayPort;

    private static MockWebServer startUpstream() {
        MockWebServer server = new MockWebServer();
        try {
            server.start();
            return server;
        } catch (IOException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    @DynamicPropertySource
    static void configureTarget(DynamicPropertyRegistry registry) {
        registry.add("test.backend.uri", () -> upstream.url("/").toString());
    }

    private WebTestClient client() {
        return WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + gatewayPort)
                .build();
    }

    @Test
    void forwardsPathHeadersBodyAndStatus() throws Exception {
        upstream.enqueue(new MockResponse()
                .setResponseCode(201)
                .addHeader("Content-Type", "application/json")
                .addHeader("X-Upstream-Result", "v1")
                .setBody("{\"accepted\":true}"));

        String payload = "{\"item\":\"pen\",\"quantity\":2}";

        client().post()
                .uri("/edge/echo?request=integration")
                .header("X-Gateway-Source", "spoofed")
                .header("X-Debug-Only", "must-not-leak")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(payload)
                .exchange()
                .expectStatus().isCreated()
                .expectHeader().contentType(MediaType.APPLICATION_JSON)
                .expectHeader().valueEquals("X-Upstream-Result", "v1")
                .expectHeader().valueEquals("X-Edge-Test", "enabled")
                .expectBody()
                .jsonPath("$.accepted").isEqualTo(true);

        RecordedRequest received =
                upstream.takeRequest(5, TimeUnit.SECONDS);

        assertThat(received).isNotNull();
        assertThat(received.getMethod()).isEqualTo("POST");
        assertThat(received.getPath())
                .isEqualTo("/echo?request=integration");
        assertThat(received.getHeader("X-Gateway-Source"))
                .isEqualTo("gateway-test");
        assertThat(received.getHeader("X-Debug-Only")).isNull();
        assertThat(received.getHeader("Content-Type"))
                .startsWith("application/json");
        assertThat(received.getBody().readUtf8())
                .isEqualTo(payload);
    }

    @Test
    void preservesAnUpstream422WithoutSetStatusOrFallback()
            throws Exception {
        upstream.enqueue(new MockResponse()
                .setResponseCode(422)
                .addHeader("Content-Type", "application/json")
                .setBody("{\"code\":\"INVALID_INPUT\"}"));

        client().post()
                .uri("/edge/validate")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"quantity\":0}")
                .exchange()
                .expectStatus().isEqualTo(422)
                .expectBody()
                .jsonPath("$.code").isEqualTo("INVALID_INPUT");

        RecordedRequest received =
                upstream.takeRequest(5, TimeUnit.SECONDS);
        assertThat(received).isNotNull();
        assertThat(received.getPath()).isEqualTo("/validate");
    }

    @Test
    void missingRouteDoesNotHitTheUpstream() {
        int before = upstream.getRequestCount();

        client().get()
                .uri("/unmatched/path")
                .exchange()
                .expectStatus().isNotFound();

        assertThat(upstream.getRequestCount()).isEqualTo(before);
    }

    @AfterAll
    static void shutdownMock() throws IOException {
        upstream.shutdown();
    }
}
~~~

### 7.2. Vì sao test này mạnh hơn test chỉ assert status?

**Phía client:** test kiểm tra 201, `Content-Type`, header upstream `X-Upstream-Result`, header Gateway thêm `X-Edge-Test`, và body `accepted=true`.

**Phía upstream:** MockWebServer cung cấp `RecordedRequest` để assert:

- Method là POST.
- Path thực tế là `/echo`, nghĩa là `StripPrefix=1` đúng.
- Query `request=integration` được giữ.
- Header `X-Gateway-Source` bị thay từ `spoofed` thành `gateway-test`.
- `X-Debug-Only` bị xóa trước khi đi tới backend.
- `Content-Type` vẫn là JSON.
- Raw JSON body ở mock bằng payload client gửi vì route không dùng body rewrite.

Mock response `422` ở test thứ hai chứng minh Gateway **không tự biến mọi upstream 4xx thành 200/500** khi không có filter/error handler thay đổi status. Test thứ ba chứng minh **request không khớp route không đi tới upstream**. Nếu ứng dụng có local handler riêng cho `/unmatched/path`, phải thay expected 404 theo contract nhưng vẫn assert upstream request count không tăng.

### 7.3. Những điều cần giữ ổn định

- Class mẫu giả định **không chạy test methods song song**, bởi mọi method chia sẻ hàng đợi `upstream.enqueue(...)`. Nếu JUnit parallel execution được bật, hãy cô lập mock server/context cho mỗi test hoặc dùng `@Execution(SAME_THREAD)` và cấu hình phù hợp.
- Không assert số port cụ thể. Gateway và mock đều dùng **ephemeral port**.
- `@DynamicPropertySource` cung cấp property **trước khi ApplicationContext bind Gateway route**. Không đổi property sau khi route đã được tạo rồi giả định Gateway tự refresh.
- `MockWebServer.takeRequest(timeout)` phải có timeout để tránh treo CI khi route sai.
- Không để các test khác trong cùng Spring context cache tiếp tục dùng MockWebServer đã shutdown; tách class/profile hoặc quản lý lifecycle đúng.
- Test này **không tự khởi động một mock order-service thật**; nó mô phỏng HTTP server upstream và thu request ở network boundary.
- Khi cấu hình security, rate limiting hoặc retry thực tế, expectations phải được mở rộng; không ngầm bỏ filters bảo mật ở môi trường production.

## 8. Kiểm chứng đường dẫn: route predicate, StripPrefix và query

### 8.1. Những path cần test tối thiểu

Một route `Path=/edge/**` và `StripPrefix=1` nên có ma trận:

| Input path | Expected upstream path | Điều cần kiểm |
| --- | --- | --- |
| `/edge/echo` | `/echo` | Loại một segment |
| `/edge/v1/orders/42` | `/v1/orders/42` | Giữ các segments còn lại |
| `/edge/echo?lang=vi` | `/echo?lang=vi` | Query không tự biến mất |
| `/edge/` | `/` nếu route và filter hỗ trợ path đó | Trường hợp cuối path |
| `/other/echo` | Không được proxy theo route này | Route predicate |
| `/edge-old/echo` | Không được coi là `/edge/**` | Ranh giới segment |
| `/edge/a%20b` | Semantics path có dấu cách đúng | URI encoding |
| `/edge/a%2Fb` | Theo policy về encoded slash | Kiểm tra proxy/router/security |
| `/edge/a/../admin` | Được normalize/chặn theo policy | Path traversal, matching khác nhau |

**Không khẳng định tất cả edge-case trên sẽ được xử lý giống nhau ở mọi Netty/Spring/ingress version.** Đặc biệt, encoded slash `%2F`, dot segments và Unicode path cần test ở **cổng thật và upstream thật/mô phỏng** đúng release. Các proxy khác nhau có thể normalize path ở các thời điểm khác nhau.

### 8.2. Query parameters có thứ tự và mã hóa

Nếu nghiệp vụ chỉ yêu cầu `lang=vi`, không nhất thiết assert raw query có đúng thứ tự bytes nếu có nhiều params và client/URI builder thay đổi encoding hợp lệ.

Ví dụ:

~~~text
Client:   /edge/search?q=a%20b&lang=vi
Upstream: /search?q=a%20b&lang=vi
~~~

Một test mức business có thể parse query để assert `q == "a b"` và `lang == "vi"`; test raw URI/encoding có thể kiểm `%20` nếu đây là contract cần giữ chính xác. Đừng dùng `URLDecoder` bừa bãi với đường dẫn URI nếu dấu `+` hay encoded slash có ngữ nghĩa riêng.

### 8.3. RewritePath cần test bắt đúng phần regex

Ví dụ WebFlux 5.x:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: rewrite-orders
              uri: http://localhost:8081
              predicates:
                - Path=/legacy/orders/**
              filters:
                - RewritePath=/legacy/orders/?(?<remaining>.*), /orders/$\{remaining}
~~~

Theo quy tắc cấu hình `RewritePath`, biểu thức `(?<remaining>.*)` lấy phần còn lại; ký hiệu `$\{remaining}` là **dạng escape được tài liệu Gateway minh họa trong YAML** để tránh xử lý placeholder không mong muốn. Khi kiểm tra source trong project thật, phải xác minh YAML parser/property resolver đã đưa replacement chính xác đến filter.

Bảng expected:

| Client path | Upstream path |
| --- | --- |
| `/legacy/orders/42` | `/orders/42` |
| `/legacy/orders/42/items` | `/orders/42/items` |
| `/legacy/orders/` | `/orders/` nếu regex/route match như cấu hình |
| `/legacy/orders-old/42` | Không khớp route này |

Không chỉ assert client nhận 200: một endpoint mock bắt cả `/legacy/orders/42` và `/orders/42` đều có thể trả 200, che giấu lỗi rewrite.

### 8.4. Thứ tự filters và route precedence

Nếu có `PrefixPath`, `StripPrefix`, `RewritePath`, `SetPath` cùng hoạt động, kết quả phụ thuộc **thứ tự thực thi**. Một request có thể khớp nhiều routes; đừng giả định route “cụ thể hơn luôn thắng” khi order và source khác nhau.

Kiểm thử:

1. Route được chọn có ID và order kỳ vọng.
2. Mỗi bước path transform tạo đầu ra đúng.
3. Backend nhận **path cuối cùng** đúng hợp đồng.
4. Những route không nên khớp **không được gọi**.
5. Nếu dùng `lb://`, chọn instance và path transform phải phối hợp đúng, không dựng URL sai sau load balancing.

## 9. Kiểm chứng request headers gửi tới upstream

### 9.1. Header đến Gateway không đồng nghĩa header tới backend

Gateway có thể:

- Thêm header: `AddRequestHeader`.
- Ghi đè header: `SetRequestHeader`.
- Xóa header: `RemoveRequestHeader`.
- Đổi `Host`: `SetRequestHostHeader` hoặc `PreserveHostHeader` theo chủ đích.
- Sinh/chuẩn hóa `Forwarded` và `X-Forwarded-*` qua các filters và trust configuration.
- Loại các headers chỉ có ý nghĩa trên một kết nối HTTP (hop-by-hop).
- Bổ sung trace context qua tracing instrumentation.

Test nên assert **những header nghiệp vụ đã có hợp đồng**, không assert toàn bộ header set phải giống nhau giữa client và backend.

### 9.2. AddRequestHeader khác SetRequestHeader

~~~yaml
filters:
  - AddRequestHeader=X-Lab-Tag, gateway
  - SetRequestHeader=X-Gateway-Source, edge
~~~

`AddRequestHeader` có thể tạo header nhiều giá trị nếu client cũng gửi header cùng tên. `SetRequestHeader` thay thế các giá trị trước đó bằng một giá trị mới.

Nếu cần header chứa **identity/tenant đáng tin**, không chỉ set giá trị mặc định theo route mà bỏ qua Spring Security. Lấy principal đã được xác minh và áp dụng chính sách trust boundary; downstream phải có cơ chế tin cậy riêng.

### 9.3. Header names không phân biệt hoa-thường

`X-Gateway-Source` và `x-gateway-source` là cùng tên về mặt HTTP. Mock HTTP libraries thường hỗ trợ `getHeader(...)` không phân biệt case.

**Không assert thứ tự tuyệt đối của các headers**: HTTP/1.1 và HTTP/2 có thứ tự/representation khác nhau; proxy còn có thể thêm `Via`, `Forwarded` hoặc headers do HTTP client sinh ra.

### 9.4. Hop-by-hop và headers tự tính toán

Những header như `Connection`, `Keep-Alive`, `Transfer-Encoding`, `TE`, `Upgrade` có xử lý đặc biệt. Gateway WebFlux có `HttpHeadersFilters` và `RemoveHopByHop` trước outbound routing.

Do đó:

- Không bắt backend phải nhận `Connection: keep-alive` giống client.
- Không assert `Transfer-Encoding: chunked` phải xuất hiện ở mọi hop.
- `Content-Length` có thể thay đổi/mất khi streaming hoặc body rewrite.
- HTTP/2 có các quy tắc header khác HTTP/1.1.
- `Host` outbound phụ thuộc target URI và preserve-host policy.

Hãy test những headers này **khi chính chúng là contract đặc biệt**, không dùng như cách xác minh route thành công mặc định.

### 9.5. X-Forwarded-For / Proto là trust boundary

Một client có thể tự gửi `X-Forwarded-For`, `X-Forwarded-Proto`. Nếu Gateway đứng sau ingress, việc nhận/sinh/appending các headers forwarded phải dựa trên **trusted proxies** đã cấu hình theo release.

Test nên có cả:

1. Request từ proxy tin cậy: backend nhận thông tin client scheme/host theo policy.
2. Request trực tiếp từ client: header do client tự đặt không được trở thành identity đáng tin.
3. Nhiều proxy hops: danh sách và priority theo contract.
4. Đường inbound HTTPS/outbound HTTP: backend nhìn `proto=https` không có nghĩa outbound socket được TLS bảo vệ.

**Không dùng `X-Forwarded-For` client tự gửi làm rate-limit key hoặc authorization key** nếu chưa xác minh proxy chain. Điều này thuộc cả security và correctness.

## 10. Kiểm chứng response headers phía client

Response sau Gateway có thể giữ, thêm, xóa hoặc dedupe headers:

| Kịch bản | Upstream trả | Gateway filter | Client kỳ vọng |
| --- | --- | --- | --- |
| Giữ header | `X-Upstream-Result: v1` | Không có | `v1` |
| Thêm header | Không có `X-Edge-Test` | `AddResponseHeader=...,enabled` | `enabled` |
| Ghi đè | `X-Feature: old` | `SetResponseHeader=X-Feature,new` | `new` |
| Xóa | `X-Internal-Debug: secret` | `RemoveResponseHeader=X-Internal-Debug` | Không có |
| Trùng CORS header | Gateway và upstream cùng thêm | `DedupeResponseHeader` theo strategy | Một giá trị hợp đồng |
| Redirect | `Location: http://internal/...` | `RewriteLocationResponseHeader` hoặc policy khác | URL public hợp lệ |

**Không mặc định mọi header upstream đều được giữ nguyên**. Những response headers như `Transfer-Encoding`, `Connection`, `Content-Length`, compression và `Set-Cookie` có quy tắc riêng, còn Gateway hoặc upstream filters có thể biến đổi.

### 10.1. DedupeResponseHeader và CORS

Nếu cả Gateway lẫn backend ghi `Access-Control-Allow-Origin`, client có thể thấy nhiều giá trị không hợp lệ cho trình duyệt.

Kiểm thử CORS cần assert:

- Một origin được cho phép chính xác theo policy, không có `*` khi gửi credentials.
- `Access-Control-Allow-Credentials` tương thích với origin.
- Preflight `OPTIONS` được xử lý theo routing/security đúng yêu cầu.
- Header đã được dedupe theo strategy mong muốn.
- Trường hợp origin bị từ chối **không bị mở lại bởi upstream**.

Không xem CORS như authentication: curl/Postman có thể gọi API không bị CORS browser policy kiểm soát. Phải test JWT/session authorization riêng.

### 10.2. Cookies không nên “so sánh chuỗi tổng thể”

`Set-Cookie` có thể có nhiều dòng, các attributes `Secure`, `HttpOnly`, `SameSite`, `Path`/domain cần được test chính xác theo contract. Nếu chỉ sort/concat toàn bộ response headers thành một chuỗi và so sánh, test dễ flaky vì serialization hoặc thứ tự.

Đặc biệt với Gateway trước nhiều backends, kiểm tra `Secure`/domain/path cookies để tránh session collision hoặc leak sang domain không phù hợp.

## 11. Kiểm chứng request body: JSON, form và binary

### 11.1. Khi không có body transformation

Nếu route chỉ làm `StripPrefix`, `SetRequestHeader`, `RemoveRequestHeader` thì nội dung request body thường được proxy theo HTTP semantics. Với một JSON payload nhỏ, test chính có thể assert raw UTF-8 body giống nhau như mục 7.

**Nhưng “body không đổi” có hai mức:**

- **Byte-level equality:** bytes upstream nhận đúng bytes client gửi. Dùng khi payload là chữ ký số, binary hoặc contract thật sự đòi nguyên vẹn.
- **Semantic equality:** JSON parse ra cùng object/fields dù whitespace, thứ tự keys hoặc charset serialization khác. Dùng khi contract chỉ quan tâm dữ liệu.

Nếu route dùng `ModifyRequestBody`, `CacheRequestBody` hoặc custom JSON serializer, byte-level equality có thể **không phù hợp** vì bộ lọc cố ý thay representation.

### 11.2. So JSON theo schema khi có biến đổi

Ví dụ input:

~~~json
{
  "sku": "PEN-01",
  "quantity": 2
}
~~~

Một filter transformation có thể chuẩn hóa:

~~~json
{"sku":"PEN-01","quantity":2,"source":"gateway"}
~~~

Test nên assert cả:

1. `sku` và `quantity` còn đúng.
2. `source` được bổ sung theo policy.
3. `Content-Type` phù hợp, thường là `application/json`.
4. `Content-Length` không bị cố giữ giá trị **trước khi rewrite**.
5. Backend parse JSON thành công.
6. Không có các trường nhạy cảm bị copy ngoài mong muốn.

Không khuyến khích mọi test so raw JSON string khi JSON order/whitespace không phải hợp đồng. Với JSON contract, dùng `jsonPath`, Jackson `JsonNode`, JSONAssert hoặc schema validation.

### 11.3. Body rỗng, null và Content-Type

Cần tách:

| Input | Điều cần kiểm |
| --- | --- |
| GET không body | Không tự sinh JSON body ngoài ý muốn |
| POST có `Content-Length: 0` | Backend nhận body rỗng hợp lệ |
| POST `Content-Type: application/json` nhưng body rỗng | Error/validation theo contract |
| JSON literal `null` | Không nhầm với **không có body** |
| JSON malformed | Status/error mapping đúng, không lộ stack trace |
| Request `text/plain; charset=UTF-8` | Unicode đúng charset |
| Form URL-encoded | Thứ tự/giá trị form params đúng |
| Multipart upload | Boundary, filename, file bytes và size limit |
| Binary `application/octet-stream` | Byte array hoặc checksum khớp |

Với `ModifyRequestBody`, Spring Cloud Gateway WebFlux cung cấp Java DSL để đổi body và có những ngữ nghĩa riêng cho **missing body**. Test phải mô phỏng rõ body vắng mặt, thay vì chỉ gửi `{ }` rồi coi đó là cùng trường hợp.

### 11.4. Không đọc DataBuffer hai lần một cách vô thức

Trong WebFlux, body thường là reactive stream chứa `DataBuffer`. Một custom filter đọc/giải phóng dữ liệu sai có thể làm upstream nhận **body rỗng**, leak buffer hoặc block event loop.

Không cài test logging filter tự dùng `subscribe()` độc lập để “nhìn body” rồi khiến luồng chính không đọc được body. Không `block()` trong Netty event loop. Nếu cần đọc và phát lại body, dùng cơ chế caching/decorating tương thích, giới hạn kích thước và giải phóng buffer đúng.

**Kiểm thử contract nên ghi body ở mock HTTP upstream**, tránh can thiệp vào reactive request pipeline bằng debugger/filter đọc body tràn lan.

### 11.5. Payload lớn và streaming

Với upload/streaming:

- Không dùng `.expectBody(String.class)` cho response hàng trăm MB.
- Kiểm tra streaming/chunk boundaries ở mức phù hợp; chunking trên network **không nhất thiết giữ nguyên** qua proxy.
- So byte count, checksum SHA-256 và content type khi contract yêu cầu.
- Test `413 Payload Too Large` khi dùng `RequestSize`/ingress size limit.
- Test client disconnect/cancellation để thấy Gateway và upstream cleanup đúng.
- Xác minh backpressure và memory usage khi có `CacheRequestBody`, Retry hoặc ModifyBody.
- Đặt timeout test có giới hạn; không để CI treo khi upstream gửi stream vô tận.

Với signed payload/webhook, xác minh chữ ký trên **bytes nhận ở backend**, không chỉ dựa vào JSON fields.

## 12. Kiểm chứng response body: upstream → Gateway → client

Tương tự request body, response có thể:

- Giữ nguyên bytes khi chỉ proxy.
- Bị đổi bởi `ModifyResponseBody` (Java DSL).
- Bị nén/giải nén theo `Content-Encoding` và client capabilities.
- Bị thay bằng fallback `CircuitBreaker`.
- Bị loại nếu status 204/304/HEAD.
- Được thêm metadata vào headers hoặc chuyển thành redirect.

Một test status 200 + JSON body **chưa đủ** nếu response thực tế phải loại một trường bí mật.

### 12.1. Ví dụ response được filter đổi cấu trúc

Upstream:

~~~json
{"id":42,"secretInternalCode":"ABC","name":"Pen"}
~~~

Contract public:

~~~json
{"id":42,"name":"Pen"}
~~~

Test cần assert:

- Body public có `id`, `name`.
- Body **không** có `secretInternalCode`.
- Content-Type và status đúng.
- `Content-Length`/compression tương thích body mới.
- JSON vẫn parse được ở frontend.

Để thực hiện `ModifyResponseBody` ở Gateway WebFlux, tài liệu mô tả filter chỉ cấu hình được bằng **Java DSL**. Không đặt `ModifyResponseBody=...` trong YAML như một shortcut bất kỳ khi chưa có factory riêng do dự án tự viết.

### 12.2. Response rỗng là trường hợp đặc biệt

Các status như `204 No Content` không có response body theo HTTP semantics. Test nên:

~~~text
Upstream: 204 No Content
Client:   204 No Content
Body:     rỗng
~~~

Một test cố parse JSON từ response 204 sẽ tự gây lỗi dù Gateway hoạt động đúng.

Với `HEAD`, header metadata có thể tồn tại nhưng client không nhận response body. Với `304 Not Modified`, caching semantics quyết định headers liên quan; không ép body JSON vào response.

### 12.3. Content-Encoding

Nếu backend trả `Content-Encoding: gzip`, Gateway/client có thể xử lý compression tùy HTTP client/server configuration. Test phải xác định muốn chứng minh:

- Bytes ở wire được nén/giải nén đúng.
- Client sau khi giải nén đọc JSON đúng.
- Header `Content-Encoding`/length nhất quán.
- Không có response body bị double compressed.

Không dùng phép so raw bytes giữa gzip response và JSON plaintext rồi kết luận Gateway sửa body sai. Dùng mock phù hợp để kiểm cả representation và semantics.

## 13. Kiểm chứng HTTP status: nguồn gốc mới là điều quan trọng

Có nhiều nơi sinh status:

| Trường hợp | Ai có thể tạo status | Cần quan sát |
| --- | --- | --- |
| Request không khớp route | Gateway/WebFlux handler mapping | Mock upstream **không nhận** request |
| Bị Security chặn `401/403` | Spring Security WebFilter trước Gateway route | Upstream không nhận; identity policy đúng |
| Rate limiter trả `429` | `RequestRateLimiter` hoặc tầng trước Gateway | Upstream không nhận nếu chặn trước routing |
| Upstream `201` | Backend | Gateway trả 201 nếu không bị filter đổi |
| Upstream `422` | Backend | Gateway trả 422 nếu không có status mapping khác |
| Upstream `500/503` | Backend | Có upstream request; status cuối phụ thuộc Retry/CB |
| `lb://` không có instance | LoadBalancer/routing | Thường 503 mặc định, có thể cấu hình 404 |
| TCP connection refused | Gateway HTTP client/routing error | Backend không có request; status tùy error handler |
| TLS handshake fail | Gateway HTTP client | Backend app có thể chưa nhận HTTP |
| `SetStatus=...` | Gateway response filter | Client status có chủ ý khác backend |
| CircuitBreaker fallback | Gateway/fallback handler | Client có thể nhận status/body thay thế |
| Timeout sau backend commit | Gateway client/timeout policy | Backend có thể đã thực hiện side effect |

**Không khẳng định mọi `ConnectException` bắt buộc là 502 hoặc mọi timeout bắt buộc là 504**: cách map lỗi tùy Gateway version, Boot error handling và custom filters. Test nên thiết kế rõ expected policy, nếu không có policy thì assert error class và việc upstream có nhận request hay không.

### 13.1. Phân biệt hai loại 404

Một request `GET /not-a-route` không match route → Gateway có thể trả 404 và mock upstream **không nhận** request.

Một request `GET /edge/missing` match route → mock upstream nhận `GET /missing` rồi **trả 404**. Gateway sẽ thường chuyển status 404 về client nếu không có filter override.

Cả hai nhìn từ client đều là 404, nhưng nguyên nhân khác hẳn. Một test đúng phải assert **upstream request count** và path.

### 13.2. SetStatus thay status upstream

~~~yaml
filters:
  - SetStatus=BAD_REQUEST
~~~

Đoạn này cố ý đổi status cuối thành 400 (tùy route/filter pipeline). Khi test route có `SetStatus`, không thể đòi “Gateway phải giữ nguyên backend 201”.

Với Gateway WebFlux, tài liệu `SetStatus` có hỗ trợ cấu hình header chứa original status theo version/property. Nếu dự án bật, có thể assert header gốc nhưng phải bảo vệ nó khỏi lộ thông tin nội bộ không cần thiết.

### 13.3. Redirect cần kiểm cả status lẫn Location

Nếu backend hoặc Gateway trả 302/307/308, test nên xác định:

- Status đúng.
- `Location` trỏ tới public origin/path mong muốn.
- Không bị lộ host `localhost` hay tên DNS nội bộ.
- Với `307/308`, method preservation semantics phù hợp.
- Không bị redirect loop.
- Cookie/header security policy không bị phá.

**`WebTestClient` không nên tự follow redirect vô hình** nếu test cần nhìn status và `Location` ở bước đầu tiên. Tránh cấu hình HTTP client test theo cách nuốt mất response 3xx đang cần assert.

## 14. Retry: một client request có thể tạo nhiều upstream requests

Ví dụ:

~~~yaml
filters:
  - name: Retry
    args:
      retries: 2
      statuses:
        - SERVICE_UNAVAILABLE
      methods:
        - GET
~~~

Nếu mock upstream trả lần lượt `503`, `503`, `200`, một request GET từ client có thể tạo **3 attempts** (lần đầu + 2 retries). Với test status cuối 200, **phải kiểm tra mock đã nhận bao nhiêu request và path/header/body có nhất quán trên từng attempt hay không**.

### 14.1. Kịch bản deterministic

~~~text
Mock response queue:
  attempt #1 -> 503
  attempt #2 -> 503
  attempt #3 -> 200

Client:
  GET /edge/items/42

Assertions:
  final status = 200
  upstream request count delta = 3
  each upstream path = /items/42
  correlation ID stable per client request (nếu policy yêu cầu)
~~~

Không chạy test Retry trên mock không kiểm soát thứ tự response. Đừng đánh giá retry chỉ bằng tổng latency, vì backoff/jitter làm thời gian có biến thiên.

### 14.2. Không bật Retry POST một cách vô ý

Với POST tạo order/payment, nếu backend đã commit nhưng response thất lạc, replay có thể tạo **hai giao dịch**. Test cần `Idempotency-Key`, backend dedup nguyên tử và xác minh chỉ có một side effect.

Spring Cloud Gateway Retry filter có thể **cache request body** khi retry phương thức có body, gây memory pressure. Vì vậy, không dùng test payload lớn để “thử retry 100 lần” ngoài môi trường kiểm soát.

### 14.3. Thứ tự filter và side effect

Một filter nằm **phía sau Retry** có thể được thực thi lại ở từng attempt. Nếu một custom filter thêm header ngẫu nhiên hoặc sửa body không idempotent, mỗi attempt có thể khác.

Test phải kiểm tra contract với:

- Một request client.
- N attempts upstream.
- Một response cuối.
- Header/body được giữ/biến đổi theo policy per-attempt.
- Không sinh side effect ngoài mong muốn.

## 15. Circuit breaker, fallback và rate limiting

### 15.1. Circuit breaker

Khi backend liên tục lỗi, circuit breaker có thể:

- Cho phép request đi tới upstream ở trạng thái CLOSED/HALF_OPEN.
- Chặn request trước upstream khi OPEN.
- Chuyển request sang fallback handler.

Trong test, quan sát cả response client **và** upstream request count. Nếu fallback trả 200, test chỉ nhìn status có thể đánh đồng fallback với backend success. Hãy dùng response marker hoặc metrics để phân biệt, không để fallback giả là một giao dịch ghi đã thành công.

### 15.2. Rate limiting

Với `RequestRateLimiter`, test:

1. Key resolver trả key đã được xác thực, không tin header tự khai báo của client.
2. Khi quota còn, upstream nhận request.
3. Khi quota hết, Gateway từ chối theo status policy (thường `429`).
4. Upstream counter **không tăng** khi request bị chặn.
5. Header quota/Retry-After nếu có được kiểm theo contract, không tự giả định giá trị cố định.
6. Test phân biệt key giữa các principals, tránh flaky do Redis state dùng chung.

Token bucket và window/timing phải được điều khiển bằng test clock/config hoặc dung sai hợp lý; không dùng những assertions phụ thuộc mili-giây thực tế không ổn định.

### 15.3. Security chặn trước route

Spring Security WebFlux có thể trả 401/403 **trước khi Gateway route chain chạy**. Nếu request bị từ chối trước route matching, filter `AddResponseHeader` ở route có thể không chạy.

Do đó một test kiểu “mọi 401 luôn có `X-Edge-Test`” không đúng nếu header được thêm trong **GatewayFilter theo route**. Nếu cần correlation/security headers cho cả response pre-route, đặt chúng ở WebFilter/tầng tương ứng và test đúng lifecycle.

## 16. Test `lb://` và service discovery mà không phụ thuộc registry production

Ví dụ route:

~~~yaml
- id: orders-lb
  uri: lb://ORDER-SERVICE
  predicates:
    - Path=/api/orders/**
  filters:
    - StripPrefix=1
~~~

Với `lb://`, tên host logic không phải DNS host thật mà là **service ID** cho Spring Cloud LoadBalancer. Test tốt cần kiểm chứng:

- Gateway chọn một instance từ nguồn `ServiceInstance` dành riêng cho test.
- Backend mock ở instance đó nhận đúng path.
- Request được gửi đúng scheme HTTP/HTTPS theo instance/security policy.
- Khi không có instance, Gateway trả status theo policy; default thông thường là 503, có thể dùng 404 nếu cấu hình.
- Có nhiều instance thì không assert cứng “request #1 phải tới A”, trừ khi test chủ động điều khiển thuật toán/nguồn instances.

### 16.1. Dùng SimpleDiscoveryClient trong lab

Với Spring Cloud Commons hỗ trợ SimpleDiscoveryClient, có thể định nghĩa instance test qua configuration:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            ORDER-SERVICE:
              - uri: http://localhost:18081
~~~

Ví dụ này cần mock ở port 18081 hoặc một property cho port động; **đừng kết luận `lb://` chạy được nếu mock chưa thực sự nhận request**. Trong một bài test liên tục ở CI, nên inject service instance URI qua property/test supplier thay vì giữ port cố định.

Việc có instance trong discovery không tự chứng minh route path/header/body đúng; vẫn phải đọc `RecordedRequest` ở instance đã chọn.

### 16.2. isSecure, TLS và chứng chỉ

Nếu `ServiceInstance.isSecure() == true`, target có thể cần HTTPS; nếu backend mock chỉ hỗ trợ HTTP và Gateway cố dùng HTTPS, test sẽ thất bại ở TLS trước khi app nhận request.

Tách test:

- Routing HTTP đơn giản để kiểm path/header/body.
- HTTPS upstream với test CA/certificate để kiểm trust/hostname/SNI.
- mTLS nếu kiến trúc yêu cầu, dùng test certificate hợp lệ.
- Scheme override đặc biệt nếu route dùng `lb:https://...` hoặc biến thể theo release.

Không bật **insecure trust manager** trong production rồi dùng test “thành công” làm bằng chứng TLS an toàn.

## 17. Kiểm thử errors: DNS, connection refused, timeout và reset

Một mock upstream có thể mô phỏng nhiều lỗi:

| Fault | Kết quả cần quan sát | Điều không nên suy diễn |
| --- | --- | --- |
| Backend trả HTTP 500 | Có request đến backend; client status theo filter policy | Không mặc định Gateway gây lỗi |
| Backend trả HTTP 503 | Có HTTP response 503, có thể retry | Không mặc định backend chưa xử lý |
| Port không lắng nghe | Kết nối thất bại trước khi gửi request hoàn chỉnh | Không luôn map thành đúng 502 |
| DNS target sai | Gateway không tìm được host | Không luôn giống 404 route |
| TCP reset giữa response | Client có thể nhận lỗi/partial body | Không khẳng định body luôn nguyên |
| Response chậm hơn timeout | Gateway timeout, backend có thể tiếp tục | Không auto-retry write |
| TLS handshake fail | Gateway không xác minh certificate/key | Không phải upstream business 500 |
| Client ngắt kết nối | Cancellation, cleanup/connection reset | Không chắc backend đã dừng xử lý |

Test nên:

1. Ghi fault type từ mock.
2. Ghi/quan sát Gateway error handling, logs (đã redact) và response theo policy.
3. Assert upstream request count nếu fault diễn ra sau khi gửi request.
4. Đặt timeout cho test; không chờ vô hạn.
5. Khi dùng Retry, tính cả attempts và backoff.
6. Không phụ thuộc một mã status “mặc định mọi version” nếu project không khai báo rõ mapping.

## 18. Bảo mật header và body trong integration tests

Trong Gateway, test correctness cũng phải xác minh **trust boundary**:

### 18.1. Các yêu cầu tối thiểu

- `Authorization` đến backend nào là cần thiết? Có `TokenRelay` hay service auth assertion đúng policy?
- Header client `X-User`, `X-Role`, `X-Tenant-Id` có bị loại trước khi backend coi chúng là nguồn đáng tin không?
- Mã `X-Request-Id` có bị client giả mạo hoặc dài vô hạn không?
- `Forwarded`/`X-Forwarded-*` có được lấy từ trusted proxy đúng cấu hình không?
- Body/response có chứa secret/PII ngoài contract không?
- Route có thể đi đến URI/host không thuộc allowlist hay địa chỉ metadata nội bộ không?
- CORS/preflight có bị mở rộng trái chính sách không?
- Trace headers/baggage có bị dùng làm credential không?

### 18.2. Không đưa secrets thật vào fixtures/log

Dùng các giá trị giả như:

~~~text
Authorization: Bearer test-token-redacted
X-Request-Id: req-demo-42
X-Debug-Only: must-not-leak
~~~

Trong production không log raw `Authorization`/cookie/body nhạy cảm để debug test. CI reports và `RecordedRequest` có thể lưu HTTP headers/body; hãy giới hạn truy cập, dùng sample synthetic, xóa fixture nhạy cảm và cấu hình redaction.

### 18.3. Test ngăn header spoofing

Một ca tiêu biểu:

~~~text
Client:
  X-Gateway-Source: spoofed

Gateway:
  SetRequestHeader=X-Gateway-Source, gateway-test

Upstream:
  X-Gateway-Source: gateway-test
~~~

Test mục 7 đã minh họa case này. Tuy nhiên, header `X-Gateway-Source` chỉ là marker để xác minh filter, **không tự chứng minh authentication**. Với danh tính người dùng, phải kiểm principal đã xác thực, chống client spoofing và có hợp đồng tin cậy với upstream.

## 19. Tracing và metrics hỗ trợ điều tra test như thế nào?

Nếu có distributed tracing (Micrometer Tracing/OpenTelemetry), test có thể liên kết Gateway và backend nhờ W3C `traceparent`, `tracestate`. Nhưng:

- Trace ID phải cùng logical trace; span IDs của các hops **khác nhau**.
- Không copy `traceparent` cố định bằng `SetRequestHeader` để “đảm bảo test có trace”.
- Gateway custom `WebClient` cần instrumented builder/context propagation.
- Sampling có thể làm trace không xuất hiện trong backend dù header được gửi.
- Retry có thể tạo nhiều HTTP attempts và nhiều spans.
- Request bị 401/429 trước routing có thể **không có upstream span**.

Metrics cần được tách:

| Metric | Ý nghĩa |
| --- | --- |
| Client request count | Số requests vào Gateway |
| Upstream attempt count | Số HTTP calls thực sự ra backend |
| Response status count | Số client responses theo status |
| Route-level latency | Thời gian xử lý qua Gateway |
| Retry count | Số retries ngoài lần gọi đầu |
| Circuit breaker state | OPEN/HALF_OPEN/CLOSED |
| Backend receive count | Số request mock/service nhận |

Không dùng raw request IDs, trace IDs hoặc path chứa user ID làm **metric label có cardinality vô hạn**. Dùng route ID có kiểm soát, status/outcome và service category; log/trace để xem request cụ thể.

## 20. Tổ chức test suite để tránh flaky và tăng khả năng phát hiện lỗi

### 20.1. Danh sách các yếu tố phải kiểm soát

| Nguy cơ flaky | Biện pháp |
| --- | --- |
| Port 8080/8081 đã bị dùng | Gateway `RANDOM_PORT`, mock upstream port động |
| Upstream staging chập chờn | Dùng mock server local |
| Mock response queue bị tranh chấp | Mỗi class/test có isolation, disable parallel hoặc dispatcher deterministic |
| Route config bind sai namespace | Kiểm effective routes/startup, dùng profile test |
| Redis state dùng chung | Dùng Redis test instance/cấu hình keys cách ly hoặc stub |
| Retry/backoff có jitter | Tắt jitter trong unit test hoặc dùng dung sai/timing clock |
| Test treo khi route không gọi backend | `takeRequest(timeout, unit)` |
| Không biết request nào đến backend | Marker header/correlation + recorded request log |
| Lẫn code/route YAML và Java | Chỉ kích hoạt một source cho case thử |
| Backend response body chưa flush | Mock trả response rõ ràng; stream tests riêng |
| HTTP compression thay bytes | Test semantic body hoặc cấu hình compression rõ |
| Auth test không có principal | Dùng mock JWT/token test hoặc test IdP phù hợp |
| Test chạy sau deployment config khác | Ghi rõ property override và version đã chạy |
| Timeout test quá thấp trên CI tải cao | Chọn timeout thực tế, không `sleep` cố định |
| Lỗi chỉ ở một Gateway replica | Dùng per-node synthetic requests trong staging |

### 20.2. Không dùng Thread.sleep() để đợi Gateway “có lẽ đã xong”

Các test cần chờ một HTTP request có thể dùng `takeRequest(5, TimeUnit.SECONDS)`, Reactor StepVerifier hoặc polling có deadline. Không dùng `Thread.sleep(3000)` tràn lan: test sẽ chậm và vẫn flaky trên CI tải cao.

Không dùng `block()` trong Gateway filter để làm test deterministic. Chỉ những chỗ test client chờ response ở thread test có thể làm việc đồng bộ một cách kiểm soát.

### 20.3. Đừng chia sẻ MockWebServer đang enqueue FIFO giữa các test song song

Nếu test A enqueue 201, test B enqueue 422, nhưng hai client calls tới upstream đến theo thứ tự khác, cả hai có thể fail ngẫu nhiên.

Các chiến lược:

1. Mỗi test có mock upstream riêng và Spring context riêng khi cần.
2. Dùng dispatcher phân nhánh theo method/path hoặc request marker.
3. Chạy những method chia sẻ cùng queue **sequentially**.
4. Clear/reset state và đảm bảo không còn in-flight attempts trước test tiếp theo.
5. Khi bật Retry, queue response đủ cho mọi attempt dự kiến.

## 21. Ma trận test contract hoàn chỉnh

| ID | Input/kịch bản | Assert ở mock upstream | Assert ở client |
| --- | --- | --- | --- |
| P01 | GET `/edge/items/42` | GET `/items/42` | Status/body hợp đồng |
| P02 | POST `/edge/echo?x=1` | POST `/echo?x=1` | 201/JSON |
| P03 | `/edge-old/path` | Không có request | No-route status |
| P04 | `/edge/a%20b` | Path encoding đúng policy | Không 500 do encode |
| P05 | `/edge/a%2Fb` | Encoded-slash semantics theo policy | Không bypass auth/path |
| P06 | `RewritePath` có named group | Path sau rewrite đúng | Hành vi đúng |
| H01 | Client spoof header | Header được set lại | Không phụ thuộc raw spoof |
| H02 | Client gửi debug-only header | Backend không nhận | Response hợp đồng |
| H03 | Multi-value header | Số/giá trị theo Add vs Set | Không rò rỉ giá trị |
| H04 | Hop-by-hop header | Theo RFC/Gateway policy | Request vẫn hợp lệ |
| H05 | Trusted forwarded header | Giá trị được chuẩn hóa | Không tin client giả |
| H06 | Backend trả `X-Upstream-Result` | Mock trả header | Client thấy header nếu không bị filter đổi |
| H07 | Gateway AddResponseHeader | Không cần có ở mock | Client thấy marker |
| H08 | Backend đặt `Set-Cookie` | Policy bảo vệ cookies | Client nhận attributes đúng |
| B01 | JSON request nhỏ | JSON fields/bytes đúng | Response body đúng |
| B02 | JSON null/body rỗng | Phân biệt hai trường hợp | Status/validation theo contract |
| B03 | Form URL encoded | Fields/charset đúng | Status hợp đồng |
| B04 | Binary payload | Byte count/checksum đúng | Không corrupt body |
| B05 | Multipart upload | File bytes/metadata đúng | Không 413 nếu dưới giới hạn |
| B06 | Request vượt size limit | Không được proxy nếu chặn trước routing | 413 theo policy |
| B07 | ModifyRequestBody | Body đã rewrite đúng | Backend nhận payload hợp lệ |
| B08 | ModifyResponseBody | Mock trả raw body | Client không còn field nội bộ |
| S01 | Upstream 201 | Nhận request | Client 201 |
| S02 | Upstream 422 | Nhận request | Client 422 nếu không mapping |
| S03 | No route | Không nhận | 404 hoặc policy mapping |
| S04 | Upstream 404 | Nhận request | 404 từ upstream |
| S05 | Upstream 503 + Retry GET | Số attempts đúng | Final response theo queue |
| S06 | Rate limit deny | Không tăng request count | 429 theo config |
| S07 | Security deny | Không tăng request count | 401/403 |
| S08 | Circuit breaker open | Không có upstream call | Fallback/status theo config |
| S09 | Backend 204 | Nhận request | 204, body rỗng |
| S10 | Redirect 307 | Theo backend/fallback | 307 + Location hợp lệ |
| S11 | Connection refused | Không có HTTP response backend | Gateway error status theo policy |
| S12 | TLS certificate fail | Backend app không nhận request hợp lệ | TLS failure được ghi nhận |
| S13 | Client disconnect | Cancellation/cleanup | Không đếm như response success giả |
| S14 | Retry POST được kiểm soát | Side effects không nhân đôi | Có idempotency và response hợp đồng |

Không phải mọi test đều phải nằm trong một class lớn. Phân nhóm theo **path, headers, body, status, resilience/security** để dễ tìm nguyên nhân khi fail.

## 22. Quy trình điều tra khi một integration test thất bại

### 22.1. Client trả 404, mock không nhận request

Khả năng:

- Route predicate `Path`/`Method` không match.
- Dùng sai prefix `spring.cloud.gateway.routes` vs `spring.cloud.gateway.server.webflux.routes`.
- Có Spring Security/handler khác chặn trước.
- Route order hoặc source khác chiếm request.
- Test gọi sai Gateway port/profile.

**Bước đầu:** xem effective route definitions hoặc startup logs trong **test profile**, rồi gọi đúng path. Đừng sửa upstream response vì upstream chưa nhận request nào.

### 22.2. Mock nhận request nhưng path sai

Khả năng:

- `StripPrefix` đếm sai số segment.
- `RewritePath` regex/replacement sai hoặc YAML placeholder escaping.
- Filter order làm `PrefixPath` trước `StripPrefix` sai.
- Context path/forwarded prefix ở ingress ảnh hưởng.
- URI target bị hiểu sai.

**Bước đầu:** so `RecordedRequest.getPath()` với expected canonical path. Gỡ từng filter trong **test profile** để cô lập biến đổi path.

### 22.3. Mock nhận đúng path nhưng header sai

Khả năng:

- `AddRequestHeader` được dùng thay vì `SetRequestHeader`, tạo nhiều giá trị.
- Header bị `RemoveRequestHeader` hoặc `HttpHeadersFilters` loại.
- Host/Forwarded headers theo proxy configuration.
- Security/TokenRelay chưa có principal hoặc token.
- Custom filter mutate request nhưng không gọi `chain.filter(mutatedExchange)`.

**Bước đầu:** assert một header cụ thể, rồi kiểm filter order và trust boundary. Không dump toàn bộ Authorization/cookie trên CI.

### 22.4. Mock thấy body rỗng hoặc không parse được

Khả năng:

- Custom filter đọc `DataBuffer` rồi không replay.
- `ModifyRequestBody` serialize sai schema/Content-Type.
- Client test không gửi body hoặc encoding sai.
- Retry/body caching/hạn mức làm request khác dự đoán.
- Body lớn vượt size limit/memory limit.

**Bước đầu:** dùng payload JSON nhỏ, kiểm raw bytes và Content-Type ở mock. Sau đó mở rộng đến streaming/multipart.

### 22.5. Mock trả 422 nhưng client thấy 200/500

Khả năng:

- `SetStatus`, CircuitBreaker fallback, exception handler hoặc custom response filter đổi status.
- Mock response queue bị test khác lấy.
- Gateway retry một attempt khác rồi cuối cùng nhận 200.
- Test client auto-follow redirect.
- Route đi đến backend khác.

**Bước đầu:** xác minh mock đã nhận request của chính test, response FIFO, số attempts và filters có hiệu lực. Đừng giả định status do backend là status client cuối nếu Gateway có response policy.

### 22.6. Chỉ CI fail, local pass

Khả năng:

- Cổng cố định bị chiếm hoặc network DNS/proxy khác nhau.
- Test song song làm lẫn MockWebServer queue.
- App profile/namespace config khác.
- Timeout quá nhỏ, runner quá tải.
- Mock server shutdown trước khi Spring context hoàn tất.
- Redis/k8s/test external state dùng chung.

**Bước đầu:** tái chạy riêng ca test với test profile cố định, port động, timeout rõ; ghi route ID, path và status đã redact. Không “chữa” bằng việc tăng `Thread.sleep` mà chưa phân tích.

## 23. Bài thực hành tổng hợp

**Bối cảnh:** Gateway nhận các endpoints `/api/catalog/**`, `/api/orders/**`; catalog GET, orders POST. Mỗi backend là một mock server riêng. Gateway có `StripPrefix`, `SetRequestHeader`, `RemoveRequestHeader`, `AddResponseHeader`, security và tùy chọn Retry GET.

Yêu cầu:

1. Tạo một profile `gateway-contract` riêng với route configs đúng namespace phiên bản.
2. Cho Gateway chạy `RANDOM_PORT`, hai mock upstream dùng cổng động.
3. Cấp target URI qua `@DynamicPropertySource` hoặc cấu hình test rõ ràng.
4. Test `GET /api/catalog/products/42` được gửi tới `/catalog/products/42`.
5. Test `POST /api/orders/create?source=mobile` được gửi tới `/orders/create?source=mobile`.
6. Gửi JSON và kiểm schema/raw body theo contract; không log secret.
7. Client gửi `X-Gateway-Source: spoofed`; backend chỉ được thấy giá trị do Gateway đã xác định.
8. Client gửi `X-Debug-Only`; backend không được thấy.
9. Backend trả 201/422/503; xác minh status cuối khi không có và khi có policy đổi status.
10. Backend thêm `X-Upstream-Result`; Gateway thêm `X-Edge-Test`; xác minh cả hai ở client.
11. Test một path không khớp và một backend 404 để chứng minh khác nhau qua request count.
12. Test `RewritePath` với segment lồng và encoded path theo security policy.
13. Test `204 No Content`, JSON malformed, Content-Type sai, body vắng mặt.
14. Thử binary 1 MiB, so checksum và memory không tăng bất thường.
15. Với Retry GET, mock trả 503 rồi 200; xác minh final status cùng số attempts.
16. Với POST orders, thử timeout sau commit và xác minh idempotency/không tự retry mù.
17. Thêm Spring Security test thiếu token/scope; chứng minh upstream không nhận request bị chặn.
18. Khi có `lb://`, dùng test service instances và xác minh backend được chọn.
19. Quan sát trace ID/route metrics mà không đưa raw token/body vào log.
20. Tổng hợp một báo cáo theo bốn trục path/header/body/status, ghi rõ assertion đã chạy và những sai lệch tìm thấy.

### Kết quả mong đợi của lab

~~~text
[PASS] Route predicate match đúng và unmatched request không đến upstream
[PASS] Path/query sau StripPrefix/RewritePath đúng hợp đồng
[PASS] Request header được thêm, set, remove theo policy
[PASS] Không tin các forwarded/identity headers do client giả mạo
[PASS] JSON/body và Content-Type upstream nhận chính xác
[PASS] Response headers/status/body cuối khớp policy
[PASS] Phân biệt backend 404 và Gateway no-route 404
[PASS] Retry/fallback/rate-limit/auth được đo bằng upstream attempts
[PASS] Test dùng mock upstream deterministic và port động
[PASS] Không lộ credentials/PII, không block event loop
~~~

Đây là **tiêu chí hoàn thành**, không phải biên bản đã chạy test trong workspace được giao.

## 24. Checklist trước khi đưa bộ kiểm thử vào CI/CD

- [ ] Có test **full HTTP chain** Gateway → mock upstream, không chỉ test predicate riêng lẻ.
- [ ] Có assertion ở **hai phía**: upstream recorded request và client response.
- [ ] Cấu hình test dùng đúng starter/route namespace của Server WebFlux version đang chạy.
- [ ] Gateway `RANDOM_PORT`, mock server port động, không gọi Internet/production.
- [ ] Không có route YAML/Java DSL trùng ID/predicate ngoài ý muốn.
- [ ] Test path `StripPrefix`/`RewritePath`, query, encoded slash và path ranh giới.
- [ ] HTTP method được kiểm cùng path, không chỉ GET mặc định.
- [ ] Request headers test `Add` vs `Set` vs `Remove`; không tin header giả mạo.
- [ ] Test response headers gồm add/remove/dedupe/CORS khi route sử dụng.
- [ ] Không assert `Connection`, `Transfer-Encoding`, `Content-Length` một cách sai HTTP semantics.
- [ ] Test JSON body semantic, binary checksum, missing body và Content-Type.
- [ ] Nếu có body rewrite, đã kiểm schema/length/content-encoding nhất quán.
- [ ] Test 201/204/4xx/5xx/no-route/timeout theo status mapping policy.
- [ ] Dùng upstream request counter phân biệt Gateway-generated và backend-generated status.
- [ ] Mỗi Retry test có response queue và assertion attempt count xác định.
- [ ] Không tự retry POST quan trọng nếu chưa có idempotency backend.
- [ ] Security 401/403, rate-limit 429, circuit breaker fallback có request counter assertions.
- [ ] TLS/upstream secure và service discovery được kiểm riêng, không giả định HTTP-only lab bao phủ.
- [ ] Không dùng `Thread.sleep` thay chờ sự kiện có timeout.
- [ ] Không dùng custom `subscribe()`/`block()` trong Gateway filter để test body.
- [ ] Mock server response queues được cách ly, không có tranh chấp parallel execution.
- [ ] Mọi tests có timeout, cleanup và không phụ thuộc trạng thái Redis/service external.
- [ ] Logs/CI artifacts che token, cookies, payload nhạy cảm và URI chứa PII.
- [ ] Khi Gateway nâng phiên bản, chạy lại contract tests cho route/filter/status mapping.
- [ ] Có test trên **mỗi replica** ở staging nếu sử dụng dynamic routes hoặc multi-node routing.
- [ ] Nội dung kiểm thử ghi rõ **expected** và **observed**, không đánh dấu PASS trước khi thực thi.

## 25. Tổng kết và tài liệu tham khảo

**Kiểm chứng chuyển tiếp trong Spring Cloud Gateway** là so sánh hợp đồng HTTP ở **hai ranh giới khác nhau**:

1. **Client → Gateway → upstream:** method, path, query, request headers và request body có đúng sau route predicates/filter chain không?
2. **Upstream → Gateway → client:** HTTP status, response headers và response body có đúng sau response filters, retry/circuit breaker/error handling không?

Dùng **`@SpringBootTest(RANDOM_PORT)` + `WebTestClient.bindToServer()` + một mock HTTP upstream** để đi qua stack routing thật. Mock upstream giúp nhìn request cuối, WebTestClient giúp nhìn response cuối; assert cả hai mới phát hiện được path sai, header bị lộ, body rỗng, status bị đổi hoặc Retry gây thêm attempts.

Các phép thử chuyên sâu cần bao gồm **không khớp route**, **backend tự trả 404**, **response 204/422/503**, **auth/rate limiting trước routing**, **retry/fallback**, **TLS/service discovery** và **streaming**, nhưng phải theo đúng contract của deployment và release. Bảo mật/quan sát không được bỏ qua: không tin headers do client giả mạo, không log secret, không dùng body test để phá reactive flow.

### Tài liệu tham khảo

- [Spring Framework — WebTestClient, bindToServer và request/response assertions](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html).
- [Spring Boot 3.5 — Testing with a Running Server, RANDOM_PORT](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html).
- [Spring Cloud Gateway Server WebFlux — GatewayFilter Factories](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories.html).
- [Spring Cloud Gateway Server WebFlux — AddRequestHeader](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/addrequestheader-factory.html).
- [Spring Cloud Gateway Server WebFlux — RewritePath](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/rewritepath-factory.html).
- [Spring Cloud Gateway Server WebFlux — ModifyRequestBody](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/modifyrequestbody-factory.html).
- [Spring Cloud Gateway Server WebFlux — ModifyResponseBody](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/modifyresponsebody-factory.html).
- [Spring Cloud Gateway Server WebFlux — SetStatus](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/setstatus-factory.html).
- [Spring Cloud Gateway Server WebFlux — Retry](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/retry-factory.html).
- [Spring Cloud Gateway Server WebFlux — HttpHeadersFilters](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/httpheadersfilters.html).
- [Spring Cloud Gateway — Configuration Properties theo phiên bản](https://docs.spring.io/spring-cloud-gateway/reference/configprops.html).
