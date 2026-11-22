# Kiểm thử WebClient với máy chủ HTTP giả có hành vi thực tế

## 1. Bối cảnh: mock phương thức chưa đủ để chứng minh HTTP client đúng

`WebClient` là HTTP client reactive của Spring WebFlux. Một lớp service có thể gọi API đối tác để lấy hàng tồn kho, gửi lệnh đặt giữ hàng, nhận mã lỗi hoặc stream các cập nhật. Logic Java đúng chưa bảo đảm HTTP exchange đúng: request có thể sai URI, thiếu header, serialize JSON không khớp hợp đồng, xử lý 404/503 không đúng, timeout không hoạt động hoặc không giải phóng body/connection.

Ví dụ một lớp gọi hệ thống kho:

~~~java
public Mono<Item> getItem(String sku) {
    return webClient.get()
        .uri("/v1/items/{sku}", sku)
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .bodyToMono(Item.class);
}
~~~

Nếu chỉ mock `WebClient` bằng Mockito ở cấp `get()`, `uri()`, `retrieve()` và `bodyToMono()`, test thường phải stub cả chuỗi fluent API phức tạp; nó **không thực sự tạo HTTP request**, không chạy connector, không encode/decode body và không quan sát trạng thái mạng.

Một giải pháp đáng tin hơn là tạo **máy chủ HTTP giả chạy thực sự trên loopback**:

- `MockWebServer` của OkHttp hoặc `WireMock` lắng nghe ở `127.0.0.1:port`.
- `WebClient` production được cấu hình gọi máy chủ giả này thay vì API Internet.
- Máy chủ giả trả các phản hồi HTTP đã xếp hàng hoặc stub theo request.
- Test kiểm tra HTTP method, path, query, headers và request body đã gửi.
- Có thể mô phỏng response delay, lỗi 4xx/5xx, chunked body, socket disconnect và các tình huống khác.

Đó là **client integration test với máy chủ giả**: bên client chạy codec, `ClientHttpConnector`, TCP I/O và logic response thật; bên remote server được kiểm soát để test nhanh và lặp lại được. Máy chủ giả không phải một bản sao đầy đủ của hệ thống đối tác.

Mục tiêu bài học:

1. Chọn đúng cấp độ kiểm thử WebClient.
2. Hiểu `MockWebServer.enqueue`, `takeRequest` và cách dùng cổng ngẫu nhiên.
3. Kiểm tra request thực gửi thay vì chỉ xác nhận method mock được gọi.
4. Test success, 404, 503, retry, timeout, no-content, response headers và NDJSON stream.
5. Viết ví dụ hoàn chỉnh Java 17, Spring Boot 3.5.7, OkHttp MockWebServer 4.12.0 và JUnit Jupiter.
6. Biết cách mở rộng sang WireMock, network fault, TLS, pooling, backpressure và CI.

## 2. Chọn lớp kiểm thử đúng mục tiêu

| Cách test | Có HTTP socket thật? | Kiểm tra được | Giới hạn |
| --- | --- | --- | --- |
| Mockito mock service/repository | Không | Business decisions và method call | Không kiểm tra encoding, status, transport |
| Mock `ExchangeFunction` | Không | WebClient request construction và custom filter theo boundary | Bỏ qua connector, wire-level semantics |
| `MockWebServer`/`WireMock` chạy loopback | Có | URI, headers, body, codec, status, timeout, lỗi transport | Remote server thật không tham gia |
| `WebTestClient.bindToController` | Không có external server | Inbound WebFlux controller/handler | Không thay test outbound WebClient |
| `WebTestClient.bindToServer` | Có | HTTP request đến server under test | Thường dùng test server-side API |
| Test với sandbox/test environment của đối tác | Có | Tích hợp end-to-end sát hệ thống thật | Chậm, khó tái lập, dữ liệu/credentials |

**Khuyến nghị:** với một service sử dụng WebClient gọi REST API, dùng MockWebServer/WireMock ở mức client-boundary; thêm unit test cho business logic phức tạp và một số contract/end-to-end test với sandbox thật khi cần.

Spring Framework chính thức khuyến nghị mock HTTP server như OkHttp MockWebServer hoặc WireMock cho WebClient testing vì nó cho phép dùng cùng HTTP client configuration như production và mô phỏng các tình huống network mà mock method không phát hiện được.

### 2.1. Sơ đồ kết nối

~~~text
JUnit / StepVerifier
        |
        v
WarehouseClient (real application code)
        |
        v
Spring WebClient
        |
        v
Reactor Netty ClientHttpConnector + codecs
        |
        v
localhost:random-port  <------ actual HTTP over TCP ------>
        |
        v
MockWebServer
        |
        +--> queued MockResponse 200 / 404 / 503
        +--> delayed response / chunked body / socket policy
        |
        +--> RecordedRequest to assert method/path/headers/body
~~~

Giá trị cốt lõi là kiểm tra **cả request gửi đi và phản hồi mà client nhận vào**. Test chỉ stub response rồi kiểm tra final DTO chưa đủ: ứng dụng có thể gọi sai đường dẫn hoặc header nhưng MockWebServer vẫn trả response xếp hàng.

## 3. Những thành phần chính của MockWebServer

### 3.1. Chọn phiên bản API rõ ràng

Ví dụ trong bài dùng **OkHttp MockWebServer 4.12.0**, package Java:

~~~java
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.RecordedRequest;
import okhttp3.mockwebserver.SocketPolicy;
~~~

Với OkHttp 5, artifact, package và builder API của MockWebServer có thể khác (ví dụ `mockwebserver3`). Không sao chép nguyên import và method từ 4.12.0 sang 5.x rồi mong biên dịch.

### 3.2. Vòng đời máy chủ giả

~~~java
MockWebServer server = new MockWebServer();
server.start();

try {
    String baseUrl = server.url("/").toString();
    WebClient client = WebClient.builder()
        .baseUrl(baseUrl)
        .build();

    // enqueue response; make WebClient request; inspect RecordedRequest.
} finally {
    server.shutdown();
}
~~~

`start()` mở HTTP listener thật; `shutdown()` đóng server và giải phóng tài nguyên. `server.url("/")` trả HTTP URL chứa host và **port thực tế**, nên không cần hardcode cổng 8080/9999 dễ va chạm với test chạy song song.

Cũng có thể dùng `@BeforeAll`/`@AfterAll` hoặc JUnit extension. Nếu Spring ApplicationContext cần base URL ngay khi khởi tạo, dùng `@DynamicPropertySource` với server đã khởi động trước khi property được lấy.

### 3.3. Xếp hàng response

~~~java
server.enqueue(new MockResponse()
    .setResponseCode(200)
    .addHeader("Content-Type", "application/json")
    .setBody("""
        {"sku":"SKU-7","name":"Keyboard","stock":12}
        """));
