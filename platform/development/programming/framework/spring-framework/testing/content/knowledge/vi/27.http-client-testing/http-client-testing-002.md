# MockRestServiceServer và cơ chế thay request factory

Khi một service dùng `RestTemplate` để gọi HTTP API bên ngoài, unit test thường cần xác nhận request được gửi đi và kiểm tra cách service xử lý response. `MockRestServiceServer` hỗ trợ việc đó mà không cần dựng HTTP server thật. Nó kết nối với `RestTemplate` bằng cách thay `ClientHttpRequestFactory` của instance này bằng một request factory giả lập.

Điểm quan trọng là `RestTemplate` vẫn thực hiện phần lớn luồng xử lý HTTP ở tầng client: tạo request, áp dụng interceptor, chuyển đổi body bằng message converter, xử lý status và chuyển response thành kiểu Java. Phần được thay thế là tầng tạo kết nối HTTP thực tế. Request được chuyển tới mock server để so khớp expectation và trả response do test định nghĩa.

## 1. MockRestServiceServer dùng để kiểm thử điều gì?

Giả sử `OrderService` gọi một inventory service bằng `RestTemplate`. Test cần xác nhận:

- Service gọi đúng URL và HTTP method.
- Request gửi đúng header, query parameter và body.
- Service chuyển đổi response thành object đúng.
- Service xử lý status lỗi hoặc response không mong muốn đúng cách.
- Request được gửi đúng số lần.

`MockRestServiceServer` cho phép khai báo trước request mong đợi và response sẽ trả về khi request khớp. Nó kiểm tra giao tiếp outbound ở ranh giới HTTP client mà không cần gọi hệ thống bên ngoài.

Ví dụ luồng xử lý:

```text
Service under test
       |
       v
  RestTemplate
       |
       v
ClientHttpRequestFactory
       |
       v
MockClientHttpRequestFactory
       |
       v
MockRestServiceServer
  - match request expectations
  - return configured response
       |
       v
RestTemplate response handling
       |
       v
Service receives Java object
```

## 2. Request factory là gì?

`ClientHttpRequestFactory` là abstraction mà `RestTemplate` dùng để tạo một `ClientHttpRequest`. Request này đại diện cho một lần gọi HTTP và có thể ghi method, URI, headers, body rồi thực thi để nhận `ClientHttpResponse`.

Ở môi trường chạy thật, request factory thường dựa trên một HTTP implementation như JDK `HttpURLConnection`, Apache HttpComponents hoặc một HTTP client khác. Request factory chịu trách nhiệm về phần transport, ví dụ mở kết nối, thiết lập TLS, timeout và gửi byte qua mạng.

Khi gắn `MockRestServiceServer`, test thay tầng transport này bằng mock request factory. Mock factory không mở socket hoặc gửi request ra mạng; nó tạo request giả, chuyển thông tin request cho expectation manager để tìm response đã khai báo.

| Thành phần | Khi chạy ứng dụng thật | Khi gắn MockRestServiceServer |
|---|---|---|
| Service | Gọi `RestTemplate` | Vẫn gọi cùng service và `RestTemplate` |
| URI, method, headers, body | Được tạo bởi RestTemplate | Vẫn được tạo bởi RestTemplate |
| Message converters | Serialize request và deserialize response | Vẫn tham gia serialize/deserialize |
| Client interceptors | Có thể sửa hoặc quan sát request/response | Vẫn nằm trong pipeline của RestTemplate |
| `ClientHttpRequestFactory` | Tạo request thực và kết nối mạng | Được thay bằng mock request factory |
| HTTP server bên ngoài | Nhận request thật | Không được gọi |

Nhờ vậy, test tập trung vào hành vi của service và cấu trúc request/response. Nó không xác nhận cấu hình transport thật như TLS handshake, connection pool hoặc timeout của HTTP client bên dưới.

## 3. Tạo MockRestServiceServer từ RestTemplate

Cách phổ biến nhất là dùng builder:

```java
RestTemplate restTemplate = new RestTemplate();

MockRestServiceServer server = MockRestServiceServer
        .bindTo(restTemplate)
        .build();
```

