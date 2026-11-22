# Tạo WebClient từ WebClient.Builder do Spring Boot quản lý

## Mục tiêu và bối cảnh

Trong một ứng dụng Spring Boot, tích hợp với dịch vụ bên ngoài thường bắt đầu bằng một lời gọi HTTP: lấy thông tin sản phẩm, kiểm tra tồn kho, xác nhận thanh toán hoặc gửi dữ liệu sang hệ thống đối tác. `WebClient` là HTTP client bất đồng bộ, hỗ trợ lập trình reactive của Spring WebFlux. Bài này tập trung vào **cách tạo các đối tượng `WebClient` từ `WebClient.Builder` do Spring Boot cung cấp**, thay vì tự dựng mọi thành phần kết nối.

Sau bài học, bạn cần có thể:

- Tiêm `WebClient.Builder` vào component Spring và tạo một `WebClient` dành riêng cho từng hệ thống.
- Đưa địa chỉ dịch vụ và cấu hình liên quan ra ngoài mã nguồn.
- Hiểu phần nào Spring Boot đã tự cấu hình và phạm vi tác động của những tùy chỉnh trên builder.
- Sử dụng client trong adapter tích hợp, xử lý lỗi, timeout và kiểm thử mà không làm mất cấu hình nền của Boot.

Nội dung nằm trong phạm vi tổ chức tích hợp hệ thống của Spring Boot: HTTP client là một adapter giao tiếp ra ngoài, phải tôn trọng hợp đồng dữ liệu, cấu hình, giao dịch nghiệp vụ, lỗi, quan sát và kiểm thử. `WebClient` chỉ thực hiện HTTP; nó không tự bảo đảm giao dịch phân tán, chống gửi trùng hay cơ chế retry an toàn.

## 1. Spring Boot quản lý WebClient.Builder như thế nào?

Khi Spring WebFlux có trên classpath và auto-configuration tương ứng đang hoạt động, Spring Boot tạo sẵn một bean **`WebClient.Builder` có scope `prototype`**. Mỗi lần Spring tiêm builder tại một injection point, nó cấp một builder đã được Boot cấu hình. Từ builder này, ứng dụng chọn `baseUrl`, header, filter và các quy tắc riêng rồi gọi `build()`.

Builder do Boot cấp giúp kế thừa các cấu hình có sẵn, chẳng hạn:

- Bộ mã hóa/giải mã (HTTP codecs) được quản lý thống nhất.
- `ClientHttpConnector` thích hợp với các thư viện HTTP nằm trên classpath; với Reactor Netty hoặc Jetty, Boot có thể chia sẻ tài nguyên phù hợp giữa server và client.
- Những `WebClientCustomizer` đã đăng ký.
- Tích hợp observation/tracing/metrics **khi** ứng dụng có các thành phần và cấu hình quan sát tương ứng.

Hai kiểu đối tượng cần phân biệt:

| Thành phần | Vòng đời và đặc điểm | Cách sử dụng |
| --- | --- | --- |
| `WebClient.Builder` | Có trạng thái, các lời gọi như `baseUrl()` hoặc `defaultHeader()` làm thay đổi builder | Cấu hình client lúc khởi tạo; cẩn thận khi dùng chung |
| `WebClient` sau `build()` | Đối tượng cấu hình ổn định, có thể dùng lại an toàn giữa nhiều request | Giữ làm field trong adapter/service; không tạo mới mỗi request |
| `WebClientCustomizer` | Tùy chỉnh được Boot áp dụng cho các builder được quản lý | Dùng cho quy tắc chung toàn ứng dụng |

~~~mermaid
flowchart LR
    A["Spring Boot auto-configuration"] --> B["WebClient.Builder (prototype)"]
    C["Codecs / Connector / Customizers"] --> B
    B --> D["Cấu hình theo downstream"]
    D --> E["WebClient đã build"]
    E --> F["CatalogGateway / adapter"]
    F --> G["Catalog HTTP API"]
~~~

