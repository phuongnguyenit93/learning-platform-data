# Dùng đồng thời HTTP client thông thường và client theo tên dịch vụ

> **Chương:** Gọi dịch vụ  
> **Module:** SPRING_CLOUD_CORE

Một ứng dụng Spring Cloud thường gọi nhiều loại đích khác nhau. Có request đi tới API bên ngoài bằng hostname cố định hoặc DNS thông thường; có request đi tới một dịch vụ nội bộ mà địa chỉ instance được lấy từ service discovery. Dùng cùng một HTTP client cho cả hai trường hợp có thể làm cấu hình khó hiểu, đặc biệt khi client được gắn cơ chế load balancing theo service ID.

Spring Cloud cho phép tạo các HTTP client riêng: **client thông thường** gửi request tới URL/hostname theo cách phân giải mạng bình thường; **client theo tên dịch vụ** dùng Spring Cloud LoadBalancer để chuyển service ID thành một instance cụ thể trước khi gửi request. Cả hai có thể cùng tồn tại trong một ApplicationContext. Bài này trình bày cách khai báo, inject, sử dụng và kiểm thử hai client trong module **SPRING_CLOUD_CORE**.

## 1. Hai kiểu địa chỉ đích trong cùng ứng dụng

Trước khi chọn client, hãy phân biệt địa chỉ vật lý với tên dịch vụ logic.

- **Địa chỉ trực tiếp:** URL chứa hostname hoặc IP mà HTTP client có thể phân giải qua DNS và network routing, ví dụ `https://api.partner.example` hoặc `http://legacy.internal:8080`.
- **Service ID:** tên logic mà discovery client biết, ví dụ `catalog-service`. Spring Cloud LoadBalancer lấy danh sách instance cho tên này và chọn một instance để gửi request.

Ví dụ một ứng dụng `order-service` có thể cần:

| Nhu cầu | Địa chỉ gọi | Cơ chế phù hợp |
| --- | --- | --- |
| Gọi API thanh toán bên ngoài | `https://payments.partner.example` | HTTP client thông thường |
| Gọi hệ thống legacy có DNS cố định | `http://legacy.internal:8080` | HTTP client thông thường |
| Gọi catalog có nhiều instance | `http://catalog-service` | Client có Spring Cloud LoadBalancer |
| Gọi inventory theo service ID | `http://inventory-service` | Client có Spring Cloud LoadBalancer |

Client thông thường không truy vấn `DiscoveryClient` để tìm instance. Client theo service ID cần tích hợp load balancing; nếu không có cơ chế này, HTTP client có thể coi service ID là hostname DNS bình thường và không tìm được địa chỉ.

## 2. Luồng xử lý của hai client

~~~mermaid
flowchart TB
    A["Ứng dụng order-service"]
    A --> B["Direct WebClient"]
    A --> C["Load-balanced WebClient"]
    B --> D["URL / hostname cố định"]
    D --> E["DNS và network routing"]
    E --> F["API đối tác hoặc legacy service"]
    C --> G["URI chứa service ID"]
    G --> H["Spring Cloud LoadBalancer"]
    H --> I["DiscoveryClient lấy danh sách instance"]
    I --> J["Chọn một ServiceInstance"]
    J --> K["HTTP request tới host và port đã chọn"]
~~~

Cả hai nhánh đều sử dụng HTTP và có thể dùng cùng các kiểu request/response của WebClient. Điểm khác biệt nằm ở bước giải quyết địa chỉ đích trước khi gửi request.

Với client thông thường, hostname trong URI được HTTP connector và hệ điều hành phân giải theo DNS/network routing. Với client load-balanced, hostname trong URI được hiểu là service ID để Spring Cloud LoadBalancer tìm instance. Vì vậy, không nên dùng nhầm builder hoặc client giữa hai mục đích.

## 3. Dependency cần thiết

Để dùng WebClient, ứng dụng cần starter WebFlux:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

Để dùng client theo service ID, cần Spring Cloud LoadBalancer tương thích với release train của ứng dụng:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
~~~

