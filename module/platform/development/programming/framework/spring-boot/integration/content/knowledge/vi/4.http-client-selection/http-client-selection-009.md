# Tích hợp quan sát và TLS qua các điểm tùy chỉnh của Boot

## 1. Bối cảnh: chọn HTTP client là chọn cả khả năng vận hành

Trong một ứng dụng **Spring Boot Integration**, HTTP client thường là cổng nối đến hệ thống đối tác: tra cứu thông tin bằng REST, gửi trạng thái giao dịch, lấy dữ liệu danh mục, hoặc gọi API sau khi nhận một sự kiện từ Kafka/RabbitMQ. Luồng có thể liên quan đến cơ sở dữ liệu, cache, transaction, retry và idempotency, nhưng ở biên HTTP phải giải quyết thêm hai yêu cầu:

- **Quan sát được (observability):** đo latency, trạng thái và tỷ lệ lỗi; liên kết request đến đối tác với trace của HTTP inbound hoặc message consumer; chẩn đoán timeout, TLS handshake và kết quả bất định.
- **Kết nối tin cậy (TLS):** xác thực chứng chỉ máy chủ bằng CA phù hợp, dùng mutual TLS (mTLS) nếu hợp đồng yêu cầu, không rò rỉ khóa và quản lý vòng đời certificate.

Spring Boot có sẵn các điểm cấu hình để hai yêu cầu này áp dụng nhất quán. Cách tạo client quyết định có nhận được **ObservationRegistry**, tracing/propagation và SSL bundle đã đăng ký trong ứng dụng hay không. Ví dụ `RestClient.create()` hoặc `WebClient.create()` bỏ qua các customizer tự cấu hình của Boot; khi cần observability mặc định, hãy **inject builder được Boot cung cấp** rồi tạo client.

### Sơ đồ thành phần

~~~mermaid
flowchart TD
    A[HTTP inbound hoặc broker consumer] --> B[Service tích hợp]
    B --> C[RestClient.Builder / WebClient.Builder từ Boot]
    D[Actuator + Micrometer ObservationRegistry] --> C
    E[RestClientCustomizer / WebClientCustomizer] --> C
    F[SSL Bundle: CA + client cert/key] --> G[RestClientSsl / WebClientSsl]
    G --> C
    C --> H[HTTP request factory / connector]
    H -->|TLS/mTLS| I[API đối tác]
    C -. quan sát, metrics, trace context .-> J[Monitoring/Tracing exporter]
    I --> K[Kết quả HTTP]
    K --> B
    B --> L[DB / cache / broker / outbox]
~~~

Điều quan trọng: *inbound TLS* của web server (`server.ssl.*`) và *outbound TLS* khi client gọi đối tác là hai cấu hình khác nhau. Đặt `server.ssl.bundle=...` không làm cho mọi HTTP client tự tin cậy chứng chỉ của đối tác.

## 2. Các điểm tùy chỉnh của Spring Boot cần chọn đúng

| Điểm tích hợp | Phạm vi | Dùng khi nào? |
| --- | --- | --- |
| `RestClient.Builder` được inject | Một client đồng bộ hoặc vài client dùng `clone()` | Đặt base URL, headers, interceptor, SSL, observation theo đối tác |
| `WebClient.Builder` được inject | Một client reactive/non-blocking hoặc `clone()` cho các client khác | Đặt filters, connector, SSL, metadata; giữ Reactor context |
| `RestTemplateBuilder` được inject | Client đồng bộ cũ dùng `RestTemplate` | Duy trì instrumentation và thêm timeout/SSL bundle theo kiểu builder |
| `RestClientCustomizer` | Mọi `RestClient.Builder` được Boot cấu hình | Chính sách chung như User-Agent hoặc convention thống nhất |
| `WebClientCustomizer` | Mọi `WebClient.Builder` được Boot cấu hình | Filter/chính sách chung cho WebClient |
| `RestTemplateCustomizer` | Mọi RestTemplate được tạo bởi builder Boot | Bổ sung thay đổi chung ở client legacy |
| `RestClientSsl` / `WebClientSsl` | Client cụ thể được chọn | Áp dụng một `SslBundle` đã khai báo |
| `SslBundles` | Tra cứu SSL bundle có tên | Áp dụng vào `RestTemplateBuilder` hoặc factory/connector custom |
| `ClientHttpRequestFactoryBuilder` / `ClientHttpConnectorBuilder` | Tầng transport đồng bộ / reactive | Cần đồng thời điều khiển SSL, timeout, redirect và chi tiết implementation |
| `ObservationRegistry` + `ObservationConvention` | Đo và gắn metadata quan sát | Thay đổi naming/tag/observation có chủ đích |

Spring Boot tự cấu hình builder theo điều kiện dependency trên classpath. Một builder **có trạng thái**: nếu cấu hình nhiều client từ cùng một instance, thay đổi về base URL, header hoặc SSL có thể ảnh hưởng những client build sau đó. Nên inject riêng ở từng bean hoặc gọi `clone()` khi chia sẻ builder để tách cấu hình.

### Lựa chọn RestClient, WebClient và RestTemplate

| Client | Đặc điểm | Đề xuất khi |
| --- | --- | --- |
| `RestClient` | API fluent đồng bộ, Spring Framework 6.1+, phù hợp Java blocking | Ứng dụng Spring MVC, scheduled job, service thread-per-request; điểm bắt đầu cho code đồng bộ mới |
| `WebClient` | API reactive dựa trên `Mono/Flux`, tích hợp reactive context và non-blocking I/O nếu dùng connector phù hợp | Spring WebFlux, streaming hoặc nhiều I/O concurrency có mô hình reactive rõ |
| `RestTemplate` | API đồng bộ lâu đời, vẫn hoạt động với hệ thống legacy | Duy trì code đã có; ưu tiên RestClient khi viết mới nếu không có ràng buộc |

Không chọn WebClient chỉ vì cho rằng nó “tự có tracing hơn”: Boot có thể instrument cả ba qua builder phù hợp. Trong luồng reactive, đừng gọi `block()` trong event-loop. Trong luồng đồng bộ thuần, dùng RestClient giúp tránh thêm độ phức tạp reactive không cần thiết.