`bindTo(restTemplate)` trả về builder gắn mock server với instance `RestTemplate` cụ thể. Khi gọi `.build()`, Spring cài đặt mock request factory vào `RestTemplate` đó.

Có phương thức tiện ích tương đương:

```java
MockRestServiceServer server = MockRestServiceServer
        .createServer(restTemplate);
```

`createServer(...)` tạo server và gắn ngay vào `RestTemplate`. Dùng `bindTo(...).build()` khi muốn cấu hình expectation manager hoặc các tùy chọn builder; dùng `createServer(...)` khi cấu hình mặc định là đủ.

### Gắn server sau khi cấu hình RestTemplate

Có thể cấu hình các thành phần phía client trước khi bind mock server:

```java
RestTemplate restTemplate = new RestTemplate();
restTemplate.getInterceptors().add(new CorrelationIdInterceptor());
restTemplate.setErrorHandler(new DefaultResponseErrorHandler());

MockRestServiceServer server = MockRestServiceServer
        .bindTo(restTemplate)
        .build();
```

Mock server thay request factory, còn các thiết lập như interceptor, message converter và error handler thuộc pipeline của `RestTemplate`. Nên hoàn tất cấu hình `RestTemplate` trước khi bind và không gọi `setRequestFactory(...)` lần nữa sau đó, vì thao tác này có thể ghi đè mock factory mà server vừa cài đặt.

## 4. Ví dụ kiểm thử service gọi REST API

Giả sử service cần lấy thông tin đơn hàng từ một hệ thống inventory:

```java
public record InventoryOrder(String id, String status) {}

public class InventoryClient {

    private final RestTemplate restTemplate;
    private final String baseUrl;

    public InventoryClient(RestTemplate restTemplate, String baseUrl) {
        this.restTemplate = restTemplate;
        this.baseUrl = baseUrl;
    }

    public InventoryOrder findOrder(String id) {
        return restTemplate.getForObject(
                baseUrl + "/orders/{id}",
                InventoryOrder.class,
                id);
    }
}
```

Test tạo `RestTemplate`, bind mock server và khai báo response:

```java
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;
import static org.springframework.test.web.client.MockRestServiceServer.bindTo;

class InventoryClientTests {

    @Test
    void retrievesOrderFromInventoryService() {
        RestTemplate restTemplate = new RestTemplate();
        MockRestServiceServer server = bindTo(restTemplate).build();
        InventoryClient client = new InventoryClient(
                restTemplate, "https://inventory.example.test");

        server.expect(requestTo("https://inventory.example.test/orders/42"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        "{\"id\":\"42\",\"status\":\"READY\"}",
                        MediaType.APPLICATION_JSON));

        InventoryOrder order = client.findOrder("42");

        assertThat(order.id()).isEqualTo("42");
        assertThat(order.status()).isEqualTo("READY");
        server.verify();
    }
}
```

Khi `client.findOrder("42")` chạy, request được `RestTemplate` tạo ra rồi chuyển đến mock request factory. Mock server kiểm tra URI và method; nếu khớp, nó trả JSON đã khai báo. Message converter của RestTemplate đọc JSON thành `InventoryOrder`. Cuối cùng `verify()` xác nhận mọi expectation đã được thực hiện.

## 5. Kiểm tra request headers, query parameters và body

Mock server có nhiều request matcher trong package `org.springframework.test.web.client.match.MockRestRequestMatchers`.

### Kiểm tra headers

```java
server.expect(requestTo("https://inventory.example.test/orders/42"))
        .andExpect(method(HttpMethod.GET))
        .andExpect(header("X-Client-Name", "order-service"))
        .andRespond(withSuccess("{}", MediaType.APPLICATION_JSON));
```

Có thể kiểm tra header tồn tại, giá trị cụ thể hoặc các giá trị được chấp nhận. Điều này hữu ích để xác nhận interceptor đã thêm authentication token, correlation ID hoặc client metadata.

### Kiểm tra query parameter

```java
server.expect(requestTo("https://inventory.example.test/orders?status=READY&page=0"))
        .andExpect(queryParam("status", "READY"))
        .andExpect(queryParam("page", "0"))
        .andRespond(withSuccess("[]", MediaType.APPLICATION_JSON));
```