~~~

Mỗi HTTP request được server xử lý sẽ lấy response tiếp theo trong hàng đợi. Điều này rất phù hợp khi test retry hoặc workflow có thứ tự:

~~~java
server.enqueue(new MockResponse().setResponseCode(503));
server.enqueue(new MockResponse().setResponseCode(200)
    .addHeader("Content-Type", "application/json")
    .setBody("..."));
~~~

**Quan trọng:** cơ chế queue không tự khớp path. Một request tới sai URI vẫn có thể lấy response 200 đầu tiên. Do đó luôn kiểm tra `RecordedRequest` sau đó, hoặc dùng `Dispatcher`/WireMock stubs nếu muốn phản hồi phụ thuộc method/path/header.

### 3.4. Ghi nhận HTTP request thật

~~~java
RecordedRequest request = server.takeRequest(
    2, TimeUnit.SECONDS
);

assertNotNull(request);
assertEquals("GET", request.getMethod());
assertEquals("/v1/items/SKU-7", request.getPath());
assertEquals("application/json", request.getHeader("Accept"));
~~~

Đối với POST, đọc request body bằng:

~~~java
String json = request.getBody().readUtf8();
assertTrue(json.contains("\"sku\":\"SKU-7\""));
~~~

`takeRequest(timeout, unit)` trả null nếu không có request trong thời gian chờ. Dùng timeout hữu hạn để tránh test treo vĩnh viễn khi code không subscribe hoặc gọi sai điều kiện.

### 3.5. HTTP status, headers, body là ba tín hiệu độc lập

HTTP response có:

- Status line (200, 204, 400, 404, 429, 503...).
- Response headers như `Content-Type`, `ETag` và `Retry-After`.
- Body, có thể rỗng, JSON, NDJSON, SSE, HTML hoặc chunked bytes.

`WebClient.retrieve()` mặc định biến 4xx/5xx thành `WebClientResponseException`, và các subclass cho một số mã phổ biến. Không tự giả định 404 trả `Mono.empty()`. Nếu muốn fallback, code client phải chủ động map status/error sang giá trị phù hợp.

## 4. Các nhóm test bắt buộc cho WebClient

### 4.1. Request contract

Với mỗi operation quan trọng, cần kiểm tra:

- Method: GET/POST/PATCH/DELETE.
- Path và percent-encoding.
- Query parameters và giá trị được encode.
- `Accept`, `Content-Type`, authorization/correlation headers.
- JSON field names, null handling và data type.
- Response DTO hoặc `ResponseEntity`.

Tránh chỉ kiểm tra output. Một mock server queue có thể trả JSON đúng cho request tới **path sai**.

### 4.2. Success với JSON

Khi server trả 200 và body JSON, test nên chứng minh WebClient decode thành DTO dự kiến. Với Java `record` và Jackson (có trong starter WebFlux phù hợp), các field `sku`, `name` và `stock` được map theo tên.

### 4.3. 204 No Content

~~~java
server.enqueue(new MockResponse().setResponseCode(204));
~~~

`bodyToMono(Item.class)` không tạo `Item` khi body rỗng; luồng có thể complete mà không phát item. `StepVerifier.verifyComplete()` thể hiện sự khác nhau giữa 204 success và 404 error.

### 4.4. 4xx và 5xx

Với `retrieve()`, 404 có thể phát `WebClientResponseException.NotFound`; 503 có thể phát `WebClientResponseException.ServiceUnavailable`.

Test hai nhóm riêng:

- 404 hợp lệ về mặt giao thức nhưng tài nguyên không tồn tại: trả lỗi hoặc fallback do nghiệp vụ quyết định.
- 503 thường là lỗi transient có thể retry theo policy.
- 400/401/403 không nên bị retry mù quáng.
- 429 có thể yêu cầu theo `Retry-After` hoặc rate limiting policy.

### 4.5. Retry có giới hạn và idempotency

~~~java
return client.get()
    .uri("/v1/items/{sku}", sku)
    .retrieve()
    .bodyToMono(Item.class)
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(20))
            .jitter(0d)
            .filter(error ->
                error instanceof WebClientResponseException.ServiceUnavailable)
    );
~~~

`Retry.backoff(2,...)` nghĩa là **tối đa hai lần retry sau request đầu**, có thể tạo tổng ba HTTP requests. Dùng jitter=0 trong test để không phụ thuộc random backoff; production nên cân nhắc jitter để giảm retry storm.

Đặt retry phía sau `bodyToMono` làm nguồn được **subscribe lại** mỗi attempt. Với GET có tính idempotent thường phù hợp; với POST tạo tài nguyên, retry có thể gây duplicate side effects dù response đầu bị mất. Cần idempotency key hoặc protocol riêng trước khi retry write operation.

### 4.6. Response body bị trễ và timeout

MockWebServer có thể trì hoãn body:

~~~java
server.enqueue(new MockResponse()
    .setResponseCode(200)
    .addHeader("Content-Type", "application/json")
    .setBody("{\"sku\":\"slow\",\"name\":\"Slow\",\"stock\":1}")
    .setBodyDelay(700, TimeUnit.MILLISECONDS));
~~~

Nếu WebClient dùng:

~~~java
return getItem("slow")
    .timeout(Duration.ofMillis(150));
~~~

thì StepVerifier có thể quan sát `TimeoutException`. Đây là timeout ở **reactive operation** kể từ subscription; nó không đồng nghĩa socket connect timeout hay per-read-timeout của Reactor Netty.

### 4.7. NDJSON stream và chunked transfer

WebClient có thể decode stream với:

~~~java
Flux<Item> updates = webClient.get()
    .uri("/v1/updates")
    .accept(MediaType.APPLICATION_NDJSON)
    .retrieve()
    .bodyToFlux(Item.class);
~~~

MockWebServer trả nhiều JSON object cách nhau bằng newline, có header `Content-Type: application/x-ndjson`. Có thể dùng `setChunkedBody` để chia body thành nhiều HTTP chunks.

**HTTP chunk boundary không bằng JSON object boundary.** Client decoder phải chịu được object bị chia qua nhiều TCP reads/HTTP chunks; đừng giả định mỗi `DataBuffer` là một dòng JSON hoàn chỉnh.

### 4.8. Lỗi transport khác lỗi HTTP status

- 404/503 là response HTTP hợp lệ; client thường nhận `WebClientResponseException`.
- Connect refused, socket reset, premature close là lỗi transport; client có thể nhận `WebClientRequestException` hoặc lỗi liên quan connector.
- Timeout reactive pipeline có thể phát `TimeoutException`.

