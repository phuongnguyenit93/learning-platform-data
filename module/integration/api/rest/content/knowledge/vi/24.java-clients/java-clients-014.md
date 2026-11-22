# Kiểm thử client bằng mock server và thông điệp HTTP thực tế

## 1. Đừng nhầm mock một phương thức Java với kiểm thử một lời gọi REST

Giả sử `OrderService` dùng Java HTTP client gọi Inventory API để tra cứu tồn kho. Một unit test kiểu:

```java
when(inventoryGateway.available("sku-7")).thenReturn(3);
assertEquals(3, orderService.checkStock("sku-7"));
```

kiểm tra **logic của service sử dụng client**, nhưng **không xác nhận** `InventoryGateway` tạo đúng URI, HTTP method, query, media type, bearer token, JSON body hoặc xử lý `404`/`429`. Một bug như gửi `GET /items/sku-7?limit=0` thay cho `GET /items/sku-7` sẽ không xuất hiện, vì gateway đã bị mock hoàn toàn.

Với một **mock HTTP server**, client thật vẫn chạy serialization, URI building, filter/interceptor, HTTP codec và transport; chỉ dịch vụ ở đầu kia được thay bằng server kiểm thử có response dự đoán được. Từ đó ta có thể đọc yêu cầu mà client **thực sự tạo ra**.

```mermaid
flowchart LR
    T[Test JUnit] --> C[Java HTTP client thật]
    C --> H[HTTP request thực hoặc request adapter]
    H --> M[Mock server / stub]
    M -->|HTTP status + headers + body| C
    C --> A[Assert kết quả và lỗi]
    T --> A
```

Bài thuộc chương **Client Java** trong module **INTEGRATION_API_REST**: học thiết kế REST theo resource/URI, HTTP methods/status, hợp đồng dữ liệu, phân trang, cache, idempotency, OpenAPI, xác thực/phân quyền, xử lý lỗi và kiểm thử bằng Java/Spring. **Mục tiêu:** xác định đúng tầng kiểm thử; khẳng định request HTTP và response theo hợp đồng; giả lập sự cố một cách quyết định; bảo vệ credential và idempotency; xây test tin cậy cho cả `RestClient`, `WebClient` hoặc JDK `HttpClient`.

### 1.1. Bốn cấp kiểm thử và phạm vi bằng chứng

| Cấp | Thành phần thật | Phần được thay | Có thể chứng minh |
| --- | --- | --- | --- |
| Unit test service | Logic nghiệp vụ gọi gateway | Mock interface gateway | Business decision của caller; **không** xác minh HTTP |
| `MockRestServiceServer` | Spring `RestClient`/message converter/request factory giả lập | Transport bị mock, không socket mạng | Method/URI/headers/body, mapping status, DTO |
| Mock **HTTP server trên loopback** | Client, encoder, network stack và HTTP request/response | Server upstream bên ngoài | Tương tác HTTP trên wire, timeout, stream, redirect, retry |
| Provider contract / môi trường tích hợp | Client và API thực hoặc provider verification | Dữ liệu/điều kiện được kiểm soát | Mức tương thích giữa hai bên, auth/proxy/TLS theo môi trường |

Mock server tạo lỗi hiếm một cách ổn định nhưng không chứng minh provider production thực sự hỗ trợ schema, TLS và network policy; integration test bổ sung bằng chứng đó.

### 1.2. Hợp đồng ví dụ xuyên suốt

Inventory API của ứng dụng mẫu:

```http
GET /api/inventory/sku-7?warehouse=hn-1 HTTP/1.1
Host: inventory.example.test
Accept: application/json
Authorization: Bearer <synthetic-token>
X-Request-Id: trace-demo-42
```

```http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "inventory-sku-7-v3"
Cache-Control: private, max-age=30

{"sku":"sku-7","warehouse":"hn-1","available":3}
```

Trường hợp không tồn tại:

```http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/item-not-found",
  "title": "Inventory item not found",
  "status": 404,
  "code": "ITEM_NOT_FOUND"
}
```

Client phải giữ ý nghĩa HTTP: `404` **khác** timeout kết nối; `401` **khác** không có hàng; `503` có thể retry theo điều kiện; header `ETag` và `If-None-Match` chỉ dùng theo đúng validator của representation. Test tốt kiểm tra cả đường thành công, lỗi có cấu trúc và một số phản hồi bất thường.

