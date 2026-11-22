# Gắn mock server vào đúng client hoặc builder được ứng dụng dùng

Khi một service gọi sang hệ thống khác qua HTTP, test cần kiểm tra request mà client thực sự gửi đi và cách ứng dụng xử lý response nhận về. Spring Test cung cấp `MockRestServiceServer` cho `RestTemplate` và `RestClient`; với `WebClient`, có thể dùng một mock HTTP server chạy cục bộ như OkHttp `MockWebServer` hoặc WireMock.

Điểm quyết định là mock server phải được gắn vào đúng client hoặc builder mà component đang dùng. Nếu test tạo một client riêng để gắn mock server nhưng service lại dùng một client khác, request của service sẽ không đi qua mock đó. Test có thể thất bại vì không thấy request, hoặc vô tình gọi ra endpoint thật.

## 1. Xác định client mà component đang dùng

Spring có nhiều HTTP client với cơ chế gửi request khác nhau:

| HTTP client | Cơ chế gửi request | Công cụ test phù hợp |
|---|---|---|
| `RestTemplate` | `ClientHttpRequestFactory` đồng bộ | `MockRestServiceServer` gắn trực tiếp vào instance `RestTemplate` |
| `RestClient` | API fluent đồng bộ, dựa trên request factory | `MockRestServiceServer` gắn vào `RestClient.Builder` trước khi build client |
| `WebClient` | Reactive `ClientHttpConnector` | Mock HTTP server cục bộ như `MockWebServer` hoặc WireMock |

`MockRestServiceServer` thay thế tầng gửi request của `RestTemplate` hoặc `RestClient` để ghi nhận và trả response giả lập trong cùng tiến trình. Nó không mở cổng HTTP. `MockWebServer` và WireMock thì khởi động một HTTP server cục bộ trên cổng được cấp, nhờ đó client gửi request qua HTTP stack thực tế.

Đây là kiểm thử **outbound HTTP client**: ứng dụng của ta là phía gửi request đến dịch vụ khác. Với kiểm thử **inbound HTTP endpoint** mà ứng dụng nhận request, dùng `MockMvc` cho Spring MVC hoặc `WebTestClient` cho WebFlux. Hai mục tiêu này nằm ở hai phía khác nhau của kết nối.

## 2. Gắn MockRestServiceServer vào RestTemplate

Với `RestTemplate`, hãy tạo hoặc lấy đúng instance được component sử dụng rồi gắn mock server vào chính instance đó. Ví dụ:

```java
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

RestTemplate restTemplate = new RestTemplate();
MockRestServiceServer server = MockRestServiceServer
    .bindTo(restTemplate)
    .build();
```

Sau khi gắn, các request được gửi qua `restTemplate` này sẽ được mock server kiểm soát. Test khai báo request mong đợi và response giả lập:

```java
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;

import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

server.expect(requestTo("https://inventory.example/api/items/42"))
    .andExpect(method(HttpMethod.GET))
    .andExpect(header("X-Client", "catalog"))
    .andRespond(withSuccess(
        """
        {"id":"42","name":"Book"}
        """,
        MediaType.APPLICATION_JSON
    ));
```

Ví dụ component sử dụng chính `RestTemplate` này:

```java
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.RestTemplate;

record Item(String id, String name) {
}

class RestTemplateCatalogClient {

    private final RestTemplate restTemplate;

    RestTemplateCatalogClient(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    Item findById(String id) {
        HttpHeaders headers = new HttpHeaders();
        headers.set("X-Client", "catalog");

        ResponseEntity<Item> response = restTemplate.exchange(
            "https://inventory.example/api/items/{id}",
            HttpMethod.GET,
            new HttpEntity<>(headers),
            Item.class,
            id
        );
        return response.getBody();
    }
}
```

Sau khi gọi component đang dùng `restTemplate`, hãy xác nhận kết quả nghiệp vụ và xác minh tất cả expectation đã được đáp ứng:

```java
import static org.assertj.core.api.Assertions.assertThat;

RestTemplateCatalogClient catalogClient =
    new RestTemplateCatalogClient(restTemplate);
Item item = catalogClient.findById("42");

assertThat(item.id()).isEqualTo("42");
assertThat(item.name()).isEqualTo("Book");
server.verify();
```

`expect(...)` mô tả request mà test muốn nhận, `andExpect(...)` kiểm tra method, URL, header hoặc body của request, còn `andRespond(...)` cung cấp response giả lập. `verify()` xác nhận các request mong đợi đã thực sự được gửi.

Trong Spring Test, `MockRestServiceServer.createServer(restTemplate)` cũng là cách tạo server gắn với một `RestTemplate` có sẵn. Dù dùng `bindTo(...).build()` hay `createServer(...)`, điều quan trọng vẫn là gắn vào instance mà component đang dùng.

## 3. Gắn MockRestServiceServer vào RestClient.Builder

`RestClient` được giới thiệu trong Spring Framework 6.1. Khác với `RestTemplate`, API thường được tạo từ `RestClient.Builder`. Để mock các request của `RestClient`, hãy gắn `MockRestServiceServer` vào builder trước khi gọi `build()`:

```java
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

RestClient.Builder builder = RestClient.builder()
    .baseUrl("https://inventory.example");

MockRestServiceServer server = MockRestServiceServer
    .bindTo(builder)
    .build();

RestClient restClient = builder.build();
```

Thứ tự này quan trọng: mock server cấu hình request factory trên builder, sau đó `RestClient` được tạo từ chính builder đã được cấu hình. Nếu tạo `RestClient` từ một builder khác, request của client đó sẽ không được mock server này ghi nhận.

Ví dụ một component dùng `RestClient`:

```java
import org.springframework.web.client.RestClient;

class CatalogClient {

    private final RestClient restClient;

    CatalogClient(RestClient.Builder builder) {
        this.restClient = builder
            .baseUrl("https://inventory.example")
            .build();
    }

    Item findById(String id) {
        return restClient.get()
            .uri("/api/items/{id}", id)
            .header("X-Client", "catalog")
            .retrieve()
            .body(Item.class);
    }
}
```

Test tạo client từ builder đã bind mock server, truyền client đó vào component, rồi khai báo expectation:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

RestClient.Builder builder = RestClient.builder()
    .baseUrl("https://inventory.example");

MockRestServiceServer server = MockRestServiceServer
    .bindTo(builder)
    .build();

CatalogClient catalogClient = new CatalogClient(builder);

server.expect(requestTo("https://inventory.example/api/items/42"))
    .andExpect(method(HttpMethod.GET))
    .andExpect(header("X-Client", "catalog"))
    .andRespond(withSuccess(
        """{"id":"42","name":"Book"}""",
        MediaType.APPLICATION_JSON
    ));

Item item = catalogClient.findById("42");

assertThat(item.name()).isEqualTo("Book");
server.verify();
```

Ở đây component nhận chính `RestClient` được build từ builder đã bind. Đây là mối liên kết cần giữ trong test và trong cách tổ chức factory của ứng dụng.

## 4. Dùng Spring Boot test slice cho REST client

Trong Spring Boot, `@RestClientTest` có thể tạo test slice cho component gọi REST service. Annotation này giới hạn application context vào các thành phần liên quan đến REST client và cấu hình hạ tầng kiểm thử; các phiên bản Boot hỗ trợ sẽ cung cấp `MockRestServiceServer` để test khai báo expectation.

Ví dụ:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.client.RestClientTest;
import org.springframework.test.web.client.MockRestServiceServer;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

@RestClientTest(CatalogClient.class)
class CatalogClientTests {

    @Autowired
    private CatalogClient catalogClient;

    @Autowired
    private MockRestServiceServer server;

    @Test
    void readsItemFromInventoryService() {
        server.expect(requestTo("https://inventory.example/api/items/42"))
            .andRespond(withSuccess(
                """{"id":"42","name":"Book"}""",
                org.springframework.http.MediaType.APPLICATION_JSON
            ));

        Item item = catalogClient.findById("42");

        assertThat(item.name()).isEqualTo("Book");
        server.verify();
    }
}
```