Ứng dụng còn cần một nguồn discovery instance. Đó có thể là provider như Eureka/Consul hoặc danh sách tĩnh từ SimpleDiscoveryClient trong môi trường phù hợp. LoadBalancer dùng dữ liệu discovery để chọn instance.

Chỉ thêm WebFlux starter không làm URI chứa service ID tự động được phân giải. Tương tự, chỉ có DiscoveryClient cũng không khiến mọi WebClient đều trở thành load-balanced client. Cần cấu hình đúng builder và dependency.

## 4. Khai báo hai WebClient riêng biệt

Một cách rõ ràng là tạo hai bean có tên khác nhau:

- `partnerWebClient`: gọi URL trực tiếp, không có load-balancer filter.
- `catalogWebClient`: được xây dựng từ `@LoadBalanced WebClient.Builder` để gọi service ID.

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class HttpClientConfiguration {

    @Bean("partnerWebClient")
    WebClient partnerWebClient() {
        return WebClient.builder()
                .baseUrl("https://api.partner.example")
                .build();
    }

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }

    @Bean("catalogWebClient")
    WebClient catalogWebClient(
            @LoadBalanced WebClient.Builder builder) {
        return builder.build();
    }
}
~~~

Ở đây, `@LoadBalanced` là qualifier đánh dấu builder được cấu hình cho service-name resolution. Bean `partnerWebClient` được tạo từ builder thông thường, vì vậy request của nó không bị gửi qua Spring Cloud LoadBalancer.

### 4.1. Vì sao nên đặt tên bean?

Một ứng dụng có thể có nhiều `WebClient` hoặc `WebClient.Builder`. Tên bean và qualifier giúp xác định đúng mục đích khi inject:

- `partnerWebClient` dành cho URL trực tiếp.
- `catalogWebClient` dành cho service ID.
- `loadBalancedWebClientBuilder` là builder đã được gắn cơ chế load balancing.

Không nên dựa vào thứ tự khai báo bean hoặc kỳ vọng Spring luôn chọn đúng builder khi có nhiều ứng viên cùng kiểu. Cũng không nên dùng `@Primary` để che giấu sự khác nhau về routing; hãy inject theo qualifier để ý định được thể hiện ngay tại nơi sử dụng.

### 4.2. Nếu ứng dụng có sẵn WebClient.Builder của Spring Boot

Spring Boot có thể cung cấp builder được auto-configure. Khi đồng thời có builder thông thường và builder có `@LoadBalanced`, inject theo qualifier là đặc biệt quan trọng. Nếu code cần builder thường, hãy dùng bean/qualifier tương ứng; nếu cần builder theo service ID, dùng qualifier `@LoadBalanced`.

Tránh thêm load-balancer filter thủ công vào một WebClient dùng chung cho mọi đích. Khi filter được gắn vào client trực tiếp, hostname của API đối tác có thể bị coi như service ID và request thất bại vì không có instance trong registry.

## 5. Gọi API bên ngoài bằng client thông thường

Client gọi API đối tác sử dụng URL hoặc base URL thông thường:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Service
public class PartnerPaymentClient {

    private final WebClient webClient;

    public PartnerPaymentClient(
            @Qualifier("partnerWebClient") WebClient webClient) {
        this.webClient = webClient;
    }

    public Mono<PaymentResponse> createPayment(
            PaymentRequest request) {
        return webClient.post()
                .uri("/v1/payments")
                .bodyValue(request)
                .retrieve()
                .bodyToMono(PaymentResponse.class);
    }
}
~~~

`baseUrl` của bean là `https://api.partner.example`, nên URI tương đối `/v1/payments` được gửi tới hostname đó. DNS, proxy, TLS và network routing của HTTP connector chịu trách nhiệm kết nối.

### 5.1. Trường hợp URL được xác định khi chạy

Nếu endpoint đến từ cấu hình, có thể đọc URL lúc tạo bean hoặc xây dựng URI theo logic ứng dụng. Ví dụ:

~~~yaml
partner:
  payment:
    base-url: https://payments.partner.example
~~~

Giá trị này có thể được bind bằng `@ConfigurationProperties` hoặc inject qua constructor. Nếu endpoint thay đổi runtime, hãy thiết kế cơ chế refresh cho client tương ứng; WebClient đã được tạo từ base URL cũ không tự thay đổi chỉ vì Environment được cập nhật.

Client thông thường vẫn có thể gọi dịch vụ nội bộ bằng DNS ổn định hoặc một load balancer của hạ tầng. Điểm phân biệt là nó không dùng service ID của Spring Cloud LoadBalancer.

## 6. Gọi dịch vụ nội bộ bằng service ID

Client gọi catalog dùng `catalogWebClient` đã được cấu hình `@LoadBalanced`:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Service
public class CatalogClient {

    private final WebClient webClient;

    public CatalogClient(
            @Qualifier("catalogWebClient") WebClient webClient) {
        this.webClient = webClient;
    }

    public Mono<CatalogItem> findById(String id) {
        return webClient.get()
                .uri("http://catalog-service/api/catalog/{id}", id)
                .retrieve()
                .bodyToMono(CatalogItem.class);
    }
}
~~~

Trong URI trên:

- `http` là scheme của request.
- `catalog-service` là service ID.
- `/api/catalog/{id}` là path của API trên instance được chọn.

Spring Cloud LoadBalancer lấy các instance của `catalog-service` qua discovery integration, chọn một instance theo policy và thay service ID bằng địa chỉ instance trước khi WebClient gửi request.

Không hard-code host/port của một instance vào client theo service ID. Mục tiêu của discovery là cho phép danh sách instance thay đổi mà code gọi dịch vụ vẫn dùng tên logic ổn định.

### 6.1. Cấu hình discovery instance

Trong local development hoặc integration test, có thể dùng SimpleDiscoveryClient để khai báo danh sách instance:

Prefix cấu hình là `spring.cloud.discovery.client.simple.instances`:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:9081
              - uri: http://localhost:9082
~~~

Khi có discovery provider động, danh sách có thể đến từ registry tương ứng. Không nên cấu hình đồng thời nhiều provider mà không xác định rõ nguồn instance mà LoadBalancer đang sử dụng.

### 6.2. Scheme và URI

Ví dụ dùng `http://catalog-service` để LoadBalancer nhận ra service ID. Địa chỉ thực tế của instance được lấy từ `ServiceInstance`. Cần kiểm tra scheme, cổng và TLS của các instance phù hợp với môi trường.

Nếu service dùng HTTPS, cấu hình URI và thông tin secure của provider phải nhất quán. Không chỉ đổi chuỗi `http` thành `https` mà bỏ qua truststore, chứng thư và hostname verification.

## 7. Sử dụng hai client trong cùng một service

Một service nghiệp vụ có thể cần gọi cả API đối tác lẫn catalog nội bộ. Inject hai bean riêng theo qualifier:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Service
public class OrderEnrichmentService {

    private final WebClient partnerWebClient;
    private final WebClient catalogWebClient;

    public OrderEnrichmentService(
            @Qualifier("partnerWebClient") WebClient partnerWebClient,
            @Qualifier("catalogWebClient") WebClient catalogWebClient) {
        this.partnerWebClient = partnerWebClient;
        this.catalogWebClient = catalogWebClient;
    }

    public Mono<OrderView> enrich(String productId) {
        Mono<CatalogItem> catalog =
                catalogWebClient.get()
                        .uri("http://catalog-service/api/catalog/{id}", productId)
                        .retrieve()
                        .bodyToMono(CatalogItem.class);

        Mono<PartnerStatus> partner =
                partnerWebClient.get()
                        .uri("/v1/status")
                        .retrieve()
                        .bodyToMono(PartnerStatus.class);

        return Mono.zip(catalog, partner)
                .map(tuple -> new OrderView(tuple.getT1(), tuple.getT2()));
    }
}
~~~