## 2. Kiểm tra ý nghĩa request, không khóa chặt chi tiết không cam kết

Một kiểm thử HTTP có giá trị cần đặt assertions ở đúng nơi:

| Vùng của thông điệp | Nên assert | Không nên khóa chặt |
| --- | --- | --- |
| Method và target | `GET`, path `/api/inventory/sku-7`, query `warehouse=hn-1` | Thứ tự tham số query nếu API không yêu cầu |
| Headers | `Accept`, `Authorization` đúng request, `Idempotency-Key` khi cần | Thứ tự/kiểu chữ của header name (HTTP case-insensitive) |
| Request body | `Content-Type`, JSON parse được và có các trường quan trọng | Khoảng trắng, thứ tự field JSON nếu không thuộc contract |
| Response | Status, media type, body/DTO, error code | Chuỗi raw HTTP tuyệt đối bao gồm framing |
| Transport | Timeout, reconnect/retry, giải phóng stream/connection | `Content-Length` vs chunked khi client tự chọn và server chấp nhận cả hai |
| Bảo mật | Không chuyển token sang host khác, không log bí mật, ngăn SSRF | Giá trị token thật hoặc credential ghi cứng trong test |

HTTP/2 có pseudo-headers/binary framing khác HTTP/1.1; test thông thường nên kiểm tra **semantics của method, target, headers và body**, không so chuỗi bytes nguyên xi.

### 2.1. URI encoding và dữ liệu không đáng tin

Nếu SKU có dấu cách hoặc ký tự đặc biệt, client phải dùng URI builder phù hợp thay vì nối chuỗi:

```java
client.get()
      .uri("/api/inventory/{sku}?warehouse={warehouse}", sku, warehouse)
      .retrieve()
      .body(InventoryItem.class);
```

Test các giá trị `sku-7`, `sku/A`, `sku 7`, dấu tiếng Việt, ký tự `?`, `&`, `#` theo chính sách URI; bảo đảm giá trị biến được encode đúng, không vô tình biến thành thêm path segment hoặc query parameter. URI encode **không thay thế kiểm tra input** hay chống SSRF: base URL phải được cấu hình từ nguồn đáng tin, không từ URL tự do do client cuối gửi.

## 3. Spring RestClient và MockRestServiceServer: test hợp đồng không mở socket

Ví dụ dùng **Java 17, Spring Framework 6.1+ / Spring Boot 3.2+, JUnit 5 và spring-test**. Cùng một `RestClient` được xây một lần, mỗi lần gọi có token riêng. Client chỉ xử lý JSON `200` và phân biệt `404` với lỗi kết nối; không tự retry một kết quả chưa rõ.

### 3.1. Client thật cần kiểm thử

```java
package example.inventory.client;

import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;

record InventorySnapshot(String sku, String warehouse, int available) {}

class InventoryNotFoundException extends RuntimeException {
    InventoryNotFoundException(String sku, Throwable cause) {
        super("Inventory item not found: " + sku, cause);
    }
}

public class InventoryRestGateway {
    private final RestClient client;

    public InventoryRestGateway(RestClient client) {
        this.client = client;
    }

    public InventorySnapshot get(
            String sku, String warehouse, String accessToken) {
        try {
            InventorySnapshot snapshot = client.get()
                .uri(builder -> builder.path("/api/inventory/{sku}")
                    .queryParam("warehouse", warehouse)
                    .build(sku))
                .accept(MediaType.APPLICATION_JSON)
                .headers(h -> h.setBearerAuth(accessToken))
                .retrieve()
                .body(InventorySnapshot.class);

            if (snapshot == null) {
                throw new IllegalStateException("Missing response body");
            }
            return snapshot;
        } catch (RestClientResponseException e) {
            if (e.getStatusCode().value() == 404) {
                throw new InventoryNotFoundException(sku, e);
            }
            throw e; // Caller quyết định chính sách cho status khác.
        }
    }
}
```

`RestClient.Builder.baseUrl(...)` được cấu hình ở composition root (Spring bean hoặc test); gateway không nhận URL tùy ý từ người dùng. Những DTO cần validation nghiệp vụ sâu hơn phải có kiểm tra tương ứng; `available` âm, currency không hợp lệ hoặc JSON không đúng schema không được coi là kết quả tốt chỉ vì parse được.

### 3.2. Mock server chứng minh URI, header, JSON và xử lý 404

