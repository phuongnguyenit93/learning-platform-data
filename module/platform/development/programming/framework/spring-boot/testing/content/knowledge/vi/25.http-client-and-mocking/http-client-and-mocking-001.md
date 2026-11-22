# Chọn ranh giới giả lập khi ứng dụng gọi dịch vụ HTTP ngoài

## 1. Vấn đề: mock ở đâu mới thực sự kiểm tra điều cần kiểm tra?

Một ứng dụng Spring Boot thường không chỉ **nhận** HTTP request. Trong cùng một nghiệp vụ, nó còn có thể **gọi ra ngoài**: dịch vụ báo giá vận chuyển, thanh toán, xác thực, định vị, email, quản lý tồn kho hoặc REST API của đối tác. Lúc viết test, ta phải quyết định **đặt ranh giới giả lập (test double boundary)** ở đâu.

Chẳng hạn quy trình checkout:

```text
                 Request từ người dùng
                          │
                          ▼
                 CheckoutController
                          │
                          ▼
                 CheckoutPriceService
                          │
                          ▼
                   ShippingQuotePort
                          │
                          ▼
                HttpShippingQuoteAdapter
                          │
                          ▼
                  Spring RestClient
                          │
                          ▼
                  TCP/TLS/HTTP transport
                          │
                          ▼
                API hãng vận chuyển
```

Nếu mock `ShippingQuotePort`, test checkout nhanh và không phụ thuộc mạng. Nhưng **nó không kiểm tra** URL, headers, JSON, status handling, HTTP client configuration hay việc request có thật sự được gửi.

Nếu mock ngay dưới `RestClient` bằng `MockRestServiceServer`, test được phần lớn cấu trúc HTTP request/response và logic adapter, nhưng **không kiểm tra** socket, DNS, TLS handshake, connection pooling, proxy hoặc read timeout của HTTP stack thật.

Nếu chạy một HTTP stub server trên `127.0.0.1`, code đi qua HTTP client thật và socket thật, nhưng **vẫn không chứng minh** đối tác production thực sự cung cấp đúng hợp đồng, mạng production có route đúng hoặc chứng chỉ TLS thực có hiệu lực.

Nếu kết nối đến sandbox của đối tác, ta có khả năng phát hiện thay đổi contract/deployment, nhưng test chậm hơn, đòi credential, khó lặp lại các sự cố như connection reset hoặc 429, và không nên chạy trên mọi lần build.

**Câu hỏi trọng tâm của bài:** cần xác định *nguy cơ cần phát hiện và thứ muốn giữ là thật*, rồi mới chọn seam/mock/stub phù hợp. Không có một tầng giả lập tốt nhất cho mọi test.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **mock ở domain port**, **mock HTTP request factory**, **HTTP stub server**, **contract test** và **sandbox test**.
2. Chọn ranh giới nhỏ nhất mà vẫn **giữ lại behavior có thể bị lỗi**.
3. Tổ chức Spring code theo **ports and adapters** để test nghiệp vụ không phải biết về HTTP.
4. Kiểm thử `RestClient` trên Spring Boot 3.x bằng `@RestClientTest` và `MockRestServiceServer`; hiểu chính xác những gì chúng không kiểm tra.
5. Kiểm thử outbound HTTP bằng server giả lập qua **socket thật** và `@DynamicPropertySource` cấp base URL/port động.
6. Phân biệt `MockMvc`/`WebTestClient` cho **inbound endpoint** với cách stub **outbound provider**.
7. Xử lý status 4xx/5xx, body null, JSON sai, headers, transport error, retry/timeout/circuit breaker, authentication và idempotency đúng phạm vi.
8. Dùng Java 17+, Spring Boot 3.x, JUnit Jupiter, Mockito và JDK HTTP server tạo ví dụ đầy đủ với **13 test methods** ở ba mức.
9. Tránh các test “xanh giả” do mock sâu quá, cấu hình client khác production hoặc chạm internet ngoài ý định.
10. Có checklist ra quyết định khi tích hợp đối tác mới hoặc phát hiện integration test flaky.

**Phạm vi ví dụ chạy:** Java 17+, Spring Boot **3.2–3.5**, Spring Framework 6.1+, Spring MVC/starter-web, `RestClient` và JUnit Jupiter. Tài liệu này phân biệt với Boot 3.0/3.1, Boot 4.x, `RestTemplate`, `WebClient` và HTTP interfaces; những phiên bản hoặc client khác phải điều chỉnh API/test setup tương ứng.

## 2. Định nghĩa rõ “ranh giới giả lập”

Ở đây **boundary** là chỗ ta thay một thành phần thật bằng một đối tượng hoặc dịch vụ do test kiểm soát. Boundary càng **cao** trong kiến trúc, test càng nhanh/cô lập nhưng càng bỏ qua nhiều hạ tầng; boundary càng **thấp**, ta giữ được nhiều behavior thật hơn nhưng test tốn tài nguyên và khó điều khiển hơn.

### 2.1. Một bản đồ năm mức

| Mức | Thành phần được thay thế | Giữ thật đến đâu? | Chủ yếu phát hiện lỗi gì? | Không chứng minh điều gì? |
|---|---|---|---|---|
| **A. Port mock** | `ShippingQuotePort` hoặc gateway interface | Business/service/aggregation phía trên port | Nhánh nghiệp vụ, validation, không gọi provider sai lúc | URL, JSON, headers, HTTP statuses, timeouts |
| **B. Client mock** | Request factory/HTTP exchange ở trong `RestClient` hoặc `RestTemplate` | Adapter + client request building + message conversion | Path/query/header/body, 2xx/4xx/5xx, response mapping | DNS/socket/TLS/redirect/connection behavior thật |
| **C. Local HTTP stub** | Endpoint ngoài ở địa chỉ loopback/ephemeral port | Adapter + HTTP library + local TCP + HTTP wire | URI encoding, headers thực, serialization, phần transport | Hợp đồng/chứng chỉ/mạng production của đối tác |
| **D. Contract verification** | Provider/consumer contract độc lập, bằng stub hoặc verifier | Schema và semantic compatibility theo contract | Field rename, required/optional fields, status/body drift | Toàn bộ deployment path/latency thật |
| **E. Provider sandbox/staging** | Ít hoặc không mock phía provider | Client + mạng/sandbox được phép + provider triển khai | Thực tích hợp credentials, routing, version/behavior | Production hoàn toàn giống sandbox hay lỗi được tái lập ổn định |

**“Mức B” và “mức C” không phải hai cách gọi khác nhau của cùng một tool.** Trong Spring, `MockRestServiceServer` cài một request factory giả, **không mở HTTP server thật**. WireMock hoặc OkHttp MockWebServer có thể mở HTTP server, nhận request qua socket và trả response theo kịch bản.

### 2.2. Mock, stub, fake, spy và contract không đồng nghĩa

- **Stub:** cung cấp câu trả lời có kiểm soát, chẳng hạn `GET /quotes/70000` trả JSON 200.
- **Mock:** ngoài trả lời còn xác minh invocation/interaction, ví dụ đúng một lần gọi `ShippingQuotePort.quote("70000")`.
- **Fake:** implementation đơn giản hoạt động thực trong test, ví dụ in-memory catalogue tính phí vận chuyển theo công thức.
- **Spy:** bọc/hỗ trợ quan sát method thật hoặc một phần method thật; dễ gây side effects ngoài ý định nếu spy một HTTP client thực.
- **Contract test:** kiểm tra một thỏa thuận request/response giữa consumer và provider; có thể kết hợp với stub nhưng không chỉ là một file JSON giả lập.
- **Sandbox test:** gọi một provider deployment được cho phép; không phải test double thuần.

Tên tool ít quan trọng hơn **đường code còn được thực thi**. Ví dụ một `@MockBean`/`@MockitoBean` cho toàn bộ `HttpShippingQuoteAdapter` chỉ kiểm tra logic phía trên adapter, dù test class đặt tên “HTTP integration test”.

### 2.3. Nguyên tắc vàng

> **Mock đúng tại ranh giới của thứ test không chịu trách nhiệm, nhưng giữ thật mọi thành phần có nguy cơ mà test cần phát hiện.**

Nếu mục tiêu là công thức checkout, mock port. Nếu mục tiêu là cách adapter dựng URL và map 503 thành domain exception, giữ adapter thật và giả HTTP. Nếu mục tiêu là client handling connection reset, proxy/TLS, cần HTTP-level/transport stub hoặc test hạ tầng tương ứng; không dùng Mockito để giả vờ đã kiểm tra mạng.

## 3. Cách chọn boundary theo câu hỏi kiểm thử

### 3.1. Một cây quyết định thực dụng

```text
Bạn cần chứng minh điều gì?
│
├─ Logic nghiệp vụ khi provider trả kết quả X?
│    └─ Mock/fake domain port (A)
│
├─ Adapter gửi method/URL/header/body đúng, parse JSON và map status?
│    └─ @RestClientTest + MockRestServiceServer (B)
│
├─ HTTP client thật xử lý networking/encoding/connections ra sao?
│    └─ Local HTTP stub (C)
│
├─ Provider và consumer đồng ý về contract/schema không?
│    └─ Consumer-driven/provider contract tests (D)
│
└─ Thực sự truy cập sandbox provider được phép và credential có hiệu lực?
     └─ Sandbox/staging smoke test tách khỏi unit CI (E)
```

Khi nhiều câu trả lời đều quan trọng, **dùng nhiều lớp test mỏng**, không ép một test lớn làm tất cả. Ví dụ 20 unit tests kiểm tra business scenarios, 5 slice tests kiểm tra adapter, 3 local HTTP tests kiểm tra wire, một ít provider contract tests và một smoke test theo lịch.

### 3.2. Ma trận tình huống