`requestTo(...)` kiểm tra URI hoàn chỉnh; `queryParam(...)` giúp diễn đạt riêng các query parameter cần xác nhận. Có thể kết hợp cả hai khi URI chính xác là một phần hợp đồng.

### Kiểm tra JSON request body

Với POST hoặc PUT, dùng `content()` để xác nhận body:

```java
server.expect(requestTo("https://inventory.example.test/orders"))
        .andExpect(method(HttpMethod.POST))
        .andExpect(content().contentType(MediaType.APPLICATION_JSON))
        .andExpect(content().json(
                "{\"customerId\":\"C-12\",\"quantity\":2}"))
        .andRespond(withSuccess(
                "{\"id\":\"order-42\",\"status\":\"CREATED\"}",
                MediaType.APPLICATION_JSON));
```

`content().json(...)` so sánh JSON theo cấu trúc, tránh phụ thuộc vào khoảng trắng hoặc thứ tự field. Nếu cần kiểm tra body text hoặc byte chính xác, có thể dùng các matcher `content().string(...)` hoặc `content().bytes(...)` tương ứng.

### Ví dụ service gửi POST

```java
public record CreateOrderRequest(String customerId, int quantity) {}

public InventoryOrder createOrder(CreateOrderRequest request) {
    return restTemplate.postForObject(
            baseUrl + "/orders", request, InventoryOrder.class);
}
```

Expectation cho phương thức này nên xác nhận POST, Content-Type, JSON body và response mà service cần deserialize. Như vậy test xác nhận cả request outbound lẫn kết quả mà service trả cho caller.

## 6. Khai báo response cho request mong đợi

Các response creator trong package `org.springframework.test.web.client.response.MockRestResponseCreators` giúp tạo response giả:

```java
withSuccess("{\"id\":\"42\"}", MediaType.APPLICATION_JSON);
withStatus(HttpStatus.NOT_FOUND);
withBadRequest();
withServerError();
withNoContent();
```

Ví dụ kiểm tra service xử lý 404:

```java
server.expect(requestTo("https://inventory.example.test/orders/missing"))
        .andRespond(withStatus(HttpStatus.NOT_FOUND));

assertThatThrownBy(() -> client.findOrder("missing"))
        .isInstanceOf(HttpClientErrorException.NotFound.class);

server.verify();
```

Mặc định `RestTemplate` dùng `DefaultResponseErrorHandler`, vì vậy status 4xx/5xx thường được chuyển thành exception trước khi `getForObject(...)` trả về. Nếu ứng dụng cấu hình error handler riêng, test phải dùng cùng cấu hình đó để xác nhận đúng hành vi.

## 7. Kiểm tra số lần gọi và thứ tự request

Expectation mặc định yêu cầu request xuất hiện đúng một lần. Có thể dùng `ExpectedCount` để quy định số lần:

```java
import static org.springframework.test.web.client.ExpectedCount.once;
import static org.springframework.test.web.client.ExpectedCount.times;
import static org.springframework.test.web.client.ExpectedCount.never;

server.expect(once(), requestTo("https://service.example.test/health"))
        .andRespond(withSuccess());

server.expect(times(2), requestTo("https://service.example.test/metrics"))
        .andRespond(withSuccess("ok", MediaType.TEXT_PLAIN));

server.expect(never(), requestTo("https://service.example.test/admin"))
        .andRespond(withSuccess());
```

Các kiểu thường dùng gồm `once()`, `manyTimes()`, `times(n)`, `min(n)`, `max(n)` và `never()`.

Mặc định `SimpleRequestExpectationManager` kiểm tra expectation theo thứ tự khai báo. Nếu request có thể xuất hiện theo thứ tự khác nhau và thứ tự không phải điều cần kiểm tra, có thể bật chế độ bỏ qua thứ tự:

```java
MockRestServiceServer server = MockRestServiceServer
        .bindTo(restTemplate)
        .ignoreExpectOrder(true)
        .build();
```