```java
package example.inventory.client;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

class InventoryRestGatewayTest {

    @Test
    void sendsGetAndParsesInventory() {
        RestClient.Builder builder = RestClient.builder()
            .baseUrl("https://inventory.example.test");
        MockRestServiceServer server =
            MockRestServiceServer.bindTo(builder).build();
        InventoryRestGateway gateway =
            new InventoryRestGateway(builder.build());

        server.expect(requestTo(
                "https://inventory.example.test/api/inventory/sku-7?warehouse=hn-1"))
            .andExpect(method(HttpMethod.GET))
            .andExpect(header(HttpHeaders.ACCEPT, "application/json"))
            .andExpect(header(HttpHeaders.AUTHORIZATION,
                "Bearer synthetic-token-A"))
            .andRespond(withSuccess("""
                {"sku":"sku-7","warehouse":"hn-1","available":3}
                """, MediaType.APPLICATION_JSON));

        InventorySnapshot result =
            gateway.get("sku-7", "hn-1", "synthetic-token-A");

        assertEquals(3, result.available());
        assertEquals("sku-7", result.sku());
        server.verify();
    }

    @Test
    void maps404WithoutPretendingItWasAConnectionFailure() {
        RestClient.Builder builder = RestClient.builder()
            .baseUrl("https://inventory.example.test");
        MockRestServiceServer server =
            MockRestServiceServer.bindTo(builder).build();
        InventoryRestGateway gateway =
            new InventoryRestGateway(builder.build());

        server.expect(requestTo(
                "https://inventory.example.test/api/inventory/missing?warehouse=hn-1"))
            .andRespond(withStatus(HttpStatus.NOT_FOUND)
                .contentType(MediaType.valueOf("application/problem+json"))
                .body("""
                    {"type":"about:blank","title":"Not Found",
                     "status":404,"code":"ITEM_NOT_FOUND"}
                    """));

        assertThrows(InventoryNotFoundException.class,
            () -> gateway.get("missing", "hn-1", "synthetic-token-B"));
        server.verify();
    }
}
```

`server.verify()` bảo đảm những tương tác đã khai báo được thực hiện; việc gọi một method Java giả mà không tạo request sẽ không thỏa expectation. Nên tạo **builder mới cho từng test** để tránh state chia sẻ. `MockRestServiceServer` chặn request trước transport, nên không chứng minh TLS, DNS, connection pool, redirect thật hay việc ứng dụng dùng HTTP/1.1 so với HTTP/2.

### 3.3. Kiểm tra body của request ghi dữ liệu

Khi client phát `POST /api/reservations`, cần assert **method, content type, idempotency header và JSON fields**:

```java
server.expect(requestTo("https://inventory.example.test/api/reservations"))
    .andExpect(method(HttpMethod.POST))
    .andExpect(header(HttpHeaders.CONTENT_TYPE,
        org.hamcrest.Matchers.startsWith("application/json")))
    .andExpect(header("Idempotency-Key", "intent-789"))
    .andExpect(content().json("""
        {"sku":"sku-7","quantity":2}
        """))
    .andRespond(withSuccess(
        "{\"id\":\"res-789\",\"status\":\"RESERVED\"}",
        MediaType.APPLICATION_JSON));
```

Đoạn này là **expectation minh họa**, dùng trong test sau khi đã tạo builder, server và method gateway phát POST tương ứng. `content().json(...)` so cấu trúc JSON, không áp đặt whitespace hoặc thứ tự thuộc tính. Nếu contract yêu cầu field `quantity` kiểu số nguyên, test nên bổ sung trường hợp invalid type, missing required field và mapping `400/422` theo API thực tế. Không test `POST` chỉ bằng cách assert nó đã trả `200`.

## 4. JDK HttpClient: mock server chạy HTTP thật trên loopback

`java.net.http.HttpClient` không tích hợp `MockRestServiceServer` của Spring. Có thể dùng **WireMock, OkHttp MockWebServer** hoặc **`com.sun.net.httpserver.HttpServer` của JDK** để tạo một HTTP endpoint thực trong tiến trình test. Khác với mock response adapter, cách này đi qua socket, HTTP parser/encoder và client transport.

### 4.1. Kiểm tra HTTP thực tế bằng `HttpServer` của JDK 17

Ví dụ JUnit 5 tự chạy server trên **port động** của địa chỉ loopback; không gọi dịch vụ bên ngoài. Đây là bài kiểm tra integration nhỏ, không phải server production.