| Tình huống cần chứng minh | Boundary phù hợp hơn | Assertion quan trọng |
|---|---|---|
| Giá vận chuyển 25.000 cents được cộng vào giỏ hàng | Port mock | Tổng giá, số lần gọi port |
| Giỏ hàng âm bị từ chối trước khi gọi provider | Port mock | Exception + `verifyNoInteractions` |
| Endpoint đúng `/api/quotes/{postalCode}` | Client mock hoặc local stub | HTTP method, full URI, path variable |
| Có header `Accept: application/json` | Client mock; local stub xác nhận wire | Header đúng |
| JSON field `feeCents` được map thành Java `long` | Client mock có Jackson thật | DTO values |
| HTTP 503 được map thành domain exception | Client mock và/hoặc local stub | Status mapping, cause |
| Body 200 rỗng | Client mock | Không phát sinh null dereference/fallback tùy contract |
| Socket refused, connection reset, read timeout | HTTP stub/fault injection | Error classification, timeout/cancel budget |
| Retry đúng số lần, không retry 4xx tùy policy | Stateful stub + retry thực | Request count và outcome |
| OAuth credential được gắn đúng | Client mock + auth config; sandbox nếu cần | Authorization header (không lộ secret) |
| TLS certificate, proxy, DNS fail | Transport/infrastructure test | Actual handshake, trust/proxy behavior |
| Provider đổi tên JSON field | Consumer/provider contract | Schema compatibility |
| Spring service thực dùng đúng base URL/profile | Full-context local stub | `@DynamicPropertySource` + bean wiring |
| Inbound Controller HTTP status và outbound fallback | `MockMvc` hoặc real inbound HTTP kết hợp outbound stub | API contract và outbound call |
| Provider sandbox đã deploy version mới | Sandbox smoke | Behavior thật theo phiên bản, cleanup |
| No network được phép trong unit tests | Port/mock factory + network guard | Test fail nếu có outbound connection ngoài mong đợi |

### 3.3. Chọn boundary theo loại hồi quy

Một số hồi quy **không thể** được phát hiện ở mức quá cao:

- Đổi `.uri("/quotes/{id}", id)` thành `.uri("/quote/{id}", id)`: port mock không biết.
- Từ `RestClient.Builder` được Boot pre-configure sang `RestClient.create()`: test mock port không biết; thậm chí client-mock có thể không gắn vào instance mới.
- Đổi HTTP client implementation gây vấn đề connection reuse/read timeout: request factory giả không kiểm tra transport.
- Provider phát thêm required field hoặc đổi enum: stub thủ công lỗi thời vẫn trả schema cũ, contract verification mới có khả năng phát hiện drift nếu cùng được cập nhật/xác minh.
- Gọi nhầm staging host bằng production token: chỉ có check config/security boundary mới phát hiện; không nên tạo một test thật chạm production.

**Đừng nâng tất cả tests lên mức C/E.** Số lượng test lớn và phụ thuộc mạng làm build chậm/flaky. Thay vào đó chọn một “test pyramid” cân bằng theo mức rủi ro.

## 4. Thiết kế đường ra HTTP để có seam ổn định

### 4.1. Ports-and-adapters giúp business test không phụ thuộc framework

Nên tách:

```text
CheckoutPriceService
   └── ShippingQuotePort (domain interface)
           └── HttpShippingQuoteAdapter (production)
                   └── RestClient (transport)
                           └── external provider
```

Ý nghĩa:

- Business nhận **abstraction theo domain** (`ShippingQuotePort`), không nhận `RestClient` hoặc URL.
- Adapter chịu trách nhiệm **HTTP-specific concerns**: URL, HTTP headers, JSON mapping, status, I/O exception translation.
- Configuration inject base URL từ Spring Environment; test có thể thay bằng local stub.
- Unit test business mock port, nhưng adapter vẫn có test riêng ở mức B/C.
- Có thể đổi `RestClient` sang `WebClient` mà không thay business interface, nếu semantics domain không đổi.

**Không nên** phân tách bằng một interface chỉ chứa `RestClient.get()`. Interface nên nói ngôn ngữ của domain: `quote(postalCode)`, `authorizePayment(...)`, `reserveStock(...)`.

### 4.2. Không tạo HTTP client “ẩn” trong method

Phản mẫu:

```java
public ShippingQuote quote(String postalCode) {
    RestClient client = RestClient.create();
    return client.get()
            .uri("https://provider.example/api/quotes/{code}", postalCode)
            .retrieve()
            .body(ShippingQuote.class);
}
```

Đây là **snippet phản mẫu**, giả định có imports và type `ShippingQuote`. Cách này buộc logic vào URL và instance được tạo bằng tay; `@RestClientTest` không bảo đảm request factory mock đang gắn vào instance ấy. Ngoài ra, client tạo mới có thể bỏ qua Boot customizers/SSL/auth/timeouts đã định nghĩa qua injected builder.

Trên Spring Boot 3.x có `RestClient.Builder` được Boot cấu hình, **inject builder** rồi build client trong adapter constructor. Đây là cách sample phần 7 thực hiện.

### 4.3. Cấu hình nào phải đi qua seam?

Với outbound calls, ít nhất cần có đường cấu hình cho:

- Base URL/domain/port và path prefix.
- Connect/read/overall timeout thích hợp với client library.
- TLS trust configuration, mTLS nếu cần.
- Authentication (API key/OAuth) và secret injection an toàn.
- Content-Type/Accept, JSON/ObjectMapper.
- Retry/backoff, idempotency, rate limit, circuit breaker.
- Correlation ID/tracing, logging redaction.
- Proxy/DNS/connection pool nếu môi trường cần.

Không phải mọi cấu hình đều phải có bean riêng. Điểm chính là **test có thể thay endpoint mà không thay production business logic** và những settings quan trọng được test ở tầng mà chúng có tác dụng thật.

## 5. Những gì MockRestServiceServer thực sự kiểm tra

### 5.1. Spring Boot 3.x @RestClientTest

Theo tài liệu Spring Boot 3.5, `@RestClientTest(MyClient.class)`:

- tạo **slice context** tập trung vào REST client component được chọn;
- auto-configure JSON mapping phù hợp;
- cấu hình `RestTemplateBuilder` và `RestClient.Builder`;
- cung cấp `MockRestServiceServer` để gắn vào client builder đã được configure;
- không quét mọi `@Component` hoặc `@ConfigurationProperties` như `@SpringBootTest`.

Đối với `RestClient.Builder`, expectation về URI nên ghi **full URI**, ví dụ `https://shipping.example.invalid/api/quotes/70000`. Trường hợp `RestTemplateBuilder.rootUri(...)` có quy tắc expectation khác; **không dùng cách viết của RestTemplate rootUri cho RestClient.Builder**.

### 5.2. Request factory mock là giả lập ở dưới adapter

Một test:

```java
server.expect(requestTo(
        "https://shipping.example.invalid/api/quotes/70000"))
        .andExpect(method(HttpMethod.GET))
        .andRespond(withSuccess(
                """
                {"service":"STANDARD","feeCents":25000}
                """,
                MediaType.APPLICATION_JSON));

ShippingQuote quote = adapter.quote("70000");
server.verify();
```

được giải thích như sau:

1. Adapter thật gọi `RestClient` thật với URI/template/headers như code.
2. Client HTTP request được kiểm tra bằng expectation.
3. Mock request factory trả HTTP response giả với status, headers, body.
4. Client message converter map JSON thành `ShippingQuote`.
5. Adapter áp validation/exception translation.
6. `verify()` xác nhận các expectations đã được thỏa.

Nhưng **không có socket tới `shipping.example.invalid`**. Không kết luận từ test này rằng DNS, TLS, proxy, TCP retry hoặc connection pooling được kiểm chứng.

### 5.3. Dùng @RestClientTest khi nào là đủ?

Thông thường nó đủ cho:

- URI template expansion và query parameters.
- HTTP method và body format.
- Expected headers và media types.
- JSON serialization/deserialization theo mapper của test slice.
- Status mapping 404, 429, 500, 503 khi code xử lý thông thường.
- Missing/empty/invalid response theo converter/adapter.
- Request invocation count, conditional calls khi expectations phản ánh logic.

Nhưng JSON mapping trong slice vẫn có thể khác production nếu application có customizers/modules nằm ngoài slice. Khi có JSON contract phức tạp, import production configuration cần thiết hoặc có **full-context local HTTP test** để kiểm tra bean wiring hiệu lực.

### 5.4. Có những gì MockRestServiceServer không thể thay thế?

- DNS và TCP handshake thực.
- TLS certificate/hostname validation, mTLS, proxy route.
- Read/connect timeout và socket reset mô phỏng chính xác ở mọi HTTP client library.
- Chunked encoding, malformed HTTP headers, response compression, transfer framing.
- Pool saturation, keep-alive reuse, connection eviction.
- Bài test về packet fragmentation, low-level protocol edge cases.
- Chính provider sandbox/production deployment.

`MockRestResponseCreators.withException(IOException)` có thể **giả lập một I/O exception tại request factory**, rất hữu ích cho error-handling logic. Nhưng đừng nói test đó đã kiểm tra timeout socket thực của Apache HttpClient/JDK HttpClient/Reactor Netty.

## 6. Kịch bản demo: checkout lấy báo giá vận chuyển

Provider giả định có API:

```http
GET /api/quotes/70000 HTTP/1.1
Host: shipping.example.invalid
Accept: application/json
```

Trả:

```json
{
  "service": "STANDARD",
  "feeCents": 25000
}
```

Business contract:

- Input `postalCode` phải có đúng 5 chữ số ASCII.
- Phí vận chuyển (`feeCents`) phải không âm.
- Nếu provider trả 200 + body hợp lệ, adapter trả `ShippingQuote`.
- Nếu 200 + body rỗng, adapter ném `ShippingProviderException`, **không trả null cho service**.
- Nếu 2xx + phí âm, adapter ném exception vì dữ liệu vi phạm contract.
- Nếu 4xx/5xx, adapter chuyển status thành exception theo domain, giữ cause kỹ thuật.
- Nếu I/O failure, adapter chuyển thành domain exception, không nhầm với 404.
- Checkout cộng `subtotalCents + feeCents` bằng `Math.addExact` để không âm thầm overflow.
- Subtotal âm bị từ chối **trước khi gọi provider**.

**Đây là một contract minh họa**, không phải API của hãng vận chuyển thực. 70000 và các mã 99999, 88888, 77777 ở tests là fixtures. Tên miền `.invalid` là tên dùng để làm rõ rằng client-mock tests **không được có outbound internet connection thật**.

## 7. Ví dụ hoàn chỉnh Java 17+ / Spring Boot 3.x

### 7.1. Dependencies

Dự án dùng Spring Boot 3.2–3.5 và Java 17+; `spring-boot-starter-web` cung cấp Spring MVC, `RestClient` trên Spring Framework 6.1+, Jackson, Boot-managed `RestClient.Builder`. `spring-boot-starter-test` cung cấp Spring Test, JUnit Jupiter, AssertJ và Mockito.