## 3. Dependencies và cấu hình cơ sở

Các đoạn code chính bên dưới dùng **Spring Boot 3.5.x / Spring Framework 6.2.x / Java 17+**. Khi dùng Spring Boot 4.x, một số package tự cấu hình, tên starter và API đã thay đổi; phần giải thích vẫn áp dụng nhưng **phải đối chiếu tài liệu và BOM theo đúng version dự án**.

Với ứng dụng đồng bộ Spring MVC:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
~~~

Nếu dùng WebClient mà chưa có Spring WebFlux, thêm starter phù hợp:

~~~xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

Có thể dùng WebClient trong ứng dụng MVC; nếu `spring-boot-starter-web` và `spring-boot-starter-webflux` cùng hiện diện, Spring Boot thường chọn ứng dụng web servlet. Điều này không biến các lời gọi WebClient thành blocking và cũng không tự làm service nghiệp vụ trở thành reactive.

Để xuất metric sang Prometheus, thêm `io.micrometer:micrometer-registry-prometheus`. Để xuất trace, thêm **một** tổ hợp Micrometer Tracing Bridge (ví dụ `micrometer-tracing-bridge-otel`) và exporter OTLP tương thích phiên bản Boot; chỉ thêm Actuator không có nghĩa đã gửi trace đến collector. Spring Boot 4.x cung cấp cách khai báo starter telemetry mới, vì vậy luôn kiểm tra hướng dẫn tracing của đúng phiên bản.

~~~yaml
# application.yml — thuộc tính ứng dụng minh họa
integration:
  partner:
    base-url: https://partner.example.internal
    connect-timeout: 2s
    read-timeout: 5s

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
  tracing:
    sampling:
      probability: 0.1
~~~

`management.tracing.sampling.probability=0.1` minh họa tỷ lệ lấy mẫu 10% khi tracing được bật đúng dependency. Với test local có thể dùng 1.0 để dễ xác minh, rồi đặt lại hợp lý trong production. Các giá trị dưới `integration.partner.*` là **thuộc tính do ứng dụng định nghĩa**, cần bind vào `@ConfigurationProperties` hoặc đọc qua `@Value`; Spring Boot không tự động cấu hình mọi HTTP client từ prefix này.

## 4. Observability tự động qua builder Boot

Micrometer Observation là API thống nhất cho metric và tracing. Spring Framework tạo observation cho cuộc trao đổi HTTP client với tên mặc định `http.client.requests`; Spring Boot kết nối các bean client được tạo qua builder tự cấu hình với `ObservationRegistry` và những customizer liên quan. Khi có tracing bridge và exporter đúng, trace context như `traceparent` có thể được truyền sang dịch vụ đối tác theo cơ chế propagator đang cấu hình.

### 4.1. RestClient đồng bộ qua builder được inject

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class PartnerRestClientConfig {

    @Bean
    RestClient partnerRestClient(
            RestClient.Builder builder,
            @Value("${integration.partner.base-url}") String baseUrl) {
        return builder
                .baseUrl(baseUrl)
                .defaultHeader("X-Caller-Service", "spring-boot-integration")
                .build();
    }
}
~~~

Vì `RestClient.Builder` do Boot cung cấp, các cấu hình quan sát chung vẫn được áp dụng. Không cần tự tạo một `ObservationRegistry` hoặc tự gắn interceptor chỉ để có metric HTTP cơ bản.

Client nghiệp vụ có thể sử dụng URI template để tránh tạo metric có quá nhiều giá trị khác nhau:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class PartnerCatalogClient {
    private final RestClient client;

    public PartnerCatalogClient(RestClient partnerRestClient) {
        this.client = partnerRestClient;
    }

    public ProductDto findProduct(String productId) {
        return client.get()
                .uri("/v1/products/{id}", productId)
                .retrieve()
                .body(ProductDto.class);
    }
}
~~~

`ProductDto` là DTO do ứng dụng định nghĩa theo JSON contract của đối tác. Dùng `.uri("/v1/products/{id}", productId)` giúp observation giữ tag URI ở dạng template có cardinality thấp; tự nối `"/v1/products/" + productId` có thể khiến mỗi ID tạo một tổ hợp tag khác nhau nếu framework không nhận diện được template.

### 4.2. WebClient qua builder tự cấu hình

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class PartnerWebClientConfig {

    @Bean
    WebClient partnerWebClient(
            WebClient.Builder builder,
            @Value("${integration.partner.base-url}") String baseUrl) {
        return builder
                .baseUrl(baseUrl)
                .defaultHeader("X-Caller-Service", "spring-boot-integration")
                .build();
    }
}
~~~

~~~java
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class ReactivePartnerCatalogClient {
    private final WebClient client;

    public ReactivePartnerCatalogClient(WebClient partnerWebClient) {
        this.client = partnerWebClient;
    }

    public Mono<ProductDto> findProduct(String id) {
        return client.get()
                .uri("/v1/products/{id}", id)
                .retrieve()
                .bodyToMono(ProductDto.class);
    }
}
~~~

Trace context ở Reactor gắn với reactive subscriber/context, không chỉ một `ThreadLocal`. Tránh tự tạo thread hoặc chuyển qua callback bên ngoài mà đánh mất context; nếu cần bridge giữa executor, coroutine hoặc message listener, sử dụng cơ chế context propagation phù hợp. Khi nhận message từ broker, cần kiểm tra riêng việc lấy và phát trace headers qua adapter broker.

### 4.3. RestTemplate legacy qua builder

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.web.client.RestTemplate;

@Configuration(proxyBeanMethods = false)
class LegacyPartnerClientConfig {

    @Bean
    RestTemplate legacyPartnerRestTemplate(RestTemplateBuilder builder) {
        return builder
                .rootUri("https://legacy.example.internal")
                .build();
    }
}
~~~

`new RestTemplate()` chạy được nhưng không tự nhận customizer/tracing của Boot như một RestTemplate tạo qua builder Boot. Tương tự, `RestClient.create()` và `WebClient.create()` tự thân không áp dụng những customizer Boot đã đăng ký.