```java
package example.inventory.client;

import static org.junit.jupiter.api.Assertions.*;

import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class JdkHttpClientWireTest {
    private HttpServer server;
    private final AtomicReference<Captured> observed =
        new AtomicReference<>();

    record Captured(
        String method, String path, String query,
        String authorization, String accept) {}

    @BeforeEach
    void start() throws Exception {
        server = HttpServer.create(
            new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/api/inventory/", exchange -> {
            observed.set(new Captured(
                exchange.getRequestMethod(),
                exchange.getRequestURI().getRawPath(),
                exchange.getRequestURI().getRawQuery(),
                exchange.getRequestHeaders().getFirst("Authorization"),
                exchange.getRequestHeaders().getFirst("Accept")));
            byte[] json = """
                {"sku":"sku-7","warehouse":"hn-1","available":3}
                """.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders()
                .set("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, json.length);
            try (OutputStream body = exchange.getResponseBody()) {
                body.write(json);
            }
        });
        server.start();
    }

    @AfterEach
    void stop() {
        if (server != null) server.stop(0);
    }

    @Test
    void sendsRealHttpAndReceivesRealResponse() throws Exception {
        String url = "http://127.0.0.1:" + server.getAddress().getPort()
            + "/api/inventory/sku-7?warehouse=hn-1";
        HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(2))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();
        HttpRequest request = HttpRequest.newBuilder(URI.create(url))
            .timeout(Duration.ofSeconds(3))
            .header("Accept", "application/json")
            .header("Authorization", "Bearer synthetic-wire-token")
            .GET().build();

        HttpResponse<String> response = client.send(
            request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertEquals("application/json",
            response.headers().firstValue("Content-Type").orElseThrow());
        assertTrue(response.body().contains("\"available\":3"));
        assertNotNull(observed.get());
        assertEquals("GET", observed.get().method());
        assertEquals("/api/inventory/sku-7", observed.get().path());
        assertEquals("warehouse=hn-1", observed.get().query());
        assertEquals("Bearer synthetic-wire-token",
            observed.get().authorization());
        assertEquals("application/json", observed.get().accept());
    }
}
```

`HttpServer` xử lý **HTTP thật** trên loopback. Port `0` tránh xung đột CI; `@AfterEach` dừng socket. JDK 17 không có API đóng `HttpClient` như JDK mới; custom executor vẫn phải được shutdown bởi owner.

Loopback HTTP không chứng minh TLS, HTTP/2, proxy hay DNS; test HTTPS phải dùng trust store test rõ ràng, **không** trust-all. Dự án Java module system cần cấu hình module `jdk.httpserver`.

### 4.2. Kiểm tra request body đã được gửi thật

Với `POST`, mock server đọc `exchange.getRequestBody()` **có giới hạn bytes**, parse JSON rồi kiểm tra fields thực gửi; test upload phải kiểm tra multipart boundary, part names và bytes thay vì chỉ kích thước.

Với streaming, server trả chunk; client dùng `BodyHandlers.ofInputStream()` và đóng stream kể cả khi lỗi. Đo pool gauges để phát hiện connection leak.

## 5. Spring WebClient và mock HTTP server

`WebClient` là client HTTP reactive; `WebTestClient` chủ yếu dùng kiểm tra **endpoint server WebFlux**. Để kiểm tra **request ra ngoài từ WebClient**, dùng mock HTTP server ở loopback hoặc một adapter chuyên dụng có hỗ trợ client. Ví dụ dưới đây dùng **OkHttp MockWebServer 4.x** như một dependency chỉ dành cho test; với version khác cần kiểm tra lại package/API.

### 5.1. WebClient + MockWebServer + StepVerifier