**Gradle Groovy DSL** (đoạn dependencies/test task của dự án đã có Spring Boot plugin, repositories, BOM/dependency management và Java 17 toolchain):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

**Maven** (đoạn dependencies trong dự án có Spring Boot parent/BOM và Surefire/JDK phù hợp):

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Đây **không phải** toàn bộ `build.gradle` hoặc `pom.xml`. Không cần thư viện HTTP mock server ngoài trong ví dụ C: JDK 17 cung cấp `com.sun.net.httpserver.HttpServer` để minh họa loopback HTTP. Đối với dự án thực cần fault injection nâng cao, dùng WireMock/OkHttp MockWebServer/MockServer có thể phù hợp hơn; phần 11 giải thích.

### 7.2. Cây file

```text
src/
├── main/
│   ├── java/com/example/outbound/
│   │   ├── OutboundDemoApplication.java
│   │   ├── ShippingQuote.java
│   │   ├── ShippingQuotePort.java
│   │   ├── ShippingProviderException.java
│   │   ├── HttpShippingQuoteAdapter.java
│   │   └── CheckoutPriceService.java
│   └── resources/
│       └── application.properties
└── test/java/com/example/outbound/
    ├── CheckoutPriceServiceTest.java
    ├── HttpShippingQuoteAdapterSliceTest.java
    └── HttpShippingQuoteAdapterLoopbackTest.java
```

Các test đều nằm cùng package root để Spring Boot tìm `@SpringBootApplication`. Mẫu không có database, HTTP inbound controller, secrets hoặc external dependencies ngoài starter web/test.

### 7.3. Entry point

**File `src/main/java/com/example/outbound/OutboundDemoApplication.java`:**

```java
package com.example.outbound;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OutboundDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(OutboundDemoApplication.class, args);
    }
}
```

### 7.4. Domain DTO và port

**File `src/main/java/com/example/outbound/ShippingQuote.java`:**

```java
package com.example.outbound;

public record ShippingQuote(
        String service,
        long feeCents
) {}
```

**File `src/main/java/com/example/outbound/ShippingQuotePort.java`:**

```java
package com.example.outbound;

public interface ShippingQuotePort {

    ShippingQuote quote(String postalCode);
}
```

Port không chứa HTTP status, `RestClient` hoặc framework-specific classes. Những details đó thuộc adapter; business logic chỉ cần một quote với số cents và service level.

### 7.5. Domain exception có thể giữ nguyên cause

**File `src/main/java/com/example/outbound/ShippingProviderException.java`:**

```java
package com.example.outbound;

public class ShippingProviderException extends RuntimeException {

    public ShippingProviderException(String message) {
        super(message);
    }

    public ShippingProviderException(
            String message,
            Throwable cause) {
        super(message, cause);
    }
}
```

Adapter sẽ không log raw response body hoặc credentials khi tạo exception. Việc lưu status code trong message để demo là được; trong sản phẩm thật có thể dùng typed error code, sanitized metadata và tracing ID.

### 7.6. HTTP adapter production sử dụng Boot-managed RestClient.Builder

**File `src/main/java/com/example/outbound/HttpShippingQuoteAdapter.java`:**

```java
package com.example.outbound;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;

@Component
public class HttpShippingQuoteAdapter implements ShippingQuotePort {

    private final RestClient client;

    public HttpShippingQuoteAdapter(
            RestClient.Builder builder,
            @Value("${shipping.base-url}") String baseUrl) {

        this.client = builder.baseUrl(baseUrl).build();
    }

    @Override
    public ShippingQuote quote(String postalCode) {

        if (postalCode == null
                || !postalCode.matches("[0-9]{5}")) {
            throw new IllegalArgumentException(
                    "postalCode must contain exactly five digits");
        }

        try {
            ShippingQuote result = client.get()
                    .uri("/api/quotes/{postalCode}", postalCode)
                    .accept(MediaType.APPLICATION_JSON)
                    .retrieve()
                    .body(ShippingQuote.class);

            if (result == null) {
                throw new ShippingProviderException(
                        "Empty shipping quote");
            }

            if (result.feeCents() < 0) {
                throw new ShippingProviderException(
                        "Negative shipping fee");
            }

            return result;
        }
        catch (RestClientResponseException ex) {
            throw new ShippingProviderException(
                    "Provider HTTP "
                    + ex.getStatusCode().value(),
                    ex);
        }
        catch (ResourceAccessException ex) {
            throw new ShippingProviderException(
                    "Provider I/O failure",
                    ex);
        }
    }
}
```

**Chú ý API và exception semantics:**

- `RestClient.Builder` được Spring Boot pre-configure; adapter build một client dùng lại, không new mỗi lần request.
- `@Value("${shipping.base-url}")` lấy base URL từ Environment. Unit/slice/live test có thể thay property mà không sửa adapter.
- `.uri("/api/quotes/{postalCode}", postalCode)` đưa path variable qua URI template; ví dụ input chỉ 5 chữ số nên không gây tranh cãi về encoding.
- `.accept(APPLICATION_JSON)` thiết lập request header mà mock và local stub có thể kiểm tra.
- `.retrieve().body(ShippingQuote.class)` dùng message converters để deserialize JSON.
- Với 4xx/5xx thông thường, `retrieve()` của Spring Framework RestClient ném một `RestClientResponseException` subtype; adapter chuyển thành domain error và giữ cause.
- Lỗi giao tiếp I/O có thể xuất hiện dưới dạng `ResourceAccessException`; adapter phân biệt với HTTP response đã có status.
- Empty-body/negative fee policy được kiểm tra **sau** deserialize.
- Client không cấu hình automatic retry trong sample. Đừng kỳ vọng một 503 tự động làm phát sinh nhiều HTTP attempts.
- JSON bị malformed có thể ném conversion-related `RestClientException` không được map riêng bởi mã sample; nếu cần một typed domain exception cho mọi malformed body, thêm logic/catch cụ thể và test riêng. Không tự tuyên bố sample đã chuẩn hóa mọi lỗi decoder.

**Không** đưa một URL thật/production credential vào test. Project demo đặt URL mặc định `.invalid`; local HTTP test thay bằng port loopback bằng `@DynamicPropertySource`.

### 7.7. Business service dùng port, không biết HTTP

**File `src/main/java/com/example/outbound/CheckoutPriceService.java`:**

```java
package com.example.outbound;

import org.springframework.stereotype.Service;

@Service
public class CheckoutPriceService {

    private final ShippingQuotePort shipping;

    public CheckoutPriceService(ShippingQuotePort shipping) {
        this.shipping = shipping;
    }

    public long totalCents(
            long subtotalCents,
            String postalCode) {

        if (subtotalCents < 0) {
            throw new IllegalArgumentException(
                    "subtotalCents must be non-negative");
        }

        ShippingQuote quote = shipping.quote(postalCode);
        return Math.addExact(
                subtotalCents,
                quote.feeCents());
    }
}
```

Service chịu trách nhiệm tổng tiền và validation input nghiệp vụ. Nó không biết `GET`, base URL, headers hay JSON. Giả lập ở port là đủ khi mục tiêu chỉ là công thức tổng, số lần gọi và nhánh exception.

`Math.addExact` ném `ArithmeticException` nếu overflow; sample không giấu lỗi bằng cách ép `long` sang `int`. Domain tiền thật có thể cần currency/precision/decimal policy khác, nhưng đây là phần minh họa nguyên tắc cộng chi phí.

### 7.8. Production configuration có giá trị an toàn cho sample

**File `src/main/resources/application.properties`:**

```properties
shipping.base-url=https://shipping.example.invalid
```

Tên miền `.invalid` ngăn người đọc nhầm với API sản xuất. Trong ứng dụng thật, base URL là một environment-specific setting như `shipping.base-url` hoặc một typed `@ConfigurationProperties`. Test cấp URL giả bằng property overrides hoặc dynamic port.

Nếu production config có connection pool/timeouts/TLS/auth, nên giữ cùng client builder/customizer cho local HTTP tests; trong các test mock request factory, **không được kết luận** những transport settings đã hoạt động thật.

## 8. Tầng A: unit test business với Mockito, không khởi động Spring

**File `src/test/java/com/example/outbound/CheckoutPriceServiceTest.java`:**

```java
package com.example.outbound;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class CheckoutPriceServiceTest {

    @Test
    void addsShippingFeeToSubtotal() {
        ShippingQuotePort port = mock(ShippingQuotePort.class);

        when(port.quote("70000"))
                .thenReturn(new ShippingQuote("STANDARD", 25_000));

        CheckoutPriceService service =
                new CheckoutPriceService(port);

        long total = service.totalCents(100_000, "70000");

        assertThat(total).isEqualTo(125_000L);
        verify(port).quote("70000");
    }

    @Test
    void rejectsNegativeSubtotalBeforeCallingProvider() {
        ShippingQuotePort port = mock(ShippingQuotePort.class);

        CheckoutPriceService service =
                new CheckoutPriceService(port);

        assertThatThrownBy(() ->
                service.totalCents(-1, "70000"))
                .isInstanceOf(IllegalArgumentException.class);

        verifyNoInteractions(port);
    }

    @Test
    void propagatesDomainFailureFromGateway() {
        ShippingQuotePort port = mock(ShippingQuotePort.class);

        when(port.quote("70000"))
                .thenThrow(new ShippingProviderException(
                        "Provider unavailable"));

        CheckoutPriceService service =
                new CheckoutPriceService(port);

        assertThatThrownBy(() ->
                service.totalCents(100_000, "70000"))
                .isInstanceOf(ShippingProviderException.class)
                .hasMessage("Provider unavailable");

        verify(port).quote("70000");
    }
}
```

**Đây là 3 bài test JUnit Jupiter hoàn chỉnh, không cần Spring ApplicationContext.**

Các tests chứng minh:

- Checkout tính tổng đúng với quote đã cho.
- Input subtotal âm bị từ chối, port **không bị gọi**.
- Business có hành vi được xác định khi port ném exception.

Chúng **không chứng minh adapter HTTP hoạt động**. Nếu bạn chỉ có ba tests này và một developer đổi `GET /api/quotes/70000` thành endpoint sai, build vẫn có thể xanh. Đây không phải lỗi của unit test; đó là **lỗ hổng nếu không có các tests ở tầng B/C**.

### 8.1. Trường hợp nên dùng một fake thay mock

Nếu logic có rất nhiều kịch bản và bạn không cần assert interaction count, có thể tạo `InMemoryShippingQuotePort` trả giá từ một `Map<String, ShippingQuote>`. Điều này làm tests bớt gắn với số lần method được gọi.