> **Điểm mấu chốt:** `WebClient.create(...)` và `WebClient.builder()` là API hợp lệ của Spring Framework, nhưng các cách tự tạo này không mặc nhiên nhận toàn bộ cấu hình và `WebClientCustomizer` do Spring Boot áp dụng cho builder được tiêm. Với ứng dụng Boot, ưu tiên constructor injection của `WebClient.Builder`.

## 2. Chuẩn bị dependency và cấu hình

Một cách thông dụng để có `WebClient` cùng Reactor Netty là thêm starter WebFlux, kể cả khi ứng dụng chủ yếu dùng Spring MVC:

~~~groovy
// build.gradle (Gradle Groovy DSL)
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Trong ứng dụng đã có `spring-boot-starter-web` (Spring MVC), việc thêm starter WebFlux **không mặc nhiên chuyển loại web application thành reactive**; hai mô hình server và HTTP client là những quyết định khác nhau. Nếu hệ thống không cần API reactive, `RestClient` cũng là một lựa chọn phù hợp. Bài này dùng `WebClient` vì adapter cần trả về `Mono` hoặc `Flux`.

Ví dụ có một dịch vụ danh mục sản phẩm với API `GET /v1/products/{id}`. Thay vì đặt địa chỉ trong Java, khai báo:

~~~yaml
# application.yml
integrations:
  catalog:
    base-url: ${CATALOG_BASE_URL:https://catalog.example.org}
~~~

`https://catalog.example.org` chỉ là địa chỉ minh họa. Ở từng môi trường, đặt biến `CATALOG_BASE_URL` tương ứng. Không đưa mật khẩu, access token hoặc khóa API thực vào repository.

Ánh xạ cấu hình thành một đối tượng có kiểu rõ ràng:

~~~java
// CatalogProperties.java
import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "integrations.catalog")
public record CatalogProperties(URI baseUrl) {
}
~~~

Với Spring Boot 3.x/4.x và Java 17+, một record có một constructor như trên có thể được bind qua configuration properties. Bean properties sẽ được đăng ký bằng `@EnableConfigurationProperties` ở bước tiếp theo.

## 3. Tạo WebClient từ builder được tiêm

Cấu hình bean đại diện cho kết nối tới Catalog API:

~~~java
// CatalogClientConfiguration.java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CatalogProperties.class)
public class CatalogClientConfiguration {

    @Bean("catalogWebClient")
    WebClient catalogWebClient(
            WebClient.Builder builder,
            CatalogProperties properties) {

        return builder
                .baseUrl(properties.baseUrl().toString())
                .defaultHeader(
                        HttpHeaders.ACCEPT,
                        MediaType.APPLICATION_JSON_VALUE)
                .build();
    }
}
~~~

Giải thích từng phần:

1. Spring Boot tiêm `WebClient.Builder` mà nó đã auto-configure vào tham số `builder`.
2. `CatalogProperties` cấp URL từ cấu hình môi trường.
3. `baseUrl(...)` áp dụng URL gốc cho các URI tương đối.
4. `defaultHeader(...)` đặt header mặc định khi một request không tự chỉ định header tương ứng.
5. `build()` tạo `WebClient` để dùng nhiều lần; `@Bean("catalogWebClient")` cho phép chọn đúng client bằng qualifier.

Nếu chỉ tích hợp một endpoint đơn giản, bạn cũng có thể tiêm builder trực tiếp vào constructor của adapter và tạo client ở đó. Khi dự án có nhiều dịch vụ ngoài, việc đăng ký các `WebClient` có tên riêng giúp cấu hình và điểm sử dụng rõ ràng hơn.

Adapter gọi dịch vụ bên ngoài:

~~~java
// ProductDto.java
public record ProductDto(String id, String name, boolean active) {
}
~~~

~~~java
// CatalogGateway.java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class CatalogGateway {

    private final WebClient catalogWebClient;

    public CatalogGateway(
            @Qualifier("catalogWebClient") WebClient catalogWebClient) {
        this.catalogWebClient = catalogWebClient;
    }

    public Mono<ProductDto> findById(String productId) {
        return catalogWebClient.get()
                .uri("/v1/products/{id}", productId)
                .retrieve()
                .bodyToMono(ProductDto.class);
    }
}
~~~