```java
package example.inventory.client;

import static org.junit.jupiter.api.Assertions.*;

import java.io.IOException;
import java.util.concurrent.TimeUnit;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class InventoryWebClientContractTest {
    private MockWebServer server;
    private WebClient client;

    @BeforeEach
    void start() throws IOException {
        server = new MockWebServer();
        server.start();
        client = WebClient.builder()
            .baseUrl(server.url("/").toString()).build();
    }

    @AfterEach
    void stop() throws IOException {
        server.shutdown();
    }

    @Test
    void verifiesOutgoingGetAndJsonResponse() throws Exception {
        server.enqueue(new MockResponse()
            .setResponseCode(200)
            .setHeader("Content-Type", "application/json")
            .setBody("""
                {"sku":"sku-7","warehouse":"hn-1","available":3}
                """));

        Mono<InventorySnapshot> result = client.get()
            .uri("/api/inventory/{sku}?warehouse={wh}", "sku-7", "hn-1")
            .header(HttpHeaders.AUTHORIZATION, "Bearer synthetic-web-token")
            .header(HttpHeaders.ACCEPT, "application/json")
            .retrieve()
            .bodyToMono(InventorySnapshot.class);

        StepVerifier.create(result)
            .assertNext(item -> assertEquals(3, item.available()))
            .expectComplete()
            .verify(java.time.Duration.ofSeconds(3));

        RecordedRequest request =
            server.takeRequest(2, TimeUnit.SECONDS);
        assertNotNull(request);
        assertEquals("GET", request.getMethod());
        assertEquals("/api/inventory/sku-7?warehouse=hn-1",
            request.getPath());
        assertEquals("Bearer synthetic-web-token",
            request.getHeader("Authorization"));
    }
}
```

`enqueue` chỉ cung cấp response; phải **assert `RecordedRequest`** cho target, method, headers và body. `StepVerifier` kiểm tra signals, không thay HTTP assertions; không `.block()` trên event loop.

### 5.2. Các lỗi response phải được test như tín hiệu HTTP

Khi mock server trả:

```http
HTTP/1.1 503 Service Unavailable
Retry-After: 2
Content-Type: application/problem+json

{"status":503,"code":"UPSTREAM_UNAVAILABLE"}
```

`WebClient.retrieve()` mặc định chuyển `4xx/5xx` thành lỗi `WebClientResponseException`; client có thể map lỗi bằng `onStatus`/`exchangeToMono`. Test nên assert **loại lỗi, mã HTTP, retry policy và số request đã gửi**, thay vì chỉ assert `expectError()` chung chung. Ví dụ `503` chỉ retry nếu hợp đồng/method cho phép, có giới hạn số lần và tổng deadline; `401`/`403` không nên retry như lỗi mạng.

## 6. Kiểm thử security: token, host đích và thông tin nhạy cảm

Mock HTTP server cần cho thấy **đúng credential được đưa vào đúng request**, nhưng không được làm test trở thành nơi lưu bí mật.

### 6.1. Cùng một client, hai danh tính khác nhau

Test quan trọng không chỉ gửi một token. Nó phải sử dụng **cùng `RestClient`/gateway** cho hai request liên tiếp rồi kiểm tra từng header:

```java
RestClient.Builder builder = RestClient.builder()
    .baseUrl("https://inventory.example.test");
MockRestServiceServer server =
    MockRestServiceServer.bindTo(builder).build();
InventoryRestGateway gateway =
    new InventoryRestGateway(builder.build());

for (String token : new String[]{"token-user-A", "token-user-B"}) {
    server.expect(requestTo(
            "https://inventory.example.test/api/inventory/sku-7?warehouse=hn-1"))
        .andExpect(header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
        .andRespond(withSuccess(
            "{\"sku\":\"sku-7\",\"warehouse\":\"hn-1\",\"available\":3}",
            MediaType.APPLICATION_JSON));
}
gateway.get("sku-7", "hn-1", "token-user-A");
gateway.get("sku-7", "hn-1", "token-user-B");
server.verify();
```

Đoạn trên dùng các static imports/JUnit fixture ở mục 3 và là **đoạn bổ sung vào test**, không phải một file Java độc lập. Trong ứng dụng đa tenant còn cần test **hai lời gọi đồng thời**, vì một `defaultHeader` hoặc biến mutable trong singleton có thể gây race mà test tuần tự không phát hiện.

### 6.2. Kiểm thử redirect và SSRF

- Cấu hình host đích từ allowlist tin cậy, test input kiểu `http://127.0.0.1/`, địa chỉ metadata nội bộ, path chứa `..` hoặc URL có `@` không thể biến thành đích mới.
- Nếu upstream trả `302 Location: https://other.example.test/collect`, test chính sách client: **không** tự chuyển bearer token/API key sang host khác. Với API không cần redirect, dùng `Redirect.NEVER` hoặc chính sách tương đương.
- HTTPS production phải xác minh certificate/hostname. Test với server HTTPS và trust store kiểm soát riêng, **không dùng** trust-all TLS hoặc bỏ hostname verification.
- Khi test `401/403`, không log raw `Authorization`, cookies, JWT claims, body có PII, signed URL hay một response lỗi chứa bí mật. Test có thể assert bằng token **giả**, còn log/trace chỉ ghi route template, status và correlation ID.