Không gộp tất cả vào “server trả 500”. Khi test transport, tránh assert message ngoại lệ Netty quá cụ thể vì phụ thuộc OS/connector. Chú ý Reactor Netty có thể tự retry một số failure trên request chưa được gửi đầy đủ; đừng luôn assert cứng một request duy nhất cho disconnect test.

## 5. Máy chủ HTTP giả có “hành vi thực tế” đến mức nào?

### 5.1. MockWebServer so với Mockito

MockWebServer mở HTTP listener thật, xử lý bytes HTTP, có socket lifecycle và ghi lại request. Do đó nó kiểm tra được encoding, decoder, body aggregation và một phần behavior của HTTP client.

Nhưng server không mô phỏng đầy đủ production:

- Không tự tái hiện load balancer, proxy, service mesh hoặc CDN.
- Không mặc định giả lập server business state nếu chỉ dùng `enqueue`.
- Không tự mô phỏng mọi đặc điểm TLS, HTTP/2, slow consumer hay NAT.
- Không mô phỏng hợp đồng data API nếu test tự viết sai JSON schema.
- Không thay contract test với đối tác hoặc sandbox test.

Cần coi nó là **controlled test double ở HTTP boundary**, không phải “remote thật”.

### 5.2. Điều chỉnh lỗi mạng

Các cơ chế có trong MockWebServer 4.x gồm:

~~~java
new MockResponse().setSocketPolicy(
    SocketPolicy.DISCONNECT_AT_START
);
~~~

Và:

~~~java
new MockResponse()
    .setResponseCode(200)
    .setBody("some bytes")
    .throttleBody(5, 100, TimeUnit.MILLISECONDS);
~~~

Hoặc:

~~~java
new MockResponse()
    .setResponseCode(200)
    .setBody("slow-body")
    .setHeadersDelay(200, TimeUnit.MILLISECONDS);
~~~

Sử dụng để thử:
- Connection bị ngắt trước khi trả response.
- Body đang stream thì connection bị cắt.
- Response trả cực chậm nhưng không hẳn mất kết nối.
- Header arrival delay, body delay hoặc bandwidth throttle.

Đây là **đoạn API minh họa**, không nằm trong project chạy đầy đủ ở mục 8. Với SocketPolicy, kết quả ngoại lệ và số request attempt có thể phụ thuộc connector/retry; viết test theo invariant đáng tin cậy, tránh flaky assertions.

### 5.3. Khi cần response theo request

`MockWebServer.enqueue` phù hợp cho chuỗi request biết trước. Nếu nhiều client request song song, response lấy theo thứ tự tới server có thể khác thứ tự logic mong đợi.

Khi đó dùng `Dispatcher` của MockWebServer hoặc WireMock stubs để match request theo path/method/header:

~~~java
server.setDispatcher(new Dispatcher() {
    @Override
    public MockResponse dispatch(RecordedRequest req) {
        if ("/health".equals(req.getPath())) {
            return new MockResponse()
                .setResponseCode(200)
                .setBody("ok");
        }
        return new MockResponse().setResponseCode(404);
    }
});
~~~

`Dispatcher` phù hợp khi muốn tạo stateful simulation hoặc nhiều route có phản hồi khác nhau. Không phụ thuộc cả queue và custom Dispatcher trong cùng test nếu không hiểu rõ thứ tự ưu tiên của server.

### 5.4. WireMock khi cần hợp đồng phong phú hơn

`WireMock` hỗ trợ HTTP stubs theo URL, method, header, body matcher, scenario state, response templating, faults, delays, request journal, record/playback. Nó phù hợp cho API có nhiều endpoint và kịch bản nhiều bước.

Ví dụ ý tưởng, không phải code thuộc project mẫu:

~~~java
stubFor(get(urlEqualTo("/v1/items/SKU-7"))
    .willReturn(okJson(
        "{\"sku\":\"SKU-7\",\"name\":\"Keyboard\",\"stock\":12}"
    )));
~~~

Đoạn trên giả định import static API của WireMock và setup instance/port riêng. Không trộn các ví dụ WireMock với package/import của MockWebServer.

### 5.5. HTTPS/TLS

MockWebServer có thể được cấu hình dùng SSL socket factory. Với WebClient, phải thiết lập truststore/certificate test phù hợp. **Không tắt certificate validation trong production** chỉ để test dễ hơn. Muốn mô phỏng mutual TLS, cần cấu hình certificate và client auth ở cả phía mock server lẫn HTTP connector.

### 5.6. Port và parallel tests

- Luôn dùng port động: `server.start()` không cố định cổng; lấy `server.url("/")`.
- Start/stop server theo test class hoặc test instance.
- Không để server hoặc queue tồn tại qua các test mà không kiểm soát trạng thái.
- Với các tests chạy song song, mỗi test/class cần server riêng hoặc dispatcher thread-safe.
- Không dùng Internet API thật trong unit/integration test CI thường xuyên; dữ liệu và rate-limit dễ thay đổi.
- Dùng timeout hữu hạn trong StepVerifier và `takeRequest`.

## 6. retrieve(), onStatus(), exchangeToMono() và giải phóng response body

### 6.1. retrieve() mặc định xử lý error status

~~~java
Mono<Item> item = webClient.get()
    .uri("/v1/items/{sku}", sku)
    .retrieve()
    .bodyToMono(Item.class);
~~~

`retrieve()` tiện nhất khi muốn decode body và dùng hành vi error default (>=400 thành `WebClientResponseException`). Khi cần ánh xạ lỗi theo domain:

~~~java
Mono<Item> item = webClient.get()
    .uri("/v1/items/{sku}", sku)
    .retrieve()
    .onStatus(
        status -> status.value() == 404,
        response -> Mono.error(new ItemNotFoundException(sku))
    )
    .bodyToMono(Item.class);
~~~

Đây là đoạn minh họa; `ItemNotFoundException` là class do ứng dụng tự định nghĩa. Nếu cần đọc error body để tạo exception, gọi `response.bodyToMono(String.class)` trước khi tạo exception phù hợp; tránh bỏ qua body/resource ownership.

### 6.2. exchangeToMono() khi cần xử lý status phức tạp

~~~java
Mono<Item> result = webClient.get()
    .uri("/v1/items/{sku}", sku)
    .exchangeToMono(response -> {
        if (response.statusCode().is2xxSuccessful()) {
            return response.bodyToMono(Item.class);
        }
        return response.createError();
    });
~~~

Trong Spring Framework 6.2, sau khi Publisher do `exchangeToMono` trả về hoàn tất, response body chưa được consume sẽ được kiểm tra và release để tránh rò rỉ resource. Nếu cần đọc body, phải làm việc đó **bên trong lambda**; không giữ `ClientResponse` để decode ở downstream sau khi response đã được release.

### 6.3. Không dùng exchange() cũ một cách tùy tiện