Nếu `integrations.catalog.base-url` là `https://catalog.example.org` và `productId` là `P100`, request có dạng `GET https://catalog.example.org/v1/products/P100`.

- `uri("/v1/products/{id}", productId)` mở rộng URI template và xử lý mã hóa giá trị tham số; tránh tự nối chuỗi URL từ dữ liệu đầu vào.
- `retrieve()` là cách gọn cho phản hồi thông thường; mặc định phản hồi 4xx/5xx được chuyển thành lỗi `WebClientResponseException`.
- `bodyToMono(ProductDto.class)` giải mã một đối tượng JSON theo hợp đồng dữ liệu. Nếu API trả một danh sách hoặc luồng phần tử, chọn toán tử phù hợp như `bodyToFlux(...)`.

Lời gọi `findById(...)` **trả về mô tả tác vụ** dưới dạng `Mono`; network request thường chỉ bắt đầu khi có subscriber. Chẳng hạn, một WebFlux controller có thể trả thẳng `Mono<ProductDto>` và để framework subscribe. Không gọi `subscribe()` trong adapter chỉ để “kích hoạt” HTTP request, vì như vậy khó truyền kết quả và lỗi về luồng nghiệp vụ.

## 4. Tách nhiều WebClient và tránh rò rỉ cấu hình

Giả sử ứng dụng kết nối Catalog và Inventory bằng hai máy chủ, header hoặc cơ chế xác thực khác nhau. Nên tạo hai client riêng:

~~~java
@Bean("catalogWebClient")
WebClient catalogWebClient(WebClient.Builder builder) {
    return builder.baseUrl("https://catalog.example.org").build();
}

@Bean("inventoryWebClient")
WebClient inventoryWebClient(WebClient.Builder builder) {
    return builder.baseUrl("https://inventory.example.org").build();
}
~~~

Đây là ví dụ rút gọn để thấy việc tách bean; trong mã thực tế vẫn nên lấy cả hai URL từ configuration properties. Mỗi tham số builder được Spring giải quyết từ bean prototype nên có thể cấu hình độc lập.

Cần lưu ý trường hợp **bản thân bạn giữ cùng một tham chiếu builder** để tạo nhiều client:

~~~java
// builder là cùng một instance trong đoạn mã dưới đây
WebClient catalog = builder.clone()
        .baseUrl("https://catalog.example.org")
        .defaultHeader("X-System", "catalog")
        .build();

WebClient inventory = builder.clone()
        .baseUrl("https://inventory.example.org")
        .defaultHeader("X-System", "inventory")
        .build();
~~~

`clone()` tách trạng thái cấu hình tiếp theo. Nếu thay đổi liên tục trên cùng builder rồi gọi `build()`, những header/filter trước đó có thể còn tồn tại trên client xây sau. Khi đã có một `WebClient` và cần biến thể, `existingClient.mutate()...build()` tạo bản mới dựa trên cấu hình hiện tại mà không sửa client gốc.

**Quy tắc chọn phạm vi cấu hình:**

| Nhu cầu | Cách nên chọn | Lưu ý |
| --- | --- | --- |
| URL, header, filter riêng của Catalog | Tùy chỉnh builder ngay trước `build()` của Catalog | Không ảnh hưởng adapter khác |
| Nhiều client sinh từ cùng một builder được giữ lại | `builder.clone()` cho mỗi nhánh | Tránh mang nhầm cấu hình giữa các nhánh |
| Header định danh ứng dụng, filter chung không chứa bí mật | Bean `WebClientCustomizer` | Tác động đến mọi builder Boot quản lý |
| Thêm client từ một client đang chạy | `webClient.mutate().build()` | Kế thừa cấu hình của client gốc |
| Cấu hình thấp tầng của kết nối HTTP | Thuộc tính của Boot hoặc tùy biến connector | Kiểm tra ảnh hưởng tới pooling, timeout và resource lifecycle |