**Tuy nhiên:** fake đó phải chỉ rõ nó không mô phỏng HTTP; không được biến nó thành một “bản sao thuật toán của provider” rồi dùng như contract truth khi provider đổi chính sách.

### 8.2. Có cần @MockitoBean/@MockBean trong unit test không?

Không. Vì service được tạo thủ công bằng `new CheckoutPriceService(port)`, Mockito `mock(ShippingQuotePort.class)` đủ. Không khởi động Spring sẽ nhanh và giảm context coupling.

Khi test **Spring bean wiring** hoặc controller/service trong một Spring test context, có thể override dependency bằng `@MockitoBean` trong Spring Framework 6.2 / Spring Boot 3.4+, hoặc `@MockBean` theo nhánh Spring Boot 3 cũ. Các annotation có version/lifecycle khác; nếu không cần context thì không nên dùng bean override chỉ để mock một interface Java.

## 9. Tầng B: @RestClientTest + MockRestServiceServer

Đây là test cho **adapter HTTP**. Ta giữ nguyên `HttpShippingQuoteAdapter` production, Boot-managed `RestClient.Builder` và JSON conversion, nhưng mock request factory. Không có socket tới domain `.invalid`.

**File `src/test/java/com/example/outbound/HttpShippingQuoteAdapterSliceTest.java`:**

```java
package com.example.outbound;

import java.io.IOException;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.client.RestClientTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;

import static org.springframework.test.web.client.response.MockRestResponseCreators.withException;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withServiceUnavailable;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

@RestClientTest(
        value = HttpShippingQuoteAdapter.class,
        properties = "shipping.base-url=https://shipping.example.invalid"
)
class HttpShippingQuoteAdapterSliceTest {

    @Autowired
    HttpShippingQuoteAdapter adapter;

    @Autowired
    MockRestServiceServer server;

    @AfterEach
    void resetExpectationsForNextTest() {
        server.reset();
    }

    @Test
    void sendsCorrectMethodUrlAndAcceptAndReadsJson() {
        server.expect(requestTo(
                "https://shipping.example.invalid/api/quotes/70000"))
                .andExpect(method(HttpMethod.GET))
                .andExpect(header(
                        HttpHeaders.ACCEPT,
                        MediaType.APPLICATION_JSON_VALUE))
                .andRespond(withSuccess(
                        """
                        {
                          "service": "STANDARD",
                          "feeCents": 25000
                        }
                        """,
                        MediaType.APPLICATION_JSON));

        ShippingQuote quote = adapter.quote("70000");

        assertThat(quote).isEqualTo(
                new ShippingQuote("STANDARD", 25_000L));
        server.verify();
    }

    @Test
    void translatesHttp503IntoDomainException() {
        server.expect(requestTo(
                "https://shipping.example.invalid/api/quotes/99999"))
                .andRespond(withServiceUnavailable());

        assertThatThrownBy(() -> adapter.quote("99999"))
                .isInstanceOf(ShippingProviderException.class)
                .hasMessage("Provider HTTP 503");

        server.verify();
    }

    @Test
    void treatsEmptySuccessfulResponseAsContractError() {
        server.expect(requestTo(
                "https://shipping.example.invalid/api/quotes/88888"))
                .andRespond(withSuccess(
                        "",
                        MediaType.APPLICATION_JSON));

        assertThatThrownBy(() -> adapter.quote("88888"))
                .isInstanceOf(ShippingProviderException.class)
                .hasMessage("Empty shipping quote");

        server.verify();
    }

    @Test
    void rejectsNegativeFeeEvenWhenHttpStatusIs200() {
        server.expect(requestTo(
                "https://shipping.example.invalid/api/quotes/77777"))
                .andRespond(withSuccess(
                        """
                        {"service":"STANDARD","feeCents":-5}
                        """,
                        MediaType.APPLICATION_JSON));

        assertThatThrownBy(() -> adapter.quote("77777"))
                .isInstanceOf(ShippingProviderException.class)
                .hasMessage("Negative shipping fee");

        server.verify();
    }

    @Test
    void translatesMockedIoException() {
        server.expect(requestTo(
                "https://shipping.example.invalid/api/quotes/55555"))
                .andRespond(withException(
                        new IOException("simulated socket failure")));

        assertThatThrownBy(() -> adapter.quote("55555"))
                .isInstanceOf(ShippingProviderException.class)
                .hasMessage("Provider I/O failure")
                .hasCauseInstanceOf(
                        org.springframework.web.client
                                .ResourceAccessException.class);

        server.verify();
    }

    @Test
    void rejectsInvalidPostalCodeWithoutHttpRequest() {
        assertThatThrownBy(() ->
                adapter.quote("NOT-A-POSTAL-CODE"))
                .isInstanceOf(IllegalArgumentException.class);

        // Không khai báo expectation nào;
        // test chỉ được pass nếu adapter không gửi request.
        server.verify();
    }
}
```

**Kỳ vọng:** 6 methods JUnit ở lớp này pass trên Spring Boot 3.2–3.5/Spring Framework tương ứng với dependencies đã nêu.

**Đặc biệt kiểm tra:** `RestClient.Builder` dùng full URI trong `MockRestServiceServer.requestTo(...)`. Nếu test expectation chỉ dùng `"/api/quotes/70000"`, có thể mismatch vì request thật mang URL tuyệt đối; Spring Boot 3.5 documentation nêu rõ sự khác biệt này giữa RestClient builder và RestTemplate rootUri.

**Vì sao `server.reset()` trong @AfterEach?** Mock server lưu expectations và request counts. Mỗi test phải độc lập, không mang state qua test khác. Mỗi test gọi `server.verify()` ngay sau operation cần kiểm tra, rồi `reset()` để tránh state rò rỉ. Khi có nhiều RestClient instances/builders trong một context, một injected mock server có thể không bao phủ tất cả; cần kiểm tra customizer/bean tương ứng.

### 9.1. Mocked IOException không phải transport test

Test `translatesMockedIoException` chỉ tạo exception từ mock request factory; nó kiểm tra **exception translation branch**. Nó **không** chứng minh JDK/Apache client có timeout đúng, socket có đóng đúng hoặc pool recover sau connection reset. Để kiểm tra các điều đó, dùng tầng C với server có khả năng trì hoãn/drop connection, hoặc network fault injection chuyên biệt.

### 9.2. @RestClientTest chỉ nạp slice

Trong ví dụ, `CheckoutPriceService` không phải bean cần test ở slice nên không cần được scan. `@RestClientTest(HttpShippingQuoteAdapter.class)` tập trung vào adapter và hỗ trợ REST client. Nếu adapter production phụ thuộc một custom `@ConfigurationProperties` class, interceptor auth hoặc Jackson module không thuộc slice, cần đưa configuration đó vào test bằng cơ chế phù hợp (ví dụ `@EnableConfigurationProperties`/`@Import`). **Không tự tạo một client test-only khác production** chỉ để làm test xanh.

## 10. Tầng C: real HTTP loopback với SpringBootTest và JDK HttpServer

Đây là **HTTP integration test với một provider stub cục bộ**, không phải gọi production provider.

- Client production `HttpShippingQuoteAdapter` không bị mock.
- Spring Boot khởi động **full non-web ApplicationContext** (không mở inbound server).
- Một `com.sun.net.httpserver.HttpServer` chạy trên `127.0.0.1` và **port 0** để hệ điều hành chọn cổng trống.
- `@DynamicPropertySource` cấp `shipping.base-url` bằng địa chỉ thực của stub trước khi adapter được tạo.
- Gọi adapter đi qua actual `RestClient` → HTTP client request factory thật → socket loopback → stub.
- Các tests xác nhận happy path, HTTP 503, empty body và HTTP 404.
- Không cần WireMock/OkHttp thêm dependency cho *minimal demonstration*. JDK stub không có các tiện ích fault injection/pattern matching mạnh như dedicated tools.

**File `src/test/java/com/example/outbound/HttpShippingQuoteAdapterLoopbackTest.java`:**

```java
package com.example.outbound;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(
        classes = OutboundDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class HttpShippingQuoteAdapterLoopbackTest {

    private static final HttpServer STUB = startStub();

    @DynamicPropertySource
    static void overrideOutboundBaseUrl(
            DynamicPropertyRegistry registry) {
        registry.add("shipping.base-url",
                () -> "http://127.0.0.1:"
                        + STUB.getAddress().getPort());
    }

    @Autowired
    HttpShippingQuoteAdapter adapter;

    private static HttpServer startStub() {
        try {
            HttpServer server = HttpServer.create(
                    new InetSocketAddress("127.0.0.1", 0), 0);

            server.createContext(
                    "/api/quotes/",
                    HttpShippingQuoteAdapterLoopbackTest::respond);

            server.start();
            return server;
        }
        catch (IOException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    private static void respond(HttpExchange exchange)
            throws IOException {

        String accept = exchange.getRequestHeaders()
                .getFirst("Accept");

        String path = exchange.getRequestURI().getPath();
        int status = 200;
        String body;

        if (!"GET".equals(exchange.getRequestMethod())) {
            status = 405;
            body = """
                    {"error":"method_not_allowed"}
                    """;
        }
        else if (accept == null
                || !accept.contains("application/json")) {
            status = 406;
            body = """
                    {"error":"not_acceptable"}
                    """;
        }
        else {
            switch (path) {
                case "/api/quotes/70000" ->
                    body = """
                            {
                              "service": "STANDARD",
                              "feeCents": 25000
                            }
                            """;

                case "/api/quotes/99999" -> {
                    status = 503;
                    body = """
                            {"error":"temporarily_unavailable"}
                            """;
                }

                case "/api/quotes/88888" ->
                    body = "";

                default -> {
                    status = 404;
                    body = """
                            {"error":"not_found"}
                            """;
                }
            }
        }

        exchange.getResponseHeaders().set(
                "Content-Type", "application/json");

        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);

        if (bytes.length == 0) {
            exchange.sendResponseHeaders(status, -1);
            exchange.close();
            return;
        }

        exchange.sendResponseHeaders(status, bytes.length);

        try (OutputStream stream = exchange.getResponseBody()) {
            stream.write(bytes);
        }
    }

    @AfterAll
    static void stopStub() {
        STUB.stop(0);
    }

    @Test
    void usesActualHttpSocketForSuccessfulQuote() {
        ShippingQuote result = adapter.quote("70000");

        assertThat(result).isEqualTo(
                new ShippingQuote("STANDARD", 25_000L));
    }

    @Test
    void mapsRealHttp503Response() {
        assertThatThrownBy(() -> adapter.quote("99999"))
                .isInstanceOf(ShippingProviderException.class)
                .hasMessage("Provider HTTP 503");
    }

    @Test
    void handles200WithNoResponseBody() {
        assertThatThrownBy(() -> adapter.quote("88888"))
                .isInstanceOf(ShippingProviderException.class)
                .hasMessage("Empty shipping quote");
    }

    @Test
    void mapsRealHttp404Response() {
        assertThatThrownBy(() -> adapter.quote("12345"))
                .isInstanceOf(ShippingProviderException.class)
                .hasMessage("Provider HTTP 404");
    }
}
```