Các API cấp thấp đòi hỏi quản lý response body đúng cách. Nếu bỏ quên release/consume body, connection pooling có thể bị ảnh hưởng. Ưu tiên `retrieve()` hoặc `exchangeToMono/Flux()` và test các tình huống lỗi liên tiếp.

### 6.4. Test chỉ ra sự khác biệt

Cần kiểm tra rõ:

- 204 trả Mono.empty (không phải 404).
- 404 qua retrieve mặc định phát WebClientResponseException.
- Error mapping dùng onStatus có giữ được contract mà service mong đợi.
- Khi retry nhiều lần, response body của attempt lỗi được xử lý/release phù hợp trước khi request mới.
- Khi cancellation xảy ra, connection/resource của request bị hủy được connector xử lý đúng.

### 6.5. Log và quan sát

Không log Bearer token, cookie/session ID hoặc dữ liệu nhạy cảm trong RecordedRequest. Trong test có thể assert token đã được gửi, nhưng không đưa token thật vào fixture. Với production, tracing và HTTP metrics cần low-cardinality path template thay vì gắn tất cả ID ngẫu nhiên thành metric label.

## 7. Thiết kế test chống flaky và đúng ngữ nghĩa Reactor

### 7.1. Luôn tạo subscription từ test

~~~java
Mono<Item> result = warehouseClient.getItem("SKU-7");
~~~

Dòng trên chưa tạo HTTP traffic. Phải subscribe bằng StepVerifier:

~~~java
StepVerifier.create(result)
    .expectNext(new Item("SKU-7", "Keyboard", 12))
    .expectComplete()
    .verify(Duration.ofSeconds(3));
~~~

Không kiểm tra `server.takeRequest` trước khi có subscriber. Khi test method đã `verify` terminal signal, request thường đã được gửi, và có thể dùng RecordedRequest để kiểm chứng.

### 7.2. Test response trước, request sau

Một kịch bản thường theo thứ tự:

1. `server.enqueue(new MockResponse(...))`.
2. Tạo Publisher hoặc gọi service method.
3. `StepVerifier...verify(Duration)`.
4. `server.takeRequest(timeout, unit)`.
5. Assert method/path/query/header/body.

Nếu cần phối hợp request-response với concurrency phức tạp, dùng Dispatcher hoặc `CountDownLatch` có timeout và cleanup. Không lạm dụng `Thread.sleep` vì tạo test phụ thuộc timing.

### 7.3. Retry test tránh phụ thuộc wall-clock quá nhiều

Đặt backoff nhỏ (ví dụ 10–20ms) và jitter=0 cho unit/integration test. Không assert số millisecond chính xác; scheduler, CI load và OS thread scheduling có thể thay đổi.

Để kiểm tra retry, queue 503, 503, 200; sau success, đọc ba RecordedRequest và assert cả ba có cùng method/path. Không chỉ assert final DTO.

### 7.4. Tránh test phụ thuộc thứ tự

JUnit mặc định không bảo đảm thứ tự test method. Mỗi method nên tự enqueue đúng số response mà nó tiêu thụ, lấy đúng số RecordedRequest và không phụ thuộc request từ test trước. Một server dùng chung toàn class có thể chấp nhận được nếu test method chạy tuần tự và queue được dùng kỷ luật; khi chạy parallel, dùng server riêng hoặc dispatcher.

### 7.5. Timeout phải rõ loại

Ba loại timeout thường khác nhau:

| Timeout | Dùng khi | Ví dụ |
| --- | --- | --- |
| Connect timeout | Không kết nối được server trong thời gian cho phép | Reactor Netty `CONNECT_TIMEOUT_MILLIS` |
| Response timeout | Server không gửi response đủ nhanh ở tầng HTTP client | Reactor Netty `responseTimeout` |
| Reactor `timeout(Duration)` | Toàn reactive operation không phát tín hiệu mong đợi trước deadline | `mono.timeout(...)` |

`StepVerifier.verify(Duration)` là timeout của **bài kiểm thử** để ngăn test treo; nó không cấu hình timeout của WebClient production. Nên có cả giới hạn client operation và test harness.

### 7.6. Không dùng virtual time để giả lập network thật

`StepVerifier.withVirtualTime` hữu ích cho Reactor timers được điều khiển bởi VirtualTimeScheduler. Nhưng một mock HTTP server đang thực sự ngủ, delay socket hoặc gửi bytes bằng thread thật không tự tiến nhanh theo virtual scheduler. Đối với network delay, dùng timeout hữu hạn và real-time test; dùng virtual time riêng cho pure reactive retry/backoff logic khi không có network I/O thật.

## 8. Project chạy được: Spring Boot 3.5.7, Java 17, MockWebServer 4.12.0

Trong project này, `WarehouseClient` là service production thực sự dùng `WebClient.Builder` được Boot auto-configure. Tests dùng `@SpringBootTest(webEnvironment=NONE)` để tạo bean nhưng không khởi động HTTP server của ứng dụng; chỉ có MockWebServer ở loopback phục vụ outbound HTTP.

### 8.1. Cấu trúc thư mục

~~~text
webclient-mock-server-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/httpclient/
    │   │   ├── HttpClientDemoApplication.java
    │   │   └── WarehouseClient.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/example/httpclient/
            └── WarehouseClientTest.java
~~~

### 8.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>webclient-mock-server-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>com.squareup.okhttp3</groupId>
            <artifactId>mockwebserver</artifactId>
            <version>4.12.0</version>
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

Các phiên bản liên quan:
- Spring Boot 3.5.7 quản lý Spring Framework 6.2.x, Reactor, JUnit 5 và Netty.
- MockWebServer 4.12.0 được pin trực tiếp để giữ package `okhttp3.mockwebserver`.
- Maven tải dependencies từ repository được cấu hình khi chạy lần đầu; project cần kết nối đến Maven Central hoặc mirror nội bộ.
- `reactor-test` và `mockwebserver` là test-only; không đưa server giả vào production runtime.

### 8.3. application.properties

~~~properties
spring.main.web-application-type=none
partner.base-url=http://127.0.0.1:1
~~~

Giá trị `partner.base-url` mặc định chỉ là placeholder an toàn cho ví dụ, không phải endpoint production thật. Trong test, `@DynamicPropertySource` sẽ thay thế bằng URL của MockWebServer đã start. Trong deployment thực tế, cấu hình URL đối tác qua environment/configuration secret được kiểm soát.

### 8.4. HttpClientDemoApplication.java

~~~java
package example.httpclient;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpClientDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(HttpClientDemoApplication.class, args);
    }
}
~~~

### 8.5. WarehouseClient.java

~~~java
package example.httpclient;

import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

@Service
public class WarehouseClient {