### 4.4. Tùy chỉnh phạm vi toàn ứng dụng và theo đối tác

Spring Boot cho phép đăng ký các bean customizer. Ví dụ thêm một `User-Agent` chung cho các RestClient:

~~~java
import org.springframework.boot.web.client.RestClientCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;

@Configuration(proxyBeanMethods = false)
class GlobalHttpClientCustomization {
    @Bean
    RestClientCustomizer integrationUserAgent() {
        return builder -> builder.defaultHeader(
                HttpHeaders.USER_AGENT, "spring-boot-integration");
    }
}
~~~

Đây là package `RestClientCustomizer` trong **Boot 3.5.x**. Với WebClient, tương ứng là `org.springframework.boot.web.reactive.function.client.WebClientCustomizer`; nó nhận `WebClient.Builder`. Với code cũ dùng RestTemplate, `org.springframework.boot.web.client.RestTemplateCustomizer` thao tác trên instance RestTemplate sau khi builder tạo client. Mỗi loại có phạm vi tác động riêng và được Boot áp dụng khi client sinh từ builder auto-configured.

Quy tắc phạm vi:

- **Toàn ứng dụng:** User-Agent chung, những convention không tiết lộ thông tin, logging/tracing policy đã được duyệt.
- **Theo từng đối tác:** base URL, token, mTLS client certificate, timeout, retry và error mapping. Không đưa header `Authorization` của đối tác A vào global customizer vì có thể làm lộ token sang đối tác B.
- **Theo từng request:** correlation/business ID, idempotency key và các tham số nghiệp vụ có thay đổi ở mỗi lần gọi.

Customizer nên **bổ sung** cấu hình mà Boot đã cung cấp. Nếu tự tạo `ObservationRegistry.create()` rồi gán lại trên builder, có thể làm mất handlers và tracing bridge do Boot đăng ký. Không gọi thêm một client riêng bằng `RestClient.create()` bên trong customizer rồi kỳ vọng các thiết lập áp dụng lên client của framework.

### 4.5. Thay ObservationConvention khi thực sự cần

Mặc định `http.client.requests` đã có metadata như method, URI template, HTTP status, outcome, tên host và loại lỗi. Để thêm tag **có cardinality thấp**, có thể tạo một convention cụ thể cho RestClient:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import org.springframework.http.client.observation.ClientRequestObservationContext;
import org.springframework.http.client.observation.DefaultClientRequestObservationConvention;

public final class PartnerHttpObservationConvention
        extends DefaultClientRequestObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(
            ClientRequestObservationContext context) {
        return super.getLowCardinalityKeyValues(context)
                .and(KeyValue.of("remote.service", "partner-catalog"));
    }
}
~~~

Gắn tại **builder của đối tác**:

~~~java
return builder
        .baseUrl(baseUrl)
        .observationConvention(new PartnerHttpObservationConvention())
        .build();
~~~

Đoạn này thay phần xây dựng client ở mục 4.1 (đặt bên trong phương thức `@Bean`, không phải một bean thứ hai trùng tên). Đặt tag theo tên *nhóm đối tác ổn định*. Không gắn `userId`, `productId`, `requestId`, token, query string hoặc URL đầy đủ làm low-cardinality tags; số lượng series metric sẽ tăng theo dữ liệu người dùng và có thể làm lộ thông tin.

Với WebClient, `ClientRequestObservationConvention` thuộc package reactive `org.springframework.web.reactive.function.client`, khác kiểu dành cho client đồng bộ. Không lấy convention của RestClient ép gán vào WebClient.

## 5. Tạo và áp dụng SSL bundle cho outbound HTTP

TLS trên HTTP client thực hiện hai công việc:

1. **Server authentication:** client xác minh certificate chain của máy chủ và hostname trong URL, ngăn kết nối tới server giả mạo.
2. **Client authentication (mTLS):** nếu API đối tác yêu cầu, client gửi certificate và private key hợp lệ để server xác minh danh tính client.

Spring Boot định nghĩa **SSL bundle** bằng tên dưới `spring.ssl.bundle.pem.*` (PEM) hoặc `spring.ssl.bundle.jks.*` (JKS/PKCS12). Bundle chứa trust material, key material và các tùy chọn TLS liên quan; có thể tái sử dụng theo tên cho các client khác nhau khi phù hợp.

### 5.1. Bundle chỉ tin cậy CA của đối tác

~~~yaml
# application.yml
spring:
  ssl:
    bundle:
      pem:
        partner-api:
          truststore:
            certificate: file:/run/secrets/partner-ca.pem
~~~

`partner-ca.pem` nên chứa CA chain được phép xác minh API đối tác. Trường hợp server dùng CA công cộng đã có trong JVM truststore, có thể không cần bundle riêng; khi đối tác dùng private CA thì cấu hình truststore là cần thiết. Không copy certificate từ một server không được xác thực rồi tự đưa vào truststore mà không kiểm tra nguồn.

### 5.2. Bundle cho mutual TLS (mTLS)

Khi đối tác đòi client certificate, bổ sung `keystore` với certificate/key của chính ứng dụng:

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        partner-api:
          truststore:
            certificate: file:/run/secrets/partner-ca.pem
          keystore:
            certificate: file:/run/secrets/integration-client.crt
            private-key: file:/run/secrets/integration-client.key
~~~

Với PKCS12/JKS, có thể dùng `spring.ssl.bundle.jks.partner-api.truststore.location` và `keystore.location`, mật khẩu lấy từ secret/environment, không commit vào Git. Chỉ cấu hình certificate **không có private key** chưa đủ để thực hiện mTLS. Trên cluster Kubernetes, mount secrets vào file với permission tối thiểu; không ghi key ra log hoặc đưa chúng vào image.

Chính sách TLS: xác minh certificate chain và hostname, chỉ cho phép TLS version/cipher được tổ chức phê duyệt, cân nhắc SNI và DNS khi đi qua proxy. **Không** dùng trust-all SSLContext hoặc tắt hostname verification để vượt lỗi handshake; đó là bỏ kiểm tra danh tính server.