**Kỳ vọng:** 4 test methods pass trong một JDK 17+ full Spring Boot 3.x context theo sample. Tổng ba lớp ở phần 8–10 là **3 + 6 + 4 = 13 JUnit test methods**.

### 10.1. Vì sao chọn port 0?

Nếu bạn hardcode cổng 8089, 9999 hoặc 9000, máy CI chạy nhiều worker song song có thể bị `BindException: Address already in use`. Bind `new InetSocketAddress("127.0.0.1", 0)` nhờ hệ điều hành chọn port rảnh, sau đó `STUB.getAddress().getPort()` trả port thực.

`@DynamicPropertySource` cung cấp giá trị đó cho Spring `Environment` **trước khi Spring khởi tạo adapter**. Nó có precedence cao trong Spring TestContext, phù hợp để thay base URL được khai báo trong `application.properties`.

### 10.2. Điều gì được kiểm tra ở đây?

- Đường code của production adapter và Spring-managed `RestClient.Builder`.
- URI được nối với base URL thực, method và Accept header (stub trả 405/406 nếu sai).
- HTTP request trên socket loopback.
- Response status, bytes, headers Content-Type qua HTTP stack.
- Jackson conversion, status handling, empty body.
- Full application bean wiring/active configuration (ngoại trừ base URL được override).

**Không được suy ra:**

- DNS tên miền ngoài hoạt động; test dùng IP loopback.
- TLS trust chain hợp lệ; test dùng HTTP không mã hóa.
- Proxy/VPN/firewall production đúng.
- Provider contract đã được provider xác nhận.
- Connect/read timeout, retry/pool hết sức chịu tải; sample không cấu hình hoặc ép những tình huống đó.
- Inbound controller của ứng dụng hoạt động; context được nạp với `webEnvironment=NONE`.

### 10.3. Lưu ý về vòng đời mock HTTP server

Sample khởi tạo một static stub trước khi TestContext resolve dynamic properties, rồi dừng ở `@AfterAll`. Trong class test này, stub phục vụ các methods tuần tự, không chứa mutable expectations.

Với suite lớn hoặc parallel tests, hãy quản lý lifecycle cẩn thận:

- Không để context cache trỏ tới server đã dừng nếu nhiều test classes dùng chung property configuration.
- Tránh chia sẻ một static stub mutable giữa các tests song song.
- Sử dụng JUnit extensions/lifecycle adapters chính thức của WireMock/MockWebServer khi có.
- Không ghi/đổi global `System.setProperty("shipping.base-url",...)` từ nhiều tests.
- Không dùng cổng cố định khi nhiều JVM/CI workers có thể chạy đồng thời.
- Nếu mỗi test cần server mới, phải đảm bảo Spring context tạo client sau khi dynamic property được cập nhật hoặc dùng context riêng; thay port của server trong khi bean RestClient đã build **không tự làm RestClient đổi base URL**.

**Nhận định chính xác:** loopback HTTP stub là một real network **trong máy kiểm thử**; nó không phải provider mạng thật và không phải end-to-end production test.

## 11. Khi nào nên dùng WireMock, MockWebServer hoặc MockServer thay cho JDK stub?

Trong dự án thực, một dedicated HTTP stub server thường dễ dùng và linh hoạt hơn tự viết handler như phần 10.

### 11.1. WireMock

WireMock có thể:

- match HTTP method, URL/path/query, headers, body;
- trả các mã 2xx/4xx/5xx, JSON payloads;
- ghi request journal để xác nhận call count;
- trả response theo kịch bản stateful;
- mô phỏng delay, faults, templating theo phiên bản/extension;
- triển khai stub độc lập phục vụ component/integration tests.

Phù hợp khi bạn muốn test một provider API phức tạp với nhiều endpoints và scenarios mà không tạo nhiều code `HttpServer.createContext`.

**Cảnh báo:** WireMock stub file không tự được provider xác nhận. Nếu viết tay fixture JSON rồi không cập nhật khi API thực thay đổi, tests vẫn có thể xanh giả. Cần contract verification hoặc sandbox check phù hợp.

### 11.2. OkHttp MockWebServer

MockWebServer nhận HTTP requests thực, cho phép enqueue responses, kiểm tra `RecordedRequest`, hỗ trợ nhiều test cases về connection behavior. Nó thường hợp lý cho test một HTTP client library hoặc adapter nhỏ.

Nên xác nhận artifact/package name theo phiên bản đang dùng; các nhánh OkHttp 4 và 5 có khác biệt modules/API. **Không sao chép import từ hướng dẫn cũ rồi mặc định áp cho version mới**.

### 11.3. MockServer

MockServer cung cấp expectation matching, request verification và response customization; có thể dùng embedded server/container. Chọn khi team đã chuẩn hóa tool đó hoặc cần HTTP interaction logic phức tạp.

### 11.4. Chọn theo mục tiêu

| Nhu cầu | Hướng cân nhắc |
|---|---|
| Một request JSON đơn giản, không cần socket | `MockRestServiceServer` |
| Một vài HTTP scenarios có socket, không thêm dependency | JDK `HttpServer` như sample |
| Nhiều routes, headers, sequential responses, faults | WireMock/MockWebServer |
| Consumer/provider contracts được xác nhận tự động | Pact/Spring Cloud Contract theo khả năng tích hợp |
| Mô phỏng TLS/proxy/latency/network faults sát thực | Dedicated stub/proxy/network fault injection |
| Kiểm tra thực với provider deployment | Sandbox smoke có credential/quota/cleanup |
| Mock trong nhiều teams cùng ngôn ngữ contract | Shared contract/stub artifact được version hóa |

Tool được chọn dựa trên **rủi ro phải phát hiện**, không phải tool có nhiều tính năng nhất.

## 12. WebClient, RestTemplate, HTTP interfaces và WebTestClient

### 12.1. RestTemplate

`RestTemplate` là synchronous client truyền thống. Spring Framework cung cấp `MockRestServiceServer.bindTo(restTemplate)`; Spring Boot có `RestTemplateBuilder`.

Nếu client production được tạo qua `RestTemplateBuilder.rootUri(...)`, expectation URI trong một số Spring Boot slice tests có thể viết **relative** theo hướng dẫn tài liệu; với `RestClient.Builder` lại cần full URI. Đọc đúng docs của client/version và test `requestTo(...)` thực, không blindly copy expectation giữa hai API.

Đặc biệt, một RestTemplate tạo thủ công bằng `new RestTemplate()` có thể không nhận builder/customizer/SSL settings mà application muốn. Hãy inject đúng production bean/builder ở tầng B/C.

### 12.2. WebClient

`WebClient` là reactive/non-blocking client của Spring WebFlux:

```java
Mono<ShippingQuote> quote = webClient.get()
        .uri("/api/quotes/{code}", "70000")
        .retrieve()
        .bodyToMono(ShippingQuote.class);
```

**Snippet minh họa**, cần WebClient bean và imports; không phải file runnable độc lập. Client tạo `Mono` không có nghĩa đã gửi HTTP request: phải **subscribe** hoặc dùng `StepVerifier`.

Spring Boot có `@WebClientTest` giúp slice test WebClient-related components và inject `WebClient.Builder`. Nhưng **không tự động đồng nghĩa** với một `MockRestServiceServer` dành cho RestClient/RestTemplate. Các lựa chọn:

- Mock `ExchangeFunction` hoặc `ExchangeFilterFunction` để unit-test một lớp nhỏ (nhận thức rõ rằng có thể bỏ qua network, codecs hoặc nhiều filters).
- Dùng MockWebServer/WireMock HTTP stub qua socket cho outbound WebClient.
- Dùng `StepVerifier` với một Publisher được compose đầy đủ; đừng chỉ assert `Mono != null`.
- Khi cần test timeout/cancellation/retry trên Reactor Netty, dùng network stub/fault injection sát cơ chế thật.
- Nếu code gọi `subscribe()` rời rạc trong business method, test rất khó quan sát hoàn tất hoặc lỗi; hãy return Publisher và để caller compose.

### 12.3. WebTestClient dễ bị nhầm

**`WebTestClient` thường dùng để test ứng dụng server nhận request** (Spring MVC/WebFlux), dù nó được xây trên WebClient. Nó có thể bind vào controller, application context hoặc một server sống.

**Dùng WebTestClient để gọi một inbound controller không tự stub outbound HTTP mà controller phát sinh.** Nếu controller gọi WebClient/RestClient ra đối tác, bạn vẫn cần mock port (A) hoặc stub outbound provider (B/C).

Ví dụ:

```text
WebTestClient -> ứng dụng của bạn -> WebClient -> provider bên ngoài
       ▲                                ▲
       │                                │
  inbound test                    outbound stub vẫn cần
```

Tương tự, `MockMvc` kiểm tra inbound Servlet MVC chain; nó không tự thay một remote REST API bằng mock.

### 12.4. HTTP interfaces / @HttpExchange

Spring Framework hỗ trợ declarative HTTP interfaces với `@HttpExchange` và proxy tạo từ `RestClientAdapter` hoặc `WebClientAdapter`. Boundary vẫn phải được chọn theo cùng nguyên tắc:

- Mock **interface theo domain** nếu chỉ test business.
- Kiểm tra request mapping của generated HTTP client bằng HTTP stub.
- Kiểm tra status/serialization/transport theo underlying adapter.
- Không nghĩ test interface method với Mockito đã chứng minh Spring HTTP proxy đúng.

### 12.5. Khác biệt phiên bản quan trọng