    public record Item(String sku, String name, int stock) {}

    public record ReserveRequest(String sku, int count) {}

    public record Reservation(
        String reservationId,
        String status
    ) {}

    private final WebClient webClient;

    public WarehouseClient(
        WebClient.Builder builder,
        @Value("${partner.base-url}") String baseUrl
    ) {
        this.webClient = builder
            .baseUrl(baseUrl)
            .defaultHeader("X-Client-Id", "warehouse-demo")
            .build();
    }

    public Mono<Item> getItem(String sku) {
        return webClient.get()
            .uri("/v1/items/{sku}", sku)
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .bodyToMono(Item.class);
    }

    public Mono<Item> getItemOrDefault(String sku) {
        return getItem(sku)
            .onErrorResume(
                WebClientResponseException.NotFound.class,
                error -> Mono.just(
                    new Item(sku, "unknown", 0)
                )
            );
    }

    public Mono<ResponseEntity<Item>> getItemEntity(String sku) {
        return webClient.get()
            .uri("/v1/items/{sku}", sku)
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .toEntity(Item.class);
    }

    public Mono<Reservation> reserve(ReserveRequest request) {
        return webClient.post()
            .uri("/v1/reservations")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .bodyValue(request)
            .retrieve()
            .bodyToMono(Reservation.class);
    }

    public Mono<Item> getItemRetrying503(String sku) {
        return getItem(sku).retryWhen(
            Retry.backoff(2, Duration.ofMillis(20))
                .jitter(0d)
                .filter(error ->
                    error instanceof
                        WebClientResponseException.ServiceUnavailable)
        );
    }

    public Mono<Item> getItemWithDeadline(
        String sku, Duration timeout
    ) {
        return getItem(sku).timeout(timeout);
    }

    public Flux<Item> streamUpdates() {
        return webClient.get()
            .uri("/v1/updates")
            .accept(MediaType.APPLICATION_NDJSON)
            .retrieve()
            .bodyToFlux(Item.class);
    }
}
~~~

Các lựa chọn thiết kế:

- Inject `WebClient.Builder` của Spring Boot để giữ codec, connector và customization đúng như application thực tế.
- Chỉ khởi tạo `WebClient` một lần trong constructor; các method trả cold `Mono/Flux` để test/service caller tự subscribe.
- `getItem` dùng default error mapping của `retrieve()`, không giấu 4xx/5xx.
- `getItemOrDefault` chỉ fallback với `NotFound`; 503 vẫn được phát thành error.
- `getItemRetrying503` chỉ retry 503, tối đa 2 lần, không retry POST.
- `getItemWithDeadline` cấu hình timeout tổng cho một Publisher.
- `streamUpdates` decode NDJSON theo từng item.
- `getItemEntity` cho phép kiểm tra cả status/headers/body.

### 8.6. WarehouseClientTest.java — khởi động server và inject base URL

~~~java
package example.httpclient;

import static org.junit.jupiter.api.Assertions.*;

import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import reactor.test.StepVerifier;