Khi bỏ qua thứ tự, mock server vẫn xác nhận request phù hợp với expectation và số lần gọi. Chỉ dùng chế độ này khi thứ tự outbound không thuộc hợp đồng cần kiểm tra; nếu thứ tự có ý nghĩa nghiệp vụ, hãy giữ chế độ mặc định.

## 8. Cơ chế thay thế request factory diễn ra thế nào?

Khi gọi:

```java
MockRestServiceServer server = MockRestServiceServer
        .bindTo(restTemplate)
        .build();
```

Spring tạo mock request factory gắn với expectation manager rồi cài factory đó vào `RestTemplate` qua cấu hình request factory. Kể từ thời điểm đó, các request phát ra từ chính instance `restTemplate` được chuyển đến mock factory thay vì request factory HTTP ban đầu.

Trình tự có thể mô tả như sau:

1. Test tạo và cấu hình `RestTemplate`.
2. Test gọi `MockRestServiceServer.bindTo(restTemplate).build()`.
3. Builder cài đặt mock `ClientHttpRequestFactory` vào `RestTemplate`.
4. Service gọi `RestTemplate` như bình thường.
5. Mock factory tạo request giả và chuyển request cho expectation manager.
6. Matcher xác nhận request; response creator tạo response giả.
7. `RestTemplate` xử lý response qua error handler và message converter hiện có.

Vì request factory bị thay thế, test không sử dụng HTTP transport thật. Các cấu hình thuộc transport ban đầu như TLS, connection pooling hoặc socket timeout không được kiểm chứng bởi test này. Muốn kiểm tra các chi tiết đó, cần integration test với HTTP client/server thực tế.

### Các cấu hình được giữ và bị thay thế

| Cấu hình của RestTemplate | Sau khi bind MockRestServiceServer |
|---|---|
| `ClientHttpRequestFactory` | Được thay bằng mock request factory |
| Message converters | Tiếp tục được dùng để ghi request và đọc response |
| `ResponseErrorHandler` | Tiếp tục xử lý status response |
| `ClientHttpRequestInterceptor` | Vẫn có thể tham gia pipeline và sửa/quan sát request |
| URI template handler | Tiếp tục tham gia mở rộng URI |
| TLS, socket timeout, connection pool của factory cũ | Không được thực thi qua mock factory |

Đừng gọi `restTemplate.setRequestFactory(...)` sau khi bind mock server, vì thao tác đó có thể thay factory giả bằng factory khác và khiến request không còn được mock server nhận.

## 9. Reset expectation và vòng đời test

`MockRestServiceServer` cung cấp `verify()` để xác nhận mọi expectation đã được đáp ứng. Nó cũng cung cấp `reset()` để xóa expectation và trạng thái tương ứng nhằm tái sử dụng server trong một kịch bản test khác.

```java
server.verify();
server.reset();

server.expect(requestTo("/next-call"))
        .andRespond(withSuccess("done"));
```

Thông thường, cách đơn giản nhất là tạo mới `RestTemplate` và `MockRestServiceServer` cho từng test. Việc này tránh expectation của test trước ảnh hưởng đến test sau và giúp mỗi test có một request factory mock riêng.

Nếu tái sử dụng server, phải gọi `reset()` đúng thời điểm và khai báo lại đầy đủ expectation. Không chia sẻ cùng một `RestTemplate` đã bind giữa các test chạy song song, vì các test có thể tranh chấp expectation và request factory state.

## 10. Dùng với Spring Boot và RestTemplateBuilder

Trong ứng dụng Spring Boot, `RestTemplateBuilder` thường được dùng để tạo `RestTemplate` có cấu hình chung như base URL, interceptor hoặc error handler. Test vẫn có thể tạo instance rồi bind mock server:

```java
RestTemplate restTemplate = restTemplateBuilder
        .rootUri("https://inventory.example.test")
        .build();

MockRestServiceServer server = MockRestServiceServer
        .bindTo(restTemplate)
        .build();
```

Khi dùng `@RestClientTest`, Spring Boot có thể tự cấu hình `MockRestServiceServer` và `RestTemplateBuilder` để test component REST client. Trong trường hợp đó, hãy sử dụng server được inject bởi test slice thay vì tự tạo một server thứ hai cho cùng `RestTemplate`.

Ví dụ dạng test slice:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;