### 5.3. Gắn bundle vào RestClient bằng RestClientSsl

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.web.client.RestClientSsl;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class SecurePartnerRestClientConfig {

    @Bean
    RestClient securePartnerRestClient(
            RestClient.Builder builder,
            RestClientSsl ssl,
            @Value("${integration.partner.base-url}") String baseUrl) {
        return builder
                .baseUrl(baseUrl)
                .apply(ssl.fromBundle("partner-api"))
                .build();
    }
}
~~~

`RestClientSsl` thuộc `org.springframework.boot.autoconfigure.web.client` trong Boot **3.5.x**. Dùng builder Boot để vừa giữ observation/tracing, vừa áp dụng SSL bundle đã đăng ký. Không cần xây `SSLContext` hay load private key thủ công cho trường hợp này.

**Chú ý thứ tự cấu hình:** `ssl.fromBundle(...)` **thay thế `ClientHttpRequestFactory` đã cấu hình trước đó**. Nếu đã tự cấu hình một factory chứa timeout, proxy hoặc connection pool rồi mới gọi `apply(ssl.fromBundle(...))`, factory cũ có thể bị thay bằng factory mới và mất các tùy chỉnh đặc thù. Khi cần kết hợp SSL với cài đặt transport nâng cao, xây factory bằng công cụ ở mục 6 rồi truyền một lần vào builder.

### 5.4. Gắn bundle vào WebClient bằng WebClientSsl

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.web.reactive.function.client.WebClientSsl;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
class SecurePartnerWebClientConfig {

    @Bean
    WebClient securePartnerWebClient(
            WebClient.Builder builder,
            WebClientSsl ssl,
            @Value("${integration.partner.base-url}") String baseUrl) {
        return builder
                .baseUrl(baseUrl)
                .apply(ssl.fromBundle("partner-api"))
                .build();
    }
}
~~~

`WebClientSsl` thuộc `org.springframework.boot.autoconfigure.web.reactive.function.client` trong Boot 3.5.x. Tương tự RestClient, áp dụng `fromBundle(...)` sẽ **thay `ClientHttpConnector` được gán trước đó**. Nếu dùng Reactor Netty connector riêng để cấu hình TCP proxy, pool, wiretap hoặc response timeout, cần kết hợp TLS đúng trong connector cuối cùng thay vì gắn connector rồi vô tình thay thế nó bằng `WebClientSsl`.

### 5.5. RestTemplateBuilder sử dụng SslBundles

~~~java
import java.time.Duration;
import org.springframework.boot.ssl.SslBundles;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.web.client.RestTemplate;

@Bean
RestTemplate secureLegacyRestTemplate(
        RestTemplateBuilder builder, SslBundles sslBundles) {
    return builder
            .rootUri("https://legacy.example.internal")
            .connectTimeout(Duration.ofSeconds(2))
            .readTimeout(Duration.ofSeconds(5))
            .sslBundle(sslBundles.getBundle("partner-api"))
            .build();
}
~~~

Đây là method `sslBundle(SslBundle)` của `RestTemplateBuilder` trong **Boot 3.4+**. Các method cũ `setSslBundle`, `setConnectTimeout` và `setReadTimeout` đã bị deprecated trong Boot 3.4 và có thể bị loại ở Boot 4. Đoạn code giả định được đặt trong lớp `@Configuration` có import `@Bean`.

## 6. Kết hợp timeout, TLS và transport mà vẫn giữ instrumentation

### 6.1. Cấu hình toàn ứng dụng bằng property Boot

Trong **Spring Boot 3.5**, các thuộc tính chung cho HTTP client có thể khai báo:

~~~yaml
spring:
  http:
    client:
      connect-timeout: 2s
      read-timeout: 5s
      redirects: dont-follow
~~~

Các thuộc tính này thuộc phạm vi **client HTTP do Boot tự cấu hình**, không phải `server.tomcat.connection-timeout`, `spring.mvc.async.request-timeout` hoặc timeout của một controller. Nếu nhiều đối tác có SLA khác nhau, nên override riêng tại client có liên quan.

**Khác biệt phiên bản:** Boot 3.5 có prefix `spring.http.client.*` (đồng bộ) và `spring.http.reactiveclient.*` (reactive). Trong **Boot 4.x**, Spring Boot hợp nhất thành `spring.http.clients.*`, ví dụ `spring.http.clients.connect-timeout`, `spring.http.clients.read-timeout` và `spring.http.clients.ssl.bundle`. Đọc metadata và migration guide của phiên bản thực tế trước khi đổi property; không sao chép lẫn lộn hai prefix.

Phân biệt các timeout:

| Timeout | Giới hạn | Không bao gồm/điều cần nhớ |
| --- | --- | --- |
| Connect timeout | Thời gian thiết lập kết nối tới máy chủ | Thời gian đọc body, xử lý backend, retry |
| Read/response timeout | Chờ dữ liệu/phản hồi theo triển khai transport | Không phải lúc nào cũng là deadline cho toàn bộ body lớn hoặc stream lâu |
| Pool acquire timeout | Thời gian chờ mượn connection khi pool quá tải | Cần cấu hình riêng ở HTTP engine phù hợp |
| Tổng deadline của tác vụ | HTTP + retry/backoff + DB/broker + xử lý dữ liệu | Thiết kế ở tầng service/worker; không có nghĩa cứ cancel là đối tác chưa xử lý |

Không chọn 5 giây làm read timeout rồi cho phép 10 lần retry liên tiếp trong một HTTP request có SLA 3 giây. Phải có **retry budget**, circuit breaker, bulkhead và idempotency key phù hợp với tác dụng phụ.

### 6.2. Factory kết hợp SSL + connect/read timeout cho RestClient

Trong Boot 3.5, `ClientHttpRequestFactorySettings` và `ClientHttpRequestFactoryBuilder` cho phép hợp nhất SSL bundle và timeout vào **một factory**:

~~~java
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.http.client.ClientHttpRequestFactoryBuilder;
import org.springframework.boot.http.client.ClientHttpRequestFactorySettings;
import org.springframework.boot.ssl.SslBundles;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.ClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class PartnerTransportConfig {

    @Bean
    RestClient partnerClientWithTransport(
            RestClient.Builder builder,
            SslBundles sslBundles,
            @Value("${integration.partner.base-url}") String baseUrl) {

        ClientHttpRequestFactorySettings settings =
                ClientHttpRequestFactorySettings.defaults()
                        .withTimeouts(
                                Duration.ofSeconds(2),
                                Duration.ofSeconds(5))
                        .withSslBundle(sslBundles.getBundle("partner-api"));

        ClientHttpRequestFactory factory =
                ClientHttpRequestFactoryBuilder.detect().build(settings);

        return builder
                .baseUrl(baseUrl)
                .requestFactory(factory)
                .build();
    }
}
~~~

Ở ví dụ này **không** gọi thêm `ssl.fromBundle(...)` vì `factory` đã được xây bằng SSL bundle. `ClientHttpRequestFactoryBuilder.detect()` chọn engine theo classpath (ví dụ Apache HttpClient, Jetty, Reactor, JDK); thứ tự ưu tiên thuộc Boot phiên bản đang chạy, và sự thay đổi dependency có thể đổi engine được chọn. Khi cần hành vi cố định, chọn factory/engine cụ thể và kiểm thử trên môi trường triển khai.

Thay factory qua `builder.requestFactory(factory)` vẫn giữ customizer quan sát đã gắn trên `RestClient.Builder`, nhưng nếu thay toàn bộ builder bằng `RestClient.builder()` tự tạo, bạn không còn bảo đảm có ObservationRegistry từ Boot.

### 6.3. Connector kết hợp SSL + timeout cho WebClient

Boot 3.5 có `ClientHttpConnectorBuilder` và `ClientHttpConnectorSettings` dành cho transport reactive. Có thể tạo connector từ cùng một SSL bundle:

~~~java
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.http.client.reactive.ClientHttpConnectorBuilder;
import org.springframework.boot.http.client.reactive.ClientHttpConnectorSettings;
import org.springframework.boot.ssl.SslBundles;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
class PartnerReactiveTransportConfig {

    @Bean
    WebClient partnerReactiveClientWithTransport(
            WebClient.Builder builder,
            SslBundles sslBundles,
            @Value("${integration.partner.base-url}") String baseUrl) {

        ClientHttpConnectorSettings settings =
                ClientHttpConnectorSettings.defaults()
                        .withTimeouts(
                                Duration.ofSeconds(2),
                                Duration.ofSeconds(5))
                        .withSslBundle(sslBundles.getBundle("partner-api"));

        ClientHttpConnector connector =
                ClientHttpConnectorBuilder.detect().build(settings);

        return builder
                .baseUrl(baseUrl)
                .clientConnector(connector)
                .build();
    }
}
~~~

Cũng như RestClient, đây là **một cách thay thế** cho `WebClientSsl.fromBundle(...)`, không phải bước phải làm thêm sau `fromBundle`. Nếu cần Reactor Netty nâng cao (pool idle/TTL, response timeout, proxy hoặc wiretap), sử dụng customizer/builder của engine được chọn và vẫn truyền SSL trust material đúng cách. Tránh custom Netty SSLContext với trust-all hoặc bỏ hostname verification.

Lưu ý rằng `ClientHttpRequestFactorySettings`, `ClientHttpConnectorSettings` và các builder ở trên là API tương đối mới của **Boot 3.4/3.5**; Boot 4 có thay đổi cấu trúc các lớp settings. Code trong bài được neo theo Boot 3.5; khi nâng major version, dùng migration guide và API reference tương ứng để chuyển đổi.

### 6.4. Tránh mất instrumentation khi thay transport

Quy trình lựa chọn:

~~~mermaid
flowchart TD
    A[Cần client HTTP?] --> B{Blocking hay reactive?}
    B -- Blocking --> C[Inject RestClient.Builder]
    B -- Reactive --> D[Inject WebClient.Builder]
    C --> E{Chỉ cần TLS bundle?}
    D --> F{Chỉ cần TLS bundle?}
    E -- Có --> G[RestClientSsl.fromBundle]
    F -- Có --> H[WebClientSsl.fromBundle]
    E -- TLS + transport nâng cao --> I[ClientHttpRequestFactoryBuilder + SslBundle]
    F -- TLS + transport nâng cao --> J[ClientHttpConnectorBuilder + SslBundle]
    G --> K[Build + giữ ObservationRegistry]
    H --> K
    I --> K
    J --> K
    K --> L[Test HTTPS, metrics, trace, timeout]
~~~

Tầng timeout hoặc TLS cần được thay bằng một factory/connector có chủ đích; tầng **quan sát** vẫn gắn ở builder. Không giả định rằng thay Netty connector hoặc Apache request factory sẽ tự tạo span của Spring khi bạn bỏ luôn builder Boot.

## 7. Thiết kế trace và metric cho luồng tích hợp

### 7.1. Một trace đi qua các hệ thống như thế nào?

~~~text
POST /integration/orders              traceId=T
   |
   +-- Spring MVC HTTP server span
          |
          +-- DB: lưu idempotency key R1
          |
          +-- RestClient HTTP client span
                 |-- traceparent: 00-T-...-01 (khi tracing đã bật)
                 +-- HTTPS / mTLS --> Partner API
          |
          +-- DB: ghi trạng thái + outbox
          |
          +-- Broker publisher / consumer spans
~~~

Với synchronous HTTP request, trace context thường có sẵn trên luồng xử lý; builder Boot kết hợp Micrometer Tracing có thể truyền context qua HTTP headers theo propagator đã cấu hình. Trong luồng Kafka/RabbitMQ, việc lấy context từ message headers và đưa sang HTTP client phụ thuộc instrumentation/adapter của broker. Nếu message được xử lý ở một executor tùy biến, cần bảo đảm context propagation để trace không bị đứt.

**Không tự gán `traceparent` từ request header do bên ngoài cung cấp mà bỏ qua xử lý của tracer**. Trace headers phải được đọc/ghi theo chuẩn và chính sách sampling/trust. Không coi traceId là idempotency key: mỗi lần retry hoặc message redelivery có thể có trace/span khác nhau, trong khi business request ID phải ổn định.

