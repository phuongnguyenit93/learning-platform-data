# Phép đo HTTP phía máy khách và cách chọn đối tượng đã được gắn phép đo

Micrometer và Spring Boot có thể ghi nhận thời gian cùng kết quả của các HTTP call do ứng dụng gửi đi. Đây là **client-side HTTP metrics**: chúng đo thao tác gọi một dịch vụ bên ngoài từ góc nhìn của ứng dụng hiện tại. Để số liệu được ghi nhận, cần sử dụng HTTP client đã được Spring Boot cấu hình instrumentation, chẳng hạn `RestTemplate` được tạo từ `RestTemplateBuilder`, `WebClient` được tạo từ `WebClient.Builder` hoặc `RestClient` được tạo từ `RestClient.Builder` trên các phiên bản Spring Boot hỗ trợ.

Điểm dễ nhầm là inject một HTTP client bất kỳ không bảo đảm client đó đã được gắn observation. Một đối tượng được tạo bằng `new RestTemplate()`, `WebClient.create()` hoặc tự khởi tạo builder có thể bỏ qua các customizer mà Spring Boot dùng để tích hợp Micrometer. Hãy chọn đúng builder do application context cung cấp, tạo client từ builder đó, rồi inject bean client đã tạo vào service nghiệp vụ.

## 1. Client-side metrics đo điều gì?

HTTP client metrics ghi nhận mỗi lần ứng dụng gửi request đến server khác. Ví dụ, order-service gọi inventory-service để kiểm tra tồn kho; client-side timer đo thời gian từ lúc client thực hiện request đến khi nhận response hoặc kết thúc bằng lỗi theo instrumentation của HTTP client.

Metric thường gặp là `http.client.requests`. Đây thường là một `Timer`, có thể cung cấp số lần request, tổng thời lượng và thống kê phân phối nếu được cấu hình. Các tag chuẩn thường mô tả client đích, HTTP method, URI template, status, outcome và lỗi. Tên tag cụ thể có thể khác theo phiên bản Spring Boot, Spring Framework và convention đang dùng.

Client-side metrics giúp trả lời:

- Ứng dụng gọi dịch vụ nào nhiều nhất?
- Request GET hay POST có độ trễ cao?
- Dịch vụ đích trả về status lỗi nào?
- Tỷ lệ lỗi và thời gian phản hồi thay đổi ra sao?
- Một dependency bên ngoài có đang làm chậm luồng xử lý của ứng dụng không?

Các phép đo này mô tả thời gian của HTTP client call. Chúng không nhất thiết bao gồm toàn bộ thời gian nghiệp vụ của request đến ứng dụng, chẳng hạn thời gian xử lý trước khi gọi HTTP, các lần retry nằm ngoài instrumentation hoặc công việc sau khi nhận response.

## 2. Phân biệt HTTP server metrics và HTTP client metrics

Hai loại metrics nhìn từ hai phía khác nhau:

| Loại | Đo thao tác nào? | Ví dụ |
| --- | --- | --- |
| HTTP server metrics | Request đi vào ứng dụng hiện tại | Client gọi `order-service` và server đo request `/orders`. |
| HTTP client metrics | Request ứng dụng hiện tại gửi đến hệ thống khác | `order-service` gọi `inventory-service` và client đo request đó. |

HTTP server metrics thường dùng tên `http.server.requests`; HTTP client metrics thường dùng `http.client.requests`. Không dùng server metric để suy luận trực tiếp độ trễ của dependency mà ứng dụng gọi ra ngoài.

Ví dụ một request tạo đơn hàng có thể tạo ra:

1. Một server observation khi request đến `POST /orders`.
2. Một client observation khi order-service gọi inventory-service.
3. Một client observation khác khi order-service gọi payment-service.

Nếu request tổng thể chậm, so sánh server duration với từng client duration giúp xác định thời gian bị tiêu tốn ở tầng ứng dụng hay trong các dependency bên ngoài.

## 3. Spring Boot gắn instrumentation vào builder như thế nào?

Spring Boot cấu hình các builder HTTP trong application context và áp dụng customizer cần thiết để tích hợp observation. Khi ứng dụng có Actuator/Micrometer observation phù hợp, các client được tạo từ builder do Boot quản lý có thể ghi nhận HTTP client observation và đưa số liệu vào `MeterRegistry`.

Các builder quan trọng:

| HTTP client | Builder nên inject | Đối tượng dùng trong service |
| --- | --- | --- |
| `RestTemplate` | `RestTemplateBuilder` | `RestTemplate` |
| `WebClient` | `WebClient.Builder` | `WebClient` |
| `RestClient` | `RestClient.Builder` | `RestClient` |

`RestClient` được giới thiệu trong Spring Framework 6.1 và được Spring Boot hỗ trợ từ dòng Boot 3.2. Nếu dự án dùng Boot cũ hơn, lựa chọn này có thể chưa có; dùng `RestTemplate` hoặc `WebClient` theo phiên bản hiện tại.

Quy tắc thực hành: inject builder được Boot quản lý ở cấu hình bean; tạo client một lần; inject client đó vào service bằng constructor. Không tạo client mới cho từng request.

## 4. Dùng RestTemplateBuilder để tạo RestTemplate đã instrument

Ví dụ cấu hình client gọi inventory-service:

```java
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration
public class HttpClientConfiguration {
    @Bean
    RestTemplate inventoryRestTemplate(RestTemplateBuilder builder) {
        return builder
                .rootUri("http://inventory-service")
                .build();
    }
}
```

`RestTemplateBuilder` được inject từ Spring Boot. Builder này có thể mang theo customizer do Boot cấu hình, bao gồm tích hợp observation cho client metrics. Bean `inventoryRestTemplate` được tạo một lần và dùng lại.

Service nghiệp vụ nhận đúng bean đó:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

@Service
public class InventoryClient {
    private final RestTemplate restTemplate;

    public InventoryClient(
            @Qualifier("inventoryRestTemplate") RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    public InventoryItem findItem(String itemId) {
        return restTemplate.getForObject(
                "/api/items/{itemId}", InventoryItem.class, itemId);
    }
}
```

Khi `findItem()` thực hiện request, instrumentation trên `RestTemplate` có thể ghi nhận observation vào registry. Dùng URI template `/api/items/{itemId}` để metric ghi nhận route dạng ổn định thay vì mỗi item ID tạo một tag value riêng.

### 4.1. Tránh tạo RestTemplate bằng constructor trực tiếp

Đoạn code sau không đi qua builder do Spring Boot cấu hình:

```java
// Không nên dùng nếu cần các customizer/observation do Spring Boot cung cấp.
RestTemplate restTemplate = new RestTemplate();
```

Client vẫn gửi request bình thường, nhưng có thể thiếu instrumentation mà builder tự động cung cấp. Nếu buộc phải tự tạo client, cần cấu hình observation tương ứng một cách tường minh và kiểm thử rằng request thực sự tạo meter.

## 5. Dùng WebClient.Builder để tạo WebClient đã instrument

Với ứng dụng reactive hoặc cần non-blocking I/O, inject `WebClient.Builder` do Spring Boot cung cấp:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class ReactiveHttpClientConfiguration {
    @Bean
    WebClient inventoryWebClient(WebClient.Builder builder) {
        return builder
                .baseUrl("http://inventory-service")
                .build();
    }
}
```

Sau đó inject bean `WebClient` vào client adapter:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Component
public class ReactiveInventoryClient {
    private final WebClient webClient;

    public ReactiveInventoryClient(
            @Qualifier("inventoryWebClient") WebClient webClient) {
        this.webClient = webClient;
    }