Mock HTTP server **không quyết định authorization** thay server thật. Nó có thể chứng minh client gửi token đúng cơ chế, nhưng chưa chứng minh token có audience/scope hợp lệ hoặc tenant được phép đọc tài nguyên. Cần test riêng với security/provider contract thật khi có khả năng.

## 7. Fault injection: lỗi mạng và HTTP phải có test quyết định

### 7.1. Ma trận test lỗi

| Tình huống mock | Điều nên assert |
| --- | --- |
| `200` + JSON hợp lệ | URI, headers, DTO, giá trị nghiệp vụ |
| `200` + JSON lỗi schema/Content-Type không phù hợp | Client báo parse/contract error, không dùng dữ liệu rỗng như thành công |
| `204 No Content` | Không đọc body JSON khi hợp đồng cho phép vắng body |
| `400`/`422` | Validation error được ánh xạ; không retry |
| `401`/`403` | Phân biệt authentication/authorization; không retry vô hạn |
| `404` + Problem Details | Không nhầm thành socket timeout hay inventory bằng 0 |
| `409`/`412` | Không tự retry một xung đột nghiệp vụ hoặc ETag cũ |
| `429`/`503` + `Retry-After` | Retry hữu hạn nếu hợp đồng cho phép; đo số lần request |
| Server chậm hơn deadline | Hết hạn đúng ngân sách, giải phóng request/response |
| Socket đóng giữa body hoặc JSON bị cắt | Parse/download lỗi, không trả kết quả thành công một phần |
| Redirect sang host khác | Không làm lộ token hoặc tự truy cập host ngoài chính sách |
| Response body rất lớn | Bị chặn bởi giới hạn bytes/buffer, không làm cạn heap |
| Hai yêu cầu song song | Không trộn headers/token/idempotency key giữa lời gọi |

Test cần tách **connect, pool-acquire, read và total timeout**. Với JDK `BodyHandlers.ofInputStream`, nhận headers/stream không chứng minh body đã đọc xong đúng deadline.

### 7.2. Tránh flaky test khi giả lập delay

Ưu tiên **barrier/latch, delay có cấu hình hoặc socket policy** thay vì dựa vào `Thread.sleep(100)` dễ flaky. Chọn timeout có biên an toàn cho CI.

Khi client dùng Reactor `retryWhen`, kiểm tra **số request thực nhận trên mock server**, không chỉ `StepVerifier` cuối cùng trả kết quả. Dùng virtual time để kiểm tra **backoff operator thuần** khi thích hợp, nhưng không thay thế kiểm thử network thực: virtual clock không điều khiển DNS, TCP hay socket server.

### 7.3. Retry sau timeout là câu hỏi nghiệp vụ

Ví dụ một request tạo lệnh giữ tồn kho:

```http
POST /api/reservations HTTP/1.1
Content-Type: application/json
Idempotency-Key: intent-789

{"sku":"sku-7","quantity":2}
```

Mock server có thể **ghi nhận lệnh rồi ngắt kết nối trước response**, sau đó nhận retry. Test cần chứng minh client giữ **cùng `Idempotency-Key`, payload và scope**; nếu được phép retry, không biến một ý định thành hai lệnh mới. Nhưng **mock server chỉ chứng minh client gửi đúng retry**, không thể một mình chứng minh provider thật đã dedup và commit đúng một lần. Cần provider contract/integration tests cho unique constraint, replay, status query và kết quả chưa chắc chắn.

Đừng coi lỗi socket là bằng chứng server chưa xử lý request. Phản hồi `504` cũng không phải kết luận operation thất bại. Với lệnh có side effect, cần tra cứu trạng thái hoặc retry theo **hợp đồng idempotency** đã công bố.

## 8. Kết nối mock test với OpenAPI và provider contract

Một mock server luôn trả đúng body bạn đã `enqueue` có thể khiến client test “xanh” ngay cả khi provider thật đã đổi từ `totalMinor` sang `amount`. Cần ba lớp bằng chứng:

1. **Đặc tả OpenAPI**: client expectations và response fixture dựa vào status, request/response schema, required fields, media type, auth requirements và error code đã được phê duyệt.
2. **Consumer/provider contract verification**: có thể dùng Pact, Spring Cloud Contract hoặc phương án tương đương để provider xác nhận có thể trả response mà consumer còn được hỗ trợ mong đợi.
3. **Integration/staging test**: kiểm chứng TLS, DNS, gateway headers, auth policy, connection pooling và các behavior không được mock phản ánh đầy đủ.

Khi có breaking change, không âm thầm sửa response fixture trong client test cho hợp với server mới. Đầu tiên kiểm tra client nào còn dùng field/status cũ; lập kế hoạch version hoặc chuyển đổi, rồi thay fixtures và assertions khi có bằng chứng đã xử lý tác động.

Trong CI, dùng **loopback và port động**, fixture/server mới cho từng test, timeout hữu hạn và shutdown qua `@AfterEach`; không phụ thuộc Internet hoặc credential thật. Dùng JSON matcher thay vì so whitespace, và kiểm tra pool metrics sau các ca timeout. Version hóa fixtures theo baseline của consumer **đang được hỗ trợ**.

## 9. Bài tập: một client “pass unit test” nhưng sai HTTP

**Bối cảnh:** `ReservationGateway` dùng `WebClient` gửi:

```http
POST /api/reservations HTTP/1.1
Content-Type: application/json
Authorization: Bearer <synthetic-user-token>
Idempotency-Key: intent-42

{"sku":"sku-7","quantity":2}
```

Client hiện tại tạo lại idempotency key sau mỗi timeout, dùng `defaultHeader` chứa token của user đầu tiên, và coi mọi `404` là số lượng tồn bằng `0`.

**Yêu cầu:**

1. Thiết kế mock server assertions cho **method, URL, content type, auth, key và JSON body**.
2. Viết trường hợp `201 Created` có `Location: /api/reservations/res-42` và phản hồi JSON hợp lệ.
3. Giả lập `404 application/problem+json`, `503 Retry-After: 2`, và mất response sau khi server nhận `POST`. Client phải phản ứng ra sao?
4. Dùng hai user gọi cùng singleton client; chứng minh token không bị trộn. Nêu thêm một test auth/scope ở provider thật mà mock client không thay thế được.
5. Giải thích vì sao `StepVerifier.expectNextCount(1)` mà không xem `RecordedRequest` **chưa đủ** để khẳng định HTTP client đúng.

**Hướng giải:** response/mock được xếp hàng theo từng request, assertions kiểm tra `POST`, path, JSON fields, `Authorization` và **`Idempotency-Key` ổn định**. Với `201`, kiểm tra `Location` và DTO; `404` phải ánh xạ đúng lỗi tài nguyên, không tự diễn giải thành hết hàng. Với `503`, retry chỉ khi được hợp đồng cho phép, giới hạn số lần và deadline, tuân thủ `Retry-After`. Mất response sau commit là **UNKNOWN**: cùng key/payload và tra cứu operation/replay. Token được gắn từng lời gọi; mock chỉ kiểm tra header đã gửi, còn provider phải xác minh chữ ký/audience/scope/tenant.

## 10. Checklist và kết luận

- [ ] Không chỉ mock gateway: có test **client thật phát request HTTP** hoặc request adapter Spring.
- [ ] Assert target URI, method, query, headers cần thiết, media type và cấu trúc JSON.
- [ ] Kiểm tra `200/201/204`, các nhóm lỗi `4xx/5xx`, `Problem Details`, timeout và response bị cắt.
- [ ] Token/key theo từng request, không tiết lộ credential qua redirect, logs hoặc singleton mutable state.
- [ ] Retry hữu hạn, không thay idempotency key/payload sau timeout; biết giới hạn của mock server.
- [ ] Đóng response stream và server test, giới hạn port/connection/timer; CI ổn định.
- [ ] Có provider contract verification và integration tests cho TLS/auth/gateway khi cần.

**Ghi nhớ:** mock một method Java chỉ kiểm thử người **sử dụng** client; mock HTTP server cho phép kiểm thử **thông điệp mà client thực sự gửi và nhận**. `MockRestServiceServer` tốt cho hợp đồng Spring nhanh; server loopback như `MockWebServer` hay JDK `HttpServer` giúp kiểm tra transport thực. Kết hợp với provider verification để tránh tạo một bộ test hoàn hảo chỉ trên dữ liệu giả.