### 7.2. Chọn tag có cardinality thấp

Observation HTTP client thường cung cấp metadata chung:

| Nhãn / thông tin | Ví dụ | Chú ý |
| --- | --- | --- |
| `method` | `GET`, `POST` | Nhóm hữu hạn |
| `uri` | `/v1/products/{id}` | Dùng URI template, không ghi ID thật vào metric |
| `client.name` | `partner.example.internal` | Tránh host động không kiểm soát |
| `status` | `200`, `503`, `IO_ERROR` | Gắn theo quy ước phiên bản framework |
| `outcome` | `SUCCESS`, `SERVER_ERROR` | Phân biệt lỗi HTTP với lỗi I/O |
| `error` | `ResourceAccessException` hoặc `none` | Không đồng nhất với message lỗi chi tiết |
| `remote.service` tùy chỉnh | `partner-catalog` | Giá trị cố định có danh mục giới hạn |

Metric `http.client.requests` giúp theo dõi throughput, latency, status/error. Để tính P95/P99 có ý nghĩa, cần cấu hình histogram/percentile của Micrometer registry và xem xét nhãn số lượng lớn. Cần đo riêng **retry attempts**, **circuit breaker state**, **TLS handshake failures**, **pool acquire waits**, **downstream timeouts** và **backlog của message/outbox** nếu chúng có tác động đáng kể; HTTP observation mặc định không phản ánh đủ các lớp này.

### 7.3. HTTP 4xx/5xx khác lỗi transport/TLS

| Tình huống | Có HTTP response không? | Cách quan sát | Hành vi tích hợp |
| --- | --- | --- | --- |
| `404 Not Found` | Có | HTTP status và URI template | Theo hợp đồng: dữ liệu vắng mặt hay API lỗi |
| `401/403` | Có | HTTP status, không log token | Kiểm tra credential/authorization, tránh retry mù |
| `429 Too Many Requests` | Có | HTTP status, `Retry-After` nếu có | Backoff/rate limit, có ngân sách retry |
| `500/503` | Có | HTTP status, latency, response/traces | Retry có giới hạn nếu operation idempotent |
| DNS/connect timeout | Không | Exception I/O, DNS/connection metrics | Phân loại unavailable, không coi là 404 |
| TLS certificate/hostname mismatch | Không có HTTP response | SSL handshake exception + trace lỗi | Sửa trust material hoặc hostname, không tắt xác minh |
| Read timeout sau khi gửi POST | Có thể không | Exception + requestId ở application logs | Kết quả nghiệp vụ *không chắc chắn*, xác minh idempotency trước retry |

Theo chính sách Spring `retrieve()` thường phát exception với 4xx/5xx nếu không đăng ký status handler khác; lỗi TLS/socket phát sinh trước hoặc trong trao đổi HTTP, phải xử lý theo nhóm exception hạ tầng. Không đổi mọi exception thành dữ liệu rỗng hoặc phản hồi thành công.

## 8. Ví dụ luồng POST có idempotency và theo dõi được

Giả sử ứng dụng nhận lệnh tạo đơn hàng từ API hoặc broker, lưu trạng thái bằng JDBC/MongoDB rồi gọi partner API. Nếu thời gian chờ kết thúc mà đối tác đã tạo đơn hàng thành công, ứng dụng vẫn phải an toàn khi thử lại. Một cách là chuyển **khóa idempotency nghiệp vụ** ổn định tới đối tác, với điều kiện partner API có hỗ trợ hợp đồng đó.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class PartnerOrderGateway {
    private final RestClient partnerRestClient;

    public PartnerOrderGateway(RestClient partnerRestClient) {
        this.partnerRestClient = partnerRestClient;
    }

    public void submit(String requestId, CreateOrderRequest payload) {
        partnerRestClient.post()
                .uri("/v1/orders")
                .header("Idempotency-Key", requestId)
                .body(payload)
                .retrieve()
                .toBodilessEntity();
    }
}
~~~

`CreateOrderRequest` là DTO theo contract đối tác. Request được gửi bằng RestClient được Boot cấu hình, nên có thể có trace span và metric mặc định, đồng thời TLS/mTLS lấy từ bundle đã gắn ở bean client. Nếu đối tác trả 202 Accepted thay vì 200/201, ứng dụng phải làm theo contract response: có thể cần poll/truy vấn trạng thái trước khi coi nghiệp vụ đã hoàn tất.

**Điều kiện thiết kế:**

1. `requestId` được sinh ở ranh giới nhận thông điệp và giữ nguyên khi retry, restart hoặc message redelivery. Không tạo UUID mới cho từng attempt.
2. Nếu đối tác không có idempotency key, cần cơ chế tra cứu trạng thái trước/sau retry và quy tắc reconciliation. HTTP observation không cung cấp exactly-once.
3. Phân biệt `ReadTimeoutException` / socket timeout (kết quả không chắc chắn), `429`, `503` và lỗi xác thực/TLS; không retry tất cả như nhau.
4. Lưu trạng thái và phát sự kiện bằng transactional outbox nếu cần nhất quán giữa DB và broker. HTTP call không trở thành một phần của DB transaction chỉ vì chạy trong `@Transactional`.
5. Không log body hay header `Authorization`/`Cookie`/client certificate key. Khi cần debug, log method, URI template, status, latency, remote service và một ID được phép lưu.

**Lưu ý khi sao chép code:** các bean `partnerRestClient`, `securePartnerRestClient` và `partnerClientWithTransport` trong các mục trước là **ba phương án cấu hình thay thế** cho cùng mục tiêu. Một ứng dụng thật nên chọn một phương án cho từng đối tác; nếu đăng ký nhiều bean kiểu `RestClient`, dùng `@Qualifier("partnerRestClient")` tại điểm inject để tránh lỗi ambiguous dependency. Tương tự với WebClient. DTO tối giản cho ví dụ GET là:

~~~java
public record ProductDto(String id, String name) {}
~~~

## 9. Kiểm thử observability và TLS có ý nghĩa

### 9.1. Kiểm thử logic HTTP không cần server thật