## 5. Tùy chỉnh chung bằng WebClientCustomizer

Khi thật sự cần một thuộc tính cho **mọi** HTTP client được khởi tạo từ builder do Boot quản lý, đăng ký một bean `WebClientCustomizer`:

~~~java
// Bổ sung trong một lớp @Configuration
@Bean
WebClientCustomizer clientIdentityCustomizer() {
    return builder -> builder.defaultHeader(
            "X-Client-Application",
            "spring-boot-integration");
}
~~~

Đoạn mã minh họa giả định bạn đã import kiểu `WebClientCustomizer` tương ứng phiên bản:

- **Spring Boot 3.x:** `org.springframework.boot.web.reactive.function.client.WebClientCustomizer`.
- **Spring Boot 4.x:** `org.springframework.boot.webclient.WebClientCustomizer`.

`WebClientCustomizer` áp dụng trên builder được Boot quản lý, vì vậy không đặt token bí mật, header đặc thù của một đối tác hoặc filter có giả định về riêng một API trong customizer toàn cục. Những yếu tố đó thuộc cấu hình của client tương ứng.

Nếu cần chèn bearer token theo người dùng hoặc access token có thời hạn, dùng cơ chế bảo mật/filter phù hợp cho từng downstream. `defaultHeader("Authorization", ...)` với một token cố định sẽ không tự xử lý refresh token.

## 6. Timeout, lỗi và độ tin cậy của luồng tích hợp

Việc tạo client thành công mới là bước đầu. Một HTTP adapter thực tế phải đặt giới hạn thời gian và định nghĩa kết quả khi downstream bất thường.

### Timeout

Có ít nhất ba khái niệm thường bị trộn lẫn:

- **Connect timeout:** thời gian chờ thiết lập kết nối tới máy chủ.
- **Read/response timeout:** giới hạn khi chờ dữ liệu phản hồi ở tầng HTTP transport.
- **Reactive `timeout(...)`:** giới hạn của chuỗi xử lý `Mono`/`Flux` tại vị trí đặt toán tử; có thể bao gồm những thao tác khác ngoài kết nối mạng.

Trong **Spring Boot 4.x**, có thể dùng cấu hình HTTP client chung, ví dụ:

~~~yaml
spring:
  http:
    clients:
      connect-timeout: 2s
      read-timeout: 5s
~~~

Các khóa trên ảnh hưởng tới HTTP clients được Boot auto-configure; chỉ đặt giá trị chung nếu phù hợp với các dịch vụ. Spring Boot 3.x có API và thuộc tính cấu hình connector khác; không sao chép máy móc cấu hình 4.x sang 3.x. Nếu cần timeout riêng theo đối tác, hãy chọn cơ chế được phiên bản Boot đang dùng hỗ trợ, hoặc cấu hình connector cho đúng client đó.

Ở tầng use case, có thể có giới hạn tổng thời gian cho một yêu cầu:

~~~java
public Mono<ProductDto> findByIdWithDeadline(String id) {
    return findById(id)
            .timeout(java.time.Duration.ofSeconds(6));
}
~~~

Đây là timeout của pipeline, không thay thế các timeout thiết lập kết nối và đọc phản hồi. Nếu tự thay `clientConnector(...)` bằng một `ReactorClientHttpConnector` dựng thủ công, bạn có thể thay luôn connector/tài nguyên mà Boot đã chuẩn bị. Chỉ làm vậy khi cần và kiểm tra lại vòng đời connection pool, tài nguyên và observation.

### Phân biệt lỗi HTTP và lỗi kết nối