    public Mono<InventoryItem> findItem(String itemId) {
        return webClient.get()
                .uri("/api/items/{itemId}", itemId)
                .retrieve()
                .bodyToMono(InventoryItem.class);
    }
}
```

`WebClient.Builder` do Boot quản lý có thể được cấu hình với observation registry và customizer cần thiết. Không thay bằng `WebClient.create()` nếu muốn giữ cấu hình tự động đó.

Với WebClient, request được thực thi khi reactive publisher được subscribe. Vì vậy, khi kiểm thử metrics, cần subscribe hoặc dùng cơ chế kiểm thử reactive như `StepVerifier`; chỉ tạo `Mono` mà không subscribe thì request có thể chưa được gửi và timer chưa được ghi nhận.

## 6. Dùng RestClient.Builder trên Spring Boot 3.2+

`RestClient` là API đồng bộ hiện đại trong Spring Framework 6.1. Trên Spring Boot 3.2 trở lên, có thể inject builder được Boot auto-configure:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
public class RestClientConfiguration {
    @Bean
    RestClient paymentRestClient(RestClient.Builder builder) {
        return builder
                .baseUrl("http://payment-service")
                .build();
    }
}
```

Sử dụng bean đã tạo:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class PaymentClient {
    private final RestClient restClient;

    public PaymentClient(@Qualifier("paymentRestClient") RestClient restClient) {
        this.restClient = restClient;
    }

    public PaymentResult authorize(PaymentCommand command) {
        return restClient.post()
                .uri("/api/payments/authorize")
                .body(command)
                .retrieve()
                .body(PaymentResult.class);
    }
}
```

Khi dùng builder từ context, các customizer observation của Boot có thể được áp dụng cho RestClient. Nếu dự án tự khởi tạo builder hoặc client, hãy xác minh observation registry đã được gắn.

## 7. Chọn đúng đối tượng đã được instrument trong ứng dụng

Một ứng dụng có thể có nhiều HTTP client: client cho inventory, payment, identity hoặc một đối tác bên ngoài. Hãy tạo từng bean client từ builder được Boot quản lý và đặt tên bean rõ ràng.

Ví dụ với hai `RestTemplate`:

```java
@Configuration
public class ExternalClientsConfiguration {
    @Bean
    RestTemplate inventoryRestTemplate(RestTemplateBuilder builder) {
        return builder.rootUri("http://inventory-service").build();
    }