Đối với phần JSON contract, status mapping và URI template, có thể dùng `@RestClientTest` + `MockRestServiceServer` hoặc test thích hợp của Spring, xác nhận:

- Request đi đúng method, path và header nghiệp vụ.
- URI template được sử dụng khi tạo request.
- JSON serializer/deserializer xử lý trường bắt buộc và lỗi schema.
- `404/409/429/5xx` có mapping hợp đồng đúng, không đánh đồng với lỗi socket.
- Retry vẫn giữ `Idempotency-Key`.

Các test mock ở tầng HTTP **không kiểm chứng TLS handshake thật** và có thể không xác minh đủ việc xuất observation/tracing. Không dựa vào test chỉ mock RestClient để kết luận truststore hoặc client certificate đúng.

### 9.2. Integration test HTTPS/mTLS

Đặt một HTTPS test server (ví dụ MockWebServer/WireMock với TLS hoặc service test container), tạo CA/cert/key *chỉ dành cho test* và chạy Spring Boot context với SSL bundle trỏ tới tài liệu test. Ma trận:

| Tình huống | Cấu hình | Kỳ vọng |
| --- | --- | --- |
| HTTPS chuẩn | CA của test server có trong truststore | Handshake thành công, request HTTP được gửi |
| Private CA chưa tin cậy | Xóa CA của test server khỏi truststore | Handshake bị từ chối; không bỏ kiểm tra certificate |
| Hostname sai | Server certificate không khớp DNS đang gọi | Handshake/hostname verification thất bại |
| mTLS đúng | Server yêu cầu client certificate, bundle có cert/key hợp lệ | Handshake và request thành công |
| mTLS thiếu client key/cert | Server yêu cầu client auth, client không cung cấp đúng | Kết nối bị từ chối theo TLS contract |
| TLS certificate hết hạn | Dùng certificate test hết hạn | Bị từ chối và phát cảnh báo/metric phù hợp |
| Connect timeout | Test server/route không thiết lập kết nối | Exception xuất hiện trong ngân sách đã đặt |
| Read timeout | Kết nối thành công nhưng server trì hoãn response | Exception đúng nhóm; timeout không bị map thành 404 |
| 429/503 | Server trả status và headers giả lập | Retry/backoff/rate-limit được thực thi theo policy |

Nếu dùng WebClient, cần kiểm tra thêm request cancellation/backpressure và việc các span vẫn có quan hệ parent–child đúng khi luồng đi qua `flatMap`/`publishOn` hoặc custom executor.

### 9.3. Xác nhận metric và trace thực tế

Một quy trình xác minh:

1. Bật Actuator và tracing exporter của **môi trường test**. Dùng sampling `1.0` chỉ trong test nếu cần mọi request xuất hiện.
2. Gọi một endpoint inbound, để service tạo HTTP outbound qua builder Boot. Chờ response rồi xem `/actuator/metrics/http.client.requests` nếu endpoint được bật và registry có đo.
3. Kiểm tra các tag: method, URI template, client name, status/outcome; không thấy request ID hoặc access token trong tag.
4. Xem trace ở collector: inbound span và outbound HTTP client span có cùng traceId, span quan hệ đúng; `traceparent` được truyền đến test server khi tracing active.
5. Gây 503, TLS handshake failure và timeout để đối chiếu exception, result tag và correlation trong log.
6. Giới hạn và bảo vệ quyền truy cập Actuator; không mở tất cả endpoint metrics/tracing cho internet chỉ để test dễ hơn.

Trên Spring Boot 3.5, Actuator còn cung cấp metric `ssl.chain.expiry` để quan sát thời gian còn lại đến khi certificate trong SSL bundle hết hạn (đơn vị giây theo metric); nên cảnh báo trước khi chứng chỉ bắt đầu gây sự cố. Tên/mẫu nhãn metric và khả năng refresh bundle có thể thay đổi theo phiên bản/transport; kiểm chứng trên runtime thay vì mặc định mọi connection pool sẽ tự dùng certificate mới ngay khi secret được thay.

### 9.4. Kiểm tra việc customizer còn hoạt động

Thực hiện một test integration tạo `RestClient` bằng đúng bean của ứng dụng, rồi kiểm tra các điểm:

- Customizer toàn ứng dụng đã thêm header `User-Agent`.
- SSL bundle đúng được áp dụng (có handshake thành công với private CA, thất bại nếu CA khác).
- Connect/read timeout được giữ lại sau khi áp dụng SSL; đây là lỗi rất dễ gặp khi thứ tự `apply(ssl.fromBundle(...))` và `requestFactory(...)` sai.
- Metric `http.client.requests` và trace context vẫn tồn tại sau khi thay request factory/connector.
- Không có header `Authorization` của đối tác A trong request đến đối tác B nếu ứng dụng có nhiều client.

Không có yêu cầu phải test bằng một endpoint production thật. Dùng HTTPS server và certificate dành riêng cho test giúp tạo các tình huống TLS lỗi có thể lặp lại mà không thay đổi hệ thống đối tác.

## 10. Checklist triển khai và xử lý sự cố

### 10.1. Trước khi deploy

| Câu hỏi | Cần kiểm tra |
| --- | --- |
| Client tạo bằng gì? | Inject builder Boot; tránh tạo client thủ công làm rơi instrumentation |
| Cấu hình toàn cục và riêng? | Customizer chung không chứa token, URL hay TLS của một đối tác cụ thể |
| Dùng SSL bundle nào? | Tên bundle đúng, CA tin cậy được xác minh; mTLS có cert và private key tương ứng |
| Có timeout hữu hạn? | Connect/read/pool wait và tổng deadline theo SLA; retry không vượt ngân sách |
| Certificate có được theo dõi? | Expiry alert, rotation runbook, kiểm tra mTLS sau rotation |
| Metric có cardinality hợp lý? | URI template, tag đối tác hữu hạn, không log/token/PII |
| Trace có xuyên hệ thống? | HTTP inbound → client outbound → broker/DB theo đúng context |
| Lỗi được phân loại? | HTTP status khác TLS/socket; timeout sau POST là kết quả chưa chắc chắn |
| Retry có idempotency? | Business key cố định, backoff, circuit breaker, outbox hoặc reconciliation |
| TLS thực sự được test? | Test handshake với CA/mTLS đúng và sai; không chỉ mock HTTP response |