| Tình huống | Dạng kết quả thường gặp | Xử lý ở biên tích hợp |
| --- | --- | --- |
| 2xx với JSON đúng hợp đồng | `Mono<ProductDto>` phát dữ liệu | Chuyển sang model nội bộ |
| 204 hoặc body rỗng | `Mono.empty()` trong trường hợp phù hợp | Quy định rõ hợp đồng có cho phép rỗng không |
| 404 | `WebClientResponseException.NotFound` theo mặc định của `retrieve()` | Quyết định “không tìm thấy” là kết quả nghiệp vụ hay lỗi |
| 4xx/5xx khác | `WebClientResponseException` | Phân loại lỗi hợp đồng, quyền truy cập hoặc downstream |
| DNS, kết nối bị từ chối, I/O | Thường là `WebClientRequestException` | Quan sát, áp dụng fallback/retry có kiểm soát |
| JSON sai cấu trúc hoặc không giải mã được | Lỗi decoding | Kiểm tra version và hợp đồng dữ liệu |

Có thể đặt cách ánh xạ 404 riêng cho adapter mà không đánh đồng mọi phản hồi lỗi:

~~~java
public Mono<ProductDto> findRequiredById(String id) {
    return catalogWebClient.get()
            .uri("/v1/products/{id}", id)
            .retrieve()
            .onStatus(
                    status -> status.value() == 404,
                    response -> Mono.error(
                            new IllegalStateException(
                                    "Catalog không có sản phẩm: " + id)))
            .bodyToMono(ProductDto.class);
}
~~~

Trong ứng dụng thật, thay `IllegalStateException` minh họa bằng exception/kiểu kết quả nghiệp vụ có chủ đích, rồi ánh xạ ở biên API. Tránh ghi toàn bộ response body hoặc token vào log. Nếu cần kiểm soát khác nhau giữa status, header và body, xem xét `exchangeToMono(...)`; khi đó ứng dụng tự chịu trách nhiệm xử lý mọi nhánh phản hồi.

Không bật retry vô điều kiện. Với `GET` có tính idempotent, có thể retry có giới hạn và backoff cho lỗi tạm thời. Với thao tác tạo đơn hàng, ghi thanh toán hay gửi thông điệp, retry có thể tạo bản ghi trùng; phải có khóa idempotency, hợp đồng retry và cơ chế xử lý trùng lặp phù hợp. Giao dịch dữ liệu trong Spring không tự rollback hiệu ứng đã xảy ra ở hệ thống HTTP bên ngoài.

### Observation và bảo mật

Builder do Boot quản lý là điểm tích hợp tốt cho cấu hình metrics/tracing có sẵn của ứng dụng, nhưng việc sinh observation thực tế phụ thuộc vào dependency và thiết lập quan sát. Đặt tên metric/tag có cardinality thấp; không đưa mã token, toàn bộ URL chứa định danh nhạy cảm hoặc payload cá nhân vào tag/log. Header xác thực phải được giới hạn cho đúng downstream.

## 7. Kiểm thử đúng hai lớp trách nhiệm

Một bộ kiểm thử hữu ích nên tách **wiring của Spring Boot** khỏi **hành vi HTTP adapter**:

1. **Kiểm tra wiring:** khởi động Spring context với `integrations.catalog.base-url` trỏ tới HTTP server giả lập; xác minh bean `catalogWebClient` được tạo bằng cấu hình môi trường và có thể tiêm vào `CatalogGateway`. Có thể dùng `@SpringBootTest` và `@DynamicPropertySource` để đưa URL server giả lập vào context.
2. **Kiểm tra hợp đồng HTTP:** dùng MockWebServer hoặc WireMock để xác minh method, path, header, JSON được decode và phản hồi 404/500 được xử lý đúng. Test phải gọi đến server giả lập, không phụ thuộc dịch vụ thật.
3. **Kiểm tra lỗi thời gian:** mô phỏng server phản hồi chậm hoặc đóng kết nối, xác minh deadline và cách chuyển lỗi theo chính sách của adapter.
4. **Kiểm tra nhiều downstream:** xác minh request đến Catalog không mang base URL, API key hay header chỉ dành cho Inventory.

Ví dụ một phép kiểm tra reactive response (đặt trong bài test đã cấu hình HTTP server giả lập và gateway):