    @Bean
    RestTemplate paymentRestTemplate(RestTemplateBuilder builder) {
        return builder.rootUri("http://payment-service").build();
    }
}
```

Service cần gọi inventory phải inject `@Qualifier("inventoryRestTemplate")`; service gọi payment inject `@Qualifier("paymentRestTemplate")`. Như vậy, mỗi client có cấu hình base URL, timeout, authentication và instrumentation rõ ràng.

Không inject `RestTemplateBuilder` vào mọi service rồi build client mới theo từng request. Builder thuộc lớp cấu hình; client đã build thuộc lớp sử dụng và nên được tái sử dụng.

### 7.1. Đừng nhầm builder đã instrument với client tự tạo

| Cách lấy client | Có thể nhận customizer của Spring Boot? | Khuyến nghị |
| --- | --- | --- |
| Inject `RestTemplateBuilder`, rồi `build()` | Có | Dùng cho RestTemplate trong Spring Boot. |
| Inject `WebClient.Builder`, rồi `build()` | Có | Dùng cho WebClient trong Spring Boot. |
| Inject `RestClient.Builder`, rồi `build()` | Có, trên Boot hỗ trợ RestClient | Dùng cho RestClient trên Boot 3.2+. |
| `new RestTemplate()` | Không qua Boot builder | Chỉ dùng khi tự cấu hình observation có chủ đích. |
| `WebClient.create()` | Không qua Boot builder | Tránh nếu dựa vào Boot auto instrumentation. |
| Tự `WebClient.builder()` hoặc `RestClient.builder()` | Không mặc nhiên nhận customizer của Boot | Phải cấu hình observation rõ ràng. |

Một client có thể vẫn hoạt động mà không có metrics. Vì vậy, việc gọi API thành công không chứng minh client đã được instrument.

## 8. ObservationRegistry và cấu hình client thủ công

Spring Framework sử dụng Observation API để tạo observation cho HTTP client. Spring Boot kết nối observation với Micrometer metrics khi có cấu hình phù hợp.

Nếu tạo client ngoài các builder do Boot quản lý, cần thiết lập observation registry hoặc instrumentation tương ứng theo API và phiên bản framework. Ví dụ với `RestTemplate` trong Spring Framework 6:

```java
import io.micrometer.observation.ObservationRegistry;
import org.springframework.web.client.RestTemplate;

RestTemplate restTemplate = new RestTemplate();
restTemplate.setObservationRegistry(observationRegistry);
```

Với `WebClient`, builder hỗ trợ cấu hình observation registry:

```java
WebClient webClient = WebClient.builder()
        .observationRegistry(observationRegistry)
        .baseUrl("http://inventory-service")
        .build();
```

Đối với `RestClient`, API builder cũng hỗ trợ cấu hình observation registry trong các phiên bản Spring Framework có hỗ trợ. Tên API và khả năng cấu hình cần được kiểm tra theo phiên bản cụ thể.

Gắn `ObservationRegistry` cho phép framework phát observation. Để có metric trong registry, ứng dụng còn cần observation handler/bridge phù hợp, thường được Spring Boot cấu hình khi Actuator và Micrometer được tích hợp. Nếu tự cấu hình hoàn toàn, hãy xác minh cả observation handler lẫn meter registry; chỉ gắn một registry rỗng không tự tạo metric backend.

## 9. Tên metric và các tag HTTP client

Metric client phổ biến là `http.client.requests`. Đây thường là timer, với các chiều phân loại có thể bao gồm:

| Tag/convention | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `clientName` hoặc `client.name` | Tên host/service đích theo convention | `inventory-service` |
| `method` | HTTP method | `GET`, `POST` |
| `uri` | URI template hoặc route đã chuẩn hóa | `/api/items/{itemId}` |
| `status` | HTTP response status | `200`, `404`, `503` |
| `outcome` | Nhóm kết quả | `SUCCESS`, `CLIENT_ERROR`, `SERVER_ERROR` |
| `error` | Loại lỗi nếu request thất bại | Tên class exception hoặc giá trị quy ước |

Tag key và tập tag có thể thay đổi theo phiên bản Spring Boot, Spring Framework và convention. Hãy xem `/actuator/metrics/http.client.requests` hoặc observation thực tế trong registry để xác nhận tag được xuất.

### 9.1. Dùng URI template để tránh cardinality cao

Đây là điểm đặc biệt quan trọng với client metrics. Nếu gọi URL đã chứa ID động và instrumentation không nhận được template, mỗi ID có thể trở thành một URI tag khác nhau.

Nên dùng template:

```java
restTemplate.getForObject(
        "http://inventory-service/api/items/{itemId}",
        InventoryItem.class,
        itemId);
```

Hoặc với WebClient:

```java
webClient.get()
        .uri("/api/items/{itemId}", itemId)
        .retrieve()
        .bodyToMono(InventoryItem.class);
```

Tránh tạo URL dạng `/api/items/` nối với từng item ID rồi dùng nó làm tag. Không đưa query string chứa search term, email hoặc token vào tag metric.

### 9.2. Client name phải ổn định

Client name nên đại diện cho dịch vụ đích hoặc host ổn định. Tránh dùng URL đầy đủ gồm query string, request ID hoặc tenant ID làm client name. Nếu nhiều endpoint thuộc cùng một dependency, nên thống nhất cách phân nhóm để dashboard không bị chia thành quá nhiều series.

## 10. Đọc client metrics qua Actuator

Khi Actuator metrics endpoint đã được expose, có thể kiểm tra meter:

```bash
curl.exe "http://localhost:8080/actuator/metrics/http.client.requests"
```

Response có thể chứa `COUNT`, `TOTAL_TIME`, `MAX` cùng `availableTags`. Dùng tag để lọc một client hoặc method cụ thể. Ví dụ minh họa:

```bash
curl.exe "http://localhost:8080/actuator/metrics/http.client.requests?tag=method:GET"
```

Nếu convention của phiên bản đang dùng có tag `clientName`, có thể lọc theo client:

```bash
curl.exe "http://localhost:8080/actuator/metrics/http.client.requests?tag=clientName:inventory-service"
```

Hãy dùng đúng tag key/value trong `availableTags`. Không giả định mọi phiên bản đều dùng chính xác `clientName`; một số convention hoặc lớp export có thể biểu diễn tên key khác.

Actuator endpoint trả snapshot hiện tại. Để xem xu hướng độ trễ, rate và percentile theo thời gian, hãy export đến Prometheus hoặc backend phù hợp.

## 11. Kiểm thử HTTP client có instrumentation

Kiểm thử cần xác minh cả request được gửi và meter được cập nhật. Với `RestTemplate`, có thể tạo test Spring context để nhận bean được build từ `RestTemplateBuilder`, dùng `MockRestServiceServer` giả lập server và đọc `MeterRegistry` sau request.

Ví dụ cấu trúc test:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import io.micrometer.core.instrument.MeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

@SpringBootTest
class InventoryClientMetricsTest {
    @Autowired
    RestTemplate inventoryRestTemplate;

    @Autowired
    MeterRegistry registry;

    @Test
    void recordsClientRequest() {
        MockRestServiceServer server =
                MockRestServiceServer.bindTo(inventoryRestTemplate).build();
        server.expect(requestTo("http://inventory-service/api/items/42"))
                .andRespond(withSuccess(
                        "{\"id\":\"42\"}",
                        org.springframework.http.MediaType.APPLICATION_JSON));

        inventoryRestTemplate.getForObject(
                "http://inventory-service/api/items/{itemId}",
                InventoryItem.class,
                "42");

        server.verify();
        assertThat(registry.find("http.client.requests").timers())
                .isNotEmpty();
    }
}
```

Test này minh họa cách kiểm tra client được inject từ context và meter client request được đăng ký. Tên bean, URL và response DTO cần khớp cấu hình của ứng dụng thực tế. Nếu registry hoặc observation handler được cấu hình khác, cần kiểm tra tag và count cụ thể thay vì chỉ kiểm tra meter tồn tại.

Với WebClient, hãy dùng `WebTestClient` hoặc mock exchange function phù hợp và subscribe publisher. Nếu không subscribe, request có thể chưa chạy nên không có observation để ghi nhận.

## 12. Các nguyên nhân khiến HTTP client metrics không xuất hiện

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Request chạy nhưng không có `http.client.requests` | Client được tạo thủ công, không qua builder đã instrument | Kiểm tra bean có được tạo từ builder Boot inject hay không. |
| Chỉ có server metrics | Server observation hoạt động nhưng client observation chưa được cấu hình | Kiểm tra HTTP client builder và observation registry. |
| Metric có nhưng thiếu client name | Host không được nhận diện hoặc convention khác | Xem `availableTags` và convention của phiên bản. |
| Có quá nhiều URI tag | Dùng URL động thay cho URI template | Dùng placeholder `{id}` và truyền biến riêng. |
| Request lỗi không thấy status | Kết nối thất bại trước khi nhận response | Xem tag `error` và cách exception được ghi nhận. |
| WebClient không có metric trong test | Publisher chưa được subscribe | Dùng `StepVerifier` hoặc block trong test đồng bộ có kiểm soát. |
| Chỉ thấy metric sau request đầu tiên | Meter được đăng ký lazy khi client call xảy ra | Thực hiện request thử rồi truy vấn endpoint. |
| Client tùy chỉnh không có observation | Tự thay HTTP connector hoặc bỏ qua customizer | Xác minh connector hỗ trợ observation và cấu hình handler. |

## 13. Những lỗi thiết kế thường gặp

- **Tạo `RestTemplate` bằng `new` rồi kỳ vọng Boot tự instrument:** object không đi qua builder customizer.
- **Gọi `WebClient.create()` trong service:** bỏ qua builder được Boot cấu hình.
- **Build client trong mỗi request:** tạo thêm object và bỏ qua mô hình tái sử dụng client.
- **Inject nhầm bean khi có nhiều client:** request đi đến dependency khác với client đang được kiểm tra.
- **Dùng URL đầy đủ có ID động:** làm URI tag tăng cardinality.
- **Nhầm `http.server.requests` với `http.client.requests`:** hai metric đo hai hướng lưu lượng khác nhau.
- **Giả định tag name giống nhau ở mọi version:** convention có thể thay đổi.
- **Chỉ kiểm tra request thành công:** bỏ qua timeout, connection error và response 4xx/5xx.
- **Cho rằng có metric là có lịch sử:** cần registry export và backend lưu time series để phân tích theo thời gian.

## 14. Checklist chọn và sử dụng HTTP client đã instrument

- [ ] Xác định đang cần đo request đi vào hay request đi ra.
- [ ] Dùng `RestTemplateBuilder`, `WebClient.Builder` hoặc `RestClient.Builder` do Spring Boot inject.
- [ ] Tạo client thành bean và tái sử dụng bằng constructor injection.
- [ ] Dùng `@Qualifier` khi ứng dụng có nhiều client cùng loại.
- [ ] Không tạo client bằng constructor hoặc static factory nếu cần Boot auto instrumentation mà chưa cấu hình bổ sung.
- [ ] Bảo đảm Actuator/Micrometer observation và registry được cấu hình.
- [ ] Dùng URI template để giới hạn cardinality.
- [ ] Xác minh tag thực tế qua `/actuator/metrics/http.client.requests`.
- [ ] Kiểm thử request thành công, response lỗi và lỗi kết nối.
- [ ] Với WebClient, bảo đảm reactive publisher được subscribe.
- [ ] Phân biệt client metrics với server metrics và backend history.

HTTP client metrics chỉ xuất hiện khi request đi qua một client có instrumentation và observation được kết nối với Micrometer registry. Trong Spring Boot, hãy chọn builder được inject từ application context, tạo bean client dùng chung và inject đúng bean vào service. Kết hợp URI template, tag có cardinality thấp và kiểm thử request thực tế để số liệu phản ánh đúng dependency mà ứng dụng đang gọi.