`@RestClientTest` hữu ích khi component nhận `RestTemplateBuilder` hoặc `RestClient.Builder` từ cấu hình Spring Boot. Hãy để component dùng builder được Spring quản lý để test slice có thể gắn mock server vào đúng hạ tầng đó. Nếu component tự tạo `new RestTemplate()` hoặc `RestClient.builder()` bên trong, builder được test slice cấu hình có thể không phải builder mà component sử dụng; khi đó cần tái cấu trúc để inject factory/builder hoặc tạo mock server thủ công với đúng instance.

Khả năng tự cấu hình `RestClient` phụ thuộc phiên bản Spring Boot. Khi dùng phiên bản cũ hơn, kiểm tra tài liệu của phiên bản đang chạy; có thể cần tự tạo `RestClient.Builder`, bind mock server và truyền client vào component như ví dụ phía trên.

## 5. Vì sao WebClient cần mock HTTP server riêng?

`WebClient` dùng reactive `ClientHttpConnector` để gửi request. `MockRestServiceServer` được thiết kế để gắn với request factory của `RestTemplate` và `RestClient.Builder`; nó không phải adapter thay thế connector của `WebClient`.

Với `WebClient`, cách thực tế là khởi động một HTTP server cục bộ trên cổng ngẫu nhiên, đặt base URL của client trỏ tới server đó, xếp response giả lập vào hàng đợi, rồi kiểm tra request server đã nhận. `MockWebServer` của OkHttp là một lựa chọn phổ biến.

Thêm dependency test, chọn phiên bản tương thích với OkHttp mà dự án sử dụng:

```groovy
dependencies {
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
}
```

Ví dụ test một `WebClient`:

```java
import java.io.IOException;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class ReactiveCatalogClientTests {

    @Test
    void sendsRequestToInventoryAndReadsResponse() throws IOException, InterruptedException {
        MockWebServer server = new MockWebServer();
        server.start();

        try {
            server.enqueue(new MockResponse()
                .setResponseCode(200)
                .addHeader("Content-Type", "application/json")
                .setBody("""{"id":"42","name":"Book"}"""));

            WebClient webClient = WebClient.builder()
                .baseUrl(server.url("/").toString())
                .build();

            ReactiveCatalogClient catalogClient =
                new ReactiveCatalogClient(webClient);

            StepVerifier.create(catalogClient.findById("42"))
                .assertNext(item -> {
                    assertThat(item.id()).isEqualTo("42");
                    assertThat(item.name()).isEqualTo("Book");
                })
                .verifyComplete();

            RecordedRequest request = server.takeRequest(1, TimeUnit.SECONDS);
            assertThat(request).isNotNull();
            assertThat(request.getMethod()).isEqualTo("GET");
            assertThat(request.getPath()).isEqualTo("/api/items/42");
        }
        finally {
            server.shutdown();
        }
    }
}
```

Trong ví dụ, `ReactiveCatalogClient` là component ứng dụng đang dùng `WebClient`; test tạo `WebClient` với base URL của mock server rồi truyền đúng instance đó vào component. Sau khi publisher hoàn tất, test đọc `RecordedRequest` để kiểm tra method và path mà server thực sự nhận.

Ví dụ component:

```java
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

class ReactiveCatalogClient {

    private final WebClient webClient;

    ReactiveCatalogClient(WebClient webClient) {
        this.webClient = webClient;
    }

    Mono<Item> findById(String id) {
        return webClient.get()
            .uri("/api/items/{id}", id)
            .retrieve()
            .bodyToMono(Item.class);
    }
}
```

`MockWebServer` nhận request qua HTTP thật trên loopback interface, vì vậy nó kiểm tra được URL, method, header và body đã gửi. Tuy nhiên, test vẫn chạy trên server cục bộ của test process, không phụ thuộc dịch vụ bên ngoài.

## 6. Kiểm tra request body, header và lỗi response

Mock server nên xác nhận hợp đồng HTTP của client, không chỉ trả một response cố định. Với `MockRestServiceServer`, có thể thêm matcher cho header, body, query parameter và method:

```java
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;

server.expect(requestTo("https://payments.example/charges"))
    .andExpect(method(HttpMethod.POST))
    .andExpect(header("Authorization", "Bearer test-token"))
    .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
    .andExpect(content().json("""{"orderId":"ORD-42","amount":250000}"""))
    .andRespond(withSuccess("""{"chargeId":"CH-1"}""", MediaType.APPLICATION_JSON));
```

Các static matcher tương ứng nằm trong `MockRestRequestMatchers`, còn response creator nằm trong `MockRestResponseCreators`. Test có thể giả lập response thành công, lỗi HTTP hoặc response rỗng để xác nhận cách component xử lý.

Với `MockWebServer`, dùng `RecordedRequest` để kiểm tra dữ liệu đã nhận:

```java
RecordedRequest request = server.takeRequest(1, TimeUnit.SECONDS);
assertThat(request).isNotNull();
assertThat(request.getHeader("Authorization")).isEqualTo("Bearer test-token");
assertThat(request.getBody().readUtf8())
    .contains("\"orderId\":\"ORD-42\"");
```

Để kiểm tra lỗi, xếp một response có status 503 hoặc 404 và xác nhận exception hoặc kết quả lỗi mà client trả ra. Với `RestClient`, `retrieve()` thường ném `RestClientResponseException` cho status lỗi nếu không cấu hình status handler xử lý riêng. Với `WebClient`, `retrieve()` thường phát `WebClientResponseException` trong reactive publisher; dùng `StepVerifier` để xác nhận loại lỗi hoặc status.

## 7. Kiểm soát số lần gọi và thứ tự request

Một component có thể gọi dịch vụ một lần, gọi lại khi retry hoặc gửi nhiều request trong một thao tác. `MockRestServiceServer` cho phép khai báo số lần mong đợi bằng `ExpectedCount`:

```java
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import org.springframework.http.MediaType;
import org.springframework.test.web.client.ExpectedCount;

server.expect(ExpectedCount.once(), requestTo("https://inventory.example/api/items/42"))
    .andRespond(withSuccess("""{"id":"42"}""", MediaType.APPLICATION_JSON));
```

Các lựa chọn thường dùng gồm `once()`, `never()`, `times(n)`, `min(n)` và `max(n)`. Dùng số lần mong đợi để phát hiện gọi thừa, gọi thiếu hoặc retry không đúng chính sách.

Theo mặc định, expectation của `MockRestServiceServer` được xác minh theo thứ tự khai báo. Nếu các request độc lập và thứ tự không thuộc hợp đồng cần kiểm tra, builder có thể được cấu hình `ignoreExpectOrder(true)`. Chỉ bỏ kiểm tra thứ tự khi ứng dụng thực sự không phụ thuộc vào thứ tự các lời gọi.

`MockWebServer` xếp response theo thứ tự request đến. Khi cần xác minh nhiều request, đọc từng `RecordedRequest` theo thứ tự hoặc dùng `takeRequest(timeout, unit)` để tránh chờ vô hạn. Với retry, xếp các response thành công/lỗi theo kịch bản và xác nhận tổng số request đã nhận.

## 8. Vòng đời mock server trong test

Mock server cần được thiết lập trước khi component gửi request và được xác minh sau khi thao tác hoàn tất:

```text
Tạo client / builder
        |
        v
Gắn mock server vào đúng client hoặc builder
        |
        v
Tạo component dùng client đó
        |
        v
Khai báo request expectation hoặc enqueue response
        |
        v
Gọi phương thức nghiệp vụ
        |
        v
Kiểm tra kết quả nghiệp vụ và request đã gửi
        |
        v
verify() / đọc RecordedRequest
        |
        v
Giải phóng mock server cục bộ nếu cần
```

Với `MockRestServiceServer`, gọi `verify()` sau khi component đã thực hiện request. Nếu tái sử dụng server trong nhiều test, reset expectation theo cơ chế của test setup để mỗi test có kịch bản độc lập. Tránh dùng chung một instance mutable giữa các test chạy song song.