@SpringBootTest(
    classes = HttpClientDemoApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class WarehouseClientTest {

    // Start before Spring resolves @DynamicPropertySource.
    private static final MockWebServer server = startServer();

    @Autowired
    WarehouseClient client;

    private static MockWebServer startServer() {
        MockWebServer instance = new MockWebServer();
        try {
            instance.start();
        } catch (IOException error) {
            throw new ExceptionInInitializerError(error);
        }
        return instance;
    }

    @DynamicPropertySource
    static void partnerBaseUrl(DynamicPropertyRegistry registry) {
        registry.add(
            "partner.base-url",
            () -> server.url("/").toString()
        );
    }

    @AfterAll
    static void shutdownServer() throws IOException {
        server.shutdown();
    }

    private static MockResponse json(int status, String body) {
        return new MockResponse()
            .setResponseCode(status)
            .addHeader("Content-Type", "application/json")
            .setBody(body);
    }

    private static RecordedRequest nextRequest()
            throws InterruptedException {
        RecordedRequest req = server.takeRequest(
            2, TimeUnit.SECONDS
        );
        assertNotNull(req, "Expected a real HTTP request");
        return req;
    }

    @Test
    void getItemDecodesJsonAndSendsCorrectRequest()
            throws InterruptedException {
        server.enqueue(json(200,
            "{\"sku\":\"SKU-7\",\"name\":\"Keyboard\",\"stock\":12}"));

        StepVerifier.create(client.getItem("SKU-7"))
            .expectNext(new WarehouseClient.Item(
                "SKU-7", "Keyboard", 12))
            .expectComplete()
            .verify(Duration.ofSeconds(4));

        RecordedRequest req = nextRequest();
        assertEquals("GET", req.getMethod());
        assertEquals("/v1/items/SKU-7", req.getPath());
        assertEquals("application/json", req.getHeader("Accept"));
        assertEquals(
            "warehouse-demo", req.getHeader("X-Client-Id"));
    }

    @Test
    void postReservationEncodesRequestBody()
            throws InterruptedException {
        server.enqueue(json(201,
            "{\"reservationId\":\"R-9\",\"status\":\"ACCEPTED\"}"));

        StepVerifier.create(client.reserve(
                new WarehouseClient.ReserveRequest("SKU-7", 2)))
            .expectNext(new WarehouseClient.Reservation(
                "R-9", "ACCEPTED"))
            .expectComplete()
            .verify(Duration.ofSeconds(4));

        RecordedRequest req = nextRequest();
        assertEquals("POST", req.getMethod());
        assertEquals("/v1/reservations", req.getPath());
        assertTrue(req.getHeader("Content-Type")
            .startsWith("application/json"));

        String requestJson = req.getBody().readUtf8();
        assertTrue(requestJson.contains("\"sku\":\"SKU-7\""));
        assertTrue(requestJson.contains("\"count\":2"));
    }

    @Test
    void missingItemProduces404Exception()
            throws InterruptedException {
        server.enqueue(json(404,
            "{\"error\":\"not found\"}"));

        StepVerifier.create(client.getItem("missing"))
            .expectError(WebClientResponseException.NotFound.class)
            .verify(Duration.ofSeconds(4));

        assertEquals(
            "/v1/items/missing",
            nextRequest().getPath()
        );
    }

    @Test
    void missingItemCanUseBusinessFallback()
            throws InterruptedException {
        server.enqueue(json(404,
            "{\"error\":\"not found\"}"));

        StepVerifier.create(client.getItemOrDefault("missing"))
            .expectNext(new WarehouseClient.Item(
                "missing", "unknown", 0))
            .expectComplete()
            .verify(Duration.ofSeconds(4));

        assertEquals(
            "/v1/items/missing",
            nextRequest().getPath()
        );
    }

    @Test
    void retry503TwiceThenSucceed()
            throws InterruptedException {
        server.enqueue(json(503,
            "{\"error\":\"temporary\"}"));
        server.enqueue(json(503,
            "{\"error\":\"temporary\"}"));
        server.enqueue(json(200,
            "{\"sku\":\"SKU-9\",\"name\":\"Mouse\",\"stock\":3}"));

        StepVerifier.create(client.getItemRetrying503("SKU-9"))
            .expectNext(new WarehouseClient.Item(
                "SKU-9", "Mouse", 3))
            .expectComplete()
            .verify(Duration.ofSeconds(6));

        for (int attempt = 0; attempt < 3; attempt++) {
            RecordedRequest req = nextRequest();
            assertEquals("GET", req.getMethod());
            assertEquals("/v1/items/SKU-9", req.getPath());
        }
    }

    @Test
    void badRequestDoesNotTrigger503Retry()
            throws InterruptedException {
        server.enqueue(json(400,
            "{\"error\":\"invalid sku\"}"));

        StepVerifier.create(client.getItemRetrying503("bad"))
            .expectError(WebClientResponseException.BadRequest.class)
            .verify(Duration.ofSeconds(4));

        assertEquals("/v1/items/bad", nextRequest().getPath());
        assertNull(server.takeRequest(200, TimeUnit.MILLISECONDS),
            "400 must not cause another attempt");
    }

    @Test
    void noContentCompletesWithoutItem()
            throws InterruptedException {
        server.enqueue(new MockResponse().setResponseCode(204));

        StepVerifier.create(client.getItem("empty"))
            .expectComplete()
            .verify(Duration.ofSeconds(4));

        assertEquals("/v1/items/empty", nextRequest().getPath());
    }

    @Test
    void responseEntityPreservesEtag()
            throws InterruptedException {
        server.enqueue(json(200,
            "{\"sku\":\"SKU-1\",\"name\":\"Cable\",\"stock\":4}")
            .addHeader("ETag", "\"v1\""));

        StepVerifier.create(client.getItemEntity("SKU-1"))
            .assertNext(entity -> {
                assertEquals(HttpStatus.OK, entity.getStatusCode());
                assertEquals("\"v1\"",
                    entity.getHeaders().getETag());
                assertEquals(new WarehouseClient.Item(
                    "SKU-1", "Cable", 4), entity.getBody());
            })
            .expectComplete()
            .verify(Duration.ofSeconds(4));

        assertEquals("/v1/items/SKU-1", nextRequest().getPath());
    }

    @Test
    void delayedBodyTriggersReactiveTimeout()
            throws InterruptedException {
        server.enqueue(json(200,
            "{\"sku\":\"slow\",\"name\":\"Delayed\",\"stock\":1}")
            .setBodyDelay(700, TimeUnit.MILLISECONDS));

        StepVerifier.create(client.getItemWithDeadline(
                "slow", Duration.ofMillis(150)))
            .expectError(TimeoutException.class)
            .verify(Duration.ofSeconds(4));

        assertEquals("/v1/items/slow", nextRequest().getPath());
    }

    @Test
    void ndjsonStreamingDecodesMultipleItems()
            throws InterruptedException {
        String ndjson =
            "{\"sku\":\"A\",\"name\":\"Alpha\",\"stock\":1}\n" +
            "{\"sku\":\"B\",\"name\":\"Beta\",\"stock\":2}\n";

        server.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "application/x-ndjson")
            .setChunkedBody(ndjson, 8));

        StepVerifier.create(client.streamUpdates())
            .expectNext(
                new WarehouseClient.Item("A", "Alpha", 1),
                new WarehouseClient.Item("B", "Beta", 2))
            .expectComplete()
            .verify(Duration.ofSeconds(4));

        RecordedRequest req = nextRequest();
        assertEquals("GET", req.getMethod());
        assertEquals("/v1/updates", req.getPath());
        assertEquals(
            MediaType.APPLICATION_NDJSON_VALUE,
            req.getHeader("Accept")
        );
    }
}
~~~

### 8.7. Giải thích thiết kế test

**Máy chủ giả được khởi động trước khi Spring tạo client.** Trường static `server` gọi `startServer()`; khi `@DynamicPropertySource` cấp `partner.base-url`, URL đã chứa cổng thật. `@SpringBootTest(webEnvironment=NONE)` tạo các bean service và WebClient.Builder, nhưng không chạy server HTTP inbound của ứng dụng.

**Mỗi test tự enqueue response và kiểm tra request đã nhận.** Giảm nguy cơ test pass giả vì queue còn dữ liệu cũ. Mặc định JUnit Jupiter không chạy test methods song song nếu không bật parallel execution; khi bật parallel, hãy chuyển sang server riêng per-test hoặc dispatcher có phân tuyến.

**Request body được assert theo field thay vì thứ tự JSON.** JSON object không bảo đảm thứ tự property trong mọi serializer; test kiểm tra nội dung quan trọng. Với payload phức tạp, dùng Jackson `ObjectMapper.readTree` để so sánh semantic JSON thay vì so sánh chuỗi byte nguyên bản.

**Retry test kiểm tra ba HTTP attempts thật.** Nếu chỉ assert final DTO thì retry có thể bị thay bằng fallback hoặc trả dữ liệu cache mà test không nhận ra.

**Timeout test làm trễ body sau khi headers đến.** Reactive `timeout` có thể kích hoạt trước khi body đủ để decode Item. Điều này khác với connect timeout hoặc response headers timeout ở connector.

**NDJSON test chia object qua nhiều chunks.** `setChunkedBody(ndjson,8)` không bảo đảm chunk trùng với ranh giới JSON object; WebClient decoder vẫn phải ghép và decode đúng.

### 8.8. Chạy project và kết quả mong đợi

Yêu cầu JDK 17+, Maven và quyền bind cổng loopback:

~~~bash
java -version
mvn test
~~~

Khi dependency được resolve và test pass, Maven thường kết thúc với:

~~~text
Tests run: 10, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Đây là **kết quả mong đợi**, không phải output đo được của lần chạy thật. Maven Surefire có thể thêm tên class, thời gian test và thông tin khác.

Project không cung cấp HTTP controller của chính ứng dụng: `spring.main.web-application-type=none`. Mục đích duy nhất là kiểm tra client outbound. Các test tự mở/đóng MockWebServer và không kết nối API Internet.

## 9. Mở rộng: stateful mock, JSON schema và protocol contract

### 9.1. Stateful behavior và response theo thứ tự

Giả sử flow đặt giữ hàng gồm:

1. POST `/v1/reservations` trả 202 Accepted với `reservationId`.
2. GET `/v1/reservations/{id}` lần đầu trả `PENDING`.
3. GET lần hai trả `ACCEPTED`.