- Spring Boot **3.0/3.1**: `RestClient` (Spring Framework 6.1) chưa có hoặc chưa là lựa chọn như trong sample. Dùng `RestTemplate` hoặc `WebClient` theo stack/version; không copy `@RestClientTest` + RestClient.Builder nếu class không tồn tại.
- Spring Boot **3.2–3.5**: `RestClient` và Boot-managed RestClient.Builder phù hợp với sample.
- Spring Framework **6.2**/Boot **3.4+** có `@MockitoBean`; Boot `@MockBean` ở nhiều nhánh Boot 3 đã được đánh dấu deprecated và đang được thay thế. Chọn annotation đúng version và test override semantics.
- Spring Boot **4.x** tổ chức nhiều test starter/module/package khác Boot 3 và dùng Spring Framework 7. Đọc Boot 4 reference/Javadocs để điều chỉnh imports và dependencies; **không coi các imports Boot 3 trong sample là bất biến**.

## 13. Những failure modes quan trọng phải đặt ở boundary phù hợp

### 13.1. HTTP statuses và response body

Không chỉ test 200. Một provider có thể trả:

- 201/202 khi operation async hoặc accepted, 204 với body rỗng.
- 400 do request sai schema.
- 401/403 do credentials/scope.
- 404 với resource chưa tồn tại.
- 409 khi conflict/idempotency key trùng.
- 422 cho validation business, theo API contract.
- 429 với `Retry-After`.
- 500/502/503/504.
- 200 có JSON sai/missing required field, hoặc Content-Type không mong đợi.

**Đặt test ở tầng B** cho mapping status/body và error classification. Đặt ở **C** nếu vấn đề cần chứng minh là cách client xử lý response frame/headers/connection thực. Đặt ở **D/E** nếu muốn xác nhận provider thật phát status theo contract.

Đừng viết một mock luôn trả 200 rồi tin rằng adapter đã xử lý lỗi; những nhánh chưa được chạy có thể chứa bug.

### 13.2. Retry, backoff và idempotency

Giả sử adapter được bổ sung retry cho 503:

- Không chỉ assert sau cùng đã thành công; **đếm số HTTP attempts**.
- Kiểm tra provider trả 503 lần đầu, 200 lần sau.
- Không retry 400/401 nếu policy không cho phép.
- Kiểm tra exponential backoff/jitter ở mức test clock/scheduler khi có thể.
- Không thực hiện retry vô hạn.
- Với POST payment/reservation, retry cần **idempotency key** và kiểm tra duplicate side effects; không mặc định POST an toàn để gửi lại.
- Tránh dùng `Thread.sleep(...)` dài để kiểm tra backoff; tốt hơn dùng injectable policy/virtual scheduler khi phù hợp.
- Với real HTTP stub, có thể ghi request journal để kiểm tra attempts thực, nhất là khi retry nằm trong HTTP library/interceptor.

**Sample không thêm retry** nên một mã 503 gây lỗi một lần. Nếu test tự cấu hình “lần đầu 503, lần hai 200” nhưng production chưa có retry, test đó không nên được đánh dấu pass.

### 13.3. Timeout không giống lỗi 503

- **HTTP 503:** provider đã trả response với status.
- **Connect timeout:** client không thiết lập kết nối trong hạn.
- **Read/response timeout:** đã kết nối nhưng response quá chậm hoặc đứng.
- **Total timeout/deadline:** ngân sách tổng cho toàn operation/nhóm retries.
- **Connection reset/EOF:** connection đóng lỗi khi đang trao đổi.
- **Pool timeout:** không lấy được connection từ pool trong hạn.

Các loại này có exception/retry policy khác nhau. `withException(new IOException(...))` ở tầng B chỉ giúp kiểm tra **một nhánh xử lý IOException**; muốn chứng minh actual client timeout, cần server chậm/drop connection thật và cấu hình timeout của request factory/client thực ở tầng C.

Thực hiện test timeout với thời hạn bounded để tránh suite treo. Dùng riêng môi trường fault-injection; đừng mô phỏng timeout bằng cách gọi API thật có địa chỉ không đáng tin hoặc mạng production.

### 13.4. Authentication, API keys và token refresh

Mock ở port không kiểm tra auth. Tầng B có thể assert:

```java
server.expect(requestTo(
        "https://shipping.example.invalid/api/quotes/70000"))
        .andExpect(header(
                "Authorization",
                "Bearer synthetic-test-token"));
```

Đây là **snippet mở rộng**; mã adapter demo không gắn Authorization, nên **không copy vào chính sample rồi kỳ vọng pass**. Trong dự án thực, inject token provider/client interceptor/SSL config theo application architecture.

Các test nên dùng token giả và không dump Authorization header vào logs/recordings. Nếu token refresh dựa vào expiry/clock, test bằng injectable clock/token provider; nếu cần xác minh với OAuth sandbox, tách smoke test có secret management và giới hạn quota.

### 13.5. URL encoding, query parameters, Unicode

Nếu provider nhận tên địa điểm hoặc chuỗi tiếng Việt thay vì mã bưu chính số, test phải bao gồm:

- dấu cách và ký tự có dấu;
- `?`, `&`, `/`, `#` trong path/query inputs;
- UTF-8, percent encoding, form encoding;
- null/empty parameters;
- duplicate query keys, order semantics nếu provider đòi;
- base URL có prefix path;
- redirect và location header khi liên quan.

Ở tầng B, `MockRestServiceServer.requestTo(...)` có thể phát hiện URI sai. Tầng C giúp kiểm tra request-target thực được transport gửi. **Không tự concatenate untrusted text vào URL bằng string addition** nếu URI template/builder cung cấp encoding phù hợp; input có thể vô tình thay route hoặc query.

### 13.6. JSON schema, unknown fields và versioning

Một JSON stub viết tay có thể chỉ chứa happy-path response. Cần có:

- optional field absent vs explicit null;
- unknown/new field do provider thêm;
- enum mới hoặc deprecated;
- giá trị số lớn/decimal, timezone;
- lists empty/large, nested structure;
- malformed JSON và Content-Type sai;
- backward/forward compatibility theo contract đã công bố.

Tầng B kiểm tra parser/adapter với fixtures đó. Tầng D kiểm tra stub/schema **có phù hợp bản provider thực** không. Nếu team dùng OpenAPI, Pact hoặc Spring Cloud Contract, hãy version hóa contract, chạy provider verification và cảnh báo khi drift.

### 13.7. SSL/TLS, proxies và network policy

Muốn chứng minh TLS trust/mTLS/hostname validation, HTTP local plaintext của phần 10 **không đủ**. Cần HTTPS stub với chứng chỉ kiểm thử, truststore/cert chain đúng, client config production-like, có tests cho certificate mismatch/expired/wrong hostname khi phù hợp.

Proxy/VPN/firewall/DNS chỉ có thể kiểm tra ở tầng cấu hình/infrastructure liên quan. Đừng dùng `MockRestServiceServer` để tuyên bố đã kiểm tra proxy route hoặc “outbound internet policy” nếu factory mock không hề mở kết nối.

### 13.8. Observability và tracing

Một outbound adapter còn chịu trách nhiệm headers/tracing/metrics. Tầng B có thể assert request headers, tầng C có thể kiểm tra chúng ở socket-level; production observability cần xác minh context propagation, filter/interceptor order và span naming.

Tránh viết tests quá chặt theo internal header order hoặc auto-generated trace IDs. Nên assert cấu trúc và correlation linkage, không assert một request ID ngẫu nhiên bằng literal cố định.

## 14. Khi kết hợp inbound test với outbound dependency

Nếu một controller nhận POST checkout rồi gọi shipping provider, có hai nhóm câu hỏi:

1. **Inbound contract:** controller nhận request hợp lệ, trả đúng status/body, validation, filters/security.
2. **Outbound interaction:** ứng dụng gửi HTTP đúng, map lỗi và fallback phù hợp.

Các cách phối hợp:

| Cách | Controller thật? | Outbound adapter thật? | Có socket outbound? |
|---|---|---|---|
| `@WebMvcTest` + port mock | Có trong MVC slice | Không | Không |
| `@SpringBootTest(MOCK) + @AutoConfigureMockMvc` + port mock | Có full app context/MVC | Adapter thay bằng mock | Không |
| `@SpringBootTest(MOCK) + MockMvc + MockRestServiceServer` | Có | Có | Không (mock request factory) |
| `@SpringBootTest(RANDOM_PORT)` + WireMock/MockWebServer | Có real inbound server | Có | Có outbound localhost |
| Sandbox e2e | Có deployment tương ứng | Có | Có provider sandbox |

Mức càng sâu càng đắt. Để kiểm tra một controller chỉ chuyển `ShippingProviderException` thành 503 cho client, `@WebMvcTest` + mock domain port thường đủ. Để kiểm tra request tạo bởi adapter, phải giữ adapter thật và stub outbound thấp hơn.

**Đặc biệt:** `@AutoConfigureMockMvc` hoặc `WebTestClient.bindToController(...)` **chỉ thiết lập phía server nhận request**. Chúng không tự chặn `RestClient` gọi provider. Khi test inbound gọi ra ngoài, luôn xác định seam outbound rõ ràng.

### 14.1. Tránh mock hai lần rồi không còn đường HTTP thật

Phản mẫu:

- Mock `ShippingQuotePort` trong controller integration test.
- Lại mock `HttpShippingQuoteAdapter` trong một “HTTP client test”.
- Assert cuối cùng controller trả 200.

Không test nào chạy method thật của adapter. Bạn đã kiểm tra business/controller nhưng **chưa kiểm tra HTTP integration**. Cần ít nhất một `@RestClientTest` hoặc loopback test giữ adapter thật.

### 14.2. Giữ responsibility của mỗi lớp test

Tên test thể hiện boundary:

- `checkoutAddsShippingFeeFromPort()`: unit.
- `adapterSendsGetAndParsesQuote()`: client slice.
- `adapterUsesSocketAndMaps503()`: local HTTP integration.
- `consumerContractMatchesProviderSpecification()`: contract verification.
- `providerSandboxAcceptsConfiguredCredential()`: opt-in smoke.

Đặt tên `endToEndTest()` cho một method mock port là sai lệch về phạm vi bằng chứng.