Với `MockWebServer`, luôn dừng server trong `finally` hoặc lifecycle callback như `@AfterEach`. Không để server giữ cổng và thread sau khi test kết thúc. Dùng cổng ngẫu nhiên do `server.start()` cấp, thay vì hard-code một cổng dễ xung đột trên CI.

## 9. Chọn đúng công cụ và phạm vi

| Mục tiêu | Công cụ |
|---|---|
| Kiểm tra `RestTemplate` gửi request đúng | `MockRestServiceServer` bind vào đúng `RestTemplate` |
| Kiểm tra `RestClient` gửi request đúng | `MockRestServiceServer` bind vào `RestClient.Builder` trước `build()` |
| Kiểm tra `WebClient` gửi HTTP request thực tế | `MockWebServer` hoặc WireMock với base URL trỏ đến server cục bộ |
| Kiểm tra controller Spring MVC nhận request | `MockMvc` |
| Kiểm tra controller WebFlux nhận request | `WebTestClient` |
| Kiểm tra toàn bộ tích hợp qua server ứng dụng đang chạy | HTTP client gọi server thật trong integration test |

Không dùng `MockMvc` hoặc `WebTestClient.bindToController(...)` để khẳng định component đã gọi đúng một dịch vụ ngoài. Những công cụ đó kiểm tra phía server nhận request. Ngược lại, `MockRestServiceServer` và `MockWebServer` kiểm tra phía client của ứng dụng phát request ra ngoài.

## 10. Lỗi thường gặp khi gắn mock server

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| `MockRestServiceServer.verify()` báo thiếu request | Component chưa được gọi, URI/method không khớp hoặc component đang dùng client khác instance đã bind |
| Test vẫn gọi ra endpoint thật | Mock server được gắn vào `RestTemplate`/builder khác; kiểm tra nơi tạo và inject client |
| `RestClient` không đi qua mock server | Client được build trước khi bind hoặc được tạo từ builder khác |
| `MockRestServiceServer` không hỗ trợ `WebClient` | `WebClient` dùng `ClientHttpConnector`; dùng mock HTTP server như `MockWebServer` hoặc WireMock |
| `WebClient` không gọi được mock server | Base URL chưa trỏ tới `server.url(...)`, server chưa start hoặc đã shutdown trước request |
| Request matcher thất bại | Kiểm tra URL đầy đủ, query string, method, header và body thực tế |
| Test retry gửi số request khác mong đợi | Xác nhận chính sách retry, backoff và response lỗi đã xếp vào mock server |
| Test treo khi đọc request từ MockWebServer | Không có request được gửi hoặc đang chờ vô hạn; dùng `takeRequest(timeout, unit)` và kiểm tra luồng gọi |

Khi debug, hãy bắt đầu từ component đang gọi ra ngoài: xác định field hoặc constructor nhận HTTP client nào, client được tạo từ builder nào, rồi lần theo đúng instance đó đến nơi gắn mock server. Sau đó mới kiểm tra expectation, response và kết quả nghiệp vụ.

## 11. Quy trình thiết lập test outbound HTTP

1. Xác định component đang dùng `RestTemplate`, `RestClient` hay `WebClient`.
2. Với `RestTemplate`, gắn `MockRestServiceServer` vào đúng instance; với `RestClient`, bind vào builder trước khi build client.
3. Với `WebClient`, khởi động mock HTTP server cục bộ và tạo client với base URL của server.
4. Truyền đúng client đã được cấu hình vào component cần kiểm thử.
5. Khai báo request mong đợi hoặc enqueue response giả lập trước khi gọi component.
6. Gọi phương thức nghiệp vụ, kiểm tra kết quả trả về và xác minh method, URL, headers, body, số lần gọi.
7. Xác minh mock server và giải phóng tài nguyên trong lifecycle của test.

Một test outbound HTTP đáng tin cậy phải chứng minh component đã dùng đúng client được gắn mock server, gửi đúng request và xử lý response như mong đợi. Khi chọn công cụ theo loại client và giữ nguyên instance hoặc builder giữa test với component, test sẽ không bỏ sót request thật đi ra ngoài hoặc xác minh nhầm một client khác.