Có thể enqueue responses theo thứ tự và assert tất cả RecordedRequest. Tuy nhiên, nếu client thực hiện request song song, response queue là FIFO theo thứ tự HTTP server nhận, không theo ý nghĩa business. Nên dùng Dispatcher nhận biết path/state hoặc WireMock scenarios.

### 9.2. Xác minh contract hai chiều

Một client HTTP integration test tốt có hai loại assertion:

**Outgoing contract**
- Method, path, query và percent encoding.
- Headers, auth metadata và content negotiation.
- Request JSON schema, field presence, datatype và serialization.

**Incoming contract**
- HTTP status mapping, including 204, 404, 429, 503.
- Charset, content type, gzip/transfer encoding khi có.
- DTO mapping, nullable fields, field mismatch và invalid JSON.
- Retry policy, timeout/cancel và response body release.
- Streaming item boundaries với SSE/NDJSON.

Đừng bịa JSON response “quá đẹp” nếu hệ thống đối tác có field thiếu, enum lạ hoặc 429 rate limit. Lấy contract chính thức của đối tác và thiết kế fixtures đại diện.

### 9.3. Test invalid JSON

~~~java
server.enqueue(new MockResponse()
    .setResponseCode(200)
    .addHeader("Content-Type", "application/json")
    .setBody("{not-valid-json"));
~~~

Đây là test mẫu riêng cho lỗi decode; client `bodyToMono(Item.class)` sẽ lỗi do decoder, không phải HTTP 500. Assertion nên kiểm tra loại lỗi Spring codec phù hợp ở version thực tế thay vì khẳng định mọi lỗi decode đều là WebClientResponseException.

### 9.4. Test request headers và authentication

Nếu client dùng bearer token/Basic auth, stub server ghi nhận header `Authorization` và test assert đúng giá trị fake. Không dùng token production trong test fixture; che token khi in failure logs và không ghi lại request full body chứa dữ liệu nhạy cảm.

### 9.5. Test conditional request, cache và ETag

Mock server có thể trả `ETag` cho GET và sau đó đáp 304 Not Modified nếu request mang `If-None-Match` tương ứng. WebClient không tự cung cấp HTTP caching như browser trong mọi cấu hình; nếu ứng dụng muốn cache, phải có policy/service/cache layer phù hợp. Test cả header outgoing và quyết định reuse data.

### 9.6. Test wire-level compression

Nếu production client gửi `Accept-Encoding` và server trả `Content-Encoding: gzip`, có thể tạo response body gzip thật và kiểm tra connector/decoder. Đừng chỉ gắn header gzip lên plaintext: đó là response giả sai protocol và có thể dẫn đến lỗi không đại diện.

### 9.7. SSE, cancellation và infinite streams

Với `text/event-stream`, dùng `bodyToFlux(ServerSentEvent<T>)` hoặc client DSL phù hợp. Mock server có thể giữ kết nối và gửi sự kiện định kỳ. Khi consumer dùng `take(n)` rồi cancel, cần quan sát behavior phù hợp; không giả định cancel đồng nghĩa server đã gửi complete. Test resource cleanup và connection reuse nếu đó là non-functional requirement.

### 9.8. Tránh nhầm backpressure network

Một `Flux<T>` trả từ `WebClient` có thể tôn trọng downstream demand trong pipeline. Nhưng khi remote server gửi bytes qua HTTP, network buffering và TCP flow control cũng tham gia. Không kết luận WebClient đã ép server tạm dừng đúng từng item chỉ vì StepVerifier dùng initial request 0. Đo throughput, memory, chunking và cancellation ở tầng phù hợp.

## 10. Test độ ổn định: lỗi và race thường xảy ra

### 10.1. Response bị chia thành nhiều TCP chunks

Thực tế network không giữ nguyên ranh giới message Java/JSON. Với NDJSON, một object có thể nằm trên nhiều chunks; bodyToFlux cần decode đúng. Test `setChunkedBody` là cách tốt để phát hiện decoder hoặc custom parser sai giả định.

### 10.2. Slow response và timeout

Dùng `setBodyDelay` hoặc `setHeadersDelay` với khoảng cách đủ lớn so với deadline để giảm flaky test (ví dụ 700ms vs 150ms). Không dùng chênh lệch 100ms vs 90ms vì CI scheduler có thể làm test lúc pass lúc fail.

### 10.3. Disconnect và retry ngoài dự kiến

Với `SocketPolicy.DISCONNECT_AT_START` hoặc `DISCONNECT_DURING_RESPONSE_BODY`, HTTP client có thể reconnect/retry tùy connector và request state. Không hardcode số request trong test socket failure nếu connector có auto retry. Xác minh response không thành công, error classification, safety và idempotency thay vì dựa vào exception message Netty/OS.

### 10.4. Connection pooling và leak

Tạo hàng loạt response mà body chưa được consume có thể làm pool cạn connection. Khi test nghiệp vụ không cần body, dùng `toBodilessEntity()` hoặc `exchangeToMono(response -> response.releaseBody().thenReturn(...))` theo API và contract phù hợp.

Đối với error path, bảo đảm error body được read/released. Test requests lặp lại với connection pool giới hạn để phát hiện leak, nhưng hãy dùng network timeouts để test không treo vô hạn.

### 10.5. Retry storm

Client retry 503 liên tục có thể làm tình hình outage xấu hơn. Khi test, assert số attempts; khi production, thêm jitter, deadline, circuit breaker/rate limit. Tôn trọng `Retry-After` nếu giao thức đối tác yêu cầu.

### 10.6. Server state giữa tests

Một MockWebServer dùng chung class ghi lại toàn bộ request trong queue. Mỗi test phải tiêu thụ đúng số RecordedRequest mà nó tạo ra. Nếu test nào timeout/cancel, các response còn bị giữ ở server queue có thể làm test sau nhận sai; cân nhắc server riêng cho từng test khi cần isolation tuyệt đối.

### 10.7. Embedded HTTP server không cần thiết

Không cần `@SpringBootTest(webEnvironment=RANDOM_PORT)` chỉ để thử outbound WebClient: bạn sẽ khởi động cả server inbound của ứng dụng, làm test chậm và tăng port/state cần quản lý. `NONE` vẫn cho phép load `WebClient.Builder` và service beans.

### 10.8. Mã 204, 304 và empty response

Cần phân biệt:
- 204: thành công, không có body.
- 304: thông điệp caching, không phải JSON payload.
- 404: `retrieve` mặc định phát error, không trả Mono.empty.
- 5xx: HTTP error, khác lỗi decode/connection.

Dùng status-specific assertions; không chuyển mọi empty body thành “không tìm thấy hàng”.

## 11. Checklist viết bài test WebClient