~~~java
StepVerifier.create(catalogGateway.findById("P100"))
        .assertNext(product -> {
            assertEquals("P100", product.id());
            assertEquals("Bàn phím", product.name());
        })
        .verifyComplete();
~~~

`StepVerifier` đến từ dependency test `io.projectreactor:reactor-test`. Test còn cần chuẩn bị JSON tương ứng trên server giả lập và các import JUnit; snippet trên chỉ thể hiện phần assertion. Để xác minh Boot thực sự tham gia cấu hình, phải có ít nhất một kiểm thử chạy trong Spring context thay vì mọi test đều gọi `WebClient.builder()` trực tiếp.

## 8. Lỗi cấu hình thường gặp

| Dấu hiệu | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `No qualifying bean of type WebClient.Builder` | Thiếu Spring WebFlux trên classpath hoặc auto-configuration bị loại trừ | Kiểm tra dependency và điều kiện auto-configuration |
| `No qualifying bean of type WebClient` | Boot tự cung cấp **builder**, không tự sinh một bean `WebClient` cho từng API | Tạo `@Bean` từ builder như ví dụ |
| Hai downstream dùng nhầm URL/header | Dùng lại cùng builder có trạng thái, hoặc customizer toàn cục chứa cấu hình riêng | Tách builder/clone, dùng bean có tên và `@Qualifier` |
| Trả `Mono` nhưng không có request | Không có subscriber trong luồng thực thi | Trả publisher cho framework/consumer có trách nhiệm subscribe |
| Treo hoặc chậm bất thường | Thiếu giới hạn thời gian, downstream chậm hoặc pool bị cạn | Thiết lập timeout và quan sát transport/pool |
| `DataBufferLimitException` khi nhận payload lớn | Giới hạn buffer của codec bị vượt | Thiết kế streaming/phân trang; chỉ tăng `maxInMemorySize` nếu có lý do |
| Metadata quan sát không xuất hiện | Dùng client tự tạo hoặc thiếu thiết lập observation | Dùng builder của Boot và kiểm tra dependency/cấu hình |
| `block()` làm chậm xử lý reactive | Blocking trên event-loop hoặc đường xử lý reactive | Duy trì `Mono`/`Flux` xuyên suốt; chỉ block ở ranh giới imperative được kiểm soát |

## 9. Tiêu chí hoàn thành một adapter WebClient

Trước khi đưa kết nối HTTP vào hệ thống, hãy tự rà soát:

- [ ] Đã dùng `WebClient.Builder` do Boot cung cấp, với dependency và auto-configuration phù hợp.
- [ ] Đã tách URL và cấu hình môi trường khỏi mã nguồn; bí mật lấy từ secret/config provider.
- [ ] Có client dành riêng cho từng downstream và điểm tiêm xác định bằng `@Qualifier` khi cần.
- [ ] Đã định nghĩa DTO, trạng thái HTTP, dữ liệu rỗng và lỗi kết nối theo hợp đồng.
- [ ] Đã có timeout hợp lý, chính sách retry/idempotency rõ ràng và điểm quan sát cần thiết.
- [ ] Đã kiểm thử bằng server giả lập ít nhất các nhánh thành công, lỗi và timeout.

**Ghi nhớ:** Spring Boot sở hữu phần cấu hình cơ sở của `WebClient.Builder`; adapter sở hữu cấu hình riêng của downstream; nghiệp vụ sở hữu cách diễn giải kết quả, lỗi và xử lý gửi trùng. Giữ ranh giới này giúp luồng tích hợp dễ thay đổi, đo đạc và kiểm thử.

## Tài liệu tham khảo

- [Spring Boot — Calling REST Services, WebClient](https://docs.spring.io/spring-boot/reference/io/rest-client.html): builder prototype, HTTP runtime, tùy biến và tích hợp Boot.
- [Spring Boot 3.4 — Calling REST Services](https://docs.spring.io/spring-boot/3.4/reference/io/rest-client.html): đối chiếu cấu hình với nhánh 3.x.
- [Spring Framework — WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): builder, `mutate()`, codec và connector.