## 15. Lỗi phổ biến khi giả lập outbound HTTP

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra và sửa |
|---|---|---|
| `@RestClientTest` cố gọi ra internet | Client dùng `RestClient.create()`/builder riêng, không đi qua mock-customized builder | Inject Boot-managed builder; kiểm tra client instance được test |
| `MockRestServiceServer` báo expected URL mismatch | Dùng relative URI với RestClient.Builder | Expect **full URI**, đối chiếu base URL/path/query |
| Test parse JSON pass nhưng app prod fail | JSON slice thiếu custom Jackson configuration | Import config production hoặc có full-context loopback test |
| Mock bean làm controller pass nhưng adapter sai path | Mock quá cao, adapter không được chạy | Bổ sung B/C test cho adapter thật |
| HTTP 503 không được xử lý đúng | Test chỉ có 200 hoặc catch sai loại exception | Thêm status cases, assert domain error/cause |
| Client timeout vẫn treo trong production | Request factory mock không dùng socket timeout thật | Test tầng C với delay/fault injection và timeout thực |
| Test 429 retry quá nhiều | Retry configured không giới hạn hoặc không dùng Retry-After | Stateful stub, assert number of requests/backoff |
| Một POST thanh toán bị gửi hai lần | Retry không dùng idempotency policy | Contract/transport tests cho idempotency key và retry |
| HTTP stub trả body nhưng không đúng media type | Header Content-Type sai, converter không chọn như mong | Stub explicit Content-Type; verify decoder behavior |
| Local stub port đã bị chiếm | Hardcode port | Bind `127.0.0.1:0` và inject dynamic property |
| Test full-context vẫn gọi production domain | Base URL override không có hiệu lực hoặc client build trước | @DynamicPropertySource, assert configured URL, network guard |
| Một test qua sau làm test khác fail | Mock server expectations chưa reset | `server.verify()` và `server.reset()` mỗi test |
| Multiple RestClient builders dùng sai mock server | Server chỉ gắn với một client/builder | Xác định builder/customizer tương ứng, tách tests |
| HTTP localhost pass nhưng staging TLS fail | Test chỉ plaintext loopback | HTTPS test với truststore/mTLS hoặc sandbox smoke |
| Sandbox test thỉnh thoảng fail | Quota/rate limit, external outage, shared test data | Tách opt-in job, retry policy rõ, monitoring/cleanup |
| Test phản hồi quá nhanh không phát hiện pool exhaustion | Không có concurrent connections/large payload | Controlled load/fault test ở tầng C/infrastructure |
| `@WebClientTest` có Mono nhưng request không chạy | Không subscribe Publisher | StepVerifier hoặc web client response subscription |
| `WebTestClient` test inbound pass nhưng outbound fail | Outbound provider không được stub/kiểm tra | Bổ sung port mock hoặc HTTP stub ở đúng tầng |
| Test kết thúc khi async request chưa hoàn thành | Không await terminal/future | Return composed Publisher/CompletableFuture và await có hạn |
| Fixture JSON cũ làm test luôn xanh | Stub không được provider verify | Consumer/provider contract và scheduled sandbox check |
| URL được nối bằng raw user input | Encode sai, route/query injection | Dùng URI builder/template, test ký tự biên |
| Auth token lộ vào CI artifacts | Record raw headers/response logs | Token giả, redaction, secret management |

### 15.1. Checklist debug theo thứ tự

1. **Đề bài test là gì?** Business logic, request construction, transport, provider contract hay deployment?
2. **Adapter thực sự được gọi không?** Kiểm tra mock bean, proxy, conditional wiring và bean selection.
3. **Client được tạo thế nào?** Boot-managed builder hay `create()`/`builder()` tạo thủ công?
4. **Base URL thực tế là gì?** Profiles, @Value/@ConfigurationProperties, @DynamicPropertySource, overrides.
5. **Mock server gắn với instance nào?** RestClient/RestTemplate builder, multiple clients.
6. **Kỳ vọng HTTP đủ sâu chưa?** Method, full URL, query, headers, body, count.
7. **Response stub có Content-Type/status đúng chưa?**
8. **Error branches?** 4xx/5xx, empty, invalid JSON, timeout, IO.
9. **Nếu WebClient:** Publisher có subscribe/verify terminal không?
10. **Nếu test cần socket:** đang dùng local HTTP stub hay chỉ MockRestServiceServer?
11. **Nếu provider đổi schema:** ai xác minh contract/fixture?
12. **Nếu flaky:** cổng cố định, shared mutable stub, context cache, parallel tests, external network, timeouts.
13. **Nếu security:** tokens giả, HTTPS/mTLS/proxy được test ở mức đúng và log không lộ secrets.
14. **Báo cáo:** phân loại lỗi đúng boundary thay vì gọi chung “HTTP test fail”.

## 16. Chạy ví dụ và cách đọc báo cáo

### 16.1. Linux/macOS

Chọn build tool của dự án:

```bash
# Gradle Wrapper:
./gradlew test --tests "com.example.outbound.CheckoutPriceServiceTest"
./gradlew test --tests "com.example.outbound.HttpShippingQuoteAdapterSliceTest"
./gradlew test --tests "com.example.outbound.HttpShippingQuoteAdapterLoopbackTest"

# Hoặc Maven Wrapper:
./mvnw -Dtest=CheckoutPriceServiceTest test
./mvnw -Dtest=HttpShippingQuoteAdapterSliceTest test
./mvnw -Dtest=HttpShippingQuoteAdapterLoopbackTest test
```

### 16.2. Windows PowerShell

```powershell
.\gradlew.bat test --tests "com.example.outbound.CheckoutPriceServiceTest"
.\gradlew.bat test --tests "com.example.outbound.HttpShippingQuoteAdapterSliceTest"
.\gradlew.bat test --tests "com.example.outbound.HttpShippingQuoteAdapterLoopbackTest"

# Nếu dự án dùng Maven:
.\mvnw.cmd "-Dtest=CheckoutPriceServiceTest" test
.\mvnw.cmd "-Dtest=HttpShippingQuoteAdapterSliceTest" test
.\mvnw.cmd "-Dtest=HttpShippingQuoteAdapterLoopbackTest" test
```

Dùng **một** build tool phù hợp với project. Với Gradle tasks up-to-date, nếu cần chạy lại để xác minh, có thể dùng test rerun option theo phiên bản Gradle đang dùng. Không khẳng định tests thực thi chỉ vì build log ghi `BUILD SUCCESSFUL`; kiểm tra JUnit report, số tests, failures/skipped.

### 16.3. Báo cáo kỳ vọng

| Class | Số @Test | Boundary | Có Spring context? | Có HTTP socket outbound? |
|---|---:|---|---|---|
| `CheckoutPriceServiceTest` | 3 | Port mock | Không | Không |
| `HttpShippingQuoteAdapterSliceTest` | 6 | Mock request factory | Slice | Không |
| `HttpShippingQuoteAdapterLoopbackTest` | 4 | Local HTTP server | Full non-web context | **Có** |
| **Tổng** | **13** | Ba mức | — | Chỉ 4 local tests |

Mã ví dụ không có lệnh in stdout ứng dụng cố định. Kết quả test runner được xác định bởi tool version và môi trường. **Bài chỉ mô tả kết quả mong đợi theo cấu hình**, không tuyên bố đã biên dịch/chạy tests trên project của bạn.

**Không truy cập provider ngoài:** domain `shipping.example.invalid` chỉ xuất hiện ở app config và client-slice expectation. Trong loopback tests, `shipping.base-url` được override thành IP localhost và cổng ngẫu nhiên. Các test unit không tạo RestClient.

### 16.4. Nếu live HTTP test không chạy trên CI

Kiểm tra:

- JDK 17 có module `jdk.httpserver` để sử dụng `com.sun.net.httpserver.HttpServer`. Trong một project **JPMS module-info.java**, có thể cần `requires jdk.httpserver;`.
- Runner cho phép bind loopback 127.0.0.1 và mở ephemeral port.
- Không có firewall/security policy chặn local network (một số sandbox CI hạn chế socket).
- `@DynamicPropertySource` được phát hiện trước khi adapter xây RestClient.
- Không có properties/profile khác override/khóa base URL.
- Test classes có thể chạy riêng mà không phụ thuộc startup order/context cache.
- Không có global parallel test settings khiến một shared server bị dừng sớm.
- Build test starter/version tương thích Spring Framework 6.1+.

Nếu môi trường CI cấm loopback sockets, **đừng mô tả tầng C như đã được kiểm chứng**; giữ tầng B trong CI đó và chạy transport test ở job cho phép network loopback.

## 17. Contract testing và sandbox: hai câu hỏi khác local stub

### 17.1. Khi stub đúng với test nhưng sai với provider

Bạn viết response fixture:

```json
{
  "service": "STANDARD",
  "feeCents": 25000
}
```

Provider triển khai version mới đổi `feeCents` thành `price.amountMinor`, hoặc yêu cầu header `X-Api-Version`. Tất cả tests mock nội bộ vẫn xanh nếu fixture không đổi.

Để phát hiện drift:

1. Xác định rõ contract/version của provider.
2. Có consumer contract test hoặc OpenAPI/schema validation.
3. Chạy provider verification phù hợp (nếu kiểm soát provider), hoặc sandbox smoke test theo lịch/hợp đồng với đối tác.
4. Tái tạo fixtures từ nguồn contract được phê duyệt, **không record trực tiếp production PII**.
5. Khi provider có breaking change, cập nhật adapter, contract, migrations và tests có chủ đích.

Pact/Spring Cloud Contract giúp tổ chức contract verification trong một số kiến trúc; chúng không tự bảo đảm provider bên thứ ba chạy verifier nếu bạn không có khả năng tích hợp với họ.

### 17.2. Khi nào dùng sandbox thật?

Dùng sandbox/test account khi cần:

- Xác nhận credentials và auth flows (OAuth token exchange, refresh, scope).
- Xác nhận base URL, DNS/TLS/cert và provider đang deploy contract cụ thể.
- Xác nhận API-specific validation rules hoặc headers mà docs không thể mô tả hết.
- Kiểm tra webhook/callback qua hạ tầng cho phép.
- Kiểm tra một số workflows end-to-end với test accounts.

Không đặt sandbox/production-like calls thành dependency của mọi unit test vì latency, quota, outages và dữ liệu shared. Dùng CI job riêng (scheduled/on demand/pre-release), timeout/budget/cleanup rõ ràng. Không gọi production provider trong tests mà không có phép và cấu hình an toàn.

### 17.3. Giữ contract tests độc lập với live provider

Một hợp đồng consumer-driven có giá trị khi provider verification **thật sự** được thực hiện. Nếu chỉ tạo Pact JSON nhưng không có verification bên provider hoặc thông tin tương đương, một phần nguy cơ drift vẫn còn.