Hai request được tạo thành hai publisher và `Mono.zip` kết hợp kết quả khi cả hai hoàn tất. Ví dụ giả định các DTO và API đã tồn tại. Trong ứng dụng thực tế, cần đặt timeout, xử lý lỗi riêng cho từng dependency và xác định liệu một API có được phép thất bại mà vẫn trả kết quả hay không.

Không cần tạo hai ApplicationContext hoặc hai ứng dụng chỉ để dùng hai cách định tuyến HTTP. Hai WebClient bean có cấu hình khác nhau có thể cùng sống trong một context.

## 8. Khác biệt về lỗi và khả năng quan sát

Vì hai client dùng cơ chế định tuyến khác nhau, cách chẩn đoán cũng khác nhau.

| Triệu chứng | Client trực tiếp | Client theo service ID |
| --- | --- | --- |
| Không phân giải được hostname | Kiểm tra DNS, hosts, network namespace | Kiểm tra DiscoveryClient trả instance nào và host của instance có phân giải được không |
| Connection refused | Kiểm tra port đích, firewall và service đích | Kiểm tra instance được chọn, port và trạng thái service |
| Không tìm thấy service | Thường là lỗi DNS hoặc URL | Kiểm tra service ID, DiscoveryClient và LoadBalancer |
| Gọi nhầm instance | Kiểm tra URL/DNS/load balancer của hạ tầng | Kiểm tra danh sách instance và policy LoadBalancer |
| TLS handshake lỗi | Kiểm tra chứng thư, truststore và hostname | Kiểm tra TLS của instance được chọn và scheme/secure metadata |
| Timeout | Kiểm tra route và latency tới host trực tiếp | Kiểm tra discovery, lựa chọn instance, network và latency của instance |

Log nên ghi nhận loại client, service ID hoặc hostname đích ở mức an toàn, thời gian request, status code và correlation ID. Không ghi token, authorization header hoặc payload nhạy cảm.

Với client theo service ID, log URI trước khi LoadBalancer thay thế có thể chỉ hiển thị service ID. Muốn quan sát host/instance cuối cùng, dùng observation, tracing hoặc hook của LoadBalancer phù hợp với phiên bản thay vì tự suy luận từ URI đầu vào.

## 9. Timeout, retry và connection pool

Hai client có thể có yêu cầu vận hành khác nhau:

- API đối tác có thể cần timeout dài hơn, proxy riêng hoặc retry theo quota của đối tác.
- Service nội bộ có thể có timeout ngắn hơn và retry có giới hạn cho lỗi tạm thời.
- TLS, connection pool và giới hạn concurrency có thể khác nhau theo dependency.

Không nên áp dụng một chính sách retry chung cho mọi request. Retry một thao tác ghi có thể tạo giao dịch trùng nếu API không idempotent hoặc không hỗ trợ idempotency key. Cần phối hợp timeout, retry, circuit breaker và xử lý lỗi theo semantics của từng API.

WebClient được thiết kế để tái sử dụng. Hãy tạo bean dùng chung theo mục đích thay vì tạo một client mới cho mỗi request. Nếu cần connector hoặc connection pool riêng, có thể cấu hình riêng từng WebClient bean.

## 10. Kiểm thử hai kiểu client

Kiểm thử nên xác nhận không chỉ response mà cả đường định tuyến đã chọn.

### 10.1. Test client trực tiếp

Dùng mock HTTP server để xác nhận request của `partnerWebClient` đi tới URL trực tiếp và không cần discovery. Kiểm tra method, path, header, body, timeout và mapping response.

### 10.2. Test client theo service ID

Cấu hình một hoặc nhiều instance test trong SimpleDiscoveryClient hoặc fake DiscoveryClient. Dùng server stub tại các port tương ứng, gọi URI chứa service ID qua client `@LoadBalanced` và xác nhận request đến instance đã được LoadBalancer chọn.

Các điểm cần kiểm tra:

- Service ID trong URI khớp key cấu hình hoặc service ID trong registry.
- DiscoveryClient trả danh sách instance mong đợi.
- LoadBalancer chọn instance theo policy được cấu hình.
- Khi không có instance, request thất bại theo cách có thể quan sát và xử lý.
- Khi một instance không truy cập được, retry/fallback chỉ xảy ra nếu ứng dụng đã cấu hình.

### 10.3. Test tránh trộn hai cấu hình

Tạo một test có cả hai bean và xác nhận:

- Request tới URL đối tác không gọi DiscoveryClient.
- Request tới service ID có sử dụng LoadBalancer.
- Inject bean theo qualifier luôn chọn đúng client.
- Không có bean builder load-balanced bị dùng nhầm cho API trực tiếp.

Test này phát hiện lỗi cấu hình thường khó nhận ra khi hai client chỉ được kiểm tra riêng rẽ.

## 11. Các lỗi thường gặp

1. **Dùng load-balanced client cho mọi URL:** hostname API bên ngoài có thể bị hiểu thành service ID; tạo client trực tiếp riêng.
2. **Dùng client thường cho service ID:** HTTP connector có thể cố phân giải service ID như DNS; dùng builder có `@LoadBalanced`.
3. **Thiếu Spring Cloud LoadBalancer dependency:** annotation không tự cung cấp implementation nếu dependency không có.
4. **Inject nhầm builder:** dùng qualifier hoặc bean name thể hiện rõ mục đích.
5. **Dùng @Primary để che mơ hồ:** inject theo qualifier để không chọn nhầm routing behavior.
6. **Không có discovery provider hoặc instance list:** service ID không thể được phân giải; kiểm tra DiscoveryClient.
7. **Sai service ID:** tên trong URI phải khớp tên được đăng ký hoặc khai báo.
8. **Nghĩ rằng SimpleDiscoveryClient tự load balance:** discovery cung cấp instance; LoadBalancer chọn instance.
9. **Tái sử dụng một WebClient có filter không phù hợp:** tách bean theo loại đích và chính sách.
10. **Cấu hình timeout/retry chung cho mọi dependency:** thiết kế theo SLA và semantics từng API.
11. **Không kiểm tra TLS ở instance được chọn:** xác minh scheme, chứng thư và hostname.
12. **Tạo WebClient mỗi request:** tái sử dụng bean và connection pool.

## 12. Quy trình thiết kế trong ứng dụng Spring Cloud

Khi một service cần gọi cả endpoint trực tiếp và dịch vụ nội bộ:

1. Liệt kê từng dependency và xác định địa chỉ là URL/hostname trực tiếp hay service ID.
2. Tạo WebClient trực tiếp cho API đối tác hoặc endpoint DNS ổn định.
3. Tạo builder có `@LoadBalanced` cho request theo service ID.
4. Đặt tên bean và dùng `@Qualifier` tại constructor injection.
5. Cấu hình DiscoveryClient/provider và Spring Cloud LoadBalancer tương thích.
6. Đặt timeout, TLS, retry và connection pool theo từng loại dependency.
7. Kiểm thử direct routing và service-name routing riêng.
8. Kiểm thử cả trường hợp không có instance hoặc hostname không phân giải được.
9. Ghi log/tracing đủ để phân biệt lỗi DNS trực tiếp với lỗi discovery/load balancing.
10. Rà soát không có client load-balanced nào bị dùng cho API bên ngoài ngoài chủ đích.

**Điểm ghi nhớ:** HTTP client thông thường gửi request tới hostname/URL được phân giải qua DNS và network routing. Client theo tên dịch vụ dùng `@LoadBalanced WebClient.Builder` để Spring Cloud LoadBalancer lấy instance từ DiscoveryClient và chọn đích cho request. Hai client có thể cùng tồn tại trong một ApplicationContext; hãy tách bean và inject bằng qualifier để routing behavior, timeout và chính sách vận hành của từng dependency luôn rõ ràng trong **SPRING_CLOUD_CORE**.