### 10.2. Những lỗi thường gặp

**Không thấy `http.client.requests`:** kiểm tra có dùng injected `RestClient.Builder`/`WebClient.Builder`/`RestTemplateBuilder` không; có Actuator/ObservationRegistry đúng context không; client đã thực hiện request chưa; meter registry/exporter có được bật không. Nếu chỉ xem trace mà không thấy, kiểm tra tracing bridge, exporter và sampling nữa.

**Span outbound không cùng traceId inbound:** kiểm tra đoạn code có tạo thread, custom scheduler, subscriber/reactive context bị cắt hoặc broker adapter không propagate headers hay không. Không khắc phục bằng cách tự copy chuỗi `traceparent` vào một header tùy ý.

**PKIX path building failed / certificate unknown:** truststore thiếu CA chain, chứng chỉ server sai hoặc hết hạn, hoặc host/proxy đưa đến server khác. Đối chiếu server certificate chain và hostname; không tắt trust verification.

**Handshake thất bại khi bật mTLS:** kiểm tra server có yêu cầu client certificate; cert/key có khớp nhau, thời hạn/extended key usage phù hợp, chain gửi đủ, SNI/hostname và TLS protocol/cipher tương thích.

**Timeout được cấu hình nhưng không có tác dụng:** xem engine nào được auto-detect; timeout nào đang được đặt (connect, response, pool acquire, toàn request); có bị `RestClientSsl/WebClientSsl` thay factory/connector sau khi đặt không; custom transport có áp dụng settings đã chọn không.

**Sau rotate secret vẫn thấy certificate cũ:** connection đang được reuse, SSLContext/connector có thể đã load key cũ. Kiểm tra cơ chế reload hỗ trợ cho client/engine và lập quy trình tái tạo connection pool hoặc rolling restart có kiểm soát; quan sát metric certificate expiry sau rotation.

**Tăng số lỗi 5xx sau khi bật retry:** tổng lượng request có thể tăng nhiều lần. Đo attempt rate, error ratio, concurrency và circuit breaker; giới hạn retry và thực hiện backoff. Đối với lệnh POST tạo tài nguyên, chỉ retry khi idempotency/reconciliation có hợp đồng rõ.

## 11. Ranh giới phiên bản và quyết định kỹ thuật

| Chủ đề | Spring Boot 3.5.x | Spring Boot 4.x |
| --- | --- | --- |
| RestClient SSL helper | `org.springframework.boot.autoconfigure.web.client.RestClientSsl` | Package đã chuyển sang module auto-configuration REST client; xem API hiện hành |
| WebClient SSL helper | `org.springframework.boot.autoconfigure.web.reactive.function.client.WebClientSsl` | `org.springframework.boot.webclient.autoconfigure.WebClientSsl` trong API Boot 4 |
| RestClientCustomizer | `org.springframework.boot.web.client.RestClientCustomizer` | Có tổ chức module/package mới; đối chiếu IDE và API |
| Global HTTP client settings | `spring.http.client.*` (blocking) và `spring.http.reactiveclient.*` (reactive) | `spring.http.clients.*` |
| Transport settings | `ClientHttpRequestFactorySettings`, `ClientHttpConnectorSettings` và các builder 3.5 | `HttpClientSettings` dùng chung trong API mới |
| Observation | Inject builder Boot + Actuator/Micrometer | Cùng nguyên tắc, tùy package và starter tương ứng |
| SSL bundle | `spring.ssl.bundle.pem/jks.*`, inject/apply bundle | Cùng ý tưởng, kiểm tra API mới trước khi nâng cấp |

Không copy một import từ Boot 3.5 sang 4.x khi package đã đổi. Nếu dự án giữ phiên bản cụ thể trong BOM, ưu tiên Javadoc/reference của **đúng bản đó** và kiểm tra warning deprecation. Bài dùng các snippet theo chủ đề; khi triển khai, chọn một cấu hình client cho mỗi endpoint và tích hợp trong Spring context thật trước khi chạy test.

### Tự kiểm tra

1. Vì sao `RestClient.create()` vẫn gọi API được nhưng có thể không xuất metric/tracing mặc định như builder Boot?
2. Đặt `server.ssl.bundle` có tự làm WebClient tin cậy certificate của API đối tác không?
3. Nếu áp dụng `RestClientSsl.fromBundle` sau một custom `requestFactory`, điều gì có thể xảy ra với timeout đã đặt?
4. Sự khác nhau giữa CA truststore và client certificate/private key trong mTLS là gì?
5. Vì sao `.uri("/v1/products/{id}", id)` tốt hơn nối ID thật khi tạo metric?
6. Khi `POST` timeout nhưng phía đối tác có thể đã nhận request, vì sao cần khóa idempotency và reconciliation?
7. Thử nghiệm nào chứng minh được cả TLS handshake, metric/tracing và timeout hoạt động sau khi custom connector?

## Tài liệu tham khảo

- [Spring Boot 3.5 — Calling REST Services](https://docs.spring.io/spring-boot/3.5/reference/io/rest-client.html)
- [Spring Boot 3.5 — SSL Bundles](https://docs.spring.io/spring-boot/3.5/reference/features/ssl.html)
- [Spring Boot 3.5 — Actuator HTTP Client Metrics](https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html)
- [Spring Boot 3.5 — Tracing and Propagation](https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html)
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Spring Boot 3.5 API — RestClientSsl](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/client/RestClientSsl.html)
- [Spring Boot 3.5 API — WebClientSsl](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/reactive/function/client/WebClientSsl.html)
- [Spring Boot 3.5 API — ClientHttpRequestFactoryBuilder](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/http/client/ClientHttpRequestFactoryBuilder.html)
- [Spring Boot 3.5 API — ClientHttpConnectorBuilder](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/http/client/reactive/ClientHttpConnectorBuilder.html)
- [Spring Boot 4 — Calling REST Services](https://docs.spring.io/spring-boot/4.0/reference/io/rest-client.html)