1. Có đang test **client outbound** thay vì nhầm WebTestClient server-side không?
2. Có dùng MockWebServer/WireMock mở HTTP socket thật không?
3. HTTP client/codec/connector có cùng cấu hình với production không?
4. Base URL có dùng random port và được inject trước khi tạo WebClient không?
5. Có test method, path, query, headers, request body thực gửi không?
6. Có assert response DTO và status/headers cần thiết không?
7. 204, 404, 400, 429 và 5xx có được phân biệt đúng không?
8. Retry có giới hạn và chỉ áp dụng cho lỗi thích hợp, operation idempotent không?
9. Có kiểm tra **số request thực sự** khi retry không?
10. Timeout có được cấu hình ở client chứ không chỉ ở StepVerifier không?
11. Có test delayed body hoặc disconnect nếu SLA yêu cầu không?
12. Có test chunked NDJSON/SSE khi client dùng streaming không?
13. Các test có timeout hữu hạn khi đợi request/verifier không?
14. Mỗi test có kiểm soát response queue, request queue và server lifecycle không?
15. Test có độc lập với Internet, credentials và dữ liệu thật không?
16. Có tránh giả định chunk boundary bằng item boundary không?
17. Error body có được consume/release để tránh leak không?
18. Tests chạy song song có server/dispatcher isolation không?
19. Có kiểm tra malformed response, unknown field và content-type mismatch không?
20. Có tách unit test, mock HTTP integration, contract test và end-to-end test không?

## 12. Bài tập tự kiểm tra

1. Vì sao mock `WebClient.get()` bằng Mockito chưa đủ? **Nó không kiểm tra HTTP socket, codecs, connector và wire semantics.**
2. `MockWebServer` có mở HTTP server thực sự không? **Có, trên loopback port.**
3. `server.enqueue` làm gì? **Đưa MockResponse vào queue cho request kế tiếp.**
4. `server.takeRequest` làm gì? **Lấy RecordedRequest thực nhận để assert method/path/header/body.**
5. Vì sao dùng `server.url("/")`? **Nó chứa địa chỉ và cổng thực tế của server.**
6. Queue response có tự match đúng URI không? **Không, phải assert RecordedRequest hoặc dùng Dispatcher/WireMock.**
7. `retrieve()` mặc định làm gì với 404/503? **Phát WebClientResponseException phù hợp.**
8. 204 với bodyToMono sẽ phát gì? **Hoàn tất rỗng khi không có body.**
9. `Retry.backoff(2,...)` nghĩa tối đa bao nhiêu lần gửi? **Ba: một lần đầu và hai retry nếu policy cho phép.**
10. Vì sao không retry POST bừa bãi? **Có nguy cơ duplicate side effects.**
11. `Mono.timeout` khác connect timeout như thế nào? **Nó giới hạn thời gian phản ứng của Publisher thay vì riêng giai đoạn TCP connect.**
12. `StepVerifier.verify(Duration)` có thay timeout production không? **Không, nó chỉ giới hạn thời gian test.**
13. Vì sao test phải subscribe Publisher? **WebClient reactive là lazy.**
14. `setBodyDelay` mô phỏng gì? **HTTP body đến trễ sau khi status/headers được gửi.**
15. `setChunkedBody` giúp phát hiện lỗi nào? **Giả định sai rằng một TCP/HTTP chunk là một JSON object.**
16. NDJSON có media type gì? **application/x-ndjson.**
17. `WebTestClient.bindToController` có thay mock server outbound không? **Không, nó chủ yếu test inbound WebFlux handler.**
18. `exchangeToMono` có thể release body chưa dùng khi nào? **Sau khi Publisher mà lambda trả về hoàn tất theo contract.**
19. HTTP 503 khác socket reset ra sao? **503 là response HTTP có status, reset là transport failure.**
20. Mock HTTP server có kiểm chứng API thật của đối tác luôn đúng không? **Không; vẫn cần contract/sandbox tests.**
21. Khi nhiều request chạy song song nên dùng gì? **Dispatcher/WireMock stubs hoặc server/test isolation.**
22. Vì sao không dùng token production trong mock fixture? **Bảo vệ secret và tránh rò rỉ trong logs.**

## 13. Tóm tắt và tài liệu tham khảo

- Muốn kiểm thử WebClient thực tế, nên dùng HTTP mock server chạy loopback thay vì mock từng method fluent API.
- MockWebServer/WireMock cho phép kiểm tra **outgoing request** và **incoming response** trên HTTP thật.
- `enqueue` tạo response, `takeRequest` ghi nhận request; phải kiểm tra path/header/body vì queue không tự match contract.
- `retrieve` mặc định chuyển 4xx/5xx thành WebClientResponseException; 204 thường hoàn tất rỗng.
- Test retry cần kiểm tra số HTTP attempts, không chỉ final DTO; không retry write operation không idempotent.
- `setBodyDelay`, `setHeadersDelay`, `setSocketPolicy` và `setChunkedBody` mô phỏng behavior network quan trọng.
- `StepVerifier` tạo subscription để kiểm tra reactive signals; `verify(Duration)` ngăn test treo nhưng không thay client timeout.
- Với NDJSON/SSE, không giả định mỗi chunk trùng với một item; cần kiểm tra streaming và cancellation.
- `exchangeToMono/Flux` và `retrieve` giúp xử lý body/resource đúng contract để tránh connection leaks.
- Test nên giữ cổng random, server lifecycle rõ ràng, response queue độc lập và không cần Internet.

**Tài liệu chính thức:**

1. [Spring Framework 6.2 — WebClient Testing](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-testing.html): khuyến nghị MockWebServer/WireMock làm HTTP mock server cho outbound WebClient.
2. [Spring Framework 6.2 — WebClient retrieve](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-retrieve.html): 4xx/5xx, onStatus, bodyToMono/Flux.
3. [Spring Framework 6.2 — WebClient exchange](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-exchange.html): exchangeToMono/Flux và lifecycle giải phóng body.
4. [Spring Framework 6.2 — WebClient Configuration](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-builder.html): connector, Reactor Netty, timeout và resources.
5. [Spring Boot 3.5 — Calling REST Services](https://docs.spring.io/spring-boot/3.5/reference/io/rest-client.html): WebClient.Builder auto-configuration/prototype.
6. [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): @SpringBootTest NONE vs RANDOM_PORT.
7. [OkHttp MockWebServer 4.x](https://square.github.io/okhttp/4.x/mockwebserver/): MockWebServer, MockResponse, RecordedRequest và SocketPolicy.
8. [WireMock Reference](https://wiremock.org/docs/): stub matching, scenarios, request journal, faults và delays.
9. [Project Reactor Reference — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): StepVerifier, demand, timeout và virtual time.