@Component
public class InventoryClient {

    private final RestTemplate restTemplate;

    public InventoryClient(RestTemplateBuilder builder,
                           @Value("${inventory.base-url}") String baseUrl) {
        this.restTemplate = builder.rootUri(baseUrl).build();
    }

    public InventoryOrder findOrder(String id) {
        return restTemplate.getForObject(
                "/orders/{id}", InventoryOrder.class, id);
    }
}
```

Test slice khai báo base URL qua property:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.client.RestClientTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

@RestClientTest(value = InventoryClient.class,
        properties = "inventory.base-url=https://inventory.example.test")
class InventoryClientSliceTests {

    @Autowired
    private InventoryClient client;

    @Autowired
    private MockRestServiceServer server;

    @Test
    void readsOrder() {
        server.expect(requestTo("https://inventory.example.test/orders/42"))
                .andRespond(withSuccess(
                        "{\"id\":\"42\",\"status\":\"READY\"}",
                        MediaType.APPLICATION_JSON));

        InventoryOrder order = client.findOrder("42");

        assertThat(order.status()).isEqualTo("READY");
        server.verify();
    }
}
```

Boot test slice cung cấp context giới hạn cho REST client và các thành phần liên quan. Hãy cấu hình base URL hoặc root URI phù hợp với cách client xây dựng request trong dự án.

## 11. Khi nào MockRestServiceServer chưa đủ?

Mock server thay request factory nên không kiểm tra được toàn bộ hành vi của HTTP transport thực. Hãy cân nhắc mock HTTP server hoặc integration test khi cần xác nhận:

- TLS certificate, hostname verification hoặc mutual TLS.
- Connection pooling, connection reuse hoặc socket timeout.
- Redirect, compression hoặc hành vi của HTTP implementation cụ thể.
- Tương tác qua mạng giữa hai process hoặc cấu hình reverse proxy.
- Hành vi của một HTTP client library ở tầng transport.

`MockRestServiceServer` phù hợp để kiểm tra request/response contract và logic xử lý của code dùng `RestTemplate`. Nó không thay thế kiểm thử mạng thật.

## 12. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Request đi ra mạng thật | Mock server chưa bind vào đúng instance `RestTemplate` mà service đang dùng | Bind server vào đúng instance được inject vào service |
| Request không khớp expectation | Sai URL, method, query parameter, header hoặc body | Kiểm tra request thực tế và khai báo matcher cụ thể |
| `verify()` thất bại vì thiếu request | Code không gọi endpoint hoặc đường đi nghiệp vụ không chạy | Kiểm tra nhánh code và thời điểm gọi service |
| Có request ngoài dự kiến | Code gọi thêm endpoint không được khai báo | Thêm expectation nếu đó là hành vi đúng hoặc sửa logic phát sinh request ngoài ý muốn |
| Không deserialize được JSON | Thiếu message converter hoặc Content-Type không phù hợp | Trả media type đúng và cấu hình converter cần thiết |
| Response 4xx/5xx ném exception | `DefaultResponseErrorHandler` chuyển status thành exception | Assert exception hoặc cấu hình error handler đúng với ứng dụng |
| Mock server không nhận request sau khi bind | Một đoạn setup gọi `setRequestFactory(...)` sau đó | Cấu hình request factory trước khi bind mock server |
| Test song song ảnh hưởng nhau | Nhiều test dùng chung `RestTemplate` và expectation manager | Tạo client/server riêng cho từng test |

## 13. Ghi nhớ

`MockRestServiceServer` kiểm thử code outbound dùng `RestTemplate` bằng cách khai báo request expectation và response giả. `bindTo(restTemplate).build()` cài một mock `ClientHttpRequestFactory` vào đúng instance được truyền vào; `RestTemplate` vẫn thực hiện URI expansion, interceptor, message conversion và error handling, nhưng không mở kết nối HTTP thật. Khai báo request bằng matcher, trả response bằng response creator, rồi gọi `verify()` để xác nhận các expectation. Vì request factory thật bị thay thế, test này kiểm tra logic client và hợp đồng HTTP, còn TLS, timeout, connection pool và transport thật cần được xác nhận ở integration test.