Đối với third-party SaaS không hỗ trợ provider verification, phối hợp:

- schema/spec được version hóa;
- adapter tests với fixtures có nguồn gốc rõ ràng;
- sandbox smoke có credentials tách biệt;
- monitoring production request failures;
- compatibility policy và rollback/feature-flag khi API thay đổi.

## 18. Bài tập lựa chọn boundary và lời giải

### Bài A. Checkout total

Một service nhận quote rồi cộng phí vào subtotal. Bạn cần test subtotal âm không gọi nhà vận chuyển. Dùng MockRestServiceServer hay Mockito port?

**Đáp án:** Mockito ở `ShippingQuotePort` hoặc fake port. Đây là quy tắc nghiệp vụ **trước outbound boundary**. Assert lỗi và `verifyNoInteractions(port)`; không cần HTTP context/socket.

### Bài B. URL path bị đổi một ký tự

Developer sửa `"/api/quotes/{postalCode}"` thành `"/api/quote/{postalCode}"`. Unit test mock port vẫn pass. Boundary nào phát hiện?

**Đáp án:** client-slice `@RestClientTest + MockRestServiceServer.requestTo(full URI)` hoặc real HTTP stub có path matching. Port mock không chạy adapter nên không phát hiện.

### Bài C. 503 và 200

Provider trả 503; adapter phải ném domain exception. Bạn có cần gọi sandbox thật để kiểm tra mapping?

**Đáp án:** không. `MockRestServiceServer.withServiceUnavailable()` kiểm tra adapter logic đủ nhanh. Một local HTTP stub có thể bổ sung confidence về actual client response handling. Sandbox chỉ cần nếu muốn xác minh provider thật phát loại response đó theo contract.

### Bài D. Read timeout

Team dùng MockRestServiceServer.withException(IOException), test pass và nói “đã kiểm tra timeout của Apache HttpClient”. Nhận định có đúng không?

**Không.** Test chỉ fake I/O exception ở request factory. Timeout thật phụ thuộc actual client request factory, socket, network và config. Cần transport-level stub có delay/connection faults và deadline assertions.

### Bài E. WebClient Publisher không được subscribe

Một `@WebClientTest` tạo `Mono<Quote>` nhưng không dùng StepVerifier/subscribe. Test xanh. Nó chứng minh request đã gửi không?

**Không.** WebClient Publisher thường lazy; phải subscribe và kiểm tra terminal/value/error. Với outbound network, dùng real HTTP stub khi muốn kiểm tra transport.

### Bài F. @WebMvcTest với outbound provider

Một `@WebMvcTest(CheckoutController.class)` inject mock `ShippingQuotePort`. Controller response đúng. Nó có chứng minh `HttpShippingQuoteAdapter` gửi Authorization header không?

**Không.** Adapter bị loại khỏi request path. Muốn kiểm tra auth header outbound, giữ adapter thật và dùng client-mock/local stub; hoặc thêm test riêng cho auth configuration/interceptor.

### Bài G. Port cố định gây CI flaky

Hai test jobs cùng chạy WireMock ở cổng 8089. Một job fail vì port bận. Sửa thế nào?

**Đáp án:** dùng ephemeral port (port 0 hoặc dynamic port API của tool), inject URL bằng `@DynamicPropertySource`/test configuration, cô lập instance theo worker và quản lý lifecycle.

### Bài H. Provider JSON thay đổi

MockRestServiceServer luôn trả một JSON cũ và tất cả tests pass. Sandbox provider đã đổi schema. Công cụ/test nào còn thiếu?

**Đáp án:** contract/provider verification hoặc sandbox smoke có versioning. Mock nội bộ không tự biết provider deployment đã đổi. Cần cập nhật schema/fixtures có nguồn rõ và quy trình cảnh báo drift.

### Bài I. Retry payment POST

Một payment adapter có retry sau connection reset. Làm sao biết không bị double-charge?

**Đáp án:** cần contract/policy về idempotency key, test số attempts, kiểm tra hai requests cùng key có side effect tối đa một lần, và provider behavior trong sandbox/contract khi có thể. Không mặc định retry POST an toàn.

### Bài J. “Full SpringBootTest” có nghĩa full network test?

Một test dùng `@SpringBootTest` nhưng `@MockBean ShippingQuotePort`. Nó có kiểm tra outbound HTTP thật không?

**Không.** Full application context không bảo đảm mọi dependency được giữ thật. Nếu port bị mock, adapter không chạy; boundary vẫn ở domain port. Phải đọc dependency wiring, không suy từ tên annotation.

## 19. Checklist QA khi thêm một outbound HTTP integration

- [ ] Đã vẽ đường code từ business service tới provider endpoint.
- [ ] Có interface/port hoặc seam rõ để mock business dependency.
- [ ] Test business không phụ thuộc network khi không cần.
- [ ] Có ít nhất một test chạy **adapter thật** với request/response contract.
- [ ] Không tạo HTTP client bằng `RestClient.create()` nếu production phụ thuộc Boot builder customizers mà test không biết.
- [ ] Base URL inject qua config, không hardcode production URL trong method.
- [ ] Không đọc/gửi production secrets trong test fixtures/log.
- [ ] Client-slice expectation kiểm tra full URI đối với RestClient.Builder.
- [ ] HTTP method, path/query, headers và body được kiểm tra ở boundary thích hợp.
- [ ] JSON mapping test có cùng customizers/modules cần thiết như app.
- [ ] Có cases 2xx, 4xx, 5xx, empty/malformed data theo contract.
- [ ] Có error translation rõ giữa HTTP status và I/O failure.
- [ ] Không mặc định một fake IOException bằng MockRestServiceServer là actual network test.
- [ ] Nếu cần transport behavior, có local HTTP stub qua socket.
- [ ] Stub dùng ephemeral port; dynamic property được inject trước client build.
- [ ] Stub lifecycle sạch, không shared mutable state giữa tests song song.
- [ ] Nếu dùng retry, test attempts/backoff/circuit breaker/idempotency.
- [ ] Với WebClient, đã subscribe và verify Publisher terminal.
- [ ] Không nhầm MockMvc/WebTestClient inbound setup với outbound stub.
- [ ] Nếu yêu cầu TLS/proxy/DNS, test ở tầng thực sự có mạng/TLS/proxy.
- [ ] Contract fixtures có nguồn và được kiểm tra với provider khi có thể.
- [ ] Sandbox tests opt-in có timeout/quota/data cleanup, không phụ thuộc internet trong unit CI.
- [ ] Khi có nhiều HTTP clients, mỗi adapter được test theo instance/builder thực.
- [ ] Tests có thể chạy độc lập với order ngẫu nhiên; reset mock expectations.
- [ ] Không logging Authorization, PII hoặc raw provider payload chứa dữ liệu nhạy cảm.
- [ ] Có báo cáo rõ test nào là unit, client slice, loopback, contract hay sandbox.
- [ ] Với Spring Boot 3.0/3.1/4.x, đã kiểm tra đúng version-specific API/imports.
- [ ] Không coi “test xanh” là bằng chứng cho lớp chưa được giữ thật trong test.

## 20. Tổng kết

**Ranh giới giả lập đúng là ranh giới vừa loại bỏ phần không thuộc mục tiêu test, vừa giữ lại phần có thể mắc lỗi mà test phải phát hiện.**

- **Mock domain port** khi kiểm tra business rules, fallback và interaction ở mức nghiệp vụ.
- **`@RestClientTest + MockRestServiceServer`** khi kiểm tra adapter thật tạo HTTP request, parse response và map lỗi — nhưng không cần socket.
- **Local HTTP stub server** khi cần client/transport thật và cấu hình Spring đầy đủ, nhưng vẫn muốn cô lập provider ngoài.
- **Consumer/provider contract tests** khi cần bảo đảm request/response schema không lệch giữa hai phía.
- **Provider sandbox smoke test** khi cần kiểm tra deployment/network/auth thật, với chi phí và quyền truy cập được quản lý.

Dùng nhiều lớp tests có mục tiêu rõ, thay vì nâng mọi thứ lên full e2e hoặc mock mọi thứ rồi thiếu HTTP coverage. Trong Spring Boot, **lựa chọn đúng client builder/bean, điểm inject base URL và cách kích hoạt request** là yếu tố quyết định mock có thật sự nằm trên đường code sản xuất hay không.

Ví dụ Java 17+/Spring Boot 3.x dùng cùng `HttpShippingQuoteAdapter` ở cả client-slice và loopback tests; chỉ thay **boundary của provider**. Điều đó làm kết quả test có ý nghĩa hơn và giảm nguy cơ một mock vô tình kiểm tra đường code hoàn toàn khác ứng dụng thật.

## Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Testing Spring Boot Applications: Auto-configured REST Clients](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@RestClientTest`, RestClient.Builder, MockRestServiceServer, full URI expectations.
- [Spring Framework 6.2 — Testing Client Applications](https://docs.spring.io/spring-framework/reference/6.2/testing/spring-mvc-test-client.html): request-factory mock vs mock HTTP server và transport-level distinctions.
- [Spring Framework 6.2 — REST Clients](https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html): RestClient, RestTemplate, WebClient, response status/error handling và HTTP interfaces.
- [Spring Framework 6.2 — MockRestResponseCreators Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/web/client/response/MockRestResponseCreators.html): `withSuccess`, `withServiceUnavailable`, `withException(IOException)`.
- [Spring Boot 3.5 — Calling REST Services](https://docs.spring.io/spring-boot/3.5/reference/io/rest-client.html): Boot-managed RestClient.Builder, HTTP clients, customization.
- [Spring Framework — Dynamic Property Sources](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/dynamic-property-sources.html): `@DynamicPropertySource` và precedence.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html): inbound controller/application/server tests, khác outbound provider stubbing.
- [Spring Framework — Context Caching](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html): context reuse, dynamic property/lifecycle implications.
- [WireMock Documentation](https://wiremock.org/docs/): mock HTTP server, request matching, response faults và standalone options.
- [OkHttp MockWebServer](https://github.com/square/okhttp/tree/master/mockwebserver): local HTTP server for client testing (verify API by version).
- [Spring Cloud Contract](https://docs.spring.io/spring-cloud-contract/reference/): consumer/provider contracts and verifier workflows.
- [Pact Specification / Pact JVM](https://docs.pact.io/): consumer-driven contract testing, provider verification.
